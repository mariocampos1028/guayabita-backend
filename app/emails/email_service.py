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


def _send_admin_email(*, subject: str, html: str) -> bool:
    """Send a notification to the configured admin inbox, if any."""
    if not email_settings.has_admin_email:
        logger.warning("Admin notification not sent — ADMIN_NOTIFICATION_EMAIL is not configured")
        return False
    return _send_html_email(to=email_settings.admin_email, subject=subject, html=html)


def send_order_created_email(
    *,
    to: str,
    username: str,
    reference: str,
    product_name: str,
    product_price: float,
    payment_type: str,
    status_label: str,
) -> bool:
    """Notify the buyer that their order was received."""
    html = render_template(
        "order_created.html",
        username=username,
        reference=reference,
        product_name=product_name,
        product_price=f"{product_price:,.0f}",
        payment_type=payment_type,
        status_label=status_label,
        orders_url=f"{email_settings.frontend_url}/compras",
    )
    return _send_html_email(
        to=to,
        subject=f"Recibimos tu pedido — {reference}",
        html=html,
    )


def send_order_created_admin_email(
    *,
    customer_name: str,
    customer_email: str,
    reference: str,
    product_name: str,
    product_price: float,
    payment_type_label: str,
    status_label: str,
    order_id: int,
) -> bool:
    """Notify the admin inbox that a new order came in."""
    html = render_template(
        "order_created_admin.html",
        customer_name=customer_name,
        customer_email=customer_email,
        reference=reference,
        product_name=product_name,
        product_price=f"{product_price:,.0f}",
        payment_type_label=payment_type_label,
        status_label=status_label,
        manage_url=f"{email_settings.frontend_url}/admin/tienda?pedido={order_id}",
    )
    return _send_admin_email(
        subject=f"Nueva compra — {reference}",
        html=html,
    )


def send_order_status_changed_email(
    *,
    to: str,
    username: str,
    reference: str,
    product_name: str,
    status_label: str,
    reason: str | None = None,
) -> bool:
    """Notify the buyer that their order's status changed."""
    html = render_template(
        "order_status_changed.html",
        username=username,
        reference=reference,
        product_name=product_name,
        status_label=status_label,
        reason=reason,
        orders_url=f"{email_settings.frontend_url}/compras",
    )
    return _send_html_email(
        to=to,
        subject=f"Tu pedido {reference} ahora está: {status_label}",
        html=html,
    )


def send_support_ticket_created_admin_email(
    *,
    username: str,
    customer_email: str,
    category_label: str,
    title: str,
    detail: str,
    ticket_id: int,
) -> bool:
    """Notify the admin inbox that a user submitted a support request."""
    html = render_template(
        "support_ticket_created_admin.html",
        username=username,
        customer_email=customer_email,
        category_label=category_label,
        title=title,
        detail=detail,
        manage_url=f"{email_settings.frontend_url}/admin/soportes?ticket={ticket_id}",
    )
    return _send_admin_email(
        subject=f"Nueva solicitud de soporte — {title}",
        html=html,
    )
