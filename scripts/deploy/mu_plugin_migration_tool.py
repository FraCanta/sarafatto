#!/usr/bin/env python3
"""Preflight bloccante per la prima installazione della request barrier.

L'installazione del solo MU-plugin può usare una sostituzione atomica a file
singolo: evita sorgenti parziali e non richiede il drain per la coerenza fra
componenti. Il writer resta disabilitato finché backup e transizione journal/
current-release non sono verificabili. La barriera non si considera attiva
uniformemente fino a prova dell'adozione del nuovo opcode da parte dei worker.
"""

import argparse
import hashlib
import json
import os
import pathlib
import stat
import subprocess
import sys
from datetime import datetime, timezone

import backup_tool
import baseline_tool

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET_RELATIVE = "mu-plugins/sarafatto-polylang-front-page-url.php"
AUTHORIZED_REPOSITORY_SHA = "50bbe01af38814f41d5a67bb37fef45b181f5fd1"
CURRENT_PUBLIC_RELEASE_SHA = "911d6a72ac0f624dc85b43d53b1c299968d683f6"
CURRENT_PUBLIC_INVENTORY_SHA256 = "d0aa002e885f252ddf23226eb59c30857dce4a1c24a03fc50da66aaadb1340cf"
BASELINE_SHA256 = "07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd"
OLD_MU_PLUGIN_SHA256 = "2ffd84b3f170ec2e0eae1cab5935391bb8e9d5311e3c55025719ab60d1417252"
NEW_MU_PLUGIN_SHA256 = "1b4d430566abf2b01e3e22512212e2f03f623450e207366e63f02d97e85d4c7f"
OFFICIAL_BACKUP_ID = "20261024T181841Z-bdcc8d63457a"
OFFICIAL_BACKUP_MANIFEST_SHA256 = "c502c1fe239515ff3324a4c55e77443c9a6ab7b8e6c77d4e3472a3d84ab369ae"
OFFICIAL_BACKUP_PATH = f"/home/www/sarafatto-deploy/backups/{OFFICIAL_BACKUP_ID}"
LEGACY_DEDICATED_BACKUP = "/home/www/sarafatto-deploy/backups/mu-plugin-pre-barrier-20261026T201411Z"
PUBLIC_WRITE_ENABLED = False
MAX_SOURCE_BYTES = 1024 * 1024
BACKUP_DIRECTORY_NAME = OFFICIAL_BACKUP_ID
BACKUP_ATTESTATION_NAME = "mu-plugin-backup-attestation.json"

BLOCKERS = (
    "Il backup ufficiale è configurato con digest indipendente noto; l'attestazione effettiva su IONOS resta da eseguire in sola lettura prima della migrazione.",
    "current-release.json accetta solo il bootstrap iniziale: manca una transizione journal/state specifica che registri il delta del solo MU-plugin senza dichiarare pubblicata l'intera release.",
    "Dopo l'installazione, l'adozione uniforme del nuovo opcode da parte dei worker PHP web non è dimostrabile con una singola richiesta HTTP; la barriera non può essere armata finché IONOS non fornisce un metodo verificabile di invalidazione/riavvio o attestazione completa dei worker.",
    "Manca una verifica post-migrazione che controlli hash live, risposta WordPress/Polylang e adozione del nuovo opcode; la cache realpath non implica sorgente parziale, ma OPcache può continuare a servire il bytecode precedente.",
)


class MigrationBlocked(Exception):
    """La migrazione non è verificabile o non è autorizzata a scrivere."""


def operation_approval():
    return (f"INSTALL-MU-BARRIER {AUTHORIZED_REPOSITORY_SHA} "
            f"{OLD_MU_PLUGIN_SHA256} {NEW_MU_PLUGIN_SHA256}")


def validate_operation_approval(value):
    if not isinstance(value, str) or value != operation_approval():
        raise MigrationBlocked("Approvazione non corrispondente a questa migrazione specifica.")
    return value


def _read_local_source(path):
    path = pathlib.Path(path)
    try:
        before = path.lstat()
    except OSError as exc:
        raise MigrationBlocked("Sorgente MU-plugin locale assente o illeggibile.") from exc
    if (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1 or before.st_size > MAX_SOURCE_BYTES):
        raise MigrationBlocked("Sorgente MU-plugin locale non regolare o oltre il limite.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise MigrationBlocked("Apertura no-follow della sorgente MU-plugin fallita.") from exc
    try:
        opened = os.fstat(fd)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or opened.st_size > MAX_SOURCE_BYTES):
            raise MigrationBlocked("Sorgente MU-plugin sostituita durante la lettura.")
        chunks = []
        total = 0
        while True:
            block = os.read(fd, min(65536, MAX_SOURCE_BYTES + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > MAX_SOURCE_BYTES:
                raise MigrationBlocked("Sorgente MU-plugin oltre il limite durante la lettura.")
        return b"".join(chunks)
    finally:
        os.close(fd)


def verify_local_candidate(repository_root=REPOSITORY_ROOT):
    """Verifica read-only che checkout e sorgente siano quelli approvati."""
    root = pathlib.Path(repository_root)
    def git_read(*arguments):
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *arguments], check=False,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MigrationBlocked("Git non disponibile per verificare la sorgente approvata.") from exc
        if result.returncode != 0:
            raise MigrationBlocked("Commit o blob sorgente autorizzato non disponibile localmente.")
        return result.stdout

    commit = git_read("rev-parse", "--verify", "HEAD").decode("ascii", errors="strict").strip()
    if not re_full_sha(commit):
        raise MigrationBlocked("HEAD locale non è uno SHA Git completo.")
    committed_source = git_read("show", f"{AUTHORIZED_REPOSITORY_SHA}:{TARGET_RELATIVE}")
    if hashlib.sha256(committed_source).hexdigest() != NEW_MU_PLUGIN_SHA256:
        raise MigrationBlocked("Il blob del MU-plugin nel commit autorizzato ha SHA inatteso.")
    source = _read_local_source(root / TARGET_RELATIVE)
    digest = hashlib.sha256(source).hexdigest()
    if digest != NEW_MU_PLUGIN_SHA256 or source != committed_source:
        raise MigrationBlocked("Sorgente locale diversa dal blob autorizzato del MU-plugin.")
    return {"repository_head": commit, "source_commit": AUTHORIZED_REPOSITORY_SHA,
            "target": TARGET_RELATIVE,
            "new_sha256": digest, "status": "local-candidate-verified"}


def re_full_sha(value):
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def readiness_report():
    return {
        "status": "blocked",
        "public_write_enabled": PUBLIC_WRITE_ENABLED,
        "target": TARGET_RELATIVE,
        "authorized_repository_sha": AUTHORIZED_REPOSITORY_SHA,
        "expected_current_release_sha": CURRENT_PUBLIC_RELEASE_SHA,
        "expected_current_inventory_sha256": CURRENT_PUBLIC_INVENTORY_SHA256,
        "baseline_sha256": BASELINE_SHA256,
        "old_mu_plugin_sha256": OLD_MU_PLUGIN_SHA256,
        "new_mu_plugin_sha256": NEW_MU_PLUGIN_SHA256,
        "official_backup": OFFICIAL_BACKUP_PATH,
        "official_backup_manifest_sha256": OFFICIAL_BACKUP_MANIFEST_SHA256,
        "preserved_legacy_copy": LEGACY_DEDICATED_BACKUP,
        "approval_challenge": operation_approval(),
        "blockers": list(BLOCKERS),
    }


def _fixed_backup_attestation(private_root, expected_root, *, private=None, lock_held=False):
    """Verifica read-only il backup applicativo ufficiale con digest fissato fuori banda."""
    manifest_sha256 = OFFICIAL_BACKUP_MANIFEST_SHA256
    if not re_full_sha256(manifest_sha256):
        raise MigrationBlocked("Digest manifesto approvato non valido.")
    owned_private = private is None
    private = private or backup_tool.open_private_directories(private_root, expected_root)
    backup_fd = None
    lock_fd = None
    try:
        if not lock_held:
            lock_fd = baseline_tool.acquire_baseline_lock(None, private["locks_fd"])
        try:
            _, baseline_digest, baseline_commit, expected = backup_tool.validate_backup_baseline(
                None, BASELINE_SHA256, state_fd=private["state_fd"])
            if baseline_digest != BASELINE_SHA256:
                raise MigrationBlocked("Baseline privata diversa dalla baseline autorizzata.")
            backup_fd = backup_tool.open_directory_at(
                private["backups_fd"], BACKUP_DIRECTORY_NAME, "backup MU-plugin dedicato")
            raw = backup_tool.open_at_regular_bytes(
                backup_fd, "manifest.json", "Manifest backup", 0o600,
                backup_tool.MAX_MANIFEST_BYTES)
            manifest = backup_tool.read_json_no_duplicates(raw, "manifest backup dedicato")
            backup_id = manifest.get("backup_id")
            backup_tool.validate_id(backup_id)
            if backup_id != OFFICIAL_BACKUP_ID:
                raise MigrationBlocked("ID del manifest diverso dal backup applicativo ufficiale autorizzato.")
            verified = backup_tool.verify_backup_directory(
                None, backup_id, BASELINE_SHA256, manifest_sha256,
                require_complete=True, directory_fd=backup_fd)
            backup_tool.verify_manifest_matches_baseline(
                verified["manifest"], baseline_digest, baseline_commit, expected)
            entry = verified["files"].get(TARGET_RELATIVE)
            if (not isinstance(entry, dict)
                    or entry.get("sha256") != OLD_MU_PLUGIN_SHA256
                    or expected.get(TARGET_RELATIVE, {}).get("sha256") != OLD_MU_PLUGIN_SHA256):
                raise MigrationBlocked("Il backup non contiene il MU-plugin originale atteso dalla baseline.")
            return {
                "schema_version": 1,
                "backup_path": OFFICIAL_BACKUP_PATH,
                "backup_id": backup_id,
                "baseline_sha256": baseline_digest,
                "manifest_sha256": verified["manifest_sha256"],
                "target": TARGET_RELATIVE,
                "original": {key: entry[key] for key in ("sha256", "size", "mode")},
                "files_verified": len(verified["files"]),
                "scope": "managed-theme-plugin-and-authorized-mu-plugin-only; excludes database/uploads/third-party-plugins",
                "verified_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "verification": "backup-tool-independent-digest-and-payload-verified",
            }
        finally:
            if lock_fd is not None:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
    except (backup_tool.BackupError, baseline_tool.BaselineError, OSError, ValueError, KeyError) as exc:
        raise MigrationBlocked(f"Backup MU-plugin non verificabile: {exc}") from exc
    finally:
        if backup_fd is not None:
            os.close(backup_fd)
        if owned_private:
            backup_tool.close_private_directories(private)


def re_full_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def verify_official_backup(*, private_root=pathlib.Path("/home/www/sarafatto-deploy"),
                           expected_root=pathlib.Path("/home/www/sarafatto-deploy")):
    """Verifica read-only il backup ufficiale fissato, senza creare attestazioni."""
    private = backup_tool.open_private_directories(private_root, expected_root)
    lock_fd = None
    try:
        lock_fd = baseline_tool.acquire_baseline_lock(None, private["locks_fd"])
        return _fixed_backup_attestation(private_root, expected_root, private=private, lock_held=True)
    finally:
        if lock_fd is not None:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        backup_tool.close_private_directories(private)


def attest_official_backup(*, private_root=pathlib.Path("/home/www/sarafatto-deploy"),
                           expected_root=pathlib.Path("/home/www/sarafatto-deploy")):
    """Verifica il backup immutabile ufficiale e registra attestazione privata no-clobber."""
    private = backup_tool.open_private_directories(private_root, expected_root)
    lock_fd = None
    try:
        lock_fd = baseline_tool.acquire_baseline_lock(None, private["locks_fd"])
        proof = _fixed_backup_attestation(private_root, expected_root,
                                          private=private, lock_held=True)
        name = BACKUP_ATTESTATION_NAME
        payload = (json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        temporary = ".mu-plugin-backup-attestation." + os.urandom(12).hex()
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=private["state_fd"])
            try:
                view = memoryview(payload)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise MigrationBlocked("Scrittura attestazione incompleta.")
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(temporary, name, src_dir_fd=private["state_fd"],
                        dst_dir_fd=private["state_fd"], follow_symlinks=False)
            except FileExistsError as exc:
                raise MigrationBlocked("Attestazione backup già presente; non verrà sovrascritta.") from exc
            os.fsync(private["state_fd"])
            return {**proof, "attestation_path": str(pathlib.Path(private_root) / "state" / name),
                    "attestation_sha256": hashlib.sha256(payload).hexdigest()}
        finally:
            try:
                os.unlink(temporary, dir_fd=private["state_fd"])
                os.fsync(private["state_fd"])
            except FileNotFoundError:
                pass
    finally:
        if lock_fd is not None:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        backup_tool.close_private_directories(private)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="mostra i blocchi correnti senza accedere al server")
    local = commands.add_parser("verify-local", help="verifica commit e SHA sorgente locale, sola lettura")
    local.add_argument("--repository", default=str(REPOSITORY_ROOT),
                       help="checkout locale da verificare; non è un percorso pubblico")
    commands.add_parser("attest-backup", help="verifica backup ufficiale fissato e crea attestazione privata no-clobber")
    commands.add_parser("verify-backup", help="verifica read-only backup ufficiale fissato, senza creare attestazione")
    install = commands.add_parser("install", help="operazione pubblica disabilitata in questa versione")
    install.add_argument("--approve-operation", required=True,
                         help="conferma esatta stampata da status; non supera i blocchi tecnici")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            report = readiness_report()
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
            return 3
        if args.command == "verify-local":
            report = verify_local_candidate(args.repository)
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        if args.command == "attest-backup":
            result = attest_official_backup()
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        if args.command == "verify-backup":
            result = verify_official_backup()
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        validate_operation_approval(args.approve_operation)
        # Non aggiungere un ramo di scrittura finché ogni blocco non è stato
        # chiuso con prove server-side e una transizione di stato implementata.
        raise MigrationBlocked("Installazione pubblica disabilitata: prerequisiti IONOS non dimostrati.")
    except (MigrationBlocked, backup_tool.BackupError, baseline_tool.BaselineError,
            OSError, ValueError, UnicodeError) as exc:
        print(f"ERRORE: migrazione MU-plugin bloccata: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
