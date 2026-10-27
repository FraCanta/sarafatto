#!/usr/bin/env python3
"""Fault-injection locale della migrazione singolo MU-plugin."""

import hashlib
import os
import pathlib
import subprocess
import sys
import threading
import unittest
from unittest import mock

import test_transaction_fixture_tool as base_tests

HERE = pathlib.Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import mu_plugin_migration_tool as migration_preflight
import mu_plugin_transaction_fixture_tool as migration
import transaction_fixture_tool as tx
import backup_tool

FLOCK_REQUIRED = os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1"
if FLOCK_REQUIRED and (tx.fcntl is None or os.name != "posix"):
    raise RuntimeError("La CI richiede POSIX/flock per le fixture di migrazione MU-plugin.")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class MuPluginMigrationStateSchemaTests(unittest.TestCase):
    def state_document(self):
        now = "2026-10-27T12:00:00Z"
        path = migration.TARGET
        inventory = {"files": [{"path": path, "sha256": migration.NEW_SHA,
                                  "size": 9000, "mode": "644"}],
                     "symlinks": [], "exclusion": {"path": "themes/sarafatto/node_modules/",
                                                          "files": 0, "symlinks": 0}}
        inventory_sha = migration.state_tool.inventory_digest_json(inventory)
        state = {
            "schema_version": 1,
            "initial_baseline": {"sha256": "a" * 64, "commit_sha": "911d6a72ac0f624dc85b43d53b1c299968d683f6",
                                 "release_id": "bootstrap-911d6a72ac0f"},
            "release": {"commit_sha": "911d6a72ac0f624dc85b43d53b1c299968d683f6",
                        "release_id": "bootstrap-911d6a72ac0f", "inventory_sha256": inventory_sha,
                        "inventory_tool_commit": "911d6a72ac0f624dc85b43d53b1c299968d683f6"},
            "inventory_sha256": inventory_sha, "inventory": inventory,
            "reference_files": [{"path": path, "sha256": migration.NEW_SHA, "size": 9000,
                                 "mode": "644", "classification": "artifact"}],
            "pre_deploy_backup": None, "candidate_release": None, "active_operation": None,
            "last_successful_operation": {"operation_id": "mu-migrate-0123456789abcdef0123456789abcdef",
                                           "kind": "mu-plugin-migration", "status": "verified",
                                           "completed_at_utc": now},
            "provenance": {"kind": "initial-baseline-content-match",
                           "baseline_provenance": "bootstrap-content-match"},
            "verification": {"status": "verified-current", "verified_at_utc": now,
                             "fresh_inventory_count": 2, "public_files": 1, "managed_symlinks": 0},
            "timestamp_utc": now,
            "component_migration": {
                "schema_version": 1, "kind": "single-mu-plugin-migration", "status": "installed",
                "operation_id": "mu-migrate-0123456789abcdef0123456789abcdef", "target": path,
                "source_commit_sha": migration.SOURCE_COMMIT, "old_sha256": migration.OLD_SHA,
                "new_sha256": migration.NEW_SHA, "backup_id": migration.BACKUP_ID,
                "backup_manifest_sha256": migration.BACKUP_MANIFEST_SHA,
                "baseline_sha256": "a" * 64, "previous_state_sha256": "b" * 64,
                "previous_inventory_sha256": "c" * 64,
                "verified_at_utc": now,
            },
        }
        state["state_sha256"] = migration.state_tool.digest_json(state)
        return state

    def test_state_migrato_valido_e_commit_app_restato_alla_baseline(self):
        state = self.state_document()
        migration.state_tool.validate_state_document(state, "a" * 64)
        self.assertEqual(state["release"]["commit_sha"], "911d6a72ac0f624dc85b43d53b1c299968d683f6")
        self.assertEqual(state["component_migration"]["source_commit_sha"], migration.SOURCE_COMMIT)

    def test_state_non_consente_promozione_arbitraria_alla_release_candidata(self):
        state = self.state_document()
        state["release"]["commit_sha"] = migration.SOURCE_COMMIT
        state.pop("state_sha256")
        state["state_sha256"] = migration.state_tool.digest_json(state)
        with self.assertRaises(migration.state_tool.ReleaseStateError):
            migration.state_tool.validate_state_document(state, "a" * 64)

    def test_state_rifiuta_delta_mu_non_autorizzato(self):
        state = self.state_document()
        state["component_migration"]["new_sha256"] = "0" * 64
        state.pop("state_sha256")
        state["state_sha256"] = migration.state_tool.digest_json(state)
        with self.assertRaises(migration.state_tool.ReleaseStateError):
            migration.state_tool.validate_state_document(state, "a" * 64)


@unittest.skipUnless(os.name == "posix" and tx.fcntl is not None,
                     "Fixture filesystem POSIX obbligatorie in CI Ubuntu.")
class MuPluginTransactionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.base = base_tests.TransactionFixtureTests("test_01_preflight_piano_completo_e_extra_conservati")
        self.base.setUp()
        self.addCleanup(self.base.tearDown)
        self.workspace = self.base.workspace
        self.target = migration.TARGET
        self.old = subprocess.run(
            ["git", "-C", str(HERE.parents[1]), "show",
             "911d6a72ac0f624dc85b43d53b1c299968d683f6:" + self.target],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
        self.candidate = (HERE.parents[1] / self.target).read_bytes()
        self.assertEqual(sha(self.old), migration.OLD_SHA)
        self.assertEqual(sha(self.candidate), migration.NEW_SHA)
        self.base.current[self.target] = (self.old, "artifact", "644")
        self.base._write_tree_file(self.workspace.public_root, self.target, self.old, "644")
        self.preserved_paths = []
        for index in range(168):
            path = f"themes/sarafatto/migration-fixture/preserved-{index:03d}.txt"
            content = f"preserve-{index}".encode()
            self.base.current[path] = (content, "artifact", "644")
            self.base._write_tree_file(self.workspace.public_root, path, content, "644")
            self.preserved_paths.append(path)
        self.base._write_state()
        self.backup = tx.create_verified_backup(self.workspace, migration.BACKUP_ID)
        self.proof = {
            "backup_id": migration.BACKUP_ID,
            "manifest_sha256": migration.BACKUP_MANIFEST_SHA,
            "baseline_sha256": migration_preflight.BASELINE_SHA256,
            "verification": "backup-tool-independent-digest-and-payload-verified",
        }

    def approve(self):
        return migration.operation_approval(self.workspace, self.backup["backup_sha256"])

    def run_migration(self, **overrides):
        args = {
            "candidate": self.candidate,
            "candidate_commit": migration.SOURCE_COMMIT,
            "backup_id": migration.BACKUP_ID,
            "backup_sha256": self.backup["backup_sha256"],
            "official_backup_proof": self.proof,
            "confirmation": self.approve(),
        }
        args.update(overrides)
        return migration.simulate_migration(self.workspace, **args)

    def test_00_staging_accetta_solo_file_interni_nel_descriptor_privato(self):
        operation_id = "mu-migrate-" + "1" * 32
        stage = migration._stage(self.workspace, operation_id, self.candidate, self.old, "644")
        self.assertEqual(migration._read_staged(self.workspace, operation_id, "candidate.php"),
                         self.candidate)
        self.assertEqual(migration._read_staged(self.workspace, operation_id, "original.php"), self.old)
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in ("../candidate.php", "baseline.json", "current-release.json", "other.php"):
                with self.subTest(name=name), self.assertRaises(migration.MigrationFixtureError):
                    migration._write_stage_file_at(stage_fd, name, b"not allowed", 0o600)
        finally:
            os.close(stage_fd)
        public_fd = os.open(self.workspace.public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaises(tx.TransactionError):
                tx._write_new_at(public_fd, "candidate.php", self.candidate, 0o644)
            with self.assertRaises(tx.TransactionError):
                tx._replace_at(public_fd, migration.state_tool.STATE_NAME, b"forbidden", 0o600, None)
        finally:
            os.close(public_fd)

    def test_00a_staging_rifiuta_symlink_e_hardlink(self):
        operation_id = "mu-migrate-" + "2" * 32
        stage = migration._stage(self.workspace, operation_id, self.candidate, self.old, "644")
        candidate = stage / "candidate.php"
        original = stage / "original.php"
        candidate.unlink()
        candidate.symlink_to(original)
        with self.assertRaises(migration.MigrationFixtureError):
            migration._read_staged(self.workspace, operation_id, "candidate.php")
        candidate.unlink()
        os.link(original, candidate)
        with self.assertRaises(migration.MigrationFixtureError):
            migration._read_staged(self.workspace, operation_id, "candidate.php")

    def test_01_migrazione_aggiorna_solo_mu_e_current_release(self):
        before = tx._current_records(self.workspace)
        baseline_before = (self.workspace.state_dir / "baseline.json").read_bytes()
        result = self.run_migration()
        after = tx._current_records(self.workspace)
        self.assertEqual(result["status"], "committed-fixture")
        self.assertEqual(set(before), set(after))
        self.assertEqual({p for p in before if before[p] != after[p]}, {self.target})
        self.assertEqual(len([p for p in self.preserved_paths if before[p] == after[p]]), 168)
        self.assertEqual((self.workspace.state_dir / "baseline.json").read_bytes(), baseline_before)
        self.assertEqual(after[self.target]["mode"], "644")
        state = tx._current_state(self.workspace)[2]
        self.assertEqual(state["release"]["commit_sha"], state["initial_baseline"]["commit_sha"])
        self.assertEqual(state["component_migration"]["source_commit_sha"], migration.SOURCE_COMMIT)
        self.assertEqual(state["component_migration"]["status"], "installed")
        events = tx._load_fixture_journal(self.workspace)
        tx.release_state.validate_component_migration_journal(state, events)
        tx.release_state.unresolved_operation(events, allow_fixture_committed=True)
        terminal = events[-1]
        self.assertEqual(terminal["status"], "component_migrated")
        self.assertEqual(terminal["operation_id"], result["operation_id"])
        self.assertEqual(terminal["details"]["final_inventory_sha256"], state["inventory_sha256"])
        self.assertEqual(terminal["details"]["final_records_sha256"],
                         tx._records_digest(tx._current_records(self.workspace)))
        self.assertEqual(result["final_inventory_sha256"], state["inventory_sha256"])
        altered_events = [dict(event, details=dict(event["details"])) for event in events]
        altered_events[-1]["details"]["final_records_sha256"] = "0" * 64
        with self.assertRaises(tx.release_state.ReleaseStateError):
            tx.release_state.validate_component_migration_journal(state, altered_events)
        state_fd = os.open(self.workspace.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            baseline_doc, baseline_sha, baseline_commit, baseline_expected = backup_tool.validate_backup_baseline(
                self.workspace.state_dir / "baseline.json", state["initial_baseline"]["sha256"])
            tool_commit, reference, state_reference = backup_tool.backup_reference(
                state_fd, baseline_doc, baseline_sha, baseline_commit, baseline_expected)
            self.assertEqual(reference[self.target]["sha256"], migration.NEW_SHA)
            self.assertEqual(state_reference["kind"], "current-release")
        finally:
            os.close(state_fd)

    def test_02_seconda_esecuzione_rifiutata(self):
        self.run_migration()
        with self.assertRaises(migration.MigrationFixtureError):
            self.run_migration()

    def test_03_sha_commit_backup_e_approvazione_errati_rifiutati(self):
        for args in (
            {"candidate": b"wrong"}, {"candidate_commit": "0" * 40},
            {"backup_sha256": "0" * 64}, {"confirmation": "--force"},
            {"official_backup_proof": {**self.proof, "manifest_sha256": "0" * 64}},
        ):
            with self.subTest(args=args), self.assertRaises(migration.MigrationFixtureError):
                self.run_migration(**args)
        self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.OLD_SHA)
        self.assertFalse((self.workspace.state_dir / tx.release_state.JOURNAL_NAME).exists())

    def test_04_drift_live_blocca_senza_sovrascrivere(self):
        target = self.workspace.public_root / self.target
        target.write_bytes(b"manual edit")
        with self.assertRaises(migration.MigrationFixtureError):
            self.run_migration()
        self.assertEqual(target.read_bytes(), b"manual edit")

    def test_05_lock_occupato_blocca_senza_scritture_pubbliche(self):
        locks_fd = os.open(self.workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lock_fd = tx.baseline.acquire_baseline_lock(None, locks_fd)
        try:
            with self.assertRaises(migration.MigrationFixtureError):
                self.run_migration()
            self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.OLD_SHA)
        finally:
            tx.fcntl.flock(lock_fd, tx.fcntl.LOCK_UN)
            os.close(lock_fd); os.close(locks_fd)

    def test_05a_due_transazioni_concorrenti_ne_completano_al_massimo_una(self):
        gate = threading.Barrier(3)
        results = []
        def worker():
            gate.wait()
            try:
                results.append(("ok", self.run_migration()))
            except migration.MigrationFixtureError as exc:
                results.append(("rejected", str(exc)))
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        gate.wait()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sum(kind == "ok" for kind, _ in results), 1)
        self.assertEqual(sum(kind == "rejected" for kind, _ in results), 1)
        terminal = [event for event in tx._load_fixture_journal(self.workspace)
                    if event["status"] == "component_migrated"]
        self.assertEqual(len(terminal), 1)

    def test_06_crash_in_punti_transazionali_rilevato_e_recuperabile(self):
        for point in ("after-prepared", "after-backup", "before-rename", "after-rename",
                      "during-state-update", "after-state-update", "before-terminal-journal"):
            with self.subTest(point=point):
                self.base.tearDown()
                self.setUp()
                with self.assertRaises(migration.SimulatedCrash):
                    self.run_migration(crash_at=point)
                events = tx._load_fixture_journal(self.workspace)
                self.assertNotIn(events[-1]["status"], ("committed", "component_migrated"))
                with self.assertRaises(tx.release_state.ReleaseStateError):
                    tx.release_state.unresolved_operation(events)
                result = migration.recover_migration(
                    self.workspace, official_backup_proof=self.proof)
                self.assertEqual(result["status"], "recovered-fixture")
                state = tx._current_state(self.workspace)[2]
                recovered_events = tx._load_fixture_journal(self.workspace)
                tx.release_state.validate_component_migration_journal(state, recovered_events)
                self.assertEqual(recovered_events[-1]["status"], "component_migrated")
                self.assertEqual(recovered_events[-1]["details"]["new_state_sha256"],
                                 state["state_sha256"])
                self.assertEqual(recovered_events[-1]["details"]["final_inventory_sha256"],
                                 state["inventory_sha256"])

    def test_07_crash_prima_del_journal_non_modifica_live(self):
        with self.assertRaises(migration.SimulatedCrash):
            self.run_migration(crash_at="before-journal")
        self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.OLD_SHA)
        self.assertEqual(tx._load_fixture_journal(self.workspace), [])

    def test_07a_errore_scrittura_current_release_recuperabile(self):
        real_replace = tx._replace_at
        calls = 0
        def fail_state_replace(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise tx.TransactionError("fault injection current-release")
            return real_replace(*args, **kwargs)
        with mock.patch.object(tx, "_replace_at", side_effect=fail_state_replace):
            with self.assertRaises(migration.MigrationFixtureError):
                self.run_migration()
        self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.NEW_SHA)
        result = migration.recover_migration(self.workspace, official_backup_proof=self.proof)
        self.assertEqual(result["status"], "recovered-fixture")

    def test_08_rollback_ripristina_solo_target_e_traccia_stato(self):
        published = self.run_migration()
        before = tx._current_records(self.workspace)
        result = migration.simulate_rollback(
            self.workspace, transaction_id=published["operation_id"],
            backup_id=migration.BACKUP_ID, backup_sha256=self.backup["backup_sha256"],
            official_backup_proof=self.proof,
            confirmation=f"ROLLBACK-MU-FIXTURE {published['operation_id']} {self.backup['backup_sha256']}",
        )
        after = tx._current_records(self.workspace)
        self.assertEqual(result["status"], "rolled-back-fixture")
        self.assertEqual({p for p in before if before[p] != after[p]}, {self.target})
        state = tx._current_state(self.workspace)[2]
        self.assertEqual(state["component_migration"]["status"], "rolled_back")
        events = tx._load_fixture_journal(self.workspace)
        tx.release_state.validate_component_migration_journal(state, events)
        self.assertEqual(events[-1]["status"], "component_rolled_back")
        self.assertEqual(events[-1]["details"]["rollback_of"], published["operation_id"])
        self.assertEqual(events[-1]["details"]["final_inventory_sha256"], state["inventory_sha256"])

    def test_09_rollback_drift_backup_alterato_e_path_arbitrario_bloccati(self):
        published = self.run_migration()
        target = self.workspace.public_root / self.target
        target.write_bytes(b"third party edit")
        with self.assertRaises(migration.MigrationFixtureError):
            migration.simulate_rollback(
                self.workspace, transaction_id=published["operation_id"], backup_id=migration.BACKUP_ID,
                backup_sha256=self.backup["backup_sha256"], official_backup_proof=self.proof,
                confirmation=f"ROLLBACK-MU-FIXTURE {published['operation_id']} {self.backup['backup_sha256']}",
            )
        with self.assertRaises(migration.MigrationFixtureError):
            migration.simulate_migration(
                pathlib.Path("C:/Users/Public"), candidate=self.candidate,
                candidate_commit=migration.SOURCE_COMMIT, backup_id=migration.BACKUP_ID,
                backup_sha256=self.backup["backup_sha256"], official_backup_proof=self.proof,
                confirmation=self.approve(),
            )

    def test_09a_backup_assente_o_alterato_blocca(self):
        backup_dir = self.workspace.backups_dir / migration.BACKUP_ID
        backup_file = backup_dir / "backup.json"
        original = backup_file.read_bytes()
        backup_file.write_bytes(original + b"tampered")
        with self.assertRaises(migration.MigrationFixtureError):
            self.run_migration()
        backup_file.unlink()
        with self.assertRaises(migration.MigrationFixtureError):
            self.run_migration()
        self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.OLD_SHA)

    def test_09b_backup_alterato_blocca_rollback(self):
        published = self.run_migration()
        backup_file = self.workspace.backups_dir / migration.BACKUP_ID / "backup.json"
        backup_file.write_bytes(backup_file.read_bytes() + b"tampered")
        with self.assertRaises(migration.MigrationFixtureError):
            migration.simulate_rollback(
                self.workspace, transaction_id=published["operation_id"],
                backup_id=migration.BACKUP_ID, backup_sha256=self.backup["backup_sha256"],
                official_backup_proof=self.proof,
                confirmation=f"ROLLBACK-MU-FIXTURE {published['operation_id']} {self.backup['backup_sha256']}",
            )
        self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.NEW_SHA)

    def test_10_rollback_interrotto_dopo_rename_recuperabile(self):
        published = self.run_migration()
        with self.assertRaises(migration.SimulatedCrash):
            migration.simulate_rollback(
                self.workspace, transaction_id=published["operation_id"], backup_id=migration.BACKUP_ID,
                backup_sha256=self.backup["backup_sha256"], official_backup_proof=self.proof,
                confirmation=f"ROLLBACK-MU-FIXTURE {published['operation_id']} {self.backup['backup_sha256']}",
                crash_at="after-rename",
            )
        result = migration.recover_migration(self.workspace, official_backup_proof=self.proof)
        self.assertEqual(result["status"], "rollback-recovered-fixture")
        self.assertEqual(sha((self.workspace.public_root / self.target).read_bytes()), migration.OLD_SHA)
        tx.release_state.validate_component_migration_journal(
            tx._current_state(self.workspace)[2], tx._load_fixture_journal(self.workspace))


if __name__ == "__main__":
    unittest.main(verbosity=2)
