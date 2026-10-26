#!/usr/bin/env python3
"""Gestione e verifica read-only della barriera richieste WordPress.

Protocollo: le richieste PHP acquisiscono LOCK_SH su web-request.lock fino allo
shutdown; una futura transazione arma request-deploy-window.json e acquisisce
LOCK_EX sullo stesso inode prima di modificare file pubblici. Questo modulo non
pubblica file.
"""

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import secrets
import stat
import sys
import time
import urllib.error
import urllib.request

try:
    import fcntl
except ImportError:  # Importabile su Windows; le prove POSIX sono obbligatorie in CI.
    fcntl = None

PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
STATE_ROOT = PRIVATE_ROOT / "state"
LOCKS_ROOT = PRIVATE_ROOT / "locks"
CONFIG_PATH = STATE_ROOT / "request-barrier.json"
PROOF_PATH = STATE_ROOT / "request-barrier-http-proof.json"
LOCK_PATH = LOCKS_ROOT / "web-request.lock"
WINDOW_PATH = STATE_ROOT / "request-deploy-window.json"
REPOSITORY_MU_PLUGIN = pathlib.Path("/home/www/sarafatto-repo/mu-plugins/sarafatto-polylang-front-page-url.php")
STATUS_URL = "https://sara-fatto.it/wp-json/sarafatto/v1/deploy-barrier"
SCHEMA_VERSION = 1
CONFIG_FIELDS = {"schema_version", "enabled", "lock_path", "window_path", "status_token_sha256"}
PROOF_MAX_AGE_SECONDS = 300
PROOF_FIELDS = {
    "schema_version", "phase", "timestamp_utc", "status_url",
    "source_sha256", "config_sha256", "php_sapi", "php_version",
    "lock_accessible", "lock_acquired", "opcache",
}


class BarrierError(Exception):
    """Prova della barriera assente, incoerente o non verificabile."""


def _require_posix():
    if (os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd):
        raise BarrierError("La barriera richiede POSIX, flock, openat e O_NOFOLLOW.")


def _open_checked_dir(path, *, expected_uid=None, mode=0o700):
    path = pathlib.Path(path)
    try:
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
                or path.resolve(strict=True) != path
                or stat.S_IMODE(info.st_mode) != mode
                or (expected_uid is not None and info.st_uid != expected_uid)):
            raise BarrierError(f"Directory privata non sicura: {path}.")
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise BarrierError(f"Directory privata assente o non apribile: {path}.") from exc
    opened = os.fstat(fd)
    if (not stat.S_ISDIR(opened.st_mode) or stat.S_IMODE(opened.st_mode) != mode
            or (expected_uid is not None and opened.st_uid != expected_uid)
            or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
        os.close(fd)
        raise BarrierError(f"Directory privata sostituita: {path}.")
    return fd


def _safe_regular_bytes(path, *, limit=4096, expected_mode=0o600, expected_uid=None):
    path = pathlib.Path(path)
    parent_fd = _open_checked_dir(path.parent, expected_uid=expected_uid)
    try:
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1 or before.st_size > limit
                or stat.S_IMODE(before.st_mode) != expected_mode
                or (expected_uid is not None and before.st_uid != expected_uid)):
            raise BarrierError(f"File privato non regolare o con permessi inattesi: {path.name}.")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            opened = os.fstat(fd)
            if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or opened.st_size > limit or stat.S_IMODE(opened.st_mode) != expected_mode
                    or (expected_uid is not None and opened.st_uid != expected_uid)):
                raise BarrierError(f"File privato sostituito durante la lettura: {path.name}.")
            raw = bytearray()
            while len(raw) <= limit:
                block = os.read(fd, min(65536, limit + 1 - len(raw)))
                if not block:
                    break
                raw.extend(block)
            if len(raw) > limit:
                raise BarrierError(f"File privato oltre il limite: {path.name}.")
            return bytes(raw)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _load_json(path, *, limit=4096, expected_mode=0o600, expected_uid=None):
    try:
        return json.loads(_safe_regular_bytes(path, limit=limit, expected_mode=expected_mode,
                                              expected_uid=expected_uid).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BarrierError(f"JSON privato malformato: {path.name}.") from exc


def _write_new_at(directory_fd, name, payload, mode=0o600):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 mode, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(fd, payload[offset:])
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)


def _replace_private_json(directory_fd, name, document):
    """Aggiornamento atomico limitato a un file JSON privato già previsto."""
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(raw) > 4096:
        raise BarrierError("Documento privato oltre il limite dimensionale.")
    try:
        target = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        target = None
    if target is not None and (stat.S_ISLNK(target.st_mode) or not stat.S_ISREG(target.st_mode)
                               or target.st_nlink != 1 or stat.S_IMODE(target.st_mode) != 0o600
                               or target.st_uid != os.getuid()):
        raise BarrierError(f"Destinazione privata non sicura: {name}.")
    temporary = ".barrier-tmp-" + secrets.token_hex(12)
    _write_new_at(directory_fd, temporary, raw)
    try:
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except Exception:
        # Il temporaneo resta privato e non viene ripulito in modo concorrente.
        raise


def _current_source_sha256():
    try:
        info = REPOSITORY_MU_PLUGIN.lstat()
    except OSError as exc:
        raise BarrierError("Sorgente MU-plugin del repository non disponibile.") from exc
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or REPOSITORY_MU_PLUGIN.resolve(strict=True) != REPOSITORY_MU_PLUGIN):
        raise BarrierError("Sorgente MU-plugin non regolare o raggiunto tramite symlink.")
    return _sha256_file(REPOSITORY_MU_PLUGIN)


def _private_config_sha256():
    return hashlib.sha256(_safe_regular_bytes(
        CONFIG_PATH, expected_uid=os.getuid() if hasattr(os, "getuid") else None
    )).hexdigest()


def _private_directories():
    uid = os.getuid()
    state_fd = _open_checked_dir(STATE_ROOT, expected_uid=uid)
    try:
        locks_fd = _open_checked_dir(LOCKS_ROOT, expected_uid=uid)
    except Exception:
        os.close(state_fd)
        raise
    return state_fd, locks_fd


def prepare_private():
    """Prepara config disabilitata e lock privato; non attiva la barriera."""
    _require_posix()
    state_fd, locks_fd = _private_directories()
    try:
        try:
            lock_info = os.stat(LOCK_PATH.name, dir_fd=locks_fd, follow_symlinks=False)
        except FileNotFoundError:
            _write_new_at(locks_fd, LOCK_PATH.name, b"", 0o600)
        else:
            if (stat.S_ISLNK(lock_info.st_mode) or not stat.S_ISREG(lock_info.st_mode)
                    or lock_info.st_nlink != 1 or lock_info.st_uid != os.getuid()
                    or stat.S_IMODE(lock_info.st_mode) != 0o600):
                raise BarrierError("web-request.lock esistente non valido; nessuna sovrascrittura.")
        token = secrets.token_urlsafe(48)
        config = {
            "schema_version": SCHEMA_VERSION,
            "enabled": False,
            "lock_path": str(LOCK_PATH),
            "window_path": str(WINDOW_PATH),
            "status_token_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
        }
        try:
            os.stat(CONFIG_PATH.name, dir_fd=state_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise BarrierError("request-barrier.json esistente: preparazione non sovrascrive configurazioni.")
        _write_new_at(state_fd, CONFIG_PATH.name,
                      (json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        print(json.dumps({
            "status": "prepared-disabled",
            "config_path": str(CONFIG_PATH),
            "lock_path": str(LOCK_PATH),
            "status_token_once": token,
            "enabled": False,
        }, ensure_ascii=False, sort_keys=True, indent=2))
    finally:
        os.close(locks_fd)
        os.close(state_fd)


def _write_proof(phase, payload):
    state_fd, locks_fd = _private_directories()
    os.close(locks_fd)
    try:
        proof = {
            "schema_version": SCHEMA_VERSION,
            "phase": phase,
            "timestamp_utc": int(time.time()),
            "status_url": STATUS_URL,
            "source_sha256": payload["source_sha256"],
            "config_sha256": _private_config_sha256(),
            "php_sapi": payload["php_sapi"],
            "php_version": payload["php_version"],
            "lock_accessible": payload["lock_accessible"],
            "lock_acquired": payload["lock_acquired"],
            "opcache": payload.get("opcache", {}),
        }
        _replace_private_json(state_fd, PROOF_PATH.name, proof)
    finally:
        os.close(state_fd)


def verify_http(token, *, phase):
    if phase not in ("accessibility", "active"):
        raise BarrierError("Fase HTTP ammessa: accessibility o active.")
    config = load_config()
    payload = fetch_http_status(token)
    expected_source = _current_source_sha256()
    if payload.get("source_sha256") != expected_source:
        raise BarrierError("MU-plugin servito dalla SAPI web diverso dal sorgente del repository IONOS.")
    if phase == "accessibility":
        if (config["enabled"] is not False or payload.get("enabled") is not False
                or payload.get("lock_accessible") is not True
                or payload.get("lock_acquired") is not False):
            raise BarrierError("Probe di accessibilità richiede config disabilitata e lock leggibile/acquisibile.")
    else:
        if config["enabled"] is not True:
            raise BarrierError("Config non attiva; impossibile registrare prova PHP web attiva.")
        payload = verify_http_active(token, expected_source,
                                     expected_config_sha256=_private_config_sha256())
    _write_proof(phase, payload)
    return payload


def activate_private():
    """Attiva solo dopo una prova HTTP fresca della fase accessibility."""
    _require_posix()
    state_fd, locks_fd = _private_directories()
    os.close(locks_fd)
    try:
        config = load_config()
        if config["enabled"]:
            raise BarrierError("Barriera già attiva; nessuna riscrittura.")
        proof = _load_json(PROOF_PATH, expected_uid=os.getuid())
        if (not isinstance(proof, dict) or set(proof) != PROOF_FIELDS
                or proof.get("schema_version") != SCHEMA_VERSION
                or proof.get("phase") != "accessibility"
                or proof.get("status_url") != STATUS_URL
                or proof.get("php_sapi") in (None, "cli")
                or proof.get("lock_accessible") is not True
                or proof.get("lock_acquired") is not False
                or proof.get("source_sha256") != _current_source_sha256()
                or proof.get("config_sha256") != _private_config_sha256()
                or not isinstance(proof.get("timestamp_utc"), int)
                or time.time() - proof["timestamp_utc"] > PROOF_MAX_AGE_SECONDS
                or time.time() < proof["timestamp_utc"]):
            raise BarrierError("Prova HTTP accessibility assente, scaduta o non legata ai file correnti.")
        if WINDOW_PATH.exists() or WINDOW_PATH.is_symlink():
            raise BarrierError("Finestra operativa presente; attivazione bloccata.")
        config["enabled"] = True
        _replace_private_json(state_fd, CONFIG_PATH.name, config)
    finally:
        os.close(state_fd)


def assert_private_ready(*, token, expected_source_sha256=None):
    """Preflight che un futuro publisher deve invocare; non autorizza scritture."""
    config = load_config()
    if config["enabled"] is not True:
        raise BarrierError("Barriera PHP web disabilitata.")
    expected_source = expected_source_sha256 or _current_source_sha256()
    proof = _load_json(PROOF_PATH, expected_uid=os.getuid())
    if (not isinstance(proof, dict) or set(proof) != PROOF_FIELDS
            or proof.get("schema_version") != SCHEMA_VERSION
            or proof.get("phase") != "active"
            or proof.get("status_url") != STATUS_URL
            or proof.get("source_sha256") != expected_source
            or proof.get("config_sha256") != _private_config_sha256()
            or proof.get("lock_accessible") is not True
            or proof.get("lock_acquired") is not True
            or not isinstance(proof.get("timestamp_utc"), int)
            or time.time() - proof["timestamp_utc"] > PROOF_MAX_AGE_SECONDS
            or time.time() < proof["timestamp_utc"]):
        raise BarrierError("Prova PHP web attiva assente, scaduta o diversa dalla configurazione corrente.")
    return verify_http_active(token, expected_source, expected_config_sha256=_private_config_sha256())


def validate_config(document, *, lock_path=LOCK_PATH, window_path=WINDOW_PATH):
    if not isinstance(document, dict) or set(document) != CONFIG_FIELDS:
        raise BarrierError("Schema request-barrier.json non valido.")
    if (document.get("schema_version") != SCHEMA_VERSION
            or not isinstance(document.get("enabled"), bool)
            or document.get("lock_path") != str(lock_path)
            or document.get("window_path") != str(window_path)
            or not re.fullmatch(r"[a-f0-9]{64}", str(document.get("status_token_sha256", "")))):
        raise BarrierError("Configurazione request barrier non valida o con percorsi inattesi.")
    return document


def validate_window(document):
    if (not isinstance(document, dict) or set(document) != {"schema_version", "operation_id"}
            or document.get("schema_version") != SCHEMA_VERSION
            or not re.fullmatch(r"(?:deploy|rollback|barrier-test)-[a-f0-9]{32}",
                                str(document.get("operation_id", "")))):
        raise BarrierError("Marker request-deploy-window.json non valido.")
    return document


def load_config(path=CONFIG_PATH, *, lock_path=LOCK_PATH, window_path=WINDOW_PATH,
                expected_uid=None):
    if expected_uid is None and hasattr(os, "getuid"):
        expected_uid = os.getuid()
    return validate_config(_load_json(path, expected_uid=expected_uid),
                           lock_path=lock_path, window_path=window_path)


def inspect_lock(lock_path=LOCK_PATH, *, expected_uid=None):
    if expected_uid is None and hasattr(os, "getuid"):
        expected_uid = os.getuid()
    path = pathlib.Path(lock_path)
    parent_fd = _open_checked_dir(path.parent, expected_uid=expected_uid)
    try:
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600
                or (expected_uid is not None and before.st_uid != expected_uid)):
            raise BarrierError("web-request.lock non regolare o con permessi inattesi.")
        return before
    except OSError as exc:
        raise BarrierError("web-request.lock assente o non verificabile.") from exc
    finally:
        os.close(parent_fd)


def arm_operation_window(operation_id, *, state_root=STATE_ROOT, expected_uid=None):
    """Arma il gate HTTP in area privata; un marker non viene mai sovrascritto."""
    _require_posix()
    if not re.fullmatch(r"(?:deploy|rollback|barrier-test)-[a-f0-9]{32}", str(operation_id or "")):
        raise BarrierError("ID finestra operativa non valido.")
    if expected_uid is None:
        expected_uid = os.getuid()
    state_fd = _open_checked_dir(state_root, expected_uid=expected_uid)
    try:
        payload = (json.dumps({"schema_version": SCHEMA_VERSION,
                               "operation_id": operation_id},
                              sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        _write_new_at(state_fd, WINDOW_PATH.name, payload, 0o600)
    except FileExistsError as exc:
        raise BarrierError("Finestra operativa già armata; nessuna sovrascrittura.") from exc
    finally:
        os.close(state_fd)


def complete_operation_window(operation_id, *, state_root=STATE_ROOT, expected_uid=None):
    """Rimuove il marker solo dopo verifica positiva e corrispondenza dell'ID."""
    _require_posix()
    if expected_uid is None:
        expected_uid = os.getuid()
    state_fd = _open_checked_dir(state_root, expected_uid=expected_uid)
    try:
        marker_path = pathlib.Path(state_root) / WINDOW_PATH.name
        raw = _safe_regular_bytes(marker_path, expected_uid=expected_uid)
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BarrierError("Marker finestra non valido; non viene rimosso.") from exc
        if validate_window(document)["operation_id"] != operation_id:
            raise BarrierError("ID operazione diverso dal marker; non viene rimosso.")
        os.unlink(WINDOW_PATH.name, dir_fd=state_fd)
        os.fsync(state_fd)
    finally:
        os.close(state_fd)


@contextlib.contextmanager
def locked_file(lock_path, mode, *, timeout=0.0, poll_interval=0.025, expected_uid=None):
    """Lock sul file persistente verificato; timeout finito e nessun retry indefinito."""
    _require_posix()
    if mode not in ("shared", "exclusive") or timeout < 0 or timeout > 300:
        raise BarrierError("Modalità o timeout lock non validi.")
    if expected_uid is None and hasattr(os, "getuid"):
        expected_uid = os.getuid()
    before = inspect_lock(lock_path, expected_uid=expected_uid)
    path = pathlib.Path(lock_path)
    parent_fd = _open_checked_dir(path.parent, expected_uid=expected_uid)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=parent_fd)
        opened = os.fstat(fd)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or (expected_uid is not None and opened.st_uid != expected_uid)):
            raise BarrierError("web-request.lock sostituito durante l'apertura.")
        operation = fcntl.LOCK_SH if mode == "shared" else fcntl.LOCK_EX
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, operation | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timeout lock {mode} dopo {timeout:.3f}s.")
                time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
        yield fd
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        os.close(parent_fd)


def lock_accessibility_probe(lock_path=LOCK_PATH, *, expected_uid=None):
    """Prova CLI breve; non prova il comportamento della SAPI PHP web."""
    with locked_file(lock_path, "shared", timeout=0, expected_uid=expected_uid):
        return True


def _validated_status_url(url):
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in {"sara-fatto.it", "www.sara-fatto.it"}
            or parsed.path != "/wp-json/sarafatto/v1/deploy-barrier"
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise BarrierError("URL consentito solo sullo status endpoint HTTPS fisso di SaràFatto.")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, new_url):
        return None


def fetch_http_status(token, *, url=STATUS_URL, timeout=10, opener=None):
    _validated_status_url(url)
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256:
        raise BarrierError("Token HTTP di verifica non valido.")
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "Cache-Control": "no-cache",
        "X-Sarafatto-Barrier-Token": token,
    })
    client = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(), _NoRedirect())
    try:
        with client.open(request, timeout=timeout) as response:
            if response.status != 200 or response.geturl() != url:
                raise BarrierError("Risposta HTTP della barriera inattesa o reindirizzata.")
            payload = json.loads(response.read(8193).decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BarrierError(f"Verifica PHP web non riuscita: {type(exc).__name__}.") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise BarrierError("Risposta PHP web non conforme allo schema della barriera.")
    if payload.get("php_sapi") in (None, "cli"):
        raise BarrierError("La risposta non proviene da una SAPI PHP web.")
    if not re.fullmatch(r"[a-f0-9]{64}", str(payload.get("source_sha256", ""))):
        raise BarrierError("Hash sorgente barriera mancante nella risposta PHP web.")
    return payload


def verify_http_active(token, expected_source_sha256, *, url=STATUS_URL,
                       expected_config_sha256=None, opener=None):
    """Gate riutilizzabile: prova che una richiesta PHP web ha acquisito LOCK_SH."""
    if not re.fullmatch(r"[a-f0-9]{64}", str(expected_source_sha256 or "")):
        raise BarrierError("SHA-256 sorgente atteso non valido.")
    payload = fetch_http_status(token, url=url, opener=opener)
    if (payload.get("enabled") is not True or payload.get("lock_accessible") is not True
            or payload.get("lock_acquired") is not True
            or payload.get("window_armed") is not False
            or payload.get("source_sha256") != expected_source_sha256):
        raise BarrierError("La barriera non è attiva e acquisita dalla richiesta PHP web.")
    if expected_config_sha256 is not None and payload.get("config_sha256") != expected_config_sha256:
        raise BarrierError("Configurazione PHP web diversa da quella verificata.")
    return payload


def verify_exclusive_interlock(token, *, url="https://sara-fatto.it/", opener=None):
    """Da invocare solo con marker armato e LOCK_EX già acquisito dal publisher.

    La richiesta radice deve essere respinta dalla barriera con il marker HTTP
    dedicato. Un semplice flock CLI non equivale a questa verifica HTTP.
    """
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in {"sara-fatto.it", "www.sara-fatto.it"}
            or parsed.path != "/" or parsed.query or parsed.fragment):
        raise BarrierError("Interlock HTTP consentito solo sulla homepage HTTPS SaràFatto.")
    request = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache", "X-Sarafatto-Barrier-Token": token,
    })
    client = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(), _NoRedirect())
    try:
        with client.open(request, timeout=10) as response:
            raise BarrierError(f"Interlock non attivo: risposta HTTP {response.status} con LOCK_EX.")
    except urllib.error.HTTPError as exc:
        if exc.code != 503 or exc.headers.get("X-Sarafatto-Deploy-Barrier") != "active":
            raise BarrierError("La risposta non identifica la barriera SaràFatto in finestra esclusiva.") from exc
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare-private", help="crea lock e configurazione privata disabilitata, senza sovrascrivere")
    verify = sub.add_parser("verify-http", help="verifica il lock tramite una richiesta alla SAPI PHP web")
    verify.add_argument("--phase", choices=("accessibility", "active"), required=True)
    sub.add_parser("activate-private", help="attiva dopo una prova HTTP di accessibilità fresca")
    sub.add_parser("assert-ready", help="verifica la prova HTTP attiva richiesta da un futuro publisher")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-private":
            prepare_private()
        elif args.command == "verify-http":
            token = os.environ.get("SARAFATTO_BARRIER_STATUS_TOKEN", "")
            payload = verify_http(token, phase=args.phase)
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        elif args.command == "activate-private":
            activate_private()
            print("Barriera abilitata solo per le richieste PHP che verificano correttamente lock e config.")
        elif args.command == "assert-ready":
            token = os.environ.get("SARAFATTO_BARRIER_STATUS_TOKEN", "")
            result = assert_private_ready(token=token)
            print(json.dumps({"status": "web-barrier-ready-for-transaction",
                              "php_sapi": result["php_sapi"],
                              "source_sha256": result["source_sha256"],
                              "config_sha256": result["config_sha256"]},
                             ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (BarrierError, OSError, TimeoutError) as exc:
        print(f"ERRORE: barriera non verificata: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
