"""Envío de correo (SMTP). Los correos de notificación se encolan en la sesión de BD y se
despachan en segundo plano sólo si la transacción se confirma (after_commit)."""
import html
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import event
from sqlalchemy.orm import Session

from ..config import settings

log = logging.getLogger("correo")
CLAVE_COLA = "correos_pendientes"


def habilitado() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM)


def plantilla(titulo: str, mensaje: str = "", enlace: str = "", texto_boton: str = "Abrir en la aplicación") -> str:
    url = f"{settings.APP_URL.rstrip('/')}{enlace}" if enlace else settings.APP_URL
    cuerpo = html.escape(mensaje).replace("\n", "<br>") if mensaje else ""
    return f"""<!doctype html><html><body style="margin:0;background:#F5F7FA;font-family:'Work Sans',Arial,sans-serif;color:#1A202C">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #E2E8F0">
<tr><td style="background:#39A909;background:linear-gradient(90deg,#39A909,#1E3A5F);color:#fff;padding:14px 22px;font-weight:700;font-size:16px">
<img src="{html.escape(settings.APP_URL.rstrip('/'))}/logo-sena-blanco.png" alt="SENA" height="40" style="height:40px;vertical-align:middle;margin-right:12px;border:0">
Materiales de Formación</td></tr>
<tr><td style="padding:22px">
<h2 style="margin:0 0 12px;font-size:18px">{html.escape(titulo)}</h2>
<p style="margin:0 0 18px;font-size:14px;line-height:1.5">{cuerpo}</p>
<a href="{html.escape(url)}" style="display:inline-block;background:#39A909;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:600;font-size:14px">{html.escape(texto_boton)}</a>
</td></tr>
<tr><td style="padding:14px 22px;font-size:11px;color:#718096;border-top:1px solid #E2E8F0">
Servicio Nacional de Aprendizaje SENA · Centros de formación. Mensaje automático, por favor no responda.</td></tr>
</table></td></tr></table></body></html>"""


def _mensaje(para: str, asunto: str, cuerpo_html: str, texto: str) -> EmailMessage:
    m = EmailMessage()
    m["From"] = formataddr((settings.SMTP_FROM_NOMBRE, settings.SMTP_FROM))
    m["To"] = para
    m["Subject"] = asunto
    m.set_content(texto)
    m.add_alternative(cuerpo_html, subtype="html")
    return m


def enviar_lote(correos: list[dict]) -> None:
    """Envía [{para, asunto, html, texto}] en una sola conexión SMTP. Lanza excepción si falla."""
    if not correos or not habilitado():
        return
    if settings.SMTP_SSL:
        srv = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20, context=ssl.create_default_context())
    else:
        srv = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
    with srv:
        if not settings.SMTP_SSL and settings.SMTP_STARTTLS:
            srv.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER:
            srv.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        for c in correos:
            srv.send_message(_mensaje(c["para"], c["asunto"], c["html"], c["texto"]))


def enviar_async(correos: list[dict]) -> None:
    def run():
        try:
            enviar_lote(correos)
            log.info("Enviados %d correos", len(correos))
        except Exception:  # el correo nunca debe tumbar la operación de negocio
            log.exception("Error enviando %d correos", len(correos))

    threading.Thread(target=run, daemon=True).start()


def encolar(db: Session, para: str, asunto: str, mensaje: str = "", enlace: str = "",
            texto_boton: str = "Abrir en la aplicación") -> None:
    if not habilitado() or not para:
        return
    url = f"{settings.APP_URL.rstrip('/')}{enlace}"
    db.info.setdefault(CLAVE_COLA, []).append({
        "para": para, "asunto": f"[Materiales SENA] {asunto}",
        "html": plantilla(asunto, mensaje, enlace, texto_boton),
        "texto": f"{asunto}\n\n{mensaje}\n\n{url}",
    })


@event.listens_for(Session, "after_commit")
def _despachar(session: Session) -> None:
    pendientes = session.info.pop(CLAVE_COLA, None)
    if pendientes:
        enviar_async(pendientes)


@event.listens_for(Session, "after_rollback")
def _descartar(session: Session) -> None:
    session.info.pop(CLAVE_COLA, None)
