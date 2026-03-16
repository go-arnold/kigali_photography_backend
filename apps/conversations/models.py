"""
Conversation Models
====================
Conversation     — one session of interaction (24h WhatsApp window)
Message          — individual inbound/outbound message
HeatEvent        — audit log for heat score changes
ApprovalQueue    — human review queue for AI-suggested actions
ScheduledMessage — future messages (follow-ups, birthday reminders, etc.)
"""

from django.db import models
from django.utils import timezone

from apps.clients.models import Client


class Conversation(models.Model):
    """
    A WhatsApp conversation session.
    Meta's 24h customer service window maps to one Conversation.
    New conversation created when window expires and client messages again.
    """

    class WindowStatus(models.TextChoices):
        OPEN = "open", "Open (within 24h)"
        CLOSED = "closed", "Closed (24h expired)"

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="conversations"
    )
    window_status = models.CharField(
        max_length=10, choices=WindowStatus.choices, default=WindowStatus.OPEN
    )
    window_expires_at = models.DateTimeField(null=True, blank=True)

    # Token accounting for this conversation
    tokens_used = models.PositiveIntegerField(
        default=0, help_text="Total Claude tokens used in this conversation"
    )
    token_budget = models.PositiveIntegerField(
        default=20000, help_text="Max tokens before forcing human takeover"
    )

    # Snapshot of state at conversation start
    entry_phase = models.CharField(max_length=30, blank=True)
    entry_heat = models.PositiveSmallIntegerField(default=50)

    started_at = models.DateTimeField(default=timezone.now)
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["client", "window_status"]),
            models.Index(fields=["window_expires_at"]),
        ]

    def __str__(self):
        return f"Conv#{self.pk} {self.client} [{self.window_status}]"

    @property
    def is_budget_exceeded(self) -> bool:
        return self.tokens_used >= self.token_budget

    def add_tokens(self, count: int):
        """Atomically increment token counter."""
        Conversation.objects.filter(pk=self.pk).update(
            tokens_used=models.F("tokens_used") + count
        )
        self.tokens_used += count  # keep in-memory copy in sync

    def touch(self):
        """Update last_message_at and refresh 24h window."""
        now = timezone.now()
        self.last_message_at = now
        self.window_expires_at = now + timezone.timedelta(hours=24)
        self.window_status = self.WindowStatus.OPEN
        self.save(
            update_fields=["last_message_at", "window_expires_at", "window_status"]
        )


class MessageDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound (client → us)"
    OUTBOUND = "outbound", "Outbound (us → client)"


class MessageStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    FAILED = "failed", "Failed"


class Message(models.Model):
    """Individual message within a conversation."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="messages"
    )

    # WhatsApp message ID (from Meta or returned on send)
    wa_message_id = models.CharField(max_length=100, unique=True, db_index=True)

    direction = models.CharField(max_length=10, choices=MessageDirection.choices)
    status = models.CharField(
        max_length=15, choices=MessageStatus.choices, default=MessageStatus.RECEIVED
    )

    content = models.TextField()
    msg_type = models.CharField(
        max_length=20,
        default="text",
        help_text="text | image | audio | interactive | template",
    )

    # AI metadata (outbound only)
    generated_by_ai = models.BooleanField(default=False)
    model_used = models.CharField(max_length=60, blank=True)
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    approved_by_human = models.BooleanField(
        null=True,
        blank=True,
        help_text="None=auto-sent, True=human approved, False=human rejected",
    )

    # Timing
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["conversation", "timestamp"]),
            models.Index(fields=["direction", "status"]),
        ]

    def __str__(self):
        arrow = "←" if self.direction == MessageDirection.INBOUND else "→"
        preview = self.content[:60]
        return f"[{arrow}] {self.client.wa_number}: {preview}"

    @property
    def total_tokens(self) -> int:
        return self.tokens_input + self.tokens_output


class HeatEvent(models.Model):
    """
    Audit trail for every heat score change.
    Powers the learning feedback loop — what signals moved heat?
    """

    class SignalType(models.TextChoices):
        REPLY_SPEED = "reply_speed", "Reply Speed"
        MESSAGE_LENGTH = "message_length", "Message Length"
        QUESTION_DEPTH = "question_depth", "Question Depth"
        EMOTIONAL_TONE = "emotional_tone", "Emotional Tone"
        ENGAGEMENT_PATTERN = "engagement_pattern", "Engagement Pattern"
        MANUAL_OVERRIDE = "manual_override", "Manual Override"

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="heat_events"
    )
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="heat_events"
    )
    signal_type = models.CharField(max_length=30, choices=SignalType.choices)
    delta = models.SmallIntegerField(help_text="Score change: +10, -5, etc.")
    score_before = models.PositiveSmallIntegerField()
    score_after = models.PositiveSmallIntegerField()
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.client} | {self.signal_type} | {sign}{self.delta} → {self.score_after}"


class ApprovalAction(models.TextChoices):
    SEND_BONUS = "send_bonus", "Send Bonus Offer"
    SEND_MESSAGE = "send_message", "Send AI Draft Message"
    PACKAGE_ADJUSTMENT = "package_adjustment", "Package Adjustment"
    ESCALATE = "escalate", "Escalate to Human"
    SEND_FOLLOWUP = "send_followup", "Send Follow-up"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired (auto-archived)"


class ApprovalQueue(models.Model):
    """
    Human review queue — AI suggestions waiting for human approval.
    Critical for: bonuses, escalation decisions, package adjustments.
    """

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="approval_items"
    )
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="approval_items"
    )

    action = models.CharField(max_length=30, choices=ApprovalAction.choices)
    status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )

    # AI's suggested content
    ai_suggestion = models.TextField(help_text="What AI wants to send/do")
    ai_reasoning = models.TextField(blank=True, help_text="Why AI is suggesting this")
    heat_score_at_suggestion = models.PositiveSmallIntegerField(default=50)

    # Human decision
    reviewer_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_approvals",
    )

    # Auto-expire pending items after 48h (follow-up timing)
    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["client", "status"]),
        ]

    def __str__(self):
        return f"[{self.status.upper()}] {self.action} for {self.client}"

    def approve(self, user, notes: str = ""):
        self.status = ApprovalStatus.APPROVED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.reviewer_notes = notes
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "reviewer_notes",
                "updated_at",
            ]
        )

    def reject(self, user, notes: str = ""):
        self.status = ApprovalStatus.REJECTED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.reviewer_notes = notes
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "reviewer_notes",
                "updated_at",
            ]
        )


class ScheduledMessageType(models.TextChoices):
    BIRTHDAY_WISH = "birthday_wish", "Birthday Wish"
    BIRTHDAY_REMINDER = "birthday_reminder", "Birthday Reminder (Outbound)"
    FOLLOWUP = "followup", "Follow-up"
    SESSION_REMINDER = "session_reminder", "Session Reminder"
    DAY_OF_WELCOME = "day_of_welcome", "Day-of Welcome"
    FEEDBACK_REQUEST = "feedback_request", "Feedback Request"


class ScheduledMessage(models.Model):
    """
    Messages scheduled to be sent in the future.
    Celery Beat picks these up and sends them at the right time.
    """

    class SendStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="scheduled_messages"
    )
    message_type = models.CharField(max_length=30, choices=ScheduledMessageType.choices)
    content = models.TextField(
        blank=True, help_text="Pre-rendered content or template name"
    )
    language = models.CharField(max_length=5, default="en")

    send_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=15,
        choices=SendStatus.choices,
        default=SendStatus.PENDING,
        db_index=True,
    )

    # Dedup: prevent duplicate scheduled messages of same type for same client
    dedup_key = models.CharField(
        max_length=100,
        unique=True,
        help_text="e.g. birthday_wish:client_id:2025 — prevents duplicates",
    )

    sent_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["send_at"]
        indexes = [
            models.Index(fields=["status", "send_at"]),
        ]

    def __str__(self):
        return f"{self.message_type} → {self.client} at {self.send_at:%Y-%m-%d %H:%M}"

    def mark_sent(self):
        self.status = self.SendStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def mark_failed(self, reason: str):
        self.status = self.SendStatus.FAILED
        self.failure_reason = reason[:200]
        self.save(update_fields=["status", "failure_reason"])
