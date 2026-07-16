#!/usr/bin/env python3
"""Validate Resend email environment configuration."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

REQUIRED = ("RESEND_API_KEY", "EMAIL_FROM", "FRONTEND_URL")
OPTIONAL = ("EMAIL_VERIFY_TOKEN_TTL_HOURS", "PASSWORD_RESET_TOKEN_TTL_MINUTES")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from app.emails.settings import email_settings

    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        print("Missing required environment variables:")
        for name in missing:
            print(f"  - {name}")
        print("\nCopy .env.example to .env and set RESEND_API_KEY from https://resend.com/api-keys")
        return 1

    print("Email configuration:")
    print(f"  EMAIL_FROM={email_settings.from_address}")
    print(f"  FRONTEND_URL={email_settings.frontend_url}")
    print(f"  EMAIL_VERIFY_TOKEN_TTL_HOURS={email_settings.verify_token_ttl_hours}")
    print(
        "  PASSWORD_RESET_TOKEN_TTL_MINUTES="
        f"{email_settings.password_reset_token_ttl_minutes}"
    )

    if email_settings.uses_dev_sender:
        print(
            "\nDev sender detected (onboarding@resend.dev). "
            "Emails only deliver to the Resend account owner until a domain is verified."
        )
    else:
        print("\nProduction sender configured. Ensure the domain is verified in Resend.")

    api_key = email_settings.api_key
    if not api_key.startswith("re_"):
        print("\nWarning: RESEND_API_KEY should start with 're_'.")

    request = urllib.request.Request(
        "https://api.resend.com/domains",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"\nResend API check failed ({exc.code}): {body}")
        return 1
    except urllib.error.URLError as exc:
        print(f"\nCould not reach Resend API: {exc.reason}")
        return 1

    domains = payload.get("data", [])
    print(f"\nResend API key valid. Domains in account: {len(domains)}")
    for domain in domains:
        name = domain.get("name", "?")
        status = domain.get("status", "?")
        print(f"  - {name} ({status})")

    if not domains and not email_settings.uses_dev_sender:
        print(
            "\nNo verified domains found. Add one at https://resend.com/domains "
            "before using a custom EMAIL_FROM in production."
        )

    print("\nResend setup looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
