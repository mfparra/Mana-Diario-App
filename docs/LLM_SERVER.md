# LLM — integração e troca de provedor

## 1. Princípio

O servidor do Maná Diário deve conseguir usar **qualquer servidor LLM** só mudando configuração.
Hoje usa o **llm-server compartilhado** (testes iniciais); depois, uma LLM mais confiável — local
ou em API externa. Toda particularidade de modelo/provedor fica dentro do adaptador.

## 2. O llm-server atual (lido em 2026-10-31)

Caminho: `/home/marcos/OneDriveLocalSync/LinguagensProgramacao/Android/CacaPalavras2/llm-server`

- É **só um contêiner `llm`** com a imagem oficial `ghcr.io/ggml-org/llama.cpp:server` (CPU),
  `restart: always`, modelo travado na RAM (`--load-mode mmap+mlock`). Não há FastAPI nele
  (o FastAPI do BuscaPalavras fica no `server/` do próprio BuscaPalavras).
- API **compatível com OpenAI**: `POST /v1/chat/completions`, `GET /health`.
  - Dentro da rede podman externa `llm-net`: `http://llm:8081/v1`
  - No host: `http://127.0.0.1:8081/v1` (só loopback)
- Configuração via `.env`: `LLM_HF_REPO`, `LLM_ALIAS` (nome do modelo na API), `LLM_CTX`,
  `LLM_PARALLEL`, `LLM_THREADS`, `LLM_MEM_LIMIT` (5g), `LLM_PORT`.
- Valores ativos hoje: **Gemma 4 E4B Q4_K_M com thinking** (`LLM_ALIAS=gemma-4-e4b-it`),
  **contexto 4096**, **1 requisição por vez** (as demais esperam na fila), 4 threads.
  Alternativa rápida documentada: Qwen3-4B-Instruct-2507 Q6_K.
- Benchmark do README (puzzle do BuscaPalavras): Gemma 4 com thinking ≈ 51 s por pedido,
  qualidade de pt-BR impecável; Qwen3 4B ≈ 6 s, boa qualidade.
- Pegadinha documentada: **Gemma 4 + `response_format: json_object` devolve conteúdo vazio** no llama.cpp
  atual. Para Gemma, omitir `response_format`; para desligar o raciocínio, enviar
  `chat_template_kwargs: {"enable_thinking": false}`.

### Consequências para o Maná
- **Rede:** `infra/compose.yaml` do Maná declara `networks: { llm-net: { external: true } }`
  nos serviços `api`/`worker` → `LLM_BASE_URL=http://llm:8081/v1`.
- **Tempo:** um estudo (≈ 700–1000 tokens de saída + raciocínio) pode levar **1–3 min** com o Gemma.
  Por isso: estudo geral pré-gerado D+7 e "Para você" pré-gerado de madrugada (ver `CONTEUDO_E_LLM.md` §7).
- **Fila compartilhada:** com `LLM_PARALLEL=1`, a geração em lote do Maná atrasa o BuscaPalavras.
  O worker roda lotes em horário de baixo uso (madrugada) e com **no máximo 1 requisição simultânea**.
- **Contexto 4096:** prompt + saída + raciocínio precisam caber. Orçamento do prompt do estudo:
  ≤ 1.800 tokens de entrada; `max_tokens` ≤ 2.000. O adaptador mede e falha cedo se estourar.
- **Mudanças no llm-server** (modelo, contexto, paralelismo) só com avaliação do BuscaPalavras,
  registradas em `DECISOES.md`. A princípio **nenhuma mudança é necessária**.

## 3. Adaptador `LlmClient`

```python
class LlmClient(Protocol):
    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel],
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> BaseModel: ...
    async def health(self) -> LlmHealth: ...
```

Implementações:
- **`OpenAICompatibleClient`** (padrão) — llama.cpp, Ollama, vLLM, LM Studio, OpenRouter, OpenAI e
  qualquer outro com `/v1/chat/completions`.
- Outros provedores (ex.: API nativa da Anthropic ou do Google) entram como **nova classe** sem tocar
  no resto do código; seleção por `LLM_PROVIDER`.
- `FakeLlmClient` para testes (respostas gravadas), nunca o servidor real.

### Robustez de JSON (independente do modelo)
1. Modo de formato configurável: `LLM_JSON_MODE = none | json_object | json_schema`
   (Gemma 4 no llama.cpp → `none`; Qwen/OpenAI → `json_schema`).
   Quando o modo não é `json_schema`, o adaptador anexa ao *system* o JSON Schema compacto do Pydantic.
2. Sempre: remover blocos de raciocínio (`<think>…</think>`, `<thinking>`, `<reasoning>`, `<thought>`,
   inclusive bloco aberto e não fechado), extrair o primeiro objeto JSON balanceado do texto
   (aceita texto em volta e cercas ```json```) e validar com Pydantic.
3. Inválido → nova tentativa com o **pedido original + o erro de validação** (até `LLM_MAX_RETRIES`).
   A resposta inválida **não** é reenviada, para caber em contextos pequenos (4096).
4. Erro do provedor (timeout, HTTP ≠ 200, conexão) → `LlmUnavailable` imediato; quem repete é o worker.
5. Orçamento: estimativa de tokens (≈ 3,2 caracteres/token) do prompt + `max_tokens` > `LLM_CONTEXT_TOKENS`
   → `LlmContextOverflow` antes de chamar o provedor.
6. `health()` chama `GET /models` e confere se `LLM_MODEL` está entre os modelos servidos.

Código: `server/app/llm/` (`base.py` interface e erros, `parsing.py`, `generation.py` laço de tentativas,
`openai_compatible.py`, `fake.py`). O semáforo `LLM_MAX_CONCURRENCY` é por processo.

## 4. Configuração (`infra/.env`)

| Variável | Exemplo (hoje) | Descrição |
|---|---|---|
| `LLM_PROVIDER` | `openai_compatible` | Implementação do adaptador |
| `LLM_BASE_URL` | `http://llm:8081/v1` | URL base da API |
| `LLM_API_KEY` | *(vazio)* | Chave, se o provedor exigir |
| `LLM_MODEL` | `gemma-4-e4b-it` | Nome do modelo (= `LLM_ALIAS` do llm-server) |
| `LLM_JSON_MODE` | `none` | Ver §3 |
| `LLM_EXTRA_BODY` | `{}` | JSON mesclado no corpo (ex.: `{"chat_template_kwargs":{"enable_thinking":false}}`) |
| `LLM_STRIP_THINKING` | `true` | Remover raciocínio da resposta |
| `LLM_TEMPERATURE` | `0.7` | Padrão; os prompts podem sobrescrever |
| `LLM_MAX_TOKENS` | `2000` | Limite de saída |
| `LLM_CONTEXT_TOKENS` | `4096` | Para o orçamento de prompt |
| `LLM_TIMEOUT_S` | `300` | Inclui espera na fila do llm-server |
| `LLM_MAX_CONCURRENCY` | `1` | Requisições simultâneas do Maná |
| `LLM_MAX_RETRIES` | `3` | Tentativas por geração |
| `LLM_SENDS_PERSONAL_DATA` | `true` | **Precisa ser decisão explícita** ao apontar para provedor externo (ver `PRIVACIDADE_LGPD.md`) |

Perfis prontos em `infra/llm-profiles/` (`llm-server-gemma.env`, `llm-server-qwen.env`, `ollama.env`,
`openai-compatible-externo.env`) para trocar copiando um arquivo.

## 5. Comando de verificação

`python -m app.cli llm-check [--env-file infra/.env] [--saida json]` → chama `health`, gera um estudo de teste
fixo (Salmos 23.1, prompt `server/prompts/llm_check.md`, schema `StudyLlmOutput`) e mostra provedor, modelo,
tempo, tentativas, tokens, erros das tentativas e o estudo. Usar sempre que trocar de provedor/modelo.

- No contêiner: `distrobox-host-exec podman compose -f infra/compose.yaml run --rm --no-deps api python -m app.cli llm-check`
- No host (sem contêiner): `cd server && LLM_BASE_URL=http://127.0.0.1:8081/v1 LLM_MODEL=gemma-4-e4b-it
  BLIVRE_SQLITE_PATH=../tools/biblia/build/blivre.sqlite uv run python -m app.cli llm-check`

### Resultado da verificação (2026-10-31, estudo de teste Salmos 23.1, mesmo código, só `.env` trocado)

| Perfil | `LLM_JSON_MODE` | Tempo | Tentativas | Tokens (entrada+saída) | Observação |
|---|---|---|---|---|---|
| `llm-server-gemma` (Gemma 4 E4B, raciocínio) | `none` | 89 s | 1 | ~720 + 1.521 (inclui raciocínio) | 1ª versão da dica de schema: 208 s / 2 tentativas (o modelo copiou o `$defs` do schema; corrigido expandindo as `$defs`). Também fechou uma lista com `}` → reparo de delimitadores |
| `llm-server-qwen` (Qwen3 4B, contêiner de teste) | `json_schema` | 49 s | 1 | 391 + 693 | Citou o versículo entre aspas no corpo → a validação de conteúdo da 3.7 precisa barrar |

Orçamento: com o Gemma, raciocínio + resposta usaram ~1.500 dos 2.000 `max_tokens`. Prompts maiores
(estudo real com citação e datas especiais) devem ficar ≤ 1.800 tokens de entrada, como previsto.

### Erros reais do Gemma tratados pelo reparo de JSON (2026-11-01, `app/llm/parsing.py`)
- lista fechada com `}` em vez de `]`; objeto principal fechado cedo (`...]}, "application": ...`);
- aspas sem escape dentro de texto (`a ideia de que "nada nos faltará" pode...`);
- `application`/`prayer` como lista de uma frase (o schema junta);
- cópia do `$defs` do schema (a dica agora expande as definições).
Todos têm teste com o trecho real. Reparos só sintáticos: nunca mudam o conteúdo gerado.

### LLM de teste separada
`infra/llm-teste/compose.yaml` sobe um llama.cpp **independente** (Qwen3 4B, `mana-llm-teste`, porta 127.0.0.1:8082,
na `llm-net`) para validar a troca de provedor sem mexer no llm-server compartilhado. Desligar depois do teste.

O estudo e o "Para você" gravam `model` e `provider` usados, para comparar qualidade entre LLMs.
