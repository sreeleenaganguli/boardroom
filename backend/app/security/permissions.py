"""RBAC permission checking dependency."""

from functools import wraps
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.security.auth import get_current_user


async def get_user_permissions(user, db: AsyncSession) -> List[str]:
    """Get all permissions for a user through their roles."""
    from app.models.permission import UserRole, RolePermission, Permission
    from app.models.role import Role

    if user.is_superuser:
        # Superusers have all permissions
        result = await db.execute(select(Permission))
        permissions = result.scalars().all()
        return [f"{p.resource}:{p.action}" for p in permissions]

    # Get user's roles
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    user_roles = result.scalars().all()
    role_ids = [ur.role_id for ur in user_roles]

    if not role_ids:
        return []

    # Get permissions for those roles
    result = await db.execute(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(role_ids))
    )
    permissions = result.scalars().all()
    return list(set(f"{p.resource}:{p.action}" for p in permissions))


def require_permission(resource: str, action: str):
    """Dependency factory that checks if user has a specific permission.

    Usage:
        @router.get("/items", dependencies=[Depends(require_permission("items", "read"))])
    """

    async def permission_checker(
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        permissions = await get_user_permissions(current_user, db)
        required = f"{resource}:{action}"
        if required not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {required}",
            )
        return current_user

    return permission_checker


def require_any_permission(*permission_pairs: tuple):
    """Dependency factory that checks if user has any of the specified permissions.

    Usage:
        @router.get("/items", dependencies=[Depends(require_any_permission(("items", "read"), ("items", "admin")))])
    """

    async def permission_checker(
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        permissions = await get_user_permissions(current_user, db)
        required = [f"{r}:{a}" for r, a in permission_pairs]
        if not any(p in permissions for p in required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires one of {required}",
            )
        return current_user

    return permission_checker
