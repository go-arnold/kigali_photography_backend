"""
Dashboard API tests.
All WhatsApp sends are mocked — tests cover permissions, logic, and response shape.
"""

from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clients.models import Client, JourneyState, JourneyPhase, JourneyStep
from apps.conversations.models import (
    ApprovalQueue,
    ApprovalAction,
    ApprovalStatus,
    Conversation,
    ScheduledMessage,
)

FAKE_WA = {
    "PHONE_NUMBER_ID": "1",
    "ACCESS_TOKEN": "x",
    "WEBHOOK_VERIFY_TOKEN": "x",
    "APP_SECRET": "x",
    "BASE_URL": "https://graph.facebook.com/v20.0",
}


def make_staff_client():
    user = User.objects.create_user("staff", password="pass")
    api = APIClient()
    api.force_authenticate(user=user)
    return api, user


def make_client(phone="+250700001000", name="Test Client"):
    client = Client.objects.create(wa_number=phone, name=name)
    JourneyState.objects.create(client=client)
    return client


def make_approval(client, user=None):
    conv = Conversation.objects.create(
        client=client,
        token_budget=20000,
        window_expires_at=timezone.now() + timezone.timedelta(hours=24),
    )
    return ApprovalQueue.objects.create(
        client=client,
        conversation=conv,
        action=ApprovalAction.SEND_BONUS,
        ai_suggestion="+2 edited photos — HIGH heat client likely to convert",
        ai_reasoning="Heat=75, 3 detailed questions asked",
        heat_score_at_suggestion=75,
        expires_at=timezone.now() + timezone.timedelta(hours=48),
    ), conv


class AuthenticationTest(TestCase):
    """All dashboard endpoints require authentication."""

    def test_unauthenticated_stats_rejected(self):
        client = APIClient()
        resp = client.get("/api/dashboard/stats/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_approvals_rejected(self):
        client = APIClient()
        resp = client.get("/api/dashboard/approvals/")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_clients_rejected(self):
        client = APIClient()
        resp = client.get("/api/dashboard/clients/")
        self.assertEqual(resp.status_code, 403)


class ApprovalQueueTest(TestCase):
    def setUp(self):
        self.api, self.user = make_staff_client()
        self.client_obj = make_client()
        self.approval, self.conv = make_approval(self.client_obj, self.user)

    def test_list_pending_approvals(self):
        resp = self.api.get("/api/dashboard/approvals/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        item = resp.data[0]
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["heat_label"], "HIGH")
        self.assertIn("+2 edited photos", item["ai_suggestion"])

    def test_filter_by_status(self):
        resp = self.api.get("/api/dashboard/approvals/?status=approved")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)

    @patch("services.whatsapp.send_text")
    def test_approve_sends_message(self, mock_send):
        resp = self.api.post(
            f"/api/dashboard/approvals/{self.approval.pk}/approve/",
            {"notes": "Perfect", "send_immediately": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "approved")
        mock_send.assert_called_once_with(
            to=self.client_obj.wa_number,
            message=self.approval.ai_suggestion,
        )

    @patch("services.whatsapp.send_text")
    def test_approve_without_send(self, mock_send):
        resp = self.api.post(
            f"/api/dashboard/approvals/{self.approval.pk}/approve/",
            {"notes": "OK but I'll send manually", "send_immediately": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_not_called()

    def test_reject_approval(self):
        resp = self.api.post(
            f"/api/dashboard/approvals/{self.approval.pk}/reject/",
            {"notes": "Client needs different approach"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "rejected")

        self.approval.refresh_from_db()
        self.assertEqual(self.approval.status, ApprovalStatus.REJECTED)
        self.assertEqual(
            self.approval.reviewer_notes, "Client needs different approach"
        )

    def test_cannot_approve_already_approved(self):
        self.approval.approve(self.user, "first approval")
        resp = self.api.post(
            f"/api/dashboard/approvals/{self.approval.pk}/approve/",
            {"notes": "again"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class ClientManagementTest(TestCase):
    def setUp(self):
        self.api, self.user = make_staff_client()
        self.client_obj = make_client("+250700002000", "Alice Uwase")

    def test_list_clients(self):
        resp = self.api.get("/api/dashboard/clients/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["name"], "Alice Uwase")
        self.assertIn("heat_label", resp.data[0])
        self.assertIn("pending_approvals", resp.data[0])

    def test_filter_takeover_only(self):
        make_client("+250700002001", "Normal Client")
        self.client_obj.journey_state.human_takeover = True
        self.client_obj.journey_state.save()

        resp = self.api.get("/api/dashboard/clients/?takeover_only=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["wa_number"], "+250700002000")

    def test_client_detail(self):
        resp = self.api.get(f"/api/dashboard/clients/{self.client_obj.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("recent_messages", resp.data)
        self.assertIn("pending_approvals_detail", resp.data)

    def test_client_not_found(self):
        resp = self.api.get("/api/dashboard/clients/99999999/")
        self.assertEqual(resp.status_code, 404)

    @patch("services.whatsapp.send_text")
    def test_manual_message_sent(self, mock_send):
        Conversation.objects.create(
            client=self.client_obj,
            token_budget=20000,
            window_status="open",
            window_expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        resp = self.api.post(
            f"/api/dashboard/clients/{self.client_obj.pk}/message/",
            {"to": self.client_obj.wa_number, "message": "Hi Alice, following up!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "sent")
        mock_send.assert_called_once_with(
            to="+250700002000",
            message="Hi Alice, following up!",
        )


class JourneyOverrideTest(TestCase):
    def setUp(self):
        self.api, self.user = make_staff_client()
        self.client_obj = make_client("+250700003000")

    def test_override_phase(self):
        resp = self.api.post(
            f"/api/dashboard/clients/{self.client_obj.pk}/journey/",
            {"phase": "booking", "step": "package_presentation"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["phase"], "booking")
        self.assertEqual(resp.data["step"], "package_presentation")

        self.client_obj.journey_state.refresh_from_db()
        self.assertEqual(self.client_obj.journey_state.phase, "booking")

    def test_override_heat_score(self):
        resp = self.api.post(
            f"/api/dashboard/clients/{self.client_obj.pk}/journey/",
            {"heat_score": 85},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["heat_label"], "HIGH")

    def test_override_requires_at_least_one_field(self):
        resp = self.api.post(
            f"/api/dashboard/clients/{self.client_obj.pk}/journey/",
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class HumanTakeoverTest(TestCase):
    def setUp(self):
        self.api, self.user = make_staff_client()
        self.client_obj = make_client("+250700004000")

    def test_enable_takeover(self):
        resp = self.api.post(
            f"/api/dashboard/clients/{self.client_obj.pk}/takeover/",
            {"enable": True, "reason": "Complex price negotiation"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["human_takeover"])

        self.client_obj.journey_state.refresh_from_db()
        self.assertTrue(self.client_obj.journey_state.human_takeover)

    def test_release_takeover(self):
        self.client_obj.journey_state.human_takeover = True
        self.client_obj.journey_state.save()

        resp = self.api.post(
            f"/api/dashboard/clients/{self.client_obj.pk}/takeover/",
            {"enable": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["human_takeover"])

        self.client_obj.journey_state.refresh_from_db()
        self.assertFalse(self.client_obj.journey_state.human_takeover)


class ScheduledMessageTest(TestCase):
    def setUp(self):
        self.api, self.user = make_staff_client()
        self.client_obj = make_client("+250700005000")
        self.scheduled = ScheduledMessage.objects.create(
            client=self.client_obj,
            message_type="birthday_wish",
            content="Happy Birthday! 🎂",
            language="en",
            send_at=timezone.now() + timezone.timedelta(hours=2),
            dedup_key=f"test_wish:{self.client_obj.pk}:2026",
        )

    def test_list_scheduled(self):
        resp = self.api.get("/api/dashboard/scheduled/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["message_type"], "birthday_wish")

    def test_cancel_scheduled(self):
        resp = self.api.delete(f"/api/dashboard/scheduled/{self.scheduled.pk}/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "cancelled")

        self.scheduled.refresh_from_db()
        self.assertEqual(self.scheduled.status, "cancelled")

    def test_cancel_nonexistent_returns_404(self):
        resp = self.api.delete("/api/dashboard/scheduled/99999/cancel/")
        self.assertEqual(resp.status_code, 404)
