#!/usr/bin/env python3
"""Solo ispezione read-only dello stato reale SaràFatto su IONOS.

Il modulo non implementa pubblicazione o rollback. Tutti i percorsi sono fissi;
le sole operazioni CLI disponibili leggono stato e inventario.
"""

import argparse
import json
import os
import pathlib
import re
import stat
import subprocess
import sys

import backup_tool
import baseline_tool
import release_state_tool

try:
    import fcntl
except ImportError:  # Importabile per test statici Windows; runtime IONOS è POSIX.
    fcntl = None

PUBLIC_ROOT = pathlib.Path("/home/www/public/wp-content")
PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
REPOSITORY_ROOT = pathlib.Path("/home/www/sarafatto-repo")
BASELINE_SHA256 = "07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd"
SOURCE_FILES = (
    "scripts/deploy/production_adapter.py",
    "scripts/deploy/baseline_tool.py",
    "scripts/deploy/backup_tool.py",
    "scripts/deploy/release_state_tool.py",
    "scripts/deploy/baseline-inventory.sh",
)


class ProductionAdapterError(Exception):
    """Ispezione IONOS non verificabile: fail closed."""


def is_authorized_public_file(relative):
    return isinstance(relative, str) and baseline_tool.safe_path(relative) and not baseline_tool.excluded(relative)


def validate_authorized_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ProductionAdapterError("Lo SHA autorizzato deve contenere 40 caratteri esadecimali minuscoli.")
    return value


def current_state_readiness(current_state):
    """Rende esplicito che uno stato mancante blocca la pubblicazione."""
    if current_state is None:
        return "bootstrap-required", [
            "current-release.json assente: eseguire separatamente il bootstrap autorizzato"
        ]
    if (not isinstance(current_state, dict)
            or not re.fullmatch(r"[a-f0-9]{64}", str(current_state.get("state_sha256", "")))
            or current_state.get("verification", {}).get("status") != "verified-current"):
        raise ProductionAdapterError("current-release fornito non è uno stato validato.")
    return "verified-current", []


def publication_readiness(*, current_state, traffic_barrier_verified=False,
                          transaction_verifier_available=False,
                          health_check_verified=False, fresh_backup_verified=False,
                          explicit_environment_approval=False):
    """Gate esplicito: inspect non equivale mai ad autorizzazione di pubblicazione.

    Le prove devono arrivare da verificatori implementati e indipendenti; valori
    booleani da soli non vengono esposti nella CLI e questa funzione non effettua
    né abilita scritture.
    """
    blockers = []
    try:
        current_state_readiness(current_state)
    except ProductionAdapterError as exc:
        blockers.append(str(exc))
    if not traffic_barrier_verified:
        blockers.append("Barriera verificata contro versioni miste non disponibile.")
    if not transaction_verifier_available:
        blockers.append("Verificatore di transazione di produzione non implementato.")
    if not fresh_backup_verified:
        blockers.append("Backup fresco verificato per questa operazione non disponibile.")
    if not health_check_verified:
        blockers.append("Health check post-operazione non verificato.")
    if not explicit_environment_approval:
        blockers.append("Approvazione esplicita dell'ambiente di produzione assente.")
    # Non esiste ancora un publisher di produzione. Anche prove future non
    # devono rendere questa ispezione una via indiretta per abilitare scritture.
    blockers.append("Publisher di produzione non implementato: le scritture restano disabilitate.")
    return {"status": "blocked",
            "publish_allowed": False, "blockers": blockers}


def _require_fixed_directory(path):
    path = pathlib.Path(path)
    if not path.is_absolute():
        raise ProductionAdapterError(f"Percorso fisso non assoluto: {path}.")
    current = pathlib.Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except OSError as exc:
            raise ProductionAdapterError(f"Directory fissa assente o illeggibile: {current}.") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ProductionAdapterError(f"Componente non directory o symlink nel percorso fisso: {current}.")
    try:
        if path.resolve(strict=True) != path:
            raise ProductionAdapterError(f"Percorso fisso non canonico: {path}.")
    except OSError as exc:
        raise ProductionAdapterError(f"Percorso fisso non risolvibile: {path}.") from exc


def _open_checked_dir(path, *, mode=0o700):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != mode):
        os.close(fd)
        raise ProductionAdapterError(f"Proprietario o permessi inattesi: {path}.")
    return fd


def _git_output(arguments):
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), *arguments], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProductionAdapterError("Verifica read-only del repository IONOS non riuscita.") from exc
    if result.returncode != 0:
        raise ProductionAdapterError("Repository IONOS non verificabile contro lo SHA autorizzato.")
    return result.stdout


def _read_repo_file(relative):
    path = REPOSITORY_ROOT.joinpath(*relative.split("/"))
    _require_fixed_directory(path.parent)
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16 * 1024 * 1024:
                raise ProductionAdapterError(f"Sorgente remota non regolare o troppo grande: {relative}.")
            chunks = []
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                chunks.append(block)
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def verify_repository_sources(authorized_sha):
    authorized_sha = validate_authorized_sha(authorized_sha)
    _require_fixed_directory(REPOSITORY_ROOT)
    head = _git_output(["rev-parse", "--verify", "HEAD"]).decode("ascii", errors="strict").strip()
    if head != authorized_sha:
        raise ProductionAdapterError("Repository IONOS non allineato allo SHA autorizzato; ispezione bloccata.")
    for relative in SOURCE_FILES:
        committed = _git_output(["show", f"{authorized_sha}:{relative}"])
        if _read_repo_file(relative) != committed:
            raise ProductionAdapterError(f"File sorgente remoto modificato rispetto al commit autorizzato: {relative}.")
    return authorized_sha


def _canonical_live_inventory(text):
    files, symlinks, exclusion, raw_digest = backup_tool.parse_inventory_text(text)
    if symlinks:
        raise ProductionAdapterError("Symlink nel perimetro pubblico gestito.")
    return files, exclusion, raw_digest, {
        "files": [{"path": name, **files[name]} for name in sorted(files)],
        "symlinks": [],
        "exclusion": exclusion,
    }


def _assert_matches_reference(files, expected):
    if set(files) != set(expected):
        raise ProductionAdapterError("Inventario pubblico con percorsi mancanti o inattesi rispetto alla baseline.")
    for name, row in expected.items():
        if any(files[name].get(key) != row.get(key) for key in ("sha256", "size", "mode")):
            raise ProductionAdapterError(f"Hash, dimensione o permessi pubblici inattesi: {name}.")


def _read_current_state(state_fd, baseline_sha):
    try:
        info = os.stat(release_state_tool.STATE_NAME, dir_fd=state_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ProductionAdapterError("current-release.json è symlink o file non regolare.")
    try:
        return release_state_tool.load_current_state(state_fd, baseline_sha)
    except release_state_tool.ReleaseStateError as exc:
        raise ProductionAdapterError(f"current-release.json non valido: {exc}") from exc


def inspect_production_state(authorized_sha):
    """Verifica stato e contenuti live con lock condiviso; non modifica file."""
    if os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW"):
        raise ProductionAdapterError("L'ispezione IONOS richiede POSIX, flock e O_NOFOLLOW.")
    authorized_sha = verify_repository_sources(authorized_sha)
    _require_fixed_directory(PUBLIC_ROOT)
    baseline_tool.validate_private_state(PRIVATE_ROOT, PRIVATE_ROOT)
    root_fd = _open_checked_dir(PRIVATE_ROOT)
    state_fd = locks_fd = lock_fd = None
    try:
        state_fd = release_state_tool._open_dir(root_fd, "state")
        locks_fd = release_state_tool._open_dir(root_fd, "locks")
        try:
            lock_fd = os.open("site-operation.lock", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=locks_fd)
        except OSError as exc:
            raise ProductionAdapterError("Lock operativo assente o non apribile in sola lettura.") from exc
        lock_info = os.fstat(lock_fd)
        if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1
                or lock_info.st_uid != os.getuid() or stat.S_IMODE(lock_info.st_mode) != 0o600):
            raise ProductionAdapterError("Lock operativo non regolare o con permessi inattesi.")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProductionAdapterError("Operazione concorrente attiva; ispezione read-only rifiutata.") from exc

        try:
            baseline_document, baseline_sha, baseline_commit, expected = backup_tool.validate_backup_baseline(
                None, BASELINE_SHA256, state_fd=state_fd)
        except (backup_tool.BackupError, OSError) as exc:
            raise ProductionAdapterError(f"Baseline ufficiale non verificata: {exc}") from exc
        if baseline_sha != BASELINE_SHA256:
            raise ProductionAdapterError("Baseline non coincide con lo SHA ufficiale approvato.")

        current_state = _read_current_state(state_fd, baseline_sha)
        if current_state is None:
            inventory_commit = baseline_commit
            state_digest = None
            state_inventory_digest = None
        else:
            if current_state["initial_baseline"]["sha256"] != baseline_sha:
                raise ProductionAdapterError("current-release non è legato alla baseline ufficiale.")
            inventory_commit = current_state["release"]["inventory_tool_commit"]
            state_digest = current_state["state_sha256"]
            state_inventory_digest = current_state["inventory_sha256"]

        try:
            first = baseline_tool.acquire_fresh_inventory(inventory_commit)
            second = baseline_tool.acquire_fresh_inventory(inventory_commit)
        except baseline_tool.BaselineError as exc:
            raise ProductionAdapterError(f"Doppio inventario pubblico fresco fallito: {exc}") from exc
        first_files, _, first_raw_digest, _ = _canonical_live_inventory(first)
        second_files, second_exclusion, second_raw_digest, second_inventory = _canonical_live_inventory(second)
        if first_raw_digest != second_raw_digest:
            raise ProductionAdapterError("Filesystem pubblico variato tra i due inventari freschi.")
        backup_tool.compare_inventory_to_baseline(second_files, [], second_exclusion, expected)

        journal = release_state_tool.read_journal_at(state_fd)
        try:
            release_state_tool.unresolved_operation(journal)
        except release_state_tool.ReleaseStateError as exc:
            raise ProductionAdapterError(f"Journal con operazione irrisolta: {exc}") from exc
        if current_state is not None:
            live_digest = release_state_tool.inventory_digest_json(second_inventory)
            if live_digest != state_inventory_digest:
                raise ProductionAdapterError("Inventario pubblico fresco diverso da current-release.json.")

        status, blockers = current_state_readiness(current_state)
        publication = publication_readiness(current_state=current_state)
        return {
            "status": status,
            "authorized_repository_sha": authorized_sha,
            "baseline_sha256": baseline_sha,
            "baseline_commit_sha": baseline_commit,
            "current_release": None if current_state is None else {
                "commit_sha": current_state["release"]["commit_sha"],
                "release_id": current_state["release"]["release_id"],
                "state_sha256": state_digest,
                "inventory_sha256": state_inventory_digest,
            },
            "live_inventory_sha256": release_state_tool.inventory_digest_json(second_inventory),
            "live_files": len(second_files),
            "node_modules_excluded_files": second_exclusion["files"],
            "node_modules_excluded_symlinks": second_exclusion["symlinks"],
            "journal_events": len(journal),
            "public_writes_performed": False,
            "publish_allowed": publication["publish_allowed"],
            "publication_readiness": publication,
            "blockers": publication["blockers"],
        }
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if locks_fd is not None:
            os.close(locks_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="ispezione read-only baseline, stato e filesystem")
    inspect.add_argument("--authorized-sha", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = inspect_production_state(args.authorized_sha)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "verified-current" else 3
    except (ProductionAdapterError, OSError, ValueError, UnicodeError,
            backup_tool.BackupError, baseline_tool.BaselineError,
            release_state_tool.ReleaseStateError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
