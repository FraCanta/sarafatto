#!/usr/bin/env bash
# Invoked only by gated GitHub jobs. Never uses git pull or rsync --delete.
set -euo pipefail
phase="${1:?prepare, publish or recover required}"
[[ "$phase" =~ ^(prepare|publish|recover)$ ]]
if [[ "$phase" == recover ]]; then
  : "${DEPLOY_SHA:?original SHA required}" "${DEPLOY_RUN:?original run required}" "${DEPLOY_ATTEMPT:?original attempt required}"
fi
[[ "$GITHUB_REF" == refs/heads/main ]]
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ && "$GITHUB_RUN_ID" =~ ^[0-9]+$ && "$GITHUB_RUN_ATTEMPT" =~ ^[0-9]+$ ]]
sha="${DEPLOY_SHA:-$GITHUB_SHA}"
run="${DEPLOY_RUN:-$GITHUB_RUN_ID}"
attempt="${DEPLOY_ATTEMPT:-$GITHUB_RUN_ATTEMPT}"
[[ "$sha" =~ ^[a-f0-9]{40}$ && "$run" =~ ^[0-9]+$ && "$attempt" =~ ^[0-9]+$ ]]
[[ "$IONOS_SSH_HOST" =~ ^[A-Za-z0-9.-]+$ && "$IONOS_SSH_USER" =~ ^[A-Za-z0-9._-]+$ ]]
[[ "$IONOS_SSH_PORT" =~ ^[0-9]{1,5}$ ]]
(( IONOS_SSH_PORT >= 1 && IONOS_SSH_PORT <= 65535 ))
[[ "$IONOS_THEME_TOOLCHAIN_SHA256" =~ ^[a-f0-9]{64}$ ]]
work="$(mktemp -d "$RUNNER_TEMP/theme-ssh.XXXXXXXX")"
trap 'rm -f "$work/key" "$work/known_hosts"' EXIT
printf '%s\n' "${IONOS_SSH_PRIVATE_KEY:?}" > "$work/key"
printf '%s\n' "${IONOS_SSH_KNOWN_HOSTS:?}" > "$work/known_hosts"
chmod 600 "$work/key" "$work/known_hosts"
remote() {
  ssh -T -p "$IONOS_SSH_PORT" -i "$work/key" -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$work/known_hosts" \
    -o ConnectTimeout=15 "$IONOS_SSH_USER@$IONOS_SSH_HOST" "$@"
}
tools=/home/www/sarafatto-deploy/tools/scripts/deploy
client="/home/www/sarafatto-deploy/staging/theme-client-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
transfer="run-${run}-${sha:0:12}"
pin="$IONOS_THEME_TOOLCHAIN_SHA256"

# The pin is configured independently on GitHub. Check every installed byte
# BEFORE executing remote Python, then let the installed contract check imports.
python3 scripts/deploy/artifact_transfer_tool.py toolchain > "$work/contract.json"
python3 - "$work/contract.json" "$pin" > "$work/tools.sha256" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); assert r['toolchain_sha256']==sys.argv[2], 'Local tooling differs from the installed authorized contract'
for f in r['contract']['files']: print(f['sha256']+'  /home/www/sarafatto-deploy/tools/scripts/deploy/'+f['file'])
PY
remote "sha256sum --strict -c -" < "$work/tools.sha256"

if [[ "$phase" == prepare ]]; then
  source="$RUNNER_TEMP/sarafatto-transfer"
  python3 scripts/deploy/production_publisher.py verify-artifact --release-sha "$sha" \
    --run-id "$run" --package "$source/sarafatto-release" --inventory "$source/sarafatto-inventory.tsv" \
    --archive "$source/sarafatto-release.tar.gz" --provenance "$source/sarafatto-provenance.json"
  archive_hash="$(sha256sum "$source/sarafatto-release.tar.gz" | cut -d ' ' -f1)"
  inventory_hash="$(sha256sum "$source/sarafatto-inventory.tsv" | cut -d ' ' -f1)"
  provenance_hash="$(sha256sum "$source/sarafatto-provenance.json" | cut -d ' ' -f1)"
  remote "PYTHONDONTWRITEBYTECODE=1 python3 $tools/artifact_transfer_tool.py reserve --transfer-id '$transfer' --release-sha '$sha' --run-id '$run' --toolchain-sha256 '$pin' --archive-sha256 '$archive_hash' --inventory-sha256 '$inventory_hash' --provenance-sha256 '$provenance_hash'"
  for name in sarafatto-release.tar.gz sarafatto-inventory.tsv sarafatto-provenance.json; do
    remote "PYTHONDONTWRITEBYTECODE=1 python3 $tools/artifact_transfer_tool.py receive --transfer-id '$transfer' --release-sha '$sha' --run-id '$run' --toolchain-sha256 '$pin' --name '$name'" < "$source/$name"
  done
  remote "PYTHONDONTWRITEBYTECODE=1 python3 $tools/artifact_transfer_tool.py publisher-inputs --transfer-id '$transfer' --release-sha '$sha' --run-id '$run' --toolchain-sha256 '$pin'" > "$work/received.json"
fi

# Upload only the new entrypoint, outside the existing immutable toolchain and
# outside the receiver directory. O_EXCL, no-follow and same-byte reuse only.
upload="$(cat <<'PY'
import os,sys,stat,hashlib
sys.path.insert(0,'/home/www/sarafatto-deploy/tools/scripts/deploy')
import production_adapter as a
p=sys.argv[1]; a._require_fixed_directory('/home/www/sarafatto-deploy/staging')
try: os.mkdir(p,0o700)
except FileExistsError: pass
a._require_fixed_directory(p); d=a._open_checked_dir(p)
raw=sys.stdin.buffer.read(1024*1024+1)
assert len(raw)<=1024*1024 and hashlib.sha256(raw).hexdigest()==sys.argv[2]
try:
 try:
  f=os.open('theme_deploy.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=d)
 except FileExistsError:
  f=os.open('theme_deploy.py',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=d)
  s=os.fstat(f); assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600
  assert os.read(f,len(raw)+1)==raw
 else:
  view=memoryview(raw)
  while view:
   n=os.write(f,view); assert n>0; view=view[n:]
  os.fsync(f)
 finally:
  if 'f' in locals(): os.close(f)
 os.fsync(d)
finally: os.close(d)
PY
)"
# Encode the constant Python program to avoid shell quoting its contents.
program="$(printf '%s' "$upload" | base64 -w0)"
client_hash="$(sha256sum scripts/deploy/theme_deploy.py | cut -d ' ' -f1)"
remote "PYTHONDONTWRITEBYTECODE=1 python3 -c \"import base64;exec(base64.b64decode('$program'))\" '$client' '$client_hash'" < scripts/deploy/theme_deploy.py
printf '%s  %s/theme_deploy.py\n' "$client_hash" "$client" | remote "sha256sum --strict -c -"
common="--sha '$sha' --run '$run' --attempt '$attempt' --toolchain-sha256 '$pin'"
if [[ "$phase" == prepare ]]; then
  removals="$(printf '%s' "${THEME_REMOVALS_JSON:-[]}" | base64 -w0)"
  remote "PYTHONDONTWRITEBYTECODE=1 python3 '$client/theme_deploy.py' preflight $common --removals-b64 '$removals'" > "$RUNNER_TEMP/theme-review.json"
  python3 - "$RUNNER_TEMP/theme-review.json" "$sha" "$run" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); assert r['status']=='theme-preflight-verified' and r['commit_sha']==sys.argv[2] and r['run_id']==sys.argv[3] and r['public_writes_performed'] is False
assert 'token' not in r
PY
  cat "$RUNNER_TEMP/theme-review.json" >> "$GITHUB_STEP_SUMMARY"
else
  if [[ "$phase" == publish ]]; then
    review="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["review_sha256"])' "$RUNNER_TEMP/theme-review/theme-review.json")"
    command=publish
  else
    review="${THEME_RECOVERY_REVIEW_SHA256:?}"
    command=recover
  fi
  [[ "$review" =~ ^[a-f0-9]{64}$ && "$IONOS_THEME_QUOTA_FREE_BYTES" =~ ^[1-9][0-9]*$ ]]
  remote "PYTHONDONTWRITEBYTECODE=1 python3 '$client/theme_deploy.py' '$command' $common --review-sha256 '$review' --quota-free-bytes '$IONOS_THEME_QUOTA_FREE_BYTES' --acknowledge theme-only-scheduled-maintenance-nonatomic" | tee "$RUNNER_TEMP/theme-result.json"
fi
