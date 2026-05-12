import hashlib
import hmac
import json
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse

FAKE_IG_SETTINGS = {
    "PAGE_ACCESS_TOKEN": "test-ig-token",
    "APP_SECRET": "test-ig-secret",
    "WEBHOOK_VERIFY_TOKEN": "ig-verify-token",
    "PAGE_ID": "page123",
    "INSTAGRAM_ACCOUNT_ID": "ig123",
    "BASE_URL": "https://graph.facebook.com/v20.0",
}

IG_TEXT_PAYLOAD = {
    "object": "instagram",
    "entry": [{
        "id": "entry1",
        "time": 1700000000,
        "messaging": [{
            "sender": {"id": "ig_user_1"},
            "recipient": {"id": "page123"},
            "timestamp": 1700000000,
            "message": {
                "mid": "m_123",
                "text": "Hello Instagram"
            }
        }]
    }]
}

def _make_ig_signature(body: bytes, secret: str = "test-ig-secret") -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"

@override_settings(INSTAGRAM=FAKE_IG_SETTINGS)
class InstagramWebhookTest(TestCase):
    url = reverse("ig-webhook")

    def test_get_verification(self):
        resp = self.client.get(self.url, {
            "hub.mode": "subscribe",
            "hub.verify_token": "ig-verify-token",
            "hub.challenge": "1234",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), 1234)

    def _post(self, payload: dict, secret: str = "test-ig-secret"):
        body = json.dumps(payload).encode()
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=_make_ig_signature(body, secret),
        )

    @patch("apps.instagram.views.process_instagram_message.delay")
    def test_post_message(self, mock_process):
        resp = self._post(IG_TEXT_PAYLOAD)
        self.assertEqual(resp.status_code, 200)
        mock_process.assert_called_once_with(
            sender_id="ig_user_1",
            message_text="Hello Instagram",
            message_id="m_123",
            timestamp=1700000000
        )

    def test_invalid_signature(self):
        body = json.dumps(IG_TEXT_PAYLOAD).encode()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=wrong"
        )
        self.assertEqual(resp.status_code, 403)
