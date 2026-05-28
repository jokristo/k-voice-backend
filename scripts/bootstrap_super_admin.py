#!/usr/bin/env python3
"""Create platform org + super_admin user, or upgrade existing admin@gmail.com."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import security
from app.core.database import SessionLocal
from app.models import Organization, RoleEnum, User

PLATFORM_SLUG = "kvoice-platform"
PLATFORM_NAME = "K-Voice Platform"
DEFAULT_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "admin@gmail.com")
DEFAULT_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "admin")
DEFAULT_NAME = os.environ.get("SUPER_ADMIN_NAME", "Super Admin")


def main() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == PLATFORM_SLUG).first()
        if not org:
            org = Organization(
                name=PLATFORM_NAME,
                slug=PLATFORM_SLUG,
                email="platform@kvoice.app",
            )
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"Created organization: {org.name} ({org.id})")
        else:
            print(f"Organization exists: {org.name} ({org.id})")

        user = db.query(User).filter(User.email == DEFAULT_EMAIL).first()
        if user:
            user.role = RoleEnum.super_admin
            user.organization_id = org.id
            if DEFAULT_PASSWORD:
                user.password_hash = security.get_password_hash(DEFAULT_PASSWORD)
            db.commit()
            print(f"Upgraded user to super_admin: {user.email}")
        else:
            user = User(
                email=DEFAULT_EMAIL,
                name=DEFAULT_NAME,
                password_hash=security.get_password_hash(DEFAULT_PASSWORD),
                role=RoleEnum.super_admin,
                organization_id=org.id,
            )
            db.add(user)
            db.commit()
            print(f"Created super_admin: {user.email} / password from SUPER_ADMIN_PASSWORD or 'admin'")
    finally:
        db.close()


if __name__ == "__main__":
    main()
