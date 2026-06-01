#!/usr/bin/env bash
# Vérifie que l’API expose le webhook PayPal et que PAYPAL_WEBHOOK_ID est chargé.
# Usage: ./scripts/check_paypal_webhook.sh
#        ./scripts/check_paypal_webhook.sh https://kvoice-api.onrender.com

set -euo pipefail
BASE="${1:-http://localhost:8000}"
BASE="${BASE%/}"

echo "→ Health: $BASE/health"
curl -sf "$BASE/health" | head -c 200
echo ""
echo ""

echo "→ Webhook status: $BASE/billing/webhooks/status"
STATUS_JSON=$(curl -sf "$BASE/billing/webhooks/status")
echo "$STATUS_JSON" | python3 -m json.tool 2>/dev/null || echo "$STATUS_JSON"
echo ""

CONFIGURED=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('webhook_id_configured', False))" 2>/dev/null || echo "false")
if [ "$CONFIGURED" != "True" ] && [ "$CONFIGURED" != "true" ]; then
  echo "⚠️  PAYPAL_WEBHOOK_ID non configuré sur ce serveur."
  exit 1
fi

echo "→ Webhook POST (sans signature, doit être 400): $BASE/billing/webhooks/paypal"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/billing/webhooks/paypal" \
  -H "Content-Type: application/json" -d '{"event_type":"BILLING.SUBSCRIPTION.CANCELLED","resource":{"id":"I-TEST"}}')
echo "   HTTP $HTTP"
if [ "$HTTP" = "404" ]; then
  echo "❌ Route absente — déployer la dernière version du backend."
  exit 1
fi
if [ "$HTTP" = "503" ]; then
  echo "❌ Webhook non configuré (PAYPAL_WEBHOOK_ID manquant sur ce serveur)."
  exit 1
fi
if [ "$HTTP" = "400" ] || [ "$HTTP" = "401" ]; then
  echo "✅ Route OK (erreur attendue sans en-têtes PayPal)."
  exit 0
fi
echo "ℹ️  Code inattendu — voir logs API."
exit 0
