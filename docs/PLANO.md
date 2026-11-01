# Plano de execução — Maná Diário (app + API)

Como usar: o agente pega a primeira tarefa `- [ ]` com dependências concluídas (`/proxima-tarefa`).
Cada tarefa tem **Aceite** (critério objetivo). **[manual]** = depende do Marcos.
Ao fim de cada fase: `/fechar-fase N`.

Meta da primeira entrega (MVP para teste interno): Fases 0–8.
Premium personalizado: Fase 9. Publicação: Fase 10.

---

## Fase 0 — Fundações

> 2026-10-31: app independente do site web (DECISOES D1). A antiga 0.1 (ler o projeto web) foi removida.

- [x] **0.1 Fonte da BLIVRE**: baixar da eBible.org (`porbr2018`, USFM), versionar o zip em `tools/biblia/fonte/`
  com SHA-256 e script de download. Aceite: zip confere com o hash; 66 livros; licença registrada (B2).
- [x] **0.2 Ler o llm-server** — feito no planejamento (2026-10-31), ver `LLM_SERVER.md` §2.
  Conferir se o `.env` dele mudou antes da Fase 3.
- [x] **0.3 Responder pendências bloqueantes** [manual] — P8/L5 e L8 respondidas em 2026-11-01; S3 resolvida (D1).
- [x] **0.4 Inicializar repositório**: git, `.gitignore` (Android, Python, `.env`, keystores,
  `google-services.json`, `build/`), `infra/.env.example`, `.editorconfig`.
  Aceite: `git status` limpo após o primeiro commit; nenhum segredo versionado.
- [ ] **0.5 Contas e consoles** [manual] — lista para o Marcos:
  - Google Cloud: projeto, tela de consentimento OAuth, **OAuth client "Web"** (usado como `serverClientId`
    e como `aud` no servidor) e **OAuth client "Android"** com SHA-1 de debug e de release/Play App Signing.
  - Play Console: criar app `com.marcosparra.manadiario`.
  - AdMob: app + bloco de banner (guardar IDs fora do git).
  Aceite: IDs anotados em local seguro; `infra/.env.example` lista as variáveis correspondentes.

## Fase 1 — Bíblia BLIVRE (dados compartilhados)

Dep.: 0.1 ✅

- [x] **1.1 Importador** `tools/biblia/importar_blivre.py`: lê o USFM da BLIVRE (`tools/biblia/fonte/`) e gera
  `build/blivre.sqlite` com `books(id, usfm, name_pt, abbrev_pt, testament, ordinal, chapters)`,
  `verses(id, book_id, chapter, verse, text)` e `verses_fts` (FTS4, `content=verses`).
  Aceite: 66 livros; contagem de versículos igual à da fonte; 10 versículos conhecidos conferidos em teste.
  Feito (2026-10-31): também `footnotes`, `superscriptions` e `metadata`; FTS sem acento (`remove_diacritics=1`). Ver `tools/biblia/SCHEMA.md`.
- [x] **1.2 Compatibilidade com Room**: o schema do SQLite gerado bate exatamente com as entidades Room
  da Fase 5 (tipos, nulabilidade, índices, `user_version`). Criar teste que compara com o JSON de schema
  exportado pelo Room (ou documentar o procedimento até o app existir).
  Feito: comparador `blivre/room_schema.py` + entidades e procedimento em `SCHEMA.md`; o teste contra o JSON real
  é pulado até a 5.5, que precisa fazê-lo passar.
- [x] **1.3 Parser de referências pt-BR** (Python, reutilizável): aceita "Sl 139.14", "Salmos 139:14",
  "1Co 13.4-7", "1 Coríntios 13", "Jo 3:16,18" → estrutura USFM; e formata de volta ("Salmos 139.14").
  Aceite: ≥ 40 casos de teste, incluindo livros numerados e as abreviações da BLIVRE (`\\toc3`).
- [x] **1.4 Licença e atribuição**: registrar em `tools/biblia/LICENCA_BLIVRE.md` a licença, a fonte e o texto
  de atribuição usados na tela "Sobre". Aceite: B5 em `DECISOES.md` vira ✅.

## Fase 2 — Servidor: base

Dep.: 0.4

- [x] **2.1 Projeto** `server/` com `uv`, FastAPI, Pydantic Settings, ruff, pytest; estrutura de camadas
  conforme `ARQUITETURA.md`. Aceite: `uv run pytest` e `ruff` passam; `GET /v1/health` responde.
- [x] **2.2 Banco**: SQLAlchemy 2 + Alembic; migração inicial com todas as tabelas de `ARQUITETURA.md` §3.
  Aceite: `alembic upgrade head` num Postgres limpo; teste de migração ida e volta.
- [x] **2.2b Containerfile** `server/Containerfile` multi-stage (alvos `api` e `worker`), rootless, `uv`, healthcheck.
  Aceite: `podman build` funciona; imagem roda como usuário não-root; nenhum segredo na imagem (`podman history`).
- [x] **2.3 Compose** `infra/compose.yaml` (+ `compose.dev.yaml`) conforme `ARQUITETURA.md` §6: `db` (Postgres 16, volume), `api`, `worker`, passo de migração; `blivre.sqlite`
  montado somente leitura; `api`/`worker` na rede externa `llm-net` (`LLM_BASE_URL=http://llm:8081/v1`);
  todas as variáveis `LLM_*` de `LLM_SERVER.md` §4 no `.env.example`. Documentar o comando que funciona no distrobox.
  Aceite: stack sobe com um comando; health mostra `db: ok` e `llm: ok`.
- [x] **2.4 Módulo Bíblia no servidor**: leitura do `blivre.sqlite`, `get_text(ref)`, `exists(ref)`, parser da 1.3
  (pacote `blivre` de `tools/biblia` como dependência de caminho no `uv`; não duplicar o parser).
  Aceite: testes de leitura de versículo, intervalo e capítulo inteiro.
- [x] **2.5 Erros, logs e middleware**: formato de erro de `API.md`, logs JSON sem PII, request-id, CORS desligado.

## Fase 3 — Conteúdo e geração

Dep.: 1.x, 2.x, 0.2

- [x] **3.1 Calendário** `domain/calendar.py`: computus + datas da tabela de `CONTEUDO_E_LLM.md` §2.
  Aceite: testes das datas listadas (Páscoa 2025–2027, 2030; Corpus Christi 2026).
- [ ] **3.2 Plano de versículos**: montar acervo próprio em `server/data/verse_plan.*` (≥ 366 referências,
  com tema e datas especiais; o agente propõe só **referências**, o texto vem da BLIVRE) + tabela `verse_plan`;
  regra de não repetição em 365 dias. Lista revisada pelo Marcos [manual]. Aceite: simulação de 2 anos sem repetição indevida; todas as refs existem na BLIVRE.
- [ ] **3.3 Citações curadas** (L5 ✅): montar o acervo de domínio público em `server/data/quotes.*` (texto, autor,
  obra, localização, URL da fonte, idioma original, tradução do projeto?) + seleção por tags e janela de repetição.
  Lista revisada pelo Marcos [manual] antes de produção.
  Aceite: teste de seleção determinística por data; nenhuma citação sem autor.
- [x] **3.4 Candidatos de leitura complementar** (P9): fonte de referências cruzadas (OpenBible.info, conferir licença).
  Aceite: para 50 versículos do plano, ≥ 3 candidatos válidos cada.
- [x] **3.5 Adaptador LLM agnóstico**: `LlmClient` + `OpenAICompatibleClient` + `FakeLlmClient`, configurado só por
  `LLM_*` (`LLM_SERVER.md` §3–4): modo JSON configurável, `LLM_EXTRA_BODY`, remoção de raciocínio, extração de JSON,
  orçamento de contexto, timeout longo, semáforo de concorrência, registro de `provider`/`model`.
  Perfis em `infra/llm-profiles/` e comando `llm-check`.
  Aceite: o mesmo estudo de teste gera com **Gemma 4 (JSON_MODE=none)** e **Qwen3 (json_schema)** trocando só o `.env`;
  testes unitários cobrem resposta com `<think>`, JSON cercado de texto, JSON inválido e timeout;
  nenhum arquivo fora de `app/llm/` cita nome de modelo.
- [ ] **3.6 Prompts v1** `server/prompts/study_v1.md` a partir de `CONTEUDO_E_LLM.md` §6. Aceite: 10 gerações de amostra
  revisadas pelo Marcos [manual] antes de seguir.
- [ ] **3.7 Pipeline de geração** com validações e tentativas (`CONTEUDO_E_LLM.md` §4).
  Aceite: testes com `FakeLlmClient` cobrindo sucesso, JSON inválido, ref fora dos candidatos,
  citação bíblica entre aspas no corpo, falha após 3 tentativas.
- [ ] **3.8 Worker**: garante hoje..D+7 publicados; processa jobs; lotes na janela da madrugada e 1 requisição
  por vez (llm-server compartilhado); CLI `gerar --data` e `gerar --de --ate`. Também roda, 1×/dia,
  `NotesService.purge_tombstones()` (tombstones de anotações com mais de 30 dias).
  Aceite: stack local gera 8 dias seguidos sozinha; BuscaPalavras continua respondendo durante o lote.
- [ ] **3.9 Pool de reserva** (14 estudos) + publicação de fallback à meia-noite. Aceite: teste simulando falha do LLM.
- [ ] **3.10 Endpoints admin** (listar falhas, regenerar, publicar). Aceite: protegidos por `X-Admin-Token`.

## Fase 4 — Servidor: autenticação e API de estudos

Dep.: 2.x (3.x para dados reais)

- [x] **4.1 `POST /auth/google`**: valida ID token (`google-auth`), cria/atualiza usuário, emite tokens.
  Aceite: testes com tokens forjados/expirados/`aud` errado rejeitados.
- [x] **4.2 Refresh rotativo + logout** com detecção de reuso. Aceite: testes de rotação e reuso.
- [x] **4.3 `/me`** (GET, PATCH, DELETE, export). Aceite: exclusão apaga todas as tabelas relacionadas.
- [x] **4.4 Estudos**: `/studies/today`, `/studies/{date}`, `/studies?from&to` com ETag e regra de data futura.
  Aceite: testes de 304, 404, 422; payload igual ao exemplo de `API.md`.
- [x] **4.5 Anotações**: `GET /notes?updated_since`, `GET/PUT/DELETE /notes/{date}` com criptografia de campo,
  versão otimista (409 com versão do servidor) e tombstones. Aceite: testes de criar, editar, conflito, excluir,
  pull incremental; banco guarda só bytes cifrados; export e exclusão de conta incluem anotações
  (o export da 4.3 hoje só traz metadados das notas: incluir o texto decifrado).
- [x] **4.6 Rate limiting** conforme `API.md`.
- [x] **4.7 Contrato**: exportar `openapi.json` para `docs/` e conferir com `API.md`.

## Fase 5 — App Android: base

Dep.: 0.5, 1.2

- [ ] **5.1 Projeto** `android/` (Kotlin, Compose, M3, Hilt, version catalog, minSdk 26, targetSdk atual exigido pela Play).
  Build types `debug`/`release`, `BuildConfig.API_BASE_URL`, IDs via `local.properties`.
  Aceite: `./gradlew assembleDebug lint testDebugUnitTest` passa.
- [ ] **5.2 Design system**: tokens de `DESIGN.md` (claro/sépia/escuro), tipografia com fontes embarcadas,
  componentes base (`MannaHeaderBlock`, `QuoteBox`, `MetaItem`, `KeywordChip`, `DropCapText`).
  Aceite: previews de todos os componentes nos 3 temas; contraste conferido.
- [ ] **5.3 Logo**: `ic_mana_logo` (VectorDrawable a partir do SVG), ícone adaptativo + monocromático, splash.
  Aceite: logo fiel ao SVG em preview; ícone legível em 48 dp.
- [ ] **5.4 Camada de rede**: Retrofit + kotlinx.serialization + interceptor de auth com refresh automático
  (Authenticator) + mapeamento do formato de erro. Aceite: testes com MockWebServer.
- [ ] **5.5 Room**: `mana_cache.db` + `blivre.db` via `createFromAsset` (cópia do `blivre.sqlite` em `assets/`
  por tarefa Gradle a partir de `tools/biblia/build`). Aceite: teste instrumentado lê Jo 3.16.
- [ ] **5.6 Navegação** com rotas tipadas, barra inferior e deep links (`ARQUITETURA.md` §4).
- [ ] **5.7 Login Google**: Credential Manager (`GetGoogleIdOption` com `serverClientId` = Web client ID) →
  `POST /auth/google` → tokens no DataStore cifrado (Tink). Onboarding + tela de login.
  Aceite: login, reabertura sem novo login, logout limpa dados; erro de rede tratado.

## Fase 6 — App: estudo do dia, cache e notificação

Dep.: 4.4, 5.x

- [ ] **6.1 Repositório de estudos** (cache-first + revalidação ETag). Aceite: testes unitários com fake API e Room em memória.
- [ ] **6.2 Tela Hoje** conforme `DESIGN.md` §5 (todos os estados). Aceite: screenshot tests/previews dos estados;
  TalkBack lê na ordem certa.
- [ ] **6.3 Links de referência** no versículo, na leitura complementar e no corpo → leitor (depende de 7.2; criar stub antes).
- [ ] **6.4 Histórico** + **Favoritos**. Aceite: funciona offline com o que está em cache.
- [ ] **6.5 SyncWorker** + **DailyNotificationWorker** (horário escolhido, permissão POST_NOTIFICATIONS,
  canal de notificação). Aceite: notificação chega no horário em aparelho real; toque abre o estudo do dia.
- [ ] **6.6 Compartilhar como imagem** (`DESIGN.md` §6).
- [ ] **6.7 Anotações — local**: tabela `notes` + FTS4, `NotesRepository`, área "Minhas anotações" na Hoje e em
  qualquer estudo do histórico, editor em tela cheia, autosave com debounce, links de referências.
  Aceite: digitar offline, fechar o app e reabrir mantém o texto; nada se perde ao girar a tela.
- [ ] **6.8 Anotações — sincronização**: `NotesPushWorker` + pull no `SyncWorker`, estados de sync, tela de conflito.
  Aceite: editar em dois aparelhos gera conflito resolvível; logout avisa se há pendências.
- [ ] **6.9 Aba Anotações**: lista, busca e exportar como texto/Markdown.

## Fase 7 — App: leitor bíblico

Dep.: 5.5

- [ ] **7.1 Navegação** livro → capítulo → texto; deslizar entre capítulos; última posição salva.
- [ ] **7.2 Abrir por referência** com rolagem e destaque temporário + "Voltar ao estudo".
  Aceite: refs de versículo, intervalo e capítulo inteiro funcionam a partir do estudo.
- [ ] **7.3 Busca** (FTS4) com resultados por livro e destaque do termo. Aceite: busca sem acento encontra texto acentuado
  (já resolvido no banco: `unicode61 remove_diacritics=1` — normalizar também o termo digitado).
- [ ] **7.4 Destaques, marcadores, copiar/compartilhar** versículos (com referência + "BLIVRE") e
  **"Anotar"** (insere a referência na anotação do devocional do dia).
- [ ] **7.5 Ajustes de leitura**: fonte, tema, espaçamento — compartilhados com a tela Hoje.
- [ ] **7.7 Notas e títulos** (surgiu na 1.1): exibir títulos de salmos (`superscriptions`) antes do v. 1 e notas de
  rodapé (`footnotes`, incl. `quote_source`) como marcador tocável no versículo. Aceite: Gn 3.5 mostra a nota; Sl 3 mostra o título.
- [ ] **7.8 Tela "Sobre"**: atribuição da BLIVRE lida de `metadata.attribution` e crédito "Referências cruzadas: OpenBible.info (CC BY)";
  compartilhamentos curtos usam a sigla "BLIVRE"
  (`tools/biblia/LICENCA_BLIVRE.md`).
- [ ] **7.6 Desempenho**: abrir Salmos 119 sem travar (LazyColumn, paginação por capítulo). Aceite: sem jank perceptível em aparelho médio.

## Fase 8 — Monetização (AdMob + assinatura)

Dep.: 6.2; M5 respondida

- [ ] **8.1 UMP + AdMob** com `AdsGate`; banner na Hoje e no Histórico; IDs de teste no debug.
  Aceite: nenhum anúncio para premium; nenhum anúncio antes do consentimento quando exigido.
- [ ] **8.2 Produto de assinatura** na Play Console [manual]: `mana_premium`/`mensal`, preço, teste grátis (se houver);
  conta de serviço com acesso à Play Developer API; testadores licenciados.
- [ ] **8.3 Servidor**: `/subscriptions/google-play/verify` e `/subscriptions/status` com acknowledge.
  Aceite: testes com respostas gravadas da API do Google para cada estado.
- [ ] **8.4 App**: `BillingRepository`, paywall, restaurar compra, estado premium vindo do servidor.
  Aceite: fluxo completo em faixa de teste interno (assinar, cancelar, restaurar em outro aparelho).
- [ ] **8.5 Página de app-ads.txt** no domínio do desenvolvedor [manual].

## Fase 9 — Premium: "Sobre você" e "Para você"

Dep.: 8.3; R2 confirmada

- [ ] **9.1 Servidor — perfil**: `GET/PUT/DELETE /me/profile`, criptografia de campo, consentimento versionado.
  Aceite: banco guarda apenas bytes cifrados; testes de revogação.
- [ ] **9.2 Prompt `personal_v1`** com delimitação do texto do usuário e regras de `CONTEUDO_E_LLM.md` §7,
  incluindo detecção de risco → mensagem com CVV 188. Aceite: testes de injeção de prompt e de sinais de risco.
- [ ] **9.3 Geração "Para você"**: lote de madrugada para premium com perfil + endpoint `/studies/{date}/personal`
  (202 → 200) para o que faltar + rate limit; respeita `LLM_SENDS_PERSONAL_DATA`.
  Aceite: com o Gemma (lento), o texto já está pronto de manhã para todos os premium de teste.
- [ ] **9.4 App — formulário "Sobre você"** com consentimento destacado, limites e ajuda.
- [ ] **9.5 App — cartão "Para você"** na Hoje (estados de `DESIGN.md`), cache local apagado no logout.
- [ ] **9.6 Revisão** [manual]: Marcos testa com 3 perfis fictícios variados e aprova o tom.

## Fase 10 — Qualidade e publicação

- [ ] **10.1 Testes**: cobertura dos repositórios/serviços críticos; teste ponta a ponta manual roteirizado (`docs/ROTEIRO_TESTE.md`).
- [ ] **10.2 Release**: R8/minificação com regras para serialization/Retrofit; assinatura via Play App Signing;
  `network_security_config` sem cleartext.
- [ ] **10.3 Servidor definitivo**: deploy com podman compose (contêineres `proxy`/Caddy com HTTPS, `api`, `worker`, `db`),
  subida automática no boot (decidir S4b: `restart: always` vs. Quadlet/systemd), backups do Postgres,
  monitoramento do health, rotação de logs. [manual parcial]
- [ ] **10.4 Documentos públicos**: política de privacidade, termos, página de exclusão de conta. [manual parcial]
- [ ] **10.5 Play Console**: ficha da loja (screenshots dos 3 temas), Segurança dos dados, ID de publicidade,
  classificação de conteúdo, teste interno → teste fechado (requisitos atuais de testadores) → produção. [manual]

## Fase 11 — Futuro (não iniciar sem pedido)

- Widget da tela inicial (Glance) com o versículo do dia.
- Ouvir o estudo (TextToSpeech).
- Planos de leitura bíblica.
- Sincronizar favoritos/destaques entre aparelhos.
- RTDN do Play Billing (Pub/Sub).
- Migração para a LLM definitiva (trocar `LLM_*`; nova classe só se o provedor não for OpenAI-compatível;
  revisão de privacidade antes de `LLM_SENDS_PERSONAL_DATA=true`).
- Premium: "Para você" considerando as anotações (exige consentimento próprio — DECISOES N7).
- Versão iOS.
