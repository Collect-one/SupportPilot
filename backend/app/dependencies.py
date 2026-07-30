import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized
    user = db.get(User, user_id)
    if (
        not user
        or not user.active
        or (user.organization_id and (not user.organization or not user.organization.active))
    ):
        raise unauthorized
    return user


def require_support(user: User = Depends(get_current_user)) -> User:
    if user.role != "SUPPORT":
        raise HTTPException(status_code=403, detail="仅人工支持人员可执行此操作")
    return user


def require_customer(user: User = Depends(get_current_user)) -> User:
    if user.role != "CUSTOMER" or not user.organization_id:
        raise HTTPException(status_code=403, detail="仅客户账号可执行此操作")
    return user
