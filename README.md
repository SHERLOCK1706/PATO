# PATO — Inventário georreferenciado e orçamento de conservação

Sistema local (painel web + servidor MCP) construído a partir da planilha
`PATO_BR_158_MT_KM_85_KM_212_REV2.xlsx`. **Fases 1 (inventário georreferenciado), 2 (custos: SICRO, BDI, composições e binômio), 3 (croqui, VMD, FIT e transportes) e a Planilha PATO (Res. DNIT nº 8/2023) entregues.**

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

## Custos (aba Custos) — Fase 2
As composições do PATO de exemplo são só exemplos: o orçamento usa as composições que você escolher na base SICRO
do estado e da data-base (MT ou outro estado; nova base a cada trimestre).

| Subaba | O que faz |
|---|---|
| **Base e BDI** | Importa os relatórios do SICRO (.xlsx soltos ou o .zip do DNIT); escolhe base, regime (com/sem desoneração) e BDI. Calculadora de BDI pelo método DNIT: SELIC → despesas financeiras, CPRB do ano (Lei 14.973/2024) e **ISSQN pelos municípios** (alíquota × base de cálculo × peso, limitado a 5%). |
| **Serviços e composições** | Busca e escolhe serviços; mostra a composição analítica (equipamentos, mão de obra, materiais, auxiliares, tempo fixo, transporte) com preço original × atual. Troca material (ex.: brita 0 → brita 1), equipamento, mão de obra ou auxiliar; tempo fixo: alterar, trocar veículo (o transporte acompanha) ou retirar; DMT. |
| **Composições próprias** | Cria, copia e edita composições (preços novos). Exemplo pronto: caminhão de 28 m³ (PN01–PN04, 1ª ATF nº 32 – FGV/2024 CGCIT), igual ao PATO. |
| **Insumos** | Altera preços de insumos; vale para todas as composições que os usam. |
| **Binômio** | Ver abaixo. |
| **Alterações** | Registro de tudo que foi alterado, com desfazer/reativar. |
| **Trocar data-base** | Compara os preços entre bases e passa o projeto para a nova data-base mantendo as alterações. |

O motor reproduz as 132 composições do PATO nos dois regimes (uma única diferença de R$ 0,01 em 6416037 CD,
arredondamento da planilha).

### Binômio aquisição + transporte
- **Materiais cotados** (pétreos, madeira, capa asfáltica comercial, outros): cotações de cada fornecedor (R$/t ou R$/m³,
  densidade, mês, DMT pavimentada/não pavimentada) + linha de referência do SICRO. Preço reajustado =
  TRUNC(preço × índice da data-base ÷ índice do mês da cotação, 2) (Conservação Rodoviária); total = preço + DMT × custo t·km;
  vence o menor.
- **Betuminosos (ANP)**: origens com preço ANP, ICMS, distâncias fluvial/pavimentada/RP/LN, pedágio e balsa; transporte pelas
  Portarias DNIT 1977/2017 e 434/2017 com Kr/Kf (índice Pavimentação); ICMS e PIS/COFINS por dentro; BDI do projeto na aquisição
  e 15% no transporte. Resultados iguais à aba BINOMIO_ANP (ex.: CAP 50/70 Cuiabá R$ 6.736,57/t).
- **Anexos**: cotações dos fornecedores, documento do ICMS, tabela ANP (PDF, e-mail, planilha…), baixáveis no sistema.
- **Aplicar vencedor ao insumo**: grava o preço vencedor (e as DMTs) no insumo SICRO; entra em Alterações.
- **Importar de planilha PATO** (BINOMIO_COTACOES, BINOMIO_ANP, INDICES_REAJ) e **Exportar binômio** no modelo da planilha de
  referência (BINOMIO_COTACOES, RESUMO_COTACOES, BINOMIO_ANP com fórmulas, índices usados e lista de anexos).
- **Índices de reajuste**: consulta, digitação mensal ou importação da aba de índices.

Os anexos ficam em `%USERPROFILE%\PATO_App\anexos\`.

## Transporte (aba Transporte) — Fase 3
| Subaba | O que faz |
|---|---|
| **Croqui** | Desenhado pelo sistema a partir do segmento do projeto. Você informa o km do canteiro/centro sede, pedreira, areal, usina e demais ocorrências (lado, acessos LN/RP/P), as travessias urbanas e localidades de referência. Ocorrências sem km (bota-fora, empréstimo, aterro) usam distância fixa até a pista (ou ½ extensão). Botão para baixar o desenho (SVG). |
| **VMD** | VMD por segmento SNV. Importa o arquivo da **modelagem do VMDa do DNIT** (servicos.dnit.gov.br/dadospnct/Modelagem — .xlsx, .csv ou GeoJSON), casando pelo código SNV (ou BR e km). VMDf = VMDa do sentido ÷ faixas por sentido; também pode ser digitado. |
| **DMT e FIT** | Para cada rota: LN, RP, P, Pr, Pu, DMT, sentido, VMDf, A1, A2 e FIT. Qualquer rota pode receber distâncias medidas (“Informar”). |
| **Quadro de transportes** | Gerado das composições dos serviços escolhidos (transportes das auxiliares expandidos, fatores multiplicados), com a quantidade anual de cada serviço. Origem/destino por material (sugestão automática; vazio = CIF). Momento = TRUNC(quant. × fator × DMT × FIT; 3), separado por composição de transporte e por superfície. **Aplicar ao orçamento** grava os momentos como quantidade dos serviços de transporte. |

**DMT** média até a pista = ((x − a)² + (b − x)²) / (2·(b − a)); parcela urbana pelo método da planilha de referência
(travessia que contém a ocorrência = média interna; demais = metade da extensão) ou exata (opção).
**FIT — Manual de Custos, Volume 05 (2ª ed., 2025)**: A1 = 70 + 0,0035·VMDf (só com operação PARE e SIGA prevista no orçamento,
serviço 5213850); A2 = Fc·DMTu, Fc = (1/Vu − 1/60)·3.600 = 60 s/km a 30 km/h (velocidade urbana ajustável); FIT = 1 + (A1 + A2)/(60·DMTp);
DMTF = FIT × DMTp, só no transporte de insumos em vias pavimentadas, DMTp ≤ 100 km, sem FIT no tempo fixo.
Detalhes e o manual em `docs/referencias/sicro/`. O VMDf da viagem é a média ponderada pela extensão dos
segmentos percorridos no sentido da viagem.

Conferência com a planilha BR-158/MT: DMT, VMDf (1476, 1174, 1392) e FIT (1,1306; 1,2297; 1,0904) idênticos; momentos
PN03 567.788,895, 5914479 299,214 e 5915014 3.309,30 idênticos. Diferenças da planilha, mantidas de propósito:
- Areal/Usina → Pista: a planilha considera só a travessia de Confresa (Pu 2,05); o sistema também a de Porto Alegre do Norte
  (Pu 3,80). Para reproduzir a planilha, informe a rota.
- 5914464 (carroceria 15 t em revestimento primário): a planilha usa a distância pavimentada (63,75 km); o sistema usa a de RP (10 km).
- 4915623A (brita 4): a planilha usa FIT 1,0917 só nessa linha (sem A1); o sistema usa o FIT da rota (1,1306).

Importar de planilha PATO traz as quantidades (aba PATO), o VMD (VMDf) e as linhas do quadro (TRANSPORTES_CONSERVA).
Exportar gera CROQUI (desenho em células), DMT, VMDf, FIT (com fórmulas), TRANSPORTES_CONSERVA (momentos com fórmulas) e
RESUMO_TRANSPORTES. Na aba Custos → Serviços, a coluna “Quant. anual” guarda a quantidade de cada serviço.

## Planilha PATO (aba PATO) — Resolução DNIT nº 8/2023
- **Importar planilha PATO**: lê as abas PATO (itens, níveis de esforço e memórias de cálculo), DESEMPENHO e BD (preços de
  administração local, canteiro, instalação industrial, mobilização) e liga as quantidades ao inventário do projeto.
- Quantidade = TRUNC|ARRED(base × nível de esforço; 3). A base pode ser medida do inventário (vínculo vivo), outro item
  (ex.: usinagem = tapa-buraco × 2,4 t/m³; betuminoso = usinagem × teor), momento do quadro de transportes, valor informado ou
  quantidade direta (levantamento IP). Cada item é editável.
- Preços nos dois regimes: composições SICRO/próprias (com as alterações do projeto), lista sintética, betuminosos AM/TM pelo
  binômio ANP, grupo por desempenho (GD — parcela mensal, art. 42) e preços informados. Parcial = TRUNC(quantidade × preço; 2).
- **Levantamento IP** (aba PATO → Levantamento IP): condição do pavimento km a km por faixa (panela, remendo, trincamento —
  Bom/Regular/Ruim/Péssimo), ICP = 50·panela + 30·remendo + 20·trincamento e condição; intervenção primária e secundária
  sugeridas pelo padrão da BR-158/MT (a escolha final é do engenheiro, km a km). Memória de cálculo (CALCULO_IP): kmf com cada
  intervenção × nível de esforço (Manual de Conservação ou % da faixa × espessura), e o PATO adota o maior entre o calculado
  e o histórico de consumo (Res. 8/2023, art. 17). Tapa-buraco, reparo, remendo, correção, fresagens, microrrevestimento e a
  sinalização para abertura passam a vir do levantamento. Importa da aba IP (modelo atual) ou ICP (modelos antigos:
  Alta/Média/Baixa, nível de serventia, intervalos de linhas), conferido com BR-158, BR-364/405/435 e BR-174/MT.
- **Regras do PATO base** reconhecidas na importação e recalculadas para qualquer segmento:
  produção da equipe (da composição da base) × 8 h × dias; fator × extensão do segmento; rateio por ano de contrato
  (canteiro, instalação industrial, mobilização: 1 ÷ anos).
- **Sinalização de obras (Anexo XIII)** — sub-aba própria: horas de cada serviço = quantidade no PATO ÷ produção horária;
  por projeto-tipo (1 fixo no acostamento, 3 fixo na pista com PARE e SIGA, 16 móvel no acostamento, 17 móvel na pista)
  dias = horas ÷ 7,333 e bandeirola = horas × operadores; dispositivos (un.dia) = ARRED(quantidade × dias), por código SICRO.
  Alimenta os itens 01.06 e as linhas de sinalização do grupo por desempenho.
- **NE da roçada (DNIT 182/2018)** — na sub-aba Desempenho: NERp = Σ(NERe/d)/Σ(1/d) das estações pluviométricas, NE adotado
  (ou informado pela observação de campo) como frequência anual da capina e das roçadas do GD.
- **Ficha de serviços** (sub-aba própria) — monta o PATO de um segmento novo sem a planilha PATO: marque os serviços,
  ajuste o nível de esforço (nos serviços do ICM/IP, o NE ou % da faixa da intervenção) e informe as poucas quantidades sem
  regra. A ficha guarda as regras do PATO de referência (BR-158/MT) sem os números do segmento: inventário, produção ×
  8 h × dias, extensão, prazo, ICM/IP (maior entre calculado e histórico — art. 17), sinalização de obras, NE da roçada,
  ADM/mobilização e o **quadro de transportes locais do modelo** (pétreos, solo, jazida, mistura betuminosa, material
  demolido). Itens que dependem de um serviço desmarcado (AM/TM, transportes) saem junto. "Gravar este PATO como ficha"
  transforma qualquer PATO importado na ficha dos próximos projetos.
- **Croqui montado pelo sistema** (aba Transporte → "Montar croqui", Res. 8/2023): informe o km do canteiro (e da usina,
  se for outro). A origem de cada material sai do binômio: SICRO mais vantajoso → centro sede (na DMT do SICRO a partir do
  canteiro, em direção à cidade mais próxima); cotação mais vantajosa → o fornecedor, com a DMT da cotação. Jazida,
  bota-fora do material demolido, depósito e aterro sanitário usam as distâncias do modelo quando não informados. As linhas
  do quadro de transportes passam a sair da origem vencedora.

  **Teste de ponta a ponta** (`tests/test_ficha.py`): projeto novo só com inventário, cotações/binômio ANP com ICMS,
  levantamento ICM, trecho (travessias e VMD) e km do canteiro 124,5 + todos os serviços da ficha → croqui igual ao do
  modelo e PATO igual ao da planilha importada (R$ 26.715.472,25 / 27.267.278,71). Diferenças para a planilha licitada:
  só as correções documentadas (transportes 5915321/5914464 da Fase 3, BDI dos betuminosos com desoneração e usina).
- **ADM local e mobilização** (sub-aba própria, itens 01.07 — SICRO Vol. 07, 08 e 09): administração local (parcelas fixa,
  vinculada e variável com MO mensalista e veículos da base, equipes de laboratório ELA = Σ quantidade no contrato ÷ QE,
  manutenção do canteiro, despesas diversas), canteiro (áreas por NPF/NMAX/NMO, FEAC, k1·k2·k3, CMCC), instalação
  industrial (laboratório + composição 903810) e mobilização/desmobilização (passagem reajustada pelo índice, tempo de
  viagem e descanso, veículo transportador e FU da tabela IMOB). Recalcula com o prazo, o BDI e a base do projeto; a
  opção "fixar" mantém o preço da planilha de origem. Na BR-158/MT reproduz ADM, CAN, MOB e DESMOB ao centavo; a usina
  com desoneração é corrigida (a planilha somava a instalação sem desoneração em USINA!H38: R$ 503.838,39 → 498.500,50).
- **Resumo e % dos grupos (Anexo XX)** com verificação do limite de 25% de DSM (art. 6º, III), **Curva ABC (Anexo XXI)**,
  **cronograma físico-financeiro** de 12 meses e detalhamento do **grupo por desempenho**.
- **Exportar (Excel)**: planilha PATO (Anexo XIX), % dos grupos, curva ABC, cronograma e desempenho, com fórmulas.
- **Exportar PATO de licitação**: o PATO final no modelo da planilha que vai para licitação (as 70 abas da BR-158/MT, com
  croqui, CPU, binômios, inventário e memórias), preenchido pelo sistema:
  - projeto e inventário nas abas CAPA e CAD_*;
  - preços das composições no BD no lugar dos vínculos externos `[1]onerado`/`[2]desonerado` (o arquivo fica autocontido);
  - base SICRO do projeto nas abas MO/EQ (com e sem desoneração);
  - níveis de esforço, quantidades informadas e momentos de transporte do sistema (células alteradas em destaque);
  - correções: betuminosos com desoneração (BDI em % sem ÷100), usina com desoneração (USINA!H38) e retirada das
    conferências auxiliares do BD que só exibiam #N/A e das células com #REF!.

  A planilha é recalculada no LibreOffice e o total é conferido com o do sistema. Onde a memória do modelo (inventário,
  levantamento IP, quadros) dá quantidade ou preço diferente do sistema — típico de um segmento novo —, a linha do PATO
  recebe o valor do sistema (em destaque, listada no log) e a planilha é recalculada de novo. Na BR-158/MT a diferença é
  zero nos dois regimes e não sobra nenhuma célula com erro. Itens incluídos no sistema que não existem no modelo aparecem
  como pendência.

Conferência com a planilha BR-158/MT: todas as quantidades e preços batem (GD R$ 148.968,45 / 148.228,95/mês), exceto:
- transportes 5915321 e 5914464 — as diferenças da planilha documentadas na Fase 3;
- **aquisição de betuminosos com desoneração (AM)**: a planilha calcula `AM_SD/(1+BDI!E25)*(1+BDI!E44)` com os BDI em % sem
  dividir por 100 (35,12 e 39,32), o que infla esses preços em ~8,3% (ex.: CAP R$ 6.564,02 em vez de R$ 6.062,43). O sistema
  aplica o BDI com desoneração corretamente;
- transporte de betuminosos com desoneração (TM): BDI de transporte 18,67% (parâmetro do binômio), diferença de R$ 0,01 por
  arredondamento.

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
`dispensar_sugestao`, `desfazer_sugestao`, `relatorio_pontos_a_corrigir`, `exportar_original_corrigido`;
custos: `custos_configuracao`, `custos_configurar`, `calcular_bdi`, `buscar_composicoes`, `servicos_do_orcamento`, `adicionar_servico`,
`ver_composicao`, `alterar_preco_insumo`, `trocar_insumo`, `alterar_tempo_fixo`, `alterar_dmt`, `listar_alteracoes_custo`,
`desfazer_alteracao_custo`, `exportar_composicoes`; binômio: `binomio_listar`, `binomio_salvar_material`, `binomio_salvar_betuminoso`,
`binomio_importar_planilha`, `binomio_aplicar_vencedor`, `binomio_anexar`, `binomio_exportar`, `indices_reajuste`,
`gravar_indice_reajuste`; transporte: `croqui_ler`, `croqui_salvar`, `importar_vmd_dnit`, `quadro_transportes`,
`gerar_quadro_transportes`, `definir_origem_material`, `definir_quantidade_servico`, `aplicar_momentos_ao_orcamento`,
`importar_transportes_planilha`, `exportar_transportes`; PATO: `pato_importar_planilha`, `pato_orcamento`, `pato_editar_item`,
`pato_medidas`, `pato_resumo`, `pato_exportar`; levantamento IP: `ip_levantamento`, `ip_importar_planilha`, `ip_lancar_km`; e para qualquer .xlsx: `listar_abas`, `ler_celulas`, `escrever_celulas`
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
4. **PATO final no modelo da planilha de licitação** — exportar a planilha completa (72 abas) preenchida pelo sistema, com as
   correções; calculadoras de administração local, canteiro e mobilização (Manual de Custos, Vol. 06–08); PDF;
   plano de trabalho conforme a Resolução DNIT nº 8/2023 (elaboração do PATO e execução, medição, fiscalização,
   prorrogação e reajuste dos contratos; revogou as Resoluções nº 8/2022 e nº 4/2023) e o Manual de Conservação (IPR-710).

## Testes
`python -m pytest -q` (o teste de recálculo com LibreOffice é pulado se ele não estiver instalado).
