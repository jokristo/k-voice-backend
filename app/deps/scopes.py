"""Authorization scopes for multi-tenant (organization) access."""

from fastapi import HTTPException, status

from app.models import RoleEnum, User


def is_super_admin(user: User) -> bool:
    return user.role == RoleEnum.super_admin


def is_org_admin(user: User) -> bool:
    return user.role == RoleEnum.admin


def is_editor_or_above(user: User) -> bool:
    return user.role in (RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor)


def can_access_organization(user: User, organization_id: str) -> bool:
    if is_super_admin(user):
        return True
    return user.organization_id == organization_id


def assert_org_access(user: User, organization_id: str) -> None:
    if not can_access_organization(user, organization_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def resolve_sermon_organization_id(user: User, requested_org_id: str | None) -> str:
    """Pick organization_id for a new sermon (JWT-scoped; super_admin may override)."""
    if requested_org_id:
        if not is_super_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super_admin can set organization_id",
            )
        return requested_org_id
    return user.organization_id
