import logging

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.deps.auth import get_current_user
from app.models import User
from app.schemas import LoginRequest, LoginResponse, TokenPayload, UserCreate, UserOut
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserOut)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        logger.warning("register rejected: email already exists %r", user_in.email)
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
        organization_id=user_in.organization_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("register ok user_id=%s email=%r", user.id, user.email)
    return user


@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user:
        logger.warning("login failed email=%r (unknown user)", credentials.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    try:
        password_valid = security.verify_password(credentials.password, user.password_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not password_valid:
        logger.warning("login failed email=%r (bad password)", credentials.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    access_token = security.create_access_token(user.id)
    refresh_token = security.create_refresh_token(user.id)
    logger.info("login ok user_id=%s email=%r", user.id, user.email)
    return LoginResponse(access_token=access_token, refresh_token=refresh_token, user=user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate refresh token"
    )
    try:
        decoded = jwt.decode(payload.refresh_token, settings.secret_key, algorithms=[settings.algorithm])
        token_data = TokenPayload(**decoded)
        if token_data.sub is None or token_data.type != "refresh":
            raise credentials_exception
    except JWTError:
        logger.warning("refresh failed: JWT decode error")
        raise credentials_exception

    user = db.query(User).filter(User.id == token_data.sub).first()
    if not user:
        logger.warning("refresh failed: user not found sub=%s", token_data.sub)
        raise credentials_exception
    access_token = security.create_access_token(user.id)
    new_refresh = security.create_refresh_token(user.id)
    logger.info("refresh ok user_id=%s", user.id)
    return {"access_token": access_token, "refresh_token": new_refresh, "token_type": "bearer"}
