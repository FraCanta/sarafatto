#!/usr/bin/env python3
"""Solo ispezione read-only dello stato reale SaràFatto su IONOS.

Il modulo non implementa pubblicazione o rollback. Tutti i percorsi sono fissi;
le sole operazioni CLI disponibili leggono stato e inventario.
"""

import argparse
import hashlib
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
PRIVATE_TOOLS_ROOT = PRIVATE_ROOT / "tools/scripts/deploy"
BASELINE_SHA256 = "07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd"
SOURCE_FILES = (
    "scripts/deploy/production_adapter.py",
    "scripts/deploy/baseline_tool.py",
    "scripts/deploy/backup_tool.py",
    "scripts/deploy/release_state_tool.py",
    "scripts/deploy/baseline-inventory.sh",
    "scripts/deploy/production_publisher.py",
    "scripts/deploy/artifact_transfer_tool.py",
    "scripts/deploy/request_barrier_tool.py",
    "scripts/deploy/mu_plugin_migration_tool.py",
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
            or (stat.S_IMODE(info.st_mode) != mode if mode is not None
                else bool(stat.S_IMODE(info.st_mode) & 0o022))):
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
        raise ProductionAdapterError("Repository Git IONOS non accessibile o comando scaduto.") from exc
    if result.returncode != 0:
        if arguments and arguments[0] == "show":
            raise ProductionAdapterError("Contenuto Git non leggibile nel commit autorizzato.")
        if arguments and arguments[0] == "ls-tree":
            raise ProductionAdapterError("Albero Git del commit autorizzato non accessibile.")
        raise ProductionAdapterError("Repository Git IONOS o HEAD non accessibile.")
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
    try:
        _require_fixed_directory(REPOSITORY_ROOT)
    except ProductionAdapterError as exc:
        raise ProductionAdapterError("Repository Git IONOS assente, non accessibile o non sicuro.") from exc
    head = _git_output(["rev-parse", "--verify", "HEAD"]).decode("ascii", errors="strict").strip()
    if head != authorized_sha:
        raise ProductionAdapterError("HEAD Git diverso dallo SHA autorizzato; ispezione legacy bloccata.")
    for relative in SOURCE_FILES:
        if not _git_output(["ls-tree", "--name-only", authorized_sha, "--", relative]).strip():
            raise ProductionAdapterError(f"File assente nel commit autorizzato: {relative}.")
        committed = _git_output(["show", f"{authorized_sha}:{relative}"])
        try:
            working = _read_repo_file(relative)
        except OSError as exc:
            raise ProductionAdapterError(f"File del checkout assente o illeggibile: {relative}.") from exc
        if working != committed:
            raise ProductionAdapterError(f"Contenuto del checkout modificato rispetto al commit autorizzato: {relative}.")
    return authorized_sha


def verify_private_toolchain(expected_sha256):
    """Il digest atteso deve arrivare dal report CI approvato, mai da un auto-bootstrap."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ProductionAdapterError("Verifica della toolchain privata richiede POSIX/O_NOFOLLOW.")
    if not re.fullmatch(r"[a-f0-9]{64}", str(expected_sha256 or "")):
        raise ProductionAdapterError("Digest toolchain autorizzato esternamente mancante o non valido.")
    _require_fixed_directory(PRIVATE_TOOLS_ROOT)
    if pathlib.Path(__file__).absolute() != PRIVATE_TOOLS_ROOT / "production_adapter.py":
        raise ProductionAdapterError("Adapter caricato fuori dalla toolchain privata autorizzata.")
    # Import tardivo: il ricevitore importa a sua volta adapter e publisher.
    import artifact_transfer_tool
    try:
        report = artifact_transfer_tool._validate_toolchain(expected_sha256)
        for path in (PRIVATE_ROOT, PRIVATE_ROOT / "tools", PRIVATE_ROOT / "tools/scripts", PRIVATE_TOOLS_ROOT):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise ProductionAdapterError("Directory degli strumenti con ownership o permessi inattesi.")
            if path == PRIVATE_ROOT and stat.S_IMODE(info.st_mode) != 0o700:
                raise ProductionAdapterError("La root privata deve conservare permessi 0700.")
        for row in report["contract"]["files"]:
            info = (PRIVATE_TOOLS_ROOT / row["file"]).lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022):
                raise ProductionAdapterError(f"File strumenti non sicuro: {row['file']}.")
        return report
    except (artifact_transfer_tool.TransferError, artifact_transfer_tool.production_publisher.PublisherError,
            OSError, ValueError) as exc:
        raise ProductionAdapterError(f"Toolchain privata non autorizzata: {exc}") from exc


def private_inventory_reader(expected_sha256):
    """Esegue solo lo script privato coperto dal digest indipendente della toolchain."""
    def acquire(_inventory_commit):
        report = verify_private_toolchain(expected_sha256)
        expected = next(row["sha256"] for row in report["contract"]["files"]
                        if row["file"] == "baseline-inventory.sh")
        directory_fd = _open_checked_dir(PRIVATE_TOOLS_ROOT, mode=None)
        try:
            import artifact_transfer_tool
            try:
                payload = artifact_transfer_tool._read_at(directory_fd, "baseline-inventory.sh", 1024 * 1024)
            except (artifact_transfer_tool.TransferError, OSError) as exc:
                raise ProductionAdapterError("Script inventario privato non leggibile in sicurezza.") from exc
        finally:
            os.close(directory_fd)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ProductionAdapterError("Script inventario privato cambiato dopo la verifica della toolchain.")
        try:
            result = subprocess.run(["bash", "-s"], input=payload, check=False,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProductionAdapterError("Acquisizione privata dell'inventario non eseguibile.") from exc
        if result.returncode != 0 or not result.stdout:
            raise ProductionAdapterError("Inventario privato fallito o vuoto; stato pubblico non verificato.")
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProductionAdapterError("Inventario privato non UTF-8.") from exc
    return acquire


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


def inspect_production_state(authorized_sha=None, *, toolchain_sha256=None):
    """Verifica stato e contenuti live con lock condiviso; non modifica file."""
    if os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW"):
        raise ProductionAdapterError("L'ispezione IONOS richiede POSIX, flock e O_NOFOLLOW.")
    if toolchain_sha256 is not None:
        if authorized_sha is not None:
            raise ProductionAdapterError("Specificare una sola autorità: toolchain privata oppure repository legacy.")
        trust = verify_private_toolchain(toolchain_sha256)
        acquire_inventory = private_inventory_reader(toolchain_sha256)
    else:
        if pathlib.Path(__file__).absolute().parent == PRIVATE_TOOLS_ROOT:
            raise ProductionAdapterError("La toolchain privata richiede --toolchain-sha256 dal report CI approvato.")
        authorized_sha = verify_repository_sources(authorized_sha)
        trust = None
        acquire_inventory = baseline_tool.acquire_fresh_inventory
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
            first = acquire_inventory(inventory_commit)
            second = acquire_inventory(inventory_commit)
        except baseline_tool.BaselineError as exc:
            raise ProductionAdapterError(f"Doppio inventario pubblico fresco fallito: {exc}") from exc
        first_files, _, first_raw_digest, _ = _canonical_live_inventory(first)
        second_files, second_exclusion, second_raw_digest, second_inventory = _canonical_live_inventory(second)
        if first_raw_digest != second_raw_digest:
            raise ProductionAdapterError("Filesystem pubblico variato tra i due inventari freschi.")
        live_reference = expected
        if current_state is not None:
            live_reference = {
                row["path"]: {key: row[key] for key in ("sha256", "size", "mode", "classification")}
                for row in current_state["reference_files"]
            }
        backup_tool.compare_inventory_to_baseline(second_files, [], second_exclusion, live_reference)

        journal = release_state_tool.read_journal_at(state_fd)
        try:
            if current_state is not None:
                release_state_tool.validate_current_state_journal(current_state, journal)
            else:
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
            "toolchain_sha256": None if trust is None else trust["toolchain_sha256"],
            "trust_mode": "legacy-git" if trust is None else "externally-authorized-private-toolchain",
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
            # Dettagli limitati ai percorsi gestiti; usati dal planner read-only.
            # Non costituiscono autorizzazione a pubblicare.
            "live_file_records": [
                {"path": name, **second_files[name]} for name in sorted(second_files)
            ],
            "current_reference_files": (
                [] if current_state is None else current_state["reference_files"]
            ),
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
    authority = inspect.add_mutually_exclusive_group(required=True)
    authority.add_argument("--authorized-sha", help="solo percorso legacy Git")
    authority.add_argument("--toolchain-sha256", help="digest degli strumenti dal report CI approvato")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = inspect_production_state(args.authorized_sha, toolchain_sha256=args.toolchain_sha256)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "verified-current" else 3
    except (ProductionAdapterError, OSError, ValueError, UnicodeError,
            backup_tool.BackupError, baseline_tool.BaselineError,
            release_state_tool.ReleaseStateError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
