#!/usr/bin/env python3
"""Test del trasferimento in staging privata usando directory temporanee POSIX."""

import hashlib
import io
import json
import os
import pathlib
import tarfile
import tempfile
import unittest
from unittest import mock

import artifact_transfer_tool as transfer
import production_publisher as publisher

POSIX_AVAILABLE = (os.name == "posix" and hasattr(os, "O_NOFOLLOW")
                   and os.open in os.supports_dir_fd and hasattr(os, "O_DIRECTORY"))
if os.environ.get("SARAFATTO_REQUIRE_POSIX") == "1" and not POSIX_AVAILABLE:
    raise RuntimeError("CI richiede il supporto POSIX per i test artifact transfer.")


@unittest.skipUnless(POSIX_AVAILABLE, "Fixture trasferimento richiede dir_fd/O_NOFOLLOW POSIX.")
class ArtifactTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent)
        self.root = pathlib.Path(self.temp.name)
        self.private = self.root / "private"
        self.staging = self.private / "staging"
        self.incoming = self.staging / "incoming"
        self.state = self.private / "state"
        self.locks = self.private / "locks"
        self.package = self.root / "package"
        self.inventory = self.root / "sarafatto-inventory.tsv"
        self.archive = self.root / "sarafatto-release.tar.gz"
        self.provenance = self.root / "sarafatto-provenance.json"
        self.release_sha = "a" * 40
        self.run_id = "12345"
        self.transfer_id = f"run-{self.run_id}-{self.release_sha[:12]}"
        for directory in (self.private, self.staging, self.incoming, self.state, self.locks):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        (self.locks / "site-operation.lock").write_bytes(b"")
        os.chmod(self.locks / "site-operation.lock", 0o600)
        self._build_artifact()
        self.toolchain_sha = transfer.toolchain_contract()["toolchain_sha256"]

    def tearDown(self):
        self.temp.cleanup()

    def _build_artifact(self):
        contents = {
            "themes/sarafatto/functions.php": b"<?php // theme\n",
            "plugins/sarafatto-core/plugin.php": b"<?php // plugin\n",
            "mu-plugins/sarafatto-polylang-front-page-url.php": b"<?php // mu\n",
        }
        dist = self.package / "themes/sarafatto/assets/dist"
        dist.mkdir(parents=True)
        entries = {}
        for index, entry in enumerate(publisher.REQUIRED_ENTRIES):
            name = f"assets/chunk-{index}.js"
            payload = f"// entry {index}\n".encode()
            contents[f"themes/sarafatto/assets/dist/{name}"] = payload
            entries[entry] = {"file": name, "isEntry": True}
        manifest = json.dumps(entries, sort_keys=True).encode()
        contents["themes/sarafatto/assets/dist/.vite/manifest.json"] = manifest
        for relative, payload in contents.items():
            target = self.package.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            os.chmod(target, 0o644)
        inventory_rows = [
            f"{hashlib.sha256(payload).hexdigest()}\t{len(payload)}\t{path}"
            for path, payload in sorted(contents.items())
        ]
        self.inventory.write_text("\n".join(inventory_rows) + "\n", encoding="utf-8")
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(self.package, arcname="sarafatto-release")
            archive.add(self.inventory, arcname="sarafatto-inventory.tsv")
        publisher.create_provenance(
            self.inventory, self.archive, self.provenance,
            self.release_sha, self.run_id, "refs/heads/main")

    def _private_roots(self):
        return mock.patch.multiple(
            transfer, PRIVATE_ROOT=self.private, STAGING_ROOT=self.staging, INCOMING_ROOT=self.incoming)

    def _reserve(self):
        archive_sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        inventory_sha = hashlib.sha256(self.inventory.read_bytes()).hexdigest()
        return transfer.reserve(self.transfer_id, self.release_sha, self.run_id,
                                archive_sha, inventory_sha, toolchain_sha256=self.toolchain_sha,
                                provenance_sha256=hashlib.sha256(self.provenance.read_bytes()).hexdigest())

    def _receive(self, path, name=None):
        return transfer.receive(self.transfer_id, self.release_sha, self.run_id, name or path.name,
                                toolchain_sha256=self.toolchain_sha, stream=io.BytesIO(path.read_bytes()))

    def _verify(self):
        return transfer.verify(self.transfer_id, self.release_sha, self.run_id,
                               toolchain_sha256=self.toolchain_sha)

    def _reserve_and_copy(self):
        with self._private_roots():
            result = self._reserve()
            for source in (self.archive, self.inventory, self.provenance):
                self._receive(source)
        target = pathlib.Path(result["remote_directory"])
        return target

    def test_ricezione_verifica_artifact_completa_e_replay_rifiutato(self):
        with self._private_roots(), \
                mock.patch.object(transfer.production_adapter, "verify_repository_sources", side_effect=AssertionError("Git vietato")), \
                mock.patch.object(transfer.production_adapter, "_git_output", side_effect=AssertionError("Git vietato")):
            target = self._reserve_and_copy()
            result = self._verify()
            repeated = self._verify()
            inputs = transfer.publisher_inputs(self.transfer_id, self.release_sha, self.run_id,
                                                toolchain_sha256=self.toolchain_sha)
            with self.assertRaisesRegex(transfer.TransferError, "già prenotato"):
                self._reserve()
        self.assertEqual(result["status"], "verified-private-artifact")
        self.assertFalse(result["public_writes_performed"])
        self.assertEqual(repeated["status"], "verified-private-artifact")
        self.assertTrue((target / transfer.COMPLETE).is_file())
        self.assertTrue((target / "package/themes/sarafatto/functions.php").is_file())
        self.assertEqual(inputs["publisher_inputs"]["package"], str(target / "package"))
        self.assertEqual(result["toolchain_sha256"], self.toolchain_sha)
        self.assertFalse((self.root / "wp-config.php").exists())

    def test_archivio_alterato_rifiutato_senza_marker_complete(self):
        target = self._reserve_and_copy()
        with (target / "sarafatto-release.tar.gz").open("ab") as stream:
            stream.write(b"tamper")
        with self._private_roots():
            with self.assertRaisesRegex(transfer.TransferError, "Digest ricevuti"):
                self._verify()
        self.assertFalse((target / transfer.COMPLETE).exists())

    def test_trasferimento_incompleto_non_viene_ripreso_automaticamente(self):
        with self._private_roots():
            reserved = self._reserve()
            with self.assertRaisesRegex(transfer.TransferError, "incompleto"):
                self._verify()
            with self.assertRaises(transfer.TransferError):
                transfer.publisher_inputs(self.transfer_id, self.release_sha, self.run_id,
                                          toolchain_sha256=self.toolchain_sha)
        self.assertFalse(pathlib.Path(reserved["remote_directory"], transfer.COMPLETE).exists())

    def test_sha_e_run_errati_rifiutati(self):
        target = self._reserve_and_copy()
        for release, run in (("b" * 40, self.run_id), (self.release_sha, "999"), ("a" * 12, self.run_id)):
            with self.subTest(release=release, run=run), self._private_roots():
                with self.assertRaises(transfer.TransferError):
                    transfer.verify(self.transfer_id, release, run, toolchain_sha256=self.toolchain_sha)
        self.assertFalse((target / transfer.COMPLETE).exists())

    def test_strumenti_incompatibili_bloccano_prima_della_prenotazione(self):
        with self._private_roots():
            with self.assertRaisesRegex(transfer.TransferError, "Strumenti server incompatibili"):
                transfer.reserve(self.transfer_id, self.release_sha, self.run_id, "1" * 64, "2" * 64,
                                 provenance_sha256="3" * 64, toolchain_sha256="0" * 64)
        self.assertEqual(list(self.incoming.iterdir()), [])

    def test_ricezione_esclusiva_e_symlink_non_sovrascrivono(self):
        outside = self.root / "outside.txt"
        outside.write_bytes(b"outside untouched")
        with self._private_roots():
            target = pathlib.Path(self._reserve()["remote_directory"])
            received = self._receive(self.archive)
            self.assertEqual(received["status"], "received-private-only")
            with self.assertRaisesRegex(transfer.TransferError, "nessuna sovrascrittura"):
                self._receive(self.archive)
            self.assertEqual((target / self.archive.name).read_bytes(), self.archive.read_bytes())
            os.symlink(outside, target / self.inventory.name)
            with self.assertRaisesRegex(transfer.TransferError, "nessuna sovrascrittura"):
                self._receive(self.inventory)
        self.assertEqual(outside.read_bytes(), b"outside untouched")
        self.assertFalse((target / transfer.COMPLETE).exists())

    def test_ricezione_payload_alterato_o_nome_estraneo_blocca(self):
        with self._private_roots():
            target = pathlib.Path(self._reserve()["remote_directory"])
            with self.assertRaisesRegex(transfer.TransferError, "fuori allowlist"):
                transfer.receive(self.transfer_id, self.release_sha, self.run_id, "../public/file.php",
                                 toolchain_sha256=self.toolchain_sha, stream=io.BytesIO(b"bad"))
            with self.assertRaisesRegex(transfer.TransferError, "Digest payload"):
                transfer.receive(self.transfer_id, self.release_sha, self.run_id, self.archive.name,
                                 toolchain_sha256=self.toolchain_sha, stream=io.BytesIO(b"tamper"))
            with self.assertRaisesRegex(transfer.TransferError, "nessuna sovrascrittura"):
                self._receive(self.archive)
        self.assertFalse((target / transfer.COMPLETE).exists())

    def test_package_alterato_dopo_complete_non_raggiunge_publisher(self):
        target = self._reserve_and_copy()
        with self._private_roots():
            self._verify()
            (target / "package/themes/sarafatto/functions.php").write_bytes(b"tamper")
            with self.assertRaises(publisher.PublisherError):
                transfer.publisher_inputs(self.transfer_id, self.release_sha, self.run_id,
                                          toolchain_sha256=self.toolchain_sha)

    def test_digest_provenance_riverificato_anche_dopo_complete(self):
        target = self._reserve_and_copy()
        with self._private_roots():
            self._verify()
            (target / self.provenance.name).write_bytes(b"{}")
            with self.assertRaisesRegex(transfer.TransferError, "Digest ricevuti"):
                self._verify()

    def test_manifest_vite_incompleto_blocca_marker_e_input_publisher(self):
        manifest_path = self.package / "themes/sarafatto/assets/dist/.vite/manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest[publisher.REQUIRED_ENTRIES[0]]["file"] = "assets/missing.js"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rows = []
        for path in sorted(self.package.rglob("*")):
            if path.is_file():
                raw = path.read_bytes()
                rows.append(f"{hashlib.sha256(raw).hexdigest()}\t{len(raw)}\t{path.relative_to(self.package).as_posix()}")
        self.inventory.write_text("\n".join(rows) + "\n", encoding="utf-8")
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(self.package, arcname="sarafatto-release")
            archive.add(self.inventory, arcname="sarafatto-inventory.tsv")
        self.provenance.unlink()
        publisher.create_provenance(self.inventory, self.archive, self.provenance,
                                    self.release_sha, self.run_id, "refs/heads/main")
        target = self._reserve_and_copy()
        with self._private_roots(), self.assertRaisesRegex(publisher.PublisherError, "Asset Vite non presente"):
            transfer.publisher_inputs(self.transfer_id, self.release_sha, self.run_id,
                                      toolchain_sha256=self.toolchain_sha)
        self.assertFalse((target / transfer.COMPLETE).exists())

    def test_provenance_commit_estraneo_blocca_anche_con_digest_prenotato(self):
        document = json.loads(self.provenance.read_bytes())
        document["commit_sha"] = "b" * 40
        self.provenance.write_text(json.dumps(document), encoding="utf-8")
        target = self._reserve_and_copy()
        with self._private_roots(), self.assertRaisesRegex(transfer.TransferError, "Provenance non concorda"):
            self._verify()
        self.assertFalse((target / transfer.COMPLETE).exists())


class TransferContractTests(unittest.TestCase):
    def test_contratto_strumenti_senza_accesso_git(self):
        with mock.patch.object(transfer.production_adapter, "_git_output", side_effect=AssertionError("Git vietato")):
            contract = transfer.toolchain_contract()
            checked = transfer._validate_toolchain(contract["toolchain_sha256"])
        self.assertEqual(checked, contract)
        self.assertEqual(len(contract["contract"]["files"]), 7)
        self.assertIn("baseline-inventory.sh", [row["file"] for row in contract["contract"]["files"]])
        self.assertEqual(contract["contract"]["transfer_protocol"], 2)

    def test_contratto_digest_errato_rifiutato(self):
        for expected in (None, "not-a-digest", "0" * 64):
            with self.subTest(expected=expected), self.assertRaises(transfer.TransferError):
                transfer._validate_toolchain(expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
