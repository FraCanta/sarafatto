#!/usr/bin/env python3
"""Fixture offline per bootstrap e journal dello stato release privato."""

import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock

MODULE_PATH = pathlib.Path(__file__).with_name("release_state_tool.py")
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("release_state_tool", MODULE_PATH)
release_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_state)
baseline = release_state.baseline

SHA = "911d6a72ac0f624dc85b43d53b1c299968d683f6"
RUN_URL = "https://github.com/FraCanta/sarafatto/actions/runs/40106509533"
FLOCK_REQUIRED = os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1"
if FLOCK_REQUIRED and (release_state.fcntl is None or os.name != "posix"):
    raise RuntimeError("flock/POSIX assenti: i test critici current-release non possono essere saltati in CI.")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReleaseStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".release-state-test-", dir=MODULE_PATH.parents[2])
        self.root = pathlib.Path(self.temp.name)
        self.private = self.root / "private"
        self.public = self.root / "public" / "wp-content"
        self.state = self.private / "state"
        self.locks = self.private / "locks"
        for path in (self.public / "themes/sarafatto", self.public / "plugins/sarafatto-core",
                     self.public / "mu-plugins", self.state, self.locks):
            path.mkdir(parents=True, exist_ok=True)
        self.marker = self.private / baseline.MARKER
        self.marker.write_text(baseline.MARKER_VALUE + "\n", encoding="utf-8")
        self.files = {
            "themes/sarafatto/front-page.php": (b"theme", "artifact", "644"),
            "plugins/sarafatto-core/plugin.php": (b"plugin", "artifact", "644"),
            "mu-plugins/sarafatto-polylang-front-page-url.php": (b"mu", "artifact", "644"),
            "themes/sarafatto/assets/dist/assets/app-OldAb12.js": (b"old bundle", "retained-vite-bundle", "644"),
            "plugins/sarafatto-core/includes/home-hero.php.bak": (b"backup", "retained-backup", "600"),
        }
        for relative, (content, _, mode) in self.files.items():
            path = self.public / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(int(mode, 8))
        self.baseline_path = self.state / "baseline.json"
        self.write_baseline()
        self.approved_baseline_sha = sha(self.baseline_path.read_bytes())
        if os.name == "posix":
            for path in (self.private, self.state, self.locks):
                path.chmod(0o700)
            self.marker.chmod(0o600)
            self.baseline_path.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def inventory_text(self, changed=False, symlink=False, count=2):
        rows = [f"EXCLUDED\t{baseline.EXCLUDED}\t{count}\t0\n"]
        for path, (content, _, mode) in sorted(self.files.items()):
            if changed and path == "themes/sarafatto/front-page.php":
                content = b"changed"
            rows.append(f"FILE\t{sha(content)}\t{len(content)}\t{mode}\t{path}\n")
        if symlink:
            rows.append("SYMLINK\tthemes/sarafatto/link.php\t../../outside\n")
        rows.append("END\n")
        return "".join(rows)

    def write_baseline(self, commit=SHA):
        managed_files, accepted = [], []
        for path, (content, classification, mode) in sorted(self.files.items()):
            record = {"path": path, "sha256": sha(content), "size": len(content), "mode": mode}
            (managed_files if classification == "artifact" else accepted).append(
                record if classification == "artifact" else {**record, "classification": classification})
        document = {
            "schema_version": 1,
            "release": {"commit_sha": commit, "release_id": "bootstrap-" + commit[:12],
                        "github_actions_run": RUN_URL},
            "provenance": "bootstrap-content-match",
            "verification": {"status": "initialized-from-verified-content-match", "managed_symlinks": 0},
            "managed_files": managed_files,
            "accepted_extras": accepted,
        }
        self.baseline_path.write_bytes(release_state.json_bytes(document))
        if os.name == "posix":
            self.baseline_path.chmod(0o600)

    def bootstrap(self, reader=None):
        baseline_sha = self.approved_baseline_sha
        with mock.patch.object(release_state, "INITIAL_BASELINE_SHA256", baseline_sha):
            return release_state.bootstrap_current_release(
                private_root=self.private, expected_root=self.private,
                inventory_reader=reader or (lambda _sha: self.inventory_text()),
                confirmation="INITIALIZE-CURRENT " + baseline_sha,
            )

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_01_bootstrap_valido_e_non_sovrascrivibile(self):
        result = self.bootstrap()
        self.assertEqual(result["status"], "bootstrapped")
        path = self.state / release_state.STATE_NAME
        original = path.read_bytes()
        state = release_state.validate_state_document(json.loads(original))
        self.assertEqual(state["initial_baseline"]["commit_sha"], SHA)
        self.assertEqual(state["release"]["commit_sha"], SHA)
        self.assertEqual(len(state["reference_files"]), len(self.files))
        with self.assertRaises(release_state.ReleaseStateError):
            self.bootstrap()
        self.assertEqual(path.read_bytes(), original)

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_02_baseline_assente_blocca(self):
        self.baseline_path.unlink()
        with self.assertRaises(release_state.ReleaseStateError):
            self.bootstrap()
        self.assertFalse((self.state / release_state.STATE_NAME).exists())

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_03_baseline_alterata_blocca(self):
        self.baseline_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(release_state.ReleaseStateError):
            self.bootstrap()
        self.assertFalse((self.state / release_state.STATE_NAME).exists())

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_04_inventario_pubblico_modificato_blocca(self):
        with self.assertRaisesRegex(release_state.ReleaseStateError, "diverso dalla baseline"):
            self.bootstrap(lambda _sha: self.inventory_text(changed=True))
        self.assertFalse((self.state / release_state.STATE_NAME).exists())

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_05_commit_release_diverso_dalla_baseline_blocca(self):
        self.bootstrap()
        path = self.state / release_state.STATE_NAME
        state = json.loads(path.read_bytes())
        state["release"]["commit_sha"] = "0" * 40
        state.pop("state_sha256")
        state["state_sha256"] = release_state.digest_json(state)
        with self.assertRaises(release_state.ReleaseStateError):
            release_state.validate_state_document(state)

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "bootstrap dir_fd richiede Ubuntu")
    def test_05a_stato_committed_forgiato_con_digest_ricalcolato_blocca(self):
        self.bootstrap()
        path = self.state / release_state.STATE_NAME
        state = json.loads(path.read_bytes())
        state["last_successful_operation"]["status"] = "committed"
        state.pop("state_sha256")
        state["state_sha256"] = release_state.digest_json(state)
        with self.assertRaises(release_state.ReleaseStateError):
            release_state.validate_state_document(state)

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_06_symlink_pubblico_blocca(self):
        with self.assertRaisesRegex(release_state.ReleaseStateError, "Symlink"):
            self.bootstrap(lambda _sha: self.inventory_text(symlink=True))
        self.assertFalse((self.state / release_state.STATE_NAME).exists())

    def test_07_stato_malformato_blocca(self):
        with self.assertRaises(release_state.ReleaseStateError):
            release_state.validate_state_document({"schema_version": 1})

    def test_07a_journal_committed_bloccato_anche_senza_parser(self):
        event = {"operation_id": "txn-forged", "status": "committed"}
        with self.assertRaisesRegex(release_state.ReleaseStateError, "committed rifiutato"):
            release_state.unresolved_operation([event])

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "fixture POSIX obbligatoria su Ubuntu CI")
    def test_08_journal_interrotto_blocca_bootstrap(self):
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        locks_fd = os.open(self.locks, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            release_state.append_operation_event(state_fd, locks_fd, "txn-fixture", "prepared", {"fixture": True})
        finally:
            os.close(locks_fd)
            os.close(state_fd)
        with self.assertRaisesRegex(release_state.ReleaseStateError, "incompleta"):
            self.bootstrap()

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "fixture POSIX obbligatoria su Ubuntu CI")
    def test_09_lock_occupato_blocca_bootstrap(self):
        lock_fd = baseline.acquire_baseline_lock(self.locks)
        try:
            with self.assertRaises(release_state.ReleaseStateError):
                self.bootstrap()
        finally:
            release_state.fcntl.flock(lock_fd, release_state.fcntl.LOCK_UN)
            os.close(lock_fd)
        self.assertFalse((self.state / release_state.STATE_NAME).exists())

    @unittest.skipUnless(os.name == "posix", "symlink filesystem test obbligatorio su Ubuntu CI")
    def test_10_baseline_symlink_blocca(self):
        self.baseline_path.unlink()
        outside = self.root / "outside.json"
        outside.write_bytes(b"{}"); outside.chmod(0o600)
        self.baseline_path.symlink_to(outside)
        with self.assertRaises(release_state.ReleaseStateError):
            self.bootstrap()

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "fixture POSIX obbligatoria su Ubuntu CI")
    def test_11_scrittura_atomica_fallita_non_crea_stato(self):
        with mock.patch.object(release_state.os, "link", side_effect=OSError("link failure")):
            with self.assertRaises(release_state.ReleaseStateError):
                self.bootstrap()
        self.assertFalse((self.state / release_state.STATE_NAME).exists())
        self.assertEqual(list(self.state.glob(".current-release.tmp.*")), [])

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "fsync directory test POSIX obbligatorio su Ubuntu")
    def test_11a_interruzione_dopo_link_lascia_solo_stato_completo(self):
        real_fsync = os.fsync
        calls = 0

        def fail_directory_sync_once(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory fsync interrupted")
            return real_fsync(fd)

        with mock.patch.object(release_state.os, "fsync", side_effect=fail_directory_sync_once):
            with self.assertRaises(release_state.ReleaseStateError):
                self.bootstrap()
        path = self.state / release_state.STATE_NAME
        if path.exists():
            document = json.loads(path.read_bytes())
            self.assertEqual(document["verification"]["status"], "verified-current")
            self.assertEqual(document["verification"]["fresh_inventory_count"], 2)
            release_state.validate_state_document(document, self.approved_baseline_sha)
        self.assertEqual(list(self.state.glob(".current-release.tmp.*")), [])

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None, "bootstrap dir_fd richiede Ubuntu")
    def test_12_digest_state_manomesso_blocca(self):
        self.bootstrap()
        state = json.loads((self.state / release_state.STATE_NAME).read_bytes())
        state["release"]["release_id"] = "forged"
        with self.assertRaises(release_state.ReleaseStateError):
            release_state.validate_state_document(state)

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "journal POSIX obbligatorio su Ubuntu CI")
    def test_13_journal_rifiuta_commit_arbitrario(self):
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        locks_fd = os.open(self.locks, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            release_state.append_operation_event(state_fd, locks_fd, "txn-fixture", "prepared", {})
            with self.assertRaisesRegex(release_state.ReleaseStateError, "verificatore di deploy"):
                release_state.append_operation_event(state_fd, locks_fd, "txn-fixture", "committed", {"sha": SHA})
        finally:
            os.close(locks_fd)
            os.close(state_fd)

    @unittest.skipUnless(os.name == "posix", "fixture journal POSIX obbligatoria su Ubuntu CI")
    def test_14_journal_forgiato_committed_o_operazioni_intercalate_blocca(self):
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            committed = {"operation_id": "txn-forged", "status": "committed",
                         "timestamp_utc": "2026-01-01T00:00:00Z", "details": {},
                         "previous_event_sha256": "0" * 64}
            committed["event_sha256"] = release_state.digest_json(committed)
            raw = (json.dumps(committed, sort_keys=True, separators=(",", ":")) + "\n").encode()
            journal_path = self.state / release_state.JOURNAL_NAME
            journal_path.write_bytes(raw)
            journal_path.chmod(0o600)
            with self.assertRaisesRegex(release_state.ReleaseStateError, "committed rifiutato"):
                release_state.read_journal_at(state_fd)

            first = {"operation_id": "txn-one", "status": "prepared",
                     "timestamp_utc": "2026-01-01T00:00:00Z", "details": {},
                     "previous_event_sha256": "0" * 64}
            first["event_sha256"] = release_state.digest_json(first)
            second = {"operation_id": "txn-two", "status": "prepared",
                      "timestamp_utc": "2026-01-01T00:00:01Z", "details": {},
                      "previous_event_sha256": first["event_sha256"]}
            second["event_sha256"] = release_state.digest_json(second)
            raw = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
                           for row in (first, second))
            journal_path.write_bytes(raw)
            journal_path.chmod(0o600)
            with self.assertRaisesRegex(release_state.ReleaseStateError, "intercalate"):
                release_state.read_journal_at(state_fd)
        finally:
            os.close(state_fd)

    @unittest.skipUnless(os.name == "posix", "journal POSIX obbligatorio su Ubuntu CI")
    def test_15a_journal_vuoto_blocca_dopo_crash_su_creazione(self):
        (self.state / release_state.JOURNAL_NAME).write_bytes(b"")
        (self.state / release_state.JOURNAL_NAME).chmod(0o600)
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaisesRegex(release_state.ReleaseStateError, "vuoto"):
                release_state.read_journal_at(state_fd)
        finally:
            os.close(state_fd)

    @unittest.skipUnless(os.name == "posix" and release_state.fcntl is not None,
                         "hard link filesystem test obbligatorio su Ubuntu CI")
    def test_15b_journal_hardlink_non_scrive_fuori_area(self):
        outside = self.root / "outside-journal"
        outside.write_bytes(b"sentinel")
        journal = self.state / release_state.JOURNAL_NAME
        os.link(outside, journal)
        journal.chmod(0o600)
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        locks_fd = os.open(self.locks, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaisesRegex(release_state.ReleaseStateError, "hard link inatteso"):
                release_state.append_operation_event(state_fd, locks_fd, "txn-fixture", "prepared", {})
        finally:
            os.close(locks_fd)
            os.close(state_fd)
        self.assertEqual(outside.read_bytes(), b"sentinel")

    def test_15_digest_inventario_normalizza_solo_node_modules(self):
        base = {"files": [{"path": "themes/sarafatto/a.php", "sha256": "a" * 64,
                           "size": 1, "mode": "644"}], "symlinks": [],
                "exclusion": {"path": baseline.EXCLUDED + "/", "files": 4, "symlinks": 2}}
        changed_exclusion = json.loads(json.dumps(base))
        changed_exclusion["exclusion"].update({"files": 999, "symlinks": 777})
        changed_managed = json.loads(json.dumps(base))
        changed_managed["files"][0]["sha256"] = "b" * 64
        self.assertEqual(release_state.inventory_digest_json(base),
                         release_state.inventory_digest_json(changed_exclusion))
        self.assertNotEqual(release_state.inventory_digest_json(base),
                            release_state.inventory_digest_json(changed_managed))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseStateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if FLOCK_REQUIRED and result.skipped:
        print("ERRORE: la CI non può superare la validazione con test saltati.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(not result.wasSuccessful())
