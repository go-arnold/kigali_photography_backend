"""
Instagram AI Orchestrator
==========================
Pure AI conversation system for Instagram DMs.
Follows mandates from services/INSTAGRAM_AI.md.

Differences from WhatsApp:
1. NO BUTTONS. NO QUICK REPLIES. NO INTERACTIVE ELEMENTS.
2. Uses InstagramConversation and InstagramMessage models.
3. Client identified by ig_user_id.
4. Pure AI conversation flow guided by state (JourneyState).
"""

import logging
import json
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
        # Language detection (if not locked)
        if message_text and not client.language_locked:
            detected_lang = detect_language(message_text)
            if detected_lang != client.language:
                client.language = detected_lang
                client.save(update_fields=["language", "updated_at"])

        # History for state detection and context
        recent_msgs = _get_recent_messages(conversation)
        
        # Discovery State Detection (Extract YES/NO from latest user message if in discovery)
        _update_discovery_state(journey, recent_msgs)

        # Calculate packages based on updated discovery state
        package_prices = _calculate_instagram_packages(journey.discovery_state)

        # RAG retrieval
        rag_context = retrieve_context(
            query=message_text or "",
            journey_phase=journey.phase,
            language=client.language
        )

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
        messages = build_messages_context(
            conversation_summary=summary_text,
            recent_messages=recent_msgs[:-1], # Don't include the new message again as build_messages_context appends it
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

            # 10. Update Journey Flow Mode & Step based on AI response
            _update_flow_after_response(journey, ai_response.text)

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
    lang_instruction = {
        "en": "Respond ONLY in English. Never switch languages.",
        "fr": "Réponds UNIQUEMENT en français. Ne change jamais de langue.",
        "rw": "Subiza mu Kinyarwanda GUSA. Ntiuhindure ururimi.",
    }.get(language, "Respond in the language the client uses.")

    discovery_context = _build_discovery_context(discovery_state)

    return f"""You are Julie, the friendly AI assistant for KP Kids Studio,
a children's photography studio in Kigali, Rwanda.

LANGUAGE RULE: {lang_instruction}

YOUR PERSONA:
- Name: Julie
- Warm, professional, helpful, never robotic
- You represent a premium children's photography studio
- Always polite, patient, and encouraging

STUDIO INFORMATION:
- Name: KP Kids Studio (also known as Kigali Photography)
- Location: Kicukiro, BRGD Plaza, opposite IPRC, next to SAWA CITY Supermarket, Kigali
- Hours: Monday–Saturday, 9 AM – 6 PM
- WhatsApp for detailed questions: +250795820170
- Specialty: Children's photoshoots, family sessions, studio and home sessions

PRICING (EXACT — never invent):
Studio packages (base prices, before extras):
  - Starter: 50,000 RWF | 1h | 8 edited photos
  - Silver:  70,000 RWF | 1h | 12 edited photos
  - Gold:    100,000 RWF | 1.5h | 18 edited photos
Home session:
  - Premium: 200,000 RWF | 2h | 30 photos
All packages include ALL unedited photos.
Extras:
  - 2 A5 Frames: +20,000 RWF
  - Birthday Cake: +30,000 RWF
  - Highlight Video (15-30sec): +29,000 RWF
  - Cake + Video bundle: +50,000 RWF (NOT 59,000)
Booking fee: 20,000 RWF via MTN MoMo 798741 (Kigali Photography Ltd)
NO DISCOUNTS UNDER ANY CIRCUMSTANCES.

CURRENT CLIENT STATE:
Client name: {client_name or "valued client"}
Conversation mode: {flow_mode}
{discovery_context}
{f"Current package prices (STRICTLY USE THESE): {current_packages}" if current_packages else ""}

FLOW RULES:
1. If flow_mode is "new" or client just greeted → welcome warmly, offer help options (Booking, Prices, Location, Questions)
2. If client asks about location → give exact address, ask if more help needed
3. If client asks about prices → invite to quick discovery questions (1 min)
   If client refuses discovery → show base packages without extras
4. During discovery → ask ONE question at a time, track answers.
   Questions: 1. Photo type? 2. Studio or Home? 3. Frames? 4. Cake? 5. Video?
5. After all discovery questions answered → calculate exact prices and present EXACTLY 3 packages (Starter, Silver, Gold for studio OR just Premium for home).
6. After packages shown → wait for client to choose or ask questions
7. If client chooses package → ask for preferred date/time
8. If client gives date/time → acknowledge warmly, say a member of the team will confirm.
9. If client asks about discount → refuse politely (max 2 times, then request human takeover)
10. If client asks to add/remove extras after packages shown → recalculate and show again

KNOWLEDGE BASE:
{rag_context if rag_context else "No additional context available."}

RESPONSE STYLE:
- Maximum 3-4 sentences per message unless presenting packages
- No bullet point overload — keep it conversational
- Use emojis sparingly but warmly (😊 📸 🎂 🎉 🙏)
- NEVER use WhatsApp-style button syntax [Button text]
- NEVER say "press 1" or "click here" — pure text conversation
- If you don't know something → apologize and suggest contacting +250795820170
- If confused twice → politely request human takeover

HUMAN TAKEOVER TRIGGERS (you must request human takeover if):
- Client explicitly asks for human agent
- Client gives preferred date/time (availability check needed)
- Client insists on discount more than twice
- Client seems upset or frustrated
- You cannot understand client after 2 attempts
When requesting human takeover, always say a warm goodbye message first.

NEVER:
- Invent prices not listed above
- Promise availability without human confirmation
- Offer discounts
- Switch languages mid-conversation
- Send buttons, numbered menus, or quick replies
- Repeat discovery questions already answered
- Mention WhatsApp buttons or interactive menus
"""

def _extract_yes_no(text: str) -> Optional[bool]:
    """Detect affirmative/negative from any language."""
    text = text.lower().strip()
    
    YES_SIGNALS = [
        "yes", "yeah", "yep", "sure", "ok", "okay", "of course",
        "absolutely", "definitely", "please", "add", "include", "with",
        "oui", "bien sûr", "ok", "d'accord", "ajouter",
        "yego", "nziza", "ndashaka", "ngomba", "twaze",
        "1", "true",
    ]
    NO_SIGNALS = [
        "no", "nope", "not", "without", "skip", "remove", "don't",
        "non", "pas", "sans", "enlever", "retirer",
        "oya", "hoya", "sinjye", "ntashaka", "ntabwo",
        "0", "false",
    ]
    
    for signal in YES_SIGNALS:
        if signal in text: return True
    for signal in NO_SIGNALS:
        if signal in text: return False
    return None

def _build_discovery_context(discovery_state: dict) -> str:
    """Formats the discovery state for the system prompt."""
    if not discovery_state:
        return "Discovery not started yet."
    
    lines = ["Discovery State:"]
    for key, val in discovery_state.items():
        val_str = "Yes" if val is True else ("No" if val is False else (val or "Unknown"))
        lines.append(f"- {key}: {val_str}")
    return "\n".join(lines)

def _update_discovery_state(journey: JourneyState, recent_msgs: list):
    """
    Scans history to detect discovery answers and update JourneyState.
    """
    if not recent_msgs: return
    
    # We only care about the very last user message IF the assistant asked a discovery question
    last_user_msg = next((m for m in reversed(recent_msgs) if m.get("role") == "user"), None)
    if not last_user_msg: return
    
    # Find the assistant question preceding this user message
    user_idx = -1
    for i, m in enumerate(recent_msgs):
        if m == last_user_msg:
            user_idx = i
            break
            
    if user_idx <= 0: return
    
    last_assistant_q = recent_msgs[user_idx - 1]
    if last_assistant_q.get("role") != "assistant": return
    
    q_text = last_assistant_q.get("content", "").lower()
    ans_text = last_user_msg.get("content", "").lower()
    
    ds = journey.discovery_state or {}
    
    # Photo Type
    if "child" in q_text and "family" in q_text:
        if "child" in ans_text: ds["photo_type"] = "child"
        elif "family" in ans_text: ds["photo_type"] = "family"
    
    # Session Type
    if "studio or home" in q_text or "rugo" in q_text:
        if any(w in ans_text for w in ["home", "rugo", "maison", "mu rugo"]):
            ds["session_type"] = "home"
        elif any(w in ans_text for w in ["studio", "i kicukiro", "at the studio"]):
            ds["session_type"] = "studio"
            
    # Yes/No Extras
    val = _extract_yes_no(ans_text)
    if val is not None:
        if "frame" in q_text or "cadre" in q_text: ds["frames"] = val
        if "cake" in q_text or "umutsima" in q_text: ds["cake"] = val
        if "video" in q_text or "videwo" in q_text: ds["video"] = val

    journey.discovery_state = ds
    
    # Auto-advance discovery steps/phase based on ds completeness
    if ds.get("photo_type") and ds.get("session_type"):
        if ds.get("session_type") == "home":
            # Home sessions don't need frames question (usually) but we follow mandates
            pass
        
    journey.save(update_fields=["discovery_state", "updated_at"])

def _calculate_instagram_packages(ds: dict) -> str:
    """Standard pricing engine from services/INSTAGRAM_AI.md."""
    if not ds: return ""
    
    base = {"Starter": 50000, "Silver": 70000, "Gold": 100000}
    extras_cost = 0
    extras_list = []

    if ds.get("frames"):
        extras_cost += 20000
        extras_list.append("2 A5 Photo Frames")
    
    if ds.get("cake") and ds.get("video"):
        extras_cost += 50000
        extras_list.append("Birthday Cake + Highlight Video Bundle")
    elif ds.get("cake"):
        extras_cost += 30000
        extras_list.append("Birthday Cake")
    elif ds.get("video"):
        extras_cost += 29000
        extras_list.append("Highlight Video")

    session_type = ds.get("session_type", "studio")
    if session_type == "home":
        total = 200000 + extras_cost
        result = f"HOME SESSION (Premium Package):\n"
        result += f"- Price: {total:,} RWF\n"
        result += f"- Includes: 30 Edited Photos, All Unedited Photos"
        if extras_list: result += f", {', '.join(extras_list)}"
        return result
    
    # Studio packages
    result = "STUDIO SESSION PACKAGES:\n"
    for name, price in base.items():
        total = price + extras_cost
        photos = 8 if name == "Starter" else (12 if name == "Silver" else 18)
        duration = "1.5h" if name == "Gold" else "1h"
        result += f"- {name}: {total:,} RWF | {duration} | {photos} Edited Photos"
        if extras_list: result += f" | Includes: {', '.join(extras_list)}"
        result += "\n"
    
    return result

def _update_flow_after_response(journey: JourneyState, ai_text: str):
    """Auto-advance flow_mode based on AI response content."""
    text = ai_text.lower()
    
    # Discovery detected
    if "first," in text or "d'abord" in text or "mbere na mbere" in text:
        journey.flow_mode = "discovery"
        journey.step = JourneyStep.ONBOARDING
    
    # Packages shown
    if "starter" in text and "silver" in text and "gold" in text:
        journey.flow_mode = "packages_shown"
        journey.phase = JourneyPhase.BOOKING
        journey.step = JourneyStep.PACKAGE_PRESENTATION
        
    # Chosen package -> awaiting date
    if any(w in text for w in ["what date", "quelle date", "ni ryari"]):
        journey.flow_mode = "awaiting_datetime"
        
    # Human takeover trigger detection in AI text
    if any(w in text for w in ["member of our team", "shortly", "patient", "ihangana"]):
        journey.human_takeover = True
        journey.flow_mode = "human_takeover"
        # Trigger email if date given
        if "checking availability" in text:
            journey.step = JourneyStep.AVAILABILITY_CHECK
            # (In production, we'd trigger the email here)

    journey.save(update_fields=["flow_mode", "phase", "step", "human_takeover", "updated_at"])

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
            "content": text or "[special message]",
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
