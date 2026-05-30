from typing import Literal, Optional

from pydantic import BaseModel, Field


class BillingPlanPublic(BaseModel):
    key: Literal["essentiel", "avance"]
    label: str
    price_usd: int
    sermons_per_month: int
    paypal_plan_id: str


class BillingConfigOut(BaseModel):
    paypal_client_id: str
    paypal_mode: str
    plans: list[BillingPlanPublic]


class ActivateSubscriptionIn(BaseModel):
    subscription_id: str = Field(..., min_length=3)
    plan: Optional[Literal["essentiel", "avance"]] = None


class EntitlementsOut(BaseModel):
    plan: str
    plan_label: str
    sermons_limit: int
    sermons_used: int
    can_create_sermon: bool
    subscription_status: str
    payment_provider: Optional[str] = None
    external_subscription_id: Optional[str] = None
    price_usd: Optional[int] = None
