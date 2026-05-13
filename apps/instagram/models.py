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
    
    # AI metadata (outbound only)
    model_used = models.CharField(max_length=60, blank=True)
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    
    timestamp = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"IG-Msg {self.direction} | {self.client.ig_user_id}"

class InstagramApprovalQueue(models.Model):
    """
    Human review queue for Instagram AI-suggested actions.
    """
    class ApprovalAction(models.TextChoices):
        SEND_MESSAGE = "send_message", "Send AI Draft Message"
        ESCALATE = "escalate", "Escalate to Human"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="ig_approval_items"
    )
    conversation = models.ForeignKey(
        InstagramConversation, on_delete=models.CASCADE, related_name="approval_items"
    )

    action = models.CharField(max_length=30, choices=ApprovalAction.choices)
    status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )

    ai_suggestion = models.TextField()
    ai_reasoning = models.TextField(blank=True)
    heat_score_at_suggestion = models.PositiveSmallIntegerField(default=50)

    reviewer_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_ig_approvals",
    )

    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[IG-{self.status.upper()}] {self.action} for {self.client}"

    def approve(self, user, notes: str = ""):
        self.status = self.ApprovalStatus.APPROVED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.reviewer_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "reviewer_notes", "updated_at"])

    def reject(self, user, notes: str = ""):
        self.status = self.ApprovalStatus.REJECTED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.reviewer_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "reviewer_notes", "updated_at"])
