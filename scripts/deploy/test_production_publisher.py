#!/usr/bin/env python3
"""Test offline del validatore artefatto di produzione (nessun filesystem IONOS)."""

import copy
import hashlib
import json
import os
import pathlib
import shutil
import tarfile
import tempfile
import unittest
from unittest import mock

import production_publisher as publisher
import test_application_release_state as release_state_fixtures
import test_release_state_tool as bootstrap_fixtures


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

    @staticmethod
    def _rehash_journal(events):
        previous = "0" * 64
        for event in events:
            event["previous_event_sha256"] = previous
            event.pop("event_sha256", None)
            event["event_sha256"] = publisher.release_state_tool.digest_json(event)
            previous = event["event_sha256"]
        return events

    def _journal_with_publisher_intent(self, parent, candidate):
        state_tool = publisher.release_state_tool
        entry = candidate["release_chain"]["entries"][-1]
        events = release_state_fixtures._journal_for(candidate)
        operation = events[-6:]
        operation[0]["details"] = publisher._prepared_release_details(
            parent, operation_kind=entry["operation_kind"], release_id=entry["release_id"],
            commit_sha=entry["commit_sha"], artifact_sha256=entry["artifact_sha256"],
            backup_reference=entry["backup"], plan=entry["plan"], manifest_sha256="1" * 64)
        operation[2]["details"] = {"plan_sha256": entry["plan_sha256"]}
        operation[3]["details"] = {"final_inventory_sha256": entry["inventory_sha256"]}
        operation[4]["details"] = {
            "health_evidence_sha256": entry["health_evidence_sha256"],
            "candidate_state_sha256": hashlib.sha256(state_tool.json_bytes(candidate)).hexdigest(),
        }
        return self._rehash_journal(events)

    def test_journal_publisher_distingue_parent_catena_e_documento(self):
        state_tool = publisher.release_state_tool
        fixtures = release_state_fixtures
        a = fixtures._state_a()
        b = fixtures._transition(a, "txn-b", "release-b", fixtures.COMMIT_B, "B")
        c = fixtures._transition(b, "txn-c", "release-c", fixtures.COMMIT_C, "C")
        plan, _ = state_tool.make_application_release_plan(
            c, b["reference_files"], "txn-r", operation_kind="rollback",
            rollback_target_release_id="release-b")
        rollback = state_tool.build_application_release_state(
            c, release_id="rollback-b", commit_sha=fixtures.COMMIT_B,
            inventory_tool_commit=fixtures.TOOL_SHA, operation_id="txn-r", operation_kind="rollback",
            artifact_sha256=None, backup=fixtures._backup_for(c, 4), reference_files=b["reference_files"],
            plan=plan, rollback_target_release_id="release-b", health_evidence_sha256="9" * 64)
        for parent, candidate in ((a, b), (b, c), (c, rollback)):
            with self.subTest(release=candidate["release"]["release_id"]):
                events = self._journal_with_publisher_intent(parent, candidate)
                entry = candidate["release_chain"]["entries"][-1]
                prepared = events[-6]["details"]
                self.assertNotEqual(entry["parent_state_sha256"], parent["state_sha256"])
                self.assertEqual(prepared["parent_state_sha256"], entry["previous_entry_sha256"])
                self.assertEqual(prepared["parent_document_sha256"], parent["state_sha256"])
                expected = copy.deepcopy(fixtures._journal_for(candidate)[-6]["details"])
                del expected["entry_sha256"], expected["final_inventory_sha256"]
                expected["transaction_manifest_sha256"] = "1" * 64
                self.assertEqual(prepared, expected)
                self.assertTrue(state_tool.validate_application_release_journal(candidate, events))

    def test_journal_publisher_rifiuta_parent_confusi_e_dettagli_intermedi_alterati(self):
        fixtures = release_state_fixtures
        a = fixtures._state_a()
        b = fixtures._transition(a, "txn-b", "release-b", fixtures.COMMIT_B, "B")
        events = self._journal_with_publisher_intent(a, b)
        mutations = (
            (0, "parent_state_sha256", a["state_sha256"]),
            (0, "parent_document_sha256", b["release_chain"]["root"]["entry_sha256"]),
            (0, "parent_release_id", "release-estranea"),
            (0, "operation_kind", "rollback"),
            (0, "transaction_manifest_sha256", "digest-non-valido"),
            (1, "manifest_sha256", "0" * 64),
            (2, "plan_sha256", "0" * 64),
            (3, "final_inventory_sha256", "0" * 64),
            (4, "health_evidence_sha256", "0" * 64),
        )
        for index, field, value in mutations:
            with self.subTest(event=index, field=field):
                altered = copy.deepcopy(events)
                altered[index]["details"][field] = value
                self._rehash_journal(altered)
                with self.assertRaises(publisher.release_state_tool.ReleaseStateError):
                    publisher.release_state_tool.validate_application_release_journal(b, altered)
        for missing in range(5):
            with self.subTest(missing_event=missing):
                incomplete = copy.deepcopy(events)
                del incomplete[missing]
                with self.assertRaises(publisher.release_state_tool.ReleaseStateError):
                    publisher.release_state_tool.validate_application_release_journal(b, incomplete)
        for scenario in ("operation-id", "event-order"):
            with self.subTest(scenario=scenario):
                altered = copy.deepcopy(events)
                if scenario == "operation-id":
                    altered[2]["operation_id"] = "txn-estranea"
                else:
                    altered[2], altered[3] = altered[3], altered[2]
                self._rehash_journal(altered)
                with self.assertRaises(publisher.release_state_tool.ReleaseStateError):
                    publisher.release_state_tool.validate_application_release_journal(b, altered)

    def test_piano_rollback_bundle_nuovo_richiede_rimozione_esatta(self):
        fixtures = release_state_fixtures
        state_tool = publisher.release_state_tool
        a = fixtures._state_a()
        new_path = "themes/sarafatto/assets/dist/assets/chunk-B.js"
        records = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                   for row in a["reference_files"] if row["classification"] == "artifact"}
        records[new_path] = {"sha256": "1" * 64, "size": 1, "mode": "644"}
        publish_plan = publisher.make_release_state_plan(a, records, "txn-b")
        b = state_tool.build_application_release_state(
            a, release_id="release-b", commit_sha=fixtures.COMMIT_B,
            inventory_tool_commit=fixtures.TOOL_SHA, operation_id="txn-b", operation_kind="publish",
            artifact_sha256="f" * 64, backup=fixtures._backup_for(a, 1),
            reference_files=publish_plan["candidate_reference_files"], plan=publish_plan["plan"],
            health_evidence_sha256="9" * 64)
        target = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                  for row in a["reference_files"]}
        removals = [{"path": new_path, "sha256": "1" * 64}]
        approval = {"approval_id": "approve-r", "reviewer": "fixture",
                    "approved_at_utc": "2026-10-28T10:00:00Z",
                    "parent_release_id": b["release"]["release_id"],
                    "parent_inventory_sha256": b["inventory_sha256"],
                    "removals_sha256": state_tool.digest_json(removals)}
        kwargs = {"operation_kind": "rollback", "rollback_target_release_id": a["release"]["release_id"]}
        result = publisher.make_release_state_plan(
            b, target, "txn-r", approved_removals=removals, removal_approval=approval, **kwargs)
        self.assertEqual(result["candidate_reference_files"], a["reference_files"])
        self.assertEqual(result["plan"]["approved_removals"], removals)
        self.assertEqual(len([row for row in result["candidate_reference_files"]
                              if row["classification"] != "artifact"]), 9)
        rollback = state_tool.build_application_release_state(
            b, release_id="rollback-a", commit_sha=fixtures.COMMIT_A,
            inventory_tool_commit=fixtures.COMMIT_A, operation_id="txn-r", operation_kind="rollback",
            artifact_sha256=None, backup=fixtures._backup_for(b, 2),
            reference_files=result["candidate_reference_files"], plan=result["plan"],
            rollback_target_release_id=a["release"]["release_id"], health_evidence_sha256="9" * 64)
        self.assertTrue(state_tool.validate_application_release_journal(
            rollback, self._journal_with_publisher_intent(b, rollback)))
        with self.assertRaises(state_tool.ReleaseStateError):
            publisher.make_release_state_plan(b, target, "txn-r", **kwargs)
        wrong = [{"path": new_path, "sha256": "0" * 64}]
        with self.assertRaises(state_tool.ReleaseStateError):
            publisher.make_release_state_plan(b, target, "txn-r", approved_removals=wrong,
                                              removal_approval=approval, **kwargs)

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

    def _release_fixture(self):
        fixture = bootstrap_fixtures.ReleaseStateTests("test_01_bootstrap_valido_e_non_sovrascrivibile")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        # La baseline di test contiene tutti i nove extra approvati, come il caso IONOS.
        for index in range(2, 9):
            path = f"themes/sarafatto/assets/dist/assets/app-old{index:02d}Ab12.js"
            data = f"old bundle {index}".encode()
            fixture.files[path] = (data, "retained-vite-bundle", "644")
            target = fixture.public / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o644)
        fixture.write_baseline()
        fixture.approved_baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        for name in ("backups", "staging"):
            path = fixture.private / name
            path.mkdir()
            if os.name == "posix":
                path.chmod(0o700)
        fixture.bootstrap()
        self.assertEqual(len([row for row in fixture.files.values()
                              if row[1] == "retained-vite-bundle"]) + 1, 9)
        return fixture

    @staticmethod
    def _inventory_reader(public, excluded_files=2):
        def read(_commit):
            records = publisher.inventory_target_tree(public)
            lines = [f"EXCLUDED\t{publisher.baseline_tool.EXCLUDED}\t{excluded_files}\t0\n"]
            lines.extend(f"FILE\t{row['sha256']}\t{row['size']}\t{row['mode']}\t{path}\n"
                         for path, row in sorted(records.items()))
            lines.append("END\n")
            return "".join(lines)
        return read

    def _stage_release_inputs(self, fixture):
        staging = fixture.private / "staging"
        package = staging / "artifact-package"
        shutil.copytree(self.package, package)
        paths = {}
        for label, source in (("inventory", self.inventory), ("provenance", self.provenance),
                              ("archive", self.archive)):
            destination = staging / f"artifact-{label}"
            shutil.copyfile(source, destination)
            paths[label] = destination
        paths["package"] = package
        return paths

    @staticmethod
    def _removal_approval(state, removed_path, approval_id):
        row = next(row for row in state["reference_files"] if row["path"] == removed_path)
        removals = [{"path": removed_path, "sha256": row["sha256"]}]
        return removals, {
            "approval_id": approval_id, "reviewer": "fixture-reviewer",
            "approved_at_utc": "2026-10-27T12:00:00Z",
            "parent_release_id": state["release"]["release_id"],
            "parent_inventory_sha256": state["inventory_sha256"],
            "removals_sha256": publisher.release_state_tool.digest_json(removals),
        }

    @staticmethod
    def _journal_events(fixture):
        fd = os.open(fixture.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            return publisher.release_state_tool.read_journal_at(fd)
        finally:
            os.close(fd)

    def _publish_fixture_b(self, fixture, *, fault_hook=None, health_check=None):
        paths = self._stage_release_inputs(fixture)
        baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        state = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        removals, approval = self._removal_approval(
            state, "themes/sarafatto/front-page.php", "approve-remove-front-page")
        reader = self._inventory_reader(fixture.public)
        return publisher.publish_filesystem_release(
            package_root=paths["package"], inventory_path=paths["inventory"],
            provenance_path=paths["provenance"], archive_path=paths["archive"],
            release_sha="a" * 40, run_id="12345", release_id="release-B-fixture",
            operation_id="publish-B-fixture", quota_free_bytes=10**10,
            private_root=fixture.private, expected_private_root=fixture.private,
            public_root=fixture.public, expected_public_root=fixture.public,
            health_check=health_check or (lambda: {"status": "healthy", "check": "fixture"}),
            rollback_health_check=lambda: {"status": "healthy", "check": "fixture-parent"},
            inventory_reader=reader, approved_removals=removals,
            removal_approval=approval, fault_hook=fault_hook)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Orchestrazione reale su filesystem richiede POSIX e openat.")
    def test_orchestrazione_publish_B_health_e_rollback_A_con_nove_extra(self):
        fixture = self._release_fixture()
        baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        state_a = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        parent_bytes = {path: fixture.public.joinpath(*path.split("/")).read_bytes()
                        for path in fixture.files}
        sentinels = {
            "uploads/product.txt": b"cms product data",
            "plugins/woocommerce/plugin.php": b"third-party plugin",
            "wp-core-version.php": b"wordpress core sentinel",
        }
        for relative, payload in sentinels.items():
            path = fixture.public / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

        checked_phases = set()

        def assert_lock_held(event, _path=None, _count=None):
            with self.assertRaisesRegex(publisher.baseline_tool.BaselineError, "già occupato"):
                publisher.baseline_tool.acquire_baseline_lock(fixture.locks)
            checked_phases.add(event)

        def healthy_with_lock():
            assert_lock_held("health")
            return {"status": "healthy", "check": "fixture"}

        published = self._publish_fixture_b(fixture, fault_hook=assert_lock_held,
                                          health_check=healthy_with_lock)
        self.assertTrue({"after-file", "after-health-verified", "after-terminal", "health"}
                        .issubset(checked_phases))
        self.assertEqual(published["status"], "published")
        self.assertTrue(published["public_writes_performed"])
        state_b = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        self.assertEqual(state_b["release"]["release_id"], "release-B-fixture")
        self.assertEqual(publisher.inventory_target_tree(fixture.public), {
            row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
            for row in state_b["reference_files"]})
        for path, payload in sentinels.items():
            self.assertEqual((fixture.public / path).read_bytes(), payload)
        for path, payload in parent_bytes.items():
            if "app-old" in path or path.endswith("home-hero.php.bak"):
                self.assertEqual(fixture.public.joinpath(*path.split("/")).read_bytes(), payload)

        target_rows = state_a["reference_files"]
        target_paths = {row["path"] for row in target_rows}
        removals = [{"path": row["path"], "sha256": row["sha256"]}
                    for row in state_b["reference_files"]
                    if row["path"] not in target_paths and row["classification"] == "artifact"]
        removals.sort(key=lambda row: row["path"])
        rollback_approval = {
            "approval_id": "approve-rollback-fixture", "reviewer": "fixture-reviewer",
            "approved_at_utc": "2026-10-27T12:10:00Z",
            "parent_release_id": state_b["release"]["release_id"],
            "parent_inventory_sha256": state_b["inventory_sha256"],
            "removals_sha256": publisher.release_state_tool.digest_json(removals),
        }
        backup = published["backup"]
        rolled_back = publisher.rollback_filesystem_release(
            target_release_id=state_a["release"]["release_id"], backup_id=backup["backup_id"],
            manifest_sha256=backup["manifest_sha256"], operation_id="rollback-B-to-A-fixture",
            quota_free_bytes=10**10, private_root=fixture.private,
            expected_private_root=fixture.private, public_root=fixture.public,
            expected_public_root=fixture.public,
            health_check=healthy_with_lock,
            rollback_health_check=lambda: {"status": "healthy", "check": "fixture-parent"},
            inventory_reader=self._inventory_reader(fixture.public),
            approved_removals=removals, removal_approval=rollback_approval,
            fault_hook=assert_lock_held)
        self.assertEqual(rolled_back["status"], "rolled-back")
        state_after = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        self.assertEqual(state_after["release_chain"]["entries"][-1]["rollback_target_release_id"],
                         state_a["release"]["release_id"])
        self.assertEqual(publisher.inventory_target_tree(fixture.public), {
            row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
            for row in state_a["reference_files"]})
        for path, payload in sentinels.items():
            self.assertEqual((fixture.public / path).read_bytes(), payload)
        for path, payload in parent_bytes.items():
            self.assertEqual(fixture.public.joinpath(*path.split("/")).read_bytes(), payload)
        events = self._journal_events(fixture)
        self.assertEqual(events[-1]["status"], "release_rolled_back")
        released_lock = publisher.baseline_tool.acquire_baseline_lock(fixture.locks)
        import fcntl
        fcntl.flock(released_lock, fcntl.LOCK_UN)
        os.close(released_lock)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Esclusione concorrente richiede flock POSIX.")
    def test_orchestrazione_lock_occupato_non_scrive_file_stato_o_journal(self):
        fixture = self._release_fixture()
        before = publisher.inventory_target_tree(fixture.public)
        state_path = fixture.state / publisher.release_state_tool.STATE_NAME
        state_before = state_path.read_bytes()
        journal_path = fixture.state / publisher.release_state_tool.JOURNAL_NAME
        journal_before = journal_path.read_bytes() if journal_path.exists() else None
        lock_fd = publisher.baseline_tool.acquire_baseline_lock(fixture.locks)
        try:
            with self.assertRaisesRegex(publisher.PublisherError, "Lock baseline già occupato"):
                self._publish_fixture_b(fixture)
            self.assertEqual(publisher.inventory_target_tree(fixture.public), before)
            self.assertEqual(state_path.read_bytes(), state_before)
            self.assertEqual(journal_path.read_bytes() if journal_path.exists() else None, journal_before)
            self.assertEqual(list((fixture.private / "backups").iterdir()), [])
        finally:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Rollback automatico end-to-end richiede filesystem POSIX.")
    def test_orchestrazione_health_check_fallito_ripristina_A(self):
        fixture = self._release_fixture()
        baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        state_a = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        parent = {path: target.read_bytes() for path in fixture.files
                  if (target := fixture.public.joinpath(*path.split("/"))).is_file()}

        def unhealthy_after_publish():
            return {"status": "unhealthy", "check": "fixture-B"}

        with self.assertRaisesRegex(publisher.PublisherError, "rollback al parent ripristinato"):
            self._publish_fixture_b(fixture, health_check=unhealthy_after_publish)

        current = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        self.assertEqual(current["state_sha256"], state_a["state_sha256"])
        actual = publisher.inventory_target_tree(fixture.public)
        expected = {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                    for row in state_a["reference_files"]}
        self.assertEqual(actual, expected)
        for relative, data in parent.items():
            self.assertEqual(fixture.public.joinpath(*relative.split("/")).read_bytes(), data)
        events = self._journal_events(fixture)
        self.assertEqual(events[-1]["status"], "recovery_completed")
        self.assertNotIn("release_committed", [event["status"] for event in events])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Fault injection transazionale richiede filesystem POSIX.")
    def test_orchestrazione_interruzione_file_e_recovery_al_parent(self):
        fixture = self._release_fixture()

        class SimulatedProcessCrash(BaseException):
            pass

        def crash(event, _path, count):
            if event == "after-file" and count == 2:
                raise SimulatedProcessCrash("crash dopo due scritture")

        with self.assertRaises(SimulatedProcessCrash):
            self._publish_fixture_b(fixture, fault_hook=crash)
        baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        before = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        recovered = publisher.recover_filesystem_release(
            operation_id="publish-B-fixture", private_root=fixture.private,
            expected_private_root=fixture.private, public_root=fixture.public,
            expected_public_root=fixture.public, quota_free_bytes=10**10,
            health_check=lambda: {"status": "healthy", "check": "fixture-recovered-parent"},
            inventory_reader=self._inventory_reader(fixture.public))
        self.assertEqual(recovered["status"], "recovery_completed")
        after = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        self.assertEqual(after["state_sha256"], before["state_sha256"])
        self.assertEqual(publisher.inventory_target_tree(fixture.public), {
            row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
            for row in before["reference_files"]})
        self.assertEqual(self._journal_events(fixture)[-1]["status"], "recovery_completed")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Recovery post-terminal richiede filesystem POSIX.")
    def test_orchestrazione_interruzione_dopo_terminale_finalizza_release(self):
        fixture = self._release_fixture()

        class SimulatedProcessCrash(BaseException):
            pass

        def crash(event, _path, _count):
            if event == "after-terminal":
                raise SimulatedProcessCrash("crash dopo terminale journal")

        with self.assertRaises(SimulatedProcessCrash):
            self._publish_fixture_b(fixture, fault_hook=crash)
        baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        result = publisher.recover_filesystem_release(
            operation_id="publish-B-fixture", private_root=fixture.private,
            expected_private_root=fixture.private, public_root=fixture.public,
            expected_public_root=fixture.public, quota_free_bytes=10**10,
            health_check=lambda: {"status": "healthy", "check": "fresh-recovery-check"},
            inventory_reader=self._inventory_reader(fixture.public))
        self.assertEqual(result["status"], "finalized-after-interruption")
        self.assertEqual(result["health_evidence"]["check"], "fresh-recovery-check")
        final = publisher.release_state_tool.validate_state_document(
            json.loads((fixture.state / publisher.release_state_tool.STATE_NAME).read_text(encoding="utf-8")),
            baseline_sha)
        self.assertEqual(final["release"]["release_id"], "release-B-fixture")

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
        # La fixture rimuove intenzionalmente obsolete.php: la pubblicazione
        # interrotta deve ricevere la stessa approvazione esplicita path+SHA
        # richiesta a una pubblicazione completata.
        obsolete_sha = hashlib.sha256(parent_content["themes/sarafatto/obsolete.php"]).hexdigest()
        removal_approval = [{"path": "themes/sarafatto/obsolete.php", "sha256": obsolete_sha}]
        counter = {"writes": 0}

        def interrupt(event, path, count):
            counter["writes"] = count
            if count == 2:
                raise RuntimeError("fault injection after second file")

        with self.assertRaisesRegex(RuntimeError, "fault injection"):
            publisher.apply_file_snapshot(self.package, target, parent_rows, candidate_rows,
                                           approved_removals=removal_approval,
                                           fault_hook=interrupt)
        self.assertEqual(counter["writes"], 2)
        before_recovery = publisher.inventory_target_tree(target)
        self.assertNotEqual(before_recovery, {row["path"]: {key: row[key] for key in ("sha256", "size", "mode")}
                                               for row in parent_rows})
        recovered = publisher.recover_file_snapshot(backup, target, parent_rows, candidate_rows)
        self.assertEqual(recovered["inventory"], publisher.inventory_target_tree(backup))
        self.assertTrue((target / "themes/sarafatto/obsolete.php").is_file())
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

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Il writer dir_fd/O_NOFOLLOW si valida obbligatoriamente su Ubuntu CI.")
    def test_filesystem_add_collisione_non_sovrascrive_e_symlink_bloccato(self):
        target = self.root / "wp-content-collision"
        target.mkdir()
        parent_content = self._fake_wp_a(target)
        extras = {
            **{f"themes/sarafatto/assets/dist/assets/app-old{index:02d}.js": "retained-vite-bundle"
               for index in range(8)},
            "plugins/sarafatto-core/includes/home-hero.php.bak": "retained-backup",
        }
        parent_rows = self._rows_from_content(parent_content, extras)
        candidate_content = dict(self.contents)
        candidate_content.update({path: parent_content[path] for path in extras})
        candidate_rows = self._rows_from_content(candidate_content, extras)
        removal_approval = [{
            "path": "themes/sarafatto/obsolete.php",
            "sha256": hashlib.sha256(parent_content["themes/sarafatto/obsolete.php"]).hexdigest(),
        }]

        real_link = os.link

        def create_racing_collision(source, destination, *, src_dir_fd=None, dst_dir_fd=None,
                                    follow_symlinks=True):
            if destination == "chunk-0.js":
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
                             dir_fd=dst_dir_fd)
                try:
                    os.write(fd, b"concurrent unapproved file")
                finally:
                    os.close(fd)
            return real_link(source, destination, src_dir_fd=src_dir_fd,
                             dst_dir_fd=dst_dir_fd, follow_symlinks=follow_symlinks)

        with mock.patch.object(publisher.os, "link", side_effect=create_racing_collision):
            with self.assertRaisesRegex(publisher.PublisherError, "Destinazione nuova già esistente"):
                publisher.apply_file_snapshot(
                    self.package, target, parent_rows, candidate_rows,
                    approved_removals=removal_approval)
        collision = target / "themes/sarafatto/assets/dist/assets/chunk-0.js"
        self.assertEqual(collision.read_bytes(), b"concurrent unapproved file")

        symlink_target = self.root / "wp-content-symlink"
        symlink_target.mkdir()
        self._fake_wp_a(symlink_target)
        managed_file = symlink_target / "themes/sarafatto/functions.php"
        managed_file.unlink()
        outside = self.root / "outside-functions.php"
        outside.write_bytes(b"must not be followed")
        managed_file.symlink_to(outside)
        with self.assertRaisesRegex(publisher.PublisherError, "Symlink nel perimetro gestito"):
            publisher.inventory_target_tree(symlink_target)

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

    def test_allowlist_directory_radice_distinta_dai_file_pubblicabili(self):
        self.assertEqual(publisher._target_directory_parts("themes/sarafatto"),
                         ["themes", "sarafatto"])
        self.assertEqual(publisher._target_directory_parts("plugins/sarafatto-core"),
                         ["plugins", "sarafatto-core"])
        for path in ("themes", "plugins", "mu-plugins", "themes/altro",
                     "plugins/altro", "themes/sarafatto/../altro", "/themes/sarafatto"):
            with self.subTest(path=path):
                with self.assertRaises(publisher.PublisherError):
                    publisher._target_directory_parts(path)
        self.assertEqual(publisher._target_path_parts("themes/sarafatto/functions.php"),
                         ["themes", "sarafatto", "functions.php"])
        self.assertEqual(publisher._target_path_parts(
            "mu-plugins/sarafatto-polylang-front-page-url.php"),
            ["mu-plugins", "sarafatto-polylang-front-page-url.php"])
        for path in ("themes/sarafatto", "themes/other/functions.php",
                     "plugins/other/plugin.php", "mu-plugins/other.php", "../wp-config.php"):
            with self.subTest(file_path=path):
                with self.assertRaises(publisher.PublisherError):
                    publisher._target_path_parts(path)

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
