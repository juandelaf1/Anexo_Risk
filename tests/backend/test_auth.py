"""Pruebas de autenticación JWT con persistencia real en SQLite.

No se sustituyen `get_user`/`create_user` por mocks: cada prueba usa una base
de datos temporal creada con las migraciones del proyecto.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.no_auth_override


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from db import database

    path = tmp_path / "auth_test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    database.init_db()
    yield path


@pytest.fixture
def client(db_path):
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def _register(
    client: TestClient,
    username: str = "alice",
    email: str | None = None,
    password: str = "password123",
    role: str = "ciudadano",
):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email or f"{username}@example.invalid",
            "password": password,
            "role": role,
        },
    )


def _login(client: TestClient, username: str = "alice", password: str = "password123"):
    return client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )


def _create_user(
    username: str,
    role: str,
    password: str = "password123",
    is_active: bool = True,
):
    from db.database import get_connection
    from modules.auth.auth_service import UserCreate, create_user

    user = create_user(
        UserCreate(
            username=username,
            email=f"{username}@example.invalid",
            password=password,
            role=role,
        ),
        allow_privileged=True,
    )
    if not is_active:
        conn = get_connection()
        try:
            conn.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
            conn.commit()
        finally:
            conn.close()
    return user


def _token(client: TestClient, username: str = "alice", password: str = "password123") -> str:
    response = _login(client, username, password)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


# ── Registro y persistencia ────────────────────────────────────────────────

def test_register_persists_user_and_hashes_password(client):
    response = _register(client)
    assert response.status_code == 201, response.text

    from db.database import get_connection
    from modules.auth.auth_service import verify_password

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT username, email, password_hash, role, is_active FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["username"] == "alice"
    assert row["email"] == "alice@example.invalid"
    assert row["role"] == "ciudadano"
    assert bool(row["is_active"]) is True
    assert row["password_hash"] != "password123"
    assert verify_password("password123", row["password_hash"]) is True


def test_duplicate_registration_is_rejected(client):
    assert _register(client).status_code == 201
    response = _register(client)
    assert response.status_code == 400


# ── Login ──────────────────────────────────────────────────────────────────

def test_login_with_valid_password_returns_token(client):
    _register(client)
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body.get("refresh_token")


def test_login_with_wrong_password_is_rejected(client):
    _register(client)
    response = _login(client, password="wrong-password")
    assert response.status_code == 401


def test_login_with_nonexistent_user_is_rejected(client):
    response = _login(client, username="nobody")
    assert response.status_code == 401


# ── Tokens ─────────────────────────────────────────────────────────────────

def test_invalid_token_is_rejected(client):
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-valid-token"}
    )
    assert response.status_code == 401


def test_expired_token_is_rejected(client):
    from modules.auth.auth_service import create_access_token

    _register(client)
    expired = create_access_token(
        {"sub": "alice"}, expires_delta=timedelta(seconds=-1)
    )
    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401


def test_token_for_deleted_user_is_rejected(client):
    _register(client)
    token = _token(client)

    from db.database import get_connection

    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE username = ?", ("alice",))
        conn.commit()
    finally:
        conn.close()

    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_inactive_user_cannot_login_or_use_token(client):
    _register(client)
    token = _token(client)

    from db.database import get_connection

    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_active = 0 WHERE username = ?", ("alice",))
        conn.commit()
    finally:
        conn.close()

    login_response = _login(client)
    assert login_response.status_code in (400, 403)

    me_response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 403


def test_token_identity_is_exact_and_not_shared(client):
    _register(client, username="alice")
    _register(client, username="bob")
    alice_token = _token(client, username="alice")
    bob_token = _token(client, username="bob")

    alice_me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {alice_token}"}
    )
    bob_me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {bob_token}"}
    )

    assert alice_me.status_code == 200
    assert alice_me.json()["username"] == "alice"
    assert bob_me.status_code == 200
    assert bob_me.json()["username"] == "bob"


def test_refresh_token_flow(client):
    _register(client)
    refresh_token = _login(client).json()["refresh_token"]

    response = client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    new_access = response.json()["access_token"]

    me_response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "alice"


def test_refresh_token_cannot_be_used_as_access_token(client):
    _register(client)
    refresh_token = _login(client).json()["refresh_token"]

    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 401


# ── Roles ──────────────────────────────────────────────────────────────────

def test_public_registration_cannot_assign_admin(client):
    response = _register(client, role="admin")
    assert response.status_code == 403

    from db.database import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("alice",)
        ).fetchone()
    finally:
        conn.close()
    assert row is None


def test_public_registration_cannot_assign_organizer(client):
    response = _register(client, role="organizador")
    assert response.status_code == 403


def test_admin_can_create_privileged_user(client):
    _create_user("root", "admin")
    admin_token = _token(client, username="root")

    response = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "coord",
            "email": "coord@example.invalid",
            "password": "password123",
            "role": "organizador",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "organizador"


def test_non_admin_cannot_create_privileged_user(client):
    _register(client)
    citizen_token = _token(client)

    response = client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "username": "coord",
            "email": "coord@example.invalid",
            "password": "password123",
            "role": "organizador",
        },
    )
    assert response.status_code == 403
