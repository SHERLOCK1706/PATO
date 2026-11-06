# PATO — Inventário georreferenciado e orçamento de conservação

Sistema local (painel web + servidor MCP) construído a partir da planilha
`PATO_BR_158_MT_KM_85_KM_212_REV2.xlsx`. **Fases 1 (inventário georreferenciado), 2 (custos: SICRO, BDI, composições e binômio), 3 (croqui, VMD, FIT e transportes) e a Planilha PATO (Res. DNIT nº 8/2023) entregues.**

## O que faz

**Navegação por etapas** (menu lateral, recolhível com «): Painel · Assistente · **Pendências**, e as etapas
1 · Dados do trecho (Projeto, Inventário, Mapa, Importar; Alertas, Revisão e Histórico de ajustes) →
2 · Custos e transporte → 3 · Orçamento (Planilha PATO, IP, Sinalização, ADM e mobilização, Desempenho) →
4 · Entrega (Conferência, Resumo, Curva ABC, Cronograma, Exportar). Cada etapa mostra ✅/⚠️/❌ pelo Assistente.

- **Barra de totais fixa no topo de todas as telas**: SD, CD, regime mais vantajoso, nº de serviços, base, BDI (com atalho
  para ajustar) e pendências; atualiza sozinha depois de cada alteração (o valor que mudou pisca).
- **Pendências** junta num lugar só o que pede ação: serviços sem preço, valores substitutos, falhas e atenções da
  conferência, decisões do inventário, alertas de erro e etapas não concluídas — cada uma com o botão para ir ao lugar
  (os itens da planilha vão direto à linha).
- Telas mais enxutas: um botão principal por tela e o resto em "⋯ Mais"; as exportações do orçamento também ficam em
  Entrega → Exportar; explicações longas ficam recolhidas em "ⓘ Como funciona"; em celular a barra mostra só SD/CD e
  pendências.

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
Sequência da planilha de referência (BR-158/MT): **① cotações → ② binômio → ③ resumo do mais vantajoso → ④ conferência →
⑤ preço adotado na composição.**
- **📄 Anexar cotações (PDF) — uma ou várias de uma vez, leitura automática**: escolha os PDFs (ou fotos) das propostas; cada uma vira um cartão editável, os campos que faltam ficam em amarelo para preencher, e **Gravar todas no binômio** grava as completas (as incompletas ficam pendentes, dizendo o que falta). O sistema lê o texto do PDF ou faz
  OCR (Tesseract, português) se for digitalizado e pré-preenche fornecedor (reconhecido pelo cadastro, pelo KMZ ou pelo nome do
  arquivo — nunca o destinatário do orçamento), CNPJ do fornecedor, mês, itens (preço unitário, unidade — inclusive “Mº” lido
  como m³), frete CIF/FOB, local e rodovia/km do endereço. A DMT vem da proposta ou, se não houver, da distância em linha reta
  do fornecedor (KMZ/endereço) ao canteiro, sinalizada como estimativa. **Tudo fica editável** (material do binômio, preço,
  unidade, densidade, DMT pavimentada e não pavimentada) antes de gravar; a cotação é acrescentada ao material (substitui a do
  mesmo fornecedor) e o PDF fica anexado. CIF ⇒ DMT 0 (IN DNIT 10/2024, art. 10, § 2º).
- **Fornecedores e localização (KMZ)**: importa a planilha de fornecedores (FORNECEDOR, ENDEREÇO, INSUMO; opcionais CNPJ e
  CONTATO) e os pontos de um KMZ/KML. Cada fornecedor é localizado pelo ponto do KMZ ou pelo endereço “BR-xxx, km yyy” no SNV
  202610A: rodovia mais próxima, km na rodovia do projeto, distância ao eixo e ao canteiro (linha reta — conferir a rota).
- **Resumo e conferência**: tabela com o mais vantajoso de cada material, total, SICRO, preço a adotar, DMT e avisos (menos de 3
  cotações, PDF não anexado, m³ sem densidade, sem código SICRO). Marque “conferido” e use **Adotar nas composições os
  conferidos**; se a cotação mudar depois, a conferência deixa de valer.
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
- **Planilha PATO editável (estilo planilha)**: colunas Item · Cód. · Descrição completa · Unid. · Qtde. (inventário/base,
  🔗 = ligada à regra do modelo) · NE · Qtde. de trabalho · preço unitário e final SD/CD. Digite o código na **linha em branco**
  (ou no ＋ de qualquer linha) e tecle Enter: a linha se preenche; **cole vários códigos** do Excel (código, quantidade e NE
  opcionais); edite item, código, descrição, unidade, Qtde. e NE direto na célula (Qtde. digitada desliga a ligação; 🔗? religa);
  **filtro por coluna**.
- **Incluir serviço pelo código** (Planilha PATO): digite o código SICRO/próprio → descrição, unidade, preço unitário SD/CD e
  as origens da quantidade **pela planilha modelo** (inventário — ex.: meio-fio `(CAD_MFC!X21+Y21)/2×8,5%`; levantamento IP;
  momento do **quadro de transportes**; quantidade de outro item — usinagem, AM/TM; produção; ou valor informado), cada uma já
  calculada com os dados do projeto; NE editável com recálculo (quantidade = base × NE; preço final = TRUNC(qtd × preço; 2)).
  O NE também é editável direto na tabela.
- **BDI no cabeçalho** (SD/CD) com o botão **conferir/ajustar**, que abre Custos → **Data-base e BDI** (parcelas, SELIC, CPRB, ISSQN).
- **Importar lista de serviços** (Ficha): .xlsx/.csv/.txt com os códigos (colunas opcionais NE e quantidade). Marca os serviços da
  ficha; códigos fora da ficha entram em “01.08 Serviços incluídos pela lista”.
- **Croqui → Importar pontos (KMZ/KML)**: pedreiras, areais, usina, jazidas localizados no eixo do SNV (km e distância); se o
  ponto está junto a outra BR, isso é indicado. Ao montar o croqui, o fornecedor vencedor usa a posição do KMZ.
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
  (ou informado pela observação de campo) como frequência anual da capina e das roçadas do GD. "Buscar estações mais
  próximas" usa as 82 estações do Anexo A da norma (arquivo Est-Pluv_NERP do IPR, em `docs/referencias/dnit/`): pega as 2 a 5
  mais próximas do ponto médio do segmento (pelo eixo do inventário), de qualquer UF, com a distância geodésica (régua do
  Google Earth). Na BR-158/MT encontra as mesmas 5 estações da planilha (NERp 5,10 → NE 6); no exemplo da norma
  (BR-381/MG), NERp 3,7 → 4. Ao montar o PATO pela ficha, o NE é calculado assim automaticamente.
- **Planilha PATO e ficha de serviços unificadas** (aba PATO → Planilha PATO) — a ficha fica no painel recolhível do
  topo (aberto quando a planilha está vazia) e a planilha é editada como no Excel:
  - "mostrar os serviços da ficha que não estão na planilha" mostra, em cinza e no lugar pela numeração, os serviços da
    ficha que faltam; **＋ incluir** (ou marcar vários e "incluir os marcados") põe o serviço na planilha já com a regra
    da quantidade (inventário, ICM/IP, outro item, transporte), sem refazer o resto; o serviço de referência de um
    AM/TM entra junto se faltar.
  - **Quantidade puxada de outra linha**: na célula Qtde. digite `=01.03.02` (quantidade da linha 01.03.02),
    `=01.03.02*0,055` (× fator), `=01.03.02/1000` ou `=base(01.03.02)` (base antes do NE) — ou use ⤴ para escolher a
    linha numa lista, com prévia do resultado. Ex.: a usinagem, a aquisição e o transporte do CAP a partir do concreto
    asfáltico. A linha de origem mostra "↳ alimenta …"; referência circular não trava o cálculo (vale 0, com aviso).
  - MCP: `pato_incluir_da_ficha` e `pato_puxar_de_outra_linha`.
  - **Como no Excel**: colunas Item e Código fixas ao rolar para o lado; ↑ ↓ e Enter andam na coluna (Shift+Enter
    sobe), Esc desfaz, e o cursor continua no lugar depois do recálculo; grupos (títulos) recolhem com ▸/▾ e mostram o
    subtotal SD/CD ("recolher grupos" deixa só os subtotais — lembrado por projeto); selo da origem da quantidade (INV,
    IP, TR, = outra linha, PRD, km, ano, SZ, ADM; ✎ digitado, clique para religar) e ↳n nas linhas que alimentam outras;
    botões da linha aparecem ao passar o mouse; linhas compactas ou confortáveis (⇕, vale para todas as tabelas).
- **Ficha de serviços** (painel da Planilha PATO) — monta o PATO de um segmento novo sem a planilha PATO: marque os serviços,
  ajuste o nível de esforço (nos serviços do ICM/IP, o NE ou % da faixa da intervenção) e informe as poucas quantidades sem
  regra. A ficha guarda as regras do PATO de referência (BR-158/MT) sem os números do segmento: inventário, produção ×
  8 h × dias, extensão, prazo, ICM/IP (maior entre calculado e histórico — art. 17), sinalização de obras, NE da roçada,
  ADM/mobilização e o **quadro de transportes locais do modelo** (pétreos, solo, jazida, mistura betuminosa, material
  demolido). Itens que dependem de um serviço desmarcado (AM/TM, transportes) saem junto. "Gravar este PATO como ficha"
  transforma qualquer PATO importado na ficha dos próximos projetos.
- **Ficha no formato da aba PATO** (quantitativos para 12 meses): Item, Código, Discriminação, Inventário (quant./und),
  Nível de esforço (quant./und por und), Quantidade de trabalho e preço unitário/parcial sem e com desoneração, com os
  dados **deste** projeto, títulos com subtotal e subtotal amarelo de cada serviço com os seus AM/TM. Tudo editável na
  célula: digite o código e a descrição, a unidade e o preço vêm da base (e continuam editáveis); NE, quantidade a
  informar e preço informado (fundo amarelo; vermelho = digitado em outra data-base; apagar volta ao preço da base).
  ＋ abre linha nova pelo código; × remove (com as linhas que puxam a quantidade dela). **As edições valem só para o
  projeto aberto**; "Tornar padrão" leva a ficha aos próximos projetos (sem os preços informados) e "Descartar
  edições" volta à ficha padrão. "Montar PATO pela ficha" leva ao PATO os serviços marcados.
- **Prazo do contrato em meses** (24 = 2 anos). Valores até 5 são lidos como anos (projetos e planilhas antigas).
- Rodar o painel na rede (`--host 0.0.0.0`) liga o login automaticamente.
- **Croqui montado pelo sistema** (aba Transporte → "Montar croqui", Res. 8/2023): informe o km do canteiro (e da usina,
  se for outro). A origem de cada material sai do binômio: SICRO mais vantajoso → centro sede (na DMT do SICRO a partir do
  canteiro, em direção à cidade mais próxima); cotação mais vantajosa → o fornecedor, com a DMT da cotação. Jazida,
  bota-fora do material demolido, depósito e aterro sanitário usam as distâncias do modelo quando não informados. As linhas
  do quadro de transportes passam a sair da origem vencedora.

  **Teste de ponta a ponta** (`tests/test_ficha.py`): projeto novo só com inventário, cotações/binômio ANP com ICMS,
  levantamento ICM, trecho (travessias e VMD) e km do canteiro 124,5 + todos os serviços da ficha → croqui igual ao do
  modelo e PATO igual ao da planilha importada (R$ 26.715.472,25 / 27.267.278,71). Diferenças para a planilha licitada:
  só as correções documentadas (transportes 5915321/5914464 da Fase 3, BDI dos betuminosos com desoneração e usina).
- **Metodologia da 2ª edição do Manual de Custos do SICRO (17/11/2025)** — padrão para administração local, canteiro, usina
  e mobilização (a da planilha BR-158 continua disponível no seletor, para reproduzir a planilha de origem):
  - administração local (Vol. 07, modelo ADM_Local_2025): parcela fixa com motorista e miniônibus, almoxarife e faxineiro;
    vinculada com 2 encarregados de turma; laboratório (ELA com 2 casas) e manejo florestal (Tf = Σ Q ÷ (produção × 182,49 h));
    manutenção do canteiro com 0,1 profissional e equipamentos por hora; (mão de obra + veículos) × meses;
  - canteiro — método construtivo, instalação provisória (Vol. 06, CANT_Construcao_2025): áreas fixas 29,54 / 37,10 / 5,29 m²,
    k2 = 1,11 (conservação, Tabela 35), k3 = 1 + 0,0008·DT pav + 0,0009·DT rp + 0,0014·DT leito (Tabela 36);
  - instalação industrial (USINA_2025): CCO = (k1·k2·k3·AC + AD·FEAD)·CMCC + instalação (k2 = 1,11 — o modelo trazia 0,11);
  - mobilização (Vol. 08): CMD = QT × FU × {[(TV × CHP + TD × CHI) × K] + CC}, TV = Σ D ÷ VM (caminhão 60/50/40 km/h, cavalo com
    prancha/dolly 30/25/20 km/h), TD = 0,5 h a cada 6 h (carga), K = 2 quando o transportador retorna, CC = pedágio; pessoal
    NTF = 50% × NMO + NPF-V + 50% × NPV × passagem.
- **Datas-base selecionáveis**: o sistema já traz o SICRO oficial de MT 01/2026, 04/2026 e 07/2026 (sem e com desoneração);
  na aba Custos escolha estado, mês e fonte (SICRO oficial ou planilha de origem). Novas datas-base entram pela importação
  do pacote publicado pelo DNIT. Os índices de reajustamento seguem a data-base escolhida: o sistema traz a publicação
  "Índices de Reajustamento de Obras Rodoviárias" de set/2026 (22 séries, 01 a 09/2026) e importa as próximas em PDF.
- **SNV oficial incluído** (versão 202610A, Mato Grosso — 350 segmentos das BR-070, 080, 158, 163, 174, 242, 251 e 364):
  segmentos do trecho, superfície e unidade local, coordenada de qualquer km pelo eixo oficial (ponto médio para o NE da
  roçada, canteiro para a capital mais próxima) e referência da Revisão do inventário sem precisar enviar a planilha.
- **Relatórios oficiais do SICRO**: na aba Custos, importe o pacote publicado pelo DNIT (.7z, .rar ou .zip, um por data-base,
  vários de uma vez). O relatório analítico dá as composições sem desoneração; as com desoneração saem dos sintéticos de
  mão de obra e equipamentos "com desoneração". Em MT 04/2026 o motor reproduz o custo unitário direto publicado em 6.611 de
  6.618 composições (as 7 restantes são canteiros-tipo). As DMT não vêm no relatório — são as do croqui/quadro do projeto.
- **ADM local e mobilização** (sub-aba própria, itens 01.07 — SICRO Vol. 07, 08 e 09): administração local (parcelas fixa,
  vinculada e variável com MO mensalista e veículos da base, equipes de laboratório ELA = Σ quantidade no contrato ÷ QE,
  manutenção do canteiro, despesas diversas), canteiro (áreas por NPF/NMAX/NMO, FEAC, k1·k2·k3, CMCC), instalação
  industrial (laboratório + composição 903810) e mobilização/desmobilização (passagem reajustada pelo índice, tempo de
  viagem e descanso, veículo transportador e FU da tabela IMOB). Recalcula com o prazo, o BDI e a base do projeto; a
  opção "fixar" mantém o preço da planilha de origem. Na BR-158/MT reproduz ADM, CAN, MOB e DESMOB ao centavo; a usina
  com desoneração é corrigida (a planilha somava a instalação sem desoneração em USINA!H38: R$ 503.838,39 → 498.500,50).
- **Resumo e % dos grupos (Anexo XX)** com verificação do limite de 25% de DSM (art. 6º, III), **Quantidades do contrato**,
  **Curva ABC (Anexo XXI)**, **cronograma físico-financeiro** e detalhamento do **grupo por desempenho**.
- **Vigência**: a planilha PATO é o orçamento de **1 ano**; QUANTIDADES, curva ABC e cronograma são do **contrato**
  (prazo do projeto, ex.: 2 anos = 24 meses): quantidade = PATO × anos, como a aba QUANTIDADES da licitação
  (`× CAPA!D81`). Canteiro, usina, mobilização e desmobilização (1 ÷ anos no PATO) entram uma vez; no cronograma,
  vão para o 1º mês (desmobilização no último) e os demais itens em parcelas de 1 ÷ meses.
- **Exportar (Excel)**: planilha PATO (Anexo XIX), QUANTIDADES do contrato, % dos grupos, curva ABC, cronograma e
  desempenho, com fórmulas.
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

A base de normas guarda só o texto pesquisável dos documentos (com página), não os arquivos originais — eles
ficam com o usuário. Isso mantém o sistema em cerca de 70 MB.

## Novidades: assistente, salvar versões, fornecedores (ANM/SIGMINE), DMT pela estrada e memória de cálculo
- **Assistente** (aba própria): as 9 etapas para montar o PATO de um segmento — projeto, inventário, ICM/IP, data-base e BDI,
  cotações/binômio, croqui, ficha de serviços, ADM/mobilização, conferência — com ✅/⚠️/❌, o que falta e o botão para a etapa.
- **Menu Arquivo (como Word/Excel):** Novo · **Abrir** (Ctrl+A / Ctrl+O) · **Salvar** (Ctrl+B / Ctrl+S) · **Salvar como** (F12) ·
  **Salvar uma cópia** · **Renomear** · **Histórico de versões** · **Fechar**. O projeto vira um arquivo **.pato** na pasta que você
  escolher (pode ser OneDrive/Google Drive, para usar em qualquer computador); no Chrome/Edge o Salvar atualiza esse mesmo arquivo.
  Ao abrir um projeto que está aberto em outro computador, o sistema informa (uma única mensagem); o Fechar libera o arquivo.
- **💾 Salvar** (ou Ctrl+S): versão completa do projeto (ponto de restauração). **Projetos ▾**: versões salvas (voltar a qualquer
  uma — o estado atual é salvo antes), **salvar como cópia** (projeto novo independente, com tudo), **baixar/abrir arquivo
  .pato** (levar para outro computador). Cada projeto é independente; ao trocar no seletor nada passa de um para outro.
  Excluir um projeto guarda o .pato em `excluidos`.
- **Fornecedores — cadastro geral** (vale para todos os projetos) com o histórico das cotações gravadas. Posição do
  fornecedor: KMZ do projeto → endereço “BR, km” (SNV) → titular na **ANM/SIGMINE** → sede do município (IBGE).
- **Sugerir pela ANM (SIGMINE)**: pedreiras, areais e cascalheiras **com lavra autorizada** (licenciamento, concessão de lavra,
  registro de extração) perto do canteiro, por titular, com a DMT pela estrada — a quem pedir as 3 cotações. Na BR-158 aparecem
  BRITASA, Vale do Araguaia e BRITAZIL, os fornecedores do binômio da planilha. Dados de MT incluídos (SIGMINE out/2026);
  **Atualizar dados da ANM** lê o `<UF>.zip` de app.anm.gov.br/dadosabertos/SIGMINE/PROCESSOS_MINERARIOS/.
- **DMT pela estrada**: caminho mínimo na rede federal do SNV 202610A, separado em pavimentada (PAV/DUP) e não pavimentada
  (IMP/LEN; o acesso até a rodovia conta como não pavimentado). Usada no cadastro, nas sugestões da ANM e na leitura da cotação.
  Trechos por rodovias estaduais/municipais não estão no SNV — o sistema avisa quando a rota parece longa demais.
- **Memória de cálculo (PDF)** (aba PATO): origem de cada quantidade (inventário, ICM/IP, memórias), NE e preços; resumo por
  grupo; binômio com o resumo do mais vantajoso, a conferência, as cotações e os anexos; croqui; conferência.
- **Ficha PATO enviada**: agora lê também GD (grupo por desempenho), ADM, CAN e MOB.

## Uso em equipe (servidor) e login
O login vem **desligado** no computador local. Para uso em equipe: `python -m pato_app --host 0.0.0.0 --login` (rede do
escritório) ou o servidor com Docker + https — passo a passo, custos e backup em [`servidor/LEIAME.md`](servidor/LEIAME.md).
Perfis: administrador (usuários), editor (monta e altera; copia projetos como modelo) e leitor (consulta e baixa). Todos veem
todos os projetos; o histórico mostra quem alterou o quê.

## Croqui no modelo da Res. DNIT nº 8/2023 (Anexo IX)
Linha da rodovia pela superfície do SNV — **Pavimentado (P) vermelho, Revestimento primário (RP) azul, Leito natural (LN)
verde**, fora do trecho em preto (até a capital mais próxima e a cidade seguinte); acessos às ocorrências com as mesmas cores
e a distância de cada trecho; formas do modelo (usina/canteiro amarelo, centro sede azul-claro, pedreira cinza, areal elipse,
jazida triângulo verde); início/fim do trecho, travessias, rosa dos ventos, legenda e as tabelas ORIGEM/DESTINO × LN/RP/P/FLUVIAL
e MATERIAL BETUMINOSO (vencedores do binômio ANP), com a observação dos insumos CIF.

**Perímetro urbano automático** (botão *Detectar perímetros urbanos*): para cada cidade do trecho (sede IBGE), o km inicial e
final vêm (1) das **placas de início/fim de perímetro urbano** — inventário de sinalização vertical (tipo/observações) ou pontos
do KMZ; (2) sem placas, da **mancha urbana no mapa** — áreas residenciais/comerciais/industriais do OpenStreetMap (precisa de
internet; fica em cache), onde a rodovia entra e sai da área urbana contínua junto à cidade; (3) sem mapa, estimativa ±1 km da
sede. Travessias digitadas pelo usuário prevalecem.

**Perímetro urbano no croqui:** início e fim de cada travessia urbana demarcados com o km. Critérios, nesta ordem: (1) perímetro
informado (lei municipal/levantamento) na tabela de travessias; (2) polígono importado — KML/KMZ da prefeitura ou shapefile do
IBGE (Áreas Urbanizadas): o sistema calcula o km onde a rodovia entra e sai; (3) sem polígono: a sede municipal do IBGE projetada
no eixo identifica a cidade, com limites estimados (±1 km), marcados como estimados.

## Base de normas: só o que está em vigor
Documentos **revogados ou substituídos** (com evidência no registro de vigência) são **excluídos da base** — índice e texto —
inclusive na reindexação. Saíram os 26 volumes da 1ª edição do Manual de Custos do SICRO (substituída pela 2ª edição de
17/11/2025) e as Emendas 2 e 3 da IPR-736 (substituídas pela Emenda 4). Os de alteração parcial (Res. 8/2023, Portaria
1977/2017…) e os sem notícia de revogação continuam.

## Confiabilidade e desempenho (revisão técnica)

- **Nenhuma edição se perde**: as alterações de um mesmo projeto são gravadas uma de cada vez (no servidor e na tela), mesmo
  passando rápido de célula em célula com Tab ou com várias pessoas no mesmo projeto.
- **Arquivo .pato autocontido**: leva a data-base usada, as bases SICRO (SD/CD), a planilha de origem e os totais do
  orçamento. Ao abrir em outro computador, o sistema instala a base se faltar, recalcula e **avisa** se o total der
  diferente do gravado, ou se uma composição própria daquele computador for diferente da usada no projeto.
- **Pendências na planilha PATO** (botão ⚠ no topo): itens sem preço e quantidades que o sistema não conseguiu calcular e
  substituiu pelo valor anterior/importado (inventário, IP, quadro de transportes, sinalização) — clique para ir ao item.
- **Recálculo ~10× mais rápido** (de ~0,5 s para < 0,05 s por edição): as medidas do inventário e os motores de custo ficam
  em memória enquanto nada muda; a importação da planilha de referência abre o arquivo uma vez só.
- **Servidor**: perfil leitor só consulta e gera arquivos (rotas exatas); limite de tamanho de upload (`PATO_MAX_UPLOAD_MB`,
  padrão 800) e recusa de .pato malformado; o aviso de "aberto em outro computador" identifica a pessoa logada.

## Dados oficiais automáticos (com internet) e bases incluídas

| Dado | Automático (botão) | Sem internet |
|---|---|---|
| **SICRO** (relatórios SD/CD) | Custos → *Baixar e importar SICRO*: escolhe UF e data-base publicadas no site do DNIT (prefere a versão revisada) | importar o pacote .zip/.7z baixado à mão |
| **Preços de asfalto (ANP)** | Binômio → *Atualizar ANP* baixa as planilhas da ANP; *Preços ANP* preenche as origens no mês da data-base: **estado → região → Brasil** | planilhas da ANP incluídas no sistema (até set/2026) ou *Importar planilha ANP* |
| **Índices de reajuste (FGV/IBRE, publicação DNIT)** | Binômio → Índices → *Atualizar (internet)* | banco de dados (até set/2026) ou importar o PDF |
| **VMD** | Transporte → *VMD da base do sistema* (modelagem VMDa 2025 DNIT/PNCT incluída); *Atualizar base de VMD* troca por uma mais nova | idem |

- **DMT automática pela estrada** (rede federal do SNV, saindo da sede do município — IBGE — até o canteiro ou, sem ele, o meio
  do segmento): Binômio → *DMT dos betuminosos* (pavimentada → Pav., não pavimentada → RP; fluvial e LN como informados) e
  ADM local e mobilização → *DMT pela estrada (capital → canteiro)*, que compara as 3 capitais mais próximas e adota a de menor
  percurso. Fora de MT (rede incluída só de MT) o percurso é estimado em linha reta × 1,07, pavimentado — conferido com os binômios
  ANP aprovados (Betim/MG 1.867,6 × 1.871,8 km; Goiânia/GO 1.200,2 × 1.198,8 km).
- **Cotação da passagem de ônibus** (mobilização de pessoal): itinerário capital → cidade do canteiro, estimativa pela tarifa
  média das passagens dos PATOs aprovados de MT (R$ 0,29/km intraestadual; R$ 0,39/km interestadual), links para pesquisar
  o preço (ClickBus, Busca Ônibus) e registro do valor, mês da pesquisa, fonte e comprovante; o reajuste até a data-base é
  pelo índice de Mobilização e Desmobilização (FGV).
- **NE (nível de esforço)**: a ficha traz o NE padrão; edite na ficha e use *Salvar NE como padrão* (vale para os próximos projetos) —
  *Restaurar ficha original* desfaz. No projeto, o NE também é editável em cada linha da planilha PATO.
- **Croqui como planilha**: edite ou cole do Excel as ocorrências (nome, tipo, km, lado, acesso LN/RP/P, distância fixa). Pedreira/areal
  fora do segmento pela rodovia: km fora do intervalo; saída por vicinal: km do entroncamento + acesso LN/RP/P.
- **ISSQN** por município com km inicial/final (peso = extensão no município, como a aba ISSQN).
- **Projetos com vários segmentos** (ex.: BR-174 km 304,6–366,3 + km 0–81,4 + km 0–3,7): a extensão é a soma dos segmentos.

### Validação contra PATOs aprovados (data-base jul/2025)
- **BR-364/MT km 693–809 REV4**: quantidades iguais à planilha; total SD a 0,03% do aprovado. Diferenças apontadas:
  aquisição de betuminoso **com desoneração** na planilha aprovada usa o BDI em % sem dividir por 100 (BD: `E/(1+BDI!E25)*(1+BDI!E44)` com
  E25 = 34,82 e E44 = 40,46) — superestima o AM com desoneração em ~11%; o sistema calcula o valor correto.
- BR-174 R2 e BR-364/405/435 REV1 buscam os preços das composições em planilhas externas (`[10]Planilha1`, `[11]Planilha1` = SICRO com BDI);
  as abas CPU internas estão desatualizadas — use a base SICRO oficial baixada do DNIT.

## PATO de licitação de outro segmento (mesmo padrão da referência)

O "Exportar PATO de licitação" parte da planilha de referência (BR-158/MT REV2): layout, fórmulas e formatação ficam;
as entradas das abas de memória são reescritas com os dados do projeto (`pato_app/memorias.py`):

| Aba(s) | O que vai do projeto |
|---|---|
| CAPA | rodovia, trecho, SNV, data-base, **prazo em anos**, **extensão real** (soma dos segmentos) |
| INDICES_REAJ | série mensal completa do banco de dados (DNIT/FGV); as fórmulas de reajuste consultam a série inteira |
| IP, CALCULO_IP | levantamento km a km, NE/% da faixa e histórico; levantamento em outro modelo (rótulos combinados, fator de serventia) entra com inventário e NE calculados (em destaque) |
| CROQUI, FIT, VMDf, TRANSPORTES_CONSERVA | DMT (LN/RP/P/Pr/Pu) de cada origem/destino, desenho (início/fim, canteiro, travessias, cidades), VMDf por segmento e rota, quadro de transportes por bloco |
| MOB | equipamentos das CPU dos serviços adotados, DMT, velocidades, descanso, itinerário e passagem |
| ANP, PEDAGIO, BINOMIO_ANP, RESUMO_ANP | origens, distâncias, ICMS, pedágio, balsa e preço ANP de cada betuminoso |
| BINOMIO_COTACOES | fornecedores, preço (t ou m³), densidade, data e DMT de cada material (linhas a mais quando há mais cotações) |
| NE_ROCADA, BDI | estações pluviométricas e NE adotado; parcelas do BDI (ISSQN dos municípios, CPRB do ano) |
| SICRO, MAT, PROD | custos, preços e produções da base SICRO do projeto |
| PATO | serviços não adotados ficam com quantidade zero (cinza); serviços novos ganham linha no grupo e preço no BD |

Depois do recálculo, a conferência compara o total com o do sistema; onde a memória ainda diverge, a linha do PATO recebe o
valor do sistema (em destaque). Uma **varredura** procura no arquivo textos do segmento de referência (rodovia, SNV, cidades,
refinarias, fornecedores) e lista o que sobrou como pendência. Teste com a BR-174 montada do zero: total igual ao do sistema,
sem #N/A e sem textos da BR-158. Limites conhecidos (viram pendência): ADM local/canteiro/usina pela 2ª edição do SICRO
(o layout da referência é o da metodologia anterior), composições analíticas CPU_SD/CPU_CD de outra data-base ou próprias,
produtos/materiais sem bloco na referência e anexos QUANTIDADES/CURVA_ABC/CRONOGRAMA para serviços incluídos.

## Instalação (Windows)
1. Instale o Python 3.10 ou mais novo (python.org, marque “Add to PATH”); o 3.13 é o mais testado. O instalador só usa
   pacotes prontos (não precisa do Visual C++). Com Python 3.14/3.15 o py7zr (opcional) pode não instalar — os .7z do
   SICRO são abertos pelo 7-Zip ou pelo tar do Windows.
2. Copie a pasta `pato-app` para, por exemplo, `C:\PATO\pato-app`.
3. Dê dois cliques em `instalar.bat` (uma vez) e depois em `iniciar.bat`.
   O painel abre em http://127.0.0.1:8000.
   O instalador põe primeiro os componentes essenciais (`requirements.txt`, todos com pacote pronto para Windows —
   Python 3.10 a 3.14) e depois tenta os opcionais (`requirements-opcionais.txt`); se algum opcional falhar, a instalação
   conclui e o sistema funciona. Para abrir os pacotes .7z do SICRO, o sistema usa o 7-Zip instalado ou o `tar` do
   Windows 10/11.

Linux/macOS: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m pato_app`

Os dados ficam em `%USERPROFILE%\PATO_App` (banco `pato.db`, `exportacoes\`, `modelos\`).
Para mudar a pasta, defina a variável de ambiente `PATO_DADOS`.

O modelo padrão é a planilha BR-158/MT incluída em `pato_app/modelos/`. Para usar outro PATO como modelo,
escolha-o na aba **Exportar → Definir como modelo padrão**.

“Conferir totais” (aba Exportar) recalcula a planilha gerada com o LibreOffice, se estiver instalado.
Sem ele, basta abrir o arquivo no Excel — o recálculo é automático.

Programas opcionais (o sistema funciona sem eles):
- **LibreOffice**: conferência automática do total da planilha de licitação exportada (sem ele, o Excel recalcula ao abrir);
- **Tesseract OCR** (com português): indexar documentos digitalizados novos na base de normas — a base que acompanha o
  sistema já está indexada;
- **7-Zip**: abrir pacotes .rar; os .7z e .zip do SICRO são abertos pelo próprio sistema (py7zr).

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
`desfazer_alteracao_custo`, `exportar_composicoes`; binômio: `assistente_pato`, `projeto_salvar_versao`, `memoria_de_calculo`, `fornecedores_anm`, `rota_dmt`, `binomio_listar`, `binomio_ler_cotacao`, `binomio_gravar_cotacao`, `binomio_resumo`, `binomio_conferir`, `binomio_adotar_conferidos`, `fornecedores`, `binomio_salvar_material`, `binomio_salvar_betuminoso`,
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


## Claude Code no projeto (para quem desenvolve o sistema)

- **`CLAUDE.md`** — regras do projeto, regras de negócio sensíveis, mapa do código e tempo de cada teste.
- **Hooks** (`.claude/settings.json`, scripts em `.claude/hooks/`):
  - `bloquear_planilhas.py` — barra `git add`/`git commit` de planilhas, PDFs e zips fora de `pato_app/modelos/`,
    `tests/dados/` e `docs/referencias/` (as planilhas enviadas pelo usuário são particulares);
  - `checar_sintaxe.py` — após cada edição, confere a sintaxe dos `.py` e do `app.js` (< 1 s).
- **Skill `/conferir-licitacao [planilha.xlsx]`** — monta um PATO do zero, exporta a planilha de licitação, recalcula e
  confere total × sistema, #N/A, sobras da referência e pendências.
- **Plugins** ativados ao abrir a pasta no Claude Code (`/plugin` para conferir): **superpowers** e
  **claude-code-setup** (marketplace oficial da Anthropic) e **claude-mem** (thedotmack/claude-mem, memória entre
  sessões).
