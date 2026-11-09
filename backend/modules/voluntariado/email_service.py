"""Envío de correos del módulo de voluntariado.

En modo dummy no usa SMTP real: imprime el contenido en consola para
facilitar pruebas locales sin configurar un servidor de correo.
"""
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from config import (
    ADMIN_EMAIL,
    BASE_URL,
    EMAIL_DUMMY_MODE,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)
EMAIL_LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "emails"


def _build_document_list(documents: list[dict[str, Any]]) -> str:
    if not documents:
        return "- (sin documentos adjuntos)"

    return "\n".join(
        f"- {document['nombre_original']} ({document['tipo_mime']})"
        for document in documents
    )


def _redact_sensitive(text: str) -> str:
    import re
    # Redact tokens in URLs/bodies for dummy logs (dev hygiene, D1)
    text = re.sub(r"([?&]token=)[^&\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(X-Volunteer-Token:\s*)[^\s]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    return text


def _deliver_email(to_email: str, subject: str, body: str) -> None:
    if EMAIL_DUMMY_MODE:
        redacted = _redact_sensitive(body)
        logger.info("EMAIL DUMMY to=%s subject=%s (body redacted in log)", to_email, subject)
        print(f"\n=== EMAIL DUMMY ===\nPara: {to_email}\nAsunto: {subject}\n\n{redacted}\n")
        EMAIL_LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = to_email.replace("@", "_at_").replace(".", "_")
        log_file = EMAIL_LOG_DIR / f"{safe_name}.txt"
        log_file.write_text(
            f"Para: {to_email}\nAsunto: {subject}\n\n{redacted}",
            encoding="utf-8",
        )
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_USER
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)


def send_admin_new_volunteer_email(
    volunteer: dict[str, Any],
    documents: list[dict[str, Any]],
    approve_url: str,
    reject_url: str,
) -> None:
    """Notifica al administrador de una nueva solicitud pendiente."""

    subject = f"[Anexo Risk] Nueva solicitud de voluntariado: {volunteer['nombre']}"
    body = (
        "Se ha recibido una nueva solicitud de voluntariado.\n\n"
        f"Nombre: {volunteer['nombre']}\n"
        f"Contacto: {volunteer['contacto']}\n"
        f"Habilidades: {volunteer['habilidades']}\n"
        f"Disponibilidad declarada: {volunteer['disponibilidad']}\n\n"
        "Documentos adjuntos:\n"
        f"{_build_document_list(documents)}\n\n"
        "Acciones:\n"
        f"- Aprobar: {approve_url}\n"
        f"- Rechazar: {reject_url}\n\n"
        "También puedes usar la API protegida con la cabecera X-Anexo-Key."
    )
    _deliver_email(ADMIN_EMAIL, subject, body)


def send_volunteer_approved_email(
    volunteer: dict[str, Any],
    availability_url: str,
    volunteer_token: str = "",
) -> None:
    """Confirma aprobación. No incluye token en URL (evitar leakage en logs/referers)."""

    subject = "[Anexo Risk] Tu solicitud de voluntariado ha sido aprobada"
    token_line = (
        f"Cabecera requerida: X-Volunteer-Token: {volunteer_token}\n"
        if volunteer_token
        else "Contacta con el equipo organizador para recibir tu token de acceso.\n"
    )
    body = (
        f"Hola {volunteer['nombre']},\n\n"
        "Tu solicitud de voluntariado en Anexo Risk ha sido aprobada.\n"
        "Ya puedes aparecer como disponible o no disponible en la app.\n\n"
        f"Endpoint: PATCH {availability_url}\n"
        f"{token_line}"
        "Ejemplo: PATCH con JSON {\"disponible\": true} y la cabecera anterior.\n\n"
        "Gracias por colaborar."
    )
    _deliver_email(volunteer["contacto"], subject, body)


def send_volunteer_rejected_email(volunteer: dict[str, Any]) -> None:
    """Informa al voluntario de que su solicitud no ha sido aceptada."""

    subject = "[Anexo Risk] Actualización sobre tu solicitud de voluntariado"
    body = (
        f"Hola {volunteer['nombre']},\n\n"
        "Gracias por tu interés en colaborar con Anexo Risk.\n"
        "En esta ocasión tu solicitud no ha sido aceptada.\n\n"
        "Si crees que se trata de un error, contacta con el equipo organizador."
    )
    _deliver_email(volunteer["contacto"], subject, body)
