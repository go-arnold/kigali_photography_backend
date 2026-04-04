"""
Parse raw Meta WhatsApp webhook payloads into clean Python dicts.
 
Meta sends a deeply nested structure. This module flattens it into
a consistent shape used everywhere else in the system.
 
Supported message types: text, image, audio, document, interactive, call
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
 
logger = logging.getLogger(__name__)
 
 
@dataclass
class InboundMessage:
    """Normalized inbound WhatsApp message."""
    message_id: str
    from_number: str
    from_name: str
    timestamp: str
    msg_type: str                               # text | image | audio | document | interactive | call | unsupported
    text: Optional[str] = None
    media_id: Optional[str] = None          # WhatsApp media ID (à télécharger)
    media_mime_type: Optional[str] = None   # image/jpeg | audio/ogg | application/pdf ...
    media_filename: Optional[str] = None    # Pour documents uniquement
    interactive_id: Optional[str] = None
    interactive_title: Optional[str] = None
    raw: dict = field(default_factory=dict)
 
 
@dataclass
class StatusUpdate:
    """Normalized delivery/read status update."""
    message_id: str
    from_number: str
    status: str
    timestamp: str
 
 
def parse_webhook_payload(body: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []
 
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
 
                for msg in value.get("messages", []):
                    parsed = _parse_message(msg, value.get("contacts", []))
                    if parsed:
                        messages.append(parsed)
 
                for status in value.get("statuses", []):
                    parsed_status = _parse_status(status)
                    if parsed_status:
                        statuses.append(parsed_status)
 
    except Exception as exc:
        logger.exception("Failed to parse webhook payload: %s", exc)
 
    return messages, statuses
 
 
def _parse_message(msg: dict, contacts: list) -> Optional[InboundMessage]:
    try:
        message_id = msg["id"]
        from_number = msg["from"]
        timestamp = msg.get("timestamp", "")
        msg_type = msg.get("type", "unsupported")
 
        from_name = _resolve_name(from_number, contacts)
 
        text = None
        media_id = None
        media_mime_type = None
        media_filename = None
        interactive_id = None
        interactive_title = None
 
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
 
        elif msg_type == "image":
            img = msg.get("image", {})
            media_id = img.get("id")
            media_mime_type = img.get("mime_type", "image/jpeg")
            # Caption si présent
            caption = img.get("caption", "")
            if caption:
                text = caption
 
        elif msg_type == "audio":
            audio = msg.get("audio", {})
            media_id = audio.get("id")
            media_mime_type = audio.get("mime_type", "audio/ogg")
            # Les voice notes ont voice=True
            is_voice = audio.get("voice", False)
            msg_type = "voice" if is_voice else "audio"
 
        elif msg_type == "document":
            doc = msg.get("document", {})
            media_id = doc.get("id")
            media_mime_type = doc.get("mime_type", "application/octet-stream")
            media_filename = doc.get("filename", "document")
            caption = doc.get("caption", "")
            if caption:
                text = caption
 
        elif msg_type == "sticker":
            sticker = msg.get("sticker", {})
            media_id = sticker.get("id")
            media_mime_type = sticker.get("mime_type", "image/webp")
 
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            reply_type = interactive.get("type")
            if reply_type == "button_reply":
                interactive_id = interactive["button_reply"]["id"]
                interactive_title = interactive["button_reply"]["title"]
                text = interactive_title
            elif reply_type == "list_reply":
                interactive_id = interactive["list_reply"]["id"]
                interactive_title = interactive["list_reply"]["title"]
                text = interactive_title
 
        # WhatsApp call attempt — Meta envoie un webhook spécial
        elif msg_type == "system":
            system = msg.get("system", {})
            if system.get("type") == "call":
                msg_type = "call"
                text = "[Missed call]"
 
        else:
            logger.debug("Unsupported message type: %s", msg_type)
            msg_type = "unsupported"
 
        return InboundMessage(
            message_id=message_id,
            from_number=from_number,
            from_name=from_name,
            timestamp=timestamp,
            type=msg_type,
            text=text,
            media_id=media_id,
            media_mime_type=media_mime_type,
            media_filename=media_filename,
            interactive_id=interactive_id,
            interactive_title=interactive_title,
            raw=msg,
        )
 
    except KeyError as exc:
        logger.warning("Missing key in message payload: %s | msg=%s", exc, msg)
        return None
 
 
def _parse_status(status: dict) -> Optional[StatusUpdate]:
    try:
        return StatusUpdate(
            message_id=status["id"],
            from_number=status["recipient_id"],
            status=status["status"],
            timestamp=status.get("timestamp", ""),
        )
    except KeyError as exc:
        logger.warning("Missing key in status payload: %s", exc)
        return None
 
 
def _resolve_name(phone: str, contacts: list) -> str:
    for contact in contacts:
        if contact.get("wa_id") == phone:
            return contact.get("profile", {}).get("name", phone)
    return phone