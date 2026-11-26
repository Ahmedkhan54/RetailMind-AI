"""Transactional account email delivery. SMTP credentials never leave the server."""
from __future__ import annotations

from email.message import EmailMessage
from html import escape
import logging
import os
import smtplib
import ssl

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when account email cannot be handed to the configured SMTP server."""


def _settings() -> tuple[str, int, str, str, str, str]:
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    name = os.getenv("SMTP_FROM_NAME", "RetailMind AI").strip() or "RetailMind AI"
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as error:
        raise EmailDeliveryError("SMTP is not configured.") from error
    if not host or not username or not password or not sender or not (1 <= port <= 65535):
        raise EmailDeliveryError("SMTP is not configured.")
    return host, port, username, password, sender, name


def send_account_email(*, recipient: str, subject: str, heading: str, body: str, action_label: str, action_url: str) -> None:
    """Send a mobile-friendly branded account email; log no tokens or credentials."""
    host, port, username, password, sender, name = _settings()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{name} <{sender}>"
    message["To"] = recipient
    message.set_content(f"{heading}\n\n{body}\n\n{action_label}: {action_url}\n\nIf you did not request this, you can safely ignore this email.")
    safe_heading, safe_body, safe_label, safe_url = map(escape, (heading, body, action_label, action_url))
    message.add_alternative(
        f"""<!doctype html><html><body style=\"margin:0;background:#f5f9f4;font-family:Arial,sans-serif;color:#24352c\"><main style=\"max-width:600px;margin:24px auto;background:#fff;border:1px solid #d4e2d8;border-radius:14px;overflow:hidden\"><header style=\"padding:24px;background:#1a3a2a;color:#fff;font-size:22px;font-weight:700\">RetailMind <span style=\"color:#81c784\">AI</span></header><section style=\"padding:28px\"><h1 style=\"margin:0 0 16px;color:#1e5233;font-size:22px\">{safe_heading}</h1><p style=\"line-height:1.6\">{safe_body}</p><p style=\"margin:26px 0\"><a href=\"{safe_url}\" style=\"display:inline-block;padding:12px 18px;border-radius:8px;background:#1e5233;color:#fff;text-decoration:none;font-weight:700\">{safe_label}</a></p><p style=\"color:#6b7d72;font-size:13px;line-height:1.5\">If you did not request this, you can safely ignore this email.</p></section></main></body></html>""",
        subtype="html",
    )
    try:
        with smtplib.SMTP(host, port, timeout=15) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.login(username, password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        logger.warning("Account email was not accepted by SMTP: %s", type(error).__name__)
        raise EmailDeliveryError("Email delivery is temporarily unavailable.") from error
