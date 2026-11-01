# API REST v1

Base: `https://<dominio>/v1` (ver DECISOES S7). JSON UTF-8. Datas `AAAA-MM-DD`, instantes ISO-8601 UTC.
Autenticação: `Authorization: Bearer <access_token>` em todos os endpoints, exceto `/auth/*` e `/health`.

O FastAPI gera o OpenAPI em `/v1/openapi.json`; **este documento é a especificação de referência** —
ao mudar código, atualize aqui.

## Formato de erro

```json
{ "error": { "code": "study_not_available", "message": "Texto legível em pt-BR", "details": {} } }
```

Códigos comuns: `unauthorized` (401), `forbidden` (403), `premium_required` (403),
`not_found` (404), `study_not_available` (404), `future_date` (422), `validation_error` (422),
`rate_limited` (429), `generation_failed` (503).

## Auth

### `POST /auth/google`
Entrada: `{ "id_token": "<Google ID token>", "device_label": "Pixel 8" }`
Saída 200:
```json
{
  "access_token": "...", "access_expires_in": 1800,
  "refresh_token": "...", "refresh_expires_in": 5184000,
  "user": { "id": "uuid", "name": "Marcos", "email": "...", "photo_url": "...", "is_premium": false, "created": true }
}
```
Cria o usuário no primeiro login (`created: true`).

### `POST /auth/refresh`
Entrada: `{ "refresh_token": "..." }` → novo par de tokens (o refresh antigo é revogado).
Reuso de refresh revogado → revoga todos os tokens do usuário (401).

### `POST /auth/logout`
Entrada: `{ "refresh_token": "..." }` → 204.

## Usuário

- `GET /me` → `user` + `preferences` + `subscription` (resumo).
- `PATCH /me` → atualiza `preferences` (ex.: `notification_time: "07:00"`, `timezone`).
- `DELETE /me` → exclusão da conta e de todos os dados (LGPD). 202; processamento imediato ou em até 24 h.
- `GET /me/export` → JSON com todos os dados do usuário, **incluindo anotações** (LGPD).

## Estudos

### `GET /studies/today?tz=America/Sao_Paulo`
Retorna o estudo publicado do dia. Suporta `ETag` / `If-None-Match` (304).

### `GET /studies/{date}`
Data ≤ hoje (+1 dia de tolerância de fuso). Futuro além disso → 422 `future_date`.

### `GET /studies?from=AAAA-MM-DD&to=AAAA-MM-DD`
Lista resumida para o histórico (máx. 62 dias por chamada):
```json
{ "items": [ { "date": "2026-11-01", "title": "Supere", "verse_ref": "PSA 139:14", "keywords": ["lealdade"] } ] }
```

### Objeto `Study`

```json
{
  "schema_version": 1,
  "date": "2026-11-01",
  "day_of_year": 305,
  "days_in_year": 365,
  "special_day": null,
  "title": "Supere",
  "verse": {
    "ref": { "book": "PSA", "chapter": 139, "verse_start": 14, "verse_end": 14 },
    "display_ref": "Salmos 139.14",
    "text": "<texto da BLIVRE resolvido pelo servidor>",
    "translation": "BLIVRE"
  },
  "body": ["parágrafo 1", "parágrafo 2", "parágrafo 3"],
  "application": "Aplicação prática curta.",
  "prayer": "Oração curta.",
  "quote": { "id": "q_0142", "text": "…", "author": "…", "source": "curated" },
  "complementary_reading": {
    "ref": { "book": "ACT", "chapter": 17, "verse_start": null, "verse_end": null },
    "display_ref": "Atos 17",
    "reason": "Uma linha sobre por que ler."
  },
  "keywords": ["lealdade", "superação", "amizade"],
  "generated_at": "2026-10-25T03:00:12Z"
}
```

- `special_day`: `null` ou `{ "key": "pascoa", "name": "Domingo de Páscoa" }`.
- `verse_start`/`verse_end` `null` = capítulo inteiro.
- `quote` pode ser `null` se não houver citação adequada (o app esconde a caixa).

### `GET /studies/{date}/personal` (premium)
- 200 → `{ "date": "...", "title": "Para você", "body": ["..."], "generated_at": "..." }`
- 202 → `{ "status": "generating", "retry_after_seconds": 10 }` (pode levar minutos com LLM local lenta)
- 403 `premium_required` · 409 `profile_missing` (premium sem perfil preenchido)

## Anotações (todos os usuários)

### `GET /notes?updated_since=2026-10-30T12:00:00Z`
Pull incremental (inclui exclusões):
```json
{ "items": [ { "date": "2026-11-01", "body": "texto…", "version": 3, "updated_at": "…", "deleted": false } ],
  "server_time": "2026-11-01T12:00:00Z" }
```
O app guarda `server_time` e usa como próximo `updated_since`.

### `GET /notes/{date}` → uma anotação (404 se não existe).

### `PUT /notes/{date}`
Entrada: `{ "body": "texto (≤ 10.000 caracteres)", "base_version": 2 }` (`base_version: 0` para criar).
- 200 → `{ "date": "...", "version": 3, "updated_at": "..." }`
- 409 `note_conflict` → `details` traz a versão atual do servidor (`body`, `version`, `updated_at`).
- A data deve ter estudo publicado (ou ser ≤ hoje).

### `DELETE /notes/{date}?base_version=3` → 204 (tombstone) · 409 se a versão mudou.

## Perfil premium

- `GET /me/profile` → perfil descriptografado (somente o dono).
- `PUT /me/profile` → corpo conforme `PRIVACIDADE_LGPD.md`; exige `consent_version` aceito. Invalida o "Para você" de hoje.
- `DELETE /me/profile` → apaga perfil e todos os `personal_studies`.

## Assinatura

### `POST /subscriptions/google-play/verify`
Entrada: `{ "product_id": "mana_premium", "purchase_token": "..." }`
O servidor consulta a Play Developer API (`purchases.subscriptionsv2.get`), grava o estado,
confirma (acknowledge) se necessário e responde:
```json
{ "is_premium": true, "status": "active", "expires_at": "2026-12-01T10:00:00Z", "auto_renewing": true }
```

### `GET /subscriptions/status` → mesmo formato. O app consulta no início e após compras.

### `POST /webhooks/google-play` (fase futura)
Recebe RTDN via Pub/Sub push; autenticado por token do Pub/Sub.

## Infra / Admin

- `GET /health` → `{ "status": "ok|error", "db": "ok|error|not_configured", "llm": "ok|degraded", "today_published": true }`
  — `503` se o banco falhar (`status: error`); LLM fora do ar só marca `degraded` (a API continua servindo estudos já gerados).
- `GET /admin/studies?status=failed` · `POST /admin/studies/{date}/regenerate` ·
  `POST /admin/studies/{date}/publish` — header `X-Admin-Token`.

## Rate limits (iniciais)
- `/auth/*`: 10/min por IP · `/studies/*`: 60/min por usuário · `/studies/{d}/personal`: 20/h por usuário
  · `/notes/*`: 120/min por usuário.
