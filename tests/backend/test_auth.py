import pytest
from fastapi.testclient import TestClient
import sys
import os
os.environ["ANEXO_ADMIN_KEY"] = "test-key"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["JWT_REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
sys.path.append("C:\\Users\\JUAN\\Desktop\\Proyectos\\Anexo_Risk_limpio\\backend")
from main import app
from modules.auth.auth_service import get_current_active_user, get_current_user, create_access_token, create_refresh_token, verify_password, get_password_hash, pwd_context, oauth2_scheme, TokenData, User, UserInDB, UserCreate, Token
from modules.auth.routes import router as auth_router

app.include_router(auth_router, prefix="/api/auth")

@pytest.fixture
def test_user():
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword",
        "role": "ciudadano"
    }

def test_register(test_user):
    response = client.post("/api/auth/register", json=test_user)
    assert response.status_code == 201
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()


def test_login(test_user):
    # Primero registramos un usuario
    client.post("/api/auth/register", json=test_user)
    
    # Luego intentamos hacer login
    response = client.post(
        "/api/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_me(test_user):
    # Registramos un usuario
    register_response = client.post("/api/auth/register", json=test_user)
    access_token = register_response.json()["access_token"]
    
    # Obtenemos información del usuario
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == test_user["username"]


def test_refresh_token(test_user):
    # Registramos un usuario
    register_response = client.post("/api/auth/register", json=test_user)
    refresh_token = register_response.json()["refresh_token"]
    
    # Refrescamos el token
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_invalid_credentials(test_user):
    # Intentamos hacer login con credenciales incorrectas
    response = client.post(
        "/api/auth/login",
        data={"username": test_user["username"], "password": "wrongpassword"}
    )
    assert response.status_code == 401


def test_invalid_token():
    # Intentamos acceder a /api/auth/me con un token inválido
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 401


def test_role_authorization(test_user):
    # Registramos un usuario con rol 'ciudadano'
    register_response = client.post("/api/auth/register", json=test_user)
    access_token = register_response.json()["access_token"]
    
    # Intentamos acceder a una ruta protegida por rol 'admin'
    response = client.get(
        "/api/admin/route",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403

# Mock para simular la base de datos
def mock_create_user(user: UserCreate):
    hashed_password = get_password_hash(user.password)
    return UserInDB(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role,
    )

def mock_get_user(username: str):
    if username == "testuser":
        return UserInDB(
            username="testuser",
            email="test@example.com",
            hashed_password=get_password_hash("testpassword"),
            role="ciudadano",
        )
    return None

# Sobrescribir las funciones de la base de datos con los mocks
from modules.auth.auth_service import create_user, get_user

create_user = mock_create_user
get_user = mock_get_user

# Sobrescribir las funciones de la base de datos en el módulo auth_service
modules.auth.auth_service.create_user = mock_create_user
modules.auth.auth_service.get_user = mock_get_user

# Sobrescribir la función get_current_active_user en el módulo auth_service
def mock_get_current_active_user(token: str = Depends(oauth2_scheme)):
    return UserInDB(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
        role="ciudadano",
    )

modules.auth.auth_service.get_current_active_user = mock_get_current_active_user

# Sobrescribir la función get_current_user en el módulo auth_service
def mock_get_current_user(token: str = Depends(oauth2_scheme)):
    return UserInDB(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
        role="ciudadano",
    )

modules.auth.auth_service.get_current_user = mock_get_current_user

# Sobrescribir la función create_access_token en el módulo auth_service
def mock_create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    return "mock_access_token"

modules.auth.auth_service.create_access_token = mock_create_access_token

# Sobrescribir la función create_refresh_token en el módulo auth_service
def mock_create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    return "mock_refresh_token"

modules.auth.auth_service.create_refresh_token = mock_create_refresh_token

# Sobrescribir la función verify_password en el módulo auth_service
def mock_verify_password(plain_password: str, hashed_password: str):
    return plain_password == "testpassword"

modules.auth.auth_service.verify_password = mock_verify_password

# Sobrescribir la función get_password_hash en el módulo auth_service
def mock_get_password_hash(password: str):
    return "mock_hashed_password"

modules.auth.auth_service.get_password_hash = mock_get_password_hash

# Sobrescribir la función pwd_context en el módulo auth_service
def mock_pwd_context():
    return pwd_context

modules.auth.auth_service.pwd_context = mock_pwd_context

# Sobrescribir la función oauth2_scheme en el módulo auth_service
def mock_oauth2_scheme():
    return oauth2_scheme

modules.auth.auth_service.oauth2_scheme = mock_oauth2_scheme

# Sobrescribir la función TokenData en el módulo auth_service
def mock_TokenData(username: Optional[str] = None):
    return TokenData(username=username)

modules.auth.auth_service.TokenData = mock_TokenData

# Sobrescribir la función User en el módulo auth_service
def mock_User(username: str, email: Optional[str] = None, role: str = "ciudadano"):
    return User(username=username, email=email, role=role)

modules.auth.auth_service.User = mock_User

# Sobrescribir la función UserInDB en el módulo auth_service
def mock_UserInDB(username: str, email: Optional[str] = None, hashed_password: str = "", role: str = "ciudadano"):
    return UserInDB(username=username, email=email, hashed_password=hashed_password, role=role)

modules.auth.auth_service.UserInDB = mock_UserInDB

# Sobrescribir la función UserCreate en el módulo auth_service
def mock_UserCreate(username: str, email: str, password: str, role: str = "ciudadano"):
    return UserCreate(username=username, email=email, password=password, role=role)

modules.auth.auth_service.UserCreate = mock_UserCreate

# Sobrescribir la función Token en el módulo auth_service
def mock_Token(access_token: str, token_type: str):
    return Token(access_token=access_token, token_type=token_type)

modules.auth.auth_service.Token = mock_Token

client = TestClient(app)

@pytest.fixture
def test_user():
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword",
        "role": "ciudadano"
    }

def test_register(test_user):
    response = client.post("/api/auth/register", json=test_user)
    assert response.status_code == 201
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()


def test_login(test_user):
    # Primero registramos un usuario
    client.post("/api/auth/register", json=test_user)
    
    # Luego intentamos hacer login
    response = client.post(
        "/api/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_me(test_user):
    # Registramos un usuario
    register_response = client.post("/api/auth/register", json=test_user)
    access_token = register_response.json()["access_token"]
    
    # Obtenemos información del usuario
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == test_user["username"]


def test_refresh_token(test_user):
    # Registramos un usuario
    register_response = client.post("/api/auth/register", json=test_user)
    refresh_token = register_response.json()["refresh_token"]
    
    # Refrescamos el token
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_invalid_credentials(test_user):
    # Intentamos hacer login con credenciales incorrectas
    response = client.post(
        "/api/auth/login",
        data={"username": test_user["username"], "password": "wrongpassword"}
    )
    assert response.status_code == 401


def test_invalid_token():
    # Intentamos acceder a /api/auth/me con un token inválido
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 401


def test_role_authorization(test_user):
    # Registramos un usuario con rol 'ciudadano'
    register_response = client.post("/api/auth/register", json=test_user)
    access_token = register_response.json()["access_token"]
    
    # Intentamos acceder a una ruta protegida por rol 'admin'
    response = client.get(
        "/api/admin/route",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 403
