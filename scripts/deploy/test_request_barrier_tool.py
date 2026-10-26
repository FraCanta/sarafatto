#!/usr/bin/env python3
"""Test offline del protocollo flock e dei gate HTTP della request barrier."""

import hashlib
import http.client
import os
import pathlib
import stat
import tempfile
import threading
import time
import unittest
import urllib.error

import request_barrier_tool as barrier

POSIX_LOCKS = (
    os.name == "posix" and barrier.fcntl is not None
    and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd
)
if os.environ.get("SARAFATTO_REQUIRE_FLOCK") == "1" and not POSIX_LOCKS:
    raise RuntimeError("SARAFATTO_REQUIRE_FLOCK=1: i test POSIX critici non possono essere saltati.")


class FakeResponse:
    def __init__(self, payload, *, status=200, url=barrier.STATUS_URL, headers=None):
        self.payload = payload
        self.status = status
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        import json
        return json.dumps(self.payload).encode("utf-8")

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None

    def open(self, request, timeout=None):
        self.request = request
        if self.error:
            raise self.error
        return self.response


class BarrierContractTests(unittest.TestCase):
    def test_schema_config_accetta_default_disabilitato_e_rifiuta_path_arbitrari(self):
        config = {
            "schema_version": 1, "enabled": False,
            "lock_path": "/private/locks/web-request.lock",
            "window_path": "/private/state/request-deploy-window.json",
            "status_token_sha256": "a" * 64,
        }
        barrier.validate_config(config, lock_path=config["lock_path"], window_path=config["window_path"])
        invalid = dict(config, lock_path="/home/www/public/wp-content/lock")
        with self.assertRaises(barrier.BarrierError):
            barrier.validate_config(invalid, lock_path=config["lock_path"], window_path=config["window_path"])
        with self.assertRaises(barrier.BarrierError):
            barrier.validate_config(dict(config, extra="unexpected"),
                                    lock_path=config["lock_path"], window_path=config["window_path"])

    def test_status_http_richiede_sapi_web_hash_sorgente_e_lock_attivo(self):
        payload = {
            "schema_version": 1, "enabled": True, "lock_accessible": True,
            "lock_acquired": True, "window_armed": False, "php_sapi": "fpm-fcgi",
            "source_sha256": "b" * 64, "config_sha256": "c" * 64,
        }
        opener = FakeOpener(FakeResponse(payload))
        result = barrier.verify_http_active(
            "t" * 40, "b" * 64, expected_config_sha256="c" * 64, opener=opener
        )
        self.assertEqual(result, payload)
        self.assertEqual(opener.request.get_header("X-sarafatto-barrier-token"), "t" * 40)

    def test_status_http_rifiuta_php_cli_lock_mancante_hash_errato_e_redirect(self):
        base = {
            "schema_version": 1, "enabled": True, "lock_accessible": True,
            "lock_acquired": True, "window_armed": False, "php_sapi": "fpm-fcgi",
            "source_sha256": "b" * 64, "config_sha256": "c" * 64,
        }
        for change in ({"php_sapi": "cli"}, {"lock_acquired": False},
                       {"source_sha256": "d" * 64}, {"window_armed": True}):
            with self.subTest(change=change):
                with self.assertRaises(barrier.BarrierError):
                    barrier.verify_http_active("t" * 40, "b" * 64,
                                               opener=FakeOpener(FakeResponse({**base, **change})))
        redirected = FakeOpener(FakeResponse(base, url="https://example.org/"))
        with self.assertRaises(barrier.BarrierError):
            barrier.fetch_http_status("t" * 40, opener=redirected)
        for url in ("http://sara-fatto.it/wp-json/sarafatto/v1/deploy-barrier",
                    "https://example.org/wp-json/sarafatto/v1/deploy-barrier",
                    "https://sara-fatto.it/wp-json/sarafatto/v1/deploy-barrier?x=1"):
            with self.subTest(url=url), self.assertRaises(barrier.BarrierError):
                barrier.fetch_http_status("t" * 40, url=url, opener=FakeOpener(FakeResponse(base)))

    def test_interlock_http_richiede_503_con_header_dedicato(self):
        error = urllib.error.HTTPError(
            "https://sara-fatto.it/", 503, "busy",
            {"X-Sarafatto-Deploy-Barrier": "active"}, None,
        )
        self.assertTrue(barrier.verify_exclusive_interlock("t" * 40, opener=FakeOpener(error=error)))
        wrong = urllib.error.HTTPError("https://sara-fatto.it/", 503, "busy", {}, None)
        with self.assertRaises(barrier.BarrierError):
            barrier.verify_exclusive_interlock("t" * 40, opener=FakeOpener(error=wrong))

    def test_php_mu_plugin_preserva_filtro_polylang_e_barriera_precede_il_filtro(self):
        path = pathlib.Path(__file__).parents[2] / "mu-plugins" / "sarafatto-polylang-front-page-url.php"
        source = path.read_text(encoding="utf-8")
        self.assertIn("function sarafatto_polylang_language_root_front_page_option", source)
        self.assertIn("$options['redirect_lang'] = 1;", source)
        self.assertIn("add_filter( 'option_polylang', 'sarafatto_polylang_language_root_front_page_option' );", source)
        self.assertLess(source.index("sarafatto_deploy_barrier_bootstrap();"),
                        source.index("add_filter( 'option_polylang'"))
        self.assertIn("LOCK_SH | LOCK_NB", source)
        self.assertIn("register_shutdown_function", source)
        self.assertIn("sarafatto_deploy_barrier_status['window_armed']", source)
        self.assertIn("X-Sarafatto-Deploy-Barrier: active", source)
        self.assertIn("register_rest_route", source)
        self.assertIn("Cache-Control', 'no-store, max-age=0", source)
        # Fuori dalla finestra armata, i problemi di lock non emettono 503.
        self.assertIn("if ( $sarafatto_deploy_barrier_status['window_armed'] )", source)
        self.assertLess(
            source.index("if ( $sarafatto_deploy_barrier_status['window_armed'] )"),
            source.index("$config = sarafatto_deploy_barrier_configuration();"),
        )
        lock_success = source.index("if ( $valid && flock( $handle, LOCK_SH | LOCK_NB ) )")
        marker_recheck = source.index(
            "$sarafatto_deploy_barrier_status['window_armed'] = sarafatto_deploy_barrier_window_is_armed();",
            lock_success,
        )
        shutdown_registration = source.index("register_shutdown_function(", lock_success)
        self.assertLess(marker_recheck, shutdown_registration)
        self.assertLess(source.index("flock( $handle, LOCK_UN );", marker_recheck),
                        source.index("sarafatto_deploy_barrier_maintenance_response();", marker_recheck))
        self.assertIn("$sarafatto_deploy_barrier_status['window_armed'] = sarafatto_deploy_barrier_window_is_armed();\n\tif ( $sarafatto_deploy_barrier_status['window_armed'] )", source)
        self.assertNotIn("sarafatto_deploy_barrier_maintenance_response();\n\t}\n\treturn;", source)


@unittest.skipUnless(POSIX_LOCKS, "flock/openat/O_NOFOLLOW richiedono POSIX (CI Ubuntu obbligatoria).")
class PosixLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sf-request-barrier-")
        self.root = pathlib.Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.lock = self.root / "web-request.lock"
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        os.chmod(self.state, 0o700)
        fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fsync(fd)
        os.close(fd)

    def tearDown(self):
        self.temp.cleanup()

    def test_shared_lock_multiplo_e_rilascio_sblocca_exclusive(self):
        with barrier.locked_file(self.lock, "shared"):
            with barrier.locked_file(self.lock, "shared"):
                with self.assertRaises(TimeoutError):
                    with barrier.locked_file(self.lock, "exclusive", timeout=0.05):
                        self.fail("LOCK_EX non doveva acquisirsi con reader attivi.")
        with barrier.locked_file(self.lock, "exclusive", timeout=0.1):
            pass

    def test_richiesta_gia_avviata_trattiene_shared_fino_a_shutdown(self):
        started = threading.Event()
        finish = threading.Event()
        result = []

        def request_worker():
            with barrier.locked_file(self.lock, "shared"):
                started.set()
                finish.wait(2)
                result.append("finished")

        worker = threading.Thread(target=request_worker)
        worker.start()
        self.assertTrue(started.wait(1))
        with self.assertRaises(TimeoutError):
            with barrier.locked_file(self.lock, "exclusive", timeout=0.08):
                self.fail("LOCK_EX doveva attendere la richiesta già avviata.")
        finish.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["finished"])
        with barrier.locked_file(self.lock, "exclusive", timeout=0.1):
            pass

    def test_errore_durante_richiesta_rilascia_il_lock(self):
        with self.assertRaisesRegex(RuntimeError, "fault"):
            with barrier.locked_file(self.lock, "shared"):
                raise RuntimeError("fault")
        with barrier.locked_file(self.lock, "exclusive", timeout=0.1):
            pass

    def test_timeout_esclusivo_e_finito(self):
        with barrier.locked_file(self.lock, "exclusive"):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                with barrier.locked_file(self.lock, "shared", timeout=0.08):
                    self.fail("LOCK_SH doveva essere rifiutato.")
            self.assertLess(time.monotonic() - started, 0.5)

    def test_lock_assente_symlink_permessi_errati_e_path_non_canonico_falliscono(self):
        missing = self.root / "missing.lock"
        with self.assertRaises(barrier.BarrierError):
            barrier.inspect_lock(missing)
        link = self.root / "link.lock"
        os.symlink(self.lock.name, link)
        with self.assertRaises(barrier.BarrierError):
            barrier.inspect_lock(link)
        os.chmod(self.lock, 0o644)
        with self.assertRaises(barrier.BarrierError):
            barrier.inspect_lock(self.lock)

    def test_marker_privato_non_sovrascrivibile_e_rimozione_legata_all_id(self):
        operation_id = "barrier-test-" + "a" * 32
        barrier.arm_operation_window(operation_id, state_root=self.state)
        marker = self.state / "request-deploy-window.json"
        document = barrier._load_json(marker)
        self.assertEqual(barrier.validate_window(document)["operation_id"], operation_id)
        with self.assertRaises(barrier.BarrierError):
            barrier.arm_operation_window(operation_id, state_root=self.state)
        with self.assertRaises(barrier.BarrierError):
            barrier.complete_operation_window("barrier-test-" + "b" * 32, state_root=self.state)
        self.assertTrue(marker.exists())
        barrier.complete_operation_window(operation_id, state_root=self.state)
        self.assertFalse(marker.exists())

    def test_config_file_symlink_o_permessi_errati_rifiutati(self):
        config = self.state / "request-barrier.json"
        document = {
            "schema_version": 1, "enabled": False, "lock_path": str(self.lock),
            "window_path": str(self.state / "request-deploy-window.json"),
            "status_token_sha256": "a" * 64,
        }
        config.write_text(__import__("json").dumps(document), encoding="utf-8")
        os.chmod(config, 0o600)
        self.assertFalse(barrier.load_config(config, lock_path=self.lock,
                                             window_path=self.state / "request-deploy-window.json")["enabled"])
        config.unlink()
        os.symlink("missing-config", config)
        with self.assertRaises(barrier.BarrierError):
            barrier.load_config(config, lock_path=self.lock,
                                window_path=self.state / "request-deploy-window.json")

    def test_concorrenza_non_permette_exclusive_durante_reader(self):
        entered = threading.Event()
        release = threading.Event()
        exclusive_acquired = []

        def reader():
            with barrier.locked_file(self.lock, "shared"):
                entered.set()
                release.wait(2)

        def writer():
            try:
                with barrier.locked_file(self.lock, "exclusive", timeout=0.08):
                    exclusive_acquired.append(True)
            except TimeoutError:
                exclusive_acquired.append(False)

        read_thread = threading.Thread(target=reader)
        read_thread.start()
        self.assertTrue(entered.wait(1))
        write_thread = threading.Thread(target=writer)
        write_thread.start()
        write_thread.join(1)
        self.assertEqual(exclusive_acquired, [False])
        release.set()
        read_thread.join(2)
        with barrier.locked_file(self.lock, "exclusive", timeout=0.1):
            exclusive_acquired.append(True)
        self.assertEqual(exclusive_acquired, [False, True])

    def test_marker_presente_con_lock_libero_o_occupato_blocca_nuova_richiesta(self):
        marker = self.state / "request-deploy-window.json"

        def simulated_request():
            if marker.exists():
                return "503"
            try:
                with barrier.locked_file(self.lock, "shared", timeout=0):
                    if marker.exists():
                        return "503"
                    return "continue"
            except TimeoutError:
                return "503" if marker.exists() else "continue"

        marker.write_text('{"schema_version":1}', encoding="ascii")
        self.assertEqual(simulated_request(), "503")
        # Il rifiuto prima del lock non lascia un reader che blocchi il publisher.
        with barrier.locked_file(self.lock, "exclusive", timeout=0.1):
            self.assertEqual(simulated_request(), "503")

    def test_marker_armato_dopo_lock_shared_rifiuta_e_drena_il_reader(self):
        marker = self.state / "request-deploy-window.json"
        reader_locked = threading.Event()
        marker_armed = threading.Event()
        result = []

        def simulated_request():
            if marker.exists():
                result.append("503-before-lock")
                return
            with barrier.locked_file(self.lock, "shared", timeout=0.1):
                reader_locked.set()
                self.assertTrue(marker_armed.wait(1))
                if marker.exists():
                    result.append("503-after-lock")
                    return
                result.append("continue")

        worker = threading.Thread(target=simulated_request)
        worker.start()
        self.assertTrue(reader_locked.wait(1))
        marker.write_text('{"schema_version":1}', encoding="ascii")
        with self.assertRaises(TimeoutError):
            with barrier.locked_file(self.lock, "exclusive", timeout=0.05):
                self.fail("Il publisher non deve superare un reader già attivo.")
        marker_armed.set()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["503-after-lock"])
        with barrier.locked_file(self.lock, "exclusive", timeout=0.1):
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
