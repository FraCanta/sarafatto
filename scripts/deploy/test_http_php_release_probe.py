#!/usr/bin/env python3
"""Test locali del harness HTTP/PHP; nessuna rete o path IONOS viene usato."""

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import http_php_release_probe as probe


POSIX_AVAILABLE = (
    os.name == "posix" and probe.fcntl is not None
    and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd
)


class HttpPhpReleaseProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and not POSIX_AVAILABLE:
            raise AssertionError("CI Ubuntu richiede POSIX, dir_fd, O_NOFOLLOW e flock.")

    def test_run_id_e_host_rifiutano_produzione_e_input_arbitrari(self):
        self.assertEqual(probe._validate_host("release-probe-2026.sara-fatto.it"),
                         "https://release-probe-2026.sara-fatto.it")
        for host in ("sara-fatto.it", "www.sara-fatto.it", "sarafatto.local",
                     "release-probe-x.sara-fatto.it:443", "release-probe-x.example.org",
                     "https://release-probe-x.sara-fatto.it/path"):
            with self.subTest(host=host), self.assertRaises(probe.ProbeError):
                probe._validate_host(host)
        for run_id in ("../../public", "ionos-http-probe-invalid", "http-probe-20260101T000000Z-aaaaaaaaaaaa"):
            with self.subTest(run_id=run_id), self.assertRaises(probe.ProbeError):
                probe._open_run(run_id)

    def test_cli_non_ha_root_publici_o_force(self):
        parser = probe.parser()
        self.assertEqual(probe.STAGING_ROOT.as_posix(), "/home/www/sarafatto-deploy/staging")
        for args in (["prepare", "--root", "/home/www/public"], ["stress", "--force"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                parser.parse_args(args)
            self.assertEqual(caught.exception.code, 2)

    def test_php_fissa_realpath_una_volta_e_non_usa_input_come_percorso(self):
        source = (probe.TEMPLATE_ROOT / "index.php").read_text(encoding="utf-8")
        self.assertIn("$releaseRoot = realpath($releasesRoot . '/current');", source)
        self.assertLess(source.index("$releaseRoot = realpath"), source.index("require $releaseRoot"))
        self.assertIn("$releaseRoot . '/theme/release.php'", source)
        self.assertIn("$releaseRoot . '/plugin/release.php'", source)
        self.assertIn("$releaseRoot . '/mu-plugin/release.php'", source)
        self.assertIn("$releaseRoot . '/assets/asset.txt'", source)
        self.assertIn("'probe_run_id' => $probeConfig['run_id']", source)
        self.assertNotIn("$_GET['path']", source)

    @unittest.skipUnless(POSIX_AVAILABLE, "preparazione fixture dir_fd richiede POSIX")
    def test_prepare_crea_solo_fixture_fake_e_auth_chiusa(self):
        with tempfile.TemporaryDirectory(prefix="sf-http-probe-") as temporary:
            staging = pathlib.Path(temporary)
            staging.chmod(0o700)
            staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                result = probe._prepare_run(staging_fd, staging)
            finally:
                os.close(staging_fd)
            run = pathlib.Path(result["run_path"])
            self.assertTrue(run.is_relative_to(staging))
            self.assertEqual(pathlib.Path(result["document_root"]).parent, run)
            self.assertFalse(result["auth_configured"])
            self.assertTrue((run / "docroot" / ".htaccess").is_file())
            self.assertTrue((run / "private" / ".htpasswd").is_file())
            self.assertEqual((run / "private" / ".htpasswd").stat().st_size, 0)
            self.assertEqual(os.readlink(run / "releases" / "current"), "release-A")
            for label in ("A", "B"):
                for component in probe.COMPONENTS:
                    self.assertTrue((run / "releases" / f"release-{label}" / component).is_dir())
            run_fd = os.open(run, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            releases_fd = os.open(run / "releases", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                probe._verify_fixture(result["run_id"], run_fd, releases_fd)
                (run / "docroot" / "unreviewed.txt").write_text("extra", encoding="utf-8")
                with self.assertRaises(probe.ProbeError):
                    probe._verify_fixture(result["run_id"], run_fd, releases_fd)
            finally:
                os.close(releases_fd)
                os.close(run_fd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
