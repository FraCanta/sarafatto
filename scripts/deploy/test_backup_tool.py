#!/usr/bin/env python3
"""Fixture locali di sicurezza per backup e restore-test; nessun accesso IONOS."""

import hashlib
import importlib.util
import io
import errno
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import tarfile
import threading
import unittest
from unittest import mock

try:
    import fcntl
except ImportError:
    fcntl = None

MODULE_PATH = pathlib.Path(__file__).with_name("backup_tool.py")
SPEC = importlib.util.spec_from_file_location("backup_tool", MODULE_PATH)
backup_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_tool)
baseline_tool = backup_tool.baseline

SHA = "911d6a72ac0f624dc85b43d53b1c299968d683f6"
RUN_URL = "https://github.com/FraCanta/sarafatto/actions/runs/40106509533"
BASELINE_SHA = "07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd"

if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and fcntl is None:
    raise RuntimeError("flock mancante: i test backup critici non possono essere saltati in CI.")


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


class BackupToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".backup-fixture-", dir=MODULE_PATH.parents[2])
        self.root = pathlib.Path(self.temp.name)
        self.public = self.root / "public" / "wp-content"
        self.private = self.root / "private"
        self.state = self.private / "state"
        self.backups = self.private / "backups"
        self.staging = self.private / "staging"
        self.locks = self.private / "locks"
        for directory in (self.public / "themes/sarafatto/assets/dist/assets",
                          self.public / "themes/sarafatto/node_modules/pkg",
                          self.public / "plugins/sarafatto-core/includes",
                          self.public / "mu-plugins", self.state, self.backups,
                          self.staging, self.locks):
            directory.mkdir(parents=True, exist_ok=True)
        self.files = {
            "themes/sarafatto/front-page.php": ("home bytes", "artifact"),
            "plugins/sarafatto-core/plugin.php": ("plugin bytes", "artifact"),
            "mu-plugins/sarafatto-polylang-front-page-url.php": ("mu bytes", "artifact"),
            **{
                f"themes/sarafatto/assets/dist/assets/legacy-{index:02d}-Ab12Cd34.js":
                    (f"old bundle {index}", "retained-vite-bundle")
                for index in range(1, 9)
            },
            "plugins/sarafatto-core/includes/home-hero.php.bak": ("backup bytes", "retained-backup"),
        }
        for relative, (content, _) in self.files.items():
            target = self.public / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode())
            target.chmod(0o600 if relative.endswith(".bak") else 0o644)
        (self.public / "themes/sarafatto/node_modules/pkg/vite.js").write_text("npm local", encoding="utf-8")
        self.marker = self.private / baseline_tool.MARKER
        self.marker.write_text(baseline_tool.MARKER_VALUE + "\n", encoding="utf-8")
        self.backup_id = "20261024T120000Z-abcdef123456"
        if os.name == "posix":
            for directory in (self.private, self.state, self.backups, self.staging, self.locks):
                directory.chmod(0o700)
            self.marker.chmod(0o600)
        self.artifact = self.root / "artifact.tsv"
        artifact_rows = []
        for relative, (content, classification) in self.files.items():
            if classification == "artifact":
                target = self.public / relative
                data = target.read_bytes()
                artifact_rows.append(f"{hash_bytes(data)}\t{len(data)}\t{relative}\n")
        self.artifact.write_text("".join(artifact_rows), encoding="utf-8")
        self.baseline_path = self.state / "baseline.json"
        self.baseline_sha = self.create_baseline()

    def tearDown(self):
        self.temp.cleanup()

    def inventory_text(self, symlinks=()):
        excluded = self.public / baseline_tool.EXCLUDED
        excluded_files = sum(1 for path in excluded.rglob("*") if path.is_file() and not path.is_symlink())
        excluded_links = sum(1 for path in excluded.rglob("*") if path.is_symlink())
        lines = [f"EXCLUDED\t{baseline_tool.EXCLUDED}\t{excluded_files}\t{excluded_links}\n"]
        roots = [self.public / "themes/sarafatto", self.public / "plugins/sarafatto-core",
                 self.public / "mu-plugins/sarafatto-polylang-front-page-url.php"]
        for root in roots:
            iterable = [root] if root.is_file() or root.is_symlink() else root.rglob("*")
            for path in iterable:
                relative = path.relative_to(self.public).as_posix()
                if baseline_tool.excluded(relative):
                    continue
                if path.is_symlink():
                    lines.append(f"SYMLINK\t{relative}\t/outside/target\n")
                elif path.is_file():
                    data = path.read_bytes()
                    mode = format(stat.S_IMODE(path.stat().st_mode), "o")
                    lines.append(f"FILE\t{hash_bytes(data)}\t{len(data)}\t{mode}\t{relative}\n")
        for relative, target in symlinks:
            lines.append(f"SYMLINK\t{relative}\t{target}\n")
        lines.append("END\n")
        return "".join(lines)

    def create_baseline(self):
        remote_path = self.root / "remote.tsv"
        remote_path.write_text(self.inventory_text(), encoding="utf-8")
        accepted = [path for path, (_, classification) in self.files.items() if classification != "artifact"]
        candidate = baseline_tool.compare(
            self.artifact, remote_path, SHA, SHA, "bootstrap-911d6a72", RUN_URL, accepted,
        )["candidate"]
        self.assertIsNotNone(candidate)
        candidate["verification"]["status"] = "initialized-from-verified-content-match"
        raw = backup_tool.json_bytes(candidate)
        self.baseline_path.write_bytes(raw)
        if os.name == "posix":
            self.baseline_path.chmod(0o600)
        return hash_bytes(raw)

    def inventory_patch(self, provider=None):
        return mock.patch.object(
            backup_tool, "inventory_text_for_backup",
            side_effect=provider or (lambda _commit: self.inventory_text()),
        )

    def create(self, backup_id=None, quota=10**9, provider=None):
        with self.inventory_patch(provider):
            return backup_tool.create_backup(
                backup_id or self.backup_id, self.baseline_sha, quota,
                private_root=self.private, expected_private_root=self.private,
                public_root=self.public, baseline_path=self.baseline_path,
            )

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_01_backup_valido_e_verificabile(self):
        created = self.create()
        result = backup_tool.verify_backup(created["backup_id"], self.baseline_sha, created["manifest_sha256"],
                                           private_root=self.private, expected_private_root=self.private)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["files"], len(self.files))

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_02_file_mancante_prima_backup_blocca(self):
        (self.public / "themes/sarafatto/front-page.php").unlink()
        with self.inventory_patch():
            with self.assertRaises(backup_tool.BackupError):
                backup_tool.create_backup(self.backup_id, self.baseline_sha, 10**9,
                                          private_root=self.private, expected_private_root=self.private,
                                          public_root=self.public, baseline_path=self.baseline_path)
        self.assertFalse((self.backups / self.backup_id).exists())

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_03_file_modificato_prima_backup_blocca(self):
        (self.public / "themes/sarafatto/front-page.php").write_text("manual edit", encoding="utf-8")
        with self.assertRaises(backup_tool.BackupError):
            self.create()

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_04_file_alterato_dopo_backup_rilevato(self):
        created = self.create()
        archive = self.backups / self.backup_id / backup_tool.BACKUP_ARCHIVE
        archive.write_bytes(archive.read_bytes() + b"tamper")
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.verify_backup(self.backup_id, self.baseline_sha, created["manifest_sha256"],
                                      private_root=self.private, expected_private_root=self.private)

    @unittest.skipUnless(os.name == "posix" and fcntl is not None, "permessi Unix verificati su runner Ubuntu")
    def test_05_permessi_modificati_prima_backup_bloccano(self):
        (self.public / "themes/sarafatto/front-page.php").chmod(0o600)
        with self.assertRaises(backup_tool.BackupError):
            self.create()

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_06_symlink_pericoloso_blocca(self):
        outside = self.root / "outside-target"
        outside.write_text("outside", encoding="utf-8")
        (self.public / "themes/sarafatto/danger-link").symlink_to(outside)
        provider = lambda _sha: self.inventory_text([("themes/sarafatto/danger", "/outside/target")])
        with self.assertRaises(backup_tool.BackupError):
            self.create(provider=provider)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_07_file_extra_non_approvato_blocca(self):
        (self.public / "themes/sarafatto/unapproved.txt").write_text("unexpected", encoding="utf-8")
        with self.assertRaises(backup_tool.BackupError):
            self.create()

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_08_extra_approvati_inclusi(self):
        self.create()
        result = backup_tool.verify_backup_directory(self.backups / self.backup_id, self.backup_id, self.baseline_sha)
        paths = {row["path"] for row in result["manifest"]["files"]}
        extras = {path for path, (_, classification) in self.files.items() if classification != "artifact"}
        self.assertEqual(len(extras), 9)
        self.assertTrue(extras.issubset(paths))
        manifest_extras = {row["path"] for row in result["manifest"]["files"]
                           if row["classification"] != "artifact"}
        self.assertEqual(manifest_extras, extras)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_09_node_modules_escluso_senza_altre_esclusioni(self):
        self.create()
        result = backup_tool.verify_backup_directory(self.backups / self.backup_id, self.backup_id, self.baseline_sha)
        self.assertFalse(any("node_modules" in row["path"] for row in result["manifest"]["files"]))
        self.assertEqual(result["manifest"]["scope"]["excluded"], ["themes/sarafatto/node_modules/"])

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_10_backup_esistente_non_sovrascritto(self):
        self.create()
        archive = self.backups / self.backup_id / backup_tool.BACKUP_ARCHIVE
        before = hash_bytes(archive.read_bytes())
        with self.assertRaises(backup_tool.BackupError):
            self.create()
        self.assertEqual(hash_bytes(archive.read_bytes()), before)

    @unittest.skipUnless(fcntl is not None, "fixture POSIX di finalizzazione eseguita su runner GitHub")
    def test_10a_renameat2_non_supportato_usa_fallback_no_clobber(self):
        cleanup = backup_tool.remove_current_temporary_snapshot
        observed_independent_files = []

        def inspect_then_cleanup(source, source_fd, parent_fd):
            final_fd = os.open(self.backup_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=parent_fd)
            try:
                for name in (backup_tool.BACKUP_ARCHIVE, "manifest.json", "manifest.sha256"):
                    source_info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
                    final_info = os.stat(name, dir_fd=final_fd, follow_symlinks=False)
                    observed_independent_files.append((source_info.st_dev, source_info.st_ino)
                                                      != (final_info.st_dev, final_info.st_ino))
                source_archive = os.open(backup_tool.BACKUP_ARCHIVE, os.O_WRONLY | os.O_TRUNC,
                                         dir_fd=source_fd)
                with os.fdopen(source_archive, "wb") as stream:
                    stream.write(b"changed only in temporary directory")
                final_archive = os.open(backup_tool.BACKUP_ARCHIVE, os.O_RDONLY | os.O_NOFOLLOW,
                                        dir_fd=final_fd)
                with os.fdopen(final_archive, "rb") as stream:
                    final_digest = hashlib.sha256(stream.read()).hexdigest()
                final_manifest = json.loads((self.backups / self.backup_id / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(final_digest, final_manifest["archive"]["sha256"])
            finally:
                os.close(final_fd)
            cleanup(source, source_fd, parent_fd)

        with mock.patch.object(backup_tool, "renameat2_noreplace", return_value=False), \
                mock.patch.object(backup_tool, "remove_current_temporary_snapshot", side_effect=inspect_then_cleanup):
            result = self.create()
        self.assertEqual(result["finalization"], "mkdirat+copyat")
        self.assertTrue(observed_independent_files)
        self.assertTrue(all(observed_independent_files))
        verified = backup_tool.verify_backup(self.backup_id, self.baseline_sha, result["manifest_sha256"],
                                             private_root=self.private, expected_private_root=self.private)
        self.assertEqual(verified["status"], "verified")
        self.assertFalse(any(path.name.startswith(".incomplete-" + self.backup_id) for path in self.backups.iterdir()))

    @unittest.skipUnless(fcntl is not None, "fixture POSIX di finalizzazione eseguita su runner GitHub")
    def test_10b_einval_renameat2_usa_fallback(self):
        with mock.patch.object(backup_tool, "renameat2_noreplace",
                               side_effect=OSError(errno.EINVAL, "flag non supportato")):
            result = self.create()
        self.assertEqual(result["finalization"], "mkdirat+copyat")
        self.assertEqual(backup_tool.verify_backup(self.backup_id, self.baseline_sha, result["manifest_sha256"],
                                                   private_root=self.private,
                                                   expected_private_root=self.private)["status"], "verified")

    @unittest.skipUnless(fcntl is not None, "fixture POSIX no-clobber eseguita su runner GitHub")
    def test_10c_destinazione_esistente_non_viene_sovrascritta(self):
        destination = self.backups / self.backup_id
        destination.mkdir(mode=0o700)
        sentinel = destination / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        sentinel.chmod(0o600)
        source_name = ".incomplete-" + self.backup_id + "-1234abcd"
        source = self.backups / source_name
        source.mkdir(mode=0o700)
        parent_fd = os.open(self.backups, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        source_fd = os.open(source_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            with mock.patch.object(backup_tool, "renameat2_noreplace", return_value=False):
                with self.assertRaisesRegex(backup_tool.BackupError, "già esistente"):
                    backup_tool.rename_backup_noreplace(source_name, self.backup_id, parent_fd, source_fd,
                                                        self.baseline_sha, "0" * 64)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertTrue(source.exists())
        finally:
            os.close(source_fd)
            os.close(parent_fd)

    @unittest.skipUnless(fcntl is not None, "fixture POSIX concorrente eseguita su runner GitHub")
    def test_10d_finalizzazione_concorrente_no_clobber(self):
        seed = self.create()
        seed_dir = self.backups / self.backup_id
        final_id = "20261024T120010Z-abcdef123456"
        source_names = [".incomplete-" + final_id + "-11111111",
                        ".incomplete-" + final_id + "-22222222"]
        manifest = json.loads((seed_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["backup_id"] = final_id
        raw = backup_tool.json_bytes(manifest)
        digest = hash_bytes(raw)
        for source_name in source_names:
            source = self.backups / source_name
            source.mkdir(mode=0o700)
            for name in (backup_tool.BACKUP_ARCHIVE,):
                shutil.copyfile(seed_dir / name, source / name)
            (source / "manifest.json").write_bytes(raw)
            (source / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="ascii")
            (source / "COMPLETE").write_text(digest + "\n", encoding="ascii")
            for item in source.iterdir():
                item.chmod(0o600)
            source.chmod(0o700)

        parent_fd = os.open(self.backups, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        barrier = threading.Barrier(2)
        results = []
        result_lock = threading.Lock()

        def finalize(source_name):
            source_fd = os.open(source_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                barrier.wait(timeout=10)
                backup_tool.rename_backup_noreplace(source_name, final_id, parent_fd, source_fd,
                                                    self.baseline_sha, digest)
                outcome = "ok"
            except backup_tool.BackupError as exc:
                outcome = str(exc)
            finally:
                os.close(source_fd)
            with result_lock:
                results.append(outcome)

        try:
            with mock.patch.object(backup_tool, "renameat2_noreplace", return_value=False):
                threads = [threading.Thread(target=finalize, args=(name,)) for name in source_names]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=20)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(results.count("ok"), 1)
            self.assertEqual(sum("già esistente" in result for result in results), 1)
            checked = backup_tool.verify_backup_directory(self.backups / final_id, final_id,
                                                          self.baseline_sha, digest)
            self.assertEqual(checked["manifest_sha256"], digest)
        finally:
            os.close(parent_fd)

    @unittest.skipUnless(fcntl is not None, "fixture POSIX di interruzione eseguita su runner GitHub")
    def test_10e_interruzioni_fallback_non_pubblicano_backup_valido(self):
        real_copy = backup_tool.copy_snapshot_file
        real_write = backup_tool.write_at
        scenarios = ["after-mkdir", "after-payload", "after-manifest", "after-checksum", "before-complete"]

        for index, scenario in enumerate(scenarios, 20):
            backup_id = f"20261024T1200{index:02d}Z-abcdef123456"
            copy_count = 0
            complete_count = 0

            def interrupt_copy(source_fd, destination_fd, name):
                nonlocal copy_count
                copy_count += 1
                if scenario == "after-mkdir":
                    raise backup_tool.BackupError("interruzione fixture dopo mkdirat")
                result = real_copy(source_fd, destination_fd, name)
                target = {"payload.tar.gz": 1, "manifest.json": 2, "manifest.sha256": 3}.get(name)
                if target == copy_count and scenario == ("after-payload" if target == 1 else
                                                         "after-manifest" if target == 2 else "after-checksum"):
                    raise backup_tool.BackupError("interruzione fixture dopo copia file")
                return result

            def interrupt_before_complete(directory_fd, name, payload, mode=0o600):
                nonlocal complete_count
                if name == "COMPLETE":
                    complete_count += 1
                    if complete_count == 2:
                        raise backup_tool.BackupError("interruzione fixture prima di COMPLETE")
                return real_write(directory_fd, name, payload, mode)

            with mock.patch.object(backup_tool, "renameat2_noreplace", return_value=False), \
                    mock.patch.object(backup_tool, "copy_snapshot_file", side_effect=interrupt_copy), \
                    mock.patch.object(backup_tool, "write_at", side_effect=interrupt_before_complete):
                with self.assertRaises(backup_tool.BackupError):
                    self.create(backup_id=backup_id)

            final_dir = self.backups / backup_id
            rows = backup_tool.list_backups(private_root=self.private, expected_private_root=self.private)
            row = next(item for item in rows if item.get("path") == final_dir.name)
            self.assertEqual(row["status"], "incomplete-or-interrupted", scenario)
            manifest_path = final_dir / "manifest.json"
            manifest_digest = hash_bytes(manifest_path.read_bytes()) if manifest_path.exists() else "0" * 64
            with self.assertRaises(backup_tool.BackupError):
                backup_tool.verify_backup(backup_id, self.baseline_sha, manifest_digest,
                                          private_root=self.private, expected_private_root=self.private)
            with self.assertRaises(backup_tool.BackupError):
                backup_tool.restore_test(backup_id, self.baseline_sha, manifest_digest, 10**9,
                                         private_root=self.private, expected_private_root=self.private,
                                         disk_free_bytes=10**9)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_11_lock_occupato_blocca(self):
        lock = self.locks / "site-operation.lock"
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with self.assertRaises(baseline_tool.BaselineError):
                self.create()
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_12_interrotto_elencato_incompleto_e_non_verificabile(self):
        incomplete = self.backups / ".incomplete-manual-test"
        incomplete.mkdir(mode=0o700)
        (incomplete / backup_tool.BACKUP_ARCHIVE).write_bytes(b"partial")
        result = backup_tool.list_backups(private_root=self.private, expected_private_root=self.private)
        self.assertEqual(result[0]["status"], "incomplete-or-interrupted")
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.verify_backup_directory(incomplete, self.backup_id, self.baseline_sha)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_13_manifest_incompleto_blocca(self):
        self.create()
        (self.backups / self.backup_id / "manifest.sha256").unlink()
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.verify_backup_directory(self.backups / self.backup_id, self.backup_id, self.baseline_sha)

    @unittest.skipUnless(os.name == "posix", "verifica openat dell'archivio eseguita sul runner Ubuntu")
    def test_14_archive_path_traversal_bloccato(self):
        directory = self.backups / self.backup_id
        directory.mkdir(mode=0o700)
        archive_path = directory / backup_tool.BACKUP_ARCHIVE
        with tarfile.open(archive_path, mode="w:gz") as archive:
            payload = b"traversal"
            member = tarfile.TarInfo(name="../../outside")
            member.size = len(payload)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(payload))
        archive_bytes = archive_path.read_bytes()
        safe_member = {
            "path": "themes/sarafatto/front-page.php", "sha256": hash_bytes(b"home bytes"),
            "size": len(b"home bytes"), "mode": "644", "classification": "artifact",
        }
        malicious = {
            "schema_version": 1, "status": "complete", "backup_id": self.backup_id,
            "baseline": {"sha256": self.baseline_sha, "commit_sha": SHA, "identifier": "fixture"},
            "scope": {"public_root": str(backup_tool.PUBLIC_WP_CONTENT),
                      "excluded": ["themes/sarafatto/node_modules/"],
                      "included_roots": ["themes/sarafatto/", "plugins/sarafatto-core/",
                                         "mu-plugins/sarafatto-polylang-front-page-url.php"]},
            "archive": {"file": backup_tool.BACKUP_ARCHIVE, "size": len(archive_bytes), "sha256": hash_bytes(archive_bytes)},
            "files": [safe_member],
        }
        raw = backup_tool.json_bytes(malicious)
        manifest_sha = hash_bytes(raw)
        (directory / "manifest.json").write_bytes(raw)
        (directory / "manifest.sha256").write_text(f"{manifest_sha}  manifest.json\n", encoding="ascii")
        (directory / "COMPLETE").write_text(manifest_sha + "\n", encoding="ascii")
        if os.name == "posix":
            for item in directory.iterdir():
                item.chmod(0o600)
            directory.chmod(0o700)
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.verify_backup_directory(directory, self.backup_id, self.baseline_sha, manifest_sha)
        self.assertFalse((self.root / "outside").exists())

    @unittest.skipUnless(os.name == "posix" and fcntl is not None, "openat/dir_fd disponibile sul runner Ubuntu")
    def test_14a_sostituzione_backups_con_symlink_dopo_apertura_fallisce_chiusa(self):
        outside = self.root / "outside-backups"
        outside.mkdir(mode=0o700)
        original_inventory = self.inventory_text()
        changed = False

        def swap_after_private_descriptors_open(_commit):
            nonlocal changed
            if not changed:
                os.rename(self.backups, self.private / "backups-held")
                os.symlink(outside, self.backups, target_is_directory=True)
                changed = True
            return original_inventory

        with self.assertRaises(backup_tool.BackupError):
            self.create(provider=swap_after_private_descriptors_open)
        self.assertTrue(changed)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list((self.private / "backups-held").iterdir()), [])

    @unittest.skipUnless(os.name == "posix" and fcntl is not None, "openat/dir_fd disponibile sul runner Ubuntu")
    def test_14b_sostituzione_staging_con_symlink_dopo_apertura_fallisce_chiusa(self):
        created = self.create()
        outside = self.root / "outside-staging"
        outside.mkdir(mode=0o700)
        original = backup_tool.verify_manifest_matches_baseline
        changed = False

        def swap_after_private_descriptors_open(*args, **kwargs):
            nonlocal changed
            result = original(*args, **kwargs)
            if not changed:
                os.rename(self.staging, self.private / "staging-held")
                os.symlink(outside, self.staging, target_is_directory=True)
                changed = True
            return result

        with mock.patch.object(backup_tool, "verify_manifest_matches_baseline", side_effect=swap_after_private_descriptors_open):
            with self.assertRaises(backup_tool.BackupError):
                backup_tool.restore_test(self.backup_id, self.baseline_sha, created["manifest_sha256"], 10**9,
                                         private_root=self.private, expected_private_root=self.private,
                                         disk_free_bytes=10**9)
        self.assertTrue(changed)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list((self.private / "staging-held").iterdir()), [])

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_15_restore_test_riuscito_solo_in_staging(self):
        created = self.create()
        before = {p: hash_bytes((self.public / p).read_bytes()) for p in self.files}
        report = backup_tool.restore_test(self.backup_id, self.baseline_sha, created["manifest_sha256"], 10**9,
                                          private_root=self.private, expected_private_root=self.private,
                                          disk_free_bytes=10**9)
        self.assertEqual(report["status"], "restore-test-passed")
        self.assertTrue(report["restore_test_path"].startswith(str(self.staging)))
        self.assertFalse(report["public_wordpress_modified"])
        self.assertEqual(before, {p: hash_bytes((self.public / p).read_bytes()) for p in self.files})
        restored = pathlib.Path(report["restore_test_path"])
        self.assertEqual({p.relative_to(restored).as_posix() for p in restored.rglob("*") if p.is_file()},
                         set(self.files))
        for relative, (content, _) in self.files.items():
            self.assertEqual((restored / relative).read_bytes(), content.encode())

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_16_restore_test_integrity_error_blocca(self):
        created = self.create()
        archive = self.backups / self.backup_id / backup_tool.BACKUP_ARCHIVE
        archive.write_bytes(archive.read_bytes() + b"altered")
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.restore_test(self.backup_id, self.baseline_sha, created["manifest_sha256"], 10**9,
                                     private_root=self.private, expected_private_root=self.private,
                                     disk_free_bytes=10**9)
        self.assertEqual(list(self.staging.iterdir()), [])

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_16a_modifica_o_assenza_di_ognuno_dei_nove_extra_blocca(self):
        extra_paths = [path for path, (_, classification) in self.files.items() if classification != "artifact"]
        self.assertEqual(len(extra_paths), 9)
        for relative in extra_paths:
            with self.subTest(path=relative, state="modified"):
                target = self.public / relative
                original = target.read_bytes()
                target.write_bytes(original + b"-modified")
                with self.assertRaises(backup_tool.BackupError):
                    self.create(backup_id="20261024T120001Z-abcdef123456")
                target.write_bytes(original)
            with self.subTest(path=relative, state="missing"):
                target = self.public / relative
                original = target.read_bytes()
                target.unlink()
                with self.assertRaises(backup_tool.BackupError):
                    self.create(backup_id="20261024T120002Z-abcdef123456")
                target.write_bytes(original)

    def test_17_destinazione_restore_non_autorizzata(self):
        outside = self.root / "outside-test"
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.validate_restore_destination(outside, self.staging)

    def test_18_rifiuta_path_fuori_area_privata_e_traversal(self):
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.validate_restore_destination(self.root / "escape", self.staging)
        self.assertFalse((self.root / "escape").exists())
        self.assertFalse(baseline_tool.safe_path("../../public/wp-config.php"))

    def test_19_quota_non_confermata_blocca(self):
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.check_capacity(None, 10**9, 1000)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_20_baseline_assente_blocca_backup(self):
        self.baseline_path.unlink()
        with self.assertRaisesRegex(backup_tool.BackupError, "Baseline assente"):
            self.create()
        self.assertEqual(list(self.backups.iterdir()), [])
        self.assertFalse(any(path.name.startswith(".incomplete-") for path in self.backups.iterdir()))

    def test_21_cli_non_accetta_destinazioni_o_root_arbitrarie(self):
        with self.assertRaises(SystemExit):
            backup_tool.parser().parse_args([
                "restore-test", "--backup-id", self.backup_id,
                "--baseline-sha256", self.baseline_sha,
                "--manifest-sha256", "0" * 64,
                "--account-quota-free-bytes", "1000000000",
                "--destination", "/home/www/public",
            ])

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_22_manifest_rihashato_ma_digest_esterno_diverso_blocca(self):
        created = self.create()
        directory = self.backups / self.backup_id
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["created_at_utc"] = "2020-01-01T00:00:00Z"
        raw = backup_tool.json_bytes(manifest)
        digest = hash_bytes(raw)
        manifest_path.write_bytes(raw)
        (directory / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="ascii")
        (directory / "COMPLETE").write_text(digest + "\n", encoding="ascii")
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.verify_backup(self.backup_id, self.baseline_sha, created["manifest_sha256"],
                                      private_root=self.private, expected_private_root=self.private)

    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_backup_di_altra_baseline_blocca_verify(self):
        created = self.create()
        with self.assertRaises(backup_tool.BackupError):
            backup_tool.verify_backup(self.backup_id, "0" * 64, created["manifest_sha256"],
                                      private_root=self.private, expected_private_root=self.private)


    @unittest.skipUnless(fcntl is not None, "fixture di lock eseguita su runner POSIX GitHub")
    def test_current_release_supporta_nuovi_backup_e_backup_storici(self):
        historical = self.create()
        state_module = backup_tool.release_state
        with mock.patch.object(state_module, "INITIAL_BASELINE_SHA256", self.baseline_sha):
            bootstrap = state_module.bootstrap_current_release(
                private_root=self.private, expected_root=self.private,
                inventory_reader=lambda _commit: self.inventory_text(),
                confirmation="INITIALIZE-CURRENT " + self.baseline_sha,
            )
        self.assertEqual(bootstrap["status"], "bootstrapped")
        old_check = backup_tool.verify_backup(
            historical["backup_id"], self.baseline_sha, historical["manifest_sha256"],
            private_root=self.private, expected_private_root=self.private,
        )
        self.assertEqual(old_check["status"], "verified")
        current_id = "20261024T120009Z-abcdef123457"
        current = self.create(backup_id=current_id)
        result = backup_tool.verify_backup(
            current_id, self.baseline_sha, current["manifest_sha256"],
            private_root=self.private, expected_private_root=self.private,
        )
        self.assertEqual(result["status"], "verified")
        manifest = json.loads((self.backups / current_id / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["reference_state"]["kind"], "current-release")
        current_state_path = self.state / backup_tool.release_state.STATE_NAME
        trusted_state = current_state_path.read_bytes()
        forged = json.loads(trusted_state)
        forged["reference_files"][0]["sha256"] = "0" * 64
        forged["inventory"]["files"][0]["sha256"] = "0" * 64
        forged["inventory_sha256"] = backup_tool.release_state.inventory_digest_json(forged["inventory"])
        forged["release"]["inventory_sha256"] = forged["inventory_sha256"]
        forged.pop("state_sha256")
        forged["state_sha256"] = backup_tool.release_state.digest_json(forged)
        current_state_path.write_bytes(backup_tool.release_state.json_bytes(forged))
        current_state_path.chmod(0o600)
        with self.assertRaisesRegex(backup_tool.BackupError, "fotografia iniziale verificata"):
            self.create(backup_id="20261024T120011Z-abcdef123459")
        current_state_path.write_bytes(trusted_state)
        current_state_path.chmod(0o600)
        state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        locks_fd = os.open(self.locks, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            backup_tool.release_state.append_operation_event(
                state_fd, locks_fd, "txn-interrupted", "prepared", {"fixture": True})
        finally:
            os.close(locks_fd)
            os.close(state_fd)
        with self.assertRaisesRegex(backup_tool.BackupError, "(?i)operazione incompleta"):
            self.create(backup_id="20261024T120010Z-abcdef123458")
        before = list(self.staging.iterdir())
        with self.assertRaisesRegex(backup_tool.BackupError, "(?i)operazione incompleta"):
            backup_tool.restore_test(
                current_id, self.baseline_sha, current["manifest_sha256"], 10**9,
                private_root=self.private, expected_private_root=self.private,
            )
        self.assertEqual(list(self.staging.iterdir()), before)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BackupToolTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and result.skipped:
        print("ERRORE: la CI non può superare la validazione con test saltati.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(not result.wasSuccessful())
