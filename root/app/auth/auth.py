from app.auth.security import create_access_token, get_password_hash, verify_password
from app.core.database import get_db
from app.models.models import User
from app.schemas.schemas import Token, UserCreate
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    db: AsyncSession = Depends(get_db),
):
    email = form_data.username.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь деактивирован",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login-json", response_model=Token)
async def login_json(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь деактивирован",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register")
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    email = user.email.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    if res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже существует",
        )
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role="student",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"status": "ok", "id": new_user.id}
