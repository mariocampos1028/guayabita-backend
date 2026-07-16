import logging

import resend

from app.emails.renderer import render_template
from app.emails.settings import email_settings

logger = logging.getLogger(__name__)


def _send_html_email(*, to: str, subject: str, html: str) -> bool:
    """Send an HTML email via Resend. Returns True on success, False on failure."""
    if not email_settings.is_configured:
        logger.warning(
            "Email not sent to %s: missing RESEND_API_KEY, EMAIL_FROM, or FRONTEND_URL",
            to,
        )
        return False

    resend.api_key = email_settings.api_key
    try:
        resend.Emails.send(
            {
                "from": email_settings.from_address,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        logger.info("Email sent to %s — subject: %s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s — subject: %s", to, subject)
        return False


def send_welcome_email(
    *,
    to: str,
    username: str,
    balance: float,
    verify_url: str | None = None,
) -> bool:
    """Send the welcome email after a new user registers."""
    html = render_template(
        "welcome.html",
        username=username,
        balance=f"{balance:,.0f}",
        lobby_url=email_settings.frontend_url,
        verify_url=verify_url,
    )
    return _send_html_email(
        to=to,
        subject="Bienvenido a Guayabita — tu cuenta está lista",
        html=html,
    )


def send_verification_email(*, to: str, username: str, verify_url: str) -> bool:
    """Resend the email verification link."""
    html = render_template(
        "verify_email.html",
        username=username,
        verify_url=verify_url,
    )
    return _send_html_email(
        to=to,
        subject="Verifica tu correo en Guayabita",
        html=html,
    )


def send_reset_password_email(*, to: str, username: str, reset_url: str) -> bool:
    """Send password reset instructions."""
    html = render_template(
        "reset_password.html",
        username=username,
        reset_url=reset_url,
    )
    return _send_html_email(
        to=to,
        subject="Restablece tu contraseña en Guayabita",
        html=html,
    )


def send_password_changed_email(*, to: str, username: str) -> bool:
    """Notify the user that their password was changed."""
    html = render_template(
        "password_changed.html",
        username=username,
        login_url=f"{email_settings.frontend_url}/login",
    )
    return _send_html_email(
        to=to,
        subject="Tu contraseña de Guayabita fue actualizada",
        html=html,
    )
