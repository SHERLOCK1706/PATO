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

### Correções automáticas (aba Ajustes) e decisões (aba Revisão)
Ao importar (ou em “Analisar novamente”), o sistema verifica SNV, coordenadas × km, limite do trecho e nomenclatura.
O registro (log) fica somente no sistema — nenhuma planilha recebe marcações ou abas extras.

**Aplicado automaticamente — aba Ajustes** (com valor anterior, novo e motivo; qualquer ajuste pode ser desfeito):
- **Coordenadas pelo km informado** (o km prevalece): pontos e pontas de feições a mais de 1 km (tolerância ajustável)
  da posição do km são reposicionados no eixo da rodovia; erros de digitação (sinal, dígito, dígitos invertidos,
  lat/long trocadas) são corrigidos mantendo a precisão original; itens sem coordenada recebem a posição pelo km.
- **Trecho**: recorte no limite e retirada de feições fora do segmento.
- **SNV**: códigos incompletos/faltantes e itens que atravessam segmentos (quando o cadastro de segmentos é coerente).
- **Nomenclatura × Álbum DNIT (IPR-736, 5ª ed.)**: grafias fora do padrão (`MFC03` → `MFC 03`, `EDA-03B` → `EDA 03 B`).

**Decisões pendentes — aba Revisão**, já com a sugestão mais provável preenchida:
- códigos antigos/incompletos: correspondência pela numeração quando o inventário usa vários (`DAR01` → `DAR 40-20`,
  `DAR02` → `DAR 60-30`), senão o tipo mais usual na rodovia, na base de projetos ou na planilha de referência
  (ex.: variante B das entradas `EDA`); entrada registrada com código de descida → a entrada que acompanha essa
  descida na mesma rodovia; dimensão fora do álbum → a padronizada mais próxima;
- SNV quando o inventário usa outra numeração que o cadastro de segmentos.
Para cada uma: **Aplicar sugestão** (item ou grupo), editar o valor, trocar a alternativa ou **Dispensar**.
Os botões têm balões de ajuda ao passar o mouse.

### Relatório de pontos a corrigir (aba Exportar)
Para enviar à empresa que levantou o inventário: planilha com o resumo (rodovia, segmento, destinatário, responsável,
observações, situação do SNV, totais) e a lista de cada ocorrência pela **aba e linha da planilha entregue**, com o
problema, a correção (aplicada ou sugerida), a ação esperada (*Corrigir na planilha*, *Confirmar a sugestão*,
*Verificar em campo*, *Retirar da planilha*), links do mapa e uma coluna “Resposta da empresa” para devolução.
Escolha o que incluir: pendentes, corrigidos automaticamente, corrigidos pela fiscalização, dispensados.

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
`categorias_inventario`, `analisar_inventario` (aplica o certo, lista o resto), `listar_sugestoes` (Revisão/Ajustes), `aplicar_sugestao`, `aplicar_sugestoes_em_lote`,
`dispensar_sugestao`, `desfazer_sugestao`, `relatorio_pontos_a_corrigir`, `exportar_original_corrigido`, e para qualquer .xlsx: `listar_abas`, `ler_celulas`, `escrever_celulas`
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
