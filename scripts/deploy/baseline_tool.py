#!/usr/bin/env python3
"""Confronto read-only e bootstrap esplicito della baseline."""

import argparse
import ctypes
import errno
import hashlib
import json
import os
import pathlib
import re
import subprocess
import stat
import sys
import tempfile
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # IONOS e runner Ubuntu usano POSIX.
    fcntl = None

PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
SINGLE_FILE = "mu-plugins/sarafatto-polylang-front-page-url.php"
EXCLUDED = "themes/sarafatto/node_modules"
MARKER = ".sarafatto-deploy-root"
MARKER_VALUE = "sarafatto-private-environment-v1"
INVENTORY_SCRIPT = pathlib.Path("/home/www/sarafatto-repo/scripts/deploy/baseline-inventory.sh")
REPOSITORY_ROOT = pathlib.Path("/home/www/sarafatto-repo")
INVENTORY_RELATIVE_PATH = "scripts/deploy/baseline-inventory.sh"


class BaselineError(Exception):
    pass


def managed(path):
    return (path == "themes/sarafatto" or path.startswith("themes/sarafatto/")
            or path == "plugins/sarafatto-core" or path.startswith("plugins/sarafatto-core/")
            or path == SINGLE_FILE)


def excluded(path):
    return path == EXCLUDED or path.startswith(EXCLUDED + "/")


def safe_path(path):
    return (bool(path) and not path.startswith("/") and "\\" not in path
            and not any(char in path for char in "\t\r\n")
            and all(part not in ("", ".", "..") for part in path.split("/"))
            and managed(path))


def parse_artifact(filename):
    files = {}
    for number, line in enumerate(pathlib.Path(filename).read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 3:
            raise BaselineError(f"Inventario artefatto malformato, riga {number}.")
        digest, size, path = fields
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or not size.isdigit() or not safe_path(path) or excluded(path):
            raise BaselineError(f"Record artefatto non valido: {path}.")
        if path in files:
            raise BaselineError(f"Percorso artefatto duplicato: {path}.")
        files[path] = {"sha256": digest, "size": int(size)}
    if not files:
        raise BaselineError("Inventario artefatto vuoto.")
    return files


def parse_remote(filename):
    files, symlinks, exclusion_record = {}, [], None
    ended = False
    for number, line in enumerate(pathlib.Path(filename).read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split("\t")
        if fields == ["END"]:
            if ended:
                raise BaselineError("Terminatore inventario remoto duplicato.")
            ended = True
        elif ended:
            raise BaselineError("Record remoto dopo il terminatore inventario.")
        elif len(fields) == 4 and fields[0] == "EXCLUDED":
            if exclusion_record is not None or fields[1] != EXCLUDED or not fields[2].isdigit() or not fields[3].isdigit():
                raise BaselineError("Record node_modules duplicato o non valido.")
            exclusion_record = {"path": EXCLUDED + "/", "files": int(fields[2]), "symlinks": int(fields[3])}
        elif len(fields) == 5 and fields[0] == "FILE":
            _, digest, size, mode, path = fields
            if (not re.fullmatch(r"[a-f0-9]{64}", digest) or not size.isdigit()
                    or not re.fullmatch(r"[0-7]{3,5}", mode) or not safe_path(path) or excluded(path)):
                raise BaselineError(f"Record FILE remoto non valido, riga {number}: {path}.")
            if path in files:
                raise BaselineError(f"Percorso remoto duplicato: {path}.")
            files[path] = {"sha256": digest, "size": int(size), "mode": mode}
        elif len(fields) == 3 and fields[0] == "SYMLINK":
            _, path, target = fields
            if not safe_path(path) or excluded(path) or any(char in target for char in "\t\r\n"):
                raise BaselineError(f"Symlink fuori perimetro o malformato: {path}.")
            symlinks.append({"path": path, "target": target})
        else:
            raise BaselineError(f"Record remoto sconosciuto, riga {number}.")
    if exclusion_record is None or not ended:
        raise BaselineError("Inventario remoto incompleto: esclusione o terminatore mancanti.")
    if len({row["path"] for row in symlinks}) != len(symlinks):
        raise BaselineError("Symlink remoto duplicato.")
    return files, symlinks, exclusion_record


def digest_json(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def classify_extra(path):
    if path.startswith("themes/sarafatto/assets/dist/assets/") and re.search(r"-[A-Za-z0-9_-]{6,}\.", path):
        return "retained-vite-bundle"
    if re.search(r"(?:\.bak|\.backup|\.orig|~)$", path, re.IGNORECASE):
        return "retained-backup"
    return "retained-extra"


def compare(artifact_file, remote_file, release_sha, authorized_sha, release_id, run_url, accepted_paths):
    if not re.fullmatch(r"[a-f0-9]{40}", release_sha) or release_sha != authorized_sha:
        raise BaselineError("Commit SHA autorizzato non coincide con quello dell'artefatto.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", release_id):
        raise BaselineError("Release ID non valido.")
    if not re.fullmatch(r"https://github\.com/FraCanta/sarafatto/actions/runs/[0-9]+", run_url):
        raise BaselineError("URL dell'esecuzione GitHub non valido.")
    artifact = parse_artifact(artifact_file)
    remote, symlinks, exclusion_record = parse_remote(remote_file)
    accepted = set(accepted_paths)
    if any(not safe_path(path) or excluded(path) for path in accepted):
        raise BaselineError("Percorso extra approvato fuori perimetro.")
    missing = sorted(set(artifact) - set(remote))
    common = set(artifact) & set(remote)
    conflicts = sorted(path for path in common if (
        artifact[path]["sha256"] != remote[path]["sha256"] or artifact[path]["size"] != remote[path]["size"]
    ))
    matching = sorted(path for path in common if path not in conflicts)
    extras = sorted(set(remote) - set(artifact))
    unapproved = sorted(set(extras) - accepted)
    unknown_accepted = sorted(accepted - set(extras))
    if unknown_accepted:
        raise BaselineError("Extra approvato non presente nell'inventario: " + ", ".join(unknown_accepted))
    blockers = []
    if missing:
        blockers.append("file dell'artefatto mancanti")
    if conflicts:
        blockers.append("contenuto diverso dall'artefatto")
    if symlinks:
        blockers.append("symlink gestiti")
    if unapproved:
        blockers.append("file extra non approvati")

    canonical_remote = {
        "files": [{"path": path, **remote[path]} for path in sorted(remote)],
        "symlinks": sorted(symlinks, key=lambda row: row["path"]),
        "exclusion": exclusion_record,
    }
    accepted_extras = [
        {"path": path, **remote[path], "classification": classify_extra(path)}
        for path in extras if path in accepted
    ]
    candidate = None
    if not blockers:
        observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        candidate = {
            "schema_version": 1,
            "release": {"commit_sha": release_sha, "release_id": release_id, "github_actions_run": run_url},
            "provenance": "bootstrap-content-match",
            "verification": {
                "status": "verified-awaiting-initialization",
                "verified_at_utc": observed_at,
                "artifact_files": len(artifact),
                "matching_files": len(matching),
                "conflicts": 0,
                "missing_files": 0,
                "managed_symlinks": 0,
                "unapproved_extras": 0,
                "deployment_performed_by_workflow": False,
                "remote_inventory_sha256": digest_json(canonical_remote),
            },
            "managed_files": [
                {"path": path, **remote[path], "classification": "artifact"} for path in sorted(artifact)
            ],
            "accepted_extras": accepted_extras,
            "exclusions": [{
                "path": exclusion_record["path"],
                "files": exclusion_record["files"],
                "symlinks": exclusion_record["symlinks"],
                "reason": "Dipendenze npm locali escluse dal pacchetto e dal confronto.",
            }],
            "publication_date": None,
        }
    return {
        "status": "blocked" if blockers else "verified-awaiting-explicit-approval",
        "release_sha": release_sha,
        "artifact_count": len(artifact),
        "matching": matching,
        "missing": missing,
        "conflicts": conflicts,
        "extras": extras,
        "unapproved_extras": unapproved,
        "accepted_extras": accepted_extras,
        "symlinks": symlinks,
        "exclusion": exclusion_record,
        "blockers": blockers,
        "candidate": candidate,
    }


def render_report(result):
    lines = [
        f"# Verifica bootstrap baseline — {result['release_sha']}",
        "",
        f"Esito confronto: **{result['status']}**.",
        "Nessuna pubblicazione o scrittura della baseline eseguita dal confronto.",
        f"File artefatto: {result['artifact_count']}; corrispondenze SHA-256: {len(result['matching'])}.",
        f"Esclusione {EXCLUDED}/: {result['exclusion']['files']} file e {result['exclusion']['symlinks']} symlink conteggiati, non confrontati.",
        "",
    ]
    sections = [
        ("File mancanti", result["missing"]),
        ("Conflitti SHA-256/dimensione", result["conflicts"]),
        ("Extra presenti solo sul server, conservati", result["extras"]),
        ("Extra non approvati", result["unapproved_extras"]),
        ("Symlink gestiti (bloccanti)", [f"{row['path']} -> {row['target']}" for row in result["symlinks"]]),
    ]
    for title, paths in sections:
        lines.append(f"## {title} ({len(paths)})")
        lines.extend(f"- {path}" for path in paths[:20] or ["Nessuno"])
        if len(paths) > 20:
            lines.append(f"- … altri {len(paths) - 20} omessi")
        lines.append("")
    if result["blockers"]:
        lines.append("Baseline non creabile: " + "; ".join(result["blockers"]) + ".")
    else:
        lines.append("Il candidato richiede revisione e inizializzazione esplicita separata.")
    return "\n".join(lines) + "\n"


def validate_private_state(private_root, expected_root):
    private_root = pathlib.Path(private_root)
    expected_root = pathlib.Path(expected_root)
    if private_root != expected_root:
        raise BaselineError("Destinazione diversa dalla root privata autorizzata.")
    public = pathlib.Path("/home/www/public")
    if private_root == public or public in private_root.parents:
        raise BaselineError("La baseline non può essere scritta nella webroot.")
    if private_root == PRIVATE_ROOT:
        for ancestor in (pathlib.Path("/home"), pathlib.Path("/home/www")):
            try:
                ancestor_info = ancestor.lstat()
            except FileNotFoundError as exc:
                raise BaselineError(f"Parent privata assente: {ancestor}") from exc
            if stat.S_ISLNK(ancestor_info.st_mode) or not stat.S_ISDIR(ancestor_info.st_mode):
                raise BaselineError(f"Parent privata non regolare o symlink: {ancestor}")
    for directory in (private_root, private_root / "state", private_root / "locks"):
        try:
            info = directory.lstat()
        except FileNotFoundError as exc:
            raise BaselineError(f"Directory privata assente: {directory}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise BaselineError(f"Directory privata non regolare o symlink: {directory}")
        if os.name == "posix":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise BaselineError(f"Proprietario inatteso: {directory}")
            if stat.S_IMODE(info.st_mode) != 0o700:
                raise BaselineError(f"Permessi attesi 700: {directory}")
    marker = private_root / MARKER
    try:
        marker_info = marker.lstat()
        marker_value = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BaselineError("Marker ambiente privato assente o illeggibile.") from exc
    if stat.S_ISLNK(marker_info.st_mode) or not stat.S_ISREG(marker_info.st_mode) or marker_value != MARKER_VALUE:
        raise BaselineError("Marker ambiente privato non valido.")
    if os.name == "posix":
        if hasattr(os, "getuid") and marker_info.st_uid != os.getuid():
            raise BaselineError("Proprietario marker ambiente privato inatteso.")
        if stat.S_IMODE(marker_info.st_mode) != 0o600:
            raise BaselineError("Permessi marker ambiente privato attesi 600.")
    return private_root / "state", private_root / "locks"


def acquire_baseline_lock(locks_dir):
    """Acquisisce un flock non bloccante su un file persistente nell'area privata."""
    if fcntl is None:
        raise BaselineError("flock non è disponibile: inizializzazione impossibile.")
    lock = locks_dir / "baseline-initialization.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        lock_fd = os.open(lock, flags, 0o600)
    except OSError as exc:
        raise BaselineError("Impossibile aprire in sicurezza il lock privato.") from exc
    info = os.fstat(lock_fd)
    if (not stat.S_ISREG(info.st_mode)
            or (os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600)
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())):
        os.close(lock_fd)
        raise BaselineError("File lock non regolare o con permessi inattesi.")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lock_fd)
        raise BaselineError("Lock baseline già occupato da un'altra operazione.") from exc
    return lock_fd


def install_without_overwrite(temporary, target):
    """Rename atomico senza sostituire un target creato concorrente."""
    if os.name == "nt":
        # Su Windows os.rename fallisce se la destinazione esiste già.
        os.rename(temporary, target)
        return
    if os.name == "posix":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            renameat2.restype = ctypes.c_int
            result = renameat2(-100, os.fsencode(temporary), -100, os.fsencode(target), 1)  # RENAME_NOREPLACE
            if result == 0:
                return
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise BaselineError("Baseline già presente: non verrà sovrascritta.")
            if error not in (errno.ENOSYS, errno.EINVAL, getattr(errno, "EOPNOTSUPP", errno.EINVAL)):
                raise OSError(error, os.strerror(error), str(target))
    # Hard link sullo stesso filesystem: pubblicazione atomica e no-clobber nei sistemi
    # senza renameat2; il temporaneo viene rimosso subito dopo.
    os.link(temporary, target, follow_symlinks=False)
    temporary.unlink()


def verified_inventory_script(authorized_sha, repo_root=REPOSITORY_ROOT, git_runner=subprocess.run):
    """Restituisce i byte del file solo se identici al blob dello SHA autorizzato."""
    if not re.fullmatch(r"[a-f0-9]{40}", authorized_sha):
        raise BaselineError("SHA autorizzato non valido per verificare lo script inventario.")
    repo_root = pathlib.Path(repo_root)
    try:
        root_info = repo_root.lstat()
        script_path = repo_root / INVENTORY_RELATIVE_PATH
        script_info = script_path.lstat()
        if (stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode)
                or repo_root.resolve(strict=True) != repo_root):
            raise BaselineError("Root del repository remoto non canonica o symlink.")
        if (stat.S_ISLNK(script_info.st_mode) or not stat.S_ISREG(script_info.st_mode)
                or script_path.resolve(strict=True) != script_path):
            raise BaselineError("Script inventario non regolare o raggiunto tramite symlink.")
        working_bytes = script_path.read_bytes()
    except OSError as exc:
        raise BaselineError("Script o repository remoto non disponibili.") from exc
    try:
        committed = git_runner(
            ["git", "-C", str(repo_root), "show", f"{authorized_sha}:{INVENTORY_RELATIVE_PATH}"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BaselineError("Impossibile verificare lo script contro il commit autorizzato.") from exc
    if committed.returncode != 0 or not committed.stdout:
        raise BaselineError("Il commit autorizzato non contiene lo script di inventario verificabile.")
    if working_bytes != committed.stdout:
        raise BaselineError("Lo script inventario sul server differisce dal blob del commit autorizzato.")
    return working_bytes


def acquire_fresh_inventory(authorized_sha):
    """Acquisisce lo stato corrente usando soltanto lo script versionato autorizzato."""
    verified_bytes = verified_inventory_script(authorized_sha)
    try:
        result = subprocess.run(
            ["bash", "-s"], input=verified_bytes, check=False, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BaselineError("Acquisizione dell'inventario fresco fallita.") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-1000:]
        raise BaselineError("Acquisizione inventario fallita" + (f": {detail}" if detail else "."))
    if not result.stdout:
        raise BaselineError("Inventario fresco vuoto.")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BaselineError("Inventario fresco non UTF-8.") from exc


def compare_fresh_inventory(artifact_file, inventory_text, candidate, authorized_sha, state_dir):
    """Confronta una fotografia appena acquisita con artefatto e candidato approvato."""
    descriptor, name = tempfile.mkstemp(prefix=".fresh-inventory.", dir=state_dir)
    inventory_path = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(inventory_text)
            stream.flush()
            os.fsync(stream.fileno())
        release = candidate.get("release", {})
        accepted = [row["path"] for row in candidate.get("accepted_extras", [])]
        fresh = compare(
            artifact_file, inventory_path, release.get("commit_sha", ""), authorized_sha,
            release.get("release_id", ""), release.get("github_actions_run", ""), accepted,
        )
        if fresh["candidate"] is None:
            raise BaselineError("Il confronto fresco ha rilevato discrepanze: " + "; ".join(fresh["blockers"]))
        current = fresh["candidate"]["verification"]["remote_inventory_sha256"]
        if candidate.get("verification", {}).get("remote_inventory_sha256") != current:
            raise BaselineError("Inventario remoto cambiato dopo la revisione del candidato.")
        if (candidate.get("managed_files") != fresh["candidate"].get("managed_files")
                or candidate.get("accepted_extras") != fresh["candidate"].get("accepted_extras")
                or candidate.get("exclusions") != fresh["candidate"].get("exclusions")):
            raise BaselineError("File gestiti, permessi, extra o esclusioni diversi dal candidato approvato.")
        if candidate.get("release", {}).get("commit_sha") != authorized_sha:
            raise BaselineError("SHA candidato diverso dal commit autorizzato.")
        return fresh
    finally:
        try:
            inventory_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_initial_baseline(candidate, private_root, expected_root):
    state_dir, _ = validate_private_state(private_root, expected_root)
    target = state_dir / "baseline.json"
    if target.exists() or target.is_symlink():
        raise BaselineError("Baseline già presente: non verrà sovrascritta.")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    temporary = state_dir / (".baseline.json.tmp." + str(os.getpid()))
    try:
        if target.exists() or target.is_symlink():
            raise BaselineError("Baseline già presente: non verrà sovrascritta.")
        initialized = json.loads(json.dumps(candidate))
        initialized["verification"]["status"] = "initialized-from-verified-content-match"
        initialized["baseline_initialized_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload = (json.dumps(initialized, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        expected_digest = hashlib.sha256(payload).hexdigest()
        temp_fd = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(temp_fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            readback = temporary.read_bytes()
            if hashlib.sha256(readback).hexdigest() != expected_digest or json.loads(readback) != initialized:
                raise BaselineError("Verifica integrità del file temporaneo fallita.")
            if target.exists() or target.is_symlink():
                raise BaselineError("Baseline già presente: non verrà sovrascritta.")
            install_without_overwrite(temporary, target)
            if os.name == "posix":
                directory_fd = os.open(state_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target, expected_digest
    finally:
        if temporary.exists():
            temporary.unlink()


def initialize_baseline(candidate, candidate_digest, approved_candidate_digest, artifact_file,
                        authorized_sha, confirmation, private_root, expected_root):
    """Verifica due inventari live sotto flock e scrive solo nella root privata."""
    release_sha = candidate.get("release", {}).get("commit_sha", "")
    if candidate_digest != approved_candidate_digest or not re.fullmatch(r"[a-f0-9]{64}", approved_candidate_digest):
        raise BaselineError("SHA-256 candidato diverso da quello approvato.")
    if (release_sha != authorized_sha or confirmation != "INITIALIZE " + release_sha
            or candidate.get("schema_version") != 1
            or candidate.get("verification", {}).get("status") != "verified-awaiting-initialization"):
        raise BaselineError("Conferma, SHA autorizzato o stato candidato non validi.")

    state_dir, locks_dir = validate_private_state(private_root, expected_root)
    target = state_dir / "baseline.json"
    if target.exists() or target.is_symlink():
        raise BaselineError("Baseline già presente: non verrà sovrascritta.")
    lock_fd = acquire_baseline_lock(locks_dir)
    try:
        if target.exists() or target.is_symlink():
            raise BaselineError("Baseline già presente: non verrà sovrascritta.")
        first = compare_fresh_inventory(
            artifact_file, acquire_fresh_inventory(authorized_sha), candidate,
            authorized_sha, state_dir,
        )
        second = compare_fresh_inventory(
            artifact_file, acquire_fresh_inventory(authorized_sha), candidate,
            authorized_sha, state_dir,
        )
        first_digest = first["candidate"]["verification"]["remote_inventory_sha256"]
        second_digest = second["candidate"]["verification"]["remote_inventory_sha256"]
        if first_digest != second_digest:
            raise BaselineError("Filesystem cambiato tra le due verifiche finali.")
        # Il controllo finale avviene immediatamente prima dell'installazione atomica.
        result = _atomic_write_initial_baseline(candidate, private_root, expected_root)
        return result, second
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def write_candidate(filename, candidate):
    destination = pathlib.Path(filename).absolute()
    public = pathlib.Path("/home/www/public")
    if destination == public or public in destination.parents or destination.is_symlink():
        raise BaselineError("Destinazione candidato non valida o nella webroot.")
    payload = (json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def load_candidate(filename):
    path = pathlib.Path(filename)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > 20_000_000:
        raise BaselineError("File candidato non regolare o troppo grande.")
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def argument_parser():
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)
    compare_parser = subparsers.add_parser("compare", help="report e candidato; non scrive la baseline")
    compare_parser.add_argument("--artifact-inventory", required=True)
    compare_parser.add_argument("--remote-inventory", required=True)
    compare_parser.add_argument("--release-sha", required=True)
    compare_parser.add_argument("--authorized-sha", required=True)
    compare_parser.add_argument("--release-id", required=True)
    compare_parser.add_argument("--run-url", required=True)
    compare_parser.add_argument("--accept-extra", action="append", default=[])
    compare_parser.add_argument("--candidate-out")

    init_parser = subparsers.add_parser("initialize", help="reverifica input e inizializza la baseline privata")
    init_parser.add_argument("--candidate", required=True)
    init_parser.add_argument("--artifact-inventory", required=True)
    init_parser.add_argument("--authorized-sha", required=True)
    init_parser.add_argument("--approved-candidate-sha256", required=True)
    init_parser.add_argument("--confirm-initial-baseline", required=True)
    return root


def main(argv=None):
    args = argument_parser().parse_args(argv)
    try:
        if args.command == "compare":
            result = compare(
                args.artifact_inventory, args.remote_inventory, args.release_sha,
                args.authorized_sha, args.release_id, args.run_url, args.accept_extra,
            )
            sys.stdout.write(render_report(result))
            if result["candidate"] is None:
                return 4
            if args.candidate_out:
                digest = write_candidate(args.candidate_out, result["candidate"])
                print(f"Candidato creato, non installato; SHA-256 {digest}.")
            return 0

        candidate, candidate_digest = load_candidate(args.candidate)
        (target, digest), result = initialize_baseline(
            candidate=candidate,
            candidate_digest=candidate_digest,
            approved_candidate_digest=args.approved_candidate_sha256,
            artifact_file=args.artifact_inventory,
            authorized_sha=args.authorized_sha,
            confirmation=args.confirm_initial_baseline,
            private_root=PRIVATE_ROOT,
            expected_root=PRIVATE_ROOT,
        )
        sys.stdout.write(render_report(result))
        print(f"Baseline inizializzata atomicamente: {target} (SHA-256 {digest}).")
        return 0
    except (BaselineError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
