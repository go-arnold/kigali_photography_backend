"""
Dashboard-specific serializers.
Richer than app-level serializers — includes computed fields
needed for the human oversight UI.
"""

from rest_framework import serializers
from apps.clients.models import Client, JourneyState
from apps.conversations.models import (
    ApprovalQueue,
    ScheduledMessage,
    Message,
    Conversation,
)


class DashboardClientSerializer(serializers.ModelSerializer):
    """Full client card for dashboard — all context staff needs at a glance."""

    heat_label = serializers.SerializerMethodField()
    heat_score = serializers.SerializerMethodField()
    phase = serializers.SerializerMethodField()
    step = serializers.SerializerMethodField()
    human_takeover = serializers.SerializerMethodField()
    pending_approvals = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    token_budget_pct = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = (
            "id",
            "wa_number",
            "name",
            "status",
            "language",
            "referral_source",
            "satisfaction_score",
            "total_sessions",
            "total_spent_rwf",
            "lifetime_tokens_used",
            "last_contact",
            "is_opted_out",
            # Journey context
            "heat_label",
            "heat_score",
            "phase",
            "step",
            "human_takeover",
            "pending_approvals",
            "children",
            "token_budget_pct",
        )

    def get_heat_label(self, obj):
        return getattr(getattr(obj, "journey_state", None), "heat_label", "UNKNOWN")

    def get_heat_score(self, obj):
        return getattr(getattr(obj, "journey_state", None), "heat_score", 50)

    def get_phase(self, obj):
        return getattr(getattr(obj, "journey_state", None), "phase", None)

    def get_step(self, obj):
        return getattr(getattr(obj, "journey_state", None), "step", None)

    def get_human_takeover(self, obj):
        return getattr(getattr(obj, "journey_state", None), "human_takeover", False)

    def get_pending_approvals(self, obj):
        return obj.approval_items.filter(status="pending").count()

    def get_children(self, obj):
        return [
            {"name": c.name, "birthday": c.birthday, "age_years": c.age_years}
            for c in obj.children.all()
        ]

    def get_token_budget_pct(self, obj):
        conv = obj.conversations.filter(window_status="open").first()
        if conv and conv.token_budget:
            return round((conv.tokens_used / conv.token_budget) * 100, 1)
        return 0.0


class ApprovalQueueSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_phone = serializers.CharField(source="client.wa_number", read_only=True)
    heat_label = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalQueue
        fields = (
            "id",
            "action",
            "status",
            "client",
            "client_name",
            "client_phone",
            "ai_suggestion",
            "ai_reasoning",
            "heat_score_at_suggestion",
            "heat_label",
            "reviewer_notes",
            "reviewed_at",
            "reviewed_by",
            "expires_at",
            "is_expired",
            "created_at",
        )
        read_only_fields = (
            "id",
            "client_name",
            "client_phone",
            "ai_suggestion",
            "ai_reasoning",
            "heat_score_at_suggestion",
            "heat_label",
            "reviewed_at",
            "reviewed_by",
            "is_expired",
            "created_at",
        )

    def get_heat_label(self, obj):
        score = obj.heat_score_at_suggestion
        if score >= 70:
            return "HIGH"
        if score >= 40:
            return "MEDIUM"
        return "LOW"

    def get_is_expired(self, obj):
        from django.utils import timezone

        return obj.expires_at < timezone.now()


class ApprovalActionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    send_immediately = serializers.BooleanField(default=True)


class ManualMessageSerializer(serializers.Serializer):
    """Send a manual message from studio staff to a client."""

    to = serializers.CharField()
    message = serializers.CharField()

    # def validate_to(self, value):
    #     if not value.startswith("+"):
    #         raise serializers.ValidationError("Phone must be in E.164 format (+250...)")
    #     return value


class JourneyOverrideSerializer(serializers.Serializer):
    """Override a client's journey phase/step or release human takeover."""

    phase = serializers.CharField(required=False)
    step = serializers.CharField(required=False)
    release_takeover = serializers.BooleanField(required=False, default=False)
    heat_score = serializers.IntegerField(required=False, min_value=0, max_value=100)

    def validate(self, data):
        if not any(
            [data.get("phase"), data.get("release_takeover"), "heat_score" in data]
        ):
            raise serializers.ValidationError(
                "Provide at least one of: phase, release_takeover, heat_score"
            )
        return data


class TokenStatsSerializer(serializers.Serializer):
    """Read-only token spend summary for dashboard."""

    total_conversations = serializers.IntegerField()
    total_tokens_used = serializers.IntegerField()
    estimated_cost_usd = serializers.FloatField()
    conversations_over_budget = serializers.IntegerField()
    pending_approvals = serializers.IntegerField()
    active_human_takeovers = serializers.IntegerField()


class ScheduledMessageSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_phone = serializers.CharField(source="client.wa_number", read_only=True)

    class Meta:
        model = ScheduledMessage
        fields = (
            "id",
            "client",
            "client_name",
            "client_phone",
            "message_type",
            "content",
            "language",
            "send_at",
            "status",
            "sent_at",
            "failure_reason",
            "created_at",
        )
        read_only_fields = (
            "id",
            "client_name",
            "client_phone",
            "sent_at",
            "created_at",
        )
