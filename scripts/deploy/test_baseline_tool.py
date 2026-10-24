#!/usr/bin/env python3
"""Fixture locali per confronto bootstrap e scrittura confinata della baseline."""
import hashlib
import importlib.util
import json
import pathlib
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import fcntl
except ImportError:
    fcntl = None

if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and fcntl is None:
    raise RuntimeError("flock mancante: i test critici baseline non possono essere saltati in CI.")

MODULE_PATH = pathlib.Path(__file__).with_name("baseline_tool.py")
SPEC = importlib.util.spec_from_file_location("baseline_tool", MODULE_PATH)
baseline_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline_tool)

SHA = "22c7fdd9970a2c8f1e9f3e3c0c0bb4cbadc44a66"
RUN_URL = "https://github.com/FraCanta/sarafatto/actions/runs/12345"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stat_mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class BaselineToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".baseline-test-", dir=MODULE_PATH.parents[2])
        self.root = pathlib.Path(self.temp.name)
        self.artifact = self.root / "artifact.tsv"
        self.remote = self.root / "remote.tsv"
        self.expected_path = "themes/sarafatto/front-page.php"
        self.old_bundle = "themes/sarafatto/assets/dist/assets/app-Ab12Cd34.js"
        self.backup = "themes/sarafatto/front-page.php.bak"
        self.write_artifact({self.expected_path: "same"})
        self.write_remote({
            self.expected_path: ("same", "644"),
            self.old_bundle: ("old bundle", "644"),
            self.backup: ("backup", "600"),
        })

    def tearDown(self):
        self.temp.cleanup()

    def write_artifact(self, rows):
        self.artifact.write_text(
            "".join(f"{digest(content)}\t{len(content)}\t{path}\n" for path, content in rows.items()),
            encoding="utf-8",
        )

    def write_remote(self, rows, symlinks=(), include_exclusion=True, include_end=True):
        lines = []
        if include_exclusion:
            lines.append("EXCLUDED\tthemes/sarafatto/node_modules\t2687\t15\n")
        for path, (content, mode) in rows.items():
            lines.append(f"FILE\t{digest(content)}\t{len(content)}\t{mode}\t{path}\n")
        for path, target in symlinks:
            lines.append(f"SYMLINK\t{path}\t{target}\n")
        if include_end:
            lines.append("END\n")
        self.remote.write_text("".join(lines), encoding="utf-8")

    def compare(self, accepted=None, release_sha=SHA, authorized_sha=SHA):
        return baseline_tool.compare(
            self.artifact, self.remote, release_sha, authorized_sha,
            "bootstrap-" + SHA[:12], RUN_URL, accepted or [],
        )

    def test_all_unchanged_with_reviewed_extras_creates_candidate(self):
        result = self.compare([self.old_bundle, self.backup])
        self.assertEqual(result["status"], "verified-awaiting-explicit-approval")
        self.assertEqual(result["matching"], [self.expected_path])
        candidate = result["candidate"]
        self.assertEqual(candidate["schema_version"], 1)
        self.assertEqual(candidate["provenance"], "bootstrap-content-match")
        self.assertIsNone(candidate["publication_date"])
        self.assertFalse(candidate["verification"]["deployment_performed_by_workflow"])
        self.assertEqual(candidate["accepted_extras"][0]["classification"], "retained-vite-bundle")
        self.assertEqual(candidate["accepted_extras"][1]["classification"], "retained-backup")

    def test_public_manual_modification_blocks(self):
        self.write_remote({self.expected_path: ("manual change", "644")})
        result = self.compare()
        self.assertEqual(result["conflicts"], [self.expected_path])
        self.assertIsNone(result["candidate"])

    def test_missing_file_blocks(self):
        self.write_remote({})
        result = self.compare()
        self.assertEqual(result["missing"], [self.expected_path])
        self.assertIsNone(result["candidate"])

    def test_unapproved_server_extra_blocks(self):
        result = self.compare()
        self.assertEqual(set(result["unapproved_extras"]), {self.old_bundle, self.backup})
        self.assertIn("file extra non approvati", result["blockers"])

    def test_node_modules_counts_are_excluded_not_reported_as_files(self):
        result = self.compare([self.old_bundle, self.backup])
        self.assertEqual(result["exclusion"]["files"], 2687)
        self.assertEqual(result["exclusion"]["symlinks"], 15)
        self.assertFalse(any("node_modules" in row["path"] for row in result["candidate"]["managed_files"]))

    def test_managed_dangerous_symlink_blocks(self):
        self.write_remote(
            {self.expected_path: ("same", "644")},
            symlinks=[("themes/sarafatto/dangerous-link", "/outside/target")],
        )
        result = self.compare()
        self.assertEqual(result["symlinks"][0]["target"], "/outside/target")
        self.assertIsNone(result["candidate"])

    def test_remote_inventory_must_be_complete_and_allowlisted(self):
        self.write_remote({self.expected_path: ("same", "644")}, include_exclusion=False)
        with self.assertRaises(baseline_tool.BaselineError):
            self.compare()
        self.write_remote({self.expected_path: ("same", "644")}, include_end=False)
        with self.assertRaises(baseline_tool.BaselineError):
            self.compare()
        self.write_remote({"themes/sarafatto/../../wp-config.php": ("secret", "644")})
        with self.assertRaises(baseline_tool.BaselineError):
            self.compare()

    def test_malformed_inventory_blocks(self):
        self.remote.write_text("FILE\tbad\tone\t644\tthemes/sarafatto/a.php\n", encoding="utf-8")
        with self.assertRaises(baseline_tool.BaselineError):
            self.compare()

    def test_commit_mismatch_blocks(self):
        with self.assertRaises(baseline_tool.BaselineError):
            self.compare(release_sha=SHA, authorized_sha="0" * 40)

    def test_inventory_script_must_match_authorized_commit(self):
        repo = self.root / "repo"
        script = repo / baseline_tool.INVENTORY_RELATIVE_PATH
        script.parent.mkdir(parents=True)
        expected = b"#!/usr/bin/env bash\nprintf 'END\\n'\n"
        script.write_bytes(expected)
        runner = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, expected, b"")
        self.assertEqual(baseline_tool.verified_inventory_script(SHA, repo, runner), expected)

        script.write_bytes(b"#!/usr/bin/env bash\nprintf 'tampered\\n'\n")
        with self.assertRaises(baseline_tool.BaselineError):
            baseline_tool.verified_inventory_script(SHA, repo, runner)

    def make_private_root(self, path):
        (path / "state").mkdir(parents=True)
        (path / "locks").mkdir()
        (path / baseline_tool.MARKER).write_text(baseline_tool.MARKER_VALUE + "\n", encoding="utf-8")
        if hasattr(pathlib.Path, "chmod"):
            if __import__("os").name == "posix":
                path.chmod(0o700)
                (path / "state").chmod(0o700)
                (path / "locks").chmod(0o700)
                (path / baseline_tool.MARKER).chmod(0o600)
        return path

    def approved_candidate(self):
        candidate = self.compare([self.old_bundle, self.backup])["candidate"]
        payload = (json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        return candidate, hashlib.sha256(payload).hexdigest()

    def initialize(self, candidate, approved_hash, provider=None, private_root=None):
        private_root = private_root or self.make_private_root(self.root / "private-init")
        fresh_read = provider or (lambda _sha: self.remote.read_text(encoding="utf-8"))
        with mock.patch.object(baseline_tool, "acquire_fresh_inventory", side_effect=fresh_read):
            return baseline_tool.initialize_baseline(
                candidate=candidate,
                candidate_digest=approved_hash,
                approved_candidate_digest=approved_hash,
                artifact_file=self.artifact,
                authorized_sha=SHA,
                confirmation="INITIALIZE " + SHA,
                private_root=private_root,
                expected_root=private_root,
            ), private_root

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_fresh_matching_inventory_initializes(self):
        candidate, approved_hash = self.approved_candidate()
        (result, final_report), private_root = self.initialize(candidate, approved_hash)
        target, written_hash = result
        self.assertTrue(target.is_file())
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), written_hash)
        self.assertEqual(final_report["status"], "verified-awaiting-explicit-approval")
        self.assertEqual(stat_mode(target), 0o600)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_file_changed_after_candidate_blocks_initialization(self):
        candidate, approved_hash = self.approved_candidate()
        self.write_remote({self.expected_path: ("changed after approval", "644"), self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600")})
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_deleted_file_after_candidate_blocks_initialization(self):
        candidate, approved_hash = self.approved_candidate()
        self.write_remote({self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600")})
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_new_extra_after_candidate_blocks_initialization(self):
        candidate, approved_hash = self.approved_candidate()
        self.write_remote({self.expected_path: ("same", "644"), self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600"), "themes/sarafatto/new-extra.txt": ("new", "644")})
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_new_symlink_after_candidate_blocks_initialization(self):
        candidate, approved_hash = self.approved_candidate()
        self.write_remote(
            {self.expected_path: ("same", "644"), self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600")},
            symlinks=[("themes/sarafatto/late-link", "/outside")],
        )
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_permission_change_after_candidate_blocks_initialization(self):
        candidate, approved_hash = self.approved_candidate()
        self.write_remote({self.expected_path: ("same", "600"), self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600")})
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_stale_inventory_file_is_not_an_initialize_input(self):
        candidate, approved_hash = self.approved_candidate()
        parser = baseline_tool.argument_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "initialize", "--candidate", str(self.root / "candidate.json"),
                "--artifact-inventory", str(self.artifact), "--remote-inventory", str(self.remote),
                "--authorized-sha", SHA, "--approved-candidate-sha256", approved_hash,
                "--confirm-initial-baseline", "INITIALIZE " + SHA,
            ])
        self.write_remote({self.expected_path: ("changed after snapshot", "644"), self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600")})
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_existing_baseline_is_not_overwritten(self):
        candidate, approved_hash = self.approved_candidate()
        private_root = self.make_private_root(self.root / "private-existing")
        target = private_root / "state" / "baseline.json"
        target.write_text("keep", encoding="utf-8")
        target.chmod(0o600)
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash, private_root=private_root)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_occupied_lock_blocks_initialization(self):
        candidate, approved_hash = self.approved_candidate()
        private_root = self.make_private_root(self.root / "private-locked")
        lock_path = private_root / "locks" / "baseline-initialization.lock"
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with self.assertRaises(baseline_tool.BaselineError):
                self.initialize(candidate, approved_hash, private_root=private_root)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_inventory_failure_does_not_write_baseline(self):
        candidate, approved_hash = self.approved_candidate()
        private_root = self.make_private_root(self.root / "private-failure")
        def fail_inventory(_authorized_sha):
            raise baseline_tool.BaselineError("fixture acquisition error")
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash, provider=fail_inventory, private_root=private_root)
        self.assertFalse((private_root / "state" / "baseline.json").exists())

    @unittest.skipUnless(fcntl is not None, "flock disponibile solo su POSIX; esecuzione coperta dal runner Ubuntu")
    def test_change_between_two_fresh_snapshots_blocks(self):
        candidate, approved_hash = self.approved_candidate()
        calls = 0
        def changing_provider(_authorized_sha):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.write_remote({self.expected_path: ("late change", "644"), self.old_bundle: ("old bundle", "644"), self.backup: ("backup", "600")})
            return self.remote.read_text(encoding="utf-8")
        private_root = self.make_private_root(self.root / "private-race")
        with self.assertRaises(baseline_tool.BaselineError):
            self.initialize(candidate, approved_hash, provider=changing_provider, private_root=private_root)
        self.assertFalse((private_root / "state" / "baseline.json").exists())

    def test_atomic_writer_only_accepts_private_root_and_does_not_overwrite(self):
        candidate = self.compare([self.old_bundle, self.backup])["candidate"]
        private_root = self.make_private_root(self.root / "private")
        outside = self.make_private_root(self.root / "outside")
        with self.assertRaises(baseline_tool.BaselineError):
            baseline_tool._atomic_write_initial_baseline(candidate, outside, private_root)
        self.assertFalse((outside / "state" / "baseline.json").exists())

        target, expected_hash = baseline_tool._atomic_write_initial_baseline(candidate, private_root, private_root)
        self.assertEqual(target, private_root / "state" / "baseline.json")
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), expected_hash)
        stored = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(stored["verification"]["status"], "initialized-from-verified-content-match")
        self.assertIn("baseline_initialized_at_utc", stored)
        with self.assertRaises(baseline_tool.BaselineError):
            baseline_tool._atomic_write_initial_baseline(candidate, private_root, private_root)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BaselineToolTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and result.skipped:
        print("ERRORE: la CI non può superare la validazione con test saltati.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(not result.wasSuccessful())
