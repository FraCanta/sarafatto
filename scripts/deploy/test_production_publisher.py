#!/usr/bin/env python3
"""Test offline del validatore artefatto di produzione (nessun filesystem IONOS)."""

import hashlib
import json
import os
import pathlib
import tarfile
import tempfile
import unittest
from unittest import mock

import production_publisher as publisher
import test_application_release_state as release_state_fixtures


class ProductionArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent)
        self.root = pathlib.Path(self.temp.name)
        self.package = self.root / "package"
        self.inventory = self.root / "inventory.tsv"
        self.archive = self.root / "release.tar.gz"
        self.provenance = self.root / "provenance.json"
        self.package.mkdir()
        self.contents = {
            "themes/sarafatto/functions.php": b"<?php // theme\n",
            "plugins/sarafatto-core/plugin.php": b"<?php // plugin\n",
            "mu-plugins/sarafatto-polylang-front-page-url.php": b"<?php // mu\n",
        }
        dist = self.package / "themes/sarafatto/assets/dist"
        dist.mkdir(parents=True)
        entries = {}
        for index, entry in enumerate(publisher.REQUIRED_ENTRIES):
            filename = f"assets/chunk-{index}.js"
            data = f"// bundle {index}\n".encode()
            self.contents[f"themes/sarafatto/assets/dist/{filename}"] = data
            target = dist / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            entries[entry] = {"file": filename, "isEntry": True}
        for relative, data in self.contents.items():
            target = self.package.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        manifest = dist / ".vite/manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest_raw = json.dumps(entries).encode("utf-8")
        manifest.write_bytes(manifest_raw)
        self.contents["themes/sarafatto/assets/dist/.vite/manifest.json"] = manifest_raw
        self._write_inventory()
        self._write_attestation()

    def tearDown(self):
        self.temp.cleanup()

    def _write_inventory(self):
        rows = []
        for path in sorted(self.contents):
            data = self.contents[path]
            rows.append(f"{hashlib.sha256(data).hexdigest()}\t{len(data)}\t{path}")
        self.inventory.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def _write_attestation(self):
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(self.package, arcname="sarafatto-release")
            archive.add(self.inventory, arcname="sarafatto-inventory.tsv")
        publisher.create_provenance(self.inventory, self.archive, self.provenance,
                                    "a" * 40, "12345", "refs/heads/main")

    def _verify(self, release_sha="a" * 40, run_id="12345"):
        return publisher.verify_artifact(
            self.package, self.inventory, release_sha,
            provenance_path=self.provenance, archive_path=self.archive,
            expected_run_id=run_id)

    def _fake_wp_a(self, root):
        content = {
            "themes/sarafatto/functions.php": b"A theme\n",
            "plugins/sarafatto-core/plugin.php": b"A plugin\n",
            "mu-plugins/sarafatto-polylang-front-page-url.php": b"A mu\n",
            "plugins/sarafatto-core/includes/home-hero.php.bak": b"approved backup\n",
            "themes/sarafatto/obsolete.php": b"remove only by approval\n",
        }
        for index in range(8):
            content[f"themes/sarafatto/assets/dist/assets/app-old{index:02d}.js"] = f"old {index}\n".encode()
        for path, data in content.items():
            target = root.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        dist = root / "themes/sarafatto/assets/dist"
        old_manifest = {entry: {"file": f"assets/app-old{index:02d}.js", "isEntry": True}
                        for index, entry in enumerate(publisher.REQUIRED_ENTRIES)}
        manifest = dist / ".vite/manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(old_manifest), encoding="utf-8")
        content["themes/sarafatto/assets/dist/.vite/manifest.json"] = manifest.read_bytes()
        return content

    @staticmethod
    def _rows_from_content(content, classifications=None):
        classifications = classifications or {}
        return [{"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                 "mode": "644", "classification": classifications.get(path, "artifact")}
                for path, data in sorted(content.items())]

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Il writer dir_fd/O_NOFOLLOW si valida obbligatoriamente su Ubuntu CI.")
    def test_filesystem_publish_rollback_e_rimozione_esplicitamente_approvata(self):
        target = self.root / "wp-content"
        target.mkdir()
        parent_content = self._fake_wp_a(target)
        backup = self.root / "verified-backup-restored"
        import shutil
        shutil.copytree(target, backup)
        extra_classes = {
            **{f"themes/sarafatto/assets/dist/assets/app-old{index:02d}.js": "retained-vite-bundle"
               for index in range(8)},
            "plugins/sarafatto-core/includes/home-hero.php.bak": "retained-backup",
        }
        parent_rows = self._rows_from_content(parent_content, extra_classes)
        live_before = publisher.inventory_target_tree(target)
        self.assertEqual(set(live_before), set(parent_content))

        artifact_rows = publisher._walk_package(self.package)
        candidate_content = dict(self.contents)
        candidate_content.update({path: parent_content[path] for path in extra_classes})
        candidate_rows = self._rows_from_content(candidate_content, extra_classes)
        removed_sha = hashlib.sha256(parent_content["themes/sarafatto/obsolete.php"]).hexdigest()
        approval = [{"path": "themes/sarafatto/obsolete.php", "sha256": removed_sha}]

        published = publisher.apply_file_snapshot(
            self.package, target, parent_rows, candidate_rows, approved_removals=approval)
        self.assertTrue(published["public_writes_performed"])
        self.assertFalse((target / "themes/sarafatto/obsolete.php").exists())
        for path, data in self.contents.items():
            self.assertEqual(target.joinpath(*path.split("/")).read_bytes(), data)
        for path in extra_classes:
            self.assertEqual(target.joinpath(*path.split("/")).read_bytes(), parent_content[path])

        candidate_current = self._rows_from_content(candidate_content, extra_classes)
        rolled_back = publisher.rollback_file_snapshot(
            backup, target, candidate_current, parent_rows)
        self.assertEqual(rolled_back["inventory"], live_before)
        for path, data in parent_content.items():
            self.assertEqual(target.joinpath(*path.split("/")).read_bytes(), data)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Il writer dir_fd/O_NOFOLLOW si valida obbligatoriamente su Ubuntu CI.")
    def test_filesystem_publish_interrotto_recovery_verifica_hash_e_preserva_extra(self):
        target = self.root / "wp-content-recovery"
        target.mkdir()
        parent_content = self._fake_wp_a(target)
        backup = self.root / "verified-backup-recovery"
        import shutil
        shutil.copytree(target, backup)
        extra_classes = {
            **{f"themes/sarafatto/assets/dist/assets/app-old{index:02d}.js": "retained-vite-bundle"
               for index in range(8)},
            "plugins/sarafatto-core/includes/home-hero.php.bak": "retained-backup",
        }
        parent_rows = self._rows_from_content(parent_content, extra_classes)
        candidate_content = dict(self.contents)
        candidate_content.update({path: parent_content[path] for path in extra_classes})
        candidate_rows = self._rows_from_content(candidate_content, extra_classes)
        counter = {"writes": 0}

        def interrupt(event, path, count):
            counter["writes"] = count
            if count == 2:
                raise RuntimeError("fault injection after second file")

        with self.assertRaisesRegex(RuntimeError, "fault injection"):
            publisher.apply_file_snapshot(self.package, target, parent_rows, candidate_rows,
                                           fault_hook=interrupt)
        self.assertEqual(counter["writes"], 2)
        before_recovery = publisher.inventory_target_tree(target)
        self.assertNotEqual(before_recovery, {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                                               for row in parent_rows})
        recovered = publisher.recover_file_snapshot(backup, target, parent_rows, candidate_rows)
        self.assertEqual(recovered["inventory"], publisher.inventory_target_tree(backup))
        for path in extra_classes:
            self.assertEqual(target.joinpath(*path.split("/")).read_bytes(), parent_content[path])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Il writer dir_fd/O_NOFOLLOW si valida obbligatoriamente su Ubuntu CI.")
    def test_filesystem_publish_health_fallito_rollback_automatico(self):
        target = self.root / "wp-content-health"
        target.mkdir()
        parent_content = self._fake_wp_a(target)
        backup = self.root / "verified-backup-health"
        import shutil
        shutil.copytree(target, backup)
        extra_classes = {
            **{f"themes/sarafatto/assets/dist/assets/app-old{index:02d}.js": "retained-vite-bundle"
               for index in range(8)},
            "plugins/sarafatto-core/includes/home-hero.php.bak": "retained-backup",
        }
        parent_rows = self._rows_from_content(parent_content, extra_classes)
        candidate_content = dict(self.contents)
        candidate_content.update({path: parent_content[path] for path in extra_classes})
        candidate_rows = self._rows_from_content(candidate_content, extra_classes)
        removed_sha = hashlib.sha256(parent_content["themes/sarafatto/obsolete.php"]).hexdigest()
        with self.assertRaisesRegex(publisher.PublisherError, "rollback al parent completato"):
            publisher.publish_filesystem_snapshot(
                self.package, target, parent_rows, candidate_rows,
                approved_removals=[{"path": "themes/sarafatto/obsolete.php", "sha256": removed_sha}],
                health_check=lambda: {"status": "unhealthy"}, recovery_root=backup)
        self.assertEqual(publisher.inventory_target_tree(target), publisher.inventory_target_tree(backup))

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Il writer dir_fd/O_NOFOLLOW si valida obbligatoriamente su Ubuntu CI.")
    def test_filesystem_writer_rifiuta_hash_estranei_e_rimozioni_non_approvate(self):
        target = self.root / "wp-content-reject"
        target.mkdir()
        parent_content = self._fake_wp_a(target)
        parent_rows = self._rows_from_content(parent_content)
        candidate_rows = self._rows_from_content(self.contents)
        with self.assertRaisesRegex(publisher.PublisherError, "Rimozioni non approvate"):
            publisher.apply_file_snapshot(self.package, target, parent_rows, candidate_rows)
        target.joinpath("themes/sarafatto/functions.php").write_bytes(b"external edit")
        with self.assertRaisesRegex(publisher.PublisherError, "Inventario target cambiato"):
            publisher.apply_file_snapshot(self.package, target, parent_rows, candidate_rows,
                                          approved_removals=[])

    def test_artifact_ammesso_solo_con_manifest_e_inventario_coerenti(self):
        records = self._verify()
        self.assertEqual(set(records), set(self.contents))

    def test_artifact_alterato_dopo_inventario_rifiutato(self):
        target = self.package / "themes/sarafatto/functions.php"
        target.write_bytes(b"alterato")
        with self.assertRaisesRegex(publisher.PublisherError, "diverso dall'inventario"):
            self._verify()

    def test_file_fuori_allowlist_rifiutato(self):
        (self.package / "wp-config.php").write_text("segreto", encoding="utf-8")
        with self.assertRaisesRegex(publisher.PublisherError, "fuori perimetro"):
            self._verify()

    def test_entry_vite_mancante_rifiutata(self):
        manifest = self.package / "themes/sarafatto/assets/dist/.vite/manifest.json"
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        del doc[publisher.REQUIRED_ENTRIES[0]]
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(publisher.PublisherError, "Entry Vite mancante"):
            self._verify()

    def test_sha_incompleto_rifiutato(self):
        with self.assertRaisesRegex(publisher.PublisherError, "SHA deve essere completo"):
            self._verify("deadbeef")

    def test_archivio_alterato_o_non_coerente_rifiutato(self):
        self.archive.write_bytes(b"not a tar.gz")
        with self.assertRaisesRegex(publisher.PublisherError, "Digest provenance"):
            self._verify()

    def test_run_id_diverso_dalla_provenance_rifiutato(self):
        with self.assertRaisesRegex(publisher.PublisherError, "(?i)provenance"):
            self._verify(run_id="99999")

    def test_provenance_esclusiva_non_sovrascrive_file_esistente(self):
        with self.assertRaisesRegex(publisher.PublisherError, "esclusiva"):
            publisher.create_provenance(
                self.inventory, self.archive, self.provenance,
                "a" * 40, "12345", "refs/heads/main")

    def test_comando_provenance_vincolato_al_run_e_runner_temp(self):
        output = self.root / "ci-provenance.json"
        args = type("Args", (), {
            "release_sha": "a" * 40, "ref": "refs/heads/main", "run_id": "12345",
            "inventory": str(self.inventory), "archive": str(self.archive),
            "output": str(output),
        })()
        environment = {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": publisher.GITHUB_REPOSITORY,
            "GITHUB_SHA": args.release_sha, "GITHUB_REF": args.ref,
            "GITHUB_RUN_ID": args.run_id, "RUNNER_TEMP": str(self.root),
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            publisher._require_ci_provenance_context(args)
        args.output = str(self.root.parent / "public-output.json")
        with mock.patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesRegex(publisher.PublisherError, "RUNNER_TEMP"):
                publisher._require_ci_provenance_context(args)

    def test_archive_digest_valido_ma_contenuti_diversi_rifiutato(self):
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(self.inventory, arcname="sarafatto-inventory.tsv")
        publisher.create_provenance(self.inventory, self.archive, self.root / "new-provenance.json",
                                    "a" * 40, "12345", "refs/heads/main")
        with self.assertRaisesRegex(publisher.PublisherError, "Archivio incompleto"):
            publisher.verify_artifact(
                self.package, self.inventory, "a" * 40,
                provenance_path=self.root / "new-provenance.json", archive_path=self.archive,
                expected_run_id="12345")

    def test_archivio_con_membro_path_traversal_rifiutato(self):
        with tarfile.open(self.archive, "w:gz") as archive:
            info = tarfile.TarInfo("sarafatto-release/../../escape.php")
            data = b"<?php"
            info.size = len(data)
            import io
            archive.addfile(info, io.BytesIO(data))
            archive.add(self.inventory, arcname="sarafatto-inventory.tsv")
        publisher.create_provenance(self.inventory, self.archive, self.root / "bad-provenance.json",
                                    "a" * 40, "12345", "refs/heads/main")
        with self.assertRaisesRegex(publisher.PublisherError, "archivio"):
            publisher.verify_artifact(
                self.package, self.inventory, "a" * 40,
                provenance_path=self.root / "bad-provenance.json", archive_path=self.archive,
                expected_run_id="12345")

    def test_piano_conserva_bundle_obsoleti_approvati_e_blocca_extra_sconosciuti(self):
        candidate = {"themes/sarafatto/functions.php": {
            "sha256": "a" * 64, "size": 1, "mode": "644"}}
        live = {
            **candidate,
            "themes/sarafatto/assets/dist/assets/app-oldhash.js": {
                "sha256": "b" * 64, "size": 1, "mode": "644"},
            "themes/sarafatto/manual.php": {
                "sha256": "c" * 64, "size": 1, "mode": "644"},
        }
        reference = {
            "themes/sarafatto/assets/dist/assets/app-oldhash.js": {
                "classification": "retained-vite-bundle"},
        }
        changes, retained, blockers = publisher.plan_inventory_changes(candidate, live, reference)
        self.assertEqual(changes, [{
            "path": "themes/sarafatto/manual.php",
            "action": "removal-requires-explicit-authorization",
        }])
        self.assertEqual(retained, ["themes/sarafatto/assets/dist/assets/app-oldhash.js"])
        self.assertEqual(blockers, ["Rimozione non autorizzata: themes/sarafatto/manual.php."])

    def test_piano_release_state_preserva_i_nove_extra_e_rifiuta_delta_non_approvati(self):
        current = release_state_fixtures._state_a()
        artifact = {}
        for row in current["reference_files"]:
            if row["classification"] == "artifact":
                artifact[row["path"]] = {key: row[key] for key in ("sha256", "size", "mode")}
        changed_path = "themes/sarafatto/functions.php"
        artifact[changed_path] = {"sha256": "f" * 64, "size": 8, "mode": "644"}
        result = publisher.make_release_state_plan(current, artifact, "plan-release-b")
        self.assertEqual(len(result["candidate_reference_files"]), 12)
        self.assertEqual(sum(row["classification"] != "artifact"
                             for row in result["candidate_reference_files"]), 9)
        original_sha = next(row["sha256"] for row in current["reference_files"]
                            if row["path"] == changed_path)
        self.assertEqual(result["plan"]["changes"], [{
            "path": changed_path, "action": "replace",
            "old_sha256": original_sha,
            "new_sha256": "f" * 64,
        }])
        self.assertRegex(result["plan_sha256"], r"^[a-f0-9]{64}$")

        artifact["themes/sarafatto/assets/dist/assets/app-old00.js"] = {
            "sha256": "0" * 64, "size": 12, "mode": "644"}
        with self.assertRaisesRegex(release_state_fixtures.state_tool.ReleaseStateError, "extra"):
            publisher.make_release_state_plan(current, artifact, "plan-release-extra")
        del artifact["mu-plugins/sarafatto-polylang-front-page-url.php"]
        del artifact["themes/sarafatto/assets/dist/assets/app-old00.js"]
        with self.assertRaisesRegex(release_state_fixtures.state_tool.ReleaseStateError,
                                   "Approvazioni rimozione"):
            publisher.make_release_state_plan(current, artifact, "plan-release-remove")

    def test_comandi_pubblici_restano_fail_closed(self):
        self.assertFalse(publisher.PUBLIC_WRITER_ENABLED)
        with self.assertRaisesRegex(publisher.PublisherError, "writer di produzione"):
            publisher.blocked_operation("publish")
        with self.assertRaisesRegex(publisher.PublisherError, "writer di produzione"):
            publisher.blocked_operation("rollback")
        with self.assertRaisesRegex(publisher.PublisherError, "writer di produzione"):
            publisher.blocked_operation("recover")

    def test_preflight_production_richiede_percorsi_nella_staging_privata(self):
        private = self.root / "private"
        staging = private / "staging"
        incoming = staging / "run-123"
        incoming.mkdir(parents=True)
        package = incoming / "package"
        package.mkdir()
        paths = [incoming / "inventory.tsv", incoming / "provenance.json", incoming / "release.tar.gz"]
        for path in paths:
            path.write_bytes(b"x")
        with mock.patch.object(publisher, "PRIVATE_ROOT", private):
            publisher._require_private_staging_paths(package, *paths)
            with self.assertRaisesRegex(publisher.PublisherError, "fuori da staging"):
                publisher._require_private_staging_paths(package, self.inventory, *paths[1:])
            with self.assertRaises(publisher.PublisherError):
                publisher._require_private_staging_paths(
                    staging / ".." / "escape", *paths)


if __name__ == "__main__":
    unittest.main(verbosity=2)
