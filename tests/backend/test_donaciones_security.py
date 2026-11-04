"""Pruebas de seguridad P0 para el módulo de donaciones.

Las rutas de mutación usan autenticación personal JWT (no la clave compartida
X-Anexo-Key) y las respuestas públicas no exponen datos personales.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.no_auth_override


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from db import database

    path = tmp_path / "donaciones_security.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    database.init_db()
    yield path


@pytest.fixture
def client(db_path):
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client, username="donante", role="ciudadano"):
    from modules.auth.auth_service import UserCreate, create_user

    create_user(
        UserCreate(
            username=username,
            email=f"{username}@example.invalid",
            password="password123",
            role=role,
        ),
        allow_privileged=True,
    )
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload():
    return {
        "tipo": "recursos",
        "recurso": "Agua",
        "cantidad": "10 litros",
        "descripcion": "Agua potable",
        "contacto": "Persona Sintetica",
        "dni": "00000000T",
    }


def test_create_donation_requires_authentication(client):
    """POST /api/donaciones sin JWT devuelve 401, no un 201 anónimo."""
    response = client.post("/api/donaciones", json=_payload())
    assert response.status_code == 401


def test_create_donation_with_jwt_allowed(client):
    """Un ciudadano autenticado puede registrar una donación."""
    token = _register_and_login(client)
    response = client.post(
        "/api/donaciones", json=_payload(), headers=_headers(token)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recurso"] == "Agua"


def test_update_donation_status_requires_organizer_role(client):
    """Un ciudadano no puede cambiar el estado de una donación."""
    token = _register_and_login(client)
    response = client.patch(
        "/api/donaciones/1/estado",
        json={"estado": "entregada"},
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_public_response_does_not_expose_contact_or_dni(client):
    """Ni la creación ni el listado público exponen contacto o DNI."""
    token = _register_and_login(client)
    created = client.post(
        "/api/donaciones", json=_payload(), headers=_headers(token)
    )
    assert created.status_code == 201, created.text

    created_body = created.json()
    assert "contacto" not in created_body
    assert "contact" not in created_body
    assert "dni" not in created_body
    assert "Persona Sintetica" not in created.text
    assert "00000000T" not in created.text

    listed = client.get("/api/donaciones")
    assert listed.status_code == 200
    assert "Persona Sintetica" not in listed.text
    assert "00000000T" not in listed.text
    for donation in listed.json():
        assert "contacto" not in donation
        assert "dni" not in donation
