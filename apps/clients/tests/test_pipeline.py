"""
Pipeline integration tests.
All external services (Claude, WhatsApp) are mocked.
Tests the full flow: message in → correct action out.
"""
from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.clients.models import Client, JourneyState, JourneyPhase, JourneyStep
from apps.conversations.models import Conversation, Message, ApprovalQueue

FAKE_CLAUDE = {
    "API_KEY": "x",
    "DEFAULT_MODEL": "claude-haiku-3-5-20251001",
    "ESCALATION_MODEL": "claude-sonnet-4-6",
    "MAX_INPUT_TOKENS": 2000,
    "MAX_OUTPUT_TOKENS": 500,
    "CONVERSATION_BUDGET": 20000,
}
FAKE_STUDIO = {
    "NAME": "Kigali Photography",
    "LOCATION": "KG 1",
    "HOURS": "Mon-Sat",
    "BOOKING_FEE_RWF": 20000,
}
FAKE_WA = {
    "PHONE_NUMBER_ID": "1",
    "ACCESS_TOKEN": "x",
    "WEBHOOK_VERIFY_TOKEN": "x",
    "APP_SECRET": "x",
    "BASE_URL": "https://graph.facebook.com/v20.0",
}


def make_claude_response(text="Welcome!", input_tokens=100, output_tokens=50):
    from services.claude import ClaudeResponse
    return ClaudeResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model="claude-haiku-3-5-20251001",
        stop_reason="end_turn",
    )


@override_settings(CLAUDE=FAKE_CLAUDE, STUDIO=FAKE_STUDIO, WHATSAPP=FAKE_WA)
class PipelineHappyPathTest(TestCase):
    """New client sends first message — should be sent automatically."""

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    @patch("services.claude.call_claude")
    @patch("services.claude.analyze_intent_and_heat")
    def test_new_client_message_sent(self, mock_intent, mock_claude, mock_read, mock_send):
        from services.claude import ClaudeResponse
        mock_intent.return_value = ClaudeResponse(
            text='{"intent":"greeting","heat_delta":5,"objection_type":"none","language":"en","urgency":"low"}',
            input_tokens=30, output_tokens=20, model="claude-haiku-3-5-20251001",
        )
        mock_claude.return_value = make_claude_response("Hello! Welcome to Kigali Photography! 📸")

        from services.journey_orchestrator import handle_inbound_message
        result = handle_inbound_message(
            message_id="wamid.test001",
            from_number="+250700000100",
            from_name="New Client",
            msg_type="text",
            text="Hello, I'm interested in booking a session",
            timestamp="1700000000",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "sent")
        mock_send.assert_called_once_with(
            to="+250700000100",
            message="Hello! Welcome to Kigali Photography! 📸",
        )
        # mark_as_read is called by the Celery task wrapper, not the orchestrator directly

        # Verify DB records created
        self.assertTrue(Client.objects.filter(wa_number="+250700000100").exists())
        self.assertTrue(
            Message.objects.filter(direction="inbound", content__contains="interested").exists()
        )
        self.assertTrue(
            Message.objects.filter(direction="outbound", generated_by_ai=True).exists()
        )

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    @patch("services.claude.call_claude")
    @patch("services.claude.analyze_intent_and_heat")
    def test_tokens_recorded(self, mock_intent, mock_claude, mock_read, mock_send):
        from services.claude import ClaudeResponse
        mock_intent.return_value = ClaudeResponse(
            text='{"intent":"inquiry","heat_delta":8,"objection_type":"none","language":"en","urgency":"medium"}',
            input_tokens=30, output_tokens=20, model="claude-haiku-3-5-20251001",
        )
        mock_claude.return_value = make_claude_response(input_tokens=300, output_tokens=150)

        from services.journey_orchestrator import handle_inbound_message
        handle_inbound_message(
            message_id="wamid.test002",
            from_number="+250700000101",
            from_name="Token Test",
            msg_type="text",
            text="What packages do you offer?",
            timestamp="1700000001",
        )

        client = Client.objects.get(wa_number="+250700000101")
        conv = client.conversations.first()
        self.assertGreater(conv.tokens_used, 0)
        self.assertGreater(client.lifetime_tokens_used, 0)


@override_settings(CLAUDE=FAKE_CLAUDE, STUDIO=FAKE_STUDIO, WHATSAPP=FAKE_WA)
class PipelineOptOutTest(TestCase):

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    def test_opt_out_keyword_stops_pipeline(self, mock_read, mock_send):
        # Create existing client
        Client.objects.create(wa_number="+250700000200", name="Leave Me")

        from services.journey_orchestrator import handle_inbound_message
        result = handle_inbound_message(
            message_id="wamid.optout001",
            from_number="+250700000200",
            from_name="Leave Me",
            msg_type="text",
            text="STOP",
            timestamp="1700000002",
        )

        self.assertEqual(result.action, "opted_out")
        client = Client.objects.get(wa_number="+250700000200")
        self.assertTrue(client.is_opted_out)

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    @patch("services.claude.call_claude")
    def test_opted_out_client_ignored(self, mock_claude, mock_read, mock_send):
        Client.objects.create(
            wa_number="+250700000201",
            name="Already Out",
            is_opted_out=True,
        )

        from services.journey_orchestrator import handle_inbound_message
        result = handle_inbound_message(
            message_id="wamid.opted001",
            from_number="+250700000201",
            from_name="Already Out",
            msg_type="text",
            text="Hello again",
            timestamp="1700000003",
        )

        self.assertEqual(result.action, "opted_out")
        mock_claude.assert_not_called()  # No Claude call for opted-out clients


@override_settings(CLAUDE=FAKE_CLAUDE, STUDIO=FAKE_STUDIO, WHATSAPP=FAKE_WA)
class PipelineBudgetTest(TestCase):

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    @patch("services.claude.call_claude")
    def test_budget_exceeded_triggers_takeover(self, mock_claude, mock_read, mock_send):
        client = Client.objects.create(wa_number="+250700000300", name="Heavy User")
        journey, _ = JourneyState.objects.get_or_create(client=client)
        conv = Conversation.objects.create(
            client=client,
            token_budget=100,
            tokens_used=101,  # Already exceeded
            window_expires_at=timezone.now() + timezone.timedelta(hours=24),
        )

        from services.journey_orchestrator import handle_inbound_message
        result = handle_inbound_message(
            message_id="wamid.budget001",
            from_number="+250700000300",
            from_name="Heavy User",
            msg_type="text",
            text="Hello",
            timestamp="1700000004",
        )

        self.assertEqual(result.action, "human_takeover")
        mock_claude.assert_not_called()  # No Claude call when budget exceeded

        journey.refresh_from_db()
        self.assertTrue(journey.human_takeover)


@override_settings(CLAUDE=FAKE_CLAUDE, STUDIO=FAKE_STUDIO, WHATSAPP=FAKE_WA)
class PipelineHumanTakeoverTest(TestCase):

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    @patch("services.claude.call_claude")
    def test_human_takeover_silences_ai(self, mock_claude, mock_read, mock_send):
        client = Client.objects.create(wa_number="+250700000400")
        journey, _ = JourneyState.objects.get_or_create(
            client=client,
            defaults={"human_takeover": True, "takeover_reason": "Manual override"},
        )

        from services.journey_orchestrator import handle_inbound_message
        result = handle_inbound_message(
            message_id="wamid.human001",
            from_number="+250700000400",
            from_name="Manual Client",
            msg_type="text",
            text="I have a question",
            timestamp="1700000005",
        )

        self.assertEqual(result.action, "human_takeover")
        mock_claude.assert_not_called()


@override_settings(CLAUDE=FAKE_CLAUDE, STUDIO=FAKE_STUDIO, WHATSAPP=FAKE_WA)
class PipelineLanguageTest(TestCase):

    @patch("services.whatsapp.send_text")
    @patch("services.whatsapp.mark_as_read")
    @patch("services.claude.call_claude")
    @patch("services.claude.analyze_intent_and_heat")
    def test_kinyarwanda_detected_updates_client(self, mock_intent, mock_claude, mock_read, mock_send):
        from services.claude import ClaudeResponse
        mock_intent.return_value = ClaudeResponse(
            text='{"intent":"greeting","heat_delta":5,"objection_type":"none","language":"rw","urgency":"low"}',
            input_tokens=20, output_tokens=10, model="claude-haiku-3-5-20251001",
        )
        mock_claude.return_value = make_claude_response("Muraho! Ndishimye kukubona.")

        from services.journey_orchestrator import handle_inbound_message
        handle_inbound_message(
            message_id="wamid.rw001",
            from_number="+250700000500",
            from_name="Uwase",
            msg_type="text",
            text="Muraho, ndashaka gufotorwa",
            timestamp="1700000006",
        )

        client = Client.objects.get(wa_number="+250700000500")
        self.assertEqual(client.language, "rw")