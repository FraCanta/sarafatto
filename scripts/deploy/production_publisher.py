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
from datetime import datetime, timezone

import baseline_tool
import backup_tool
import production_adapter

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
                visit(entry, rel)
            elif stat.S_ISREG(info.st_mode):
                if (not baseline_tool.safe_path(rel) or not _in_component(rel)
                        or baseline_tool.excluded(rel)):
                    raise PublisherError(f"File artefatto fuori perimetro: {rel}.")
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


def build_preflight(package_root, inventory_path, release_sha, *, provenance_path,
                    archive_path, expected_run_id):
    """Confronta candidato, commit server e live; non scrive alcun file."""
    records = verify_artifact(package_root, inventory_path, release_sha,
                              provenance_path=provenance_path, archive_path=archive_path,
                              expected_run_id=expected_run_id)
    try:
        authorized = production_adapter.verify_repository_sources(release_sha)
        branch = production_adapter._git_output(["branch", "--show-current"]).decode("ascii").strip()
    except (production_adapter.ProductionAdapterError, UnicodeError) as exc:
        raise PublisherError(f"Repository IONOS non autorizzato: {exc}") from exc
    if branch != "main" or authorized != release_sha:
        raise PublisherError("Repository server non è main allo SHA esatto dell'artefatto.")
    inspection = production_adapter.inspect_production_state(release_sha)
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
    # L'implementazione non ha ancora un writer verificato per journal/current-state
    # né prova uniforme OPcache: queste condizioni non sono trasformabili in flag.
    blockers.append("Scritture pubbliche disabilitate: barriera HTTP/PHP e OPcache da collaudare su IONOS.")
    blockers.append("Writer transazionale di produzione non abilitato; nessuna modifica pubblica consentita.")
    return {
        "status": "blocked" if blockers else "ready",
        "release_sha": release_sha,
        "artifact_files": len(records),
        "live_files": len(live),
        "changes": changes,
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
    status.add_argument("--authorized-sha", required=True)
    verify = commands.add_parser("verify-artifact", help="verifica offline package, archivio e provenance")
    verify.add_argument("--release-sha", required=True)
    verify.add_argument("--package", required=True)
    verify.add_argument("--inventory", required=True)
    verify.add_argument("--provenance", required=True)
    verify.add_argument("--archive", required=True)
    verify.add_argument("--run-id", required=True)
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
            result = production_adapter.inspect_production_state(args.authorized_sha)
        elif args.command == "create-provenance":
            _require_ci_provenance_context(args)
            result = create_provenance(args.inventory, args.archive, args.output,
                                       args.release_sha, args.run_id, args.ref)
        elif args.command == "verify-artifact":
            records = verify_artifact(args.package, args.inventory, args.release_sha,
                                      provenance_path=args.provenance, archive_path=args.archive,
                                      expected_run_id=args.run_id)
            result = {"status": "verified", "release_sha": args.release_sha,
                      "run_id": args.run_id, "files": len(records),
                      "provenance_is_signature": False}
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
                expected_run_id=args.run_id)
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
