from rest_framework import serializers
from .models import InstagramConversation, InstagramMessage, InstagramApprovalQueue
from apps.clients.models import Client

class InstagramMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramMessage
        fields = "__all__"

class InstagramClientSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Client
        fields = ["id", "ig_user_id", "name", "status", "last_message", "last_contact"]

    def get_last_message(self, obj):
        last_msg = InstagramMessage.objects.filter(client=obj).order_by("-timestamp").first()
        if last_msg:
            return {
                "content": last_msg.content,
                "timestamp": last_msg.timestamp,
                "direction": last_msg.direction
            }
        return None

class InstagramApprovalQueueSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_id = serializers.IntegerField(source="client.id", read_only=True)
    heat_label = serializers.SerializerMethodField()

    class Meta:
        model = InstagramApprovalQueue
        fields = [
            "id", "client_id", "client_name", "action", "status",
            "ai_suggestion", "ai_reasoning", "heat_score_at_suggestion",
            "heat_label", "created_at", "expires_at"
        ]

    def get_heat_label(self, obj):
        score = obj.heat_score_at_suggestion
        if score >= 70: return "HIGH"
        if score >= 40: return "MEDIUM"
        return "LOW"
