#!/usr/bin/env python3
"""Test offline POSIX del preflight/transazione/rollback fixture-only."""

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import threading
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("transaction_fixture_tool.py")
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("transaction_fixture_tool", MODULE_PATH)
tx = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tx
SPEC.loader.exec_module(tx)
release_state = tx.release_state
baseline = tx.baseline

FLOCK_REQUIRED = os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1"
if FLOCK_REQUIRED and (tx.fcntl is None or os.name != "posix"):
    raise RuntimeError("flock/POSIX assenti: i test transazionali non possono essere saltati in CI.")

CURRENT_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40
RUN_URL = "https://github.com/FraCanta/sarafatto/actions/runs/40106509533"
EXTRA_BUNDLES = tuple(
    f"themes/sarafatto/assets/dist/assets/{name}"
    for name in (
        "app-OldAb12.js", "home-OldCd34.js", "product-OldEf56.js",
        "product-archive-OldGh78.js", "vendor-OldIj90.js", "gsap-OldKl12.js",
        "lenis-OldMn34.js", "chunk-OldOp56.js",
    )
)
EXTRA_BUNDLE = EXTRA_BUNDLES[0]
EXTRA_BACKUP = "plugins/sarafatto-core/includes/home-hero.php.bak"


def digest(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(tx.fcntl is not None and os.name == "posix", "motore fixture richiede Ubuntu/POSIX")
class TransactionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tx.create_fixture_workspace()
        self.root = self.workspace.root
        self.current = {
            "themes/sarafatto/front-page.php": (b"old home", "artifact", "644"),
            "themes/sarafatto/obsolete.php": (b"old managed", "artifact", "644"),
            "plugins/sarafatto-core/plugin.php": (b"plugin", "artifact", "644"),
            baseline.SINGLE_FILE: (b"mu", "artifact", "644"),
            **{path: (f"old bundle {index}".encode(), "retained-vite-bundle", "644")
               for index, path in enumerate(EXTRA_BUNDLES)},
            EXTRA_BACKUP: (b"hero backup", "retained-backup", "600"),
        }
        self.candidate = {
            "themes/sarafatto/front-page.php": (b"new home", "artifact", "644"),
            "themes/sarafatto/new-page.php": (b"new managed", "artifact", "644"),
            "plugins/sarafatto-core/plugin.php": (b"plugin", "artifact", "644"),
            baseline.SINGLE_FILE: (b"mu", "artifact", "644"),
        }
        for path, (content, _, mode) in self.current.items():
            self._write_tree_file(self.workspace.public_root, path, content, mode)
        for path, (content, _, mode) in self.candidate.items():
            self._write_tree_file(self.workspace.artifact_root, path, content, mode)
        self._write_vite_assets()
        npm_bin = self.workspace.public_root / "themes/sarafatto/node_modules/.bin"
        npm_bin.mkdir(parents=True, exist_ok=True)
        target = npm_bin.parent / "vite.js"
        target.write_text("local npm dependency", encoding="utf-8")
        (npm_bin / "vite").symlink_to(target)
        self._write_state()
        self.inventory_path = self.root / "artifact-inventory.tsv"
        records = tx._tree_inventory(self.workspace.artifact_root)
        self.inventory_path.write_text("".join(
            f"{row['sha256']}\t{row['size']}\t{path}\n" for path, row in sorted(records.items())
        ), encoding="utf-8")
        self.plan = self.preflight()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def _write_tree_file(root, relative, content, mode="644"):
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(int(mode, 8))

    def _write_vite_assets(self):
        dist = self.workspace.artifact_root / "themes/sarafatto/assets/dist"
        assets = dist / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        manifest = {}
        names = ("app.js", "home.js", "product.js", "product-archive.js")
        for index, name in enumerate(names):
            filename = f"{name.removesuffix('.js')}-Ab12Cd{index}.js"
            (assets / filename).write_text(f"export const entry{index} = true;\n", encoding="utf-8")
            manifest[f"assets/src/js/{name}"] = {
                "file": f"assets/{filename}", "isEntry": True, "imports": [], "css": [], "assets": []
            }
        (dist / ".vite").mkdir(parents=True, exist_ok=True)
        (dist / ".vite/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _write_state(self):
        baseline_path = self.workspace.state_dir / "baseline.json"
        managed, extras, references, inventory_files = [], [], [], []
        for path, (content, classification, mode) in sorted(self.current.items()):
            record = {"path": path, "sha256": digest(content), "size": len(content), "mode": mode}
            if classification == "artifact":
                managed.append(record)
            else:
                extras.append({**record, "classification": classification})
            references.append({**record, "classification": classification})
            inventory_files.append(record)
        baseline_doc = {
            "schema_version": 1,
            "release": {"commit_sha": CURRENT_SHA, "release_id": "bootstrap-aaaaaaaaaaaa",
                        "github_actions_run": RUN_URL},
            "provenance": "bootstrap-content-match",
            "verification": {"status": "initialized-from-verified-content-match", "managed_symlinks": 0},
            "managed_files": managed,
            "accepted_extras": extras,
        }
        raw_baseline = release_state.json_bytes(baseline_doc)
        baseline_path.write_bytes(raw_baseline)
        baseline_path.chmod(0o600)
        baseline_sha = digest(raw_baseline)
        inventory = {"files": inventory_files, "symlinks": [],
                     "exclusion": {"path": baseline.EXCLUDED + "/", "files": 0, "symlinks": 0}}
        inventory_sha = release_state.inventory_digest_json(inventory)
        now = "2026-10-26T12:00:00Z"
        state = {
            "schema_version": 1,
            "initial_baseline": {"sha256": baseline_sha, "commit_sha": CURRENT_SHA,
                                 "release_id": "bootstrap-aaaaaaaaaaaa"},
            "release": {"commit_sha": CURRENT_SHA, "release_id": "bootstrap-aaaaaaaaaaaa",
                        "inventory_sha256": inventory_sha, "inventory_tool_commit": CURRENT_SHA},
            "inventory_sha256": inventory_sha,
            "inventory": inventory,
            "reference_files": references,
            "pre_deploy_backup": None, "candidate_release": None, "active_operation": None,
            "last_successful_operation": {"operation_id": "baseline-bootstrap-aaaaaaaaaaaa",
                                          "kind": "verified-content-bootstrap", "status": "verified",
                                          "completed_at_utc": now},
            "provenance": {"kind": "initial-baseline-content-match",
                           "baseline_provenance": "bootstrap-content-match", "artifact_run": RUN_URL},
            "verification": {"status": "verified-current", "verified_at_utc": now,
                             "fresh_inventory_count": 2, "public_files": len(references),
                             "managed_symlinks": 0},
            "timestamp_utc": now,
        }
        state["state_sha256"] = release_state.digest_json(state)
        self.state_path = self.workspace.state_dir / release_state.STATE_NAME
        self.state_path.write_bytes(release_state.json_bytes(state))
        self.state_path.chmod(0o600)

    def preflight(self, **overrides):
        args = {
            "artifact_inventory_path": self.inventory_path if hasattr(self, "inventory_path") else self.root / "artifact-inventory.tsv",
            "artifact_commit_sha": CANDIDATE_SHA,
            "authorized_commit_sha": CANDIDATE_SHA,
            "quota_free_bytes": 1024 * 1024 * 1024,
        }
        args.update(overrides)
        return tx.preflight(self.workspace, **args)

    def approved_plan(self):
        if self.plan["files_candidate_for_removal"]:
            paths = [row["path"] for row in self.plan["files_candidate_for_removal"]]
            return tx.approve_fixture_removals(
                self.plan, paths,
                confirmation="APPROVE-FIXTURE-REMOVALS " + self.plan["plan_sha256"],
            )
        return self.plan

    def backup(self):
        return tx.create_verified_backup(self.workspace, "backup-fixture-001")

    def publish(self, plan=None, **kwargs):
        selected = plan or self.approved_plan()
        backup = self.backup()
        return tx.simulate_publish(
            self.workspace, selected, authorized_commit_sha=CANDIDATE_SHA,
            backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
            confirmation="PUBLISH-FIXTURE " + selected["plan_sha256"],
            health_check="passed", **kwargs,
        ), backup, selected

    def test_01_preflight_piano_completo_e_extra_conservati(self):
        self.assertEqual(self.plan["mode"], "fixture-only")
        self.assertFalse(self.plan["production_writes_allowed"])
        self.assertEqual(self.plan["candidate_release"]["commit_sha"], CANDIDATE_SHA)
        self.assertEqual(self.plan["files_candidate_for_removal"][0]["path"], "themes/sarafatto/obsolete.php")
        self.assertEqual({row["path"] for row in self.plan["approved_extras"]},
                         set(EXTRA_BUNDLES) | {EXTRA_BACKUP})
        self.assertFalse(any("node_modules" in row["path"] for row in self.plan["artifact_files"]))
        self.assertEqual(len(self.plan["plan_sha256"]), 64)

    def test_01a_mu_plugins_e_contenitore_valido_ma_non_inventariato(self):
        records = tx._tree_inventory(self.workspace.public_root)
        self.assertIn(baseline.SINGLE_FILE, records)
        self.assertNotIn("mu-plugins", records)
        self.assertNotIn("themes", records)
        self.assertNotIn("plugins", records)

    def test_01b_solo_il_mu_plugin_autorizzato_e_un_file_gestito(self):
        self.assertTrue(baseline.safe_path(baseline.SINGLE_FILE))
        self.assertFalse(baseline.safe_path("mu-plugins/other.php"))
        self.assertFalse(baseline.safe_path("mu-plugins/sarafatto-polylang-front-page-url.php/child.php"))

    def test_01c_file_estraneo_in_mu_plugins_rifiutato(self):
        extra = self.workspace.public_root / "mu-plugins/other.php"
        extra.write_text("not managed", encoding="utf-8")
        with self.assertRaisesRegex(tx.TransactionError, "allowlist"):
            tx._tree_inventory(self.workspace.public_root)

    def test_01d_symlink_directory_mu_plugins_rifiutato(self):
        directory = self.workspace.public_root / "mu-plugins"
        saved = self.workspace.public_root / "mu-plugins-saved"
        directory.rename(saved)
        directory.symlink_to(saved, target_is_directory=True)
        with self.assertRaisesRegex(tx.TransactionError, "Symlink"):
            tx._tree_inventory(self.workspace.public_root)

    def test_01e_mu_plugin_autorizzato_sostituito_da_symlink_rifiutato(self):
        target = self.workspace.public_root / "plugins/sarafatto-core/plugin.php"
        allowed = self.workspace.public_root / baseline.SINGLE_FILE
        allowed.unlink()
        allowed.symlink_to(target)
        with self.assertRaisesRegex(tx.TransactionError, "Symlink"):
            tx._tree_inventory(self.workspace.public_root)

    def test_01f_themes_e_plugins_attraversabili_solo_per_componenti_gestiti(self):
        records = tx._tree_inventory(self.workspace.public_root)
        self.assertIn("themes/sarafatto/front-page.php", records)
        self.assertIn("plugins/sarafatto-core/plugin.php", records)
        for path in ("themes/other/file.php", "plugins/other/file.php"):
            self._write_tree_file(self.workspace.public_root, path, b"outside allowlist")
            with self.subTest(path=path), self.assertRaisesRegex(tx.TransactionError, "allowlist"):
                tx._tree_inventory(self.workspace.public_root)
            (self.workspace.public_root / path).unlink()

    def test_01g_percorso_fuori_allowlist_rifiutato(self):
        for path in ("mu-plugins/other.php", "themes/other/file.php", "plugins/other/file.php"):
            with self.subTest(path=path), self.assertRaisesRegex(tx.TransactionError, "allowlist"):
                tx._safe_relative(path)

    def test_01h_collisioni_file_directory_mu_plugins_rifiutate(self):
        directory = self.workspace.public_root / "mu-plugins"
        saved = self.workspace.public_root / "mu-plugins-saved"
        directory.rename(saved)
        directory.write_text("collision", encoding="utf-8")
        with self.assertRaisesRegex(tx.TransactionError, "allowlist"):
            tx._tree_inventory(self.workspace.public_root)

    def test_02_commit_errato_e_quota_insufficiente_bloccano(self):
        with self.assertRaises(tx.TransactionError):
            self.preflight(authorized_commit_sha="c" * 40)
        with self.assertRaisesRegex(tx.TransactionError, "Quota/spazio insufficiente"):
            self.preflight(quota_free_bytes=1)

    def test_02a_sha_non_autorizzato_blocca_la_simulazione(self):
        plan = self.approved_plan()
        backup = self.backup()
        with self.assertRaisesRegex(tx.TransactionError, "SHA autorizzato"):
            tx.simulate_publish(
                self.workspace, plan, authorized_commit_sha="c" * 40,
                backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed")

    def test_03_artifact_alterato_o_manifest_vite_incompleto_blocca(self):
        entry = self.workspace.artifact_root / "themes/sarafatto/front-page.php"
        entry.write_bytes(b"altered")
        with self.assertRaisesRegex(tx.TransactionError, "diverso dall'inventario"):
            self.preflight()
        entry.write_bytes(self.candidate["themes/sarafatto/front-page.php"][0])
        manifest = self.workspace.artifact_root / "themes/sarafatto/assets/dist/.vite/manifest.json"
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        doc.pop(tx.ENTRYPOINTS[0])
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        # Mantiene coerente l'inventario autorizzato con i byte della fixture,
        # così il preflight raggiunge davvero la verifica semantica del manifest.
        records = tx._tree_inventory(self.workspace.artifact_root)
        self.inventory_path.write_text("".join(
            f"{row['sha256']}\t{row['size']}\t{path}\n" for path, row in sorted(records.items())
        ), encoding="utf-8")
        with self.assertRaisesRegex(tx.TransactionError, "Entry Vite mancante"):
            self.preflight()

    def test_04_baseline_o_stato_corrente_alterati_bloccano(self):
        baseline_path = self.workspace.state_dir / "baseline.json"
        baseline_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(tx.TransactionError):
            self.preflight()
        self._write_state()
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        state["release"]["release_id"] = "forged"
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(tx.TransactionError):
            self.preflight()

    def test_05_path_traversal_symlink_hardlink_e_file_speciali_bloccano(self):
        with self.assertRaises(tx.TransactionError):
            tx._safe_relative("themes/sarafatto/../../public/wp-config.php")
        link = self.workspace.public_root / "themes/sarafatto/link.php"
        link.symlink_to(self.root / "outside")
        with self.assertRaisesRegex(tx.TransactionError, "Symlink"):
            tx._tree_inventory(self.workspace.public_root)
        link.unlink()
        link.symlink_to(self.workspace.public_root / "plugins/sarafatto-core/plugin.php")
        with self.assertRaisesRegex(tx.TransactionError, "Symlink"):
            tx._tree_inventory(self.workspace.public_root)
        link.unlink()
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        hardlink = self.workspace.public_root / "themes/sarafatto/hard.php"
        os.link(outside, hardlink)
        with self.assertRaisesRegex(tx.TransactionError, "(?i)hard link"):
            tx._tree_inventory(self.workspace.public_root)
        hardlink.unlink()
        if hasattr(os, "mkfifo"):
            fifo = self.workspace.public_root / "themes/sarafatto/pipe"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(tx.TransactionError, "speciale"):
                tx._tree_inventory(self.workspace.public_root)

    def test_05a_symlink_su_directory_radice_fixture_bloccato(self):
        public_parent = self.root / "public"
        outside = self.root / "outside-public"
        outside.mkdir(mode=0o700)
        original = self.root / "public-saved"
        public_parent.rename(original)
        public_parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(tx.TransactionError, "sostituita|symlink|Symbolic link|reparse"):
            tx._validate_workspace(self.workspace)

    def test_05b_root_fixture_sostituita_bloccata(self):
        from dataclasses import replace
        other = tx.create_fixture_workspace()
        try:
            forged = replace(self.workspace, root=other.root)
            with self.assertRaisesRegex(tx.TransactionError, "root|Root|percorso"):
                tx._validate_workspace(forged)
        finally:
            shutil.rmtree(other.root, ignore_errors=True)

    def test_06_manifest_vite_asset_mancante_e_file_artifact_symlink_bloccano(self):
        assets = self.workspace.artifact_root / "themes/sarafatto/assets/dist/assets"
        victim = next(assets.glob("app-*.js"))
        victim.unlink()
        with self.assertRaises(tx.TransactionError):
            self.preflight()
        victim.write_text("restored", encoding="utf-8")
        link = self.workspace.artifact_root / "themes/sarafatto/symlink.php"
        link.symlink_to(victim)
        with self.assertRaisesRegex(tx.TransactionError, "Symlink"):
            self.preflight()

    def test_06a_extra_pubblico_non_approvato_e_collisione_bloccano(self):
        unexpected = self.workspace.public_root / "themes/sarafatto/unapproved.php"
        unexpected.write_bytes(b"unapproved")
        with self.assertRaisesRegex(tx.TransactionError, "diverso dallo stato corrente"):
            self.preflight()
        unexpected.unlink()
        candidate_collision = self.workspace.artifact_root / EXTRA_BUNDLE
        candidate_collision.parent.mkdir(parents=True, exist_ok=True)
        candidate_collision.write_bytes(b"collision")
        records = tx._tree_inventory(self.workspace.artifact_root)
        self.inventory_path.write_text("".join(
            f"{row['sha256']}\t{row['size']}\t{path}\n" for path, row in sorted(records.items())
        ), encoding="utf-8")
        with self.assertRaisesRegex(tx.TransactionError, "Collisione con extra approvato"):
            self.preflight()

    def test_06b_node_modules_in_artifact_bloccato(self):
        dependency = self.workspace.artifact_root / "themes/sarafatto/node_modules/pkg.js"
        dependency.parent.mkdir(parents=True, exist_ok=True)
        dependency.write_text("must not ship", encoding="utf-8")
        with self.assertRaisesRegex(tx.TransactionError, "node_modules non può"):
            self.preflight()

    def test_07_rifiuta_root_pubblica_e_piano_manomesso(self):
        from dataclasses import replace
        unsafe = replace(self.workspace, public_root=pathlib.Path("/home/www/public/wp-content"))
        with self.assertRaises(tx.TransactionError):
            tx.preflight(unsafe, artifact_inventory_path=self.inventory_path,
                         artifact_commit_sha=CANDIDATE_SHA, authorized_commit_sha=CANDIDATE_SHA,
                         quota_free_bytes=1024 * 1024 * 1024)
        altered = dict(self.plan)
        altered["files_to_add"] = []
        with self.assertRaisesRegex(tx.TransactionError, "Digest del piano"):
            tx._validate_plan(altered)

    def test_08_rimozione_richiede_approvazione_separata(self):
        with self.assertRaises(tx.TransactionError):
            tx.approve_fixture_removals(self.plan, ["themes/sarafatto/obsolete.php"], confirmation="no")
        approved = self.approved_plan()
        self.assertEqual(approved["removal_approvals"]["themes/sarafatto/obsolete.php"],
                         self.plan["files_candidate_for_removal"][0]["sha256"])

    def test_08a_approvazione_forgiata_non_supera_digest_o_prova_originale(self):
        path = self.plan["files_candidate_for_removal"][0]["path"]
        sha_value = self.plan["files_candidate_for_removal"][0]["sha256"]
        forged = dict(self.plan)
        forged["removal_approvals"] = {path: sha_value}
        unsigned = dict(forged)
        unsigned.pop("plan_sha256", None)
        forged["plan_sha256"] = tx._json_digest(unsigned)
        with self.assertRaises(tx.TransactionError):
            tx._validate_plan(forged)
        with self.assertRaises(tx.TransactionError):
            tx.approve_fixture_removals(
                forged, [path], confirmation="APPROVE-FIXTURE-REMOVALS " + forged["plan_sha256"])

        approved = self.approved_plan()
        changed = dict(approved)
        changed["files_candidate_for_removal"] = []
        changed_unsigned = dict(changed)
        changed_unsigned.pop("plan_sha256", None)
        changed["plan_sha256"] = tx._json_digest(changed_unsigned)
        with self.assertRaises(tx.TransactionError):
            tx._validate_plan(changed)

    def test_09_backup_mancante_corrotto_e_extra_verificati(self):
        with self.assertRaises(tx.TransactionError):
            tx._load_verified_backup(self.workspace, "missing")
        backup = self.backup()
        self.assertEqual(backup["files"], len(self.current))
        data = json.loads((self.workspace.backups_dir / backup["backup_id"] / "backup.json").read_text())
        paths = {row["path"] for row in data["files"]}
        self.assertTrue(set(EXTRA_BUNDLES).issubset(paths))
        self.assertIn(EXTRA_BACKUP, paths)
        data["files"][0]["content_b64"] = "Y29ycnVwdA=="
        (self.workspace.backups_dir / backup["backup_id"] / "backup.json").write_text(json.dumps(data))
        with self.assertRaises(tx.TransactionError):
            tx._load_verified_backup(self.workspace, backup["backup_id"], backup["backup_sha256"])

    def test_09a_backup_mancante_blocca_prima_di_ogni_scrittura(self):
        plan = self.approved_plan()
        before = tx._tree_inventory(self.workspace.public_root)
        with self.assertRaises(tx.TransactionError):
            tx.simulate_publish(
                self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                backup_id="missing", backup_sha256="0" * 64,
                confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed")
        self.assertEqual(tx._tree_inventory(self.workspace.public_root), before)
        self.assertEqual(tx._load_fixture_journal(self.workspace), [])

    def test_10_pubblicazione_simulata_e_rollback_completano(self):
        result, backup, plan = self.publish()
        self.assertEqual(result["status"], "committed-fixture")
        self.assertTrue((self.workspace.public_root / "themes/sarafatto/new-page.php").exists())
        self.assertFalse((self.workspace.public_root / "themes/sarafatto/obsolete.php").exists())
        for path in (*EXTRA_BUNDLES, EXTRA_BACKUP):
            self.assertTrue((self.workspace.public_root / path).exists(), path)
        rolled = tx.simulate_rollback(
            self.workspace, transaction_id=result["operation_id"], backup_id=backup["backup_id"],
            backup_sha256=backup["backup_sha256"],
            confirmation=f"ROLLBACK-FIXTURE {result['operation_id']} {backup['backup_sha256']}",
            health_check="passed",
        )
        self.assertEqual(rolled["status"], "rollback-committed-fixture")
        self.assertEqual(tx._tree_inventory(self.workspace.public_root), {
            path: {"path": path, "sha256": digest(content), "size": len(content), "mode": mode}
            for path, (content, _, mode) in self.current.items()
        })
        restored_backup = tx._load_verified_backup(
            self.workspace, backup["backup_id"], backup["backup_sha256"])[0]
        self.assertTrue(set(EXTRA_BUNDLES).issubset(restored_backup))
        self.assertIn(EXTRA_BACKUP, restored_backup)
        events = tx._load_fixture_journal(self.workspace)
        release_state.unresolved_operation(events, allow_fixture_committed=True)

    def test_11_crash_in_punti_deterministici_blocca_nuove_operazioni(self):
        for fault in (0, 1, 2, -1):
            with self.subTest(fault=fault):
                if fault != 0:
                    self.tearDown()
                    self.setUp()
                plan = self.approved_plan()
                backup = self.backup()
                with self.assertRaises(tx.TransactionError):
                    tx.simulate_publish(
                        self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                        backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                        confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed",
                        fault_after_writes=fault,
                    )
                with self.assertRaises(tx.TransactionError):
                    self.preflight()

    def test_11a_rollback_fixture_recupera_una_pubblicazione_interrotta(self):
        plan = self.approved_plan()
        backup = self.backup()
        with self.assertRaises(tx.TransactionError):
            tx.simulate_publish(
                self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed",
                fault_after_writes=1)
        events = tx._load_fixture_journal(self.workspace)
        operation_id = events[0]["operation_id"]
        result = tx.simulate_rollback(
            self.workspace, transaction_id=operation_id, backup_id=backup["backup_id"],
            backup_sha256=backup["backup_sha256"],
            confirmation=f"ROLLBACK-FIXTURE {operation_id} {backup['backup_sha256']}",
            health_check="passed", plan=plan)
        self.assertEqual(result["status"], "rollback-committed-fixture")
        release_state.unresolved_operation(tx._load_fixture_journal(self.workspace), allow_fixture_committed=True)

    def test_11b_modifica_concorrente_file_e_rollback_interrotto_bloccano(self):
        plan = self.approved_plan()
        backup = self.backup()
        real_replace = tx._replace_at
        changed = False

        def mutate_before_replace(root_fd, relative, data, mode, expected_before):
            nonlocal changed
            if not changed and relative == "themes/sarafatto/front-page.php":
                (self.workspace.public_root / relative).write_bytes(b"concurrent edit")
                changed = True
            return real_replace(root_fd, relative, data, mode, expected_before)

        from unittest import mock
        with mock.patch.object(tx, "_replace_at", side_effect=mutate_before_replace):
            with self.assertRaises(tx.TransactionError):
                tx.simulate_publish(
                    self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                    backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                    confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed")
        with self.assertRaises(tx.TransactionError):
            self.preflight()

    def test_11c_rollback_recovery_rifiuta_permessi_alterati(self):
        plan = self.approved_plan()
        backup = self.backup()
        with self.assertRaises(tx.TransactionError):
            tx.simulate_publish(
                self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed",
                fault_after_writes=1)
        # I contenuti di una recovery possono coincidere con candidate o backup;
        # permessi inattesi non devono tuttavia essere accettati.
        target = self.workspace.public_root / "themes/sarafatto/front-page.php"
        target.chmod(0o600)
        events = tx._load_fixture_journal(self.workspace)
        operation_id = events[0]["operation_id"]
        with self.assertRaisesRegex(tx.TransactionError, "permessi fixture inattesi"):
            tx.simulate_rollback(
                self.workspace, transaction_id=operation_id, backup_id=backup["backup_id"],
                backup_sha256=backup["backup_sha256"],
                confirmation=f"ROLLBACK-FIXTURE {operation_id} {backup['backup_sha256']}",
                health_check="passed", plan=plan)

    def test_11d_rollback_interrotto_rimane_in_recovery_required(self):
        result, backup, _ = self.publish()
        with self.assertRaises(tx.TransactionError):
            tx.simulate_rollback(
                self.workspace, transaction_id=result["operation_id"], backup_id=backup["backup_id"],
                backup_sha256=backup["backup_sha256"],
                confirmation=f"ROLLBACK-FIXTURE {result['operation_id']} {backup['backup_sha256']}",
                health_check="passed", fault_after_writes=1)
        with self.assertRaises(tx.TransactionError):
            self.preflight()

    def test_12_health_status_distinti_e_health_non_disponibile_blocca(self):
        plan = self.approved_plan()
        backup = self.backup()
        result = tx.simulate_publish(
            self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
            backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
            confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="unavailable",
        )
        self.assertEqual(result["integrity"], "verified")
        self.assertEqual(result["health"], "unavailable")
        with self.assertRaises(tx.TransactionError):
            self.preflight()

    def test_12a_health_check_fallito_distinto_dall_integrita(self):
        plan = self.approved_plan()
        backup = self.backup()
        result = tx.simulate_publish(
            self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
            backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
            confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="failed")
        self.assertEqual(result["integrity"], "verified")
        self.assertEqual(result["health"], "failed")
        self.assertEqual(result["status"], "health-check-failed")

    def test_13_lock_occupato_e_doppia_esecuzione_non_concorrono(self):
        locks_fd = os.open(self.workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY)
        lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
        try:
            with self.assertRaises(baseline.BaselineError):
                baseline.acquire_baseline_lock(None, locks_fd)
        finally:
            tx.fcntl.flock(lock_fd, tx.fcntl.LOCK_UN)
            os.close(lock_fd)
            os.close(locks_fd)
        backup = self.backup()
        plan = self.approved_plan()
        before = tx._tree_inventory(self.workspace.public_root)
        lock_dir_fd = os.open(self.workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY)
        held_fd = baseline.acquire_baseline_lock(None, lock_dir_fd)
        try:
            with self.assertRaises(tx.TransactionError) as caught:
                tx.simulate_publish(
                    self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                    backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                    confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed")
            self.assertIsInstance(caught.exception.__cause__, baseline.BaselineError)
            self.assertEqual(tx._tree_inventory(self.workspace.public_root), before)
            self.assertEqual(tx._load_fixture_journal(self.workspace), [])
        finally:
            tx.fcntl.flock(held_fd, tx.fcntl.LOCK_UN)
            os.close(held_fd)
            os.close(lock_dir_fd)

        barrier = threading.Barrier(2)
        results = []

        def publish_worker():
            barrier.wait()
            try:
                results.append(tx.simulate_publish(
                    self.workspace, plan, authorized_commit_sha=CANDIDATE_SHA,
                    backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                    confirmation="PUBLISH-FIXTURE " + plan["plan_sha256"], health_check="passed"))
            except (tx.TransactionError, baseline.BaselineError) as exc:
                results.append(exc)

        workers = [threading.Thread(target=publish_worker) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        successful = [item for item in results if isinstance(item, dict)]
        self.assertLessEqual(len(successful), 1)
        self.assertEqual(len(successful), 1)
        self.assertEqual(sum(isinstance(item, tx.TransactionError) for item in results), 1)
        self.assertEqual(len(results), 2)

        # Il descriptor e il flock acquisiti dal publish concluso devono essere rilasciati.
        lock_dir_fd = os.open(self.workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY)
        released_fd = baseline.acquire_baseline_lock(None, lock_dir_fd)
        tx.fcntl.flock(released_fd, tx.fcntl.LOCK_UN)
        os.close(released_fd)
        os.close(lock_dir_fd)

    def test_14_operazione_committed_arbitraria_rifiutata(self):
        state_fd = os.open(self.workspace.state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        locks_fd = os.open(self.workspace.locks_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self.assertRaisesRegex(release_state.ReleaseStateError, "futuro verificatore"):
                release_state.append_operation_event(state_fd, locks_fd, "forged", "committed", {})
        finally:
            os.close(state_fd)
            os.close(locks_fd)

    def test_15_rollback_rifiuta_hash_corrente_alterato_e_autorizzazione_errata(self):
        result, backup, _ = self.publish()
        file = self.workspace.public_root / "themes/sarafatto/front-page.php"
        file.write_bytes(b"outside change")
        with self.assertRaises(tx.TransactionError):
            tx.simulate_rollback(
                self.workspace, transaction_id=result["operation_id"], backup_id=backup["backup_id"],
                backup_sha256=backup["backup_sha256"], confirmation="wrong", health_check="passed")

    def test_16_rimozione_non_approvata_non_pubblica(self):
        backup = self.backup()
        before = tx._tree_inventory(self.workspace.public_root)
        with self.assertRaises(tx.TransactionError):
            tx.simulate_publish(
                self.workspace, self.plan, authorized_commit_sha=CANDIDATE_SHA,
                backup_id=backup["backup_id"], backup_sha256=backup["backup_sha256"],
                confirmation="PUBLISH-FIXTURE " + self.plan["plan_sha256"], health_check="passed")
        self.assertTrue((self.workspace.public_root / "themes/sarafatto/obsolete.php").exists())
        self.assertEqual(tx._tree_inventory(self.workspace.public_root), before)
        self.assertEqual(tx._load_fixture_journal(self.workspace), [])

        path = self.plan["files_candidate_for_removal"][0]["path"]
        forged = dict(self.plan)
        forged["removal_approvals"] = {
            row["path"]: row["sha256"] for row in self.plan["files_candidate_for_removal"]
        }
        unsigned = dict(forged)
        unsigned.pop("plan_sha256", None)
        forged["plan_sha256"] = tx._json_digest(unsigned)
        with self.assertRaises(tx.TransactionError):
            tx.approve_fixture_removals(
                forged, [path], confirmation="APPROVE-FIXTURE-REMOVALS " + forged["plan_sha256"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransactionFixtureTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if FLOCK_REQUIRED and result.skipped:
        print("ERRORE: la CI non può saltare test POSIX transazionali.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(not result.wasSuccessful())
