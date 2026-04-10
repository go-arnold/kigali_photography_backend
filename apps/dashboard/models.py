#Notifications added
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class PushSubscription(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="push_subscription"
    )
    subscription_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Push subscription for {self.user.username}"