"""
WhatsApp Webhook Views
======================
GET  /api/webhook/whatsapp/  → Meta verification challenge
POST /api/webhook/whatsapp/  → Inbound messages & status updates

Security:
- GET:  verify_token check
- POST: X-Hub-Signature-256 HMAC validation + message_id idempotency

Processing:
- Signature verified synchronously (fast, in-request)
- Message parsing done synchronously (fast, no I/O)
- All heavy work (Claude, DB writes) dispatched to Celery async
  → Webhook returns 200 to Meta in <500ms, preventing retries
"""

import logging

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from utils.decorators import signature_required, idempotent_webhook
from .parsers import parse_webhook_payload
from apps.automation.tasks import process_inbound_message, update_message_status

logger = logging.getLogger(__name__)


def _get_message_id(request) -> str:
    """Extract first message_id from body for idempotency key."""
    try:
        body = request.data
        entries = body.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                msgs = change.get("value", {}).get("messages", [])
                if msgs:
                    return msgs[0]["id"]
    except Exception:
        pass
    return ""


class WhatsAppWebhookView(APIView):
    """
    Single endpoint for all WhatsApp Cloud API traffic.
    Deliberately kept thin — parse and dispatch only.
    """

    permission_classes = [
        AllowAny
    ]  # Meta calls this unauthenticated; we verify via HMAC

    # ── GET: Meta verification handshake ──────────────────────────────────────
    def get(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and token == settings.WHATSAPP["WEBHOOK_VERIFY_TOKEN"]:
            logger.info("WhatsApp webhook verified successfully")
            return Response(int(challenge), status=200)

        logger.warning(
            "Webhook verification failed: mode=%s token_match=%s",
            mode,
            token == settings.WHATSAPP["WEBHOOK_VERIFY_TOKEN"],
        )
        return Response({"error": "Verification failed"}, status=403)

    # ── POST: Inbound messages ─────────────────────────────────────────────────
    @signature_required
    @idempotent_webhook(key_func=_get_message_id, ttl=300)
    def post(self, request):
        body = request.data

        # Ignore Meta's test ping
        if body.get("object") != "whatsapp_business_account":
            return Response({"status": "ignored"}, status=200)

        messages, statuses = parse_webhook_payload(body)

        # Dispatch each message to Celery — fire and forget
        for msg in messages:
            if msg.message_id:  # skip empty (safety)
                _dispatch_message(msg)

        # Status updates (delivered/read) — lightweight update
        for status in statuses:
            _dispatch_status(status)

        # Always return 200 fast — Meta retries on non-200
        return Response({"status": "ok"}, status=200)


def _dispatch_message(msg) -> None:
    """Send inbound message to async processing pipeline."""
    try:
        process_inbound_message.delay(
            message_id=msg.message_id,
            from_number=msg.from_number,
            from_name=msg.from_name,
            timestamp=msg.timestamp,
            msg_type=msg.type,
            text=msg.text or "",
            media_id=msg.media_id,
            interactive_id=msg.interactive_id,
        )
        logger.debug("Dispatched message %s from %s", msg.message_id, msg.from_number)
    except Exception as exc:
        # Never crash the webhook response due to dispatch failure
        logger.exception("Failed to dispatch message %s: %s", msg.message_id, exc)


def _dispatch_status(status) -> None:
    """Update message delivery status asynchronously."""
    try:
        update_message_status.delay(
            message_id=status.message_id,
            from_number=status.from_number,
            status=status.status,
        )
    except Exception as exc:
        logger.exception("Failed to dispatch status update: %s", exc)
