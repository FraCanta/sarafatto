#!/usr/bin/env bash
set -euo pipefail

expected_root='/home/www/public/wp-content'
roots=('themes/sarafatto' 'plugins/sarafatto-core')
single_file='mu-plugins/sarafatto-polylang-front-page-url.php'
validate_record_path() {
  local path=$1
  [[ "$path" != *$'\t'* && "$path" != *$'\n'* && "$path" != *$'\r'* ]] || { echo 'Nome file remoto non rappresentabile nell inventario.' >&2; exit 24; }
}
root_real=$(realpath -e -- "$expected_root")
[[ "$root_real" == "$expected_root" ]] || { echo 'wp-content inatteso.' >&2; exit 20; }
for tool in realpath find sha256sum stat rsync; do command -v "$tool" >/dev/null || { echo "Comando remoto assente: $tool" >&2; exit 21; }; done
[[ -d "$root_real/themes/sarafatto" && -d "$root_real/plugins/sarafatto-core" && -f "$root_real/$single_file" ]] || { echo 'Percorsi allowlist incompleti.' >&2; exit 22; }

baseline='/home/www/sarafatto-deploy/state/production-inventory.tsv'
if [[ -r "$baseline" ]]; then printf 'BASELINE\tavailable\n'; else printf 'BASELINE\tabsent\n'; fi
if [[ -r "$baseline" ]]; then
  printf 'BASELINE_BEGIN\n'
  cat -- "$baseline"
  printf 'BASELINE_END\n'
fi
for rel in "${roots[@]}" "$single_file"; do
  target="$root_real/$rel"
  if [[ -L "$target" ]]; then
    validate_record_path "$rel"
    printf 'SYMLINK\t%s\n' "$rel"
    continue
  fi
  if [[ -d "$target" ]]; then
    while IFS= read -r -d '' link; do
      relative_link=${link#"$root_real/"}
      validate_record_path "$relative_link"
      printf 'SYMLINK\t%s\n' "$relative_link"
    done < <(find "$target" -type l -print0)
    while IFS= read -r -d '' file; do
      relative_file=${file#"$root_real/"}
      validate_record_path "$relative_file"
      hash=$(sha256sum -- "$file" | cut -d ' ' -f 1)
      size=$(stat -c '%s' -- "$file")
      printf 'FILE\t%s\t%s\t%s\n' "$hash" "$size" "$relative_file"
    done < <(find "$target" -type f -print0)
  else
    hash=$(sha256sum -- "$target" | cut -d ' ' -f 1)
    size=$(stat -c '%s' -- "$target")
    printf 'FILE\t%s\t%s\t%s\n' "$hash" "$size" "$rel"
  fi
done
