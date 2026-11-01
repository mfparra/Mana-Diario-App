# Decisões

Legenda de status:

- ✅ **Definido** — decidido pelo Marcos.
- 🟡 **Proposto** — escolha padrão deste plano; pode ser trocada sem grande custo até a fase indicada.
- ❓ **Pendente** — precisa de resposta do Marcos antes da fase indicada.

Ao mudar o status de uma decisão, registre data e motivo na coluna "Notas".

**Independência:** o app e o site web Maná Diário são projetos independentes (✅ D1). Nenhuma decisão,
arquivo ou dado é herdado do site.

## Produto

| # | Decisão | Status | Notas |
|---|---|---|---|
| D1 | **App independente do site web**: nada é lido, importado ou reaproveitado do projeto web (Bíblia, acervos, prompts, servidor) | ✅ | 2026-10-31, pedido do Marcos. Substitui a antiga tarefa 0.1 e o checklist "Herdado do web" |
| P1 | App Android é o carro-chefe | ✅ | |
| P2 | Estudo diário baseado em um versículo da BLIVRE | ✅ | |
| P3 | Página do estudo mostra: nome "Maná Diário" + logo do maná, frase curta, versículo complementar, palavras-chave | ✅ | Logo em `docs/assets/logo-mana.svg` |
| P4 | Referência visual: layout do devocional em `docs/assets/referencia-design.png` | ✅ | Adaptado para coluna única no celular — ver `DESIGN.md` |
| P5 | Leitor bíblico integrado, usável sozinho ou aberto ao tocar numa referência do estudo | ✅ | |
| P6 | Datas especiais: Páscoa e móveis (ex.: Corpus Christi), Natal, Dia das Mães, Dia dos Pais | 🟡 | Calendário próprio: tabela de `CONTEUDO_E_LLM.md` §2. Colisões: litúrgicas antes das civis; véspera de Natal fora (2026-10-31) |
| P7 | Acervo de versículos que dure mais de um ano | 🟡 | Acervo próprio em `server/data/verse_plan.*` (≥ 366 referências validadas na BLIVRE), revisado pelo Marcos na tarefa 3.2 |
| P8 | **"Pequena frase"** = citação curada (caixa escura, com autor) | ❓ | Sem o banco do site, é preciso montar um acervo curado do zero (ver L5). Alternativa: frase-síntese gerada pela LLM, sem autor. Definir até a Fase 3 |
| P9 | **Versículo complementar**: servidor oferece candidatos (referências cruzadas) e a LLM escolhe um; servidor valida | 🟡 | Fonte: referências cruzadas do **OpenBible.info**, licença **CC BY** confirmada em 2026-10-31 (`tools/biblia/LICENCA_REFERENCIAS.md`). Até 8 candidatos, votos ≥ 3, máx. 3 por livro, sem sobrepor a passagem-base |
| P10 | Seções extras geradas: "aplicação prática" e "oração" curta | 🟡 | |
| P11 | Funções extras do app: histórico, favoritos, compartilhar como imagem, notificação diária em horário escolhido | 🟡 | Widget, áudio (TTS) e planos de leitura ficam para a fase futura |
| P12 | **Espaço de anotações pessoais em cada devocional do dia** | ✅ | 2026-10-31 — detalhes na seção "Anotações" |

## Bíblia

| # | Decisão | Status | Notas |
|---|---|---|---|
| B1 | Tradução: Bíblia Livre (BLIVRE), salva localmente | ✅ | |
| B2 | Fonte: **eBible.org `porbr2018`** (Bíblia Livre, Textus Receptus, fev/2018), formato USFM | ✅ | 2026-10-31. Zip versionado em `tools/biblia/fonte/` com SHA-256; 66 livros, 31.102 versículos |
| B3 | Um único `blivre.sqlite` gerado por script, usado pelo servidor e embarcado no app | 🟡 | Evita divergência de texto entre servidor e app. Schema em `tools/biblia/SCHEMA.md` |
| B6 | Texto bíblico importado **sem alteração**: só saem os marcadores USFM; notas (`\f`) e referências de citação (`\rq`) vão para `footnotes`; títulos de salmos (`\d`) para `superscriptions`; palavras `\add` mantidas sem itálico | 🟡 | 2026-10-31. Espaços irregulares da fonte são preservados. Itálico das palavras `\add` pode voltar depois, se desejado |
| B7 | Abreviações: Jó = "Jó" (a fonte usa "Jo" para Jó e João), Joel = "Jl" | 🟡 | 2026-10-31. Só apresentação |
| B4 | Códigos de livro USFM internamente | 🟡 | |
| B5 | Texto de atribuição/licença da BLIVRE na tela "Sobre" | ✅ | 2026-10-31. CC BY 4.0 Brasil, texto sugerido pelos autores; em `tools/biblia/LICENCA_BLIVRE.md` e em `metadata.attribution` |

## Conteúdo / LLM

| # | Decisão | Status | Notas |
|---|---|---|---|
| L1 | Tudo que não é versículo é gerado pela LLM, exceto citações curadas | ✅ | |
| L2 | LLM atual: llm-server do CacaPalavras2 (llama.cpp, API OpenAI-compatível, rede `llm-net`) | ✅ | Compartilhado com o BuscaPalavras; hoje Gemma 4 E4B com thinking, ctx 4096, 1 req. por vez |
| L3 | Versão final usará uma LLM mais confiável | ✅ | |
| L9 | **O servidor deve poder apontar para qualquer servidor LLM** só por configuração | ✅ | 2026-10-31. Adaptador `LlmClient`; padrão OpenAI-compatível; ver `LLM_SERVER.md` |
| L10 | JSON robusto sem depender de `response_format` (Gemma 4 devolve vazio com `json_object`) | 🟡 | `LLM_JSON_MODE` configurável + extração/validação + nova tentativa |
| L11 | Lotes de geração de madrugada, 1 requisição por vez, para não travar o BuscaPalavras | 🟡 | |
| L4 | Prompts, tom teológico e regras de conteúdo | 🟡 | Prompts próprios a partir de `CONTEUDO_E_LLM.md` §6; amostras revisadas pelo Marcos (3.6) |
| L5 | Banco de citações curadas e regras de uso (repetição, autores) | ❓ | Montar do zero. Quem fornece as citações (com autor e fonte verificáveis)? Ligado a P8. Definir até a Fase 3 |
| L6 | Saída da LLM sempre em JSON validado por schema; até 3 tentativas; depois fallback | 🟡 | |
| L7 | Estudo geral pré-gerado com 7 dias de antecedência pelo worker | 🟡 | Dá margem para falhas do llm-server |
| L8 | Estudos publicados automaticamente após validação (sem revisão humana obrigatória) | ❓ | Alternativa: fila de aprovação no painel admin. Definir até a Fase 3 |

## Servidor

| # | Decisão | Status | Notas |
|---|---|---|---|
| S1 | API REST controla o estudo diário; app mantém cache | ✅ | |
| S2 | Stack: FastAPI + PostgreSQL + Alembic | 🟡 | |
| S3 | Servidor próprio do app, independente do backend do site | ✅ | 2026-10-31 (D1) |
| S4 | **Servidor inteiro em contêineres Podman** (`api`, `worker`, `db`, `proxy`) com podman compose; testar local e depois levar ao servidor definitivo | ✅ | 2026-10-31: explicitado como regra no AGENTS.md |
| S4a | Imagens rootless a partir de `Containerfile` (multi-stage, usuário não-root, `uv` para dependências) | 🟡 | |
| S4b | Produção com `podman compose` + `restart: always` (como o llm-server) | 🟡 | Alternativa: Quadlet/systemd para subir com o boot sem sessão aberta — avaliar na Fase 10 |
| S4c | Dados persistentes só em volumes nomeados (`mana-pgdata`, `mana-caddy`); `blivre.sqlite` dentro da imagem ou volume somente leitura | 🟡 | |
| S5 | HTTPS em produção via Caddy (contêiner `proxy`) | 🟡 | |
| S6 | "Hoje" definido em `America/Sao_Paulo`; servidor aceita até D+1 para fusos a leste | 🟡 | |
| S7 | Domínio/URL pública da API | ❓ | Necessário antes do teste fechado na Play Store |

## Autenticação

| # | Decisão | Status | Notas |
|---|---|---|---|
| A1 | Login obrigatório com conta Google para criar usuário e entrar | ✅ | |
| A2 | App usa Credential Manager → ID token Google → servidor valida e emite JWT próprio | 🟡 | Alternativa: Supabase Auth, como no BuscaPalavras. Escolhido JWT próprio para manter tudo no mesmo servidor |
| A3 | Access token 30 min; refresh token 60 dias, rotativo, guardado com hash no banco | 🟡 | |

## Monetização

| # | Decisão | Status | Notas |
|---|---|---|---|
| M1 | Gratuito com Google AdMob | ✅ | |
| M2 | Assinatura mensal remove anúncios e libera "Para você" | ✅ | |
| M3 | Formatos: banner adaptativo no fim do estudo e no histórico; **sem intersticial** | 🟡 | Contexto devocional; intersticial prejudica a experiência |
| M4 | Sem anúncios dentro do leitor bíblico | 🟡 | |
| M5 | Preço da assinatura e período de teste grátis | ❓ | Definir antes da Fase 8 |
| M6 | Verificação da compra no servidor (Play Developer API) | 🟡 | RTDN (Pub/Sub) numa fase posterior |

## Premium / Privacidade

| # | Decisão | Status | Notas |
|---|---|---|---|
| R1 | Usuário premium pode informar detalhes pessoais; a LLM gera um texto adicional direcionado | ✅ | |
| R2 | Campos do perfil (ver `PRIVACIDADE_LGPD.md`) | 🟡 | Confirmar lista até a Fase 9 |
| R3 | "Para você" **pré-gerado de madrugada** para premium com perfil; sob demanda só se faltar | 🟡 | Com o Gemma, cada geração leva 1–3 min — sob demanda pura deixaria o usuário esperando |
| R4 | Dados do perfil criptografados em repouso; consentimento específico (LGPD art. 11) | 🟡 | |
| R5 | Ao migrar para LLM externa, reavaliar envio de dados do perfil | 🟡 | Hoje o llm-server é próprio — dados não saem da infraestrutura |

## Anotações

| # | Decisão | Status | Notas |
|---|---|---|---|
| N1 | Uma anotação por devocional (por usuário e data), texto livre com até 10.000 caracteres | 🟡 | |
| N2 | Disponível para **todos** os usuários (gratuito e premium) | 🟡 | O requisito não restringiu ao premium |
| N3 | Offline-first: salva no aparelho na hora (autosave) e sincroniza com o servidor | 🟡 | Login é obrigatório, então a anotação segue o usuário para outro aparelho |
| N4 | Criptografadas em repouso no servidor; incluídas no export e apagadas na exclusão da conta | 🟡 | Podem conter dados sensíveis |
| N5 | Conflito entre aparelhos: versão otimista; em conflito, guardar as duas versões e o usuário escolhe | 🟡 | |
| N6 | Referências bíblicas digitadas na anotação ("Jo 3.16") viram links para o leitor | 🟡 | |
| N7 | A LLM **não** lê as anotações (nem no "Para você") | 🟡 | Possível recurso premium futuro, com consentimento próprio |
