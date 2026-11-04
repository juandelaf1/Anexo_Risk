"""Configuración común de las pruebas del backend de Anexo Risk.

Las pruebas funcionales existentes no fueron escritas con autenticación JWT.
Para no reescribirlas todas de golpe, se sustituye la dependencia de
autenticación por un usuario sintético con rol admin **solo en las pruebas
funcionales**. Las pruebas de seguridad usan el marcador
``no_auth_override`` y ejercitan el sistema real (SQLite + JWT).
"""
import os

import pytest

# Deben existir antes de importar `main`/`config`.
os.environ.setdefault(
    "ANEXO_ADMIN_KEY", "test-only-admin-key-not-for-production"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-only-jwt-secret-not-for-production-0123456789abcdef"
)
os.environ.setdefault("DATABASE_URL", "sqlite:///./anexo_risk.db")


@pytest.fixture(autouse=True)
def _functional_auth_override(request):
    """Inyecta un usuario sintético en pruebas funcionales.

    Las pruebas marcadas con ``@pytest.mark.no_auth_override`` quedan fuera
    de esta sustitución para probar el flujo JWT real.
    """
    if request.node.get_closest_marker("no_auth_override"):
        yield
        return

    from main import app
    from modules.auth.auth_service import (
        User,
        get_current_active_user,
        get_current_user,
    )

    def _fake_user() -> User:
        return User(
            username="functional-test-user",
            email="functional-test@example.invalid",
            role="admin",
            is_active=True,
        )

    app.dependency_overrides[get_current_active_user] = _fake_user
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)
