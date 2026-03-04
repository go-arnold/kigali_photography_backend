"""
Client Models
=============
Core entities: Client, Child, JourneyState

Design decisions:
- Client is keyed by WhatsApp phone number (wa_number) — that's the identity
- Child stores birthday for automated birthday reminders (the whole retention loop)
- JourneyState is ONE row per client — tracks where they are in the funnel
- All enums use TextChoices for readable DB values + IDE autocomplete
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class ClientStatus(models.TextChoices):
    NEW = "new", "New"
    ACTIVE = "active", "Active"  # In conversation
    BOOKED = "booked", "Booked"  # Deposit paid
    SESSION_DONE = "session_done", "Session Done"
    RETURNING = "returning", "Returning"  # Past client, eligible for campaigns
    COLD = "cold", "Cold"  # No response, archived


class PreferredLanguage(models.TextChoices):
    EN = "en", "English"
    RW = "rw", "Kinyarwanda"


class Client(models.Model):
    """A photography studio client identified by their WhatsApp number."""

    wa_number = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ClientStatus.choices,
        default=ClientStatus.NEW,
        db_index=True,
    )
    language = models.CharField(
        max_length=5, choices=PreferredLanguage.choices, default=PreferredLanguage.EN
    )

    # Relationship tracking
    referral_source = models.CharField(
        max_length=50,
        blank=True,
        help_text="ad | story_reply | manual | outbound | birthday",
    )
    satisfaction_score = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="1-5 from post-session feedback"
    )
    total_sessions = models.PositiveSmallIntegerField(default=0)
    total_spent_rwf = models.PositiveIntegerField(default=0)

    # Token budget enforcement
    lifetime_tokens_used = models.PositiveIntegerField(
        default=0, help_text="Running total of Claude tokens spent on this client"
    )

    # Opt-out / STOP handling
    is_opted_out = models.BooleanField(default=False, db_index=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    first_contact = models.DateTimeField(default=timezone.now)
    last_contact = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_contact"]
        indexes = [
            models.Index(fields=["status", "last_contact"]),
        ]

    def __str__(self):
        return f"{self.name or self.wa_number} ({self.status})"

    def update_last_contact(self):
        self.last_contact = timezone.now()
        self.save(update_fields=["last_contact", "updated_at"])


class Child(models.Model):
    """A client's child — birthday drives the retention loop."""

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="children"
    )
    name = models.CharField(max_length=80)
    birthday = models.DateField(null=True, blank=True, db_index=True)

    # Track if birthday wish was sent this year
    birthday_wish_sent_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Year when last birthday wish was sent (prevents duplicates)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "children"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (child of {self.client})"

    @property
    def birthday_wish_needed(self) -> bool:
        """True if birthday is today and wish hasn't been sent this year."""
        if not self.birthday:
            return False
        today = timezone.now().date()
        return (
            self.birthday.month == today.month
            and self.birthday.day == today.day
            and self.birthday_wish_sent_year != today.year
        )


class JourneyPhase(models.TextChoices):
    ENTRY = "entry", "Entry"
    BOOKING = "booking", "Booking"
    SALES_RESISTANCE = "sales_resistance", "Sales Resistance"
    PREPARATION = "preparation", "Preparation"
    DELIVERY = "delivery", "Delivery"
    FEEDBACK = "feedback", "Feedback"
    COMPLETE = "complete", "Complete"
    PAUSED = "paused", "Paused (Human Takeover)"


class JourneyStep(models.TextChoices):
    # Entry
    GREETING = "greeting", "Greeting"
    IDENTIFY_TYPE = "identify_type", "Identify Client Type"
    COLLECT_CHILD_INFO = "collect_child_info", "Collect Child Info"
    # Booking
    PACKAGE_PRESENTATION = "package_presentation", "Package Presentation"
    DATE_COORDINATION = "date_coordination", "Date Coordination"
    PAYMENT_CONFIRMATION = "payment_confirmation", "Payment Confirmation"
    # Sales resistance
    OBJECTION_HANDLING = "objection_handling", "Objection Handling"
    FOLLOW_UP = "follow_up", "Follow Up"
    # Preparation
    SESSION_CONFIRMATION = "session_confirmation", "Session Confirmation"
    PREPARATION_CHECKLIST = "preparation_checklist", "Preparation Checklist"
    DAY_OF_WELCOME = "day_of_welcome", "Day-of Welcome"
    # Delivery
    THANK_YOU = "thank_you", "Thank You"
    PHOTO_DELIVERY = "photo_delivery", "Photo Delivery"
    # Feedback
    FEEDBACK_REQUEST = "feedback_request", "Feedback Request"
    APPRECIATION = "appreciation", "Appreciation"


class JourneyState(models.Model):
    """
    Single row per client tracking their exact position in the funnel.
    Updated atomically as the client progresses.
    """

    client = models.OneToOneField(
        Client, on_delete=models.CASCADE, related_name="journey_state"
    )
    phase = models.CharField(
        max_length=30, choices=JourneyPhase.choices, default=JourneyPhase.ENTRY
    )
    step = models.CharField(
        max_length=40, choices=JourneyStep.choices, default=JourneyStep.GREETING
    )

    # Heat score (0-100, updated per message)
    heat_score = models.PositiveSmallIntegerField(default=50)

    # Objection tracking
    detected_objection = models.CharField(
        max_length=50,
        blank=True,
        help_text="price | timing | authority | passive | competitor",
    )
    objection_count = models.PositiveSmallIntegerField(default=0)

    # Follow-up scheduling
    next_followup_at = models.DateTimeField(null=True, blank=True)
    followup_count = models.PositiveSmallIntegerField(default=0)

    # Human takeover flag
    human_takeover = models.BooleanField(
        default=False,
        help_text="When True, AI is silenced and human handles this client",
    )
    takeover_reason = models.CharField(max_length=200, blank=True)

    # Package being discussed
    selected_package = models.CharField(max_length=100, blank=True)
    session_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["phase", "heat_score"]),
            models.Index(fields=["next_followup_at"]),
            models.Index(fields=["human_takeover"]),
        ]

    def __str__(self):
        return f"{self.client} | {self.phase}/{self.step} | heat={self.heat_score}"

    @property
    def heat_label(self) -> str:
        if self.heat_score >= 70:
            return "HIGH"
        if self.heat_score >= 40:
            return "MEDIUM"
        return "LOW"

    def advance(self, phase: str, step: str):
        self.phase = phase
        self.step = step
        self.save(update_fields=["phase", "step", "updated_at"])

    def flag_human_takeover(self, reason: str):
        self.human_takeover = True
        self.takeover_reason = reason
        self.save(update_fields=["human_takeover", "takeover_reason", "updated_at"])


class ClientNote(models.Model):
    """
    Human or AI-flagged notes about a client.
    AI-detected facts (new child info, preferences) are flagged for human review.
    """

    class Source(models.TextChoices):
        HUMAN = "human", "Human"
        AI_FLAGGED = "ai_flagged", "AI Flagged (Pending Review)"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="notes")
    content = models.TextField()
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.HUMAN
    )
    is_approved = models.BooleanField(
        default=True, help_text="AI-flagged notes start False until human approves"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.client} [{self.source}]"

    SOURCE_CHOICES = [
        ("human", "Human"),
        ("ai_flagged", "AI Flagged (Pending Review)"),
    ]

    client = models.ForeignKey(
        "clients.Client", on_delete=models.CASCADE, related_name="notes"
    )
    content = models.TextField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="human")
    is_approved = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note for {self.client} by {self.created_by}"
