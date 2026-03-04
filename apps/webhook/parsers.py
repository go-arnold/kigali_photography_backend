"""
Parse raw Meta WhatsApp webhook payloads into clean Python dicts.

Meta sends a deeply nested structure. This module flattens it into
a consistent shape used everywhere else in the system.

Supported message types: text, image, audio, video, document, interactive
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class InboundMessage:
    """Normalized inbound WhatsApp message."""
    message_id: str          # Unique WA message ID (used for idempotency)
    from_number: str         # Sender's phone number (e.164 format)
    from_name: str           # Sender's display name
    timestamp: str           # Unix timestamp string from Meta
    type: str                # text | image | audio | video | document | interactive | unsupported
    text: Optional[str] = None          # For type=text
    media_id: Optional[str] = None      # For media types
    interactive_id: Optional[str] = None    # Button/list reply ID
    interactive_title: Optional[str] = None # Button/list reply title
    raw: dict = field(default_factory=dict) # Original payload for edge cases


@dataclass
class StatusUpdate:
    """Normalized delivery/read status update."""
    message_id: str
    from_number: str
    status: str   # sent | delivered | read | failed
    timestamp: str


def parse_webhook_payload(body: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    """
    Parse a Meta webhook POST body.

    Returns:
        (messages, statuses) — both lists, usually one item each.
    """
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # ── Parse inbound messages ─────────────────────────────────
                for msg in value.get("messages", []):
                    parsed = _parse_message(msg, value.get("contacts", []))
                    if parsed:
                        messages.append(parsed)

                # ── Parse status updates ───────────────────────────────────
                for status in value.get("statuses", []):
                    parsed_status = _parse_status(status)
                    if parsed_status:
                        statuses.append(parsed_status)

    except Exception as exc:
        logger.exception("Failed to parse webhook payload: %s", exc)

    return messages, statuses


def _parse_message(msg: dict, contacts: list) -> Optional[InboundMessage]:
    """Extract a single InboundMessage from a raw message dict."""
    try:
        message_id = msg["id"]
        from_number = msg["from"]
        timestamp = msg.get("timestamp", "")
        msg_type = msg.get("type", "unsupported")

        # Resolve display name from contacts list
        from_name = _resolve_name(from_number, contacts)

        text = None
        media_id = None
        interactive_id = None
        interactive_title = None

        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")

        elif msg_type in ("image", "audio", "video", "document", "sticker"):
            media_id = msg.get(msg_type, {}).get("id")

        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            reply_type = interactive.get("type")
            if reply_type == "button_reply":
                interactive_id = interactive["button_reply"]["id"]
                interactive_title = interactive["button_reply"]["title"]
                text = interactive_title  # normalise: treat button tap as text too
            elif reply_type == "list_reply":
                interactive_id = interactive["list_reply"]["id"]
                interactive_title = interactive["list_reply"]["title"]
                text = interactive_title

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