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
from apps.instagram.models import InstagramConversation, InstagramMessage
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
            "question": (
                "Would you like to add 2 beautiful A5 photo frames to your package? 🖼️ (+20,000 RWF)\n\n"
                "For more details about the frames, feel free to contact us on WhatsApp: +250795820170 😊"
            ),
        },
        {
            "key": "cake",
            "question": (
                "How about adding a birthday cake? 🎂 (+30,000 RWF)\n\n"
                "It is perfectly sized for a celebration!"
            ),
        },
        {
            "key": "video",
            "question": (
                "Would you like a short highlight video of the session? 🎬 "
                "(15 to 30 seconds of your best moments — +29,000 RWF)\n\n"
                "Or get the cake + video bundle together for only +50,000 RWF "
                "instead of +59,000 RWF separately!\n\n"
                "For more details: +250795820170 😊"
            ),
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
            "question": (
                "Souhaitez-vous ajouter 2 beaux cadres photo A5 à votre forfait? 🖼️ (+20,000 RWF)\n\n"
                "Pour plus de détails sur les cadres, contactez-nous sur WhatsApp: +250795820170 😊"
            ),
        },
        {
            "key": "cake",
            "question": "Et un gâteau d'anniversaire? 🎂 (+30,000 RWF — parfaitement dimensionné pour une célébration!)",
        },
        {
            "key": "video",
            "question": (
                "Souhaitez-vous une courte vidéo souvenir? 🎬 "
                "(15 à 30 secondes de vos meilleurs moments — +29,000 RWF)\n\n"
                "Ou le bundle gâteau + vidéo pour seulement +50,000 RWF au lieu de +59,000 RWF!\n\n"
                "Pour plus de détails: +250795820170 😊"
            ),
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
            "question": (
                "Murifuza kongereramo ama cadre 2 ya A5 muri package yanyu? 🖼️ (+20,000 RWF)\n\n"
                "Kugira amakuru arambuye yerekeye ama cadre, "
                "mwaduhamagara kuri WhatsApp: +250795820170 😊"
            ),
        },
        {
            "key": "cake",
            "question": "Murifuza kongereramo cake ya aniverseri? 🎂 (+30,000 RWF — irashyitse kugira ngo irahire icyo gihe!)",
        },
        {
            "key": "video",
            "question": (
                "Murifuza video ngufi ya session yanyu? 🎬 "
                "(Amasegonda 15 kugeza 30 — +29,000 RWF)\n\n"
                "Cyangwa murifuza cake na video hamwe kuri +50,000 RWF "
                "aho kuba +59,000 RWF uguze veru!\n\n"
                "Kugira amakuru: +250795820170 😊"
            ),
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
    # English
    "where", "location", "address", "find you", "how to get",
    "directions", "map", "located",
    # French
    "où", "adresse", "localisation", "comment venir", "trouver",
    "emplacement",
    # Kinyarwanda
    "aho muri", "aho muba", "aho", "murari he", "adresse",
]

LOCATION_RESPONSES = {
    "en": (
        "We are located in Kicukiro, BRGD Plaza, opposite IPRC, "
        "next to SAWA CITY Supermarket, Kigali. 📍\n\n"
        "We are open Monday to Saturday, 9 AM to 6 PM.\n\n"
        "Is there anything else I can help you with? 😊"
    ),
    "fr": (
        "Nous sommes situés à Kicukiro, BRGD Plaza, en face de l'IPRC, "
        "à côté du Supermarché SAWA CITY, Kigali. 📍\n\n"
        "Nous sommes ouverts du lundi au samedi, de 9h à 18h.\n\n"
        "Puis-je vous aider avec autre chose? 😊"
    ),
    "rw": (
        "Turi i Kicukiro, BRGD Plaza, imbere y'IPRC, "
        "hafi ya Supermarché SAWA CITY, Kigali. 📍\n\n"
        "Turi hafi kuva ku wa Mbere kugeza ku wa Gatanu, "
        "kuva saa tatu z'igitondo kugeza saa cyenda nijoro.\n\n"
        "Hari ikindi mbasaba? 😊"
    ),
}

PRICE_SIGNALS = [
    # English
    "price", "cost", "how much", "package", "rates", "pricing",
    "afford", "expensive", "cheap", "fees",
    # French
    "prix", "coût", "combien", "forfait", "tarif", "cher",
    # Kinyarwanda
    "ibiciro", "ingahe", "package", "amafaranga", "agahe",
]

PRICE_INVITE_MESSAGES = {
    "en": (
        "Great question! 😊 Our prices depend on what you would like "
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
    COMPLETE ORCHESTRATOR — replaces the buggy version.
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
        ds = journey.discovery_state or {}

        # ── 9. LOCATION INTENT — highest priority, always answer ──────────
        text_lower = (message_text or "").lower()
        if any(sig in text_lower for sig in LOCATION_SIGNALS):
            response_text = LOCATION_RESPONSES.get(lang, LOCATION_RESPONSES["en"])
            send_text(sender_id, response_text)
            _save_outbound(client, conversation, response_text)
            conversation.touch()
            return  # Do not change flow_mode

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
            # Figure out which question was just answered
            answered = _process_discovery_answer(journey, message_text, lang)
            ds = journey.discovery_state  # refreshed

            if _is_discovery_complete(ds):
                # ALL DONE — present packages immediately
                package_text = _build_package_presentation(ds, lang)
                send_text(sender_id, package_text)
                _save_outbound(client, conversation, package_text)
                journey.flow_mode = "packages_shown"
                journey.save(update_fields=["flow_mode", "updated_at"])
                conversation.touch()
                return
            else:
                # Ask next question
                next_q = _get_next_discovery_question(ds, lang)
                if next_q:
                    send_text(sender_id, next_q["question"])
                    _save_outbound(client, conversation, next_q["question"])
                    conversation.touch()
                    return

        # ── 13. PACKAGES SHOWN — wait for choice or extra adjustment ─────
        if flow_mode == "packages_shown":
            # Check if client wants to remove/add extras
            recalc_needed = _check_extra_adjustment(message_text, journey, lang)
            if recalc_needed:
                ds = journey.discovery_state
                package_text = _build_package_presentation(ds, lang)
                send_text(sender_id, package_text)
                _save_outbound(client, conversation, package_text)
                conversation.touch()
                return

            # Check if client chose a package
            chosen = _detect_package_choice(message_text)
            if chosen:
                ds = journey.discovery_state or {}
                extras_cost = _calculate_extras_cost(ds)
                base = {"starter": 50000, "silver": 70000, "gold": 100000, "premium": 200000}
                total = base.get(chosen, 0) + extras_cost

                CHOICE_MESSAGES = {
                    "en": f"Excellent choice! 🎉 You have selected the {chosen.title()} Package at {total:,} RWF.\n\nWhat date and time would you prefer for your session? 📅\n(We are open Monday to Saturday, 9 AM to 6 PM)",
                    "fr": f"Excellent choix! 🎉 Vous avez sélectionné le forfait {chosen.title()} à {total:,} RWF.\n\nQuelle date et heure préférez-vous pour votre séance? 📅\n(Nous sommes ouverts lundi au samedi, 9h à 18h)",
                    "rw": f"Amahitamo meza! 🎉 Mwahisemo {chosen.title()} Package kuri {total:,} RWF.\n\nNi ryari kandi isaha yingahe mushaka session yanyu? 📅\n(Turi hafi kuva ku wa Mbere kugeza ku wa Gatanu, 9AM-6PM)",
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
                "demain", "semaine", "next week",
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

                # Activate human takeover
                _activate_human_takeover(
                    client, journey, conversation, sender_id, lang,
                    reason=f"Client provided date: {message_text[:100] if message_text else '[media]'}",
                    send_message=False,  # already sent acknowledgment
                )
                conversation.touch()
                return

        # ── 15. PRICE INTENT in active/other modes ────────────────────────
        if flow_mode in ("active", "packages_shown") or (
            flow_mode not in ("discovery", "awaiting_datetime", "await_confirm", "human_takeover")
        ):
            if any(sig in text_lower for sig in PRICE_SIGNALS):
                # Check if client refuses discovery
                REFUSAL_SIGNALS = [
                    "just show", "just tell", "directly", "straight",
                    "skip", "no questions", "without questions",
                    "montre juste", "directement", "sans questions",
                    "nta bibazo", "binyereke gusa",
                ]
                if any(sig in text_lower for sig in REFUSAL_SIGNALS):
                    response_text = BASE_PACKAGES_NO_EXTRAS.get(lang, BASE_PACKAGES_NO_EXTRAS["en"])
                    send_text(sender_id, response_text)
                    _save_outbound(client, conversation, response_text)
                    journey.flow_mode = "packages_shown"
                    journey.save(update_fields=["flow_mode", "updated_at"])
                    conversation.touch()
                    return
                else:
                    # Start discovery
                    invite = PRICE_INVITE_MESSAGES.get(lang, PRICE_INVITE_MESSAGES["en"])
                    send_text(sender_id, invite)
                    _save_outbound(client, conversation, invite)

                    # Ask first question immediately
                    first_q = _get_next_discovery_question(
                        journey.discovery_state or {}, lang
                    )
                    if first_q:
                        send_text(sender_id, first_q["question"])
                        _save_outbound(client, conversation, first_q["question"])

                    journey.flow_mode = "discovery"
                    journey.save(update_fields=["flow_mode", "updated_at"])
                    conversation.touch()
                    return

        # ── 16. DISCOUNT REFUSAL ──────────────────────────────────────────
        DISCOUNT_SIGNALS = [
            "discount", "reduce", "cheaper", "lower price", "negotiate",
            "réduction", "moins cher", "baisser", "négocier",
            "gutanga igiciro gito", "gucunga",
        ]
        if any(sig in text_lower for sig in DISCOUNT_SIGNALS):
            discount_count = journey.discovery_state.get("_discount_count", 0) + 1
            journey.discovery_state["_discount_count"] = discount_count
            journey.save(update_fields=["discovery_state", "updated_at"])

            if discount_count >= 3:
                _activate_human_takeover(
                    client, journey, conversation, sender_id, lang,
                    reason="Client insisted on discount 3+ times"
                )
                return

            DISCOUNT_RESPONSES = {
                "en": (
                    "I completely understand! 😊 Our packages are designed to offer "
                    "the best value for the quality we deliver — professional photos, "
                    "experienced team, and a special gift for your child included. "
                    "Our prices are fixed to ensure we always deliver our best work. 🙏"
                    if discount_count == 1 else
                    "I truly appreciate your interest! 😊 Unfortunately our pricing "
                    "is fixed and we are unable to offer discounts. However, our "
                    "packages are already priced competitively for the quality you get. "
                    "Would you like to proceed with a package? 🙏"
                ),
                "fr": (
                    "Je comprends tout à fait! 😊 Nos forfaits sont conçus pour offrir "
                    "le meilleur rapport qualité-prix — photos professionnelles, "
                    "équipe expérimentée et un cadeau spécial pour votre enfant. "
                    "Nos prix sont fixes pour garantir notre meilleur travail. 🙏"
                    if discount_count == 1 else
                    "J'apprécie vraiment votre intérêt! 😊 Malheureusement nos tarifs "
                    "sont fixes et nous ne pouvons pas offrir de réductions. "
                    "Nos forfaits sont déjà compétitifs pour la qualité offerte. "
                    "Souhaitez-vous procéder avec un forfait? 🙏"
                ),
                "rw": (
                    "Ndabizi! 😊 Packages zacu zagenywe kugira ngo zitange "
                    "ubwiza bwuzuye — amafoto y'inzobere, itsinda rikennye, "
                    "n'impano yihariye y'umwana. Ibiciro byacu ni bya ngombwa "
                    "kugira ngo tubashe gutanga ubwiza bwacu. 🙏"
                    if discount_count == 1 else
                    "Ndashimira interest yanyu! 😊 Ntabwo dushobora gutanga "
                    "discount. Ariko packages zacu ziri mu ibiciro byiza "
                    "ku bwiza uronka. Mushaka gukomeza na package? 🙏"
                ),
            }
            response_text = DISCOUNT_RESPONSES.get(lang, DISCOUNT_RESPONSES["en"])
            send_text(sender_id, response_text)
            _save_outbound(client, conversation, response_text)
            conversation.touch()
            return

        # ── 17. AI FALLBACK for everything else ───────────────────────────
        rag_context = retrieve_context(
            query=message_text or "",
            journey_phase=journey.phase,
            language=lang,
        )

        next_q = _get_next_discovery_question(ds, lang)
        system_prompt = build_instagram_system_prompt(
            language=lang,
            client_name=client.name,
            flow_mode=flow_mode,
            discovery_state=ds,
            rag_context=rag_context,
            next_question=next_q["question"] if next_q else "",
        )

        recent_msgs = _get_recent_messages(conversation)
        messages = build_messages_context(
            conversation_summary=None,
            recent_messages=recent_msgs[:-1] if recent_msgs else [],
            new_message=message_text or "[media]",
        )

        ai_response = call_openai(system_prompt=system_prompt, messages=messages)

        if ai_response.ok and ai_response.text.strip():
            from services.client_service import record_tokens
            record_tokens(client, conversation, ai_response.input_tokens, ai_response.output_tokens)
            send_text(sender_id, ai_response.text)
            _save_outbound(client, conversation, ai_response.text,
                          model=ai_response.model,
                          tokens_input=ai_response.input_tokens,
                          tokens_output=ai_response.output_tokens)

        conversation.touch()
        client.update_last_contact()

    except Exception as e:
        logger.exception("Error in handle_instagram_message for %s: %s", sender_id, e)

# --- HELPER FUNCTIONS ---

def _detect_and_lock_language(client: Client, message_text: str) -> str:
    """
    Detect language from message. Lock it on client.
    Kinyarwanda takes priority — if detected, always use rw.
    Once locked, never change.
    """
    if client.language_locked and client.language:
        return client.language

    from utils.language import detect_language
    detected = detect_language(message_text)

    text_lower = message_text.lower()
    if any(signal in text_lower for signal in RW_SIGNALS):
        detected = "rw"

    client.language = detected
    client.language_locked = True
    client.save(update_fields=["language", "language_locked", "updated_at"])
    return detected

def _get_next_discovery_question(discovery_state: dict, lang: str) -> Optional[dict]:
    """Returns next unanswered question or None if all done."""
    questions = DISCOVERY_QUESTIONS.get(lang, DISCOVERY_QUESTIONS["en"])
    for q in questions:
        if discovery_state.get(q["key"]) is None:
            return q
    return None

def _is_discovery_complete(discovery_state: dict) -> bool:
    required = ["photo_type", "session_type", "frames", "cake", "video"]
    return all(
        discovery_state.get(k) is not None
        for k in required
    )

def _extract_yes_no(text: str) -> Optional[bool]:
    """
    Detect affirmative/negative from any language.
    Returns True (yes), False (no), or None (unclear).
    """
    text = text.lower().strip()

    YES = [
        "yes", "yeah", "yep", "sure", "ok", "okay", "of course",
        "absolutely", "please", "add", "include", "with", "want",
        "would like", "i do", "go ahead", "why not",
        "oui", "bien sûr", "d'accord", "ajouter", "inclure", "je veux",
        "yego", "ndashaka", "ngomba", "nziza", "twaze", "oya nziza",
        "ntakibazo",
    ]
    NO = [
        "no", "nope", "not", "without", "skip", "remove", "don't",
        "no thanks", "no need", "pass",
        "non", "pas", "sans", "enlever", "retirer", "je ne veux pas",
        "oya", "hoya", "sinjye", "ntashaka", "ntabwo", "nta", "anze",
    ]

    for signal in YES:
        if signal in text:
            return True
    for signal in NO:
        if signal in text:
            return False
    return None

def _process_discovery_answer(journey: JourneyState, message_text: str, lang: str) -> bool:
    """
    Determine which question was last asked (first None field),
    extract yes/no from message, save to discovery_state.
    Returns True if answer was successfully recorded.
    """
    ds = journey.discovery_state or {}
    text_lower = (message_text or "").lower()

    # Find the currently pending question (first None)
    for key in ["photo_type", "session_type", "frames", "cake", "video"]:
        if ds.get(key) is None:
            # This is the question we just asked
            if key == "photo_type":
                # Family signals
                if any(x in text_lower for x in ["family", "famille", "umuryango", "all of us", "together"]):
                    ds["photo_type"] = "family"
                else:
                    ds["photo_type"] = "child"  # default to child
            elif key == "session_type":
                if any(x in text_lower for x in ["home", "house", "rugo", "domicile", "maison", "chez moi", "chez nous"]):
                    ds["session_type"] = "home"
                else:
                    ds["session_type"] = "studio"
            else:
                # Boolean yes/no
                answer = _extract_yes_no(message_text)
                if answer is None:
                    # Unclear — do not update, let AI ask again
                    return False
                ds[key] = answer
            break

    journey.discovery_state = ds
    journey.save(update_fields=["discovery_state", "updated_at"])
    return True

def _detect_package_choice(message_text: str) -> Optional[str]:
    text_lower = (message_text or "").lower()
    if any(x in text_lower for x in ["starter", "first", "cheapest", "50", "ya mbere"]):
        return "starter"
    if any(x in text_lower for x in ["silver", "second", "middle", "70", "ya kabiri"]):
        return "silver"
    if any(x in text_lower for x in ["gold", "third", "last", "100", "best", "ya gatatu"]):
        return "gold"
    if any(x in text_lower for x in ["premium", "home", "200"]):
        return "premium"
    return None

def _check_extra_adjustment(message_text: str, journey: JourneyState, lang: str) -> bool:
    """Returns True if an extra was added/removed and state was updated."""
    text_lower = (message_text or "").lower()
    ds = journey.discovery_state or {}
    changed = False

    if any(x in text_lower for x in ["remove video", "without video", "no video", "sans video", "gukuraho video"]):
        ds["video"] = False; changed = True
    elif any(x in text_lower for x in ["add video", "with video", "include video", "ajouter video", "kongeraho video"]):
        ds["video"] = True; changed = True

    if any(x in text_lower for x in ["remove cake", "without cake", "no cake", "sans gateau", "gukuraho cake"]):
        ds["cake"] = False; changed = True
    elif any(x in text_lower for x in ["add cake", "with cake", "include cake", "ajouter gateau", "kongeraho cake"]):
        ds["cake"] = True; changed = True

    if any(x in text_lower for x in ["remove frame", "without frame", "no frame", "sans cadre", "gukuraho frame"]):
        ds["frames"] = False; changed = True
    elif any(x in text_lower for x in ["add frame", "with frame", "include frame", "ajouter cadre", "kongeraho frame"]):
        ds["frames"] = True; changed = True

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

def _activate_human_takeover(client, journey, conversation, sender_id, lang,
                              reason="Human takeover", send_message=True):
    if send_message:
        TAKEOVER_MESSAGES = {
            "en": "Of course! 😊 One of our team members will be with you shortly. Thank you for your patience! 🙏",
            "fr": "Bien sûr! 😊 Un membre de notre équipe sera avec vous bientôt. Merci de votre patience! 🙏",
            "rw": "Yego rwose! 😊 Umwe mu bakozi bacu aragufasha vuba. Murakoze kwihangana! 🙏",
        }
        msg = TAKEOVER_MESSAGES.get(lang, TAKEOVER_MESSAGES["en"])
        send_text(sender_id, msg)
        _save_outbound(client, conversation, msg)

    journey.human_takeover = True
    journey.takeover_reason = reason
    journey.flow_mode = "human_takeover"
    journey.save(update_fields=["human_takeover", "takeover_reason", "flow_mode", "updated_at"])

    # Create approval queue entry
    from apps.instagram.models import InstagramApprovalQueue
    InstagramApprovalQueue.objects.create(
        client=client,
        conversation=conversation,
        action=InstagramApprovalQueue.ApprovalAction.ESCALATE,
        ai_suggestion=f"[Instagram] Human takeover: {reason}",
        ai_reasoning=reason,
        heat_score_at_suggestion=getattr(journey, "heat_score", 50),
        expires_at=timezone.now() + timezone.timedelta(hours=72),
    )

    # Send email
    try:
        from services.button_flow import _send_agent_request_email
        _send_agent_request_email(client, journey)
    except Exception as e:
        logger.warning("Failed to send IG takeover email: %s", e)

    # Push notification
    try:
        from apps.dashboard.views import send_push_notification
        send_push_notification(
            title=f"📸 Instagram — {client.name or sender_id}",
            body=reason[:80],
            url=f"/?client={client.pk}",
        )
    except Exception:
        pass

def _build_package_presentation(discovery_state: dict, lang: str) -> str:
    """
    Build exact package presentation matching WhatsApp button_flow.py format.
    Show per-package details: price, duration, photo count, includes.
    """
    # 1. Calculate extras
    extras_cost = _calculate_extras_cost(discovery_state)
    extras_lines = []

    if discovery_state.get("frames"):
        EXTRAS_LABELS = {
            "en": "2 A5 Photo Frames",
            "fr": "2 Cadres Photo A5",
            "rw": "Ama cadre 2 ya A5",
        }
        extras_lines.append(EXTRAS_LABELS.get(lang, EXTRAS_LABELS["en"]))

    if discovery_state.get("cake") and discovery_state.get("video"):
        BUNDLE_LABELS = {
            "en": "Birthday Cake + Highlight Video",
            "fr": "Gâteau + Vidéo Souvenir",
            "rw": "Cake + Video",
        }
        extras_lines.append(BUNDLE_LABELS.get(lang, BUNDLE_LABELS["en"]))
    elif discovery_state.get("cake"):
        CAKE_LABELS = {"en": "Birthday Cake", "fr": "Gâteau d'Anniversaire", "rw": "Cake ya Aniverseri"}
        extras_lines.append(CAKE_LABELS.get(lang, CAKE_LABELS["en"]))
    elif discovery_state.get("video"):
        VIDEO_LABELS = {"en": "Highlight Video (15-30 sec)", "fr": "Vidéo Souvenir (15-30 sec)", "rw": "Video Ngufi (15-30 sec)"}
        extras_lines.append(VIDEO_LABELS.get(lang, VIDEO_LABELS["en"]))

    includes_str = ", ".join(extras_lines) if extras_lines else ""

    session_type = discovery_state.get("session_type", "studio")

    if session_type == "home":
        total = 200000 + extras_cost
        INTROS = {
            "en": "Here is the package built just for you!\n\n",
            "fr": "Voici le forfait fait pour vous!\n\n",
            "rw": "Dore package yakuburiwe!\n\n",
        }
        PREMIUM_LINES = {
            "en": (
                f"🏆 Premium Package — {total:,} RWF\n"
                "2h Home Session\n"
                "Delivery: 30 Edited Photos\n"
                "All Other Unedited Photos\n"
            ),
            "fr": (
                f"🏆 Premium Package — {total:,} RWF\n"
                "2h Séance à Domicile\n"
                "Livraison: 30 Photos Éditées\n"
                "Toutes les Autres Non Éditées\n"
            ),
            "rw": (
                f"🏆 Premium Package — {total:,} RWF\n"
                "Amasaha 2 mu Rugo\n"
                "Kubaboherereza: Amafoto 30 atunganijwe\n"
                "Yandi Yose Adatunganijwe\n"
            ),
        }
        INCLUDES = {"en": "Includes: ", "fr": "Inclus: ", "rw": "Harimo: "}
        QUESTIONS = {
            "en": "\nAnd on behalf of KP Kids Studio I will personally include a special gift for the child!\n\nWhich package feels right for you? 😊",
            "fr": "\nEt au nom de KP Kids Studio je vais personnellement ajouter un cadeau spécial pour l'enfant!\n\nLequel vous convient? 😊",
            "rw": "\nKandi mu izina rya KP Kids Studio nzabongera impano yihariye y'umwana!\n\nNi iyihe mwifuza? 😊",
        }
        text = INTROS.get(lang, INTROS["en"])
        text += PREMIUM_LINES.get(lang, PREMIUM_LINES["en"])
        if includes_str:
            text += INCLUDES.get(lang, INCLUDES["en"]) + includes_str + "\n"
        text += QUESTIONS.get(lang, QUESTIONS["en"])
        return text

    # Studio — 3 packages
    packages = [
        {"name": "Starter", "base": 50000, "emoji": "🥉", "duration": "1h", "photos": 8},
        {"name": "Silver",  "base": 70000, "emoji": "🥈", "duration": "1h", "photos": 12},
        {"name": "Gold",    "base": 100000,"emoji": "🥇", "duration": "1.5h","photos": 18},
    ]

    INTROS = {
        "en": "Here are the 3 packages built just for you!\n\n",
        "fr": "Voici les 3 forfaits faits pour vous!\n\n",
        "rw": "Dore packages 3 zakubakiwe!\n\n",
    }
    SESSION_LABELS = {"en": "Studio Session", "fr": "Séance Studio", "rw": "Session ya Studio"}
    DELIVERY_LABELS = {
        "en": "Delivery: {photos} Edited Photos",
        "fr": "Livraison: {photos} Photos Éditées",
        "rw": "Kubaboherereza: Amafoto {photos} atunganijwe",
    }
    UNEDITED_LABELS = {
        "en": "All Other Unedited Photos",
        "fr": "Toutes les Autres Non Éditées",
        "rw": "Ayandi Yose Adatunganijwe",
    }
    INCLUDES = {"en": "Includes: ", "fr": "Inclus: ", "rw": "Harimo: "}
    QUESTIONS = {
        "en": "\nAnd on behalf of KP Kids Studio I will personally include a special gift for the child!\n\nWhich package feels right for you? 😊",
        "fr": "\nEt au nom de KP Kids Studio je vais personnellement ajouter un cadeau spécial pour l'enfant!\n\nLequel vous convient? 😊",
        "rw": "\nKandi mu izina rya KP Kids Studio nzabongera impano yihariye y'umwana!\n\nNi iyihe mwifuza? 😊",
    }

    text = INTROS.get(lang, INTROS["en"])
    for pkg in packages:
        total = pkg["base"] + extras_cost
        text += f"{pkg['emoji']} {pkg['name']} Package — {total:,} RWF\n"
        text += f"{pkg['duration']} {SESSION_LABELS.get(lang, SESSION_LABELS['en'])}\n"
        text += DELIVERY_LABELS.get(lang, DELIVERY_LABELS["en"]).format(photos=pkg["photos"]) + "\n"
        text += UNEDITED_LABELS.get(lang, UNEDITED_LABELS["en"]) + "\n"
        if includes_str:
            text += INCLUDES.get(lang, INCLUDES["en"]) + includes_str + "\n"
        text += "\n"

    text += QUESTIONS.get(lang, QUESTIONS["en"])
    return text

def build_instagram_system_prompt(
    language: str,
    client_name: str,
    flow_mode: str,
    discovery_state: dict,
    rag_context: str,
    next_question: str = "",
) -> str:

    lang_instruction = LANG_INSTRUCTIONS.get(language, LANG_INSTRUCTIONS["en"])
    discovery_context = _build_discovery_context(discovery_state)

    # Build flow-specific instruction
    if flow_mode == "new":
        flow_instruction = (
            "The client just sent their FIRST message. "
            "Send ONLY the welcome message. "
            "Do NOT ask for the child's name or age. "
            "Do NOT start discovery. "
            "Just welcome them warmly and offer help options."
        )
    elif flow_mode == "discovery" and next_question:
        flow_instruction = (
            f"You are in the DISCOVERY phase. "
            f"The client answered the previous question. "
            f"Now ask ONLY this next question and nothing else:\n{next_question}\n\n"
            f"Do NOT present packages yet. "
            f"Do NOT skip ahead. "
            f"Do NOT ask multiple questions at once."
        )
    elif flow_mode == "packages_shown":
        flow_instruction = (
            "Packages have already been presented. "
            "Wait for the client to choose a package. "
            "If they ask to remove or add an extra, acknowledge it and "
            "say you will recalculate — the system will handle the recalculation. "
            "Do NOT re-present packages in your text response. "
            "If they choose a package, ask for their preferred date and time."
        )
    elif flow_mode == "awaiting_datetime":
        flow_instruction = (
            "The client has chosen a package. "
            "Wait for them to provide a preferred date and time for their session. "
            "Remind them we are open Monday to Saturday, 9 AM to 6 PM."
        )
    elif flow_mode in ("await_confirm", "human_takeover"):
        flow_instruction = (
            "A human agent is handling this conversation. "
            "You must NOT respond. Stay completely silent. "
            "Return an empty string."
        )
    else:
        flow_instruction = (
            "Listen to the client. Detect their intent. "
            "If they ask about location → give address and ask if more help needed. "
            "If they ask about prices → invite them to the 1-minute discovery. "
            "If they ask a specific question → answer it directly from knowledge base. "
            "If you don't know → apologize and suggest calling +250795820170."
        )

    return f"""You are Julie, the friendly AI assistant for KP Kids Studio,
a children's photography studio in Kigali, Rwanda.

==== LANGUAGE RULE (HIGHEST PRIORITY) ====
{lang_instruction}

==== YOUR PERSONA ====
Name: Julie.
Warm, professional, helpful. Never robotic.
Use emojis warmly: 😊 📸 🎂 🎉 🙏
NO MARKDOWN: No **bold**, no *italic*, no bullet points with hyphens.
NO BUTTONS: Never write [Button text] or numbered menus.
Max 4 sentences per response unless presenting packages or answering discovery.

==== STUDIO INFO ====
Name: KP Kids Studio (also known as Kigali Photography)
Location: Kicukiro, BRGD Plaza, opposite IPRC, next to SAWA CITY Supermarket, Kigali
Hours: Monday to Saturday, 9 AM to 6 PM
WhatsApp for detailed questions: +250795820170
Specialty: Children and family photoshoots — studio and home sessions

==== PRICING (EXACT — NEVER INVENT) ====
Single photo pricing: WE DO NOT OFFER THIS. Packages only.
Studio packages (base, before extras):
  Starter: 50,000 RWF | 1h | 8 edited photos + all unedited
  Silver:  70,000 RWF | 1h | 12 edited photos + all unedited
  Gold:    100,000 RWF | 1.5h | 18 edited photos + all unedited
Home session:
  Premium: 200,000 RWF | 2h | 30 edited photos + all unedited
Extras:
  2 A5 frames: +20,000 RWF
  Birthday cake: +30,000 RWF
  Highlight video (15-30 SECONDS, NOT minutes): +29,000 RWF
  Cake + video bundle: +50,000 RWF (saves 9,000 vs buying separately)
Booking fee: 20,000 RWF via MTN MoMo 798741 (Kigali Photography Ltd)
NO DISCOUNTS. EVER.

==== SPECIFIC ANSWERS ====
About frames: "Beautiful A5-format framed prints, perfect for home display.
  For more details: WhatsApp +250795820170"
About cake: "Perfectly sized for a celebration! 🎂"
About video: "A 15 to 30-second highlight clip of your session's best moments.
  For more details: WhatsApp +250795820170"
About video duration: ALWAYS say "15 to 30 seconds" — NEVER say minutes.
About family photoshoot: This does NOT mean home session. They are separate questions.
  A family can choose studio OR home. Ask session_type separately.

==== CURRENT CLIENT STATE ====
Client name: {client_name or "valued client"}
Conversation mode: {flow_mode}
{discovery_context}

==== CURRENT INSTRUCTION ====
{flow_instruction}

==== KNOWLEDGE BASE ====
{rag_context if rag_context else "No additional context."}

==== HARD RULES ====
1. Never ask for the child's name or age in your first message.
2. Never present packages before all 5 discovery questions are answered.
3. Never skip a discovery question.
4. Never combine two discovery questions in one message.
5. Never invent prices, durations, or photo counts.
6. Never say the video is more than 30 seconds.
7. Never interpret "family" as "home session" — they are independent choices.
8. If flow_mode is "human_takeover" or "await_confirm" → return empty string.
9. No discounts under any circumstances.
10. If you cannot answer → "I'm not sure about that, but you can reach us
    directly on WhatsApp at +250795820170 for more details! 😊"
"""

def _build_discovery_context(ds: dict) -> str:
    if not ds: return "Discovery: Not started."
    steps = []
    for k in ["photo_type", "session_type", "frames", "cake", "video"]:
        v = ds.get(k)
        if v is None: val = "Pending"
        else: val = "Yes" if v is True else ("No" if v is False else v)
        steps.append(f"{k}: {val}")
    return "Discovery Progress: " + ", ".join(steps)

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
            "content": text or "[media]",
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
