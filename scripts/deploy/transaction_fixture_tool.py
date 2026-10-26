#!/usr/bin/env python3
"""Preflight, deploy simulato e rollback confinati a fixture temporanee.

Il modulo non espone CLI e rifiuta ogni workspace che non sia stato creato sotto
la directory temporanea del sistema. Non contiene un adattatore per WordPress.
"""

import base64
import ctypes
import errno
import hashlib
import hmac
import json
import os
import pathlib
import re
import shutil
import secrets
import stat
import tempfile
import uuid
from dataclasses import dataclass

import baseline_tool as baseline
import release_state_tool as release_state

try:
    import fcntl
except ImportError:
    fcntl = None

FIXTURE_MARKER = ".sarafatto-transaction-fixture"
FIXTURE_MARKER_VALUE = "sarafatto-transaction-fixture-v1"
PUBLIC_PRODUCTION = pathlib.Path("/home/www/public/wp-content")
ALLOWED_SINGLE = baseline.SINGLE_FILE
ENTRYPOINTS = (
    "assets/src/js/app.js", "assets/src/js/home.js",
    "assets/src/js/product.js", "assets/src/js/product-archive.js",
)
MAX_JSON = 32 * 1024 * 1024
TOKEN = object()
_REMOVAL_APPROVAL_KEY = secrets.token_bytes(32)


class TransactionError(Exception):
    """Errore fail-closed nel preflight o nella simulazione fixture."""


@dataclass(frozen=True)
class FixtureWorkspace:
    root: pathlib.Path
    root_identity: tuple
    public_root: pathlib.Path
    private_root: pathlib.Path
    artifact_root: pathlib.Path
    state_dir: pathlib.Path
    backups_dir: pathlib.Path
    staging_dir: pathlib.Path
    locks_dir: pathlib.Path
    _token: object


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_digest(value):
    return release_state.digest_json(value)


def _safe_relative(path):
    if not baseline.safe_path(path) or baseline.excluded(path):
        raise TransactionError(f"Percorso fuori allowlist o non sicuro: {path!r}.")
    return path


def _safe_directory(relative):
    """Valida i soli contenitori necessari per raggiungere file gestiti."""
    return (
        relative in ("themes", "plugins", "mu-plugins")
        or relative == "themes/sarafatto"
        or relative.startswith("themes/sarafatto/")
        or relative == "plugins/sarafatto-core"
        or relative.startswith("plugins/sarafatto-core/")
    )


def _within(path, root):
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def _validate_workspace(workspace):
    if not isinstance(workspace, FixtureWorkspace) or workspace._token is not TOKEN:
        raise TransactionError("È accettato soltanto un workspace fixture creato da questo modulo.")
    temp_root = pathlib.Path(tempfile.gettempdir()).resolve(strict=True)
    try:
        root = workspace.root.resolve(strict=True)
        public_prod = PUBLIC_PRODUCTION.resolve(strict=False)
    except OSError as exc:
        raise TransactionError("Percorsi fixture non risolvibili.") from exc
    if (root == temp_root or not _within(root, temp_root) or root == public_prod
            or _within(public_prod, root) or _within(root, public_prod)):
        raise TransactionError("Workspace fuori dalla root temporanea autorizzata.")
    root_fd = None
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_info = os.fstat(root_fd)
        if ((root_info.st_dev, root_info.st_ino) != workspace.root_identity
                or not stat.S_ISDIR(root_info.st_mode)
                or os.name == "posix" and
                (root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700)):
            raise TransactionError("Identità, proprietario o permessi della root fixture sono cambiati.")

        marker_fd = os.open(FIXTURE_MARKER, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            marker_info = os.fstat(marker_fd)
            if (not stat.S_ISREG(marker_info.st_mode) or marker_info.st_nlink != 1
                    or marker_info.st_size > 1024):
                raise TransactionError("Marker fixture non regolare o non valido.")
            marker_raw = os.read(marker_fd, 1025)
        finally:
            os.close(marker_fd)
        if marker_raw.decode("ascii").strip() != FIXTURE_MARKER_VALUE:
            raise TransactionError("Marker fixture assente o non valido.")

        expected = {
            "public_root": ("public", "wp-content"),
            "private_root": ("private",),
            "artifact_root": ("artifact",),
            "state_dir": ("private", "state"),
            "backups_dir": ("private", "backups"),
            "staging_dir": ("private", "staging"),
            "locks_dir": ("private", "locks"),
        }
        for name, parts in expected.items():
            if getattr(workspace, name) != root.joinpath(*parts):
                raise TransactionError(f"Percorso fixture {name} non corrispondente alla root.")
            current_fd = os.dup(root_fd)
            try:
                for part in parts:
                    next_fd = _open_dir(current_fd, part)
                    os.close(current_fd)
                    current_fd = next_fd
                info = os.fstat(current_fd)
                if not stat.S_ISDIR(info.st_mode):
                    raise TransactionError(f"Directory fixture non regolare: {name}.")
                if os.name == "posix" and (info.st_uid != os.getuid()
                                             or stat.S_IMODE(info.st_mode) != 0o700):
                    raise TransactionError(f"Proprietario o permessi fixture inattesi: {name}.")
            except OSError as exc:
                raise TransactionError(f"Directory fixture mancante o sostituita: {name}.") from exc
            finally:
                os.close(current_fd)
    except OSError as exc:
        raise TransactionError("Root o marker fixture mancante, sostituito o illeggibile.") from exc
    finally:
        if root_fd is not None:
            os.close(root_fd)
    return root


def create_fixture_workspace(parent=None):
    """Crea tutte le radici sotto tempfile.gettempdir(); non accetta root pubbliche."""
    if fcntl is None or os.name != "posix":
        raise TransactionError("Il motore fixture richiede POSIX e flock.")
    temp_root = pathlib.Path(tempfile.gettempdir()).resolve(strict=True)
    selected = pathlib.Path(parent).resolve(strict=True) if parent is not None else temp_root
    if selected != temp_root and not _within(selected, temp_root):
        raise TransactionError("La directory padre deve restare sotto la root temporanea di sistema.")
    if selected == PUBLIC_PRODUCTION.resolve(strict=False):
        raise TransactionError("La root pubblica WordPress è sempre vietata.")
    root = pathlib.Path(tempfile.mkdtemp(prefix="sarafatto-transaction-fixture-", dir=selected))
    root_info = root.stat(follow_symlinks=False)
    paths = {
        "public_root": root / "public" / "wp-content",
        "private_root": root / "private",
        "artifact_root": root / "artifact",
        "state_dir": root / "private" / "state",
        "backups_dir": root / "private" / "backups",
        "staging_dir": root / "private" / "staging",
        "locks_dir": root / "private" / "locks",
    }
    for path in (paths["public_root"] / "themes" / "sarafatto",
                 paths["public_root"] / "plugins" / "sarafatto-core",
                 paths["public_root"] / "mu-plugins", paths["private_root"],
                 paths["state_dir"], paths["backups_dir"], paths["staging_dir"],
                 paths["locks_dir"], paths["artifact_root"] / "themes" / "sarafatto",
                 paths["artifact_root"] / "plugins" / "sarafatto-core",
                 paths["artifact_root"] / "mu-plugins"):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    paths["public_root"].chmod(0o700)
    paths["artifact_root"].chmod(0o700)
    marker = root / FIXTURE_MARKER
    marker.write_text(FIXTURE_MARKER_VALUE + "\n", encoding="ascii")
    marker.chmod(0o600)
    workspace = FixtureWorkspace(root=root, root_identity=(root_info.st_dev, root_info.st_ino),
                                 **paths, _token=TOKEN)
    _validate_workspace(workspace)
    return workspace


def _open_dir(parent_fd, name, create=False):
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        raise TransactionError(f"Directory non regolare: {name}.")
    return fd


def _open_parent(root_fd, relative, create=False):
    parts = _safe_relative(relative).split("/")
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = _open_dir(current, part, create=create)
            os.close(current)
            current = next_fd
        return current, parts[-1]
    except Exception:
        os.close(current)
        raise


def _read_at(root_fd, relative, limit=MAX_JSON):
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        raise TransactionError(f"File assente o non regolare: {relative}.") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise TransactionError(f"File speciale, hard link o dimensione non valida: {relative}.")
        chunks, total = [], 0
        while True:
            block = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise TransactionError(f"File troppo grande: {relative}.")
            chunks.append(block)
        return b"".join(chunks), format(stat.S_IMODE(info.st_mode), "o")
    finally:
        os.close(fd)
        os.close(parent_fd)


def _write_new_at(root_fd, relative, data, mode=0o600, create_dirs=False):
    parent_fd, name = _open_parent(root_fd, relative, create=create_dirs)
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        if os.write(fd, data) != len(data):
            raise TransactionError(f"Scrittura incompleta: {relative}.")
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.fsync(parent_fd)
    except OSError as exc:
        raise TransactionError(f"Scrittura sicura fallita: {relative}.") from exc
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def _replace_at(root_fd, relative, data, mode, expected_before):
    parent_fd, name = _open_parent(root_fd, relative, create=True)
    temp_name = ".sf-txn-" + uuid.uuid4().hex
    temp_fd = None
    try:
        try:
            current_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            if expected_before is not None:
                raise TransactionError(f"Collisione: file sparito prima della sostituzione: {relative}.")
        else:
            try:
                current = os.fstat(current_fd)
                if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                    raise TransactionError(f"Destinazione speciale o hard link: {relative}.")
                if expected_before is None:
                    raise TransactionError(f"Collisione con file preesistente: {relative}.")
                content = bytearray()
                while True:
                    block = os.read(current_fd, 1024 * 1024)
                    if not block:
                        break
                    content.extend(block)
                if (_sha(content) != expected_before["sha256"]
                        or len(content) != expected_before["size"]
                        or format(stat.S_IMODE(current.st_mode), "o") != expected_before["mode"]):
                    raise TransactionError(f"Modifica concorrente rilevata: {relative}.")
            finally:
                os.close(current_fd)
        temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          mode, dir_fd=parent_fd)
        if os.write(temp_fd, data) != len(data):
            raise TransactionError(f"Scrittura temporanea incompleta: {relative}.")
        os.fchmod(temp_fd, mode)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None
        if expected_before is None:
            try:
                os.link(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            except FileExistsError as exc:
                raise TransactionError(f"Collisione concorrente su nuovo file: {relative}.") from exc
            os.unlink(temp_name, dir_fd=parent_fd)
        else:
            renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
            if renameat2 is None:
                raise TransactionError("renameat2(RENAME_EXCHANGE) non disponibile; sostituzione bloccata.")
            renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            renameat2.restype = ctypes.c_int
            if renameat2(parent_fd, os.fsencode(temp_name), parent_fd, os.fsencode(name), 2) != 0:
                error = ctypes.get_errno()
                raise TransactionError(f"Scambio atomico fixture non riuscito: errno {error}.")
            swapped = True
            try:
                # Dopo lo scambio il temporaneo contiene il vecchio file: la verifica
                # rileva eventuali modifiche concorrenti avvenute prima dello scambio.
                old_fd = os.open(temp_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
                try:
                    old_info = os.fstat(old_fd)
                    old_digest = hashlib.sha256()
                    old_size = 0
                    while True:
                        block = os.read(old_fd, 1024 * 1024)
                        if not block:
                            break
                        old_digest.update(block)
                        old_size += len(block)
                    if (not stat.S_ISREG(old_info.st_mode) or old_info.st_nlink != 1
                            or old_digest.hexdigest() != expected_before["sha256"]
                            or old_size != expected_before["size"]
                            or format(stat.S_IMODE(old_info.st_mode), "o") != expected_before["mode"]):
                        raise TransactionError(f"Modifica concorrente rilevata: {relative}.")
                finally:
                    os.close(old_fd)
                new_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
                try:
                    new_info = os.fstat(new_fd)
                    new_digest = hashlib.sha256()
                    new_size = 0
                    while True:
                        block = os.read(new_fd, 1024 * 1024)
                        if not block:
                            break
                        new_digest.update(block)
                        new_size += len(block)
                    if (not stat.S_ISREG(new_info.st_mode) or new_info.st_nlink != 1
                            or new_digest.hexdigest() != _sha(data) or new_size != len(data)):
                        raise TransactionError(f"Nuovo file cambiato durante la pubblicazione: {relative}.")
                finally:
                    os.close(new_fd)
            except Exception:
                if renameat2(parent_fd, os.fsencode(temp_name), parent_fd, os.fsencode(name), 2) != 0:
                    raise TransactionError("Verifica concorrente fallita e scambio inverso non riuscito.")
                swapped = False
                raise
            if swapped:
                os.unlink(temp_name, dir_fd=parent_fd)
                swapped = False
        os.fsync(parent_fd)
    except OSError as exc:
        raise TransactionError(f"Sostituzione fixture fallita: {relative}.") from exc
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _unlink_verified(root_fd, relative, expected_record):
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise TransactionError(f"Rimozione rifiutata per file speciale/hard link: {relative}.")
            data = bytearray()
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                data.extend(block)
            if (_sha(data) != expected_record["sha256"] or len(data) != expected_record["size"]
                    or format(stat.S_IMODE(info.st_mode), "o") != expected_record["mode"]):
                raise TransactionError(f"Hash cambiato: rimozione bloccata per {relative}.")
        finally:
            os.close(fd)
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _inventory(root, root_fd, reject_node_modules=False):
    records = {}

    def visit(directory_fd, prefix=""):
        for name in sorted(os.listdir(directory_fd)):
            if name in (".", "..") or any(ch in name for ch in "/\\\t\r\n"):
                raise TransactionError("Nome file non sicuro nella fixture.")
            relative = f"{prefix}/{name}" if prefix else name
            if baseline.excluded(relative):
                # L'esclusione è esattamente il node_modules locale del tema;
                # si pruna senza seguire o enumerare i suoi link interni.
                if reject_node_modules:
                    raise TransactionError("node_modules non può essere incluso nell'artefatto fixture.")
                continue
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise TransactionError(f"Symlink fixture vietato: {relative}.")
            if stat.S_ISDIR(info.st_mode):
                if not _safe_directory(relative) or baseline.excluded(relative):
                    raise TransactionError(f"Directory contenitore fuori allowlist: {relative}.")
                child_fd = _open_dir(directory_fd, name)
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                _safe_relative(relative)
                if info.st_nlink != 1:
                    raise TransactionError(f"Hard link sospetto vietato: {relative}.")
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    opened = os.fstat(fd)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise TransactionError(f"File sostituito durante inventario: {relative}.")
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        block = os.read(fd, 1024 * 1024)
                        if not block:
                            break
                        digest.update(block)
                        size += len(block)
                    records[relative] = {"path": relative, "sha256": digest.hexdigest(),
                                         "size": size, "mode": format(stat.S_IMODE(opened.st_mode), "o")}
                finally:
                    os.close(fd)
            else:
                raise TransactionError(f"File speciale o hard link vietato: {relative}.")

    visit(root_fd)
    return records


def _tree_inventory(path, reject_node_modules=False):
    root_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return _inventory(path, root_fd, reject_node_modules=reject_node_modules)
    finally:
        os.close(root_fd)


def _copy_tree(src, dst):
    records = _tree_inventory(src)
    src_fd = os.open(src, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    dst_fd = os.open(dst, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for relative, record in sorted(records.items()):
            data, mode = _read_at(src_fd, relative, limit=max(record["size"], 1))
            if _sha(data) != record["sha256"] or len(data) != record["size"]:
                raise TransactionError(f"Artefatto cambiato durante la copia: {relative}.")
            _write_new_at(dst_fd, relative, data, int(mode, 8), create_dirs=True)
    finally:
        os.close(src_fd)
        os.close(dst_fd)
    return records


def _read_json_file(path):
    try:
        raw = _read_file_bytes(path, MAX_JSON)
        return json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise TransactionError(f"JSON malformato: {path.name}.") from exc


def _read_file_bytes(path, limit):
    path = pathlib.Path(path)
    try:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
                    raise TransactionError(f"File non regolare o troppo grande: {path.name}.")
                chunks = []
                total = 0
                while True:
                    block = os.read(fd, min(1024 * 1024, limit + 1 - total))
                    if not block:
                        break
                    chunks.append(block)
                    total += len(block)
                    if total > limit:
                        raise TransactionError(f"File troppo grande: {path.name}.")
                return b"".join(chunks)
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise TransactionError(f"File assente o non apribile senza symlink: {path.name}.") from exc


def _write_private_file(directory, name, data, mode=0o600):
    dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode, dir_fd=dir_fd)
        if os.write(fd, data) != len(data):
            raise TransactionError(f"Scrittura privata incompleta: {name}.")
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.fsync(dir_fd)
    except OSError as exc:
        raise TransactionError(f"Scrittura privata non sicura: {name}.") from exc
    finally:
        if fd is not None:
            os.close(fd)
        os.close(dir_fd)


def _current_state(workspace):
    baseline_path = workspace.state_dir / "baseline.json"
    state_path = workspace.state_dir / release_state.STATE_NAME
    baseline_raw = _read_file_bytes(baseline_path, MAX_JSON)
    try:
        baseline_doc = json.loads(baseline_raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TransactionError("Baseline fixture malformata.") from exc
    baseline_sha = _sha(baseline_raw)
    state = _read_json_file(state_path)
    try:
        release_state.validate_state_document(state, baseline_sha)
    except release_state.ReleaseStateError as exc:
        raise TransactionError(f"Stato corrente non valido: {exc}") from exc
    if state["initial_baseline"]["sha256"] != baseline_sha:
        raise TransactionError("Baseline fixture diversa dallo stato corrente.")
    baseline_rows = {}
    for group, classification in (("managed_files", "artifact"), ("accepted_extras", None)):
        rows = baseline_doc.get(group)
        if not isinstance(rows, list):
            raise TransactionError("Baseline fixture malformata.")
        for row in rows:
            if not isinstance(row, dict) or not baseline.safe_path(row.get("path")):
                raise TransactionError("Percorso baseline fixture non valido.")
            normalized = {**row, "classification": row.get("classification", classification)}
            if row["path"] in baseline_rows:
                raise TransactionError("Percorso duplicato nella baseline fixture.")
            baseline_rows[row["path"]] = normalized
    if (baseline_doc.get("release", {}).get("commit_sha") != state["initial_baseline"]["commit_sha"]
            or baseline_doc.get("release", {}).get("release_id") != state["initial_baseline"]["release_id"]
            or baseline_rows != {row["path"]: row for row in state["reference_files"]}):
        raise TransactionError("Baseline fixture non concorda con lo stato corrente registrato.")
    return baseline_doc, baseline_sha, state


def _manifest_files(manifest, dist_root):
    if not isinstance(manifest, dict):
        raise TransactionError("Manifest Vite non valido.")
    for entrypoint in ENTRYPOINTS:
        row = manifest.get(entrypoint)
        if not isinstance(row, dict) or row.get("isEntry") is not True or not isinstance(row.get("file"), str):
            raise TransactionError(f"Entry Vite mancante o incompleto: {entrypoint}.")
    referenced = set()
    for name, row in manifest.items():
        if not isinstance(row, dict):
            raise TransactionError(f"Voce manifest Vite non valida: {name}.")
        for relative in [row.get("file"), *(row.get("css") or []), *(row.get("assets") or [])]:
            if relative is None:
                continue
            if (not isinstance(relative, str) or relative.startswith("/") or "\\" in relative
                    or any(part in ("", ".", "..") for part in relative.split("/"))):
                raise TransactionError(f"Percorso asset Vite non sicuro: {relative!r}.")
            target = dist_root.joinpath(*relative.split("/"))
            try:
                target.relative_to(dist_root)
                info = target.lstat()
            except (ValueError, OSError) as exc:
                raise TransactionError(f"Asset Vite mancante/fuori build: {relative}.") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise TransactionError(f"Asset Vite non regolare: {relative}.")
            referenced.add("themes/sarafatto/assets/dist/" + relative)
        for imported in [*(row.get("imports") or []), *(row.get("dynamicImports") or [])]:
            if imported not in manifest:
                raise TransactionError(f"Import Vite inesistente: {name} -> {imported}.")
    return referenced


def _verify_vite_manifest(artifact_root):
    dist = artifact_root / "themes" / "sarafatto" / "assets" / "dist"
    manifest_path = dist / ".vite" / "manifest.json"
    manifest = _read_json_file(manifest_path)
    return _manifest_files(manifest, dist)


def _parse_artifact_inventory(path, workspace):
    path = pathlib.Path(path)
    try:
        info = path.lstat()
        if path.parent != workspace.root or path.parent.is_symlink():
            raise TransactionError("Inventario artefatto deve risiedere direttamente nella fixture.")
    except (OSError, ValueError) as exc:
        raise TransactionError("Inventario artefatto fuori dall'area temporanea o assente.") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise TransactionError("Inventario artefatto non regolare o hard link inatteso.")
    try:
        records = baseline.parse_artifact(path)
    except (baseline.BaselineError, OSError) as exc:
        raise TransactionError(f"Inventario artefatto non valido: {exc}") from exc
    return records


def _to_records(inventory):
    return [inventory[key] for key in sorted(inventory)]


def _records_digest(inventory):
    return _json_digest(_to_records(inventory))


def _load_fixture_journal(workspace):
    state_fd = os.open(workspace.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return release_state.read_journal_at(state_fd, allow_fixture_committed=True)
    except release_state.ReleaseStateError as exc:
        raise TransactionError(f"Journal fixture non valido: {exc}") from exc
    finally:
        os.close(state_fd)


def preflight(workspace, *, artifact_inventory_path, artifact_commit_sha,
              authorized_commit_sha, quota_free_bytes):
    """Genera solo un piano JSON; non scrive l'albero simulato."""
    root = _validate_workspace(workspace)
    if (not re.fullmatch(r"[a-f0-9]{40}", str(artifact_commit_sha or ""))
            or artifact_commit_sha != authorized_commit_sha):
        raise TransactionError("Commit candidato diverso dallo SHA autorizzato.")
    if not isinstance(quota_free_bytes, int) or isinstance(quota_free_bytes, bool) or quota_free_bytes < 0:
        raise TransactionError("Quota fixture non valida.")
    baseline_doc, baseline_sha, state = _current_state(workspace)
    events = _load_fixture_journal(workspace)
    try:
        release_state.unresolved_operation(events, allow_fixture_committed=True)
    except release_state.ReleaseStateError as exc:
        raise TransactionError(f"Operazione incompleta: {exc}") from exc
    if not state.get("verification", {}).get("status") == "verified-current":
        raise TransactionError("Stato corrente non verificato.")

    artifact_inventory = _parse_artifact_inventory(artifact_inventory_path, workspace)
    actual_artifact = _tree_inventory(workspace.artifact_root, reject_node_modules=True)
    if (set(actual_artifact) != set(artifact_inventory)
            or any(actual_artifact[path]["sha256"] != artifact_inventory[path]["sha256"]
                   or actual_artifact[path]["size"] != artifact_inventory[path]["size"]
                   for path in artifact_inventory)):
        raise TransactionError("Artefatto diverso dall'inventario autorizzato.")
    _verify_vite_manifest(workspace.artifact_root)
    current_inventory = _tree_inventory(workspace.public_root)
    expected_current = {row["path"]: row for row in state["reference_files"]}
    if set(current_inventory) != set(expected_current) or any(
            any(current_inventory[path][key] != expected_current[path][key]
                for key in ("sha256", "size", "mode")) for path in expected_current):
        raise TransactionError("Filesystem simulato diverso dallo stato corrente registrato.")

    candidate = {path: {"path": path, "sha256": row["sha256"], "size": row["size"],
                        "mode": actual_artifact[path]["mode"], "classification": "artifact"}
                 for path, row in artifact_inventory.items()}
    existing = {path: dict(row) for path, row in expected_current.items()}
    extras = {path: row for path, row in existing.items() if row.get("classification") != "artifact"}
    collisions = sorted(set(candidate) & set(extras))
    if collisions:
        raise TransactionError("Collisione con extra approvato: " + ", ".join(collisions[:10]))
    additions, replacements, retained = [], [], []
    for path, row in sorted(candidate.items()):
        prior = existing.get(path)
        if prior is None:
            additions.append(row)
        elif all(prior.get(key) == row.get(key) for key in ("sha256", "size", "mode")):
            retained.append(row)
        else:
            replacements.append({"path": path, "before": prior, "after": row})
    removals = [row for path, row in sorted(existing.items())
                if row.get("classification") == "artifact" and path not in candidate]
    approved_extras = [row for _, row in sorted(extras.items())]
    old_bytes = sum(row["size"] for row in existing.values())
    new_bytes = sum(row["size"] for row in candidate.values())
    required_bytes = old_bytes + new_bytes + max(16 * 1024 * 1024, int((old_bytes + new_bytes) * 0.05))
    disk_free = shutil.disk_usage(root).free
    available = min(quota_free_bytes, disk_free)
    if available < required_bytes:
        raise TransactionError(f"Quota/spazio insufficiente: disponibili {available}, richiesti {required_bytes} byte.")
    plan = {
        "schema_version": 1,
        "mode": "fixture-only",
        "current_release": {"commit_sha": state["release"]["commit_sha"],
                            "release_id": state["release"]["release_id"],
                            "inventory_sha256": state["inventory_sha256"],
                            "state_sha256": state["state_sha256"]},
        "candidate_release": {"commit_sha": artifact_commit_sha,
                              "artifact_sha256": _records_digest(actual_artifact)},
        "baseline_sha256": baseline_sha,
        "artifact_files": _to_records(actual_artifact),
        "files_to_add": additions,
        "files_to_replace": replacements,
        "files_to_keep": retained,
        "files_candidate_for_removal": removals,
        "approved_extras": approved_extras,
        "removal_approvals": {},
        "removal_approval_proof": None,
        "backup": {"required": True, "verified_before_publish": True},
        "space": {"old_bytes": old_bytes, "candidate_bytes": new_bytes,
                  "required_bytes": required_bytes, "quota_free_bytes": quota_free_bytes,
                  "fixture_disk_free_bytes": disk_free, "available_bytes": available},
        "required_checks": ["lock-exclusive", "state-current", "artifact-sha256", "vite-manifest",
                            "backup-verified", "fresh-fixture-inventory", "post-write-sha256",
                            "health-check-explicit"],
        "production_writes_allowed": False,
    }
    plan["plan_sha256"] = _json_digest(plan)
    return plan


def approve_fixture_removals(plan, paths, *, confirmation):
    """Approva separatamente solo le rimozioni elencate e vincolate ai loro SHA attesi."""
    _validate_plan(plan)
    if confirmation != "APPROVE-FIXTURE-REMOVALS " + plan["plan_sha256"]:
        raise TransactionError("Conferma separata delle rimozioni non valida.")
    requested = set(paths)
    candidates = {row["path"]: row for row in plan["files_candidate_for_removal"]}
    if not requested or not requested.issubset(candidates):
        raise TransactionError("Rimozione non candidata o approvazione vuota.")
    approved = dict(plan)
    approvals = {path: candidates[path]["sha256"] for path in sorted(requested)}
    approved["removal_approvals"] = approvals
    proof_body = {"plan_sha256": plan["plan_sha256"], "approvals": approvals}
    proof_digest = _json_digest(proof_body)
    approved["removal_approval_proof"] = {
        "base_plan_sha256": plan["plan_sha256"],
        "hmac_sha256": hmac.new(
            _REMOVAL_APPROVAL_KEY, proof_digest.encode("ascii"), hashlib.sha256
        ).hexdigest(),
    }
    approved.pop("plan_sha256", None)
    approved["plan_sha256"] = _json_digest(approved)
    return approved


def _validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("mode") != "fixture-only" or plan.get("production_writes_allowed") is not False:
        raise TransactionError("Piano non fixture-only.")
    digest = plan.get("plan_sha256")
    unsigned = dict(plan)
    unsigned.pop("plan_sha256", None)
    if not re.fullmatch(r"[a-f0-9]{64}", str(digest or "")) or _json_digest(unsigned) != digest:
        raise TransactionError("Digest del piano non valido.")
    approvals = plan.get("removal_approvals")
    removals = plan.get("files_candidate_for_removal")
    if not isinstance(removals, list) or not isinstance(approvals, dict):
        raise TransactionError("Approvazioni rimozione del piano non valide.")
    candidates = {}
    for row in removals:
        if not isinstance(row, dict):
            raise TransactionError("Rimozione candidata malformata.")
        path, sha_value = row.get("path"), row.get("sha256")
        if (not isinstance(path, str) or not baseline.safe_path(path) or baseline.excluded(path)
                or not re.fullmatch(r"[a-f0-9]{64}", str(sha_value or ""))
                or path in candidates):
            raise TransactionError("Rimozione candidata fuori allowlist, duplicata o malformata.")
        candidates[path] = sha_value
    if any(path not in candidates or digest_value != candidates[path]
           for path, digest_value in approvals.items()):
        raise TransactionError("Approvazioni rimozione non corrispondenti ai file candidati.")

    proof = plan.get("removal_approval_proof")
    if not approvals:
        if proof is not None:
            raise TransactionError("Prova di approvazione presente senza rimozioni autorizzate.")
        return
    if (not isinstance(proof, dict) or set(proof) != {"base_plan_sha256", "hmac_sha256"}
            or not re.fullmatch(r"[a-f0-9]{64}", str(proof.get("base_plan_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(proof.get("hmac_sha256", "")))):
        raise TransactionError("Prova di approvazione rimozioni assente o malformata.")
    # Ricostruisce il digest del piano originale rimuovendo esclusivamente i
    # campi aggiunti dal passaggio esplicito di approvazione.
    original = dict(plan)
    original.pop("plan_sha256", None)
    original["removal_approvals"] = {}
    original["removal_approval_proof"] = None
    original_sha = _json_digest(original)
    proof_body = {"plan_sha256": original_sha, "approvals": approvals}
    expected_proof = hmac.new(
        _REMOVAL_APPROVAL_KEY, _json_digest(proof_body).encode("ascii"), hashlib.sha256
    ).hexdigest()
    if (proof.get("base_plan_sha256") != original_sha
            or not hmac.compare_digest(proof.get("hmac_sha256", ""), expected_proof)):
        raise TransactionError("Approvazione non legata al piano originale o alterata.")


def _write_journal_event(workspace, operation_id, status, details, *, verified_commit=False,
                         lock_already_held=False):
    state_fd = os.open(workspace.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    locks_fd = os.open(workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = None
    try:
        lock_fd = None if lock_already_held else baseline.acquire_baseline_lock(None, locks_fd)
        events = release_state.read_journal_at(state_fd, allow_fixture_committed=True)
        previous = events[-1]["event_sha256"] if events else "0" * 64
        if events and events[-1]["status"] not in ("committed",):
            if events[-1]["operation_id"] != operation_id and not (
                    events[-1]["status"] == "recovery_required" and status == "prepared"
                    and details.get("rollback_of") == events[-1]["operation_id"]):
                raise TransactionError("Transazione precedente irrisolta.")
        if status == "committed" and (not verified_commit or details.get("fixture_only") is not True):
            raise TransactionError("Solo il controllo finale della fixture può registrare committed.")
        event = {"operation_id": operation_id, "status": status,
                 "timestamp_utc": release_state.utc_now(), "details": details,
                 "previous_event_sha256": previous}
        event["event_sha256"] = _json_digest(event)
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        try:
            fd = os.open(release_state.JOURNAL_NAME,
                         os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                         0o600, dir_fd=state_fd)
        except OSError as exc:
            raise TransactionError("Journal fixture non scrivibile in sicurezza.") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
                raise TransactionError("Journal fixture non regolare o hard link inatteso.")
            if os.write(fd, payload) != len(payload):
                raise TransactionError("Scrittura journal fixture incompleta.")
            os.fsync(fd)
            os.fsync(state_fd)
        finally:
            os.close(fd)
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        os.close(locks_fd)
        os.close(state_fd)


def _commit_verified_fixture(workspace, operation_id, plan_sha256, expected_records,
                             backup_sha256, rollback_of=None):
    """Verificatore interno: confronta il filesystem fixture prima di scrivere committed."""
    _validate_workspace(workspace)
    actual = _current_records(workspace)
    _check_records(actual, expected_records)
    events = _load_fixture_journal(workspace)
    transaction = [event for event in events if event["operation_id"] == operation_id]
    if not transaction or transaction[-1]["status"] != "health_verified":
        raise TransactionError("Commit fixture senza verifica file e health precedente.")
    prepared = next((event for event in transaction if event["status"] == "prepared"), None)
    if not prepared or prepared["details"].get("plan_sha256") != plan_sha256:
        raise TransactionError("Commit fixture non corrisponde al piano preparato.")
    if rollback_of is None:
        verified_backup = next((event for event in transaction if event["status"] == "backup_verified"), None)
        if not verified_backup or verified_backup["details"].get("backup_sha256") != backup_sha256:
            raise TransactionError("Commit fixture senza backup verificato corrispondente.")
    else:
        if (prepared["details"].get("rollback_of") != rollback_of
                or prepared["details"].get("backup_sha256") != backup_sha256):
            raise TransactionError("Commit rollback fixture non legato alla transazione/backup autorizzati.")
        backup_event = next((event for event in transaction if event["status"] == "backup_verified"), None)
        if not backup_event or backup_event["details"].get("target_backup_sha256") != backup_sha256:
            raise TransactionError("Rollback fixture privo di verifica del backup di destinazione.")
    final_digest = _records_digest(actual)
    details = {"fixture_only": True, "plan_sha256": plan_sha256,
               "final_inventory_sha256": final_digest, "backup_sha256": backup_sha256}
    if rollback_of is not None:
        details["rollback_of"] = rollback_of
    _write_journal_event(workspace, operation_id, "committed", details,
                         verified_commit=True, lock_already_held=True)
    return final_digest


def _load_verified_backup(workspace, backup_id, expected_digest=None):
    if (not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(backup_id or ""))
            or backup_id in (".", "..") or backup_id.startswith(".")):
        raise TransactionError("ID backup fixture non valido.")
    path = workspace.backups_dir / backup_id / "backup.json"
    doc = _read_json_file(path)
    recorded = doc.pop("backup_sha256", None)
    digest = _json_digest(doc)
    if recorded != digest or expected_digest is not None and recorded != expected_digest:
        raise TransactionError("Digest backup fixture non valido.")
    if (doc.get("fixture_only") is not True or doc.get("schema_version") != 1
            or doc.get("backup_id") != backup_id
            or not re.fullmatch(r"[a-f0-9]{64}", str(doc.get("baseline_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(doc.get("current_state_sha256", "")))):
        raise TransactionError("Backup non riconosciuto come fixture.")
    _, baseline_sha, current_state = _current_state(workspace)
    if (doc["baseline_sha256"] != baseline_sha
            or doc["current_state_sha256"] != current_state["state_sha256"]):
        raise TransactionError("Backup fixture riferito a baseline/stato differenti.")
    records, data = {}, {}
    for row in doc.get("files", []):
        if (not isinstance(row, dict) or not re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", "")))
                or not isinstance(row.get("size"), int) or isinstance(row.get("size"), bool)
                or row["size"] < 0 or not re.fullmatch(r"[0-7]{3,5}", str(row.get("mode", "")))
                or not isinstance(row.get("classification"), str)):
            raise TransactionError("Record backup fixture malformato.")
        path = _safe_relative(row.get("path"))
        raw = base64.b64decode(row.get("content_b64", ""), validate=True)
        if len(raw) != row.get("size") or _sha(raw) != row.get("sha256") or path in records:
            raise TransactionError(f"Backup fixture corrotto: {path}.")
        records[path] = {key: row[key] for key in ("path", "sha256", "size", "mode", "classification")}
        data[path] = raw
    if not records:
        raise TransactionError("Backup fixture vuoto.")
    return records, data, recorded


def create_verified_backup(workspace, backup_id):
    """Crea uno snapshot privato della fixture, mai della webroot reale."""
    _validate_workspace(workspace)
    current = _tree_inventory(workspace.public_root)
    _, baseline_sha, state = _current_state(workspace)
    expected = {row["path"]: row for row in state["reference_files"]}
    if set(current) != set(expected) or any(
            any(current[path][key] != expected[path][key] for key in ("sha256", "size", "mode"))
            for path in expected):
        raise TransactionError("Backup fixture bloccato: filesystem diverso dallo stato registrato.")
    if (not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", str(backup_id or ""))
            or backup_id in (".", "..") or backup_id.startswith(".")):
        raise TransactionError("ID backup fixture non valido.")
    target = workspace.backups_dir / backup_id
    if target.exists() or target.is_symlink():
        raise TransactionError("Backup fixture esistente: no-overwrite.")
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    rows = []
    root_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path in sorted(expected):
            raw, mode = _read_at(root_fd, path, limit=max(expected[path]["size"], 1))
            if _sha(raw) != expected[path]["sha256"] or mode != expected[path]["mode"]:
                raise TransactionError(f"File cambiato durante backup fixture: {path}.")
            rows.append({**expected[path], "content_b64": base64.b64encode(raw).decode("ascii")})
    finally:
        os.close(root_fd)
    document = {"schema_version": 1, "fixture_only": True, "backup_id": backup_id,
                "baseline_sha256": baseline_sha, "current_state_sha256": state["state_sha256"],
                "files": rows}
    document["backup_sha256"] = _json_digest(document)
    _write_private_file(target, "backup.json", release_state.json_bytes(document))
    return {"backup_id": backup_id, "backup_sha256": document["backup_sha256"],
            "files": len(rows), "status": "verified-fixture"}


def _current_records(workspace):
    root_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        raw = _inventory(workspace.public_root, root_fd)
    finally:
        os.close(root_fd)
    _, _, state = _current_state(workspace)
    classifications = {row["path"]: row.get("classification", "artifact")
                       for row in state["reference_files"]}
    return {path: {**row, "classification": classifications.get(path, "artifact")}
            for path, row in raw.items()}


def _expected_after_plan(plan):
    candidate = {row["path"]: row for row in plan["artifact_files"]}
    extras = {row["path"]: row for row in plan["approved_extras"]}
    return {**candidate, **extras}


def _check_records(actual, expected):
    if set(actual) != set(expected):
        raise TransactionError("Inventario finale diverso: percorsi mancanti o inattesi.")
    for path in expected:
        if any(actual[path].get(key) != expected[path].get(key) for key in ("sha256", "size", "mode")):
            raise TransactionError(f"Hash, dimensione o permessi finali non corrispondenti: {path}.")


def _verify_artifact_again(workspace, plan):
    actual = _tree_inventory(workspace.artifact_root, reject_node_modules=True)
    if _records_digest(actual) != plan["candidate_release"]["artifact_sha256"]:
        raise TransactionError("Artefatto alterato dopo il preflight.")
    _verify_vite_manifest(workspace.artifact_root)
    return actual


def _verify_plan_actions(workspace, plan, actual_artifact, current):
    """Ricalcola le operazioni dal vivo: il digest del piano da solo non è autorizzazione."""
    _, baseline_sha, state = _current_state(workspace)
    if (plan.get("baseline_sha256") != baseline_sha
            or plan.get("current_release", {}).get("state_sha256") != state["state_sha256"]
            or plan.get("current_release", {}).get("inventory_sha256") != state["inventory_sha256"]
            or plan.get("artifact_files") != _to_records(actual_artifact)
            or plan.get("candidate_release", {}).get("artifact_sha256") != _records_digest(actual_artifact)):
        raise TransactionError("Piano non corrispondente a baseline, stato o artefatto fixture.")
    candidate = {path: {**row, "classification": "artifact"} for path, row in actual_artifact.items()}
    existing = {path: dict(row) for path, row in current.items()}
    extras = {path: row for path, row in existing.items() if row.get("classification") != "artifact"}
    if set(candidate) & set(extras):
        raise TransactionError("Artefatto collide con un extra approvato.")
    additions, replacements, retained = [], [], []
    for path, row in sorted(candidate.items()):
        prior = existing.get(path)
        if prior is None:
            additions.append(row)
        elif all(prior.get(key) == row.get(key) for key in ("sha256", "size", "mode")):
            retained.append(row)
        else:
            replacements.append({"path": path, "before": prior, "after": row})
    removals = [row for path, row in sorted(existing.items())
                if row.get("classification") == "artifact" and path not in candidate]
    if (plan.get("files_to_add") != additions or plan.get("files_to_replace") != replacements
            or plan.get("files_to_keep") != retained or plan.get("files_candidate_for_removal") != removals
            or plan.get("approved_extras") != [row for _, row in sorted(extras.items())]):
        raise TransactionError("Azioni del piano non corrispondono al confronto ricalcolato.")
    approvals = plan.get("removal_approvals")
    if not isinstance(approvals, dict) or any(
            path not in {row["path"]: row["sha256"] for row in removals}
            or {row["path"]: row["sha256"] for row in removals}[path] != sha_value
            for path, sha_value in approvals.items()):
        raise TransactionError("Approvazioni di rimozione alterate o non valide.")
    old_bytes = sum(row["size"] for row in current.values())
    candidate_bytes = sum(row["size"] for row in candidate.values())
    required = old_bytes + candidate_bytes + max(16 * 1024 * 1024, int((old_bytes + candidate_bytes) * .05))
    quota = plan.get("space", {}).get("quota_free_bytes")
    if (not isinstance(quota, int) or isinstance(quota, bool) or quota < required
            or shutil.disk_usage(workspace.root).free < required):
        raise TransactionError("Quota/spazio non più sufficiente al momento della transazione.")


def _copy_artifact_to_staging(workspace, operation_id, artifact_records):
    stage = workspace.staging_dir / operation_id
    if stage.exists() or stage.is_symlink():
        raise TransactionError("Staging fixture già esistente.")
    stage.mkdir(mode=0o700)
    stage.chmod(0o700)
    src_fd = os.open(workspace.artifact_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    dst_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path, row in sorted(artifact_records.items()):
            data, mode = _read_at(src_fd, path, max(row["size"], 1))
            if _sha(data) != row["sha256"] or len(data) != row["size"]:
                raise TransactionError(f"Artefatto alterato durante staging: {path}.")
            _write_new_at(dst_fd, path, data, int(mode, 8), create_dirs=True)
    finally:
        os.close(src_fd)
        os.close(dst_fd)
    return stage


def _apply_plan(workspace, plan, artifact_records, stage_root, fault_after_writes=None):
    public_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    artifact_fd = os.open(stage_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    writes = 0
    try:
        changes = [(row["path"], None, row) for row in plan["files_to_add"]]
        changes.extend((row["path"], row["before"]["sha256"], row["after"])
                       for row in plan["files_to_replace"])
        for relative, expected_before, after in changes:
            data, mode = _read_at(artifact_fd, relative, max(after["size"], 1))
            if _sha(data) != after["sha256"] or len(data) != after["size"]:
                raise TransactionError(f"File artefatto cambiato prima della scrittura: {relative}.")
            before_record = next((row["before"] for row in plan["files_to_replace"]
                                  if row["path"] == relative), None)
            _replace_at(public_fd, relative, data, int(after["mode"], 8), before_record)
            writes += 1
            if fault_after_writes is not None and writes == fault_after_writes:
                raise TransactionError(f"Interruzione fault-injection dopo scrittura {writes}.")
        approvals = plan["removal_approvals"]
        for row in plan["files_candidate_for_removal"]:
            if row["path"] not in approvals:
                continue
            if approvals[row["path"]] != row["sha256"]:
                raise TransactionError(f"Approvazione/hash rimozione incoerenti: {row['path']}.")
            _unlink_verified(public_fd, row["path"], row)
            writes += 1
            if fault_after_writes is not None and writes == fault_after_writes:
                raise TransactionError(f"Interruzione fault-injection dopo scrittura {writes}.")
    finally:
        os.close(artifact_fd)
        os.close(public_fd)
    actual = _current_records(workspace)
    _check_records(actual, _expected_after_plan(plan))
    return actual


def simulate_publish(workspace, plan, *, authorized_commit_sha, backup_id, backup_sha256,
                     confirmation, health_check, fault_after_writes=None):
    """Esegue la transazione solo sull'albero public/ interno alla fixture."""
    _validate_workspace(workspace)
    _validate_plan(plan)
    if (not re.fullmatch(r"[a-f0-9]{40}", str(authorized_commit_sha or ""))
            or plan.get("candidate_release", {}).get("commit_sha") != authorized_commit_sha):
        raise TransactionError("Commit candidato del piano non coincide con lo SHA autorizzato.")
    unapproved_removals = {row["path"] for row in plan["files_candidate_for_removal"]} - set(plan["removal_approvals"])
    if unapproved_removals:
        raise TransactionError("Piano contiene rimozioni senza approvazione separata.")
    operation_id = "fixture-" + uuid.uuid4().hex
    if confirmation != "PUBLISH-FIXTURE " + plan["plan_sha256"]:
        raise TransactionError("Conferma fixture non valida.")
    if fcntl is None:
        raise TransactionError("flock non disponibile.")
    locks_fd = os.open(workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
    started = False
    try:
        events = _load_fixture_journal(workspace)
        try:
            release_state.unresolved_operation(events, allow_fixture_committed=True)
        except release_state.ReleaseStateError as exc:
            raise TransactionError(f"Transazione precedente irrisolta: {exc}") from exc
        _, _, state = _current_state(workspace)
        if state["state_sha256"] != plan["current_release"]["state_sha256"]:
            raise TransactionError("Stato corrente diverso da quello del piano.")
        artifact_records = _verify_artifact_again(workspace, plan)
        current_records = _current_records(workspace)
        _verify_plan_actions(workspace, plan, artifact_records, current_records)
        backup_records, _, actual_backup_sha = _load_verified_backup(workspace, backup_id, backup_sha256)
        if actual_backup_sha != backup_sha256:
            raise TransactionError("Digest backup effettivo diverso da quello approvato.")
        _check_records(current_records, backup_records)
        _write_journal_event(workspace, operation_id, "prepared", {"fixture_only": True,
                             "plan_sha256": plan["plan_sha256"]}, lock_already_held=True)
        started = True
        _write_journal_event(workspace, operation_id, "backup_verified", {"fixture_only": True,
                             "backup_id": backup_id, "backup_sha256": actual_backup_sha}, lock_already_held=True)
        stage = _copy_artifact_to_staging(workspace, operation_id, artifact_records)
        _write_journal_event(workspace, operation_id, "publishing", {"fixture_only": True}, lock_already_held=True)
        # L'inventario viene ricontrollato immediatamente prima delle sostituzioni.
        current = _current_records(workspace)
        baseline_files = {row["path"]: row for row in state["reference_files"]}
        if set(current) != set(baseline_files) or any(
                any(current[path][key] != baseline_files[path][key] for key in ("sha256", "size", "mode"))
                for path in baseline_files):
            raise TransactionError("File fixture modificato da un processo concorrente.")
        if fault_after_writes == 0:
            raise TransactionError("Interruzione fault-injection prima della prima scrittura.")
        actual = _apply_plan(workspace, plan, artifact_records, stage, fault_after_writes)
        final_digest = _records_digest(actual)
        _write_journal_event(workspace, operation_id, "files_verified", {"fixture_only": True,
                             "final_inventory_sha256": final_digest}, lock_already_held=True)
        if health_check == "unavailable":
            _write_journal_event(workspace, operation_id, "recovery_required", {
                "fixture_only": True, "reason": "health-check-unavailable",
                "plan_sha256": plan["plan_sha256"],
                "final_inventory_sha256": final_digest}, lock_already_held=True)
            return {"operation_id": operation_id, "integrity": "verified",
                    "health": "unavailable", "status": "health-check-unavailable"}
        if health_check != "passed":
            _write_journal_event(workspace, operation_id, "recovery_required", {
                "fixture_only": True, "reason": "health-check-failed",
                "plan_sha256": plan["plan_sha256"],
                "final_inventory_sha256": final_digest}, lock_already_held=True)
            return {"operation_id": operation_id, "integrity": "verified",
                    "health": "failed", "status": "health-check-failed"}
        _write_journal_event(workspace, operation_id, "health_verified", {"fixture_only": True,
                             "health": "fixture-callback-passed"}, lock_already_held=True)
        if fault_after_writes == -1:
            raise TransactionError("Interruzione fault-injection prima del commit.")
        final_digest = _commit_verified_fixture(workspace, operation_id, plan["plan_sha256"],
                                                _expected_after_plan(plan), actual_backup_sha)
        return {"operation_id": operation_id, "integrity": "verified", "health": "verified",
                "status": "committed-fixture", "final_inventory_sha256": final_digest}
    except Exception as exc:
        if started:
            try:
                events = _load_fixture_journal(workspace)
                if events and events[-1]["status"] not in ("committed", "recovery_required"):
                    _write_journal_event(workspace, operation_id, "recovery_required",
                                         {"fixture_only": True, "error": type(exc).__name__,
                                          "plan_sha256": plan["plan_sha256"]},
                                         lock_already_held=True)
            except Exception:
                pass
        if isinstance(exc, TransactionError):
            raise
        raise TransactionError(f"Transazione fixture fallita: {exc}") from exc
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(locks_fd)


def simulate_rollback(workspace, *, transaction_id, backup_id, backup_sha256,
                      confirmation, health_check, plan=None, fault_after_writes=None):
    """Ripristina la sola fixture dopo aver verificato backup, journal e hash attuali."""
    _validate_workspace(workspace)
    if confirmation != f"ROLLBACK-FIXTURE {transaction_id} {backup_sha256}":
        raise TransactionError("Autorizzazione rollback fixture non valida.")
    if not re.fullmatch(r"fixture-[a-f0-9]{32}", transaction_id or ""):
        raise TransactionError("ID transazione fixture non valido.")
    locks_fd = os.open(workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
    rollback_started = False
    try:
        events = _load_fixture_journal(workspace)
        transaction_events = [event for event in events if event["operation_id"] == transaction_id]
        committed = [event for event in transaction_events if event["status"] == "committed"]
        recovery = [event for event in transaction_events if event["status"] == "recovery_required"]
        if not committed and not recovery:
            raise TransactionError("Transazione fixture non risulta committed o in recovery_required.")
        backup_records, backup_data, verified_digest = _load_verified_backup(workspace, backup_id, backup_sha256)
        original_backup = next((event for event in transaction_events
                                if event["status"] == "backup_verified"), None)
        if committed:
            if committed[-1]["details"].get("backup_sha256") != verified_digest:
                raise TransactionError("Il backup richiesto non è quello associato alla transazione.")
        elif (original_backup is None
              or original_backup["details"].get("backup_id") != backup_id
              or original_backup["details"].get("backup_sha256") != verified_digest):
            raise TransactionError("Il backup richiesto non è quello verificato dalla transazione interrotta.")
        # La fotografia attuale deve essere completa e priva di contenuti inattesi.
        current = _current_records(workspace)
        if committed:
            detail = committed[-1]["details"]
            if _records_digest(current) != detail.get("final_inventory_sha256"):
                raise TransactionError("Stato simulato modificato dopo la transazione; rollback bloccato.")
        else:
            _validate_plan(plan)
            if plan["plan_sha256"] != recovery[-1]["details"].get("plan_sha256"):
                raise TransactionError("Piano non corrispondente alla transazione interrotta.")
            candidate = {row["path"]: row for row in plan["artifact_files"]}
            allowed_paths = set(backup_records) | set(candidate)
            if not set(current).issubset(allowed_paths):
                raise TransactionError("Stato fixture interrotto contiene file o hash inattesi.")
            for path in set(backup_records) | set(candidate):
                was_extra = backup_records.get(path, {}).get("classification") != "artifact"
                removal_approved = path in plan["removal_approvals"]
                existed_before = path in backup_records
                must_exist = existed_before and (was_extra or path in candidate or not removal_approved)
                if must_exist and path not in current:
                    raise TransactionError(f"File fixture inatteso mancante durante rollback: {path}.")
                if path in current:
                    allowed_records = (backup_records.get(path), candidate.get(path))
                    actual = current[path]
                    if not any(
                        row is not None
                        and all(actual.get(key) == row.get(key) for key in ("sha256", "size", "mode"))
                        for row in allowed_records
                    ):
                        raise TransactionError(
                            f"Contenuto, dimensione o permessi fixture inattesi durante rollback: {path}."
                        )
        rollback_id = "rollback-" + uuid.uuid4().hex
        _write_journal_event(workspace, rollback_id, "prepared", {"fixture_only": True,
                             "rollback_of": transaction_id, "backup_sha256": verified_digest,
                             "plan_sha256": "0" * 64},
                             lock_already_held=True)
        rollback_started = True
        # Copia cautelativa dello stato corrente in area privata prima del rollback.
        safety = {"schema_version": 1, "fixture_only": True, "backup_id": "pre-" + rollback_id,
                  "baseline_sha256": _current_state(workspace)[1],
                  "current_state_sha256": _current_state(workspace)[2]["state_sha256"],
                  "files": []}
        public_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for path, row in sorted(current.items()):
                raw, mode = _read_at(public_fd, path, max(row["size"], 1))
                safety["files"].append({**row, "content_b64": base64.b64encode(raw).decode("ascii")})
        finally:
            os.close(public_fd)
        safety["backup_sha256"] = _json_digest(safety)
        safety_dir = workspace.backups_dir / safety["backup_id"]
        safety_dir.mkdir(mode=0o700)
        _write_private_file(safety_dir, "backup.json", release_state.json_bytes(safety))
        verified_safety, _, safety_sha = _load_verified_backup(workspace, safety["backup_id"], safety["backup_sha256"])
        _check_records(current, verified_safety)
        _write_journal_event(workspace, rollback_id, "backup_verified", {"fixture_only": True,
                             "backup_id": safety["backup_id"], "backup_sha256": safety["backup_sha256"],
                             "target_backup_sha256": verified_digest},
                             lock_already_held=True)
        stage = workspace.staging_dir / rollback_id
        stage.mkdir(mode=0o700)
        stage.chmod(0o700)
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for path, raw in sorted(backup_data.items()):
                mode = int(backup_records[path]["mode"], 8)
                _write_new_at(stage_fd, path, raw, mode, create_dirs=True)
        finally:
            os.close(stage_fd)
        _write_journal_event(workspace, rollback_id, "publishing", {"fixture_only": True}, lock_already_held=True)
        public_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        writes = 0
        try:
            if fault_after_writes == 0:
                raise TransactionError("Interruzione fault-injection prima della prima scrittura rollback.")
            for path in sorted(set(current) | set(backup_records)):
                prior = current.get(path)
                wanted = backup_records.get(path)
                if wanted is None:
                    if prior:
                        _unlink_verified(public_fd, path, prior)
                        writes += 1
                else:
                    raw = backup_data[path]
                    if (prior and prior["sha256"] == wanted["sha256"]
                            and prior["size"] == wanted["size"] and prior["mode"] == wanted["mode"]):
                        continue
                    _replace_at(public_fd, path, raw, int(wanted["mode"], 8), prior)
                    writes += 1
                if fault_after_writes is not None and writes == fault_after_writes:
                    raise TransactionError(f"Interruzione fault-injection rollback dopo scrittura {writes}.")
        finally:
            os.close(public_fd)
        restored = _current_records(workspace)
        _check_records(restored, backup_records)
        final_digest = _records_digest(restored)
        _write_journal_event(workspace, rollback_id, "files_verified", {"fixture_only": True,
                             "final_inventory_sha256": final_digest}, lock_already_held=True)
        if health_check == "unavailable":
            _write_journal_event(workspace, rollback_id, "recovery_required", {
                "fixture_only": True, "reason": "health-check-unavailable",
                "plan_sha256": "0" * 64, "final_inventory_sha256": final_digest},
                lock_already_held=True)
            return {"operation_id": rollback_id, "integrity": "verified", "health": "unavailable",
                    "status": "health-check-unavailable"}
        if health_check != "passed":
            _write_journal_event(workspace, rollback_id, "recovery_required", {
                "fixture_only": True, "reason": "health-check-failed",
                "plan_sha256": "0" * 64, "final_inventory_sha256": final_digest},
                lock_already_held=True)
            return {"operation_id": rollback_id, "integrity": "verified", "health": "failed",
                    "status": "health-check-failed"}
        _write_journal_event(workspace, rollback_id, "health_verified", {"fixture_only": True,
                             "health": "fixture-callback-passed"}, lock_already_held=True)
        final_digest = _commit_verified_fixture(workspace, rollback_id, "0" * 64,
                                                backup_records, verified_digest,
                                                rollback_of=transaction_id)
        return {"operation_id": rollback_id, "integrity": "verified", "health": "verified",
                "status": "rollback-committed-fixture", "final_inventory_sha256": final_digest}
    except Exception as exc:
        if rollback_started:
            try:
                events = _load_fixture_journal(workspace)
                if events and events[-1]["status"] not in ("committed", "recovery_required"):
                    _write_journal_event(workspace, rollback_id, "recovery_required",
                                         {"fixture_only": True, "error": type(exc).__name__,
                                          "plan_sha256": "0" * 64},
                                         lock_already_held=True)
            except Exception:
                pass
        if isinstance(exc, TransactionError):
            raise
        raise TransactionError(f"Rollback fixture fallito: {exc}") from exc
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(locks_fd)


def fixture_health_check_unavailable():
    """Stato esplicito: non effettua richieste HTTP."""
    return "unavailable"
