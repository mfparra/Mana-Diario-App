# Arquitetura

## 1. Visão geral

```
┌────────────────────────── Android (com.marcosparra.manadiario) ──────────────────────────┐
│  Compose UI ─ ViewModels ─ Repositórios ─┬─ Room: cache, anotações, favoritos, marcações │
│                                          ├─ Room (asset): blivre.sqlite (somente leitura)│
│                                          ├─ DataStore: preferências + tokens (cifrados)  │
│                                          └─ Retrofit ──────────────┐                     │
│  WorkManager: sync diário + notificação   AdMob/UMP   Play Billing │                     │
└────────────────────────────────────────────────────────────────────┼─────────────────────┘
                                                                     │ HTTPS / JSON (v1)
┌──────────────────────────── Servidor (podman compose) ─────────────┼─────────────────────┐
│  Caddy (TLS) ──> api (FastAPI) ──> PostgreSQL                      ▼                     │
│                    │   └─ blivre.sqlite (somente leitura)                                │
│                    └─ verificação Google ID token / Play Developer API                   │
│  worker (agendador) ──> pipeline de geração ──> LlmClient ──> qualquer LLM (config .env) │
└──────────────────────────────────────────────────────────────────────────────────────────┘
      hoje: rede podman `llm-net` → contêiner `llm` (llama.cpp, API OpenAI) http://llm:8081/v1
      amanhã: outro servidor local ou API externa — só muda o .env (ver LLM_SERVER.md)
```

## 2. Monorepo

Um repositório com `android/`, `server/`, `tools/` e `infra/`. Motivos: o contrato da API e o
`blivre.sqlite` são compartilhados; uma única fila de trabalho (`PLANO.md`) para o agente.

## 3. Servidor

### Camadas
- `app/api/` — routers FastAPI (validação de entrada, auth, serialização). Sem regra de negócio.
- `app/services/` — casos de uso: `StudyService`, `GenerationService`, `AuthService`,
  `SubscriptionService`, `ProfileService`.
- `app/domain/` — modelos puros: referência bíblica, calendário litúrgico, schema do estudo.
- `app/db/` — modelos SQLAlchemy, repositórios, sessão.
- `app/llm/` — `LlmClient` (interface) + `OpenAICompatibleClient` (padrão; serve o llm-server atual)
  + `FakeLlmClient`. Único lugar com particularidades de provedor/modelo.
- `app/notes/` — sincronização de anotações (criptografia, versão otimista).
- `app/bible/` — `BibleRepository` (leitura somente leitura do `blivre.sqlite`: `exists`, `get_passage`, `get_text`);
  o parser de referências vem do pacote `blivre` (`tools/biblia`). Referências guardadas no banco usam a forma
  canônica USFM (`JHN 3:16`, `1CO 13:4-7`), via `format_canonical`.
- `worker/` — agendador (APScheduler ou laço simples) que chama `GenerationService`.

### Tabelas principais (PostgreSQL)

| Tabela | Campos-chave |
|---|---|
| `users` | id (uuid), google_sub (único), email, name, photo_url, created_at, deleted_at |
| `refresh_tokens` | id, user_id, family_id (detecção de reuso), token_hash, expires_at, revoked_at, replaced_by_id, device_label |
| `studies` | date (PK), status (`draft`/`published`/`failed`), payload (jsonb), etag, schema_version, verse_ref, special_day, quote_id, provider, model, prompt_version, is_fallback, generated_at, published_at |
| `generation_jobs` | id, kind (`daily`/`personal`), date, user_id?, status (`pending`/`running`/`done`/`failed`), priority, attempts, last_error, created_at, updated_at |
| `verse_plan` | id, verse_ref (USFM canônico, ex.: `JHN 3:16`), theme?, special_day? (chave do calendário), active — origem: acervo próprio em `server/data/` |
| `curated_quotes` | id, text, author (não vazio), source, tags (text[]), active, last_used_at |
| `user_profiles` | user_id, encrypted_payload (bytea), consent_at, consent_version, updated_at |
| `personal_studies` | user_id, date, payload (jsonb), provider, model, prompt_version, generated_at — PK (user_id, date) |
| `subscriptions` | id, user_id, product_id, purchase_token_hash, status, expires_at, auto_renewing, acknowledged, created_at, last_verified_at |
| `notes` | user_id, date, encrypted_body (bytea), version (int), updated_at, deleted_at — PK (user_id, date) |

Todas as tabelas com `user_id` usam `ON DELETE CASCADE` (excluir a conta apaga tudo). Modelos em `server/app/db/models.py`;
migrações em `server/migrations/` (testadas em Postgres real: ida e volta + sincronia modelo↔migração).

`studies.payload` guarda o estudo completo já com o **texto bíblico resolvido**, para que a
resposta da API seja estática e cacheável (ETag = hash do payload).

### Geração do estudo diário
1. Worker roda a cada hora e garante estudos publicados de **hoje até D+7**.
2. Para cada data faltante: resolve versículo-base (calendário especial > plano de versículos),
   escolhe citação curada, monta candidatos de leitura complementar, chama a LLM.
3. Valida JSON (Pydantic), valida referências contra a BLIVRE, aplica regras de conteúdo.
4. Até 3 tentativas; se falhar, marca `failed`, registra erro e alerta no log.
   **Fallback**: se hoje não tiver estudo publicado, a API serve o estudo mais recente com aviso
   ou um estudo de reserva (pool pré-gerado) — ver `CONTEUDO_E_LLM.md`.

### Geração "Para você" (premium)
- **Lote de madrugada**: depois que o estudo de D está publicado, o worker enfileira um job `personal`
  para cada premium com perfil (janela 01:00–05:00, 1 requisição por vez — o llm-server é compartilhado).
- **Sob demanda** só se faltar (perfil editado hoje, novo assinante): `GET /v1/studies/{date}/personal`
  cria job prioritário e responde `202`; o app mostra "preparando seu texto", consulta a cada 10 s
  enquanto a tela está aberta e o `SyncWorker` busca depois. Com modelos lentos (1–3 min) isso é esperado.
- Entrada: estudo do dia + perfil descriptografado em memória. Nunca logar o prompt completo.

### Anotações
- Uma anotação por (usuário, data). O app é a fonte imediata (salva local a cada pausa de digitação)
  e sincroniza: `PUT /v1/notes/{date}` com `base_version`; servidor aceita se `base_version == version`,
  senão `409` com a versão do servidor → o app guarda as duas e pede ao usuário para escolher/mesclar.
- Exclusão = marca `deleted_at` (tombstone) para propagar a outros aparelhos; limpeza após 30 dias.
- Pull incremental: `GET /v1/notes?updated_since=<instante>`.

## 4. App Android

### Módulos e pacotes
Começar com um único módulo `:app`, organizado por feature:
`core/` (design system, rede, banco, auth, ads, billing), `feature/today`, `feature/bible`,
`feature/history`, `feature/profile`, `feature/premium`, `feature/onboarding`.

### Bancos locais
- **`mana_cache.db`** (Room, gravável): `cached_studies` (date, json, etag, fetched_at),
  `cached_personal` (date, json), `notes` (date, body, version, local_updated_at, sync_state
  [`synced`/`pending`/`conflict`], server_body_on_conflict), `favorites`, `highlights` (ref, cor),
  `bookmarks`, `reading_position`. FTS4 sobre `notes.body` para busca nas anotações.
- **`blivre.db`** (Room `createFromAsset`, somente leitura): `books`, `verses`, `verses_fts` (FTS4, sem acento),
  `footnotes`, `superscriptions`, `metadata`. O schema gerado pelo script **precisa bater exatamente** com as
  entidades Room: ver `tools/biblia/SCHEMA.md`.

### Cache e sincronização
- Abrir "Hoje": mostra o cache imediatamente; em paralelo faz `GET` com `If-None-Match`.
- `SyncWorker` (WorkManager, periódico ~12 h, com rede): busca hoje, preenche dias faltantes do histórico
  e faz push/pull das anotações. `NotesPushWorker` (único, com rede) é disparado após cada edição.
- `DailyNotificationWorker`: agendado para o horário escolhido; pré-carrega o estudo e notifica.
- Logout: tenta enviar anotações pendentes; avisa se alguma não sincronizou; apaga tokens,
  `cached_personal`, anotações e dados de perfil; mantém Bíblia e estudos gerais.

### Navegação e deep links
Rotas: `today`, `study/{date}`, `bible/{book}/{chapter}?verse={v}&end={e}`, `bible/search`,
`history`, `favorites`, `notes` (todas as anotações), `note/{date}` (editor em tela cheia),
`profile`, `premium`, `about`.
Tocar numa referência no estudo navega para `bible/...` com destaque do(s) versículo(s).
Deep link externo opcional: `manadiario://study/2026-11-01`.

## 5. Segurança

- HTTPS obrigatório; `network_security_config` sem cleartext em release (exceto debug → IP local).
- ID token Google validado no servidor (assinatura, `aud` = Web client ID, `iss`, `exp`).
- JWT próprio assinado (HS256 com segredo forte ou EdDSA); refresh token rotativo com detecção de reuso.
- Tokens no app: DataStore cifrado com Tink (chave no Android Keystore).
- Perfil premium e anotações: criptografia de campo no servidor (chave em variável de ambiente, rotação documentada).
- Rate limit por usuário nos endpoints de geração; endpoints admin protegidos por token separado.
- Logs JSON sem PII (`app/core/logging.py`): sem e-mail, IP, cabeçalhos, corpo, query string, texto do perfil
  ou da anotação, prompt personalizado nem mensagem de exceção (só tipo + pilha). Campos extras só de uma
  lista permitida; o access log do uvicorn fica desligado (registra IP) e o middleware loga o **modelo** da rota.

## 6. Contêineres (Podman)

Tudo do servidor roda em contêineres, orquestrados por `infra/compose.yaml` com `podman compose`:

| Serviço | Imagem | Rede | Volumes | Observação |
|---|---|---|---|---|
| `proxy` | `caddy` oficial | `mana-net` | `mana-caddy` (certificados) | Única porta exposta (80/443); só em produção/staging |
| `api` | `server/Containerfile` (alvo `api`) | `mana-net`, `llm-net` (externa) | `blivre.sqlite` somente leitura | Uvicorn, usuário não-root, healthcheck em `/v1/health` |
| `worker` | mesma imagem (alvo `worker`) | `mana-net`, `llm-net` (externa) | `blivre.sqlite` somente leitura | Gera estudos e "Para você" |
| `db` | `postgres:16` oficial | `mana-net` | `mana-pgdata` | Sem porta publicada no host em produção |
| `llm` | *(projeto llm-server, fora deste compose)* | `llm-net` | — | Compartilhado; o Maná só entra na rede |

- `Containerfile` multi-stage (build com `uv` → runtime slim), usuário 10001, sem segredos na imagem.
  No compose, `api`/`worker`/`migrate` rodam com `read_only`, `tmpfs: /tmp`, `cap_drop: ALL` e `no-new-privileges`.
- `proxy` (Caddy) fica no perfil `prod`; `DATABASE_URL` é montada pelo compose a partir de `POSTGRES_*`.
- Migrações Alembic rodam num passo `migrate` (serviço one-shot ou `podman compose run --rm api alembic upgrade head`).
- Em desenvolvimento, a `api` publica `127.0.0.1:8000` (o celular de teste acessa pelo IP da máquina
  via override `compose.dev.yaml`); em produção só o `proxy` publica portas.
- Backup: `podman exec db pg_dump` agendado no host (ou contêiner `backup`), com retenção documentada.

## 7. Ambientes

| Ambiente | API | LLM | Ads | Billing |
|---|---|---|---|---|
| debug | `http://<IP-da-máquina>:8000` | llm-server local (`llm-net`) | IDs de teste | contas de teste licenciadas |
| staging | servidor definitivo, subdomínio staging | llm-server | IDs de teste | teste interno Play |
| release | servidor definitivo | qualquer LLM configurada (`LLM_*`) | IDs reais | produção |

`BuildConfig.API_BASE_URL` por build type; IDs reais via `local.properties`/variáveis de CI.
