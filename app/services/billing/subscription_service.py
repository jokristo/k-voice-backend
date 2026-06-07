from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Organization, RoleEnum, Sermon, User
from app.services.billing.plans import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    PLAN_DEFINITIONS,
    BillingPlanKey,
    plan_has_brochures,
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


def has_paid_subscription(org: Organization) -> bool:
    return effective_billing_plan(org) != "free"


def build_entitlements(db: Session, org: Organization) -> dict[str, Any]:
    used = count_sermons_this_month(db, org.id)
    base = {
        "subscription_status": org.subscription_status or "none",
        "payment_provider": org.payment_provider,
        "external_subscription_id": org.external_subscription_id,
    }

    if not has_paid_subscription(org):
        return {
            **base,
            "plan": "none",
            "plan_label": "Aucun abonnement actif",
            "sermons_limit": 0,
            "sermons_used": used,
            "can_create_sermon": False,
            "has_paid_subscription": False,
            "price_usd": None,
            "brochures_enabled": False,
        }

    plan_key = effective_billing_plan(org)
    plan_def = PLAN_DEFINITIONS[plan_key]
    limit = plan_def["sermons_per_month"]
    return {
        **base,
        "plan": plan_key,
        "plan_label": plan_def["label"],
        "sermons_limit": limit,
        "sermons_used": used,
        "can_create_sermon": used < limit,
        "has_paid_subscription": True,
        "price_usd": plan_def["price_usd"],
        "brochures_enabled": plan_has_brochures(plan_key),
    }


def assert_can_create_sermon(
    db: Session, org: Organization, user: User | None = None
) -> None:
    if user is not None and user.role == RoleEnum.super_admin:
        return
    if not has_paid_subscription(org):
        raise ValueError(
            "Un abonnement actif (Essentiel, Standard ou Avancé) est requis pour enregistrer des prédications."
        )
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


def list_admin_subscriptions(db: Session, *, paypal_mode: str) -> dict[str, Any]:
    orgs = db.query(Organization).order_by(Organization.name).all()
    items: list[dict[str, Any]] = []
    by_plan: dict[str, int] = {"free": 0, "essentiel": 0, "standard": 0, "avance": 0}
    mrr_usd = 0
    paying_count = 0

    for org in orgs:
        ent = build_entitlements(db, org)
        effective = ent["plan"]
        stored = (org.billing_plan or "free").lower()
        if stored not in PLAN_DEFINITIONS:
            stored = "free"
        by_plan[effective] = by_plan.get(effective, 0) + 1
        is_paying = effective != "free"
        if is_paying:
            paying_count += 1
            if ent.get("price_usd"):
                mrr_usd += int(ent["price_usd"])

        items.append(
            {
                "organization_id": org.id,
                "organization_name": org.name,
                "organization_slug": org.slug,
                "organization_email": org.email,
                "stored_plan": stored,
                "effective_plan": effective,
                "plan_label": ent["plan_label"],
                "subscription_status": org.subscription_status or "none",
                "payment_provider": org.payment_provider,
                "external_subscription_id": org.external_subscription_id,
                "paypal_plan_id": org.paypal_plan_id,
                "subscription_started_at": org.subscription_started_at,
                "price_usd": ent.get("price_usd"),
                "sermons_used": ent["sermons_used"],
                "sermons_limit": ent["sermons_limit"],
                "can_create_sermon": ent["can_create_sermon"],
                "is_paying": is_paying,
            }
        )

    return {
        "summary": {
            "total_organizations": len(orgs),
            "paying_count": paying_count,
            "mrr_usd": mrr_usd,
            "paypal_mode": paypal_mode,
            "by_plan": by_plan,
        },
        "items": items,
    }
