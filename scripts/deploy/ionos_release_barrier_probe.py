#!/usr/bin/env python3
"""Probe filesystem privato e coerenza concorrente, senza accesso alla webroot.

La modalità IONOS scrive soltanto in una nuova directory sotto
/home/www/sarafatto-deploy/staging/. Non ripulisce mai run precedenti.
"""

import argparse
try:
    import fcntl
except ImportError:  # Importabile per validazione/test statici anche su Windows.
    fcntl = None
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone

STAGING_ROOT = pathlib.Path("/home/www/sarafatto-deploy/staging")
PUBLIC_ROOT = pathlib.Path("/home/www/public")
COMPONENTS = ("theme", "plugin", "mu_plugin", "assets")
VERSION_FILES = {name: f"{name}/release.txt" for name in COMPONENTS}


class ProbeError(Exception):
    """Probe non sicuro o risultato non verificabile."""


def _require_posix():
    if (os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd or os.rename not in os.supports_dir_fd
            or os.symlink not in os.supports_dir_fd):
        raise ProbeError("Sono richieste primitive POSIX dir_fd, O_NOFOLLOW e symlink.")


def _open_dir_at(parent_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise ProbeError(f"Componente non directory: {name}.")
    return fd


def _open_absolute_dir(path):
    """Apre un path assoluto componente per componente senza seguire symlink."""
    path = pathlib.PurePosixPath(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ProbeError("Percorso assoluto non valido.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:]:
            next_fd = _open_dir_at(fd, component)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_staging_root():
    staging_fd = _open_absolute_dir(str(STAGING_ROOT))
    info = os.fstat(staging_fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(staging_fd)
        raise ProbeError("staging deve appartenere all'utente corrente e avere permessi 0700.")
    public = pathlib.Path(str(PUBLIC_ROOT))
    # La webroot non viene aperta né usata; il controllo è lessicale e impedisce
    # in futuro di accettarla accidentalmente come destinazione del probe.
    if STAGING_ROOT == public or public in STAGING_ROOT.parents or STAGING_ROOT in public.parents:
        os.close(staging_fd)
        raise ProbeError("La destinazione del probe interseca la root pubblica vietata.")
    return staging_fd


def _mkdir_open(parent_fd, name):
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    return _open_dir_at(parent_fd, name)


def _write_new_at(directory_fd, name, content, mode=0o600):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 mode, dir_fd=directory_fd)
    try:
        raw = content.encode("utf-8")
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_at(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096:
            raise ProbeError(f"File fixture non regolare: {name}.")
        return os.read(fd, 4097).decode("utf-8")
    finally:
        os.close(fd)


def _open_relative_dir(root_fd, relative):
    current = os.dup(root_fd)
    try:
        for component in relative.split("/"):
            if component in ("", ".", ".."):
                raise ProbeError("Percorso relativo non sicuro.")
            next_fd = _open_dir_at(current, component)
            os.close(current)
            current = next_fd
        return current
    except Exception:
        os.close(current)
        raise


def _version_vector(root_fd):
    result = {}
    for component, filename in VERSION_FILES.items():
        directory_fd = _open_relative_dir(root_fd, component)
        try:
            result[component] = _read_at(directory_fd, "release.txt").strip()
        finally:
            os.close(directory_fd)
    return result


def _make_release(root_fd, release_name, version):
    release_fd = _mkdir_open(root_fd, release_name)
    try:
        for component in COMPONENTS:
            component_fd = _mkdir_open(release_fd, component)
            try:
                _write_new_at(component_fd, "release.txt", version + "\n")
            finally:
                os.close(component_fd)
        os.fsync(release_fd)
    finally:
        os.close(release_fd)


def _make_symlink_at(target, link_name, directory_fd):
    os.symlink(target, link_name, dir_fd=directory_fd)


def _switch_symlink(directory_fd, link_name, target):
    temporary = ".switch-" + uuid.uuid4().hex
    _make_symlink_at(target, temporary, directory_fd)
    try:
        os.replace(temporary, link_name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except Exception:
        # Lasciare un elemento temporaneo in staging è preferibile a una pulizia
        # che possa cancellare un oggetto sostituito concorrente.
        raise


def _pin_current_release(releases_fd):
    target = os.readlink("current", dir_fd=releases_fd)
    if target not in ("release-A", "release-B"):
        raise ProbeError("Target del puntatore corrente non ammesso.")
    return _open_dir_at(releases_fd, target)


def _php_cli_probe(run_path):
    php = shutil.which("php")
    if not php:
        return {"available": False, "note": "PHP CLI non disponibile; SAPI web non verificabile."}
    code = (
        "$p=$argv[1]; echo json_encode(["
        "'version'=>PHP_VERSION,'sapi'=>PHP_SAPI,"
        "'realpath'=>realpath($p), 'include_result'=>include $p,"
        "'open_basedir'=>ini_get('open_basedir'),"
        "'opcache.enable'=>ini_get('opcache.enable'),"
        "'opcache.enable_cli'=>ini_get('opcache.enable_cli'),"
        "'realpath_cache_ttl'=>ini_get('realpath_cache_ttl'),"
        "'realpath_cache_size'=>ini_get('realpath_cache_size')]);"
    )
    try:
        result = subprocess.run([php, "-r", code, str(run_path)], capture_output=True,
                                text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": type(exc).__name__,
                "note": "PHP CLI non verificabile; SAPI web non verificabile."}
    if result.returncode != 0:
        return {"available": True, "exit_code": result.returncode,
                "stderr": result.stderr[:1000], "note": "Il risultato non descrive PHP-FPM."}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": True, "output": result.stdout[:1000],
                "note": "Output PHP CLI non parsabile; SAPI web non verificabile."}
    data["note"] = "Valori PHP CLI soltanto; non provano configurazione o comportamento PHP-FPM/WordPress."
    return data


def _filesystem_primitives(run_fd, run_path):
    result = {}
    _write_new_at(run_fd, "rename-source.txt", "rename-probe\n")
    os.rename("rename-source.txt", "rename-file.txt", src_dir_fd=run_fd, dst_dir_fd=run_fd)
    result["file_rename"] = _read_at(run_fd, "rename-file.txt").strip() == "rename-probe"

    os.mkdir("rename-dir-source", 0o700, dir_fd=run_fd)
    os.rename("rename-dir-source", "rename-dir-target", src_dir_fd=run_fd, dst_dir_fd=run_fd)
    result["directory_rename"] = stat.S_ISDIR(os.stat("rename-dir-target", dir_fd=run_fd,
                                                     follow_symlinks=False).st_mode)

    _write_new_at(run_fd, "permission-probe.txt", "private\n", 0o600)
    permission_info = os.stat("permission-probe.txt", dir_fd=run_fd, follow_symlinks=False)
    result["private_mode_0600"] = stat.S_IMODE(permission_info.st_mode) == 0o600

    link_target = "rename-file.txt"
    _make_symlink_at(link_target, "symlink-probe", run_fd)
    link_info = os.stat("symlink-probe", dir_fd=run_fd, follow_symlinks=False)
    result["symlink_created"] = stat.S_ISLNK(link_info.st_mode)
    result["symlink_target"] = os.readlink("symlink-probe", dir_fd=run_fd)
    result["symlink_realpath"] = os.path.realpath(run_path / "symlink-probe")

    file_fd = os.open("rename-file.txt", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=run_fd)
    try:
        os.fsync(file_fd)
    finally:
        os.close(file_fd)
    os.fsync(run_fd)
    result["fsync_file_and_directory"] = True
    _write_new_at(run_fd, "php-path-probe.php", "<?php return 'sf-private-include-ok';\n")
    result["php_cli"] = _php_cli_probe(run_path / "php-path-probe.php")
    lock_path = run_path / "flock-probe.lock"
    lock_fd = os.open("flock-probe.lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=run_fd)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_result = {"acquired": False}
        finished = threading.Event()

        def contender():
            other_fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                try:
                    fcntl.flock(other_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock_result["acquired"] = True
                except BlockingIOError:
                    lock_result["acquired"] = False
            finally:
                os.close(other_fd)
                finished.set()

        worker = threading.Thread(target=contender)
        worker.start()
        if not finished.wait(timeout=5):
            raise ProbeError("Il test flock non ha risposto entro il timeout.")
        worker.join()
        result["flock_exclusive"] = lock_result["acquired"] is False
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    return result


def _model_in_place(releases_fd):
    # Deterministic interleaving: reader samples after one component changed.
    source_fd = _open_dir_at(releases_fd, "release-A")
    live_fd = _mkdir_open(releases_fd, "in-place")
    try:
        for component in COMPONENTS:
            source_component_fd = _open_dir_at(source_fd, component)
            target_component_fd = _mkdir_open(live_fd, component)
            try:
                _write_new_at(target_component_fd, "release.txt",
                              _read_at(source_component_fd, "release.txt"))
            finally:
                os.close(source_component_fd)
                os.close(target_component_fd)
        for component in COMPONENTS:
            component_fd = _open_dir_at(live_fd, component)
            try:
                fd = os.open("release.txt", os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
                             dir_fd=component_fd)
                try:
                    os.write(fd, b"B\n")
                    os.fsync(fd)
                finally:
                    os.close(fd)
                observed = _version_vector(live_fd)
                if len(set(observed.values())) > 1:
                    return {"mixed_state_observed": True, "sample": observed}
            finally:
                os.close(component_fd)
    finally:
        os.close(source_fd)
        os.close(live_fd)
    return {"mixed_state_observed": False}


def _model_component_symlinks(releases_fd):
    root_fd = _mkdir_open(releases_fd, "component-links")
    try:
        for component in COMPONENTS:
            _make_symlink_at(f"../release-A/{component}", component, root_fd)
        # Un aggiornamento sequenziale dei quattro alias espone una finestra mista.
        _switch_symlink(root_fd, "theme", "../release-B/theme")
        observed = {}
        for component in COMPONENTS:
            target = os.readlink(component, dir_fd=root_fd)
            expected_target = f"../release-A/{component}"
            if target not in (expected_target, f"../release-B/{component}"):
                raise ProbeError("Alias componente punta a un target non ammesso.")
            release_name = target.split("/")[1]
            release_fd = _open_dir_at(releases_fd, release_name)
            try:
                component_fd = _open_dir_at(release_fd, component)
                try:
                    observed[component] = _read_at(component_fd, "release.txt").strip()
                finally:
                    os.close(component_fd)
            finally:
                os.close(release_fd)
        return {"mixed_state_observed": len(set(observed.values())) > 1,
                "sample_after_first_alias_switch": observed}
    finally:
        os.close(root_fd)


def _model_root_pointer(releases_fd):
    _make_symlink_at("release-A", "current", releases_fd)
    counts = {"requests": 0, "mixed": 0, "errors": []}
    counts_lock = threading.Lock()
    start = threading.Barrier(5)

    def reader():
        try:
            start.wait(timeout=5)
            for _ in range(80):
                pinned_fd = _pin_current_release(releases_fd)
                try:
                    vector = _version_vector(pinned_fd)
                finally:
                    os.close(pinned_fd)
                with counts_lock:
                    counts["requests"] += 1
                    counts["mixed"] += int(len(set(vector.values())) > 1)
        except Exception as exc:
            with counts_lock:
                counts["errors"].append(type(exc).__name__)

    readers = [threading.Thread(target=reader) for _ in range(4)]
    for worker in readers:
        worker.start()
    start.wait(timeout=5)
    for index in range(80):
        _switch_symlink(releases_fd, "current", "release-B" if index % 2 == 0 else "release-A")
    for worker in readers:
        worker.join(timeout=10)
    if any(worker.is_alive() for worker in readers):
        raise ProbeError("Thread reader non terminato entro il timeout.")
    return {"requests": counts["requests"], "mixed_requests": counts["mixed"],
            "reader_errors": counts["errors"],
            "note": "Simulazione filesystem Python: non prova la risoluzione dei path da PHP-FPM."}


def _model_maintenance_does_not_drain(releases_fd):
    source_fd = _open_dir_at(releases_fd, "release-A")
    live_fd = _mkdir_open(releases_fd, "maintenance-live")
    try:
        for component in COMPONENTS:
            src = _open_dir_at(source_fd, component)
            dst = _mkdir_open(live_fd, component)
            try:
                _write_new_at(dst, "release.txt", _read_at(src, "release.txt"))
            finally:
                os.close(src)
                os.close(dst)

        # Una richiesta già partita legge il tema A prima della manutenzione.
        theme_fd = _open_dir_at(live_fd, "theme")
        try:
            first = _read_at(theme_fd, "release.txt").strip()
        finally:
            os.close(theme_fd)
        # La pagina di manutenzione può fermare nuove richieste; non sincronizza
        # né termina questa richiesta già attiva mentre i file cambiano in-place.
        rest = {}
        for component in COMPONENTS[1:]:
            component_fd = _open_dir_at(live_fd, component)
            try:
                fd = os.open("release.txt", os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
                             dir_fd=component_fd)
                try:
                    os.write(fd, b"B\n")
                    os.fsync(fd)
                finally:
                    os.close(fd)
                rest[component] = _read_at(component_fd, "release.txt").strip()
            finally:
                os.close(component_fd)
        vector = {"theme": first, **rest}
        return {"mixed_state_observed": len(set(vector.values())) > 1,
                "already_started_request": vector,
                "conclusion": "Maintenance da sola non prova il drain dei worker già attivi."}
    finally:
        os.close(source_fd)
        os.close(live_fd)


def run_probe(root_fd, run_path):
    _require_posix()
    result = {"schema_version": 1, "public_root_touched": False,
              "run_directory": str(run_path), "filesystem": {}, "strategies": {}}
    result["filesystem"] = _filesystem_primitives(root_fd, run_path)
    releases_fd = _mkdir_open(root_fd, "releases")
    try:
        _make_release(releases_fd, "release-A", "A")
        _make_release(releases_fd, "release-B", "B")
        result["strategies"]["in_place"] = _model_in_place(releases_fd)
        result["strategies"]["component_symlinks"] = _model_component_symlinks(releases_fd)
        result["strategies"]["single_release_pointer"] = _model_root_pointer(releases_fd)
        result["strategies"]["maintenance_only"] = _model_maintenance_does_not_drain(releases_fd)
    finally:
        os.close(releases_fd)
    return result


def _create_run(staging_fd):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"ionos-release-probe-{timestamp}-{uuid.uuid4().hex[:12]}"
    os.mkdir(name, 0o700, dir_fd=staging_fd)
    run_fd = _open_dir_at(staging_fd, name)
    return name, run_fd


def run_ionos_diagnostic():
    _require_posix()
    staging_fd = _open_staging_root()
    try:
        name, run_fd = _create_run(staging_fd)
        run_path = STAGING_ROOT / name
        try:
            result = run_probe(run_fd, run_path)
            result["staging_root"] = str(STAGING_ROOT)
            result["preserved_prior_runs"] = True
            report = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            _write_new_at(run_fd, "report.json", report)
            os.fsync(run_fd)
            return result
        finally:
            os.close(run_fd)
    finally:
        os.close(staging_fd)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("command", choices=("diagnose",))
    return root


def main(argv=None):
    parser().parse_args(argv)
    try:
        report = run_ionos_diagnostic()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (OSError, ProbeError, ValueError) as exc:
        print(f"ERRORE: probe interrotto senza cleanup automatico: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
