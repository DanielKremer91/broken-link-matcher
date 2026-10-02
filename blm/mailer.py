"""Send the report through the Resend e-mail API."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

RESEND_URL = "https://api.resend.com/emails"
RETRY_PAUSES = (2, 4)
MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024  # Resend allows 40 MB per mail after base64 encoding


class MailError(Exception):
    """Sending failed; message is user-facing German and never contains the key."""


def _attachments(paths: list[Path]) -> list[dict]:
    total = 0
    out = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            raise MailError(f"Anhang nicht gefunden: {p}")
        data = p.read_bytes()
        total += len(data)
        out.append({"filename": p.name, "content": base64.b64encode(data).decode("ascii")})
    if total > MAX_ATTACHMENT_BYTES:
        raise MailError(f"Anhänge sind zu groß ({total} Bytes, erlaubt {MAX_ATTACHMENT_BYTES}).")
    return out


def _api_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])[:300]
    except ValueError:
        pass
    return resp.text[:300]


def send_resend(
    api_key: str,
    sender: str,
    to: list[str],
    subject: str,
    html: str,
    text: str,
    attachments: list[Path],
    *,
    client: Optional[httpx.Client] = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    """Send one mail; returns the Resend message id."""
    payload = {"from": sender, "to": list(to), "subject": subject, "html": html, "text": text}
    files = _attachments(attachments)
    if files:
        payload["attachments"] = files
    own_client = client is None
    client = client or httpx.Client(timeout=60.0)
    last = "unbekannt"
    try:
        for attempt in range(len(RETRY_PAUSES) + 1):
            try:
                resp = client.post(RESEND_URL, json=payload, headers={"Authorization": f"Bearer {api_key}"})
            except httpx.HTTPError as exc:
                last = f"Netzwerkfehler: {type(exc).__name__}"
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    raise MailError(f"Resend lehnt ab (HTTP {resp.status_code}): {_api_message(resp)}")
                else:
                    try:
                        return str(resp.json()["id"])
                    except (ValueError, KeyError, TypeError) as exc:
                        raise MailError("Resend: unerwartete Antwort") from exc
            if attempt < len(RETRY_PAUSES):
                sleeper(RETRY_PAUSES[attempt])
        raise MailError(f"Resend nicht erreichbar nach mehreren Versuchen ({last}).")
    finally:
        if own_client:
            client.close()
