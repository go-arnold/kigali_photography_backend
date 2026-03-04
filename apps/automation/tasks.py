"""
Celery Tasks — Automation Layer
================================
All heavy processing lives here, off the request thread.

Tasks:
  process_inbound_message  → full 16-step pipeline via journey_orchestrator
  update_message_status    → delivery receipt handler
  send_scheduled_messages  → birthday wishes, follow-ups, reminders (beat task)
  expire_approval_items    → auto-archive stale approval queue items (beat task)
  summarize_long_conversation → compress old messages when threshold hit (beat task)

Cost protection:
  - _acquire_processing_lock: Redis atomic lock prevents duplicate concurrent processing
  - acks_late=True: task not lost if worker crashes mid-flight
  - Exponential backoff: 5s, 10s, 20s between retries
"""

import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from services.whatsapp import mark_as_read  

logger = logging.getLogger(__name__)

_PROCESSING_TTL = 60  # seconds — lock TTL per message_id


def _acquire_processing_lock(message_id: str) -> bool:
    """Atomic Redis lock. Returns True if this worker got the lock."""
    key = f"processing_lock:{message_id}"
    return cache.add(key, 1, _PROCESSING_TTL)


# Main pipeline task


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    name="automation.process_inbound_message",
)
def process_inbound_message(
    self,
    message_id: str,
    from_number: str,
    from_name: str,
    timestamp: str,
    msg_type: str,
    text: str,
    media_id: str = None,
    interactive_id: str = None,
):
    """
    Full 16-step inbound message pipeline.

    Steps (in journey_orchestrator.handle_inbound_message):
      1. Opt-out check
      2. Onboard client (upsert Client + JourneyState + Conversation)
      3. Save inbound message
      4. Token budget check → human takeover if exceeded
      5. Human takeover check → silence AI if flagged
      6. Language detection → update client preference
      7. Intent + objection analysis (Haiku, cheap)
      8. Heat score update
      9. RAG context retrieval
     10. Build system prompt
     11. Build messages context (sliding window + summary)
     12. Call Claude (Haiku default, Sonnet for escalated sales resistance)
     13. Record tokens at conversation + client level
     14. Save outbound message with full token accounting
     15. Human approval gate (payment, escalation, bonuses)
     16. Send via WhatsApp or queue for approval
    """
    # Concurrency guard (layer 2 — layer 1 is in webhook idempotency)
    if not _acquire_processing_lock(message_id):
        logger.warning("Duplicate task for message %s — skipping", message_id)
        return

    logger.info(
        "Processing | id=%s from=%s type=%s text='%s'",
        message_id,
        from_number,
        msg_type,
        (text or "")[:80],
    )

    try:
        # Mark as read immediately — costs nothing, shows blue ticks

        mark_as_read(message_id)

        # Run full pipeline
        from services.journey_orchestrator import handle_inbound_message

        result = handle_inbound_message(
            message_id=message_id,
            from_number=from_number,
            from_name=from_name,
            msg_type=msg_type,
            text=text,
            timestamp=timestamp,
            interactive_id=interactive_id,
        )

        logger.info(
            "Pipeline result | id=%s action=%s tokens=%s",
            message_id,
            result.action,
            result.tokens_used,
        )

        if not result.success and result.action == "error":
            raise Exception(result.error)

    except Exception as exc:
        logger.exception("Pipeline error for message %s: %s", message_id, exc)
        raise self.retry(exc=exc, countdown=2**self.request.retries * 5)


# Delivery status update


@shared_task(
    bind=True,
    max_retries=2,
    acks_late=True,
    name="automation.update_message_status",
)
def update_message_status(self, message_id: str, from_number: str, status: str):
    """Update delivery/read status on outbound message record."""
    try:
        from apps.conversations.models import Message

        updated = Message.objects.filter(wa_message_id=message_id).update(
            status=status,
        )
        if updated:
            logger.debug("Status updated | wamid=%s status=%s", message_id, status)
    except Exception as exc:
        logger.warning("Status update failed for %s: %s", message_id, exc)
        raise self.retry(exc=exc, countdown=5)


# Scheduled messages (Celery Beat)


@shared_task(
    name="automation.send_scheduled_messages",
    acks_late=True,
)
def send_scheduled_messages():
    """
    Pick up pending ScheduledMessages due for sending.
    Runs every 5 minutes via Celery Beat.

    Handles:
      - Birthday wishes (pure emotional, no selling)
      - Birthday reminders (outbound to past clients)
      - Follow-ups (heat-based cadence)
      - Session reminders
      - Day-of welcome messages
      - Feedback requests
    """
    from apps.conversations.models import ScheduledMessage
    from services.whatsapp import send_text, send_template

    now = timezone.now()
    due = (
        ScheduledMessage.objects.filter(
            status=ScheduledMessage.SendStatus.PENDING,
            send_at__lte=now,
            client__is_opted_out=False,
        )
        .select_related("client")
        .order_by("send_at")[:50]
    )  # batch of 50

    sent_count = 0
    for scheduled in due:
        try:
            _dispatch_scheduled(scheduled, send_text, send_template)
            scheduled.mark_sent()
            sent_count += 1
        except Exception as exc:
            logger.error("Failed to send scheduled message %s: %s", scheduled.pk, exc)
            scheduled.mark_failed(str(exc)[:200])

    if sent_count:
        logger.info("Sent %s scheduled messages", sent_count)


def _dispatch_scheduled(scheduled, send_text_fn, send_template_fn):
    """Route scheduled message to correct send method."""
    from apps.conversations.models import ScheduledMessageType

    client = scheduled.client
    msg_type = scheduled.message_type

    # Template messages for outbound (24h window closed)
    if msg_type in (
        ScheduledMessageType.BIRTHDAY_REMINDER,
        ScheduledMessageType.FOLLOWUP,
    ):
        # Use pre-approved Meta template for outbound
        template_name = _get_template_name(msg_type, scheduled.language)
        lang_code = "rw_RW" if scheduled.language == "rw" else "en_US"
        send_template_fn(
            to=client.wa_number,
            template_name=template_name,
            language_code=lang_code,
        )
    else:
        # Session window open — send direct text
        if scheduled.content:
            send_text_fn(to=client.wa_number, message=scheduled.content)


def _get_template_name(msg_type: str, language: str) -> str:
    """Map message type + language to pre-approved Meta template name."""
    templates = {
        ("birthday_reminder", "en"): "birthday_reminder_en",
        ("birthday_reminder", "rw"): "birthday_reminder_rw",
        ("followup", "en"): "followup_en",
        ("followup", "rw"): "followup_rw",
    }
    return templates.get((msg_type, language), "followup_en")


# Approval queue maintenance


@shared_task(
    name="automation.expire_approval_items",
    acks_late=True,
)
def expire_approval_items():
    """
    Auto-expire pending approval items past their expires_at.
    Runs every 30 minutes via Celery Beat.
    Prevents the queue from growing unbounded.
    """
    from apps.conversations.models import ApprovalQueue, ApprovalStatus

    now = timezone.now()
    expired = ApprovalQueue.objects.filter(
        status=ApprovalStatus.PENDING,
        expires_at__lt=now,
    )
    count = expired.count()
    if count:
        expired.update(status=ApprovalStatus.EXPIRED)
        logger.info("Expired %s stale approval items", count)


# Conversation summarization


@shared_task(
    name="automation.summarize_long_conversations",
    acks_late=True,
)
def summarize_long_conversations():
    """
    Find conversations with 12+ messages and no summary yet.
    Compress old messages into ConversationSummary.
    Runs every hour via Celery Beat.

    Token savings: 60-70% reduction on subsequent turns in long conversations.
    """
    from apps.conversations.models import Conversation
    from django.db.models import Count

    # Find open conversations with many messages and no summary
    candidates = (
        Conversation.objects.annotate(msg_count=Count("messages"))
        .filter(
            window_status=Conversation.WindowStatus.OPEN,
            msg_count__gte=12,
            summary__isnull=True,
        )
        .select_related("client")[:20]
    )

    for conv in candidates:
        try:
            _summarize_conversation(conv)
        except Exception as exc:
            logger.error("Summarization failed for conv #%s: %s", conv.pk, exc)


def _summarize_conversation(conversation):
    """Compress conversation messages into a ConversationSummary."""
    from apps.rag.models import ConversationSummary
    from services.claude import summarize_conversation
    from utils.tokens import estimate_tokens

    # Get all but last 5 messages (keep recent ones fresh)
    all_msgs = list(conversation.messages.order_by("timestamp"))
    to_summarize = all_msgs[:-5]

    if len(to_summarize) < 5:
        return

    messages_dicts = [
        {
            "role": "user" if m.direction == "inbound" else "assistant",
            "content": m.content,
        }
        for m in to_summarize
    ]

    client_name = conversation.client.name or conversation.client.wa_number
    result = summarize_conversation(messages_dicts, client_name)

    if not result.ok or not result.text:
        logger.warning("Summarization returned empty for conv #%s", conversation.pk)
        return

    # Estimate tokens saved
    original_tokens = sum(estimate_tokens(m["content"]) for m in messages_dicts)
    summary_tokens = estimate_tokens(result.text)
    tokens_saved = max(0, original_tokens - summary_tokens)

    ConversationSummary.objects.update_or_create(
        conversation=conversation,
        defaults={
            "summary_text": result.text,
            "messages_summarized": len(to_summarize),
            "tokens_saved": tokens_saved,
            "last_updated": timezone.now(),
        },
    )
    logger.info(
        "Summarized conv #%s | compressed %s messages | saved ~%s tokens",
        conversation.pk,
        len(to_summarize),
        tokens_saved,
    )


# S Birthday automation


@shared_task(
    name="automation.schedule_birthday_messages",
    acks_late=True,
)
def schedule_birthday_messages():
    """
    Daily task: find children with birthdays today and schedule messages.
    Runs at 7:00 AM Kigali time via Celery Beat.

    Two types:
      - birthday_wish:     pure emotional, for ALL past clients (no selling)
      - birthday_reminder: outbound campaign for RETURNING clients only
    """
    from apps.clients.models import Child, ClientStatus
    from apps.conversations.models import ScheduledMessage, ScheduledMessageType

    today = timezone.now().date()

    # Find children with today's birthday
    birthday_children = Child.objects.filter(
        birthday__month=today.month,
        birthday__day=today.day,
        client__is_opted_out=False,
    ).select_related("client__journey_state")

    scheduled_count = 0
    for child in birthday_children:
        client = child.client
        year = today.year

        if child.birthday_wish_sent_year == year:
            continue

        # Birthday wish (all clients)
        wish_key = f"birthday_wish:{client.pk}:{year}"
        ScheduledMessage.objects.get_or_create(
            dedup_key=wish_key,
            defaults={
                "client": client,
                "message_type": ScheduledMessageType.BIRTHDAY_WISH,
                "content": _render_birthday_wish(child, client.language),
                "language": client.language,
                "send_at": timezone.now().replace(hour=9, minute=0, second=0),
            },
        )

        # Birthday reminder (returning clients only)
        if client.status in (ClientStatus.RETURNING, "past"):
            reminder_key = f"birthday_reminder:{client.pk}:{year}"
            ScheduledMessage.objects.get_or_create(
                dedup_key=reminder_key,
                defaults={
                    "client": client,
                    "message_type": ScheduledMessageType.BIRTHDAY_REMINDER,
                    "content": "",  # template-based
                    "language": client.language,
                    "send_at": timezone.now().replace(hour=10, minute=0, second=0),
                },
            )

        # Mark wish as scheduled for this year
        child.birthday_wish_sent_year = year
        child.save(update_fields=["birthday_wish_sent_year"])
        scheduled_count += 1

    if scheduled_count:
        logger.info("Scheduled birthday messages for %s children", scheduled_count)


def _render_birthday_wish(child, language: str) -> str:
    """
    Warm, personal birthday wish. No selling, no pressure.
    Pure emotional connection — follows Phase 1.3 spec.
    """
    if language == "rw":
        return (
            f"Muramutse! 🎂 Uyu munsi ni umunsi mwiza wa {child.name}! "
            f"Twifuriza {child.name} amahoro, ibyishimo n'ubuzima bwiza. "
            f"Murakoze kugira ibihe byiza natwe! 📸✨"
        )
    return (
        f"Happy Birthday to the wonderful {child.name}! 🎂🎉 "
        f"Wishing them a day full of joy, laughter, and beautiful memories. "
        f"Thank you for letting us be part of your family's journey! 📸✨"
    )
