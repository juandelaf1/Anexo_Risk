# Cierre P0 — Autenticación real Anexo_Risk

Repositorio: `C:\Users\JUAN\Desktop\Proyectos\Anexo_Risk_limpio`
Rama: `feature/auth-jwt`
HEAD local: `fc251896fc1110aa4ed0a99a4d562524de3666ed` (sin commits nuevos)
Remoto: `https://github.com/juandelaf1/Anexo_Risk.git`
No se han realizado commits, pushes, merges ni despliegues.

## 1. Cambios principales

### Autenticación real (JWT + SQLite `users`)
- `backend/modules/auth/auth_service.py`:
  - `create_user()` persiste en la tabla `users` (migración 032).
  - `get_user()` recupera exactamente el usuario solicitado por `username`; inexistente → `None`.
  - Hashing con `bcrypt` directo (se eliminó la dependencia rota de `passlib` con `bcrypt>=4.1`).
  - `verify_password()` usa `bcrypt.checkpw`.
  - `get_current_active_user` rechaza usuarios inactivos (403).
  - `require_roles(*roles)` para autorización por rol.
  - `get_user_organization_id()` vincula identidad JWT con `operational_users` (sin tabla nueva).
  - Registro público restringido a `ciudadano`; `admin`/`organizador` solo vía `/api/auth/users` (admin).
- `backend/modules/auth/routes.py`:
  - `register`, `login`, `refresh` (body JSON), `me`, `POST /users` (admin).
  - Refresh token se recibe en JSON (`RefreshTokenRequest`).

### Rutas de mutación protegidas
Se añadió `Depends(require_roles(...))` a POST/PUT/PATCH/DELETE en:
Donaciones, Incidentes, Alertas, Asignaciones, Necesidades, Recursos, Organizaciones, Voluntariado, Personas, Action Areas, Alert Policies, Correlation, Live Ingestion, Network Links, Operational Nodes, Outcome, Regions, Source Registry, Timeline, Normalized Events, Sync batch.

`X-Anexo-Key` se mantiene solo como credencial de integración/administración (middleware y endpoints de admin); ya no sustituye la autenticación personal.

### Privacidad de donaciones
- `DonationResponse` usa `extra="ignore"` para descartar `contacto`/`dni` de la respuesta pública.
- `models/donaciones` sigue persistiendo PII en BD (no se expone).

### Migración 032 idempotente
- `CREATE TABLE IF NOT EXISTS` y `INSERT OR IGNORE` para poder re-ejecutar `init_db()`.

### Import de la aplicación
- `backend/models/__init__.py` y `backend/models/feedback.py` creados (faltaban; bloqueaban import de `incidentes`/`outcome`).
- Imports faltantes corregidos en `organizaciones` y `recursos`.

### CI
- `.github/workflows/ci.yml`: añadida rama `feature/auth-jwt` en push y PR.
- Claves `ANEXO_ADMIN_KEY` y `JWT_SECRET_KEY` se generan efímeramente en tiempo de ejecución con `secrets.token_urlsafe(32)`, se enmascaran con `::add-mask::` y se inyectan vía `GITHUB_ENV`. Sin secretos estáticos.

## 2. Rutas que siguen sin protección y motivo

- `GET` de solo lectura en todos los módulos (no mutan datos).
- `accessibility` POST `/check` y `/batch`: cálculo sin persistencia; se dejan públicos por ser herramienta de consulta.
- `voluntariado` GET `/aprobar` y `/rechazar` por token de email: enlace administrativo por email (credencial de integración), no JWT personal. Pendiente de convertir a JWT en P1.
- `middleware/auth.py` DELETE con `X-Anexo-Key`: gestión de credencial de integración, no identidad personal.

## 3. Tests ejecutados

Comando estándar (entorno local):
```
ANEXO_ADMIN_KEY=test-key-123 JWT_SECRET_KEY=test-jwt-secret-123 DATABASE_URL=sqlite:///./backend/anexo_risk.db PYTHONPATH=backend
```

- `tests/backend/test_auth.py`: 16 passed (12.6s)
- `tests/backend/test_auth_security.py` + `test_donaciones_security.py`: 21 passed (24s)
- Suite completa (ignorando 2 archivos con errores de recolección pre-existentes): 653 passed, 5 failed, 8 skipped (115.7s)

Fallos restantes (no relacionados con autenticación):
- `test_db_integrity.py::TestDataCompleteness::test_at_least_one_organization` (BD vacía, sin seed)
- `test_db_integrity.py::TestDataCompleteness::test_at_least_one_operational_user` (idem)
- `test_fase4.py::TestRegionSourceResolution::*` (3) — fuentes vacías para región nueva (lógica pre-existente)

Errores de recolección pre-existentes (módulos no presentes en el repo):
- `tests/backend/test_correlation.py` (importa `correlate_earthquakes` inexistente)
- `tests/backend/test_global_sources.py` (importa `integrations.global_sources` inexistente)

Verificación de imports: `from main import app` → OK, 44 rutas.
Migraciones: `init_db()` aplica 032 sin error; idempotente.

## 4. Estado de git

- Rama: `feature/auth-jwt`
- HEAD: `fc251896fc1110aa4ed0a99a4d562524de3666ed` (sin cambios de SHA)
- Cambios sin stage: múltiples archivos modificados + nuevos (conftest, tests de seguridad, models/feedback, etc.)
- No hay commits ni pushes.

## 5. Estado de CI remota

No verificable: no se ha autorizado commit/push. El workflow local ahora dispara en `feature/auth-jwt` por push y PR, y genera claves efímeras en tiempo de ejecución. CI remota pendiente de ejecución del SHA correspondiente.

## 6. Riesgos P1/P2 pendientes

- Multi-tenant: la vinculación usuario→organización se resuelve por `operational_users.username`; no hay gestión de usuarios organizacionales desde JWT todavía.
- `X-Anexo-Key` sigue existiendo para integración; conviene rotarla y limitarla a endpoints administrativos.
- Tests de integración frontend no cubren el nuevo flujo JWT.
- `test_db_integrity` y `test_fase4` region sources dependen de datos seed; fuera del alcance P0.
- `datetime.utcnow()` deprecado en Python 3.12+; migrar a `datetime.now(timezone.utc)` en P1.
