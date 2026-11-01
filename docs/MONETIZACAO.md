# Monetização

## 1. Modelo
- **Gratuito**: todo o estudo diário, leitor bíblico, histórico, favoritos — com anúncios AdMob.
- **Premium (assinatura mensal)**: sem anúncios + seção diária **"Para você"** baseada nos detalhes
  que o usuário fornece. Preço e teste grátis: ❓ (DECISOES M5).

## 2. AdMob

- SDK Google Mobile Ads + **UMP** (formulário de consentimento; necessário para usuários do EEE/Reino Unido
  e boa prática no geral). Inicializar o SDK só após o fluxo de consentimento.
- Formatos (🟡): banner adaptativo ancorado no fim da tela "Hoje" e no "Histórico".
  **Sem intersticiais e sem anúncios no leitor bíblico.**
- Debug sempre com **IDs de teste** do Google; IDs reais via `local.properties` → `BuildConfig`/`manifestPlaceholders`.
- Registrar dispositivos de teste. Nunca clicar nos próprios anúncios reais.
- `app-ads.txt` publicado no domínio do desenvolvedor informado na Play Console (DECISOES S7).
- Classificação de conteúdo dos anúncios: limitar a categorias adequadas (ex.: bloquear apostas,
  namoro, conteúdo sexual) no painel do AdMob — [manual].
- `AdsGate`: componente único que decide se mostra anúncio (`!isPremium && consentOk`). Premium nunca
  carrega o SDK de anúncios na sessão (evita requisições desnecessárias).

## 3. Assinatura (Google Play Billing)

- Produto: `mana_premium`, plano base `mensal` (renovação automática). Opcional: oferta de teste grátis.
- Fluxo no app:
  1. `BillingClient` conecta; consulta `ProductDetails` para mostrar preço localizado.
  2. Usuário assina → `PurchasesUpdatedListener` recebe o `purchaseToken`.
  3. App envia `POST /v1/subscriptions/google-play/verify` → servidor verifica e **confirma (acknowledge)**.
     (Compra não confirmada em 3 dias é reembolsada automaticamente.)
  4. App atualiza estado a partir da resposta do servidor.
- `obfuscatedAccountId` = hash do `user.id` — vincula a compra ao usuário do servidor.
- Ao abrir o app: `queryPurchasesAsync` + `GET /subscriptions/status` (restaura em novo aparelho).
- Estados tratados: ativo, cancelado (ativo até expirar), período de carência, suspensão (account hold),
  pausado, expirado, reembolsado.

### Servidor
- Conta de serviço com acesso à Play Developer API — [manual] (Play Console → Usuários e permissões).
- `purchases.subscriptionsv2.get` → grava `status`, `expires_at`, `auto_renewing`, `last_verified_at`.
- `is_premium` = status em {ativo, carência, cancelado-ainda-vigente}. Reverificar quando `expires_at`
  passar ou a cada 24 h no acesso.
- Fase futura: **RTDN** (Pub/Sub push) para refletir cancelamentos/reembolsos em tempo real.

## 4. Testes
- Licenciados para teste na Play Console (compras sem cobrança; renovação acelerada).
- Billing só funciona com o app instalado a partir de uma faixa de teste da Play (teste interno).
- Casos: assinar, cancelar, restaurar, trocar de aparelho, reembolso, logout/login com outra conta.

## 5. Requisitos da Play Store (verificar regras atuais antes da publicação)
- Política de privacidade pública; formulário de **Segurança dos dados** coerente com o app
  (login Google, ID de publicidade, dados do perfil premium).
- Declaração de uso do ID de publicidade; público-alvo (não direcionado a crianças).
- Contas pessoais novas exigem **teste fechado** com um número mínimo de testadores por um período
  antes da produção — confirmar números atuais na Play Console.
