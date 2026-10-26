#!/usr/bin/env python3
"""Test offline della simulazione release; non accede ai path IONOS."""

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ionos_release_barrier_probe as probe


POSIX_PROBE_AVAILABLE = (
    os.name == "posix" and probe.fcntl is not None
    and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd
)


class ReleaseBarrierProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and not POSIX_PROBE_AVAILABLE:
            raise AssertionError("CI Ubuntu richiede POSIX, dir_fd, O_NOFOLLOW e flock.")

    @unittest.skipUnless(POSIX_PROBE_AVAILABLE, "probe filesystem richiede POSIX e dir_fd")
    def test_confronta_strategie_e_interleaving_concorrenti(self):
        with tempfile.TemporaryDirectory(prefix="sf-release-barrier-") as temporary:
            root = pathlib.Path(temporary)
            root.chmod(0o700)
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                report = probe.run_probe(root_fd, root)
            finally:
                os.close(root_fd)

        self.assertTrue(report["strategies"]["in_place"]["mixed_state_observed"])
        self.assertTrue(report["strategies"]["component_symlinks"]["mixed_state_observed"])
        pointer = report["strategies"]["single_release_pointer"]
        self.assertGreater(pointer["requests"], 0)
        self.assertEqual(pointer["mixed_requests"], 0)
        self.assertEqual(pointer["reader_errors"], [])
        self.assertTrue(report["strategies"]["maintenance_only"]["mixed_state_observed"])

    @unittest.skipUnless(POSIX_PROBE_AVAILABLE, "probe filesystem richiede POSIX e dir_fd")
    def test_probe_primitivi_e_php_cli_dichiarano_limiti(self):
        with tempfile.TemporaryDirectory(prefix="sf-release-primitives-") as temporary:
            root = pathlib.Path(temporary)
            root.chmod(0o700)
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                result = probe._filesystem_primitives(root_fd, root)
            finally:
                os.close(root_fd)
        self.assertTrue(result["file_rename"])
        self.assertTrue(result["directory_rename"])
        self.assertTrue(result["private_mode_0600"])
        self.assertTrue(result["symlink_created"])
        self.assertTrue(result["fsync_file_and_directory"])
        self.assertTrue(result["flock_exclusive"])
        if result["php_cli"].get("available"):
            self.assertIn("PHP CLI soltanto", result["php_cli"]["note"])

    def test_cli_non_accetta_path_personalizzati_o_force(self):
        self.assertEqual(probe.STAGING_ROOT.as_posix(), "/home/www/sarafatto-deploy/staging")
        self.assertEqual(probe.PUBLIC_ROOT.as_posix(), "/home/www/public")
        parser = probe.parser()
        self.assertEqual(parser.parse_args(["diagnose"]).command, "diagnose")
        for args in (["diagnose", "--root", "/home/www/public"],
                     ["diagnose", "--force"], ["self-test"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                parser.parse_args(args)
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
