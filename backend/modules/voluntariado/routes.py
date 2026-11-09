"""Endpoints de voluntariado (Equipo 3, núcleo).

Este archivo recibe las peticiones HTTP relacionadas con voluntarios.
La lógica de negocio vive en services.py y el acceso a datos en models.py.
"""
import json

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

from middleware.auth import requiere_clave_organizador
from modules.voluntariado.file_service import InvalidVolunteerDocument
from modules.voluntariado.models import (
    InvalidVolunteerTransition,
    get_volunteer_documents,
    list_pending_volunteers,
    list_volunteers_for_frontend,
    update_coordination_status,
)
from modules.auth.auth_service import (
    get_current_active_user,
    get_current_user,
    require_roles,
)

from modules.voluntariado.schemas import (
    VolunteerActionResponse,
    VolunteerAvailabilityUpdate,
    VolunteerCoordinationUpdate,
    VolunteerCreate,
    VolunteerFrontendCreate,
    VolunteerFrontendRegistrationResponse,
    VolunteerFrontendResponse,
    VolunteerPendingResponse,
    VolunteerResponse,
)
from modules.voluntariado import services

router = APIRouter(prefix="/api/voluntarios", tags=["voluntariado"])


def _error_response(status_code: int, error: str, detalle: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "detalle": detalle},
    )


class EmailActionToken(BaseModel):
    token: str = Field(min_length=10, max_length=512)


def _confirmation_page(action: str, volunteer_id: int, token: str) -> str:
    # token is embedded for POST body submission (not in mutation URL/query to server logs beyond initial GET);
    # action is performed via POST. Keep page minimal (no external deps).
    safe_action = "aprobar" if action == "aprobar" else "rechazar"
    label = "Aprobar" if action == "aprobar" else "Rechazar"
    import html
    t = html.escape(token, quote=True)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Confirmar {label}</title></head>
<body><h3>Confirmar acción: {label} voluntario #{volunteer_id}</h3>
<p>Por seguridad, la acción se ejecuta mediante POST (no con un simple enlace GET).</p>
<button id="go">{label}</button> <span id="out"></span>
<script>
document.getElementById('go').onclick = async () => {{
  const out = document.getElementById('out'); out.textContent = 'Procesando...';
  try {{
    const r = await fetch('/api/voluntarios/{volunteer_id}/{safe_action}-email', {{
      method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{token: "{t}"}})
    }});
    const d = await r.json().catch(()=>({{}}));
    out.textContent = r.ok ? (d.mensaje || 'OK') : (d.detalle || d.error || 'Error');
  }} catch(e) {{ out.textContent = 'Error de red'; }}
}};
</script></body></html>"""


def _normalize_uploads(documentos: list[UploadFile] | None) -> list[UploadFile]:
    if not documentos:
        return []
    return [upload for upload in documentos if upload.filename]


@router.get(
    "",
    response_model=list[VolunteerFrontendResponse],
    dependencies=[Depends(get_current_active_user)],
)
def get_volunteers(
    coordination_status: str | None = Query(default=None, alias="status"),
    skill: str | None = Query(default=None, alias="habilidad"),
    is_available: bool | None = Query(default=None, alias="disponible"),
):
    """Devuelve voluntarios aprobados (requiere autenticación; minimización PII)."""

    return list_volunteers_for_frontend(
        coordination_status=coordination_status,
        skill=skill,
        is_available=is_available,
    )


@router.get(
    "/pendientes",
    response_model=list[VolunteerPendingResponse],
    dependencies=[Depends(get_current_active_user)],
)
def get_pending_volunteers():
    """Lista solicitudes pendientes de validación (solo administrador)."""

    pending = list_pending_volunteers()
    return [
        {
            **volunteer,
            "documentos": [
                {
                    "id": document["id"],
                    "nombre_original": document["nombre_original"],
                    "tipo_mime": document["tipo_mime"],
                    "creado_en": document["creado_en"],
                }
                for document in get_volunteer_documents(volunteer["id"])
            ],
        }
        for volunteer in pending
    ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("ciudadano", "organizador", "admin"))],
    responses={
        status.HTTP_201_CREATED: {
            "content": {
                "application/json": {
                    "schema": VolunteerFrontendRegistrationResponse.model_json_schema()
                }
            }
        }
    },
)
async def create_new_volunteer(request: Request):
    """Registra una solicitud pendiente (JSON frontend o multipart legacy)."""

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            raw_payload = await request.json()
            payload = VolunteerFrontendCreate.model_validate(raw_payload)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            ValidationError,
        ) as exc:
            import logging
            logging.getLogger(__name__).warning("Registro voluntario inválido: %s", exc)
            return _error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Datos de registro no válidos",
                "Revise los campos enviados",
            )

        return services.register_volunteer_from_frontend(payload)

    form = await request.form()

    try:
        volunteer_data = VolunteerCreate(
            nombre=form.get("nombre"),
            contacto=form.get("contacto"),
            habilidades=form.get("habilidades"),
            disponibilidad=form.get("disponibilidad") or "inmediata",
        )
    except ValidationError as exc:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Datos de registro no válidos",
            str(exc),
        )

    uploads: list[UploadFile] = []

    for value in form.getlist("documentos"):
        if isinstance(value, UploadFile) and value.filename:
            uploads.append(value)

    try:
        return services.register_volunteer(
            volunteer_data=volunteer_data,
            documents=uploads,
        )
    except InvalidVolunteerDocument as exc:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "Documento no válido",
            str(exc),
        )


@router.get("/{volunteer_id}/aprobar", response_class=HTMLResponse)
def approve_volunteer_from_email_page(volunteer_id: int, token: str = Query(...)):
    """Página de confirmación (no muta estado por GET). La acción real se ejecuta vía POST con token en cuerpo."""
    return HTMLResponse(_confirmation_page("aprobar", volunteer_id, token))


@router.get("/{volunteer_id}/rechazar", response_class=HTMLResponse)
def reject_volunteer_from_email_page(volunteer_id: int, token: str = Query(...)):
    """Página de confirmación (no muta estado por GET). La acción real se ejecuta vía POST con token en cuerpo."""
    return HTMLResponse(_confirmation_page("rechazar", volunteer_id, token))


@router.post("/{volunteer_id}/aprobar-email", response_model=VolunteerActionResponse)
def approve_volunteer_from_email_confirm(volunteer_id: int, payload: EmailActionToken):
    """Ejecuta aprobación desde confirmación (token en cuerpo, no en query)."""
    result = services.approve_volunteer(volunteer_id, admin_token=payload.token, via_api=False)
    if result.get("error") == "not_found":
        return _error_response(
            status.HTTP_404_NOT_FOUND, "Solicitud no encontrada",
            f"No existe una solicitud válida con el identificador {volunteer_id}.",
        )
    if result.get("error") == "invalid_transition":
        return _error_response(
            status.HTTP_409_CONFLICT, "Transición no válida",
            "La solicitud ya no está pendiente de validación.",
        )
    return result


@router.post("/{volunteer_id}/rechazar-email", response_model=VolunteerActionResponse)
def reject_volunteer_from_email_confirm(volunteer_id: int, payload: EmailActionToken):
    """Ejecuta rechazo desde confirmación (token en cuerpo, no en query)."""
    result = services.reject_volunteer(volunteer_id, admin_token=payload.token, via_api=False)
    if result.get("error") == "not_found":
        return _error_response(
            status.HTTP_404_NOT_FOUND, "Solicitud no encontrada",
            f"No existe una solicitud válida con el identificador {volunteer_id}.",
        )
    if result.get("error") == "invalid_transition":
        return _error_response(
            status.HTTP_409_CONFLICT, "Transición no válida",
            "La solicitud ya no está pendiente de validación.",
        )
    return result


@router.post(
    "/{volunteer_id}/aprobar",
    response_model=VolunteerActionResponse,
    dependencies=[Depends(require_roles("organizador", "admin"))],
)
def approve_volunteer_from_api(volunteer_id: int):
    """Aprueba una solicitud pendiente usando la clave de organizador."""

    result = services.approve_volunteer(volunteer_id, via_api=True)
    if result.get("error") == "not_found":
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "Solicitud no encontrada",
            f"No existe una solicitud con el identificador {volunteer_id}.",
        )
    if result.get("error") == "invalid_transition":
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Transición no válida",
            "La solicitud ya no está pendiente de validación.",
        )
    return result


@router.post(
    "/{volunteer_id}/rechazar",
    response_model=VolunteerActionResponse,
    dependencies=[Depends(require_roles("organizador", "admin"))],
)
def reject_volunteer_from_api(volunteer_id: int):
    """Rechaza una solicitud pendiente usando la clave de organizador."""

    result = services.reject_volunteer(volunteer_id, via_api=True)
    if result.get("error") == "not_found":
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "Solicitud no encontrada",
            f"No existe una solicitud con el identificador {volunteer_id}.",
        )
    if result.get("error") == "invalid_transition":
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Transición no válida",
            "La solicitud ya no está pendiente de validación.",
        )
    return result

@router.patch(
    "/{volunteer_id}",
    response_model=VolunteerFrontendResponse,
    dependencies=[Depends(require_roles("organizador", "admin"))],
)

def update_volunteer_coordination_status(
    volunteer_id: int,
    update: VolunteerCoordinationUpdate,
):
    """Actualiza el estado operativo de coordinación de un voluntario."""

    try:
        updated = update_coordination_status(
            volunteer_id=volunteer_id,
            status=update.status.value,
        )
    except InvalidVolunteerTransition:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Operación no permitida",
            "Solo los voluntarios aprobados pueden cambiar su estado operativo.",
        )

    if updated is None:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "Voluntario no encontrado",
            f"No existe un voluntario aprobado con el identificador {volunteer_id}.",
        )

    return updated


@router.patch("/{volunteer_id}/disponible", response_model=VolunteerResponse)
def update_volunteer_availability(
    volunteer_id: int,
    update: VolunteerAvailabilityUpdate,
    x_volunteer_token: str | None = Header(default=None, alias="X-Volunteer-Token"),
):
    """Permite al voluntario aprobado marcar disponibilidad (token solo en cabecera, no en URL)."""

    volunteer_token = x_volunteer_token
    if volunteer_token is None:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token requerido",
            "Debes enviar la cabecera X-Volunteer-Token.",
        )

    try:
        updated = services.update_availability(
            volunteer_id=volunteer_id,
            is_available=update.is_available,
            volunteer_token=volunteer_token,
        )
    except InvalidVolunteerTransition:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Operación no permitida",
            "Solo los voluntarios aprobados pueden cambiar su disponibilidad.",
        )

    if updated is None:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "Voluntario no encontrado",
            "No existe un voluntario aprobado con ese identificador y token.",
        )

    return updated
