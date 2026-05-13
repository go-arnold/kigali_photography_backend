"""
Instagram AI Orchestrator
==========================
Pure AI conversation system for Instagram DMs.
Follows mandates from services/INSTAGRAM_AI.md and GEMINI.md.

KP Kids Studio | Kigali, Rwanda
"""

import logging
import uuid
from typing import Optional
from django.utils import timezone
from django.conf import settings

from apps.clients.models import Client, JourneyState, JourneyPhase, JourneyStep
from apps.instagram.models import InstagramConversation, InstagramMessage
from services.instagram_service import send_text, send_image, mark_as_seen
from services.openai_service import call_openai, build_messages_context
from services.rag_service import retrieve_context
from utils.language import detect_language

logger = logging.getLogger(__name__)

def handle_instagram_message(sender_id: str, message_text: str, message_id: str, timestamp_ms: int):
    """
    Main entry point for Instagram inbound messages.
    Pure AI flow with state management.
    """
    try:
        # 1. Onboard / Get Client
        from services.client_service import onboard_client
        # Use ig_ prefix for wa_number to avoid conflicts with real WhatsApp numbers
        client, journey, _, is_new = onboard_client(
            wa_number=f"ig_{sender_id}"[:20],
            name=f"IG User {sender_id[:8]}",
            ig_user_id=sender_id
        )

        # 1.1 Fetch Real Instagram Name if placeholder
        if client.name.startswith("IG User"):
            try:
                from services.instagram_service import get_user_profile
                profile = get_user_profile(sender_id)
                if profile and profile.get("name"):
                    client.name = profile["name"]
                    client.save(update_fields=["name", "updated_at"])
                    logger.info("Updated IG client name: %s -> %s", sender_id, client.name)
            except Exception as e:
                logger.warning("Failed to fetch IG profile for %s: %s", sender_id, e)

        # 2. Get/Create Instagram Conversation
        conversation = _get_or_create_conversation(client)

        # 3. Save Inbound Message
        _save_inbound(
            client=client,
            conversation=conversation,
            mid=message_id,
            text=message_text
        )

        # 4. Human Takeover Check
        if journey.human_takeover:
            logger.info("Human takeover active for IG client %s — AI silenced", sender_id)
            conversation.touch()
            return

        # 5. Mark as seen
        try:
            mark_as_seen(sender_id)
        except Exception:
            pass

        # 6. AI Pipeline
        # Language detection — lock on first meaningful message
        if message_text and len(message_text.strip()) > 3 and not client.language_locked:
            try:
                detected = detect_language(message_text)
            except Exception:
                detected = "en"
            client.language = detected
            client.language_locked = True
            client.save(update_fields=["language", "language_locked", "updated_at"])

        # History for context
        recent_msgs = _get_recent_messages(conversation)
        
        # Discovery State Extraction (AI handles this usually, but we help it)
        # We don't surgically update discovery_state here to let AI be more flexible,
        # but we do keep track of what has been answered in the prompt.

        # RAG retrieval
        rag_context = retrieve_context(
            query=message_text or "",
            journey_phase=journey.phase,
            language=client.language
        )

        # Package calculation for the prompt
        package_prices = _calculate_instagram_packages(journey.discovery_state)

        # Build SPECIAL Instagram System Prompt
        system_prompt = build_instagram_system_prompt(
            language=client.language,
            client_name=client.name,
            flow_mode=journey.flow_mode or "new",
            discovery_state=journey.discovery_state,
            rag_context=rag_context,
            current_packages=package_prices
        )

        # Build message context
        summary_text = getattr(conversation.summary, 'summary_text', None) if hasattr(conversation, 'summary') else None
        # We need to exclude the current message from history because build_messages_context adds it
        history = recent_msgs[:-1] if len(recent_msgs) > 0 else []
        
        messages = build_messages_context(
            conversation_summary=summary_text,
            recent_messages=history,
            new_message=message_text or "[image/special message]"
        )

        # Call OpenAI
        ai_response = call_openai(
            system_prompt=system_prompt,
            messages=messages,
            escalate=(journey.phase == JourneyPhase.SALES_RESISTANCE and journey.heat_score >= 40)
        )

        if ai_response.ok:
            # 7. Record Tokens
            from services.client_service import record_tokens
            record_tokens(client, ai_response.total_tokens)
            logger.info("IG AI Usage | client=%s in=%s out=%s", sender_id, ai_response.input_tokens, ai_response.output_tokens)

            # 8. Save Outbound Message
            _save_outbound(
                client=client,
                conversation=conversation,
                text=ai_response.text,
                model=ai_response.model,
                tokens_input=ai_response.input_tokens,
                tokens_output=ai_response.output_tokens
            )

            # 9. Send response via Instagram
            send_text(sender_id, ai_response.text)

            # 10. Update Journey Flow & State based on AI response
            # This is where we detect if discovery completed or if human takeover is needed
            _post_process_ai_response(journey, ai_response.text, message_text)

        conversation.touch()
        client.update_last_contact()

    except Exception as e:
        logger.exception("Error in handle_instagram_message: %s", e)

def build_instagram_system_prompt(
    language: str,
    client_name: str,
    flow_mode: str,
    discovery_state: dict,
    rag_context: str,
    current_packages: str = "",
) -> str:
    """
    Builds the specialized Instagram AI system prompt as mandated by INSTAGRAM_AI.md.
    """
    # Stickiness rule: Respond in the detected language only.
    lang_instruction = {
        "en": "Respond ONLY in English. Never switch languages. If the user mixes languages, reply in English only.",
        "fr": "Réponds UNIQUEMENT en français. Ne change jamais de langue. Si l'utilisateur mélange les langues, réponds en français uniquement.",
        "rw": "Subiza mu Kinyarwanda GUSA. Ntiuhindure ururimi. Niba umukiliya avanze indimi, subiza mu Kinyarwanda gusa.",
    }.get(language, "Respond in the language the client uses.")

    discovery_context = _build_discovery_context(discovery_state)

    return f"""You are Julie, the friendly AI assistant for KP Kids Studio,
a children's photography studio in Kigali, Rwanda.

LANGUAGE RULE: {lang_instruction}

YOUR PERSONA:
- Name: Julie
- Warm, professional, helpful, never robotic.
- You represent a premium children's photography studio.
- Always polite, patient, and encouraging.
- Use emojis sparingly but warmly (😊 📸 🎂 🎉 🙏).

STUDIO INFORMATION:
- Name: KP Kids Studio (also known as Kigali Photography)
- Location: Kicukiro, BRGD Plaza, opposite IPRC, next to SAWA CITY Supermarket, Kigali.
- Hours: Monday–Saturday, 9 AM – 6 PM.
- WhatsApp for detailed questions: +250795820170.
- Specialty: Children's photoshoots, family sessions, studio and home sessions.

PRICING (EXACT — NEVER INVENT):
Studio packages (Base prices):
  - Starter: 50,000 RWF | 1h | 8 edited photos
  - Silver:  70,000 RWF | 1h | 12 edited photos
  - Gold:    100,000 RWF | 1.5h | 18 edited photos
Home session (Fixed price):
  - Premium: 200,000 RWF | 2h | 30 photos
All packages include all unedited photos.
Extras:
  - 2 A5 Frames: +20,000 RWF
  - Birthday Cake: +30,000 RWF
  - Highlight Video (15-30sec): +29,000 RWF
  - Cake + Video bundle: +50,000 RWF (Special bundle price)
Booking fee: 20,000 RWF via MTN MoMo 798741 (Kigali Photography Ltd).
NO DISCOUNTS UNDER ANY CIRCUMSTANCES.

CURRENT CLIENT STATE:
Client name: {client_name or "valued client"}
Conversation mode: {flow_mode}
{discovery_context}
{f"Current package prices (STRICTLY USE THESE): {current_packages}" if current_packages else ""}

FLOW RULES:
1. GREETING: Welcome warmly, offer options (Booking, Prices, Location, Questions).
2. PRICES: Invite to a quick discovery (1 min) to calculate their exact package.
3. DISCOVERY: Ask ONE question at a time. Track answers for:
   - Photo type (Child or Family?)
   - Session type (Studio or Home?)
   - Frames (Would you like 2 A5 frames?)
   - Cake (Would you like a birthday cake included?)
   - Video (Would you like a highlight video?)
4. PRESENTATION: After all discovery info is known, present the EXACT packages.
   - For Studio: Show Starter, Silver, Gold with their totals (Base + Extras).
   - For Home: Show the Premium package with its total.
5. BOOKING: If they choose a package, ask for their preferred date and time.
6. HANDOVER: Once they give a date/time, tell them a team member will confirm availability shortly.
7. OBJECTIONS: If they ask for a discount, politely refuse. Max 2 refusals before handover.

CONSTRAINTS:
- NO MARKDOWN: Instagram does not support **bold**, *italic*, or bullet points. Use plain text.
- NO BUTTONS: Never use WhatsApp button syntax like [Button text].
- NO NUMBERED MENUS: Do not say "Reply 1 for X". Keep it natural.
- MAX 3-4 SENTENCES: Keep messages concise and easy to read.

KNOWLEDGE BASE:
{rag_context if rag_context else "No additional context available."}

HUMAN TAKEOVER TRIGGERS:
- Client asks for a real person.
- Client provides a preferred date/time (needs availability check).
- Client insists on a discount after 2 refusals.
- Client seems angry or frustrated.
- You are confused and cannot help after 2 attempts.
Always say a warm goodbye before handing over to a human.

NEVER:
- Invent prices.
- Promise availability (say 'we will check').
- Offer discounts.
- Switch languages mid-conversation.
- Send buttons or interactive elements.
"""

def _extract_yes_no(text: str) -> Optional[bool]:
    """Detect affirmative/negative from any language."""
    text = text.lower().strip()
    YES_SIGNALS = ["yes", "yeah", "yep", "sure", "ok", "okay", "oui", "d'accord", "yego", "ndabishaka", "ni byiza"]
    NO_SIGNALS = ["no", "nope", "not", "non", "pas", "oya", "hoya", "sinshaka"]
    
    for s in YES_SIGNALS:
        if s in text: return True
    for s in NO_SIGNALS:
        if s in text: return False
    return None

def _calculate_instagram_packages(ds: dict) -> str:
    """Pricing engine matching services/INSTAGRAM_AI.md."""
    if not ds or "session_type" not in ds:
        return ""
    
    extras_cost = 0
    extras_list = []
    if ds.get("frames"):
        extras_cost += 20000
        extras_list.append("2 A5 Frames")
    if ds.get("cake") and ds.get("video"):
        extras_cost += 50000
        extras_list.append("Cake + Video Bundle")
    elif ds.get("cake"):
        extras_cost += 30000
        extras_list.append("Birthday Cake")
    elif ds.get("video"):
        extras_cost += 29000
        extras_list.append("Highlight Video")

    session_type = ds.get("session_type", "studio")
    if session_type == "home":
        total = 200000 + extras_cost
        return f"PREMIUM HOME PACKAGE: {total:,} RWF (includes all extras chosen)"
    
    base = {"Starter": 50000, "Silver": 70000, "Gold": 100000}
    lines = []
    for name, price in base.items():
        total = price + extras_cost
        lines.append(f"{name}: {total:,} RWF")
    return " | ".join(lines)

def _build_discovery_context(ds: dict) -> str:
    if not ds: return "Discovery: Not started."
    summary = []
    for k, v in ds.items():
        val = "Yes" if v is True else ("No" if v is False else v)
        summary.append(f"{k}: {val}")
    return "Discovery State: " + ", ".join(summary)

def _post_process_ai_response(journey: JourneyState, ai_text: str, user_text: str):
    """
    Updates JourneyState based on what Julie said and what the user said.
    """
    ai_text_lower = ai_text.lower()
    user_text_lower = user_text.lower()
    
    # 1. Update Discovery State (Heuristics to help the prompt)
    ds = journey.discovery_state or {}
    
    # Simple extraction for mandatory fields
    if "home" in user_text_lower or "rugo" in user_text_lower:
        ds["session_type"] = "home"
    elif "studio" in user_text_lower or "i kicukiro" in user_text_lower:
        ds["session_type"] = "studio"
        
    if "family" in user_text_lower:
        ds["photo_type"] = "family"
    elif "child" in user_text_lower:
        ds["photo_type"] = "child"

    # Extras detection based on Julie's questions
    val = _extract_yes_no(user_text_lower)
    if val is not None:
        # We look at history to see what was asked
        # For simplicity in this orchestrator, we rely on AI to track state, 
        # but we can also look at Julie's last message if needed.
        pass

    journey.discovery_state = ds

    # 2. Detect Flow Transitions
    if "starter" in ai_text_lower and "silver" in ai_text_lower:
        journey.flow_mode = "packages_shown"
        journey.phase = JourneyPhase.BOOKING
        journey.step = JourneyStep.PACKAGE_PRESENTATION
    
    if "date" in ai_text_lower or "time" in ai_text_lower or "ryari" in ai_text_lower:
        journey.flow_mode = "awaiting_datetime"

    # 3. Human Takeover Detection
    # If client gives a date/time, Julie will say "team member will confirm"
    # We trigger takeover here.
    TAKEOVER_PHRASES = ["team member", "agent", "confirm availability", "shortly", "patient"]
    if any(p in ai_text_lower for p in TAKEOVER_PHRASES):
        journey.human_takeover = True
        journey.takeover_reason = "Date/Time provided - availability check needed"
        journey.flow_mode = "human_takeover"
        
        # Trigger push notification
        try:
            from apps.dashboard.views import send_push_notification
            send_push_notification(
                title=f"📸 New Booking Inquiry — {journey.client.name}",
                body=f"Client provided date/time on Instagram: {user_text[:50]}...",
                url=f"/?client={journey.client.pk}"
            )
        except Exception:
            pass

    journey.save(update_fields=["discovery_state", "flow_mode", "phase", "step", "human_takeover", "takeover_reason", "updated_at"])
    
    # 4. Queue for Approval if needed
    if journey.human_takeover:
        _queue_for_approval(
            client=journey.client,
            conversation=InstagramConversation.objects.filter(client=journey.client, is_open=True).first(),
            ai_suggestion=ai_text,
            ai_reasoning=journey.takeover_reason,
            heat_score=journey.heat_score,
            action="escalate"
        )

def _queue_for_approval(client, conversation, ai_suggestion, ai_reasoning, heat_score, action):
    from apps.instagram.models import InstagramApprovalQueue
    
    InstagramApprovalQueue.objects.get_or_create(
        client=client,
        conversation=conversation,
        status="pending",
        defaults={
            "action": action,
            "ai_suggestion": ai_suggestion,
            "ai_reasoning": ai_reasoning,
            "heat_score_at_suggestion": heat_score,
            "expires_at": timezone.now() + timezone.timedelta(hours=48),
        }
    )
    logger.info("Queued IG approval | client=%s action=%s", client.ig_user_id, action)

def _get_or_create_conversation(client) -> InstagramConversation:
    conv = InstagramConversation.objects.filter(client=client, is_open=True).first()
    if not conv:
        conv = InstagramConversation.objects.create(client=client)
    return conv

def _save_inbound(client, conversation, mid, text):
    msg, _ = InstagramMessage.objects.get_or_create(
        ig_mid=mid,
        defaults={
            "conversation": conversation,
            "client": client,
            "direction": "inbound",
            "content": text or "[image/special]",
            "timestamp": timezone.now(),
        }
    )
    return msg

def _save_outbound(client, conversation, text, model="", tokens_input=0, tokens_output=0):
    return InstagramMessage.objects.create(
        ig_mid=f"out_{uuid.uuid4().hex[:12]}",
        conversation=conversation,
        client=client,
        direction="outbound",
        content=text,
        model_used=model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        timestamp=timezone.now(),
    )

def _get_recent_messages(conversation) -> list:
    msgs = InstagramMessage.objects.filter(conversation=conversation).order_by("-timestamp")[:15]
    result = []
    for m in reversed(msgs):
        role = "user" if m.direction == "inbound" else "assistant"
        result.append({"role": role, "content": m.content})
    return result
