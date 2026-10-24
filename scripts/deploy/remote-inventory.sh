#!/usr/bin/env bash
set -euo pipefail

expected_root='/home/www/public/wp-content'
roots=('themes/sarafatto' 'plugins/sarafatto-core')
single_file='mu-plugins/sarafatto-polylang-front-page-url.php'
fixture_mode=0

if [[ "${1:-}" == '--fixture-root' && $# == 2 ]]; then
  fixture_mode=1
  expected_root=$2
elif [[ $# -ne 0 ]]; then
  echo 'Argomenti non validi.' >&2
  exit 19
fi

validate_record_path() {
  local path=$1
  [[ "$path" != *$'\t'* && "$path" != *$'\n'* && "$path" != *$'\r'* ]] || { echo 'Nome file remoto non rappresentabile nell inventario.' >&2; exit 24; }
}
root_real=$(realpath -e -- "$expected_root")
if (( fixture_mode == 0 )); then
  [[ "$root_real" == "$expected_root" ]] || { echo 'wp-content inatteso.' >&2; exit 20; }
elif [[ "$root_real" == '/' ]]; then
  echo 'Root fixture non valida.' >&2
  exit 20
fi
for tool in realpath find sha256sum stat; do command -v "$tool" >/dev/null || { echo "Comando remoto assente: $tool" >&2; exit 21; }; done
if (( fixture_mode == 0 )); then command -v rsync >/dev/null || { echo 'Comando remoto assente: rsync' >&2; exit 21; }; fi
[[ -d "$root_real/themes/sarafatto" && -d "$root_real/plugins/sarafatto-core" && -f "$root_real/$single_file" ]] || { echo 'Percorsi allowlist incompleti.' >&2; exit 22; }

baseline='/home/www/sarafatto-deploy/state/production-inventory.tsv'
if (( fixture_mode == 1 )); then
  printf 'BASELINE\tabsent\n'
elif [[ -r "$baseline" ]]; then
  printf 'BASELINE\tavailable\n'
  printf 'BASELINE_BEGIN\n'
  cat -- "$baseline"
  printf 'BASELINE_END\n'
else
  printf 'BASELINE\tabsent\n'
fi

excluded_node_modules="$root_real/themes/sarafatto/node_modules"
excluded_files=0
excluded_symlinks=0
if [[ -L "$excluded_node_modules" ]]; then
  excluded_symlinks=1
elif [[ -d "$excluded_node_modules" ]]; then
  excluded_files=$(find "$excluded_node_modules" -type f -printf '.' | wc -c)
  excluded_symlinks=$(find "$excluded_node_modules" -type l -printf '.' | wc -c)
fi
printf 'EXCLUDED\tthemes/sarafatto/node_modules\t%s\t%s\n' "$excluded_files" "$excluded_symlinks"

for rel in "${roots[@]}" "$single_file"; do
  target="$root_real/$rel"
  if [[ -L "$target" ]]; then
    validate_record_path "$rel"
    printf 'SYMLINK\t%s\n' "$rel"
    continue
  fi
  if [[ -d "$target" ]]; then
    while IFS= read -r -d '' file; do
      relative_link=${file#"$root_real/"}
      validate_record_path "$relative_link"
      printf 'SYMLINK\t%s\n' "$relative_link"
    done < <(find "$target" -path "$excluded_node_modules" -prune -o -type l -print0)
    while IFS= read -r -d '' file; do
      relative_file=${file#"$root_real/"}
      validate_record_path "$relative_file"
      hash=$(sha256sum -- "$file" | cut -d ' ' -f 1)
      size=$(stat -c '%s' -- "$file")
      printf 'FILE\t%s\t%s\t%s\n' "$hash" "$size" "$relative_file"
    done < <(find "$target" -path "$excluded_node_modules" -prune -o -type f -print0)
  else
    hash=$(sha256sum -- "$target" | cut -d ' ' -f 1)
    size=$(stat -c '%s' -- "$target")
    printf 'FILE\t%s\t%s\t%s\n' "$hash" "$size" "$rel"
  fi
done
