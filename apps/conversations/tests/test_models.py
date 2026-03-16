from django.test import TestCase
from django.utils import timezone

from apps.clients.models import Client
from apps.conversations.models import (
    Conversation, Message, ApprovalQueue,
    ApprovalAction, ApprovalStatus, MessageDirection,
)


def make_client(phone="+250700000010"):
    return Client.objects.create(wa_number=phone, name="Test Client")


def make_conversation(client):
    return Conversation.objects.create(
        client=client,
        token_budget=1000,
    )


class ConversationTokenTest(TestCase):
    def setUp(self):
        self.client_obj = make_client()
        self.conv = make_conversation(self.client_obj)

    def test_not_over_budget_initially(self):
        self.assertFalse(self.conv.is_budget_exceeded)

    def test_add_tokens_increments(self):
        self.conv.add_tokens(500)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.tokens_used, 500)

    def test_budget_exceeded_flag(self):
        self.conv.add_tokens(1001)
        self.conv.refresh_from_db()
        self.assertTrue(self.conv.is_budget_exceeded)

    def test_add_tokens_is_cumulative(self):
        self.conv.add_tokens(300)
        self.conv.add_tokens(300)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.tokens_used, 600)

    def test_touch_refreshes_window(self):
        before = timezone.now()
        self.conv.touch()
        self.conv.refresh_from_db()
        self.assertGreater(self.conv.window_expires_at, before)
        self.assertEqual(self.conv.window_status, Conversation.WindowStatus.OPEN)


class ApprovalQueueTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.client_obj = make_client("+250700000020")
        self.conv = make_conversation(self.client_obj)
        self.reviewer = User.objects.create_user("reviewer", password="pass")
        self.item = ApprovalQueue.objects.create(
            client=self.client_obj,
            conversation=self.conv,
            action=ApprovalAction.SEND_BONUS,
            ai_suggestion="+2 edited photos",
            ai_reasoning="HIGH heat, client engaged",
            heat_score_at_suggestion=75,
            expires_at=timezone.now() + timezone.timedelta(hours=48),
        )

    def test_default_status_pending(self):
        self.assertEqual(self.item.status, ApprovalStatus.PENDING)

    def test_approve_sets_fields(self):
        self.item.approve(self.reviewer, notes="Looks good")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ApprovalStatus.APPROVED)
        self.assertEqual(self.item.reviewed_by, self.reviewer)
        self.assertEqual(self.item.reviewer_notes, "Looks good")
        self.assertIsNotNone(self.item.reviewed_at)

    def test_reject_sets_fields(self):
        self.item.reject(self.reviewer, notes="Not appropriate now")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ApprovalStatus.REJECTED)


class MessageTest(TestCase):
    def setUp(self):
        self.client_obj = make_client("+250700000030")
        self.conv = make_conversation(self.client_obj)

    def test_create_inbound_message(self):
        msg = Message.objects.create(
            conversation=self.conv,
            client=self.client_obj,
            wa_message_id="wamid.test001",
            direction=MessageDirection.INBOUND,
            content="Hello I want to book",
            tokens_input=0,
            tokens_output=0,
        )
        self.assertEqual(msg.total_tokens, 0)
        self.assertIn("Hello", str(msg))

    def test_total_tokens_sum(self):
        msg = Message.objects.create(
            conversation=self.conv,
            client=self.client_obj,
            wa_message_id="wamid.test002",
            direction=MessageDirection.OUTBOUND,
            content="Welcome to Kigali Photography!",
            tokens_input=150,
            tokens_output=80,
        )
        self.assertEqual(msg.total_tokens, 230)