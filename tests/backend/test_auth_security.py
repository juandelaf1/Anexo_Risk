"""Pruebas de seguridad de rutas y autorización por rol.

Usan SQLite real y JWT real. No se sustituye `get_user` por un mock.
"""
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.no_auth_override


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from db import database

    path = tmp_path / "auth_security.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    database.init_db()
    yield path


@pytest.fixture
def client(db_path):
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def _create_user(username: str, role: str, password: str = "password123"):
    from modules.auth.auth_service import UserCreate, create_user

    return create_user(
        UserCreate(
            username=username,
            email=f"{username}@example.invalid",
            password=password,
            role=role,
        ),
        allow_privileged=True,
    )


def _token(client: TestClient, username: str, password: str = "password123") -> str:
    response = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


NEED_PAYLOAD = {"tipo": "agua", "latitud": 40.0, "longitud": -3.0}


def test_sensitive_mutation_without_authentication_is_rejected(client):
    response = client.post("/api/necesidades", json=NEED_PAYLOAD)
    assert response.status_code == 401


def test_shared_key_does_not_replace_personal_authentication(client):
    """X-Anexo-Key es credencial de integración, no autenticación personal."""
    from config import ANEXO_ADMIN_KEY

    response = client.post(
        "/api/donaciones",
        json={
            "tipo": "recursos",
            "recurso": "Agua",
            "cantidad": "1",
            "contacto": "Persona Sintetica",
        },
        headers={"X-Anexo-Key": ANEXO_ADMIN_KEY},
    )
    assert response.status_code == 401


def test_citizen_cannot_execute_operational_mutation(client):
    _create_user("citizen", "ciudadano")
    token = _token(client, "citizen")

    response = client.patch(
        "/api/necesidades/1",
        json={"estado": "cubierta"},
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_organizer_can_create_need(client):
    _create_user("organizer", "organizador")
    token = _token(client, "organizer")

    response = client.post(
        "/api/necesidades", json=NEED_PAYLOAD, headers=_headers(token)
    )
    assert response.status_code == 201, response.text
    assert response.json()["tipo"] == "agua"


def test_only_admin_can_create_organizations(client):
    _create_user("citizen", "ciudadano")
    _create_user("root", "admin")

    citizen_response = client.post(
        "/api/organizations",
        json={"name": "Org Ciudadana", "type": "ong"},
        headers=_headers(_token(client, "citizen")),
    )
    assert citizen_response.status_code == 403

    admin_response = client.post(
        "/api/organizations",
        json={"name": "Org Admin", "type": "ong"},
        headers=_headers(_token(client, "root")),
    )
    assert admin_response.status_code == 201, admin_response.text


def test_cross_organization_resource_mutation_is_rejected(client):
    from modules.organizaciones.models import (
        create_operational_user,
        create_organization,
    )

    org_a = create_organization("Organizacion A", "ong", "Region A")
    org_b = create_organization("Organizacion B", "ong", "Region B")
    create_operational_user(org_a["id"], "orga", "Usuario A", "operador")
    create_operational_user(org_b["id"], "orgb", "Usuario B", "operador")
    _create_user("orga", "organizador")
    _create_user("orgb", "organizador")

    token_a = _token(client, "orga")
    token_b = _token(client, "orgb")

    resource_a = client.post(
        "/api/resources",
        json={
            "organization_id": org_a["id"],
            "type": "ambulancia",
            "name": "Ambulancia A",
        },
        headers=_headers(token_a),
    )
    assert resource_a.status_code == 201, resource_a.text

    resource_b = client.post(
        "/api/resources",
        json={
            "organization_id": org_b["id"],
            "type": "ambulancia",
            "name": "Ambulancia B",
        },
        headers=_headers(token_b),
    )
    assert resource_b.status_code == 201, resource_b.text

    # A no puede modificar un recurso de B.
    update_other = client.patch(
        f"/api/resources/{resource_b.json()['id']}",
        json={"status": "retirado"},
        headers=_headers(token_a),
    )
    assert update_other.status_code == 403

    # A tampoco puede crear un recurso a nombre de B.
    create_for_other = client.post(
        "/api/resources",
        json={
            "organization_id": org_b["id"],
            "type": "ambulancia",
            "name": "Intento cruzado",
        },
        headers=_headers(token_a),
    )
    assert create_for_other.status_code == 403


def test_admin_can_modify_any_organization_resource(client):
    from modules.organizaciones.models import create_organization

    org = create_organization("Organizacion Admin", "ong", "Region")
    _create_user("root", "admin")
    token = _token(client, "root")

    created = client.post(
        "/api/resources",
        json={
            "organization_id": org["id"],
            "type": "generador",
            "name": "Generador",
        },
        headers=_headers(token),
    )
    assert created.status_code == 201, created.text

    updated = client.patch(
        f"/api/resources/{created.json()['id']}",
        json={"status": "en_mantenimiento"},
        headers=_headers(token),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "en_mantenimiento"
