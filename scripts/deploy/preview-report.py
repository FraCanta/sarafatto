#!/usr/bin/env python3
"""Build a bounded, read-only report from local and remote deployment inventories."""
import pathlib
import re
import sys

EXCLUDED = "themes/sarafatto/node_modules"
SINGLE_FILE = "mu-plugins/sarafatto-polylang-front-page-url.php"
MAX_DETAILS = 20


def fail(message):
    raise SystemExit(f"Inventario non valido: {message}")


def managed(path):
    return (path == "themes/sarafatto" or path.startswith("themes/sarafatto/")
            or path == "plugins/sarafatto-core" or path.startswith("plugins/sarafatto-core/")
            or path == SINGLE_FILE)


def excluded(path):
    return path == EXCLUDED or path.startswith(EXCLUDED + "/")


def valid_path(path):
    return bool(path) and not path.startswith("/") and "\\" not in path and "\t" not in path and "\r" not in path and "\n" not in path and all(part not in ("", ".", "..") for part in path.split("/"))


def read_local(path):
    result = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 3:
            fail(f"riga locale {number} malformata")
        digest, size, name = fields
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or not size.isdigit() or not valid_path(name):
            fail(f"riga locale {number} non valida")
        if not managed(name) or excluded(name):
            fail(f"percorso locale fuori dal perimetro gestito: {name}")
        if name in result:
            fail(f"percorso locale duplicato: {name}")
        result[name] = (digest, size)
    return result


def read_remote(path):
    files, baseline, links = {}, {}, []
    baseline_state, excluded_counts = None, (0, 0)
    excluded_seen = False
    section = None
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line in ("BASELINE_BEGIN", "BASELINE_END"):
            if line == "BASELINE_BEGIN":
                if section is not None:
                    fail("marker baseline annidato")
                section = "baseline"
            else:
                if section != "baseline":
                    fail("chiusura baseline inattesa")
                section = None
            continue
        fields = line.split("\t")
        if section == "baseline":
            if len(fields) != 3:
                fail(f"riga baseline {number} malformata")
            digest, size, name = fields
            if not re.fullmatch(r"[a-f0-9]{64}", digest) or not size.isdigit() or not valid_path(name):
                fail(f"riga baseline {number} non valida")
            if excluded(name):
                continue
            if not managed(name) or name in baseline:
                fail(f"percorso baseline inatteso o duplicato: {name}")
            baseline[name] = (digest, size)
        elif len(fields) == 2 and fields[0] == "BASELINE":
            if baseline_state is not None or fields[1] not in ("available", "absent"):
                fail("stato baseline duplicato o non valido")
            baseline_state = fields[1]
        elif len(fields) == 4 and fields[0] == "EXCLUDED":
            if excluded_seen or fields[1] != EXCLUDED or not fields[2].isdigit() or not fields[3].isdigit():
                fail("record di esclusione non valido")
            excluded_counts = (int(fields[2]), int(fields[3]))
            excluded_seen = True
        elif len(fields) == 2 and fields[0] == "SYMLINK":
            name = fields[1]
            if not valid_path(name) or not managed(name) or excluded(name):
                fail(f"symlink fuori dal perimetro gestito: {name}")
            links.append(name)
        elif len(fields) == 4 and fields[0] == "FILE":
            _, digest, size, name = fields
            if not re.fullmatch(r"[a-f0-9]{64}", digest) or not size.isdigit() or not valid_path(name):
                fail(f"riga file remota {number} non valida")
            if excluded(name):
                fail(f"file escluso apparso nell'inventario gestito: {name}")
            if not managed(name) or name in files:
                fail(f"percorso remoto fuori perimetro o duplicato: {name}")
            files[name] = (digest, size)
        else:
            fail(f"record remoto sconosciuto alla riga {number}")
    if section is not None or baseline_state is None or not excluded_seen:
        fail("inventario remoto incompleto")
    if baseline_state == "available" and not baseline:
        fail("baseline dichiarata presente ma vuota/non valida")
    return files, baseline, links, baseline_state, excluded_counts


def details(title, paths):
    lines = [f"#### {title} ({len(paths)})"]
    lines += [f"- `{name}`" for name in paths[:MAX_DETAILS]] or ["- Nessuno"]
    if len(paths) > MAX_DETAILS:
        lines.append(f"- … altri {len(paths) - MAX_DETAILS} omessi")
    return lines


def main():
    if len(sys.argv) != 5:
        fail("uso: preview-report.py LOCAL REMOTE SUMMARY RELEASE_SHA")
    local_path, remote_path, summary_path = map(pathlib.Path, sys.argv[1:4])
    release_sha = sys.argv[4]
    if not re.fullmatch(r"[a-f0-9]{40}", release_sha):
        fail("SHA release non valido")
    desired = read_local(local_path)
    remote, baseline, links, baseline_state, counts = read_remote(remote_path)
    new = sorted(desired.keys() - remote.keys())
    modified = sorted(p for p in desired.keys() & remote.keys() if desired[p] != remote[p])
    unchanged = sorted(p for p in desired.keys() & remote.keys() if desired[p] == remote[p])
    remote_only = sorted(remote.keys() - desired.keys())
    drift = sorted(p for p in remote.keys() | baseline.keys() if remote.get(p) != baseline.get(p)) if baseline_state == "available" else []
    old_bundles = [p for p in remote_only if p.startswith("themes/sarafatto/assets/dist/assets/") and re.search(r"-[A-Za-z0-9_-]{6,}\.", p)]
    backups = [p for p in remote_only if re.search(r"(?:\.bak|\.backup|\.orig|~)$", p, re.I)]

    lines = [f"# Anteprima rilascio `{release_sha}`", "", "Confronto in sola lettura; nessuna scrittura o eliminazione remota eseguita.", "",
             f"Baseline remota: **{baseline_state}**.",
             f"Esclusi dal perimetro: `{EXCLUDED}/` — {counts[0]} file e {counts[1]} symlink (conteggi sintetici; non confrontati né proposti per la rimozione).", "",
             *details("Nuovi file", new), "", *details("Modificati rispetto all'artefatto", modified), "",
             *details("Invariati", unchanged), "", *details("Solo in produzione — conservati", remote_only), "",
             *details("Vecchi bundle Vite — conservati", old_bundles), "", *details("Backup — conservati", backups), ""]
    if baseline_state == "available":
        lines += details("Drift dalla baseline", drift) + [""]
    else:
        lines += ["Senza baseline approvata non è possibile verificare l'assenza di modifiche manuali in produzione.",
                  "Drift dalla baseline: non verificabile perché la baseline è assente.", ""]
    lines += details("Symlink nel perimetro gestito (bloccanti)", sorted(links))
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Inventario: {len(new)} nuovi, {len(modified)} modificati, {len(unchanged)} invariati, {len(remote_only)} solo remoto; esclusi node_modules: {counts[0]} file/{counts[1]} symlink; baseline {baseline_state}.")
    if links:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
