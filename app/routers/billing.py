import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps.auth import get_current_user, require_role
from app.models import Organization, RoleEnum, User
from app.schemas.billing import (
    ActivateSubscriptionIn,
    AdminSubscriptionsListOut,
    BillingConfigOut,
    BillingPlanPublic,
    EntitlementsOut,
)
from app.services.billing.providers.paypal import get_paypal_provider
from app.services.billing.subscription_service import (
    activate_paypal_subscription,
    build_entitlements,
    list_admin_subscriptions,
)
from app.services.billing.webhook_handler import process_paypal_webhook_event

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


@router.get("/admin/subscriptions", response_model=AdminSubscriptionsListOut)
def admin_list_subscriptions(
    db: Session = Depends(get_db),
    _: User = Depends(require_role([RoleEnum.super_admin])),
):
    return list_admin_subscriptions(db, paypal_mode=settings.paypal_mode)


@router.get("/webhooks/status")
def paypal_webhook_status():
    """Vérification déploiement : webhook ID présent (sans exposer la valeur)."""
    return {
        "paypal_mode": settings.paypal_mode,
        "webhook_id_configured": bool(settings.paypal_webhook_id),
        "webhook_skip_verify": settings.paypal_webhook_skip_verify,
        "endpoint": "/billing/webhooks/paypal",
    }


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    try:
        event = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from e

    if not settings.paypal_webhook_skip_verify:
        if not settings.paypal_webhook_id:
            logger.error("PayPal webhook received but PAYPAL_WEBHOOK_ID is not set")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook not configured",
            )
        headers = request.headers
        transmission_id = headers.get("paypal-transmission-id") or headers.get("PAYPAL-TRANSMISSION-ID")
        transmission_time = headers.get("paypal-transmission-time") or headers.get("PAYPAL-TRANSMISSION-TIME")
        transmission_sig = headers.get("paypal-transmission-sig") or headers.get("PAYPAL-TRANSMISSION-SIG")
        cert_url = headers.get("paypal-cert-url") or headers.get("PAYPAL-CERT-URL")
        auth_algo = headers.get("paypal-auth-algo") or headers.get("PAYPAL-AUTH-ALGO")

        if not all([transmission_id, transmission_time, transmission_sig, cert_url, auth_algo]):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing PayPal signature headers")

        try:
            paypal = get_paypal_provider()
            ok = paypal.verify_webhook_signature(
                transmission_id=transmission_id,
                transmission_time=transmission_time,
                transmission_sig=transmission_sig,
                cert_url=cert_url,
                auth_algo=auth_algo,
                webhook_id=settings.paypal_webhook_id,
                webhook_event=event,
            )
        except RuntimeError:
            logger.exception("PayPal webhook signature verification API failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Signature verification failed",
            ) from None

        if not ok:
            logger.warning("PayPal webhook signature invalid event_id=%s", event.get("id"))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    result = process_paypal_webhook_event(db, event)
    logger.info(
        "PayPal webhook processed event_id=%s type=%s result=%s",
        event.get("id"),
        event.get("event_type"),
        result,
    )
    return result
