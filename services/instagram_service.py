"""
Instagram Graph API Service
===========================
Handles all outbound communication to Instagram via the Messenger API.

Key differences from WhatsApp:
- Uses Page Access Token
- Different recipient structure: {"id": ig_user_id}
- 7-day messaging window (no templates)
"""
import logging
import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_BASE_URL = settings.INSTAGRAM.get("BASE_URL", "https://graph.facebook.com/v20.0")
_PAGE_ACCESS_TOKEN = settings.INSTAGRAM.get("PAGE_ACCESS_TOKEN", "")
_MESSAGES_URL = f"{_BASE_URL}/me/messages"
_TIMEOUT = 15

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

def _post(payload: dict) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as client:
        # Instagram uses a different endpoint structure: /me/messages
        params = {"access_token": _PAGE_ACCESS_TOKEN}
        response = client.post(_MESSAGES_URL, json=payload, headers={"Content-Type": "application/json"})

    if response.status_code != 200:
        logger.error(
            "Instagram API error %s: %s | payload=%s",
            response.status_code,
            response.text,
            payload,
        )
    response.raise_for_status()
    return response.json()

def send_text(to: str, message: str) -> dict:
    """Send a plain text message to an Instagram user."""
    payload = {
        "recipient": {"id": to},
        "message": {"text": message},
        "messaging_type": "RESPONSE"
    }
    result = _post(payload)
    logger.info("Instagram Text sent to %s | mid=%s", to, result.get("message_id"))
    return result

def send_image(to: str, image_url: str) -> dict:
    """Send an image to an Instagram user."""
    payload = {
        "recipient": {"id": to},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                    "is_reusable": True
                }
            }
        },
        "messaging_type": "RESPONSE"
    }
    result = _post(payload)
    logger.info("Instagram Image sent to %s | mid=%s", to, result.get("message_id"))
    return result

def mark_as_seen(sender_id: str) -> dict:
    """Send a read receipt (mark as seen)."""
    payload = {
        "recipient": {"id": sender_id},
        "sender_action": "mark_seen"
    }
    result = _post(payload)
    return result

def get_user_profile(ig_user_id: str) -> dict:
    """
    Get user profile info (name) from Instagram.
    Requires 'instagram_manage_messages' permission.
    """
    url = f"{_BASE_URL}/{ig_user_id}"
    params = {
        "fields": "name,profile_pic",
        "access_token": _PAGE_ACCESS_TOKEN
    }
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(url, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        logger.warning("Failed to get IG profile for %s: %s", ig_user_id, response.text)
        return {}
