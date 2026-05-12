import logging
import json
from django.utils import timezone
from django.conf import settings
from apps.clients.models import Client, JourneyState, JourneyPhase, JourneyStep
from apps.instagram.models import InstagramConversation, InstagramMessage
from services.instagram_service import send_text
from services.openai_service import build_system_prompt, call_openai
from services.rag_service import retrieve_context
from utils.language import detect_language

logger = logging.getLogger(__name__)

INSTAGRAM_WELCOME = """Hello! 😊 Welcome to *KP Kids Studio*.

Please reply with a number to continue:
1️⃣ Book a photoshoot session
2️⃣ View our packages and prices
3️⃣ Ask a question

Reply *1*, *2*, or *3* to get started!"""

def _detect_instagram_intent(text: str) -> str:
    """Map free text to intent for Instagram menu."""
    text = text.lower().strip()
    if any(x in text for x in ["1", "book", "session", "reserve", "kwifotoza"]):
        return "book"
    if any(x in text for x in ["2", "price", "cost", "how much", "ibiciro"]):
        return "prices"  
    if any(x in text for x in ["3", "question", "ask", "help", "info"]):
        return "question"
    return "unknown"

def handle_instagram_message(sender_id, message_text, message_id, timestamp_ms):
    """
    Main pipeline for Instagram messages.
    """
    try:
        # 1. Look up or create Client
        client, is_new = Client.objects.get_or_create(
            ig_user_id=sender_id,
            defaults={
                "wa_number": f"ig_{sender_id}"[:20], # Prefix to avoid unique constraint clash
                "name": f"IG User {sender_id[:8]}",
            }
        )
        
        # 2. Ensure JourneyState exists
        journey, _ = JourneyState.objects.get_or_create(client=client)
        
        # 3. Get or create InstagramConversation
        # For simplicity, we keep one active conversation or create daily
        conversation = InstagramConversation.objects.filter(client=client, is_open=True).first()
        if not conversation:
            conversation = InstagramConversation.objects.create(client=client)
            
        # 4. Save inbound message
        InstagramMessage.objects.get_or_create(
            ig_mid=message_id,
            defaults={
                "conversation": conversation,
                "client": client,
                "direction": "inbound",
                "content": message_text,
                "timestamp": timezone.now(),
            }
        )
        
        # 5. Human takeover check
        if journey.human_takeover:
            logger.info("Human takeover active for IG client %s", sender_id)
            return

        # 6. Intent Detection for Menu
        intent = _detect_instagram_intent(message_text)
        
        # 7. AI Pipeline
        # Language detection
        lang = detect_language(message_text) if message_text else "en"
        if is_new and not message_text:
            # First time, send welcome
            send_text(sender_id, INSTAGRAM_WELCOME)
            _save_outbound(client, conversation, INSTAGRAM_WELCOME)
            return

        # RAG retrieval
        rag_context = retrieve_context(query=message_text, journey_phase=journey.phase, language=lang)
        
        # Build system prompt (REUSE)
        system_prompt = build_system_prompt(
            journey_phase=journey.phase,
            journey_step=journey.step,
            heat_label=journey.heat_label,
            language=lang,
            client_name=client.name,
            children_info="", # Can extend later
            rag_context=rag_context,
            flow_mode=intent if intent != "unknown" else "question"
        )
        
        # Call OpenAI (REUSE)
        # We need to format history
        recent_msgs = InstagramMessage.objects.filter(conversation=conversation).order_by("-timestamp")[:10]
        history = []
        for m in reversed(recent_msgs):
            role = "user" if m.direction == "inbound" else "assistant"
            history.append({"role": role, "content": m.content})
            
        # If history is empty (first message was saved above but maybe we want to exclude it from 'messages' param)
        # OpenAI service call_openai takes messages list
        ai_response = call_openai(system_prompt=system_prompt, messages=history)
        
        if ai_response.ok:
            # 8. Save outbound message
            _save_outbound(client, conversation, ai_response.text)
            
            # 9. Send via Instagram
            send_text(sender_id, ai_response.text)
            
            # Update last contact
            client.update_last_contact()
            
    except Exception as e:
        logger.exception("Error in handle_instagram_message: %s", e)

def _save_outbound(client, conversation, text):
    import uuid
    InstagramMessage.objects.create(
        ig_mid=f"out_{uuid.uuid4().hex[:12]}",
        conversation=conversation,
        client=client,
        direction="outbound",
        content=text,
        timestamp=timezone.now(),
    )
