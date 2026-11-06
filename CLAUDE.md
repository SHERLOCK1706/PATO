# PATO — orçamento de conservação rodoviária (Res. DNIT nº 8/2023)

Sistema local (FastAPI + SQLite + JS puro) que monta o Plano Anual de Trabalho e Orçamento: inventário
georreferenciado, custos SICRO/BDI, transporte (croqui, DMT, FIT), planilha PATO, ficha de serviços, ADM/mobilização,
e exporta o Excel do orçamento e a **planilha de licitação no modelo da referência BR-158/MT** (72 abas).

## Regras do projeto
- **Responder ao usuário em português (BR)**, sem jargão de programação; o usuário é engenheiro orçamentista.
- **Commits**: `git -c user.name="Matheus" -c user.email="matheusfp.eng@gmail.com" commit ...` e `git push -u origin main`.
  Commitar e enviar ao final de cada entrega.
- **Nunca versionar as planilhas, PDFs e zips enviados pelo usuário** (BR-174, BR-158 REV2, PATOs aprovados…): são
  particulares e o repositório é público. Só há binários versionados em `pato_app/modelos/`, `tests/dados/` e
  `docs/referencias/` (o hook `.claude/hooks/bloquear_planilhas.py` barra o resto). Scripts e saídas de teste vão para
  o scratchpad, não para o repositório.
- O app roda **local** (`python -m pato_app` → http://localhost:8000). Não adicionar serviços externos obrigatórios.

## Regras de negócio que já causaram erro
- **A aba PATO é o orçamento de 1 ano** (quantitativos para 12 meses). QUANTIDADES, curva ABC e cronograma são do
  **contrato**: PATO × anos de vigência (`CAPA!D81`, em anos). Canteiro, usina, MOB e DESMOB valem 1 ÷ anos no PATO e
  1 no contrato (`pato_orcamento.contrato`).
- Prazo do projeto: meses se > 6, senão anos (`orcamento_servico.anos_contrato`).
- Quantidade = TRUNC|ROUND(base × NE; 3); parcial = TRUNC(quantidade × preço; 2) — igual à planilha.
- Valores vêm do banco de dados do projeto (base SICRO, binômio, índices), nunca dos números da referência.
- Equipamentos da mobilização = os das CPU dos serviços adotados (`aplicar_mob_pelos_servicos`).
- Projeto-tipo de sinalização: conserva, modelo BR-158 v2.

## Mapa do código (`pato_app/`)
- `orcamento_servico.py` — planilha PATO: calcular, editar, ficha (montar, `ficha_planilha`, edição de linhas), resumo.
- `pato_orcamento.py` — motor de quantidades e preços (`Calculo`), curva ABC, cronograma, contrato.
- `ficha.py` + `modelos/ficha_servicos.json` — ficha de serviços (cópia do usuário em `<dados>/modelos/`).
- `licitacao.py` (exportar → memórias → alinhar → conferir → varredura) e `memorias.py` (escritores das abas).
- `xlsx_patch.py` — editor de xlsx no nível do XML (preserva fórmulas). `exportador.py` — CAPA/CAD_*.
- `api.py` (rotas), `mcp_server.py` (ferramentas MCP), `static/` (index.html, app.js, style.css).

## Testes
- Rápidos (< 1 min): `tests/test_ficha_planilha.py`, `tests/test_planilha_ficha.py`, `tests/test_ip.py`.
- Médios (~3–5 min): `tests/test_orcamento.py`, `tests/test_pato.py`, `tests/test_ficha.py`.
- Lentos (~10 min, LibreOffice): `tests/test_licitacao.py` — rode em segundo plano.
- Conferência completa da exportação: `/conferir-licitacao`.
- Tela: subir o app com um projeto carregado e conferir com Playwright (Chromium já instalado no ambiente remoto).
