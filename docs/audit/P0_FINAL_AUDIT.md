# Auditoría final P0 — Anexo Risk (solo lectura)

Repositorio: `C:\Users\JUAN\Desktop\Proyectos\Anexo_Risk_limpio`
Rama: `feature/auth-jwt`
HEAD local: `fc251896fc1110aa4ed0a99a4d562524de3666ed`
Remoto: `https://github.com/juandelaf1/Anexo_Risk.git` (origin/feature/auth-jwt = mismo SHA, sin push de cambios locales)
No se han modificado archivos en esta auditoría.

## 1. Integridad del repositorio

- Rama actual: `feature/auth-jwt`
- Último commit: `fc251896fc1110aa4ed0a99a4d562524de3666ed`
- `git status`: 44 archivos modificados (tracked) + archivos sin seguimiento (conftest, tests de seguridad, models/feedback, auth.js, docs, etc.)
- `git diff --stat`: 1110 inserciones, 441 eliminaciones.
- Diferencia local/remoto: el remoto está en el SHA de referencia; los cambios locales NO han sido publicados (no push).
- Archivos sin seguimiento incluyen: `tests/backend/conftest.py`, `tests/backend/test_auth_security.py`, `tests/backend/test_donaciones_security.py`, `backend/models/__init__.py`, `backend/models/feedback.py`, `frontend/js/shared/auth.js`, `docs/audit/P0_AUTH_CLOSURE.md`.

## 2. Matriz de endpoints (mutaciones)

Todas las rutas de mutación (POST/PUT/PATCH/DELETE) de los módulos auditados están protegidas con `Depends(require_roles(...))` que valida JWT + rol. Excepciones justificadas:

| Ruta | Módulo | Tipo | Protección | Justificación |
|------|--------|------|------------|---------------|
| POST /check, /batch | accessibility | mutación (cálculo) | Sin auth | Cálculo sin persistencia; herramienta de consulta |
| POST /register | auth | mutación | Público (intencional) | Registro público |
| POST /login | auth | mutación | Público (intencional) | Login |
| POST /refresh | auth | mutación | Público (intencional) | Refresh con token |
| PATCH /{volunteer_id}/disponible | voluntariado | mutación | Token de voluntario (integración) | Auto-servicio del voluntario vía enlace email |

Resto de mutaciones (donaciones, incidentes, alertas, asignaciones, necesidades, recursos, organizaciones, voluntariado admin, personas, action_areas, alert_policies, correlation, live_ingestion, network_links, operational_nodes, outcome, regiones, source_registry, timeline, normalized_events, sync batch): **VERIFICADO** con JWT + rol + (recursos) control de organización.

## 3. JWT y autorización

- Persistencia real: `create_user()` inserta en `users` (migración 032). ✅
- bcrypt: `bcrypt.hashpw` / `bcrypt.checkpw` directo. ✅
- Firma y expiración: `jwt.encode/decode` con `JWT_SECRET_KEY` y `JWT_ALGORITHM`; `exp` validado por jose. ✅
- Usuario inexistente: `get_user()` retorna `None`. ✅
- Usuario desactivado: `get_current_active_user` lanza 403. ✅
- Autoasignación de admin: registro público restringido a `ciudadano`; `/api/auth/users` requiere rol admin. ✅
- Roles aplicados: `require_roles(...)` en todas las mutaciones sensibles. ✅
- Aislamiento organizacional: `_assert_organization_scope` en recursos (creación y actualización). ✅
- Sin usuarios ficticios/fallbacks: no hay usuarios de ejemplo; `get_user` retorna None. ✅
- Bypass identificado: ninguno en mutaciones sensibles. `X-Anexo-Key` solo en middleware/admin, no sustituye JWT personal.

## 4. Frontend

- Almacenamiento JWT: `localStorage` (`anexo_access_token`). ✅ (estándar para SPA)
- Envío Bearer: `authHeaders()` en `config.js` apiGet/apiPost/apiPatch/apiDelete. ✅
- Mutaciones migradas: assignments, donaciones, necesidades (mapa), incident needs (decision-center). ⚠️ Parcial — otras secciones (alertas, dashboard) aún usan fetch directo sin auth.
- Manejo de expiración: no implementado (sin refresh automático ni redirección a login). ⚠️ Pendiente P1.
- Exposición de tokens: no se loggea token en console. ✅
- Widget de login: botón 👤 en header con prompt. Básico pero funcional.

## 5. Datos y seed

- Datos sintéticos: sí (seed.py usa datos ficticios de Valencia).
- Seed idempotente: usa INSERT/DELETE; re-ejecutable. ✅
- Tests no dependen del orden: cada test de seguridad usa BD temporal aislada. ✅
- Seed no se ejecuta automáticamente en producción: solo en CI (paso explícito) y manualmente. ✅
- BD real no alterada en tests: tests usan `tmp_path` monkeypatcheado. ✅

## 6. test_global_sources.py

- Intenta importar `integrations.global_sources` (módulo inexistente).
- No existe con otro nombre; la funcionalidad de fuentes globales está en `services/` y `modules/source_registry/`.
- El test depende de red (llama APIs externas reales).
- Es obsoleto / fuera del alcance actual del MVP.
- Corrección mínima propuesta: eliminar el archivo o reescribirlo para probar `source_registry` + `region_source_resolution` con datos locales (sin red). Por ahora se ignora en CI con `--ignore`.

## 7. CI

Workflow local vs remoto:
- Ramas: push `main, anexo-risk, feature/auth-jwt`; PR `main, dev, anexo-risk, feature/auth-jwt`. ✅ (remoto no tenía feature/auth-jwt)
- Variables efímeras: generadas con `secrets.token_urlsafe(32)` + `::add-mask::` + `GITHUB_ENV`. ✅
- Sin secretos estáticos. ✅
- Instalación: pip install requirements + requirements-dev. ✅
- Imports: `from main import app`. ✅
- Tests: `pytest tests/backend/ -v --ignore=test_global_sources.py` + seed step. ✅
- Lo que debe pasar en CI al publicar: todos los tests excepto el ignorado (network-dependent).

## 8. Informe final

### Hallazgos confirmados
- Autenticación JWT real implementada y verificada con 34 tests de seguridad.
- Todas las mutaciones sensibles protegidas con JWT + rol.
- `X-Anexo-Key` degradada a credencial de integración/admin.
- Privacidad de donaciones (sin contacto/DNI en respuestas públicas).
- CI preparada para feature/auth-jwt con claves efímeras.
- Frontend tiene helpers y widget mínimo de auth.

### Riesgos residuales
- Frontend: no todas las secciones migradas a helpers autenticados (alertas, dashboard).
- Sin refresh automático de token ni redirección a login en frontend.
- Multi-tenant: vinculación usuario→org por username (frágil).
- `X-Anexo-Key` sigue existiendo (rotarla).
- `test_global_sources.py` obsoleto (ignorado).
- `datetime.utcnow()` deprecado.

### Decisión recomendada

**PUBLICAR CON LIMITACIONES DOCUMENTADAS**

El P0 de seguridad (autenticación y autorización efectivas) está completo y verificado. Las limitaciones restantes (frontend parcial, multi-tenant, refresh automático) son P1/P2 y no bloquean la publicación de la rama de seguridad, siempre que se documenten.
