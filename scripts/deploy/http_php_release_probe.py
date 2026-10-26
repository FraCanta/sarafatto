#!/usr/bin/env python3
"""Prepara fixture PHP A/B private e misura richieste HTTPS concorrenti.

prepare scrive soltanto sotto /home/www/sarafatto-deploy/staging/.
stress commuta soltanto il puntatore fixture sotto staging e legge un sottodominio
HTTPS temporaneo esplicitamente ammesso. Non ha accesso a WordPress o al DB.
"""

import argparse
import base64
import concurrent.futures
import getpass
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:
    fcntl = None

STAGING_ROOT = pathlib.Path("/home/www/sarafatto-deploy/staging")
TEMPLATE_ROOT = pathlib.Path(__file__).with_name("http-release-probe")
RUN_RE = re.compile(r"^ionos-http-probe-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")
HOST_RE = re.compile(r"^release-probe-[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?\.sara-fatto\.it$")
MARKER = ".sarafatto-http-release-probe"
MARKER_VALUE = "sarafatto-http-release-probe-v1"
PHP_FILES = ("index.php", "asset.php")
COMPONENTS = ("theme", "plugin", "mu-plugin", "assets")


class ProbeError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, new_url):
        return None


def _require_posix():
    if (os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd or os.symlink not in os.supports_dir_fd):
        raise ProbeError("Sono richiesti POSIX, flock, openat/O_NOFOLLOW e symlink.")


def _open_dir_at(parent_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        raise ProbeError(f"Directory non valida: {name}.")
    return fd


def _open_absolute_dir(path):
    target = pathlib.PurePosixPath(path)
    if not target.is_absolute() or ".." in target.parts:
        raise ProbeError("Root staging non valida.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in target.parts[1:]:
            next_fd = _open_dir_at(fd, part)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_staging():
    fd = _open_absolute_dir(str(STAGING_ROOT))
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ProbeError("staging non appartiene all'utente o non ha permessi 0700.")
    return fd


def _write_new_at(directory_fd, name, raw, mode=0o600):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 mode, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_regular_at(directory_fd, name, limit=1024 * 1024):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ProbeError(f"File non regolare o troppo grande: {name}.")
        result = bytearray()
        while len(result) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(result)))
            if not block:
                break
            result.extend(block)
        if len(result) > limit:
            raise ProbeError(f"File oltre il limite: {name}.")
        return bytes(result)
    finally:
        os.close(fd)


def _safe_template(name):
    if name not in PHP_FILES:
        raise ProbeError("Template non autorizzato.")
    path = TEMPLATE_ROOT / name
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > 128 * 1024:
        raise ProbeError(f"Template non regolare: {name}.")
    return path.read_bytes()


def _mkdir(parent_fd, name, mode=0o700):
    os.mkdir(name, mode, dir_fd=parent_fd)
    return _open_dir_at(parent_fd, name)


def _prepare_run(staging_fd, staging_path):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"ionos-http-probe-{timestamp}-{uuid.uuid4().hex[:12]}"
    run_fd = _mkdir(staging_fd, run_id, 0o700)
    run_path = staging_path / run_id
    try:
        _write_new_at(run_fd, MARKER, (MARKER_VALUE + "\n").encode("ascii"))
        docroot_fd = _mkdir(run_fd, "docroot", 0o755)
        os.fchmod(docroot_fd, 0o755)
        releases_fd = _mkdir(run_fd, "releases")
        private_fd = _mkdir(run_fd, "private")
        try:
            # .htpasswd vuoto: fino all'aggiunta manuale di un utente nessun
            # accesso autenticato è possibile. IONOS deve prima confermare .htaccess.
            _write_new_at(private_fd, ".htpasswd", b"", 0o600)
            auth_file = run_path / "private" / ".htpasswd"
            htaccess = (
                'AuthType Basic\n'
                'AuthName "Sarafatto isolated release probe"\n'
                f'AuthUserFile {auth_file}\n'
                'Require valid-user\n'
            ).encode("utf-8")
            _write_new_at(docroot_fd, ".htaccess", htaccess, 0o644)
            for name in PHP_FILES:
                _write_new_at(docroot_fd, name, _safe_template(name), 0o644)
            config = f"<?php\ndeclare(strict_types=1);\nreturn ['run_id' => '{run_id}'];\n"
            _write_new_at(docroot_fd, "probe-config.php", config.encode("ascii"), 0o644)
            for label in ("A", "B"):
                release_fd = _mkdir(releases_fd, f"release-{label}")
                try:
                    for component in COMPONENTS:
                        component_fd = _mkdir(release_fd, component)
                        try:
                            if component == "assets":
                                _write_new_at(component_fd, "asset.txt",
                                              f"asset-{label}\n".encode("ascii"), 0o644)
                            else:
                                php = f"<?php\ndeclare(strict_types=1);\nreturn '{label}';\n"
                                _write_new_at(component_fd, "release.php", php.encode("ascii"), 0o644)
                        finally:
                            os.close(component_fd)
                    os.fsync(release_fd)
                finally:
                    os.close(release_fd)
            os.symlink("release-A", "current", dir_fd=releases_fd)
            os.fsync(releases_fd)
        finally:
            os.close(private_fd)
            os.close(releases_fd)
            os.close(docroot_fd)
        os.fsync(run_fd)
        return {"run_id": run_id, "run_path": str(run_path),
                "document_root": str(run_path / "docroot"),
                "initial_release": "release-A", "php_files_sha256": {
                    name: hashlib.sha256(_safe_template(name)).hexdigest() for name in PHP_FILES
                },
                "auth_configured": False,
                "htpasswd_available": shutil.which("htpasswd") is not None,
                "note": "Non associare il sottodominio finché non è stato impostato un utente Basic Auth.",
                "public_wordpress_touched": False}
    finally:
        os.close(run_fd)


def _verify_fixture(run_id, run_fd, releases_fd):
    run_path = STAGING_ROOT / run_id
    docroot_fd = _open_dir_at(run_fd, "docroot")
    private_fd = _open_dir_at(run_fd, "private")
    try:
        if set(os.listdir(docroot_fd)) != {".htaccess", "index.php", "asset.php", "probe-config.php"}:
            raise ProbeError("Document root fixture contiene file extra o mancanti.")
        if set(os.listdir(private_fd)) != {".htpasswd"}:
            raise ProbeError("Directory privata fixture contiene elementi inattesi.")
        if set(os.listdir(releases_fd)) != {"release-A", "release-B", "current"}:
            raise ProbeError("Directory releases fixture contiene elementi inattesi.")
        if _read_regular_at(run_fd, MARKER, 1024).decode("ascii").strip() != MARKER_VALUE:
            raise ProbeError("Marker del run assente o non valido.")
        expected_auth = (
            'AuthType Basic\n'
            'AuthName "Sarafatto isolated release probe"\n'
            f'AuthUserFile {run_path / "private" / ".htpasswd"}\n'
            'Require valid-user\n'
        ).encode("utf-8")
        if _read_regular_at(docroot_fd, ".htaccess", 4096) != expected_auth:
            raise ProbeError("Protezione Basic Auth .htaccess alterata o assente.")
        auth_info = os.stat(".htpasswd", dir_fd=private_fd, follow_symlinks=False)
        if (not stat.S_ISREG(auth_info.st_mode) or auth_info.st_nlink != 1
                or auth_info.st_uid != os.getuid() or auth_info.st_size > 4096
                or stat.S_IMODE(auth_info.st_mode) != 0o600):
            raise ProbeError("File .htpasswd non regolare o con permessi inattesi.")
        for name in PHP_FILES:
            if _read_regular_at(docroot_fd, name, 128 * 1024) != _safe_template(name):
                raise ProbeError(f"Endpoint PHP fixture alterato: {name}.")
        expected_config = f"<?php\ndeclare(strict_types=1);\nreturn ['run_id' => '{run_id}'];\n".encode("ascii")
        if _read_regular_at(docroot_fd, "probe-config.php", 4096) != expected_config:
            raise ProbeError("Configurazione run PHP alterata.")
        for label in ("A", "B"):
            release_fd = _open_dir_at(releases_fd, f"release-{label}")
            try:
                if set(os.listdir(release_fd)) != set(COMPONENTS):
                    raise ProbeError(f"Directory release-{label} contiene elementi inattesi.")
                for component in COMPONENTS:
                    component_fd = _open_dir_at(release_fd, component)
                    try:
                        name = "asset.txt" if component == "assets" else "release.php"
                        if set(os.listdir(component_fd)) != {name}:
                            raise ProbeError(f"Release {label}/{component} contiene elementi inattesi.")
                        expected = (f"asset-{label}\n" if component == "assets"
                                    else f"<?php\ndeclare(strict_types=1);\nreturn '{label}';\n")
                        if _read_regular_at(component_fd, name, 4096) != expected.encode("ascii"):
                            raise ProbeError(f"Fixture release-{label}/{component} alterata.")
                    finally:
                        os.close(component_fd)
            finally:
                os.close(release_fd)
        if os.readlink("current", dir_fd=releases_fd) not in ("release-A", "release-B"):
            raise ProbeError("Puntatore current alterato o fuori allowlist.")
    except Exception:
        raise
    finally:
        os.close(private_fd)
        os.close(docroot_fd)


def _open_run(run_id):
    if not isinstance(run_id, str) or not RUN_RE.fullmatch(run_id):
        raise ProbeError("ID run non valido.")
    staging_fd = _open_staging()
    try:
        run_fd = _open_dir_at(staging_fd, run_id)
    except Exception:
        os.close(staging_fd)
        raise
    try:
        run_info = os.fstat(run_fd)
        if run_info.st_uid != os.getuid() or stat.S_IMODE(run_info.st_mode) != 0o700:
            raise ProbeError("Directory run con owner o permessi inattesi.")
        releases_fd = _open_dir_at(run_fd, "releases")
        try:
            _verify_fixture(run_id, run_fd, releases_fd)
            return staging_fd, run_fd, releases_fd
        except Exception:
            os.close(releases_fd)
            raise
    except Exception:
        os.close(run_fd)
        os.close(staging_fd)
        raise


def _switch_release(releases_fd, label):
    if label not in ("A", "B"):
        raise ProbeError("Release consentite: A o B.")
    temporary = ".current-switch-" + uuid.uuid4().hex
    os.symlink(f"release-{label}", temporary, dir_fd=releases_fd)
    os.replace(temporary, "current", src_dir_fd=releases_fd, dst_dir_fd=releases_fd)
    os.fsync(releases_fd)


def _validate_host(host):
    if not isinstance(host, str) or not HOST_RE.fullmatch(host):
        raise ProbeError("Host ammesso: solo release-probe-<id>.sara-fatto.it, mai il dominio di produzione.")
    return f"https://{host}"


def _http_opener():
    return urllib.request.build_opener(urllib.request.HTTPSHandler(), NoRedirect())


def _request(opener, url, authorization=None, timeout=15):
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept": "application/json"})
    if authorization:
        request.add_header("Authorization", authorization)
    return opener.open(request, timeout=timeout)


def _stress(run_fd, releases_fd, run_id, host, count, workers, hold_ms):
    base_url = _validate_host(host)
    opener = _http_opener()
    endpoint = base_url + "/index.php"
    try:
        with _request(opener, endpoint, timeout=10) as response:
            if response.status != 401:
                raise ProbeError("Endpoint non protetto: richiesta anonima non ha restituito HTTP 401.")
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise ProbeError(f"Controllo anonimo atteso 401, ricevuto HTTP {exc.code}.") from exc
        challenge = exc.headers.get("WWW-Authenticate", "")
        if 'Basic realm="Sarafatto isolated release probe"' not in challenge:
            raise ProbeError("Challenge 401 non corrisponde al realm Basic Auth della fixture.") from exc
    username = input("Utente Basic Auth del probe: ")
    password = getpass.getpass("Password Basic Auth del probe: ")
    if not username or not password:
        raise ProbeError("Credenziali Basic Auth vuote.")
    authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    # Non conservare le credenziali oltre la funzione e non includerle nel report.
    password = ""

    start = threading.Event()
    stop_switch = threading.Event()
    report_lock = threading.Lock()
    report = {"host": host, "requests_expected": count, "requests_ok": 0,
              "mixed": 0, "errors": [], "versions": {}, "http_errors": {},
              "switches": 0, "test_id": run_id, "runtime_profiles": {}}

    def fetch_one(index):
        start.wait(timeout=10)
        request_id = uuid.uuid4().hex
        url = f"{endpoint}?rid={request_id}&hold_ms={hold_ms}"
        try:
            with _request(opener, url, authorization) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ProbeError("Status o URL finale inattesi nella risposta PHP.")
                payload = json.loads(response.read(65536))
            if payload.get("probe_run_id") != run_id:
                raise ProbeError("Il sottodominio non serve il run privato selezionato.")
            components = payload.get("components", {})
            runtime = payload.get("runtime", {})
            if not isinstance(runtime, dict) or runtime.get("sapi") in (None, "cli"):
                raise ProbeError("La risposta non proviene da una SAPI HTTP PHP riconoscibile.")
            runtime_key = json.dumps(runtime, sort_keys=True, separators=(",", ":"))
            with report_lock:
                report["runtime_profiles"][runtime_key] = report["runtime_profiles"].get(runtime_key, 0) + 1
            release = payload.get("release")
            label = release[-1] if release in ("release-A", "release-B") else None
            component_versions = {components.get(key) for key in ("theme", "plugin", "mu_plugin")}
            if (label is None or component_versions != {label}
                    or components.get("asset") != f"asset-{label}"):
                with report_lock:
                    report["mixed"] += 1
                return
            asset_path = payload.get("asset_url")
            if asset_path != f"/asset.php?release={payload['release']}":
                raise ProbeError("URL asset non legato alla release fissata dalla richiesta.")
            asset_url = base_url + asset_path
            asset_request = urllib.request.Request(asset_url, headers={"Cache-Control": "no-cache"})
            asset_request.add_header("Authorization", authorization)
            with opener.open(asset_request, timeout=15) as asset_response:
                if asset_response.geturl() != asset_url:
                    raise ProbeError("Redirect non consentito durante il test dell'asset.")
                if asset_response.headers.get("X-SF-Probe-Run-ID") != run_id:
                    raise ProbeError("Endpoint asset non corrisponde al run privato selezionato.")
                asset_text = asset_response.read(4096).decode("ascii").strip()
            if asset_text != components["asset"]:
                with report_lock:
                    report["mixed"] += 1
                return
            with report_lock:
                report["requests_ok"] += 1
                report["versions"][release] = report["versions"].get(release, 0) + 1
        except urllib.error.HTTPError as exc:
            with report_lock:
                report["http_errors"][str(exc.code)] = report["http_errors"].get(str(exc.code), 0) + 1
        except Exception as exc:
            with report_lock:
                report["errors"].append(f"request-{index}:{type(exc).__name__}:{str(exc)[:240]}")

    original_target = os.readlink("current", dir_fd=releases_fd)
    if original_target not in ("release-A", "release-B"):
        raise ProbeError("Puntatore current iniziale non valido.")

    def switcher():
        start.wait(timeout=10)
        label = "B" if original_target == "release-A" else "A"
        try:
            for _ in range(120):
                if stop_switch.is_set():
                    break
                _switch_release(releases_fd, label)
                label = "A" if label == "B" else "B"
                with report_lock:
                    report["switches"] += 1
                time.sleep(0.025)
        except Exception as exc:
            with report_lock:
                report["errors"].append(f"switcher:{type(exc).__name__}:{str(exc)[:240]}")

    writer = threading.Thread(target=switcher, name="release-pointer-switcher")
    writer.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch_one, index) for index in range(count)]
            start.set()
            for future in concurrent.futures.as_completed(futures, timeout=max(60, count * 2)):
                future.result()
    finally:
        stop_switch.set()
        writer.join(timeout=10)
        if writer.is_alive():
            report["errors"].append("switcher:timeout")
        # Lascia la fixture nello stesso stato in cui è stata trovata.
        _switch_release(releases_fd, original_target[-1])

    report["status"] = ("passed" if report["requests_ok"] == count
                        and report["mixed"] == 0 and not report["errors"]
                        and not report["http_errors"] and report["switches"] > 0
                        and set(report["versions"]) == {"release-A", "release-B"}
                        and len(report["runtime_profiles"]) == 1
                        else "blocked")
    report["opcache_note"] = "Ogni risposta include PHP SAPI e flag OPcache/realpath; validare che corrispondano alla configurazione attesa del dominio."
    report["webroot_or_wordpress_modified"] = False
    return report


def _save_report(run_fd, report):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"http-stress-report-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_new_at(run_fd, name, raw, 0o600)
    os.fsync(run_fd)
    return name


def prepare():
    _require_posix()
    staging_fd = _open_staging()
    try:
        result = _prepare_run(staging_fd, STAGING_ROOT)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    finally:
        os.close(staging_fd)


def stress(args):
    _require_posix()
    if not 1 <= args.requests <= 2000 or not 1 <= args.workers <= 32 or not 0 <= args.hold_ms <= 2000:
        raise ProbeError("Limiti test: requests 1..2000, workers 1..32, hold-ms 0..2000.")
    _validate_host(args.host)
    staging_fd, run_fd, releases_fd = _open_run(args.run_id)
    try:
        result = _stress(run_fd, releases_fd, args.run_id, args.host,
                         args.requests, args.workers, args.hold_ms)
        report_name = _save_report(run_fd, result)
        result["private_report"] = str(STAGING_ROOT / args.run_id / report_name)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "passed" else 3
    finally:
        os.close(releases_fd)
        os.close(run_fd)
        os.close(staging_fd)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="crea fixture HTTP/PHP solo in staging privato")
    run = commands.add_parser("stress", help="commuta il puntatore fixture e verifica richieste HTTPS")
    run.add_argument("--run-id", required=True)
    run.add_argument("--host", required=True)
    run.add_argument("--requests", type=int, default=320)
    run.add_argument("--workers", type=int, default=16)
    run.add_argument("--hold-ms", type=int, default=500)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return prepare() if args.command == "prepare" else stress(args)
    except (OSError, ProbeError, ValueError, urllib.error.URLError,
            concurrent.futures.TimeoutError) as exc:
        print(f"ERRORE: test interrotto; fixture private conservate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
