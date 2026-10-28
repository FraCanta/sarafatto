#!/usr/bin/env python3
"""Controllo release IONOS: verifica e preflight read-only, senza writer pubblico.

Il comando `publish` resta intenzionalmente fail-closed: la barriera HTTP/PHP e
la coerenza OPcache non sono ancora provate in modo sufficiente per proteggere
richieste WordPress reali. Questo modulo non contiene primitive di scrittura
sotto /home/www/public.
"""

import argparse
import hashlib
import json
import os
import pathlib
import posixpath
import re
import stat
import sys
import tarfile
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone

import baseline_tool
import backup_tool
import production_adapter
import release_state_tool

REPOSITORY_ROOT = pathlib.Path("/home/www/sarafatto-repo")
PUBLIC_ROOT = pathlib.Path("/home/www/public/wp-content")
PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
REQUIRED_ENTRIES = (
    "assets/src/js/app.js",
    "assets/src/js/home.js",
    "assets/src/js/product.js",
    "assets/src/js/product-archive.js",
)
ALLOWED_COMPONENTS = (
    "themes/sarafatto",
    "plugins/sarafatto-core",
    "mu-plugins/sarafatto-polylang-front-page-url.php",
)
PUBLIC_WRITER_ENABLED = False
GITHUB_REPOSITORY = "FraCanta/sarafatto"


class PublisherError(Exception):
    """Errore di verifica o rifiuto fail-closed del publisher."""


def _sha256(path, expected_info):
    if os.name == "posix" and not hasattr(os, "O_NOFOLLOW"):
        raise PublisherError("Verifica artefatto POSIX senza O_NOFOLLOW non supportata.")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise PublisherError(f"Apertura no-follow dell'asset fallita: {path.name}.") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (expected_info.st_dev, expected_info.st_ino)
                or opened.st_size != expected_info.st_size):
            raise PublisherError(f"Asset sostituito o non regolare durante la verifica: {path.name}.")
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
        if (after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns):
            raise PublisherError(f"Asset cambiato durante la verifica: {path.name}.")
    finally:
        os.close(fd)
    return digest.hexdigest()


def _read_regular(path, limit):
    try:
        before = pathlib.Path(path).lstat()
    except OSError as exc:
        raise PublisherError(f"File assente o illeggibile: {path}.") from exc
    if (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1 or before.st_size > limit):
        raise PublisherError(f"File non regolare, hard link o oltre limite: {path}.")
    if os.name == "posix" and not hasattr(os, "O_NOFOLLOW"):
        raise PublisherError("Lettura artefatto POSIX senza O_NOFOLLOW non supportata.")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise PublisherError(f"Apertura no-follow fallita: {path}.") from exc
    try:
        opened = os.fstat(fd)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or opened.st_size > limit):
            raise PublisherError(f"File sostituito durante la lettura: {path}.")
        data = bytearray()
        while len(data) <= limit:
            block = os.read(fd, min(1024 * 1024, limit + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > limit:
            raise PublisherError(f"File oltre limite durante la lettura: {path}.")
        after = os.fstat(fd)
        if (after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns):
            raise PublisherError(f"File cambiato durante la lettura: {path}.")
        return bytes(data)
    finally:
        os.close(fd)


def _verify_archive_contents(archive_path, inventory_bytes, records):
    """Verifica i byte dell'archivio senza estrarlo e rifiuta membri speciali."""
    archive_path = pathlib.Path(archive_path)
    try:
        before = archive_path.lstat()
    except OSError as exc:
        raise PublisherError("Archivio release assente o illeggibile.") from exc
    if (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1 or before.st_size > 2 * 1024 * 1024 * 1024):
        raise PublisherError("Archivio release non regolare o oltre il limite.")
    if os.name == "posix" and not hasattr(os, "O_NOFOLLOW"):
        raise PublisherError("Verifica archivio POSIX senza O_NOFOLLOW non supportata.")
    try:
        fd = os.open(archive_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise PublisherError("Apertura no-follow dell'archivio fallita.") from exc

    expected = {f"sarafatto-release/{name}": row for name, row in records.items()}
    expected["sarafatto-inventory.tsv"] = {
        "sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "size": len(inventory_bytes),
    }
    required_directories = set()
    for name in expected:
        parent = posixpath.dirname(name)
        while parent:
            required_directories.add(parent)
            parent = posixpath.dirname(parent)
    found_files = set()
    found_directories = set()
    total = 0
    try:
        opened = os.fstat(fd)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or opened.st_size != before.st_size):
            raise PublisherError("Archivio sostituito durante la verifica.")
        with os.fdopen(os.dup(fd), "rb") as archive_stream:
            try:
                with tarfile.open(fileobj=archive_stream, mode="r:gz") as archive:
                    for member in archive:
                        if len(found_files) + len(found_directories) >= len(expected) + len(required_directories):
                            raise PublisherError("Numero di membri archivio superiore al contenuto atteso.")
                        name = member.name.rstrip("/") if member.isdir() else member.name
                        if (not name or name.startswith("/") or "\\" in name
                                or posixpath.normpath(name) != name
                                or any(part in ("", ".", "..") for part in name.split("/"))):
                            raise PublisherError(f"Percorso non sicuro nell'archivio: {member.name!r}.")
                        if member.isdir():
                            if name not in required_directories or name in found_directories:
                                raise PublisherError(f"Directory inattesa o duplicata nell'archivio: {name}.")
                            found_directories.add(name)
                            continue
                        if not member.isfile() or name not in expected or name in found_files:
                            raise PublisherError(f"Membro inatteso, speciale o duplicato nell'archivio: {name}.")
                        row = expected[name]
                        if member.size != row["size"]:
                            raise PublisherError(f"Dimensione archivio non coerente: {name}.")
                        if name.startswith("sarafatto-release/"):
                            package_path = name.removeprefix("sarafatto-release/")
                            expected_mode = int(records[package_path]["mode"], 8)
                            if stat.S_IMODE(member.mode) != expected_mode:
                                raise PublisherError(f"Permessi archivio non coerenti: {name}.")
                        source = archive.extractfile(member)
                        if source is None:
                            raise PublisherError(f"Contenuto archivio non leggibile: {name}.")
                        digest = hashlib.sha256()
                        read_size = 0
                        with source:
                            while True:
                                block = source.read(1024 * 1024)
                                if not block:
                                    break
                                read_size += len(block)
                                total += len(block)
                                if total > 2 * 1024 * 1024 * 1024:
                                    raise PublisherError("Contenuto archivio oltre il limite totale.")
                                digest.update(block)
                        if read_size != row["size"] or digest.hexdigest() != row["sha256"]:
                            raise PublisherError(f"Hash archivio diverso dal pacchetto verificato: {name}.")
                        found_files.add(name)
            except (OSError, tarfile.TarError, EOFError) as exc:
                raise PublisherError("Archivio tar.gz malformato o illeggibile.") from exc
        if found_files != set(expected) or found_directories != required_directories:
            missing = sorted(set(expected) - found_files)
            raise PublisherError(f"Archivio incompleto; membri mancanti: {missing[:5]}.")
        after = os.fstat(fd)
        if (after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns):
            raise PublisherError("Archivio cambiato durante la verifica.")
    finally:
        os.close(fd)


def _artifact_file_digest(path, limit):
    try:
        info = pathlib.Path(path).lstat()
    except OSError as exc:
        raise PublisherError("Archivio release assente o illeggibile.") from exc
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1 or info.st_size > limit):
        raise PublisherError("Archivio release non regolare o oltre il limite.")
    return _sha256(pathlib.Path(path), info)


def _in_component(path):
    return (path == ALLOWED_COMPONENTS[2]
            or path.startswith(ALLOWED_COMPONENTS[0] + "/")
            or path.startswith(ALLOWED_COMPONENTS[1] + "/"))


def _allowed_directory(path):
    return (path in ("themes", "plugins", "mu-plugins", "themes/sarafatto",
                     "plugins/sarafatto-core")
            or path.startswith("themes/sarafatto/")
            or path.startswith("plugins/sarafatto-core/"))


def _walk_package(package_root):
    """Inventaria senza seguire symlink e rifiuta contenuti fuori allowlist."""
    root = pathlib.Path(package_root)
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise PublisherError("Directory artefatto assente o non leggibile.") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise PublisherError("Root artefatto non è una directory regolare.")
    records = {}

    def visit(directory, relative):
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise PublisherError(f"Directory artefatto illeggibile: {relative}.") from exc
        for entry in entries:
            rel = f"{relative}/{entry.name}" if relative else entry.name
            try:
                info = entry.lstat()
            except OSError as exc:
                raise PublisherError(f"File artefatto cambiato durante la lettura: {rel}.") from exc
            if stat.S_ISLNK(info.st_mode):
                raise PublisherError(f"Symlink vietato nell'artefatto: {rel}.")
            if stat.S_ISDIR(info.st_mode):
                if not _allowed_directory(rel):
                    raise PublisherError(f"Directory fuori allowlist nell'artefatto: {rel}.")
                if os.name == "posix" and (stat.S_IMODE(info.st_mode) & 0o022
                                            or stat.S_IMODE(info.st_mode) & 0o6000):
                    raise PublisherError(f"Permessi directory non sicuri nell'artefatto: {rel}.")
                visit(entry, rel)
            elif stat.S_ISREG(info.st_mode):
                if (not baseline_tool.safe_path(rel) or not _in_component(rel)
                        or baseline_tool.excluded(rel)):
                    raise PublisherError(f"File artefatto fuori perimetro: {rel}.")
                if os.name == "posix" and (stat.S_IMODE(info.st_mode) & 0o022
                                            or stat.S_IMODE(info.st_mode) & 0o6000):
                    raise PublisherError(f"Permessi file non sicuri nell'artefatto: {rel}.")
                records[rel] = {"sha256": _sha256(entry, info), "size": info.st_size,
                                "mode": format(stat.S_IMODE(info.st_mode), "o")}
            else:
                raise PublisherError(f"Tipo file speciale nell'artefatto: {rel}.")

    visit(root, "")
    for component in ALLOWED_COMPONENTS:
        target = root.joinpath(*component.split("/"))
        try:
            info = target.lstat()
        except OSError as exc:
            raise PublisherError(f"Componente mancante nell'artefatto: {component}.") from exc
        if stat.S_ISLNK(info.st_mode):
            raise PublisherError(f"Componente symlink nell'artefatto: {component}.")
        if component == ALLOWED_COMPONENTS[2]:
            if not stat.S_ISREG(info.st_mode) or component not in records:
                raise PublisherError(f"MU-plugin autorizzato mancante o non regolare: {component}.")
        elif not stat.S_ISDIR(info.st_mode):
            raise PublisherError(f"Componente non directory: {component}.")
    if not records:
        raise PublisherError("Artefatto vuoto.")
    return records


def _verify_vite(package_root, records):
    manifest_path = pathlib.Path(package_root) / "themes/sarafatto/assets/dist/.vite/manifest.json"
    try:
        manifest_info = manifest_path.lstat()
        if stat.S_ISLNK(manifest_info.st_mode) or not stat.S_ISREG(manifest_info.st_mode):
            raise PublisherError("Manifest Vite non regolare.")
        if manifest_info.st_size > 2 * 1024 * 1024:
            raise PublisherError("Manifest Vite oltre il limite.")
        manifest = json.loads(_read_regular(manifest_path, 2 * 1024 * 1024).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublisherError("Manifest Vite assente o malformato.") from exc
    dist_prefix = "themes/sarafatto/assets/dist/"
    for entry in REQUIRED_ENTRIES:
        row = manifest.get(entry)
        if (not isinstance(row, dict) or row.get("isEntry") is not True
                or not isinstance(row.get("file"), str) or not row["file"]):
            raise PublisherError(f"Entry Vite mancante: {entry}.")
    for name, row in manifest.items():
        if not isinstance(row, dict):
            raise PublisherError(f"Voce manifest Vite non valida: {name}.")
        lists = ("css", "assets", "imports", "dynamicImports")
        if any(key in row and (not isinstance(row[key], list)
                               or any(not isinstance(value, str) for value in row[key]))
               for key in lists):
            raise PublisherError(f"Liste riferimenti manifest Vite non valide: {name}.")
        refs = [row.get("file"), *(row.get("css") or []), *(row.get("assets") or [])]
        for value in refs:
            if value is None:
                continue
            if (not isinstance(value, str) or value.startswith("/") or "\\" in value
                    or any(part in ("", ".", "..") for part in value.split("/"))):
                raise PublisherError(f"Percorso manifest non sicuro: {value!r}.")
            if dist_prefix + value not in records:
                raise PublisherError(f"Asset Vite non presente nell'artefatto: {value}.")
        for imported in [*(row.get("imports") or []), *(row.get("dynamicImports") or [])]:
            if imported not in manifest:
                raise PublisherError(f"Import Vite inesistente: {name} -> {imported}.")


def verify_provenance(provenance_path, inventory_path, archive_path, release_sha, expected_run_id):
    try:
        document = json.loads(_read_regular(provenance_path, 65536).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublisherError("Provenance artifact assente o malformata.") from exc
    fields = {"schema_version", "repository", "commit_sha", "ref", "run_id",
              "inventory_sha256", "archive_sha256", "workflow_run_url"}
    if not isinstance(document, dict) or set(document) != fields:
        raise PublisherError("Schema provenance artifact inatteso.")
    if (document.get("schema_version") != 1 or document.get("repository") != GITHUB_REPOSITORY
            or document.get("commit_sha") != release_sha or document.get("ref") != "refs/heads/main"
            or str(document.get("run_id")) != str(expected_run_id)
            or not re.fullmatch(r"[0-9]+", str(document.get("run_id", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(document.get("inventory_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(document.get("archive_sha256", "")))
            or document.get("workflow_run_url") !=
            f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{document.get('run_id')}"):
        raise PublisherError("Provenance non legata al repository, branch, commit o run autorizzato.")
    inventory_digest = hashlib.sha256(_read_regular(inventory_path, 32 * 1024 * 1024)).hexdigest()
    archive_digest = _artifact_file_digest(archive_path, 2 * 1024 * 1024 * 1024)
    if (document["inventory_sha256"] != inventory_digest
            or document["archive_sha256"] != archive_digest):
        raise PublisherError("Digest provenance/inventario/archivio non concordanti.")
    return document


def verify_artifact(package_root, inventory_path, release_sha, *, provenance_path=None,
                    archive_path=None, expected_run_id=None):
    if not re.fullmatch(r"[a-f0-9]{40}", str(release_sha or "")):
        raise PublisherError("Release SHA deve essere completo e in minuscolo.")
    records = _walk_package(package_root)
    _verify_vite(package_root, records)
    try:
        inventory_bytes = _read_regular(inventory_path, 32 * 1024 * 1024)
        inventory_text = inventory_bytes.decode("utf-8")
        expected = {}
        for number, line in enumerate(inventory_text.splitlines(), 1):
            fields = line.split("\t")
            if len(fields) != 3:
                raise PublisherError(f"Inventario artefatto malformato alla riga {number}.")
            digest, size_text, path = fields
            if (not re.fullmatch(r"[a-f0-9]{64}", digest) or not size_text.isdigit()
                    or not baseline_tool.safe_path(path) or baseline_tool.excluded(path)
                    or path in expected):
                raise PublisherError(f"Record inventario artefatto non valido: {path!r}.")
            expected[path] = {"sha256": digest, "size": int(size_text)}
        if not expected:
            raise PublisherError("Inventario artefatto vuoto.")
    except (OSError, UnicodeError, baseline_tool.BaselineError) as exc:
        raise PublisherError(f"Inventario artefatto non valido: {exc}") from exc
    actual = {path: {key: row[key] for key in ("sha256", "size")}
              for path, row in records.items()}
    if actual != expected:
        raise PublisherError("Contenuto artefatto diverso dall'inventario autorizzato.")
    if (provenance_path is None or archive_path is None or expected_run_id is None):
        raise PublisherError("Preflight richiede provenance, archivio e run GitHub atteso.")
    verify_provenance(provenance_path, inventory_path, archive_path, release_sha, expected_run_id)
    _verify_archive_contents(archive_path, inventory_bytes, records)
    return records


def plan_inventory_changes(candidate, live, reference):
    """Piano senza eliminazioni: gli extra classificati vengono preservati."""
    changes, retained, blockers = [], [], []
    for path in sorted(set(candidate) | set(live)):
        if path not in candidate:
            classification = reference.get(path, live[path]).get("classification")
            if classification in ("retained-vite-bundle", "retained-backup", "retained-extra"):
                retained.append(path)
            else:
                changes.append({"path": path, "action": "removal-requires-explicit-authorization"})
                blockers.append(f"Rimozione non autorizzata: {path}.")
        elif path not in live:
            changes.append({"path": path, "action": "add"})
        elif (candidate[path]["sha256"] != live[path]["sha256"]
              or candidate[path]["size"] != live[path]["size"]
              or candidate[path].get("mode") != live[path].get("mode")):
            changes.append({"path": path, "action": "replace"})
    return changes, retained, blockers


def make_release_state_plan(current_state, artifact_records, operation_id, *,
                            approved_removals=(), removal_approval=None,
                            operation_kind="publish", rollback_target_release_id=None):
    """Crea il piano schema-release senza scrivere né autorizzare rimozioni.

    I file extra registrati nello stato corrente vengono mantenuti nello snapshot
    candidato. Se l'artefatto tenta di cambiarli, o omette un file gestito senza
    un'approvazione esplicita separata, il validatore dello stato rifiuta il piano.
    """
    current_rows = {row["path"]: row for row in current_state["reference_files"]}
    candidate_rows = {}
    for path, row in artifact_records.items():
        previous = current_rows.get(path)
        classification = (previous["classification"]
                          if previous and previous["classification"] != "artifact"
                          else "artifact")
        candidate_rows[path] = {
            "path": path, "sha256": row["sha256"], "size": row["size"],
            "mode": row["mode"], "classification": classification,
        }
    for path, row in current_rows.items():
        # I bundle Vite hashati omessi dalla build restano disponibili per cache
        # HTML e client che li richiedano durante o subito dopo il rilascio.
        # Un rollback deve coincidere con lo snapshot storico: i bundle nuovi
        # della release abbandonata sono rimossi solo con approvazione esatta.
        if (operation_kind == "publish" and path.startswith("themes/sarafatto/assets/dist/")
                and path not in candidate_rows):
            retained = dict(row)
            retained["classification"] = "retained-vite-bundle"
            candidate_rows[path] = retained
        elif row["classification"] != "artifact" and path not in candidate_rows:
            candidate_rows[path] = dict(row)
    ordered_rows = [candidate_rows[path] for path in sorted(candidate_rows)]
    plan, digest = release_state_tool.make_application_release_plan(
        current_state, ordered_rows, operation_id, operation_kind=operation_kind,
        approved_removals=approved_removals, rollback_target_release_id=rollback_target_release_id,
        removal_approval=removal_approval)
    return {"operation_id": operation_id, "plan": plan, "plan_sha256": digest,
            "candidate_reference_files": ordered_rows}


def _target_path_parts(relative):
    if (not isinstance(relative, str) or not baseline_tool.safe_path(relative)
            or not _in_component(relative) or baseline_tool.excluded(relative)):
        raise PublisherError(f"Percorso target fuori allowlist: {relative!r}.")
    return relative.split("/")


def _target_directory_parts(relative):
    """Ammette solo le due root directory dei componenti, mai i parent generici."""
    allowed = {ALLOWED_COMPONENTS[0], ALLOWED_COMPONENTS[1]}
    if not isinstance(relative, str) or relative not in allowed:
        raise PublisherError(f"Directory target fuori allowlist: {relative!r}.")
    return relative.split("/")


def _open_target_component_dir(root_fd, relative):
    """Apre la root esatta di tema/plugin; ogni segmento è no-follow e deve essere directory."""
    parts = _target_directory_parts(relative)
    fd = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(child)
            if not stat.S_ISDIR(info.st_mode):
                os.close(child)
                raise PublisherError(f"Componente target non-directory: {relative}.")
            os.close(fd)
            fd = child
        return fd
    except OSError as exc:
        os.close(fd)
        raise PublisherError(f"Root componente assente, symlink o non-directory: {relative}.") from exc
    except Exception:
        os.close(fd)
        raise


def _open_target_parent(root_fd, relative, *, create=False):
    """Apre il parent di un file gestito senza seguire symlink."""
    parts = _target_path_parts(relative)
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(child)
            if not stat.S_ISDIR(info.st_mode):
                os.close(child)
                raise PublisherError(f"Directory target non valida: {relative}.")
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except Exception:
        os.close(fd)
        raise


def _hash_at(parent_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PublisherError(f"Target non regolare o hard link: {name}.")
        digest = hashlib.sha256()
        size = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
        after = os.fstat(fd)
        if (size != info.st_size or after.st_size != info.st_size
                or after.st_mtime_ns != info.st_mtime_ns or after.st_ctime_ns != info.st_ctime_ns):
            raise PublisherError(f"Target cambiato durante la verifica: {name}.")
        return {"sha256": digest.hexdigest(), "size": size,
                "mode": format(stat.S_IMODE(info.st_mode), "o"),
                "uid": info.st_uid, "gid": info.st_gid}
    finally:
        os.close(fd)


def inventory_target_tree(root):
    """Inventario no-follow dei soli componenti gestiti (usato anche dalle fixture)."""
    root = pathlib.Path(root)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PublisherError("Inventario target richiede primitive POSIX no-follow.")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    records = {}

    def walk(directory_fd, prefix):
        for name in sorted(os.listdir(directory_fd)):
            relative = f"{prefix}/{name}" if prefix else name
            if relative == "themes/sarafatto/node_modules" or relative.startswith("themes/sarafatto/node_modules/"):
                continue
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise PublisherError(f"Symlink nel perimetro gestito: {relative}.")
            if stat.S_ISDIR(info.st_mode):
                if not _allowed_directory(relative):
                    raise PublisherError(f"Directory target fuori allowlist: {relative}.")
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    walk(child, relative)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                if not _in_component(relative) or not baseline_tool.safe_path(relative):
                    raise PublisherError(f"File target fuori allowlist: {relative}.")
                row = _hash_at(directory_fd, name)
                row.pop("uid")
                row.pop("gid")
                records[relative] = row
            else:
                raise PublisherError(f"File speciale nel perimetro: {relative}.")

    try:
        for component in ALLOWED_COMPONENTS:
            if component in (ALLOWED_COMPONENTS[0], ALLOWED_COMPONENTS[1]):
                component_fd = _open_target_component_dir(root_fd, component)
                try:
                    walk(component_fd, component)
                finally:
                    os.close(component_fd)
                continue
            parent_fd, leaf = _open_target_parent(root_fd, component)
            try:
                info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise PublisherError(f"Componente gestito symlink: {component}.")
                if component == ALLOWED_COMPONENTS[2]:
                    if not stat.S_ISREG(info.st_mode):
                        raise PublisherError("MU-plugin gestito non regolare.")
                    row = _hash_at(parent_fd, leaf)
                    row.pop("uid")
                    row.pop("gid")
                    records[component] = row
            finally:
                os.close(parent_fd)
        return records
    finally:
        os.close(root_fd)


def apply_file_snapshot(source_root, target_root, current_rows, candidate_rows, *,
                        approved_removals=(), fault_hook=None):
    """Applica file allowlistati con rename atomico per file; non è atomico per release.

    La funzione verifica l'intero snapshot parent prima di scrivere. I file extra
    devono essere presenti identici nel candidato. Le rimozioni richiedono una
    lista esatta di path+SHA; nessun delete ricorsivo è usato.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PublisherError("Writer filesystem richiede POSIX/O_NOFOLLOW.")
    source_root, target_root = pathlib.Path(source_root), pathlib.Path(target_root)
    source_records = _walk_package(source_root)
    target_records = inventory_target_tree(target_root)
    expected_current = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                        for row in current_rows}
    if target_records != expected_current:
        raise PublisherError("Inventario target cambiato o diverso dallo stato parent.")
    desired = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
               for row in candidate_rows}
    for row in candidate_rows:
        if row["classification"] != "artifact" and desired.get(row["path"]) != expected_current.get(row["path"]):
            raise PublisherError(f"File extra alterato nel candidato: {row['path']}.")
    expected_removed = sorted(({"path": path, "sha256": expected_current[path]["sha256"]}
                               for path in set(expected_current) - set(desired)),
                              key=lambda row: row["path"])
    approvals = sorted((dict(row) for row in approved_removals), key=lambda row: row.get("path", ""))
    if approvals != expected_removed:
        raise PublisherError("Rimozioni non approvate o approvazione non esatta.")

    target_fd = os.open(target_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    written = []
    try:
        # Prima si installano i nuovi file statici/hashati; poi plugin e tema.
        # Così i riferimenti ai bundle già serviti restano disponibili durante
        # l'aggiornamento del markup. Le sostituzioni dei singoli file sono atomiche.
        def rank(path):
            if "/assets/dist/" in f"/{path}/" or "/assets/images/" in f"/{path}/":
                return 0
            if path.startswith("plugins/sarafatto-core/"):
                return 1
            return 2

        # Le aggiunte e le sostituzioni devono essere insiemi disgiunti:
        # un file nuovo non deve comparire anche in `changed` solo perché
        # expected_current.get(path) restituisce None.
        artifact_paths = set(desired) & set(source_records)
        changed = [path for path in sorted(artifact_paths & set(expected_current))
                   if desired[path] != expected_current[path]]
        added = sorted(artifact_paths - set(expected_current))
        for relative in sorted(added + changed, key=lambda value: (rank(value), value)):
            source_parts = _target_path_parts(relative)
            source_path = source_root.joinpath(*source_parts)
            source_info = source_path.lstat()
            source_fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
            parent_fd, name = _open_target_parent(target_fd, relative, create=True)
            temp_name = ".sf-new-" + uuid.uuid4().hex
            temp_fd = None
            try:
                source_opened = os.fstat(source_fd)
                if (not stat.S_ISREG(source_opened.st_mode) or source_opened.st_nlink != 1
                        or (source_opened.st_dev, source_opened.st_ino) != (source_info.st_dev, source_info.st_ino)):
                    raise PublisherError(f"Sorgente sostituita durante l'applicazione: {relative}.")
                temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                  0o600, dir_fd=parent_fd)
                digest = hashlib.sha256()
                count = 0
                while True:
                    block = os.read(source_fd, 1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                    count += len(block)
                    view = memoryview(block)
                    while view:
                        written_bytes = os.write(temp_fd, view)
                        if written_bytes <= 0:
                            raise PublisherError(f"Scrittura incompleta: {relative}.")
                        view = view[written_bytes:]
                if (digest.hexdigest() != desired[relative]["sha256"]
                        or count != desired[relative]["size"]):
                    raise PublisherError(f"SHA sorgente non corrispondente: {relative}.")
                os.fchmod(temp_fd, int(desired[relative]["mode"], 8))
                current_identity = None
                if relative in expected_current:
                    current_info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if (stat.S_ISLNK(current_info.st_mode) or not stat.S_ISREG(current_info.st_mode)
                            or current_info.st_nlink != 1):
                        raise PublisherError(f"Destinazione non regolare o hard link: {relative}.")
                    current_identity = (current_info.st_dev, current_info.st_ino)
                    current_record = _hash_at(parent_fd, name)
                    if {key: current_record[key] for key in ("sha256", "size", "mode")} != expected_current[relative]:
                        raise PublisherError(f"Destinazione modificata prima della sostituzione: {relative}.")
                    os.fchown(temp_fd, current_info.st_uid, current_info.st_gid)
                os.fsync(temp_fd)
                os.close(temp_fd)
                temp_fd = None
                if relative in expected_current:
                    # Ricontrollo immediatamente prima del rename. Il lock
                    # serializza i writer cooperanti; il controllo d'identità
                    # rileva sostituzioni esterne avvenute durante lo staging.
                    latest_info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if (not stat.S_ISREG(latest_info.st_mode) or latest_info.st_nlink != 1
                            or (latest_info.st_dev, latest_info.st_ino) != current_identity):
                        raise PublisherError(f"Destinazione sostituita durante lo staging: {relative}.")
                    latest_record = _hash_at(parent_fd, name)
                    if {key: latest_record[key] for key in ("sha256", "size", "mode")} != expected_current[relative]:
                        raise PublisherError(f"Destinazione modificata durante lo staging: {relative}.")
                    os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                else:
                    try:
                        # hard-link nello stesso parent: creazione atomica
                        # senza sostituire una destinazione apparsa nel frattempo.
                        os.link(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                                follow_symlinks=False)
                    except FileExistsError as exc:
                        raise PublisherError(f"Destinazione nuova già esistente: {relative}.") from exc
                    os.unlink(temp_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
                written.append(relative)
                if fault_hook:
                    fault_hook("after-file", relative, len(written))
            finally:
                if temp_fd is not None:
                    os.close(temp_fd)
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                os.close(source_fd)
                os.close(parent_fd)

        for approval in approvals:
            relative = approval["path"]
            parent_fd, name = _open_target_parent(target_fd, relative)
            try:
                actual = _hash_at(parent_fd, name)
                if actual["sha256"] != approval["sha256"]:
                    raise PublisherError(f"File cambiato prima della rimozione approvata: {relative}.")
                os.unlink(name, dir_fd=parent_fd)
                os.fsync(parent_fd)
                written.append(relative)
                if fault_hook:
                    fault_hook("after-file", relative, len(written))
            finally:
                os.close(parent_fd)
        final = inventory_target_tree(target_root)
        if final != desired:
            raise PublisherError("Inventario target finale diverso dal candidato.")
        return {"written": written, "inventory": final, "public_writes_performed": bool(written),
                "atomicity": "per-file-only; release can be mixed during operation"}
    finally:
        os.close(target_fd)


def recover_file_snapshot(backup_root, target_root, parent_rows, candidate_rows, *, fault_hook=None):
    """Riconcilia un'operazione interrotta solo se ogni file è parent o candidato.

    Qualunque hash terzo, symlink, extra non registrato o file speciale blocca il
    recovery. Il ripristino usa il backup verificato già estratto in area privata.
    """
    actual = inventory_target_tree(target_root)
    parent = {row["path"]: row for row in parent_rows}
    candidate = {row["path"]: row for row in candidate_rows}
    allowed_paths = set(parent) | set(candidate)
    if set(actual) - allowed_paths:
        raise PublisherError("Recovery bloccato: file live fuori dai due snapshot autorizzati.")
    for path, current in actual.items():
        allowed_hashes = {snapshot[path]["sha256"] for snapshot in (parent, candidate) if path in snapshot}
        if current["sha256"] not in allowed_hashes:
            raise PublisherError(f"Recovery bloccato: hash live estraneo ai due snapshot: {path}.")
    current_rows = []
    for path, row in actual.items():
        classification = (parent.get(path) or candidate[path]).get("classification", "artifact")
        current_rows.append({"path": path, **row, "classification": classification})
    removals = [{"path": path, "sha256": actual[path]["sha256"]}
                for path in sorted(set(actual) - set(parent))]
    return apply_file_snapshot(backup_root, target_root, current_rows, parent_rows,
                               approved_removals=removals, fault_hook=fault_hook)


def rollback_file_snapshot(verified_backup_root, target_root, current_rows, target_rows, *,
                           fault_hook=None):
    """Ripristina uno snapshot già estratto e verificato dal backup applicativo."""
    current = {row["path"]: row for row in current_rows}
    target = {row["path"]: row for row in target_rows}
    removals = [{"path": path, "sha256": current[path]["sha256"]}
                for path in sorted(set(current) - set(target))]
    return apply_file_snapshot(verified_backup_root, target_root, current_rows, target_rows,
                               approved_removals=removals, fault_hook=fault_hook)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def production_health_check(*, urls=("https://sara-fatto.it/", "https://sara-fatto.it/wp-json/"),
                            opener=None, timeout=12):
    """Health check HTTP read-only: HTTPS, host vincolato, 2xx e body non-manutenzione."""
    from urllib.parse import urlsplit
    if not urls or len(urls) > 5:
        raise PublisherError("Health check richiede da uno a cinque URL espliciti.")
    client = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(), _NoRedirect())
    checks = []
    for url in urls:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"sara-fatto.it", "www.sara-fatto.it"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment):
            raise PublisherError("URL health check fuori dagli endpoint HTTPS autorizzati.")
        request = urllib.request.Request(url, headers={
            "Cache-Control": "no-cache, no-store", "Pragma": "no-cache",
            "User-Agent": "Sarafatto-Release-Health/1",
        })
        try:
            response = client.open(request, timeout=timeout)
            with response:
                status = getattr(response, "status", 200)
                body = response.read(2 * 1024 * 1024 + 1)
                final_url = response.geturl()
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise PublisherError(f"Health check HTTP non riuscito per {parsed.path or '/'}.") from exc
        final = urlsplit(final_url)
        if (status < 200 or status >= 300 or not body or len(body) > 2 * 1024 * 1024
                or final.scheme != "https" or final.hostname not in {"sara-fatto.it", "www.sara-fatto.it"}
                or b"Briefly unavailable for scheduled maintenance" in body
                or b"X-Sarafatto-Deploy-Barrier" in body):
            raise PublisherError(f"Health check HTTP non valido per {parsed.path or '/'}.")
        checks.append({"url": url, "status": status, "body_sha256": hashlib.sha256(body).hexdigest(),
                       "bytes": len(body)})
    return {"status": "healthy", "checks": checks, "checked_at_utc":
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}


def publish_filesystem_snapshot(source_root, target_root, current_rows, candidate_rows, *,
                                approved_removals=(), health_check, fault_hook=None,
                                recovery_root=None):
    """Pubblica file reali e fa rollback automatico se health check fallisce.

    `recovery_root` deve essere l'estrazione già verificata del backup pre-deploy.
    La funzione non dichiara atomicità multi-file: ogni file è sostituito
    atomicamente, mentre le richieste concorrenti possono vedere stati misti.
    """
    if not callable(health_check):
        raise PublisherError("Health check obbligatorio.")
    applied = apply_file_snapshot(source_root, target_root, current_rows, candidate_rows,
                                  approved_removals=approved_removals, fault_hook=fault_hook)
    try:
        evidence = health_check()
        if not isinstance(evidence, dict) or evidence.get("status") != "healthy":
            raise PublisherError("Health check post-pubblicazione non superato.")
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":"))
                                .encode("utf-8")).hexdigest()
        final = inventory_target_tree(target_root)
        expected = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                    for row in candidate_rows}
        if final != expected:
            raise PublisherError("Inventario live variato dopo l'health check.")
        return {**applied, "status": "files-and-health-verified", "health_evidence": evidence,
                "health_evidence_sha256": digest}
    except Exception as exc:
        if recovery_root is None:
            raise PublisherError(f"Pubblicazione applicata ma health check fallito; recovery necessario: {exc}") from exc
        try:
            recover_file_snapshot(recovery_root, target_root, current_rows, candidate_rows)
        except Exception as rollback_exc:
            raise PublisherError(f"Health check fallito e rollback automatico non verificato: {rollback_exc}") from exc
        raise PublisherError(f"Health check fallito; rollback al parent completato e verificato: {exc}") from exc


TRANSACTION_MANIFEST_LIMIT = 32 * 1024 * 1024


def _transaction_directory(staging_fd, *, create=False):
    name = "transactions"
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=staging_fd)
            os.fsync(staging_fd)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=staging_fd)
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(fd)
        raise PublisherError("Directory privata transactions non sicura.")
    return fd


def _write_private_file_at(parent_fd, name, payload):
    if (not re.fullmatch(r"[A-Za-z0-9._-]{1,140}", name)
            or not isinstance(payload, bytes) or len(payload) > TRANSACTION_MANIFEST_LIMIT):
        raise PublisherError("File transazione privato non valido o oltre limite.")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent_fd)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise PublisherError("Scrittura del file transazione incompleta.")
            view = view[count:]
        os.fsync(fd)
        return hashlib.sha256(payload).hexdigest()
    finally:
        os.close(fd)
        os.fsync(parent_fd)


def _read_private_file_at(parent_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size > TRANSACTION_MANIFEST_LIMIT):
            raise PublisherError("File transazione privato non regolare o non sicuro.")
        chunks = []
        total = 0
        while True:
            block = os.read(fd, min(1024 * 1024, TRANSACTION_MANIFEST_LIMIT + 1 - total))
            if not block:
                break
            total += len(block)
            if total > TRANSACTION_MANIFEST_LIMIT:
                raise PublisherError("File transazione privato oltre limite.")
            chunks.append(block)
        after = os.fstat(fd)
        if (total != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns or after.st_ctime_ns != before.st_ctime_ns):
            raise PublisherError("File transazione cambiato durante la lettura.")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _health_evidence(health_check):
    try:
        result = health_check()
    except Exception as exc:
        raise PublisherError(f"Health check non eseguibile: {exc}") from exc
    if not isinstance(result, dict) or result.get("status") != "healthy":
        raise PublisherError("Health check post-operazione non superato.")
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8")).hexdigest()
    return result, digest


def _verify_fresh_snapshot(inventory_reader, tool_commit, reference_files, exclusion,
                           expected_digest):
    expected = {row["path"]: row for row in reference_files}
    first_text, second_text = inventory_reader(tool_commit), inventory_reader(tool_commit)
    try:
        first = release_state_tool._validate_inventory(first_text, expected)
        second = release_state_tool._validate_inventory(second_text, expected)
    except release_state_tool.ReleaseStateError as exc:
        raise PublisherError(f"Inventario fresco non valido: {exc}") from exc
    first_digest = release_state_tool.inventory_digest_json(first)
    second_digest = release_state_tool.inventory_digest_json(second)
    if first_digest != second_digest or second_digest != expected_digest:
        raise PublisherError("I due inventari freschi non coincidono con lo snapshot atteso.")
    if second.get("exclusion") != exclusion:
        raise PublisherError("Conteggi delle esclusioni non coerenti con lo stato release.")
    return second


def _backup_release_reference(current_state, backup_result):
    return {
        "backup_id": backup_result["backup_id"],
        "manifest_sha256": backup_result["manifest_sha256"],
        "release_id": current_state["release"]["release_id"],
        "inventory_sha256": current_state["inventory_sha256"],
        "baseline_sha256": current_state["initial_baseline"]["sha256"],
    }


def _verify_backup_for_parent(private, parent_state, backup_reference):
    """Verifica un backup rispetto al parent noto senza richiedere journal idle.

    Serve soltanto durante recovery: il journal è intenzionalmente incompleto,
    quindi il verificatore standard rifiuterebbe correttamente lo stato attivo.
    Qui digest esterno, archivio e file vengono confrontati direttamente con il
    parent già validato sotto il lock esclusivo.
    """
    backup_fd = backup_tool.open_directory_at(
        private["backups_fd"], backup_reference["backup_id"], "backup transazione")
    try:
        verified = backup_tool.verify_backup_directory(
            None, backup_reference["backup_id"], parent_state["initial_baseline"]["sha256"],
            backup_reference["manifest_sha256"], directory_fd=backup_fd)
        _, baseline_sha, baseline_commit, _ = backup_tool.validate_backup_baseline(
            None, parent_state["initial_baseline"]["sha256"], state_fd=private["state_fd"])
        reference = verified["manifest"].get("reference_state")
        if reference is not None and (reference.get("release_id") != parent_state["release"]["release_id"]
                                      or reference.get("inventory_sha256") != parent_state["inventory_sha256"]
                                      or reference.get("state_sha256") != parent_state["state_sha256"]):
            raise PublisherError("Backup transazione non riferito al parent corrente.")
        expected = {row["path"]: {key: row[key] for key in
                                   ("path", "sha256", "size", "mode", "classification")}
                    for row in parent_state["reference_files"]}
        backup_tool.verify_manifest_matches_baseline(
            verified["manifest"], baseline_sha, baseline_commit, expected)
        return verified
    finally:
        os.close(backup_fd)


def _prepared_release_details(current_state, *, operation_kind, release_id, commit_sha,
                              artifact_sha256, backup_reference, plan, manifest_sha256):
    """Serializza l'intento con i distinti digest di catena e documento parent."""
    _, _, parent_chain_sha = release_state_tool._application_release_parent(current_state)
    return {
        "operation_kind": operation_kind, "release_id": release_id,
        "commit_sha": commit_sha, "artifact_sha256": artifact_sha256,
        "plan_sha256": release_state_tool.digest_json(plan),
        "backup_id": backup_reference["backup_id"],
        "backup_manifest_sha256": backup_reference["manifest_sha256"],
        "parent_release_id": current_state["release"]["release_id"],
        "parent_inventory_sha256": current_state["inventory_sha256"],
        "parent_state_sha256": parent_chain_sha,
        "parent_document_sha256": current_state["state_sha256"], "plan": plan,
        "transaction_manifest_sha256": manifest_sha256,
    }


def _run_filesystem_release_transaction(*, operation_kind, operation_id, release_id,
                                        commit_sha, inventory_tool_commit, artifact_sha256,
                                        source_root, candidate_rows, plan, rollback_target_release_id,
                                        approved_removals, current_state, private, lock_fd,
                                        private_root, public_root, expected_private_root,
                                        expected_public_root, quota_free_bytes,
                                        inventory_reader, health_check, rollback_health_check,
                                        fault_hook=None):
    state_fd, locks_fd = private["state_fd"], private["locks_fd"]
    staging_fd, backups_fd = private["staging_fd"], private["backups_fd"]
    baseline_sha = current_state["initial_baseline"]["sha256"]
    parent_state_sha = current_state["state_sha256"]
    parent_rows = current_state["reference_files"]
    transaction_dir_fd = _transaction_directory(staging_fd, create=True)
    restore_report = None
    prepared_written = False
    try:
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        backup_result = backup_tool.create_backup(
            backup_id, baseline_sha, quota_free_bytes,
            private_root=private_root, expected_private_root=expected_private_root,
            public_root=public_root, baseline_path=pathlib.Path(private_root) / "state" / "baseline.json",
            lock_fd=lock_fd, inventory_reader=inventory_reader)
        backup_verification = backup_tool.verify_backup(
            backup_id, baseline_sha, backup_result["manifest_sha256"],
            private_root=private_root, expected_private_root=expected_private_root, lock_fd=lock_fd)
        if backup_verification.get("status") != "verified":
            raise PublisherError("Backup fresco non verificato indipendentemente.")
        restore_report = backup_tool.restore_test(
            backup_id, baseline_sha, backup_result["manifest_sha256"], quota_free_bytes,
            private_root=private_root, expected_private_root=expected_private_root, lock_fd=lock_fd)
        recovery_root = pathlib.Path(restore_report["restore_test_path"])
        if recovery_root != pathlib.Path(private_root) / "staging" / recovery_root.relative_to(pathlib.Path(private_root) / "staging"):
            raise PublisherError("Snapshot di recovery fuori dalla staging privata.")
        if recovery_root.name != "restored" or not recovery_root.is_dir() or recovery_root.is_symlink():
            raise PublisherError("Snapshot di recovery assente o non sicuro.")

        backup_reference = _backup_release_reference(current_state, backup_result)
        plan_sha = release_state_tool.digest_json(plan)
        # Nel manifest privato schema 1 parent_state_sha256 identifica il
        # documento current-release; nel journal è parent_document_sha256.
        # Il parent_state_sha256 del journal identifica invece la voce di catena.
        manifest = {
            "schema_version": 1, "operation_id": operation_id, "operation_kind": operation_kind,
            "release_id": release_id, "commit_sha": commit_sha,
            "inventory_tool_commit": inventory_tool_commit, "artifact_sha256": artifact_sha256,
            "parent_state_sha256": parent_state_sha, "parent_release_id": current_state["release"]["release_id"],
            "parent_inventory_sha256": current_state["inventory_sha256"],
            "backup": backup_reference, "plan": plan, "plan_sha256": plan_sha,
            "rollback_target_release_id": rollback_target_release_id,
            "parent_reference_files": parent_rows, "candidate_reference_files": candidate_rows,
            "source_root": str(pathlib.Path(source_root)), "recovery_root": str(recovery_root),
            "public_root": str(pathlib.Path(public_root)),
            "approved_removals": list(approved_removals),
        }
        manifest_raw = release_state_tool.json_bytes(manifest)
        manifest_name = f"transaction-{operation_id}.json"
        manifest_sha = _write_private_file_at(transaction_dir_fd, manifest_name, manifest_raw)
        entry_fields = _prepared_release_details(
            current_state, operation_kind=operation_kind, release_id=release_id,
            commit_sha=commit_sha, artifact_sha256=artifact_sha256,
            backup_reference=backup_reference, plan=plan, manifest_sha256=manifest_sha)
        release_state_tool.append_operation_event(
            state_fd, locks_fd, operation_id, "prepared", entry_fields, lock_fd=lock_fd)
        prepared_written = True
        if fault_hook:
            fault_hook("after-prepared", operation_id, 0)
        release_state_tool.append_operation_event(
            state_fd, locks_fd, operation_id, "backup_verified", backup_reference, lock_fd=lock_fd)
        release_state_tool.append_operation_event(
            state_fd, locks_fd, operation_id, "publishing", {"plan_sha256": plan_sha}, lock_fd=lock_fd)
        if fault_hook:
            fault_hook("after-publishing", operation_id, 0)
        applied = apply_file_snapshot(source_root, public_root, parent_rows, candidate_rows,
                                      approved_removals=approved_removals, fault_hook=fault_hook)
        _verify_fresh_snapshot(inventory_reader, inventory_tool_commit, candidate_rows,
                               current_state["inventory"]["exclusion"],
                               plan["candidate_inventory_sha256"])
        release_state_tool.append_operation_event(
            state_fd, locks_fd, operation_id, "files_verified",
            {"final_inventory_sha256": plan["candidate_inventory_sha256"]}, lock_fd=lock_fd)
        evidence, health_sha = _health_evidence(health_check)
        candidate = release_state_tool.build_application_release_state(
            current_state, release_id=release_id, commit_sha=commit_sha,
            inventory_tool_commit=inventory_tool_commit, operation_id=operation_id,
            operation_kind=operation_kind, artifact_sha256=artifact_sha256,
            backup=backup_reference, reference_files=candidate_rows, plan=plan,
            rollback_target_release_id=rollback_target_release_id,
            health_evidence_sha256=health_sha)
        candidate_payload = release_state_tool.json_bytes(candidate)
        candidate_state_sha = _write_private_file_at(
            transaction_dir_fd, f"candidate-{operation_id}.json", candidate_payload)
        release_state_tool.append_operation_event(
            state_fd, locks_fd, operation_id, "health_verified",
            {"health_evidence_sha256": health_sha, "candidate_state_sha256": candidate_state_sha},
            lock_fd=lock_fd)
        if fault_hook:
            fault_hook("after-health-verified", operation_id, len(applied["written"]))
        terminal = release_state_tool.append_verified_application_terminal(
            candidate, parent_state_sha, private_root=private_root, expected_root=expected_private_root,
            inventory_reader=inventory_reader, lock_fd=lock_fd)
        if fault_hook:
            fault_hook("after-terminal", operation_id, len(applied["written"]))
        promoted = release_state_tool.persist_verified_application_release_state(
            candidate, parent_state_sha, private_root=private_root, expected_root=expected_private_root,
            baseline_sha256=baseline_sha, inventory_reader=inventory_reader, lock_fd=lock_fd)
        return {"status": "published" if operation_kind == "publish" else "rolled-back",
                "operation_id": operation_id, "release_id": release_id,
                "inventory_sha256": plan["candidate_inventory_sha256"],
                "backup": backup_reference, "health_evidence": evidence,
                "terminal": terminal, "state": promoted,
                "files_written": applied["written"], "public_writes_performed": True,
                "atomicity": "per-file-only; requests may observe mixed component versions"}
    except BaseException as exc:
        # Interruzioni di processo (BaseException) lasciano il journal riprendibile.
        # Gli errori ordinari tentano invece immediatamente il ripristino verificato.
        if prepared_written and isinstance(exc, Exception):
            try:
                release_state_tool.append_operation_event(
                    state_fd, locks_fd, operation_id, "recovery_required",
                    {"reason": type(exc).__name__, "message": str(exc)[:1000]}, lock_fd=lock_fd)
                recovered = recover_file_snapshot(
                    recovery_root, public_root, parent_rows, candidate_rows)
                parent_health, parent_health_sha = _health_evidence(rollback_health_check or health_check)
                release_state_tool.append_verified_recovery_completion(
                    operation_id, parent_state_sha, backup_id=backup_reference["backup_id"],
                    backup_manifest_sha256=backup_reference["manifest_sha256"],
                    restored_inventory_sha256=current_state["inventory_sha256"],
                    health_evidence_sha256=parent_health_sha,
                    private_root=private_root, expected_root=expected_private_root,
                    inventory_reader=inventory_reader, lock_fd=lock_fd)
                raise PublisherError(
                    f"Operazione fallita; rollback al parent ripristinato e verificato ({len(recovered['written'])} file)."
                ) from exc
            except PublisherError as recovery_error:
                if "rollback al parent" in str(recovery_error):
                    raise
                raise PublisherError(f"Operazione interrotta; recovery_required, intervento necessario: {recovery_error}") from exc
            except Exception as recovery_error:
                raise PublisherError(f"Operazione interrotta; recovery_required, intervento necessario: {recovery_error}") from exc
        raise
    finally:
        os.close(transaction_dir_fd)


def _require_staging_path(root, path, label, *, directory=False):
    root, path = pathlib.Path(root), pathlib.Path(path)
    try:
        if not root.is_absolute() or root.resolve(strict=True) != root or not path.is_absolute():
            raise PublisherError(f"Percorso {label} non canonico o non assoluto.")
        relative = path.relative_to(root)
        if not relative.parts:
            raise PublisherError(f"Percorso {label} coincide con la root staging.")
        current = root
        for part in relative.parts[:-1] if not directory else relative.parts:
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise PublisherError(f"Componente non-directory o symlink nel percorso {label}.")
        if not directory:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PublisherError(f"File {label} non regolare o hard link.")
    except (OSError, ValueError) as exc:
        if isinstance(exc, PublisherError):
            raise
        raise PublisherError(f"Percorso {label} fuori o non sicuro nella staging privata.") from exc


def _open_release_context(private_root, expected_private_root):
    if (pathlib.Path(private_root) != pathlib.Path(expected_private_root)
            or not pathlib.Path(private_root).is_absolute()):
        raise PublisherError("Root privata diversa da quella autorizzata.")
    private = backup_tool.open_private_directories(private_root, expected_private_root)
    try:
        lock_fd = baseline_tool.acquire_baseline_lock(private["paths"]["locks"], private["locks_fd"])
        return private, lock_fd
    except Exception:
        backup_tool.close_private_directories(private)
        raise


def _load_locked_release(private, baseline_sha256=None):
    state = release_state_tool.load_current_state(private["state_fd"], baseline_sha256)
    events = release_state_tool.read_journal_at(private["state_fd"])
    release_state_tool.validate_current_state_journal(state, events)
    return state, events


def publish_filesystem_release(*, package_root, inventory_path, provenance_path, archive_path,
                               release_sha, run_id, release_id, operation_id, quota_free_bytes,
                               private_root, expected_private_root, public_root, expected_public_root,
                               health_check, rollback_health_check=None, inventory_reader=None,
                               approved_removals=(), removal_approval=None, fault_hook=None):
    """Orchestra A→B su filesystem autorizzato; CLI IONOS resta separata e disabilitata.

    `private_root == expected_private_root` e `public_root == expected_public_root`
    sono obbligatori. I test passano directory temporanee identiche; il wrapper
    produttivo dovrà passare esclusivamente le costanti IONOS.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not callable(health_check):
        raise PublisherError("Orchestrazione richiede POSIX/O_NOFOLLOW e health check.")
    if pathlib.Path(public_root) != pathlib.Path(expected_public_root):
        raise PublisherError("Root pubblica diversa dal target autorizzato.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", str(operation_id or "")):
        raise PublisherError("ID operazione non valido.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(release_id or "")):
        raise PublisherError("ID release non valido.")
    if not re.fullmatch(r"[a-f0-9]{40}", str(release_sha or "")):
        raise PublisherError("Commit SHA completo richiesto.")
    private = lock_fd = None
    try:
        private, lock_fd = _open_release_context(private_root, expected_private_root)
        staging_root = pathlib.Path(private_root) / "staging"
        for label, path in (("package", package_root), ("inventory", inventory_path),
                            ("provenance", provenance_path), ("archive", archive_path)):
            _require_staging_path(staging_root, path, label, directory=(label == "package"))
        current, events = _load_locked_release(private)
        if any(event["operation_id"] == operation_id for event in events):
            raise PublisherError("ID operazione già usato nel journal.")
        baseline_doc, baseline_sha, _, _ = backup_tool.validate_backup_baseline(
            None, current["initial_baseline"]["sha256"], state_fd=private["state_fd"])
        if baseline_sha != current["initial_baseline"]["sha256"]:
            raise PublisherError("Baseline storica diversa dal current-release.")
        reader = inventory_reader or baseline_tool.acquire_fresh_inventory
        tool_commit = release_sha
        _verify_fresh_snapshot(reader, current["release"]["inventory_tool_commit"],
                               current["reference_files"], current["inventory"]["exclusion"],
                               current["inventory_sha256"])
        artifact = verify_artifact(package_root, inventory_path, release_sha,
                                   provenance_path=provenance_path, archive_path=archive_path,
                                   expected_run_id=run_id)
        plan_result = make_release_state_plan(
            current, artifact, operation_id, approved_removals=approved_removals,
            removal_approval=removal_approval)
        plan = plan_result["plan"]
        candidate_rows = plan_result["candidate_reference_files"]
        artifact_sha = _artifact_file_digest(pathlib.Path(archive_path), 2 * 1024 * 1024 * 1024)
        return _run_filesystem_release_transaction(
            operation_kind="publish", operation_id=operation_id, release_id=release_id,
            commit_sha=release_sha, inventory_tool_commit=tool_commit,
            artifact_sha256=artifact_sha, source_root=package_root,
            candidate_rows=candidate_rows, plan=plan, rollback_target_release_id=None,
            approved_removals=approved_removals, current_state=current, private=private,
            lock_fd=lock_fd, private_root=private_root, public_root=public_root,
            expected_private_root=expected_private_root, expected_public_root=expected_public_root,
            quota_free_bytes=quota_free_bytes, inventory_reader=reader,
            health_check=health_check, rollback_health_check=rollback_health_check,
            fault_hook=fault_hook)
    except (backup_tool.BackupError, baseline_tool.BaselineError,
            release_state_tool.ReleaseStateError, OSError, ValueError) as exc:
        if isinstance(exc, PublisherError):
            raise
        raise PublisherError(f"Publish filesystem bloccato: {exc}") from exc
    finally:
        if lock_fd is not None:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if private is not None:
            backup_tool.close_private_directories(private)


def rollback_filesystem_release(*, target_release_id, backup_id, manifest_sha256,
                                operation_id, quota_free_bytes, private_root,
                                expected_private_root, public_root, expected_public_root,
                                health_check, rollback_health_check=None, inventory_reader=None,
                                approved_removals=(), removal_approval=None, fault_hook=None):
    """Rollback verificato a uno snapshot e backup appartenenti alla catena release."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not callable(health_check):
        raise PublisherError("Rollback richiede POSIX/O_NOFOLLOW e health check.")
    if pathlib.Path(public_root) != pathlib.Path(expected_public_root):
        raise PublisherError("Root pubblica diversa dal target autorizzato.")
    private = lock_fd = None
    try:
        private, lock_fd = _open_release_context(private_root, expected_private_root)
        current, events = _load_locked_release(private)
        if current["schema_version"] != release_state_tool.APPLICATION_STATE_SCHEMA:
            raise PublisherError("Rollback applicativo disponibile solo dopo una release schema 2.")
        if any(event["operation_id"] == operation_id for event in events):
            raise PublisherError("ID operazione rollback già usato nel journal.")
        reader = inventory_reader or baseline_tool.acquire_fresh_inventory
        _verify_fresh_snapshot(reader, current["release"]["inventory_tool_commit"],
                               current["reference_files"], current["inventory"]["exclusion"],
                               current["inventory_sha256"])
        chain = current["release_chain"]
        records = [chain["root"], *chain["entries"]]
        target = next((row for row in records if row["release_id"] == target_release_id), None)
        if target is None or target_release_id == current["release"]["release_id"]:
            raise PublisherError("Release target non storica o non presente nella catena verificata.")
        target_backup = next((row["backup"] for row in chain["entries"]
                              if row["parent_release_id"] == target_release_id
                              and row["backup"]["release_id"] == target_release_id), None)
        if (target_backup is None or target_backup["backup_id"] != backup_id
                or target_backup["manifest_sha256"] != manifest_sha256):
            raise PublisherError("Backup esplicito non corrisponde allo snapshot target autorizzato.")
        baseline_sha = current["initial_baseline"]["sha256"]
        verification = backup_tool.verify_backup(
            backup_id, baseline_sha, manifest_sha256, private_root=private_root,
            expected_private_root=expected_private_root, lock_fd=lock_fd)
        if verification.get("status") != "verified":
            raise PublisherError("Backup storico target non verificato.")
        restore_report = backup_tool.restore_test(
            backup_id, baseline_sha, manifest_sha256, quota_free_bytes,
            private_root=private_root, expected_private_root=expected_private_root,
            lock_fd=lock_fd)
        source_root = pathlib.Path(restore_report["restore_test_path"])
        target_rows = release_state_tool.resolve_release_snapshot(
            current, target_release_id, target["inventory_sha256"])
        artifact_records = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                            for row in target_rows}
        operation_id = str(operation_id)
        plan_result = make_release_state_plan(
            current, artifact_records, operation_id, approved_removals=approved_removals,
            removal_approval=removal_approval, operation_kind="rollback",
            rollback_target_release_id=target_release_id)
        rollback_release_id = "rollback-" + hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:24]
        return _run_filesystem_release_transaction(
            operation_kind="rollback", operation_id=operation_id, release_id=rollback_release_id,
            commit_sha=target["commit_sha"], inventory_tool_commit=target["inventory_tool_commit"],
            artifact_sha256=None, source_root=source_root,
            candidate_rows=plan_result["candidate_reference_files"], plan=plan_result["plan"],
            rollback_target_release_id=target_release_id, approved_removals=approved_removals,
            current_state=current, private=private, lock_fd=lock_fd,
            private_root=private_root, public_root=public_root,
            expected_private_root=expected_private_root, expected_public_root=expected_public_root,
            quota_free_bytes=quota_free_bytes, inventory_reader=reader,
            health_check=health_check, rollback_health_check=rollback_health_check,
            fault_hook=fault_hook)
    except (backup_tool.BackupError, baseline_tool.BaselineError,
            release_state_tool.ReleaseStateError, OSError, ValueError) as exc:
        if isinstance(exc, PublisherError):
            raise
        raise PublisherError(f"Rollback filesystem bloccato: {exc}") from exc
    finally:
        if lock_fd is not None:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if private is not None:
            backup_tool.close_private_directories(private)


def recover_filesystem_release(*, operation_id, private_root, expected_private_root,
                               public_root, expected_public_root, quota_free_bytes,
                               health_check, inventory_reader=None):
    """Riprende una transazione interrotta dal journal e dal manifest privato verificato."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not callable(health_check):
        raise PublisherError("Recovery richiede POSIX/O_NOFOLLOW e health check.")
    if pathlib.Path(public_root) != pathlib.Path(expected_public_root):
        raise PublisherError("Root pubblica diversa dal target autorizzato.")
    private = lock_fd = transaction_dir_fd = None
    try:
        private, lock_fd = _open_release_context(private_root, expected_private_root)
        current = release_state_tool.load_current_state(private["state_fd"])
        events = release_state_tool.read_journal_at(private["state_fd"])
        operation = [event for event in events if event["operation_id"] == operation_id]
        if not operation or operation[0]["status"] != "prepared":
            raise PublisherError("Operazione assente dal journal o senza evento prepared.")
        prepared = operation[0]["details"]
        manifest_sha = prepared.get("transaction_manifest_sha256")
        if not re.fullmatch(r"[a-f0-9]{64}", str(manifest_sha or "")):
            raise PublisherError("Journal senza digest del manifest privato di recovery.")
        transaction_dir_fd = _transaction_directory(private["staging_fd"])
        raw_manifest = _read_private_file_at(transaction_dir_fd, f"transaction-{operation_id}.json")
        if hashlib.sha256(raw_manifest).hexdigest() != manifest_sha:
            raise PublisherError("Manifest transazione privato alterato.")
        try:
            manifest = release_state_tool._read_json(raw_manifest, "manifest transazione")
        except release_state_tool.ReleaseStateError as exc:
            raise PublisherError(f"Manifest transazione non valido: {exc}") from exc
        required = {"schema_version", "operation_id", "operation_kind", "release_id", "commit_sha",
                    "inventory_tool_commit", "artifact_sha256", "parent_state_sha256", "parent_release_id",
                    "parent_inventory_sha256", "backup", "plan", "plan_sha256", "rollback_target_release_id",
                    "parent_reference_files", "candidate_reference_files", "source_root", "recovery_root",
                    "public_root", "approved_removals"}
        if (not isinstance(manifest, dict) or set(manifest) != required
                or manifest["schema_version"] != 1 or manifest["operation_id"] != operation_id
                or manifest["public_root"] != str(pathlib.Path(public_root))
                or release_state_tool.digest_json(manifest["plan"]) != manifest["plan_sha256"]):
            raise PublisherError("Manifest recovery non corrispondente a operazione, parent o destinazione.")
        if (prepared.get("parent_document_sha256") != manifest["parent_state_sha256"]
                or prepared.get("parent_release_id") != manifest["parent_release_id"]
                or prepared.get("parent_inventory_sha256") != manifest["parent_inventory_sha256"]):
            raise PublisherError("Manifest recovery non corrisponde all'intento nel journal.")
        if current["state_sha256"] != manifest["parent_state_sha256"]:
            if (current.get("schema_version") == release_state_tool.APPLICATION_STATE_SCHEMA
                    and current.get("release_chain", {}).get("entries")
                    and current["release_chain"]["entries"][-1].get("operation_id") == operation_id):
                release_state_tool.validate_current_state_journal(current, events)
                _verify_fresh_snapshot(
                    inventory_reader or baseline_tool.acquire_fresh_inventory,
                    current["release"]["inventory_tool_commit"], current["reference_files"],
                    current["inventory"]["exclusion"], current["inventory_sha256"])
                return {"status": "already-finalized", "operation_id": operation_id,
                        "state_sha256": current["state_sha256"], "public_writes_performed": False}
            raise PublisherError("Current-release non coincide né con il parent né con la transazione conclusa.")
        if (manifest["parent_release_id"] != current["release"]["release_id"]
                or manifest["parent_inventory_sha256"] != current["inventory_sha256"]):
            raise PublisherError("Manifest recovery parent diverso dal current-release.")
        _, _, parent_chain_sha = release_state_tool._application_release_parent(current)
        if prepared.get("parent_state_sha256") != parent_chain_sha:
            raise PublisherError("Parent della catena nel journal recovery diverso dal current-release.")
        backup_reference = manifest["backup"]
        baseline_sha = current["initial_baseline"]["sha256"]
        _verify_backup_for_parent(private, current, backup_reference)
        recovery_root = pathlib.Path(manifest["recovery_root"])
        staging_root = pathlib.Path(private_root) / "staging"
        _require_staging_path(staging_root, recovery_root, "snapshot recovery", directory=True)
        if recovery_root.name != "restored":
            raise PublisherError("Directory recovery non è la root estratta autorizzata.")
        actual_snapshot = inventory_target_tree(recovery_root)
        parent_expected = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                           for row in manifest["parent_reference_files"]}
        if actual_snapshot != parent_expected:
            raise PublisherError("Snapshot privato di recovery diverso dal parent verificato.")

        operation_status = operation[-1]["status"]
        if operation_status in ("release_committed", "release_rolled_back"):
            health_event = next((event for event in reversed(operation)
                                 if event["status"] == "health_verified"), None)
            candidate_digest = health_event["details"].get("candidate_state_sha256") if health_event else None
            if not re.fullmatch(r"[a-f0-9]{64}", str(candidate_digest or "")):
                raise PublisherError("Terminale presente ma stato candidato durevole assente.")
            candidate_raw = _read_private_file_at(
                transaction_dir_fd, f"candidate-{operation_id}.json")
            if hashlib.sha256(candidate_raw).hexdigest() != candidate_digest:
                raise PublisherError("Stato candidato privato alterato dopo il terminale.")
            candidate = release_state_tool.validate_state_document(
                release_state_tool._read_json(candidate_raw, "stato candidato"), baseline_sha)
            if (candidate["release_chain"]["entries"][-1]["operation_id"] != operation_id
                    or current["state_sha256"] != manifest["parent_state_sha256"]):
                raise PublisherError("Stato candidato terminale non discende dal parent corrente.")
            reader = inventory_reader or baseline_tool.acquire_fresh_inventory
            release_state_tool.validate_fresh_release_inventories(
                candidate, (reader(candidate["release"]["inventory_tool_commit"]),
                           reader(candidate["release"]["inventory_tool_commit"])))
            # L'evidenza originale è già legata al candidato conservato e al
            # terminale journalizzato. Dopo un crash si richiede un nuovo esito
            # sano, ma il digest non deve coincidere: i controlli HTTP includono
            # timestamp e altri dati variabili tra richieste.
            recovery_health, _ = _health_evidence(health_check)
            promoted = release_state_tool.persist_verified_application_release_state(
                candidate, current["state_sha256"], private_root=private_root,
                expected_root=expected_private_root, baseline_sha256=baseline_sha,
                inventory_reader=reader, lock_fd=lock_fd)
            return {"status": "finalized-after-interruption", "operation_id": operation_id,
                    "state": promoted, "health_evidence": recovery_health,
                    "public_writes_performed": False}

        if operation_status == "recovery_completed":
            release_state_tool.validate_current_state_journal(current, events)
            return {"status": "already-recovered", "operation_id": operation_id,
                    "state_sha256": current["state_sha256"], "public_writes_performed": False}
        if operation_status != "recovery_required":
            release_state_tool.append_operation_event(
                private["state_fd"], private["locks_fd"], operation_id, "recovery_required",
                {"reason": "process-interruption", "message": "Recovery manuale verificata"},
                lock_fd=lock_fd)
        recovered = recover_file_snapshot(
            recovery_root, public_root, manifest["parent_reference_files"],
            manifest["candidate_reference_files"])
        if recovered["inventory"] != parent_expected:
            raise PublisherError("Inventario live non ripristinato al parent.")
        reader = inventory_reader or baseline_tool.acquire_fresh_inventory
        _verify_fresh_snapshot(reader, current["release"]["inventory_tool_commit"],
                               current["reference_files"], current["inventory"]["exclusion"],
                               current["inventory_sha256"])
        _, health_digest = _health_evidence(health_check)
        result = release_state_tool.append_verified_recovery_completion(
            operation_id, current["state_sha256"], backup_id=backup_reference["backup_id"],
            backup_manifest_sha256=backup_reference["manifest_sha256"],
            restored_inventory_sha256=current["inventory_sha256"],
            health_evidence_sha256=health_digest, private_root=private_root,
            expected_root=expected_private_root, inventory_reader=reader, lock_fd=lock_fd)
        return {"status": result["status"], "operation_id": operation_id,
                "state_sha256": current["state_sha256"],
                "files_restored": recovered["written"], "public_writes_performed": True}
    except (backup_tool.BackupError, baseline_tool.BaselineError,
            release_state_tool.ReleaseStateError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, PublisherError):
            raise
        raise PublisherError(f"Recovery bloccata in fail-closed: {exc}") from exc
    finally:
        if transaction_dir_fd is not None:
            os.close(transaction_dir_fd)
        if lock_fd is not None:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if private is not None:
            backup_tool.close_private_directories(private)


def _load_verified_current_state(expected_state_sha256, *, inventory_reader=None):
    """Rilegge stato, journal e inventari con i descriptor privati e il lock CLI."""
    private = None
    lock_fd = None
    try:
        private = backup_tool.open_private_directories(PRIVATE_ROOT, PRIVATE_ROOT)
        lock_fd = baseline_tool.acquire_baseline_lock(None, private["locks_fd"])
        state = release_state_tool.load_current_state(
            private["state_fd"], production_adapter.BASELINE_SHA256)
        events = release_state_tool.read_journal_at(private["state_fd"])
        release_state_tool.validate_current_state_journal(state, events)
        if state["state_sha256"] != expected_state_sha256:
            raise PublisherError("current-release è cambiato dopo l'ispezione iniziale.")
        tool_commit = state["release"]["inventory_tool_commit"]
        reader = inventory_reader or baseline_tool.acquire_fresh_inventory
        fresh = (reader(tool_commit), reader(tool_commit))
        release_state_tool.validate_fresh_release_inventories(state, fresh)
        return state
    except (backup_tool.BackupError, baseline_tool.BaselineError,
            release_state_tool.ReleaseStateError, OSError) as exc:
        raise PublisherError(f"Stato release non verificabile per il piano: {exc}") from exc
    finally:
        if lock_fd is not None:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if private is not None:
            backup_tool.close_private_directories(private)


def build_preflight(package_root, inventory_path, release_sha, *, provenance_path,
                    archive_path, expected_run_id, toolchain_sha256=None):
    """Confronta candidato e live con autorità esplicita; non scrive alcun file."""
    if toolchain_sha256 is not None:
        production_adapter.verify_private_toolchain(toolchain_sha256)
    records = verify_artifact(package_root, inventory_path, release_sha,
                              provenance_path=provenance_path, archive_path=archive_path,
                              expected_run_id=expected_run_id)
    if toolchain_sha256 is None:
        inspection = production_adapter.inspect_production_state(release_sha)
        if production_adapter._git_output(["branch", "--show-current"]).decode("ascii").strip() != "main":
            raise PublisherError("Il preflight legacy richiede il branch Git main.")
        reader = None
    else:
        inspection = production_adapter.inspect_production_state(toolchain_sha256=toolchain_sha256)
        reader = production_adapter.private_inventory_reader(toolchain_sha256)
    blockers = list(inspection["blockers"])
    live = {row["path"]: row for row in inspection.get("live_file_records", [])}
    reference = {row["path"]: row for row in inspection.get("current_reference_files", [])}
    if not reference:
        blockers.append("Stato current-release assente o senza inventario di riferimento.")
    if set(live) != set(reference) or any(
        live.get(path, {}).get("sha256") != row.get("sha256")
        or live.get(path, {}).get("size") != row.get("size")
        or live.get(path, {}).get("mode") != row.get("mode")
        for path, row in reference.items()
    ):
        blockers.append("Drift live rispetto a current-release: pubblicazione rifiutata.")
    changes, retained, diff_blockers = plan_inventory_changes(records, live, reference)
    blockers.extend(diff_blockers)
    release_plan = None
    current = inspection.get("current_release")
    if current and current.get("state_sha256"):
        current_state = _load_verified_current_state(current["state_sha256"], inventory_reader=reader)
        operation_id = "plan-" + uuid.uuid4().hex
        try:
            release_plan = make_release_state_plan(current_state, records, operation_id)
        except release_state_tool.ReleaseStateError as exc:
            blockers.append(f"Piano release non autorizzabile: {exc}")
    # Il piano è soltanto una fotografia read-only; non equivale a una
    # transazione journalizzata né a un'autorizzazione di scrittura.
    blockers.append("Scritture pubbliche disabilitate: barriera HTTP/PHP e OPcache da collaudare su IONOS.")
    blockers.append("Writer multi-file non abilitato: mancano prova di drain PHP-FPM e adozione uniforme OPcache.")
    return {
        "status": "blocked" if blockers else "ready",
        "release_sha": release_sha,
        "toolchain_sha256": inspection.get("toolchain_sha256"),
        "publish_allowed": False,
        "artifact_files": len(records),
        "live_files": len(live),
        "changes": changes,
        "release_plan": release_plan,
        "retained_live_extras": retained,
        "blockers": blockers,
        "public_writes_performed": False,
    }


def blocked_operation(name):
    raise PublisherError(
        f"{name} rifiutato: non esiste un writer di produzione abilitato. "
        "Nessun file pubblico è stato modificato. Completare prima il collaudo PHP web/OPcache."
    )


def _require_private_staging_paths(package, inventory, provenance, archive):
    """Limita i file usati dal preflight server all'area privata di staging."""
    staging = PRIVATE_ROOT / "staging"
    try:
        production_adapter._require_fixed_directory(PRIVATE_ROOT)
        production_adapter._require_fixed_directory(staging)
    except production_adapter.ProductionAdapterError as exc:
        raise PublisherError(f"Area privata non verificabile: {exc}") from exc
    for label, raw in (("package", package), ("inventory", inventory),
                       ("provenance", provenance), ("archive", archive)):
        path = pathlib.Path(raw)
        if not path.is_absolute():
            raise PublisherError(f"Percorso {label} deve essere assoluto.")
        try:
            relative = path.relative_to(staging)
        except ValueError as exc:
            raise PublisherError(f"Percorso {label} fuori da staging privata.") from exc
        if (not relative.parts or any(part in ("", ".", "..") for part in relative.parts)):
            raise PublisherError(f"Percorso {label} non può coincidere con la root staging.")
        current = staging
        for component in relative.parts[:-1] if label != "package" else relative.parts:
            current = current / component
            try:
                info = current.lstat()
            except OSError as exc:
                raise PublisherError(f"Percorso {label} assente o non sicuro.") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise PublisherError(f"Symlink o componente non-directory nel percorso {label}.")
        if label == "package":
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise PublisherError("Root package non-directory o symlink.")
        else:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PublisherError(f"File {label} non regolare o hard link.")


def create_provenance(inventory_path, archive_path, output_path, release_sha, run_id, ref):
    """Crea provenance del job corrente in modo esclusivo; non è firma crittografica."""
    if (not re.fullmatch(r"[a-f0-9]{40}", str(release_sha or ""))
            or not re.fullmatch(r"[0-9]+", str(run_id or ""))
            or ref != "refs/heads/main"):
        raise PublisherError("Commit, run ID o ref non validi per la provenance.")
    inventory_digest = hashlib.sha256(_read_regular(inventory_path, 32 * 1024 * 1024)).hexdigest()
    archive_digest = _artifact_file_digest(archive_path, 2 * 1024 * 1024 * 1024)
    document = {
        "schema_version": 1,
        "repository": GITHUB_REPOSITORY,
        "commit_sha": release_sha,
        "ref": ref,
        "run_id": str(run_id),
        "inventory_sha256": inventory_digest,
        "archive_sha256": archive_digest,
        "workflow_run_url": f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{run_id}",
    }
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    output = pathlib.Path(output_path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(output, flags, 0o600)
    except OSError as exc:
        raise PublisherError("Creazione provenance esclusiva fallita; output già presente o non sicuro.") from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise PublisherError("Scrittura provenance incompleta.")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return document


def _require_ci_provenance_context(args):
    """Impedisce che il comando CI crei file su percorsi scelti fuori dal runner."""
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": GITHUB_REPOSITORY,
        "GITHUB_SHA": args.release_sha,
        "GITHUB_REF": args.ref,
        "GITHUB_RUN_ID": str(args.run_id),
    }
    if any(os.environ.get(name) != value for name, value in expected.items()):
        raise PublisherError("create-provenance è consentito soltanto nel run GitHub Actions corrispondente.")
    raw_temp = os.environ.get("RUNNER_TEMP", "")
    temp = pathlib.Path(raw_temp)
    if not temp.is_absolute():
        raise PublisherError("RUNNER_TEMP assente o non assoluto.")
    try:
        if temp.resolve(strict=True) != temp:
            raise PublisherError("RUNNER_TEMP non canonico.")
        for label, raw in (("inventory", args.inventory), ("archive", args.archive),
                           ("output", args.output)):
            path = pathlib.Path(raw)
            if not path.is_absolute():
                raise PublisherError(f"Percorso {label} CI non assoluto.")
            relative = path.relative_to(temp)
            if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
                raise PublisherError(f"Percorso {label} fuori da RUNNER_TEMP.")
            current = temp
            for part in relative.parts[:-1]:
                current = current / part
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                    raise PublisherError(f"Percorso {label} con directory non sicura.")
            target = current / relative.parts[-1]
            if label == "output":
                try:
                    target.lstat()
                except FileNotFoundError:
                    pass
                else:
                    raise PublisherError("Output provenance già esistente.")
            else:
                info = target.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise PublisherError(f"File {label} CI non regolare o hard link.")
    except (OSError, ValueError) as exc:
        if isinstance(exc, PublisherError):
            raise
        raise PublisherError("Percorsi CI non verificabili dentro RUNNER_TEMP.") from exc


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="ispezione read-only dello stato pubblico")
    status_authority = status.add_mutually_exclusive_group(required=True)
    status_authority.add_argument("--authorized-sha")
    status_authority.add_argument("--toolchain-sha256")
    verify = commands.add_parser("verify-artifact", help="verifica offline package, archivio e provenance")
    verify.add_argument("--release-sha", required=True)
    verify.add_argument("--package", required=True)
    verify.add_argument("--inventory", required=True)
    verify.add_argument("--provenance", required=True)
    verify.add_argument("--archive", required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--toolchain-sha256", help="verifica anche gli strumenti privati con il digest CI approvato")
    create = commands.add_parser("create-provenance", help="crea provenance esclusiva per l'artefatto CI")
    create.add_argument("--release-sha", required=True)
    create.add_argument("--ref", required=True)
    create.add_argument("--run-id", required=True)
    create.add_argument("--inventory", required=True)
    create.add_argument("--archive", required=True)
    create.add_argument("--output", required=True)
    for command in ("preflight", "publish"):
        item = commands.add_parser(command)
        item.add_argument("--release-sha", required=True)
        item.add_argument("--package", required=True)
        item.add_argument("--inventory", required=True)
        item.add_argument("--provenance", required=True)
        item.add_argument("--archive", required=True)
        item.add_argument("--run-id", required=True)
        item.add_argument("--toolchain-sha256", help="autorità privata indipendente dal checkout Git")
    backup = commands.add_parser("backup", help="crea e verifica un backup fresco solo nell'area privata")
    backup.add_argument("--account-quota-free-bytes", type=int, required=True)
    backup.add_argument("--confirm", required=True,
                        help="conferma esatta: CREATE-BACKUP <SHA-256 baseline ufficiale>")
    for command in ("rollback", "recover"):
        item = commands.add_parser(command)
        item.add_argument("--operation-id", required=True)
        if command == "rollback":
            item.add_argument("--backup-id", required=True)
            item.add_argument("--manifest-sha256", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            result = production_adapter.inspect_production_state(
                args.authorized_sha, toolchain_sha256=args.toolchain_sha256)
        elif args.command == "create-provenance":
            _require_ci_provenance_context(args)
            result = create_provenance(args.inventory, args.archive, args.output,
                                       args.release_sha, args.run_id, args.ref)
        elif args.command == "verify-artifact":
            if (args.toolchain_sha256 is None
                    and pathlib.Path(__file__).absolute().parent == production_adapter.PRIVATE_TOOLS_ROOT):
                raise PublisherError("La verifica dalla toolchain privata richiede --toolchain-sha256 dal report CI approvato.")
            if args.toolchain_sha256 is not None:
                production_adapter.verify_private_toolchain(args.toolchain_sha256)
                _require_private_staging_paths(args.package, args.inventory, args.provenance, args.archive)
            records = verify_artifact(args.package, args.inventory, args.release_sha,
                                      provenance_path=args.provenance, archive_path=args.archive,
                                      expected_run_id=args.run_id)
            result = {"status": "verified", "release_sha": args.release_sha,
                      "run_id": args.run_id, "files": len(records),
                      "provenance_is_signature": False}
            if args.toolchain_sha256 is not None:
                result["toolchain_sha256"] = args.toolchain_sha256
        elif args.command == "backup":
            expected = f"CREATE-BACKUP {production_adapter.BASELINE_SHA256}"
            if args.confirm != expected:
                raise PublisherError("Conferma backup privata non corrispondente alla baseline ufficiale.")
            backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
            result = backup_tool.create_backup(
                backup_id, production_adapter.BASELINE_SHA256, args.account_quota_free_bytes)
        elif args.command in ("preflight", "publish"):
            _require_private_staging_paths(args.package, args.inventory, args.provenance, args.archive)
            result = build_preflight(
                args.package, args.inventory, args.release_sha,
                provenance_path=args.provenance, archive_path=args.archive,
                expected_run_id=args.run_id, toolchain_sha256=args.toolchain_sha256)
            if args.command == "publish":
                blocked_operation("publish")
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0 if result["status"] == "ready" else 3
        elif args.command in ("rollback", "recover"):
            blocked_operation(args.command)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (PublisherError, backup_tool.BackupError, production_adapter.ProductionAdapterError,
            baseline_tool.BaselineError, OSError, ValueError, KeyError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
