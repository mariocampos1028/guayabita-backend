import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailSettings:
    """Resend and email-link configuration loaded from environment variables."""

    api_key: str
    from_address: str
    frontend_url: str
    verify_token_ttl_hours: int
    password_reset_token_ttl_minutes: int

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.from_address and self.frontend_url)

    @property
    def uses_dev_sender(self) -> bool:
        return "@resend.dev" in self.from_address


def _load_email_settings() -> EmailSettings:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:4200").rstrip("/")
    return EmailSettings(
        api_key=os.getenv("RESEND_API_KEY", "").strip(),
        from_address=os.getenv("EMAIL_FROM", "Guayabita <onboarding@resend.dev>").strip(),
        frontend_url=frontend_url,
        verify_token_ttl_hours=int(os.getenv("EMAIL_VERIFY_TOKEN_TTL_HOURS", "48")),
        password_reset_token_ttl_minutes=int(
            os.getenv("PASSWORD_RESET_TOKEN_TTL_MINUTES", "30")
        ),
    )


email_settings = _load_email_settings()
