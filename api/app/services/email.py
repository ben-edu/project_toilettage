"""Envoi d'emails de confirmation (client + toiletteur).

Au début : SMTP SORIA pour les tests. Les identifiants viennent de l'environnement
(Secret K8s). Si SMTP n'est pas configuré, l'envoi est ignoré silencieusement
(utile en dev) et journalisé.
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("toilettage.email")


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


async def _send(to: str, subject: str, body: str) -> None:
    if not _smtp_configured():
        logger.warning("SMTP non configuré : email ignoré (to=%s, subj=%s)", to, subject)
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
    logger.info("Email envoyé à %s : %s", to, subject)


async def send_booking_confirmation(
    *,
    customer_email: str,
    customer_name: str,
    service_name: str,
    start_at_str: str,
    address: str,
) -> None:
    """Confirmation au client."""
    body = (
        f"Bonjour {customer_name},\n\n"
        f"Votre réservation est bien enregistrée :\n\n"
        f"  Prestation : {service_name}\n"
        f"  Date/heure : {start_at_str}\n"
        f"  Adresse : {address}\n\n"
        f"Le toiletteur se déplacera chez vous avec tout le matériel nécessaire.\n"
        f"Pour toute modification, répondez simplement à cet email.\n\n"
        f"À très bientôt,\nL'équipe de toilettage à domicile"
    )
    await _send(customer_email, "Confirmation de votre réservation", body)


async def send_groomer_notification(
    *,
    service_name: str,
    start_at_str: str,
    customer_name: str,
    customer_phone: str,
    address: str,
    dog_size: str,
    distance_km: float,
) -> None:
    """Notification au toiletteur."""
    if not settings.groomer_notification_email:
        return
    body = (
        f"Nouvelle réservation :\n\n"
        f"  Prestation : {service_name}\n"
        f"  Date/heure : {start_at_str}\n"
        f"  Client : {customer_name} ({customer_phone})\n"
        f"  Adresse : {address} — {distance_km} km du centre\n"
        f"  Taille du chien : {dog_size}\n"
    )
    await _send(
        settings.groomer_notification_email,
        f"Nouvelle réservation — {start_at_str}",
        body,
    )
