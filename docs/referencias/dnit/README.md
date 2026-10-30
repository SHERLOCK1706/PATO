# Referências — DNIT

| Arquivo | Conteúdo | Uso no sistema |
|---|---|---|
| `VMDa_2025.xlsx` | Modelagem do VMDa 2025 (PNCT) sobre o SNV 202401A — https://servicos.dnit.gov.br/dadospnct. Aba `VMDa2025_SNV202401A`: segmentos com quebras (`km_i_estim`/`km_f_estim`), VMDa por sentido (`VMDa_C`, `VMDa_D`) e por categoria (A–J), tipo de pista (`ds_superfi`: PAV, DUP, N_PAV…) | aba **Transporte → VMD → Importar VMD do DNIT** |

Na importação o sistema usa os subtrechos da mesma BR/UF que cruzam o segmento do projeto (o SNV da modelagem pode ser de
versão diferente do projeto), junta subtrechos vizinhos de mesmo VMD, considera 2 faixas por sentido em pista duplicada e
aponta os trechos sem VMD (ex.: não pavimentados na versão do SNV da modelagem).

Exemplo BR-158/MT (km 85–212,5): 85–143 1308/1174 · 143–169,4 1478/1355 · 171–173,3 1479/1355 · 173,3–189 1690/1600 ·
189–201,2 1357/1281; sem VMD em 169,4–171 e 201,2–212,5 (158BMT0205 não pavimentado no SNV 202401A).
