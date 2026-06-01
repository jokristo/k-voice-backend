# Webhooks PayPal — Ecclesiato / K-Voice

Les webhooks mettent à jour automatiquement le statut d’abonnement en base (annulation, suspension, impayé, réactivation) **sans** recharger l’admin.

## URL à enregistrer chez PayPal

| Environnement | URL |
|---------------|-----|
| **Production (Render)** | `https://<votre-api>.onrender.com/billing/webhooks/paypal` |
| **Local (ngrok)** | `https://<sous-domaine>.ngrok-free.app/billing/webhooks/paypal` |

Même chemin que le router FastAPI : préfixe `/billing` + `/webhooks/paypal`.

---

## 1. Créer le webhook dans PayPal (Sandbox d’abord)

1. Ouvrir [PayPal Developer](https://developer.paypal.com/dashboard/) → **Apps & Credentials**.
2. Choisir l’application **Sandbox** qui correspond à votre `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`.
3. Descendre à **Webhooks** → **Add Webhook**.
4. Coller l’URL ci-dessus.
5. Cocher au minimum ces événements :

   - `BILLING.SUBSCRIPTION.ACTIVATED`
   - `BILLING.SUBSCRIPTION.UPDATED`
   - `BILLING.SUBSCRIPTION.CANCELLED`
   - `BILLING.SUBSCRIPTION.SUSPENDED`
   - `BILLING.SUBSCRIPTION.EXPIRED`
   - `BILLING.SUBSCRIPTION.PAYMENT.FAILED`
   - `BILLING.SUBSCRIPTION.RE-ACTIVATED` (si proposé)

6. Enregistrer, puis copier le **Webhook ID** (format `WH-…` ou identifiant affiché dans les détails du webhook).

---

## 2. Variables d’environnement (backend)

### Local (`.env`)

```env
PAYPAL_WEBHOOK_ID=<Webhook ID copié depuis PayPal>
# Ne pas activer en production :
# PAYPAL_WEBHOOK_SKIP_VERIFY=true
```

### Render (obligatoire pour que PayPal atteigne l’API)

Dans le service **kvoice-api** → **Environment** :

| Variable | Valeur |
|----------|--------|
| `PAYPAL_WEBHOOK_ID` | Même ID que dans PayPal (ex. `94Y07706XW640764Y`) |
| `PAYPAL_MODE` | `sandbox` (ou `live` en prod) |
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | Credentials de la **même** app Sandbox |
| `PAYPAL_PLAN_ID_ESSENTIEL` / `PAYPAL_PLAN_ID_AVANCE` | Plans `P-…` de cette app |

Puis **Manual Deploy** (ou push sur la branche connectée).

Les autres variables PayPal doivent déjà être définies.

### Vérifier après deploy

```bash
curl https://kvoice-api.onrender.com/billing/webhooks/status
```

Réponse attendue :

```json
{
  "paypal_mode": "sandbox",
  "webhook_id_configured": true,
  "webhook_skip_verify": false,
  "endpoint": "/billing/webhooks/paypal"
}
```

Si `webhook_id_configured` est `false` → ajouter `PAYPAL_WEBHOOK_ID` sur Render et redéployer.

Si `POST /billing/webhooks/paypal` renvoie **404** → le code webhooks n’est pas encore déployé (push + deploy du backend).

---

## 3. Tester en local avec ngrok

```bash
# Terminal 1 — API
cd k-voice-backend
uvicorn main:app --reload --port 8000

# Terminal 2 — tunnel public
ngrok http 8000
```

1. Mettre l’URL ngrok dans PayPal (webhook Sandbox).
2. Mettre `PAYPAL_WEBHOOK_ID` dans `.env`.
3. Dans le dashboard PayPal → Webhook → **Simulate event** → choisir `BILLING.SUBSCRIPTION.CANCELLED` (ou autre).
4. Vérifier les logs API : `PayPal webhook processed …`
5. Rafraîchir `/admin/abonnements` : le statut doit refléter l’événement (si l’org a déjà un `external_subscription_id` = l’`I-…` PayPal).

**Important :** le webhook retrouve l’organisation via `organizations.external_subscription_id`. Cet ID est enregistré lors du flux **Activation** après paiement (`POST /billing/activate`). Tant qu’une église ne s’est pas abonnée au moins une fois via l’app, PayPal peut envoyer des événements mais aucune ligne ne sera mise à jour.

---

## 4. Production (Live)

1. Répéter la création du webhook sur l’app **Live** (pas Sandbox).
2. URL : `https://<api-prod>/billing/webhooks/paypal`
3. `PAYPAL_MODE=live` + credentials Live + `PAYPAL_WEBHOOK_ID` du webhook Live.
4. Recréer les plans `P-…` en Live si ce n’est pas déjà fait.

---

## 5. Comportement côté application

| Événement PayPal | Effet en base |
|------------------|---------------|
| ACTIVE / APPROVED | `subscription_status=active`, plan Essentiel/Avancé selon `P-…` |
| CANCELLED / EXPIRED | `subscription_status=cancelled` → plan **effectif** gratuit (quota free) |
| SUSPENDED / PAYMENT.FAILED | `subscription_status=suspended` |
| Autres types | Ignorés (réponse 200, pas d’erreur PayPal) |

La signature est vérifiée via l’API PayPal `verify-webhook-signature` (sauf `PAYPAL_WEBHOOK_SKIP_VERIFY=true` en dev).

---

## 6. Dépannage

| Symptôme | Cause probable |
|----------|----------------|
| `503 Webhook not configured` | `PAYPAL_WEBHOOK_ID` vide |
| `401 Invalid signature` | Mauvais Webhook ID, ou URL webhook sur une autre app que les credentials |
| `org_not_linked` dans les logs | Aucune org avec cet `I-…` — faire un abonnement test via l’app d’abord |
| PayPal réessaie en boucle | L’API doit répondre **2xx** ; les erreurs 4xx/5xx déclenchent des retries |

Simulateur PayPal : [Webhooks simulator](https://developer.paypal.com/tools/sandbox-notifications/) (lié à votre app Sandbox).
