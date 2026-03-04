"""
Conversation serializers — dashboard read views + approval actions.
"""
from rest_framework import serializers
from .models import Conversation, Message, ApprovalQueue, ScheduledMessage, HeatEvent


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id", "wa_message_id", "direction", "status", "content",
            "msg_type", "generated_by_ai", "model_used",
            "tokens_input", "tokens_output", "approved_by_human", "timestamp",
        )
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    budget_percent = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id", "client", "window_status", "window_expires_at",
            "tokens_used", "token_budget", "budget_percent",
            "started_at", "last_message_at", "messages",
        )
        read_only_fields = fields

    def get_budget_percent(self, obj):
        if not obj.token_budget:
            return 0
        return round((obj.tokens_used / obj.token_budget) * 100, 1)


class ApprovalQueueSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_phone = serializers.CharField(source="client.wa_number", read_only=True)

    class Meta:
        model = ApprovalQueue
        fields = (
            "id", "client", "client_name", "client_phone",
            "action", "status", "ai_suggestion", "ai_reasoning",
            "heat_score_at_suggestion", "reviewer_notes",
            "reviewed_at", "reviewed_by", "expires_at", "created_at",
        )
        read_only_fields = (
            "id", "client_name", "client_phone", "ai_suggestion",
            "ai_reasoning", "heat_score_at_suggestion",
            "reviewed_at", "reviewed_by", "created_at",
        )


class ApprovalActionSerializer(serializers.Serializer):
    """Used for PATCH /approvals/{id}/approve/ and /reject/"""
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ScheduledMessageSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)

    class Meta:
        model = ScheduledMessage
        fields = (
            "id", "client", "client_name", "message_type", "content",
            "language", "send_at", "status", "dedup_key",
            "sent_at", "failure_reason", "created_at",
        )
        read_only_fields = ("id", "client_name", "sent_at", "failure_reason", "created_at")


class HeatEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeatEvent
        fields = (
            "id", "signal_type", "delta", "score_before",
            "score_after", "reason", "created_at",
        )
        read_only_fields = fields