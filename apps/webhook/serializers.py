"""
Minimal serializers for webhook validation.
Meta sends JSON so we only need basic structure validation.
"""
from rest_framework import serializers


class WebhookVerifySerializer(serializers.Serializer):
    """Query params for Meta's GET verification challenge."""
    hub_mode = serializers.CharField(source="hub.mode")
    hub_challenge = serializers.CharField(source="hub.challenge")
    hub_verify_token = serializers.CharField(source="hub.verify_token")

    def validate(self, attrs):
        # Fields come in as hub.mode etc from query params
        return attrs


class OutboundMessageSerializer(serializers.Serializer):
    """Used by dashboard to trigger manual outbound messages."""
    to = serializers.CharField()
    message = serializers.CharField()
    message_type = serializers.ChoiceField(
        choices=["text", "template"],
        default="text",
    )