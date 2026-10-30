# Referências — SICRO / DNIT

| Arquivo | Conteúdo | Uso no sistema |
|---|---|---|
| `Manual-de-Custos-SICRO_V05-FIT.7z` | Manual de Custos de Infraestrutura de Transportes, **Volume 05 – Fator de Interferência de Tráfego (FIT)**, 2ª edição (2025), aprovado em 21/10/2025 (Relato nº 191/2025); divulgado pelo Informativo SICRO nº 02/2025 (17/11/2025) | aba **Transporte** (DMT e FIT) |
| `V05-FIT/` | o mesmo volume extraído (PDF) e em texto, para consulta | — |

## FIT — como o sistema aplica o Volume 05 (2ª ed.)
- O FIT incide **só no momento de transporte de insumos** feito pela contratada (FOB), em **vias pavimentadas** — não na produção
  dos serviços nem no tempo fixo (itens 2.1, 3 e Vol. 01, 2.8.8). Recolhimento de resíduos na pista: sem FIT.
- **A1 = 70 + 0,0035·VMDf** (s) — atraso da operação **PARE e SIGA**; só entra se o orçamento prevê a operação de sinalização
  (serviço 5213850 "Operação de sinalização por bandeirola…" ou similar) e o transporte passa pela extensão da obra (3.2.1.1).
- **A2 = Fc·DMTu** (s), **Fc = (1/Vu − 1/Vp)·3.600** = 60 s/km com Vu = 30 km/h (ajustável com justificativa) e Vp = 60 km/h (3.2.1.2).
- **FIT = 1 + (A1 + A2)/(DMTp·Fp)**, Fp = 3.600/Vp = 60 s/km; **DMTp = DMTr + DMTu** (Eq. 5–7).
- **DMTF = FIT × DMTp**, aplicada na parcela F (momento de transporte) (Eq. 8).
- **VMDf**: VMD por faixa (VMDa ÷ nº de faixas), média ponderada pela distância percorrida em cada segmento da obra (Eq. 1).
- **DMT > 100 km**: sem FIT (3.2.1).

A regra anterior (Anexo 01/2017: até 15% + 5% urbano sobre equipamentos e mão de obra dos serviços), citada no Anexo VI da
Resolução DNIT nº 8/2023, foi substituída pela 2ª edição do Manual.
