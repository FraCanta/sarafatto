#!/usr/bin/env python3
"""Test di protocollo per release successive, rollback e snapshot backup storici."""

import copy
import hashlib
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

try:
    import fcntl
except ImportError:  # Windows: i test POSIX vengono marcati come skipped.
    fcntl = None

import backup_tool
import release_state_tool as state_tool


COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
COMMIT_C = "c" * 40
TOOL_SHA = "d" * 40
BASELINE_SHA = "e" * 64
if os.environ.get("SARAFATTO_REQUIRE_POSIX") == "1" and os.name != "posix":
    raise RuntimeError("CI richiede POSIX per i test d'integrazione backup/release-state.")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _rows(content_map):
    rows = []
    for path, (content, classification) in sorted(content_map.items()):
        rows.append({"path": path, "sha256": _sha(content), "size": len(content),
                     "mode": "644", "classification": classification})
    return rows


def _state_a(baseline_sha=BASELINE_SHA):
    content = {
        "themes/sarafatto/functions.php": (b"A theme", "artifact"),
        "plugins/sarafatto-core/plugin.php": (b"A plugin", "artifact"),
        "mu-plugins/sarafatto-polylang-front-page-url.php": (b"A mu", "artifact"),
    }
    for index in range(8):
        content[f"themes/sarafatto/assets/dist/assets/app-old{index:02d}.js"] = (
            f"old bundle {index}".encode(), "retained-vite-bundle")
    content["plugins/sarafatto-core/includes/home-hero.php.bak"] = (b"approved backup", "retained-backup")
    reference = _rows(content)
    files = [{"path": row["path"], **{key: row[key] for key in ("sha256", "size", "mode")}}
             for row in reference]
    inventory = {"files": files, "symlinks": [],
                 "exclusion": {"path": "themes/sarafatto/node_modules/", "files": 91, "symlinks": 2}}
    inventory_sha = state_tool.inventory_digest_json(inventory)
    state = {
        "schema_version": 1,
        "initial_baseline": {"sha256": baseline_sha, "commit_sha": COMMIT_A,
                             "release_id": "bootstrap-aaaaaaaaaaaa"},
        "release": {"commit_sha": COMMIT_A, "release_id": "bootstrap-aaaaaaaaaaaa",
                    "inventory_sha256": inventory_sha, "inventory_tool_commit": COMMIT_A},
        "inventory_sha256": inventory_sha, "inventory": inventory, "reference_files": reference,
        "pre_deploy_backup": None, "candidate_release": None, "active_operation": None,
        "last_successful_operation": {"operation_id": "baseline-bootstrap-aaaaaaaaaaaa",
                                       "kind": "verified-content-bootstrap", "status": "verified",
                                       "completed_at_utc": "2026-10-27T10:00:00Z"},
        "provenance": {"kind": "initial-baseline-content-match",
                       "baseline_provenance": "bootstrap-content-match"},
        "verification": {"status": "verified-current", "verified_at_utc": "2026-10-27T10:00:00Z",
                         "fresh_inventory_count": 2, "public_files": len(files), "managed_symlinks": 0},
        "timestamp_utc": "2026-10-27T10:00:00Z",
    }
    state["state_sha256"] = state_tool.digest_json(state)
    return state_tool.validate_state_document(state, baseline_sha)


def _backup_for(state, number):
    return {"backup_id": f"20261027T10000{number}Z-{number:012x}",
            "manifest_sha256": f"{number:064x}", "release_id": state["release"]["release_id"],
            "inventory_sha256": state["inventory_sha256"],
            "baseline_sha256": state["initial_baseline"]["sha256"]}


def _transition(state, operation_id, release_id, commit, suffix, *, kind="publish", target=None,
                content_change=True):
    rows = copy.deepcopy(state["reference_files"])
    managed = next(row for row in rows if row["path"] == "themes/sarafatto/functions.php")
    if content_change:
        payload = f"{suffix} theme".encode()
        managed.update({"sha256": _sha(payload), "size": len(payload)})
    backup = _backup_for(state, ord(suffix[0].lower()) - ord("a") + 1)
    plan, _ = state_tool.make_application_release_plan(
        state, rows, operation_id, operation_kind=kind,
        rollback_target_release_id=target)
    return state_tool.build_application_release_state(
        state, release_id=release_id, commit_sha=commit, inventory_tool_commit=TOOL_SHA,
        operation_id=operation_id, operation_kind=kind,
        artifact_sha256=("f" * 64 if kind == "publish" else None), backup=backup,
        reference_files=rows, plan=plan, rollback_target_release_id=target,
        health_evidence_sha256="9" * 64,
        verified_at_utc=f"2026-10-27T10:00:0{operation_id[-1]}Z")


def _journal_for(state):
    events, previous = [], "0" * 64
    for entry in state["release_chain"]["entries"]:
        terminal_status = "release_committed" if entry["operation_kind"] == "publish" else "release_rolled_back"
        details = {"operation_kind": entry["operation_kind"], "release_id": entry["release_id"],
                   "commit_sha": entry["commit_sha"], "artifact_sha256": entry["artifact_sha256"],
                   "plan_sha256": entry["plan_sha256"], "backup_id": entry["backup"]["backup_id"],
                   "backup_manifest_sha256": entry["backup"]["manifest_sha256"],
                   "parent_release_id": entry["parent_release_id"],
                   "parent_inventory_sha256": entry["parent_inventory_sha256"],
                   "parent_state_sha256": entry["parent_state_sha256"],
                   "parent_document_sha256": entry["parent_document_sha256"],
                   "final_inventory_sha256": entry["inventory_sha256"],
                   "health_evidence_sha256": entry["health_evidence_sha256"],
                   "entry_sha256": entry["entry_sha256"]}
        steps = ["prepared", "backup_verified", "publishing", "files_verified", "health_verified",
                 terminal_status]
        for status in steps:
            if status == "prepared":
                event_details = {
                    "operation_kind": entry["operation_kind"], "release_id": entry["release_id"],
                    "commit_sha": entry["commit_sha"], "artifact_sha256": entry["artifact_sha256"],
                    "plan_sha256": entry["plan_sha256"], "backup_id": entry["backup"]["backup_id"],
                    "backup_manifest_sha256": entry["backup"]["manifest_sha256"],
                    "parent_release_id": entry["parent_release_id"],
                    "parent_inventory_sha256": entry["parent_inventory_sha256"],
                    "parent_state_sha256": entry["parent_state_sha256"],
                    "parent_document_sha256": entry["parent_document_sha256"],
                    "final_inventory_sha256": entry["inventory_sha256"],
                    "plan": entry["plan"], "entry_sha256": entry["entry_sha256"],
                }
            elif status == "backup_verified":
                event_details = {"backup_id": entry["backup"]["backup_id"],
                                 "manifest_sha256": entry["backup"]["manifest_sha256"],
                                 "release_id": entry["backup"]["release_id"],
                                 "inventory_sha256": entry["backup"]["inventory_sha256"],
                                 "baseline_sha256": entry["backup"]["baseline_sha256"]}
            elif status == "publishing":
                event_details = {"entry_sha256": entry["entry_sha256"],
                                 "plan_sha256": entry["plan_sha256"]}
            elif status == "files_verified":
                event_details = {"entry_sha256": entry["entry_sha256"],
                                 "final_inventory_sha256": entry["inventory_sha256"]}
            elif status == "health_verified":
                event_details = {"entry_sha256": entry["entry_sha256"],
                                 "health_evidence_sha256": entry["health_evidence_sha256"]}
            else:
                event_details = details
            row = {"operation_id": entry["operation_id"], "status": status,
                   "timestamp_utc": "2026-10-27T10:00:00Z",
                   "details": event_details,
                   "previous_event_sha256": previous}
            row["event_sha256"] = state_tool.digest_json(row)
            previous = row["event_sha256"]
            events.append(row)
    return events


class ApplicationReleaseStateTests(unittest.TestCase):
    def test_bootstrap_b_c_rollback_b_nuova_release_e_nove_extra(self):
        a = _state_a()
        b = _transition(a, "txn-b", "release-b", COMMIT_B, "B")
        c = _transition(b, "txn-c", "release-c", COMMIT_C, "C")
        b_snapshot = state_tool.resolve_release_snapshot(c, "release-b", b["inventory_sha256"])
        rollback_state = copy.deepcopy(c)
        rollback_rows = copy.deepcopy(b_snapshot)
        rollback_plan, _ = state_tool.make_application_release_plan(
            c, rollback_rows, "txn-r", operation_kind="rollback", rollback_target_release_id="release-b")
        r = state_tool.build_application_release_state(
            c, release_id="rollback-b", commit_sha=COMMIT_B, inventory_tool_commit=TOOL_SHA,
            operation_id="txn-r", operation_kind="rollback", artifact_sha256=None,
            backup=_backup_for(c, 3), reference_files=rollback_rows, plan=rollback_plan,
            health_evidence_sha256="9" * 64,
            rollback_target_release_id="release-b", verified_at_utc="2026-10-27T10:00:03Z")
        d = _transition(r, "txn-d", "release-d", "f" * 40, "D")
        self.assertEqual(len(d["release_chain"]["root"]["reference_files"]), 12)
        self.assertEqual(len(d["release_chain"]["entries"]), 4)
        self.assertEqual(d["release"]["release_id"], "release-d")
        self.assertEqual(state_tool.resolve_release_snapshot(d, "release-b", b["inventory_sha256"]), b_snapshot)
        self.assertEqual(d["initial_baseline"]["sha256"], BASELINE_SHA)
        self.assertEqual(state_tool.validate_application_release_journal(d, _journal_for(d)), True)

    def test_rifiuta_backup_non_corrente_e_piano_manomesso(self):
        a = _state_a()
        bad_backup = _backup_for(a, 1)
        bad_backup["inventory_sha256"] = "0" * 64
        rows = copy.deepcopy(a["reference_files"])
        plan, _ = state_tool.make_application_release_plan(a, rows, "txn-x")
        with self.assertRaises(state_tool.ReleaseStateError):
            state_tool.build_application_release_state(
                a, release_id="release-x", commit_sha=COMMIT_B, inventory_tool_commit=TOOL_SHA,
                operation_id="txn-x", operation_kind="publish", artifact_sha256="f" * 64,
                backup=bad_backup, reference_files=rows, plan=plan, health_evidence_sha256="9" * 64)
        altered = copy.deepcopy(plan)
        altered["candidate_inventory_sha256"] = "0" * 64
        with self.assertRaises(state_tool.ReleaseStateError):
            state_tool.build_application_release_state(
                a, release_id="release-x", commit_sha=COMMIT_B, inventory_tool_commit=TOOL_SHA,
                operation_id="txn-x", operation_kind="publish", artifact_sha256="f" * 64,
                backup=_backup_for(a, 1), reference_files=rows, plan=altered,
                health_evidence_sha256="9" * 64)

    def test_rifiuta_artifact_digest_mancante_stato_falsificato_e_journal_incompleto(self):
        a = _state_a()
        rows = copy.deepcopy(a["reference_files"])
        plan, _ = state_tool.make_application_release_plan(a, rows, "txn-x")
        with self.assertRaises(state_tool.ReleaseStateError):
            state_tool.build_application_release_state(
                a, release_id="release-x", commit_sha=COMMIT_B, inventory_tool_commit=TOOL_SHA,
                operation_id="txn-x", operation_kind="publish", artifact_sha256="invalid",
                backup=_backup_for(a, 1), reference_files=rows, plan=plan,
                health_evidence_sha256="9" * 64)
        b = _transition(a, "txn-b", "release-b", COMMIT_B, "B")
        forged = copy.deepcopy(b)
        forged["release"]["commit_sha"] = COMMIT_C
        forged.pop("state_sha256")
        forged["state_sha256"] = state_tool.digest_json(forged)
        with self.assertRaises(state_tool.ReleaseStateError):
            state_tool.validate_state_document(forged, BASELINE_SHA)
        events = _journal_for(b)[:-1]
        with self.assertRaises(state_tool.ReleaseStateError):
            state_tool.validate_application_release_journal(b, events)
        altered = copy.deepcopy(b)
        altered["release_chain"]["entries"][0]["artifact_sha256"] = "0" * 64
        entry = altered["release_chain"]["entries"][0]
        entry.pop("entry_sha256")
        entry["entry_sha256"] = state_tool.digest_json(entry)
        altered.pop("state_sha256")
        altered["state_sha256"] = state_tool.digest_json(altered)
        state_tool.validate_state_document(altered, BASELINE_SHA)
        with self.assertRaisesRegex(state_tool.ReleaseStateError, "terminale journal"):
            state_tool.validate_application_release_journal(altered, _journal_for(b))

    def test_inventario_live_deve_corrispondere_due_volte_e_rimozione_deve_essere_approvata(self):
        a = _state_a()
        rows = copy.deepcopy(a["reference_files"])
        removed = next(row for row in rows if row["path"] == "themes/sarafatto/functions.php")
        rows.remove(removed)
        approval_rows = [{"path": removed["path"], "sha256": removed["sha256"]}]
        approval = {"approval_id": "review-123", "reviewer": "owner",
                    "approved_at_utc": "2026-10-27T10:00:00Z",
                    "parent_release_id": a["release"]["release_id"],
                    "parent_inventory_sha256": a["inventory_sha256"],
                    "removals_sha256": state_tool.digest_json(approval_rows)}
        plan, _ = state_tool.make_application_release_plan(
            a, rows, "txn-x", approved_removals=approval_rows, removal_approval=approval)
        candidate = state_tool.build_application_release_state(
            a, release_id="release-x", commit_sha=COMMIT_B, inventory_tool_commit=TOOL_SHA,
            operation_id="txn-x", operation_kind="publish", artifact_sha256="f" * 64,
            backup=_backup_for(a, 1), reference_files=rows, plan=plan,
            health_evidence_sha256="9" * 64)
        remote = ["EXCLUDED\tthemes/sarafatto/node_modules\t5\t0\n"]
        for row in candidate["reference_files"]:
            remote.append(f"FILE\t{row['sha256']}\t{row['size']}\t{row['mode']}\t{row['path']}\n")
        remote.append("END\n")
        raw = "".join(remote)
        state_tool.validate_fresh_release_inventories(candidate, (raw, raw))
        changed = raw.replace(candidate["reference_files"][0]["sha256"], "0" * 64, 1)
        with self.assertRaisesRegex(state_tool.ReleaseStateError, "diverso"):
            state_tool.validate_fresh_release_inventories(candidate, (raw, changed))
        without_approval = copy.deepcopy(approval)
        without_approval["removals_sha256"] = "0" * 64
        with self.assertRaises(state_tool.ReleaseStateError):
            state_tool.make_application_release_plan(
                a, rows, "txn-x", approved_removals=approval_rows, removal_approval=without_approval)

    def test_rifiuta_extra_modificati_rimozioni_non_approvate_e_concorrenza_di_id(self):
        a = _state_a()
        rows = copy.deepcopy(a["reference_files"])
        extra = next(row for row in rows if row["classification"] != "artifact")
        extra["sha256"] = "0" * 64
        with self.assertRaisesRegex(state_tool.ReleaseStateError, "extra"):
            state_tool.make_application_release_plan(a, rows, "txn-x")
        rows = copy.deepcopy(a["reference_files"])
        rows = rows[:-1]
        with self.assertRaisesRegex(state_tool.ReleaseStateError, "Approvazioni rimozione"):
            state_tool.make_application_release_plan(a, rows, "txn-x")
        b = _transition(a, "txn-b", "release-b", COMMIT_B, "B")
        with self.assertRaises(state_tool.ReleaseStateError):
            _transition(b, "txn-b", "release-c", COMMIT_C, "C")

    @unittest.skipUnless(os.name == "posix", "Verifica backup/current-release richiede dir_fd POSIX.")
    def test_backup_usa_snapshot_attivo_e_risolve_snapshot_storico(self):
        a = _state_a()
        b = _transition(a, "txn-b", "release-b", COMMIT_B, "B")
        c = _transition(b, "txn-c", "release-c", COMMIT_C, "C")
        with tempfile.TemporaryDirectory() as temp:
            state_dir = pathlib.Path(temp)
            state_path = state_dir / state_tool.STATE_NAME
            journal_path = state_dir / state_tool.JOURNAL_NAME

            def store(document):
                state_path.write_bytes(state_tool.json_bytes(document))
                state_path.chmod(0o600)
                journal_path.write_text("".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                                                      for event in _journal_for(document)), encoding="utf-8")
                journal_path.chmod(0o600)

            state_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                store(c)
                baseline_document = {"release": {"release_id": "bootstrap-aaaaaaaaaaaa"},
                                     "provenance": "bootstrap-content-match"}
                baseline_expected = {}
                tool_commit, expected_c, reference_c = backup_tool.backup_reference(
                    state_fd, baseline_document, BASELINE_SHA, COMMIT_A, baseline_expected)
                self.assertEqual(tool_commit, TOOL_SHA)
                self.assertEqual(len(expected_c), 12)
                self.assertEqual(sum(row["classification"] != "artifact" for row in expected_c.values()), 9)
                manifest_b = {"reference_state": {"kind": "current-release",
                                                   "state_sha256": "0" * 64,
                                                   "inventory_sha256": b["inventory_sha256"],
                                                   "commit_sha": COMMIT_B, "release_id": "release-b",
                                                   "excluded_node_modules_files": 1,
                                                   "excluded_node_modules_symlinks": 0}}
                expected_b = backup_tool.expected_for_backup_manifest(
                    state_fd, baseline_expected, manifest_b, BASELINE_SHA)
                self.assertEqual(expected_b, {row["path"]: row for row in b["reference_files"]})
                self.assertEqual(reference_c["release_id"], "release-c")
            finally:
                os.close(state_fd)

    @unittest.skipUnless(os.name == "posix", "Promozione atomica private state richiede POSIX.")
    def test_promozione_privata_atomica_richiede_journal_e_live_coerenti(self):
        baseline_raw = b"immutable baseline fixture\n"
        baseline_sha = _sha(baseline_raw)
        a = _state_a(baseline_sha)
        b = _transition(a, "txn-b", "release-b", COMMIT_B, "B")
        rows = b["reference_files"]
        remote = ["EXCLUDED\tthemes/sarafatto/node_modules\t3\t0\n"]
        for row in rows:
            remote.append(f"FILE\t{row['sha256']}\t{row['size']}\t{row['mode']}\t{row['path']}\n")
        remote.append("END\n")
        inventory_text = "".join(remote)
        with tempfile.TemporaryDirectory() as temp:
            private = pathlib.Path(temp) / "private"
            state_dir, locks_dir = private / "state", private / "locks"
            state_dir.mkdir(parents=True)
            locks_dir.mkdir()
            marker = private / state_tool.baseline.MARKER
            marker.write_text(state_tool.baseline.MARKER_VALUE + "\n", encoding="utf-8")
            baseline_path = state_dir / "baseline.json"
            baseline_path.write_bytes(baseline_raw)
            state_path = state_dir / state_tool.STATE_NAME
            state_path.write_bytes(state_tool.json_bytes(a))
            journal_path = state_dir / state_tool.JOURNAL_NAME
            journal_path.write_text("".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                                                      for event in _journal_for(b)), encoding="utf-8")
            (locks_dir / "site-operation.lock").write_bytes(b"")
            for directory in (private, state_dir, locks_dir):
                directory.chmod(0o700)
            for file_path in (marker, baseline_path, state_path, journal_path,
                              locks_dir / "site-operation.lock"):
                file_path.chmod(0o600)
            reader = lambda _sha: inventory_text
            result = state_tool.persist_verified_application_release_state(
                b, a["state_sha256"], private_root=private, expected_root=private,
                baseline_sha256=baseline_sha, inventory_reader=reader)
            self.assertEqual(result["status"], "promoted")
            state_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                self.assertEqual(state_tool.load_current_state(state_fd, baseline_sha)["state_sha256"],
                                 b["state_sha256"])
            finally:
                os.close(state_fd)
            repeated = state_tool.persist_verified_application_release_state(
                b, a["state_sha256"], private_root=private, expected_root=private,
                baseline_sha256=baseline_sha, inventory_reader=reader)
            self.assertEqual(repeated["status"], "already-promoted")

    @unittest.skipUnless(os.name == "posix", "Lock flock e fault injection richiedono POSIX.")
    def test_promozione_lock_occupato_o_rename_fallito_non_cambia_lo_stato(self):
        baseline_raw = b"immutable baseline fixture\n"
        baseline_sha = _sha(baseline_raw)
        a = _state_a(baseline_sha)
        b = _transition(a, "txn-b", "release-b", COMMIT_B, "B")
        inventory_lines = ["EXCLUDED\tthemes/sarafatto/node_modules\t3\t0\n"]
        inventory_lines.extend(
            f"FILE\t{row['sha256']}\t{row['size']}\t{row['mode']}\t{row['path']}\n"
            for row in b["reference_files"])
        inventory_lines.append("END\n")
        inventory_text = "".join(inventory_lines)
        with tempfile.TemporaryDirectory() as temp:
            private = pathlib.Path(temp) / "private"
            state_dir, locks_dir = private / "state", private / "locks"
            state_dir.mkdir(parents=True)
            locks_dir.mkdir()
            (private / state_tool.baseline.MARKER).write_text(
                state_tool.baseline.MARKER_VALUE + "\n", encoding="utf-8")
            (state_dir / "baseline.json").write_bytes(baseline_raw)
            state_path = state_dir / state_tool.STATE_NAME
            state_path.write_bytes(state_tool.json_bytes(a))
            journal_path = state_dir / state_tool.JOURNAL_NAME
            journal_path.write_text("".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                                               for event in _journal_for(b)), encoding="utf-8")
            lock_path = locks_dir / "site-operation.lock"
            lock_path.write_bytes(b"")
            for path in (private, state_dir, locks_dir):
                path.chmod(0o700)
            for path in (private / state_tool.baseline.MARKER, state_dir / "baseline.json",
                         state_path, journal_path, lock_path):
                path.chmod(0o600)
            reader = lambda _sha: inventory_text

            held_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(state_tool.ReleaseStateError):
                    state_tool.persist_verified_application_release_state(
                        b, a["state_sha256"], private_root=private, expected_root=private,
                        baseline_sha256=baseline_sha, inventory_reader=reader)
                state_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    self.assertEqual(state_tool.load_current_state(state_fd, baseline_sha)["state_sha256"],
                                     a["state_sha256"])
                finally:
                    os.close(state_fd)
            finally:
                fcntl.flock(held_fd, fcntl.LOCK_UN)
                os.close(held_fd)

            real_rename = os.rename
            def fail_state_rename(source, destination, *, src_dir_fd=None, dst_dir_fd=None):
                if source.startswith(".current-release.update."):
                    raise OSError("fault injection prima del rename")
                return real_rename(source, destination, src_dir_fd=src_dir_fd,
                                   dst_dir_fd=dst_dir_fd)

            with mock.patch.object(state_tool.os, "rename", side_effect=fail_state_rename):
                with self.assertRaises(state_tool.ReleaseStateError):
                    state_tool.persist_verified_application_release_state(
                        b, a["state_sha256"], private_root=private, expected_root=private,
                        baseline_sha256=baseline_sha, inventory_reader=reader)
            state_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                self.assertEqual(state_tool.load_current_state(state_fd, baseline_sha)["state_sha256"],
                                 a["state_sha256"])
            finally:
                os.close(state_fd)
            self.assertEqual(list(state_dir.glob(".current-release.update.*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
