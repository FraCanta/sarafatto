#!/usr/bin/env bash
set -euo pipefail

public_root='/home/www/public/wp-content'
readonly excluded_path='themes/sarafatto/node_modules'
fixture_mode=0

if [[ "${1:-}" == '--fixture-root' && $# -eq 2 ]]; then
  fixture_mode=1
  public_root=$2
elif [[ $# -ne 0 ]]; then
  echo 'Questo inventario read-only non accetta argomenti.' >&2
  exit 2
fi

for tool in realpath find sha256sum stat wc cut readlink; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Comando richiesto assente: $tool" >&2; exit 10; }
done
root_real=$(realpath -e -- "$public_root")
if (( fixture_mode == 0 )); then
  [[ "$root_real" == "$public_root" ]] || { echo 'Root pubblica non canonica.' >&2; exit 11; }
else
  temp_root=$(realpath -e -- "${TMPDIR:-/tmp}")
  [[ ! -L "$public_root" && "$root_real" == "$temp_root/"* ]] || { echo 'Fixture fuori dalla directory temporanea o symlink.' >&2; exit 11; }
fi
public_root=$root_real
excluded_root="$public_root/$excluded_path"
[[ -d "$public_root/themes/sarafatto" && -d "$public_root/plugins/sarafatto-core" && -f "$public_root/mu-plugins/sarafatto-polylang-front-page-url.php" ]] || { echo 'Root fixture o componenti gestiti incompleti.' >&2; exit 13; }

validate_field() {
  local value=$1
  [[ "$value" != *$'\t'* && "$value" != *$'\n'* && "$value" != *$'\r'* ]] || {
    echo 'Percorso o destinazione symlink non rappresentabile nell inventario.' >&2
    exit 12
  }
}

excluded_files=0
excluded_symlinks=0
if [[ -L "$excluded_root" ]]; then
  excluded_symlinks=1
elif [[ -d "$excluded_root" ]]; then
  excluded_files=$(find -P "$excluded_root" -type f -printf '.' | wc -c)
  excluded_symlinks=$(find -P "$excluded_root" -type l -printf '.' | wc -c)
fi
printf 'EXCLUDED\t%s\t%s\t%s\n' "$excluded_path" "$excluded_files" "$excluded_symlinks"

for relative_root in themes/sarafatto plugins/sarafatto-core mu-plugins/sarafatto-polylang-front-page-url.php; do
  target="$public_root/$relative_root"
  if [[ -L "$target" ]]; then
    link_target=$(readlink -- "$target")
    validate_field "$relative_root"
    validate_field "$link_target"
    printf 'SYMLINK\t%s\t%s\n' "$relative_root" "$link_target"
    continue
  fi
  if [[ -d "$target" ]]; then
    find -P "$target" -path "$excluded_root" -prune -o -type l -print0 | while IFS= read -r -d '' link; do
      relative_link=${link#"$public_root/"}
      link_target=$(readlink -- "$link")
      validate_field "$relative_link"
      validate_field "$link_target"
      printf 'SYMLINK\t%s\t%s\n' "$relative_link" "$link_target"
    done

    find -P "$target" -path "$excluded_root" -prune -o -type f -print0 | while IFS= read -r -d '' file; do
      relative_file=${file#"$public_root/"}
      validate_field "$relative_file"
      hash=$(sha256sum -- "$file" | cut -d ' ' -f 1)
      size=$(stat -c '%s' -- "$file")
      mode=$(stat -c '%a' -- "$file")
      printf 'FILE\t%s\t%s\t%s\t%s\n' "$hash" "$size" "$mode" "$relative_file"
    done
  elif [[ -f "$target" ]]; then
    hash=$(sha256sum -- "$target" | cut -d ' ' -f 1)
    size=$(stat -c '%s' -- "$target")
    mode=$(stat -c '%a' -- "$target")
    printf 'FILE\t%s\t%s\t%s\t%s\n' "$hash" "$size" "$mode" "$relative_root"
  else
    echo "Percorso gestito assente o di tipo non supportato: $relative_root" >&2
    exit 13
  fi
done
printf 'END\n'
