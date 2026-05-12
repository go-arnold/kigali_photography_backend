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

_TIMEOUT = 15

def _get_config():
    return {
        "base_url": settings.INSTAGRAM.get("BASE_URL", "https://graph.facebook.com/v20.0"),
        "token": settings.INSTAGRAM.get("PAGE_ACCESS_TOKEN", "").strip(),
    }

def _post(payload: dict) -> dict:
    config = _get_config()
    messages_url = f"{config['base_url']}/me/messages"
    
    if not config['token']:
        logger.error("Instagram PAGE_ACCESS_TOKEN is missing in settings")
        raise ValueError("Instagram PAGE_ACCESS_TOKEN is missing")

    with httpx.Client(timeout=_TIMEOUT) as client:
        # Pass the access token as a query parameter
        params = {"access_token": config['token']}
        response = client.post(
            messages_url, 
            json=payload, 
            params=params,
            headers={"Content-Type": "application/json"}
        )

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
    config = _get_config()
    url = f"{config['base_url']}/{ig_user_id}"
    params = {
        "fields": "name,profile_pic",
        "access_token": config['token']
    }
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(url, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        logger.warning("Failed to get IG profile for %s: %s", ig_user_id, response.text)
        return {}
