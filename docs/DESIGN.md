# Design

Referências: `assets/logo-mana.svg` (logo oficial) e `assets/referencia-design.png`
(layout de devocional impresso usado como inspiração). A referência é de **estrutura e clima visual**
— não copiar textos, nomes ou citações dela.

## 1. Clima visual

Página de livro devocional: papel creme, tipografia serifada, bloco de destaque laranja-terracota com
data e versículo, capitular (drop cap) no início do texto, caixa escura com a frase do dia em laranja,
lista lateral de metadados (devocional N/366, leitura bíblica, palavra-chave) com ícones finos.
O logo traz o maná: tigela de madeira com grãos claros e o nome "MANÁ DIÁRIO" em arco.

## 2. Tokens de cor

| Token | Claro | Escuro | Uso |
|---|---|---|---|
| `paper` (background) | `#FFFCF5` | `#1A1411` | Fundo das telas |
| `paperAlt` (surfaceVariant) | `#F3EBDD` | `#2A211C` | Cartões, leitor sépia |
| `ink` (onBackground) | `#1F1A17` | `#F3EBDD` | Texto principal |
| `inkSoft` | `#5A4A3F` | `#CDBFAE` | Texto secundário |
| `mannaOrange` (primary container) | `#E98A5A` | `#C9744A` | Bloco da data/versículo |
| `onMannaOrange` | `#1F1A17` | `#1A1411` | Texto sobre o bloco |
| `brandBrown` (primary) | `#9C5524` | `#F0A57F` | Rótulos pequenos, links, ícones |
| `wood` | `#9B6A3E` → `#6E4627` | idem | Gradiente do logo/elementos decorativos |
| `woodDark` | `#5A3A22` | `#5A3A22` | Detalhes |
| `manna` | `#FFFDF7` | `#FFFDF7` | Grãos, destaques claros |
| `line` | `#CDBFAE` | `#4A3D34` | Divisórias |
| `quoteBg` | `#14100E` | `#000000` | Caixa da frase do dia |
| `quoteText` | `#E98A5A` | `#F0A57F` | Texto da frase do dia |

Acessibilidade: o laranja `#E98A5A` **não** tem contraste suficiente para texto pequeno sobre creme —
para rótulos pequenos use `brandBrown #9C5524` (≈5,5:1 sobre `paper`). Texto escuro sobre o laranja e
laranja sobre o preto passam com folga. Validar todos os pares (meta WCAG AA).

Temas: **Claro** (padrão), **Sépia** (leitor; fundo `paperAlt`) e **Escuro**. Sem dynamic color
(Material You) — a identidade é fixa.

## 3. Tipografia

| Papel | Fonte | Observação |
|---|---|---|
| Marca (wordmark) | Nunito Black | Mesma do logo (OFL) |
| Títulos do estudo | Literata Bold, caixa alta, espaçamento leve | Equivalente livre ao serifado da referência |
| Corpo do estudo e leitor | Literata Regular / Italic | Feita para leitura longa (OFL) |
| UI (botões, navegação) | Nunito SemiBold | |

Fontes embarcadas em `res/font` (funciona offline).
Tamanho do texto ajustável (4 passos) — aplicado ao estudo e ao leitor; respeitar a escala do sistema.

## 4. Logo e ícone

- Converter `logo-mana.svg` para VectorDrawable (`ic_mana_logo`). O SVG usa `transform` em elipses e
  textos; se o importador do Android Studio falhar, achatar as transformações antes
  (Inkscape "Aplicar transformações" ou `svgo` com `convertTransform`) e conferir gradientes.
- **Ícone do app (adaptativo)**: apenas a tigela com os grãos sobre fundo creme — o texto em arco
  fica ilegível em 48 dp. Gerar também ícone monocromático (Android 13+).
- Splash screen (API `SplashScreen`): tigela centralizada sobre `paper`.

## 5. Telas

Navegação inferior: **Hoje · Bíblia · Histórico · Perfil**.

### Hoje (adaptação da referência para coluna única)
1. Barra superior: logo pequeno + "Maná Diário" (Nunito Black, `brandBrown`); ações: compartilhar, favoritar.
2. **Bloco laranja**: dia em número grande ("05"), mês abreviado ("JUL"), linha dupla, **TÍTULO**,
   versículo em itálico centralizado, referência em versalete negrito. Tocar no versículo/referência → leitor.
   Se `special_day`, selo discreto acima do título (ex.: "Domingo de Páscoa").
3. **Corpo** com capitular de 3 linhas na primeira letra; parágrafos justificados à esquerda
   (evitar justificação total em telas estreitas). Referências citadas no corpo viram links.
4. **Aplicação** e **Oração** em blocos discretos com rótulo pequeno.
5. **Para você** (premium): cartão com borda `brandBrown` e ícone de grãos; estados: gerando (shimmer),
   pronto, erro (tentar de novo), perfil não preenchido (CTA). Usuário gratuito vê cartão de convite ao premium.
6. **Frase do dia**: caixa escura, texto laranja em negrito, filete laranja curto, autor em `@`/nome.
7. **Metadados** (como a coluna da referência), cada um com ícone fino:
   - DEVOCIONAL — `305/365`
   - LEITURA COMPLEMENTAR — `ATOS 17` (link → leitor) + motivo em uma linha
   - PALAVRAS-CHAVE — chips `#LEALDADE` `#AMIZADE` (caixa alta)
8. **Minhas anotações** (todos os usuários): área estilo "folha pautada" em `paperAlt`, rótulo
   "MINHAS ANOTAÇÕES" em `brandBrown`, placeholder "O que Deus falou com você hoje?".
   - Campo multilinha que cresce com o texto; salva sozinho (indicador discreto "Salvo" / "Sincronizando…" /
     "Salvo no aparelho — sincroniza quando houver internet").
   - Botão expandir → editor em tela cheia (`note/{date}`) com o versículo do dia fixo no topo.
   - Referências digitadas ("Jo 3.16") aparecem sublinhadas e abrem o leitor.
   - Ação "Anotar" no toque longo de um versículo no leitor insere a referência na anotação do dia.
   - Conflito entre aparelhos: faixa "Há outra versão desta anotação" → comparar e escolher/mesclar.
   - Não fica atrás do teclado (`imePadding`); acessível por botão "Anotar" fixo na barra superior.
9. Banner AdMob (só gratuito), separado do conteúdo e das anotações por espaço e rótulo "Publicidade".

Estados: carregando (esqueleto do layout), offline com cache (aviso discreto), sem cache e sem rede
(ilustração do maná + tentar de novo), estudo indisponível.

### Bíblia (leitor)
- Seletor de livro (AT/NT, busca por nome/abreviação) → grade de capítulos → texto.
- Texto contínuo com números de versículo em sobrescrito `brandBrown`; deslizar entre capítulos.
- Toque longo num versículo: destacar (3 cores), marcar, copiar, compartilhar (com referência e "BLIVRE").
- Ao chegar via estudo: rolar até o versículo e destacá-lo temporariamente; botão "Voltar ao estudo".
- Busca de texto (FTS) com resultados agrupados por livro.
- Configurações rápidas: tamanho da fonte, tema (claro/sépia/escuro), espaçamento.
- Lembrar última posição de leitura.

### Histórico
Calendário/lista dos estudos em cache e disponíveis no servidor; filtro por palavra-chave; favoritos no topo.
Dias com anotação mostram um ícone de caneta. Aba **Anotações**: lista de todas as anotações (data, título do
estudo, trecho), busca no texto das anotações, exportar como texto/Markdown (compartilhar).

### Perfil
Conta Google (foto/nome), status da assinatura, "Sobre você" (premium), horário da notificação,
tema, tamanho de fonte, privacidade (exportar dados, excluir conta), Sobre (versão, licenças,
atribuição da BLIVRE, política de privacidade).

### Premium (paywall)
Benefícios em 3 itens (sem anúncios, "Para você" diário, apoiar o projeto), preço vindo do Play Billing
(nunca fixo no código), botão assinar, link "Restaurar compra", termos e privacidade.

### Onboarding / Login
2–3 telas curtas (o que é, leitor offline, notificação) + "Entrar com Google". Pedir permissão de
notificação (Android 13+) após o login, com contexto.

## 6. Compartilhar como imagem
Gerar cartão 1080×1350 com bloco laranja (título + versículo + referência), logo e "Maná Diário — BLIVRE".
Renderizado localmente (Compose → Bitmap), enviado via share sheet.

## 7. Acessibilidade
Rótulos de conteúdo em ícones, ordem de leitura do TalkBack seguindo o layout, áreas de toque ≥ 48 dp,
capitular marcada como decorativa (o texto completo é lido normalmente), suporte a fonte grande sem cortes.
