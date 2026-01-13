from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps.auth import get_current_user, require_role
from app.models import Organization, RoleEnum
from app.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate

router = APIRouter()


@router.get("", response_model=list[OrganizationOut])
def list_organizations(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(Organization).all()


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    org_in: OrganizationCreate, db: Session = Depends(get_db), _: str = Depends(require_role([RoleEnum.admin]))
):
    existing = db.query(Organization).filter(Organization.slug == org_in.slug).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")
    org = Organization(**org_in.dict())
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: str, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: str,
    org_in: OrganizationUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_role([RoleEnum.admin])),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    for field, value in org_in.dict(exclude_unset=True).items():
        setattr(org, field, value)
    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    org_id: str, db: Session = Depends(get_db), _: str = Depends(require_role([RoleEnum.admin]))
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    db.delete(org)
    db.commit()
    return None
