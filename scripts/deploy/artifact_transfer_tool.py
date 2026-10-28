#!/usr/bin/env python3
"""Ricezione atomica di artifact in staging privata IONOS (mai nella webroot)."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import tarfile
from datetime import datetime, timezone

import baseline_tool
import production_adapter
import production_publisher

PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
STAGING_ROOT = PRIVATE_ROOT / "staging"
INCOMING_ROOT = STAGING_ROOT / "incoming"
MAX_INVENTORY = 32 * 1024 * 1024
MAX_ARCHIVE = 2 * 1024 * 1024 * 1024
RESERVATION = "TRANSFER.json"
COMPLETE = "TRANSFER_COMPLETE"
TRANSFER_ID_RE = re.compile(r"^run-[0-9]+-[a-f0-9]{12}$")
TRANSFER_PROTOCOL = 2
PAYLOAD_FILES = {"sarafatto-release.tar.gz": ("archive_sha256", MAX_ARCHIVE),
                 "sarafatto-inventory.tsv": ("inventory_sha256", MAX_INVENTORY),
                 "sarafatto-provenance.json": ("provenance_sha256", 65536)}


class TransferError(Exception):
    """Rifiuto fail-closed della ricezione privata."""


def _require_posix():
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd):
        raise TransferError("Ricezione artifact richiede POSIX, openat e O_NOFOLLOW.")


def _open_child_dir(parent_fd, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        raise TransferError(f"Directory privata assente o non sicura: {name}.") from exc
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(fd)
        raise TransferError(f"Proprietario o permessi inattesi nella directory privata: {name}.")
    return fd


def _open_incoming():
    try:
        production_adapter._require_fixed_directory(PRIVATE_ROOT)
        production_adapter._require_fixed_directory(STAGING_ROOT)
        root_fd = production_adapter._open_checked_dir(PRIVATE_ROOT)
        staging_fd = _open_child_dir(root_fd, "staging")
        try:
            os.mkdir("incoming", 0o700, dir_fd=staging_fd)
            os.fsync(staging_fd)
        except FileExistsError:
            pass
        incoming_fd = _open_child_dir(staging_fd, "incoming")
        production_adapter._require_fixed_directory(INCOMING_ROOT)
        return root_fd, staging_fd, incoming_fd
    except Exception as exc:
        for descriptor in locals().get("incoming_fd",), locals().get("staging_fd",), locals().get("root_fd",):
            if descriptor is not None:
                os.close(descriptor)
        if isinstance(exc, production_adapter.ProductionAdapterError):
            raise TransferError(f"Root privata non verificabile: {exc}") from exc
        raise


def _read_at(directory_fd, name, limit):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as exc:
        raise TransferError(f"File assente o non apribile senza symlink: {name}.") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_size > limit):
            raise TransferError(f"File non regolare, hard link o oltre limite: {name}.")
        data = bytearray()
        while len(data) <= limit:
            block = os.read(fd, min(1024 * 1024, limit + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > limit:
            raise TransferError(f"File oltre limite durante la lettura: {name}.")
        after = os.fstat(fd)
        if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            raise TransferError(f"File cambiato durante la lettura: {name}.")
        return bytes(data)
    finally:
        os.close(fd)


def _hash_at(directory_fd, name, limit):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as exc:
        raise TransferError(f"File assente o non apribile senza symlink: {name}.") from exc
    digest = hashlib.sha256()
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or before.st_size > limit):
            raise TransferError(f"File non regolare, hard link o oltre limite: {name}.")
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise TransferError(f"File cambiato durante il digest: {name}.")
        return digest.hexdigest(), before.st_size
    finally:
        os.close(fd)


def _write_new_at(directory_fd, name, payload, mode=0o600):
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode, dir_fd=directory_fd)
    except OSError as exc:
        raise TransferError(f"Creazione esclusiva fallita: {name}.") from exc
    try:
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise TransferError(f"Scrittura incompleta: {name}.")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)


def _transfer_name(transfer_id):
    if not TRANSFER_ID_RE.fullmatch(str(transfer_id or "")):
        raise TransferError("Identificativo trasferimento non valido.")
    return transfer_id


def _read_reservation(transfer_fd, transfer_id, release_sha, run_id, toolchain_sha256):
    try:
        document = json.loads(_read_at(transfer_fd, RESERVATION, 16384).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TransferError("Prenotazione trasferimento malformata.") from exc
    fields = {"schema_version", "repository", "release_sha", "run_id", "ref", "transfer_id",
              "archive_sha256", "inventory_sha256", "provenance_sha256", "toolchain_sha256", "reserved_at_utc"}
    if (not isinstance(document, dict) or set(document) != fields
            or document.get("schema_version") != TRANSFER_PROTOCOL
            or document.get("repository") != production_publisher.GITHUB_REPOSITORY
            or document.get("release_sha") != release_sha or document.get("run_id") != run_id
            or document.get("ref") != "refs/heads/main" or document.get("transfer_id") != transfer_id
            or document.get("toolchain_sha256") != toolchain_sha256
            or not re.fullmatch(r"[a-f0-9]{64}", str(document.get("provenance_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(document.get("archive_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(document.get("inventory_sha256", "")))):
        raise TransferError("Prenotazione non corrispondente al run autorizzato.")
    return document


def toolchain_contract():
    """Identifica i moduli caricati senza consultare HEAD, branch o working tree Git."""
    directory = pathlib.Path(__file__).absolute().parent
    modules = {"artifact_transfer_tool.py": pathlib.Path(__file__).absolute(),
               "baseline_tool.py": pathlib.Path(baseline_tool.__file__).absolute(),
               "production_adapter.py": pathlib.Path(production_adapter.__file__).absolute(),
               "production_publisher.py": pathlib.Path(production_publisher.__file__).absolute(),
               "backup_tool.py": pathlib.Path(production_publisher.backup_tool.__file__).absolute(),
               "release_state_tool.py": pathlib.Path(production_publisher.release_state_tool.__file__).absolute()}
    files = []
    for name, path in sorted(modules.items()):
        if path != directory / name or path.resolve(strict=True) != path:
            raise TransferError(f"Modulo strumenti caricato da un percorso inatteso: {name}.")
        files.append({"file": name, "sha256": production_publisher._artifact_file_digest(path, 10 * 1024 * 1024)})
    contract = {"schema_version": 1, "transfer_protocol": TRANSFER_PROTOCOL,
                "provenance_schema": 1, "required_entries": list(production_publisher.REQUIRED_ENTRIES),
                "components": list(production_publisher.ALLOWED_COMPONENTS), "files": files}
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "compatible-toolchain", "toolchain_sha256": hashlib.sha256(raw).hexdigest(),
            "contract": contract}


def _validate_toolchain(expected):
    if not re.fullmatch(r"[a-f0-9]{64}", str(expected or "")):
        raise TransferError("Digest indipendente degli strumenti richiesto.")
    report = toolchain_contract()
    if report["toolchain_sha256"] != expected:
        raise TransferError("Strumenti server incompatibili con quelli autorizzati dalla CI.")
    return report


def _validate_identity(transfer_id, release_sha, run_id):
    if (not re.fullmatch(r"[a-f0-9]{40}", str(release_sha or ""))
            or not re.fullmatch(r"[0-9]+", str(run_id or ""))
            or _transfer_name(transfer_id) != f"run-{run_id}-{release_sha[:12]}"):
        raise TransferError("Commit, run ID o trasferimento non concordanti.")


def _lock_site_operation(locks_fd):
    try:
        import fcntl
        fd = os.open("site-operation.lock", os.O_RDWR | os.O_NOFOLLOW, dir_fd=locks_fd)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
            os.close(fd)
            raise TransferError("site-operation.lock non regolare o con permessi inattesi.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise TransferError("Operazione esclusiva attiva; staging rifiutato.") from exc
        return fd, fcntl
    except ImportError as exc:
        raise TransferError("flock non disponibile.") from exc


def _open_state_and_locks(root_fd):
    state_fd = _open_child_dir(root_fd, "state")
    try:
        locks_fd = _open_child_dir(root_fd, "locks")
        return state_fd, locks_fd
    except Exception:
        os.close(state_fd)
        raise


def reserve(transfer_id, release_sha, run_id, archive_sha256, inventory_sha256, *,
            provenance_sha256, toolchain_sha256):
    """Riserva una directory nuova; retry/replay dello stesso run non sovrascrive."""
    _require_posix()
    transfer_id = _transfer_name(transfer_id)
    _validate_identity(transfer_id, release_sha, run_id)
    if (not re.fullmatch(r"[a-f0-9]{40}", str(release_sha or ""))
            or not re.fullmatch(r"[0-9]+", str(run_id or ""))
            or not re.fullmatch(r"[a-f0-9]{64}", str(archive_sha256 or ""))
            or not re.fullmatch(r"[a-f0-9]{64}", str(inventory_sha256 or ""))
            or not re.fullmatch(r"[a-f0-9]{64}", str(provenance_sha256 or ""))
            or transfer_id != f"run-{run_id}-{release_sha[:12]}"):
        raise TransferError("SHA, run ID, digest o identificativo trasferimento non concordanti.")
    _validate_toolchain(toolchain_sha256)
    root_fd, staging_fd, incoming_fd = _open_incoming()
    state_fd = locks_fd = lock_fd = transfer_fd = None
    try:
        state_fd, locks_fd = _open_state_and_locks(root_fd)
        lock_fd, fcntl = _lock_site_operation(locks_fd)
        try:
            os.mkdir(transfer_id, 0o700, dir_fd=incoming_fd)
        except FileExistsError as exc:
            raise TransferError("Run già prenotato: replay o retry non autorizzato.") from exc
        os.fsync(incoming_fd)
        transfer_fd = _open_child_dir(incoming_fd, transfer_id)
        record = {
            "schema_version": TRANSFER_PROTOCOL, "repository": production_publisher.GITHUB_REPOSITORY,
            "release_sha": release_sha, "run_id": str(run_id), "ref": "refs/heads/main",
            "transfer_id": transfer_id, "archive_sha256": archive_sha256,
            "inventory_sha256": inventory_sha256,
            "provenance_sha256": provenance_sha256, "toolchain_sha256": toolchain_sha256,
            "reserved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        _write_new_at(transfer_fd, RESERVATION,
                      (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
        return {"status": "reserved-private-only", "transfer_id": transfer_id,
                "remote_directory": str(INCOMING_ROOT / transfer_id), "public_writes_performed": False}
    finally:
        if transfer_fd is not None:
            os.close(transfer_fd)
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if locks_fd is not None:
            os.close(locks_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(incoming_fd)
        os.close(staging_fd)
        os.close(root_fd)


def receive(transfer_id, release_sha, run_id, name, *, toolchain_sha256, stream):
    """Riceve stdin SSH solo in un nome fisso prenotato, senza sovrascritture."""
    _require_posix()
    _validate_identity(transfer_id, release_sha, run_id)
    _validate_toolchain(toolchain_sha256)
    if name not in PAYLOAD_FILES:
        raise TransferError("Nome payload fuori allowlist.")
    root_fd, staging_fd, incoming_fd = _open_incoming()
    state_fd = locks_fd = lock_fd = transfer_fd = payload_fd = None
    try:
        state_fd, locks_fd = _open_state_and_locks(root_fd)
        lock_fd, fcntl = _lock_site_operation(locks_fd)
        transfer_fd = _open_child_dir(incoming_fd, transfer_id)
        reservation = _read_reservation(transfer_fd, transfer_id, release_sha, run_id, toolchain_sha256)
        if COMPLETE in os.listdir(transfer_fd):
            raise TransferError("Trasferimento già completo: ricezione rifiutata.")
        try:
            payload_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=transfer_fd)
        except FileExistsError as exc:
            raise TransferError("Payload già presente: nessuna sovrascrittura consentita.") from exc
        digest, size = hashlib.sha256(), 0
        key, limit = PAYLOAD_FILES[name]
        while True:
            block = stream.read(min(1024 * 1024, limit + 1 - size))
            if not block:
                break
            size += len(block)
            if size > limit:
                raise TransferError("Payload ricevuto oltre limite.")
            digest.update(block)
            view = memoryview(block)
            while view:
                count = os.write(payload_fd, view)
                if count <= 0:
                    raise TransferError("Scrittura payload incompleta.")
                view = view[count:]
        os.fsync(payload_fd)
        os.fsync(transfer_fd)
        if digest.hexdigest() != reservation[key]:
            raise TransferError("Digest payload ricevuto diverso dalla prenotazione; parziale conservato.")
        return {"status": "received-private-only", "file": name, "sha256": digest.hexdigest(),
                "bytes": size, "transfer_id": transfer_id, "public_writes_performed": False}
    finally:
        if payload_fd is not None:
            os.close(payload_fd)
        if transfer_fd is not None:
            os.close(transfer_fd)
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        for descriptor in (locks_fd, state_fd, incoming_fd, staging_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _parse_inventory(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise TransferError("Inventario trasferito non UTF-8.") from exc
    records = {}
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 3:
            raise TransferError(f"Inventario malformato alla riga {number}.")
        digest, size_text, path = fields
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or not size_text.isdigit()
                or not baseline_tool.safe_path(path) or baseline_tool.excluded(path)
                or not production_publisher._in_component(path)
                or path in records):
            raise TransferError(f"Record inventario non valido: {path!r}.")
        records[path] = {"sha256": digest, "size": int(size_text)}
    if not records:
        raise TransferError("Inventario trasferito vuoto.")
    for component in production_publisher.ALLOWED_COMPONENTS:
        if component == production_publisher.ALLOWED_COMPONENTS[2]:
            if component not in records:
                raise TransferError("MU-plugin autorizzato assente dall'inventario.")
        elif not any(path.startswith(component + "/") for path in records):
            raise TransferError(f"Componente vuoto o assente: {component}.")
    return records


def _open_or_create_dir(parent_fd, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    return _open_child_dir(parent_fd, name)


def _extract_archive(transfer_fd, archive_fd, inventory_bytes, records):
    """Estrae in una nuova directory privata con mkdirat/openat esclusivi."""
    try:
        archive_stream = os.fdopen(os.dup(archive_fd), "rb")
        archive = tarfile.open(fileobj=archive_stream, mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise TransferError("Archivio tar.gz malformato.") from exc
    expected = {f"sarafatto-release/{path}": row for path, row in records.items()}
    expected["sarafatto-inventory.tsv"] = {
        "sha256": hashlib.sha256(inventory_bytes).hexdigest(), "size": len(inventory_bytes)}
    directories = set()
    for path in expected:
        parent = pathlib.PurePosixPath(path).parent
        while str(parent) != ".":
            directories.add(str(parent))
            parent = parent.parent
    found_files, found_dirs = set(), set()
    total_extracted = 0
    package_fd = None
    try:
        os.mkdir("package", 0o700, dir_fd=transfer_fd)
        os.fsync(transfer_fd)
        package_fd = _open_child_dir(transfer_fd, "package")
        with archive_stream, archive:
            members = archive.getmembers()
            if len(members) > 50000 or len(members) != len(expected) + len(directories):
                raise TransferError("Numero di membri archivio diverso dall'inventario.")
            for member in members:
                name = member.name.rstrip("/") if member.isdir() else member.name
                if (not name or name.startswith("/") or "\\" in name
                        or pathlib.PurePosixPath(name).as_posix() != name
                        or any(part in ("", ".", "..") for part in name.split("/"))):
                    raise TransferError(f"Path traversal o nome non canonico nell'archivio: {member.name!r}.")
                if member.isdir():
                    if name not in directories or name in found_dirs:
                        raise TransferError(f"Directory inattesa o duplicata nell'archivio: {name}.")
                    found_dirs.add(name)
                    if name.startswith("sarafatto-release/"):
                        components = name.removeprefix("sarafatto-release/").split("/")
                        parent_fd = os.dup(package_fd)
                        try:
                            for part in components:
                                child_fd = _open_or_create_dir(parent_fd, part)
                                os.close(parent_fd)
                                parent_fd = child_fd
                        finally:
                            os.close(parent_fd)
                    continue
                if not member.isfile() or name not in expected or name in found_files:
                    raise TransferError(f"Membro speciale, inatteso o duplicato: {name}.")
                mode = stat.S_IMODE(member.mode)
                if member.size != expected[name]["size"] or mode & 0o022 or mode & 0o6000:
                    raise TransferError(f"Dimensione o permessi archive non sicuri: {name}.")
                source = archive.extractfile(member)
                if source is None:
                    raise TransferError(f"Contenuto archive non leggibile: {name}.")
                digest, size = hashlib.sha256(), 0
                if name == "sarafatto-inventory.tsv":
                    file_parent_fd, filename = transfer_fd, "inventory.tsv"
                else:
                    relative = name.removeprefix("sarafatto-release/").split("/")
                    file_parent_fd = os.dup(package_fd)
                    for part in relative[:-1]:
                        next_fd = _open_child_dir(file_parent_fd, part)
                        os.close(file_parent_fd)
                        file_parent_fd = next_fd
                    filename = relative[-1]
                try:
                    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 mode or 0o600, dir_fd=file_parent_fd)
                    try:
                        os.fchmod(fd, mode or 0o600)
                        with source:
                            while True:
                                block = source.read(1024 * 1024)
                                if not block:
                                    break
                                digest.update(block)
                                size += len(block)
                                total_extracted += len(block)
                                if total_extracted > MAX_ARCHIVE:
                                    raise TransferError("Dimensione decompressa complessiva oltre il limite.")
                                offset = 0
                                while offset < len(block):
                                    offset += os.write(fd, block[offset:])
                        if size != expected[name]["size"] or digest.hexdigest() != expected[name]["sha256"]:
                            raise TransferError(f"SHA-256 archivio diverso dall'inventario: {name}.")
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    os.fsync(file_parent_fd)
                finally:
                    if file_parent_fd != transfer_fd:
                        os.close(file_parent_fd)
                found_files.add(name)
        if found_files != set(expected) or found_dirs != directories:
            raise TransferError("Archivio incompleto rispetto all'inventario autorizzato.")
        os.fsync(package_fd)
        return package_fd
    except Exception:
        if package_fd is not None:
            os.close(package_fd)
        raise


def verify(transfer_id, release_sha, run_id, *, toolchain_sha256):
    """Verifica trasferimento, estrae in privato e pubblica marker COMPLETE per ultimo."""
    _require_posix()
    transfer_id = _transfer_name(transfer_id)
    _validate_identity(transfer_id, release_sha, run_id)
    _validate_toolchain(toolchain_sha256)
    root_fd, staging_fd, incoming_fd = _open_incoming()
    state_fd = locks_fd = lock_fd = transfer_fd = package_fd = None
    try:
        state_fd, locks_fd = _open_state_and_locks(root_fd)
        lock_fd, fcntl = _lock_site_operation(locks_fd)
        transfer_fd = _open_child_dir(incoming_fd, transfer_id)
        names = set(os.listdir(transfer_fd))
        reservation = _read_reservation(transfer_fd, transfer_id, release_sha, run_id, toolchain_sha256)
        allowed = {RESERVATION, "sarafatto-release.tar.gz", "sarafatto-inventory.tsv",
                   "sarafatto-provenance.json"}
        completed_names = allowed | {COMPLETE, "package", "inventory.tsv"}
        if names not in (allowed, completed_names):
            raise TransferError("Trasferimento incompleto o con file inattesi; nessun recupero automatico.")
        # Anche le verifiche ripetute ricalcolano tutti i digest originariamente
        # ricevuti; il solo marker COMPLETE non costituisce una prova.
        for name, (key, limit) in PAYLOAD_FILES.items():
            actual_digest, _ = _hash_at(transfer_fd, name, limit)
            if actual_digest != reservation[key]:
                raise TransferError("Digest ricevuti diversi da quelli prenotati nel run GitHub.")
        if names == completed_names:
            try:
                marker = json.loads(_read_at(transfer_fd, COMPLETE, 4096).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise TransferError("Marker COMPLETE malformato.") from exc
            package_path = INCOMING_ROOT / transfer_id / "package"
            inventory_path = INCOMING_ROOT / transfer_id / "inventory.tsv"
            archive_path = INCOMING_ROOT / transfer_id / "sarafatto-release.tar.gz"
            provenance_path = INCOMING_ROOT / transfer_id / "sarafatto-provenance.json"
            records = production_publisher.verify_artifact(
                package_path, inventory_path, release_sha, provenance_path=provenance_path,
                archive_path=archive_path, expected_run_id=run_id)
            marker_fields = {"schema_version", "transfer_id", "release_sha", "run_id",
                             "archive_sha256", "inventory_sha256", "provenance_sha256", "toolchain_sha256",
                             "verified_files", "verified_at_utc"}
            if (not isinstance(marker, dict) or set(marker) != marker_fields
                    or marker.get("schema_version") != TRANSFER_PROTOCOL or marker.get("release_sha") != release_sha
                    or marker.get("run_id") != run_id
                    or marker.get("transfer_id") != transfer_id
                    or any(marker.get(key) != reservation[key] for key in
                           ("archive_sha256", "inventory_sha256", "provenance_sha256", "toolchain_sha256"))
                    or marker.get("verified_files") != len(records)
                    or not isinstance(marker.get("verified_at_utc"), str)):
                raise TransferError("Marker COMPLETE non concorda con artifact verificato.")
            return {"status": "verified-private-artifact", "transfer_id": transfer_id,
                    "release_sha": release_sha, "archive_sha256": marker["archive_sha256"],
                    "toolchain_sha256": toolchain_sha256,
                    "public_writes_performed": False}
        inventory_bytes = _read_at(transfer_fd, "sarafatto-inventory.tsv", MAX_INVENTORY)
        provenance_raw = _read_at(transfer_fd, "sarafatto-provenance.json", 65536)
        archive_digest, _ = _hash_at(transfer_fd, "sarafatto-release.tar.gz", MAX_ARCHIVE)
        inventory_digest = hashlib.sha256(inventory_bytes).hexdigest()
        if (archive_digest != reservation.get("archive_sha256")
                or inventory_digest != reservation.get("inventory_sha256")):
            raise TransferError("Digest ricevuti diversi da quelli prenotati nel run GitHub.")
        try:
            provenance = json.loads(provenance_raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TransferError("Provenance trasferita malformata.") from exc
        if (not isinstance(provenance, dict) or provenance.get("repository") != reservation["repository"]
                or provenance.get("commit_sha") != release_sha or provenance.get("run_id") != run_id
                or provenance.get("ref") != "refs/heads/main"
                or provenance.get("archive_sha256") != reservation["archive_sha256"]
                or provenance.get("inventory_sha256") != reservation["inventory_sha256"]):
            raise TransferError("Provenance non concorda con la prenotazione SSH e i digest.")
        records = _parse_inventory(inventory_bytes)
        archive_fd = os.open("sarafatto-release.tar.gz", os.O_RDONLY | os.O_NOFOLLOW,
                             dir_fd=transfer_fd)
        try:
            package_fd = _extract_archive(transfer_fd, archive_fd, inventory_bytes, records)
        finally:
            os.close(archive_fd)
        inventory_from_tar = _read_at(transfer_fd, "inventory.tsv", MAX_INVENTORY)
        if inventory_from_tar != inventory_bytes:
            raise TransferError("Inventario contenuto nell'archivio diverso da quello trasferito.")
        package_path = INCOMING_ROOT / transfer_id / "package"
        publisher_records = production_publisher.verify_artifact(
            package_path, INCOMING_ROOT / transfer_id / "inventory.tsv", release_sha,
            provenance_path=INCOMING_ROOT / transfer_id / "sarafatto-provenance.json",
            archive_path=INCOMING_ROOT / transfer_id / "sarafatto-release.tar.gz",
            expected_run_id=run_id)
        marker = {"schema_version": TRANSFER_PROTOCOL, "transfer_id": transfer_id, "release_sha": release_sha,
                  "run_id": run_id, "archive_sha256": reservation["archive_sha256"],
                  "inventory_sha256": reservation["inventory_sha256"],
                  "provenance_sha256": reservation["provenance_sha256"], "toolchain_sha256": toolchain_sha256,
                  "verified_files": len(publisher_records),
                  "verified_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
        _write_new_at(transfer_fd, COMPLETE,
                      (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode())
        return {"status": "verified-private-artifact", **marker, "public_writes_performed": False}
    finally:
        if package_fd is not None:
            os.close(package_fd)
        if transfer_fd is not None:
            os.close(transfer_fd)
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if locks_fd is not None:
            os.close(locks_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(incoming_fd)
        os.close(staging_fd)
        os.close(root_fd)


def publisher_inputs(transfer_id, release_sha, run_id, *, toolchain_sha256):
    """Espone i percorsi solo dopo riverifica completa; non invoca il publisher."""
    result = verify(transfer_id, release_sha, run_id, toolchain_sha256=toolchain_sha256)
    directory = INCOMING_ROOT / transfer_id
    return {**result, "run_id": run_id, "publisher_inputs": {
        "package": str(directory / "package"), "inventory": str(directory / "inventory.tsv"),
        "archive": str(directory / "sarafatto-release.tar.gz"),
        "provenance": str(directory / "sarafatto-provenance.json")}}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    reserve_parser = commands.add_parser("reserve", help="prenota directory privata non riutilizzabile")
    verify_parser = commands.add_parser("verify", help="verifica artifact ricevuto e lo estrae in privato")
    receive_parser = commands.add_parser("receive", help="riceve un file su stdin senza sovrascriverlo")
    inputs_parser = commands.add_parser("publisher-inputs", help="riverifica e restituisce input privati verificati")
    tools_parser = commands.add_parser("toolchain", help="contratto read-only degli strumenti caricati")
    tools_parser.add_argument("--expected-toolchain-sha256")
    for command in (reserve_parser, verify_parser, receive_parser, inputs_parser):
        command.add_argument("--transfer-id", required=True)
        command.add_argument("--release-sha", required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--toolchain-sha256", required=True)
    reserve_parser.add_argument("--archive-sha256", required=True)
    reserve_parser.add_argument("--inventory-sha256", required=True)
    reserve_parser.add_argument("--provenance-sha256", required=True)
    receive_parser.add_argument("--name", required=True, choices=sorted(PAYLOAD_FILES))
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "toolchain":
            result = (_validate_toolchain(args.expected_toolchain_sha256)
                      if args.expected_toolchain_sha256 else toolchain_contract())
        elif args.command == "reserve":
            result = reserve(args.transfer_id, args.release_sha, args.run_id,
                             args.archive_sha256, args.inventory_sha256,
                             provenance_sha256=args.provenance_sha256, toolchain_sha256=args.toolchain_sha256)
        elif args.command == "receive":
            result = receive(args.transfer_id, args.release_sha, args.run_id, args.name,
                             toolchain_sha256=args.toolchain_sha256, stream=sys.stdin.buffer)
        else:
            operation = verify if args.command == "verify" else publisher_inputs
            result = operation(args.transfer_id, args.release_sha, args.run_id,
                               toolchain_sha256=args.toolchain_sha256)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (TransferError, production_publisher.PublisherError, production_adapter.ProductionAdapterError,
            OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"ERRORE: trasferimento non verificato: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
