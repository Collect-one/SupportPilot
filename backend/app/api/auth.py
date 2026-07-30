from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.serializers import user_dict
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import create_access_token, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User)
        .options(joinedload(User.organization))
        .where(func.lower(User.email) == payload.email.lower())
    )
    if (
        not user
        or not user.active
        or (user.organization_id and (not user.organization or not user.organization.active))
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_access_token(
        str(user.id), user.role, str(user.organization_id) if user.organization_id else None
    )
    return {"access_token": token, "token_type": "bearer", "user": user_dict(user)}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_dict(user)
