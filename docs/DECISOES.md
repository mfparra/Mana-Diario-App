# Decisões

Legenda de status:

- ✅ **Definido** — decidido pelo Marcos.
- 🔁 **Herdado do web** — vale o que o site Maná Diário já faz; **confirmar na Fase 0** lendo o projeto web.
- 🟡 **Proposto** — escolha padrão deste plano; pode ser trocada sem grande custo até a fase indicada.
- ❓ **Pendente** — precisa de resposta do Marcos antes da fase indicada.

Ao mudar o status de uma decisão, registre data e motivo na coluna "Notas".

**Precedência:** requisitos do Marcos (✅) sempre vencem. O site web só preenche lacunas (🔁) —
o app é muito mais completo e não deve ser limitado ao que o site faz.

## Produto

| # | Decisão | Status | Notas |
|---|---|---|---|
| P1 | App Android é o carro-chefe, com mais funções que o site | ✅ | |
| P2 | Estudo diário baseado em um versículo da BLIVRE | ✅ | |
| P3 | Página do estudo mostra: nome "Maná Diário" + logo do maná, frase curta, versículo complementar, palavras-chave | ✅ | Logo em `docs/assets/logo-mana.svg` (mesmo do site) |
| P4 | Referência visual: layout do devocional em `docs/assets/referencia-design.png` | ✅ | Adaptado para coluna única no celular — ver `DESIGN.md` |
| P5 | Leitor bíblico integrado, usável sozinho ou aberto ao tocar numa referência do estudo | ✅ | |
| P6 | Datas especiais: Páscoa e móveis (ex.: Corpus Christi), Natal, Dia das Mães, Dia dos Pais | 🔁 | Definido no site; reaproveitar o mesmo calendário |
| P7 | Acervo de versículos que dure mais de um ano | 🔁 | Reaproveitar o banco do site |
| P8 | **"Pequena frase"** = citação curada (caixa escura, com autor), como no site | 🟡 | Interpretação deste plano. Alternativa: frase-síntese gerada pela LLM **além** da citação curada. Confirmar até a Fase 3 |
| P9 | **Versículo complementar**: servidor oferece candidatos (referências cruzadas) e a LLM escolhe um; servidor valida | 🟡 | Se o site já resolve isso, herdar. Fonte de candidatos sugerida: referências cruzadas do OpenBible.info (CC BY) — confirmar licença |
| P10 | Seções extras geradas: "aplicação prática" e "oração" curta | 🟡 | Herdar do site se ele tiver estrutura diferente |
| P11 | Funções extras do app: histórico, favoritos, compartilhar como imagem, notificação diária em horário escolhido | 🟡 | Widget, áudio (TTS) e planos de leitura ficam para a fase futura |
| P12 | **Espaço de anotações pessoais em cada devocional do dia** | ✅ | 2026-10-31 — detalhes na seção "Anotações" |

## Bíblia

| # | Decisão | Status | Notas |
|---|---|---|---|
| B1 | Tradução: Bíblia Livre (BLIVRE), salva localmente | ✅ | |
| B2 | Mesmo arquivo-fonte da BLIVRE usado no site | 🔁 | Fase 0 localiza arquivo, formato e versão |
| B3 | Um único `blivre.sqlite` gerado por script, usado pelo servidor e embarcado no app | 🟡 | Evita divergência de texto entre servidor e app |
| B4 | Códigos de livro USFM internamente | 🟡 | |
| B5 | Texto de atribuição/licença da BLIVRE na tela "Sobre" | 🔁 | Confirmar licença e texto exatos na fonte usada |

## Conteúdo / LLM

| # | Decisão | Status | Notas |
|---|---|---|---|
| L1 | Tudo que não é versículo é gerado pela LLM, exceto citações curadas | ✅ | |
| L2 | LLM atual: llm-server do CacaPalavras2 (llama.cpp, API OpenAI-compatível, rede `llm-net`) | ✅ | Compartilhado com o BuscaPalavras; hoje Gemma 4 E4B com thinking, ctx 4096, 1 req. por vez |
| L3 | Versão final usará uma LLM mais confiável | ✅ | |
| L9 | **O servidor deve poder apontar para qualquer servidor LLM** só por configuração | ✅ | 2026-10-31. Adaptador `LlmClient`; padrão OpenAI-compatível; ver `LLM_SERVER.md` |
| L10 | JSON robusto sem depender de `response_format` (Gemma 4 devolve vazio com `json_object`) | 🟡 | `LLM_JSON_MODE` configurável + extração/validação + nova tentativa |
| L11 | Lotes de geração de madrugada, 1 requisição por vez, para não travar o BuscaPalavras | 🟡 | |
| L4 | Prompts, tom teológico e regras de conteúdo | 🔁 | Partir dos prompts do site e adaptar para o schema do app |
| L5 | Banco de citações curadas e regras de uso (repetição, autores) | 🔁 | Importar do site |
| L6 | Saída da LLM sempre em JSON validado por schema; até 3 tentativas; depois fallback | 🟡 | |
| L7 | Estudo geral pré-gerado com 7 dias de antecedência pelo worker | 🟡 | Dá margem para falhas do llm-server |
| L8 | Estudos publicados automaticamente após validação (sem revisão humana obrigatória) | ❓ | Alternativa: fila de aprovação no painel admin. Definir até a Fase 3 |

## Servidor

| # | Decisão | Status | Notas |
|---|---|---|---|
| S1 | API REST controla o estudo diário; app mantém cache | ✅ | |
| S2 | Stack: FastAPI + PostgreSQL + Alembic | 🟡 | Se o site usa outra stack, perguntar se o app deve seguir a mesma |
| S3 | Servidor do app = mesmo backend que gera o estudo do site? | ❓ | Recomendado: **uma única fonte** do estudo do dia, consumida por site e app. Definir até a Fase 2 |
| S4 | **Servidor inteiro em contêineres Podman** (`api`, `worker`, `db`, `proxy`) com podman compose; testar local e depois levar ao servidor definitivo | ✅ | 2026-10-31: explicitado como regra no AGENTS.md |
| S4a | Imagens rootless a partir de `Containerfile` (multi-stage, usuário não-root, `uv` para dependências) | 🟡 | |
| S4b | Produção com `podman compose` + `restart: always` (como o llm-server) | 🟡 | Alternativa: Quadlet/systemd para subir com o boot sem sessão aberta — avaliar na Fase 10 |
| S4c | Dados persistentes só em volumes nomeados (`mana-pgdata`, `mana-caddy`); `blivre.sqlite` dentro da imagem ou volume somente leitura | 🟡 | |
| S5 | HTTPS em produção via Caddy (contêiner `proxy`) | 🟡 | Herdar a solução do site se já houver |
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

## Herdado do web — checklist da Fase 0

Usar **apenas** para pontos que os requisitos acima não definem.

Preencher após ler o projeto web (caminho: `<INFORMAR>`):

- [ ] Arquivo e formato da BLIVRE, versão, licença e texto de atribuição
- [ ] Banco de versículos (formato, tamanho, como evita repetição)
- [ ] Calendário de datas especiais (como calcula Páscoa e móveis; quais datas)
- [ ] Banco de citações curadas (formato, campos, regras)
- [ ] Prompts e parâmetros da LLM (temperatura, tamanho, tom)
- [ ] Estrutura do estudo exibido no site (seções)
- [ ] Stack do servidor, banco de dados, agendamento da geração
- [ ] Cores e fontes do site
- [ ] Hospedagem/HTTPS/domínio e como o podman compose roda no distrobox
