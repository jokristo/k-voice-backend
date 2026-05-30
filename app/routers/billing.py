import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps.auth import get_current_user, require_role
from app.models import Organization, RoleEnum, User
from app.schemas.billing import ActivateSubscriptionIn, BillingConfigOut, BillingPlanPublic, EntitlementsOut
from app.services.billing.subscription_service import activate_paypal_subscription, build_entitlements

router = APIRouter()
logger = logging.getLogger(__name__)


def _org_for_user(db: Session, user: User) -> Organization:
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("/config", response_model=BillingConfigOut)
def billing_config():
    plans: list[BillingPlanPublic] = []
    if settings.paypal_plan_id_essentiel:
        plans.append(
            BillingPlanPublic(
                key="essentiel",
                label="Essentiel",
                price_usd=25,
                sermons_per_month=4,
                paypal_plan_id=settings.paypal_plan_id_essentiel,
            )
        )
    if settings.paypal_plan_id_avance:
        plans.append(
            BillingPlanPublic(
                key="avance",
                label="Avancé",
                price_usd=55,
                sermons_per_month=8,
                paypal_plan_id=settings.paypal_plan_id_avance,
            )
        )
    return BillingConfigOut(
        paypal_client_id=settings.paypal_client_id,
        paypal_mode=settings.paypal_mode,
        plans=plans,
    )


@router.get("/subscription", response_model=EntitlementsOut)
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = _org_for_user(db, current_user)
    return build_entitlements(db, org)


@router.post("/activate", response_model=EntitlementsOut)
def activate_subscription(
    body: ActivateSubscriptionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin])),
):
    org = _org_for_user(db, current_user)
    try:
        ent = activate_paypal_subscription(
            db,
            org,
            subscription_id=body.subscription_id.strip(),
            expected_plan=body.plan,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        logger.exception("PayPal activation failed org=%s", org.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Impossible de valider l'abonnement PayPal",
        ) from e
    logger.info(
        "subscription activated org=%s plan=%s sub=%s by=%s",
        org.id,
        ent["plan"],
        body.subscription_id,
        current_user.id,
    )
    return ent
