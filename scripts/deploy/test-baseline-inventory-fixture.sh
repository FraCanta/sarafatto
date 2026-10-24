#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT

wp="$tmp/wp-content"
theme="$wp/themes/sarafatto"
plugin="$wp/plugins/sarafatto-core"
mu="$wp/mu-plugins"
mkdir -p "$theme/node_modules/.bin" "$theme/node_modules/pkg" "$theme/assets/dist/assets" "$plugin" "$mu"
printf 'dependency fixture\n' > "$theme/node_modules/pkg/vite.js"
ln -s ../pkg/vite.js "$theme/node_modules/.bin/vite"
printf 'same application bytes\n' > "$theme/front-page.php"
printf 'old hashed asset\n' > "$theme/assets/dist/assets/app-Ab12Cd34.js"
printf 'backup bytes\n' > "$theme/front-page.php.bak"
printf 'plugin bytes\n' > "$plugin/plugin.php"
printf 'mu bytes\n' > "$mu/sarafatto-polylang-front-page-url.php"
printf 'outside bytes\n' > "$tmp/outside"
ln -s "$tmp/outside" "$theme/dangerous-link"

remote="$tmp/remote.tsv"
bash "$script_dir/baseline-inventory.sh" --fixture-root "$wp" > "$remote"
grep -q $'^EXCLUDED\tthemes/sarafatto/node_modules\t1\t1$' "$remote"
! grep -q 'node_modules/' "$remote"
grep -q $'^SYMLINK\tthemes/sarafatto/dangerous-link\t' "$remote"
grep -q $'^END$' "$remote"

artifact="$tmp/artifact.tsv"
for relative in themes/sarafatto/front-page.php plugins/sarafatto-core/plugin.php mu-plugins/sarafatto-polylang-front-page-url.php; do
  file="$wp/$relative"
  hash=$(sha256sum -- "$file" | cut -d ' ' -f 1)
  size=$(stat -c '%s' -- "$file")
  printf '%s\t%s\t%s\n' "$hash" "$size" "$relative" >> "$artifact"
done
sha='22c7fdd9970a2c8f1e9f3e3c0c0bb4cbadc44a66'
run_url='https://github.com/FraCanta/sarafatto/actions/runs/12345'
old_bundle='themes/sarafatto/assets/dist/assets/app-Ab12Cd34.js'
backup='themes/sarafatto/front-page.php.bak'

set +e
python3 "$script_dir/baseline_tool.py" compare \
  --artifact-inventory "$artifact" --remote-inventory "$remote" \
  --release-sha "$sha" --authorized-sha "$sha" --release-id "bootstrap-$sha" \
  --run-url "$run_url" --accept-extra "$old_bundle" --accept-extra "$backup" \
  > "$tmp/blocked-report.md"
status=$?
set -e
[[ $status == 4 ]]
grep -q 'Symlink gestiti (bloccanti) (1)' "$tmp/blocked-report.md"
grep -q 'node_modules/.*1 file e 1 symlink' "$tmp/blocked-report.md"

rm -- "$theme/dangerous-link"
bash "$script_dir/baseline-inventory.sh" --fixture-root "$wp" > "$remote"
python3 "$script_dir/baseline_tool.py" compare \
  --artifact-inventory "$artifact" --remote-inventory "$remote" \
  --release-sha "$sha" --authorized-sha "$sha" --release-id "bootstrap-$sha" \
  --run-url "$run_url" --accept-extra "$old_bundle" --accept-extra "$backup" \
  --candidate-out "$tmp/candidate.json" > "$tmp/report.md"
grep -q 'verified-awaiting-explicit-approval' "$tmp/report.md"
python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); assert data["publication_date"] is None; assert len(data["accepted_extras"]) == 2' "$tmp/candidate.json"

echo 'Fixture baseline inventory superata: symlink node_modules escluso, symlink gestito bloccante, extra conservati e candidato prodotto.'
