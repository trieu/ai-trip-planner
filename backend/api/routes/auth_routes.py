"""
Authentication API routes (JWT-based).
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt

from config import get_settings

# ==========================================
# Config
# ==========================================
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


# ==========================================
# Mock User Store (replace with DB later)
# ==========================================
fake_users_db = {
    "admin@example.com": {
        "id": "user_1",
        "email": "admin@example.com",
        "password": "admin123",  # ⚠️ replace with hashed password in prod
    }
}


# ==========================================
# JWT Helpers
# ==========================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )

    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)

    to_encode = data.copy()
    to_encode.update({"exp": expire, "type": "refresh"})

    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ==========================================
# Dependencies
# ==========================================
def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return {
        "user_id": user_id,
        "email": payload.get("email"),
    }


# ==========================================
# Routes
# ==========================================

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint (OAuth2 compatible).
    """

    user = fake_users_db.get(form_data.username)

    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    payload = {
        "sub": user["id"],
        "email": user["email"],
    }

    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60,
    }


@router.post("/refresh")
async def refresh_token(refresh_token: str):
    """
    Refresh access token using refresh token.
    """

    payload = verify_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    new_payload = {
        "sub": payload["sub"],
        "email": payload.get("email"),
    }

    new_access_token = create_access_token(new_payload)

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user.
    """
    return {
        "user": current_user
    }


@router.post("/register")
async def register(email: str, password: str):
    """
    Simple registration (mock).
    """

    if email in fake_users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    user_id = f"user_{len(fake_users_db) + 1}"

    fake_users_db[email] = {
        "id": user_id,
        "email": email,
        "password": password,
    }

    return {
        "message": "User created",
        "user_id": user_id,
    }