#!/usr/bin/env python3
"""Offline tests; real filesystem operations stay inside temporary directories."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from unittest import mock

import theme_deploy as deploy
import production_publisher as publisher
import test_production_publisher as fixtures

POSIX = os.name == 'posix' and hasattr(os, 'O_NOFOLLOW')
if os.environ.get('SARAFATTO_REQUIRE_POSIX') == '1' and not POSIX:
    raise RuntimeError('I test theme deploy POSIX non possono essere saltati in CI.')


def runtime(**changes):
    return {'operation_id': 'theme-12345-1', 'nonce': 'nonce', 'sapi': 'fpm-fcgi',
            'opcache_loaded': True, 'opcache_enable': '1', 'validate_timestamps': '1',
            'revalidate_freq': '0', 'file_cache_only': '0', **changes}


class Contracts(unittest.TestCase):
    def test_maintenance_probe_verifica_risposta_autenticata_e_503_anonimo(self):
        url = 'https://sara-fatto.it/'
        operation_id, token, nonce = 'theme-12345-1', 't'*64, 'n'*48
        payload = runtime(nonce=nonce)
        response = mock.MagicMock(status=200, headers={
            'X-Sarafatto-Theme-Maintenance': operation_id})
        response.__enter__.return_value = response
        response.geturl.return_value = url
        response.read.return_value = json.dumps(payload).encode()
        anonymous = urllib.error.HTTPError(url, 503, 'Maintenance', {
            'X-Sarafatto-Theme-Maintenance': operation_id}, None)
        opener = mock.Mock()
        opener.open.side_effect = [response, anonymous]
        window = deploy.Maintenance(pathlib.Path('unused'), operation_id, token, opener=opener)

        with mock.patch.object(deploy.secrets, 'token_hex', return_value=nonce) as nonce_factory:
            self.assertEqual(window.probe(), payload)
        nonce_factory.assert_called_once_with(24)
        self.assertEqual(opener.open.call_count, 2)
        authenticated_call, anonymous_call = opener.open.call_args_list
        authenticated_request = authenticated_call.args[0]
        anonymous_request = anonymous_call.args[0]
        self.assertEqual(authenticated_request.get_header('X-sarafatto-theme-token'), token)
        self.assertEqual(authenticated_request.get_header('X-sarafatto-theme-nonce'), nonce)
        self.assertIsNone(anonymous_request.get_header('X-sarafatto-theme-token'))
        self.assertIsNone(anonymous_request.get_header('X-sarafatto-theme-nonce'))
        for call in opener.open.call_args_list:
            self.assertEqual(call.args[0].full_url, url)
            self.assertEqual(call.args[0].get_header('Cache-control'), 'no-cache, no-store')
            self.assertEqual(call.kwargs, {'timeout': 15})

    def test_pubblicazione_richiede_approvazione_github_del_revisore_esatto(self):
        approval = {'state': 'approved', 'user': {'login': 'FraCanta'},
                    'environments': [{'name': 'ionos-production'}]}
        self.assertTrue(deploy.require_github_approval([approval], 'FraCanta'))
        for history in ([], [{**approval, 'state': 'rejected'}],
                        [{**approval, 'user': {'login': 'other'}}],
                        [{**approval, 'environments': [{'name': 'ionos-private-staging'}]}]):
            with self.subTest(history=history), self.assertRaises(deploy.ThemeDeployError):
                deploy.require_github_approval(history, 'FraCanta')

    def test_health_wordpress_rifiuta_frontend_vecchio_e_rest_non_wordpress(self):
        class Response:
            status = 200
            def __init__(self, url, body): self.url, self.body = url, body
            def geturl(self): return self.url
            def read(self, _limit): return self.body
            def __enter__(self): return self
            def __exit__(self, *args): pass
        class Client:
            def __init__(self, html, api): self.html, self.api = html, api
            def open(self, request, timeout):
                body = self.api if request.full_url.endswith('/wp-json/') else self.html
                return Response(request.full_url, body)
        html = b'<html><script src="/wp-content/themes/sarafatto/assets/dist/assets/app-B.js"></script></html>'
        api = b'{"namespaces":["wp/v2"]}'
        self.assertEqual(len(deploy.wordpress_health(opener=Client(html, api), expected_app='assets/app-B.js')), 2)
        for body, rest, expected in ((html, api, 'assets/app-A.js'), (html, b'{}', None),
                                     (b'<html>Fatal error</html>', api, None)):
            with self.subTest(expected=expected), self.assertRaises(deploy.ThemeDeployError):
                deploy.wordpress_health(opener=Client(body, rest), expected_app=expected)

    def test_sintassi_php_del_marker(self):
        php = shutil.which('php')
        if php is None:
            if os.environ.get('SARAFATTO_REQUIRE_POSIX') == '1':
                self.fail('PHP CLI richiesto su Ubuntu per il lint del marker, non per provare PHP web.')
            self.skipTest('PHP CLI assente: lint da eseguire su Ubuntu.')
        result = subprocess.run([php, '-l'], input=deploy.maintenance_php('theme-12345-1', 't'*64),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_runtime_web_rifiuta_cli_cache_e_nonce_estraneo(self):
        self.assertEqual(deploy.validate_runtime(runtime(), 'theme-12345-1', 'nonce'), runtime())
        for changes in ({'sapi': 'cli'}, {'revalidate_freq': '180'}, {'validate_timestamps': '0'},
                        {'file_cache_only': '1'}, {'nonce': 'cached'}, {'operation_id': 'other'}):
            with self.subTest(changes=changes), self.assertRaises(deploy.ThemeDeployError):
                deploy.validate_runtime(runtime(**changes), 'theme-12345-1', 'nonce')

    def test_marker_persistente_non_scade_e_non_espone_token(self):
        token = 'a'*64
        raw = deploy.maintenance_php('theme-12345-1', token)
        self.assertIn(b'$upgrading = time();', raw)
        self.assertNotIn(token.encode(), raw)
        self.assertIn(hashlib.sha256(token.encode()).hexdigest().encode(), raw)
        with self.assertRaises(deploy.ThemeDeployError):
            deploy.maintenance_php("theme-1-1';evil", token)

    def test_scopo_ignora_modifiche_plugin_mu_e_rifiuta_piano_fuori_tema(self):
        state = fixtures.release_state_fixtures._state_a()
        incoming = {r['path']: {'sha256': '0'*64, 'size': 1, 'mode': '644'}
                    for r in state['reference_files'] if r['classification'] == 'artifact'}
        selected = deploy.scoped_records(state, incoming)
        for row in state['reference_files']:
            if not row['path'].startswith(deploy.THEME):
                self.assertEqual(selected[row['path']]['sha256'], row['sha256'])
        with self.assertRaises(deploy.ThemeDeployError):
            deploy.assert_theme_plan({'changes': [{'path': 'plugins/sarafatto-core/plugin.php'}]})
        for path in ('themes/sarafatto/../other.php', '/themes/sarafatto/file.php', 'themes/sarafatto/a\\b.php'):
            with self.subTest(path=path), self.assertRaises(deploy.ThemeDeployError):
                deploy.assert_theme_plan({'changes': [{'path': path}]})

    def test_health_negativo_riarma_prima_del_rollback(self):
        window = mock.Mock()
        with mock.patch.object(publisher, 'production_health_check', side_effect=RuntimeError('down')):
            with self.assertRaises(RuntimeError):
                deploy._health(publisher, window, ['https://sara-fatto.it/'], {}, sleeper=lambda _: None)
        self.assertEqual(window.method_calls, [mock.call.probe(), mock.call.reopen(), mock.call.arm(recovery=True)])


@unittest.skipUnless(POSIX, 'Filesystem descriptor e flock richiedono Ubuntu.')
class Filesystem(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.ProductionArtifactTests('test_artifact_ammesso_solo_con_manifest_e_inventario_coerenti')
        self.base.setUp()
        self.fixture = self.base._release_fixture()
        self.inputs = self.base._stage_release_inputs(self.fixture)
        self.reader = self.base._inventory_reader(self.fixture.public)
        state = json.loads((self.fixture.state / publisher.release_state_tool.STATE_NAME).read_bytes())
        self.removals, _ = self.base._removal_approval(state, 'themes/sarafatto/front-page.php', 'theme-removal')
        self.original = publisher.inventory_target_tree(self.fixture.public)

        class Window(deploy.Maintenance):
            def probe(self):
                self._owned()
                return runtime()
        self.Window = Window

    def tearDown(self):
        self.base.doCleanups()
        self.base.tearDown()

    def execute(self, command, **kwargs):
        return deploy.execute(publisher, inputs=self.inputs, identity=('a'*40, '12345', '1'),
            private_root=self.fixture.private, public_root=self.fixture.public, reader=self.reader,
            command=command, removals=self.removals, quota=10**10, window_factory=self.Window,
            sleeper=lambda _: None, grace=0, health=self.health, **kwargs)

    def health(self, window):
        window.probe()
        window.reopen()
        return {'status': 'healthy', 'test_http_only': True}

    def test_publish_scrive_solo_tema_backup_restore_stato_e_nove_extra(self):
        review = self.execute('preflight')
        self.assertNotIn('token', review)
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), self.original)
        result = self.execute('publish', expected_review=review['review_sha256'])
        self.assertEqual(result['status'], 'published')
        self.assertTrue(all(p.startswith(deploy.THEME) for p in result['files_written']))
        after = publisher.inventory_target_tree(self.fixture.public)
        for path, row in self.original.items():
            if not path.startswith(deploy.THEME) or 'app-old' in path or path.endswith('.bak'):
                self.assertEqual(after[path], row)
        self.assertTrue(result['backup']['manifest_sha256'])
        self.assertFalse((self.fixture.public.parent / '.maintenance').exists())
        self.assertEqual(self.base._journal_events(self.fixture)[-1]['status'], 'release_committed')

    def test_rimozione_non_approvata_blocca_prima_del_backup(self):
        self.removals = []
        with self.assertRaises(Exception):
            self.execute('preflight')
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), self.original)
        self.assertEqual(list((self.fixture.private/'backups').iterdir()), [])

    def test_piano_artifact_alterati_e_parent_drift_bloccano(self):
        review = self.execute('preflight')
        for digest in ('0'*64,):
            with self.assertRaises(deploy.ThemeDeployError):
                self.execute('publish', expected_review=digest)
        file = self.inputs['package'] / 'themes/sarafatto/functions.php'
        file.write_bytes(b'altered artifact')
        with self.assertRaises(publisher.PublisherError):
            self.execute('publish', expected_review=review['review_sha256'])
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), self.original)

    def test_parent_modificato_dopo_review_blocca_senza_scritture(self):
        review = self.execute('preflight')
        file = self.fixture.public/'themes/sarafatto/functions.php'
        file.write_bytes(b'manual edit')
        before = publisher.inventory_target_tree(self.fixture.public)
        with self.assertRaises(publisher.PublisherError):
            self.execute('publish', expected_review=review['review_sha256'])
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), before)
        self.assertEqual(self.base._journal_events(self.fixture), [])

    def test_health_fallito_ripristina_parent_e_non_registra_release_committed(self):
        review = self.execute('preflight')
        calls = []
        def health(window):
            calls.append(True)
            if len(calls) == 1:
                window.arm(recovery=True)
                raise RuntimeError('HTTP health failed')
            window.reopen()
            return {'status': 'healthy', 'parent': True}
        with mock.patch.object(self, 'health', side_effect=health):
            with self.assertRaisesRegex(publisher.PublisherError, 'rollback al parent'):
                self.execute('publish', expected_review=review['review_sha256'])
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), self.original)
        statuses = [e['status'] for e in self.base._journal_events(self.fixture)]
        self.assertEqual(statuses[-1], 'recovery_completed')
        self.assertNotIn('release_committed', statuses)
        self.assertFalse((self.fixture.public.parent/'.maintenance').exists())

    def test_backup_corrotto_dopo_crash_blocca_recovery_e_mantiene_manutenzione(self):
        review = self.execute('preflight')
        class Crash(BaseException):
            pass
        def crash(event, _path, count):
            if event == 'after-file' and count == 1:
                raise Crash()
        with self.assertRaises(Crash):
            self.execute('publish', expected_review=review['review_sha256'], fault_hook=crash)
        backup = next((self.fixture.private/'backups').glob('*/payload.tar.gz'))
        backup.write_bytes(b'invalid archive')
        before = publisher.inventory_target_tree(self.fixture.public)
        with self.assertRaises(publisher.PublisherError):
            self.execute('recover', expected_review=review['review_sha256'])
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), before)
        self.assertTrue((self.fixture.public.parent/'.maintenance').exists())

    def test_lock_occupato_e_marker_estraneo_non_vengono_aggirati(self):
        review = self.execute('preflight')
        private, lock = publisher._open_release_context(self.fixture.private, self.fixture.private)
        try:
            with self.assertRaises(publisher.baseline_tool.BaselineError):
                self.execute('publish', expected_review=review['review_sha256'])
        finally:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
            publisher.backup_tool.close_private_directories(private)
        marker = self.fixture.public.parent/'.maintenance'
        marker.write_bytes(b'foreign maintenance')
        with self.Window(self.fixture.public.parent, 'theme-12345-1', 't'*64) as window:
            with self.assertRaises(deploy.ThemeDeployError):
                window.arm()
            with self.assertRaises(deploy.ThemeDeployError):
                window.reopen()
        self.assertEqual(marker.read_bytes(), b'foreign maintenance')
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), self.original)

    def test_marker_symlink_non_viene_seguito_o_rimosso(self):
        outside = self.base.root/'outside-marker'
        outside.write_bytes(b'untouched')
        marker = self.fixture.public.parent/'.maintenance'
        marker.symlink_to(outside)
        with self.Window(self.fixture.public.parent, 'theme-12345-1', 't'*64) as window:
            with self.assertRaises(deploy.ThemeDeployError): window.arm()
            with self.assertRaises(OSError): window.reopen()
        self.assertTrue(marker.is_symlink())
        self.assertEqual(outside.read_bytes(), b'untouched')

    def test_marker_pubblicato_completo_senza_sovrascrivere_collisioni(self):
        marker = self.fixture.public.parent/'.maintenance'
        real_link = os.link
        with self.Window(self.fixture.public.parent, 'theme-12345-1', 't'*64) as window:
            def checked_link(source, destination, **kwargs):
                self.assertFalse(marker.exists())
                fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=kwargs['src_dir_fd'])
                try: self.assertEqual(os.read(fd, len(window.payload)+1), window.payload)
                finally: os.close(fd)
                return real_link(source, destination, **kwargs)
            with mock.patch.object(deploy.os, 'link', side_effect=checked_link): window.arm()
            self.assertEqual(window._owned().st_nlink, 1)
            self.assertEqual(list(marker.parent.glob('.sf-maintenance-*')), [])
            window.reopen()

            def collision(source, destination, **kwargs):
                marker.write_bytes(b'concurrent maintenance')
                return real_link(source, destination, **kwargs)
            with mock.patch.object(deploy.os, 'link', side_effect=collision):
                with self.assertRaises(deploy.ThemeDeployError): window.arm()
            self.assertEqual(marker.read_bytes(), b'concurrent maintenance')
            self.assertEqual(list(marker.parent.glob('.sf-maintenance-*')), [])

    def test_crash_recovery_ripristina_parent_senza_plugin_mu_o_extra_modificati(self):
        review = self.execute('preflight')

        class Crash(BaseException):
            pass

        def crash(event, _path, count):
            if event == 'after-file' and count == 2:
                raise Crash()
        with self.assertRaises(Crash):
            self.execute('publish', expected_review=review['review_sha256'], fault_hook=crash)
        self.assertTrue((self.fixture.public.parent/'.maintenance').exists())
        result = self.execute('recover', expected_review=review['review_sha256'])
        self.assertEqual(result['status'], 'recovery_completed')
        self.assertEqual(publisher.inventory_target_tree(self.fixture.public), self.original)
        self.assertFalse((self.fixture.public.parent/'.maintenance').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
