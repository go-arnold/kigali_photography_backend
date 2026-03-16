"""
Client serializers — used by dashboard API endpoints.
"""
from rest_framework import serializers
from .models import Client, Child, JourneyState


class ChildSerializer(serializers.ModelSerializer):
    age_years = serializers.ReadOnlyField()
    birthday_wish_needed = serializers.ReadOnlyField()

    class Meta:
        model = Child
        fields = ("id", "name", "birthday", "age_years", "birthday_wish_needed",
                  "birthday_wish_sent_year", "created_at")
        read_only_fields = ("id", "created_at")


class JourneyStateSerializer(serializers.ModelSerializer):
    heat_label = serializers.ReadOnlyField()

    class Meta:
        model = JourneyState
        fields = (
            "phase", "step", "heat_score", "heat_label",
            "detected_objection", "objection_count",
            "next_followup_at", "followup_count",
            "human_takeover", "takeover_reason",
            "selected_package", "session_date",
            "updated_at",
        )
        read_only_fields = ("heat_label", "updated_at")


class ClientSerializer(serializers.ModelSerializer):
    children = ChildSerializer(many=True, read_only=True)
    journey_state = JourneyStateSerializer(read_only=True)

    class Meta:
        model = Client
        fields = (
            "id", "wa_number", "name", "status", "language",
            "referral_source", "satisfaction_score",
            "total_sessions", "total_spent_rwf", "lifetime_tokens_used",
            "first_contact", "last_contact", "created_at",
            "children", "journey_state",
        )
        read_only_fields = ("id", "lifetime_tokens_used", "first_contact", "created_at")


class ClientListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — no nested data."""
    heat_label = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ("id", "wa_number", "name", "status", "language",
                  "total_sessions", "last_contact", "heat_label")

    def get_heat_label(self, obj):
        try:
            return obj.journey_state.heat_label
        except Exception:
            return "UNKNOWN"