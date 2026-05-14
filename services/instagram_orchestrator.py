"""
Instagram AI Orchestrator — v2 (CORRECTED)
=========================================
Pure AI conversation system for Instagram DMs.
Follows strict mandates from services/INSTAGRAM_AI.md and GEMINI.md.

KP Kids Studio | Kigali, Rwanda
"""

import logging
import uuid
from typing import Optional, Dict, Any, List
from django.utils import timezone
from django.conf import settings

from apps.clients.models import Client, JourneyState, JourneyPhase, JourneyStep
from apps.instagram.models import InstagramConversation, InstagramMessage, InstagramApprovalQueue
from services.instagram_service import send_text, send_image, mark_as_seen
from services.openai_service import call_openai, build_messages_context
from services.rag_service import retrieve_context

logger = logging.getLogger(__name__)

# --- CONSTANTS ---

RW_SIGNALS = [
    "muraho", "mwaramutse", "mwiriwe", "yego", "oya", "hoya",
    "ndi", "turi", "ubu", "muri", "kuki", "bite", "mbega",
    "amakuru", "ni meza", "murakoze", "ndashaka", "ibiciro",
    "kwifotoza", "amafoto", "gufotora", "umwana", "umuryango",
    "nziza", "muragize", "barakaza", "murakaza"
]

LANG_INSTRUCTIONS = {
    "en": (
        "You MUST respond ONLY in English. "
        "Even if the client writes in French or Kinyarwanda, YOU respond in English. "
        "Never switch languages."
    ),
    "fr": (
        "Tu DOIS répondre UNIQUEMENT en français. "
        "Même si le client écrit en anglais ou kinyarwanda, TU réponds en français. "
        "Ne change JAMAIS de langue."
    ),
    "rw": (
        "Ugomba gusubiza mu Kinyarwanda GUSA. "
        "Niba umukiriya andika mu cyongereza cyangwa igifaransa, "
        "WEWE subiza mu Kinyarwanda. "
        "Ntuzahindure ururimi na rimwe mu kiganiro. "
        "Niba umukiriya avanga ururimi, subiza mu Kinyarwanda."
    ),
}

DISCOVERY_QUESTIONS = {
    "en": [
        {
            "key": "photo_type",
            "question": "First, is this session for a child photoshoot or a family photoshoot? 😊",
        },
        {
            "key": "session_type",
            "question": "Would you prefer the session at our studio in Kicukiro, or would you like us to come to your home? 📸",
        },
        {
            "key": "frames",
            "question": "Would you like to add 2 beautiful A5 photo frames to your package? 🖼️ ",
                
        },
        {
            "key": "cake",
            "question": "How about adding a birthday cake? 🎂",
              
        },
        {
            "key": "video",
            "question": "Would you like a short highlight video of the session? 🎬 ",
                
        },
    ],
    "fr": [
        {
            "key": "photo_type",
            "question": "Tout d'abord, cette séance est-elle pour un enfant seul ou pour toute la famille? 😊",
        },
        {
            "key": "session_type",
            "question": "Préférez-vous la séance dans notre studio à Kicukiro, ou souhaitez-vous que nous venions à votre domicile? 📸",
        },
        {
            "key": "frames",
            "question": "Souhaitez-vous ajouter 2 beaux cadres photo A5 à votre forfait? 🖼️",
               
        },
        {
            "key": "cake",
            "question": "Et un gâteau d'anniversaire, on l'inclut? ",
        },
        {
            "key": "video",
            "question": "Souhaitez-vous une courte vidéo souvenir? 🎬 ",
        },
    ],
    "rw": [
        {
            "key": "photo_type",
            "question": "Mbere na mbere, ni ubuhe bwoko bwa photoshoot mushaka? Umwana gusa cyangwa umuryango wose? 😊",
        },
        {
            "key": "session_type",
            "question": "Murifuza kwifotoza muri studio yacu i Kicukiro, cyangwa murifuza tuze mu rugo rwanyu? 📸",
        },
        {
            "key": "frames",
            "question": "Murifuza kongereramo ama cadre 2 ya A5 muri package yanyu? 🖼️ ",
        },
        {
            "key": "cake",
            "question": "Murifuza kongereramo cake ya aniverseri?",
        },
        {
            "key": "video",
            "question": "Murifuza video ngufi ya session yanyu? 🎬 ",
        },
    ],
}

WELCOME_MESSAGES = {
    "en": (
        "Hello! 😊 Welcome to KP Kids Studio — your children's photography "
        "specialist in Kigali, Rwanda.\n\n"
        "My name is Julie and I'm here to help you.\n\n"
        "How can I assist you today? You can ask me about:\n"
        "📸 Booking a photoshoot session\n"
        "💰 Our packages and pricing\n"
        "📍 Finding our studio\n"
        "❓ Any other questions"
    ),
    "fr": (
        "Bonjour! 😊 Bienvenue chez KP Kids Studio — votre spécialiste en "
        "photographie pour enfants à Kigali, Rwanda.\n\n"
        "Je m'appelle Julie et je suis là pour vous aider.\n\n"
        "Comment puis-je vous aider? Vous pouvez me demander:\n"
        "📸 Réserver une séance photo\n"
        "💰 Nos forfaits et tarifs\n"
        "📍 Trouver notre studio\n"
        "❓ Toute autre question"
    ),
    "rw": (
        "Muraho! 😊 Murakaza neza kuri KP Kids Studio — inzobere mu gufotora "
        "abana i Kigali, Rwanda.\n\n"
        "Nitwa Julie kandi ndi hano kubafasha.\n\n"
        "Ni gute nabafasha uyu munsi? Mwambaza ibi:\n"
        "📸 Gufatira igihe cyo kwifotoza\n"
        "💰 Packages zacu n'ibiciro\n"
        "📍 Ahantu turi\n"
        "❓ Ibibazo ibindi"
    ),
}

LOCATION_SIGNALS = [
    "where", "location", "address", "find you", "how to get",
    "directions", "map", "located", "où", "adresse", "localisation",
    "comment venir", "trouver", "emplacement", "aho muri", "aho muba",
    "aho", "murari he", "adresse", "ehe", "murakora he",
]

LOCATION_RESPONSES = {
    "en": (
        "We are located in Kicukiro, BRGD Plaza, opposite IPRC, "
        "next to SAWA CITY Supermarket, Kigali. 📍\n\n"
        "We are open Monday to Sunday, 9 AM to 6 PM."
    ),
    "fr": (
        "Nous sommes situés à Kicukiro, BRGD Plaza, en face de l'IPRC, "
        "à côté du Supermarché SAWA CITY, Kigali. 📍\n\n"
        "Nous sommes ouverts du lundi au dimanche, de 9h à 18h."
    ),
    "rw": (
        "Turi i Kicukiro, BRGD Plaza, imbere y'IPRC, "
        "hafi ya Supermarché SAWA CITY, Kigali. 📍\n\n"
        "Turi hafi kuva ku wa Mbere kugeza ku Ku cyumweru, "
        "saa tatu z'igitondo kugeza saa cyenda nijoro."
    ),
}

PRICE_SIGNALS = [
    "price", "cost", "how much", "package", "rates", "pricing", "booking", "book",
    "afford", "expensive", "cheap", "fees", "prix", "coût", "combien", "reservation", "reserver", "reserve",
    "forfait", "tarif", "cher", "ibiciro", "ingahe", "amafaranga", "agahe", "gufatira igihe", "gufatira", "packages zanyu", "bookinga", "bukinga", "angae",
]

PRICE_INVITE_MESSAGES = {
    "en": (
        "Great !😊 Well, prices depend on what you would like "
        "included in your session.\n\n"
        "To give you an exact price, I have a few quick questions — "
        "it only takes about 1 minute!\n\n"
        "Shall we start? 😊"
    ),
    "fr": (
        "Bonne question! 😊 Nos tarifs dépendent de ce que vous souhaitez "
        "inclure dans votre séance.\n\n"
        "Pour vous donner un prix exact, j'ai quelques questions rapides — "
        "cela prend environ 1 minute!\n\n"
        "On commence? 😊"
    ),
    "rw": (
        "Ni ikibazo cyiza! 😊 Ibiciro byacu biterwa n'ibyo mushaka "
        "no guterwa muri session yanyu.\n\n"
        "Kugira ngo mbabwire igiciro nyacyo, mfite ibibazo bike byihuse — "
        "birengera nka minuto imwe!\n\n"
        "Twatangira? 😊"
    ),
}

BASE_PACKAGES_NO_EXTRAS = {
    "en": (
        "No problem! Here are our packages 😊\n\n"
        "Studio Session:\n"
        "Starter — 50,000 RWF | 1h | 8 edited photos + all unedited\n"
        "Silver — 70,000 RWF | 1h | 12 edited photos + all unedited\n"
        "Gold — 100,000 RWF | 1.5h | 18 edited photos + all unedited\n\n"
        "Home Session:\n"
        "Premium — 200,000 RWF | 2h | 30 edited photos + all unedited\n\n"
        "You can add extras: 2 A5 frames (+20k), cake (+30k), "
        "video (+29k), or cake+video bundle (+50k).\n\n"
        "Which one interests you? 😊"
    ),
    "fr": (
        "Pas de problème! Voici nos forfaits 😊\n\n"
        "Séance Studio:\n"
        "Starter — 50,000 RWF | 1h | 8 photos éditées + toutes non éditées\n"
        "Silver — 70,000 RWF | 1h | 12 photos éditées + toutes non éditées\n"
        "Gold — 100,000 RWF | 1.5h | 18 photos éditées + toutes non éditées\n\n"
        "Séance à Domicile:\n"
        "Premium — 200,000 RWF | 2h | 30 photos éditées + toutes non éditées\n\n"
        "Vous pouvez ajouter: 2 cadres A5 (+20k), gâteau (+30k), "
        "vidéo (+29k), ou bundle gâteau+vidéo (+50k).\n\n"
        "Lequel vous intéresse? 😊"
    ),
    "rw": (
        "Ntakibazo! Dore packages zacu 😊\n\n"
        "Session ya Studio:\n"
        "Starter — 50,000 RWF | Isaha 1 | Amafoto 8 atunganijwe + yose adatunganijwe\n"
        "Silver — 70,000 RWF | Isaha 1 | Amafoto 12 atunganijwe + yose adatunganijwe\n"
        "Gold — 100,000 RWF | Isaha 1.5 | Amafoto 18 atunganijwe + yose adatunganijwe\n\n"
        "Session mu Rugo:\n"
        "Premium — 200,000 RWF | Amasaha 2 | Amafoto 30 atunganijwe + yose adatunganijwe\n\n"
        "Mwongera: ama cadre 2 ya A5 (+20k), cake (+30k), "
        "video (+29k), cyangwa cake+video hamwe (+50k).\n\n"
        "Ni izihe mushaka? 😊"
    ),
}

# --- MAIN ORCHESTRATOR ---

def handle_instagram_message(sender_id: str, message_text: str, message_id: str, timestamp_ms: int):
    """
    COMPLETE ORCHESTRATOR — v2.1 with informational question fix.
    """
    try:
        # ── 1. Onboard ────────────────────────────────────────────────────
        from services.client_service import onboard_client
        client, journey, _, is_new = onboard_client(
            wa_number=f"ig_{sender_id}"[:20],
            name=f"IG_{sender_id[:8]}",
            ig_user_id=sender_id,
        )

        # ── 2. Fetch real name if placeholder ─────────────────────────────
        if client.name.startswith("IG_"):
            try:
                from services.instagram_service import get_user_profile
                profile = get_user_profile(sender_id)
                if profile and profile.get("name"):
                    client.name = profile["name"]
                    client.save(update_fields=["name", "updated_at"])
            except Exception:
                pass

        # ── 3. Language detection and locking ─────────────────────────────
        lang = _detect_and_lock_language(client, message_text or "")

        # ── 4. Get or create Instagram conversation ───────────────────────
        conversation = _get_or_create_conversation(client)

        # ── 5. Save inbound message ───────────────────────────────────────
        _save_inbound(client, conversation, message_id, message_text)

        # ── 6. Human takeover check ───────────────────────────────────────
        if journey.human_takeover:
            logger.info("Human takeover active for IG %s — AI silent", sender_id)
            conversation.touch()
            return

        # ── 7. Mark as seen ───────────────────────────────────────────────
        try:
            mark_as_seen(sender_id)
        except Exception:
            pass

        # ── 8. Initialize flow_mode if new ────────────────────────────────
        if not journey.flow_mode or is_new:
            journey.flow_mode = "new"

        # Initialize discovery state if empty
        if not journey.discovery_state:
            journey.discovery_state = {
                "photo_type": None,
                "session_type": None,
                "frames": None,
                "cake": None,
                "video": None,
            }
            journey.save(update_fields=["discovery_state", "flow_mode", "updated_at"])

        flow_mode = journey.flow_mode
        text_lower = (message_text or "").lower()

        # ── 9. INFORMATIONAL QUESTIONS ────────────────────────────────────
        # Answer first, then append flow prompt if needed.
        info_answer = None
        
        # Location
        if any(sig in text_lower for sig in LOCATION_SIGNALS):
            info_answer = LOCATION_RESPONSES.get(lang, LOCATION_RESPONSES["en"])
        
        # Frames
        elif any(sig in text_lower for sig in ["frame","frames", "cadre", "ama cadre", "amaframe", "ama frame"]):
            FRAME_ANSWERS = {
                "en": "Our A5 photo frames are beautiful high-quality prints in a classic frame, perfect for home decor! 🖼️ For more details or/and If i didn't answer your question correctly, Kindly request to talk to a real person",
                "fr": "Nos cadres photo A5 sont des impressions de haute qualité, parfaits pour la décoration! 🖼️ Pour plus de détails, ou si ma réponse ne vous a pas satisfait, demandez à parler à un agent",
                "rw": "Ama cadre yacu ya A5 ni meza cyane kandi akomeye, akaba meza cyane mu rugo! 🖼️ Kubona ibisobanuro birambuye cyangwa niba ntasubije ikibazo cyawe neza, ndagusaba kugisha inama umuntu nyakuri.",
            }
            info_answer = FRAME_ANSWERS.get(lang, FRAME_ANSWERS["en"])

        # Cake
        elif any(sig in text_lower for sig in ["cake","keke", "gâteau", "gateau", "umutsima"]):
            CAKE_ANSWERS = {
                "en": "Our birthday cakes are perfectly sized for a celebration! 🎂, For more details or/and If i didn't answer your question correctly, Kindly request to talk to a real person",
                "fr": "Nos gâteaux d'anniversaire sont parfaitement dimensionnés pour une célébration! 🎂, Pour plus de détails, ou si ma réponse ne vous a pas satisfait, demandez à parler à un agent",
                "rw": "Umutsima (cake) yacu irashyitse kugira ngo irahire icyo gihe! 🎂, Kubona ibisobanuro birambuye cyangwa niba ntasubije ikibazo cyawe neza, ndagusaba kugisha inama umuntu nyakuri.",
            }
            info_answer = CAKE_ANSWERS.get(lang, CAKE_ANSWERS["en"])

        # Video
        elif any(sig in text_lower for sig in ["video", "videwo", "vidéo", "duration", "how long", "amasegonda", "iminota"]):
            VIDEO_ANSWERS = {
                "en": "Our highlight videos are short clips of 15 to 30 seconds of your best moments! 🎬 For more details or/and If i didn't answer your question correctly, Kindly request to talk to a real person",
                "fr": "Nos vidéos souvenirs sont de courts clips de 15 à 30 secondes de vos meilleurs moments! 🎬 Pour plus de détails, ou si ma réponse ne vous a pas satisfait, demandez à parler à un agent",
                "rw": "Video zacu ngufi ziba zifite amasegonda 15 kugeza kuri 30 y'ibihe byiza mwagize! 🎬 Kubona ibisobanuro birambuye cyangwa niba ntasubije ikibazo cyawe neza, ndagusaba kugisha inama umuntu nyakuri.",
            }
            info_answer = VIDEO_ANSWERS.get(lang, VIDEO_ANSWERS["en"])

        if info_answer:
            if flow_mode == "discovery":
                # Try to process the answer if they gave one in the same message
                _process_discovery_answer(journey, message_text, lang)
                ds = journey.discovery_state
                next_q = _get_next_discovery_question(ds, lang)
                if next_q:
                    response_text = f"{info_answer}\n\n{next_q['question']}"
                else:
                    package_text = _build_package_presentation(ds, lang)
                    response_text = f"{info_answer}\n\n{package_text}"
            elif flow_mode == "packages_shown":
                reprompt = {"en": "Which package feels right for you? 😊", "fr": "Lequel vous convient? 😊", "rw": "Ni iyihe mwifuza? 😊"}
                response_text = f"{info_answer}\n\n{reprompt.get(lang, reprompt['en'])}"
            elif flow_mode == "awaiting_datetime":
                reprompt = {"en": "What date and time would you prefer? 📅", "fr": "Quelle date et heure préférez-vous? 📅", "rw": "Ni ryari kandi isaha yingahe mushaka? 📅"}
                response_text = f"{info_answer}\n\n{reprompt.get(lang, reprompt['en'])}"
            else:
                response_text = info_answer

            send_text(sender_id, response_text)
            _save_outbound(client, conversation, response_text)
            conversation.touch()
            return

        # ── 10. WELCOME — first message or new flow ───────────────────────
        if flow_mode == "new":
            response_text = WELCOME_MESSAGES.get(lang, WELCOME_MESSAGES["en"])
            send_text(sender_id, response_text)
            _save_outbound(client, conversation, response_text)
            journey.flow_mode = "active"
            journey.save(update_fields=["flow_mode", "updated_at"])
            conversation.touch()
            return

        # ── 11. HUMAN TAKEOVER CHECK ──────────────────────────────────────
        TAKEOVER_SIGNALS = [
            "agent", "human", "real person", "speak to someone", "talk to someone",
            "umuntu", "umukozi", "vugana", "agent réel", "quelqu'un",
        ]
        if any(sig in text_lower for sig in TAKEOVER_SIGNALS):
            _activate_human_takeover(
                client, journey, conversation, sender_id, lang,
                reason="Client explicitly requested human agent"
            )
            return

        # ── 12. DISCOVERY FLOW ────────────────────────────────────────────
        if flow_mode == "discovery":
            answered = _process_discovery_answer(journey, message_text, lang)
            ds = journey.discovery_state

            if _is_discovery_complete(ds):
                package_text = _build_package_presentation(ds, lang)
                send_text(sender_id, package_text)
                _save_outbound(client, conversation, package_text)
                journey.flow_mode = "packages_shown"
                journey.save(update_fields=["flow_mode", "updated_at"])
                conversation.touch()
                return
            
            if answered:
                # Clear answer given, move to next question
                next_q = _get_next_discovery_question(ds, lang)
                if next_q:
                    send_text(sender_id, next_q["question"])
                    _save_outbound(client, conversation, next_q["question"])
                    conversation.touch()
                    return
            
            # If not answered clearly (answered=False), allow fallthrough to Step 17 (AI Fallback)
            # The AI will answer any specific question and repeat the current discovery question.

        # ── 13. PACKAGES SHOWN — wait for choice or extra adjustment ─────
        if flow_mode == "packages_shown":
            recalc_needed = _check_extra_adjustment(message_text, journey, lang)
            if recalc_needed:
                ds = journey.discovery_state
                package_text = _build_package_presentation(ds, lang)
                send_text(sender_id, package_text)
                _save_outbound(client, conversation, package_text)
                conversation.touch()
                return

            chosen = _detect_package_choice(message_text)
            if chosen:
                ds = journey.discovery_state or {}
                extras_cost = _calculate_extras_cost(ds)
                base = {"starter": 50000, "silver": 70000, "gold": 100000, "premium": 200000}
                total = base.get(chosen, 0) + extras_cost

                CHOICE_MESSAGES = {
                    "en": f"Excellent choice! 🎉 You have selected the {chosen.title()} Package at {total:,} RWF.\n\nWhat date and time would you prefer for your session? 📅\n(We are open Monday to Sunday, 9 AM to 6 PM)",
                    "fr": f"Excellent choix! 🎉 Vous avez sélectionné le forfait {chosen.title()} à {total:,} RWF.\n\nQuelle date et heure préférez-vous pour votre séance? 📅\n(Nous sommes ouverts lundi au dimanche, 9h à 18h)",
                    "rw": f"Amahitamo meza! 🎉 Mwahisemo {chosen.title()} Package kuri {total:,} RWF.\n\nNi ryari kandi isaha yingahe mushaka session yanyu? 📅\n(Turi hafi kuva ku wa Mbere kugeza ku Ku cyumweru, 9AM-6PM)",
                }
                response_text = CHOICE_MESSAGES.get(lang, CHOICE_MESSAGES["en"])
                send_text(sender_id, response_text)
                _save_outbound(client, conversation, response_text)
                journey.selected_package = chosen
                journey.flow_mode = "awaiting_datetime"
                journey.save(update_fields=["selected_package", "flow_mode", "updated_at"])
                conversation.touch()
                return

        # ── 14. AWAITING DATE/TIME ────────────────────────────────────────
        if flow_mode == "awaiting_datetime":
            DATE_SIGNALS = [
                "tomorrow", "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "january", "february", "march",
                "april", "may", "june", "july", "august", "september",
                "october", "november", "december",
                "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
                "demain", "semaine", "next week", "weekend",
                "ejo", "ku cyumweru", "wakati",
            ] + [str(i) for i in range(1, 32)]

            if any(sig in text_lower for sig in DATE_SIGNALS) or any(
                c.isdigit() for c in (message_text or "")
            ):
                ACK_MESSAGES = {
                    "en": "Thank you! 😊 We have noted your preferred date. Our team will check availability and get back to you shortly to confirm. 🙏",
                    "fr": "Merci! 😊 Nous avons noté votre date préférée. Notre équipe vérifiera les disponibilités et vous confirmera bientôt. 🙏",
                    "rw": "Murakoze! 😊 Twabikuye itariki mushaka. Itsinda ryacu rizasuzuma ubusabe kandi rizosubiza vuba. 🙏",
                }
                response_text = ACK_MESSAGES.get(lang, ACK_MESSAGES["en"])
                send_text(sender_id, response_text)
                _save_outbound(client, conversation, response_text)

                _activate_human_takeover(
                    client, journey, conversation, sender_id, lang,
                    reason=f"Client provided date: {message_text[:100] if message_text else '[media]'}",
                    send_message=False,
                )
                conversation.touch()
                return

        # ── 15. PRICE INTENT ──────────────────────────────────────────────
        if flow_mode in ("active", "packages_shown") or (
            flow_mode not in ("discovery", "awaiting_datetime", "await_confirm", "human_takeover")
        ):
            if any(sig in text_lower for sig in PRICE_SIGNALS):
                REFUSAL_SIGNALS = ["just show", "just tell", "directly", "straight", "skip", "no questions", "montre juste", "directement", "nta bibazo", "binyereke gusa"]
                if any(sig in text_lower for sig in REFUSAL_SIGNALS):
                    response_text = BASE_PACKAGES_NO_EXTRAS.get(lang, BASE_PACKAGES_NO_EXTRAS["en"])
                    send_text(sender_id, response_text)
                    _save_outbound(client, conversation, response_text)
                    journey.flow_mode = "packages_shown"
                    journey.save(update_fields=["flow_mode", "updated_at"])
                    conversation.touch()
                    return
                else:
                    invite = PRICE_INVITE_MESSAGES.get(lang, PRICE_INVITE_MESSAGES["en"])
                    send_text(sender_id, invite)
                    _save_outbound(client, conversation, invite)
                    first_q = _get_next_discovery_question(journey.discovery_state or {}, lang)
                    if first_q:
                        send_text(sender_id, first_q["question"])
                        _save_outbound(client, conversation, first_q["question"])
                    journey.flow_mode = "discovery"
                    journey.save(update_fields=["flow_mode", "updated_at"])
                    conversation.touch()
                    return

        # ── 16. DISCOUNT REFUSAL ──────────────────────────────────────────
        DISCOUNT_SIGNALS = ["discount", "reduce", "cheaper", "lower price", "negotiate", "réduction", "moins cher", "baisser", "négocier", "gutanga igiciro gito", "gucunga", "discounts", "expensive", "too much", "can't afford","ibiciro bito", "meshi cyane", "menshi", "menshi","menshi cyane",]
        if any(sig in text_lower for sig in DISCOUNT_SIGNALS):
            discount_count = journey.discovery_state.get("_discount_count", 0) + 1
            journey.discovery_state["_discount_count"] = discount_count
            journey.save(update_fields=["discovery_state", "updated_at"])

            if discount_count >= 3:
                _activate_human_takeover(client, journey, conversation, sender_id, lang, reason="Client insisted on discount 3+ times")
                return

            DISCOUNT_RESPONSES = {
                "en": ("I completely understand! 😊 Our packages are designed to offer the best value for the quality we deliver. Our prices are fixed to ensure we always deliver our best work. 🙏" if discount_count == 1 else "I truly appreciate your interest! 😊 Unfortunately our pricing is fixed and we are unable to offer discounts. Would you like to proceed with a package? 🙏"),
                "fr": ("Je comprends tout à fait! 😊 Nos forfaits sont conçus pour offrir le meilleur rapport qualité-prix. Nos prix sont fixes pour garantir notre meilleur travail. 🙏" if discount_count == 1 else "J'apprécie vraiment votre intérêt! 😊 Malheureusement nos tarifs sont fixes et nous ne pouvons pas offrir de réductions. Souhaitez-vous procéder avec un forfait? 🙏"),
                "rw": ("Ndabizi! 😊 Packages zacu zagenywe kugira ngo zitange ubwiza bwuzuye. Ibiciro byacu ni bya ngombwa kugira ngo tubashe gutanga ubwiza bwacu. 🙏" if discount_count == 1 else "Ndashimira interest yanyu! 😊 Ntabwo dushobora gutanga discount. Ariko packages zacu ziri mu ibiciro byiza. Mushaka gukomeza na package? 🙏"),
            }
            response_text = DISCOUNT_RESPONSES.get(lang, DISCOUNT_RESPONSES["en"])
            send_text(sender_id, response_text)
            _save_outbound(client, conversation, response_text)
            conversation.touch()
            return

        # ── 17. AI FALLBACK ───────────────────────────────────────────────
        rag_context = retrieve_context(query=message_text or "", journey_phase=journey.phase, language=lang)
        next_q = _get_next_discovery_question(journey.discovery_state or {}, lang)
        system_prompt = build_instagram_system_prompt(
            language=lang, client_name=client.name, flow_mode=flow_mode,
            discovery_state=journey.discovery_state, rag_context=rag_context,
            next_question=next_q["question"] if next_q else ""
        )
        recent_msgs = _get_recent_messages(conversation)
        messages = build_messages_context(conversation_summary=None, recent_messages=recent_msgs[:-1] if recent_msgs else [], new_message=message_text or "[media]")
        ai_response = call_openai(system_prompt=system_prompt, messages=messages)

        if ai_response.ok and ai_response.text.strip():
            from services.client_service import record_tokens
            record_tokens(client, conversation, ai_response.input_tokens, ai_response.output_tokens)
            send_text(sender_id, ai_response.text)
            _save_outbound(client, conversation, ai_response.text, model=ai_response.model, tokens_input=ai_response.input_tokens, tokens_output=ai_response.output_tokens)

        conversation.touch()
        client.update_last_contact()

    except Exception as e:
        logger.exception("Error in handle_instagram_message for %s: %s", sender_id, e)

# --- HELPER FUNCTIONS ---

def _detect_and_lock_language(client: Client, message_text: str) -> str:
    if client.language_locked and client.language: return client.language
    from utils.language import detect_language
    detected = detect_language(message_text)
    text_lower = message_text.lower()
    if any(signal in text_lower for signal in RW_SIGNALS): detected = "rw"
    client.language = detected
    client.language_locked = True
    client.save(update_fields=["language", "language_locked", "updated_at"])
    return detected

def _get_next_discovery_question(discovery_state: dict, lang: str) -> Optional[dict]:
    questions = DISCOVERY_QUESTIONS.get(lang, DISCOVERY_QUESTIONS["en"])
    for q in questions:
        if discovery_state.get(q["key"]) is None: return q
    return None

def _is_discovery_complete(discovery_state: dict) -> bool:
    return all(discovery_state.get(k) is not None for k in ["photo_type", "session_type", "frames", "cake", "video"])

def _extract_yes_no(text: str) -> Optional[bool]:
    text = text.lower().strip()
    YES = ["yes", "yeah", "yep", "sure", "ok", "okay", "oui", "yego", "ndashaka", "twaze", "ntakibazo"]
    NO = ["no", "nope", "not", "without", "skip", "non", "oya", "hoya", "ntabwo", "nta"]
    for s in YES:
        if s in text: return True
    for s in NO:
        if s in text: return False
    return None

def _process_discovery_answer(journey: JourneyState, message_text: str, lang: str) -> bool:
    ds = journey.discovery_state or {}
    text_lower = (message_text or "").lower()
    for key in ["photo_type", "session_type", "frames", "cake", "video"]:
        if ds.get(key) is None:
            if key == "photo_type":
                if any(x in text_lower for x in ["family", "famille", "umuryango"]): ds["photo_type"] = "family"
                else: ds["photo_type"] = "child"
            elif key == "session_type":
                if any(x in text_lower for x in ["home", "house", "rugo", "domicile", "maison"]): ds["session_type"] = "home"
                else: ds["session_type"] = "studio"
            else:
                answer = _extract_yes_no(message_text)
                if answer is None: return False
                ds[key] = answer
            break
    journey.discovery_state = ds
    journey.save(update_fields=["discovery_state", "updated_at"])
    return True

def _detect_package_choice(message_text: str) -> Optional[str]:
    text_lower = (message_text or "").lower()
    if any(x in text_lower for x in ["starter", "50"]): return "starter"
    if any(x in text_lower for x in ["silver", "70"]): return "silver"
    if any(x in text_lower for x in ["gold", "100"]): return "gold"
    if any(x in text_lower for x in ["premium", "200"]): return "premium"
    return None

def _check_extra_adjustment(message_text: str, journey: JourneyState, lang: str) -> bool:
    text_lower = (message_text or "").lower()
    ds = journey.discovery_state or {}
    changed = False
    if "remove video" in text_lower or "sans video" in text_lower: ds["video"] = False; changed = True
    elif "add video" in text_lower or "avec video" in text_lower: ds["video"] = True; changed = True
    if "remove cake" in text_lower or "sans gateau" in text_lower: ds["cake"] = False; changed = True
    elif "add cake" in text_lower or "avec gateau" in text_lower: ds["cake"] = True; changed = True
    if "remove frame" in text_lower or "sans cadre" in text_lower: ds["frames"] = False; changed = True
    elif "add frame" in text_lower or "avec cadre" in text_lower: ds["frames"] = True; changed = True
    if changed:
        journey.discovery_state = ds
        journey.save(update_fields=["discovery_state", "updated_at"])
    return changed

def _calculate_extras_cost(ds: dict) -> int:
    cost = 0
    if ds.get("frames"): cost += 20000
    if ds.get("cake") and ds.get("video"): cost += 50000
    elif ds.get("cake"): cost += 30000
    elif ds.get("video"): cost += 29000
    return cost

def _activate_human_takeover(client, journey, conversation, sender_id, lang, reason="Human takeover", send_message=True):
    if send_message:
        msg = {"en": "Of course! 😊 One of our team members will be with you shortly. 🙏", "fr": "Bien sûr! 😊 Un membre de notre équipe sera avec vous bientôt. 🙏", "rw": "Yego rwose! 😊 Umwe mu bakozi bacu aragufasha vuba. 🙏"}.get(lang, "Of course! 😊")
        send_text(sender_id, msg); _save_outbound(client, conversation, msg)
    journey.human_takeover = True; journey.takeover_reason = reason; journey.flow_mode = "human_takeover"
    journey.save(update_fields=["human_takeover", "takeover_reason", "flow_mode", "updated_at"])
    from apps.instagram.models import InstagramApprovalQueue
    InstagramApprovalQueue.objects.create(client=client, conversation=conversation, action=InstagramApprovalQueue.ApprovalAction.ESCALATE, ai_suggestion=f"[Instagram] Human takeover: {reason}", ai_reasoning=reason, expires_at=timezone.now() + timezone.timedelta(hours=72))
    try:
        from apps.dashboard.views import send_push_notification
        send_push_notification(title=f"📸 Instagram — {client.name or sender_id}", body=reason[:80], url=f"/?client={client.pk}")
    except Exception: pass

def _build_package_presentation(discovery_state: dict, lang: str) -> str:
    extras_cost = _calculate_extras_cost(discovery_state)
    extras_lines = []
    if discovery_state.get("frames"): extras_lines.append({"en": "2 A5 Photo Frames", "fr": "2 Cadres Photo A5", "rw": "Ama cadre 2 ya A5"}[lang])
    if discovery_state.get("cake") and discovery_state.get("video"): extras_lines.append({"en": "Birthday Cake + Highlight Video", "fr": "Gâteau + Vidéo Souvenir", "rw": "Cake + Video"}[lang])
    elif discovery_state.get("cake"): extras_lines.append({"en": "Birthday Cake", "fr": "Gâteau d'Anniversaire", "rw": "Cake ya Aniverseri"}[lang])
    elif discovery_state.get("video"): extras_lines.append({"en": "Highlight Video (15-30 sec)", "fr": "Vidéo Souvenir (15-30 sec)", "rw": "Video Ngufi (15-30 sec)"}[lang])
    includes_str = ", ".join(extras_lines) if extras_lines else ""
    session_type = discovery_state.get("session_type", "studio")
    if session_type == "home":
        total = 200000 + extras_cost
        text = {"en": f"🏆 Premium Package — {total:,} RWF\n2h Home Session\nDelivery: 30 Edited Photos\n", "fr": f"🏆 Premium Package — {total:,} RWF\n2h Séance à Domicile\nLivraison: 30 Photos Éditées\n", "rw": f"🏆 Premium Package — {total:,} RWF\nAmasaha 2 mu Rugo\nKubaboherereza: Amafoto 30 atunganijwe\n"}[lang]
        if includes_str: text += {"en": "Includes: ", "fr": "Inclus: ", "rw": "Harimo: "}[lang] + includes_str + "\n"
        text += {"en": "\nAnd a special gift for the child!\nWhich package feels right? 😊", "fr": "\nEt un cadeau spécial pour l'enfant!\nLequel vous convient? 😊", "rw": "\nKandi impano yihariye y'umwana!\nNi iyihe mwifuza? 😊"}[lang]
        return text
    packages = [{"name": "Starter", "base": 50000, "emoji": "🥉", "duration": "1h", "photos": 8}, {"name": "Silver", "base": 70000, "emoji": "🥈", "duration": "1h", "photos": 12}, {"name": "Gold", "base": 100000, "emoji": "🥇", "duration": "1.5h", "photos": 18}]
    text = {"en": "Here are the 3 packages built just for you!\n\n", "fr": "Voici les 3 forfaits faits pour vous!\n\n", "rw": "Dore packages 3 zakubakiwe!\n\n"}[lang]
    for pkg in packages:
        total = pkg["base"] + extras_cost
        text += f"{pkg['emoji']} {pkg['name']} Package — {total:,} RWF\n"
        text += f"{pkg['duration']} " + {"en": "Studio Session", "fr": "Séance Studio", "rw": "Session ya Studio"}[lang] + "\n"
        text += {"en": f"Delivery: {pkg['photos']} Edited Photos", "fr": f"Livraison: {pkg['photos']} Photos Éditées", "rw": f"Kubaboherereza: Amafoto {pkg['photos']} atunganijwe"}[lang] + "\n"
        if includes_str: text += {"en": "Includes: ", "fr": "Inclus: ", "rw": "Harimo: "}[lang] + includes_str + "\n"
        text += "\n"
    text += {"en": "And a special gift for the child!\nWhich package feels right? 😊", "fr": "Et un cadeau spécial pour l'enfant!\nLequel vous convient? 😊", "rw": "Kandi impano yihariye y'umwana!\nNi iyihe mwifuza? 😊"}[lang]
    return text

def build_instagram_system_prompt(language: str, client_name: str, flow_mode: str, discovery_state: dict, rag_context: str, next_question: str = "") -> str:
    lang_instruction = LANG_INSTRUCTIONS.get(language, LANG_INSTRUCTIONS["en"])
    if flow_mode == "discovery" and next_question:
        flow_instruction = f"The client is in a discovery session. If they asked a question, answer it using the knowledge base, then repeat this discovery question: {next_question}"
    elif flow_mode == "packages_shown": flow_instruction = "Packages shown. Wait for choice. If they ask to add/remove extras, say you will recalculate."
    elif flow_mode == "awaiting_datetime": flow_instruction = "Package chosen. Wait for date/time (Mon-Sat, 9-6)."
    elif flow_mode in ("await_confirm", "human_takeover"): flow_instruction = "Human agent handling. STAY SILENT. Return empty string."
    else: flow_instruction = "Listen to client. If location -> give address. If price -> invite to discovery. If question -> answer from knowledge base."
    return f"""You are Julie, AI assistant for KP Kids Studio, Kigali.
{lang_instruction}
Persona: Julie, warm, helpful, emoji-friendly. No markdown. Max 4 sentences.
Pricing: Studio (Starter 50k, Silver 70k, Gold 100k), Home (Premium 200k). Extras: Frames 20k, Cake 30k, Video 29k (15-30 SECONDS).
Rules: No markdown. No buttons. No discounts. No minutes for video (only seconds).
Current State: {client_name}, Mode: {flow_mode}
Instruction: {flow_instruction}
Context: {rag_context}"""

def _build_discovery_context(ds: dict) -> str:
    steps = []
    for k in ["photo_type", "session_type", "frames", "cake", "video"]:
        v = ds.get(k); val = "Pending" if v is None else ("Yes" if v is True else ("No" if v is False else v))
        steps.append(f"{k}: {val}")
    return "Progress: " + ", ".join(steps)

def _get_or_create_conversation(client) -> InstagramConversation:
    conv = InstagramConversation.objects.filter(client=client, is_open=True).first()
    if not conv: conv = InstagramConversation.objects.create(client=client)
    return conv

def _save_inbound(client, conversation, mid, text):
    msg, _ = InstagramMessage.objects.get_or_create(ig_mid=mid, defaults={"conversation": conversation, "client": client, "direction": "inbound", "content": text or "[media]", "timestamp": timezone.now()})
    return msg

def _save_outbound(client, conversation, text, model="", tokens_input=0, tokens_output=0):
    return InstagramMessage.objects.create(ig_mid=f"out_{uuid.uuid4().hex[:12]}", conversation=conversation, client=client, direction="outbound", content=text, model_used=model, tokens_input=tokens_input, tokens_output=tokens_output, timestamp=timezone.now())

def _get_recent_messages(conversation) -> list:
    msgs = InstagramMessage.objects.filter(conversation=conversation).order_by("-timestamp")[:15]
    result = []
    for m in reversed(msgs): result.append({"role": "user" if m.direction == "inbound" else "assistant", "content": m.content})
    return result
