#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(realpath -e -- "$script_dir/../..")
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT

wp="$tmp/wp-content"
theme="$wp/themes/sarafatto"
plugin="$wp/plugins/sarafatto-core"
mu="$wp/mu-plugins"
mkdir -p "$theme/node_modules/.bin" "$theme/node_modules/pkg" "$theme/assets/dist/assets" "$theme/template-parts" "$plugin" "$mu" "$tmp/outside"
printf 'npm dependency fixture\n' > "$theme/node_modules/pkg/vite.js"
ln -s ../pkg/vite.js "$theme/node_modules/.bin/vite"
printf 'identical application file\n' > "$theme/front-page.php"
printf 'remote old version\n' > "$theme/template-parts/edit-me.php"
printf 'old hashed bundle must remain\n' > "$theme/assets/dist/assets/app-Ab12Cd34.js"
printf 'backup must remain\n' > "$theme/front-page.php.bak"
printf 'outside target\n' > "$tmp/outside/target"
ln -s "$tmp/outside/target" "$theme/managed-dangerous-link"
printf 'plugin fixture\n' > "$plugin/plugin.php"
printf 'mu plugin fixture\n' > "$mu/sarafatto-polylang-front-page-url.php"

remote="$tmp/remote.tsv"
bash "$script_dir/remote-inventory.sh" --fixture-root "$wp" > "$remote"
grep -q $'^EXCLUDED\tthemes/sarafatto/node_modules\t1\t1$' "$remote"
grep -q $'^SYMLINK\tthemes/sarafatto/managed-dangerous-link$' "$remote"
! grep -q 'node_modules/' "$remote"
grep -q 'themes/sarafatto/assets/dist/assets/app-Ab12Cd34.js' "$remote"
grep -q 'themes/sarafatto/front-page.php.bak' "$remote"

local="$tmp/local.tsv"
hash_front=$(sha256sum -- "$theme/front-page.php" | cut -d ' ' -f 1)
size_front=$(stat -c '%s' -- "$theme/front-page.php")
printf '%s\t%s\t%s\n' "$hash_front" "$size_front" 'themes/sarafatto/front-page.php' > "$local"
printf 'new local version\n' > "$tmp/local-edit.php"
hash_edit=$(sha256sum -- "$tmp/local-edit.php" | cut -d ' ' -f 1)
size_edit=$(stat -c '%s' -- "$tmp/local-edit.php")
printf '%s\t%s\t%s\n' "$hash_edit" "$size_edit" 'themes/sarafatto/template-parts/edit-me.php' >> "$local"
printf 'brand new local asset\n' > "$tmp/new-asset.webp"
hash_new=$(sha256sum -- "$tmp/new-asset.webp" | cut -d ' ' -f 1)
size_new=$(stat -c '%s' -- "$tmp/new-asset.webp")
printf '%s\t%s\t%s\n' "$hash_new" "$size_new" 'themes/sarafatto/assets/images/new-asset.webp' >> "$local"

summary="$tmp/summary.md"
set +e
python3 "$script_dir/preview-report.py" "$local" "$remote" "$summary" '0123456789012345678901234567890123456789'
status=$?
set -e
[[ $status == 3 ]]
grep -q 'Baseline remota: \*\*absent\*\*' "$summary"
grep -q '1 file e 1 symlink' "$summary"
grep -q 'Nuovi file (1)' "$summary"
grep -Fq "Modificati rispetto all'artefatto (1)" "$summary"
grep -q 'Invariati (1)' "$summary"
grep -q 'app-Ab12Cd34.js' "$summary"
grep -q 'front-page.php.bak' "$summary"
grep -q 'managed-dangerous-link' "$summary"
! grep -q 'node_modules/.bin/vite' "$summary"

# Elimina la fixture del symlink pericoloso e conferma che il dry-run logico passa.
rm -- "$theme/managed-dangerous-link"
bash "$script_dir/remote-inventory.sh" --fixture-root "$wp" > "$remote"
python3 "$script_dir/preview-report.py" "$local" "$remote" "$summary" '0123456789012345678901234567890123456789'
grep -q 'Symlink nel perimetro gestito (bloccanti) (0)' "$summary"

# L'esclusione rsync è ancorata alla radice del tema e non include node_modules.
mkdir -p "$tmp/rsync-dest"
rsync --archive --dry-run --itemize-changes --exclude='/node_modules/' "$theme/" "$tmp/rsync-dest/" > "$tmp/rsync.txt"
! grep -q 'node_modules' "$tmp/rsync.txt"
! grep -q -- '--delete' "$repo_root/scripts/deploy/compare-remote.sh"

echo 'Fixture preview superate: node_modules escluso, symlink gestito bloccante, contenuti extra conservati, SHA classificati.'
