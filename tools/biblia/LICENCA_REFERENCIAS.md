# Referências cruzadas (OpenBible.info): fonte e licença

| Campo | Valor |
|---|---|
| Fonte | <https://www.openbible.info/labs/cross-references/> → `cross-references.zip` (<https://a.openbible.info/data/cross-references.zip>) |
| Arquivo versionado | `fonte/openbible_cross-references.zip` (SHA-256 em `fonte/SHA256SUMS`); cabeçalho do TSV: `#www.openbible.info CC-BY 2026-10-26` |
| Licença | **Creative Commons Attribution (CC BY)**: "Unless otherwise indicated, all content is licensed under a Creative Commons Attribution License" (página da fonte, lida em 2026-10-31) |
| Conteúdo | 344.799 pares (versículo → versículo/intervalo) com votos; importados 341.282 (descartados: 3.512 com votos ≤ 0 e 5 que apontam para 3Jo 1.15, inexistente na BLIVRE) |
| Uso | Só no servidor, para sugerir candidatos de leitura complementar (DECISOES P9). Não é embarcado no app nem exibido como lista. |

Os dados são só referências (nenhum texto bíblico; o OpenBible usa a ESV nas páginas dele, mas o arquivo não
contém texto). A versificação é a mesma da BLIVRE (KJV/Textus Receptus).

## Atribuição

Na tela "Sobre" do app: **"Referências cruzadas: OpenBible.info (CC BY)"**, com link para a página da fonte.
O mesmo texto fica em `metadata.attribution` do `crossrefs.sqlite`.
