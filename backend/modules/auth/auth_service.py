"""Autenticación JWT respaldada por usuarios persistidos en SQLite.

La tabla `users` se crea con la migración 032_auth_jwt.sql.
No existe un usuario de ejemplo: toda identidad proviene de la base de datos.
"""
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field, field_validator

from config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
)
from db.database import get_connection

# bcrypt limita el hash a 72 bytes. Se valida el límite en UserCreate para
# no truncar contraseñas silenciosamente.
BCRYPT_MAX_BYTES = 72

# El registro público solo puede crear ciudadanos. Los roles privilegiados
# (organizador/admin) se asignan únicamente desde una cuenta administradora.
PUBLIC_REGISTRATION_ROLES = {"ciudadano"}
ALLOWED_ROLES = {"ciudadano", "organizador", "admin"}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    username: Optional[str] = None


class User(BaseModel):
    username: str
    email: Optional[str] = None
    role: str = "ciudadano"
    is_active: bool = True


class UserInDB(User):
    hashed_password: str

    class Config:
        arbitrary_types_allowed = True


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=72)
    # El rol se valida en create_user: el registro público nunca puede
    # asignarse 'admin'.
    role: str = "ciudadano"

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError("La contraseña no puede superar 72 bytes en UTF-8")
        return value


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (TypeError, ValueError):
        return False


def get_password_hash(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail="La contraseña no puede superar 72 bytes en UTF-8",
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# Dependencias de autenticación
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _row_to_user(row) -> UserInDB:
    return UserInDB(
        username=row["username"],
        email=row["email"],
        hashed_password=row["password_hash"],
        role=row["role"],
        is_active=bool(row["is_active"]),
    )


def get_user(username: str) -> Optional[UserInDB]:
    """Recupera exactamente el usuario solicitado o None si no existe."""
    if not username:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT username, email, password_hash, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_user(row)


def get_user_by_email(email: str) -> Optional[UserInDB]:
    if not email:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT username, email, password_hash, role, is_active FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_user(row)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type", "access")
        if username is None or token_type != "access":
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(username=token_data.username)
    if user is None:
        # El token puede ser válido criptográficamente pero el usuario ya no
        # existe: se rechaza igualmente.
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Usuario desactivado")
    return current_user


def require_roles(*allowed_roles: str):
    """Dependencia de autorización por rol.

    Se apoya en el usuario ya autenticado por JWT y en la tabla `users`.
    No crea un sistema de permisos paralelo.
    """
    allowed = set(allowed_roles)

    async def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Permisos insuficientes para esta operación",
            )
        return current_user

    return dependency


def get_user_organization_id(username: str) -> Optional[int]:
    """Devuelve la organización operacional vinculada al usuario, si existe.

    La vinculación se hace por `operational_users.username`, que es el puente
    existente entre la identidad JWT y el modelo organizativo. No se inventa
    una segunda tabla de pertenencia.
    """
    if not username:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT organization_id FROM operational_users WHERE username = ? AND active = 1",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    return int(row["organization_id"]) if row else None


def create_user(user: UserCreate, allow_privileged: bool = False) -> UserInDB:
    """Persiste un usuario nuevo.

    Por defecto se comporta como registro público: solo crea ciudadanos.
    `allow_privileged=True` se usa exclusivamente desde una ruta protegida de
    administración o desde pruebas con datos sintéticos.
    """
    if user.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail="Rol no permitido")
    if not allow_privileged and user.role not in PUBLIC_REGISTRATION_ROLES:
        raise HTTPException(
            status_code=403,
            detail="El registro público no puede asignar roles administrativos",
        )

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (user.username, user.email),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Usuario o email ya registrado")
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role, is_active) VALUES (?, ?, ?, ?, 1)",
            (user.username, user.email, get_password_hash(user.password), user.role),
        )
        conn.commit()
        row = conn.execute(
            "SELECT username, email, password_hash, role, is_active FROM users WHERE username = ?",
            (user.username,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=500, detail="Error creando usuario")
    return _row_to_user(row)
