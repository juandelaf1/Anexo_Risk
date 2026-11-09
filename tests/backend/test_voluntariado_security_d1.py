"""Pruebas de seguridad D1 (fixes 1,4,5) para voluntariado.

Cambios mínimos: auth en listado, no mutación por GET+token en query (confirmación->POST),
token de disponibilidad solo en cabecera. Fork P7 (Equipo Nexo, MIT).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.no_auth_override


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from db import database
    from modules.voluntariado import models

    path = tmp_path / "voluntariado_security_d1.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    database.init_db()
    models._schema_ready = False
    yield path
    models._schema_ready = False


@pytest.fixture
def client(db_path):
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client, username="org", role="organizador"):
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
    response = client.post("/api/auth/login", data={"username": username, "password": "password123"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_pending(volunteer_token="vol_tok_d1", admin_token="adm_tok_d1"):
    from modules.voluntariado import models

    return models.create_volunteer_pending(
        name="María García López",
        contact="maria@example.com",
        skills="Primeros auxilios",
        availability="inmediata",
        admin_token=admin_token,
        volunteer_token=volunteer_token,
    )


def test_list_volunteers_requires_auth(client):
    """D1-1: GET /api/voluntarios no debe exponer listado sin autenticación."""
    r = client.get("/api/voluntarios")
    assert r.status_code == 401


def test_list_volunteers_with_auth_ok(client):
    token = _register_and_login(client)
    r = client.get("/api/voluntarios", headers=_headers(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_email_approve_get_does_not_mutate_state(client):
    """D1-2: GET con token en URL no debe mutar estado; devuelve confirmación HTML."""
    v = _create_pending(admin_token="adm_confirm_token_123")
    r = client.get(f"/api/voluntarios/{v['id']}/aprobar", params={"token": "adm_confirm_token_123"})
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    # sigue pendiente
    from modules.voluntariado import models
    assert models.get_volunteer(v["id"])["estado"] == "pendiente"


def test_email_approve_post_confirms_with_token_in_body(client):
    """D1-2: acción real vía POST con token en cuerpo."""
    v = _create_pending(admin_token="adm_post_token_12345")
    with patch("modules.voluntariado.email_service.send_volunteer_approved_email"):
        r = client.post(f"/api/voluntarios/{v['id']}/aprobar-email", json={"token": "adm_post_token_12345"})
    assert r.status_code == 200
    assert r.json()["estado"] == "aprobado"


def test_email_reject_post_confirms_with_token_in_body(client):
    v = _create_pending(admin_token="adm_rej_token_123456")
    with patch("modules.voluntariado.email_service.send_volunteer_rejected_email"):
        r = client.post(f"/api/voluntarios/{v['id']}/rechazar-email", json={"token": "adm_rej_token_123456"})
    assert r.status_code == 200
    assert r.json()["estado"] == "rechazado"


def test_availability_rejects_token_in_query(client):
    """D1-3: no aceptar token en query (solo cabecera)."""
    from modules.voluntariado import services

    v = _create_pending(volunteer_token="vol_hdr")
    services.approve_volunteer(v["id"], via_api=True)
    r = client.patch(
        f"/api/voluntarios/{v['id']}/disponible?token=vol_hdr",
        json={"disponible": False},
    )
    assert r.status_code == 401


def test_availability_accepts_header_token(client):
    """D1-3: header aceptado (la mutación de disponibilidad se aplica)."""
    from modules.voluntariado import services, models
    from main import app
    from fastapi.testclient import TestClient

    v = _create_pending(volunteer_token="vol_hdr_token_12345")
    services.approve_volunteer(v["id"], via_api=True)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.patch(
            f"/api/voluntarios/{v['id']}/disponible",
            json={"disponible": False},
            headers={"X-Volunteer-Token": "vol_hdr_token_12345"},
        )
    assert r.status_code != 401
    updated = models.get_volunteer(v["id"])
    # disponible puede ser 0/False según representación
    assert updated is not None and (updated.get("disponible") in (0, False) or updated.get("is_available") is False)
