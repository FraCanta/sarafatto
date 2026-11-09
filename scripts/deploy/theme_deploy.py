#!/usr/bin/env python3
"""Theme-only maintenance deployment. Reuses the installed release protocol unchanged."""
import argparse
import base64
import hashlib
import json
import os
import pathlib
import re
import secrets
import sys
import time
import urllib.request
from datetime import datetime, timezone

PRIVATE = pathlib.Path('/home/www/sarafatto-deploy')
PUBLIC = pathlib.Path('/home/www/public/wp-content')
TOOLS = PRIVATE / 'tools/scripts/deploy'
THEME = 'themes/sarafatto/'
ACK = 'theme-only-scheduled-maintenance-nonatomic'


class ThemeDeployError(Exception):
    pass


def require_github_approval(history, reviewer):
    if not isinstance(history, list) or not isinstance(reviewer, str) or not reviewer.strip():
        raise ThemeDeployError('Revisore produzione o cronologia approvazioni assente.')
    relevant = [item for item in history if isinstance(item, dict) and any(
        isinstance(environment, dict) and environment.get('name') == 'ionos-production'
        for environment in item.get('environments', []))]
    if (any(item.get('state') == 'rejected' for item in relevant)
            or not any(item.get('state') == 'approved'
                       and str(item.get('user', {}).get('login', '')).casefold() == reviewer.casefold()
                       for item in relevant)):
        raise ThemeDeployError('Approvazione esplicita ionos-production della sviluppatrice non verificata.')
    return True


def scoped_records(current, artifact):
    """The artifact's plugin/MU bytes are verified but NEVER selected for publication."""
    selected = {row['path']: {k: row[k] for k in ('sha256', 'size', 'mode')}
                for row in current['reference_files'] if not row['path'].startswith(THEME)}
    selected.update({path: row for path, row in artifact.items() if path.startswith(THEME)})
    if not any(path.startswith(THEME) for path in artifact):
        raise ThemeDeployError('Artifact privo del tema.')
    return selected


def assert_theme_plan(plan):
    for change in plan['changes']:
        path = change['path']
        if (not isinstance(path, str) or not path.startswith(THEME)
                or '\\' in path or any(part in ('', '.', '..') for part in path.split('/'))):
            raise ThemeDeployError('Piano non limitato al tema.')


def validate_runtime(payload, operation_id, nonce):
    if (not isinstance(payload, dict) or payload.get('operation_id') != operation_id
            or payload.get('nonce') != nonce
            or not isinstance(payload.get('opcache_loaded'), bool)
            or payload.get('sapi') not in ('fpm-fcgi', 'cgi-fcgi', 'apache2handler', 'litespeed')):
        raise ThemeDeployError('Manutenzione PHP web non dimostrata da risposta fresca.')
    if payload.get('opcache_loaded') is not False:
        if str(payload.get('opcache_enable')).lower() not in ('0', 'off', ''):
            if (str(payload.get('validate_timestamps')).lower() not in ('1', 'on')
                    or str(payload.get('revalidate_freq')) != '0'
                    or str(payload.get('file_cache_only')).lower() not in ('0', 'off', '')):
                raise ThemeDeployError('OPcache web richiede timestamps attivi, revalidate_freq=0 e file_cache_only=0.')
    # No CLI-based inference, opcache_get_status(false) or global reset is used.
    return payload


def maintenance_php(operation_id, token):
    if not re.fullmatch(r'theme-[0-9]+-[0-9]+', operation_id):
        raise ThemeDeployError('Operation ID non valido.')
    digest = hashlib.sha256(token.encode()).hexdigest()
    return ("<?php\n$upgrading = time();\n"
            f"header('X-Sarafatto-Theme-Maintenance: {operation_id}');\n"
            "header('Cache-Control: no-store, max-age=0');\n"
            f"if (hash_equals('{digest}', hash('sha256', $_SERVER['HTTP_X_SARAFATTO_THEME_TOKEN'] ?? ''))) {{\n"
            "header('Content-Type: application/json');\n"
            "echo json_encode(array(\n"
            f"'operation_id'=>'{operation_id}',\n"
            "'nonce'=>($_SERVER['HTTP_X_SARAFATTO_THEME_NONCE'] ?? ''), 'sapi'=>PHP_SAPI,\n"
            "'opcache_loaded'=>extension_loaded('Zend OPcache'), 'opcache_enable'=>ini_get('opcache.enable'),\n"
            "'validate_timestamps'=>ini_get('opcache.validate_timestamps'),\n"
            "'revalidate_freq'=>ini_get('opcache.revalidate_freq'),\n"
            "'file_cache_only'=>ini_get('opcache.file_cache_only'))); exit;\n}\n").encode()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Maintenance:
    """The only public non-theme file is this owned, temporary WordPress marker.

    time() deliberately prevents WP's ten-minute expiry reopening a crashed deploy.
    It is NOT a drain. Existing requests may complete while per-file updates occur.
    """
    def __init__(self, wp_root, operation_id, token, *, opener=None):
        self.root = pathlib.Path(wp_root)
        self.operation_id = operation_id
        self.token = token
        self.payload = maintenance_php(operation_id, token)
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.fd = None

    def __enter__(self):
        import production_adapter as adapter
        adapter._require_fixed_directory(self.root)
        self.fd = adapter._open_checked_dir(self.root, mode=None)
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    def _owned(self):
        import stat
        fd = os.open('.maintenance', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                    or info.st_size != len(self.payload) or (info.st_mode & 0o777) != 0o644
                    or os.read(fd, len(self.payload) + 1) != self.payload):
                raise ThemeDeployError('Marker manutenzione estraneo o alterato; non verrà rimosso.')
            return info
        finally:
            os.close(fd)

    def arm(self, *, recovery=False):
        if recovery:
            try:
                self._owned()
                return
            except FileNotFoundError:
                pass
        # Never expose a partially written PHP marker to a concurrent request.
        # The hard link publishes a complete fsynced file without replacing any
        # maintenance window that appeared concurrently.
        temporary = '.sf-maintenance-' + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            view = memoryview(self.payload)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise ThemeDeployError('Scrittura marker incompleta; intervento necessario.')
                view = view[count:]
            os.fchmod(fd, 0o644)
            os.fsync(fd)
            try:
                os.link(temporary, '.maintenance', src_dir_fd=self.fd, dst_dir_fd=self.fd,
                        follow_symlinks=False)
            except FileExistsError as exc:
                if not recovery:
                    raise ThemeDeployError('Manutenzione preesistente: pubblicazione bloccata.') from exc
                self._owned()
        finally:
            os.close(fd)
            os.unlink(temporary, dir_fd=self.fd)
            os.fsync(self.fd)
        self._owned()

    def probe(self):
        nonce = secrets.token_hex(24)
        request = urllib.request.Request('https://sara-fatto.it/', headers={
            'X-Sarafatto-Theme-Token': self.token, 'X-Sarafatto-Theme-Nonce': nonce,
            'Cache-Control': 'no-cache, no-store'})
        with self.opener.open(request, timeout=15) as response:
            if (response.status != 200 or response.geturl() != request.full_url
                    or response.headers.get('X-Sarafatto-Theme-Maintenance') != self.operation_id):
                raise ThemeDeployError('Probe manutenzione inatteso.')
            payload = json.loads(response.read(8193))
        validate_runtime(payload, self.operation_id, nonce)
        # Also prove that ordinary anonymous traffic is actually denied.
        import urllib.error
        try:
            with self.opener.open(urllib.request.Request('https://sara-fatto.it/', headers={
                    'Cache-Control': 'no-cache, no-store'}), timeout=15):
                raise ThemeDeployError('La homepage anonima non è in manutenzione.')
        except urllib.error.HTTPError as exc:
            if exc.code != 503 or exc.headers.get('X-Sarafatto-Theme-Maintenance') != self.operation_id:
                raise ThemeDeployError('Il 503 non appartiene a questa operazione.') from exc
        return payload

    def reopen(self):
        before = self._owned()
        named = os.stat('.maintenance', dir_fd=self.fd, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
            raise ThemeDeployError('Marker sostituito prima della riapertura.')
        os.unlink('.maintenance', dir_fd=self.fd)
        os.fsync(self.fd)


def _modules():
    # CLI never imports executable dependencies from an uploaded artifact/checkout.
    sys.path.insert(0, str(TOOLS))
    import production_publisher as publisher
    import production_adapter as adapter
    import artifact_transfer_tool as transfer
    if pathlib.Path(publisher.__file__).resolve().parent != TOOLS:
        raise ThemeDeployError('Moduli non caricati dalla toolchain privata fissata.')
    return publisher, adapter, transfer


def _plan(publisher, current, artifact, operation_id, removals, approval):
    if not isinstance(removals, list) or any(not isinstance(row, dict)
            or not str(row.get('path', '')).startswith(THEME) for row in removals):
        raise ThemeDeployError('Rimozioni fuori dal tema.')
    result = publisher.make_release_state_plan(
        current, scoped_records(current, artifact), operation_id,
        approved_removals=removals, removal_approval=approval)
    assert_theme_plan(result['plan'])
    return result


def wordpress_health(*, opener=None, expected_app=None):
    client = opener or urllib.request.build_opener(NoRedirect())
    bodies = {}
    for path in ('/', '/wp-json/'):
        url = 'https://sara-fatto.it' + path
        with client.open(urllib.request.Request(url, headers={'Cache-Control': 'no-cache, no-store'}), timeout=15) as response:
            body = response.read(2*1024*1024 + 1)
            if response.status != 200 or response.geturl() != url or not body or len(body) > 2*1024*1024:
                raise ThemeDeployError('Health WordPress non valido: ' + path)
            bodies[path] = body
    html = bodies['/'].decode('utf-8', errors='replace')
    api = json.loads(bodies['/wp-json/'])
    if ('<html' not in html.lower() or 'wp-content/themes/sarafatto/' not in html
            or any(message in html.lower() for message in ('critical error', 'errore critico', 'fatal error'))
            or not isinstance(api, dict) or not isinstance(api.get('namespaces'), list)
            or 'wp/v2' not in api['namespaces']
            or expected_app is not None and expected_app not in html):
        raise ThemeDeployError('WordPress non sano o homepage ancora riferita al vecchio frontend.')
    return {path: hashlib.sha256(body).hexdigest() for path, body in bodies.items()}


def http_assets(rows):
    return {row['path']: row for row in rows if row['path'].startswith((
        THEME+'assets/dist/assets/', THEME+'assets/images/', THEME+'assets/fonts/'))}


def _health(publisher, window, urls, assets, *, sleeper=time.sleep, expected_app=None):
    """On failure re-arm BEFORE the existing engine attempts parent restoration."""
    try:
        runtime = window.probe()
        # Revalidate on every web request, with a different mtime second and a
        # small settling interval. No claim of all-worker invalidation/drain.
        sleeper(3)
        window.reopen()
        result = publisher.production_health_check(urls=tuple(urls))
        application = wordpress_health(expected_app=expected_app)
        client = urllib.request.build_opener(NoRedirect())
        for path, expected in assets.items():
            from urllib.parse import quote
            url = 'https://sara-fatto.it/wp-content/' + quote(path, safe='/')
            with client.open(urllib.request.Request(url, headers={'Cache-Control': 'no-cache'}), timeout=15) as response:
                raw = response.read(expected['size'] + 1)
                if (response.status != 200 or response.geturl() != url
                        or len(raw) != expected['size'] or hashlib.sha256(raw).hexdigest() != expected['sha256']):
                    raise ThemeDeployError('Asset HTTP diverso dal candidato: ' + path)
        return {**result, 'strategy': ACK, 'runtime': runtime, 'wordpress': application,
                'asset_hash_checks': len(assets)}
    except Exception:
        window.arm(recovery=True)
        raise


def execute(publisher, *, inputs, identity, private_root, public_root, reader,
            command, expected_review=None, removals=(), quota=0, window_factory=Maintenance,
            health=None, sleeper=time.sleep, grace=30, fault_hook=None):
    """Integration API; CLI supplies only FIXED IONOS roots and trusted modules.

    Uses the SAME current-release, journal, snapshots and lock, not a parallel state.
    Test callers supply temporary roots, synthetic HTTP and fault injection.
    """
    sha, run, attempt = identity
    if not re.fullmatch(r'[a-f0-9]{40}', sha) or not re.fullmatch(r'[0-9]+', run) or not re.fullmatch(r'[0-9]+', attempt):
        raise ThemeDeployError('Identità GitHub non valida.')
    if not 0 <= grace <= 120:
        raise ThemeDeployError('Intervallo manutenzione non valido.')
    operation_id = f'theme-{run}-{attempt}'
    private, lock = publisher._open_release_context(private_root, private_root)
    tx_fd = None
    try:
        state_tool = publisher.release_state_tool
        if command == 'recover':
            # The engine must acquire its own lock; release this lock only BEFORE
            # recovery starts. No public writes or state changes have occurred.
            tx_fd = publisher._transaction_directory(private['staging_fd'])
            raw = publisher._read_private_file_at(tx_fd, f'theme-review-{operation_id}.json')
            review = json.loads(raw)
        else:
            current, events = publisher._load_locked_release(private)
            if any(event['operation_id'] == operation_id for event in events):
                raise ThemeDeployError('Operazione già registrata; usare recovery esplicito.')
            publisher.backup_tool.validate_backup_baseline(
                None, current['initial_baseline']['sha256'], state_fd=private['state_fd'])
            publisher._verify_fresh_snapshot(reader, current['release']['inventory_tool_commit'],
                current['reference_files'], current['inventory']['exclusion'], current['inventory_sha256'])
            for key, path in inputs.items():
                publisher._require_staging_path(pathlib.Path(private_root) / 'staging', path, key,
                                               directory=key == 'package')
            artifact = publisher.verify_artifact(inputs['package'], inputs['inventory'], sha,
                provenance_path=inputs['provenance'], archive_path=inputs['archive'], expected_run_id=run)
            tx_fd = publisher._transaction_directory(private['staging_fd'], create=True)
            name = f'theme-review-{operation_id}.json'
            if command == 'publish':
                raw = publisher._read_private_file_at(tx_fd, name)
                review = json.loads(raw)
                removals = review['removals']
                approval = review['removal_approval']
            else:
                approval = None
                if removals:
                    approval = {'approval_id': operation_id, 'reviewer': 'github-environment:ionos-production',
                        'approved_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'parent_release_id': current['release']['release_id'],
                        'parent_inventory_sha256': current['inventory_sha256'],
                        'removals_sha256': state_tool.digest_json(list(removals))}
            planned = _plan(publisher, current, artifact, operation_id, list(removals), approval)
            archive_sha = publisher._artifact_file_digest(pathlib.Path(inputs['archive']), 2*1024**3)
            if command == 'preflight':
                review = {'schema_version': 1, 'scope': THEME, 'operation_id': operation_id,
                    'commit_sha': sha, 'run_id': run, 'attempt': attempt,
                    'parent_sha256': current['state_sha256'], 'parent_release_id': current['release']['release_id'],
                    'artifact_sha256': archive_sha, 'plan_sha256': planned['plan_sha256'],
                    'plan': planned['plan'], 'removals': list(removals), 'removal_approval': approval,
                    'preserved_extras': [row for row in planned['candidate_reference_files']
                                         if row['classification'] != 'artifact'],
                    'token': secrets.token_hex(32), 'public_writes_performed': False}
                raw = state_tool.json_bytes(review)
                publisher._write_private_file_at(tx_fd, name, raw)
                return {'status': 'theme-preflight-verified', 'review_sha256': hashlib.sha256(raw).hexdigest(),
                        **{k: v for k, v in review.items() if k != 'token'}}
            if (hashlib.sha256(raw).hexdigest() != expected_review
                    or review['parent_sha256'] != current['state_sha256']
                    or review['artifact_sha256'] != archive_sha or review['plan'] != planned['plan']):
                raise ThemeDeployError('Revisione, parent o artifact cambiato: nuova approvazione richiesta.')
        if (not re.fullmatch(r'[a-f0-9]{64}', str(expected_review or ''))
                or hashlib.sha256(raw).hexdigest() != expected_review
                or review['operation_id'] != operation_id or review['commit_sha'] != sha
                or review['run_id'] != run or review['scope'] != THEME):
            raise ThemeDeployError('Autorizzazione non corrispondente alla revisione esatta.')
        with window_factory(pathlib.Path(public_root).parent, operation_id, review['token']) as window:
            maintenance_ready = False
            parent_assets = http_assets(current['reference_files']) if command != 'recover' else {}

            def checked_health():
                assets = http_assets(planned['candidate_reference_files'])
                manifest_path = pathlib.Path(inputs['package']) / THEME / 'assets/dist/.vite/manifest.json'
                frontend = json.loads(manifest_path.read_bytes())['assets/src/js/app.js']['file']
                return health(window) if health else _health(publisher, window,
                    ['https://sara-fatto.it/', 'https://sara-fatto.it/wp-json/'], assets,
                    sleeper=sleeper, expected_app=frontend)

            def hook(event, path, count):
                nonlocal maintenance_ready
                if event == 'after-prepared':
                    window.arm()
                    window.probe()
                    maintenance_ready = True
                    sleeper(grace)  # bounded settling period, explicitly NOT proof of drain
                if fault_hook:
                    fault_hook(event, path, count)

            if command == 'recover':
                # Check the scoped durable plan before allowing the old engine to restore.
                manifest = json.loads(publisher._read_private_file_at(tx_fd, f'transaction-{operation_id}.json'))
                assert_theme_plan(manifest['plan'])
                live_state = state_tool.load_current_state(private['state_fd'])
                last_entry = live_state.get('release_chain', {}).get('entries', [])
                if (live_state['state_sha256'] != manifest['parent_state_sha256']
                        and (not last_entry or last_entry[-1]['operation_id'] != operation_id)):
                    raise ThemeDeployError('Recovery superata da una release successiva: nessuna manutenzione armata.')
                window.arm(recovery=True)
                window.probe()
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_UN)
                os.close(lock)
                lock = None
                def recovered_health():
                    return health(window) if health else _health(publisher, window,
                        ['https://sara-fatto.it/', 'https://sara-fatto.it/wp-json/'], {}, sleeper=sleeper)
                result = publisher.recover_filesystem_release(operation_id=operation_id,
                    private_root=private_root, expected_private_root=private_root,
                    public_root=public_root, expected_public_root=public_root,
                    quota_free_bytes=quota, health_check=recovered_health, inventory_reader=reader)
                # already-finalized is a read-only engine branch; still reopen only after web proof.
                try:
                    window._owned()
                except FileNotFoundError:
                    pass
                else:
                    recovered_health()
                return result
            # Do not journal a new deployment over another maintenance window.
            try:
                os.stat('.maintenance', dir_fd=window.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ThemeDeployError('Manutenzione preesistente: nessuna nuova transazione avviata.')

            def parent_health():
                if health:
                    return health(window)
                if maintenance_ready:
                    return _health(publisher, window, ['https://sara-fatto.it/', 'https://sara-fatto.it/wp-json/'],
                                   parent_assets, sleeper=sleeper)
                # Probe failure occurred before publishing/files were attempted.
                # Restore the untouched original site's availability rather than
                # leave it offline merely because its current OPcache policy is unsuitable.
                try:
                    window.reopen()
                    return {**publisher.production_health_check(), 'theme_writes_started': False}
                except Exception:
                    window.arm(recovery=True)
                    raise
            return publisher._run_filesystem_release_transaction(
                operation_kind='publish', operation_id=operation_id, release_id='theme-'+sha[:12]+'-'+run,
                commit_sha=sha, inventory_tool_commit=sha, artifact_sha256=archive_sha,
                source_root=inputs['package'], candidate_rows=planned['candidate_reference_files'],
                plan=planned['plan'], rollback_target_release_id=None,
                approved_removals=removals, current_state=current, private=private, lock_fd=lock,
                private_root=private_root, public_root=public_root, expected_private_root=private_root,
                expected_public_root=public_root, quota_free_bytes=quota, inventory_reader=reader,
                health_check=checked_health,
                rollback_health_check=parent_health,
                fault_hook=hook)
    finally:
        if tx_fd is not None:
            os.close(tx_fd)
        if lock is not None:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
        publisher.backup_tool.close_private_directories(private)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'publish', 'recover'))
    parser.add_argument('--sha', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--toolchain-sha256', required=True)
    parser.add_argument('--review-sha256')
    parser.add_argument('--quota-free-bytes', type=int, default=0)
    parser.add_argument('--acknowledge', choices=(ACK,))
    parser.add_argument('--removals-b64', default='W10=')
    args = parser.parse_args(argv)
    try:
        if args.command != 'preflight' and (args.acknowledge != ACK or args.quota_free_bytes <= 0):
            raise ThemeDeployError('Approvazione manutenzione e quota libera confermata obbligatorie.')
        publisher, adapter, transfer = _modules()
        adapter.verify_private_toolchain(args.toolchain_sha256)
        transfer_id = f'run-{args.run}-{args.sha[:12]}'
        report = transfer.publisher_inputs(transfer_id, args.sha, args.run,
                                          toolchain_sha256=args.toolchain_sha256)
        inputs = report['publisher_inputs']
        removals = json.loads(base64.b64decode(args.removals_b64, validate=True))
        result = execute(publisher, inputs=inputs, identity=(args.sha, args.run, args.attempt),
            private_root=PRIVATE, public_root=PUBLIC, reader=adapter.private_inventory_reader(args.toolchain_sha256),
            command=args.command, expected_review=args.review_sha256, removals=removals,
            quota=args.quota_free_bytes)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print('ERRORE theme deploy fail-closed: '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
