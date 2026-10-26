#!/usr/bin/env python3
"""Bootstrap e validazione del registro privato dello stato release.

Questo modulo non pubblica file e non offre un comando per confermare un deploy.
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
from datetime import datetime, timezone

import baseline_tool as baseline

try:
    import fcntl
except ImportError:  # IONOS e CI Linux; importabile anche nei test statici Windows.
    fcntl = None

PRIVATE_ROOT = pathlib.Path("/home/www/sarafatto-deploy")
PUBLIC_ROOT = pathlib.Path("/home/www/public/wp-content")
STATE_SCHEMA = 1
STATE_NAME = "current-release.json"
JOURNAL_NAME = "operation-journal.jsonl"
MAX_STATE_BYTES = 20_000_000
MAX_JOURNAL_BYTES = 5_000_000
INITIAL_BASELINE_SHA256 = "07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd"
OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
OPERATION_STATES = (
    "prepared", "backup_verified", "publishing", "files_verified",
    "health_verified", "committed", "recovery_required",
)


class ReleaseStateError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def inventory_digest_json(inventory):
    """Digest del perimetro gestito; i conteggi della directory esclusa non sono release state."""
    canonical = json.loads(json.dumps(inventory))
    exclusion = canonical.get("exclusion", {})
    exclusion["files"] = 0
    exclusion["symlinks"] = 0
    return digest_json(canonical)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseStateError(f"Chiave JSON duplicata: {key}.")
        result[key] = value
    return result


def _read_json(raw, label):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReleaseStateError(f"JSON {label} non valido.") from exc


def _read_at(directory_fd, name, label, limit):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ReleaseStateError(f"{label} assente o non apribile senza symlink.") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or os.name == "posix" and info.st_nlink != 1
                or os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600)):
            raise ReleaseStateError(f"{label} non regolare, hard link inatteso, troppo grande o con permessi inattesi.")
        chunks, total = [], 0
        while True:
            block = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise ReleaseStateError(f"{label} supera il limite.")
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _canonical_inventory(files, symlinks, exclusion):
    return {
        "files": [{"path": path, **files[path]} for path in sorted(files)],
        "symlinks": sorted(symlinks, key=lambda row: row["path"]),
        "exclusion": exclusion,
    }


def _expected_from_baseline(document):
    expected = {}
    for group, classification in (("managed_files", "artifact"), ("accepted_extras", None)):
        records = document.get(group)
        if not isinstance(records, list):
            raise ReleaseStateError(f"Elenco {group} della baseline non valido.")
        for row in records:
            if not isinstance(row, dict):
                raise ReleaseStateError(f"Record {group} della baseline non valido.")
            path = row.get("path")
            mode, size, sha = row.get("mode"), row.get("size"), row.get("sha256")
            kind = row.get("classification", classification)
            if (not baseline.safe_path(path) or baseline.excluded(path)
                    or not isinstance(size, int) or isinstance(size, bool) or size < 0
                    or not re.fullmatch(r"[0-7]{3,5}", str(mode))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(sha))
                    or not isinstance(kind, str) or path in expected):
                raise ReleaseStateError(f"Record baseline non valido o duplicato: {path}.")
            expected[path] = {"path": path, "sha256": sha, "size": size,
                              "mode": str(mode), "classification": kind}
    if not expected:
        raise ReleaseStateError("La baseline non contiene file.")
    return expected


def _validate_inventory(text, expected):
    try:
        files, symlinks, exclusion = baseline.parse_remote_text(text)
    except baseline.BaselineError as exc:
        raise ReleaseStateError("Inventario pubblico fresco malformato.") from exc
    if symlinks:
        raise ReleaseStateError("Symlink rilevati nel perimetro pubblico gestito.")
    if exclusion.get("path") != baseline.EXCLUDED + "/":
        raise ReleaseStateError("Record esclusione node_modules non valido.")
    missing, extra = set(expected) - set(files), set(files) - set(expected)
    changed = sorted(path for path in set(expected) & set(files) if any(
        expected[path][key] != files[path][key] for key in ("sha256", "size", "mode")
    ))
    if missing or extra or changed:
        raise ReleaseStateError(
            f"Inventario pubblico diverso dalla baseline: mancanti={len(missing)}, "
            f"extra={len(extra)}, modificati={len(changed)}."
        )
    return _canonical_inventory(files, [], exclusion)


def _state_payload(state):
    document = dict(state)
    document.pop("state_sha256", None)
    document["state_sha256"] = digest_json(document)
    return json_bytes(document)


def validate_state_document(document, expected_baseline_sha=None):
    if not isinstance(document, dict) or document.get("schema_version") != STATE_SCHEMA:
        raise ReleaseStateError("Schema current-release non supportato.")
    recorded = document.get("state_sha256")
    unsigned = dict(document)
    unsigned.pop("state_sha256", None)
    if not re.fullmatch(r"[a-f0-9]{64}", str(recorded or "")) or digest_json(unsigned) != recorded:
        raise ReleaseStateError("Digest interno current-release non valido.")
    baseline_info = document.get("initial_baseline")
    release = document.get("release")
    inventory = document.get("inventory")
    if (not isinstance(baseline_info, dict) or not isinstance(release, dict)
            or not isinstance(inventory, dict) or not isinstance(document.get("provenance"), dict)
            or not isinstance(document.get("verification"), dict)):
        raise ReleaseStateError("Sezioni current-release mancanti.")
    provenance = document["provenance"]
    verification = document["verification"]
    if (not re.fullmatch(r"[a-f0-9]{64}", str(baseline_info.get("sha256", "")))
            or expected_baseline_sha is not None
            and (not re.fullmatch(r"[a-f0-9]{64}", str(expected_baseline_sha))
                 or baseline_info["sha256"] != expected_baseline_sha)
            or not re.fullmatch(r"[a-f0-9]{40}", str(release.get("commit_sha", "")))
            or not isinstance(release.get("release_id"), str)
            or verification.get("status") != "verified-current"):
        raise ReleaseStateError("Riferimenti o stato di verifica current-release non validi.")
    # In Fase 3D.1 l'unica provenienza producibile è il bootstrap iniziale.
    # Stati post-deploy restano rifiutati fino a un futuro verificatore di transazione.
    if (provenance.get("kind") != "initial-baseline-content-match"
            or provenance.get("baseline_provenance") != "bootstrap-content-match"
            or release.get("commit_sha") != baseline_info.get("commit_sha")
            or release.get("release_id") != baseline_info.get("release_id")
            or release.get("inventory_tool_commit") != baseline_info.get("commit_sha")
            or verification.get("fresh_inventory_count") != 2
            or not isinstance(verification.get("verified_at_utc"), str)):
        raise ReleaseStateError("Provenienza current-release non prodotta dal bootstrap verificato.")
    if not re.fullmatch(r"[a-f0-9]{40}", str(release.get("inventory_tool_commit", ""))):
        raise ReleaseStateError("Commit dello strumento inventario non valido.")
    if (inventory_digest_json(inventory) != document.get("inventory_sha256")
            or release.get("inventory_sha256") != document.get("inventory_sha256")):
        raise ReleaseStateError("Digest inventario current-release non valido.")
    files = inventory.get("files")
    if not isinstance(files, list) or not files or inventory.get("symlinks") != []:
        raise ReleaseStateError("Inventario registrato non valido o contiene symlink.")
    if (verification.get("public_files") != len(files)
            or verification.get("managed_symlinks") != 0):
        raise ReleaseStateError("Conteggi di verifica current-release non coerenti.")
    seen = set()
    for row in files:
        if not isinstance(row, dict):
            raise ReleaseStateError("Record inventario current-release non valido.")
        path = row.get("path")
        if (not baseline.safe_path(path) or baseline.excluded(path) or path in seen
                or not re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", "")))
                or not isinstance(row.get("size"), int) or isinstance(row.get("size"), bool)
                or row["size"] < 0 or not re.fullmatch(r"[0-7]{3,5}", str(row.get("mode", "")))):
            raise ReleaseStateError(f"Record inventario non valido: {path}.")
        seen.add(path)
    exclusion = inventory.get("exclusion")
    if (not isinstance(exclusion, dict) or exclusion.get("path") != baseline.EXCLUDED + "/"
            or not isinstance(exclusion.get("files"), int) or isinstance(exclusion.get("files"), bool)
            or exclusion["files"] < 0 or not isinstance(exclusion.get("symlinks"), int)
            or isinstance(exclusion.get("symlinks"), bool) or exclusion["symlinks"] < 0
            or any(key not in document for key in ("active_operation", "candidate_release", "pre_deploy_backup"))
            or document.get("active_operation") is not None
            or document.get("candidate_release") is not None
            or document.get("pre_deploy_backup") is not None
            or not isinstance(document.get("last_successful_operation"), dict)):
        raise ReleaseStateError("Campi operativi non iniziali current-release non supportati in questa fase.")
    last = document["last_successful_operation"]
    if (not OPERATION_ID_RE.fullmatch(str(last.get("operation_id", "")))
            or last.get("status") != "verified"
            or last.get("kind") != "verified-content-bootstrap"
            or last.get("operation_id") != "baseline-bootstrap-" + release["commit_sha"][:12]
            or not isinstance(last.get("completed_at_utc"), str)):
        raise ReleaseStateError("Ultima operazione conclusa current-release non valida.")
    reference_files = document.get("reference_files")
    if not isinstance(reference_files, list) or len(reference_files) != len(files):
        raise ReleaseStateError("Snapshot file di riferimento assente o incoerente.")
    by_path = {row["path"]: row for row in files}
    seen_reference = set()
    for row in reference_files:
        if not isinstance(row, dict):
            raise ReleaseStateError("Record file di riferimento non valido.")
        path = row.get("path")
        if (path in seen_reference or path not in by_path
                or any(row.get(key) != by_path[path].get(key) for key in ("sha256", "size", "mode"))
                or not isinstance(row.get("classification"), str)):
            raise ReleaseStateError(f"File di riferimento incoerente: {path}.")
        seen_reference.add(path)
    return document


def read_journal_at(state_fd):
    try:
        fd = os.open(JOURNAL_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=state_fd)
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise ReleaseStateError("Journal operazioni non apribile senza symlink.") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JOURNAL_BYTES
                or os.name == "posix" and info.st_nlink != 1
                or os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600)):
            raise ReleaseStateError("Journal non regolare, hard link inatteso, troppo grande o con permessi inattesi.")
        chunks, total = [], 0
        while True:
            block = os.read(fd, min(1024 * 1024, MAX_JOURNAL_BYTES + 1 - total))
            if not block:
                break
            total += len(block)
            if total > MAX_JOURNAL_BYTES:
                raise ReleaseStateError("Journal supera il limite.")
            chunks.append(block)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if not raw:
        raise ReleaseStateError("Journal esistente ma vuoto: probabile interruzione di scrittura.")
    events = []
    previous = "0" * 64
    operation_status = {}
    journal_operation_id = None
    allowed_next = {
        None: {"prepared"}, "prepared": {"backup_verified", "recovery_required"},
        "backup_verified": {"publishing", "recovery_required"},
        "publishing": {"files_verified", "recovery_required"},
        "files_verified": {"health_verified", "recovery_required"},
        # Nessuna transizione a committed è ammessa finché manca il verificatore
        # della transazione di pubblicazione previsto per una fase successiva.
        "health_verified": {"recovery_required"},
        "recovery_required": set(),
    }
    for number, line in enumerate(raw.splitlines(), 1):
        event = _read_json(line, f"journal riga {number}")
        if (not isinstance(event, dict)
                or set(event) != {"operation_id", "status", "timestamp_utc", "details",
                                  "previous_event_sha256", "event_sha256"}
                or event.get("previous_event_sha256") != previous
                or not isinstance(event.get("details"), dict)
                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                                    str(event.get("timestamp_utc", "")))):
            raise ReleaseStateError("Catena journal non valida.")
        event_hash = event.get("event_sha256")
        unsigned = dict(event)
        unsigned.pop("event_sha256", None)
        if not re.fullmatch(r"[a-f0-9]{64}", str(event_hash or "")) or digest_json(unsigned) != event_hash:
            raise ReleaseStateError("Digest evento journal non valido.")
        operation_id, status = event.get("operation_id"), event.get("status")
        if not OPERATION_ID_RE.fullmatch(str(operation_id or "")) or status not in OPERATION_STATES:
            raise ReleaseStateError("Evento journal con ID o stato non valido.")
        if status == "committed":
            raise ReleaseStateError("Evento committed rifiutato: nessun verificatore di deploy è abilitato in Fase 3D.1.")
        if journal_operation_id is None:
            journal_operation_id = operation_id
        elif operation_id != journal_operation_id:
            raise ReleaseStateError("Journal con operazioni intercalate o ID duplicati non consentiti.")
        prior_status = operation_status.get(operation_id)
        if status not in allowed_next.get(prior_status, set()):
            raise ReleaseStateError(f"Sequenza journal non valida: {prior_status} -> {status}.")
        operation_status[operation_id] = status
        events.append(event)
        previous = event_hash
    return events


def unresolved_operation(events):
    active = {}
    for event in events:
        operation_id = event["operation_id"]
        if event["status"] == "committed":
            raise ReleaseStateError("Evento committed rifiutato: nessun verificatore di deploy è abilitato in Fase 3D.1.")
        active[operation_id] = event
    unresolved = list(active.values())
    if unresolved:
        latest = unresolved[-1]
        raise ReleaseStateError(
            f"Operazione incompleta {latest['operation_id']} ({latest['status']}); "
            "richiesta riconciliazione manuale."
        )


def append_operation_event(state_fd, locks_fd, operation_id, status, details):
    """Aggiunge un evento sotto site-operation.lock; non pubblica né committa release."""
    if not OPERATION_ID_RE.fullmatch(str(operation_id)) or status not in OPERATION_STATES:
        raise ReleaseStateError("ID o stato operazione non validi.")
    if status == "committed":
        raise ReleaseStateError("La conferma committed richiede il futuro verificatore di deploy.")
    if not isinstance(details, dict):
        raise ReleaseStateError("Dettagli evento non validi.")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ReleaseStateError("Journal richiede openat/O_NOFOLLOW POSIX.")
    lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
    try:
        events = read_journal_at(state_fd)
        active = {}
        for prior_event in events:
            active[prior_event["operation_id"]] = prior_event
        if any(key != operation_id for key in active):
            raise ReleaseStateError("Un'altra operazione è incompleta; journal in sola lettura.")
        prior_status = active.get(operation_id, {}).get("status")
        transitions = {
            None: {"prepared"}, "prepared": {"backup_verified", "recovery_required"},
            "backup_verified": {"publishing", "recovery_required"},
            "publishing": {"files_verified", "recovery_required"},
            "files_verified": {"health_verified", "recovery_required"},
            "health_verified": {"recovery_required"},
        }
        if status not in transitions.get(prior_status, set()):
            raise ReleaseStateError(f"Transizione journal non consentita: {prior_status} -> {status}.")
        previous = events[-1]["event_sha256"] if events else "0" * 64
        event = {"operation_id": operation_id, "status": status, "timestamp_utc": utc_now(),
                 "details": details, "previous_event_sha256": previous}
        event["event_sha256"] = digest_json(event)
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        if len(payload) > 64 * 1024:
            raise ReleaseStateError("Evento journal troppo grande.")
        fd = os.open(JOURNAL_NAME, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                     0o600, dir_fd=state_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise ReleaseStateError("Journal non regolare o con permessi inattesi.")
            if info.st_size + len(payload) > MAX_JOURNAL_BYTES:
                raise ReleaseStateError("Journal al limite dimensionale; rotazione manuale non implementata.")
            if os.write(fd, payload) != len(payload):
                raise ReleaseStateError("Scrittura journal incompleta.")
            os.fsync(fd)
            os.fsync(state_fd)
        finally:
            os.close(fd)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def load_current_state(state_fd, expected_baseline_sha=None):
    raw = _read_at(state_fd, STATE_NAME, "Stato release corrente", MAX_STATE_BYTES)
    return validate_state_document(_read_json(raw, "current-release"), expected_baseline_sha)


def _open_dir(parent_fd, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        raise ReleaseStateError(f"Directory privata non sicura: {name}.") from exc
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(fd)
        raise ReleaseStateError(f"Proprietario o permessi inattesi: {name}.")
    return fd


def _assert_named(parent_fd, name, descriptor, label):
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise ReleaseStateError(f"Directory privata {label} non più raggiungibile dal percorso autorizzato.") from exc
    if (stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode)
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)
            or named.st_uid != os.getuid() or stat.S_IMODE(named.st_mode) != 0o700):
        raise ReleaseStateError(f"Directory privata {label} sostituita durante l'operazione.")


def _assert_root_path(path, descriptor):
    try:
        named = pathlib.Path(path).lstat()
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise ReleaseStateError("Root privata non più raggiungibile.") from exc
    if (stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode)
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)
            or named.st_uid != os.getuid() or stat.S_IMODE(named.st_mode) != 0o700):
        raise ReleaseStateError("Root privata sostituita durante l'operazione.")


def _atomic_create_state(state_fd, state):
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd or os.link not in os.supports_dir_fd:
        raise ReleaseStateError("Bootstrap sicuro richiede primitive POSIX dir_fd/O_NOFOLLOW/linkat.")
    payload = _state_payload(state)
    tmp = ".current-release.tmp." + os.urandom(12).hex()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(tmp, flags, 0o600, dir_fd=state_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ReleaseStateError("Temporaneo current-release non regolare.")
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ReleaseStateError("Scrittura current-release incompleta.")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp, dir_fd=state_fd)
        except OSError:
            pass
        raise
    else:
        os.close(fd)
    try:
        readback = _read_at(state_fd, tmp, "Temporaneo current-release", MAX_STATE_BYTES)
        if readback != payload or _read_json(readback, "current-release temporaneo") != {
                **state, "state_sha256": digest_json(state)}:
            raise ReleaseStateError("Verifica readback del temporaneo current-release fallita.")
        os.link(tmp, STATE_NAME, src_dir_fd=state_fd, dst_dir_fd=state_fd, follow_symlinks=False)
        os.fsync(state_fd)
    except FileExistsError as exc:
        raise ReleaseStateError("current-release.json già presente: nessuna sovrascrittura.") from exc
    finally:
        try:
            os.unlink(tmp, dir_fd=state_fd)
            os.fsync(state_fd)
        except FileNotFoundError:
            pass
    return hashlib.sha256(payload).hexdigest()


def bootstrap_current_release(*, private_root=PRIVATE_ROOT, expected_root=PRIVATE_ROOT,
                              public_root=PUBLIC_ROOT, inventory_reader=None, confirmation=None):
    """Inizializza solo current-release.json da due inventari freschi uguali alla baseline."""
    if pathlib.Path(public_root) != PUBLIC_ROOT:
        raise ReleaseStateError("Root pubblica fissa non modificabile.")
    if (fcntl is None or os.name != "posix" or not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")):
        raise ReleaseStateError("Bootstrap sicuro richiede primitive POSIX flock/openat.")
    state_path, locks_path = baseline.validate_private_state(private_root, expected_root)
    root_fd = os.open(private_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    state_fd = lock_fd = None
    try:
        state_fd = _open_dir(root_fd, "state")
        locks_fd = _open_dir(root_fd, "locks")
        _assert_root_path(private_root, root_fd)
        _assert_named(root_fd, "state", state_fd, "state")
        _assert_named(root_fd, "locks", locks_fd, "locks")
        lock_fd = baseline.acquire_baseline_lock(locks_path, locks_fd)
        try:
            os.stat(STATE_NAME, dir_fd=state_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ReleaseStateError("Stato current-release già presente; bootstrap una tantum bloccato.")
        events = read_journal_at(state_fd)
        unresolved_operation(events)
        raw_baseline = _read_at(state_fd, "baseline.json", "Baseline", MAX_STATE_BYTES)
        baseline_sha = hashlib.sha256(raw_baseline).hexdigest()
        if baseline_sha != INITIAL_BASELINE_SHA256:
            raise ReleaseStateError("Digest baseline diverso dal valore iniziale approvato.")
        if confirmation != "INITIALIZE-CURRENT " + baseline_sha:
            raise ReleaseStateError("Conferma esplicita current-release non valida.")
        document = _read_json(raw_baseline, "baseline")
        if (document.get("schema_version") != 1
                or document.get("verification", {}).get("status") != "initialized-from-verified-content-match"
                or not document.get("release", {}).get("commit_sha")):
            raise ReleaseStateError("Baseline non inizializzata o schema non riconosciuto.")
        commit_sha = document["release"]["commit_sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", commit_sha):
            raise ReleaseStateError("Commit baseline non valido.")
        expected = _expected_from_baseline(document)
        reader = inventory_reader or baseline.acquire_fresh_inventory
        first = _validate_inventory(reader(commit_sha), expected)
        second = _validate_inventory(reader(commit_sha), expected)
        first_digest, second_digest = inventory_digest_json(first), inventory_digest_json(second)
        if first_digest != second_digest:
            raise ReleaseStateError("Filesystem pubblico cambiato tra le acquisizioni fresche.")
        observed = utc_now()
        release_id = document.get("release", {}).get("release_id")
        state = {
            "schema_version": STATE_SCHEMA,
            "initial_baseline": {"sha256": baseline_sha, "commit_sha": commit_sha,
                                 "release_id": release_id},
            "release": {"commit_sha": commit_sha, "release_id": release_id,
                        "inventory_sha256": second_digest,
                        "inventory_tool_commit": commit_sha},
            "inventory_sha256": second_digest,
            "inventory": second,
            "reference_files": [{"path": path, **expected[path]} for path in sorted(expected)],
            "backup_pre_deploy": None,
            "candidate_release": None,
            "active_operation": None,
            "last_successful_operation": {"operation_id": "baseline-bootstrap-" + commit_sha[:12],
                                          "kind": "verified-content-bootstrap",
                                          "status": "verified", "completed_at_utc": observed},
            "provenance": {"kind": "initial-baseline-content-match",
                           "baseline_provenance": document.get("provenance"),
                           "artifact_run": document.get("release", {}).get("github_actions_run")},
            "verification": {"status": "verified-current", "verified_at_utc": observed,
                             "fresh_inventory_count": 2, "public_files": len(expected),
                             "managed_symlinks": 0},
            "timestamp_utc": observed,
        }
        validate_state_document({**state, "state_sha256": digest_json(state)}, baseline_sha)
        _assert_root_path(private_root, root_fd)
        _assert_named(root_fd, "state", state_fd, "state")
        _assert_named(root_fd, "locks", locks_fd, "locks")
        state_hash = _atomic_create_state(state_fd, state)
        try:
            _assert_root_path(private_root, root_fd)
            _assert_named(root_fd, "state", state_fd, "state")
            _assert_named(root_fd, "locks", locks_fd, "locks")
        except ReleaseStateError:
            try:
                os.unlink(STATE_NAME, dir_fd=state_fd)
                os.fsync(state_fd)
            except OSError:
                pass
            raise
        return {"path": str(state_path / STATE_NAME), "state_sha256": state_hash,
                "baseline_sha256": baseline_sha, "inventory_sha256": second_digest,
                "commit_sha": commit_sha, "files": len(expected), "status": "bootstrapped"}
    except (OSError, baseline.BaselineError) as exc:
        if isinstance(exc, ReleaseStateError):
            raise
        raise ReleaseStateError(f"Bootstrap stato release fallito: {exc}") from exc
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if state_fd is not None:
            os.close(state_fd)
        if 'locks_fd' in locals():
            os.close(locks_fd)
        os.close(root_fd)


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap", help="inizializza current-release dalla baseline e da due inventari live")
    bootstrap.add_argument("--confirm-bootstrap", required=True,
                           help="conferma esatta: INITIALIZE-CURRENT <SHA-256 baseline>")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "bootstrap":
            result = bootstrap_current_release(confirmation=args.confirm_bootstrap)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
    except (ReleaseStateError, baseline.BaselineError, OSError, ValueError, KeyError) as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
