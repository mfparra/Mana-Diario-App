# AGENTS.md — Maná Diário (app Android + API)

> Arquivo de instruções do projeto para agentes de código (Claude Code e outros).
> O `CLAUDE.md` apenas importa este arquivo. **Edite aqui**, não lá.

## 1. O que é o projeto

**Maná Diário** é o carro-chefe da família Maná Diário: um app Android que entrega, todo dia,
um estudo bíblico curto construído em torno de **um versículo da Bíblia Livre (BLIVRE)**,
com um leitor bíblico completo e offline integrado.

- **App e site web Maná Diário são projetos independentes** (decisão de 2026-10-31). Nada é lido,
  importado ou reaproveitado do projeto web: Bíblia, acervo de versículos, citações, calendário, prompts
  e servidor são próprios deste repositório. **Ordem de precedência:** (1) o que está escrito nestes
  docs/requisitos do Marcos → (2) perguntar ao Marcos.
- Funções do app: leitor bíblico, **anotações pessoais em cada devocional**,
  histórico, favoritos, notificação diária, login Google, plano pago com estudo personalizado.
- Monetização: **gratuito com Google AdMob** + **assinatura mensal** (Google Play Billing) que
  remove anúncios e libera a seção personalizada **"Para você"**.

Documentos de referência (leia o que for relevante antes de cada tarefa):

| Documento | Conteúdo |
|---|---|
| `docs/PLANO.md` | Fases e tarefas com critérios de aceite. **É a fila de trabalho.** |
| `docs/DECISOES.md` | Decisões: definidas, herdadas do web, propostas e pendentes. |
| `docs/ARQUITETURA.md` | Visão geral, monorepo, servidor, app, dados, cache, segurança. |
| `docs/API.md` | Contrato REST v1 (endpoints, payloads, erros). |
| `docs/CONTEUDO_E_LLM.md` | Estrutura do estudo, calendário, prompts, validações, guardrails. |
| `docs/LLM_SERVER.md` | Integração com o llm-server compartilhado e regras para alterá-lo. |
| `docs/DESIGN.md` | Identidade visual, tokens, telas, componentes. |
| `docs/MONETIZACAO.md` | AdMob, assinatura, entitlement, verificação no servidor. |
| `docs/PRIVACIDADE_LGPD.md` | Dados sensíveis, consentimento, exclusão, retenção. |
| `docs/assets/` | `logo-mana.svg` (logo oficial) e `referencia-design.png` (referência de layout). |

## 2. Regras de ouro (não negociáveis)

1. **O texto bíblico nunca é gerado pela LLM.** Todo versículo exibido vem da base BLIVRE local,
   buscado por referência. A LLM só pode *sugerir referências*, que o servidor valida contra a base.
2. **Citações curadas nunca são geradas pela LLM.** Vêm do banco curado próprio do app
   (`server/data/`), com autor/fonte preservados exatamente.
3. **Todo o resto do estudo é gerado pela LLM** do llm-server (título, corpo, aplicação, palavras-chave,
   texto personalizado "Para você"), sempre em **JSON validado por schema**.
4. **O servidor é a fonte da verdade do estudo do dia.** O app só exibe e mantém **cache** (Room).
   O app funciona offline com o que já está em cache e com a Bíblia embarcada.
5. **Dados do perfil premium são sensíveis** (convicção religiosa = dado sensível na LGPD).
   Criptografar em repouso, nunca logar, nunca enviar a terceiros sem decisão registrada.
6. **LLM trocável por configuração.** O servidor fala com **qualquer** servidor LLM: hoje o llm-server
   compartilhado (llama.cpp, API compatível com OpenAI); amanhã outro. Nada de código específico de um
   modelo fora do adaptador `LlmClient` — URL, modelo, chave e capacidades vêm do `.env`
   (ver `docs/LLM_SERVER.md`). O llm-server também atende o BuscaPalavras: não mudar o modelo
   ou parâmetros dele sem avaliar esse impacto.
7. **Segredos fora do git.** `.env`, `google-services.json`, chaves de serviço, keystores,
   IDs reais de AdMob ficam fora do repositório (há `.env.example` / `local.properties`).
8. **Quando algo não estiver claro** (e só então): **pare e pergunte ao Marcos** em vez de inventar —
   e registre como "Pendente" em `docs/DECISOES.md`. Não consultar o projeto web.
9. **Anotações do usuário são dele.** A anotação de cada devocional funciona offline, sincroniza com o
   servidor, é criptografada em repouso e nunca é enviada à LLM sem decisão registrada.
10. **Todo o servidor roda em contêineres Podman** — `api`, `worker`, `db` (PostgreSQL) e `proxy` (Caddy),
   orquestrados por `podman compose`, em desenvolvimento e em produção. Nada é instalado direto no host
   além do Podman. Imagens próprias via `Containerfile`, rootless, com `restart: always` e healthcheck
   (mesmo padrão do llm-server).

## 3. Stack

**App Android** (`android/`)
- Kotlin, Jetpack Compose, Material 3, MVVM + UDF (StateFlow), Hilt
- Navigation Compose (rotas tipadas), Room (cache + Bíblia pré-empacotada), DataStore
- Retrofit + OkHttp + kotlinx.serialization, WorkManager (sync e notificação)
- Credential Manager + Google ID (login Google), Google Play Billing, Google Mobile Ads + UMP
- Pacote: `com.marcosparra.manadiario`

**Servidor** (`server/`)
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, PostgreSQL 16
- Worker de geração (agendador) em contêiner separado
- LLM via adaptador `LlmClient` (padrão: cliente HTTP para API compatível com OpenAI, `httpx`);
  em desenvolvimento aponta para `http://llm:8081/v1` na rede externa `llm-net`
- `pytest` + `pytest-asyncio`; `ruff` para lint/format
- Podman + `podman compose` (testes locais primeiro, depois servidor definitivo)

**Dados bíblicos** (`tools/biblia/`)
- Script que importa a BLIVRE e gera **um único** `blivre.sqlite`, usado pelo servidor (somente leitura)
  e embarcado no app como banco pré-empacotado do Room.

## 4. Estrutura do repositório

```
mana-diario-app/
├── AGENTS.md / CLAUDE.md / README.md
├── docs/                 # planos, contratos, design, decisões
├── android/              # app (Gradle, módulo :app — modularizar só se necessário)
├── server/
│   ├── app/              # FastAPI: api/, core/, domain/, services/, db/
│   ├── worker/           # agendador de geração
│   ├── prompts/          # prompts versionados (.md/.j2)
│   ├── data/             # banco de versículos, citações curadas, calendário (fonte versionada)
│   ├── migrations/       # Alembic
│   └── tests/
├── tools/biblia/         # importador BLIVRE → blivre.sqlite (+ testes)
└── infra/                # compose.yaml, Caddyfile, .env.example
```

## 5. Ambiente e comandos

- O Claude Code roda **dentro de um distrobox**; use o Podman do host: `distrobox-host-exec podman ...`
  (confirmado em 2026-10-31: Podman 5.8, provedor compose = Docker Compose v5 do host).
- Servidor: `cd server && uv run pytest` / `uv run ruff check . && uv run ruff format --check .`;
  rodar local sem contêiner: `uv run uvicorn app.main:app --port 8000` → `curl localhost:8000/v1/health`
- Testes de banco: `server/scripts/test-db.sh up` (Postgres descartável em 127.0.0.1:55432) e
  `TEST_DATABASE_URL=postgresql+psycopg://mana:mana@127.0.0.1:55432/mana_test uv run pytest`; sem a variável, são pulados.
- Migrações: `DATABASE_URL=... uv run alembic upgrade head`; nova revisão:
  `uv run alembic revision --autogenerate -m "..."` (revisar o arquivo gerado).
- Imagens (contexto = raiz do repo): `distrobox-host-exec podman build --format docker -f server/Containerfile --target api -t localhost/mana-api:dev .`
  (idem `--target worker`). `--format docker` é necessário para o `HEALTHCHECK` ser mantido.
- Subir stack local (gera antes o `tools/biblia/build/blivre.sqlite`; `infra/.env` a partir do `.env.example`):
  `distrobox-host-exec podman compose -f infra/compose.yaml -f infra/compose.dev.yaml up -d --build`
  → `curl 127.0.0.1:8000/v1/health` deve mostrar `db: ok` e `llm: ok`. Parar: `... compose -f infra/compose.yaml down`.
  Produção: sem o `compose.dev.yaml` e com `--profile prod` (Caddy/HTTPS).
- Gerar estudo manualmente: `uv run python -m app.cli gerar --data AAAA-MM-DD`
- Bíblia: `cd tools/biblia && uv run python importar_blivre.py` (padrão: `fonte/porbr2018_usfm.zip` → `build/blivre.sqlite`);
  testes `uv run pytest`; lint `uv run ruff check . && uv run ruff format --check .`;
  conferir/atualizar a fonte: `uv run python baixar_fonte.py`. Pacote `blivre` (parser de referências) é reutilizado pelo servidor.
- App: `cd android && ./gradlew assembleDebug testDebugUnitTest lint`
- llm-server (compartilhado): `/home/marcos/OneDriveLocalSync/LinguagensProgramacao/Android/CacaPalavras2/llm-server`
  — contêiner `llm` (llama.cpp), `curl 127.0.0.1:8081/health`; o compose do Maná entra na rede `llm-net`.
- Testar outro provedor LLM: trocar só as variáveis `LLM_*` do `infra/.env` e rodar `uv run python -m app.cli llm-check`.

(Ajuste esta seção quando os comandos reais existirem — ela deve refletir a realidade.)

## 6. Como trabalhar

1. Pegue **a próxima tarefa não concluída** de `docs/PLANO.md` cujas dependências estejam prontas
   (atalho: `/proxima-tarefa`).
2. Antes de codar, escreva um plano curto (arquivos a criar/alterar, testes). Se a tarefa tocar uma
   decisão "Pendente", pergunte primeiro.
3. Implemente em passos pequenos; rode testes e lint a cada passo.
4. Ao terminar: marque o checkbox no `PLANO.md`, atualize docs afetados (API, DECISOES, este arquivo)
   e faça um commit pequeno e descritivo (em português, imperativo: "Adiciona importador BLIVRE").
5. Tarefas marcadas **[manual]** dependem do Marcos (consoles Google, contas, chaves).
   Prepare tudo o que der e liste exatamente o que ele precisa fazer.

**Definição de pronto:** compila, testes passam, lint limpo, critérios de aceite do PLANO atendidos,
docs atualizados, nenhum segredo commitado.

## 7. Convenções

- Código, identificadores e campos JSON da API em **inglês**; docs, commits, textos de UI e
  prompts em **português do Brasil**.
- Strings de UI sempre em `strings.xml` (nada hardcoded em Compose).
- Datas: o "dia" do estudo segue `America/Sao_Paulo`; datas em ISO-8601 (`AAAA-MM-DD`).
- Referências bíblicas internas usam códigos **USFM** de livro (`GEN`, `PSA`, `1CO`…);
  nomes em português só na apresentação.
- API versionada em `/v1`; mudanças incompatíveis exigem `/v2`.
- Kotlin: ViewModels sem referência a Context; repositórios expõem `Flow`; erros via `Result`/sealed class.
- Python: camadas `api → services → domain/db`; nada de lógica de negócio nos routers.

## 8. O que NÃO fazer

- Não gerar, "corrigir" ou parafrasear texto bíblico com a LLM; não exibir versículo sem passar pela base.
- Não inventar citações nem atribuir frases a pessoas reais fora do banco curado.
- Não usar IDs reais de AdMob em builds de debug (use os IDs de teste do Google).
- Não confiar no app para dizer se o usuário é premium — **o servidor verifica a compra**.
- Não adicionar dependências pesadas sem registrar o motivo em `docs/DECISOES.md`.
- Não trocar modelo/contexto/paralelismo do llm-server sem avaliar o BuscaPalavras e registrar.
- Não acoplar o código a um modelo específico (ex.: tags de "thinking" do Gemma) fora do adaptador LLM.
