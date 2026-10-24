#!/usr/bin/env bash
set -euo pipefail

die() { echo "ERRORE: $*" >&2; exit 2; }
finish() {
  local status=$1
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    if (( status == 0 )); then
      printf '\n### Esito: dry-run completato\nNessuna scrittura remota eseguita.\n' >> "$GITHUB_STEP_SUMMARY"
    else
      printf '\n### Esito: FALLITO\nIl confronto si è interrotto (codice %s); nessun esito positivo da presumere.\n' "$status" >> "$GITHUB_STEP_SUMMARY"
    fi
  fi
  if [[ -n "${tmp:-}" && -d "$tmp" ]]; then rm -rf -- "$tmp"; fi
  return "$status"
}
trap 'finish "$?"' EXIT
[[ "${RELEASE_SHA:-}" =~ ^[a-f0-9]{40}$ ]] || die 'SHA autorizzato non valido.'
[[ "${IONOS_SSH_HOST:-}" =~ ^[A-Za-z0-9.-]+$ ]] || die 'IONOS_SSH_HOST assente/non valido.'
[[ "${IONOS_SSH_USER:-}" =~ ^[A-Za-z0-9._-]+$ ]] || die 'IONOS_SSH_USER assente/non valido.'
[[ "${IONOS_SSH_PORT:-}" =~ ^[0-9]{1,5}$ ]] || die 'IONOS_SSH_PORT assente/non valido.'
[[ -r "${SSH_KEY_FILE:-}" && -r "${SSH_KNOWN_HOSTS_FILE:-}" ]] || die 'File SSH effimeri assenti.'
[[ -d "${PACKAGE_DIR:-}" && -r "${LOCAL_INVENTORY:-}" ]] || die 'Artefatto o inventario locale assente.'

remote_root='/home/www/public/wp-content'
destination="$IONOS_SSH_USER@$IONOS_SSH_HOST"
ssh_opts=(-i "$SSH_KEY_FILE" -p "$IONOS_SSH_PORT" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE" -o ConnectTimeout=20)
tmp=$(mktemp -d)

ssh "${ssh_opts[@]}" "$destination" 'bash -s' < scripts/deploy/remote-inventory.sh > "$tmp/remote.tsv"
python3 - "$LOCAL_INVENTORY" "$tmp/remote.tsv" "$GITHUB_STEP_SUMMARY" "$RELEASE_SHA" <<'PY'
import pathlib, sys

local_path, remote_path, summary_path = map(pathlib.Path, sys.argv[1:4])
release_sha = sys.argv[4]
rows = local_path.read_text().splitlines()
desired = {}
for row in rows:
    parts = row.split("\t", 2)
    if len(parts) != 3 or parts[2] in desired:
        raise SystemExit("Inventario locale malformato o duplicato.")
    desired[parts[2]] = (parts[0], parts[1])

remote = {}
baseline = {}
symlinks = []
baseline_state = "absent"
in_baseline = False
for row in remote_path.read_text().splitlines():
    if row == "BASELINE_BEGIN":
        in_baseline = True
        continue
    if row == "BASELINE_END":
        in_baseline = False
        continue
    fields = row.split("\t", 3)
    if in_baseline:
        if len(fields) != 3:
            raise SystemExit("Inventario baseline remoto malformato.")
        baseline[fields[2]] = (fields[0], fields[1])
    elif fields[0] == "BASELINE" and len(fields) == 2:
        baseline_state = fields[1]
    elif fields[0] == "SYMLINK" and len(fields) == 2:
        symlinks.append(fields[1])
    elif fields[0] == "FILE" and len(fields) == 4:
        remote[fields[3]] = (fields[1], fields[2])

if baseline_state == "available" and not baseline:
    raise SystemExit("Baseline dichiarata presente ma vuota/non valida; confronto interrotto.")
new = sorted(desired.keys() - remote.keys())
modified = sorted(p for p in desired.keys() & remote.keys() if desired[p] != remote[p])
unchanged = sorted(p for p in desired.keys() & remote.keys() if desired[p] == remote[p])
remote_only = sorted(remote.keys() - desired.keys())
manual_drift = sorted(p for p in remote.keys() | baseline.keys() if remote.get(p) != baseline.get(p)) if baseline_state == "available" else []

def section(title, paths):
    lines = [f"### {title}", ""]
    lines.extend(f"- `{p}`" for p in paths) if paths else lines.append("- Nessuno")
    return "\n".join(lines)

text = [f"# Anteprima rilascio `{release_sha}`", "", "Confronto in sola lettura; non è stata eseguita alcuna scrittura remota.", "",
        f"Baseline remota: **{baseline_state}**", "",
        section("Nuovi file", new), "", section("Modificati rispetto all'artefatto", modified), "",
        section("Invariati", unchanged), "", section("Solo in produzione (conservati)", remote_only), "",
        section("Drift dalla baseline", manual_drift), "", section("Symlink remoti", sorted(symlinks))]
if baseline_state != "available":
    text += ["", "Senza baseline approvata non è possibile distinguere modifiche manuali in produzione da differenze di release."]
summary_path.write_text("\n".join(text) + "\n")
PY

if [[ -s "$tmp/remote.tsv" ]] && grep -q '^SYMLINK' "$tmp/remote.tsv"; then die 'Symlink presenti nelle directory allowlist: dry-run rsync bloccato.'; fi

rsync_dry_run() {
  local source=$1 target=$2
  rsync --archive --checksum --dry-run --itemize-changes --safe-links --out-format='%i %n%L' \
    -e "ssh -i $SSH_KEY_FILE -p $IONOS_SSH_PORT -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE" \
    "$source" "$destination:$target"
}

{
  printf '\n### rsync --dry-run (nessuna scrittura)\n\n```text\n'
  rsync_dry_run "$PACKAGE_DIR/themes/sarafatto/" "$remote_root/themes/sarafatto/"
  rsync_dry_run "$PACKAGE_DIR/plugins/sarafatto-core/" "$remote_root/plugins/sarafatto-core/"
  rsync_dry_run "$PACKAGE_DIR/mu-plugins/sarafatto-polylang-front-page-url.php" "$remote_root/mu-plugins/sarafatto-polylang-front-page-url.php"
  printf '```\n'
} >> "$GITHUB_STEP_SUMMARY"

echo 'Anteprima completata. Nessun file remoto è stato scritto o eliminato.'
