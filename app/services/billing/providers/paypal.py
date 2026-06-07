import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings
from app.services.billing.providers.base import PaymentProvider

logger = logging.getLogger(__name__)

_PAYPAL_ACTIVE = frozenset({"ACTIVE", "APPROVED"})


class PayPalProvider(PaymentProvider):
    def __init__(self) -> None:
        self._api_base = (
            "https://api-m.paypal.com"
            if settings.paypal_mode == "live"
            else "https://api-m.sandbox.paypal.com"
        )
        self._plan_map = {
            settings.paypal_plan_id_essentiel: "essentiel",
            settings.paypal_plan_id_standard: "standard",
            settings.paypal_plan_id_avance: "avance",
        }
        # Ignore empty plan IDs (not configured yet)
        self._plan_map = {k: v for k, v in self._plan_map.items() if k}

    def _access_token(self) -> str:
        if not settings.paypal_client_id or not settings.paypal_client_secret:
            raise RuntimeError("PayPal credentials are not configured")
        creds = base64.b64encode(
            f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode()
        ).decode()
        req = urllib.request.Request(
            f"{self._api_base}/v1/oauth2/token",
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            payload = json.loads(res.read().decode())
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("PayPal OAuth token missing")
        return token

    def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._access_token()
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self._api_base}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            logger.warning("PayPal API %s %s -> %s %s", method, path, e.code, err_body[:500])
            raise RuntimeError(f"PayPal API error ({e.code})") from e

    def verify_webhook_signature(
        self,
        *,
        transmission_id: str,
        transmission_time: str,
        transmission_sig: str,
        cert_url: str,
        auth_algo: str,
        webhook_id: str,
        webhook_event: dict[str, Any],
    ) -> bool:
        payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": webhook_event,
        }
        result = self._request("POST", "/v1/notifications/verify-webhook-signature", body=payload)
        return (result.get("verification_status") or "").upper() == "SUCCESS"

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/billing/subscriptions/{subscription_id}")

    def resolve_plan_key(self, provider_plan_id: str) -> str | None:
        return self._plan_map.get(provider_plan_id)

    def is_subscription_usable(self, subscription: dict[str, Any]) -> bool:
        status = (subscription.get("status") or "").upper()
        return status in _PAYPAL_ACTIVE

    def extract_plan_id(self, subscription: dict[str, Any]) -> str | None:
        plan_id = subscription.get("plan_id")
        if plan_id:
            return plan_id
        plan = subscription.get("plan") or {}
        if isinstance(plan, dict):
            return plan.get("id")
        return None


def get_paypal_provider() -> PayPalProvider:
    return PayPalProvider()
