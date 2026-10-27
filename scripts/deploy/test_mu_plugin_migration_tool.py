#!/usr/bin/env python3
"""Test offline dei gate per la prima migrazione del MU-plugin."""

import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import mu_plugin_migration_tool as migration

if str(pathlib.Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
import test_backup_tool as backup_fixture_module


class MuPluginMigrationTests(unittest.TestCase):
    def make_official_backup_fixture(self):
        fixture = backup_fixture_module.BackupToolTests("test_01_backup_valido_e_verificabile")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        created = fixture.create()
        return fixture, created, __import__("hashlib").sha256(b"mu bytes").hexdigest()

    def mock_git_for_source(self, source):
        def fake_run(command, **_kwargs):
            output = b"b" * 40 + b"\n" if "rev-parse" in command else source
            return subprocess.CompletedProcess(command, 0, output, b"")
        return fake_run

    def test_candidate_locale_ha_commit_e_digest_autorizzati(self):
        source = (migration.REPOSITORY_ROOT / migration.TARGET_RELATIVE).read_bytes()
        with mock.patch.object(migration.subprocess, "run", self.mock_git_for_source(source)):
            result = migration.verify_local_candidate()
        self.assertEqual(result["status"], "local-candidate-verified")
        self.assertEqual(result["source_commit"], migration.AUTHORIZED_REPOSITORY_SHA)
        self.assertEqual(result["repository_head"], "b" * 40)
        self.assertEqual(result["new_sha256"], migration.NEW_MU_PLUGIN_SHA256)

    def test_candidate_rifiuta_sha_sorgente_diverso(self):
        with tempfile.TemporaryDirectory(prefix="sf-mu-migration-", dir=pathlib.Path(__file__).parent) as temporary:
            root = pathlib.Path(temporary)
            target = root / migration.TARGET_RELATIVE
            target.parent.mkdir(parents=True)
            target.write_bytes(b"wrong source")
            committed_source = (migration.REPOSITORY_ROOT / migration.TARGET_RELATIVE).read_bytes()
            with mock.patch.object(migration.subprocess, "run",
                                   self.mock_git_for_source(committed_source)):
                with self.assertRaisesRegex(migration.MigrationBlocked, "Sorgente locale diversa"):
                    migration.verify_local_candidate(root)

    def test_approvazione_deve_corrispondere_esattamente_alloperazione(self):
        approval = migration.operation_approval()
        self.assertEqual(migration.validate_operation_approval(approval), approval)
        for changed in (approval + " extra", approval.replace(migration.OLD_MU_PLUGIN_SHA256, "0" * 64), "--force"):
            with self.subTest(changed=changed), self.assertRaises(migration.MigrationBlocked):
                migration.validate_operation_approval(changed)

    def test_install_rimane_disabilitato_anche_con_conferma_valida(self):
        report = migration.readiness_report()
        self.assertFalse(report["public_write_enabled"])
        self.assertEqual(report["status"], "blocked")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = migration.main(["install", "--approve-operation", migration.operation_approval()])
        self.assertEqual(code, 2)
        self.assertIn("Installazione pubblica disabilitata", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_blocchi_distinguono_atomicita_file_da_barriera_uniforme_e_stato(self):
        blockers = " ".join(migration.readiness_report()["blockers"])
        self.assertNotIn("dreni tutte le richieste", blockers)
        for required in ("digest indipendente", "current-release", "opcode", "worker", "Polylang"):
            with self.subTest(required=required):
                self.assertIn(required, blockers)

    def test_codice_polylang_restato_identico_tra_release_e_mu_plugin_candidato(self):
        old = subprocess.run(
            ["git", "-C", str(migration.REPOSITORY_ROOT), "show",
             "911d6a72ac0f624dc85b43d53b1c299968d683f6:" + migration.TARGET_RELATIVE],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
        new = (migration.REPOSITORY_ROOT / migration.TARGET_RELATIVE).read_bytes()
        marker = b"/** Apply Polylang's built-in language-root front page behavior"
        self.assertIn(marker, old)
        self.assertIn(marker, new)
        self.assertEqual(old[old.index(marker):], new[new.index(marker):])

    @unittest.skipUnless(os.name == "posix", "Semantica rename su inode aperto verificata in CI POSIX.")
    def test_sostituzione_atomica_file_singolo_non_produce_contenuto_parziale(self):
        with tempfile.TemporaryDirectory(prefix="sf-atomic-file-", dir=pathlib.Path(__file__).parent) as temporary:
            root = pathlib.Path(temporary)
            target = root / "mu-plugin.php"
            replacement = root / ".mu-plugin.candidate"
            old_bytes = b"<?php /* old complete source */\n" * 100
            new_bytes = b"<?php /* new complete source */\n" * 100
            target.write_bytes(old_bytes)
            with target.open("rb") as old_handle:
                replacement.write_bytes(new_bytes)
                os.replace(replacement, target)
                self.assertEqual(old_handle.read(), old_bytes)
            self.assertEqual(target.read_bytes(), new_bytes)

    @unittest.skipUnless(os.name == "posix", "Verifica backup con dir_fd richiede CI POSIX.")
    def test_backup_ufficiale_verifica_e_attesta_senza_sovrascrittura(self):
        fixture, created, old_sha = self.make_official_backup_fixture()
        with mock.patch.object(migration, "BASELINE_SHA256", fixture.baseline_sha), \
                mock.patch.object(migration, "OLD_MU_PLUGIN_SHA256", old_sha), \
                mock.patch.object(migration, "OFFICIAL_BACKUP_MANIFEST_SHA256", created["manifest_sha256"]), \
                mock.patch.object(migration, "OFFICIAL_BACKUP_ID", created["backup_id"]), \
                mock.patch.object(migration, "BACKUP_DIRECTORY_NAME", created["backup_id"]):
            verified = migration.verify_official_backup(
                private_root=fixture.private, expected_root=fixture.private)
            self.assertEqual(verified["backup_id"], created["backup_id"])
            self.assertIn("excludes database/uploads/third-party-plugins", verified["scope"])
            self.assertFalse((fixture.state / migration.BACKUP_ATTESTATION_NAME).exists())
            result = migration.attest_official_backup(
                private_root=fixture.private,
                expected_root=fixture.private)
            self.assertEqual(result["verification"],
                             "backup-tool-independent-digest-and-payload-verified")
            proof_path = fixture.state / migration.BACKUP_ATTESTATION_NAME
            self.assertTrue(proof_path.is_file())
            original = proof_path.read_bytes()
            with self.assertRaisesRegex(migration.MigrationBlocked, "già presente"):
                migration.attest_official_backup(
                    private_root=fixture.private,
                    expected_root=fixture.private)
            self.assertEqual(proof_path.read_bytes(), original)

    @unittest.skipUnless(os.name == "posix", "Verifica backup con dir_fd richiede CI POSIX.")
    def test_attestazione_rifiuta_digest_esterno_errato_senza_scrivere(self):
        fixture, created, old_sha = self.make_official_backup_fixture()
        with mock.patch.object(migration, "BASELINE_SHA256", fixture.baseline_sha), \
                mock.patch.object(migration, "OLD_MU_PLUGIN_SHA256", old_sha), \
                mock.patch.object(migration, "OFFICIAL_BACKUP_MANIFEST_SHA256", "0" * 64), \
                mock.patch.object(migration, "OFFICIAL_BACKUP_ID", created["backup_id"]), \
                mock.patch.object(migration, "BACKUP_DIRECTORY_NAME", created["backup_id"]):
            with self.assertRaisesRegex(migration.MigrationBlocked, "manifest|SHA-256"):
                migration.attest_official_backup(
                    private_root=fixture.private, expected_root=fixture.private)
        self.assertFalse((fixture.state / migration.BACKUP_ATTESTATION_NAME).exists())

    @unittest.skipUnless(os.name == "posix", "Verifica backup con dir_fd richiede CI POSIX.")
    def test_attestazione_rifiuta_backup_mancante_o_archivio_alterato(self):
        for alter_archive in (False, True):
            with self.subTest(alter_archive=alter_archive):
                fixture, created, old_sha = self.make_official_backup_fixture()
                if alter_archive:
                    archive = (fixture.backups / created["backup_id"] /
                               backup_fixture_module.backup_tool.BACKUP_ARCHIVE)
                    archive.write_bytes(archive.read_bytes() + b"tamper")
                else:
                    (fixture.backups / created["backup_id"]).rename(
                        fixture.backups / "held-away-from-fixed-path")
                with mock.patch.object(migration, "BASELINE_SHA256", fixture.baseline_sha), \
                        mock.patch.object(migration, "OLD_MU_PLUGIN_SHA256", old_sha), \
                        mock.patch.object(migration, "OFFICIAL_BACKUP_MANIFEST_SHA256", created["manifest_sha256"]), \
                        mock.patch.object(migration, "OFFICIAL_BACKUP_ID", created["backup_id"]), \
                        mock.patch.object(migration, "BACKUP_DIRECTORY_NAME", created["backup_id"]):
                    with self.assertRaises(migration.MigrationBlocked):
                        migration.attest_official_backup(
                            private_root=fixture.private,
                            expected_root=fixture.private)
                self.assertFalse((fixture.state / migration.BACKUP_ATTESTATION_NAME).exists())

    def test_sorgente_symlink_rifiutata(self):
        with tempfile.TemporaryDirectory(prefix="sf-mu-migration-", dir=pathlib.Path(__file__).parent) as temporary:
            root = pathlib.Path(temporary)
            target = root / migration.TARGET_RELATIVE
            target.parent.mkdir(parents=True)
            other = root / "source.php"
            other.write_bytes(b"source")
            try:
                os.symlink(other, target)
            except (OSError, NotImplementedError):
                if os.environ.get("SARAFATTO_REQUIRE_POSIX") == "1":
                    self.fail("CI POSIX deve poter creare symlink per eseguire il test no-follow.")
                self.skipTest("Symlink non disponibili su questo filesystem Windows.")
            with self.assertRaises(migration.MigrationBlocked):
                migration._read_local_source(target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
