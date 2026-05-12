from django.db import models
from django.utils import timezone
from apps.clients.models import Client

class InstagramConversation(models.Model):
    """
    An Instagram DM conversation session.
    Instagram has a 7-day messaging window.
    """
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="ig_conversations"
    )
    is_open = models.BooleanField(default=True)
    last_message_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at"]

    def __str__(self):
        return f"IG-Conv for {self.client.ig_user_id or self.client.pk}"

class InstagramMessage(models.Model):
    """Individual message within an Instagram conversation."""
    conversation = models.ForeignKey(
        InstagramConversation, on_delete=models.CASCADE, related_name="messages"
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="ig_messages"
    )
    ig_mid = models.CharField(max_length=200, unique=True, db_index=True)
    
    direction = models.CharField(max_length=10, choices=[("inbound", "Inbound"), ("outbound", "Outbound")])
    content = models.TextField()
    msg_type = models.CharField(max_length=20, default="text") # text, image, video
    
    media_url = models.URLField(max_length=500, blank=True, default="")
    
    timestamp = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"IG-Msg {self.direction} | {self.client.ig_user_id}"
