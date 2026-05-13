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
        # Language detection logic: update only if not locked
        if message_text and len(message_text.strip()) > 3:
            detected = detect_language(message_text)
            # Logic: If client mixes languages with Kinyarwanda, lock to Kinyarwanda.
            # Otherwise lock to detected.
            if "rw" in detected or "kin" in detected:
                client.language = "rw"
            else:
                client.language = detected
            
            client.language_locked = True
            client.save(update_fields=["language", "language_locked", "updated_at"])

        # History for context
        recent_msgs = _get_recent_messages(conversation)
        
        # Discovery State Extraction
        _update_discovery_state(journey, message_text)

        # RAG retrieval
        rag_context = retrieve_context(
            query=message_text or "",
            journey_phase=journey.phase,
            language=client.language
        )

        # Package calculation for the prompt (STRICTLY for AI use in presenting)
        package_info = _calculate_instagram_packages(journey.discovery_state)

        # Build SPECIAL Instagram System Prompt
        system_prompt = build_instagram_system_prompt(
            language=client.language,
            client_name=client.name,
            flow_mode=journey.flow_mode or "new",
            discovery_state=journey.discovery_state,
            rag_context=rag_context,
            package_info=package_info
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
            record_tokens(
                client=client, 
                conversation=conversation, 
                input_tokens=ai_response.input_tokens, 
                output_tokens=ai_response.output_tokens
            )

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
    package_info: dict,
) -> str:
    """
    Builds the specialized Instagram AI system prompt as mandated by INSTAGRAM_AI.md.
    """
    lang_instruction = {
        "en": "Respond ONLY in English. Never switch languages.",
        "fr": "Répondez UNIQUEMENT en français. Ne changez jamais de langue.",
        "rw": "Subiza mu Kinyarwanda GUSA. Match the client's mix of languages but prioritize Kinyarwanda.",
    }.get(language, "Respond in the language the client uses.")

    discovery_context = _build_discovery_context(discovery_state)
    is_discovery_complete = _check_discovery_complete(discovery_state)

    return f"""You are Julie, the friendly AI assistant for KP Kids Studio,
a children's photography studio in Kigali, Rwanda.

LANGUAGE RULE: {lang_instruction}

YOUR PERSONA:
- Warm, professional, helpful. Use emojis warmly (😊 📸 🎂).
- NO MARKDOWN: Never use **bold**, *italic*, or bullet points.
- NO BUTTONS: Never use [Button] syntax.

STUDIO INFO:
- Location: Kicukiro, BRGD Plaza, opposite IPRC, Kigali.
- Hours: Mon-Sat, 9AM-6PM.
- WhatsApp: +250795820170.

PRICING RULES (STRICT):
- We NEVER sell single pictures. We only offer packages.
- If asked for price of 1 pic: "We don't provide pricing for a single picture, but we have great packages! Let me ask you a few quick questions (takes <2 min) so I can build a personalized package for you."
- Studio Base: Starter (50k), Silver (70k), Gold (100k).
- Home Base: Premium (200k).
- Extras: 2 A5 Frames (+20k), Cake (+30k), Video (+29k), Bundle (+50k).
- All packages INCLUDE ALL UNEDITED PHOTOS.

DISCOVERY FLOW (MANDATORY ORDER):
1. Session Type (Studio or Home?)
2. Photo Type (Child or Family?)
3. Frames (Would you like 2 A5 frames?)
4. Cake (Would you like a birthday cake included?)
5. Video (Would you like a highlight video?)

CURRENT STATE:
Client: {client_name or "valued client"}
{discovery_context}

RULES FOR DISCOVERY:
- Ask ONE question at a time.
- Move to next question ONLY AFTER current one is answered (accepted/rejected).
- NEVER present packages until ALL 5 questions are answered.

PACKAGES PRESENTATION (ONLY IF DISCOVERY COMPLETE):
{f"Format to use exactly: {package_info['text']}" if is_discovery_complete else "DO NOT SHOW PACKAGES YET. Complete discovery first."}
- Mention: "All other unedited pictures are included."

BOOKING:
- Once client chooses a package, ask for preferred date/time.
- After they give a date: "Thank you! I've noted that. Our agent will check availability and get back to you shortly to confirm."
- STOP after this. A human will take over.

KNOWLEDGE BASE:
{rag_context}
"""

def _check_discovery_complete(ds: dict) -> bool:
    required = ["session_type", "photo_type", "frames", "cake", "video"]
    return all(k in ds for k in required)

def _update_discovery_state(journey: JourneyState, text: str):
    """Surgical updates to discovery state based on user input."""
    ds = journey.discovery_state or {}
    text = text.lower().strip()
    
    # Logic for Session Type
    if "home" in text or "rugo" in text: ds["session_type"] = "home"
    elif "studio" in text: ds["session_type"] = "studio"
    
    # Logic for Photo Type
    if "family" in text or "muryango" in text: ds["photo_type"] = "family"
    elif "child" in text or "umwana" in text: ds["photo_type"] = "child"
    
    # Logic for Extras (Yes/No)
    # This is tricky because we need to know what was asked. 
    # AI handles the "yes/no" mapping better in prompt, 
    # but we look for strong signals here to help.
    
    journey.discovery_state = ds
    journey.save(update_fields=["discovery_state", "updated_at"])

def _calculate_instagram_packages(ds: dict) -> dict:
    """Pricing engine matching Instagram_ai.md format."""
    if not ds: return {"text": ""}
    
    extras_cost = 0
    if ds.get("frames") is True: extras_cost += 20000
    if ds.get("cake") is True and ds.get("video") is True:
        extras_cost += 50000
    elif ds.get("cake") is True: extras_cost += 30000
    elif ds.get("video") is True: extras_cost += 29000

    session_type = ds.get("session_type", "studio")
    if session_type == "home":
        total = 200000 + extras_cost
        return {"text": f"PREMIUM HOME PACKAGE: {total:,} RWF"}
    
    base = {"Starter": 50000, "Silver": 70000, "Gold": 100000}
    lines = []
    for name, price in base.items():
        total = price + extras_cost
        lines.append(f"{name}: {total:,} RWF")
    
    return {"text": " | ".join(lines)}

def _build_discovery_context(ds: dict) -> str:
    if not ds: return "Discovery: Not started."
    steps = []
    for k in ["session_type", "photo_type", "frames", "cake", "video"]:
        v = ds.get(k)
        if v is None: val = "Pending"
        else: val = "Yes" if v is True else ("No" if v is False else v)
        steps.append(f"{k}: {val}")
    return "Discovery Progress: " + ", ".join(steps)

def _post_process_ai_response(journey: JourneyState, ai_text: str, user_text: str):
    ai_text_lower = ai_text.lower()
    
    # Update flow mode based on AI content
    if "starter" in ai_text_lower and "silver" in ai_text_lower:
        journey.flow_mode = "packages_shown"
    
    # Human Takeover Trigger: Date provided
    # Julie says: "Our agent will check availability"
    TAKEOVER_PHRASES = ["agent will check availability", "shortly to confirm", "agent azagusubiza"]
    if any(p in ai_text_lower for p in TAKEOVER_PHRASES):
        journey.human_takeover = True
        journey.takeover_reason = "Date provided - awaiting confirmation"
        
        # Approval Queue
        _queue_for_approval(
            client=journey.client,
            conversation=InstagramConversation.objects.filter(client=journey.client, is_open=True).first(),
            ai_suggestion=ai_text,
            ai_reasoning="Client provided date/time on Instagram",
            heat_score=journey.heat_score,
            action="escalate"
        )
        
        # Push notification
        try:
            from apps.dashboard.views import send_push_notification
            send_push_notification(
                title=f"📸 IG Booking — {journey.client.name}",
                body=f"Client provided date on Instagram: {user_text[:50]}",
                url=f"/?client={journey.client.pk}"
            )
        except Exception:
            pass

    journey.save(update_fields=["human_takeover", "takeover_reason", "flow_mode", "updated_at"])

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
