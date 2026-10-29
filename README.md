# PATO — Inventário georreferenciado e orçamento de conservação

Sistema local (painel web + servidor MCP) construído a partir da planilha
`PATO_BR_158_MT_KM_85_KM_212_REV2.xlsx`. **Fase 1 entregue: inventário georreferenciado.**

## O que faz

| Função | Onde |
|---|---|
| Importar inventário de qualquer segmento em Excel (modelo DNIT “Cadastro de …” ou abas `CAD_*` do PATO). As colunas são reconhecidas **pelo nome do cabeçalho**, então funcionam planilhas com colunas em outra posição. Prévia antes de gravar. | aba **Importar** |
| Painel com extensões, áreas, volumes; quadro igual à aba `RESUMO_INVENT`; **reflexo nas quantidades do PATO** (itens 01.02.01, 01.02.05.07, 01.02.06.x, 01.02.08.x, 01.03.06.01). | aba **Painel** |
| Tabela editável por categoria (21 categorias), filtro por km/texto, inclusão/exclusão; quantidades recalculadas na hora. | aba **Inventário** |
| Mapa (OpenStreetMap) com camadas por categoria; feições sem coordenada são posicionadas pelo km ao longo do eixo; clique para gravar coordenada de um item. | aba **Mapa** |
| Validação: item fora do trecho, km invertido, coordenada a > 2 km do eixo, SNV inexistente. | aba **Alertas** |
| Alterar trecho (km inicial/final) com opção de recortar o inventário; gerar aceiro a partir da cerca; dados da CAPA (rodovia, trecho, SNV, data-base, prazo). | aba **Projeto e trecho** |
| **Exportar a planilha PATO preenchida**: grava CAPA, CAD_SEG e todas as abas CAD_* numa cópia do modelo, **preservando fórmulas, croqui, composições e as 72 abas**. Se o segmento tiver mais itens que linhas, a tabela cresce e todos os totais/referências acompanham. O Excel recalcula ao abrir. | aba **Exportar** |
| Exportar inventário em Excel (uma aba por categoria + resumo), GeoJSON e KML (Google Earth). | aba **Exportar** |
| Servidor **MCP** para o Claude ler e preencher o inventário e qualquer planilha. | `pato_app/mcp_server.py` |

### Verificação do SNV e correção de pontos (aba Alertas)
- Confere o código SNV de cada item com o km (cadastro de segmentos ou **planilha oficial do SNV**, opcional) e
  detecta quando o inventário usa outra numeração/versão do SNV.
- Constrói o eixo da rodovia com todas as coordenadas (descartando as discrepantes) e classifica cada ponto:
  ≤ 1 km de divergência km × coordenada = aceitável (odômetro × GPS); 1–2 km = **verificar em campo**; > 2 km = erro.
- Corrige: erro de digitação (sinal, dígito, dígitos invertidos, lat/long trocadas), coordenada registrada na
  ponta errada ou copiada de outro ponto (quando o km é confirmado pela continuidade/extensão), SNV faltante ou
  incompleto, feições que ultrapassam o trecho (recorte) ou estão fora dele (remoção).
- Saídas: relatório (.xlsx) com links do Google Maps, planilha original com as células corrigidas **pintadas**,
  e os valores originais guardados em cada item.

### Nomenclatura conforme o Álbum de Projetos-Tipo de Drenagem (DNIT/IPR-736, 5ª ed.)
Na importação, os tipos de bueiro, meio-fio, sarjeta, descida d'água, entrada e valeta são conferidos com os códigos
do álbum (na forma usada pelo SICRO: `BSTC` Ø0,60–1,50, `BSCC` 1,50–3,00, `MFC 01–08`, `STC 125-25`, `DAR 60-30`,
`EDA 03 B`, `VPCC 120-30`…). Grafias fora do padrão são ajustadas (`MFC03` → `MFC 03`, `EDA-03B` → `EDA 03 B`) e o que
não dá para converter com segurança (ex.: `DAR01`, `EDA01` sem A/B) fica marcado para verificação.
Tudo vai para um **log** (aba Exportar → Log), junto com o vocabulário normalizado (lado, condição) e as correções.

### Fórmulas reproduzidas (conferidas contra a planilha original)
Pista: km de faixa = extensão × nº faixas; área = ext × 1000 × largura · Acostamento por revestimento (CA/TS) ·
Meio-fio/sarjeta: ext = (kmf − kmi) × 1000, caiação = ext × largura, capina = 0,2 × ext ·
OAC: tubular (BxTC) π·d²/4·L·n, celular (BxCC) d²·L·n · OAE: guarda-corpo = 2 × ext, caiação = 1,8 × guarda-corpo ·
Roçada: largura × ext × (2 se E/D) / 10 000 · Defensa: ext × (2 se E/D) · Aceiro: 1,5·ext; (largura até cerca − 4,5)·ext; 3·ext ·
Capina total = sarjeta + meio-fio + 1,5 × defensa · regras do PATO (ex.: meio-fio a recompor/2 × 8,5 %).

Teste de regressão: importar o inventário do próprio PATO, reexportar e recalcular devolve exatamente
**R$ 26.682.348,76** (sem desoneração) e **R$ 27.994.808,64** (com desoneração).

## Instalação (Windows)
1. Instale o Python 3.10+ (python.org, marque “Add to PATH”).
2. Copie a pasta `pato-app` para, por exemplo, `C:\PATO\pato-app`.
3. Dê dois cliques em `instalar.bat` (uma vez) e depois em `iniciar.bat`.
   O painel abre em http://127.0.0.1:8000.

Linux/macOS: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m pato_app`

Os dados ficam em `%USERPROFILE%\PATO_App` (banco `pato.db`, `exportacoes\`, `modelos\`).
Para mudar a pasta, defina a variável de ambiente `PATO_DADOS`.

O modelo padrão é a planilha BR-158/MT incluída em `pato_app/modelos/`. Para usar outro PATO como modelo,
escolha-o na aba **Exportar → Definir como modelo padrão**.

“Conferir totais” (aba Exportar) recalcula a planilha gerada com o LibreOffice, se estiver instalado.
Sem ele, basta abrir o arquivo no Excel — o recálculo é automático.

## Conectar ao Claude (MCP)
No Claude Desktop: *Configurações → Desenvolvedor → Editar configuração* e acrescente o bloco de
`claude_desktop_config.exemplo.json` (ajuste o caminho). Reinicie o Claude Desktop.

Ferramentas disponíveis: `listar_projetos`, `ler_projeto`, `criar_projeto`, `atualizar_projeto`, `alterar_trecho`,
`listar_inventario`, `adicionar_itens_inventario`, `atualizar_item`, `remover_itens`, `importar_planilha`,
`resumo_inventario`, `validar_inventario`, `gerar_aceiro`, `exportar_planilha_pato`, `exportar_inventario`,
`categorias_inventario`, `verificar_e_corrigir`, `log_padronizacao`, `exportar_original_corrigido`, e para qualquer .xlsx: `listar_abas`, `ler_celulas`, `escrever_celulas`
(grava preservando desenhos e fórmulas).

Exemplos de pedidos: *“importe C:\inventarios\BR-070.xlsx como novo projeto e me mostre os alertas”*,
*“acrescente um bueiro BSTC Ø1,00 m, 14 m, no km 132,4 lado direito”*, *“gere o PATO preenchido”*.

## Observações sobre a planilha modelo
- `RESUMO_INVENT!D20/G20`, `PATO!F59` e `CAD_PISTA!V` foram reescritas com SOMASE por revestimento para
  funcionarem com qualquer número de linhas de acostamento (antes apontavam para linhas fixas).
- As abas `IP`/`CALCULO_IP` (condição do pavimento km a km) **não** são alteradas pelo inventário; revise-as
  quando mudar de trecho.
- `BD` usa vínculos externos (`[1]onerado`, `[2]desonerado`); os valores em cache são mantidos.
- Categorias sem aba no modelo (sinalização vertical, tachas, marcas, inscrições, intervenção funcional)
  ficam no inventário exportado; a área gramada vai para `RESUMO_INVENT!B44`.

## Próximas fases (planejadas)
2. **Insumos e composições** — importar SICRO/EQ/MO/MAT e as 132 CPUs; alterar preço de insumo e ver o efeito;
   tempo fixo: alterar, trocar veículo transportador ou retirar.
3. **Transporte, FIT e croqui** — DMT por origem/destino, FIT = 1 + ((70 + 0,0035·VMDf) + 60·DMTu)/(DMTp·60),
   croqui de ocorrências desenhado e quadro de transportes.
4. **Data-base e PATO completo** — trocar data-base (SICRO, ANP, índices), BDI, curva ABC, cronograma, PDF;
   plano de trabalho conforme Resolução DNIT nº 9/2023 e Manual de Conservação (IPR-710).

## Testes
`python -m pytest -q` (o teste de recálculo com LibreOffice é pulado se ele não estiver instalado).
