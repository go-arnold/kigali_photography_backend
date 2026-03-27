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

DISCOVERY_STEPS = [
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
]

# ─── MAPPING BOUTON → SIGNIFICATION ─────────────────────────────────────────

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
        # Bouton inconnu → renvoyer le menu principal
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


def send_welcome(to: str) -> None:
    """
    Envoie le message de bienvenue + les 3 boutons entry.
    Appelé au premier message ET si le client tape du texte hors-contexte.
    """
    send_text(
        to=to,
        message=(
            "Hello! 😊 Thank you for reaching out to *KP Kids Studio*.\n"
            "My name is Julie, and I am here to help.\n\n"
            "How can I assist you today?"
        ),
    )
    send_buttons(
        to=to,
        body="Please choose an option:",
        buttons=[
            {"id": "btn_book",     "title": "📸 Book a Session"},
            {"id": "btn_prices",   "title": "💰 View Prices"},
            {"id": "btn_question", "title": "ℹ️ Ask a Question"},
        ],
    )


# ─── HANDLERS D'ACTION ───────────────────────────────────────────────────────

def _handle_action(action: str, from_number: str, journey, client) -> str:

    if action == "start_booking":
        _set_flow_mode(journey, "booking")
        _reset_discovery(journey)
        send_text(
            to=from_number,
            message=(
                "Perfect! 🎉 To prepare your session, "
                "I just need to ask you a few quick questions "
                "so we can build the right package for you.\n\n"
                "Let's start! 👇"
            ),
        )
        _send_next_discovery_question(from_number, journey)
        return "started_booking_flow"

    if action == "start_prices":
        _set_flow_mode(journey, "prices")
        _reset_discovery(journey)
        send_text(
            to=from_number,
            message=(
                "Our prices depend on what's included in your package. 📦\n\n"
                "Let me ask you a few quick questions "
                "and I'll build your custom price right away!"
            ),
        )
        _send_next_discovery_question(from_number, journey)
        return "started_prices_flow"

    if action == "start_question":
        _set_flow_mode(journey, "question")
        send_text(
            to=from_number,
            message=(
                "Of course! 😊 Feel free to type your question "
                "and I'll do my best to help you."
            ),
        )
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
    next_step = _get_next_unanswered_step(state)

    if next_step:
        _send_discovery_question(from_number, next_step)
        return f"discovery_{field}_saved_next_{next_step['key']}"
    else:
        # Toutes les questions répondues → présenter les packages
        _present_packages(from_number, journey, client)
        return "discovery_complete_packages_sent"


# ─── CALCUL ET PRÉSENTATION DES PACKAGES ────────────────────────────────────

def _present_packages(from_number: str, journey, client) -> None:
    """
    Calcule les 3 packages selon discovery_state
    et les présente avec 3 boutons de choix.
    """
    state = journey.discovery_state or {}
    session_type = state.get("session_type", "studio")
    frames  = state.get("frames", False)
    cake    = state.get("cake",   False)
    video   = state.get("video",  False)

    # ── Calcul des extras ──
    extras_cost = 0
    extras_lines = []

    if frames:
        extras_cost += 20000
        extras_lines.append("2 A5 Photo Frames")
    if cake and video:
        extras_cost += 50000
        extras_lines.append("A Birthday Cake")
        extras_lines.append("Highlight Video (15–30 sec)")
    elif cake:
        extras_cost += 30000
        extras_lines.append("Birthday Cake")
    elif video:
        extras_cost += 29000
        extras_lines.append("Highlight Video (15–30 sec)")

    home_fee = 69000 if session_type == "home" else 0
    session_label = "Home" if session_type == "home" else "Studio"
    includes_line = ", ".join(extras_lines) if extras_lines else None

    # ── Prix des 3 packages ──
    packages = [
        {"name": "Starter", "base": 50000, "duration": "1h",   "photos": 8,  "emoji": "🥉"},
        {"name": "Silver",  "base": 70000, "duration": "1h",   "photos": 12, "emoji": "🥈"},
        {"name": "Gold",    "base": 100000,"duration": "1.5h", "photos": 18, "emoji": "🥇"},
    ]

    # ── Construction du message ──
    lines = ["Here are the 3 packages built just for you:\n"]

    for pkg in packages:
        total = pkg["base"] + extras_cost + home_fee
        lines.append(f"{pkg['emoji']} *{pkg['name']} Package* — {total:,} RWF")
        lines.append(f"{pkg['duration']} {session_label} Session")
        lines.append(f"Delivery: {pkg['photos']} Edited Photos")
        lines.append("All Other Unedited Photos")
        if includes_line:
            lines.append(f"Includes: {includes_line}")
        lines.append("")  # ligne vide entre packages

    lines.append("Which one feels right for you? 😊")
    message = "\n".join(lines)

    # ── Envoi message + boutons ──
    send_text(to=from_number, message=message)
    send_buttons(
        to=from_number,
        body="Choose your package:",
        buttons=[
            {"id": "pkg_starter", "title": "🥉 Starter"},
            {"id": "pkg_silver",  "title": "🥈 Silver"},
            {"id": "pkg_gold",    "title": "🥇 Gold"},
        ],
    )


# ─── HANDLER CHOIX DE PACKAGE ────────────────────────────────────────────────

def _handle_package_choice(package_name: str, from_number: str, journey, client) -> str:
    """
    Le client a choisi un package → envoyer les instructions de paiement
    puis les boutons post-booking.
    """
    # Sauvegarder le choix
    journey.selected_package = package_name
    journey.save(update_fields=["selected_package", "updated_at"])

    # Message de paiement
    send_text(
        to=from_number,
        message=(
            f"Great choice! 🎉 You selected the *{package_name} Package*.\n\n"
            f"To secure your date, please send the booking fee of "
            f"*20,000 RWF* to:\n\n"
            f"📱 MTN MoMo: *798741*\n"
            f"Name: *Kigali Photography Ltd*\n\n"
            f"The rest is paid after the session. "
            f"Just let us know once you're done! 🙏"
        ),
    )

    # Boutons post-booking
    send_buttons(
        to=from_number,
        body="What would you like to do next?",
        buttons=[
            {"id": "btn_paid",  "title": "✅ I've Sent Payment"},
            {"id": "btn_agent", "title": "🧑 Talk to Agent"},
        ],
    )

    # Avancer le journey
    from apps.clients.models import JourneyPhase, JourneyStep
    journey.advance(JourneyPhase.BOOKING, JourneyStep.PAYMENT_CONFIRMATION)

    return f"package_chosen_{package_name.lower()}"


# ─── HANDLER PAIEMENT CONFIRMÉ ───────────────────────────────────────────────

def _handle_payment_confirmed(from_number: str, journey, client) -> str:
    """
    Client dit qu'il a payé → human takeover immédiat + email notification.
    """
    # Silencer l'IA
    journey.flag_human_takeover("Client confirmed payment via button")

    # Notifier le dashboard
    try:
        from services.journey_orchestrator import _notify_human_takeover, _send_payment_notification_email
        from apps.clients.models import JourneyPhase, JourneyStep

        # Récupérer la conversation active
        conversation = (
            client.conversations
            .filter(window_status="open")
            .order_by("-started_at")
            .first()
        )
        if conversation:
            _notify_human_takeover(client, conversation, reason="Payment confirmed by client via button")
            _send_payment_notification_email(client, conversation)
    except Exception as exc:
        logger.warning("Notification failed after payment_confirmed: %s", exc)

    # Message de confirmation au client
    send_text(
        to=from_number,
        message=(
            "Thank you! 🙏 We've received your confirmation.\n\n"
            "We're verifying your payment now and will confirm your booking shortly. "
            "A team member will be with you in a moment! 😊"
        ),
    )
    return "payment_confirmed_human_takeover"


# ─── HANDLER TALK TO AGENT ───────────────────────────────────────────────────

def _handle_talk_to_agent(from_number: str, journey, client) -> str:
    """
    Client demande un agent humain → human takeover immédiat.
    """
    journey.flag_human_takeover("Client requested human agent via button")

    try:
        from services.journey_orchestrator import _notify_human_takeover
        conversation = (
            client.conversations
            .filter(window_status="open")
            .order_by("-started_at")
            .first()
        )
        if conversation:
            _notify_human_takeover(client, conversation, reason="Client requested human agent")
    except Exception as exc:
        logger.warning("Notification failed after talk_to_agent: %s", exc)

    send_text(
        to=from_number,
        message=(
            "Of course! 😊 One of our team members will be with you shortly.\n"
            "Thank you for your patience! 🙏"
        ),
    )
    return "talk_to_agent_human_takeover"


# ─── HELPERS DISCOVERY ───────────────────────────────────────────────────────

def _get_next_unanswered_step(state: dict) -> dict | None:
    """Retourne la prochaine étape discovery sans réponse, ou None si tout est rempli."""
    for step in DISCOVERY_STEPS:
        if state.get(step["key"]) is None:
            return step
    return None


def _send_next_discovery_question(to: str, journey) -> None:
    """Envoie la prochaine question discovery non répondue."""
    state = journey.discovery_state or {}
    next_step = _get_next_unanswered_step(state)
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