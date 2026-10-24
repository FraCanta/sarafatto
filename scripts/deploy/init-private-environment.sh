#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly private_root='/home/www/sarafatto-deploy'
readonly marker_name='.sarafatto-deploy-root'
readonly marker_value='sarafatto-private-environment-v1'
create=0

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != '--create' ) ]]; then
  echo 'Uso: init-private-environment.sh [--create]' >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then create=1; fi

for tool in realpath stat id find cat mkdir chmod basename; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Comando richiesto assente: $tool" >&2; exit 9; }
done

for parent in /home /home/www; do
  [[ ! -L "$parent" && -d "$parent" ]] || { echo "Parent assente o symlink: $parent" >&2; exit 10; }
done
[[ "$(realpath -e -- /home/www)" == '/home/www' ]] || { echo 'Root /home/www non canonica.' >&2; exit 11; }
case "$private_root/" in /home/www/public/*) echo 'Root privata dentro la webroot.' >&2; exit 12 ;; esac

uid=$(id -u)
marker="$private_root/$marker_name"

check_owned_directory() {
  local path=$1 owner mode
  [[ ! -L "$path" && -d "$path" ]] || { echo "Directory assente o symlink inatteso: $path" >&2; exit 13; }
  owner=$(stat -c '%u' -- "$path")
  mode=$(stat -c '%a' -- "$path")
  [[ "$owner" == "$uid" ]] || { echo "Proprietario inatteso per $path (uid $owner, atteso $uid)." >&2; exit 14; }
  if (( create == 0 )) && [[ "$mode" != '700' ]]; then
    echo "Permessi non restrittivi su $path (mode $mode; atteso 700). Usare --create solo dopo revisione." >&2
    exit 15
  fi
}

if [[ -e "$private_root" || -L "$private_root" ]]; then
  check_owned_directory "$private_root"
  [[ ! -L "$marker" && -f "$marker" ]] || { echo 'Root preesistente non riconosciuta: marker assente o non regolare.' >&2; exit 16; }
  marker_owner=$(stat -c '%u' -- "$marker")
  marker_mode=$(stat -c '%a' -- "$marker")
  [[ "$marker_owner" == "$uid" ]] || { echo 'Proprietario marker inatteso.' >&2; exit 16; }
  if (( create == 0 )) && [[ "$marker_mode" != '600' ]]; then
    echo "Permessi marker non restrittivi (mode $marker_mode; atteso 600)." >&2
    exit 16
  fi
  [[ "$(cat -- "$marker")" == "$marker_value" ]] || { echo 'Marker root non riconosciuto.' >&2; exit 17; }
  find -P "$private_root" -mindepth 1 -maxdepth 1 -printf '%f\0' | while IFS= read -r -d '' name; do
    [[ "$name" == "$marker_name" ]] && continue
    case "$name" in state|backups|staging|releases|locks|logs) ;; *) echo "Contenuto inatteso nella root privata: $name" >&2; exit 18 ;; esac
  done
  for directory in state backups staging releases locks logs; do
    path="$private_root/$directory"
    if [[ -e "$path" || -L "$path" ]]; then check_owned_directory "$path"; else printf 'Da creare: %s\n' "$path"; fi
  done
else
  printf 'Root privata assente: %s\n' "$private_root"
  for directory in state backups staging releases locks logs; do printf 'Da creare: %s/%s\n' "$private_root" "$directory"; done
fi

if (( create == 0 )); then
  echo 'SIMULAZIONE: nessuna directory o file creato; per creare la root privata occorre --create.'
  exit 0
fi

if [[ ! -e "$private_root" ]]; then
  mkdir -m 700 -- "$private_root"
  printf '%s\n' "$marker_value" > "$marker"
  chmod 600 -- "$marker"
fi
chmod 700 -- "$private_root"
for directory in state backups staging releases locks logs; do
  path="$private_root/$directory"
  if [[ -L "$path" ]]; then echo "Symlink inatteso: $path" >&2; exit 19; fi
  if [[ ! -e "$path" ]]; then mkdir -m 700 -- "$path"; fi
  check_owned_directory "$path"
  chmod 700 -- "$path"
done
chmod 600 -- "$marker"
echo 'Root privata verificata e inizializzata; nessun percorso pubblico è stato modificato.'
