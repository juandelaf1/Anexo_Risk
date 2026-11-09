# D1 — Matriz Auth/PII (SOLO MATRIZ, sin cambios de lógica)

- **Fecha:** 2026-11-09
- **Alcance:** revisión estática de `backend/modules/voluntariado` y `backend/modules/donaciones` (rutas/schemas). **No se modifica lógica, rutas, schemas ni comportamiento.**
- **Estado:** **pendiente confirmación explícita** para aplicar fixes (`solo matriz+fixes 1,4,5` / `completo`, patch vs directo en fork). P7: fork de **Equipo Nexo (MIT)** — preservar atribución/licencia; cambios mínimos y seguros.
- **Fuentes revisadas:** `voluntariado/routes.py`, `voluntariado/schemas.py`, `donaciones/routes.py`, `donaciones/schemas.py`.

## Resumen

| ID | Módulo | Endpoint / patrón | Hallazgo | Severidad | PII afectada (potencial) | Fix sugerido (NO aplicado) |
|---|---|---|---|---|---|---|
| D1-1 | voluntariado | `GET /api/voluntarios` (sin auth) | Listado público de voluntarios aprobados; expone datos personales/operativos (nombre, localidad, disponibilidad, habilidades/certificaciones, transporte). | Alta | Nombre, localidad, patrones de disponibilidad, perfil/capacidades | Restringir por rol/scope o devolver vista pública mínima/no identificable; paginación; documentar base legal/consentimiento. |
| D1-2 | voluntariado | `GET /{id}/aprobar?token=...`, `GET /{id}/rechazar?token=...` | **GET con efecto de cambio de estado** + token en query (filtrable en logs/proxy/referer/historial). Riesgo CSRF si se consume desde navegador sin protección. | Alta | Token de administración/acción | Usar POST con token en header/body o enlace de un solo uso server-side; rotar/expirar tokens; proteger CSRF; no loguear query sensible. |
| D1-3 | voluntariado | `PATCH /{id}/disponible` acepta `X-Volunteer-Token` **o** `token` (query) | Token sensible aceptado en query (leakage en logs/telemetría). Header es preferible. | Media/Alta | Token de voluntario | Aceptar solo `X-Volunteer-Token`/Authorization; rechazar query token (o deprecar con aviso); no registrar tokens. |
| D1-4 | voluntariado | `POST /` (registro JSON/multipart) | Recoge PII sensible (DNI, fecha nacimiento, teléfono, contacto). Requiere auth/roles en ruta, pero el flujo de consentimiento/minimización/retención debe verificarse en service/storage. | Media | DNI, nacimiento, teléfono, contacto, ubicación/localidad | Revisar minimización, cifrado/retención, acceso mínimo, logs sin PII, consentimiento; validar que solo roles autorizados acceden a registros completos. |
| D1-5 | donaciones | `GET /api/donaciones`, `GET /api/donaciones/{id}` (sin auth) | Listado/detalle públicos. **Positivo:** `DonationResponse` omite `contacto`/`DNI` (schema documenta). Verificar que modelos/services no serialicen PII por otros caminos. | Media | Potencial si se filtra por joins/campos extra (hoy mitigado en response) | Mantener response mínima; añadir auth/rate-limit si se requiere; tests que impidan exposición de contacto/DNI. |
| D1-6 | donaciones | `POST /api/donaciones` almacena `contacto`/`DNI` | PII almacenada (legítimo para coordinación) pero requiere controles de acceso/retención/minimización en lectura/exportación. | Media | Contacto, DNI | Verificar endpoints admin/export, cifrado/retención, auditoría de acceso, sin PII en logs. |

## Notas (AGENTS Anexo_Risk)
- Prioridad: **datos correctos y seguridad** antes que features. No inventar datos; no copiar auth insegura de GeoRisk Finder.
- `DonationResponse` ya excluye PII sensible — preservar este patrón.
- Cualquier fix debe incluir **tests** (API/seguridad), no romper contratos deliberadamente, y mantener atribución P7 (Equipo Nexo, MIT).

## Estado de implementación (2026-11-09)
- **Aplicado y pusheado** en `feature/auth-jwt` (`juandelaf1/Anexo_Risk`): fixes **1,4,5** + redacción de tokens en logs dummy (`c3b55a7`,`7bfbedd`). Tests voluntariado **110 passed** (incl. 7 seguridad D1). Cambios no commiteados en tiempo de parche → ya commiteados.
- **D1-5 (donaciones):** `GET /api/donaciones` y `GET /{id}` públicos pero **`DonationResponse` omite `contacto`/`DNI`**; verificado por `tests/backend/test_donaciones_security.py` (**4 passed**). No se añadió auth de lectura para evitar romper contrato (riesgo residual bajo con respuesta PII-safe).
- **Pendiente (“completo” profundo, backlog aprobado/escalable):** retención/minimización/cifrado, auditoría de accesos a registros con PII, revisión de logs/exports/admin y controles transversales; ejecutar con plan incremental + tests.