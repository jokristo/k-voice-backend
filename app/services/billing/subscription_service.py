from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Organization, Sermon
from app.services.billing.plans import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    PLAN_DEFINITIONS,
    BillingPlanKey,
)
from app.services.billing.providers.paypal import PayPalProvider, get_paypal_provider


def _month_start_utc() -> datetime:
    now = datetime.utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def effective_billing_plan(org: Organization) -> BillingPlanKey:
    plan = (org.billing_plan or "free").lower()
    if plan not in PLAN_DEFINITIONS:
        plan = "free"
    status = (org.subscription_status or "none").lower()
    if plan != "free" and status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return "free"
    return plan  # type: ignore[return-value]


def count_sermons_this_month(db: Session, organization_id: str) -> int:
    return (
        db.query(Sermon)
        .filter(
            Sermon.organization_id == organization_id,
            Sermon.created_at >= _month_start_utc(),
        )
        .count()
    )


def build_entitlements(db: Session, org: Organization) -> dict[str, Any]:
    plan_key = effective_billing_plan(org)
    plan_def = PLAN_DEFINITIONS[plan_key]
    used = count_sermons_this_month(db, org.id)
    limit = plan_def["sermons_per_month"]
    return {
        "plan": plan_key,
        "plan_label": plan_def["label"],
        "sermons_limit": limit,
        "sermons_used": used,
        "can_create_sermon": used < limit,
        "subscription_status": org.subscription_status or "none",
        "payment_provider": org.payment_provider,
        "external_subscription_id": org.external_subscription_id,
        "price_usd": plan_def["price_usd"],
    }


def assert_can_create_sermon(db: Session, org: Organization) -> None:
    ent = build_entitlements(db, org)
    if not ent["can_create_sermon"]:
        raise ValueError(
            f"Quota mensuel atteint ({ent['sermons_used']}/{ent['sermons_limit']}). "
            "Passez à un plan supérieur ou attendez le mois prochain."
        )


def activate_paypal_subscription(
    db: Session,
    org: Organization,
    *,
    subscription_id: str,
    expected_plan: str | None,
    provider: PayPalProvider | None = None,
) -> dict[str, Any]:
    paypal = provider or get_paypal_provider()
    sub = paypal.get_subscription(subscription_id)
    if not paypal.is_subscription_usable(sub):
        raise ValueError("Abonnement PayPal non actif ou non approuvé")

    provider_plan_id = paypal.extract_plan_id(sub) or ""
    plan_key = paypal.resolve_plan_key(provider_plan_id)
    if not plan_key:
        raise ValueError("Plan PayPal non reconnu pour cette application")

    if expected_plan and expected_plan != plan_key:
        raise ValueError("Le plan PayPal ne correspond pas au plan sélectionné")

    org.billing_plan = plan_key
    org.subscription_status = "active"
    org.payment_provider = "paypal"
    org.external_subscription_id = subscription_id
    org.paypal_plan_id = provider_plan_id
    org.subscription_started_at = datetime.utcnow()
    db.add(org)
    db.commit()
    db.refresh(org)
    return build_entitlements(db, org)
