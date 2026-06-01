import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Organization
from app.services.billing.plans import PLAN_DEFINITIONS
from app.services.billing.providers.paypal import PayPalProvider, get_paypal_provider

logger = logging.getLogger(__name__)

# Événements PayPal pris en charge (préfixe ou liste exacte)
_HANDLED_PREFIXES = ("BILLING.SUBSCRIPTION.",)
_HANDLED_EXACT = frozenset(
    {
        "BILLING.SUBSCRIPTION.CREATED",
        "BILLING.SUBSCRIPTION.ACTIVATED",
        "BILLING.SUBSCRIPTION.UPDATED",
        "BILLING.SUBSCRIPTION.CANCELLED",
        "BILLING.SUBSCRIPTION.SUSPENDED",
        "BILLING.SUBSCRIPTION.EXPIRED",
        "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
        "BILLING.SUBSCRIPTION.RE-ACTIVATED",
    }
)

_PAYPAL_STATUS_MAP = {
    "ACTIVE": "active",
    "APPROVED": "active",
    "APPROVAL_PENDING": "pending",
    "SUSPENDED": "suspended",
    "CANCELLED": "cancelled",
    "EXPIRED": "cancelled",
}


def _subscription_id_from_resource(resource: dict[str, Any]) -> str | None:
    if not resource:
        return None
    for key in ("id", "subscription_id", "billing_agreement_id"):
        val = resource.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def map_paypal_subscription_status(paypal_status: str) -> str:
    return _PAYPAL_STATUS_MAP.get((paypal_status or "").upper(), "none")


def apply_paypal_subscription_to_org(
    db: Session,
    org: Organization,
    subscription: dict[str, Any],
    *,
    provider: PayPalProvider | None = None,
) -> bool:
    """Met à jour l'organisation à partir d'un objet subscription PayPal. Retourne True si modifié."""
    paypal = provider or get_paypal_provider()
    paypal_status = (subscription.get("status") or "").upper()
    our_status = map_paypal_subscription_status(paypal_status)
    provider_plan_id = paypal.extract_plan_id(subscription) or ""
    plan_key = paypal.resolve_plan_key(provider_plan_id)

    sub_id = subscription.get("id")
    if isinstance(sub_id, str) and sub_id.strip():
        org.external_subscription_id = sub_id.strip()

    org.payment_provider = "paypal"
    org.subscription_status = our_status
    if provider_plan_id:
        org.paypal_plan_id = provider_plan_id

    if paypal.is_subscription_usable(subscription) and plan_key:
        org.billing_plan = plan_key
        if not org.subscription_started_at:
            start = subscription.get("start_time") or subscription.get("create_time")
            if isinstance(start, str):
                try:
                    org.subscription_started_at = datetime.fromisoformat(start.replace("Z", "+00:00")).replace(
                        tzinfo=None
                    )
                except ValueError:
                    org.subscription_started_at = datetime.utcnow()
            else:
                org.subscription_started_at = datetime.utcnow()
    elif our_status in ("cancelled", "suspended", "pending", "none"):
        # Conserver billing_plan pour l'historique admin ; le plan effectif devient free via effective_billing_plan
        pass
    elif plan_key and plan_key in PLAN_DEFINITIONS:
        org.billing_plan = plan_key

    db.add(org)
    db.commit()
    db.refresh(org)
    return True


def sync_organization_by_subscription_id(
    db: Session,
    subscription_id: str,
    *,
    provider: PayPalProvider | None = None,
) -> Organization | None:
    org = (
        db.query(Organization)
        .filter(Organization.external_subscription_id == subscription_id)
        .first()
    )
    if not org:
        logger.warning("PayPal webhook: no org for subscription_id=%s", subscription_id)
        return None

    paypal = provider or get_paypal_provider()
    try:
        subscription = paypal.get_subscription(subscription_id)
    except RuntimeError:
        logger.exception("PayPal webhook: fetch subscription failed id=%s", subscription_id)
        return None

    apply_paypal_subscription_to_org(db, org, subscription, provider=paypal)
    logger.info(
        "PayPal webhook synced org=%s sub=%s status=%s plan=%s",
        org.id,
        subscription_id,
        org.subscription_status,
        org.billing_plan,
    )
    return org


def should_handle_event(event_type: str) -> bool:
    if event_type in _HANDLED_EXACT:
        return True
    return any(event_type.startswith(p) for p in _HANDLED_PREFIXES) and "SUBSCRIPTION" in event_type


def process_paypal_webhook_event(db: Session, event: dict[str, Any]) -> dict[str, Any]:
    """
    Traite un événement webhook PayPal. Toujours retourner un dict pour la réponse HTTP 200.
    """
    event_type = event.get("event_type") or ""
    event_id = event.get("id") or ""

    if not should_handle_event(event_type):
        logger.debug("PayPal webhook ignored event_type=%s id=%s", event_type, event_id)
        return {"ok": True, "handled": False, "reason": "ignored_event_type"}

    resource = event.get("resource")
    if not isinstance(resource, dict):
        logger.warning("PayPal webhook missing resource event=%s", event_id)
        return {"ok": True, "handled": False, "reason": "missing_resource"}

    subscription_id = _subscription_id_from_resource(resource)
    if not subscription_id:
        logger.warning("PayPal webhook no subscription id event=%s type=%s", event_id, event_type)
        return {"ok": True, "handled": False, "reason": "no_subscription_id"}

    org = sync_organization_by_subscription_id(db, subscription_id)
    if not org:
        return {"ok": True, "handled": False, "reason": "org_not_linked", "subscription_id": subscription_id}

    return {
        "ok": True,
        "handled": True,
        "event_type": event_type,
        "organization_id": org.id,
        "subscription_id": subscription_id,
    }
