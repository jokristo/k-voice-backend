from typing import Callable, List, Optional

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import RoleEnum, User
from app.schemas import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
logger = logging.getLogger(__name__)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        token_data = TokenPayload(**payload)
        if token_data.sub is None or token_data.type != "access":
            logger.warning("auth rejected: invalid token payload type=%s", getattr(token_data, "type", None))
            raise credentials_exception
    except JWTError as e:
        logger.warning("auth rejected: JWT decode failed (%s)", type(e).__name__)
        raise credentials_exception

    user = db.query(User).filter(User.id == token_data.sub).first()
    if not user:
        logger.warning("auth rejected: user id=%s not in database", token_data.sub)
        raise credentials_exception
    return user


def require_role(allowed: List[RoleEnum]) -> Callable:
    def _role_guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            logger.warning(
                "auth forbidden: user=%s role=%s needs one of %s",
                current_user.id,
                current_user.role,
                allowed,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return _role_guard


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    # Placeholder for additional checks (suspension, etc.)
    return current_user
