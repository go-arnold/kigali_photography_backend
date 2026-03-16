"""
WhatsApp Cloud API Service
===========================
Handles all outbound communication to Meta's Graph API.

Design principles:
- All calls are synchronous (called from Celery workers, not request thread)
- Raises on HTTP errors — callers handle retry logic
- Typed methods per message type for clarity
- Single httpx client reused across calls (connection pooling)
"""
import logging
from typing import Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_BASE_URL = settings.WHATSAPP["BASE_URL"]
_PHONE_ID = settings.WHATSAPP["PHONE_NUMBER_ID"]
_MESSAGES_URL = f"{_BASE_URL}/{_PHONE_ID}/messages"
_TIMEOUT = 15  # seconds


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def _post(payload: dict) -> dict:
    """
    Core POST to Meta messages endpoint.
    Returns parsed response JSON.
    Raises httpx.HTTPStatusError on 4xx/5xx.
    """
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(_MESSAGES_URL, json=payload, headers=_headers())

    if response.status_code != 200:
        logger.error(
            "WhatsApp API error %s: %s | payload=%s",
            response.status_code,
            response.text,
            payload,
        )
    response.raise_for_status()
    return response.json()



def send_text(to: str, message: str, preview_url: bool = False) -> dict:
    """Send a plain text message."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": message, "preview_url": preview_url},
    }
    result = _post(payload)
    logger.info("Text sent to %s | wamid=%s", to, _extract_wamid(result))
    return result


def send_buttons(to: str, body: str, buttons: list[dict]) -> dict:
    """
    Send interactive button message.
    buttons = [{"id": "btn_1", "title": "Book Now"}, ...]
    Max 3 buttons per Meta limit.
    """
    assert len(buttons) <= 3, "Meta allows max 3 buttons"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                    for b in buttons
                ]
            },
        },
    }
    result = _post(payload)
    logger.info("Buttons sent to %s | wamid=%s", to, _extract_wamid(result))
    return result


def send_list(to: str, body: str, button_label: str, sections: list[dict]) -> dict:
    """
    Send interactive list message.
    sections = [{"title": "Packages", "rows": [{"id": "pkg_1", "title": "Basic", "description": "..."}]}]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_label[:20],
                "sections": sections,
            },
        },
    }
    result = _post(payload)
    logger.info("List sent to %s | wamid=%s", to, _extract_wamid(result))
    return result


def send_template(to: str, template_name: str, language_code: str = "en_US",
                  components: Optional[list] = None) -> dict:
    """
    Send a pre-approved Meta template message.
    Used for outbound (birthday reminders, re-engagement) where 24h window is closed.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components or [],
        },
    }
    result = _post(payload)
    logger.info("Template '%s' sent to %s | wamid=%s", template_name, to, _extract_wamid(result))
    return result


def mark_as_read(message_id: str) -> dict:
    """
    Mark a received message as read.
    Costs nothing, improves UX (shows blue ticks).
    """
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        return _post(payload)
    except Exception as exc:
        # Non-critical — don't fail processing if this errors
        logger.warning("Failed to mark message as read %s: %s", message_id, exc)
        return {}


def _extract_wamid(response: dict) -> str:
    """Extract WhatsApp message ID from API response."""
    try:
        return response["messages"][0]["id"]
    except (KeyError, IndexError):
        return "unknown"