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
MU_MIGRATION_TARGET = "mu-plugins/sarafatto-polylang-front-page-url.php"
MU_MIGRATION_SOURCE_COMMIT = "50bbe01af38814f41d5a67bb37fef45b181f5fd1"
MU_MIGRATION_OLD_SHA256 = "2ffd84b3f170ec2e0eae1cab5935391bb8e9d5311e3c55025719ab60d1417252"
MU_MIGRATION_NEW_SHA256 = "1b4d430566abf2b01e3e22512212e2f03f623450e207366e63f02d97e85d4c7f"
MU_MIGRATION_BACKUP_ID = "20261024T181841Z-bdcc8d63457a"
MU_MIGRATION_BACKUP_MANIFEST_SHA256 = "c502c1fe239515ff3324a4c55e77443c9a6ab7b8e6c77d4e3472a3d84ab369ae"
OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
OPERATION_STATES = (
    "prepared", "backup_verified", "publishing", "files_verified",
    "health_verified", "committed", "recovery_required",
    "recovery_completed",
    "component_migrated", "component_rolled_back", "release_committed",
    "release_rolled_back",
)
APPLICATION_STATE_SCHEMA = 2
RELEASE_CHAIN_SCHEMA = 1
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")


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
    if (not isinstance(document, dict)
            or document.get("schema_version") not in (STATE_SCHEMA, APPLICATION_STATE_SCHEMA)):
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
    if document["schema_version"] == STATE_SCHEMA:
        # Lo schema storico resta immutato: bootstrap iniziale più delta MU-plugin.
        if (provenance.get("kind") != "initial-baseline-content-match"
                or provenance.get("baseline_provenance") != "bootstrap-content-match"
                or release.get("commit_sha") != baseline_info.get("commit_sha")
                or release.get("release_id") != baseline_info.get("release_id")
                or release.get("inventory_tool_commit") != baseline_info.get("commit_sha")
                or verification.get("fresh_inventory_count") != 2
                or not isinstance(verification.get("verified_at_utc"), str)):
            raise ReleaseStateError("Provenienza current-release non prodotta dal bootstrap verificato.")
    else:
        if (provenance.get("kind") != "application-release-chain"
                or provenance.get("baseline_provenance") != "bootstrap-content-match"
                or verification.get("fresh_inventory_count") != 2
                or not isinstance(verification.get("verified_at_utc"), str)):
            raise ReleaseStateError("Provenienza current-release applicativa non valida.")
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
            or document["schema_version"] == STATE_SCHEMA and document.get("pre_deploy_backup") is not None
            or not isinstance(document.get("last_successful_operation"), dict)):
        raise ReleaseStateError("Campi operativi current-release non coerenti.")
    last = document["last_successful_operation"]
    migration = document.get("component_migration")
    if document["schema_version"] == APPLICATION_STATE_SCHEMA:
        if migration is not None:
            raise ReleaseStateError("Lo schema release applicativo non può riattivare il delta MU-plugin legacy.")
        _validate_application_release_state(document)
    elif migration is None:
        if (not OPERATION_ID_RE.fullmatch(str(last.get("operation_id", "")))
                or last.get("status") != "verified"
                or last.get("kind") != "verified-content-bootstrap"
                or last.get("operation_id") != "baseline-bootstrap-" + release["commit_sha"][:12]
                or not isinstance(last.get("completed_at_utc"), str)):
            raise ReleaseStateError("Ultima operazione conclusa current-release non valida.")
    else:
        if not isinstance(migration, dict):
            raise ReleaseStateError("Record migrazione MU-plugin non valido.")
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
    if migration is not None:
        _validate_mu_migration_state(document, migration, last)
    return document


def _validate_mu_migration_state(document, migration, last):
    """Accetta solo il delta MU-plugin fissato; non promuove il commit applicativo."""
    required = {
        "schema_version", "kind", "status", "operation_id", "target",
        "source_commit_sha", "old_sha256", "new_sha256", "backup_id",
        "backup_manifest_sha256", "baseline_sha256", "previous_state_sha256",
        "previous_inventory_sha256", "verified_at_utc",
    }
    status = migration.get("status") if isinstance(migration, dict) else None
    expected_current = MU_MIGRATION_NEW_SHA256 if status == "installed" else MU_MIGRATION_OLD_SHA256
    if (not isinstance(migration, dict) or set(migration) != required
            or migration.get("schema_version") != 1
            or migration.get("kind") != "single-mu-plugin-migration"
            or status not in ("installed", "rolled_back")
            or not OPERATION_ID_RE.fullmatch(str(migration.get("operation_id", "")))
            or migration.get("target") != MU_MIGRATION_TARGET
            or migration.get("source_commit_sha") != MU_MIGRATION_SOURCE_COMMIT
            or migration.get("old_sha256") != MU_MIGRATION_OLD_SHA256
            or migration.get("new_sha256") != MU_MIGRATION_NEW_SHA256
            or migration.get("backup_id") != MU_MIGRATION_BACKUP_ID
            or migration.get("backup_manifest_sha256") != MU_MIGRATION_BACKUP_MANIFEST_SHA256
            or migration.get("baseline_sha256") != document["initial_baseline"].get("sha256")
            or not re.fullmatch(r"[a-f0-9]{64}", str(migration.get("previous_state_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(migration.get("previous_inventory_sha256", "")))
            or not isinstance(migration.get("verified_at_utc"), str)
            or last.get("operation_id") != migration.get("operation_id")
            or last.get("kind") != "mu-plugin-migration"
            or last.get("status") != "verified"
            or last.get("completed_at_utc") != migration.get("verified_at_utc")):
        raise ReleaseStateError("Record migrazione MU-plugin non autorizzato o incoerente.")
    rows = {row["path"]: row for row in document["reference_files"]}
    target = rows.get(MU_MIGRATION_TARGET)
    if not target or target.get("sha256") != expected_current:
        raise ReleaseStateError("Hash MU-plugin current-release non corrisponde alla migrazione registrata.")
    inventory_rows = {row["path"]: row for row in document["inventory"].get("files", [])}
    if inventory_rows != {path: {key: row[key] for key in ("path", "sha256", "size", "mode")}
                          for path, row in rows.items()}:
        raise ReleaseStateError("Inventario e reference_files divergono nello stato migrato.")


def _validate_release_rows(rows, label):
    if not isinstance(rows, list) or not rows:
        raise ReleaseStateError(f"Snapshot {label} assente o vuoto.")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size", "mode", "classification"}:
            raise ReleaseStateError(f"Record snapshot {label} malformato.")
        path, classification = row["path"], row["classification"]
        if (not baseline.safe_path(path) or baseline.excluded(path) or path in result
                or not re.fullmatch(r"[a-f0-9]{64}", str(row["sha256"]))
                or not isinstance(row["size"], int) or isinstance(row["size"], bool)
                or row["size"] < 0 or not re.fullmatch(r"[0-7]{3,5}", str(row["mode"]))
                or classification not in ("artifact", "retained-vite-bundle", "retained-backup", "retained-extra")):
            raise ReleaseStateError(f"Record snapshot {label} non valido: {path!r}.")
        result[path] = dict(row)
    return result


def _release_row_digest(row):
    unsigned = dict(row)
    unsigned.pop("entry_sha256", None)
    return digest_json(unsigned)


def _release_inventory(rows, exclusion):
    return {
        "files": [{"path": path, **{key: rows[path][key] for key in ("sha256", "size", "mode")}}
                  for path in sorted(rows)],
        "symlinks": [],
        "exclusion": dict(exclusion),
    }


def _validate_application_release_state(document):
    chain = document.get("release_chain")
    if (not isinstance(chain, dict) or set(chain) != {"schema_version", "root", "entries"}
            or chain.get("schema_version") != RELEASE_CHAIN_SCHEMA or not isinstance(chain.get("entries"), list)):
        raise ReleaseStateError("Catena release applicative assente o non supportata.")
    root = chain["root"]
    root_fields = {"kind", "release_id", "commit_sha", "inventory_tool_commit", "inventory_sha256",
                   "source_state_sha256", "reference_files", "component_migration", "entry_sha256"}
    if (not isinstance(root, dict) or set(root) != root_fields or root.get("kind") != "bootstrap-root"
            or not RELEASE_ID_RE.fullmatch(str(root.get("release_id", "")))
            or root.get("release_id") != document["initial_baseline"].get("release_id")
            or root.get("commit_sha") != document["initial_baseline"].get("commit_sha")
            or not re.fullmatch(r"[a-f0-9]{40}", str(root.get("inventory_tool_commit", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(root.get("source_state_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(root.get("inventory_sha256", "")))):
        raise ReleaseStateError("Radice della catena release non legata al bootstrap storico.")
    root_rows = _validate_release_rows(root.get("reference_files"), "root")
    migration = root.get("component_migration")
    if migration is not None:
        migration_fields = {
            "schema_version", "kind", "status", "operation_id", "target", "source_commit_sha",
            "old_sha256", "new_sha256", "backup_id", "backup_manifest_sha256", "baseline_sha256",
            "previous_state_sha256", "previous_inventory_sha256", "verified_at_utc",
        }
        if (not isinstance(migration, dict) or set(migration) != migration_fields
                or migration.get("schema_version") != 1
                or migration.get("kind") != "single-mu-plugin-migration"
                or migration.get("status") not in ("installed", "rolled_back")
                or migration.get("target") != MU_MIGRATION_TARGET
                or migration.get("source_commit_sha") != MU_MIGRATION_SOURCE_COMMIT
                or migration.get("old_sha256") != MU_MIGRATION_OLD_SHA256
                or migration.get("new_sha256") != MU_MIGRATION_NEW_SHA256
                or migration.get("backup_id") != MU_MIGRATION_BACKUP_ID
                or migration.get("backup_manifest_sha256") != MU_MIGRATION_BACKUP_MANIFEST_SHA256
                or migration.get("baseline_sha256") != document["initial_baseline"].get("sha256")
                or not re.fullmatch(r"[a-f0-9]{64}", str(migration.get("previous_state_sha256", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(migration.get("previous_inventory_sha256", "")))
                or not isinstance(migration.get("verified_at_utc"), str)):
            raise ReleaseStateError("Migrazione MU-plugin storica nella radice release non valida.")
    root_inventory = _release_inventory(root_rows, document["inventory"].get("exclusion", {}))
    if release_state_inventory_digest(root_inventory) != root.get("inventory_sha256"):
        raise ReleaseStateError("Inventario della radice release non valido.")
    root_unsigned = dict(root)
    root_unsigned.pop("entry_sha256", None)
    previous_hash = digest_json(root_unsigned)
    if root.get("entry_sha256") != previous_hash:
        raise ReleaseStateError("Digest della radice release non valido.")
    records = [{"release_id": root["release_id"], "commit_sha": root["commit_sha"],
                "inventory_tool_commit": root["inventory_tool_commit"],
                "inventory_sha256": root["inventory_sha256"], "reference_files": root_rows,
                "entry_sha256": previous_hash, "state_sha256": previous_hash}]
    seen_release_ids = {root["release_id"]}
    seen_operation_ids = set()
    parent = records[0]
    entry_fields = {"schema_version", "generation", "operation_id", "operation_kind", "release_id",
                    "commit_sha", "inventory_tool_commit", "inventory_sha256", "artifact_sha256",
                    "plan", "plan_sha256", "health_evidence_sha256", "backup", "parent_release_id",
                    "parent_inventory_sha256", "parent_state_sha256", "parent_document_sha256",
                    "rollback_target_release_id", "reference_files",
                    "previous_entry_sha256", "verified_at_utc", "entry_sha256"}
    for index, entry in enumerate(chain["entries"], 1):
        if (not isinstance(entry, dict) or set(entry) != entry_fields
                or entry.get("schema_version") != 1 or entry.get("generation") != index
                or not OPERATION_ID_RE.fullmatch(str(entry.get("operation_id", "")))
                or entry.get("operation_kind") not in ("publish", "rollback")
                or not RELEASE_ID_RE.fullmatch(str(entry.get("release_id", "")))
                or entry["release_id"] in seen_release_ids
                or entry.get("operation_id") in seen_operation_ids
                or not re.fullmatch(r"[a-f0-9]{40}", str(entry.get("commit_sha", "")))
                or not re.fullmatch(r"[a-f0-9]{40}", str(entry.get("inventory_tool_commit", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("inventory_sha256", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("plan_sha256", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("health_evidence_sha256", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("parent_document_sha256", "")))
                or entry.get("previous_entry_sha256") != previous_hash
                or entry.get("parent_release_id") != parent["release_id"]
                or entry.get("parent_inventory_sha256") != parent["inventory_sha256"]
                or entry.get("parent_state_sha256") != parent["state_sha256"]
                or not isinstance(entry.get("verified_at_utc"), str)):
            raise ReleaseStateError("Voce o legame della catena release non valido.")
        backup = entry.get("backup")
        if (not isinstance(backup, dict) or set(backup) != {"backup_id", "manifest_sha256", "release_id",
                                                            "inventory_sha256", "baseline_sha256"}
                or not BACKUP_ID_RE.fullmatch(str(backup.get("backup_id", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(backup.get("manifest_sha256", "")))
                or backup.get("release_id") != parent["release_id"]
                or backup.get("inventory_sha256") != parent["inventory_sha256"]
                or backup.get("baseline_sha256") != document["initial_baseline"].get("sha256")):
            raise ReleaseStateError("Backup della transazione non riferito alla release parent verificata.")
        rows = _validate_release_rows(entry.get("reference_files"), f"generation-{index}")
        inventory = _release_inventory(rows, document["inventory"].get("exclusion", {}))
        if release_state_inventory_digest(inventory) != entry["inventory_sha256"]:
            raise ReleaseStateError("Digest inventario della release nella catena non valido.")
        plan = entry.get("plan")
        if (not isinstance(plan, dict)
                or set(plan) != {"schema_version", "operation_id", "operation_kind", "parent_release_id",
                                 "parent_inventory_sha256", "candidate_inventory_sha256", "changes",
                                 "approved_removals", "removal_approval", "rollback_target_release_id"}
                or digest_json(plan) != entry["plan_sha256"]
                or plan.get("schema_version") != 1 or plan.get("operation_id") != entry["operation_id"]
                or plan.get("operation_kind") != entry["operation_kind"]
                or plan.get("parent_release_id") != parent["release_id"]
                or plan.get("parent_inventory_sha256") != parent["inventory_sha256"]
                or plan.get("candidate_inventory_sha256") != entry["inventory_sha256"]
                or plan.get("rollback_target_release_id") != entry["rollback_target_release_id"]):
            raise ReleaseStateError("Piano della release non legato alla transazione o agli inventari.")
        parent_rows = parent["reference_files"]
        changes = []
        for path in sorted(set(parent_rows) | set(rows)):
            old, new = parent_rows.get(path), rows.get(path)
            if old is None:
                changes.append({"path": path, "action": "add", "old_sha256": None,
                                "new_sha256": new["sha256"]})
            elif new is None:
                changes.append({"path": path, "action": "remove", "old_sha256": old["sha256"],
                                "new_sha256": None})
            elif any(old[key] != new[key] for key in ("sha256", "size", "mode")):
                changes.append({"path": path, "action": "replace", "old_sha256": old["sha256"],
                                "new_sha256": new["sha256"]})
        if plan.get("changes") != changes:
            raise ReleaseStateError("Modifiche del piano non corrispondono agli snapshot parent/candidato.")
        approved = plan.get("approved_removals")
        expected_approved = [{"path": row["path"], "sha256": row["old_sha256"]}
                             for row in changes if row["action"] == "remove"]
        if (not isinstance(approved, list) or approved != expected_approved
                or any(parent_rows[row["path"]]["classification"] != "artifact" for row in approved)):
            raise ReleaseStateError("Rimozioni release non approvate o riferite a file extra.")
        approval = plan.get("removal_approval")
        if approved:
            if (not isinstance(approval, dict)
                    or set(approval) != {"approval_id", "reviewer", "approved_at_utc", "parent_release_id",
                                         "parent_inventory_sha256", "removals_sha256"}
                    or not OPERATION_ID_RE.fullmatch(str(approval.get("approval_id", "")))
                    or not isinstance(approval.get("reviewer"), str) or not approval["reviewer"].strip()
                    or not isinstance(approval.get("approved_at_utc"), str)
                    or approval.get("parent_release_id") != parent["release_id"]
                    or approval.get("parent_inventory_sha256") != parent["inventory_sha256"]
                    or approval.get("removals_sha256") != digest_json(approved)):
                raise ReleaseStateError("Approvazione rimozioni assente o non legata ai file esatti.")
        elif approval is not None:
            raise ReleaseStateError("Approvazione rimozioni inattesa per un piano senza rimozioni.")
        # Gli extra accettati dalla baseline restano identici e non sono candidati a rimozione.
        for path, old in parent_rows.items():
            if old["classification"] != "artifact" and rows.get(path) != old:
                raise ReleaseStateError(f"Extra approvato modificato o rimosso: {path}.")
        rollback_target = entry.get("rollback_target_release_id")
        artifact_digest = entry.get("artifact_sha256")
        if entry["operation_kind"] == "publish":
            if (rollback_target is not None
                    or not re.fullmatch(r"[a-f0-9]{64}", str(artifact_digest or ""))):
                raise ReleaseStateError("Entry pubblicazione senza artifact verificato.")
        else:
            target = next((row for row in records if row["release_id"] == rollback_target), None)
            if (target is None or target["release_id"] == parent["release_id"]
                    or rows != target["reference_files"] or entry["commit_sha"] != target["commit_sha"]
                    or entry["inventory_tool_commit"] != target["inventory_tool_commit"]
                    or artifact_digest is not None):
                raise ReleaseStateError("Rollback non corrispondente a una release storica verificata.")
        unsigned = dict(entry)
        unsigned.pop("entry_sha256", None)
        if digest_json(unsigned) != entry.get("entry_sha256"):
            raise ReleaseStateError("Digest della voce release non valido.")
        previous_hash = entry["entry_sha256"]
        seen_release_ids.add(entry["release_id"])
        seen_operation_ids.add(entry["operation_id"])
        records.append({"release_id": entry["release_id"], "commit_sha": entry["commit_sha"],
                        "inventory_tool_commit": entry["inventory_tool_commit"],
                        "inventory_sha256": entry["inventory_sha256"], "reference_files": rows,
                        "entry_sha256": previous_hash, "state_sha256": previous_hash})
        parent = records[-1]
    latest = records[-1]
    if (document["release"].get("release_id") != latest["release_id"]
            or document["release"].get("commit_sha") != latest["commit_sha"]
            or document["release"].get("inventory_sha256") != latest["inventory_sha256"]
            or document.get("inventory_sha256") != latest["inventory_sha256"]
            or document.get("reference_files") != [latest["reference_files"][path]
                                                   for path in sorted(latest["reference_files"])]
            or document.get("pre_deploy_backup") != (chain["entries"][-1]["backup"] if chain["entries"] else None)
            or document["last_successful_operation"].get("operation_id") != (
                chain["entries"][-1]["operation_id"] if chain["entries"] else "baseline-bootstrap-"
                + document["initial_baseline"]["commit_sha"][:12])
            or document["last_successful_operation"].get("status") != "verified"
            or document["last_successful_operation"].get("kind") != "application-release"
            or document["last_successful_operation"].get("completed_at_utc") != (
                chain["entries"][-1]["verified_at_utc"] if chain["entries"] else None)):
        raise ReleaseStateError("Campi current-release non corrispondono alla release attiva della catena.")
    current_rows = {row["path"]: {key: row[key] for key in ("path", "sha256", "size", "mode")}
                    for row in document["inventory"].get("files", [])}
    expected_rows = {path: {key: latest["reference_files"][path][key]
                            for key in ("path", "sha256", "size", "mode")}
                     for path in latest["reference_files"]}
    if current_rows != expected_rows:
        raise ReleaseStateError("Inventario corrente non coincide con la release attiva.")


def release_state_inventory_digest(inventory):
    return inventory_digest_json(inventory)


def make_application_release_plan(current_state, candidate_reference_files, operation_id,
                                  *, operation_kind="publish", approved_removals=(),
                                  rollback_target_release_id=None, removal_approval=None):
    """Crea un piano canonico; ogni rimozione deve coincidere con una lista esplicita."""
    validate_state_document(current_state)
    if not OPERATION_ID_RE.fullmatch(str(operation_id)) or operation_kind not in ("publish", "rollback"):
        raise ReleaseStateError("ID o tipo transazione release non valido.")
    parent = _validate_release_rows(current_state["reference_files"], "parent")
    candidate_list = candidate_reference_files
    candidate = _validate_release_rows(candidate_list, "candidate")
    changes = []
    for path in sorted(set(parent) | set(candidate)):
        old, new = parent.get(path), candidate.get(path)
        if old is None:
            changes.append({"path": path, "action": "add", "old_sha256": None,
                            "new_sha256": new["sha256"]})
        elif new is None:
            changes.append({"path": path, "action": "remove", "old_sha256": old["sha256"],
                            "new_sha256": None})
        elif any(old[key] != new[key] for key in ("sha256", "size", "mode")):
            changes.append({"path": path, "action": "replace", "old_sha256": old["sha256"],
                            "new_sha256": new["sha256"]})
    approved = sorted([{"path": row["path"], "sha256": row["sha256"]}
                       for row in approved_removals], key=lambda row: row["path"])
    removals = [{"path": row["path"], "sha256": row["old_sha256"]}
                for row in changes if row["action"] == "remove"]
    if approved != removals:
        raise ReleaseStateError("Approvazioni rimozione non corrispondono esattamente al piano.")
    if any(parent[row["path"]]["classification"] != "artifact" for row in approved):
        raise ReleaseStateError("Un file extra approvato non può essere rimosso dal piano.")
    for path, row in parent.items():
        if row["classification"] != "artifact" and candidate.get(path) != row:
            raise ReleaseStateError(f"Il file extra deve restare invariato: {path}.")
    if operation_kind == "rollback":
        targets = {current_state["initial_baseline"]["release_id"]: current_state["initial_baseline"]["commit_sha"]}
        chain = current_state.get("release_chain")
        if chain:
            targets.update({row["release_id"]: row["commit_sha"] for row in chain["entries"]})
        if rollback_target_release_id not in targets:
            raise ReleaseStateError("Target rollback non presente nella catena release verificata.")
    elif rollback_target_release_id is not None:
        raise ReleaseStateError("Target rollback non consentito su una pubblicazione.")
    plan = {"schema_version": 1, "operation_id": operation_id, "operation_kind": operation_kind,
            "parent_release_id": current_state["release"]["release_id"],
            "parent_inventory_sha256": current_state["inventory_sha256"],
            "candidate_inventory_sha256": inventory_digest_json(
                _release_inventory(candidate, current_state["inventory"]["exclusion"])),
            "changes": changes, "approved_removals": approved,
            "removal_approval": removal_approval,
            "rollback_target_release_id": rollback_target_release_id}
    if approved:
        if (not isinstance(removal_approval, dict)
                or set(removal_approval) != {"approval_id", "reviewer", "approved_at_utc", "parent_release_id",
                                             "parent_inventory_sha256", "removals_sha256"}
                or not OPERATION_ID_RE.fullmatch(str(removal_approval.get("approval_id", "")))
                or not isinstance(removal_approval.get("reviewer"), str)
                or not removal_approval["reviewer"].strip()
                or not isinstance(removal_approval.get("approved_at_utc"), str)
                or removal_approval.get("parent_release_id") != plan["parent_release_id"]
                or removal_approval.get("parent_inventory_sha256") != plan["parent_inventory_sha256"]
                or removal_approval.get("removals_sha256") != digest_json(approved)):
            raise ReleaseStateError("Approvazione esplicita delle rimozioni non valida.")
    elif removal_approval is not None:
        raise ReleaseStateError("Approvazione rimozioni inattesa per un piano senza rimozioni.")
    return plan, digest_json(plan)


def build_application_release_state(current_state, *, release_id, commit_sha, inventory_tool_commit,
                                    operation_id, operation_kind, artifact_sha256, backup,
                                    reference_files, plan, rollback_target_release_id=None,
                                    health_evidence_sha256=None, verified_at_utc=None):
    """Prepara in memoria lo stato v2 dopo verifiche esterne di artifact, backup e live.

    Non scrive file e non autorizza da solo una pubblicazione. Il publisher deve
    eseguire le verifiche live/health e registrare il terminale tramite il proprio
    verificatore transazionale.
    """
    validate_state_document(current_state)
    if (not RELEASE_ID_RE.fullmatch(str(release_id or ""))
            or not re.fullmatch(r"[a-f0-9]{40}", str(commit_sha or ""))
            or not re.fullmatch(r"[a-f0-9]{40}", str(inventory_tool_commit or ""))
            or not OPERATION_ID_RE.fullmatch(str(operation_id or ""))):
        raise ReleaseStateError("Riferimenti release non validi.")
    rows = _validate_release_rows(reference_files, "candidate")
    supplied_plan = plan
    plan, plan_sha = make_application_release_plan(
        current_state, reference_files, operation_id, operation_kind=operation_kind,
        approved_removals=plan.get("approved_removals", []) if isinstance(plan, dict) else (),
        rollback_target_release_id=rollback_target_release_id,
        removal_approval=plan.get("removal_approval") if isinstance(plan, dict) else None)
    if supplied_plan != plan:
        raise ReleaseStateError("Piano fornito alterato rispetto agli snapshot parent e candidato.")
    if operation_kind == "publish":
        if not re.fullmatch(r"[a-f0-9]{64}", str(artifact_sha256 or "")):
            raise ReleaseStateError("Digest artifact verificato mancante.")
    elif artifact_sha256 is not None:
        raise ReleaseStateError("Il rollback deve riferirsi al backup, non a un artifact di pubblicazione.")
    if not re.fullmatch(r"[a-f0-9]{64}", str(health_evidence_sha256 or "")):
        raise ReleaseStateError("Digest delle verifiche health post-operazione mancante.")
    backup_fields = {"backup_id", "manifest_sha256", "release_id", "inventory_sha256", "baseline_sha256"}
    if (not isinstance(backup, dict) or set(backup) != backup_fields
            or backup.get("release_id") != current_state["release"]["release_id"]
            or backup.get("inventory_sha256") != current_state["inventory_sha256"]
            or backup.get("baseline_sha256") != current_state["initial_baseline"]["sha256"]
            or not BACKUP_ID_RE.fullmatch(str(backup.get("backup_id", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(backup.get("manifest_sha256", "")))):
        raise ReleaseStateError("Backup non riferito esattamente alla release parent corrente.")
    chain = current_state.get("release_chain")
    if chain is None:
        root = {"kind": "bootstrap-root", "release_id": current_state["release"]["release_id"],
                "commit_sha": current_state["release"]["commit_sha"],
                "inventory_tool_commit": current_state["release"]["inventory_tool_commit"],
                "inventory_sha256": current_state["inventory_sha256"],
                "source_state_sha256": current_state["state_sha256"],
                "reference_files": current_state["reference_files"],
                "component_migration": current_state.get("component_migration")}
        root["entry_sha256"] = digest_json(root)
        entries = []
    else:
        root, entries = chain["root"], list(chain["entries"])
    parent_state_sha256 = entries[-1]["entry_sha256"] if entries else root["entry_sha256"]
    record = {"schema_version": 1, "generation": len(entries) + 1,
              "operation_id": operation_id, "operation_kind": operation_kind,
              "release_id": release_id, "commit_sha": commit_sha,
              "inventory_tool_commit": inventory_tool_commit,
              "inventory_sha256": plan["candidate_inventory_sha256"],
              "artifact_sha256": artifact_sha256, "plan": plan, "plan_sha256": plan_sha,
              "health_evidence_sha256": health_evidence_sha256,
              "backup": dict(backup), "parent_release_id": current_state["release"]["release_id"],
              "parent_inventory_sha256": current_state["inventory_sha256"],
              "parent_state_sha256": parent_state_sha256,
              "parent_document_sha256": current_state["state_sha256"],
              "rollback_target_release_id": rollback_target_release_id,
              "reference_files": [rows[path] for path in sorted(rows)],
              "previous_entry_sha256": (entries[-1]["entry_sha256"] if entries else root["entry_sha256"]),
              "verified_at_utc": verified_at_utc or utc_now()}
    record["entry_sha256"] = _release_row_digest(record)
    entries.append(record)
    exclusion = current_state["inventory"]["exclusion"]
    inventory = _release_inventory(rows, exclusion)
    state = dict(current_state)
    state.update({
        "schema_version": APPLICATION_STATE_SCHEMA,
        "release": {"commit_sha": commit_sha, "release_id": release_id,
                    "inventory_sha256": record["inventory_sha256"],
                    "inventory_tool_commit": inventory_tool_commit},
        "inventory_sha256": record["inventory_sha256"], "inventory": inventory,
        "reference_files": record["reference_files"],
        "pre_deploy_backup": dict(backup), "candidate_release": None,
        "active_operation": None,
        "last_successful_operation": {"operation_id": operation_id,
                                       "kind": "application-release", "status": "verified",
                                       "completed_at_utc": record["verified_at_utc"]},
        "provenance": {"kind": "application-release-chain",
                       "baseline_provenance": "bootstrap-content-match"},
        "verification": {"status": "verified-current", "verified_at_utc": record["verified_at_utc"],
                         "fresh_inventory_count": 2, "public_files": len(rows),
                         "managed_symlinks": 0},
        "release_chain": {"schema_version": RELEASE_CHAIN_SCHEMA, "root": root, "entries": entries},
        "timestamp_utc": record["verified_at_utc"],
    })
    state.pop("component_migration", None)
    state.pop("state_sha256", None)
    state["state_sha256"] = digest_json(state)
    validate_state_document(state, current_state["initial_baseline"]["sha256"])
    return state


def resolve_release_snapshot(document, release_id, inventory_sha256):
    """Risoluzione immutabile di snapshot per backup e rollback storici."""
    validate_state_document(document)
    if document["schema_version"] == STATE_SCHEMA:
        if (document["release"]["release_id"] != release_id
                or document["inventory_sha256"] != inventory_sha256):
            raise ReleaseStateError("Backup legacy non risolvibile nello stato release disponibile.")
        return document["reference_files"]
    candidates = [document["release_chain"]["root"], *document["release_chain"]["entries"]]
    for item in candidates:
        if item.get("release_id") == release_id and item.get("inventory_sha256") == inventory_sha256:
            return item["reference_files"]
    raise ReleaseStateError("Snapshot backup assente dalla catena release verificata.")


def validate_fresh_release_inventories(document, inventory_texts):
    """Confronta due inventari appena acquisiti con lo snapshot della release attiva."""
    validate_state_document(document)
    if not isinstance(inventory_texts, (list, tuple)) or len(inventory_texts) != 2:
        raise ReleaseStateError("Sono richiesti esattamente due inventari pubblici freschi.")
    expected = {row["path"]: row for row in document["reference_files"]}
    first = _validate_inventory(inventory_texts[0], expected)
    second = _validate_inventory(inventory_texts[1], expected)
    first_digest = inventory_digest_json(first)
    second_digest = inventory_digest_json(second)
    if first_digest != second_digest or second_digest != document["inventory_sha256"]:
        raise ReleaseStateError("Filesystem live variato o diverso dalla release attiva.")
    return second


def persist_verified_application_release_state(candidate, expected_previous_state_sha256, *,
                                               private_root=PRIVATE_ROOT, expected_root=PRIVATE_ROOT,
                                               baseline_sha256=None, inventory_reader=None,
                                               lock_fd=None):
    """Promuove atomicamente current-release nell'area privata dopo terminale e doppio inventario.

    Non scrive il filesystem pubblico. Richiede che il writer abbia già completato
    e journalizzato una transazione, inclusa la verifica health; in assenza del
    terminale coerente o con live diverso si arresta senza sostituire lo stato.
    """
    if pathlib.Path(private_root) != pathlib.Path(expected_root):
        raise ReleaseStateError("Root privata diversa dal percorso atteso.")
    if (fcntl is None or os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd or os.rename not in os.supports_dir_fd):
        raise ReleaseStateError("Promozione stato richiede POSIX, flock e rename ancorati a descriptor.")
    validate_state_document(candidate, baseline_sha256)
    if candidate["schema_version"] != APPLICATION_STATE_SCHEMA:
        raise ReleaseStateError("È promuovibile soltanto uno stato release applicativo schema 2.")
    root_path, locks_path = baseline.validate_private_state(private_root, expected_root)
    root_fd = os.open(private_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    state_fd = locks_fd = lock_fd = temp_fd = old_fd = None
    owned_lock = lock_fd is None
    temp_name = ".current-release.update." + os.urandom(12).hex()
    try:
        state_fd = _open_dir(root_fd, "state")
        locks_fd = _open_dir(root_fd, "locks")
        _assert_root_path(private_root, root_fd)
        _assert_named(root_fd, "state", state_fd, "state")
        _assert_named(root_fd, "locks", locks_fd, "locks")
        if owned_lock:
            lock_fd = baseline.acquire_baseline_lock(locks_path, locks_fd)
        current = load_current_state(state_fd, candidate["initial_baseline"]["sha256"])
        if current["state_sha256"] == candidate["state_sha256"]:
            events = read_journal_at(state_fd)
            validate_application_release_journal(current, events)
            reader = inventory_reader or baseline.acquire_fresh_inventory
            validate_fresh_release_inventories(current, (reader(current["release"]["inventory_tool_commit"]),
                                                          reader(current["release"]["inventory_tool_commit"])))
            return {"status": "already-promoted", "state_sha256": current["state_sha256"],
                    "public_writes_performed": False}
        if not re.fullmatch(r"[a-f0-9]{64}", str(expected_previous_state_sha256 or "")):
            raise ReleaseStateError("Digest dello stato precedente mancante.")
        if current["state_sha256"] != expected_previous_state_sha256:
            raise ReleaseStateError("current-release è cambiato: promozione concorrente rifiutata.")
        entries = candidate["release_chain"]["entries"]
        current_entries = current.get("release_chain", {}).get("entries", [])
        if (len(entries) != len(current_entries) + 1
                or entries[:-1] != current_entries
                or entries[-1]["parent_document_sha256"] != current["state_sha256"]
                or entries[-1]["parent_release_id"] != current["release"]["release_id"]
                or entries[-1]["parent_inventory_sha256"] != current["inventory_sha256"]):
            raise ReleaseStateError("Candidate non è la singola transizione successiva allo stato corrente.")
        raw_baseline = _read_at(state_fd, "baseline.json", "Baseline", MAX_STATE_BYTES)
        expected_baseline = baseline_sha256 or candidate["initial_baseline"]["sha256"]
        if (hashlib.sha256(raw_baseline).hexdigest() != expected_baseline
                or candidate["initial_baseline"]["sha256"] != expected_baseline):
            raise ReleaseStateError("Baseline storica immutabile non corrispondente.")
        events = read_journal_at(state_fd)
        validate_application_release_journal(candidate, events)
        reader = inventory_reader or baseline.acquire_fresh_inventory
        tool_commit = candidate["release"]["inventory_tool_commit"]
        fresh = (reader(tool_commit), reader(tool_commit))
        validate_fresh_release_inventories(candidate, fresh)
        raw_candidate = json_bytes(candidate)
        if len(raw_candidate) > MAX_STATE_BYTES:
            raise ReleaseStateError("current-release candidato supera il limite.")
        old_fd = os.open(STATE_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=state_fd)
        old_info = os.fstat(old_fd)
        named_info = os.stat(STATE_NAME, dir_fd=state_fd, follow_symlinks=False)
        if (not stat.S_ISREG(old_info.st_mode) or old_info.st_nlink != 1
                or (old_info.st_dev, old_info.st_ino) != (named_info.st_dev, named_info.st_ino)):
            raise ReleaseStateError("current-release sostituito o non regolare prima della promozione.")
        current_raw = _read_at(state_fd, STATE_NAME, "Stato precedente", MAX_STATE_BYTES)
        current_disk = validate_state_document(
            _read_json(current_raw, "current-release precedente"), expected_baseline)
        if current_disk != current or current_disk["state_sha256"] != expected_previous_state_sha256:
            raise ReleaseStateError("Stato precedente cambiato durante la promozione.")
        temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=state_fd)
        view = memoryview(raw_candidate)
        while view:
            written = os.write(temp_fd, view)
            if written <= 0:
                raise ReleaseStateError("Scrittura temporaneo current-release incompleta.")
            view = view[written:]
        os.fchmod(temp_fd, 0o600)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None
        readback = _read_at(state_fd, temp_name, "Temporaneo current-release", MAX_STATE_BYTES)
        if (readback != raw_candidate
                or validate_state_document(_read_json(readback, "current-release candidato"),
                                           expected_baseline) != candidate):
            raise ReleaseStateError("Readback temporaneo current-release non corrispondente.")
        named_before_replace = os.stat(STATE_NAME, dir_fd=state_fd, follow_symlinks=False)
        if (named_before_replace.st_dev, named_before_replace.st_ino) != (old_info.st_dev, old_info.st_ino):
            raise ReleaseStateError("current-release sostituito prima del rename atomico.")
        _assert_root_path(private_root, root_fd)
        _assert_named(root_fd, "state", state_fd, "state")
        os.rename(temp_name, STATE_NAME, src_dir_fd=state_fd, dst_dir_fd=state_fd)
        os.fsync(state_fd)
        promoted = load_current_state(state_fd, expected_baseline)
        if promoted["state_sha256"] != candidate["state_sha256"]:
            raise ReleaseStateError("Stato non corrispondente dopo il rename atomico.")
        return {"status": "promoted", "state_sha256": promoted["state_sha256"],
                "release_id": promoted["release"]["release_id"], "public_writes_performed": False}
    except (OSError, baseline.BaselineError) as exc:
        if isinstance(exc, ReleaseStateError):
            raise
        raise ReleaseStateError(f"Promozione current-release fallita: {exc}") from exc
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if old_fd is not None:
            os.close(old_fd)
        if state_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=state_fd)
                os.fsync(state_fd)
            except FileNotFoundError:
                pass
        if lock_fd is not None and owned_lock:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if locks_fd is not None:
            os.close(locks_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)


# Alias compatibile con il nome usato durante lo sviluppo iniziale delle primitive.
persist_verified_application_release = persist_verified_application_release_state


def read_journal_at(state_fd, *, allow_fixture_committed=False):
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
        "health_verified": ({"committed", "component_migrated", "component_rolled_back",
                             "release_committed", "release_rolled_back", "recovery_required"}
                             if allow_fixture_committed else
                             {"component_migrated", "component_rolled_back", "release_committed",
                              "release_rolled_back", "recovery_required"}),
        "committed": set(), "component_migrated": set(), "component_rolled_back": set(),
        "release_committed": set(), "release_rolled_back": set(),
        "recovery_required": {"recovery_completed"}, "recovery_completed": set(),
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
            details = event["details"]
            if (not allow_fixture_committed or details.get("fixture_only") is not True
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("plan_sha256", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("final_inventory_sha256", "")))):
                raise ReleaseStateError("Evento committed rifiutato: solo il verificatore fixture può registrarlo.")
        if status in ("component_migrated", "component_rolled_back"):
            details = event["details"]
            expected_current = MU_MIGRATION_NEW_SHA256 if status == "component_migrated" else MU_MIGRATION_OLD_SHA256
            if (details.get("operation_kind") != "mu-plugin-migration"
                    or details.get("target") != MU_MIGRATION_TARGET
                    or details.get("source_commit_sha") != MU_MIGRATION_SOURCE_COMMIT
                    or details.get("old_sha256") != MU_MIGRATION_OLD_SHA256
                    or details.get("new_sha256") != MU_MIGRATION_NEW_SHA256
                    or details.get("current_sha256") != expected_current
                    or details.get("backup_id") != MU_MIGRATION_BACKUP_ID
                    or details.get("backup_manifest_sha256") != MU_MIGRATION_BACKUP_MANIFEST_SHA256
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("baseline_sha256", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("new_state_sha256", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("final_inventory_sha256", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("final_records_sha256", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("backup_sha256", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("plan_sha256", "")))
                    or status == "component_rolled_back" and not OPERATION_ID_RE.fullmatch(str(details.get("rollback_of", "")))
                    or status == "component_migrated" and details.get("rollback_of") is not None):
                raise ReleaseStateError("Evento terminale MU-plugin non autorizzato o incompleto.")
        if status in ("release_committed", "release_rolled_back"):
            details = event["details"]
            required = {"operation_kind", "release_id", "commit_sha", "artifact_sha256", "plan_sha256",
                        "backup_id", "backup_manifest_sha256", "parent_release_id",
                        "parent_inventory_sha256", "parent_state_sha256", "parent_document_sha256",
                        "final_inventory_sha256", "health_evidence_sha256", "entry_sha256"}
            kind = "publish" if status == "release_committed" else "rollback"
            artifact = details.get("artifact_sha256")
            if (set(details) != required or details.get("operation_kind") != kind
                    or not RELEASE_ID_RE.fullmatch(str(details.get("release_id", "")))
                    or not re.fullmatch(r"[a-f0-9]{40}", str(details.get("commit_sha", "")))
                    or kind == "publish" and not re.fullmatch(r"[a-f0-9]{64}", str(artifact or ""))
                    or kind == "rollback" and artifact is not None
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("plan_sha256", "")))
                    or not BACKUP_ID_RE.fullmatch(str(details.get("backup_id", "")))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(details.get("backup_manifest_sha256", "")))
                    or not RELEASE_ID_RE.fullmatch(str(details.get("parent_release_id", "")))
                    or any(not re.fullmatch(r"[a-f0-9]{64}", str(details.get(key, "")))
                           for key in ("parent_inventory_sha256", "parent_state_sha256",
                                       "parent_document_sha256", "final_inventory_sha256",
                                       "health_evidence_sha256", "entry_sha256"))):
                raise ReleaseStateError("Evento terminale release non autorizzato o incompleto.")
        if status == "recovery_completed":
            details = event["details"]
            required = {"backup_id", "backup_manifest_sha256", "parent_state_sha256",
                        "restored_inventory_sha256", "health_evidence_sha256"}
            if (set(details) != required or not BACKUP_ID_RE.fullmatch(str(details.get("backup_id", "")))
                    or any(not re.fullmatch(r"[a-f0-9]{64}", str(details.get(key, "")))
                           for key in ("backup_manifest_sha256", "parent_state_sha256",
                                       "restored_inventory_sha256", "health_evidence_sha256"))):
                raise ReleaseStateError("Evento recovery_completed incompleto o non valido.")
        if journal_operation_id is None:
            journal_operation_id = operation_id
        elif operation_id != journal_operation_id:
            previous_status = operation_status.get(journal_operation_id)
            completed_by_rollback = (
                previous_status in ("recovery_required", "component_migrated")
                and status == "prepared"
                and event["details"].get("rollback_of") == journal_operation_id
            )
            completed = previous_status in ("committed", "component_rolled_back", "recovery_completed",
                                            "release_committed", "release_rolled_back")
            if not completed and not completed_by_rollback:
                raise ReleaseStateError("Journal con operazioni intercalate o ID duplicati non consentiti.")
            journal_operation_id = operation_id
        prior_status = operation_status.get(operation_id)
        if status not in allowed_next.get(prior_status, set()):
            raise ReleaseStateError(f"Sequenza journal non valida: {prior_status} -> {status}.")
        operation_status[operation_id] = status
        events.append(event)
        previous = event_hash
    return events


def unresolved_operation(events, *, allow_fixture_committed=False, allow_application_release=False):
    active = {}
    for event in events:
        operation_id = event["operation_id"]
        if event["status"] in ("committed", "component_migrated", "component_rolled_back",
                                "release_committed", "release_rolled_back", "recovery_completed"):
            if event["status"] == "committed":
                if (not allow_fixture_committed or event.get("details", {}).get("fixture_only") is not True):
                    raise ReleaseStateError("Evento committed rifiutato: nessun verificatore fixture autorizzato.")
            if (event["status"] in ("release_committed", "release_rolled_back")
                    and not allow_application_release):
                raise ReleaseStateError("Evento terminale release rifiutato senza validazione stato/journal.")
            active.pop(operation_id, None)
            rollback_of = event.get("details", {}).get("rollback_of")
            if rollback_of is not None:
                active.pop(rollback_of, None)
        else:
            active[operation_id] = event
    unresolved = list(active.values())
    if unresolved:
        latest = unresolved[-1]
        raise ReleaseStateError(
            f"Operazione incompleta {latest['operation_id']} ({latest['status']}); "
            "richiesta riconciliazione manuale."
        )


def append_operation_event(state_fd, locks_fd, operation_id, status, details, *, lock_fd=None):
    """Aggiunge un evento sotto site-operation.lock; non pubblica né committa release."""
    if not OPERATION_ID_RE.fullmatch(str(operation_id)) or status not in OPERATION_STATES:
        raise ReleaseStateError("ID o stato operazione non validi.")
    if status in ("committed", "component_migrated", "component_rolled_back",
                  "release_committed", "release_rolled_back"):
        raise ReleaseStateError(
            "La conferma terminale richiede il verificatore di deploy specifico della transazione."
        )
    if not isinstance(details, dict):
        raise ReleaseStateError("Dettagli evento non validi.")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ReleaseStateError("Journal richiede openat/O_NOFOLLOW POSIX.")
    owned_lock = lock_fd is None
    if owned_lock:
        lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
    try:
        events = read_journal_at(state_fd)
        active = {}
        last_status = {}
        for prior_event in events:
            prior_id, prior_status = prior_event["operation_id"], prior_event["status"]
            last_status[prior_id] = prior_status
            if prior_status in ("committed", "component_migrated", "component_rolled_back",
                                "release_committed", "release_rolled_back", "recovery_completed"):
                active.pop(prior_id, None)
            else:
                active[prior_id] = prior_event
        if any(key != operation_id for key in active):
            raise ReleaseStateError("Un'altra operazione è incompleta; journal in sola lettura.")
        prior_status = last_status.get(operation_id)
        transitions = {
            None: {"prepared"}, "prepared": {"backup_verified", "recovery_required"},
            "backup_verified": {"publishing", "recovery_required"},
            "publishing": {"files_verified", "recovery_required"},
            "files_verified": {"health_verified", "recovery_required"},
            "health_verified": {"recovery_required"},
            "recovery_required": set(),
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
        if owned_lock:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def load_current_state(state_fd, expected_baseline_sha=None):
    raw = _read_at(state_fd, STATE_NAME, "Stato release corrente", MAX_STATE_BYTES)
    return validate_state_document(_read_json(raw, "current-release"), expected_baseline_sha)


def validate_component_migration_journal(state, events):
    """Collega lo stato MU-plugin al terminale hash-chain corrispondente."""
    migration = state.get("component_migration")
    if migration is None:
        return
    terminal_status = "component_migrated" if migration["status"] == "installed" else "component_rolled_back"
    terminal = next((event for event in reversed(events)
                     if event["operation_id"] == migration["operation_id"]
                     and event["status"] == terminal_status), None)
    if terminal is None:
        raise ReleaseStateError("Stato MU-plugin senza evento terminale verificato nel journal.")
    operation = [event for event in events if event["operation_id"] == migration["operation_id"]]
    expected_states = ["prepared", "backup_verified", "publishing", "files_verified",
                       "health_verified", terminal_status]
    if [event["status"] for event in operation] != expected_states:
        raise ReleaseStateError("Sequenza journal della migrazione MU-plugin incompleta o duplicata.")
    details = terminal["details"]
    prepared = operation[0]["details"]
    backup_event = operation[1]["details"]
    files_event = operation[3]["details"]
    expected_current = MU_MIGRATION_NEW_SHA256 if migration["status"] == "installed" else MU_MIGRATION_OLD_SHA256
    expected_records_sha256 = digest_json(sorted(state["reference_files"], key=lambda row: row["path"]))
    if (prepared.get("operation_kind") != ("mu-plugin-migration" if migration["status"] == "installed"
                                             else "mu-plugin-rollback")
            or prepared.get("target") != MU_MIGRATION_TARGET
            or prepared.get("source_commit_sha") != MU_MIGRATION_SOURCE_COMMIT
            or prepared.get("old_sha256") != MU_MIGRATION_OLD_SHA256
            or prepared.get("new_sha256") != MU_MIGRATION_NEW_SHA256
            or prepared.get("backup_id") != MU_MIGRATION_BACKUP_ID
            or prepared.get("backup_manifest_sha256") != MU_MIGRATION_BACKUP_MANIFEST_SHA256
            or prepared.get("old_state_sha256") != migration.get("previous_state_sha256")
            or backup_event.get("backup_sha256") != prepared.get("backup_sha256")
            or files_event.get("installed_sha256") != expected_current
            or details.get("plan_sha256") != prepared.get("plan_sha256")
            or details.get("backup_sha256") != prepared.get("backup_sha256")
            or details.get("new_state_sha256") != state.get("state_sha256")
            or details.get("final_inventory_sha256") != state.get("inventory_sha256")
            or details.get("final_records_sha256") != expected_records_sha256
            or details.get("baseline_sha256") != migration.get("baseline_sha256")
            or details.get("current_sha256") != expected_current
            or details.get("backup_manifest_sha256") != migration.get("backup_manifest_sha256")
            or migration["status"] == "rolled_back"
            and (details.get("rollback_of") != prepared.get("rollback_of")
                 or not any(event["operation_id"] == prepared.get("rollback_of")
                            and event["status"] == "component_migrated" for event in events))):
        raise ReleaseStateError("Journal terminale e current-release MU-plugin non concordano.")


def validate_application_release_journal(state, events):
    """Collega ogni release applicativa della catena a una transazione terminale completa."""
    validate_state_document(state)
    if state["schema_version"] != APPLICATION_STATE_SCHEMA:
        raise ReleaseStateError("La validazione journal applicativa richiede current-release schema 2.")
    chain = state["release_chain"]
    migration = chain["root"].get("component_migration")
    if migration is not None:
        root = chain["root"]
        pseudo = dict(state)
        pseudo.update({
            "schema_version": STATE_SCHEMA,
            "release": {"commit_sha": root["commit_sha"], "release_id": root["release_id"]},
            "inventory_sha256": root["inventory_sha256"],
            "inventory": _release_inventory(_validate_release_rows(root["reference_files"], "root"),
                                             state["inventory"]["exclusion"]),
            "reference_files": root["reference_files"],
            "component_migration": migration,
            "state_sha256": root["source_state_sha256"],
        })
        validate_component_migration_journal(pseudo, events)
    for entry in chain["entries"]:
        operation = [event for event in events if event["operation_id"] == entry["operation_id"]]
        terminal_status = ("release_committed" if entry["operation_kind"] == "publish"
                           else "release_rolled_back")
        expected = ["prepared", "backup_verified", "publishing", "files_verified",
                    "health_verified", terminal_status]
        if [event["status"] for event in operation] != expected:
            raise ReleaseStateError("Journal della release incompleto, duplicato o fuori sequenza.")
        terminal = operation[-1]
        details = terminal["details"]
        expected_details = {
            "operation_kind": entry["operation_kind"], "release_id": entry["release_id"],
            "commit_sha": entry["commit_sha"], "artifact_sha256": entry["artifact_sha256"],
            "plan_sha256": entry["plan_sha256"], "backup_id": entry["backup"]["backup_id"],
            "backup_manifest_sha256": entry["backup"]["manifest_sha256"],
            "parent_release_id": entry["parent_release_id"],
            "parent_inventory_sha256": entry["parent_inventory_sha256"],
            "parent_state_sha256": entry["parent_state_sha256"],
            "parent_document_sha256": entry["parent_document_sha256"],
            "final_inventory_sha256": entry["inventory_sha256"],
            "health_evidence_sha256": entry["health_evidence_sha256"],
            "entry_sha256": entry["entry_sha256"],
        }
        if details != expected_details:
            raise ReleaseStateError("Evento terminale journal non corrisponde all'entry verificata.")
        prepared = operation[0]["details"]
        expected_prepared = {
            "operation_kind": entry["operation_kind"], "release_id": entry["release_id"],
            "commit_sha": entry["commit_sha"], "artifact_sha256": entry["artifact_sha256"],
            "plan_sha256": entry["plan_sha256"], "backup_id": entry["backup"]["backup_id"],
            "backup_manifest_sha256": entry["backup"]["manifest_sha256"],
            "parent_release_id": entry["parent_release_id"],
            "parent_inventory_sha256": entry["parent_inventory_sha256"],
            "parent_state_sha256": entry["parent_state_sha256"],
            "parent_document_sha256": entry["parent_document_sha256"],
            "plan": entry["plan"], "entry_sha256": entry["entry_sha256"],
        }
        # I writer reali devono poter journalizzare l'intento prima di modificare
        # il filesystem. L'inventario finale e l'entry hash sono noti soltanto
        # dopo le scritture e l'health check; il journal storico delle fixture
        # può ancora includerli nell'evento prepared.
        production_prepared = dict(expected_prepared)
        production_prepared.pop("entry_sha256")
        manifest_sha = prepared.get("transaction_manifest_sha256")
        production_prepared_with_manifest = {**production_prepared,
                                             "transaction_manifest_sha256": manifest_sha}
        manifest_prepared_valid = (
            re.fullmatch(r"[a-f0-9]{64}", str(manifest_sha or "")) is not None
            and prepared == production_prepared_with_manifest
        )
        legacy_prepared = dict(expected_prepared)
        legacy_prepared["final_inventory_sha256"] = entry["inventory_sha256"]
        backup_details = operation[1]["details"]
        expected_backup = {"backup_id": entry["backup"]["backup_id"],
                           "manifest_sha256": entry["backup"]["manifest_sha256"],
                           "release_id": entry["backup"]["release_id"],
                           "inventory_sha256": entry["backup"]["inventory_sha256"],
                           "baseline_sha256": entry["backup"]["baseline_sha256"]}
        health_details = operation[4]["details"]
        health_details_valid = health_details in (
            {"entry_sha256": entry["entry_sha256"],
             "health_evidence_sha256": entry["health_evidence_sha256"]},
            {"health_evidence_sha256": entry["health_evidence_sha256"]},
        ) or (
            set(health_details) == {"health_evidence_sha256", "candidate_state_sha256"}
            and health_details.get("health_evidence_sha256") == entry["health_evidence_sha256"]
            and re.fullmatch(r"[a-f0-9]{64}", str(health_details.get("candidate_state_sha256", "")))
            is not None
        )
        if (prepared not in (legacy_prepared, expected_prepared, production_prepared)
                and not manifest_prepared_valid
                or backup_details != expected_backup
                or operation[2]["details"] not in (
                    {"entry_sha256": entry["entry_sha256"], "plan_sha256": entry["plan_sha256"]},
                    {"plan_sha256": entry["plan_sha256"]})
                or operation[3]["details"] not in (
                    {"entry_sha256": entry["entry_sha256"],
                     "final_inventory_sha256": entry["inventory_sha256"]},
                    {"final_inventory_sha256": entry["inventory_sha256"]})
                or not health_details_valid):
            raise ReleaseStateError("Dettagli intermedi del journal non concordano con la transazione release.")
    expected_terminal_ops = {entry["operation_id"] for entry in chain["entries"]}
    journal_release_order = [event["operation_id"] for event in events
                             if event["status"] == "prepared"
                             and event["operation_id"] in expected_terminal_ops]
    if journal_release_order != [entry["operation_id"] for entry in chain["entries"]]:
        raise ReleaseStateError("Ordine delle transazioni journal diverso dalla catena release.")
    actual_release_ops = {event["operation_id"] for event in events
                          if event["status"] in ("release_committed", "release_rolled_back")}
    if actual_release_ops != expected_terminal_ops:
        raise ReleaseStateError("Journal contiene terminali release assenti dalla catena current-release.")
    unresolved_operation(events, allow_application_release=True)
    return True


def append_verified_application_terminal(candidate, expected_parent_state_sha256, *,
                                         private_root=PRIVATE_ROOT, expected_root=PRIVATE_ROOT,
                                         inventory_reader=None, lock_fd=None):
    """Append release terminal soltanto dopo aver verificato candidato, parent e live.

    È l'unico percorso produttivo che può scrivere release_committed o
    release_rolled_back. L'evento viene aggiunto prima della promozione atomica
    current-release: un crash nella finestra intermedia lascia lo stato incoerente
    e quindi bloccato, mai falsamente valido.
    """
    if pathlib.Path(private_root) != pathlib.Path(expected_root):
        raise ReleaseStateError("Root privata diversa dal percorso atteso.")
    if (fcntl is None or os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd):
        raise ReleaseStateError("Conferma release richiede POSIX, flock e openat/O_NOFOLLOW.")
    candidate = validate_state_document(candidate)
    if candidate["schema_version"] != APPLICATION_STATE_SCHEMA:
        raise ReleaseStateError("Terminale disponibile soltanto per release applicative.")
    chain = candidate["release_chain"]
    if not chain["entries"]:
        raise ReleaseStateError("Nessuna entry applicativa da confermare.")
    entry = chain["entries"][-1]
    status = "release_committed" if entry["operation_kind"] == "publish" else "release_rolled_back"
    root_fd = os.open(private_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    state_fd = locks_fd = lock_fd = None
    owned_lock = lock_fd is None
    try:
        state_fd = _open_dir(root_fd, "state")
        locks_fd = _open_dir(root_fd, "locks")
        if owned_lock:
            lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
        current = load_current_state(state_fd, candidate["initial_baseline"]["sha256"])
        if current["state_sha256"] != expected_parent_state_sha256:
            raise ReleaseStateError("current-release parent cambiato; terminale rifiutato.")
        entries = current.get("release_chain", {}).get("entries", [])
        if (len(chain["entries"]) != len(entries) + 1
                or chain["entries"][:-1] != entries
                or entry["parent_document_sha256"] != current["state_sha256"]
                or entry["parent_release_id"] != current["release"]["release_id"]
                or entry["parent_inventory_sha256"] != current["inventory_sha256"]):
            raise ReleaseStateError("Entry candidata non è la prossima transizione del parent corrente.")
        reader = inventory_reader or baseline.acquire_fresh_inventory
        tool_commit = candidate["release"]["inventory_tool_commit"]
        validate_fresh_release_inventories(candidate, (reader(tool_commit), reader(tool_commit)))
        events = read_journal_at(state_fd)
        operation = [event for event in events if event["operation_id"] == entry["operation_id"]]
        required = ["prepared", "backup_verified", "publishing", "files_verified", "health_verified"]
        if [event["status"] for event in operation] != required:
            raise ReleaseStateError("Transazione non ha completato tutti i controlli prima del terminale.")
        terminal_details = {
            "operation_kind": entry["operation_kind"], "release_id": entry["release_id"],
            "commit_sha": entry["commit_sha"], "artifact_sha256": entry["artifact_sha256"],
            "plan_sha256": entry["plan_sha256"], "backup_id": entry["backup"]["backup_id"],
            "backup_manifest_sha256": entry["backup"]["manifest_sha256"],
            "parent_release_id": entry["parent_release_id"],
            "parent_inventory_sha256": entry["parent_inventory_sha256"],
            "parent_state_sha256": entry["parent_state_sha256"],
            "parent_document_sha256": entry["parent_document_sha256"],
            "final_inventory_sha256": entry["inventory_sha256"],
            "health_evidence_sha256": entry["health_evidence_sha256"],
            "entry_sha256": entry["entry_sha256"],
        }
        event = {"operation_id": entry["operation_id"], "status": status,
                 "timestamp_utc": utc_now(), "details": terminal_details,
                 "previous_event_sha256": events[-1]["event_sha256"] if events else "0" * 64}
        event["event_sha256"] = digest_json(event)
        validate_application_release_journal(candidate, events + [event])
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8") + b"\n"
        fd = os.open(JOURNAL_NAME, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                     0o600, dir_fd=state_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size + len(payload) > MAX_JOURNAL_BYTES):
                raise ReleaseStateError("Journal non sicuro o oltre il limite.")
            if os.write(fd, payload) != len(payload):
                raise ReleaseStateError("Scrittura evento terminale incompleta.")
            os.fsync(fd)
            os.fsync(state_fd)
        finally:
            os.close(fd)
        return {"status": status, "operation_id": entry["operation_id"],
                "entry_sha256": entry["entry_sha256"]}
    except (OSError, baseline.BaselineError) as exc:
        if isinstance(exc, ReleaseStateError):
            raise
        raise ReleaseStateError(f"Conferma terminale fallita: {exc}") from exc
    finally:
        if lock_fd is not None and owned_lock:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if locks_fd is not None:
            os.close(locks_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)


def append_verified_recovery_completion(operation_id, expected_parent_state_sha256, *,
                                        backup_id, backup_manifest_sha256,
                                        restored_inventory_sha256, health_evidence_sha256,
                                        private_root=PRIVATE_ROOT, expected_root=PRIVATE_ROOT,
                                        inventory_reader=None, lock_fd=None):
    """Chiude una recovery solo dopo aver provato il ripristino del parent live.

    Il current-release deve essere ancora il parent; l'evento prepared deve
    riferirsi allo stesso backup e la doppia acquisizione live deve coincidere
    con il digest del parent prima di registrare recovery_completed.
    """
    if pathlib.Path(private_root) != pathlib.Path(expected_root):
        raise ReleaseStateError("Root privata diversa dal percorso atteso.")
    if (fcntl is None or os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd):
        raise ReleaseStateError("Recovery richiede POSIX, flock e openat/O_NOFOLLOW.")
    if (not OPERATION_ID_RE.fullmatch(str(operation_id or ""))
            or not re.fullmatch(r"[a-f0-9]{64}", str(expected_parent_state_sha256 or ""))
            or not BACKUP_ID_RE.fullmatch(str(backup_id or ""))
            or any(not re.fullmatch(r"[a-f0-9]{64}", str(value or "")) for value in
                   (backup_manifest_sha256, restored_inventory_sha256, health_evidence_sha256))):
        raise ReleaseStateError("Riferimenti recovery non validi.")
    root_fd = os.open(private_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    state_fd = locks_fd = None
    owned_lock = lock_fd is None
    try:
        state_fd = _open_dir(root_fd, "state")
        locks_fd = _open_dir(root_fd, "locks")
        if owned_lock:
            lock_fd = baseline.acquire_baseline_lock(None, locks_fd)
        parent = load_current_state(state_fd)
        if parent["state_sha256"] != expected_parent_state_sha256:
            raise ReleaseStateError("Current-release cambiato durante la recovery.")
        events = read_journal_at(state_fd)
        operation = [event for event in events if event["operation_id"] == operation_id]
        if not operation or operation[-1]["status"] != "recovery_required":
            raise ReleaseStateError("La transazione non è in stato recovery_required.")
        prepared = operation[0]["details"]
        if (prepared.get("parent_state_sha256") != expected_parent_state_sha256
                or prepared.get("backup_id") != backup_id
                or prepared.get("backup_manifest_sha256") != backup_manifest_sha256
                or restored_inventory_sha256 != parent["inventory_sha256"]):
            raise ReleaseStateError("Recovery non corrisponde al parent o al backup registrato.")
        reader = inventory_reader or baseline.acquire_fresh_inventory
        tool_commit = parent["release"]["inventory_tool_commit"]
        validate_fresh_release_inventories(parent, (reader(tool_commit), reader(tool_commit)))
        details = {"backup_id": backup_id, "backup_manifest_sha256": backup_manifest_sha256,
                   "parent_state_sha256": expected_parent_state_sha256,
                   "restored_inventory_sha256": restored_inventory_sha256,
                   "health_evidence_sha256": health_evidence_sha256}
        event = {"operation_id": operation_id, "status": "recovery_completed",
                 "timestamp_utc": utc_now(), "details": details,
                 "previous_event_sha256": events[-1]["event_sha256"] if events else "0" * 64}
        event["event_sha256"] = digest_json(event)
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8") + b"\n"
        fd = os.open(JOURNAL_NAME, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                     0o600, dir_fd=state_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size + len(payload) > MAX_JOURNAL_BYTES):
                raise ReleaseStateError("Journal recovery non sicuro o oltre il limite.")
            if os.write(fd, payload) != len(payload):
                raise ReleaseStateError("Scrittura recovery_completed incompleta.")
            os.fsync(fd)
            os.fsync(state_fd)
        finally:
            os.close(fd)
        verified_events = read_journal_at(state_fd)
        unresolved_operation(verified_events, allow_application_release=True)
        return {"status": "recovery_completed", "operation_id": operation_id,
                "event_sha256": event["event_sha256"]}
    except (OSError, baseline.BaselineError) as exc:
        if isinstance(exc, ReleaseStateError):
            raise
        raise ReleaseStateError(f"Conferma recovery fallita: {exc}") from exc
    finally:
        if lock_fd is not None and owned_lock:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if locks_fd is not None:
            os.close(locks_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)


def validate_current_state_journal(state, events):
    """Validazione unica per stato bootstrap/MU legacy o catena applicativa v2."""
    if state["schema_version"] == APPLICATION_STATE_SCHEMA:
        return validate_application_release_journal(state, events)
    unresolved_operation(events)
    return validate_component_migration_journal(state, events)


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
            "pre_deploy_backup": None,
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
