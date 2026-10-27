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
