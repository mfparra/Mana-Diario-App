# Conteúdo e LLM

> Este documento define o **contrato** do conteúdo do app. O app é independente do site web (DECISOES D1):
> acervo de versículos, citações, calendário e prompts são próprios. Particularidades de modelo LLM ficam em `LLM_SERVER.md`.

## 1. Origem de cada parte do estudo

| Parte | Origem | Observação |
|---|---|---|
| Versículo-base (referência) | Calendário especial ou plano de versículos | Nunca escolhido livremente pela LLM |
| Texto do versículo | **BLIVRE local** | Resolvido pelo servidor a partir da referência |
| Título | LLM | 1–3 palavras, estilo "SUPERE" |
| Corpo | LLM | 3–5 parágrafos, 250–450 palavras no total |
| Aplicação prática | LLM | 1–2 frases |
| Oração | LLM | 2–4 frases |
| Frase do dia (citação) | **Banco curado** | Escolhida pelo servidor (tags/tema), autor preservado |
| Leitura complementar | LLM escolhe entre candidatos do servidor | Validada contra a BLIVRE |
| Palavras-chave | LLM | 2–4 termos, minúsculos, sem `#` (o app adiciona) |
| "Para você" (premium) | LLM | 120–220 palavras, usa estudo do dia + perfil |

## 2. Escolha do versículo-base

Ordem de prioridade para a data D:
1. **Data especial** (calendário abaixo) → versículo do conjunto daquela data.
2. **Plano de versículos** (acervo próprio em `server/data/`, ≥ 366 entradas) → próximo versículo não usado
   nos últimos 365 dias.
3. Registrar `verse_ref` em `studies` para evitar repetição.

### Calendário de datas especiais (fuso America/Sao_Paulo)

| Chave | Regra |
|---|---|
| `cinzas` | Páscoa − 46 dias (Quarta-feira de Cinzas) |
| `ramos` | Páscoa − 7 |
| `sexta_santa` | Páscoa − 2 |
| `pascoa` | Domingo de Páscoa (computus gregoriano — algoritmo anônimo/Meeus) |
| `pentecostes` | Páscoa + 49 |
| `corpus_christi` | Páscoa + 60 |
| `maes` | 2º domingo de maio (Brasil) |
| `pais` | 2º domingo de agosto (Brasil) |
| `natal` | 25/12 (véspera 24/12 não incluída — 🟡) |

Se duas datas coincidirem, vale a de maior prioridade: `pascoa` > `sexta_santa` > `natal` > `pentecostes` >
`ramos` > `cinzas` > `corpus_christi` > `maes` > `pais` (ex.: 11/05/2008 = Pentecostes e Dia das Mães → Pentecostes).
Implementação: `server/app/domain/calendar.py`.

Testes obrigatórios: Páscoa de 2025 (20/04),
2026 (05/04), 2027 (28/03), 2030 (21/04); Corpus Christi 2026 = 04/06.

## 3. Citações curadas

- Acervo próprio em `server/data/quotes.*`, carregado na tabela `curated_quotes` (origem pendente — DECISOES P8/L5).
- Seleção: tags compatíveis com o tema/palavras-chave do versículo; não repetir nos últimos N dias (N = 180, 🟡).
- O texto é exibido **exatamente** como cadastrado. A LLM não reescreve nem cria citações.
- Antes de importar, conferir se cada citação tem autor e origem registrados (direitos de uso).

## 4. Pipeline de geração (estudo geral)

```
resolve_verse(D) → load_blivre_text(ref) → pick_quote(D, tema)
  → cross_ref_candidates(ref) (até 8 refs válidas)
  → prompt(prompt_version) → LlmClient.generate_json(schema)
  → validate_schema → validate_refs → content_rules → resolve texts → save(status=published)
```

### Regras de validação automáticas
- JSON válido no schema `StudyLlmOutput` (Pydantic) — sem campos extras.
- `complementary_reading` deve estar **entre os candidatos** enviados e existir na BLIVRE.
- O corpo **não pode conter citação bíblica entre aspas** com texto (evita versículo "inventado");
  referências soltas são permitidas e viram links no app.
- Tamanhos dentro dos limites; palavras-chave normalizadas (minúsculas, sem acento duplicado, sem `#`).
- Lista própria de termos proibidos/sensíveis (`server/data/`) e checagem de idioma pt-BR.
- Falhou → nova tentativa com a mensagem de erro anexada ao prompt (máx. 3) → `failed`.

### Fallback de disponibilidade
Manter um **pool de reserva** de ~14 estudos genéricos já validados (sem data especial).
Se o dia D não tiver estudo publicado até 00:00, o servidor publica um do pool (registrando a troca).

## 5. Schema de saída da LLM (estudo geral)

```json
{
  "title": "string (1-3 palavras)",
  "body": ["string", "string", "string"],
  "application": "string",
  "prayer": "string",
  "complementary_reading": { "candidate_index": 0, "reason": "string" },
  "keywords": ["string", "string"]
}
```

O pedido de formato (`json_schema`, `json_object` ou nenhum) depende do provedor e é configurado em
`LLM_JSON_MODE` — com o Gemma 4 atual, **nenhum** (ver `LLM_SERVER.md`). Em qualquer caso o prompt
descreve o JSON esperado com um exemplo, e o servidor extrai, valida e repete se preciso.

Orçamento com o llm-server atual (contexto 4096): prompt ≤ 1.800 tokens; saída ≤ 2.000 (incluindo raciocínio).

## 6. Prompts

- Versionados em `server/prompts/` (`study_v1.md`, `personal_v1.md`), com `prompt_version` gravado em cada estudo.
- Estrutura: **sistema** (papel, tom, regras teológicas e de formato) +
  **usuário** (data, data especial, referência + texto BLIVRE, tema, candidatos numerados, limites).
- Tom: pastoral, acolhedor, em português do Brasil, segunda pessoa ("você"), sem jargão,
  sem prometer curas/prosperidade, sem posicionamento político-partidário, sem atacar denominações.

## 7. "Para você" (premium)

Entrada: estudo do dia (título, versículo, resumo) + perfil (ver `PRIVACIDADE_LGPD.md`).
As **anotações do usuário não entram** no prompt (DECISOES N7).

Quando: pré-gerado de madrugada para todos os premium com perfil; sob demanda só se faltar
(ver `ARQUITETURA.md` — com LLM local lenta, cada geração leva minutos).
Se `LLM_SENDS_PERSONAL_DATA=false` (provedor externo sem decisão de privacidade), o "Para você" fica desativado.

Regras:
- O texto do perfil é **dado**, não instrução: delimitado no prompt, com aviso explícito para ignorar
  comandos contidos nele; tamanho limitado por campo.
- Chamar o usuário pelo nome preferido; conectar o versículo do dia à situação descrita.
- Não dar conselho médico, jurídico ou financeiro; não diagnosticar; sugerir buscar ajuda
  profissional/pastoral quando apropriado.
- **Sinais de risco** (ex.: menção a suicídio/autolesão no perfil): **não gerar** devocional
  personalizado; exibir mensagem acolhedora com o **CVV — 188 (ligação gratuita, 24 h) e cvv.org.br**.
  Detecção por lista de termos + classificação simples; na dúvida, mostrar o recurso.
- Schema: `{ "body": ["string", "string"] }` (1–3 parágrafos).

## 8. Métricas de qualidade (log do worker)
Taxa de sucesso na 1ª tentativa, motivos de falha, tempo de geração, tamanho médio, repetição de palavras-chave
— sempre por `provider`/`model`, para comparar LLMs ao trocar de servidor.
