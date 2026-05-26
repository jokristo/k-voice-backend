from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import get_db
from app.deps.auth import get_current_user, require_role
from app.deps.scopes import assert_org_access, is_super_admin
from app.models import RoleEnum, User
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter()


@router.get("", response_model=list[UserOut])
def list_users(
    org_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(User)
    if org_id:
        if not is_super_admin(current_user) and org_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        query = query.filter(User.organization_id == org_id)
    elif not is_super_admin(current_user):
        query = query.filter(User.organization_id == current_user.organization_id)
    return query.all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin])),
):
    if user_in.role == RoleEnum.super_admin and not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign super_admin role")

    if not is_super_admin(current_user):
        if user_in.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        target_org = current_user.organization_id
    else:
        target_org = user_in.organization_id

    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    try:
        password_hash = security.get_password_hash(user_in.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    user = User(
        email=user_in.email,
        name=user_in.name,
        password_hash=password_hash,
        role=user_in.role,
        avatar=user_in.avatar,
        organization_id=target_org,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    assert_org_access(current_user, user.organization_id)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_in.role == RoleEnum.super_admin and not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign super_admin role")
    if not is_super_admin(current_user) and current_user.id != user.id:
        assert_org_access(current_user, user.organization_id)
        if current_user.role != RoleEnum.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    for field, value in user_in.dict(exclude_unset=True, exclude={"password"}).items():
        setattr(user, field, value)
    if user_in.password:
        try:
            user.password_hash = security.get_password_hash(user_in.password)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if is_super_admin(current_user):
        pass
    elif current_user.role == RoleEnum.admin:
        assert_org_access(current_user, user.organization_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    db.delete(user)
    db.commit()
    return None
