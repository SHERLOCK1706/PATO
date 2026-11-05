"""Abertura de planilhas .xlsx com reaproveitamento.

A planilha modelo do PATO (72 abas, centenas de milhares de estilos) leva cerca de 10 s para abrir no openpyxl, e a
importação de referência lia o mesmo arquivo 10 vezes (cada módulo abria valores e fórmulas por conta própria). Dentro de
`compartilhar()`, cada arquivo é aberto uma vez para valores e uma para fórmulas, e o mesmo objeto é entregue a todos.
Fora do bloco, `abrir()` funciona exatamente como `openpyxl.load_workbook`.
"""
from __future__ import annotations

import contextlib
import os
import threading

import openpyxl

_local = threading.local()


@contextlib.contextmanager
def compartilhar():
    """Dentro do bloco, a mesma planilha (mesmo caminho, data e tamanho) é aberta uma vez só e reaproveitada."""
    if getattr(_local, "cache", None) is not None:  # já dentro de um bloco
        yield
        return
    _local.cache = {}
    try:
        yield
    finally:
        _local.cache = None


def abrir(caminho, data_only: bool = False, read_only: bool = True):
    """Como openpyxl.load_workbook(caminho, read_only=..., data_only=...). Dentro de compartilhar(), devolve a planilha
    já aberta (completa, que serve tanto para leitura sequencial quanto para acesso direto às células)."""
    cache = getattr(_local, "cache", None)
    if cache is None or not isinstance(caminho, (str, os.PathLike)):
        return openpyxl.load_workbook(caminho, read_only=read_only, data_only=data_only)
    st = os.stat(caminho)
    chave = (os.path.abspath(os.fspath(caminho)), st.st_mtime_ns, st.st_size, bool(data_only))
    if chave not in cache:
        cache[chave] = openpyxl.load_workbook(caminho, data_only=data_only)
    return cache[chave]
