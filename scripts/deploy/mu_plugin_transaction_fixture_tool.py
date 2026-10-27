#!/usr/bin/env python3
"""Transazione fixture-only per la prima migrazione del MU-plugin.

Non contiene una CLI né accetta root pubbliche. Il solo workspace ammesso è
quello marcato e creato da transaction_fixture_tool.
"""

import copy
import hashlib
import json
import os
import pathlib
import re
import stat
import uuid

import release_state_tool as state_tool
import transaction_fixture_tool as tx

TARGET = state_tool.MU_MIGRATION_TARGET
SOURCE_COMMIT = state_tool.MU_MIGRATION_SOURCE_COMMIT
OLD_SHA = state_tool.MU_MIGRATION_OLD_SHA256
NEW_SHA = state_tool.MU_MIGRATION_NEW_SHA256
BACKUP_ID = state_tool.MU_MIGRATION_BACKUP_ID
BACKUP_MANIFEST_SHA = state_tool.MU_MIGRATION_BACKUP_MANIFEST_SHA256
TOKEN = object()
STAGE_FILE_NAMES = ("candidate.php", "original.php")
MIGRATION_OPERATION_ID_RE = re.compile(r"mu-migrate-[a-f0-9]{32}")


class MigrationFixtureError(Exception):
    """Rifiuto fail-closed della sola simulazione locale."""


class SimulatedCrash(BaseException):
    """Interruzione non recuperata dalla transazione, come SIGKILL/crash."""


def _validate_migration_workspace(workspace):
    try:
        return tx._validate_workspace(workspace)
    except tx.TransactionError as exc:
        raise MigrationFixtureError(f"Workspace fixture non autorizzato: {exc}") from exc


def operation_approval(workspace, fixture_backup_sha256):
    _validate_migration_workspace(workspace)
    if not re.fullmatch(r"[a-f0-9]{64}", str(fixture_backup_sha256)):
        raise MigrationFixtureError("Digest backup fixture non valido.")
    scope = hashlib.sha256(str(workspace.root).encode("utf-8")).hexdigest()[:16]
    return (f"MIGRATE-MU-FIXTURE {scope} {SOURCE_COMMIT} {OLD_SHA} {NEW_SHA} "
            f"{BACKUP_ID} {BACKUP_MANIFEST_SHA} {fixture_backup_sha256}")


def _read_target(workspace):
    root_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        raw, mode = tx._read_at(root_fd, TARGET, 1024 * 1024)
        return raw, mode
    finally:
        os.close(root_fd)


def _state_bytes(workspace):
    state_fd = os.open(workspace.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        raw, _ = tx._read_at(
            state_fd, state_tool.STATE_NAME, state_tool.MAX_STATE_BYTES,
            validator=tx._safe_private_state_relative,
        )
        return raw
    finally:
        os.close(state_fd)


def _write_state(workspace, current, migration, *, lifecycle):
    state = copy.deepcopy(current)
    rows = {row["path"]: dict(row) for row in state["reference_files"]}
    first_inventory = tx._current_records(workspace)
    second_inventory = tx._current_records(workspace)
    if tx._records_digest(first_inventory) != tx._records_digest(second_inventory):
        raise MigrationFixtureError("Inventario fixture variato durante le due verifiche fresche.")
    observed_target = second_inventory.get(TARGET)
    if observed_target is None:
        raise MigrationFixtureError("MU-plugin assente dall'inventario finale.")
    target_raw, target_mode = _read_target(workspace)
    target_row = rows.get(TARGET)
    if (target_row is None or hashlib.sha256(target_raw).hexdigest() not in (OLD_SHA, NEW_SHA)
            or observed_target["sha256"] != hashlib.sha256(target_raw).hexdigest()
            or observed_target["size"] != len(target_raw) or observed_target["mode"] != target_mode):
        raise MigrationFixtureError("Target live fuori dalle due versioni autorizzate.")
    target_row.update({"sha256": hashlib.sha256(target_raw).hexdigest(),
                       "size": len(target_raw), "mode": target_mode})
    ordered = [rows[path] for path in sorted(rows)]
    inv_files = [{key: row[key] for key in ("path", "sha256", "size", "mode")}
                 for row in ordered]
    observed_files = [{key: row[key] for key in ("path", "sha256", "size", "mode")}
                      for _, row in sorted(second_inventory.items())]
    if inv_files != observed_files:
        raise MigrationFixtureError("Il delta live contiene modifiche oltre il MU-plugin autorizzato.")
    state["reference_files"] = ordered
    state["inventory"]["files"] = inv_files
    inventory_sha = state_tool.inventory_digest_json(state["inventory"])
    state["inventory_sha256"] = inventory_sha
    state["release"]["inventory_sha256"] = inventory_sha
    state["verification"]["verified_at_utc"] = migration["verified_at_utc"]
    state["verification"]["fresh_inventory_count"] = 2
    state["verification"]["public_files"] = len(inv_files)
    state["timestamp_utc"] = migration["verified_at_utc"]
    migration["status"] = lifecycle
    state["component_migration"] = migration
    state["last_successful_operation"] = {
        "operation_id": migration["operation_id"],
        "kind": "mu-plugin-migration", "status": "verified",
        "completed_at_utc": migration["verified_at_utc"],
    }
    state.pop("state_sha256", None)
    state["state_sha256"] = state_tool.digest_json(state)
    state_tool.validate_state_document(state, state["initial_baseline"]["sha256"])
    state_fd = os.open(workspace.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before_raw = _state_bytes(workspace)
        before = {"sha256": hashlib.sha256(before_raw).hexdigest(), "size": len(before_raw), "mode": "600"}
        tx._replace_at(
            state_fd, state_tool.STATE_NAME, state_tool.json_bytes(state), 0o600, before,
            validator=tx._safe_private_state_relative,
        )
    finally:
        os.close(state_fd)
    return state


def _new_migration(workspace, current, backup_digest, operation_id, status):
    return {
        "schema_version": 1, "kind": "single-mu-plugin-migration", "status": status,
        "operation_id": operation_id, "target": TARGET, "source_commit_sha": SOURCE_COMMIT,
        "old_sha256": OLD_SHA, "new_sha256": NEW_SHA, "backup_id": BACKUP_ID,
        "backup_manifest_sha256": BACKUP_MANIFEST_SHA,
        "baseline_sha256": current["initial_baseline"]["sha256"],
        "previous_state_sha256": current["state_sha256"],
        "previous_inventory_sha256": current["inventory_sha256"],
        "verified_at_utc": state_tool.utc_now(),
    }


def _journal(workspace, operation_id, status, details):
    try:
        tx._write_journal_event(workspace, operation_id, status,
                                {"fixture_only": True, "operation_kind": "mu-plugin-migration",
                                 **details}, lock_already_held=True,
                                verified_commit=(status == "committed"))
    except (tx.TransactionError, state_tool.ReleaseStateError) as exc:
        raise MigrationFixtureError(f"Journal fixture non aggiornabile: {exc}") from exc


def _verify_inputs(workspace, candidate, candidate_commit, backup_id, backup_sha256,
                   official_backup_proof):
    _validate_migration_workspace(workspace)
    if candidate_commit != SOURCE_COMMIT or hashlib.sha256(candidate).hexdigest() != NEW_SHA:
        raise MigrationFixtureError("Commit o SHA candidato non autorizzato.")
    if backup_id != BACKUP_ID:
        raise MigrationFixtureError("Backup diverso da quello ufficiale autorizzato.")
    proof = official_backup_proof
    if (not isinstance(proof, dict) or proof.get("backup_id") != BACKUP_ID
            or proof.get("manifest_sha256") != BACKUP_MANIFEST_SHA
            or proof.get("baseline_sha256") != state_tool.INITIAL_BASELINE_SHA256
            or proof.get("verification") != "backup-tool-independent-digest-and-payload-verified"):
        raise MigrationFixtureError("Attestazione indipendente del backup ufficiale non valida.")
    try:
        current = tx._current_state(workspace)[2]
    except tx.TransactionError as exc:
        raise MigrationFixtureError(f"current-release fixture non valido: {exc}") from exc
    if current.get("component_migration") is not None:
        raise MigrationFixtureError("Migrazione già registrata; seconda esecuzione rifiutata.")
    raw, mode = _read_target(workspace)
    if hashlib.sha256(raw).hexdigest() != OLD_SHA:
        raise MigrationFixtureError("MU-plugin fixture diverso dall'hash originale autorizzato.")
    try:
        backup_records, backup_data, actual_backup_sha = tx._load_verified_backup(
            workspace, backup_id, backup_sha256)
    except tx.TransactionError as exc:
        raise MigrationFixtureError(f"Backup fixture non verificabile: {exc}") from exc
    if actual_backup_sha != backup_sha256:
        raise MigrationFixtureError("Digest effettivo backup fixture non corrispondente.")
    backup = backup_records.get(TARGET)
    if (not backup or backup["sha256"] != OLD_SHA or backup_data[TARGET] != raw
            or backup["mode"] != mode):
        raise MigrationFixtureError("Il backup fixture non conserva il MU-plugin originale e i permessi.")
    return current, raw, mode, backup_records, backup_data, actual_backup_sha


def _stage(workspace, operation_id, candidate, original, mode):
    _validate_migration_workspace(workspace)
    if not isinstance(operation_id, str) or not MIGRATION_OPERATION_ID_RE.fullmatch(operation_id):
        raise MigrationFixtureError("ID operazione staging non valido.")
    if not isinstance(candidate, bytes) or not isinstance(original, bytes):
        raise MigrationFixtureError("Contenuti staging non validi.")
    try:
        mode_bits = int(mode, 8) if isinstance(mode, str) and re.fullmatch(r"[0-7]{3,4}", mode) else mode
    except ValueError as exc:
        raise MigrationFixtureError("Permessi staging non validi.") from exc
    if not isinstance(mode_bits, int) or mode_bits < 0 or mode_bits & ~0o777:
        raise MigrationFixtureError("Permessi staging non validi.")
    stage = workspace.staging_dir / ("mu-migration-" + operation_id)
    staging_fd = os.open(workspace.staging_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            os.mkdir(stage.name, 0o700, dir_fd=staging_fd)
        except FileExistsError as exc:
            raise MigrationFixtureError("Directory staging migrazione già presente.") from exc
        stage_fd = os.open(stage.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=staging_fd)
        public_fd = None
        try:
            public_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            if os.fstat(stage_fd).st_dev != os.fstat(public_fd).st_dev:
                raise MigrationFixtureError("Staging e target non condividono filesystem.")
            _write_stage_file_at(stage_fd, "candidate.php", candidate, mode_bits)
            _write_stage_file_at(stage_fd, "original.php", original, mode_bits)
            os.fsync(stage_fd)
        finally:
            if public_fd is not None:
                os.close(public_fd)
            os.close(stage_fd)
    finally:
        os.close(staging_fd)
    return stage


def _safe_stage_name(name):
    if name not in STAGE_FILE_NAMES:
        raise MigrationFixtureError("Nome file staging non autorizzato.")
    return name


def _safe_stage_relative(path):
    return _safe_stage_name(path)


def _write_stage_file_at(stage_fd, name, data, mode):
    """Crea uno dei due file temporanei ammessi, solo nel descriptor dello staging."""
    name = _safe_stage_name(name)
    if not isinstance(data, bytes) or not isinstance(mode, int) or mode < 0 or mode & ~0o777:
        raise MigrationFixtureError("Contenuto o permessi file staging non validi.")
    directory_info = os.fstat(stage_fd)
    if not stat.S_ISDIR(directory_info.st_mode):
        raise MigrationFixtureError("Descriptor staging non riferito a una directory.")
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     mode, dir_fd=stage_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise MigrationFixtureError("File staging speciale o hard link sospetto.")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise MigrationFixtureError("Scrittura staging incompleta.")
            view = view[written:]
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.fsync(stage_fd)
    except OSError as exc:
        raise MigrationFixtureError(f"Creazione file staging non riuscita: {name}.") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _read_staged(workspace, operation_id, name):
    _safe_stage_name(name)
    if not isinstance(operation_id, str) or not MIGRATION_OPERATION_ID_RE.fullmatch(operation_id):
        raise MigrationFixtureError("ID operazione staging non valido.")
    stage = workspace.staging_dir / ("mu-migration-" + operation_id)
    if stage.parent != workspace.staging_dir:
        raise MigrationFixtureError("Percorso staging fuori allowlist.")
    staging_fd = os.open(workspace.staging_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        stage_fd = os.open(stage.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=staging_fd)
        try:
            raw, _ = tx._read_at(stage_fd, name, 1024 * 1024, validator=_safe_stage_relative)
            return raw
        finally:
            os.close(stage_fd)
    except (OSError, tx.TransactionError) as exc:
        raise MigrationFixtureError("File staging assente o non sicuro.") from exc
    finally:
        os.close(staging_fd)


def _atomic_target_replace(workspace, data, mode, expected_sha):
    public_fd = os.open(workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        actual, actual_mode = tx._read_at(public_fd, TARGET, 1024 * 1024)
        if hashlib.sha256(actual).hexdigest() != expected_sha:
            raise MigrationFixtureError("MU-plugin modificato da terzi; sostituzione rifiutata.")
        before = {"sha256": expected_sha, "size": len(actual), "mode": actual_mode,
                  "classification": "artifact"}
        tx._replace_at(public_fd, TARGET, data, int(mode, 8), before)
        os.fsync(public_fd)
    finally:
        os.close(public_fd)


def _commit(workspace, operation_id, backup_digest, plan_sha, *, rollback_of=None):
    _, _, state = tx._current_state(workspace)
    records = tx._current_records(workspace)
    final_records_digest = tx._records_digest(records)
    if state["inventory_sha256"] != state_tool.inventory_digest_json({
            "files": [{key: row[key] for key in ("path", "sha256", "size", "mode")}
                      for _, row in sorted(records.items())],
            "symlinks": state["inventory"]["symlinks"],
            "exclusion": state["inventory"]["exclusion"],
    }):
        raise MigrationFixtureError("current-release e inventario live non coincidono prima del terminale journal.")
    migration = state["component_migration"]
    details = {"plan_sha256": plan_sha,
               "final_inventory_sha256": state["inventory_sha256"],
               "final_records_sha256": final_records_digest,
               "backup_sha256": backup_digest,
               "new_state_sha256": state["state_sha256"],
               "operation_kind": "mu-plugin-migration", "target": TARGET,
               "source_commit_sha": SOURCE_COMMIT, "old_sha256": OLD_SHA,
               "new_sha256": NEW_SHA,
               "current_sha256": NEW_SHA if migration["status"] == "installed" else OLD_SHA,
               "backup_id": BACKUP_ID, "backup_manifest_sha256": BACKUP_MANIFEST_SHA,
               "baseline_sha256": migration["baseline_sha256"],
               "fixture_backup_sha256": backup_digest}
    if rollback_of:
        details["rollback_of"] = rollback_of
    terminal = "component_migrated" if migration["status"] == "installed" else "component_rolled_back"
    _journal(workspace, operation_id, terminal, details)
    return state["inventory_sha256"]


def _advance_recovery_journal(workspace, operation_id, details, *, through_health=False):
    events = [event for event in tx._load_fixture_journal(workspace)
              if event["operation_id"] == operation_id]
    last = events[-1]["status"]
    if last == "prepared":
        _journal(workspace, operation_id, "backup_verified", details)
        last = "backup_verified"
    if last == "backup_verified":
        _journal(workspace, operation_id, "publishing", details)
        last = "publishing"
    if not through_health:
        if last not in ("publishing", "files_verified", "health_verified"):
            raise MigrationFixtureError(f"Journal non pronto alla ripresa: {last}.")
        return
    if last == "publishing":
        expected_sha = OLD_SHA if details.get("operation_kind") == "mu-plugin-rollback" else NEW_SHA
        _journal(workspace, operation_id, "files_verified",
                 {**details, "installed_sha256": expected_sha})
        last = "files_verified"
    if last == "files_verified":
        _journal(workspace, operation_id, "health_verified",
                 {**details, "fixture_health": "recovery-content-check"})
    elif last != "health_verified":
        raise MigrationFixtureError(f"Journal in stato non recuperabile: {last}.")


def simulate_migration(workspace, *, candidate, candidate_commit, backup_id, backup_sha256,
                       official_backup_proof, confirmation, crash_at=None):
    """Installa il singolo file solo nell'albero public/ della fixture."""
    if os.name != "posix" or tx.fcntl is None:
        raise MigrationFixtureError("La transazione fixture richiede POSIX e flock.")
    current, old, mode, _, _, backup_digest = _verify_inputs(
        workspace, candidate, candidate_commit, backup_id, backup_sha256, official_backup_proof)
    if confirmation != operation_approval(workspace, backup_digest):
        raise MigrationFixtureError("Approvazione fixture specifica non valida.")
    operation_id = "mu-migrate-" + uuid.uuid4().hex
    stage = _stage(workspace, operation_id, candidate, old, mode)
    plan_sha = state_tool.digest_json({"kind": "mu-plugin-migration", "operation_id": operation_id,
                                       "target": TARGET, "old_sha256": OLD_SHA,
                                       "new_sha256": NEW_SHA, "backup_sha256": backup_digest,
                                       "current_state_sha256": current["state_sha256"]})
    locks_fd = os.open(workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = None
    started = False
    try:
        try:
            lock_fd = tx.baseline.acquire_baseline_lock(None, locks_fd)
        except tx.baseline.BaselineError as exc:
            raise MigrationFixtureError("Lock fixture occupato; transazione rifiutata.") from exc
        if tx._current_state(workspace)[2]["state_sha256"] != current["state_sha256"]:
            raise MigrationFixtureError("Stato current-release cambiato prima della migrazione.")
        try:
            locked_backup, locked_data, locked_digest = tx._load_verified_backup(
                workspace, backup_id, backup_digest)
        except tx.TransactionError as exc:
            raise MigrationFixtureError(f"Backup cambiato prima della transazione: {exc}") from exc
        if (locked_digest != backup_digest
                or locked_backup.get(TARGET, {}).get("sha256") != OLD_SHA
                or hashlib.sha256(locked_data.get(TARGET, b"")).hexdigest() != OLD_SHA):
            raise MigrationFixtureError("Backup non corrisponde più all'MU-plugin originale atteso.")
        live_before, _ = _read_target(workspace)
        if hashlib.sha256(live_before).hexdigest() != OLD_SHA:
            raise MigrationFixtureError("MU-plugin modificato mentre veniva acquisito il lock.")
        if crash_at == "before-journal":
            raise SimulatedCrash("crash before journal")
        details = {"operation_id": operation_id, "operation_kind": "mu-plugin-migration",
                   "target": TARGET, "plan_sha256": plan_sha,
                   "old_sha256": OLD_SHA, "new_sha256": NEW_SHA,
                   "source_commit_sha": SOURCE_COMMIT, "backup_id": BACKUP_ID,
                   "backup_manifest_sha256": BACKUP_MANIFEST_SHA,
                   "backup_sha256": backup_digest, "old_state_sha256": current["state_sha256"]}
        _journal(workspace, operation_id, "prepared", details)
        started = True
        if crash_at == "after-prepared":
            raise SimulatedCrash("crash after prepared")
        _journal(workspace, operation_id, "backup_verified", details)
        if crash_at == "after-backup":
            raise SimulatedCrash("crash after backup verification")
        _journal(workspace, operation_id, "publishing", details)
        if crash_at == "before-rename":
            raise SimulatedCrash("crash before rename")
        staged = _read_staged(workspace, operation_id, "candidate.php")
        if hashlib.sha256(staged).hexdigest() != NEW_SHA:
            raise MigrationFixtureError("Candidato staged alterato.")
        _atomic_target_replace(workspace, staged, mode, OLD_SHA)
        if crash_at == "after-rename":
            raise SimulatedCrash("crash after rename")
        installed, installed_mode = _read_target(workspace)
        if (hashlib.sha256(installed).hexdigest() != NEW_SHA or installed_mode != mode):
            raise MigrationFixtureError("Verifica hash o permessi del MU-plugin installato fallita.")
        _journal(workspace, operation_id, "files_verified",
                 {**details, "installed_sha256": NEW_SHA, "mode": mode})
        _journal(workspace, operation_id, "health_verified",
                 {**details, "fixture_health": "passed"})
        migration = _new_migration(workspace, current, backup_digest, operation_id, "installed")
        if crash_at == "during-state-update":
            raise SimulatedCrash("crash before atomic state replace")
        _write_state(workspace, current, migration, lifecycle="installed")
        if crash_at == "after-state-update" or crash_at == "before-terminal-journal":
            raise SimulatedCrash("crash after state update")
        _commit(workspace, operation_id, backup_digest, plan_sha)
        final_state = tx._current_state(workspace)[2]
        return {"status": "committed-fixture", "operation_id": operation_id,
                "final_inventory_sha256": final_state["inventory_sha256"],
                "final_records_sha256": tx._records_digest(tx._current_records(workspace))}
    except SimulatedCrash:
        raise
    except Exception as exc:
        # Lascia l'ultimo evento durevole non terminale: ogni tool che usa il
        # journal blocca nuove operazioni e recover_migration può riconciliare.
        if isinstance(exc, MigrationFixtureError):
            raise
        raise MigrationFixtureError(f"Migrazione fixture fallita: {exc}") from exc
    finally:
        if lock_fd is not None:
            tx.fcntl.flock(lock_fd, tx.fcntl.LOCK_UN)
            os.close(lock_fd)
        os.close(locks_fd)


def _recover_migration_locked(workspace, *, official_backup_proof):
    """Completa in modo idempotente un crash solo se live/state/staging concordano."""
    _validate_migration_workspace(workspace)
    events = tx._load_fixture_journal(workspace)
    if not events or events[-1]["status"] in ("committed", "component_migrated", "component_rolled_back"):
        raise MigrationFixtureError("Nessuna migrazione interrotta recuperabile.")
    op_id = events[-1]["operation_id"]
    operation = [event for event in events if event["operation_id"] == op_id]
    prepared = operation[0]
    details = prepared["details"]
    if (details.get("operation_kind") == "mu-plugin-rollback"):
        return _recover_rollback_locked(workspace, op_id, operation, official_backup_proof)
    if (details.get("operation_kind") != "mu-plugin-migration"
            or details.get("backup_id") != BACKUP_ID
            or details.get("backup_manifest_sha256") != BACKUP_MANIFEST_SHA
            or not isinstance(official_backup_proof, dict)
            or official_backup_proof.get("manifest_sha256") != BACKUP_MANIFEST_SHA):
        raise MigrationFixtureError("Journal o attestazione backup non autorizzati per recovery.")
    backup_records, backup_data, backup_digest = tx._load_verified_backup(
        workspace, BACKUP_ID, details.get("backup_sha256"))
    if backup_records.get(TARGET, {}).get("sha256") != OLD_SHA or hashlib.sha256(backup_data[TARGET]).hexdigest() != OLD_SHA:
        raise MigrationFixtureError("Backup fixture non contiene l'originale autorizzato.")
    raw, mode = _read_target(workspace)
    live_sha = hashlib.sha256(raw).hexdigest()
    _, _, current = tx._current_state(workspace)
    current_migration = current.get("component_migration")
    _advance_recovery_journal(workspace, op_id, details)
    if live_sha == OLD_SHA and current_migration is None:
        candidate = _read_staged(workspace, op_id, "candidate.php")
        if hashlib.sha256(candidate).hexdigest() != NEW_SHA:
            raise MigrationFixtureError("Candidato staged mancante o alterato; recovery manuale richiesta.")
        _atomic_target_replace(workspace, candidate, mode, OLD_SHA)
        raw, mode = _read_target(workspace)
        live_sha = hashlib.sha256(raw).hexdigest()
    if live_sha != NEW_SHA:
        raise MigrationFixtureError("Filesystem live fuori dagli stati recuperabili; intervento manuale richiesto.")
    _advance_recovery_journal(workspace, op_id, details, through_health=True)
    if current_migration is None:
        migration = _new_migration(workspace, current, backup_digest, op_id, "installed")
        _write_state(workspace, current, migration, lifecycle="installed")
    elif current_migration.get("operation_id") != op_id or current_migration.get("status") != "installed":
        raise MigrationFixtureError("current-release non corrisponde alla migrazione interrotta.")
    current_records = tx._current_records(workspace)
    if current_records.get(TARGET, {}).get("sha256") != NEW_SHA:
        raise MigrationFixtureError("Inventario live finale non registra il candidato autorizzato.")
    plan_sha = details["plan_sha256"]
    _commit(workspace, op_id, backup_digest, plan_sha)
    return {"status": "recovered-fixture", "operation_id": op_id}


def _recover_rollback_locked(workspace, op_id, operation, official_backup_proof):
    prepared = operation[0]["details"]
    if (prepared.get("backup_id") != BACKUP_ID
            or not isinstance(official_backup_proof, dict)
            or official_backup_proof.get("manifest_sha256") != BACKUP_MANIFEST_SHA):
        raise MigrationFixtureError("Journal rollback o attestazione ufficiale non validi.")
    backup_records, backup_data, backup_digest = tx._load_verified_backup(
        workspace, BACKUP_ID, prepared.get("backup_sha256"))
    if backup_records.get(TARGET, {}).get("sha256") != OLD_SHA:
        raise MigrationFixtureError("Backup rollback non conserva il file originale.")
    raw, mode = _read_target(workspace)
    live_sha = hashlib.sha256(raw).hexdigest()
    current = tx._current_state(workspace)[2]
    migration = current.get("component_migration")
    rollback_of = prepared.get("rollback_of")
    _advance_recovery_journal(workspace, op_id, prepared)
    if live_sha == NEW_SHA and migration and migration.get("status") == "installed":
        _atomic_target_replace(workspace, backup_data[TARGET], backup_records[TARGET]["mode"], NEW_SHA)
        raw, mode = _read_target(workspace)
        live_sha = hashlib.sha256(raw).hexdigest()
    if live_sha != OLD_SHA:
        raise MigrationFixtureError("Filesystem live ambiguo durante recovery rollback.")
    _advance_recovery_journal(workspace, op_id, prepared, through_health=True)
    if migration and migration.get("status") == "installed":
        if migration.get("operation_id") != rollback_of:
            raise MigrationFixtureError("Rollback non riferito alla migrazione attiva.")
        rollback_state = _new_migration(workspace, current, backup_digest, op_id, "rolled_back")
        _write_state(workspace, current, rollback_state, lifecycle="rolled_back")
    elif not migration or migration.get("operation_id") != op_id or migration.get("status") != "rolled_back":
        raise MigrationFixtureError("Stato current-release non riconciliabile col rollback.")
    _commit(workspace, op_id, backup_digest, prepared["plan_sha256"], rollback_of=rollback_of)
    return {"status": "rollback-recovered-fixture", "operation_id": op_id}


def recover_migration(workspace, *, official_backup_proof):
    _validate_migration_workspace(workspace)
    if os.name != "posix" or tx.fcntl is None:
        raise MigrationFixtureError("Recovery fixture richiede POSIX e flock.")
    locks_fd = os.open(workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            lock_fd = tx.baseline.acquire_baseline_lock(None, locks_fd)
        except tx.baseline.BaselineError as exc:
            raise MigrationFixtureError("Lock fixture occupato; recovery rifiutato.") from exc
        try:
            return _recover_migration_locked(workspace, official_backup_proof=official_backup_proof)
        finally:
            tx.fcntl.flock(lock_fd, tx.fcntl.LOCK_UN)
            os.close(lock_fd)
    finally:
        os.close(locks_fd)


def simulate_rollback(workspace, *, transaction_id, backup_id, backup_sha256,
                      official_backup_proof, confirmation, crash_at=None):
    """Ripristina solo la fixture dal backup verificato; rifiuta drift esterno."""
    _validate_migration_workspace(workspace)
    if os.name != "posix" or tx.fcntl is None:
        raise MigrationFixtureError("Rollback fixture richiede POSIX e flock.")
    events = tx._load_fixture_journal(workspace)
    committed = next((event for event in reversed(events)
                      if event["operation_id"] == transaction_id
                      and event["status"] == "component_migrated"), None)
    if committed is None:
        raise MigrationFixtureError("Migrazione originale non risulta conclusa nel journal.")
    if (backup_id != BACKUP_ID or backup_sha256 != committed["details"].get("backup_sha256")
            or confirmation != f"ROLLBACK-MU-FIXTURE {transaction_id} {backup_sha256}"):
        raise MigrationFixtureError("Autorizzazione o backup rollback non corrispondenti.")
    if (not isinstance(official_backup_proof, dict)
            or official_backup_proof.get("manifest_sha256") != BACKUP_MANIFEST_SHA):
        raise MigrationFixtureError("Attestazione backup ufficiale non valida.")
    current = tx._current_state(workspace)[2]
    try:
        state_tool.validate_component_migration_journal(current, events)
    except state_tool.ReleaseStateError as exc:
        raise MigrationFixtureError(f"Journal migration/current-release non coerenti: {exc}") from exc
    active_migration = current.get("component_migration")
    if (not active_migration or active_migration.get("operation_id") != transaction_id
            or active_migration.get("status") != "installed"):
        raise MigrationFixtureError("current-release non riconosce la migrazione richiesta come attiva.")
    backup_records, backup_data, digest = tx._load_verified_backup(workspace, backup_id, backup_sha256)
    current_records = tx._current_records(workspace)
    if tx._records_digest(current_records) != committed["details"].get("final_records_sha256"):
        raise MigrationFixtureError("Drift dopo migrazione: rollback bloccato senza sovrascrivere modifiche esterne.")
    if backup_records.get(TARGET, {}).get("sha256") != OLD_SHA:
        raise MigrationFixtureError("Backup non contiene il MU-plugin originale.")
    op_id = "mu-rollback-" + uuid.uuid4().hex
    plan_sha = state_tool.digest_json({"rollback_of": transaction_id, "backup_sha256": digest,
                                       "state_sha256": current["state_sha256"]})
    locks_fd = os.open(workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = None
    started = False
    try:
        try:
            lock_fd = tx.baseline.acquire_baseline_lock(None, locks_fd)
        except tx.baseline.BaselineError as exc:
            raise MigrationFixtureError("Lock fixture occupato; rollback rifiutato.") from exc
        locked_state = tx._current_state(workspace)[2]
        locked_records = tx._current_records(workspace)
        if (locked_state.get("state_sha256") != current.get("state_sha256")
                or tx._records_digest(locked_records) != committed["details"].get("final_records_sha256")):
            raise MigrationFixtureError("Stato o file live cambiati durante l'acquisizione del lock.")
        locked_events = tx._load_fixture_journal(workspace)
        try:
            state_tool.unresolved_operation(locked_events, allow_fixture_committed=True)
        except state_tool.ReleaseStateError as exc:
            raise MigrationFixtureError(f"Journal cambiato o operazione concorrente incompleta: {exc}") from exc
        try:
            state_tool.validate_component_migration_journal(locked_state, locked_events)
        except state_tool.ReleaseStateError as exc:
            raise MigrationFixtureError(f"Journal locked migration/current-release non coerenti: {exc}") from exc
        still_committed = next((event for event in reversed(locked_events)
                                if event["operation_id"] == transaction_id
                                and event["status"] == "component_migrated"), None)
        if (still_committed is None
                or still_committed["details"].get("final_inventory_sha256")
                != committed["details"].get("final_inventory_sha256")):
            raise MigrationFixtureError("Journal della migrazione è cambiato durante l'acquisizione del lock.")
        try:
            locked_backup, locked_data, locked_digest = tx._load_verified_backup(
                workspace, backup_id, backup_sha256)
        except tx.TransactionError as exc:
            raise MigrationFixtureError(f"Backup cambiato prima del rollback: {exc}") from exc
        if (locked_digest != digest or locked_backup.get(TARGET, {}).get("sha256") != OLD_SHA
                or hashlib.sha256(locked_data.get(TARGET, b"")).hexdigest() != OLD_SHA):
            raise MigrationFixtureError("Backup rollback non corrisponde più all'originale autorizzato.")
        details = {"operation_kind": "mu-plugin-rollback", "rollback_of": transaction_id,
                   "target": TARGET, "source_commit_sha": SOURCE_COMMIT,
                   "old_sha256": OLD_SHA, "new_sha256": NEW_SHA,
                   "backup_id": backup_id, "backup_manifest_sha256": BACKUP_MANIFEST_SHA,
                   "backup_sha256": digest, "old_state_sha256": current["state_sha256"],
                   "plan_sha256": plan_sha}
        _journal(workspace, op_id, "prepared", details); started = True
        _journal(workspace, op_id, "backup_verified", details)
        _journal(workspace, op_id, "publishing", details)
        if crash_at == "before-rename":
            raise SimulatedCrash("crash before rollback rename")
        _atomic_target_replace(workspace, backup_data[TARGET], backup_records[TARGET]["mode"], NEW_SHA)
        if crash_at == "after-rename":
            raise SimulatedCrash("crash after rollback rename")
        _journal(workspace, op_id, "files_verified", {**details, "installed_sha256": OLD_SHA})
        _journal(workspace, op_id, "health_verified", {**details, "fixture_health": "passed"})
        migration = _new_migration(workspace, current, digest, op_id, "rolled_back")
        _write_state(workspace, current, migration, lifecycle="rolled_back")
        if crash_at == "after-state-update":
            raise SimulatedCrash("crash after rollback state update")
        _commit(workspace, op_id, digest, plan_sha, rollback_of=transaction_id)
        return {"status": "rolled-back-fixture", "operation_id": op_id}
    finally:
        if lock_fd is not None:
            tx.fcntl.flock(lock_fd, tx.fcntl.LOCK_UN)
            os.close(lock_fd)
        os.close(locks_fd)
