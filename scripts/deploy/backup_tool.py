#!/usr/bin/env python3
"""Backup applicativo verificato e simulazione di restore in area privata."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import tarfile
import uuid
from datetime import datetime, timezone

import baseline_tool as baseline


PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
PUBLIC_WP_CONTENT = pathlib.Path("/home/www/public/wp-content")
BACKUP_SCHEMA = 1
BACKUP_ARCHIVE = "payload.tar.gz"
MAX_MANIFEST_BYTES = 20_000_000
MAX_PAYLOAD_BYTES = 50 * 1024**3
SPACE_MARGIN_BYTES = 16 * 1024**2
SPACE_MARGIN_PERCENT = 5
BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")


class BackupError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def read_regular_bytes(path, label, expected_mode=None, limit=None):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise BackupError(f"{label} non è un file regolare.")
        if expected_mode is not None and os.name == "posix" and stat.S_IMODE(info.st_mode) != expected_mode:
            raise BackupError(f"Permessi inattesi per {label}.")
        if os.name == "posix" and hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise BackupError(f"Proprietario inatteso per {label}.")
        if limit is not None and info.st_size > limit:
            raise BackupError(f"{label} supera la dimensione massima consentita.")
        data = stream.read(None if limit is None else limit + 1)
        if limit is not None and len(data) > limit:
            raise BackupError(f"{label} supera la dimensione massima consentita.")
        return data


def read_json_no_duplicates(raw, label):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BackupError(f"Chiave JSON duplicata in {label}: {key}.")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError(f"JSON non valido: {label}.") from exc


def require_regular(path, label, expected_mode=None):
    try:
        info = path.lstat()
    except OSError as exc:
        raise BackupError(f"{label} assente o illeggibile: {path}.") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise BackupError(f"{label} non è un file regolare: {path}.")
    if expected_mode is not None and os.name == "posix" and stat.S_IMODE(info.st_mode) != expected_mode:
        raise BackupError(f"Permessi inattesi per {label}: {path}.")
    if os.name == "posix" and hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise BackupError(f"Proprietario inatteso per {label}: {path}.")
    return info


def require_private_directories(private_root, expected_root):
    state_dir, locks_dir = baseline.validate_private_state(private_root, expected_root)
    root = pathlib.Path(private_root)
    result = {"state": state_dir, "locks": locks_dir}
    for name in ("backups", "staging"):
        directory = root / name
        try:
            info = directory.lstat()
        except OSError as exc:
            raise BackupError(f"Directory privata assente: {directory}.") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise BackupError(f"Directory privata non valida: {directory}.")
        if os.name == "posix":
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise BackupError(f"Proprietario o permessi inattesi: {directory}.")
        result[name] = directory
    return result


def open_directory_at(parent_fd, name, label):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not os.open in os.supports_dir_fd:
        raise BackupError("Operazioni private sicure richiedono openat/O_NOFOLLOW su POSIX.")
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        raise BackupError(f"Directory assente o non sicura: {label}.") from exc
    info = os.fstat(descriptor)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(descriptor)
        raise BackupError(f"Proprietario, tipo o permessi inattesi: {label}.")
    return descriptor


def open_private_directories(private_root, expected_root):
    """Apre e mantiene ancorate le directory private tramite descriptor POSIX."""
    paths = require_private_directories(private_root, expected_root)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not os.open in os.supports_dir_fd:
        raise BackupError("Backup e restore-test richiedono openat/O_NOFOLLOW su POSIX.")
    root = pathlib.Path(private_root)
    if root.resolve(strict=True) != root:
        raise BackupError("Root privata non canonica o raggiunta tramite symlink.")
    parent_fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_fd = os.open(root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except Exception:
        os.close(parent_fd)
        raise
    descriptors = {"root_parent_fd": parent_fd, "root_fd": root_fd}
    try:
        root_info = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid()
                or stat.S_IMODE(root_info.st_mode) != 0o700):
            raise BackupError("Root privata sostituita o con proprietario/permessi inattesi.")
        for name in ("state", "locks", "backups", "staging"):
            descriptors[name + "_fd"] = open_directory_at(root_fd, name, name)
        descriptors["paths"] = paths
        descriptors["root"] = root
        assert_directory_still_named(parent_fd, root.name, root_fd, "root privata")
        return descriptors
    except Exception:
        close_private_directories(descriptors)
        raise


def close_private_directories(descriptors):
    for name, descriptor in list(descriptors.items()):
        if name.endswith("_fd") and isinstance(descriptor, int):
            try:
                os.close(descriptor)
            except OSError:
                pass


def assert_directory_still_named(parent_fd, name, child_fd, label):
    """Blocca se il nome atteso è stato sostituito dopo l'apertura ancorata."""
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(child_fd)
    except OSError as exc:
        raise BackupError(f"Directory privata sostituita o non accessibile: {label}.") from exc
    if (not stat.S_ISDIR(named.st_mode) or stat.S_ISLNK(named.st_mode)
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)):
        raise BackupError(f"Directory privata sostituita durante l'operazione: {label}.")


def assert_private_root_still_named(private):
    assert_directory_still_named(private["root_parent_fd"], private["root"].name,
                                 private["root_fd"], "root privata")


def assert_private_child_still_named(private, name):
    assert_directory_still_named(private["root_fd"], name, private[name + "_fd"], name)


def available_bytes_at(directory_fd):
    values = os.fstatvfs(directory_fd)
    return values.f_bavail * values.f_frsize


def open_at_regular_bytes(directory_fd, name, label, expected_mode=None, limit=None):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as exc:
        raise BackupError(f"{label} assente o non apribile in sicurezza.") from exc
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise BackupError(f"{label} non è un file regolare.")
        if expected_mode is not None and stat.S_IMODE(info.st_mode) != expected_mode:
            raise BackupError(f"Permessi inattesi per {label}.")
        if info.st_uid != os.getuid():
            raise BackupError(f"Proprietario inatteso per {label}.")
        if limit is not None and info.st_size > limit:
            raise BackupError(f"{label} supera la dimensione massima consentita.")
        data = stream.read(None if limit is None else limit + 1)
        if limit is not None and len(data) > limit:
            raise BackupError(f"{label} supera la dimensione massima consentita.")
        return data


def stat_regular_at(directory_fd, name, label, expected_mode=None):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as exc:
        raise BackupError(f"{label} assente o non apribile in sicurezza.") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise BackupError(f"{label} non è un file regolare o ha proprietario inatteso.")
        if expected_mode is not None and stat.S_IMODE(info.st_mode) != expected_mode:
            raise BackupError(f"Permessi inattesi per {label}.")
        return info
    finally:
        os.close(descriptor)


def write_at(directory_fd, name, payload, mode=0o600):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
    descriptor = os.open(name, flags, mode, dir_fd=directory_fd)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def validate_id(backup_id):
    if not isinstance(backup_id, str) or not BACKUP_ID_RE.fullmatch(backup_id):
        raise BackupError("Backup ID non valido.")
    return backup_id


def validate_backup_baseline(path, expected_sha256, state_fd=None):
    if state_fd is None:
        path = pathlib.Path(path)
        info = require_regular(path, "Baseline", 0o600)
        if info.st_size > MAX_MANIFEST_BYTES:
            raise BackupError("Baseline troppo grande.")
        raw = read_regular_bytes(path, "Baseline", 0o600, MAX_MANIFEST_BYTES)
    else:
        raw = open_at_regular_bytes(state_fd, "baseline.json", "Baseline", 0o600, MAX_MANIFEST_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256 or "") or digest != expected_sha256:
        raise BackupError("SHA-256 della baseline assente o non corrispondente.")
    document = read_json_no_duplicates(raw, "baseline")
    if (document.get("schema_version") != 1
            or document.get("verification", {}).get("status") != "initialized-from-verified-content-match"
            or document.get("verification", {}).get("managed_symlinks") != 0):
        raise BackupError("Schema o stato della baseline non valido.")
    release_sha = document.get("release", {}).get("commit_sha", "")
    if not re.fullmatch(r"[a-f0-9]{40}", release_sha):
        raise BackupError("Commit SHA della baseline non valido.")

    expected = {}
    for group, classification in (("managed_files", "artifact"), ("accepted_extras", None)):
        records = document.get(group)
        if not isinstance(records, list):
            raise BackupError(f"Elenco {group} non valido nella baseline.")
        for row in records:
            if not isinstance(row, dict):
                raise BackupError(f"Record {group} non valido nella baseline.")
            relative = row.get("path")
            if not baseline.safe_path(relative) or baseline.excluded(relative):
                raise BackupError(f"Percorso baseline non consentito: {relative}.")
            digest_value, size, mode = row.get("sha256"), row.get("size"), row.get("mode")
            if (not re.fullmatch(r"[a-f0-9]{64}", str(digest_value))
                    or not isinstance(size, int) or isinstance(size, bool) or size < 0
                    or not re.fullmatch(r"[0-7]{3,5}", str(mode))):
                raise BackupError(f"Hash, dimensione o permessi baseline non validi: {relative}.")
            item_class = row.get("classification", classification)
            if group == "managed_files" and item_class != "artifact":
                raise BackupError(f"Classificazione file gestito non valida: {relative}.")
            if group == "accepted_extras" and not isinstance(item_class, str):
                raise BackupError(f"Classificazione extra non valida: {relative}.")
            if relative in expected:
                raise BackupError(f"Percorso duplicato nella baseline: {relative}.")
            expected[relative] = {
                "path": relative, "sha256": digest_value, "size": size,
                "mode": str(mode), "classification": item_class,
            }
    if not expected:
        raise BackupError("La baseline non contiene file applicativi.")
    return document, digest, release_sha, expected


def parse_inventory_text(text):
    files, symlinks, exclusion = baseline.parse_remote_text(text)
    canonical = {
        "files": [{"path": path, **files[path]} for path in sorted(files)],
        "symlinks": sorted(symlinks, key=lambda row: row["path"]),
        "exclusion": exclusion,
    }
    return files, symlinks, exclusion, baseline.digest_json(canonical)


def compare_inventory_to_baseline(files, symlinks, exclusion, expected):
    if exclusion.get("path") != baseline.EXCLUDED + "/":
        raise BackupError("L'esclusione node_modules non corrisponde al perimetro previsto.")
    if symlinks:
        names = ", ".join(row["path"] for row in symlinks[:10])
        raise BackupError("Symlink nei percorsi gestiti: " + names)
    missing = sorted(set(expected) - set(files))
    unexpected = sorted(set(files) - set(expected))
    changed = sorted(path for path in set(expected) & set(files) if any(
        expected[path][key] != files[path][key] for key in ("sha256", "size", "mode")
    ))
    if missing or unexpected or changed:
        raise BackupError(
            f"Filesystem diverso dalla baseline: mancanti={len(missing)}, "
            f"extra={len(unexpected)}, modificati={len(changed)}. "
            f"Esempi: {', '.join((missing + unexpected + changed)[:12])}"
        )
    return {"files": len(files), "extras": len(expected) - len([p for p, v in expected.items() if v["classification"] == "artifact"]),
            "excluded_node_modules_files": exclusion["files"],
            "excluded_node_modules_symlinks": exclusion["symlinks"]}


def open_public_file(public_root, relative):
    if not baseline.safe_path(relative) or baseline.excluded(relative):
        raise BackupError(f"Percorso pubblico non consentito: {relative}.")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise BackupError("Backup richiede openat/O_NOFOLLOW su POSIX.")
    root = pathlib.Path(public_root)
    descriptor = None
    try:
        root_info = root.lstat()
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode) or root.resolve(strict=True) != root:
            raise BackupError("Root WordPress non canonica o symlink.")
        flags_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        descriptor = os.open(root, flags_dir)
        parts = relative.split("/")
        for part in parts[:-1]:
            next_fd = os.open(part, flags_dir, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
        parent_fd = descriptor
        descriptor = None
        return file_fd, parent_fd
    except (OSError, RuntimeError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Impossibile aprire in sicurezza il file pubblico {relative}.") from exc


def check_capacity(quota_free_bytes, disk_free_bytes, source_bytes):
    if not isinstance(quota_free_bytes, int) or isinstance(quota_free_bytes, bool) or quota_free_bytes <= 0:
        raise BackupError("Quota libera account non confermata: controllare IONOS e fornire il limite approvato.")
    if source_bytes < 0 or source_bytes > MAX_PAYLOAD_BYTES:
        raise BackupError("Dimensione totale del backup non valida o oltre il limite operativo.")
    required = 2 * source_bytes + max(SPACE_MARGIN_BYTES, source_bytes * SPACE_MARGIN_PERCENT // 100)
    if disk_free_bytes < required:
        raise BackupError(f"Spazio filesystem insufficiente: servono almeno {required} byte, df ne indica {disk_free_bytes}.")
    if quota_free_bytes < required:
        raise BackupError(f"Quota account insufficiente: servono almeno {required} byte, quota approvata {quota_free_bytes}.")
    return required


class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, amount=-1):
        data = self.stream.read(amount)
        self.digest.update(data)
        self.bytes_read += len(data)
        return data


def archive_public_files(public_root, private_dir_fd, expected):
    descriptor = os.open(BACKUP_ARCHIVE, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                         0o600, dir_fd=private_dir_fd)
    with os.fdopen(descriptor, "wb") as archive_stream:
        with tarfile.open(fileobj=archive_stream, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
            for relative in sorted(expected):
                expected_row = expected[relative]
                file_fd, parent_fd = open_public_file(public_root, relative)
                try:
                    before = os.fstat(file_fd)
                    mode = format(stat.S_IMODE(before.st_mode), "o")
                    if (not stat.S_ISREG(before.st_mode) or before.st_size != expected_row["size"]
                            or mode != expected_row["mode"]):
                        raise BackupError(f"File cambiato o tipo/permessi inattesi durante il backup: {relative}.")
                    source = os.fdopen(file_fd, "rb", closefd=False)
                    hashing = HashingReader(source)
                    info = tarfile.TarInfo(name=relative)
                    info.type = tarfile.REGTYPE
                    info.size = before.st_size
                    info.mode = stat.S_IMODE(before.st_mode)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    archive.addfile(info, hashing)
                    after = os.fstat(file_fd)
                    source.close()
                    if (hashing.bytes_read != before.st_size or hashing.digest.hexdigest() != expected_row["sha256"]
                            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                        raise BackupError(f"Contenuto cambiato durante la lettura: {relative}.")
                finally:
                    os.close(file_fd)
                    os.close(parent_fd)
        archive_stream.flush()
        os.fsync(archive_stream.fileno())
        os.fchmod(archive_stream.fileno(), 0o600)


def manifest_for(backup_id, baseline_sha, baseline_commit, baseline_document, expected,
                 archive_size, archive_sha256):
    return {
        "schema_version": BACKUP_SCHEMA,
        "status": "complete",
        "backup_id": backup_id,
        "created_at_utc": utc_now(),
        "baseline": {
            "sha256": baseline_sha,
            "commit_sha": baseline_commit,
            "identifier": baseline_document.get("release", {}).get("release_id"),
        },
        "scope": {
            "public_root": str(PUBLIC_WP_CONTENT),
            "included_roots": ["themes/sarafatto/", "plugins/sarafatto-core/",
                               "mu-plugins/sarafatto-polylang-front-page-url.php"],
            "excluded": [baseline.EXCLUDED + "/"],
        },
        "archive": {"file": BACKUP_ARCHIVE, "size": archive_size,
                    "sha256": archive_sha256},
        "files": [expected[path] for path in sorted(expected)],
    }


def safe_manifest_files(manifest):
    if (manifest.get("schema_version") != BACKUP_SCHEMA or manifest.get("status") != "complete"
            or not BACKUP_ID_RE.fullmatch(str(manifest.get("backup_id", "")))):
        raise BackupError("Versione, stato o ID del manifest backup non validi.")
    baseline_info = manifest.get("baseline")
    if (not isinstance(baseline_info, dict)
            or not re.fullmatch(r"[a-f0-9]{64}", str(baseline_info.get("sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{40}", str(baseline_info.get("commit_sha", "")))):
        raise BackupError("Riferimento baseline non valido nel manifest.")
    scope = manifest.get("scope", {})
    if (scope.get("public_root") != str(PUBLIC_WP_CONTENT)
            or scope.get("excluded") != [baseline.EXCLUDED + "/"]
            or scope.get("included_roots") != ["themes/sarafatto/", "plugins/sarafatto-core/",
                                                "mu-plugins/sarafatto-polylang-front-page-url.php"]):
        raise BackupError("Esclusioni backup non valide.")
    archive = manifest.get("archive", {})
    if (archive.get("file") != BACKUP_ARCHIVE or not isinstance(archive.get("size"), int)
            or archive["size"] < 1 or not re.fullmatch(r"[a-f0-9]{64}", str(archive.get("sha256", "")))):
        raise BackupError("Descrizione archivio non valida.")
    records = manifest.get("files")
    if not isinstance(records, list) or not records or len(records) > 20000:
        raise BackupError("Elenco file del manifest non valido.")
    files = {}
    total = 0
    for row in records:
        if not isinstance(row, dict):
            raise BackupError("Record file del manifest non valido.")
        relative = row.get("path")
        size, mode, digest_value = row.get("size"), row.get("mode"), row.get("sha256")
        if (not baseline.safe_path(relative) or baseline.excluded(relative)
                or not re.fullmatch(r"[a-f0-9]{64}", str(digest_value))
                or not isinstance(size, int) or isinstance(size, bool) or size < 0
                or not re.fullmatch(r"[0-7]{3,5}", str(mode))
                or not isinstance(row.get("classification"), str)):
            raise BackupError(f"Record file non sicuro o malformato: {relative}.")
        if relative in files:
            raise BackupError(f"Percorso duplicato nel manifest: {relative}.")
        files[relative] = {"path": relative, "sha256": digest_value, "size": size,
                           "mode": str(mode), "classification": row["classification"]}
        total += size
    if total > MAX_PAYLOAD_BYTES:
        raise BackupError("Payload oltre il limite operativo.")
    return files, total


def verify_backup_directory(directory, backup_id, expected_baseline_sha=None,
                            expected_manifest_sha256=None, require_complete=True, directory_fd=None):
    validate_id(backup_id)
    owned_fd = directory_fd is None
    if owned_fd:
        if os.name != "posix" or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
            raise BackupError("Verifica backup richiede openat/O_DIRECTORY/O_NOFOLLOW su POSIX.")
        directory = pathlib.Path(directory)
        try:
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise BackupError(f"Backup assente o non sicuro: {directory}.") from exc
    try:
        dir_info = os.fstat(directory_fd)
        if (not stat.S_ISDIR(dir_info.st_mode)
                or (os.name == "posix" and (dir_info.st_uid != os.getuid()
                    or stat.S_IMODE(dir_info.st_mode) != 0o700))):
            raise BackupError("Proprietario, permessi o tipo directory backup inattesi.")
        entries = set(os.listdir(directory_fd))
        return _verify_backup_directory_fd(directory_fd, entries, backup_id, expected_baseline_sha,
                                           expected_manifest_sha256, require_complete)
    finally:
        if owned_fd:
            os.close(directory_fd)


def _verify_backup_directory_fd(directory_fd, entries, backup_id, expected_baseline_sha,
                                expected_manifest_sha256, require_complete):
    allowed = {BACKUP_ARCHIVE, "manifest.json", "manifest.sha256", "COMPLETE"}
    if set(entries) - allowed or not {BACKUP_ARCHIVE, "manifest.json", "manifest.sha256"}.issubset(entries):
        raise BackupError("Backup incompleto o con file non previsti.")
    if require_complete and "COMPLETE" not in entries:
        raise BackupError("Backup incompleto: marker COMPLETE assente.")
    for name in entries:
        stat_regular_at(directory_fd, name, "File backup", 0o600)
    raw = open_at_regular_bytes(directory_fd, "manifest.json", "Manifest", 0o600, MAX_MANIFEST_BYTES)
    manifest_digest = hashlib.sha256(raw).hexdigest()
    if expected_manifest_sha256 is not None and manifest_digest != expected_manifest_sha256:
        raise BackupError("SHA-256 manifest diverso dal valore conservato alla creazione del backup.")
    checksum_line = open_at_regular_bytes(directory_fd, "manifest.sha256", "SHA manifest", 0o600, 256).decode("ascii")
    if checksum_line != f"{manifest_digest}  manifest.json\n":
        raise BackupError("SHA-256 manifest non corrispondente.")
    if require_complete and open_at_regular_bytes(directory_fd, "COMPLETE", "Marker COMPLETE", 0o600, 128).decode("ascii") != manifest_digest + "\n":
        raise BackupError("Marker COMPLETE non corrispondente al manifest.")
    manifest = read_json_no_duplicates(raw, "manifest backup")
    if manifest.get("backup_id") != backup_id:
        raise BackupError("Backup ID del manifest diverso dal percorso richiesto.")
    if expected_baseline_sha and manifest.get("baseline", {}).get("sha256") != expected_baseline_sha:
        raise BackupError("Backup appartenente a una baseline differente.")
    files, total = safe_manifest_files(manifest)
    archive_fd = os.open(BACKUP_ARCHIVE, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    archive_stream = os.fdopen(archive_fd, "rb")
    archive_info = os.fstat(archive_stream.fileno())
    if not stat.S_ISREG(archive_info.st_mode) or stat.S_IMODE(archive_info.st_mode) != 0o600:
        archive_stream.close()
        raise BackupError("Archivio backup non regolare o con permessi inattesi.")
    archive_metadata = manifest["archive"]
    digest = hashlib.sha256()
    for block in iter(lambda: archive_stream.read(1024 * 1024), b""):
        digest.update(block)
    if archive_info.st_size != archive_metadata["size"] or digest.hexdigest() != archive_metadata["sha256"]:
        archive_stream.close()
        raise BackupError("Archivio troncato o SHA-256 non corrispondente.")
    archive_stream.seek(0)
    try:
        with tarfile.open(fileobj=archive_stream, mode="r:gz") as archive:
            members = archive.getmembers()
            seen = set()
            for member in members:
                name = member.name
                if (not baseline.safe_path(name) or baseline.excluded(name) or name in seen
                        or not member.isfile() or member.issym() or member.islnk()
                        or member.isdev() or member.isfifo()):
                    raise BackupError(f"Membro TAR non sicuro: {name}.")
                seen.add(name)
                row = files.get(name)
                if row is None or member.size != row["size"] or format(member.mode & 0o7777, "o") != row["mode"]:
                    raise BackupError(f"Membro TAR inatteso o metadata diverso: {name}.")
                stream = archive.extractfile(member)
                if stream is None:
                    raise BackupError(f"Membro TAR illeggibile: {name}.")
                digest_value = hashlib.sha256()
                count = 0
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest_value.update(block)
                    count += len(block)
                if count != row["size"] or digest_value.hexdigest() != row["sha256"]:
                    raise BackupError(f"Contenuto archivio alterato: {name}.")
            if seen != set(files):
                raise BackupError("Archivio incompleto: mancano file del manifest.")
    except (tarfile.TarError, EOFError, OSError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError("Archivio TAR.GZ troncato, malformato o non leggibile.") from exc
    finally:
        archive_stream.close()
    return {"manifest": manifest, "manifest_sha256": manifest_digest,
            "files": files, "total_bytes": total, "archive_size": archive_info.st_size}


def inventory_text_for_backup(baseline_commit_sha):
    return baseline.acquire_fresh_inventory(baseline_commit_sha)


def create_backup(backup_id, baseline_sha256, quota_free_bytes, *,
                  private_root=PRIVATE_ROOT, expected_private_root=PRIVATE_ROOT,
                  public_root=PUBLIC_WP_CONTENT, baseline_path=None):
    validate_id(backup_id)
    if baseline_path is not None and pathlib.Path(baseline_path) != pathlib.Path(private_root) / "state" / "baseline.json":
        raise BackupError("Percorso baseline arbitrario non consentito.")
    private = open_private_directories(private_root, expected_private_root)
    paths = private["paths"]
    try:
        assert_private_root_still_named(private)
        assert_private_child_still_named(private, "locks")
        lock_fd = baseline.acquire_baseline_lock(paths["locks"], private["locks_fd"])
    except Exception:
        close_private_directories(private)
        raise
    temporary_name = None
    temporary_fd = None
    try:
        assert_private_child_still_named(private, "locks")
        document, baseline_digest, commit_sha, expected = validate_backup_baseline(
            None, baseline_sha256, state_fd=private["state_fd"])
        assert_private_child_still_named(private, "state")
        assert_private_root_still_named(private)
        assert_directory_still_named(private["root_fd"], "backups", private["backups_fd"], "backups")
        try:
            os.stat(backup_id, dir_fd=private["backups_fd"], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise BackupError("Backup ID già esistente: nessuna sovrascrittura consentita.")
        first_text = inventory_text_for_backup(commit_sha)
        files, symlinks, exclusion, first_digest = parse_inventory_text(first_text)
        summary = compare_inventory_to_baseline(files, symlinks, exclusion, expected)
        total_bytes = sum(row["size"] for row in expected.values())
        disk_free = available_bytes_at(private["root_fd"])
        required = check_capacity(quota_free_bytes, disk_free, total_bytes)

        assert_private_root_still_named(private)
        assert_directory_still_named(private["root_fd"], "backups", private["backups_fd"], "backups")
        temporary_name = ".incomplete-" + backup_id + "-" + uuid.uuid4().hex[:8]
        os.mkdir(temporary_name, 0o700, dir_fd=private["backups_fd"])
        temporary_fd = open_directory_at(private["backups_fd"], temporary_name, "backup temporaneo")
        archive_public_files(public_root, temporary_fd, expected)
        archive_fd = os.open(BACKUP_ARCHIVE, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=temporary_fd)
        with os.fdopen(archive_fd, "rb") as archive_stream:
            archive_info = os.fstat(archive_stream.fileno())
            archive_digest = hashlib.sha256()
            for block in iter(lambda: archive_stream.read(1024 * 1024), b""):
                archive_digest.update(block)
        manifest = manifest_for(backup_id, baseline_digest, commit_sha, document, expected,
                                archive_info.st_size, archive_digest.hexdigest())
        raw = json_bytes(manifest)
        manifest_hash = hashlib.sha256(raw).hexdigest()
        write_at(temporary_fd, "manifest.json", raw)
        write_at(temporary_fd, "manifest.sha256", f"{manifest_hash}  manifest.json\n".encode("ascii"))
        verify_backup_directory(None, backup_id, baseline_digest, manifest_hash,
                                require_complete=False, directory_fd=temporary_fd)
        write_at(temporary_fd, "COMPLETE", (manifest_hash + "\n").encode("ascii"))
        verify_backup_directory(None, backup_id, baseline_digest, manifest_hash,
                                require_complete=True, directory_fd=temporary_fd)

        second_text = inventory_text_for_backup(commit_sha)
        after_files, after_links, after_exclusion, second_digest = parse_inventory_text(second_text)
        compare_inventory_to_baseline(after_files, after_links, after_exclusion, expected)
        if first_digest != second_digest:
            raise BackupError("Filesystem pubblico cambiato durante la creazione del backup.")
        assert_private_root_still_named(private)
        assert_directory_still_named(private["root_fd"], "backups", private["backups_fd"], "backups")
        rename_backup_noreplace(temporary_name, backup_id, directory_fd=private["backups_fd"])
        os.fsync(private["backups_fd"])
        return {"backup_id": backup_id, "path": str(paths["backups"] / backup_id), "baseline_sha256": baseline_digest,
                "baseline_commit": commit_sha, "files": summary["files"], "extras": summary["extras"],
                "bytes": total_bytes, "required_free_bytes": required,
                "account_quota_free_bytes_confirmed": quota_free_bytes,
                "archive_bytes": manifest["archive"]["size"], "manifest_sha256": manifest_hash}
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        import fcntl
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        close_private_directories(private)


def rename_backup_noreplace(source, destination, directory_fd=None):
    if os.name != "posix" or directory_fd is None:
        raise BackupError("Finalizzazione sicura richiede renameat2 e directory descriptor POSIX.")
    import ctypes
    import errno
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise BackupError("renameat2(RENAME_NOREPLACE) non disponibile: finalizzazione bloccata.")
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    result = renameat2(directory_fd, os.fsencode(source), directory_fd, os.fsencode(destination), 1)
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise BackupError("Backup ID già esistente: nessuna sovrascrittura consentita.")
    raise OSError(error, os.strerror(error), str(destination))


def verify_backup(backup_id, baseline_sha256, manifest_sha256, *, private_root=PRIVATE_ROOT,
                  expected_private_root=PRIVATE_ROOT):
    validate_id(backup_id)
    private = open_private_directories(private_root, expected_private_root)
    paths = private["paths"]
    try:
        assert_private_root_still_named(private)
        assert_private_child_still_named(private, "locks")
        lock_fd = baseline.acquire_baseline_lock(paths["locks"], private["locks_fd"])
    except Exception:
        close_private_directories(private)
        raise
    backup_fd = None
    try:
        assert_private_child_still_named(private, "locks")
        _, digest, commit_sha, expected = validate_backup_baseline(
            None, baseline_sha256, state_fd=private["state_fd"])
        assert_private_child_still_named(private, "state")
        assert_directory_still_named(private["root_fd"], "backups", private["backups_fd"], "backups")
        backup_fd = open_directory_at(private["backups_fd"], backup_id, "backup")
        result = verify_backup_directory(None, backup_id, baseline_sha256, manifest_sha256,
                                         directory_fd=backup_fd)
        verify_manifest_matches_baseline(result["manifest"], digest, commit_sha, expected)
        return {"backup_id": backup_id, "path": str(paths["backups"] / backup_id), "manifest_sha256": result["manifest_sha256"],
                "files": len(result["files"]), "bytes": result["total_bytes"],
                "archive_bytes": result["archive_size"], "baseline_sha256": baseline_sha256,
                "status": "verified"}
    finally:
        if backup_fd is not None:
            os.close(backup_fd)
        import fcntl
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        close_private_directories(private)


def validate_restore_destination(destination, staging_dir):
    destination = pathlib.Path(destination)
    staging_dir = pathlib.Path(staging_dir)
    if destination.is_absolute() is False or staging_dir.resolve(strict=True) != staging_dir:
        raise BackupError("Root staging non valida.")
    if destination.parent != staging_dir or destination.exists() or destination.is_symlink():
        raise BackupError("Destinazione restore-test non consentita o già esistente.")
    if destination.name in ("", ".", ".."):
        raise BackupError("Nome destinazione restore-test non valido.")
    return destination


def verify_manifest_matches_baseline(manifest, baseline_sha256, commit_sha, expected):
    if (manifest.get("baseline", {}).get("sha256") != baseline_sha256
            or manifest.get("baseline", {}).get("commit_sha") != commit_sha):
        raise BackupError("Backup appartenente a una baseline o release differente.")
    manifest_files, _ = safe_manifest_files(manifest)
    if manifest_files != expected:
        raise BackupError("Elenco, SHA-256, dimensioni o permessi del backup diversi dalla baseline approvata.")


def extract_verified_archive(backup_fd, verification, staging_fd, destination_name, display_path):
    validate_id(verification["manifest"]["backup_id"])
    os.mkdir(destination_name, 0o700, dir_fd=staging_fd)
    destination_fd = open_directory_at(staging_fd, destination_name, "destinazione restore-test")
    restored_fd = None
    os.mkdir("restored", 0o700, dir_fd=destination_fd)
    restored_fd = open_directory_at(destination_fd, "restored", "albero restore-test")
    files = verification["files"]
    try:
        archive_descriptor = os.open(BACKUP_ARCHIVE, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=backup_fd)
        with os.fdopen(archive_descriptor, "rb") as archive_stream, tarfile.open(fileobj=archive_stream, mode="r:gz") as archive:
            seen = set()
            for member in archive.getmembers():
                relative = member.name
                row = files.get(relative)
                if (row is None or not baseline.safe_path(relative) or baseline.excluded(relative)
                        or not member.isfile() or member.issym() or member.islnk()
                        or member.isdev() or member.isfifo() or relative in seen
                        or member.size != row["size"]
                        or format(member.mode & 0o7777, "o") != row["mode"]):
                    raise BackupError(f"Membro non previsto durante restore-test: {relative}.")
                seen.add(relative)
                current_fd = os.dup(restored_fd)
                parts = relative.split("/")
                try:
                    for part in parts[:-1]:
                        try:
                            os.mkdir(part, 0o700, dir_fd=current_fd)
                        except FileExistsError:
                            pass
                        next_fd = open_directory_at(current_fd, part, "directory di estrazione")
                        os.close(current_fd)
                        current_fd = next_fd
                    target_name = parts[-1]
                except Exception:
                    os.close(current_fd)
                    raise
                stream = archive.extractfile(member)
                if stream is None:
                    os.close(current_fd)
                    raise BackupError(f"Membro TAR illeggibile: {relative}.")
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
                descriptor = os.open(target_name, flags, 0o600, dir_fd=current_fd)
                digest_value = hashlib.sha256()
                count = 0
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            output.write(block)
                            digest_value.update(block)
                            count += len(block)
                        output.flush()
                        os.fsync(output.fileno())
                    row = files[relative]
                    if count != row["size"] or digest_value.hexdigest() != row["sha256"]:
                        raise BackupError(f"Verifica SHA post-estrazione fallita: {relative}.")
                    verify_fd = os.open(target_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
                    try:
                        os.fchmod(verify_fd, int(row["mode"], 8))
                        os.fsync(verify_fd)
                    finally:
                        os.close(verify_fd)
                finally:
                    stream.close()
                    os.close(current_fd)
            if seen != set(files):
                raise BackupError("Archivio cambiato durante il restore-test: elenco incompleto.")
        verify_restored_tree_fd(restored_fd, files)
        assert_directory_still_named(staging_fd, destination_name, destination_fd, "staging restore-test")
        report = {
            "status": "restore-test-passed",
            "backup_id": verification["manifest"]["backup_id"],
            "baseline": verification["manifest"]["baseline"],
            "restore_test_path": display_path + "/restored",
            "files_verified": len(files),
            "bytes_verified": verification["total_bytes"],
            "completed_at_utc": utc_now(),
            "public_wordpress_modified": False,
        }
        write_at(destination_fd, "restore-test-report.json", json_bytes(report))
        return report
    except Exception as exc:
        error_report = {"status": "restore-test-failed", "error": str(exc), "backup_id": verification["manifest"]["backup_id"],
                        "restore_test_path": display_path, "public_wordpress_modified": False,
                        "failed_at_utc": utc_now()}
        try:
            write_at(destination_fd, "restore-test-report.json", json_bytes(error_report))
        except (OSError, BackupError):
            pass
        raise
    finally:
        if restored_fd is not None:
            os.close(restored_fd)
        os.close(destination_fd)


def verify_restored_tree_fd(root_fd, expected_files):
    found = {}

    def visit(directory_fd, prefix=""):
        for name in os.listdir(directory_fd):
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            relative = f"{prefix}/{name}" if prefix else name
            if stat.S_ISLNK(info.st_mode):
                raise BackupError(f"Symlink estratto inatteso: {relative}.")
            if stat.S_ISDIR(info.st_mode):
                child_fd = open_directory_at(directory_fd, name, "directory estratta")
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
                with os.fdopen(descriptor, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    digest = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                    row = expected_files.get(relative)
                    if (row is None or opened.st_size != row["size"]
                            or format(stat.S_IMODE(opened.st_mode), "o") != row["mode"]
                            or digest.hexdigest() != row["sha256"]):
                        raise BackupError(f"Integrità post-restore non valida: {relative}.")
                    found[relative] = True
            else:
                raise BackupError(f"File speciale estratto inatteso: {relative}.")

    visit(root_fd)
    if set(found) != set(expected_files):
        raise BackupError("Albero ripristinato con file mancanti o inattesi.")


def restore_test(backup_id, baseline_sha256, manifest_sha256, quota_free_bytes, *,
                 private_root=PRIVATE_ROOT, expected_private_root=PRIVATE_ROOT, disk_free_bytes=None):
    validate_id(backup_id)
    private = open_private_directories(private_root, expected_private_root)
    paths = private["paths"]
    try:
        assert_private_root_still_named(private)
        assert_private_child_still_named(private, "locks")
        lock_fd = baseline.acquire_baseline_lock(paths["locks"], private["locks_fd"])
    except Exception:
        close_private_directories(private)
        raise
    backup_fd = None
    try:
        assert_private_child_still_named(private, "locks")
        assert_directory_still_named(private["root_fd"], "backups", private["backups_fd"], "backups")
        assert_private_root_still_named(private)
        assert_directory_still_named(private["root_fd"], "staging", private["staging_fd"], "staging")
        backup_fd = open_directory_at(private["backups_fd"], backup_id, "backup")
        verification = verify_backup_directory(None, backup_id, baseline_sha256, manifest_sha256,
                                               directory_fd=backup_fd)
        _, digest, commit_sha, expected = validate_backup_baseline(
            None, baseline_sha256, state_fd=private["state_fd"])
        assert_private_child_still_named(private, "state")
        verify_manifest_matches_baseline(verification["manifest"], digest, commit_sha, expected)
        disk_free = disk_free_bytes if disk_free_bytes is not None else available_bytes_at(private["root_fd"])
        required = verification["total_bytes"] + SPACE_MARGIN_BYTES
        if not isinstance(quota_free_bytes, int) or isinstance(quota_free_bytes, bool) or quota_free_bytes <= 0:
            raise BackupError("Quota libera account non confermata per restore-test.")
        if disk_free < required or quota_free_bytes < required:
            raise BackupError(f"Spazio insufficiente per restore-test: richiesti {required} byte.")
        assert_private_root_still_named(private)
        assert_directory_still_named(private["root_fd"], "staging", private["staging_fd"], "staging")
        name = "restore-test-" + backup_id + "-" + uuid.uuid4().hex[:8]
        report = extract_verified_archive(backup_fd, verification, private["staging_fd"], name,
                                          str(paths["staging"] / name))
        report["required_free_bytes"] = required
        return report
    finally:
        if backup_fd is not None:
            os.close(backup_fd)
        import fcntl
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        close_private_directories(private)


def list_backups(*, private_root=PRIVATE_ROOT, expected_private_root=PRIVATE_ROOT):
    private = open_private_directories(private_root, expected_private_root)
    results = []
    try:
        for name in sorted(os.listdir(private["backups_fd"])):
            if name.startswith(".incomplete-"):
                results.append({"path": name, "status": "incomplete-or-interrupted"})
                continue
            try:
                entry_fd = open_directory_at(private["backups_fd"], name, "backup")
                try:
                    raw = open_at_regular_bytes(entry_fd, "manifest.json", "Manifest", 0o600, MAX_MANIFEST_BYTES)
                    manifest = read_json_no_duplicates(raw, "manifest")
                    backup_id = manifest.get("backup_id")
                    result = verify_backup_directory(None, backup_id, directory_fd=entry_fd)
                    results.append({"backup_id": backup_id, "status": "self-consistent; external digest required",
                                    "files": len(result["files"]),
                                    "baseline_sha256": manifest["baseline"]["sha256"]})
                finally:
                    os.close(entry_fd)
            except Exception as exc:
                results.append({"path": name, "status": "anomaly-or-invalid", "error": str(exc)})
        return results
    finally:
        close_private_directories(private)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup", help="crea backup verificato nella root privata")
    create.add_argument("--baseline-sha256", required=True)
    create.add_argument("--account-quota-free-bytes", required=True, type=int,
                        help="quota libera verificata manualmente su IONOS")
    verify = commands.add_parser("verify", help="verifica un backup senza modificarlo")
    verify.add_argument("--backup-id", required=True)
    verify.add_argument("--baseline-sha256", required=True)
    verify.add_argument("--manifest-sha256", required=True,
                        help="SHA-256 manifest conservato indipendentemente alla creazione")
    restore = commands.add_parser("restore-test", help="simula il ripristino solo in staging privata")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--baseline-sha256", required=True)
    restore.add_argument("--manifest-sha256", required=True,
                         help="SHA-256 manifest conservato indipendentemente alla creazione")
    restore.add_argument("--account-quota-free-bytes", required=True, type=int,
                         help="quota libera verificata manualmente su IONOS")
    commands.add_parser("list", help="elenca backup autoconsistenti, incompleti e anomalie")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "backup":
            backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
            result = create_backup(backup_id, args.baseline_sha256, args.account_quota_free_bytes)
        elif args.command == "verify":
            result = verify_backup(args.backup_id, args.baseline_sha256, args.manifest_sha256)
        elif args.command == "restore-test":
            result = restore_test(args.backup_id, args.baseline_sha256, args.manifest_sha256,
                                  args.account_quota_free_bytes)
        else:
            result = {"backups": list_backups()}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (BackupError, baseline.BaselineError, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
