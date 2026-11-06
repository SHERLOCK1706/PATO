"""PreToolUse (Bash): impede que planilhas/PDF/zip particulares entrem no git.

Só são versionáveis os binários de pato_app/modelos/, tests/dados/ e docs/referencias/. Em `git add`/`git commit`
o hook confere o que entraria (arquivos novos ou alterados que o git não ignora, e o que já está no índice) e bloqueia
(saída 2) se houver planilha, PDF ou zip fora dessas pastas — as planilhas enviadas pelo usuário (BR-174, BR-158…)
ficam só na máquina.
"""
import json
import re
import shlex
import subprocess
import sys

PERMITIDAS = ("pato_app/modelos/", "tests/dados/", "docs/referencias/")
PRIVADO = re.compile(r"\.(xlsx|xlsm|xls|pdf|zip|pato|db|sqlite)$", re.I)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []


def main():
    try:
        cmd = (json.load(sys.stdin).get("tool_input") or {}).get("command") or ""
    except Exception:  # noqa: BLE001
        return 0
    if not re.search(r"\bgit\b[^;&|]*\b(add|commit)\b", cmd):
        return 0
    candidatos = set(git("diff", "--cached", "--name-only"))
    for m in re.finditer(r"\bgit\s+add\b([^;&|]*)", cmd):
        args = shlex.split(m.group(1), posix=True) if m.group(1).strip() else []
        nomes = [a for a in args if not a.startswith("-")]
        if any(a in ("-A", "--all", "-u", "--update") for a in args) or not nomes or \
                any(n in (".", "*") or any(ch in n for ch in "*?[") or n.endswith("/") for n in nomes):
            candidatos |= set(git("ls-files", "--others", "--modified", "--exclude-standard"))
        else:  # add pelo nome: só os arquivos citados (e o conteúdo das pastas citadas)
            for n in nomes:
                candidatos |= set(git("ls-files", "--others", "--modified", "--exclude-standard", "--", n)) or {n}
    if re.search(r"\bgit\s+commit\b[^;&|]*\s-[a-zA-Z]*a", cmd):
        candidatos |= set(git("ls-files", "--modified"))
    ruins = sorted(f for f in candidatos if PRIVADO.search(f) and not f.startswith(PERMITIDAS))
    if ruins:
        print("Bloqueado: arquivos particulares (planilhas/PDF/zip) fora de pato_app/modelos/, tests/dados/ e "
              "docs/referencias/ entrariam no git:\n  " + "\n  ".join(ruins) +
              "\nTire-os do índice (git restore --staged <arquivo>) ou adicione ao .gitignore e adicione só os arquivos "
              "do código pelo nome.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
