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

#----------
def _send_text_and_save(to: str, message: str, client=None) -> None:
    """Envoie un message texte ET le sauvegarde en DB si client fourni."""
    send_text(to=to, message=message)
    if client:
        _save_button_message(client, message)


def _send_buttons_and_save(to: str, body: str, buttons: list, client=None) -> None:
    """Envoie des boutons ET sauvegarde le body en DB si client fourni."""
    send_buttons(to=to, body=body, buttons=buttons)
    if client:
        # On sauvegarde le body + les titres des boutons pour lisibilité
        btn_labels = " | ".join(f"[{b['title']}]" for b in buttons)
        _save_button_message(client, f"{body}\n{btn_labels}")
#----------

logger = logging.getLogger(__name__)

# ─── DÉFINITION DES ÉTAPES DISCOVERY ────────────────────────────────────────

DISCOVERY_STEPS = {
    "en": [
        {
            "key": "photo_type",
            "message": "First, what type of photoshoot is this for? 😊",
            "buttons": [
                {"id": "disc_child",  "title": "👶 Child Photoshoot"},
                {"id": "disc_family", "title": "👨‍👩‍👧 Family Photos"},
            ],
        },
        {
            "key": "session_type",
            "message": "Where would you prefer your session? 📸",
            "buttons": [
                {"id": "disc_studio", "title": "🎨 At the Studio"},
                {"id": "disc_home",   "title": "🏠 At Home"},
            ],
        },
        {
            "key": "frames",
            "message": "Would you like 2 A5 photo frames added to your package? 🖼️",
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
            "message": "Would you like a short highlight video included in your package? 🎬",
            "buttons": [
                {"id": "disc_video_yes", "title": "✅ Yes"},
                {"id": "disc_video_no",  "title": "❌ No"},
            ],
        },
    ],
    "rw": [
        {
            "key": "photo_type",
            "message": "Mbere na mbere, ni ubuhe bwoko bwa photoshoot mwifuzako twabakorera? 😊",
            "buttons": [
                {"id": "disc_child",  "title": "👶 Gufotoza Umwana"},
                {"id": "disc_family", "title": "👨‍👩‍👧 Cg Umuryango"},
            ],
        },
        {
            "key": "session_type",
            "message": "Murifuzako twabafotorera he? 📸",
            "buttons": [
                {"id": "disc_studio", "title": "🎨 Muri Studio"},
                {"id": "disc_home",   "title": "🏠 Mu Rugo"},
            ],
        },
        {
            "key": "frames",
            "message": "Murifuzako Twabongereramo frame 2 za A5 muri package yanyu? 🖼️",
            "buttons": [
                {"id": "disc_frames_yes", "title": "✅ Yego"},
                {"id": "disc_frames_no",  "title": "❌ Hoya"},
            ],
        },
        {
            "key": "cake",
            "message": "Murifuzako Twabakorera na cake? 🎂",
            "buttons": [
                {"id": "disc_cake_yes", "title": "✅ Yego"},
                {"id": "disc_cake_no",  "title": "❌ Hoya"},
            ],
        },
        {
            "key": "video",
            "message": "Twabakorera naka video kagufi? 🎬",
            "buttons": [
                {"id": "disc_video_yes", "title": "✅ Yego"},
                {"id": "disc_video_no",  "title": "❌ Hoya"},
            ],
        },
    ],
    "fr": [
        {
            "key": "photo_type",
            "message": "Tout d'abord, quel type de séance souhaitez-vous? 😊",
            "buttons": [
                {"id": "disc_child",  "title": "👶 Séance Enfant"},
                {"id": "disc_family", "title": "👨‍👩‍👧 Séance Famille"},
            ],
        },
        {
            "key": "session_type",
            "message": "Où préférez-vous votre séance? 📸",
            "buttons": [
                {"id": "disc_studio", "title": "🎨 Au Studio"},
                {"id": "disc_home",   "title": "🏠 À Domicile"},
            ],
        },
        {
            "key": "frames",
            "message": "Souhaitez-vous 2 cadres photo A5 inclus dans le paquet? 🖼️",
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
            "message": "Voulez-vous qu'on inclut une courte vidéo souvenir? 🎬",
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
        "session_studio": "yo kwifotoza muri Studio",
        "session_home": "Session mu Rugo",
        "delivery": "Hakubiyemo: Amafoto {photos} mwahisemo atunganijwe",
        "unedited": "Ayandi mafoto Yose Adatunganijwe(unedited)",
        "includes": "Harimo: {includes}",
        "question": "Kandi mu izina rya Kigali Photography, Tuzabongereramo impano yihariye y'umwana, murifuzako ari iyihe package twabakorera? 😊",
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
        "frames":    "Ama cadre 2 y'amafoto ya A5",
        "cake":      "Cake ya Aniverseri",
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
    "disc_child":  ("discovery", "photo_type", "child"),
    "disc_family": ("discovery", "photo_type", "family"),
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
def send_welcome(to: str, client=None) -> None:
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
    _send_buttons_and_save(
        to=to,
        body="Language / Ururimi / Langue:",
        buttons=[
            {"id": "lang_en", "title": "🇬🇧 English"},
            {"id": "lang_rw", "title": "🇷🇼 Kinyarwanda"},
            {"id": "lang_fr", "title": "🇫🇷 Français"},
        ],
        client=client,
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
        client.language_locked = True #nexplit
        client.save(update_fields=["language", "language_locked", "updated_at"]) #nexplit
        journey.flow_mode = "menu_shown"
        try:
            from services.journey_orchestrator import advance_journey
            advance_journey(journey, "entry", "main_menu")
        except Exception:
            pass
        _send_main_menu(to=from_number, lang=lang, client = client)
        return f"language_set_{lang}"

    if action == "start_booking":
        _set_flow_mode(journey, "booking")
        _reset_discovery(journey)
        try:
            from services.journey_orchestrator import advance_journey
            advance_journey(journey, "discovery", "questions")
        except Exception:
            pass
        _send_text_and_save(from_number, _m(client, "start_booking"), client)
        _send_next_discovery_question(from_number, journey, client)
        return "started_booking_flow"

    if action == "start_prices":
        _set_flow_mode(journey, "prices")
        _reset_discovery(journey)
        try:
            from services.journey_orchestrator import advance_journey
            advance_journey(journey, "discovery", "questions")
        except Exception:
            pass
        _send_text_and_save(from_number, _m(client, "start_prices"), client)
        _send_next_discovery_question(from_number, journey, client)
        return "started_prices_flow"

    if action == "start_question":
        _set_flow_mode(journey, "question")
        try:
            from services.journey_orchestrator import advance_journey
            advance_journey(journey, "question", "active")
        except Exception:
            pass
        _send_text_and_save(from_number, _m(client, "start_question"), client)
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
        _send_discovery_question(from_number, next_step, client)
        return f"discovery_{field}_saved_next_{next_step['key']}"
    else:
        try:
            from services.journey_orchestrator import advance_journey
            advance_journey(journey, "discovery", "complete")
        except Exception:
            pass
        # Toutes les questions répondues → présenter les packages
        _present_packages(from_number, journey, client)
        try:
            from services.journey_orchestrator import advance_journey
            advance_journey(journey, "packages", "presented")
        except Exception:
            pass
        return "discovery_complete_packages_sent"


# ─── CALCUL ET PRÉSENTATION DES PACKAGES Cherche ici────────────────────────────────────

def _present_packages(from_number: str, journey, client) -> None:
    state = journey.discovery_state or {}
    lang = getattr(client, "language", "en") or "en"
    msgs = PACKAGE_MESSAGES.get(lang, PACKAGE_MESSAGES["en"])
    labels = EXTRAS_LABELS.get(lang, EXTRAS_LABELS["en"])

    session_type = state.get("session_type", "studio")
    frames = state.get("frames", False)
    cake   = state.get("cake",   False)
    video  = state.get("video",  False)

    # Calcul extras (identique pour studio et home)
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

    includes_line = ", ".join(extras_lines) if extras_lines else None

    if session_type == "home":
        _present_premium_package(from_number, journey, client,
                                  extras_cost, includes_line, msgs, lang)
    else:
        _present_studio_packages(from_number, extras_cost, includes_line, msgs, client)


def _present_studio_packages(
    from_number: str,
    extras_cost: int,
    includes_line,
    msgs: dict,
    client=None
) -> None:
    """Présente les 3 packages studio (Starter, Silver, Gold)."""
    packages = [
        {"name": "Starter", "base": 50000,  "duration": "1h",   "photos": 8,  "emoji": "🥉"},
        {"name": "Silver",  "base": 70000,  "duration": "1h",   "photos": 12, "emoji": "🥈"},
        {"name": "Gold",    "base": 100000, "duration": "1.5h", "photos": 18, "emoji": "🥇"},
    ]

    lines = [msgs["intro"]]
    for pkg in packages:
        total = pkg["base"] + extras_cost
        lines.append(f"{pkg['emoji']} *{pkg['name']} Package* — {total:,} RWF")
        lines.append(f"{pkg['duration']} {msgs['session_studio']}")
        lines.append(msgs["delivery"].format(photos=pkg["photos"]))
        lines.append(msgs["unedited"])
        if includes_line:
            lines.append(msgs["includes"].format(includes=includes_line))
        lines.append("")

    lines.append(msgs["question"])
    _send_text_and_save(from_number, "\n".join(lines), client)
    _send_buttons_and_save(
        from_number,
        msgs["body"],
        [
            {"id": "pkg_starter", "title": "🥉 Starter"},
            {"id": "pkg_silver",  "title": "🥈 Silver"},
            {"id": "pkg_gold",    "title": "🥇 Gold"},
        ],
        client,
    )


def _present_premium_package(
    from_number: str,
    journey,
    client,
    extras_cost: int,
    includes_line,
    msgs: dict,
    lang: str,
) -> None:
    """Home session = un seul package Premium 200k."""
    base = 200000
    total = base + extras_cost

    premium_texts = {
        "en": {
            "header": f"🏆 *Premium Package* — {total:,} RWF",
            "session": "2h Home Session",
            "delivery": "Delivery: 30 Edited Photos",
            "unedited": "All Other Unedited Photos",
            "question": (
                "This is our Home Session package, tailored just for you! 😊\n\n"
                "What date and time would you prefer? 📅\n"
                #"Kindly allow us to check our availability right away!"
            ),
        },
        "rw": {
            "header": f"🏆 *Premium Package* — {total:,} RWF",
            "session": "Amasaha 2 yo kwifotoza mu Rugo",
            "delivery": "Tubatunganiriza: Amafoto 30 mwahisemo",
            "unedited": "Tukabaha nandi Yose Adatunganijwe",
            "question": (
                "Iyi ni package yo mu rugo ibabereye! 😊\n\n"
                "Mwatubwira umunsi nisaha mwifuzako twabafotora? 📅\n"
                #"Mutwihanganire akanya gato mugihe tugisuzuma ubusabe bwanyu!"
            ),
        },
        "fr": {
            "header": f"🏆 *Premium Package* — {total:,} RWF",
            "session": "2h Séance à Domicile",
            "delivery": "Livraison: 30 Photos Éditées",
            "unedited": "Toutes les Autres Non Éditées",
            "question": (
                "Voici notre package Séance à Domicile, fait pour vous! 😊\n\n"
                "Dites nous, Quelle date et heure préférez-vous? 📅\n"
                #"Nous vérifierons notre disponibilité immédiatement!"
            ),
        },
    }

    pt = premium_texts.get(lang, premium_texts["en"])

    lines = [
        pt["header"],
        pt["session"],
        pt["delivery"],
        pt["unedited"],
    ]
    if includes_line:
        lines.append(msgs["includes"].format(includes=includes_line))
    lines.append("")
    lines.append(pt["question"])

    #send_text(to=from_number, message="\n".join(lines))
    _send_text_and_save(from_number, "\n".join(lines), client)

    # Sauvegarder directement — pas de choix à faire pour home
    journey.selected_package = f"Premium — {total:,} RWF"
    journey.flow_mode = "awaiting_datetime"
    journey.save(update_fields=["selected_package", "flow_mode", "updated_at"])

    # # Bouton Talk to Agent uniquement
    # agent_bodies = {"en": "Need help?", "rw": "Ufite ikibazo?", "fr": "Besoin d'aide?"}
    # agent_titles = {
    #     "en": "🧑 Talk to Agent",
    #     "rw": "🧑 Vugana n'Umukozi",
    #     "fr": "🧑 Parler à un Agent",
    # }
    # send_buttons(
    #     to=from_number,
    #     body=agent_bodies.get(lang, agent_bodies["en"]),
    #     buttons=[
    #         {"id": "btn_agent", "title": agent_titles.get(lang, agent_titles["en"])},
    #     ],
    # )

# ─── HANDLER CHOIX DE PACKAGE ────────────────────────────────────────────────

def _handle_package_choice(package_name: str, from_number: str, journey, client) -> str:
    """Package studio choisi → demander date/heure préférée."""
    journey.selected_package = package_name
    journey.flow_mode = "awaiting_datetime"
    journey.save(update_fields=["selected_package", "flow_mode", "updated_at"])

    try:
        from services.journey_orchestrator import advance_journey
        advance_journey(journey, "packages", "chosen")
    except Exception:
        pass

    lang = getattr(client, "language", "en") or "en"

    datetime_msgs = {
        "en": (
            f"Great choice! 🎉 You selected the *{package_name} Package*.\n\n"
            f"What date and time would you prefer for your session? 📅\n"
            #f"Kindly allow us to check our availability right away!"
        ),
        "rw": (
            f"Murakoze! 🎉 Mwahisemo *{package_name} Package*.\n\n"
            f"Ni uwuhe munsi/itariki n'isaha mwifuzaho session yanyu? 📅\n"
            
        ),
        "fr": (
            f"Excellent choix! 🎉 Vous avez sélectionné le *{package_name} Package*.\n\n"
            f"Dites nous, quelle date et heure préférez-vous pour votre séance? 📅\n"
            #f"Nous vérifierons notre disponibilité immédiatement!"
        ),
    }
    
    #send_text(to=from_number, message=datetime_msgs.get(lang, datetime_msgs["en"]))
    _send_text_and_save(from_number, datetime_msgs.get(lang, datetime_msgs["en"]), client)

    try:
        from services.journey_orchestrator import advance_journey
        advance_journey(journey, "booking", "awaiting_datetime")
    except Exception:
        pass

    return f"package_chosen_{package_name.lower()}_awaiting_datetime"

# ─── HANDLER PAIEMENT CONFIRMÉ ───────────────────────────────────────────────

def _handle_payment_confirmed(from_number: str, journey, client) -> str:
    # Imports en dehors du try — évite UnboundLocalError
    from services.journey_orchestrator import (
        _notify_human_takeover,
        _send_payment_notification_email,
        advance_journey,
    )

    journey.flag_human_takeover("Client confirmed payment via button")

    advance_journey(journey, "booking", "payment_confirmed")
     
    # ← CORRECTION : mettre aussi flow_mode = "payment_confirmed" pour analytics
    journey.flow_mode = "payment_confirmed"
    journey.save(update_fields=["flow_mode", "updated_at"])


    # Construire le formulaire de booking pour le dashboard
    pkg  = journey.selected_package or "?"
    lang = getattr(client, "language", "en") or "en"

    if lang == "rw":
        booking_form = (
            f"Twayakiriye! Murakoze.\n\n"
            f"Mwatwuzuriza iyi myirondoro:\n\n"
            f"Izina:\n"
            f"Igitsina cy'umwana:\n"
            f"Imyaka y'umwana:\n"
            f"Package: {pkg}\n"
            f"Umunsi wo kwifotoza:\n"
            f"Isaha yo kwifotoza:"
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

    #send_text(to=from_number, message=_m(client, "payment_confirmed"))
    _send_text_and_save(from_number, _m(client, "payment_confirmed"), client)
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
            _send_agent_request_email(client, journey)
    except Exception as exc:
        logger.warning("Notification failed after talk_to_agent: %s", exc)

    #send_text(to=from_number, message=_m(client, "talk_to_agent"))
    _send_text_and_save(from_number, _m(client, "talk_to_agent"), client)
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
            {"id": "btn_book",     "title": "📸 Kwifotoza"},
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
            "Murakoze! 🎉 Kugira ngo dutegure session yanyu, "
            "twababaza ibibazo bike byoroshye kugira ngo "
            "tubakorere package ibanogeye.?\n\nTwatangia! 👇"
        ),
        "start_prices": (
            "Ibiciro byacu biterwa n'ibiri muri package. 📦\n\n"
            "twababaza ibibazo bike byoroshye "
            "kugira ngo tubahe igiciro cyihariye?"
        ),
        "start_question": (
            "Yego rwose! 😊 Baza ikibazo cyawe "
            "kandi ndagerageza kubafasha."
        ),
        "package_chosen": (
            "Murakoze! 🎉 Mwahisemo *{package_name} Package*.\n\n"
            "Kugira ngo tubafatire itariki yanyu, "
            "mwakora booking ya *20,000 RWF* kuri:\n\n"
            "📱 MTN MoMo: *798741*\n"
            "Izina: *Kigali Photography Ltd*\n\n"
            "Andi yishyurwa Kwifotoza birangiye. "
            "Mwatubwira musoje kwishyura, Murakoze! 🙏"
        ),
        "package_choice_body": "Twakomeza dute?",
        "btn_paid_title":  "✅ Nishyuye",
        "btn_agent_title": "🧑 Vugana n'Umukozi",
        "payment_confirmed": (
            "Murakoze! 🙏Mutwihanganire gato mugihe.\n\n"
            "Tukiri gusuzuma booking yanyu, "
            "Umwe mu bakozi bacu aragufasha bitarambiranye! 😊"
        ),
        "talk_to_agent": (
            "Yego rwose! 😊 Umwe mu bakozi bacu aragufasha vuba.\n"
            "Murakoze kwihangana! 🙏"
        ),
        "resend_options":    "Ntakibazo! 😊 Reka nongere nohereze amahitamo:",
        "fallback_question": "Ntakibazo! 😊 turabafasha bitarambiranye.",
        "fallback_recalc":   "Mwatubwira ibyo mwifuza guhindura tukabafasha ntakibazo! 😊",
        "recalc_confirm":    "Ntakibazo! 😊 Reka nongere mbakorere packages na {change}.",
        "package_buttons_body": "Ni iyihe package mwifuza?",
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

def _send_main_menu(to: str, lang: str, client=None) -> None:
    menu = MAIN_MENU.get(lang, MAIN_MENU["en"])
    _send_text_and_save(to, menu["text"], client)
    _send_buttons_and_save(to, menu["body"], menu["buttons"], client)


# ─── HELPERS DISCOVERY ───────────────────────────────────────────────────────

def _get_next_unanswered_step(state: dict, lang: str = "en") -> dict | None:
    steps = DISCOVERY_STEPS.get(lang, DISCOVERY_STEPS["en"])
    for step in steps:
        if state.get(step["key"]) is None:
            return step
    return None


def _send_next_discovery_question(to: str, journey, client) -> None:
    state = journey.discovery_state or {}
    next_step = _get_next_unanswered_step(state, lang=client.language)
    if next_step:
        _send_discovery_question(to, next_step, client)

def _send_discovery_question(to: str, step: dict, client=None) -> None:
    _send_buttons_and_save(to, step["message"], step["buttons"], client)


def _reset_discovery(journey) -> None:
    """Réinitialise l'état discovery pour un nouveau flow."""
    journey.discovery_state = {
        "photo_type":   None, 
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
    lang = getattr(client, "language", "en") or "en"

    # Texte trop court → renvoyer boutons directement
    MEANINGLESS = {"ok", "okay", "k", "hmm", "lol", "haha", "👍", "🙏"}
    if len(text_clean) <= 3 or text_clean in MEANINGLESS:
        send_text(to=from_number, message=_m(client, "resend_options"))

        _resend_current_step(from_number, journey, client)
        return "resent_buttons_short_text"

    state = journey.discovery_state or {}
    discovery_done = _get_next_unanswered_step(state) is None

    RECALC_KEYWORDS = [
        "remove", "add", "without", "with", "instead",
        "if i", "what if", "how much if", "price without",
        "enlever", "ajouter", "sans", "avec",
        "gukuraho", "kongeraho", "nta", "kuramo", "ongeramo",
        "vanamo", "shyiramo", "vanaho", "shyiraho", "simbuza",
        "simbura", "hindura", "hinduranya",
    ]
    is_recalc_request = any(kw in text_clean for kw in RECALC_KEYWORDS)

    if discovery_done and is_recalc_request:
        return _handle_package_recalc(text, from_number, journey, client, conversation)

    # ── Réponse IA ────────────────────────────────────────────────────────────
    ai_responded = False
    try:
        from services.rag_service import retrieve_context
        from services.openai_service import call_openai

        rag_context = retrieve_context(
            query=text,
            journey_phase="booking",
            language=lang,
            top_k=2,
        )
        packages_context = _build_packages_context_for_prompt(journey) if discovery_done else ""

        back_to_options = {
            "en": "Now, back to your options 👇",
            "rw": "Noneho, turgaruke ku mahitamo yanyu 👇",
            "fr": "Maintenant, revenons à vos options 👇",
        }.get(lang, "Now, back to your options 👇")

        system_prompt = (
            f"You are Julie, WhatsApp assistant for KP Kids Studio, Kigali.\n"
            f"CRITICAL: Respond ONLY in {lang.upper()}. Never switch languages.\n"
            f"Answer briefly (2-3 sentences, WhatsApp style). Be warm.\n\n"
            f"LOCATION: We are in Kicukiro, opposite IPRC, BRGD Plaza, next to SAWA CITY Supermarket.\n"
            f"ONE PICTURE PRICE: Sorry, no single-picture pricing — we offer packages. "
            f"Click Book a Session or View Prices for a custom quote.\n"
            f"FRAMES: 2 A5-format framed photos, beautiful quality for home display.\n"
            f"CAKE SIZE: Perfectly sized for a birthday celebration.\n"
            f"OWN CAKE: No problem — clients can bring their own cake.\n"
            f"VIDEO: A 15-30 second highlight clip of the session's best moments.\n"
            f"DISCOUNT: No discounts — quality service, 24h delivery, child specialists.\n\n"
            f"{packages_context}"
            f"{'Knowledge base:\\n' + rag_context if rag_context else ''}\n\n"
            f"After your answer, end with EXACTLY this sentence on its own line:\n"
            f"{back_to_options}"
        )

        response = call_openai(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": text}],
            escalate=False,
        )

        if response.ok:
            # 1. Réponse IA (contient déjà "back to your options" à la fin)
            #_send_text_and_save(from_number, _m(client, "talk_to_agent"), client)

            #send_text(to=from_number, message=response.text)
            _send_text_and_save(from_number, response.text, client)

            ai_responded = True

            try:
                from services.client_service import record_tokens
                record_tokens(client, conversation, response.input_tokens, response.output_tokens)
            except Exception:
                pass
        else:
            send_text(to=from_number, message=_m(client, "fallback_question"))
            #_send_text_and_save(from_number, response.text, client)
            

    except Exception as exc:
        logger.warning("AI response during discovery failed: %s", exc)
        send_text(to=from_number, message=_m(client, "fallback_question"))
        # _send_text_and_save(from_number, response.text, client)
        

    # ── Toujours envoyer dans cet ordre exact ─────────────────────────────────
    # 2. Boutons de l'étape courante (discovery question OU package buttons)
    _resend_current_step(from_number, journey, client)

    # 3. Bouton "Talk to Agent" seulement si l'IA a répondu (pas sur fallback)
    if ai_responded:
        agent_titles = {
            "en": "🧑 Talk to Agent",
            "rw": "🧑 Vugana n'Umukozi",
            "fr": "🧑 Parler à un Agent",
        }
        still_need_help_body = {
            "en": "Still need help? Talk or call a real person — we've got you 😊",
            "rw": "Ukeneye ubufasha bwisumbuye? Vugana cyangwa uhamagare umuntu wa nyawe 😊",
            "fr": "Besoin d'aide ? Discutez ou appelez une vraie personne 😊",
        }.get(lang, "Still need help? Talk or call a real person — we've got you 😊")

        _send_buttons_and_save(
            from_number,
            still_need_help_body,
            [{"id": "btn_agent", "title": agent_titles.get(lang, agent_titles["en"])}],
            client,
        )

    return "answered_text_resent_step"
# ```

# ---



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
        _send_buttons_and_save(to, lang_step["message"], lang_step["buttons"], client)
    else:
        _resend_package_buttons(to, client)

def _resend_package_buttons(to: str, client=None) -> None:
    body = _m(client, "package_buttons_body") if client else "Which package would you like?"
    buttons = [
        {"id": "pkg_starter", "title": "🥉 Starter"},
        {"id": "pkg_silver",  "title": "🥈 Silver"},
        {"id": "pkg_gold",    "title": "🥇 Gold"},
    ]
    _send_buttons_and_save(to, body, buttons, client)


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

#Gerer la partie demande de date et heure pour la reservation
def handle_datetime_response(
    text: str,
    from_number: str,
    journey,
    client,
    conversation,
) -> str:
    from services.journey_orchestrator import _notify_human_takeover
    from apps.conversations.models import ApprovalQueue, ApprovalAction, Conversation
    from django.utils import timezone

    try:
        from services.journey_orchestrator import advance_journey
        advance_journey(journey, "booking", "availability_check")
    except Exception:
        pass

    lang = getattr(client, "language", "en") or "en"
    pkg  = journey.selected_package or "?"
    state = journey.discovery_state or {}

    session_type = state.get("session_type", "studio")
    photo_type   = state.get("photo_type", "child")

    extras_list = []
    if state.get("frames"):
        extras_list.append("2 A5 Photo Frames")
    if state.get("cake") and state.get("video"):
        extras_list.append("Birthday Cake + Highlight Video")
    elif state.get("cake"):
        extras_list.append("Birthday Cake")
    elif state.get("video"):
        extras_list.append("Highlight Video")
    extras_str = ", ".join(extras_list) if extras_list else "None"

    booking_msgs = {
        "en": (
            f"Great news! 🎉 Your preferred slot is available!\n\n"
            f"To secure your booking, please send the booking fee of "
            f"*20,000 RWF* to:\n\n"
            f"📱 MTN MoMo: *798741*\n"
            f"Name: *Kigali Photography Ltd*\n\n"
            f"The rest is paid after the session. "
            f"Just let us know once you're done! 🙏"
        ),
        "rw": (
            f"Amakuru meza! 🎉 Itariki mushaka iraboneka!\n\n"
            f"Kugira ngo tubafatire itariki yanyu, "
            f"mwakishyura booking fee ya *20,000 RWF* kuri:\n\n"
            f"📱 MTN MoMo: *798741*\n"
            f"Izina: *Kigali Photography Ltd*\n\n"
            f"Andi yishyurwa kwifotoza birangiye. "
            f"Mwatubwira murangije, murakoze! 🙏"
        ),
        "fr": (
            f"Bonne nouvelle! 🎉 Votre créneau est disponible!\n\n"
            f"Pour réserver, veuillez envoyer *20,000 RWF* à:\n\n"
            f"📱 MTN MoMo: *798741*\n"
            f"Nom: *Kigali Photography Ltd*\n\n"
            f"Le reste est payé après la séance. "
            f"Faites-nous signe! 🙏"
        ),
    }
    booking_msg_for_client = booking_msgs.get(lang, booking_msgs["en"])

    paid_titles  = {"en": "✅ I've Sent Payment", "rw": "✅ Nishyuye", "fr": "✅ J'ai Envoyé"}
    agent_titles = {"en": "🧑 Talk to Agent",    "rw": "🧑 Vugana n'Umukozi", "fr": "🧑 Parler à un Agent"}
    bodies       = {"en": "What would you like to do next?", "rw": "Ni iki mushaka gukora?", "fr": "Que faire ensuite?"}

    # Ce que l'agent verra dans le dashboard
    dashboard_suggestion = (
        f"{booking_msg_for_client}\n"
    )

    # ── Étape 1 : Répondre au client immédiatement ──
    ack_msgs = {
        "en": "Thank you! 😊 We're checking availability for your preferred date. A team member will get back to you shortly! 🙏",
        "rw": "Murakoze! 😊 Mwaduha akanya gato, tugasuzuma ubusabe bwanyu, tukabafasha! 🙏",
        "fr": "Merci! 😊 Nous vérifions notre disponibilité. Un membre de notre équipe vous répondra bientôt! 🙏",
    }
    #send_text(to=from_number, message=ack_msgs.get(lang, ack_msgs["en"]))
    _send_text_and_save(from_number, ack_msgs.get(lang, ack_msgs["en"]), client)

    # ── Étape 2 : Récupérer/créer la conversation AVANT tout le reste ──
    active_conversation = conversation
    if active_conversation is None:
        active_conversation = (
            client.conversations
            .filter(window_status="open")
            .order_by("-started_at")
            .first()
        )
    if active_conversation is None:
        # Créer une conversation si vraiment aucune n'existe
        active_conversation = Conversation.objects.create(
            client=client,
            window_status=Conversation.WindowStatus.OPEN,
            window_expires_at=timezone.now() + timezone.timedelta(hours=24),
            entry_phase=getattr(journey, "phase", "booking"),
            entry_heat=getattr(journey, "heat_score", 50),
        )
        logger.warning(
            "Created fallback conversation for ApprovalQueue | client=%s",
            client.wa_number,
        )

    # ── Étape 3 : Créer l'ApprovalQueue ──
    try:
        ApprovalQueue.objects.create(
            client=client,
            conversation=active_conversation,
            action=ApprovalAction.SEND_MESSAGE,
            ai_suggestion=dashboard_suggestion,
            ai_reasoning=(
                f"Client chose {pkg} | "
                f"Session: {session_type} | "
                f"Type: {photo_type.title()} Photoshoot | "
                f"Extras: {extras_str} | "
                f"Preferred: {text}"
            ),
            heat_score_at_suggestion=getattr(
                getattr(client, "journey_state", None), "heat_score", 50
            ),
            expires_at=timezone.now() + timezone.timedelta(hours=72),
        )
        logger.info(
            "ApprovalQueue created ✅ | client=%s preferred=%s",
            client.wa_number, text,
        )
        # ← NOUVEAU : email de notification pour vérification de disponibilité
        _send_availability_check_email(client, journey, text, extras_str, pkg)
    except Exception as exc:
        logger.error(
            "ApprovalQueue creation FAILED | client=%s error=%s",
            client.wa_number, exc,
        )

    # ── Étape 4 : Activer human takeover ET mettre à jour flow_mode ──
    try:
        journey.flag_human_takeover("Client provided date — availability check needed")
        journey.flow_mode = "await_confirm"
        journey.save(update_fields=["flow_mode", "updated_at"])
    except Exception as exc:
        logger.error("Could not save journey state: %s", exc)

    return "datetime_received_human_takeover"

# FONCTIONS DE L'ENVOIE DES MAILS
# --------------------------------
def _send_agent_request_email(client, journey):
    """Email de notification quand un client demande à parler à un agent."""
    try:
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings

        state = journey.discovery_state or {}
        pkg = journey.selected_package or "Not yet chosen"
        lang = getattr(client, "language", "en") or "en"

        text_body = (
            f"Client requesting human agent.\n\n"
            f"Name: {client.name or 'Unknown'}\n"
            f"Phone: {client.wa_number}\n"
            f"Language: {lang.upper()}\n"
            f"Journey: {journey.phase}/{journey.step}\n"
            f"Heat: {journey.heat_label}\n"
            f"Package selected: {pkg}\n\n"
            f"Action: Go to dashboard and take over the conversation.\n"
            f"Dashboard: https://senior-madeleine-matabar-93648cd5.koyeb.app/"
        )

        html_body = f"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body {{margin:0;padding:0;background:#f5f0eb;font-family:'Georgia',serif;}}
  .wrapper {{max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);}}
  .header {{background:linear-gradient(135deg,#1a1a2e,#0f3460);padding:40px 30px;text-align:center;}}
  .header h1 {{color:#fff;margin:0;font-size:24px;letter-spacing:2px;text-transform:uppercase;}}
  .header p {{color:#e2b96f;margin:8px 0 0;font-size:14px;}}
  .badge {{display:inline-block;background:#ff6b35;color:#fff;padding:6px 16px;border-radius:20px;font-size:12px;font-weight:bold;margin-top:15px;}}
  .body {{padding:35px 40px;}}
  .section-title {{font-size:11px;text-transform:uppercase;letter-spacing:2px;color:#999;margin-bottom:8px;margin-top:24px;}}
  .info-block {{background:#f9f6f2;border-left:4px solid #ff6b35;border-radius:6px;padding:16px 20px;margin-bottom:16px;}}
  .info-block p {{margin:6px 0;color:#333;font-size:15px;}}
  .info-block strong {{color:#1a1a2e;}}
  .action-btn {{display:block;background:#e2b96f;color:#1a1a2e;text-align:center;padding:16px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;margin:25px 0;}}
  .footer {{background:#1a1a2e;padding:20px;text-align:center;}}
  .footer p {{color:#666;font-size:12px;margin:4px 0;}}
  .footer a {{color:#e2b96f;text-decoration:none;}}
</style></head><body>
<div class="wrapper">
  <div class="header">
    <h1>KP Kids Studio</h1>
    <p>Agent Request</p>
    <span class="badge">👤 HUMAN NEEDED</span>
  </div>
  <div class="body">
    <div class="section-title">Client Details</div>
    <div class="info-block">
      <p><strong>Name:</strong> {client.name or 'Unknown'}</p>
      <p><strong>Phone:</strong> {client.wa_number}</p>
      <p><strong>Language:</strong> {lang.upper()}</p>
    </div>
    <div class="section-title">Journey State</div>
    <div class="info-block">
      <p><strong>Phase/Step:</strong> {journey.phase}/{journey.step}</p>
      <p><strong>Heat:</strong> {journey.heat_label}</p>
      <p><strong>Package selected:</strong> {pkg}</p>
    </div>
    <div class="section-title">Action Required</div>
    <div class="info-block">
      <p>The client wants to speak with a human agent.</p>
      <p>Go to the dashboard and take over the conversation.</p>
    </div>
    <a href="https://senior-madeleine-matabar-93648cd5.koyeb.app/" class="action-btn">Open Dashboard →</a>
  </div>
  <div class="footer">
    <p>KP Kids Studio — Kigali, Rwanda</p>
    <p><a href="https://senior-madeleine-matabar-93648cd5.koyeb.app/">Dashboard</a></p>
  </div>
</div></body></html>"""

        msg = EmailMultiAlternatives(
            subject=f"👤 Agent requested — {client.name or client.wa_number}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.STUDIO_NOTIFICATION_EMAIL],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
        logger.info("Agent request email sent for %s", client.wa_number)
    except Exception as exc:
        logger.warning("Agent request email failed: %s", exc)

#Availability email
def _send_availability_check_email(client, journey, preferred_datetime, extras_str, pkg):
    """Email de notification pour vérification de disponibilité."""
    try:
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings

        state = journey.discovery_state or {}
        session_type = state.get("session_type", "studio").title()
        lang = getattr(client, "language", "en") or "en"

        text_body = (
            f"Availability check needed.\n\n"
            f"Name: {client.name or 'Unknown'}\n"
            f"Phone: {client.wa_number}\n\n"
            f"Package: {pkg}\n"
            f"Session: {session_type}\n"
            f"Extras: {extras_str}\n"
            f"Preferred date/time: {preferred_datetime}\n\n"
            f"Action: Check booking table for availability, then approve in dashboard.\n"
            f"Dashboard: https://senior-madeleine-matabar-93648cd5.koyeb.app/"
        )

        html_body = f"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body {{margin:0;padding:0;background:#f5f0eb;font-family:'Georgia',serif;}}
  .wrapper {{max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);}}
  .header {{background:linear-gradient(135deg,#1a1a2e,#0f3460);padding:40px 30px;text-align:center;}}
  .header h1 {{color:#fff;margin:0;font-size:24px;letter-spacing:2px;text-transform:uppercase;}}
  .header p {{color:#e2b96f;margin:8px 0 0;font-size:14px;}}
  .badge {{display:inline-block;background:#e2b96f;color:#1a1a2e;padding:6px 16px;border-radius:20px;font-size:12px;font-weight:bold;margin-top:15px;}}
  .body {{padding:35px 40px;}}
  .section-title {{font-size:11px;text-transform:uppercase;letter-spacing:2px;color:#999;margin-bottom:8px;margin-top:24px;}}
  .info-block {{background:#f9f6f2;border-left:4px solid #e2b96f;border-radius:6px;padding:16px 20px;margin-bottom:16px;}}
  .info-block p {{margin:6px 0;color:#333;font-size:15px;}}
  .info-block strong {{color:#1a1a2e;}}
  .datetime-block {{background:linear-gradient(135deg,#1a1a2e,#0f3460);border-radius:10px;padding:20px 24px;margin-bottom:16px;text-align:center;}}
  .datetime-block p {{color:#e2b96f;font-size:20px;font-weight:bold;margin:0;}}
  .action-btn {{display:block;background:#e2b96f;color:#1a1a2e;text-align:center;padding:16px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;margin:25px 0;}}
  .footer {{background:#1a1a2e;padding:20px;text-align:center;}}
  .footer p {{color:#666;font-size:12px;margin:4px 0;}}
  .footer a {{color:#e2b96f;text-decoration:none;}}
</style></head><body>
<div class="wrapper">
  <div class="header">
    <h1>KP Kids Studio</h1>
    <p>Availability Check</p>
    <span class="badge">📅 CHECK NEEDED</span>
  </div>
  <div class="body">
    <div class="section-title">Client Details</div>
    <div class="info-block">
      <p><strong>Name:</strong> {client.name or 'Unknown'}</p>
      <p><strong>Phone:</strong> {client.wa_number}</p>
      <p><strong>Language:</strong> {lang.upper()}</p>
    </div>
    <div class="section-title">Requested Date & Time</div>
    <div class="datetime-block">
      <p>📅 {preferred_datetime}</p>
    </div>
    <div class="section-title">Package Details</div>
    <div class="info-block">
      <p><strong>Package:</strong> {pkg}</p>
      <p><strong>Session:</strong> {session_type}</p>
      <p><strong>Extras:</strong> {extras_str}</p>
    </div>
    <div class="section-title">Action Required</div>
    <div class="info-block">
      <p>1. Check booking table for <strong>{preferred_datetime}</strong></p>
      <p>2. If available → approve the booking message in the dashboard</p>
      <p>3. If not available → contact client directly via Send Message</p>
    </div>
    <a href="https://senior-madeleine-matabar-93648cd5.koyeb.app/" class="action-btn">Open Dashboard →</a>
  </div>
  <div class="footer">
    <p>KP Kids Studio — Kigali, Rwanda</p>
    <p><a href="https://senior-madeleine-matabar-93648cd5.koyeb.app/">Dashboard</a></p>
  </div>
</div></body></html>"""

        msg = EmailMultiAlternatives(
            subject=f"📅 Availability check — {client.name or client.wa_number} | {preferred_datetime}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.STUDIO_NOTIFICATION_EMAIL],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
        logger.info("Availability check email sent for %s", client.wa_number)
    except Exception as exc:
        logger.warning("Availability check email failed: %s", exc)

#save buttons messages
def _save_button_message(client, text_content: str) -> None:
    """
    Sauvegarde un message outbound du flow boutons en DB.
    Permet au dashboard de voir l'historique complet.
    """
    import uuid
    from apps.conversations.models import (
        Message, MessageDirection, MessageStatus, Conversation
    )
    from django.utils import timezone
    try:
        conversation = (
            client.conversations
            .filter(window_status="open")
            .order_by("-started_at")
            .first()
        )
        if not conversation:
            return
        Message.objects.create(
            wa_message_id=f"btn_{uuid.uuid4().hex[:12]}",
            conversation=conversation,
            client=client,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.SENT,
            content=text_content,
            msg_type="interactive",
            generated_by_ai=False,
            approved_by_human=True,
            timestamp=timezone.now(),
        )
    except Exception as exc:
        logger.warning("Could not save button message to DB: %s", exc)