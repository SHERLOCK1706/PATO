---
name: conferir-licitacao
description: Monta um PATO do zero (segmento fictício BR-999 ou a planilha indicada), exporta a planilha de licitação no modelo da referência BR-158, recalcula no LibreOffice e confere total igual ao do sistema, ausência de #N/A, sobras do texto da referência e pendências. Use depois de mexer em licitacao.py, memorias.py, exportador.py, no cálculo do orçamento ou na ficha.
disable-model-invocation: true
---

# Conferir a planilha de licitação

1. Rode (demora de 3 a 10 minutos; use `run_in_background` e espere a notificação):

   ```bash
   python .claude/skills/conferir-licitacao/scripts/conferir.py $ARGUMENTS
   ```

   Sem argumento usa o segmento fictício BR-999/MT (data-base 2025-07, prazo 24 meses) montado pela ficha.
   Com o caminho de uma planilha PATO de outro segmento, importa inventário, binômio e IP dela e monta do zero
   (a planilha do usuário é particular: **nunca** copie para o repositório).

2. Relate ao usuário, em português, sem jargão:
   - **RESULTADO OK/FALHOU** — total da planilha recalculada × sistema (diferença deve ser 0,00 nos dois regimes);
   - erros de fórmula (#N/A, #REF!) com a aba e a célula;
   - sobras da referência (textos da BR-158 que ficaram no arquivo);
   - pendências que dependem do usuário (DMT pela estrada, passagem, blocos de produto que a referência não tem).

3. Se falhar, investigue a causa antes de corrigir (a diferença costuma vir de `memorias.py` ou do `alinhar` em
   `licitacao.py`) e rode de novo depois da correção. Não apague o arquivo gerado: ele fica numa pasta temporária.
