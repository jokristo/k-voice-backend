from typing import Literal, TypedDict

BillingPlanKey = Literal["free", "essentiel", "standard", "avance"]


class PlanDefinition(TypedDict):
    label: str
    sermons_per_month: int
    price_usd: int | None
    brochures_enabled: bool


PLAN_DEFINITIONS: dict[BillingPlanKey, PlanDefinition] = {
    "free": {"label": "Gratuit", "sermons_per_month": 5, "price_usd": None, "brochures_enabled": False},
    "essentiel": {
        "label": "Essentiel",
        "sermons_per_month": 4,
        "price_usd": 25,
        "brochures_enabled": False,
    },
    "standard": {
        "label": "Standard",
        "sermons_per_month": 4,
        "price_usd": 35,
        "brochures_enabled": True,
    },
    "avance": {
        "label": "Avancé",
        "sermons_per_month": 8,
        "price_usd": 55,
        "brochures_enabled": True,
    },
}

ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})

BROCHURE_PLANS = frozenset({"standard", "avance"})


def plan_has_brochures(plan_key: str) -> bool:
    key = (plan_key or "free").lower()
    if key not in PLAN_DEFINITIONS:
        return False
    return PLAN_DEFINITIONS[key]["brochures_enabled"]  # type: ignore[index]
