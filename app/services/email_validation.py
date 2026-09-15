import re

from fastapi import HTTPException

from app.config.disposable_email_domains import DISPOSABLE_EMAIL_DOMAINS

_PHONE_DIGITS_RE = re.compile(r"\D")


def normalize_phone(phone: str) -> str:
    """Conserva solo dígitos para comparar teléfonos."""
    return _PHONE_DIGITS_RE.sub("", phone.strip())


def extract_email_domain(email: str) -> str:
    parts = email.strip().lower().split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail="Correo electrónico inválido")
    return parts[1]


def is_disposable_email(email: str) -> bool:
    domain = extract_email_domain(email)
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return True
    # Subdominios de servicios temporales conocidos
    for blocked in DISPOSABLE_EMAIL_DOMAINS:
        if domain.endswith(f".{blocked}"):
            return True
    return False


def validate_registration_email(email: str) -> None:
    if is_disposable_email(email):
        raise HTTPException(
            status_code=400,
            detail="No se permiten correos temporales o desechables. Usa un correo personal permanente.",
        )


def mask_email(email: str) -> str:
    """Enmascara un correo: mar********@g******.com"""
    local, _, domain = email.partition("@")
    if not domain:
        return "***@***.***"

    if len(local) >= 3:
        local_masked = local[:3] + "*" * 8
    elif local:
        local_masked = local[0] + "*" * max(8, len(local))
    else:
        local_masked = "*" * 8

    dot_index = domain.rfind(".")
    if dot_index <= 0:
        domain_name = domain
        tld = ""
    else:
        domain_name = domain[:dot_index]
        tld = domain[dot_index:]

    if domain_name:
        domain_masked = domain_name[0] + "*" * 6 + tld
    else:
        domain_masked = "*" * 6 + tld

    return f"{local_masked}@{domain_masked}"
