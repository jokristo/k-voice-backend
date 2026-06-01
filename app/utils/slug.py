import re
import unicodedata

from sqlalchemy.orm import Session

from app.models import Organization


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_text.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "eglise"


def unique_organization_slug(db: Session, name: str) -> str:
    base = slugify(name)
    candidate = base
    suffix = 2
    while db.query(Organization).filter(Organization.slug == candidate).first():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
