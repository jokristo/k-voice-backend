import logging

from sqlalchemy.orm import Session

from app.constants.africa_dial_codes import ALLOWED_DIAL_CODES, DIAL_CODE_TO_COUNTRY
from app.core import security
from app.models import Organization, RoleEnum, User
from app.utils.slug import unique_organization_slug

logger = logging.getLogger(__name__)


def signup_church_admin(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    church_name: str,
    city: str,
    dial_code: str,
    phone_local: str,
) -> tuple[User, Organization]:
    if dial_code not in ALLOWED_DIAL_CODES:
        raise ValueError("Indicatif pays non pris en charge")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("Cet email est déjà utilisé")

    country = DIAL_CODE_TO_COUNTRY.get(dial_code, "")
    slug = unique_organization_slug(db, church_name)
    phone = f"{dial_code}{phone_local}"

    org = Organization(
        name=church_name.strip(),
        slug=slug,
        city=city.strip(),
        country=country,
        dial_code=dial_code,
        phone=phone,
        email=email,
        billing_plan=None,
        subscription_status="none",
    )
    db.add(org)
    db.flush()

    password_hash = security.get_password_hash(password)
    user = User(
        email=email,
        name=name.strip(),
        password_hash=password_hash,
        role=RoleEnum.admin,
        organization_id=org.id,
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    logger.info("signup ok user_id=%s org_id=%s slug=%s", user.id, org.id, slug)
    return user, org
