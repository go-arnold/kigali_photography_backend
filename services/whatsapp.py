"""
WhatsApp Cloud API Service
===========================
Handles all outbound communication to Meta's Graph API.
 
Added:
- send_image()     → envoie une image depuis une URL publique
- send_audio()     → envoie un audio depuis une URL publique (pour les voice notes de l'agent)
- send_document()  → envoie un document depuis une URL publique
- download_media() → télécharge un media depuis Meta (délégué à media_service)
"""
import logging
from typing import Optional
 
import httpx
from django.conf import settings
 
logger = logging.getLogger(__name__)
 
_BASE_URL = settings.WHATSAPP["BASE_URL"]
_PHONE_ID = settings.WHATSAPP["PHONE_NUMBER_ID"]
_MESSAGES_URL = f"{_BASE_URL}/{_PHONE_ID}/messages"
_TIMEOUT = 15
 
 
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }
 
 
def _post(payload: dict) -> dict:
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
    """Send interactive button message. Max 3 buttons."""
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
 
 
def send_image(to: str, image_url: str, caption: str = "") -> dict:
    """
    Envoie une image depuis une URL publique.
    L'URL doit être accessible publiquement par Meta.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "image",
        "image": {
            "link": image_url,
        },
    }
    if caption:
        payload["image"]["caption"] = caption
 
    result = _post(payload)
    logger.info("Image sent to %s | wamid=%s", to, _extract_wamid(result))
    return result
 
 
def send_audio(to: str, audio_url: str) -> dict:
    """
    Envoie un fichier audio depuis une URL publique.
    Formats supportés: audio/aac, audio/mp4, audio/mpeg, audio/amr, audio/ogg
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "audio",
        "audio": {
            "link": audio_url,
        },
    }
    result = _post(payload)
    logger.info("Audio sent to %s | wamid=%s", to, _extract_wamid(result))
    return result
 
 
def send_document(to: str, document_url: str, filename: str = "document.pdf", caption: str = "") -> dict:
    """
    Envoie un document depuis une URL publique.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {
            "link": document_url,
            "filename": filename,
        },
    }
    if caption:
        payload["document"]["caption"] = caption
 
    result = _post(payload)
    logger.info("Document sent to %s | wamid=%s", to, _extract_wamid(result))
    return result
 
 
def send_list(to: str, body: str, button_label: str, sections: list[dict]) -> dict:
    """Send interactive list message."""
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
    """Send a pre-approved Meta template message."""
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
    """Mark a received message as read (blue ticks)."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        return _post(payload)
    except Exception as exc:
        logger.warning("Failed to mark message as read %s: %s", message_id, exc)
        return {}
 
 
def _extract_wamid(response: dict) -> str:
    try:
        return response["messages"][0]["id"]
    except (KeyError, IndexError):
        return "unknown"

#_______________________NEW FOR SEND AUDIO UPDATES
def upload_media(file_path, mime_type: str) -> Optional[str]:
    """
    Upload un fichier vers WhatsApp Media API.
    Retourne media_id ou None.
    Plus fiable que URL externe car stocké chez Meta.
    """
    from pathlib import Path
    try:
        upload_url = f"https://graph.facebook.com/v20.0/{_PHONE_ID}/media"
        with open(file_path, "rb") as f:
            file_bytes = f.read()
 
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                upload_url,
                headers={"Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}"},
                files={"file": (Path(str(file_path)).name, file_bytes, mime_type)},
                data={"messaging_product": "whatsapp"},
            )
 
        if resp.status_code == 200:
            media_id = resp.json().get("id")
            logger.info("Media uploaded to WA | media_id=%s mime=%s size=%s",
                       media_id, mime_type, len(file_bytes))
            return media_id
        else:
            logger.error("WA media upload failed | status=%s body=%s",
                        resp.status_code, resp.text[:300])
            return None
    except Exception as exc:
        logger.error("upload_media failed: %s", exc)
        return None
 
def send_audio_by_id(to: str, media_id: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "audio",
        "audio": {"id": media_id},
    }
    result = _post(payload)
    logger.info("Audio sent by id to %s | wamid=%s", to, _extract_wamid(result))
    return result
 
 
def send_image_by_id(to: str, media_id: str, caption: str = "") -> dict:
    """Envoie une image via son media_id."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "image",
        "image": {"id": media_id, **({"caption": caption} if caption else {})},
    }
    result = _post(payload)
    logger.info("Image sent by id to %s | wamid=%s", to, _extract_wamid(result))
    return result
 
 
def send_document_by_id(to: str, media_id: str, filename: str = "document", caption: str = "") -> dict:
    """Envoie un document via son media_id."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
            **({"caption": caption} if caption else {}),
        },
    }
    result = _post(payload)
    logger.info("Document sent by id to %s | wamid=%s", to, _extract_wamid(result))
    return result
