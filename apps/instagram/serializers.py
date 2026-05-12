from rest_framework import serializers
from .models import InstagramConversation, InstagramMessage
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
