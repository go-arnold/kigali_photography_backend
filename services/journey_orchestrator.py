"""
Journey Orchestrator
=====================
The brain that connects all services into one coherent pipeline.

Called by process_inbound_message Celery task.
Takes a raw inbound message → produces a WhatsApp reply or approval queue item.

Pipeline (in order):
  1. Opt-out check         → hard stop if client opted out
  2. Onboard               → upsert client + journey + conversation
  3. Save inbound message  → permanent record
  4. Budget check          → hard stop + human takeover if exceeded
  5. Human takeover check  → hard stop if human already handling
  6. Language detection    → update client preference
  7. Intent analysis       → classify message, detect objections (gtp 4 mini, cheap)
  8. Heat update           → update score from signals
  9. RAG retrieval         → fetch top-K relevant knowledge chunks
 10. Build prompt          → compact system prompt with context
 11. Call Openai           → get response (4o mini or 4o)
 12. Save outbound message → record with full token accounting
 13. Human approval gate   → queue or send directly based on phase/action
 14. Send / queue          → WhatsApp send or approval queue

Every step is logged. Any step can flag human takeover.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional
from django.utils import timezone
from django.conf import settings


logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    success: bool
    action: (
        str  # "sent" | "queued_for_approval" | "human_takeover" | "opted_out" | "error"
    )
    client_id: Optional[str] = None
    conversation_id: Optional[int] = None
    tokens_used: int = 0
    error: Optional[str] = None


# Phase : requires human approval?

_APPROVAL_REQUIRED_STEPS = {
    "payment_confirmation",
    "send_bonus",
    "package_adjustment",
    "escalate",
}

_AUTO_SEND_PHASES = {
    "entry",
    "preparation",
    "delivery",
    "feedback",
}


# Main pipeline


def handle_inbound_message(
    message_id: str,
    from_number: str,
    from_name: str,
    msg_type: str,
    text: str,
    timestamp: str,
    interactive_id: Optional[str] = None,
) -> OrchestratorResult:
    """
    Full inbound message pipeline.
    Returns OrchestratorResult — never raises.
    """

    try:
        # Step 1: Opt-out hard check
        opt_out_result = _check_opt_out(from_number, text)
        if opt_out_result:
            return opt_out_result

        # Step 2: Onboard client
        from services.client_service import onboard_client

        client, journey, conversation, is_new = onboard_client(
            wa_number=from_number,
            name=from_name,
        )

        # Step 3: Save inbound message
        inbound_msg = _save_inbound(
            client=client,
            conversation=conversation,
            message_id=message_id,
            text=text,
            msg_type=msg_type,
        )

        # Step 4: Budget check
        from services.client_service import is_budget_exceeded

        if is_budget_exceeded(client, conversation):
            journey.flag_human_takeover("Token budget exceeded")
            _notify_human_takeover(client, conversation, reason="Token budget exceeded")
            return OrchestratorResult(
                success=True,
                action="human_takeover",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
            )

        # Step 5: Human takeover check
        if journey.human_takeover:
            logger.info("Human takeover active for %s — AI silenced", client.wa_number)
            return OrchestratorResult(
                success=True,
                action="human_takeover",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
            )

        # Step 6: Language detection
        if text:
            _update_language(client, text)

        # Step 7: Intent + objection analysis
        intent_data = _analyze_intent(text, journey, conversation)

        # Step 8: Heat score update
        _update_heat(
            journey=journey,
            message_text=text,
            intent_data=intent_data,
            inbound_msg=inbound_msg,
            conversation=conversation,
        )

        # Step 9: RAG context retrieval
        from services.rag_service import retrieve_context

        rag_context = retrieve_context(
            query=text or "",
            journey_phase=journey.phase,
            language=client.language,
        )

        # Step 10: Build system prompt
        
        # from services.claude import build_system_prompt, build_messages_context
        from services.openai_service import build_system_prompt, build_messages_context

        children_info = _format_children(client)
        system_prompt = build_system_prompt(
            journey_phase=journey.phase,
            journey_step=journey.step,
            heat_label=journey.heat_label,
            language=client.language,
            client_name=client.name or from_number,
            children_info=children_info,
            rag_context=rag_context,
            
        )

        # Step 11: Build messages context
        summary = _get_conversation_summary(conversation)
        recent_msgs = _get_recent_messages(conversation)
        messages = build_messages_context(
            conversation_summary=summary,
            recent_messages=recent_msgs,
            new_message=text or f"[{msg_type} message]",
        )

        # Step 12: Call Claude
        escalate = journey.phase == "sales_resistance" and journey.heat_score >= 40
        # from services.claude import call_claude

        # claude_response = call_claude(
        #     system_prompt=system_prompt,
        #     messages=messages,
        #     escalate=escalate,
        # )
        from services.openai_service import call_openai
        claude_response = call_openai(
                system_prompt=system_prompt,
                messages=messages,
                escalate=escalate,
        )

        # Step 13: Record tokens
        from services.client_service import record_tokens

        record_tokens(
            client,
            conversation,
            claude_response.input_tokens,
            claude_response.output_tokens,
        )

        # Step 14: Save outbound message
        outbound_msg = _save_outbound(
            client=client,
            conversation=conversation,
            text=claude_response.text,
            model=claude_response.model,
            tokens_input=claude_response.input_tokens,
            tokens_output=claude_response.output_tokens,
        )

        

        # Step 15: Human approval gate
        needs_approval = _requires_approval(journey, intent_data)

        if needs_approval:
            _queue_for_approval(
                client=client,
                conversation=conversation,
                ai_suggestion=claude_response.text,
                ai_reasoning=f"Phase: {journey.phase}/{journey.step} | Heat: {journey.heat_label} | Intent: {intent_data.get('intent', 'unknown')}",
                heat_score=journey.heat_score,
                action=_map_approval_action(journey, intent_data),
            )
            outbound_msg.approved_by_human = None  # pending
            outbound_msg.save(update_fields=["approved_by_human"])
            return OrchestratorResult(
                success=True,
                action="queued_for_approval",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
                tokens_used=claude_response.total_tokens,
            )

        # Step 16: Send response
        from services.whatsapp import send_text

        send_text(to=from_number, message=claude_response.text)
        outbound_msg.approved_by_human = True
        outbound_msg.save(update_fields=["approved_by_human"])

        # Update conversation window
        conversation.touch()

        logger.info(
            "Pipeline complete | client=%s phase=%s tokens=%s action=sent",
            client.wa_number,
            journey.phase,
            claude_response.total_tokens,
        )

        return OrchestratorResult(
            success=True,
            action="sent",
            client_id=str(client.pk),
            conversation_id=conversation.pk,
            tokens_used=claude_response.total_tokens,
        )

    except Exception as exc:
        logger.exception("Orchestrator pipeline error for %s: %s", from_number, exc)
        return OrchestratorResult(
            success=False,
            action="error",
            error=str(exc),
        )


# Step helpers


def _check_opt_out(from_number: str, text: str) -> Optional[OrchestratorResult]:
    """
    Check if client has opted out OR is sending an opt-out signal.
    Opt-out keywords: STOP, UNSUBSCRIBE, OPT OUT, ARRÊT, HAGARARA
    """
    OPT_OUT_KEYWORDS = {"stop", "unsubscribe", "opt out", "hagarara", "tanga"}

    from apps.clients.models import Client

    try:
        client = Client.objects.get(wa_number=from_number)
        if client.is_opted_out:
            logger.info("Opted-out client %s messaged — ignoring", from_number)
            return OrchestratorResult(success=True, action="opted_out")
    except Client.DoesNotExist:
        pass

    if text and any(kw in text.lower() for kw in OPT_OUT_KEYWORDS):
        _process_opt_out(from_number)
        return OrchestratorResult(success=True, action="opted_out")

    return None


def _process_opt_out(from_number: str):
    """Mark client as opted out and send acknowledgement."""
    from apps.clients.models import Client
    from services.whatsapp import send_text

    client, _ = Client.objects.get_or_create(
        wa_number=from_number,
        defaults={"status": "new"},
    )
    client.is_opted_out = True
    client.opted_out_at = timezone.now()
    client.save(update_fields=["is_opted_out", "opted_out_at"])


def _save_inbound(client, conversation, message_id, text, msg_type):
    from apps.conversations.models import Message, MessageDirection, MessageStatus

    # Dedup by wa_message_id — safe to call even if already exists
    msg, _ = Message.objects.get_or_create(
        wa_message_id=message_id,
        defaults={
            "conversation": conversation,
            "client": client,
            "direction": MessageDirection.INBOUND,
            "status": MessageStatus.RECEIVED,
            "content": text or f"[{msg_type}]",
            "msg_type": msg_type,
            "timestamp": timezone.now(),
        },
    )
    return msg


def _save_outbound(client, conversation, text, model, tokens_input, tokens_output):
    import uuid
    from apps.conversations.models import Message, MessageDirection, MessageStatus

    msg = Message.objects.create(
        wa_message_id=f"outbound_{uuid.uuid4().hex[:12]}",
        conversation=conversation,
        client=client,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        content=text,
        msg_type="text",
        generated_by_ai=True,
        model_used=model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        timestamp=timezone.now(),
    )
    return msg


def _update_language(client, text: str):
    from utils.language import detect_language

    detected = detect_language(text)
    if detected != client.language:
        client.language = detected
        client.save(update_fields=["language", "updated_at"])


def _analyze_intent(text: str, journey, conversation) -> dict:
    """
    Run intent classification. Returns parsed dict.
    Gracefully returns empty dict on failure — non-critical.
    """
    if not text:
        return {}
    try:
        # Build mini context from last 2 messages
        last_msgs = conversation.messages.order_by("-timestamp")[:2]
        history = " | ".join(m.content[:100] for m in reversed(last_msgs))

        #from services.claude import analyze_intent_and_heat
        from services.openai_service import analyze_intent_and_heat

        result = analyze_intent_and_heat(text, history)

        if result.ok:
            # Strip markdown fences if model wraps response despite instructions
            raw = result.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)

       
    except (json.JSONDecodeError, Exception) as exc:
        logger.debug("Intent analysis parse failed (non-critical): %s", exc)
    return {}


def _update_heat(journey, message_text, intent_data, inbound_msg, conversation):
    """Apply all heat signals from this message."""
    from services.heat_engine import calculate_heat_delta, update_heat_score
    from apps.conversations.models import HeatEvent

    # Get timing for reply speed signal
    last_outbound = (
        conversation.messages.filter(direction="outbound")
        .order_by("-timestamp")
        .values_list("timestamp", flat=True)
        .first()
    )

    result = calculate_heat_delta(
        message_text=message_text or "",
        last_outbound_at=last_outbound,
        message_received_at=inbound_msg.timestamp,
    )

    # Apply delta from message analysis
    if result["total_delta"] != 0:
        dominant_signal = (
            result["signals"][0] if result["signals"] else "engagement_pattern"
        )
        update_heat_score(
            journey_state=journey,
            delta=result["total_delta"],
            signal_type=_map_heat_signal(dominant_signal),
            reason=", ".join(result["signals"][:3]),
        )

    # Apply additional delta from AI intent analysis
    ai_delta = intent_data.get("heat_delta", 0)
    if ai_delta and ai_delta != 0:
        update_heat_score(
            journey_state=journey,
            delta=ai_delta,
            signal_type=HeatEvent.SignalType.EMOTIONAL_TONE,
            reason=f"AI intent: {intent_data.get('intent', 'unknown')}",
        )

    # Update detected objection if found
    objection = intent_data.get("objection_type", "none")
    if objection and objection != "none":
        journey.detected_objection = objection
        journey.objection_count = (journey.objection_count or 0) + 1

        # If objection detected and in booking phase → activate sales resistance
        if journey.phase == "booking":
            from apps.clients.models import JourneyPhase, JourneyStep

            journey.advance(
                JourneyPhase.SALES_RESISTANCE, JourneyStep.OBJECTION_HANDLING
            )
        else:
            journey.save(
                update_fields=["detected_objection", "objection_count", "updated_at"]
            )


def _get_conversation_summary(conversation) -> Optional[str]:
    """Return compressed summary if it exists."""
    try:
        return conversation.summary.summary_text
    except Exception:
        return None


def _get_recent_messages(conversation) -> list:
    """
    Return last N messages as {role, content} dicts.
    Includes messages from current conversation only,
    but falls back to recent conversations if current is empty.
    """
    from apps.conversations.models import Message

    msgs = conversation.messages.order_by("-timestamp")[:10]

    # If current conversation has no messages yet, get from client's recent history
    if not msgs.exists():
        msgs = Message.objects.filter(
            client=conversation.client,
        ).order_by("-timestamp")[:10]

    result = []
    for m in reversed(msgs):
        role = "user" if m.direction == "inbound" else "assistant"
        result.append({"role": role, "content": m.content})
    return result


def _format_children(client) -> str:
    children = client.children.all()
    if not children:
        return ""
    parts = []
    for c in children:
        age = (
            f", {c.age_years} years old"
            if hasattr(c, "age_years") and c.age_years
            else ""
        )
        parts.append(f"{c.name}{age}")
    return "; ".join(parts)


def _requires_approval(journey, intent_data: dict) -> bool:
    """
    Determine if AI response needs human review before sending.
    Based on the AI vs Human Control Matrix.
    """
    phase = journey.phase
    step = journey.step
    intent = intent_data.get("intent", "")

    # Payment confirmation always needs human
    if step == "payment_confirmation":
        return True

    # Sales resistance: escalation decisions need human
    if phase == "sales_resistance" and journey.escalation_needed(intent_data):
        return True

    # Booking phase: moderate oversight
    if phase == "booking" and step in ("package_presentation",):
        # Only auto-send for LOW heat — HIGH/MEDIUM needs human check
        return journey.heat_score >= 70

    return False


def _queue_for_approval(
    client, conversation, ai_suggestion, ai_reasoning, heat_score, action
):
    from apps.conversations.models import ApprovalQueue

    ApprovalQueue.objects.create(
        client=client,
        conversation=conversation,
        action=action,
        ai_suggestion=ai_suggestion,
        ai_reasoning=ai_reasoning,
        heat_score_at_suggestion=heat_score,
        expires_at=timezone.now() + timezone.timedelta(hours=48),
    )
    logger.info(
        "Queued for human approval | client=%s action=%s heat=%s",
        client.wa_number,
        action,
        heat_score,
    )


def _map_approval_action(journey, intent_data: dict) -> str:
    from apps.conversations.models import ApprovalAction

    step = journey.step
    if step == "payment_confirmation":
        return ApprovalAction.SEND_MESSAGE
    if journey.phase == "sales_resistance":
        return ApprovalAction.ESCALATE
    return ApprovalAction.SEND_MESSAGE


def _map_heat_signal(signal_name: str) -> str:
    from apps.conversations.models import HeatEvent

    mapping = {
        "reply_speed_immediate": HeatEvent.SignalType.REPLY_SPEED,
        "reply_speed_fast": HeatEvent.SignalType.REPLY_SPEED,
        "reply_speed_same_day": HeatEvent.SignalType.REPLY_SPEED,
        "reply_speed_slow": HeatEvent.SignalType.REPLY_SPEED,
        "reply_speed_very_slow": HeatEvent.SignalType.REPLY_SPEED,
        "length_detailed": HeatEvent.SignalType.MESSAGE_LENGTH,
        "length_moderate": HeatEvent.SignalType.MESSAGE_LENGTH,
        "length_brief": HeatEvent.SignalType.MESSAGE_LENGTH,
        "question_detected": HeatEvent.SignalType.QUESTION_DEPTH,
        "emotional_language": HeatEvent.SignalType.EMOTIONAL_TONE,
        "commitment_signal": HeatEvent.SignalType.ENGAGEMENT_PATTERN,
        "objection_detected": HeatEvent.SignalType.ENGAGEMENT_PATTERN,
    }
    return mapping.get(signal_name, HeatEvent.SignalType.ENGAGEMENT_PATTERN)




def _notify_human_takeover(client, conversation, reason: str):
    """
    Log and optionally notify dashboard that a client needs human handling.
    In future: push notification to studio staff.
    """
    from apps.conversations.models import ApprovalQueue, ApprovalAction

    ApprovalQueue.objects.create(
        client=client,
        conversation=conversation,
        action=ApprovalAction.ESCALATE,
        ai_suggestion="[AI silenced — human takeover required]",
        ai_reasoning=reason,
        heat_score_at_suggestion=getattr(
            getattr(client, "journey_state", None), "heat_score", 50
        ),
        expires_at=timezone.now() + timezone.timedelta(hours=72),
    )
    logger.warning(
        "Human takeover triggered | client=%s reason=%s", client.wa_number, reason
    )
       

