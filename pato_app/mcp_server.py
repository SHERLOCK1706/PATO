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
    "exportar_planilha_pato para gerar o PATO preenchido. Custos: custos_configuracao, ver_composicao, alterar_preco_insumo, trocar_insumo, alterar_tempo_fixo, calcular_bdi; binômio: binomio_listar, binomio_salvar_material, binomio_aplicar_vencedor; transporte: croqui_ler, croqui_salvar, importar_vmd_dnit, quadro_transportes, aplicar_momentos_ao_orcamento. ler_celulas / escrever_celulas atuam em qualquer .xlsx."))
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
def relatorio_pontos_a_corrigir(projeto_id: int, destinatario: str | None = None, responsavel: str | None = None,
                                observacoes: str | None = None, pendentes: bool = True, automaticos: bool = True,
                                manuais: bool = True, dispensadas: bool = False) -> dict:
    """Gera o relatório (.xlsx) de pontos a corrigir para a empresa que levantou o inventário: aba e linha da planilha,
    problema, correção (aplicada ou sugerida), ação esperada, links do mapa e coluna para a resposta da empresa."""
    return sv().relatorio_pontos(projeto_id, pendentes, automaticos, manuais, dispensadas, destinatario, responsavel,
                                 observacoes)


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


# ------------------------------------------------------------------ custos (SICRO, BDI, composições)
@mcp.tool()
def custos_configuracao(projeto_id: int) -> dict:
    """Base SICRO (UF e data-base), regime e BDI do projeto, com as bases disponíveis."""
    return sv().custos.config(projeto_id)


@mcp.tool()
def custos_configurar(projeto_id: int, uf: str | None = None, data_base: str | None = None, regime: str | None = None,
                      bdi_sd: float | None = None, bdi_cd: float | None = None) -> dict:
    """Troca a base (UF, data-base AAAA-MM), o regime (SD sem desoneração / CD com desoneração) ou o BDI (%)."""
    return sv().custos.configurar(projeto_id, uf, data_base, regime, bdi_sd, bdi_cd)


@mcp.tool()
def calcular_bdi(parcelas: dict | None = None, municipios: list[dict] | None = None, selic: float | None = None,
                 ano: int | None = None) -> dict:
    """Calculadora de BDI (método DNIT). municipios: [{nome, uf, aliquota (%), base (% do PV), peso}] para o ISSQN;
    selic (% a.a.) define as despesas financeiras; ano define a CPRB do regime com desoneração."""
    return sv().custos.calcular_bdi_completo(parcelas, municipios, selic, ano)


@mcp.tool()
def buscar_composicoes(projeto_id: int, texto: str = "", limite: int = 30) -> list[dict]:
    """Procura composições na base SICRO do projeto (código ou palavras da descrição)."""
    return sv().custos.buscar(projeto_id, texto, limite)


@mcp.tool()
def servicos_do_orcamento(projeto_id: int) -> dict:
    """Serviços escolhidos com preço atual e original nos dois regimes."""
    return sv().custos.servicos(projeto_id)


@mcp.tool()
def adicionar_servico(projeto_id: int, codigo: str) -> dict:
    """Inclui uma composição (SICRO ou própria) entre os serviços do orçamento."""
    return sv().custos.adicionar_servico(projeto_id, codigo)


@mcp.tool()
def ver_composicao(projeto_id: int, codigo: str, regime: str | None = None) -> dict:
    """Composição analítica calculada: equipamentos, mão de obra, materiais, auxiliares, tempo fixo, transportes,
    custo direto e preço com BDI (com as alterações do projeto)."""
    return sv().custos.composicao(projeto_id, codigo, regime)


@mcp.tool()
def alterar_preco_insumo(projeto_id: int, tipo: str, codigo: str, preco: float | None = None,
                         custo_produtivo: float | None = None, custo_improdutivo: float | None = None,
                         regime: str = "AMBOS", motivo: str | None = None) -> dict:
    """Altera o preço de um insumo em todas as composições. tipo: MAT, MO, TF (preco) ou EQ (custos horários)."""
    vals = dict(preco=preco) if tipo.upper() != "EQ" else dict(custo_op=custo_produtivo, custo_imp=custo_improdutivo)
    return sv().custos.alterar_insumo(projeto_id, tipo, codigo, vals, regime, motivo)


@mcp.tool()
def trocar_insumo(projeto_id: int, secao: str, de_codigo: str, para_codigo: str, composicao: str | None = None,
                  quantidade: float | None = None) -> dict:
    """Troca um insumo por outro da base (secao A equipamento, B mão de obra, C material, D auxiliar),
    ex.: brita 0 comercial → brita 1. composicao=None troca em todas."""
    return sv().custos.trocar_insumo(projeto_id, secao, de_codigo, para_codigo, composicao, quantidade)


@mcp.tool()
def alterar_tempo_fixo(projeto_id: int, acao: str, composicao: str | None = None, insumo: str | None = None,
                       de_composicao: str | None = None, valor: float | None = None,
                       para_composicao: str | None = None) -> dict:
    """Tempo fixo: acao quantidade | retirar | incluir | trocar (troca o veículo/composição de tempo fixo e o transporte)."""
    return sv().custos.alterar_tempo_fixo(projeto_id, acao, composicao, insumo, de_composicao, valor, para_composicao)


@mcp.tool()
def alterar_dmt(projeto_id: int, insumo: str, composicao: str | None = None, dmt_leito_natural: float | None = None,
                dmt_revestimento_primario: float | None = None, dmt_pavimentada: float | None = None) -> dict:
    """Altera as distâncias de transporte (km) de um insumo, numa composição ou em todas."""
    return sv().custos.alterar_dmt(projeto_id, composicao, insumo, dmt_leito_natural, dmt_revestimento_primario,
                                   dmt_pavimentada)


@mcp.tool()
def listar_alteracoes_custo(projeto_id: int) -> list[dict]:
    """Registro das alterações de custo (preço, troca de insumo, tempo fixo, transporte) com situação ativa/desfeita."""
    return sv().custos.alteracoes(projeto_id)


@mcp.tool()
def desfazer_alteracao_custo(projeto_id: int, alteracao_id: int, reativar: bool = False) -> dict:
    """Desfaz (ou reativa) uma alteração de custo."""
    return sv().custos.ativar(projeto_id, alteracao_id, reativar)


@mcp.tool()
def exportar_composicoes(projeto_id: int) -> dict:
    """Gera o Excel com serviços, composições (SD/CD), insumos alterados e BDI."""
    return sv().exportar_composicoes(projeto_id)


# ------------------------------------------------------------------ binômio
def _resumo_binomio(r: dict) -> dict:
    v = r.get("vencedor") or {}
    return dict(id=r["id"], nome=r.get("nome") or r.get("produto"), codigo=r.get("codigo"),
                vencedor=v.get("fornecedor") or (f"{v.get('local')}/{v.get('uf')}" if v else None), total=v.get("total"),
                linhas=[{k: x.get(k) for k in ("fornecedor", "local", "uf", "preco_t_reaj", "preco_m3_reaj", "transporte",
                                                "aq_icms", "tr_icms", "aq_bdi", "tr_bdi", "total", "vencedor") if k in x}
                        for x in r["linhas"]], aplicado=r.get("aplicado"))


@mcp.tool()
def binomio_listar(projeto_id: int) -> dict:
    """Binômio do projeto: materiais cotados (pétreos, madeira, capa asfáltica comercial) e betuminosos ANP,
    com o vencedor (menor aquisição + transporte) de cada um."""
    r = sv().binomio.listar(projeto_id)
    return dict(data_base=r["data_base"], bdi=r["bdi"], materiais=[_resumo_binomio(m) for m in r["materiais"]],
                betuminosos=[_resumo_binomio(p) for p in r["produtos"]])


@mcp.tool()
def binomio_salvar_material(projeto_id: int, nome: str, cotacoes: list[dict], codigo: str | None = None,
                            grupo: str = "petreo", custo_pav: float | None = None, custo_npav: float | None = None,
                            indice: str | None = None, binomio_id: int | None = None) -> dict:
    """Cria/atualiza um material cotado. cotacoes: [{fornecedor, preco, unidade 't'|'m3', densidade, data 'AAAA-MM',
    dmt_pav, dmt_npav}] — inclua {fornecedor:'SICRO', sicro:true, densidade, dmt_pav, dmt_npav} para comparar com a base.
    grupo: petreo | madeira | betuminoso_comercial | outro."""
    return _resumo_binomio(sv().binomio.salvar_material(projeto_id, dict(
        nome=nome, codigo=codigo, grupo=grupo, custo_pav=custo_pav, custo_npav=custo_npav, indice=indice,
        cotacoes=cotacoes), binomio_id))


@mcp.tool()
def binomio_salvar_betuminoso(projeto_id: int, produto: str, origens: list[dict], codigo: str | None = None,
                              bdi: float | None = None, binomio_id: int | None = None) -> dict:
    """Cria/atualiza um betuminoso (ANP). origens: [{nome 'R-1', uf, local, preco_t (ANP R$/t s/ ICMS), icms (%),
    d_fluvial, d_pav, d_rp, d_ln, pedagio, balsa}]. bdi vazio = BDI do projeto."""
    return _resumo_binomio(sv().binomio.salvar_produto(projeto_id, dict(
        produto=produto, codigo=codigo, bdi=bdi, origens=origens), binomio_id))


@mcp.tool()
def binomio_importar_planilha(projeto_id: int, caminho_xlsx: str, substituir: bool = False) -> dict:
    """Lê BINOMIO_COTACOES, BINOMIO_ANP e INDICES_REAJ de uma planilha PATO."""
    r = sv().binomio.importar_de_planilha(projeto_id, caminho_xlsx, substituir)
    return r["importados"]


@mcp.tool()
def binomio_aplicar_vencedor(projeto_id: int, binomio_id: int, codigo_insumo: str | None = None,
                             aplicar_dmt: bool = True) -> dict:
    """Grava o preço do vencedor no insumo SICRO (e as DMTs, para materiais cotados). Fica no registro de alterações."""
    r = sv().binomio.aplicar_vencedor(projeto_id, binomio_id, aplicar_dmt, codigo_insumo)
    return dict(mensagens=r["mensagens"])


@mcp.tool()
def binomio_anexar(projeto_id: int, caminho_arquivo: str, binomio_id: int | None = None, tipo: str = "cotacao",
                   fornecedor: str | None = None) -> dict:
    """Anexa um documento (tipo cotacao | icms | anp | outro) a um binômio ou ao projeto."""
    import os
    return sv().binomio.anexar(projeto_id, caminho_arquivo, os.path.basename(caminho_arquivo), binomio_id, tipo, fornecedor)


@mcp.tool()
def binomio_exportar(projeto_id: int) -> dict:
    """Gera o Excel do binômio (BINOMIO_COTACOES, RESUMO_COTACOES, BINOMIO_ANP, índices e anexos) com fórmulas."""
    return sv().binomio.exportar(projeto_id)


@mcp.tool()
def indices_reajuste(nome: str | None = None) -> dict:
    """Índices de reajustamento cadastrados (todas as séries ou uma pelo nome)."""
    r = sv().binomio.indices()
    return {nome: r["series"].get(nome)} if nome else dict(nomes=r["nomes"], meses=r["meses"])


@mcp.tool()
def gravar_indice_reajuste(nome: str, mes: str, valor: float) -> str:
    """Grava o índice de um mês (AAAA-MM), ex.: Conservação Rodoviária 2026-07 = 485,2."""
    sv().binomio.gravar_indice(nome, mes, valor)
    return "ok"


# ------------------------------------------------------------------ transporte (croqui, VMD, FIT, quadro)
@mcp.tool()
def croqui_ler(projeto_id: int) -> dict:
    """Croqui do segmento: ocorrências (km, acessos), travessias urbanas, VMD por segmento e as rotas calculadas
    (LN, RP, P, Pr, Pu, DMT, VMDf, FIT)."""
    r = sv().transporte.croqui(projeto_id)
    return dict(dados=r["dados"], km_ini=r["km_ini"], km_fim=r["km_fim"], rotas=r["rotas"])


@mcp.tool()
def croqui_salvar(projeto_id: int, ocorrencias: list[dict] | None = None, travessias: list[dict] | None = None,
                  vmd: list[dict] | None = None, localidades: list[dict] | None = None, metodo: str | None = None) -> dict:
    """Grava o croqui. ocorrencias: [{nome, tipo (canteiro|pedreira|areal|usina|deposito|bota_fora|emprestimo|aterro|
    cidade|outro), km, lado 'E'|'D', acesso_ln, acesso_rp, acesso_p}] — sem km, use dist_ln/dist_rp/dist_p (distância
    fixa até a pista) ou meia_extensao=true. travessias: [{nome, km_ini, km_fim}]. vmd: [{snv, km_ini, km_fim, vmda,
    vmda_c, vmda_d, faixas_sentido, vmdf_c, vmdf_d}]. metodo: referencia | exato (parcela urbana). Campos omitidos são mantidos."""
    dados = {k: v for k, v in dict(ocorrencias=ocorrencias, travessias=travessias, vmd=vmd, localidades=localidades,
                                   metodo=metodo).items() if v is not None}
    r = sv().transporte.salvar_croqui(projeto_id, dados)
    return dict(rotas=r["rotas"])


@mcp.tool()
def importar_vmd_dnit(projeto_id: int, caminho_arquivo: str) -> dict:
    """Importa o VMDa da modelagem do DNIT (servicos.dnit.gov.br/dadospnct/Modelagem — .xlsx, .csv ou GeoJSON),
    casando pelo código SNV dos segmentos do projeto (ou pela BR e km)."""
    r = sv().transporte.importar_vmd(projeto_id, caminho_arquivo)
    return dict(casados=r["casados"], lidos=r["lidos"], vmd=r["dados"]["vmd"])


@mcp.tool()
def quadro_transportes(projeto_id: int, com_linhas: bool = False) -> dict:
    """Quadro de transportes: momentos (t·km) por composição de transporte e, se pedido, as linhas
    (serviço, material, fator, origem → destino, DMT, FIT, momento)."""
    r = sv().transporte.quadro(projeto_id)
    out = dict(totais=r["totais"], sem_quantidade=r["sem_quantidade"], materiais=r["materiais"])
    if com_linhas:
        out["linhas"] = [{k: ln.get(k) for k in ("servico", "material", "quantidade_anual", "fator", "origem", "destino",
                                                  "dmt", "fit", "momentos", "erro")} for ln in r["linhas"]]
    return out


@mcp.tool()
def gerar_quadro_transportes(projeto_id: int) -> dict:
    """Monta o quadro a partir dos transportes das composições dos serviços escolhidos (auxiliares expandidas)."""
    r = sv().transporte.gerar_quadro(projeto_id)
    return dict(totais=r["totais"], materiais=r["materiais"])


@mcp.tool()
def definir_origem_material(projeto_id: int, chave: str, origem: str | None, destino: str | None = "Pista") -> dict:
    """Origem/destino de um material do quadro (chave 'INSUMO|pista' ou 'INSUMO|usina'); origem vazia = CIF."""
    return dict(totais=sv().transporte.definir_origem(projeto_id, chave, origem, destino)["totais"])


@mcp.tool()
def definir_quantidade_servico(projeto_id: int, codigo: str, quantidade: float) -> dict:
    """Quantidade anual (12 meses) de um serviço do orçamento — base do quadro de transportes."""
    return sv().transporte.definir_quantidade(projeto_id, codigo, quantidade)


@mcp.tool()
def aplicar_momentos_ao_orcamento(projeto_id: int) -> dict:
    """Grava os momentos do quadro como quantidade dos serviços de transporte do orçamento."""
    return sv().transporte.aplicar_ao_orcamento(projeto_id)


@mcp.tool()
def importar_transportes_planilha(projeto_id: int, caminho_xlsx: str) -> dict:
    """Lê de uma planilha PATO as quantidades (aba PATO), o VMD (VMDf) e as linhas do quadro (TRANSPORTES_CONSERVA)."""
    return sv().transporte.importar_planilha(projeto_id, caminho_xlsx)


@mcp.tool()
def exportar_transportes(projeto_id: int) -> dict:
    """Gera o Excel com CROQUI, DMT, VMDf, FIT, TRANSPORTES_CONSERVA e resumo dos momentos (com fórmulas)."""
    return sv().transporte.exportar(projeto_id)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
