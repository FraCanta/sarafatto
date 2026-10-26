#!/usr/bin/env python3
"""Controlli offline delle sole interfacce read-only dell'adattatore IONOS."""

import contextlib
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import production_adapter as adapter


class ProductionAdapterTests(unittest.TestCase):
    def test_componenti_autorizzati_e_file_fuori_perimetro(self):
        for path in (
            "themes/sarafatto/front-page.php",
            "plugins/sarafatto-core/includes/home-hero.php",
            "mu-plugins/sarafatto-polylang-front-page-url.php",
        ):
            with self.subTest(path=path):
                self.assertTrue(adapter.is_authorized_public_file(path))
        for path in (
            "wp-config.php",
            "uploads/private.jpg",
            "plugins/third-party/plugin.php",
            "themes/other/functions.php",
            "mu-plugins/other.php",
            "themes/sarafatto/node_modules/pkg.js",
            "themes/sarafatto/../../wp-config.php",
            "themes/sarafatto/\\escape.php",
        ):
            with self.subTest(path=path):
                self.assertFalse(adapter.is_authorized_public_file(path))

    def test_current_release_mancante_blocca_pubblicazione(self):
        status, blockers = adapter.current_state_readiness(None)
        self.assertEqual(status, "bootstrap-required")
        self.assertTrue(blockers)
        valid_stub = {"state_sha256": "a" * 64,
                      "verification": {"status": "verified-current"}}
        self.assertEqual(adapter.current_state_readiness(valid_stub),
                         ("verified-current", []))
        with self.assertRaises(adapter.ProductionAdapterError):
            adapter.current_state_readiness({"state_sha256": "a" * 64})

    def test_gate_pubblicazione_rimane_chiuso_anche_con_prove_simulate(self):
        current = {"state_sha256": "a" * 64,
                   "verification": {"status": "verified-current"}}
        gate = adapter.publication_readiness(
            current_state=current,
            traffic_barrier_verified=True,
            transaction_verifier_available=True,
            health_check_verified=True,
            fresh_backup_verified=True,
            explicit_environment_approval=True,
        )
        self.assertEqual(gate["status"], "blocked")
        self.assertFalse(gate["publish_allowed"])
        self.assertTrue(any("Publisher di produzione non implementato" in item
                            for item in gate["blockers"]))

    def test_gate_elenca_prerequisiti_reali_mancanti(self):
        gate = adapter.publication_readiness(current_state=None)
        self.assertEqual(gate["status"], "blocked")
        self.assertFalse(gate["publish_allowed"])
        self.assertGreaterEqual(len(gate["blockers"]), 6)

    def test_sha_autorizzato_completo_obbligatorio(self):
        self.assertEqual(adapter.validate_authorized_sha("a" * 40), "a" * 40)
        for value in ("a" * 39, "A" * 40, "a" * 41, "../main"):
            with self.subTest(value=value), self.assertRaises(adapter.ProductionAdapterError):
                adapter.validate_authorized_sha(value)

    def test_cli_non_esporta_bootstrap_deploy_o_rollback(self):
        commands = adapter.parser()._subparsers._group_actions[0].choices
        self.assertEqual(set(commands), {"inspect"})
        for command in ("bootstrap", "publish", "deploy", "rollback"):
            stderr = io.StringIO()
            with self.subTest(command=command), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    adapter.parser().parse_args([command])
            self.assertEqual(caught.exception.code, 2)

    def test_perimetro_produzione_fisso_e_scritture_pubbliche_disabilitate(self):
        self.assertEqual(adapter.PUBLIC_ROOT.as_posix(), "/home/www/public/wp-content")
        self.assertEqual(adapter.PRIVATE_ROOT.as_posix(), "/home/www/sarafatto-deploy")
        report = adapter.current_state_readiness(None)
        self.assertNotIn("publish", adapter.parser()._subparsers._group_actions[0].choices)
        self.assertEqual(report[0], "bootstrap-required")


if __name__ == "__main__":
    unittest.main(verbosity=2)
