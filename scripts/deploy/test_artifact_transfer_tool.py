#!/usr/bin/env python3
"""Test del trasferimento in staging privata usando directory temporanee POSIX."""

import hashlib
import json
import os
import pathlib
import shutil
import stat
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

    def _authorized_repo(self):
        return mock.patch.object(transfer.production_adapter, "verify_repository_sources",
                                 return_value=self.release_sha), mock.patch.object(
                                     transfer.production_adapter, "_git_output", return_value=b"main\n")

    def _private_roots(self):
        return mock.patch.multiple(
            transfer, PRIVATE_ROOT=self.private, STAGING_ROOT=self.staging, INCOMING_ROOT=self.incoming)

    def _reserve_and_copy(self):
        archive_sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        inventory_sha = hashlib.sha256(self.inventory.read_bytes()).hexdigest()
        with self._private_roots(), self._authorized_repo()[0], self._authorized_repo()[1]:
            result = transfer.reserve(self.transfer_id, self.release_sha, self.run_id,
                                      archive_sha, inventory_sha)
        target = pathlib.Path(result["remote_directory"])
        shutil.copyfile(self.archive, target / "sarafatto-release.tar.gz")
        shutil.copyfile(self.inventory, target / "sarafatto-inventory.tsv")
        shutil.copyfile(self.provenance, target / "sarafatto-provenance.json")
        return target

    def test_ricezione_verifica_artifact_completa_e_replay_rifiutato(self):
        target = self._reserve_and_copy()
        with self._private_roots(), self._authorized_repo()[0], self._authorized_repo()[1]:
            result = transfer.verify(self.transfer_id, self.release_sha, self.run_id)
            repeated = transfer.verify(self.transfer_id, self.release_sha, self.run_id)
            with self.assertRaisesRegex(transfer.TransferError, "già prenotato"):
                transfer.reserve(self.transfer_id, self.release_sha, self.run_id,
                                 hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                                 hashlib.sha256(self.inventory.read_bytes()).hexdigest())
        self.assertEqual(result["status"], "verified-private-artifact")
        self.assertFalse(result["public_writes_performed"])
        self.assertEqual(repeated["status"], "verified-private-artifact")
        self.assertTrue((target / transfer.COMPLETE).is_file())
        self.assertTrue((target / "package/themes/sarafatto/functions.php").is_file())
        self.assertFalse((self.root / "wp-config.php").exists())

    def test_archivio_alterato_rifiutato_senza_marker_complete(self):
        target = self._reserve_and_copy()
        with (target / "sarafatto-release.tar.gz").open("ab") as stream:
            stream.write(b"tamper")
        with self._private_roots(), self._authorized_repo()[0], self._authorized_repo()[1]:
            with self.assertRaisesRegex(transfer.TransferError, "Digest ricevuti"):
                transfer.verify(self.transfer_id, self.release_sha, self.run_id)
        self.assertFalse((target / transfer.COMPLETE).exists())

    def test_trasferimento_incompleto_non_viene_ripreso_automaticamente(self):
        archive_sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        inventory_sha = hashlib.sha256(self.inventory.read_bytes()).hexdigest()
        with self._private_roots(), self._authorized_repo()[0], self._authorized_repo()[1]:
            reserved = transfer.reserve(self.transfer_id, self.release_sha, self.run_id,
                                        archive_sha, inventory_sha)
            with self.assertRaisesRegex(transfer.TransferError, "incompleto"):
                transfer.verify(self.transfer_id, self.release_sha, self.run_id)
        self.assertFalse(pathlib.Path(reserved["remote_directory"], transfer.COMPLETE).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
