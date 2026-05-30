from typing import Literal, TypedDict

BillingPlanKey = Literal["free", "essentiel", "avance"]


class PlanDefinition(TypedDict):
    label: str
    sermons_per_month: int
    price_usd: int | None


PLAN_DEFINITIONS: dict[BillingPlanKey, PlanDefinition] = {
    "free": {"label": "Gratuit", "sermons_per_month": 5, "price_usd": None},
    "essentiel": {"label": "Essentiel", "sermons_per_month": 4, "price_usd": 25},
    "avance": {"label": "Avancé", "sermons_per_month": 8, "price_usd": 55},
}

ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})
