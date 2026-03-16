"""
Webhook tests — no external services required.
Tests cover: GET verification, POST parsing, signature rejection, deduplication.
"""
import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.webhook.parsers import parse_webhook_payload, InboundMessage

FAKE_WA_SETTINGS = {
    "PHONE_NUMBER_ID": "123",
    "ACCESS_TOKEN": "test-token",
    "WEBHOOK_VERIFY_TOKEN": "my-verify-token",
    "APP_SECRET": "my-app-secret",
    "BASE_URL": "https://graph.facebook.com/v20.0",
}

# ── Sample Meta payloads ───────────────────────────────────────────────────────

TEXT_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "entry1",
        "changes": [{
            "value": {
                "messaging_product": "whatsapp",
                "contacts": [{"wa_id": "250700000001", "profile": {"name": "Alice"}}],
                "messages": [{
                    "id": "wamid.abc123",
                    "from": "250700000001",
                    "timestamp": "1700000000",
                    "type": "text",
                    "text": {"body": "Hello, I'd like to book a session"},
                }],
            },
            "field": "messages",
        }],
    }],
}


def _make_signature(body: bytes, secret: str = "my-app-secret") -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@override_settings(WHATSAPP=FAKE_WA_SETTINGS)
class WebhookVerificationTest(TestCase):
    url = "/api/webhook/whatsapp/"

    def test_valid_verification(self):
        resp = self.client.get(self.url, {
            "hub.mode": "subscribe",
            "hub.verify_token": "my-verify-token",
            "hub.challenge": "9876",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), 9876)

    def test_wrong_token_rejected(self):
        resp = self.client.get(self.url, {
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "9876",
        })
        self.assertEqual(resp.status_code, 403)


@override_settings(WHATSAPP=FAKE_WA_SETTINGS)
class WebhookInboundTest(TestCase):
    url = "/api/webhook/whatsapp/"

    def _post(self, payload: dict, secret: str = "my-app-secret"):
        body = json.dumps(payload).encode()
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=_make_signature(body, secret),
        )

    @patch("apps.webhook.views.process_inbound_message.delay")
    @patch("apps.webhook.views.update_message_status.delay")
    def test_valid_text_message(self, mock_status, mock_process):
        resp = self._post(TEXT_PAYLOAD)
        self.assertEqual(resp.status_code, 200)
        mock_process.assert_called_once()
        call_kwargs = mock_process.call_args[1]
        self.assertEqual(call_kwargs["message_id"], "wamid.abc123")
        self.assertEqual(call_kwargs["from_number"], "250700000001")
        self.assertEqual(call_kwargs["text"], "Hello, I'd like to book a session")

    def test_invalid_signature_rejected(self):
        body = json.dumps(TEXT_PAYLOAD).encode()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=invalidsignature",
        )
        self.assertEqual(resp.status_code, 403)

    @patch("apps.webhook.views.process_inbound_message.delay")
    @patch("apps.webhook.views.update_message_status.delay")
    def test_duplicate_message_ignored(self, mock_status, mock_process):
        """Second POST with same message_id must return 200 but NOT re-dispatch."""
        self._post(TEXT_PAYLOAD)  # first — processed
        resp = self._post(TEXT_PAYLOAD)  # duplicate
        self.assertEqual(resp.status_code, 200)
        # process_inbound_message should only be called once total
        self.assertEqual(mock_process.call_count, 1)

    @patch("apps.webhook.views.process_inbound_message.delay")
    @patch("apps.webhook.views.update_message_status.delay")
    def test_non_whatsapp_object_ignored(self, mock_status, mock_process):
        payload = {**TEXT_PAYLOAD, "object": "page"}
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)
        mock_process.assert_not_called()


class ParserTest(TestCase):
    def test_parse_text_message(self):
        messages, statuses = parse_webhook_payload(TEXT_PAYLOAD)
        self.assertEqual(len(messages), 1)
        msg = messages[0]
        self.assertIsInstance(msg, InboundMessage)
        self.assertEqual(msg.message_id, "wamid.abc123")
        self.assertEqual(msg.from_name, "Alice")
        self.assertEqual(msg.type, "text")
        self.assertEqual(msg.text, "Hello, I'd like to book a session")

    def test_parse_interactive_button(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "e1",
                "changes": [{
                    "value": {
                        "contacts": [],
                        "messages": [{
                            "id": "wamid.btn1",
                            "from": "250700000002",
                            "timestamp": "1700000001",
                            "type": "interactive",
                            "interactive": {
                                "type": "button_reply",
                                "button_reply": {"id": "book_now", "title": "Book Now"},
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        messages, _ = parse_webhook_payload(payload)
        self.assertEqual(messages[0].interactive_id, "book_now")
        self.assertEqual(messages[0].text, "Book Now")  # normalized

    def test_malformed_payload_no_crash(self):
        messages, statuses = parse_webhook_payload({"object": "whatsapp_business_account"})
        self.assertEqual(messages, [])
        self.assertEqual(statuses, [])