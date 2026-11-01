---
description: Pega a próxima tarefa do docs/PLANO.md e executa seguindo o AGENTS.md
---

1. Leia `docs/PLANO.md` e encontre a primeira tarefa `- [ ]` cujas dependências estejam concluídas.
   Se o usuário passou um ID em $ARGUMENTS (ex.: `3.4`), use essa tarefa.
2. Leia os documentos de `docs/` que a tarefa referencia e a seção correspondente de `docs/DECISOES.md`.
3. Se a tarefa depender de decisão "❓ Pendente", pare e pergunte ao Marcos, propondo uma opção padrão.
4. Se for **[manual]**, prepare o que for possível e liste o passo a passo exato para o Marcos.
5. Apresente um plano curto (arquivos, testes) e implemente.
6. Rode testes e lint. Corrija até passar.
7. Marque a tarefa como `- [x]`, atualize docs afetados e faça um commit pequeno.
8. Termine dizendo em 2–3 linhas o que foi feito e qual é a próxima tarefa.
