# Perfis de LLM

Cada arquivo tem só as variáveis `LLM_*`. Para trocar de provedor/modelo, copie o bloco para o `infra/.env`
(substituindo as `LLM_*` que estiverem lá), recrie `api`/`worker` e rode o `llm-check`:

    distrobox-host-exec podman compose -f infra/compose.yaml -f infra/compose.dev.yaml up -d api worker
    distrobox-host-exec podman compose -f infra/compose.yaml run --rm --no-deps api python -m app.cli llm-check

| Perfil | Uso |
|---|---|
| `llm-server-gemma.env` | llm-server compartilhado como está hoje (Gemma 4 E4B com raciocínio). **Padrão.** |
| `llm-server-qwen.env` | Mesmo servidor rodando Qwen3 4B (exige trocar o modelo do llm-server — avaliar o BuscaPalavras antes) ou o contêiner de teste `infra/llm-teste/`. |
| `ollama.env` | Ollama local (`ollama serve`) |
| `openai-compatible-externo.env` | Qualquer API externa compatível com OpenAI (OpenRouter, OpenAI, vLLM remoto...). **Antes de usar:** decidir `LLM_SENDS_PERSONAL_DATA` (PRIVACIDADE_LGPD). |
