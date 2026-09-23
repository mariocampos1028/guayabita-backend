from app.emails.email_service import (
    send_order_created_admin_email,
    send_order_created_email,
    send_order_status_changed_email,
    send_password_changed_email,
    send_reset_password_email,
    send_support_ticket_created_admin_email,
    send_verification_email,
    send_welcome_email,
)
from app.emails.settings import email_settings

__all__ = [
    "email_settings",
    "send_order_created_admin_email",
    "send_order_created_email",
    "send_order_status_changed_email",
    "send_password_changed_email",
    "send_reset_password_email",
    "send_support_ticket_created_admin_email",
    "send_verification_email",
    "send_welcome_email",
]
