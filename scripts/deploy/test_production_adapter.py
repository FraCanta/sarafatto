#!/usr/bin/env python3
"""Controlli offline delle sole interfacce read-only dell'adattatore IONOS."""

import contextlib
import io
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import production_adapter as adapter

if os.environ.get("SARAFATTO_REQUIRE_POSIX") == "1" and (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")):
    raise RuntimeError("La CI richiede le verifiche POSIX della toolchain privata.")


class ProductionAdapterTests(unittest.TestCase):
    def test_diagnostica_commit_vecchio_identifica_il_primo_file_assente(self):
        sha = "b2f4698e8f945471b5db5dc2fff458c8623dbcda"
        def git(arguments):
            if arguments[0] == "rev-parse":
                return sha.encode() + b"\n"
            if arguments[0] == "ls-tree":
                return b"" if arguments[-1] == "scripts/deploy/production_publisher.py" else arguments[-1].encode()
            if arguments[0] == "show":
                return b"committed"
            raise AssertionError(arguments)
        with mock.patch.object(adapter, "_require_fixed_directory"), \
                mock.patch.object(adapter, "_git_output", side_effect=git), \
                mock.patch.object(adapter, "_read_repo_file", return_value=b"committed"):
            with self.assertRaisesRegex(adapter.ProductionAdapterError, "File assente nel commit autorizzato: scripts/deploy/production_publisher.py"):
                adapter.verify_repository_sources(sha)

    def test_diagnostica_distingue_head_accesso_e_contenuto_modificato(self):
        with mock.patch.object(adapter, "_require_fixed_directory", side_effect=adapter.ProductionAdapterError("accesso negato")):
            with self.assertRaisesRegex(adapter.ProductionAdapterError, "Repository Git IONOS assente, non accessibile"):
                adapter.verify_repository_sources("a" * 40)
        with mock.patch.object(adapter, "_require_fixed_directory"), \
                mock.patch.object(adapter, "_git_output", return_value=b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"):
            with self.assertRaisesRegex(adapter.ProductionAdapterError, "HEAD Git diverso"):
                adapter.verify_repository_sources("a" * 40)
        with mock.patch.object(adapter, "_require_fixed_directory"), \
                mock.patch.object(adapter, "_git_output", side_effect=[b"a" * 40, b"file", b"committed"]), \
                mock.patch.object(adapter, "_read_repo_file", return_value=b"modified"):
            with self.assertRaisesRegex(adapter.ProductionAdapterError, "Contenuto del checkout modificato"):
                adapter.verify_repository_sources("a" * 40)
        with mock.patch.object(adapter.subprocess, "run", return_value=subprocess.CompletedProcess([], 128, b"", b"sensitive-detail")):
            with self.assertRaises(adapter.ProductionAdapterError) as caught:
                adapter._git_output(["rev-parse", "--verify", "HEAD"])
            self.assertNotIn("sensitive-detail", str(caught.exception))

    def test_cli_richiede_autorita_esplicita_e_non_accetta_due_modelli(self):
        args = adapter.parser().parse_args(["inspect", "--toolchain-sha256", "a" * 64])
        self.assertIsNone(args.authorized_sha)
        self.assertEqual(args.toolchain_sha256, "a" * 64)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            adapter.parser().parse_args(["inspect", "--authorized-sha", "b" * 40,
                                         "--toolchain-sha256", "a" * 64])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "Integrazione toolchain/stato/inventario richiede Ubuntu.")
    def test_toolchain_privata_checkout_vecchio_preflight_e_rifiuti_integrita(self):
        import test_release_state_tool as bootstrap_fixtures
        import test_production_publisher as artifact_fixtures
        import artifact_transfer_tool as transfer
        fixture = bootstrap_fixtures.ReleaseStateTests("test_01_bootstrap_valido_e_non_sovrascrivibile")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        for index in range(2, 9):
            relative = f"themes/sarafatto/assets/dist/assets/app-old{index:02d}Ab12.js"
            data = f"old {index}".encode()
            fixture.files[relative] = (data, "retained-vite-bundle", "644")
            path = fixture.public / relative
            path.write_bytes(data)
            path.chmod(0o644)
        fixture.write_baseline()
        fixture.approved_baseline_sha = hashlib.sha256(fixture.baseline_path.read_bytes()).hexdigest()
        fixture.bootstrap()
        baseline_before = fixture.baseline_path.read_bytes()
        state_before = (fixture.state / adapter.release_state_tool.STATE_NAME).read_bytes()
        staging = fixture.private / "staging"
        staging.mkdir(mode=0o700)
        (fixture.private / "backups").mkdir(mode=0o700)
        tools = fixture.private / "tools/scripts/deploy"
        tools.mkdir(parents=True)
        for directory in (fixture.private / "tools", tools.parent, tools):
            directory.chmod(0o700)
        contract = transfer.toolchain_contract()
        for row in contract["contract"]["files"]:
            path = tools / row["file"]
            shutil.copyfile(pathlib.Path(adapter.__file__).parent / row["file"], path)
            path.chmod(0o600)
        legacy = fixture.root / "old-repository"
        legacy.mkdir()
        (legacy / "HEAD-fixture").write_text("b2f4698e8f945471b5db5dc2fff458c8623dbcda")
        artifact = artifact_fixtures.ProductionArtifactTests("test_sha_incompleto_rifiutato")
        artifact.setUp()
        self.addCleanup(artifact.tearDown)
        package = staging / "package"
        shutil.copytree(artifact.package, package)
        for source, name in ((artifact.inventory, "inventory.tsv"), (artifact.archive, "archive.tar.gz"),
                             (artifact.provenance, "provenance.json")):
            shutil.copyfile(source, staging / name)
        worker = r'''
import contextlib, io, json, os, pathlib, stat, subprocess, sys
tools, private, public, legacy, baseline_sha, approved, scenario = sys.argv[1:]
sys.path.insert(0, tools)
import production_adapter as a, production_publisher as p, baseline_tool as b
a.PRIVATE_ROOT=pathlib.Path(private); a.PRIVATE_TOOLS_ROOT=pathlib.Path(tools)
a.PUBLIC_ROOT=pathlib.Path(public); a.REPOSITORY_ROOT=pathlib.Path(legacy); a.BASELINE_SHA256=baseline_sha
p.PRIVATE_ROOT=pathlib.Path(private); p.PUBLIC_ROOT=pathlib.Path(public)
original_run=subprocess.run
def forbidden(*args, **kwargs): raise AssertionError('Checkout Git o inventario legacy usato')
a._git_output=forbidden; b.acquire_fresh_inventory=forbidden
def inventory(args, **kwargs):
    if args != ['bash','-s']: raise AssertionError('Solo inventario Bash verificato consentito')
    kwargs['env']={**os.environ,'TMPDIR':str(pathlib.Path(private).parent.parent)}
    return original_run(['bash','-s','--','--fixture-root',public],**kwargs)
a.subprocess.run=inventory
stage=pathlib.Path(private)/'staging'
if scenario=='unapproved': approved='0'*64
arguments=['--release-sha','a'*40,'--run-id','12345','--package',str(stage/'package'),
           '--inventory',str(stage/'inventory.tsv'),'--archive',str(stage/'archive.tar.gz'),
           '--provenance',str(stage/'provenance.json'),'--toolchain-sha256',approved]
target=None; previous=None; previous_mode=None
if scenario=='tools': target=pathlib.Path(tools)/'baseline-inventory.sh'
if scenario=='module': target=pathlib.Path(tools)/'production_publisher.py'
if scenario=='permissions': target=pathlib.Path(tools)/'production_publisher.py'
if scenario=='artifact': target=stage/'archive.tar.gz'
if scenario=='public': target=pathlib.Path(public)/'themes/sarafatto/front-page.php'
if scenario=='state': target=pathlib.Path(private)/'state/current-release.json'
if scenario=='journal': target=pathlib.Path(private)/'state'/p.release_state_tool.JOURNAL_NAME
if target is not None:
    previous=target.read_bytes() if target.exists() else None
    previous_mode=stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    if scenario=='permissions': target.chmod(0o666)
    else:
        target.write_bytes((previous or b'')+b'changed'); target.chmod(0o600)
try:
    if scenario=='no-pin':
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            code=p.main(['status','--authorized-sha','b2f4698e8f945471b5db5dc2fff458c8623dbcda'])
        if code!=2: raise AssertionError('La toolchain privata ha accettato il repository come autorita')
    elif scenario in ('tools','module','permissions','public','state','journal','unapproved'):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            code=p.main(['status','--toolchain-sha256',approved])
        if code!=2: raise AssertionError(('Atteso rifiuto status',scenario,code))
    elif scenario=='artifact':
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            code=p.main(['preflight',*arguments])
        if code!=2: raise AssertionError(('Atteso rifiuto artifact',code))
    else:
        report=a.inspect_production_state(toolchain_sha256=approved)
        if report['status']!='verified-current' or report['authorized_repository_sha'] is not None:
            raise AssertionError(report)
        if report['publish_allowed'] or report['public_writes_performed']: raise AssertionError(report)
        for command, expected in ((['status','--toolchain-sha256',approved],0),
                                  (['verify-artifact',*arguments],0),(['preflight',*arguments],3)):
            output=io.StringIO()
            with contextlib.redirect_stdout(output): code=p.main(command)
            if code!=expected: raise AssertionError((command[0],code,output.getvalue()))
            result=json.loads(output.getvalue())
            if result.get('public_writes_performed') is True: raise AssertionError(result)
    print(json.dumps({'scenario':scenario,'checked':True}))
finally:
    if target is not None:
        if previous is None: target.unlink()
        else:
            target.write_bytes(previous); target.chmod(previous_mode)
'''
        for scenario in ("valid", "tools", "module", "permissions", "artifact", "public", "state", "journal", "unapproved", "no-pin"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([sys.executable, "-B", "-c", worker, str(tools), str(fixture.private),
                                         str(fixture.public), str(legacy), fixture.approved_baseline_sha,
                                         contract["toolchain_sha256"], scenario],
                                        check=False, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(json.loads(result.stdout)["checked"])
        self.assertEqual(fixture.baseline_path.read_bytes(), baseline_before)
        self.assertEqual((fixture.state / adapter.release_state_tool.STATE_NAME).read_bytes(), state_before)
        self.assertFalse((fixture.state / adapter.release_state_tool.JOURNAL_NAME).exists())
        self.assertEqual(len([row for row in fixture.files.values() if row[1] != "artifact"]), 9)
        for relative, (payload, _, mode) in fixture.files.items():
            path = fixture.public / relative
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(path.stat().st_mode & 0o7777, int(mode, 8))
        self.assertEqual((legacy / "HEAD-fixture").read_text(), "b2f4698e8f945471b5db5dc2fff458c8623dbcda")

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
