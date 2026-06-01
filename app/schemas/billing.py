from datetime import datetime
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
    has_paid_subscription: bool = False
    subscription_status: str
    payment_provider: Optional[str] = None
    external_subscription_id: Optional[str] = None
    price_usd: Optional[int] = None


class AdminOrgBillingOut(BaseModel):
    organization_id: str
    organization_name: str
    organization_slug: str
    organization_email: Optional[str] = None
    stored_plan: str
    effective_plan: str
    plan_label: str
    subscription_status: str
    payment_provider: Optional[str] = None
    external_subscription_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None
    subscription_started_at: Optional[datetime] = None
    price_usd: Optional[int] = None
    sermons_used: int
    sermons_limit: int
    can_create_sermon: bool
    is_paying: bool


class AdminSubscriptionsSummaryOut(BaseModel):
    total_organizations: int
    paying_count: int
    mrr_usd: int
    paypal_mode: str
    by_plan: dict[str, int]


class AdminSubscriptionsListOut(BaseModel):
    summary: AdminSubscriptionsSummaryOut
    items: list[AdminOrgBillingOut]
