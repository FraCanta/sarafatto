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
if python3 scripts/deploy/preview-report.py "$LOCAL_INVENTORY" "$tmp/remote.tsv" "$GITHUB_STEP_SUMMARY" "$RELEASE_SHA"; then
  :
else
  status=$?
  if (( status == 3 )); then die 'Symlink presenti nel perimetro gestito; dry-run rsync bloccato.'; fi
  die "Confronto inventari fallito (codice $status)."
fi

rsync_dry_run() {
  local source=$1 target=$2 exclude_node_modules=${3:-0}
  local options=(--archive --checksum --dry-run --itemize-changes --safe-links --out-format='%i %n%L')
  if (( exclude_node_modules == 1 )); then options+=(--exclude='/node_modules/'); fi
  rsync "${options[@]}" \
    -e "ssh -i $SSH_KEY_FILE -p $IONOS_SSH_PORT -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE" \
    "$source" "$destination:$target"
}

{
  printf '\n### rsync --dry-run (nessuna scrittura)\n\n```text\n'
  rsync_dry_run "$PACKAGE_DIR/themes/sarafatto/" "$remote_root/themes/sarafatto/" 1
  rsync_dry_run "$PACKAGE_DIR/plugins/sarafatto-core/" "$remote_root/plugins/sarafatto-core/"
  rsync_dry_run "$PACKAGE_DIR/mu-plugins/sarafatto-polylang-front-page-url.php" "$remote_root/mu-plugins/sarafatto-polylang-front-page-url.php"
  printf '```\n'
} >> "$GITHUB_STEP_SUMMARY"

echo 'Anteprima completata. Nessun file remoto è stato scritto o eliminato.'
