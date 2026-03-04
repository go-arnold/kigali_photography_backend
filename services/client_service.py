"""
Client Service
==============
Single source of truth for creating, fetching, and updating clients.
All DB writes go through here — keeps views and tasks clean.
"""

import logging
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from apps.clients.models import (
    Client,
    ClientStatus,
    JourneyState,
    JourneyPhase,
)
from apps.conversations.models import Conversation

logger = logging.getLogger(__name__)


def get_or_create_client(wa_number: str, name: str = "") -> tuple[Client, bool]:
    """
    Upsert a client by WhatsApp number.
    Returns (client, created).
    Updates name if provided and different.
    """
    client, created = Client.objects.get_or_create(
        wa_number=wa_number,
        defaults={"name": name, "status": ClientStatus.NEW},
    )
    if not created and name and client.name != name:
        client.name = name
        client.save(update_fields=["name", "updated_at"])
    return client, created


def get_or_create_journey(client: Client) -> tuple[JourneyState, bool]:
    """Ensure client has a JourneyState row."""
    return JourneyState.objects.get_or_create(client=client)


def get_or_create_conversation(client: Client) -> tuple[Conversation, bool]:
    """
    Get the active (open window) conversation or create a new one.
    A new conversation is created when:
      - No conversation exists
      - Last conversation's 24h window has expired
    """
    now = timezone.now()
    conv = (
        Conversation.objects.filter(
            client=client,
            window_status=Conversation.WindowStatus.OPEN,
            window_expires_at__gt=now,
        )
        .order_by("-started_at")
        .first()
    )

    if conv:
        return conv, False

    # Close any stale open conversations
    Conversation.objects.filter(
        client=client,
        window_status=Conversation.WindowStatus.OPEN,
    ).update(window_status=Conversation.WindowStatus.CLOSED)

    # Get current journey state for snapshot
    journey = getattr(client, "journey_state", None)

    conv = Conversation.objects.create(
        client=client,
        token_budget=settings.CLAUDE["CONVERSATION_BUDGET"],
        window_expires_at=now + timezone.timedelta(hours=24),
        entry_phase=journey.phase if journey else JourneyPhase.ENTRY,
        entry_heat=journey.heat_score if journey else 50,
    )
    logger.info("New conversation #%s opened for client %s", conv.pk, client.wa_number)
    return conv, True


@transaction.atomic
def onboard_client(
    wa_number: str, name: str = "", referral: str = ""
) -> tuple[Client, JourneyState, Conversation, bool]:
    """
    Full onboarding: ensure client + journey + conversation exist.
    Returns (client, journey, conversation, is_new_client).
    Used at the start of every inbound message processing.
    """
    client, is_new = get_or_create_client(wa_number, name)

    if referral and not client.referral_source:
        client.referral_source = referral
        client.save(update_fields=["referral_source", "updated_at"])

    client.update_last_contact()

    if client.status == ClientStatus.NEW:
        client.status = ClientStatus.ACTIVE
        client.save(update_fields=["status", "updated_at"])

    journey, _ = get_or_create_journey(client)
    conversation, _ = get_or_create_conversation(client)
    conversation.touch()

    return client, journey, conversation, is_new


def is_budget_exceeded(client: Client, conversation: Conversation) -> bool:
    """
    Check both conversation-level and client lifetime token budgets.
    If exceeded, flag for human takeover.
    """
    if conversation.is_budget_exceeded:
        logger.warning(
            "Conversation #%s token budget exceeded (%s/%s tokens)",
            conversation.pk,
            conversation.tokens_used,
            conversation.token_budget,
        )
        return True

    # Also check lifetime budget (soft ceiling — log but don't hard-block returning clients)
    lifetime_limit = (
        settings.CLAUDE["CONVERSATION_BUDGET"] * 50
    )  # configurable sentinel
    if client.lifetime_tokens_used > lifetime_limit:
        logger.warning(
            "Client %s lifetime token budget exceeded (%s tokens)",
            client.wa_number,
            client.lifetime_tokens_used,
        )
        return True

    return False


def record_tokens(
    client: Client, conversation: Conversation, input_tokens: int, output_tokens: int
):
    """Atomically record token usage at both conversation and client level."""
    total = input_tokens + output_tokens
    conversation.add_tokens(total)
    # Client.objects.filter(pk=client.pk).update(
    #     lifetime_tokens_used=Client.lifetime_tokens_used.__class__(
    #         "lifetime_tokens_used"
    #     )
    #     + total
    # )
    from django.db.models import F
    Client.objects.filter(pk=client.pk).update(
        lifetime_tokens_used=F("lifetime_tokens_used") + total
    )
