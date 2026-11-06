"""PostToolUse (Edit/Write): checagem de sintaxe em menos de 1 s — py_compile nos .py e `node --check` nos .js.

O erro aparece logo após a edição (saída 2 devolve a mensagem ao Claude), em vez de só ao subir o servidor.
"""
import json
import py_compile
import shutil
import subprocess
import sys


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    arq = (d.get("tool_input") or {}).get("file_path") or ""
    if arq.endswith(".py"):
        try:
            py_compile.compile(arq, doraise=True)
        except py_compile.PyCompileError as e:
            print(f"Erro de sintaxe em {arq}:\n{e.msg}", file=sys.stderr)
            return 2
    elif arq.endswith(".js") and shutil.which("node"):
        r = subprocess.run(["node", "--check", arq], capture_output=True, text=True)
        if r.returncode:
            print(f"Erro de sintaxe em {arq}:\n{r.stderr.strip()[:1500]}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
