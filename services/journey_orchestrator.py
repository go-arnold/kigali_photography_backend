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
from services.button_flow import handle_button_click, send_welcome #CITO BUTTONS

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

        # # Step 2: Onboard client
        # from services.client_service import onboard_client

        # client, journey, conversation, is_new = onboard_client(
        #     wa_number=from_number,
        #     name=from_name,
        # )
        # from django.utils import timezone as tz
        # last_conv = client.conversations.order_by("-started_at").first()
        # if last_conv:
        #     days_since = (tz.now() - last_conv.started_at).days
        #     if days_since > 30 and flow_mode not in ("", None):
        #         journey.flow_mode = ""
        #         journey.save(update_fields=["flow_mode", "updated_at"])
        #         flow_mode = ""

        # Step 2: Onboard client
        from services.client_service import onboard_client

        client, journey, conversation, is_new = onboard_client(
            wa_number=from_number,
            name=from_name,
        )

        # ── BRANCHEMENT BOUTONS ──────────────────────────────────────────────────────
        if msg_type == "interactive" and interactive_id:
            # ← SAUVEGARDER le clic bouton comme message inbound
            _save_inbound(
                client=client,
                conversation=conversation,
                message_id=message_id,
                text=text or f"[button: {interactive_id}]",
                msg_type=msg_type,
            )
            action = handle_button_click(
                interactive_id=interactive_id,
                from_number=from_number,
                journey=journey,
                client=client,
            )
            conversation.touch()
            logger.info("Button handled | client=%s button=%s action=%s",
                        from_number, interactive_id, action)
            return OrchestratorResult(
                success=True,
                action="sent",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
                tokens_used=0,
            )

        # ── HUMAN TAKEOVER EARLY CHECK ───────────────────────────────────────────────
        if journey.human_takeover:
            logger.info("Human takeover active for %s — AI silenced (early check)", client.wa_number)
            _save_inbound(
                client=client,
                conversation=conversation,
                message_id=message_id,
                text=text or f"[{msg_type}]",
                msg_type=msg_type,
            )
            conversation.touch()
            return OrchestratorResult(
                success=True,
                action="human_takeover",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
            )

        # ── ROUTING TEXTE LIBRE ───────────────────────────────────────────────────────
        #flow_mode = getattr(journey, "flow_mode", "") or ""
        flow_mode = getattr(journey, "flow_mode", None) or ""

        if flow_mode == "question" and text:
            # Mode question → pipeline IA directement, skip tout le reste
            pass  # continue vers Step 3

        elif not flow_mode:
            # Toujours envoyer le welcome + choix de langue au premier contact
            send_welcome(from_number, client = client)
            _set_flow_mode_on_journey(journey, "welcome_sent")
            # Sauvegarder le message inbound avant de partir
            _save_inbound(
                client=client,
                conversation=conversation,
                message_id=message_id,
                text=text or f"[{msg_type}]",
                msg_type=msg_type,
            )
            conversation.touch()
            return OrchestratorResult(
                success=True,
                action="sent",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
                tokens_used=0,
            )


        elif flow_mode == "welcome_sent":
            from services.button_flow import _send_main_menu
            from utils.language import detect_language
            from services.whatsapp import send_text as _send_text, send_buttons as _send_buttons
            _save_inbound(
                client=client,
                conversation=conversation,
                message_id=message_id,
                text=text or f"[{msg_type}]",
                msg_type=msg_type,
            )

            if text and msg_type == "text":
                
                # Si la langue est déjà verrouillée (bouton cliqué) → renvoyer le menu principal
                if getattr(client, "language_locked", False):
                    _send_main_menu(to=from_number, lang=client.language)
                    conversation.touch()
                    return OrchestratorResult(
                        success=True, action="sent",
                        client_id=str(client.pk), conversation_id=conversation.pk,
                    )

                # Langue pas encore choisie → détecter + répondre + renvoyer langue
                detected_lang = detect_language(text)

                GREETING_WORDS = {
                    "hello", "hi", "hey", "bonjour", "bonsoir", "muraho",
                    "mwaramutse", "mwiriwe", "salut", "good morning",
                    "good afternoon", "good evening", "👋", "🙏"
                }
                is_greeting = (
                    text.lower().strip().rstrip("!") in GREETING_WORDS or
                    len(text.split()) <= 2
                )

                if not is_greeting:
                    from services.openai_service import build_system_prompt, build_messages_context, call_openai
                    from services.rag_service import retrieve_context

                    rag_context = retrieve_context(query=text, journey_phase="entry", language=detected_lang)
                    system_prompt = build_system_prompt(
                        journey_phase=journey.phase,
                        journey_step=journey.step,
                        heat_label=journey.heat_label,
                        language=detected_lang,
                        client_name=client.name or from_number,
                        children_info="",
                        rag_context=rag_context,
                        flow_mode="question",
                    )
                    response = call_openai(
                        system_prompt=system_prompt,
                        messages=[{"role": "user", "content": text}],
                    )
                    if response.ok:
                        _send_text(to=from_number, message=response.text)

                # Renvoyer SEULEMENT les boutons de langue (pas encore choisi)
                _send_buttons(
                    to=from_number,
                    body="Please select your language to continue / Hitamo ururimi / Choisissez votre langue:",
                    buttons=[
                        {"id": "lang_en", "title": "🇬🇧 English"},
                        {"id": "lang_rw", "title": "🇷🇼 Kinyarwanda"},
                        {"id": "lang_fr", "title": "🇫🇷 Français"},
                    ],
                )

            conversation.touch()
            return OrchestratorResult(
                success=True, action="sent",
                client_id=str(client.pk), conversation_id=conversation.pk,
            )
        
        elif flow_mode == "menu_shown" and text:
            # Client tape du texte après avoir choisi la langue mais sans cliquer un bouton menu
            # → répondre en mode question + renvoyer le menu dans sa langue
            from services.button_flow import _send_main_menu
            from services.openai_service import build_system_prompt, build_messages_context, call_openai
            from services.rag_service import retrieve_context
            from services.whatsapp import send_text as _send_text

            _save_inbound(
                client=client, conversation=conversation,
                message_id=message_id, text=text, msg_type=msg_type,
            )

            rag_context = retrieve_context(query=text, journey_phase="entry", language=client.language)
            system_prompt = build_system_prompt(
                journey_phase=journey.phase,
                journey_step=journey.step,
                heat_label=journey.heat_label,
                language=client.language,
                client_name=client.name or from_number,
                children_info="",
                rag_context=rag_context,
                flow_mode="question",
            )
            response = call_openai(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": text}],
            )
            if response.ok:
                _send_text(to=from_number, message=response.text)
                # Bouton Talk to Agent
                lang = client.language or "en"
                from services.whatsapp import send_buttons as _send_buttons
                agent_titles = {"en": "🧑 Talk to Agent", "rw": "🧑 Vugana n'Umukozi", "fr": "🧑 Parler à un Agent"}
                _send_buttons(
                    to=from_number,
                    body={"en": "Still need help?", "rw": "Ukeneye ubufasha?", "fr": "Besoin d'aide?"}.get(lang, "Still need help?"),
                    buttons=[{"id": "btn_agent", "title": agent_titles.get(lang, agent_titles["en"])}],
                )

            # Renvoyer le menu principal (pas les boutons de langue)
            _send_main_menu(to=from_number, lang=client.language)
            conversation.touch()
            return OrchestratorResult(
                success=True, action="sent",
                client_id=str(client.pk), conversation_id=conversation.pk,
            )

        elif flow_mode == "awaiting_datetime" and text and msg_type != "interactive":
            # Client répond avec sa date/heure préférée → human takeover
            from services.button_flow import handle_datetime_response
            handle_datetime_response(
                text=text,
                from_number=from_number,
                journey=journey,
                client=client,
                conversation=conversation,
            )
            conversation.touch()
            return OrchestratorResult(
                success=True,
                action="human_takeover",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
                tokens_used=0,
            )

        elif flow_mode in ("booking", "prices") and text:
            # Texte pendant discovery → répondre + renvoyer boutons
            from services.button_flow import handle_text_during_discovery
            handle_text_during_discovery(
                text=text,
                from_number=from_number,
                journey=journey,
                client=client,
                conversation=conversation,
            )
            conversation.touch()
            return OrchestratorResult(
                success=True,
                action="sent",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
                tokens_used=0,
            )
        elif flow_mode == "awaiting_payment" and msg_type != "interactive":
            # Client tape du texte pendant qu'il attend de payer
            # Les boutons btn_paid / btn_agent gèrent tout → on ne répond pas
            _save_inbound(
                client=client,
                conversation=conversation,
                message_id=message_id,
                text=text or f"[{msg_type}]",
                msg_type=msg_type,
            )
            conversation.touch()
            return OrchestratorResult(
                success=True,
                action="human_takeover",
                client_id=str(client.pk),
                conversation_id=conversation.pk,
                tokens_used=0,
            )

        elif flow_mode not in ("question",) and text and flow_mode != "":
            # flow_mode inconnu mais pas vide → renvoyer le menu par sécurité
            # (ex: flow_mode = "payment_confirmation" et client tape du texte)
            pass  # laisser le pipeline IA gérer

        # ── FIN ROUTING ───────────────────────────────────────────────────────────────
        # ── FIN BRANCHEMENT BOUTONS ──────────────────────────────────────────────────

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

       
        # Step 6: Language detection — NE PAS changer la langue en mode question
        # pour éviter de déclencher le human takeover Kinyarwanda
        if text and flow_mode != "question":
            _update_language(client, text)

        # Step 6b: Kinyarwanda → human takeover (seulement hors mode question)
        if flow_mode != "question":
            text_words = text.strip().lower().split() if text else []
            SHORT_SAFE_WORDS = {
                "ok", "yes", "no", "silver", "gold", "starter",
                "studio", "home", "package"
            }
            is_short_safe = (
                len(text_words) <= 3
                and all(w in SHORT_SAFE_WORDS for w in text_words)
            )
            if (
                client.language not in ["en", "unknown"]
                and not is_short_safe
                and not journey.human_takeover
            ):
                journey.flag_human_takeover("Client writes in Kinyarwanda — human agent required")
                _notify_human_takeover(
                    client, conversation,
                    reason="Kinyarwanda client — needs human agent"
                )
                return OrchestratorResult(
                    success=True,
                    action="human_takeover",
                    client_id=str(client.pk),
                    conversation_id=conversation.pk,
                )
        

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

        # Step 11: Build messages context
        summary = _get_conversation_summary(conversation)
        recent_msgs = _get_recent_messages(conversation)

        # Step 10: Build system prompt
        from services.openai_service import build_system_prompt, build_messages_context

        # discovery_state = _get_discovery_state(journey, recent_msgs) #CITO CITO
        children_info = _format_children(client)

        assistant_count = sum(1 for m in recent_msgs if m.get("role") == "assistant")
        # Si flow_mode est défini, on n'est jamais au premier message
        # (le welcome bouton a déjà été envoyé)
        is_first_message = (
            assistant_count == 0
            and (flow_mode == "" or flow_mode is None)
        )

        # Détecte les choix de discovery depuis l'historique
        session_type = "studio"
        frames = False
        cake = False
        video = False

        for msg in recent_msgs:
            if msg.get("role") == "assistant":
                content = msg.get("content", "").lower()
                if "home" in content and ("session" in content or "rugo" in content):
                    pass  # question posée
            if msg.get("role") == "user":
                content = msg.get("content", "").lower()

        # Méthode plus fiable — cherche dans les messages assistant les questions
        # et dans les messages user les réponses correspondantes
        msgs_list = list(recent_msgs)
        for i, msg in enumerate(msgs_list):
            if msg.get("role") == "assistant":
                q = msg.get("content", "").lower()
                # Cherche la réponse suivante du client
                next_user = next((m for m in msgs_list[i+1:] if m.get("role") == "user"), None)
                if not next_user:
                    continue
                answer = next_user.get("content", "").lower()
                yes = any(w in answer for w in [
                    "yes", "yego", "oui", "sure", "yeah", "ok", "okay",
                    "yep", "alright", "nziza", "ntakibazo", "twaza", "ndashaka",
                    "nshaka", "ngomba", "good", "mhm"
                ])

                no = any(w in answer for w in [
                    "no", "non", "oya", "hoya", "sinjye", "sinshaka",
                    "ntabwo", "ntago", "nta", "anze", "nope"
                ])
                home_ans = any(w in answer for w in [
                    "home", "rugo", "maison", "mu rugo", "at home"
                ])

                # Detect "NO EXTRA RESPONSE"
                no_extras = any(w in answer for w in [
                    "no extras", "just photos", "photos only", "nothing else", "that's it", "base only", "none", "nothing","only pictures"
                ])
                if no_extras:
                    frames = False
                    cake = False  
                    video = False
                
                if any(w in q for w in ["studio or home", "home session", "studio session", 
                         "rugo", "studio cyangwa", "murifuzako", "muri studio"]):
                    if home_ans:
                        session_type = "home"
                if any(w in q for w in [
                    "frame", "cadre", "amaframe", "twabongereramo", 
                    "a5", "photo frame", "frames 2", "frame 2"]):
                    if yes:
                        frames = True
                    elif no:
                        frames = False
                if any(w in q for w in ["cake", "umutsima", "gateau", "twabakorera na cake"]):
                    if yes:
                        cake = True
                    elif no:
                        cake = False
                if any(w in q for w in ["video", "videwo", "twabakorera naka video"]):
                    if yes:
                        video = True
                    elif no:
                        video = False

        # Calcule les prix
        package_prices = _calculate_packages(session_type, frames, cake, video)

        system_prompt = build_system_prompt(
            journey_phase=journey.phase,
            journey_step=journey.step,
            heat_label=journey.heat_label,
            language=client.language,
            client_name=client.name or from_number,
            children_info=children_info,
            rag_context=rag_context,
            is_first_message=is_first_message,
            package_prices=package_prices,
            flow_mode=flow_mode,

           
            # discovery_state=discovery_state, #cito cito
)

        messages = build_messages_context(
            conversation_summary=summary,
            recent_messages=recent_msgs,
            new_message=text or f"[{msg_type} message]",
        )

        # Step 12: Call OpenAi
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

        
        #Step 15: Human approval gate
        needs_approval = _requires_approval(journey, intent_data)

        if needs_approval:
            if journey.step == "payment_confirmation":
                last_package_msg = conversation.messages.filter(
                    direction="outbound",
                    content__icontains="Package"
                ).order_by("-timestamp").first()
                
                package_line = "Package: (see conversation)"
                if last_package_msg:
                    lines = last_package_msg.content.split("\n")
                    for i, line in enumerate(lines):
                        # Trouve la ligne du package choisi (dernier message client)
                        last_client_msg = conversation.messages.filter(
                            direction="inbound"
                        ).order_by("-timestamp").first()
                        
                        chosen = last_client_msg.content.lower() if last_client_msg else ""
                        
                        # Cherche la ligne de prix du package choisi
                        if any(p.lower() in chosen for p in ["starter", "silver", "gold", 
                                                            "first", "cheaper", "last", 
                                                            "middle", "expensive"]):
                            # Détermine quel package
                            if "starter" in chosen or "first" in chosen or "cheaper" in chosen:
                                pkg_name = "Starter"
                            elif "gold" in chosen or "last" in chosen or "expensive" in chosen:
                                pkg_name = "Gold"
                            else:
                                pkg_name = "Silver"
                            
                            # Trouve la ligne prix + extras pour ce package
                            for j, l in enumerate(lines):
                                if pkg_name in l and "RWF" in l:
                                    # Prend le prix + la ligne Includes suivante
                                    price_line = l.strip()
                                    includes_line = ""
                                    if j+4 < len(lines) and "Includes" in lines[j+4]:
                                        includes_line = lines[j+4].strip()
                                    package_line = f"Package: {pkg_name} — {price_line.split('—')[1].strip() if '—' in price_line else ''} ({includes_line})"
                                    break
                            break

                lang = client.language  # "rw" or "en"
    
                if lang == "rw":
                    ai_suggestion = (
                        "Twayakiriye! Murakoze.\n\n"
                        "Mwuzuze amakuru yanyu:\n\n"
                        "Izina:\n"
                        "Igitsina cy'umwana:\n"
                        "Imyaka y'umwana:\n"
                        f"{package_line}\n"
                        "Umunsi w'isoko:\n"
                        "Isaha y'isoko:"
                    )
                else:
                    ai_suggestion = (
                        "Well received! Thank you.\n\n"
                        "Please fill in your details:\n\n"
                        "Name:\n"
                        "Kid's Gender:\n"
                        "Kid's Age:\n"
                        f"{package_line}\n"
                        "Booking Day:\n"
                        "Booking Time:"
                    )
            else:
                ai_suggestion = claude_response.text

            _queue_for_approval(
                client=client,
                conversation=conversation,
                ai_suggestion=ai_suggestion,  # ai_suggestion to use
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

        

        # # Step 16: Send response
        # from services.whatsapp import send_text

        # send_text(to=from_number, message=claude_response.text)
        # outbound_msg.approved_by_human = True
        # outbound_msg.save(update_fields=["approved_by_human"])


        # Step 16: Send response
        from services.whatsapp import send_text, send_buttons

        send_text(to=from_number, message=claude_response.text)

        # En mode "question" → bouton dans la bonne langue
        flow_mode = getattr(journey, "flow_mode", "")
        if flow_mode == "question":
            lang = getattr(client, "language", "en") or "en"
            bodies = {"en": "Still need help? Talk or call a real person — we've got you 😊", "rw": "Ukeneye ubufasha bwisumbuye? Vugana cyangwa uhamagare umuntu wa nyawe agufashe — turi hano kubwanyu 😊", "fr": "Besoin d'aide ? Discutez ou appelez une vraie personne — nous sommes là pour vous 😊"}
            agent_titles = {"en": "🧑 Talk to Agent", "rw": "🧑 Vugana n'Umukozi", "fr": "🧑 Parler à un Agent"}
            book_titles = {"en": "📸 Book a Session", "rw": "📸 Fata Igihe", "fr": "📸 Réserver"}
            send_buttons(
                to=from_number,
                body=bodies.get(lang, bodies["en"]),
                buttons=[
                    {"id": "btn_agent", "title": agent_titles.get(lang, agent_titles["en"])},
                    {"id": "btn_book",  "title": book_titles.get(lang, book_titles["en"])},
                ],
            )

        #  # Auto-advance to payment_confirmation if AI just sent payment details CITO
        _maybe_flag_payment_confirmation(journey, claude_response.text, conversation)

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


# def _update_language(client, text: str):
#     from utils.language import detect_language

#     detected = detect_language(text)

#     # # Not switch RW → EN on a short message
#     # if client.language == "rw" and detected == "en":
#     #     if len(text.strip().split()) < 5:
#     #         return  # "ok", "yes", "Silver", "no" → We keep RW

#     if detected != client.language:
#         client.language = detected
#         client.save(update_fields=["language", "updated_at"])
#nexplit
def _update_language(client, text: str):
    # Si la langue a été choisie explicitement via bouton → ne jamais changer
    if getattr(client, "language_locked", False):
        return

    from utils.language import detect_language
    detected = detect_language(text)

    # Ne pas dégrader sur message court
    if client.language == "rw" and detected == "en":
        if len(text.strip().split()) < 5:
            return

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
    phase = journey.phase
    step = journey.step

    # Payment confirmation always needs human
    if step == "payment_confirmation":
        return True

    # Sales resistance: let AI handle levels 1 and 2, escalate on 3rd objection
    if phase == "sales_resistance":
        if journey.objection_count and journey.objection_count >= 2:
            return True
        return False

    # Booking phase: moderate oversight
    if phase == "booking" and step in ("package_presentation",):
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

#Confirmation awaiting

def _maybe_flag_payment_confirmation(journey, ai_response_text: str, conversation =None):
    if not ai_response_text:
        return
    PAYMENT_SENT_SIGNALS = ["798741", "mtn momo", "please send the 20,000"]
    text_lower = ai_response_text.lower()
    if any(signal in text_lower for signal in PAYMENT_SENT_SIGNALS):
        from apps.clients.models import JourneyPhase, JourneyStep
        try:
            if journey.step != JourneyStep.PAYMENT_CONFIRMATION:
                journey.phase = JourneyPhase.BOOKING
                journey.step = JourneyStep.PAYMENT_CONFIRMATION
                journey.save(update_fields=["phase", "step", "updated_at"])
                logger.info(
                    "Auto-advanced to payment_confirmation | client=%s",
                    journey.client.wa_number,
                )
                # Envoie email notification
                _send_payment_notification_email(journey.client, conversation, journey = journey)
        except Exception as exc:
            logger.warning("Could not advance to payment_confirmation: %s", exc)


def _send_payment_notification_email(client, conversation=None, journey=None):
    try:
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings

        # ── Récupérer les infos depuis journey.discovery_state (flow boutons)
        chosen = "Unknown"
        extras = "None"
        session_label = "Studio"
        total_price = ""

        if journey:
            chosen = journey.selected_package or "Unknown"
            state = journey.discovery_state or {}

            session_type = state.get("session_type", "studio")
            photo_type   = state.get("photo_type", "child")   # ← AJOUTE
            session_label = "Home" if session_type == "home" else "Studio"
            photo_label   = "Family Photoshoot" if photo_type == "family" else "Child Photoshoot"  # ← AJOUTE

            frames = state.get("frames", False)
            cake   = state.get("cake",   False)
            video  = state.get("video",  False)

            extras_list = []
            extras_cost = 0
            if frames:
                extras_cost += 20000
                extras_list.append("2 A5 Photo Frames")
            if cake and video:
                extras_cost += 50000
                extras_list.append("Birthday Cake + Highlight Video")
            elif cake:
                extras_cost += 30000
                extras_list.append("Birthday Cake")
            elif video:
                extras_cost += 29000
                extras_list.append("Highlight Video")

            home_fee = 200000 if session_type == "home" else 0   # ← CORRIGE (était 69000)
            extras = ", ".join(extras_list) if extras_list else "None"

            # Pour home session, il n'y a qu'un seul package "Premium"
            if session_type == "home":
                base = 200000
                total = base + extras_cost
                chosen = "Premium"
            else:
                base_prices = {"Starter": 50000, "Silver": 70000, "Gold": 100000}
                base = base_prices.get(chosen, 0)
                total = base + extras_cost
            total_price = f"{total:,} RWF" if total else ""

        # ── Fallback : chercher dans les messages DB (ancien flow IA)
        elif conversation:
            last_client_msg = conversation.messages.filter(
                direction="inbound"
            ).order_by("-timestamp").first()
            if last_client_msg:
                chosen = last_client_msg.content

            last_pkg_msg = conversation.messages.filter(
                direction="outbound",
                content__icontains="Includes:"
            ).order_by("-timestamp").first()
            if last_pkg_msg:
                for line in last_pkg_msg.content.split("\n"):
                    if "Includes:" in line:
                        extras = line.replace("Includes:", "").strip()
                        break

        text_body = (
            f"Client ready to pay.\n\n"
            f"Name: {client.name or 'Unknown'}\n"
            f"Phone: {client.wa_number}\n\n"
            f"Package: {chosen} {total_price}\n"
            f"Session: {session_label}\n"
            f"Extras: {extras}\n\n"
            f"Action: Verify MoMo on 798741 then approve in dashboard.\n"
            f"Dashboard: https://senior-madeleine-matabar-93648cd5.koyeb.app/"
        )

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ margin: 0; padding: 0; background-color: #f5f0eb; font-family: 'Georgia', serif; }}
    .wrapper {{ max-width: 600px; margin: 40px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
    .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); padding: 40px 30px; text-align: center; }}
    .header h1 {{ color: #fff; margin: 0; font-size: 24px; letter-spacing: 2px; text-transform: uppercase; }}
    .header p {{ color: #e2b96f; margin: 8px 0 0; font-size: 14px; letter-spacing: 1px; }}
    .badge {{ display: inline-block; background: #e2b96f; color: #1a1a2e; padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-top: 15px; letter-spacing: 1px; }}
    .body {{ padding: 35px 40px; }}
    .section-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: #999; margin-bottom: 8px; margin-top: 24px; }}
    .info-block {{ background: #f9f6f2; border-left: 4px solid #e2b96f; border-radius: 6px; padding: 16px 20px; margin-bottom: 16px; }}
    .info-block p {{ margin: 6px 0; color: #333; font-size: 15px; }}
    .info-block strong {{ color: #1a1a2e; }}
    .package-block {{ background: linear-gradient(135deg, #1a1a2e, #0f3460); border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; }}
    .package-block p {{ margin: 6px 0; color: #fff; font-size: 15px; }}
    .pkg-name {{ color: #e2b96f; font-size: 20px; font-weight: bold; margin-bottom: 8px; }}
    .pkg-price {{ color: #fff; font-size: 18px; font-weight: bold; }}
    .pkg-detail {{ color: #a8d8ea; font-size: 13px; }}
    .action-btn {{ display: block; background: #e2b96f; color: #1a1a2e; text-align: center; padding: 16px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px; letter-spacing: 1px; margin: 25px 0; }}
    .footer {{ background: #1a1a2e; padding: 20px; text-align: center; }}
    .footer p {{ color: #666; font-size: 12px; margin: 4px 0; }}
    .footer a {{ color: #e2b96f; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>KP Kids Studio</h1>
      <p>Payment Notification</p>
      <span class="badge">💳 ACTION REQUIRED</span>
    </div>
    <div class="body">

      <div class="section-title">Client Details</div>
      <div class="info-block">
        <p><strong>Name:</strong> {client.name or 'Unknown'}</p>
        <p><strong>Phone:</strong> {client.wa_number}</p>
      </div>

      <div class="section-title">Package Selected</div>
      <div class="package-block">
        <p class="pkg-name">📦 {chosen} Package</p>
        <p class="pkg-price">{total_price}</p>
        <p class="pkg-detail">📍 {session_label} Session</p>
        <p class="pkg-detail">📸 {photo_label}</p>
        <p class="pkg-detail">✨ Extras: {extras}</p>
      </div>

      <div class="section-title">Action Required</div>
      <div class="info-block">
        <p>1. Verify MoMo payment on <strong>798741</strong></p>
        <p>2. Approve the booking in the dashboard</p>
        <p>3. Send the booking form to the client</p>
      </div>

      <a href="https://senior-madeleine-matabar-93648cd5.koyeb.app/" class="action-btn">
        Open Dashboard →
      </a>

    </div>
    <div class="footer">
      <p>KP Kids Studio — Kigali, Rwanda</p>
      <p><a href="https://senior-madeleine-matabar-93648cd5.koyeb.app/">Dashboard</a></p>
    </div>
  </div>
</body>
</html>
"""
        msg = EmailMultiAlternatives(
            subject=f"💳 Payment pending — {client.name or client.wa_number} | {chosen} {total_price}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.STUDIO_NOTIFICATION_EMAIL],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
        logger.info("Payment notification sent for %s", client.wa_number)

    except Exception as exc:
        logger.warning("Email notification failed: %s", exc)
 
def _notify_human_takeover(
    client, conversation, reason: str,
    ai_suggestion: str = "[AI silenced — human takeover required]"
):
    from apps.conversations.models import ApprovalQueue, ApprovalAction

    ApprovalQueue.objects.create(
        client=client,
        conversation=conversation,
        action=ApprovalAction.ESCALATE,
        ai_suggestion=ai_suggestion,
        ai_reasoning=reason,
        heat_score_at_suggestion=getattr(
            getattr(client, "journey_state", None), "heat_score", 50
        ),
        expires_at=timezone.now() + timezone.timedelta(hours=72),
    )
    logger.warning(
        "Human takeover triggered | client=%s reason=%s", client.wa_number, reason
    )



def _calculate_packages(session_type: str, frames: bool, cake: bool, video: bool) -> str:
    """Calculate exact prices based on discovery answers."""
    base = {"Starter": 50000, "Silver": 70000, "Gold": 100000}
    
    extras = 0
    extras_list = []
    
    if frames:
        extras += 20000
        extras_list.append("2 A5 Photo Frames")
    if cake and video:
        extras += 50000
        extras_list.append("Birthday Cake")
        extras_list.append("Highlight Video")
    elif cake:
        extras += 30000
        extras_list.append("Birthday Cake")
    elif video:
        extras += 29000
        extras_list.append("Highlight Video")
    
    home = 69000 if session_type == "home" else 0
    session_label = "Home" if session_type == "home" else "Studio"
    includes = ", ".join(extras_list) if extras_list else "No extras"
    
    result = f"SESSION: {session_label}\nEXTRAS CHOSEN: {includes}\n\n"
    for name, base_price in base.items():
        total = base_price + extras + home
        duration = "1.5h" if name == "Gold" else "1h"
        photos = 8 if name == "Starter" else (12 if name == "Silver" else 18)
        result += f"{name}: {total:,} RWF | {duration} {session_label} Session | {photos} Edited Photos"
        if extras_list:
            result += f" | Includes: {includes}"
        result += "\n"
    
    return result

def _set_flow_mode_on_journey(journey, mode: str):
    journey.flow_mode = mode
    journey.save(update_fields=["flow_mode", "updated_at"])
#________________________________________________________________________________________________________
# """
# Journey Orchestrator
# =====================
# The brain that connects all services into one coherent pipeline.

# Called by process_inbound_message Celery task.
# Takes a raw inbound message → produces a WhatsApp reply or approval queue item.

# Pipeline (in order):
#   1. Opt-out check         → hard stop if client opted out
#   2. Onboard               → upsert client + journey + conversation
#   3. Save inbound message  → permanent record
#   4. Budget check          → hard stop + human takeover if exceeded
#   5. Human takeover check  → hard stop if human already handling
#   6. Language detection    → update client preference
#   7. Intent analysis       → classify message, detect objections (gtp 4 mini, cheap)
#   8. Heat update           → update score from signals
#   9. RAG retrieval         → fetch top-K relevant knowledge chunks
#  10. Build prompt          → compact system prompt with context
#  11. Call Openai           → get response (4o mini or 4o)
#  12. Save outbound message → record with full token accounting
#  13. Human approval gate   → queue or send directly based on phase/action
#  14. Send / queue          → WhatsApp send or approval queue

# Every step is logged. Any step can flag human takeover.
# """

# import json
# import logging
# from dataclasses import dataclass
# from typing import Optional
# from django.utils import timezone
# from django.conf import settings


# logger = logging.getLogger(__name__)


# @dataclass
# class OrchestratorResult:
#     success: bool
#     action: (
#         str  # "sent" | "queued_for_approval" | "human_takeover" | "opted_out" | "error"
#     )
#     client_id: Optional[str] = None
#     conversation_id: Optional[int] = None
#     tokens_used: int = 0
#     error: Optional[str] = None


# # Phase : requires human approval?

# _APPROVAL_REQUIRED_STEPS = {
#     "payment_confirmation",
#     "send_bonus",
#     "package_adjustment",
#     "escalate",
# }

# _AUTO_SEND_PHASES = {
#     "entry",
#     "preparation",
#     "delivery",
#     "feedback",
# }


# # Main pipeline


# def handle_inbound_message(
#     message_id: str,
#     from_number: str,
#     from_name: str,
#     msg_type: str,
#     text: str,
#     timestamp: str,
#     interactive_id: Optional[str] = None,
# ) -> OrchestratorResult:
#     """
#     Full inbound message pipeline.
#     Returns OrchestratorResult — never raises.
#     """

#     try:
#         # Step 1: Opt-out hard check
#         opt_out_result = _check_opt_out(from_number, text)
#         if opt_out_result:
#             return opt_out_result

#         # Step 2: Onboard client
#         from services.client_service import onboard_client

#         client, journey, conversation, is_new = onboard_client(
#             wa_number=from_number,
#             name=from_name,
#         )

#         # Step 3: Save inbound message
#         inbound_msg = _save_inbound(
#             client=client,
#             conversation=conversation,
#             message_id=message_id,
#             text=text,
#             msg_type=msg_type,
#         )

#         # Step 4: Budget check
#         from services.client_service import is_budget_exceeded

#         if is_budget_exceeded(client, conversation):
#             journey.flag_human_takeover("Token budget exceeded")
#             _notify_human_takeover(client, conversation, reason="Token budget exceeded")
#             return OrchestratorResult(
#                 success=True,
#                 action="human_takeover",
#                 client_id=str(client.pk),
#                 conversation_id=conversation.pk,
#             )

#         # Step 5: Human takeover check
#         if journey.human_takeover:
#             logger.info("Human takeover active for %s — AI silenced", client.wa_number)
#             return OrchestratorResult(
#                 success=True,
#                 action="human_takeover",
#                 client_id=str(client.pk),
#                 conversation_id=conversation.pk,
#             )

#         # Step 6: Language detection
#         if text:
#             _update_language(client, text)

#         # Step 7: Intent + objection analysis
#         intent_data = _analyze_intent(text, journey, conversation)

#         # Step 8: Heat score update
#         _update_heat(
#             journey=journey,
#             message_text=text,
#             intent_data=intent_data,
#             inbound_msg=inbound_msg,
#             conversation=conversation,
#         )

#         # Step 9: RAG context retrieval
#         from services.rag_service import retrieve_context

#         rag_context = retrieve_context(
#             query=text or "",
#             journey_phase=journey.phase,
#             language=client.language,
#         )

#         # Step 11: Build messages context
#         summary = _get_conversation_summary(conversation)
#         recent_msgs = _get_recent_messages(conversation)

#         # Step 10: Build system prompt
#         from services.openai_service import build_system_prompt, build_messages_context

#         # discovery_state = _get_discovery_state(journey, recent_msgs) #CITO CITO
#         children_info = _format_children(client)
#         system_prompt = build_system_prompt(
#             journey_phase=journey.phase,
#             journey_step=journey.step,
#             heat_label=journey.heat_label,
#             language=client.language,
#             client_name=client.name or from_number,
#             children_info=children_info,
#             rag_context=rag_context,
#             #is_first_message=not any(m.get("role") == "assistant" for m in recent_msgs),
#             # discovery_state=discovery_state,
# )

#         messages = build_messages_context(
#             conversation_summary=summary,
#             recent_messages=recent_msgs,
#             new_message=text or f"[{msg_type} message]",
#         )

#         # Step 12: Call Claude
#         escalate = journey.phase == "sales_resistance" and journey.heat_score >= 40
#         # from services.claude import call_claude

#         # claude_response = call_claude(
#         #     system_prompt=system_prompt,
#         #     messages=messages,
#         #     escalate=escalate,
#         # )
#         from services.openai_service import call_openai
#         claude_response = call_openai(
#                 system_prompt=system_prompt,
#                 messages=messages,
#                 escalate=escalate,
#         )

#         # Step 13: Record tokens
#         from services.client_service import record_tokens

#         record_tokens(
#             client,
#             conversation,
#             claude_response.input_tokens,
#             claude_response.output_tokens,
#         )

#         # Step 14: Save outbound message
#         outbound_msg = _save_outbound(
#             client=client,
#             conversation=conversation,
#             text=claude_response.text,
#             model=claude_response.model,
#             tokens_input=claude_response.input_tokens,
#             tokens_output=claude_response.output_tokens,
#         )

#         #  # Auto-advance to payment_confirmation if AI just sent payment details CITO
#         # _maybe_flag_payment_confirmation(journey, claude_response.text)
        

#         # Step 15: Human approval gate
#         needs_approval = _requires_approval(journey, intent_data)

#         if needs_approval:
#             _queue_for_approval(
#                 client=client,
#                 conversation=conversation,
#                 ai_suggestion=claude_response.text,
#                 ai_reasoning=f"Phase: {journey.phase}/{journey.step} | Heat: {journey.heat_label} | Intent: {intent_data.get('intent', 'unknown')}",
#                 heat_score=journey.heat_score,
#                 action=_map_approval_action(journey, intent_data),
#             )
#             outbound_msg.approved_by_human = None  # pending
#             outbound_msg.save(update_fields=["approved_by_human"])
#             return OrchestratorResult(
#                 success=True,
#                 action="queued_for_approval",
#                 client_id=str(client.pk),
#                 conversation_id=conversation.pk,
#                 tokens_used=claude_response.total_tokens,
#             )

#         # Step 16: Send response
#         from services.whatsapp import send_text

#         send_text(to=from_number, message=claude_response.text)
#         outbound_msg.approved_by_human = True
#         outbound_msg.save(update_fields=["approved_by_human"])

#         # Update conversation window
#         conversation.touch()

#         logger.info(
#             "Pipeline complete | client=%s phase=%s tokens=%s action=sent",
#             client.wa_number,
#             journey.phase,
#             claude_response.total_tokens,
#         )

#         return OrchestratorResult(
#             success=True,
#             action="sent",
#             client_id=str(client.pk),
#             conversation_id=conversation.pk,
#             tokens_used=claude_response.total_tokens,
#         )

#     except Exception as exc:
#         logger.exception("Orchestrator pipeline error for %s: %s", from_number, exc)
#         return OrchestratorResult(
#             success=False,
#             action="error",
#             error=str(exc),
#         )


# # Step helpers


# def _check_opt_out(from_number: str, text: str) -> Optional[OrchestratorResult]:
#     """
#     Check if client has opted out OR is sending an opt-out signal.
#     Opt-out keywords: STOP, UNSUBSCRIBE, OPT OUT, ARRÊT, HAGARARA
#     """
#     OPT_OUT_KEYWORDS = {"stop", "unsubscribe", "opt out", "hagarara", "tanga"}

#     from apps.clients.models import Client

#     try:
#         client = Client.objects.get(wa_number=from_number)
#         if client.is_opted_out:
#             logger.info("Opted-out client %s messaged — ignoring", from_number)
#             return OrchestratorResult(success=True, action="opted_out")
#     except Client.DoesNotExist:
#         pass

#     if text and any(kw in text.lower() for kw in OPT_OUT_KEYWORDS):
#         _process_opt_out(from_number)
#         return OrchestratorResult(success=True, action="opted_out")

#     return None


# def _process_opt_out(from_number: str):
#     """Mark client as opted out and send acknowledgement."""
#     from apps.clients.models import Client
#     from services.whatsapp import send_text

#     client, _ = Client.objects.get_or_create(
#         wa_number=from_number,
#         defaults={"status": "new"},
#     )
#     client.is_opted_out = True
#     client.opted_out_at = timezone.now()
#     client.save(update_fields=["is_opted_out", "opted_out_at"])


# def _save_inbound(client, conversation, message_id, text, msg_type):
#     from apps.conversations.models import Message, MessageDirection, MessageStatus

#     # Dedup by wa_message_id — safe to call even if already exists
#     msg, _ = Message.objects.get_or_create(
#         wa_message_id=message_id,
#         defaults={
#             "conversation": conversation,
#             "client": client,
#             "direction": MessageDirection.INBOUND,
#             "status": MessageStatus.RECEIVED,
#             "content": text or f"[{msg_type}]",
#             "msg_type": msg_type,
#             "timestamp": timezone.now(),
#         },
#     )
#     return msg


# def _save_outbound(client, conversation, text, model, tokens_input, tokens_output):
#     import uuid
#     from apps.conversations.models import Message, MessageDirection, MessageStatus

#     msg = Message.objects.create(
#         wa_message_id=f"outbound_{uuid.uuid4().hex[:12]}",
#         conversation=conversation,
#         client=client,
#         direction=MessageDirection.OUTBOUND,
#         status=MessageStatus.SENT,
#         content=text,
#         msg_type="text",
#         generated_by_ai=True,
#         model_used=model,
#         tokens_input=tokens_input,
#         tokens_output=tokens_output,
#         timestamp=timezone.now(),
#     )
#     return msg


# def _update_language(client, text: str):
#     from utils.language import detect_language

#     detected = detect_language(text)
#     if detected != client.language:
#         client.language = detected
#         client.save(update_fields=["language", "updated_at"])


# def _analyze_intent(text: str, journey, conversation) -> dict:
#     """
#     Run intent classification. Returns parsed dict.
#     Gracefully returns empty dict on failure — non-critical.
#     """
#     if not text:
#         return {}
#     try:
#         # Build mini context from last 2 messages
#         last_msgs = conversation.messages.order_by("-timestamp")[:2]
#         history = " | ".join(m.content[:100] for m in reversed(last_msgs))

#         #from services.claude import analyze_intent_and_heat
#         from services.openai_service import analyze_intent_and_heat

#         result = analyze_intent_and_heat(text, history)

#         if result.ok:
#             # Strip markdown fences if model wraps response despite instructions
#             raw = result.text.strip()
#             if raw.startswith("```"):
#                 raw = raw.split("```")[1]
#                 if raw.startswith("json"):
#                     raw = raw[4:]
#                 raw = raw.strip()
#             return json.loads(raw)

       
#     except (json.JSONDecodeError, Exception) as exc:
#         logger.debug("Intent analysis parse failed (non-critical): %s", exc)
#     return {}


# def _update_heat(journey, message_text, intent_data, inbound_msg, conversation):
#     """Apply all heat signals from this message."""
#     from services.heat_engine import calculate_heat_delta, update_heat_score
#     from apps.conversations.models import HeatEvent

#     # Get timing for reply speed signal
#     last_outbound = (
#         conversation.messages.filter(direction="outbound")
#         .order_by("-timestamp")
#         .values_list("timestamp", flat=True)
#         .first()
#     )

#     result = calculate_heat_delta(
#         message_text=message_text or "",
#         last_outbound_at=last_outbound,
#         message_received_at=inbound_msg.timestamp,
#     )

#     # Apply delta from message analysis
#     if result["total_delta"] != 0:
#         dominant_signal = (
#             result["signals"][0] if result["signals"] else "engagement_pattern"
#         )
#         update_heat_score(
#             journey_state=journey,
#             delta=result["total_delta"],
#             signal_type=_map_heat_signal(dominant_signal),
#             reason=", ".join(result["signals"][:3]),
#         )

#     # Apply additional delta from AI intent analysis
#     ai_delta = intent_data.get("heat_delta", 0)
#     if ai_delta and ai_delta != 0:
#         update_heat_score(
#             journey_state=journey,
#             delta=ai_delta,
#             signal_type=HeatEvent.SignalType.EMOTIONAL_TONE,
#             reason=f"AI intent: {intent_data.get('intent', 'unknown')}",
#         )

#     # Update detected objection if found
#     objection = intent_data.get("objection_type", "none")
#     if objection and objection != "none":
#         journey.detected_objection = objection
#         journey.objection_count = (journey.objection_count or 0) + 1

#         # If objection detected and in booking phase → activate sales resistance
#         if journey.phase == "booking":
#             from apps.clients.models import JourneyPhase, JourneyStep

#             journey.advance(
#                 JourneyPhase.SALES_RESISTANCE, JourneyStep.OBJECTION_HANDLING
#             )
#         else:
#             journey.save(
#                 update_fields=["detected_objection", "objection_count", "updated_at"]
#             )


# def _get_conversation_summary(conversation) -> Optional[str]:
#     """Return compressed summary if it exists."""
#     try:
#         return conversation.summary.summary_text
#     except Exception:
#         return None


# def _get_recent_messages(conversation) -> list:
#     """
#     Return last N messages as {role, content} dicts.
#     Includes messages from current conversation only,
#     but falls back to recent conversations if current is empty.
#     """
#     from apps.conversations.models import Message

#     msgs = conversation.messages.order_by("-timestamp")[:10]

#     # If current conversation has no messages yet, get from client's recent history
#     if not msgs.exists():
#         msgs = Message.objects.filter(
#             client=conversation.client,
#         ).order_by("-timestamp")[:10]

#     result = []
#     for m in reversed(msgs):
#         role = "user" if m.direction == "inbound" else "assistant"
#         result.append({"role": role, "content": m.content})
#     return result


# def _format_children(client) -> str:
#     children = client.children.all()
#     if not children:
#         return ""
#     parts = []
#     for c in children:
#         age = (
#             f", {c.age_years} years old"
#             if hasattr(c, "age_years") and c.age_years
#             else ""
#         )
#         parts.append(f"{c.name}{age}")
#     return "; ".join(parts)


# def _requires_approval(journey, intent_data: dict) -> bool:
#     """
#     Determine if AI response needs human review before sending.
#     Based on the AI vs Human Control Matrix.
#     """
#     phase = journey.phase
#     step = journey.step
#     intent = intent_data.get("intent", "")

#     # Payment confirmation always needs human
#     if step == "payment_confirmation":
#         return True

#     # Sales resistance: escalation decisions need human
#     if phase == "sales_resistance" and journey.escalation_needed(intent_data):
#         return True

#     # Booking phase: moderate oversight
#     if phase == "booking" and step in ("package_presentation",):
#         # Only auto-send for LOW heat — HIGH/MEDIUM needs human check
#         return journey.heat_score >= 70

#     return False


# def _queue_for_approval(
#     client, conversation, ai_suggestion, ai_reasoning, heat_score, action
# ):
#     from apps.conversations.models import ApprovalQueue

#     ApprovalQueue.objects.create(
#         client=client,
#         conversation=conversation,
#         action=action,
#         ai_suggestion=ai_suggestion,
#         ai_reasoning=ai_reasoning,
#         heat_score_at_suggestion=heat_score,
#         expires_at=timezone.now() + timezone.timedelta(hours=48),
#     )
#     logger.info(
#         "Queued for human approval | client=%s action=%s heat=%s",
#         client.wa_number,
#         action,
#         heat_score,
#     )


# def _map_approval_action(journey, intent_data: dict) -> str:
#     from apps.conversations.models import ApprovalAction

#     step = journey.step
#     if step == "payment_confirmation":
#         return ApprovalAction.SEND_MESSAGE
#     if journey.phase == "sales_resistance":
#         return ApprovalAction.ESCALATE
#     return ApprovalAction.SEND_MESSAGE


# def _map_heat_signal(signal_name: str) -> str:
#     from apps.conversations.models import HeatEvent

#     mapping = {
#         "reply_speed_immediate": HeatEvent.SignalType.REPLY_SPEED,
#         "reply_speed_fast": HeatEvent.SignalType.REPLY_SPEED,
#         "reply_speed_same_day": HeatEvent.SignalType.REPLY_SPEED,
#         "reply_speed_slow": HeatEvent.SignalType.REPLY_SPEED,
#         "reply_speed_very_slow": HeatEvent.SignalType.REPLY_SPEED,
#         "length_detailed": HeatEvent.SignalType.MESSAGE_LENGTH,
#         "length_moderate": HeatEvent.SignalType.MESSAGE_LENGTH,
#         "length_brief": HeatEvent.SignalType.MESSAGE_LENGTH,
#         "question_detected": HeatEvent.SignalType.QUESTION_DEPTH,
#         "emotional_language": HeatEvent.SignalType.EMOTIONAL_TONE,
#         "commitment_signal": HeatEvent.SignalType.ENGAGEMENT_PATTERN,
#         "objection_detected": HeatEvent.SignalType.ENGAGEMENT_PATTERN,
#     }
#     return mapping.get(signal_name, HeatEvent.SignalType.ENGAGEMENT_PATTERN)

# #CITO CITO

# # def _maybe_flag_payment_confirmation(journey, ai_response_text: str):
# #     """
# #     If AI just sent payment instructions (MTN number),
# #     advance journey to payment_confirmation.
# #     Next client message will trigger human approval automatically.
# #     """
# #     if not ai_response_text:
# #         return
# #     PAYMENT_SENT_SIGNALS = [
# #         "798741", "momo", "booking fee", "20,000",
# #         "20k", "payment number", "send the booking",
# #     ]
# #     text_lower = ai_response_text.lower()
# #     if any(signal in text_lower for signal in PAYMENT_SENT_SIGNALS):
# #         from apps.clients.models import JourneyPhase, JourneyStep
# #         try:
# #             if journey.step != JourneyStep.PAYMENT_CONFIRMATION:
# #                 journey.phase = JourneyPhase.BOOKING
# #                 journey.step = JourneyStep.PAYMENT_CONFIRMATION
# #                 journey.save(update_fields=["phase", "step", "updated_at"])
# #                 logger.info(
# #                     "Auto-advanced to payment_confirmation | client=%s",
# #                     journey.client.wa_number,
# #                 )
# #         except Exception as exc:
# #             logger.warning("Could not advance to payment_confirmation: %s", exc)





# def _notify_human_takeover(client, conversation, reason: str):
#     """
#     Log and optionally notify dashboard that a client needs human handling.
#     In future: push notification to studio staff.
#     """
#     from apps.conversations.models import ApprovalQueue, ApprovalAction

#     ApprovalQueue.objects.create(
#         client=client,
#         conversation=conversation,
#         action=ApprovalAction.ESCALATE,
#         ai_suggestion="[AI silenced — human takeover required]",
#         ai_reasoning=reason,
#         heat_score_at_suggestion=getattr(
#             getattr(client, "journey_state", None), "heat_score", 50
#         ),
#         expires_at=timezone.now() + timezone.timedelta(hours=72),
#     )
#     logger.warning(
#         "Human takeover triggered | client=%s reason=%s", client.wa_number, reason
#     )
       

