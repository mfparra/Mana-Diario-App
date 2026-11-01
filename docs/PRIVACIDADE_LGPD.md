# Privacidade e LGPD

> Não é parecer jurídico. Antes da publicação, revisar a política de privacidade com atenção
> (idealmente com alguém da área).

## 1. Dados coletados

| Dado | Origem | Finalidade | Base legal provável |
|---|---|---|---|
| ID Google (`sub`), nome, e-mail, foto | Login Google | Conta e login | Execução de contrato |
| Preferências (horário, tema) | App | Funcionamento | Execução de contrato |
| Status da assinatura, token de compra (hash) | Play Billing | Premium | Execução de contrato |
| ID de publicidade | SDK AdMob | Anúncios (gratuito) | Consentimento / legítimo interesse — conforme UMP |
| **Perfil premium** ("Sobre você") | Usuário | Texto "Para você" | **Consentimento específico e destacado** |
| **Anotações dos devocionais** | Usuário | Guardar e sincronizar entre aparelhos | Execução de contrato; podem conter dados sensíveis → criptografadas, nunca enviadas à LLM |
| Favoritos, destaques, marcações | App (local) | Funcionamento | Ficam só no aparelho (sem sync nesta versão) |

O perfil premium revela **convicção religiosa** e pode conter dados de saúde ou família —
**dados pessoais sensíveis** (LGPD art. 5º, II). Exige consentimento específico (art. 11, I).

## 2. Perfil premium — campos (🟡 confirmar)

Todos opcionais, com limite de caracteres e texto de ajuda:

| Campo | Tipo | Limite |
|---|---|---|
| `preferred_name` | texto | 40 |
| `life_stage` | opção (estudante, trabalhando, aposentado, pai/mãe…) | — |
| `current_challenges` | texto livre | 500 |
| `prayer_requests` | texto livre | 500 |
| `interests` | multiescolha (família, trabalho, ansiedade, gratidão, fé, relacionamentos…) | até 5 |
| `faith_journey` | opção (conhecendo a fé, caminhando há algum tempo, liderança…) | — |
| `tone` | opção (acolhedor, encorajador, reflexivo, direto) | — |

Na tela: aviso claro antes de salvar — "Essas informações serão usadas somente para gerar seu texto
'Para você'. Evite incluir dados de terceiros ou informações que não queira compartilhar."

## 3. Regras técnicas
- Consentimento: caixa não marcada por padrão + texto versionado (`consent_version`) + data registrada.
  Revogar consentimento = apagar perfil e textos personalizados.
- Criptografia do perfil em repouso (chave fora do banco); descriptografar só em memória no momento da geração.
- Nunca registrar em log o perfil nem o prompt personalizado.
- O llm-server é infraestrutura própria — os dados não saem dela. Como o servidor pode apontar para
  **qualquer** LLM, há a chave `LLM_SENDS_PERSONAL_DATA`: ao trocar para LLM externa, ela só fica `true`
  depois de avaliar contrato, retenção do provedor e transferência internacional, e atualizar a política.
- Anotações: criptografadas em repouso, nunca registradas em log, nunca enviadas à LLM; tombstones
  limpos após 30 dias; incluídas no export; apagadas com a conta.
- Retenção: `personal_studies` por 90 dias (🟡); conta excluída → tudo apagado em até 24 h
  (backups expiram no ciclo normal, documentado).
- Direitos do titular no app: ver/editar/apagar perfil, exportar dados (`GET /me/export`), excluir conta.
  Exclusão de conta também acessível por página web (exigência da Play Store).

## 4. Segurança emocional
Se o perfil contiver sinais de risco (suicídio, autolesão), não gerar devocional personalizado
e exibir mensagem acolhedora com o **CVV — 188** (ligação gratuita, 24 h) e **cvv.org.br**.
Ver `CONTEUDO_E_LLM.md` §7.

## 5. Documentos públicos necessários
- Política de privacidade (URL pública — pode ficar no site Maná Diário).
- Termos de uso (assinatura, cancelamento pela Play Store, conteúdo gerado por IA).
- Aviso no app: "Os estudos são gerados com auxílio de inteligência artificial a partir de versículos
  da Bíblia Livre" (transparência).
