"""
Button Flow Service
====================
Gère tout le flow boutons WhatsApp de A à Z.

Flow :
  ENTRY       → Message de bienvenue + 3 boutons
  DISCOVERY   → 4 questions avec boutons (session, frames, cake, video)
  PACKAGES    → Calcul + présentation des 3 packages avec boutons
  BOOKING     → Instructions paiement + boutons post-booking
  QUESTION    → Mode IA libre + bouton "Talk to Agent"

Appelé par l'orchestrateur quand msg_type == "interactive"
OU pour envoyer le message de bienvenue (premier message).
"""

import logging
from services.whatsapp import send_text, send_buttons

logger = logging.getLogger(__name__)

# ─── DÉFINITION DES ÉTAPES DISCOVERY ────────────────────────────────────────

DISCOVERY_STEPS = {
    "en": [
        {
            "key": "session_type",
            "message": "Where would you prefer your session? 📸",
            "buttons": [
                {"id": "disc_studio", "title": "🎨 In Studio"},
                {"id": "disc_home",   "title": "🏠 At Home"},
            ],
        },
        {
            "key": "frames",
            "message": "Would you like 2 A5 photo frames included? 🖼️",
            "buttons": [
                {"id": "disc_frames_yes", "title": "✅ Yes"},
                {"id": "disc_frames_no",  "title": "❌ No"},
            ],
        },
        {
            "key": "cake",
            "message": "How about a birthday cake? 🎂",
            "buttons": [
                {"id": "disc_cake_yes", "title": "✅ Yes"},
                {"id": "disc_cake_no",  "title": "❌ No"},
            ],
        },
        {
            "key": "video",
            "message": "Would you like a short highlight video? 🎬",
            "buttons": [
                {"id": "disc_video_yes", "title": "✅ Yes"},
                {"id": "disc_video_no",  "title": "❌ No"},
            ],
        },
    ],
    "rw": [
        {
            "key": "session_type",
            "message": "Murifuzako mufotorwe he? 📸",
            "buttons": [
                {"id": "disc_studio", "title": "🎨 Muri Studio"},
                {"id": "disc_home",   "title": "🏠 Mu Rugo"},
            ],
        },
        {
            "key": "frames",
            "message": "Twabongereramo frame 2 za A5 muri package? 🖼️",
            "buttons": [
                {"id": "disc_frames_yes", "title": "✅ Yego"},
                {"id": "disc_frames_no",  "title": "❌ Oya"},
            ],
        },
        {
            "key": "cake",
            "message": "Murifuzako Twabakorera na cake? 🎂",
            "buttons": [
                {"id": "disc_cake_yes", "title": "✅ Yego"},
                {"id": "disc_cake_no",  "title": "❌ Oya"},
            ],
        },
        {
            "key": "video",
            "message": "Twabakorera naka video kagufi? 🎬",
            "buttons": [
                {"id": "disc_video_yes", "title": "✅ Yego"},
                {"id": "disc_video_no",  "title": "❌ Oya"},
            ],
        },
    ],
    "fr": [
        {
            "key": "session_type",
            "message": "Où préférez-vous votre séance? 📸",
            "buttons": [
                {"id": "disc_studio", "title": "🎨 En Studio"},
                {"id": "disc_home",   "title": "🏠 À Domicile"},
            ],
        },
        {
            "key": "frames",
            "message": "Souhaitez-vous 2 cadres photo A5? 🖼️",
            "buttons": [
                {"id": "disc_frames_yes", "title": "✅ Oui"},
                {"id": "disc_frames_no",  "title": "❌ Non"},
            ],
        },
        {
            "key": "cake",
            "message": "Et un gâteau d'anniversaire? 🎂",
            "buttons": [
                {"id": "disc_cake_yes", "title": "✅ Oui"},
                {"id": "disc_cake_no",  "title": "❌ Non"},
            ],
        },
        {
            "key": "video",
            "message": "Une courte vidéo souvenir? 🎬",
            "buttons": [
                {"id": "disc_video_yes", "title": "✅ Oui"},
                {"id": "disc_video_no",  "title": "❌ Non"},
            ],
        },
    ],
}

PACKAGE_MESSAGES = {
    "en": {
        "intro": "Here are the 3 packages built just for you:\n",
        "session_studio": "Studio Session",
        "session_home": "Home Session",
        "delivery": "Delivery: {photos} Edited Photos",
        "unedited": "All Other Unedited Photos",
        "includes": "Includes: {includes}",
        "question": "And on behalf of Kigali Photography I'll personally include an *extra gift* for the child, Which one feels right for you? 😊",
        "body": "Choose your package:",
    },
    "rw": {
        "intro": "Dore packages 3 zikubiyemo ibyo mwadusabye\n",
        "session_studio": "Session muri Studio",
        "session_home": "Session mu Rugo",
        "delivery": "Gutangwa: Amafoto {photos} mwahisemo",
        "unedited": "Ayandi amafoto Yose Adatunganijwe(unedited)",
        "includes": "Birimo: {includes}",
        "question": "Ku izina rya Kigali Photography, jye ubwanjye nzaha umwana impano y’inyongera, Ni iyihe muyifata? 😊",
        "body": "Hitamo package:",
    },
    "fr": {
        "intro": "Voici les 3 packets faits pour vous:\n",
        "session_studio": "Séance en Studio",
        "session_home": "Séance à Domicile",
        "delivery": "Livraison: {photos} Photos traitées",
        "unedited": "Toutes les Autres Non traitées",
        "includes": "Inclus: {includes}",
        "question": "AU nom de Kigali Photography, je veux personnellement ajouter un cadeau à l'enfant. Lequel vous convient? 😊",
        "body": "Choisissez votre packet:",
    },
}
# ─── MAPPING BOUTON → SIGNIFICATION ─────────────────────────────────────────

EXTRAS_LABELS = {
    "en": {
        "frames":    "2 A5 Photo Frames",
        "cake":      "Birthday Cake",
        "video":     "Highlight Video (15–30 sec)",
    },
    "rw": {
        "frames":    "Ama frames 2 ya A5",
        "cake":      "Cake ya Birthday",
        "video":     "Video Ngufi (15–30 sec)",
    },
    "fr": {
        "frames":    "2 Cadres Photo A5",
        "cake":      "Gâteau d'Anniversaire",
        "video":     "Vidéo Souvenir (15–30 sec)",
    },
}

# Format : "button_id" → ("type", *valeurs)
BUTTON_MAP = {
    # Entry
    "btn_book":          ("action", "start_booking"),
    "btn_prices":        ("action", "start_prices"),
    "btn_question":      ("action", "start_question"),

    # Discovery
    "disc_studio":       ("discovery", "session_type", "studio"),
    "disc_home":         ("discovery", "session_type", "home"),
    "disc_frames_yes":   ("discovery", "frames", True),
    "disc_frames_no":    ("discovery", "frames", False),
    "disc_cake_yes":     ("discovery", "cake",   True),
    "disc_cake_no":      ("discovery", "cake",   False),
    "disc_video_yes":    ("discovery", "video",  True),
    "disc_video_no":     ("discovery", "video",  False),

    # Package choice
    "pkg_starter":       ("package", "Starter"),
    "pkg_silver":        ("package", "Silver"),
    "pkg_gold":          ("package", "Gold"),

    # Post-booking
    "btn_paid":          ("action", "payment_confirmed"),
    "btn_agent":         ("action", "talk_to_agent"),

    # Language selection
    "lang_en": ("action", "set_language_en"),
    "lang_rw": ("action", "set_language_rw"),
    "lang_fr": ("action", "set_language_fr"),
}


# ─── POINT D'ENTRÉE PRINCIPAL ────────────────────────────────────────────────

def handle_button_click(interactive_id: str, from_number: str, journey, client) -> str:
    """
    Reçoit l'ID du bouton cliqué et exécute l'action correspondante.
    Retourne une string décrivant l'action effectuée (pour les logs).
    Ne lève jamais d'exception — erreurs loggées et ignorées.
    """
    mapping = BUTTON_MAP.get(interactive_id)
    if not mapping:
        logger.warning("Unknown button_id: %s from %s", interactive_id, from_number)
        send_text(to=from_number, message=_m(client, "unknown_button"))
        send_welcome(from_number)
        return "unknown_button_resent_welcome"

    action_type = mapping[0]

    if action_type == "action":
        return _handle_action(mapping[1], from_number, journey, client)

    if action_type == "discovery":
        return _handle_discovery(mapping[1], mapping[2], from_number, journey, client)

    if action_type == "package":
        return _handle_package_choice(mapping[1], from_number, journey, client)

    return "unhandled"


# def send_welcome(to: str) -> None:
#     """
#     Envoie le message de bienvenue + les 3 boutons entry.
#     Appelé au premier message ET si le client tape du texte hors-contexte.
#     """
#     send_text(
#         to=to,
#         message=(
#             "Hello! 😊 Thank you for reaching out to *KP Kids Studio*.\n"
#             "My name is Julie, and I am here to help.\n\n"
#             "How can I assist you today?"
#         ),
#     )
#     send_buttons(
#         to=to,
#         body="Please choose an option:",
#         buttons=[
#             {"id": "btn_book",     "title": "📸 Book a Session"},
#             {"id": "btn_prices",   "title": "💰 View Prices"},
#             {"id": "btn_question", "title": "ℹ️ Ask a Question"},
#         ],
#     )
def send_welcome(to: str) -> None:
    """
    Envoie le message de bienvenue UNIQUEMENT avec le choix de langue.
    Les 3 boutons (Book/Prices/Question) arrivent APRÈS le choix de langue.
    """
    send_text(
        to=to,
        message=(
            "Hello! 😊 Welcome to *KP Kids Studio*.\n"
            "Muraho! Murakaza neza kuri *KP Kids Studio*.\n"
            "Bonjour! Bienvenue chez *KP Kids Studio*.\n"
        ),
    )
    send_buttons(
        to=to,
        body="Language / Ururimi / Langue:",
        buttons=[
            {"id": "lang_en", "title": "🇬🇧 English"},
            {"id": "lang_rw", "title": "🇷🇼 Kinyarwanda"},
            {"id": "lang_fr", "title": "🇫🇷 Français"},
        ],
    )


# ─── HANDLERS D'ACTION ───────────────────────────────────────────────────────

def _handle_action(action: str, from_number: str, journey, client) -> str:

    if action in ("set_language_en", "set_language_rw", "set_language_fr"):
        lang_map = {
            "set_language_en": "en",
            "set_language_rw": "rw",
            "set_language_fr": "fr",
        }
        lang = lang_map[action]
        client.language = lang
        client.save(update_fields=["language", "updated_at"])
        _send_main_menu(to=from_number, lang=lang)
        return f"language_set_{lang}"

    if action == "start_booking":
        _set_flow_mode(journey, "booking")
        _reset_discovery(journey)
        send_text(to=from_number, message=_m(client, "start_booking"))
        _send_next_discovery_question(from_number, journey, client)
        return "started_booking_flow"

    if action == "start_prices":
        _set_flow_mode(journey, "prices")
        _reset_discovery(journey)
        send_text(to=from_number, message=_m(client, "start_prices"))
        _send_next_discovery_question(from_number, journey, client)
        return "started_prices_flow"

    if action == "start_question":
        _set_flow_mode(journey, "question")
        send_text(to=from_number, message=_m(client, "start_question"))
        return "started_question_mode"

    if action == "payment_confirmed":
        return _handle_payment_confirmed(from_number, journey, client)

    if action == "talk_to_agent":
        return _handle_talk_to_agent(from_number, journey, client)

    logger.warning("Unhandled action: %s", action)
    return "unhandled_action"

# ─── HANDLER DISCOVERY ───────────────────────────────────────────────────────

def _handle_discovery(field: str, value, from_number: str, journey, client) -> str:
    """
    Enregistre la réponse discovery et envoie la prochaine question.
    Quand tout est rempli → calcule et présente les packages.
    """
    # Sauvegarder la réponse
    state = journey.discovery_state or {}
    state[field] = value
    journey.discovery_state = state
    journey.save(update_fields=["discovery_state", "updated_at"])

    # Y a-t-il encore des questions sans réponse ?
    next_step = _get_next_unanswered_step(state, lang=client.language)

    if next_step:
        _send_discovery_question(from_number, next_step)
        return f"discovery_{field}_saved_next_{next_step['key']}"
    else:
        # Toutes les questions répondues → présenter les packages
        _present_packages(from_number, journey, client)
        return "discovery_complete_packages_sent"


# ─── CALCUL ET PRÉSENTATION DES PACKAGES Cherche ici────────────────────────────────────

def _present_packages(from_number: str, journey, client) -> None:
    state = journey.discovery_state or {}
    lang = getattr(client, "language", "en") or "en"
    msgs = PACKAGE_MESSAGES.get(lang, PACKAGE_MESSAGES["en"])

    session_type = state.get("session_type", "studio")
    session_label = (
        msgs["session_home"] if session_type == "home" 
        else msgs["session_studio"]
    )
    frames  = state.get("frames", False)
    cake    = state.get("cake",   False)
    video   = state.get("video",  False)

    # Récupérer les labels dans la bonne langue
    labels = EXTRAS_LABELS.get(lang, EXTRAS_LABELS["en"])

    extras_cost = 0
    extras_lines = []
    if frames:
        extras_cost += 20000
        extras_lines.append(labels["frames"])
    if cake and video:
        extras_cost += 50000
        extras_lines.append(labels["cake"])
        extras_lines.append(labels["video"])
    elif cake:
        extras_cost += 30000
        extras_lines.append(labels["cake"])
    elif video:
        extras_cost += 29000
        extras_lines.append(labels["video"])

    home_fee = 69000 if session_type == "home" else 0
    session_label = msgs["session_home"] if session_type == "home" else msgs["session_studio"]
    includes_line = ", ".join(extras_lines) if extras_lines else None

    packages = [
        {"name": "Starter", "base": 50000, "duration": "1h",   "photos": 8,  "emoji": "🥉"},
        {"name": "Silver",  "base": 70000, "duration": "1h",   "photos": 12, "emoji": "🥈"},
        {"name": "Gold",    "base": 100000,"duration": "1.5h", "photos": 18, "emoji": "🥇"},
    ]

    lines = [msgs["intro"]]
    for pkg in packages:
        total = pkg["base"] + extras_cost + home_fee
        lines.append(f"{pkg['emoji']} *{pkg['name']} Package* — {total:,} RWF")
        lines.append(f"{pkg['duration']} {session_label}")
        lines.append(msgs["delivery"].format(photos=pkg["photos"]))
        lines.append(msgs["unedited"])
        if includes_line:
            lines.append(msgs["includes"].format(includes=includes_line))
        lines.append("")

    lines.append(msgs["question"])

    send_text(to=from_number, message="\n".join(lines))
    send_buttons(
        to=from_number,
        body=msgs["body"],
        buttons=[
            {"id": "pkg_starter", "title": "🥉 Starter"},
            {"id": "pkg_silver",  "title": "🥈 Silver"},
            {"id": "pkg_gold",    "title": "🥇 Gold"},
        ],
    )

# ─── HANDLER CHOIX DE PACKAGE ────────────────────────────────────────────────

def _handle_package_choice(package_name: str, from_number: str, journey, client) -> str:
    journey.selected_package = package_name
    journey.save(update_fields=["selected_package", "updated_at"])

    send_text(
        to=from_number,
        message=_m(client, "package_chosen", package_name=package_name),
    )
    send_buttons(
        to=from_number,
        body=_m(client, "package_choice_body"),
        buttons=[
            {"id": "btn_paid",  "title": _m(client, "btn_paid_title")},
            {"id": "btn_agent", "title": _m(client, "btn_agent_title")},
        ],
    )

    from apps.clients.models import JourneyPhase, JourneyStep
    journey.advance(JourneyPhase.BOOKING, JourneyStep.PAYMENT_CONFIRMATION)
    return f"package_chosen_{package_name.lower()}"

# ─── HANDLER PAIEMENT CONFIRMÉ ───────────────────────────────────────────────

def _handle_payment_confirmed(from_number: str, journey, client) -> str:
    # Imports en dehors du try — évite UnboundLocalError
    from services.journey_orchestrator import (
        _notify_human_takeover,
        _send_payment_notification_email,
    )

    journey.flag_human_takeover("Client confirmed payment via button")

    # Construire le formulaire de booking pour le dashboard
    pkg  = journey.selected_package or "?"
    lang = getattr(client, "language", "en") or "en"

    if lang == "rw":
        booking_form = (
            f"Twayakiriye! Murakoze.\n\n"
            f"Mwuzuze amakuru yanyu:\n\n"
            f"Izina:\n"
            f"Igitsina cy'umwana:\n"
            f"Imyaka y'umwana:\n"
            f"Package: {pkg}\n"
            f"Umunsi w'isoko:\n"
            f"Isaha y'isoko:"
        )
    elif lang == "fr":
        booking_form = (
            f"Bien reçu! Merci.\n\n"
            f"Veuillez remplir vos informations:\n\n"
            f"Nom:\n"
            f"Sexe de l'enfant:\n"
            f"Âge de l'enfant:\n"
            f"Package: {pkg}\n"
            f"Jour de réservation:\n"
            f"Heure de réservation:"
        )
    else:
        booking_form = (
            f"Well received! Thank you.\n\n"
            f"Please fill in your details:\n\n"
            f"Name:\n"
            f"Kid's Gender:\n"
            f"Kid's Age:\n"
            f"Package: {pkg}\n"
            f"Booking Day:\n"
            f"Booking Time:"
        )

    try:
        conversation = (
            client.conversations.filter(window_status="open")
            .order_by("-started_at").first()
        )
        if conversation:
            _notify_human_takeover(
                client,
                conversation,
                reason="Payment confirmed by client via button",
                ai_suggestion=booking_form,
            )
            _send_payment_notification_email(client, conversation, journey=journey)
    except Exception as exc:
        logger.warning("Notification failed after payment_confirmed: %s", exc)

    send_text(to=from_number, message=_m(client, "payment_confirmed"))
    return "payment_confirmed_human_takeover"


# ─── HANDLER TALK TO AGENT ───────────────────────────────────────────────────
def _handle_talk_to_agent(from_number: str, journey, client) -> str:
    # Import en dehors du try
    from services.journey_orchestrator import _notify_human_takeover

    journey.flag_human_takeover("Client requested human agent via button")

    agent_message = (
        f"Client {client.name or client.wa_number} requested to speak "
        f"with a human agent.\n\n"
        f"Journey: {journey.phase}/{journey.step}\n"
        f"Heat: {journey.heat_label}\n\n"
        f"Action: Take over the conversation and assist the client directly."
    )

    try:
        conversation = (
            client.conversations.filter(window_status="open")
            .order_by("-started_at").first()
        )
        if conversation:
            _notify_human_takeover(
                client,
                conversation,
                reason="Client requested human agent",
                ai_suggestion=agent_message,
            )
    except Exception as exc:
        logger.warning("Notification failed after talk_to_agent: %s", exc)

    send_text(to=from_number, message=_m(client, "talk_to_agent"))
    return "talk_to_agent_human_takeover"
MAIN_MENU = {
    "en": {
        "text": (
            "Thank you! 😊 My name is Julie and I'm here to help.\n\n"
            "How can I assist you today?"
        ),
        "body": "Please choose an option:",
        "buttons": [
            {"id": "btn_book",     "title": "📸 Book a Session"},
            {"id": "btn_prices",   "title": "💰 View Prices"},
            {"id": "btn_question", "title": "ℹ️ Ask a Question"},
        ],
    },
    "rw": {
        "text": (
            "Murakoze! 😊 Nitwa Julie, ndi hano ngo mbafashe.\n\n"
            "Ni gute nabafasha uyu munsi?"
        ),
        "body": "Hitamo:",
        "buttons": [
            {"id": "btn_book",     "title": "📸 Fata Igihe"},
            {"id": "btn_prices",   "title": "💰 Reba Ibiciro"},
            {"id": "btn_question", "title": "ℹ️ Baza Ikibazo"},
        ],
    },
    "fr": {
        "text": (
            "Merci! 😊 Je m'appelle Julie et je suis là pour vous aider.\n\n"
            "Comment puis-je vous aider aujourd'hui?"
        ),
        "body": "Choisissez une option:",
        "buttons": [
            {"id": "btn_book",     "title": "📸 Réserver"},
            {"id": "btn_prices",   "title": "💰 Voir les Prix"},
            {"id": "btn_question", "title": "Poser une Question"},
        ],
    },
}

MESSAGES = {
    "en": {
        # Actions
        "start_booking": (
            "Perfect! 🎉 To prepare your session, "
            "I just need to ask you a few quick questions "
            "so we can build the right package for you.\n\nLet's start! 👇"
        ),
        "start_prices": (
            "Our prices depend on what's included in your package. 📦\n\n"
            "Let me ask you a few quick questions "
            "and I'll build your custom price right away!"
        ),
        "start_question": (
            "Of course! 😊 Feel free to type your question "
            "and I'll do my best to help you."
        ),
        # Package choice
        "package_chosen": (
            "Great choice! 🎉 You selected the *{package_name} Package*.\n\n"
            "To secure your date, please send the booking fee of "
            "*20,000 RWF* to:\n\n"
            "📱 MTN MoMo: *798741*\n"
            "Name: *Kigali Photography Ltd*\n\n"
            "The rest is paid after the session. "
            "Just let us know once you're done! 🙏"
        ),
        "package_choice_body": "What would you like to do next?",
        "btn_paid_title":  "✅ I've Sent Payment",
        "btn_agent_title": "🧑 Talk to Agent",
        # Payment confirmed
        "payment_confirmed": (
            "Thank you! 🙏 We've received your confirmation.\n\n"
            "We're verifying your payment now and will confirm your booking shortly. "
            "A team member will be with you in a moment! 😊"
        ),
        # Talk to agent
        "talk_to_agent": (
            "Of course! 😊 One of our team members will be with you shortly.\n"
            "Thank you for your patience! 🙏"
        ),
        # Text during discovery
        "resend_options":    "No worries! 😊 Let me re-send the options:",
        "fallback_question": "Great question! 😊 Our team will follow up on that.",
        "fallback_recalc":   "Just let me know what you'd like to change and I'll recalculate! 😊",
        "recalc_confirm":    "Got it! 😊 Let me recalculate your packages with {change}.",
        "package_buttons_body": "Which package would you like?",
        # Unknown button
        "unknown_button": "No worries! 😊 Let me re-send the options:",
    },
    "rw": {
        "start_booking": (
            "Nziza! 🎉 Kugira ngo dutegure session yanyu, "
            "ngomba kubabaza ibibazo bike kugira ngo "
            "twubake package ikubahirije.\n\nTangirira! 👇"
        ),
        "start_prices": (
            "Ibiciro byacu biterwa n'ibiri muri package. 📦\n\n"
            "Ngomba kubabaza ibibazo bike "
            "kugira ngo mbahe igiciro cyihariye!"
        ),
        "start_question": (
            "Yego rwose! 😊 Baza ikibazo cyawe "
            "kandi nzagerageza kukifashisha."
        ),
        "package_chosen": (
            "Amahitamo nziza! 🎉 Mwahisemo *{package_name} Package*.\n\n"
            "Kugira ngo twohereze itariki yanyu, "
            "mwishyure booking fee ya *20,000 RWF* kuri:\n\n"
            "📱 MTN MoMo: *798741*\n"
            "Izina: *Kigali Photography Ltd*\n\n"
            "Andi yishyurwa session irangiye. "
            "Mutubanize murangije! 🙏"
        ),
        "package_choice_body": "Ni iki mushaka gukora?",
        "btn_paid_title":  "✅ Nishyuye",
        "btn_agent_title": "🧑 Vugana n'Umukozi",
        "payment_confirmed": (
            "Murakoze! 🙏 Twayakiriye inyandiko yanyu.\n\n"
            "Turimo gusuzuma payment yanyu kandi tuzemeza "
            "igaburo ryanyu vuba. "
            "Umwe mu bakoze bacu azaza vuba! 😊"
        ),
        "talk_to_agent": (
            "Yego rwose! 😊 Umwe mu bakoze bacu azaza vuba.\n"
            "Murakoze kwihangana! 🙏"
        ),
        "resend_options":    "Ntakibazo! 😊 Reka nongere nohereze amahitamo:",
        "fallback_question": "Ikibazo cyiza! 😊 Itsinda ryacu rizakurikira.",
        "fallback_recalc":   "Mubwire ibyo mushaka guhindura kandi nzababara! 😊",
        "recalc_confirm":    "Nkuwe! 😊 Reka nongere nbare packages na {change}.",
        "package_buttons_body": "Ni iyihe package mushaka?",
        "unknown_button": "Ntakibazo! 😊 Reka nongere nohereze amahitamo:",
    },
    "fr": {
        "start_booking": (
            "Parfait! 🎉 Pour préparer votre séance, "
            "j'ai juste besoin de vous poser quelques questions rapides "
            "pour créer le bon package pour vous.\n\nC'est parti! 👇"
        ),
        "start_prices": (
            "Nos prix dépendent de ce qui est inclus dans votre package. 📦\n\n"
            "Laissez-moi vous poser quelques questions rapides "
            "et je construirai votre prix personnalisé!"
        ),
        "start_question": (
            "Bien sûr! 😊 N'hésitez pas à poser votre question "
            "et je ferai de mon mieux pour vous aider."
        ),
        "package_chosen": (
            "Excellent choix! 🎉 Vous avez sélectionné le *{package_name} Package*.\n\n"
            "Pour réserver votre date, veuillez envoyer les frais de réservation "
            "de *20,000 RWF* à:\n\n"
            "📱 MTN MoMo: *798741*\n"
            "Nom: *Kigali Photography Ltd*\n\n"
            "Le reste est payé après la séance. "
            "Faites-nous signe une fois que c'est fait! 🙏"
        ),
        "package_choice_body": "Que souhaitez-vous faire ensuite?",
        "btn_paid_title":  "✅ J'ai Envoyé",
        "btn_agent_title": "🧑 Parler à un Agent",
        "payment_confirmed": (
            "Merci! 🙏 Nous avons reçu votre confirmation.\n\n"
            "Nous vérifions votre paiement et confirmerons votre réservation "
            "sous peu. Un membre de notre équipe sera avec vous bientôt! 😊"
        ),
        "talk_to_agent": (
            "Bien sûr! 😊 Un membre de notre équipe sera avec vous bientôt.\n"
            "Merci de votre patience! 🙏"
        ),
        "resend_options":    "Pas de souci! 😊 Je vous renvoie les options:",
        "fallback_question": "Bonne question! 😊 Notre équipe vous répondra.",
        "fallback_recalc":   "Dites-moi ce que vous souhaitez changer et je recalcule! 😊",
        "recalc_confirm":    "Compris! 😊 Je recalcule vos packages avec {change}.",
        "package_buttons_body": "Quel package souhaitez-vous?",
        "unknown_button": "Pas de souci! 😊 Je vous renvoie les options:",
    },
}

def _m(client_or_lang, key: str, **kwargs) -> str:
    """
    Récupère un message dans la bonne langue.
    Accepte un objet client ou une string langue directement.
    kwargs = variables à formater dans le message (ex: package_name="Gold")
    """
    if isinstance(client_or_lang, str):
        lang = client_or_lang
    else:
        lang = getattr(client_or_lang, "language", "en") or "en"
    
    lang_msgs = MESSAGES.get(lang, MESSAGES["en"])
    msg = lang_msgs.get(key, MESSAGES["en"].get(key, ""))
    
    return msg.format(**kwargs) if kwargs else msg

def _send_main_menu(to: str, lang: str) -> None:
    menu = MAIN_MENU.get(lang, MAIN_MENU["en"])
    send_text(to=to, message=menu["text"])
    send_buttons(to=to, body=menu["body"], buttons=menu["buttons"])


# ─── HELPERS DISCOVERY ───────────────────────────────────────────────────────

def _get_next_unanswered_step(state: dict, lang: str = "en") -> dict | None:
    steps = DISCOVERY_STEPS.get(lang, DISCOVERY_STEPS["en"])
    for step in steps:
        if state.get(step["key"]) is None:
            return step
    return None


def _send_next_discovery_question(to: str, journey,client) -> None:
    """Envoie la prochaine question discovery non répondue."""
    state = journey.discovery_state or {}
    next_step = _get_next_unanswered_step(state, lang=client.language)
    if next_step:
        _send_discovery_question(to, next_step)


def _send_discovery_question(to: str, step: dict) -> None:
    """Envoie une question discovery avec ses boutons."""
    send_buttons(
        to=to,
        body=step["message"],
        buttons=step["buttons"],
    )


def _reset_discovery(journey) -> None:
    """Réinitialise l'état discovery pour un nouveau flow."""
    journey.discovery_state = {
        "session_type": None,
        "frames":       None,
        "cake":         None,
        "video":        None,
    }
    journey.save(update_fields=["discovery_state", "updated_at"])


def _set_flow_mode(journey, mode: str) -> None:
    """Sauvegarde le mode de flow actif."""
    journey.flow_mode = mode
    journey.save(update_fields=["flow_mode", "updated_at"])


#Ajoute apres pour gerer les reponses du clients pendant les discovery questions ou plus

def handle_text_during_discovery(
    text: str,
    from_number: str,
    journey,
    client,
    conversation,
) -> str:
    text_clean = text.strip().lower()

    # Texte trop court → renvoyer boutons
    MEANINGLESS = {"ok", "okay", "k", "hmm", "lol", "haha", "👍", "🙏"}
    if len(text_clean) <= 3 or text_clean in MEANINGLESS:
        send_text(to=from_number, message=_m(client, "resend_options"))
        _resend_current_step(from_number, journey, client)
        return "resent_buttons_short_text"

    # Vérifier si discovery complète ou non
    state = journey.discovery_state or {}
    discovery_done = _get_next_unanswered_step(state) is None

    # Détecter si c'est une demande de recalcul des packages
    RECALC_KEYWORDS = [
        "remove", "add", "without", "with", "instead",
        "if i", "what if", "how much if", "price without",
        "enlever", "ajouter", "sans", "avec",
        "gukuraho", "kongeraho", "nta",
    ]
    is_recalc_request = any(kw in text_clean for kw in RECALC_KEYWORDS)

    if discovery_done and is_recalc_request:
        return _handle_package_recalc(text, from_number, journey, client, conversation)

    # Question normale → réponse IA + renvoyer l'étape courante
    try:
        from services.rag_service import retrieve_context
        from services.openai_service import call_openai

        rag_context = retrieve_context(
            query=text,
            journey_phase="booking",
            language=client.language,
            top_k=2,
        )

        # Construire le contexte packages si discovery terminée
        packages_context = ""
        if discovery_done:
            packages_context = _build_packages_context_for_prompt(journey)

        system_prompt = (
            "You are Julie, WhatsApp assistant for KP Kids Studio, Kigali. "
            "Answer the client's question briefly (2-3 sentences max, WhatsApp style). "
            "Be warm and helpful. "
            f"{packages_context}"
            f"{'Knowledge base: ' + rag_context if rag_context else ''}\n\n"
            "After your answer, end with: 'Now, back to your options 👇'"
        )

        response = call_openai(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": text}],
            escalate=False,
        )

        if response.ok:
            send_text(to=from_number, message=response.text)
        else:
            send_text(
                to=from_number,
                message=_m(client, "fallback_question"),
            )

        try:
            from services.client_service import record_tokens
            record_tokens(client, conversation,
                         response.input_tokens, response.output_tokens)
        except Exception:
            pass

    except Exception as exc:
        logger.warning("AI response during discovery failed: %s", exc)
        send_text(
            to=from_number,
            message=_m(client, "fallback_question"),
        )

    # Renvoyer l'étape courante (question OU packages selon où on en est)
    _resend_current_step(from_number, journey, client)
    return "answered_text_resent_step"


def _handle_package_recalc(
    text: str,
    from_number: str,
    journey,
    client,
    conversation,
) -> str:
    """
    Le client veut modifier les extras après la présentation des packages.
    Ex: "remove the video", "add a cake", "without frames"
    On détecte ce qu'il veut changer, on met à jour discovery_state, on recalcule.
    """
    text_lower = text.lower()
    state = journey.discovery_state or {}
    changed = False
    change_description = ""

    # Détecter remove video
    if any(w in text_lower for w in ["remove video", "without video", "no video",
                                      "remove highlight", "sans video", "gukuraho video"]):
        state["video"] = False
        changed = True
        change_description = "video removed"

    # Détecter add video
    elif any(w in text_lower for w in ["add video", "with video", "include video",
                                        "ajouter video", "kongeraho video"]):
        state["video"] = True
        changed = True
        change_description = "video added"

    # Détecter remove frames
    elif any(w in text_lower for w in ["remove frame", "without frame", "no frame",
                                        "sans frame", "gukuraho frame"]):
        state["frames"] = False
        changed = True
        change_description = "frames removed"

    # Détecter add frames
    elif any(w in text_lower for w in ["add frame", "with frame", "include frame",
                                        "ajouter frame", "kongeraho frame"]):
        state["frames"] = True
        changed = True
        change_description = "frames added"

    # Détecter remove cake
    elif any(w in text_lower for w in ["remove cake","gukuraho cake", "without cake", "no cake",
                                        "sans gateau", "sans gâteau"]):
        state["cake"] = False
        changed = True
        change_description = "cake removed"

    # Détecter add cake
    elif any(w in text_lower for w in ["add cake","kongeraho cake", "with cake", "include cake",
                                        "ajouter gateau", "ajouter gâteau"]):
        state["cake"] = True
        changed = True
        change_description = "cake added"

    # Détecter remove all extras
    elif any(w in text_lower for w in ["remove all", "no extras", "just photos", "amafoto gusa", "amafoto niyonine"
                                        "base only", "nothing else"]):
        state["frames"] = False
        state["cake"] = False
        state["video"] = False
        changed = True
        change_description = "all extras removed"

    if changed:
        # Sauvegarder le nouvel état
        journey.discovery_state = state
        journey.save(update_fields=["discovery_state", "updated_at"])

        send_text(
            to=from_number,
            message=_m(client, "recalc_confirm"),
        )
        _present_packages(from_number, journey, client)
        return f"packages_recalculated_{change_description.replace(' ', '_')}"

    else:
        # Demande de recalcul mais on n'a pas compris quoi changer
        # → Laisser l'IA répondre avec le contexte complet des prix
        packages_context = _build_packages_context_for_prompt(journey)

        from services.openai_service import call_openai
        system_prompt = (
            "You are Julie, WhatsApp assistant for KP Kids Studio, Kigali. "
            "The client is asking about modifying their package options. "
            "Answer precisely using the package prices below. "
            "Be brief (2-3 sentences, WhatsApp style). "
            "End with: 'Just let me know what you'd prefer! 😊'\n\n"
            f"{packages_context}"
        )

        response = call_openai(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": text}],
            escalate=False,
        )

        if response.ok:
            send_text(to=from_number, message=response.text)
        else:
            send_text(
                to=from_number,
                message=_m(client, "fallback_question"),
            )

        try:
            from services.client_service import record_tokens
            record_tokens(client, conversation,
                         response.input_tokens, response.output_tokens)
        except Exception:
            pass

        # Renvoyer les boutons packages
        _resend_package_buttons(from_number)
        return "recalc_unclear_ai_responded"

def _resend_current_step(to: str, journey, client) -> None:
    """
    Renvoie l'étape courante :
    - Si discovery pas terminée → renvoyer la question en cours
    - Si discovery terminée → renvoyer les boutons des packages
    """
    state = journey.discovery_state or {}
    current_step = _get_next_unanswered_step(state)

    if current_step:
        # Discovery pas finie → renvoyer la question
        lang = getattr(client, "language", "en") or "en"
        # Retrouver la version dans la bonne langue
        steps = DISCOVERY_STEPS.get(lang, DISCOVERY_STEPS["en"])
        lang_step = next(
            (s for s in steps if s["key"] == current_step["key"]),
            current_step
        )
        send_buttons(to=to, body=lang_step["message"], buttons=lang_step["buttons"])
    else:
        # Discovery terminée → renvoyer les boutons packages
        _resend_package_buttons(to)


def _resend_package_buttons(to: str, client=None) -> None:
    body = _m(client, "package_buttons_body") if client else "Which package would you like?"
    send_buttons(
        to=to,
        body=body,
        buttons=[
            {"id": "pkg_starter", "title": "🥉 Starter"},
            {"id": "pkg_silver",  "title": "🥈 Silver"},
            {"id": "pkg_gold",    "title": "🥇 Gold"},
        ],
    )


def _build_packages_context_for_prompt(journey) -> str:
    """
    Construit le contexte des packages calculés pour l'injecter dans le prompt IA.
    Comme ça l'IA connaît les vrais prix et peut répondre correctement.
    """
    state = journey.discovery_state or {}
    session_type = state.get("session_type", "studio")
    frames  = state.get("frames", False)
    cake    = state.get("cake",   False)
    video   = state.get("video",  False)

    extras_cost = 0
    extras_list = []
    if frames:
        extras_cost += 20000
        extras_list.append("2 A5 Photo Frames (+20,000 RWF)")
    if cake and video:
        extras_cost += 50000
        extras_list.append("Birthday Cake + Highlight Video (+50,000 RWF bundle)")
    elif cake:
        extras_cost += 30000
        extras_list.append("Birthday Cake (+30,000 RWF)")
    elif video:
        extras_cost += 29000
        extras_list.append("Highlight Video (+29,000 RWF)")

    home_fee = 69000 if session_type == "home" else 0
    session_label = "Home" if session_type == "home" else "Studio"

    packages = [
        {"name": "Starter", "base": 50000},
        {"name": "Silver",  "base": 70000},
        {"name": "Gold",    "base": 100000},
    ]

    lines = [
        "CURRENT PACKAGE PRICES (use these exact numbers):",
        f"Session type: {session_label}",
        f"Extras chosen: {', '.join(extras_list) if extras_list else 'None'}",
        "",
    ]
    for pkg in packages:
        total = pkg["base"] + extras_cost + home_fee
        lines.append(f"- {pkg['name']}: {total:,} RWF")

    lines += [
        "",
        "If an extra is removed:",
        f"  - Remove video (-29,000 RWF, or -21,000 if cake+video bundle)",
        f"  - Remove frames (-20,000 RWF)",
        f"  - Remove cake (-30,000 RWF, or -21,000 if cake+video bundle)",
        "",
    ]

    return "\n".join(lines)