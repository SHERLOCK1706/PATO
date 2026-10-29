"""Servidor MCP: permite ao Claude ler e preencher o inventário/planilhas do PATO.

Configuração no Claude Desktop (claude_desktop_config.json):
  "mcpServers": {"pato": {"command": "python", "args": ["-m", "pato_app.mcp_server"],
                           "cwd": "C:/caminho/para/pato-app"}}
"""
from __future__ import annotations

from typing import Any

try:  # SDK mcp 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # SDK mcp 1.x
    from mcp.server.fastmcp import FastMCP

from .catalogo import CATEGORIAS, COLUNAS_UI, ROTULOS
from .servico import Servico

mcp = FastMCP("pato", instructions=(
    "Ferramentas do sistema PATO (Plano Anual de Trabalho e Orçamento — conservação rodoviária DNIT). "
    "Use listar_projetos para achar o projeto; listar_inventario / adicionar_itens_inventario para ler e "
    "preencher o inventário georreferenciado; importar_planilha para trazer o inventário de outro segmento; "
    "exportar_planilha_pato para gerar o PATO preenchido. ler_celulas / escrever_celulas atuam em qualquer .xlsx."))
_sv: Servico | None = None


def sv() -> Servico:
    global _sv
    if _sv is None:
        _sv = Servico()
    return _sv


@mcp.tool()
def categorias_inventario() -> dict:
    """Lista as categorias de inventário (código, nome, geometria) e os campos de cada uma."""
    return {c: dict(nome=v["nome"], geometria=v["geom"],
                    campos=["snv", "tipo_pista", "km_ini", "km_fim", "lat_ini", "lon_ini", "lat_fim", "lon_fim",
                            "lado", "condicao", "tipo", "obs"] + COLUNAS_UI.get(c, []))
            for c, v in CATEGORIAS.items()} | {"_rotulos": ROTULOS}


@mcp.tool()
def listar_projetos() -> list[dict]:
    """Projetos (trechos) cadastrados, com id, rodovia, segmento, km e número de itens."""
    return sv().listar_projetos()


@mcp.tool()
def ler_projeto(projeto_id: int) -> dict:
    """Dados do projeto, resumo do inventário, reflexo no PATO e alertas de validação."""
    r = sv().resumo(projeto_id)
    r["alertas"] = r["alertas"][:50]
    for c in r["categorias"].values():
        c.pop("por_tipo", None)
    return r


@mcp.tool()
def criar_projeto(rodovia: str, km_ini: float, km_fim: float, trecho: str = "", subtrecho: str = "",
                  snv: str = "", data_base: str = "", nome: str = "") -> dict:
    """Cria um projeto vazio. data_base no formato AAAA-MM-DD."""
    return sv().criar_projeto(dict(rodovia=rodovia, km_ini=km_ini, km_fim=km_fim, trecho=trecho or None,
                                   subtrecho=subtrecho or None, snv=snv or None, data_base=data_base or None,
                                   nome=nome or f"{rodovia} km {km_ini}–{km_fim}"))


@mcp.tool()
def atualizar_projeto(projeto_id: int, campos: dict[str, Any]) -> dict:
    """Altera campos do projeto: rodovia, trecho, subtrecho, segmento, snv, snv_versao, estado,
    unidade_local, data_inventario, data_base (AAAA-MM-DD), prazo, nome."""
    return sv().atualizar_projeto(projeto_id, campos)


@mcp.tool()
def alterar_trecho(projeto_id: int, km_ini: float, km_fim: float, recortar: bool = False) -> dict:
    """Muda o km inicial/final. recortar=True remove itens fora e corta feições na divisa."""
    return sv().alterar_trecho(projeto_id, km_ini, km_fim, recortar)


@mcp.tool()
def listar_inventario(projeto_id: int, categoria: str | None = None, km_de: float | None = None,
                      km_ate: float | None = None, limite: int = 200) -> dict:
    """Itens do inventário (filtro por categoria e faixa de km), com quantidades calculadas."""
    itens = sv().itens(projeto_id, categoria, km_de, km_ate)
    return dict(total=len(itens), itens=itens[:limite])


@mcp.tool()
def adicionar_itens_inventario(projeto_id: int, itens: list[dict[str, Any]], categoria: str | None = None) -> dict:
    """Adiciona itens. Cada item: categoria (ou use o parâmetro), km_ini, km_fim, lat_ini, lon_ini, lat_fim,
    lon_fim, snv, lado (E/D/E/D), condicao (Satisfatória/Recompor/Demolir e Recompor), tipo, obs e atributos
    da categoria (ex.: largura, extensao, dimensao, linhas...). Veja categorias_inventario."""
    novos = sv().adicionar_itens(projeto_id, itens, categoria)
    return dict(adicionados=len(novos), ids=[n["id"] for n in novos])


@mcp.tool()
def atualizar_item(item_id: int, campos: dict[str, Any]) -> dict:
    """Altera campos de um item (atributos não reconhecidos vão para 'dados'; None apaga)."""
    return sv().atualizar_item(item_id, campos)


@mcp.tool()
def remover_itens(item_ids: list[int]) -> dict:
    """Remove itens do inventário."""
    return {"removidos": sv().excluir_itens(item_ids)}


@mcp.tool()
def importar_planilha(caminho_xlsx: str, modo: str = "novo", projeto_id: int | None = None,
                      categorias: list[str] | None = None) -> dict:
    """Importa inventário de um .xlsx (modelo DNIT 'Cadastro de ...' ou abas CAD_* do PATO).
    modo: 'novo' cria projeto; 'substituir' troca as categorias no projeto_id; 'acrescentar' soma."""
    r = sv().importar_arquivo(caminho_xlsx, modo, projeto_id, categorias)
    r["relatorio"] = [{k: v for k, v in x.items() if k in ("aba", "categoria", "linhas", "avisos", "nao_mapeadas")}
                      for x in r["relatorio"]]
    return r


@mcp.tool()
def resumo_inventario(projeto_id: int) -> dict:
    """Quadro-resumo do inventário (equivalente à aba RESUMO_INVENT) e quantidades que vão ao PATO."""
    r = sv().resumo(projeto_id)
    return dict(painel=r["painel"], resumo_invent=r["resumo_invent"], pato=r["pato"], n_alertas=r["n_alertas"])


@mcp.tool()
def validar_inventario(projeto_id: int, limite: int = 100) -> list[dict]:
    """Alertas: fora do trecho, km invertido, coordenada discrepante, sem coordenada, SNV inexistente."""
    return sv().validar(projeto_id)[:limite]


@mcp.tool()
def analisar_inventario(projeto_id: int, arquivo_snv: str | None = None, versao_snv: str | None = None,
                        tolerancia_km: float = 1.0) -> dict:
    """Verifica SNV, coordenadas × km, limite do trecho e nomenclatura (Álbum DNIT IPR-736).
    Correções certas são aplicadas automaticamente (coordenada pelo km informado, digitação, grafia, fora do trecho)
    e ficam em Ajustes; as demais ficam pendentes com a sugestão mais provável preenchida.
    arquivo_snv: planilha/CSV oficial do SNV (opcional)."""
    return sv().gerar_sugestoes(projeto_id, arquivo_snv, versao_snv, tolerancia_km)


@mcp.tool()
def listar_sugestoes(projeto_id: int, status: str = "pendente", tipo: str | None = None, limite: int = 200) -> dict:
    """Sugestões e ajustes. status: pendente (Revisão) | aplicada (Ajustes; campo 'automatica' indica se foi o sistema)
    | dispensada. tipo: correção | padronização | SNV. Traz motivo, valores atuais, correção sugerida ('mudancas'),
    alternativas ('opcoes') e, se aplicada, o que foi gravado ('aplicado')."""
    lst = sv().sugestoes(projeto_id, status, tipo)
    return dict(total=len(lst), sugestoes=lst[:limite])


@mcp.tool()
def aplicar_sugestao(sugestao_id: int, opcao: int | None = None, mudancas: dict[str, Any] | None = None) -> dict:
    """Aplica uma sugestão: a correção sugerida, a alternativa nº `opcao`, ou valores informados em `mudancas`."""
    return sv().aplicar_sugestao(sugestao_id, mudancas, opcao)


@mcp.tool()
def aplicar_sugestoes_em_lote(projeto_id: int, ids: list[int] | None = None, confianca: str | None = "alta",
                              tipo: str | None = None) -> dict:
    """Aplica várias sugestões pendentes que tenham correção definida (por padrão só as de confiança alta)."""
    return sv().aplicar_lote(projeto_id, ids, confianca, tipo)


@mcp.tool()
def dispensar_sugestao(sugestao_id: int) -> dict:
    """Dispensa (não aplica) uma sugestão; ela não volta em novas análises."""
    return sv().dispensar_sugestao(sugestao_id)


@mcp.tool()
def desfazer_sugestao(sugestao_id: int) -> dict:
    """Desfaz uma sugestão aplicada (restaura os valores anteriores) ou reabre uma dispensada."""
    return sv().desfazer_sugestao(sugestao_id)


@mcp.tool()
def exportar_original_corrigido(projeto_id: int) -> dict:
    """Cópia da planilha de inventário importada com os valores das sugestões aplicadas (sem marcações)."""
    return sv().exportar_original(projeto_id)


@mcp.tool()
def gerar_aceiro(projeto_id: int, largura_ate_cerca: float = 30.0, pct_arboreo: float = 0.2) -> dict:
    """Gera o memorial de aceiro + roçada da faixa (CAD_ACEIRO) a partir das cercas."""
    return sv().gerar_aceiro(projeto_id, largura_ate_cerca, pct_arboreo)


@mcp.tool()
def exportar_planilha_pato(projeto_id: int, modelo_xlsx: str | None = None) -> dict:
    """Gera cópia da planilha PATO com CAPA e abas CAD_* preenchidas (fórmulas preservadas)."""
    return sv().exportar_pato(projeto_id, modelo_xlsx)


@mcp.tool()
def exportar_inventario(projeto_id: int, formato: str = "xlsx") -> dict:
    """Exporta o inventário: xlsx (por categoria + resumo), geojson ou kml."""
    if formato == "xlsx":
        return sv().exportar_inventario(projeto_id)
    return sv().exportar_geo(projeto_id, formato)


@mcp.tool()
def listar_abas(caminho_xlsx: str) -> list[dict]:
    """Abas de uma planilha qualquer."""
    return sv().listar_abas(caminho_xlsx)


@mcp.tool()
def ler_celulas(caminho_xlsx: str, aba: str, intervalo: str, formulas: bool = False) -> list[list]:
    """Lê um intervalo (ex.: 'A1:H40'). formulas=True devolve as fórmulas em vez dos valores."""
    return sv().ler_celulas(caminho_xlsx, aba, intervalo, formulas)


@mcp.tool()
def escrever_celulas(caminho_xlsx: str, aba: str, valores: dict[str, Any], salvar_como: str | None = None) -> str:
    """Grava valores ou fórmulas ('=SOMA(...)' em inglês: '=SUM(...)') em células, ex.: {'D74': 'BR-158/MT'}.
    Preserva desenhos, estilos e demais abas. Retorna o caminho salvo."""
    return sv().escrever_celulas(caminho_xlsx, aba, valores, salvar_como)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
