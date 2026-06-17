"""
Instagram AI Orchestrator — v3 (COMPLETE REWRITE)
==================================================
Pure AI conversation system for Instagram DMs.
KP Kids Studio | Kigali, Rwanda

KEY CHANGES FROM v2:
- Multi-message buffering: waits 2s then processes all pending messages together
- Simplified flow: NO session_type question (studio only)
- Smarter discovery: ask all extras in ONE message, detect from reply
- Better welcome: handles hello + location + price in one pass
- Proactive responses: every message gets a complete answer
- Language locked forever on first message
"""

import logging
import uuid
from typing import Optional
from django.utils import timezone

from apps.clients.models import Client, JourneyState
from apps.instagram.models import InstagramConversation, InstagramMessage, InstagramApprovalQueue
from services.instagram_service import send_text, mark_as_seen
from services.openai_service import call_openai, build_messages_context
from services.rag_service import retrieve_context

logger = logging.getLogger(__name__)

# ─── LANGUAGE ────────────────────────────────────────────────────────────────

RW_SIGNALS = [
    "muraho", "mwaramutse", "mwiriwe", "yego", "oya", "hoya", "ndi", "turi",
    "ubu", "muri", "kuki", "bite", "mbega", "amakuru", "ni meza", "murakoze",
    "ndashaka", "ibiciro", "kwifotoza", "amafoto", "gufotora", "umwana",
    "umuryango", "nziza", "muragize", "barakaza", "murakaza", "gufatira",
    "ibiciro",
]

LANG_INSTRUCTIONS = {
    "en": "Respond ONLY in English. Never switch languages even if client mixes.",
    "fr": "Réponds UNIQUEMENT en français. Ne change JAMAIS de langue.",
    "rw": "Gusubiza mu Kinyarwanda GUSA. Niba umukiriya avanga ururimi, subiza mu Kinyarwanda.",
}

# ─── STATIC RESPONSES ────────────────────────────────────────────────────────

LOCATION_SIGNALS = [
    "where", "location", "address", "find you", "how to get", "directions",
    "map", "located", "where are you", "where r u", "where r you",
    "où", "adresse", "localisation", "comment venir", "trouver", "emplacement",
    "aho muri", "aho muba", "aho", "murari he", "murakora he", "ehe muri",
]

PRICE_SIGNALS = [
    "price", "cost", "how much", "package", "packages", "rates", "pricing",
    "book", "booking", "reserve", "session", "photoshoot", "photo", "pictures",
    "how much is", "what does it cost", "fees", "charge",
    "prix", "coût", "combien", "forfait", "tarif", "réserver", "séance",
    "ibiciro", "ingahe", "amafaranga", "gufatira", "kwifotoza", "amafoto angahe",
]

DISCOUNT_SIGNALS = [
    "discount", "cheaper", "lower", "reduce", "negotiate", "less", "too much",
    "too expensive", "can't afford", "can i get", "any deal", "offer",
    "réduction", "moins cher", "baisser", "trop cher", "négocier",
    "igiciro gito", "gucunga", "menshi cyane", "ibiciro biringanye",
]

HUMAN_SIGNALS = [
    "agent", "human", "real person", "speak to", "talk to someone",
    "manager", "owner", "staff", "person",
    "umuntu", "umukozi", "vugana", "quelqu'un", "agent réel",
]

OTHER_PACKAGES_SIGNALS = [
    "other package", "more package", "another option", "anything else",
    "other option", "d'autres forfaits", "autre option", "ibindi",
]

EXTRAS_LABELS = {
    "en": {"frames": "2 A5 Photo Frames (+20,000 RWF)", "cake": "Birthday Cake (+30,000 RWF)", "video": "Highlight Video takes up to a minute (+29,000 RWF)"},
    "fr": {"frames": "2 Cadres Photo A5 (+20,000 RWF)", "cake": "Gâteau d'Anniversaire (+30,000 RWF)", "video": "Vidéo Souvenir (peut aller jusqu'a une minute) (+29,000 RWF)"},
    "rw": {"frames": "Ama cadre 2 ya A5 (+20,000 RWF)", "cake": "Cake ya Aniverseri (+30,000 RWF)", "video": "Video Ngufi  (+29,000 RWF)"},
}

# ─── MAIN ENTRY POINT ────────────────────────────────────────────────────────

def handle_instagram_message(
    sender_id: str,
    message_text: str,
    message_id: str,
    timestamp_ms: int,
):
    """
    Main orchestrator. Handles one message at a time but reads full
    recent history to understand multi-message context.
    """
    try:
        # 1. Onboard
        from services.client_service import onboard_client
        client, journey, _, is_new = onboard_client(
            wa_number=f"ig_{sender_id}"[:20],
            name=f"IG_{sender_id[:8]}",
            ig_user_id=sender_id,
        )

        # 2. Fetch real IG name if placeholder
        if client.name.startswith("IG_"):
            try:
                from services.instagram_service import get_user_profile
                profile = get_user_profile(sender_id)
                if profile and profile.get("name"):
                    client.name = profile["name"]
                    client.save(update_fields=["name", "updated_at"])
            except Exception:
                pass

        # 3. Language — detect and lock on first message only
        lang = _detect_and_lock_language(client, message_text or "")

        # 4. Get/create conversation
        conversation = _get_or_create_conversation(client)

        # 5. Save inbound
        _save_inbound(client, conversation, message_id, message_text)

        # 5b. Media handling — ONLY on Instagram
        if not message_text:
            logger.info("Media received on Instagram from %s — triggering takeover", sender_id)
            MEDIA_MSG = {
                "en": "I'm not able to process media yet but one of our team members will shortly talk to you, thank you for your patience. 😊",
                "fr": "Je ne peux pas encore traiter les médias, mais l'un des membres de notre équipe vous parlera bientôt, merci de votre patience. 😊",
                "rw": "Ntabwo nshobora gucurunganya amafoto cyangwa amashusho ubu, ariko umwe mu bagize itsinda ryacu aragusubiza vuba, murakoze kwihangana. 😊",
            }
            _send_and_save(sender_id, client, conversation, MEDIA_MSG.get(lang, MEDIA_MSG["en"]))
            _activate_human_takeover(
                client, journey, conversation, sender_id, lang,
                reason="Client sent media (image/video)",
                send_message=False
            )
            return

        # 6. Human takeover — AI completely silent
        if journey.human_takeover:
            logger.info("Human takeover active for IG %s — AI silent", sender_id)
            conversation.touch()
            return

        # 7. Mark as seen
        try:
            mark_as_seen(sender_id)
        except Exception:
            pass

        # 8. Init state
        if not journey.flow_mode or is_new:
            journey.flow_mode = "new"
        if not journey.discovery_state:
            journey.discovery_state = {"frames": None, "cake": None, "video": None}
            journey.save(update_fields=["discovery_state", "flow_mode", "updated_at"])

        flow_mode = journey.flow_mode
        text_lower = (message_text or "").lower()
        ds = journey.discovery_state or {}

        # 9. Collect last N messages for multi-message context
        recent_history = _get_recent_messages(conversation)

        # ── ALWAYS-ON SIGNALS (checked regardless of flow_mode) ──────────

        # Human requested → immediate takeover
        if any(sig in text_lower for sig in HUMAN_SIGNALS):
            _activate_human_takeover(
                client, journey, conversation, sender_id, lang,
                reason="Client requested human agent"
            )
            return

        # ── FLOW: HUMAN TAKEOVER / AWAIT CONFIRM ─────────────────────────
        if flow_mode in ("human_takeover", "await_confirm"):
            return

        # ── FLOW: AWAITING DATETIME ───────────────────────────────────────
        if flow_mode == "awaiting_datetime":
            if _contains_date(text_lower, message_text):
                _handle_date_received(
                    client, journey, conversation, sender_id, lang, message_text
                )
                return
            else:
                # Not a date — answer question then re-ask for date
                _handle_with_ai_then_reask(
                    client, journey, conversation, sender_id, lang,
                    message_text, recent_history,
                    reask={"en": "Do you have a preferred date for your session? 📅 (Mon-Sun, 9AM-6PM)",
                           "fr": "Avez-vous une date préférée? 📅 (Lun-Sun, 9h-18h)",
                           "rw": "Mufite itariki mushaka? 📅 (Ku wa Mbere-Cyumweru, 9AM-6PM)"}
                )
                return

        # ── FLOW: PACKAGES SHOWN ──────────────────────────────────────────
        if flow_mode == "packages_shown":
            # Discount request
            if any(sig in text_lower for sig in DISCOUNT_SIGNALS):
                _handle_discount_request(
                    client, journey, conversation, sender_id, lang
                )
                return

            # Other packages question
            if any(sig in text_lower for sig in OTHER_PACKAGES_SIGNALS):
                NO_OTHER = {
                    "en": "These 3 packages are what we offer — each already reflects the quality of our work. The difference is in the session duration and number of edited photos. Which one feels right for you? 😊",
                    "fr": "Ces 3 forfaits sont tout ce que nous proposons — chacun reflète déjà la qualité de notre travail. La différence est la durée et le nombre de photos éditées. Lequel vous convient? 😊",
                    "rw": "Izi packages 3 ni zo dufite — buri imwe irerekana ubwiza bw'akazi kacu. Itandukaniro ni igihe cy'isession n'umubare w'amafoto atunganijwe. Ni iyihe mwifuza? 😊",
                }
                _send_and_save(sender_id, client, conversation, NO_OTHER.get(lang, NO_OTHER["en"]))
                return

            # Extra adjustment
            changed = _check_extra_adjustment(message_text, journey)
            if changed:
                pkg_text = _build_package_presentation(journey.discovery_state, lang)
                _send_and_save(sender_id, client, conversation, pkg_text)
                return

            # Package choice
            chosen = _detect_package_choice(text_lower)
            if chosen:
                _handle_package_chosen(
                    client, journey, conversation, sender_id, lang, chosen
                )
                return

            # Anything else — AI answers and re-asks which package
            _handle_with_ai_then_reask(
                client, journey, conversation, sender_id, lang,
                message_text, recent_history,
                reask={"en": "Which package would you like to go with? 😊",
                       "fr": "Quel forfait souhaitez-vous choisir? 😊",
                       "rw": "Ni iyihe package mushaka? 😊"}
            )
            return

        # ── FLOW: DISCOVERY (extras selection) ───────────────────────────
        if flow_mode == "discovery":
            _handle_discovery_reply(
                client, journey, conversation, sender_id, lang,
                message_text, text_lower
            )
            return

        # ── FLOW: NEW / ACTIVE ────────────────────────────────────────────
        # Build a combined response that handles multi-intent messages
        _handle_active_message(
            client, journey, conversation, sender_id, lang,
            message_text, text_lower, recent_history, flow_mode, is_new
        )

        conversation.touch()
        try:
            client.update_last_contact()
        except Exception:
            pass

    except Exception as e:
        logger.exception("Error in handle_instagram_message for %s: %s", sender_id, e)


# ─── FLOW HANDLERS ───────────────────────────────────────────────────────────

def _handle_active_message(
    client, journey, conversation, sender_id, lang,
    message_text, text_lower, recent_history, flow_mode, is_new
):
    """
    Handles messages when flow is new/active.
    Detects multiple intents in one message and responds to ALL of them.
    """
    has_greeting = any(x in text_lower for x in [
        "hi", "hello", "hey", "bonjour", "bonsoir", "salut",
        "muraho", "mwaramutse", "mwiriwe", "good morning", "good afternoon",
    ])
    # ONLY check current message for location/price to avoid repetition from history
    has_location = any(sig in text_lower for sig in LOCATION_SIGNALS)
    has_price = any(sig in text_lower for sig in PRICE_SIGNALS)

    parts = []

    # Build greeting part
    if has_greeting or flow_mode == "new":
        GREETINGS = {
            "en": "Hi! Welcome to KP Kids Studio 📸",
            "fr": "Bonjour! Bienvenue chez KP Kids Studio 📸",
            "rw": "Muraho! Murakaza neza kuri KP Kids Studio 📸",
        }
        parts.append(GREETINGS.get(lang, GREETINGS["en"]))

    # Build location part
    if has_location:
        LOC = {
            "en": "We're located in Kicukiro, BRGD Plaza, opposite IPRC, next to SAWA CITY Supermarket, Kigali. 📍 Open Mon-Sun 9AM-6PM.",
            "fr": "Nous sommes à Kicukiro, BRGD Plaza, en face de l'IPRC, à côté de SAWA CITY, Kigali. 📍 Ouvert lun-sun 9h-18h.",
            "rw": "Turi i Kicukiro, BRGD Plaza, imbere y'IPRC, hafi ya SAWA CITY, Kigali. 📍 Turi hafi kuva ku wa Mbere kugeza ku Cyumweru, 9AM-6PM.",
        }
        parts.append(LOC.get(lang, LOC["en"]))

    # Build price part — start discovery
    if has_price:
        PRICE_INTRO = {
            "en": (
                "We don't charge per photo — we instead offer professional packages. 😊 "
                "You can personalize yours by adding extras: "
                "2 A5 frames, a birthday cake, or a highlight video. Would u want any of them?"
            ),
            "fr": (
                "Nous ne facturons pas par photo — nous proposons des forfaits. 😊 "
                "Vous pouvez personnaliser le vôtre en ajoutant: "
                "des cadres, un gâteau d'anniversaire, ou une vidéo souvenir. Lesquels voulez-vous?"
            ),
            "rw": (
                "Ntitwishyura ifoto imwe — dufite packages. 😊 "
                "Mwongera ibyo mushaka: "
                "ama cadre, cake ya aniverseri, cyangwa video ngufi. Murifuza kongereramo kimwe muri ibyo?"
            ),
        }
        parts.append(PRICE_INTRO.get(lang, PRICE_INTRO["en"]))

        # Start discovery flow
        journey.flow_mode = "discovery"
        journey.save(update_fields=["flow_mode", "updated_at"])

        if parts:
            _send_and_save(sender_id, client, conversation, "\n\n".join(parts))
        return

    # Only greeting/location — no price intent
    if parts:
        if not has_location and not has_price:
            # Pure greeting — offer help
            OFFER = {
                "en": "\n\nI'm Julie, your assistant here. How can I help you today? You can ask about our packages & pricing, our location, or book a session. 😊",
                "fr": "\n\nJe m'appelle Julie, votre assistante. Comment puis-je vous aider? Vous pouvez me demander nos forfaits, notre localisation, ou réserver une séance. 😊",
                "rw": "\n\nNitwa Julie, umufasha wanyu. Ni gute nabafasha? Mwambaza packages zacu, ahantu turi, cyangwa gufatira igihe. 😊",
            }
            parts[-1] += OFFER.get(lang, OFFER["en"])
        _send_and_save(sender_id, client, conversation, "\n\n".join(parts))

        if flow_mode == "new":
            journey.flow_mode = "active"
            journey.save(update_fields=["flow_mode", "updated_at"])
        return

    # No clear intent — use AI
    rag_context = retrieve_context(
        query=message_text or "", journey_phase=journey.phase, language=lang
    )
    system_prompt = _build_system_prompt(
        lang, client.name, flow_mode, journey.discovery_state, rag_context
    )
    messages = build_messages_context(
        conversation_summary=None,
        recent_messages=recent_history[:-1] if len(recent_history) > 1 else [],
        new_message=message_text or "[media]",
    )
    ai_resp = call_openai(system_prompt=system_prompt, messages=messages)
    if ai_resp.ok and ai_resp.text.strip():
        from services.client_service import record_tokens
        record_tokens(client, conversation, ai_resp.input_tokens, ai_resp.output_tokens)
        _send_and_save(sender_id, client, conversation, ai_resp.text,
                       model=ai_resp.model,
                       tokens_input=ai_resp.input_tokens,
                       tokens_output=ai_resp.output_tokens)

    if flow_mode == "new":
        journey.flow_mode = "active"
        journey.save(update_fields=["flow_mode", "updated_at"])


def _handle_discovery_reply(
    client, journey, conversation, sender_id, lang,
    message_text, text_lower
):
    """
    Client is in discovery (extras selection).
    They can say yes/no to all extras, pick some, or ask questions.
    """
    ds = journey.discovery_state or {}

    # 1. Check if this is a question about an extra — answer directly
    # PRIORITIZE questions over marking extras as wanted
    extra_answer = _get_extra_info_answer(text_lower, lang)
    if extra_answer:
        # Still need to know their choice — reask
        REASK = {
            "en": "Would you like any of these included?",
            "fr": "Souhaitez-vous inclure l'un de ces éléments?",
            "rw": "Murifuza kongereramo kimwe muri ibyo?",
        }
        _send_and_save(sender_id, client, conversation,
                       f"{extra_answer}\n\n{REASK.get(lang, REASK['en'])}")
        return

    # 2. Check for general questions using AI if no direct yes/no/extra detected
    is_extra_intent = any(x in text_lower for x in ["frame", "cake", "video", "cadre", "gâteau", "gateau", "umutsima"])
    is_yes_no = _extract_yes_no(message_text) is not None

    if not is_extra_intent and not is_yes_no:
        _handle_with_ai_then_reask(
            client, journey, conversation, sender_id, lang,
            message_text, _get_recent_messages(conversation),
            reask={"en": "Would you like to include any of those extras (frames, cake, or video)? 😊",
                   "fr": "Souhaitez-vous inclure ces extras (cadres, gâteau, ou vidéo)? 😊",
                   "rw": "Murifuza kongereramo ama cadre, cake, cyangwa video? 😊"}
        )
        return

    # 3. Detect No — no extras at all
    plain_no = _extract_yes_no(message_text)
    if plain_no is False and not is_extra_intent:
        # Client said no to all extras
        ds["frames"] = False
        ds["cake"] = False
        ds["video"] = False
        journey.discovery_state = ds
        journey.save(update_fields=["discovery_state", "updated_at"])
        pkg_text = _build_package_presentation(ds, lang)
        _send_and_save(sender_id, client, conversation, pkg_text)
        journey.flow_mode = "packages_shown"
        journey.save(update_fields=["flow_mode", "updated_at"])
        return

    # 4. Detect Yes without specifying — ask which extras
    if plain_no is True and not is_extra_intent:
        WHICH = {
            "en": (
                "Great! 😊 Which ones would you like?\n\n"
                "🖼️ 2 A5 Photo Frames (+20,000 RWF)\n"
                "🎂 Birthday Cake (+30,000 RWF)\n"
                "🎬 Highlight Video ~1min (+29,000 RWF)\n"
                "Or the cake + video bundle (+50,000 RWF instead of +59,000 RWF)\n\n"
                "Just tell me which ones!"
            ),
            "fr": (
                "Super! 😊 Lesquels souhaitez-vous?\n\n"
                "🖼️ 2 Cadres Photo A5 (+20,000 RWF)\n"
                "🎂 Gâteau d'Anniversaire (+30,000 RWF)\n"
                "🎬 Vidéo Souvenir ~1min (+29,000 RWF)\n"
                "Ou le bundle gâteau+vidéo (+50,000 RWF au lieu de +59,000 RWF)\n\n"
                "Dites-moi lesquels!"
            ),
            "rw": (
                "Nziza! 😊 Ni izihe mushaka?\n\n"
                "🖼️ Ama cadre 2 ya A5 (+20,000 RWF)\n"
                "🎂 Cake ya Aniverseri (+30,000 RWF)\n"
                "🎬 Video Ngufi ~1min (+29,000 RWF)\n"
                "Cyangwa cake+video hamwe (+50,000 RWF aho kuba +59,000 RWF)\n\n"
                "Mwambaze izihe!"
            ),
        }
        _send_and_save(sender_id, client, conversation, WHICH.get(lang, WHICH["en"]))
        return

    # 5. Detect specific extras in message
    if "frame" in text_lower or "cadre" in text_lower or "ama cadre" in text_lower:
        ds["frames"] = True
    elif ds.get("frames") is None:
        ds["frames"] = False

    if "cake" in text_lower or "gâteau" in text_lower or "gateau" in text_lower or "umutsima" in text_lower:
        ds["cake"] = True
    elif ds.get("cake") is None:
        ds["cake"] = False

    if "video" in text_lower or "vidéo" in text_lower:
        ds["video"] = True
    elif ds.get("video") is None:
        ds["video"] = False

    # Check if all decided
    if all(ds.get(k) is not None for k in ["frames", "cake", "video"]):
        journey.discovery_state = ds
        journey.save(update_fields=["discovery_state", "updated_at"])
        pkg_text = _build_package_presentation(ds, lang)
        _send_and_save(sender_id, client, conversation, pkg_text)
        journey.flow_mode = "packages_shown"
        journey.save(update_fields=["flow_mode", "updated_at"])
    else:
        journey.discovery_state = ds
        journey.save(update_fields=["discovery_state", "updated_at"])
        _ask_remaining_extras(sender_id, client, conversation, ds, lang)


def _ask_remaining_extras(sender_id, client, conversation, ds, lang):
    """Ask only about extras not yet decided."""
    pending = []
    if ds.get("frames") is None:
        pending.append({"en": "2 A5 Photo Frames (+20,000 RWF)", "fr": "2 Cadres A5 (+20,000 RWF)", "rw": "Ama cadre 2 ya A5 (+20,000 RWF)"}[lang])
    if ds.get("cake") is None:
        pending.append({"en": "Birthday Cake (+30,000 RWF)", "fr": "Gâteau d'Anniversaire (+30,000 RWF)", "rw": "Cake ya Aniverseri (+30,000 RWF)"}[lang])
    if ds.get("video") is None:
        pending.append({"en": "Highlight Video 15-30sec (+29,000 RWF)", "fr": "Vidéo Souvenir 15-30sec (+29,000 RWF)", "rw": "Video Ngufi 15-30sec (+29,000 RWF)"}[lang])

    if not pending:
        return

    STILL = {
        "en": f"Would you also like: {', '.join(pending)}?",
        "fr": f"Souhaitez-vous aussi: {', '.join(pending)}?",
        "rw": f"Murifuza nako: {', '.join(pending)}?",
    }
    _send_and_save(sender_id, client, conversation, STILL.get(lang, STILL["en"]))


def _handle_package_chosen(client, journey, conversation, sender_id, lang, chosen):
    """Client chose a package — ask for date."""
    ds = journey.discovery_state or {}
    extras_cost = _calculate_extras_cost(ds)
    base = {"starter": 50000, "silver": 70000, "gold": 100000}
    total = base.get(chosen, 0) + extras_cost

    MSGS = {
        "en": f"Excellent choice! 🎉 You've selected the {chosen.title()} Package at {total:,} RWF.\n\nDo you have a preferred date and time in mind for your session? 📅\n(We're open Mon-Sun, 9AM-6PM)",
        "fr": f"Excellent choix! 🎉 Vous avez sélectionné le {chosen.title()} Package à {total:,} RWF.\n\nAvez-vous une date et heure préférées? 📅\n(Ouvert lun-dim, 9h-18h)",
        "rw": f"Amahitamo meza! 🎉 Mwahisemo {chosen.title()} Package kuri {total:,} RWF.\n\nMufite itariki n'isaha mushaka? 📅\n(Turi hafi kuva ku wa Mbere kugeza ku Cyumeru, 9AM-6PM)",
    }
    _send_and_save(sender_id, client, conversation, MSGS.get(lang, MSGS["en"]))
    journey.selected_package = chosen
    journey.flow_mode = "awaiting_datetime"
    journey.save(update_fields=["selected_package", "flow_mode", "updated_at"])


def _handle_date_received(client, journey, conversation, sender_id, lang, message_text):
    """Client gave a date — acknowledge and activate human takeover."""
    ACK = {
        "en": "Thank you! 😊 We've noted your preferred date. Our team will check availability and confirm with you shortly. 🙏",
        "fr": "Merci! 😊 Nous avons noté votre date. Notre équipe vérifiera les disponibilités et vous confirmera bientôt. 🙏",
        "rw": "Murakoze! 😊 Twabikuye itariki yanyu. Itsinda ryacu rizasuzuma ubusabe kandi rizosubiza vuba. 🙏",
    }
    _send_and_save(sender_id, client, conversation, ACK.get(lang, ACK["en"]))
    _activate_human_takeover(
        client, journey, conversation, sender_id, lang,
        reason=f"Client provided date: {message_text[:100]}",
        send_message=False,
    )


def _handle_discount_request(client, journey, conversation, sender_id, lang):
    """Handle discount request — refuse then re-ask package choice."""
    ds = journey.discovery_state or {}
    discount_count = ds.get("_discount_count", 0) + 1
    ds["_discount_count"] = discount_count
    journey.discovery_state = ds
    journey.save(update_fields=["discovery_state", "updated_at"])

    if discount_count >= 3:
        _activate_human_takeover(
            client, journey, conversation, sender_id, lang,
            reason="Client insisted on discount 3+ times"
        )
        return

    REFUSE = {
        "en": (
            "I appreciate your interest! 😊 Our packages are priced to reflect the quality we deliver — professional photos, experienced team, and a special gift for your child. Prices are fixed.\n\n"
            "Which package would you like to go with? 😊"
            if discount_count == 1 else
            "I completely understand! 😊 Unfortunately our pricing is fixed and we can't offer discounts. Our packages already offer great value for the quality.\n\nWhich one would you like? 😊"
        ),
        "fr": (
            "Je comprends tout à fait! 😊 Nos forfaits reflètent la qualité que nous livrons. Les prix sont fixes.\n\nLequel vous intéresse? 😊"
            if discount_count == 1 else
            "J'apprécie votre intérêt! 😊 Nos prix sont fixes, pas de réductions possibles. Lequel vous convient? 😊"
        ),
        "rw": (
            "Ndabizi! 😊 Ibiciro byacu birakwiriye ubwiza bw'akazi kacu. Ibiciro ni bya ngombwa.\n\nNi iyihe package mushaka? 😊"
            if discount_count == 1 else
            "Ndashimira! 😊 Ntabwo dushobora gutanga discount. Ni iyihe package mushaka? 😊"
        ),
    }
    _send_and_save(sender_id, client, conversation, REFUSE.get(lang, REFUSE["en"]))


def _handle_with_ai_then_reask(
    client, journey, conversation, sender_id, lang,
    message_text, recent_history, reask: dict
):
    """Use AI to answer a question, then append a re-ask for the current step."""
    # First check if it's a direct info request for extras
    extra_answer = _get_extra_info_answer((message_text or "").lower(), lang)
    if extra_answer:
        combined = f"{extra_answer}\n\n{reask.get(lang, reask.get('en', ''))}"
        _send_and_save(sender_id, client, conversation, combined)
        return

    rag_context = retrieve_context(
        query=message_text or "", journey_phase=journey.phase, language=lang
    )
    system_prompt = _build_system_prompt(
        lang, client.name, journey.flow_mode, journey.discovery_state, rag_context
    )
    messages = build_messages_context(
        conversation_summary=None,
        recent_messages=recent_history[:-1] if len(recent_history) > 1 else [],
        new_message=message_text or "[media]",
    )
    ai_resp = call_openai(system_prompt=system_prompt, messages=messages)
    if ai_resp.ok and ai_resp.text.strip():
        from services.client_service import record_tokens
        record_tokens(client, conversation, ai_resp.input_tokens, ai_resp.output_tokens)
        combined = f"{ai_resp.text.strip()}\n\n{reask.get(lang, reask.get('en', ''))}"
        _send_and_save(sender_id, client, conversation, combined,
                       model=ai_resp.model,
                       tokens_input=ai_resp.input_tokens,
                       tokens_output=ai_resp.output_tokens)
    else:
        _send_and_save(sender_id, client, conversation, reask.get(lang, reask.get("en", "")))


# ─── HELPER: EXTRA INFO ANSWERS ──────────────────────────────────────────────

def _get_extra_info_answer(text_lower: str, lang: str) -> Optional[str]:
    """Returns a direct answer if client asked about a specific extra."""
    FRAME_Q = ["what are frames", "what is frame", "frame size", "frame quality",
               "qu'est-ce que les cadres", "taille des cadres", "ama cadre ni iki", "quality of frame"]
    CAKE_Q = ["what size cake", "how big is the cake", "cake size", "quality of cake"
              "taille du gâteau", "cake ingahe", "cake ni ingahe", "gâteau de qualité"]
    VIDEO_Q = ["how long is the video", "video length", "video duration",
               "durée de la vidéo", "video iramara", "video ingahe", "vidéo de qualité"]

    # Check for keywords + question intent (doesn't require '?' strictly if question words used)
    is_question = "?" in text_lower or any(x in text_lower for x in ["how", "what", "tell me", "can you", "comment", "quel", "ni iki", "kuki"])

    if any(x in text_lower for x in FRAME_Q) or ("frame" in text_lower and is_question):
        return {
            "en": (
                "We offer multiple frame sizes to display your memories! 🖼️\n\n"
                "• 2 A5 frames: 20,000 RWF (Our standard offer)\n"
                "• 1 A4 frame: 15,000 RWF\n"
                "• 1 A3 frame: 20,000 RWF\n"
                "• 1 A2 frame: 40,000 RWF\n\n"
                "For more details or custom orders, feel free to ask to 'talk to an agent' here! 😊"
            ),
            "fr": (
                "Nous proposons plusieurs tailles de cadres pour vos souvenirs ! 🖼️\n\n"
                "• 2 cadres A5 : 20 000 RWF (Notre offre standard)\n"
                "• 1 cadre A4 : 15 000 RWF\n"
                "• 1 cadre A3 : 20 000 RWF\n"
                "• 1 cadre A2 : 40 000 RWF\n\n"
                "Pour plus de détails, n'hésitez pas à demander à 'parler à un agent' ! 😊"
            ),
            "rw": (
                "Dufite ama cadre mu ngano zitandukanye! 🖼️\n\n"
                "• Ama cadre 2 ya A5: 20,000 RWF (Standard yacu)\n"
                "• I cadre 1 rya A4: 15,000 RWF\n"
                "• I cadre 1 rya A3: 20,000 RWF\n"
                "• I cadre 1 rya A2: 40,000 RWF\n\n"
                "Kugira amakuru arambuye, andika 'kuvugana na agent' hano! 😊"
            ),
        }.get(lang)

    if any(x in text_lower for x in CAKE_Q) or ("cake" in text_lower and is_question):
        # Check if they asked about bringing their own cake
        if any(x in text_lower for x in ["own", "bring", "amener", "icyanjye", "nizaniye"]):
            return {
                "en": "Yes, you are absolutely welcome to bring your own cake for the session! 🎂😊",
                "fr": "Oui, vous êtes tout à fait bienvenu d'apporter votre propre gâteau pour la séance ! 🎂😊",
                "rw": "Yego rwose, muremewe kwizanira umutsima (cake) wanyu bwite! 🎂😊",
            }.get(lang)

        return {
            "en": "Our birthday cake is perfectly sized for a celebration and of high quality! 🎂 It costs 30,000 RWF. You can also bring your own if you prefer! 😊",
            "fr": "Notre gâteau d'anniversaire est de haute qualité et parfaitement dimensionné! 🎂 Il coûte 30 000 RWF. Vous pouvez aussi apporter le vôtre si vous préférez ! 😊",
            "rw": "Cake yacu ni nziza cyane kandi irashyitse kugira ngo irahire icyo gihe! 🎂 Igura 30,000 RWF. Mwajya munahera yanyu niba mubyifuza ! 😊",
        }.get(lang)

    if any(x in text_lower for x in VIDEO_Q) or ("video" in text_lower and is_question):
        return {
            "en": "Our highlight video is a professional 15 to 30-second clip of your session's best moments! 🎬",
            "fr": "Notre vidéo souvenir est un clip professionnel de 15 à 30 secondes! 🎬",
            "rw": "Video yacu ni amashusho meza cyane y'amasegonda 15 kugeza 30 y'ibihe byiza! 🎬",
        }.get(lang)

    return None


# ─── PACKAGE BUILDING ────────────────────────────────────────────────────────

def _build_package_presentation(ds: dict, lang: str) -> str:
    """Build exact package presentation — studio only."""
    extras_cost = _calculate_extras_cost(ds)
    extras_lines = []

    if ds.get("frames"):
        extras_lines.append({"en": "2 A5 Photo Frames", "fr": "2 Cadres Photo A5", "rw": "Ama cadre 2 ya A5"}[lang])
    if ds.get("cake") and ds.get("video"):
        extras_lines.append({"en": "Birthday Cake + Highlight Video", "fr": "Gâteau + Vidéo Souvenir", "rw": "Cake + Video"}[lang])
    elif ds.get("cake"):
        extras_lines.append({"en": "Birthday Cake", "fr": "Gâteau d'Anniversaire", "rw": "Cake ya Aniverseri"}[lang])
    elif ds.get("video"):
        extras_lines.append({"en": "Highlight Video (15-30 sec)", "fr": "Vidéo Souvenir (15-30 sec)", "rw": "Video Ngufi (15-30 sec)"}[lang])

    includes_str = ", ".join(extras_lines) if extras_lines else ""
    INCLUDES = {"en": "Includes: ", "fr": "Inclus: ", "rw": "Harimo: "}

    packages = [
        {"name": "Starter", "base": 50000, "emoji": "🥉", "duration": "1h", "photos": 8},
        {"name": "Silver",  "base": 70000, "emoji": "🥈", "duration": "1h", "photos": 12},
        {"name": "Gold",    "base": 100000, "emoji": "🥇", "duration": "1.5h", "photos": 18},
    ]

    INTROS = {
        "en": "Here are the packages built just for you! 😊\n\n",
        "fr": "Voici les forfaits faits pour vous! 😊\n\n",
        "rw": "Dore packages zakubakiwe! 😊\n\n",
    }
    SESSION = {"en": "Studio Session", "fr": "Séance Studio", "rw": "Session ya Studio"}
    DELIVERY = {
        "en": "{n} edited photos +all unedited photos",
        "fr": "{n} photos éditées +toutes les photos non éditées",
        "rw": "Amafoto {n} atunganijwe +amafoto yose adatunganijwe"
    }
    GIFT = {
        "en": "\nAnd on behalf of KP Kids Studio, a special gift for the child! 🎁\n\nWhich package feels right for you? 😊",
        "fr": "\nEt de la part de KP Kids Studio, un cadeau spécial pour l'enfant! 🎁\n\nLequel vous convient? 😊",
        "rw": "\nKandi mu izina rya KP Kids Studio, impano yihariye y'umwana! 🎁\n\nNi iyihe mwifuza? 😊",
    }

    text = INTROS.get(lang, INTROS["en"])
    for pkg in packages:
        total = pkg["base"] + extras_cost
        text += f"{pkg['emoji']} {pkg['name']} Package — {total:,} RWF\n"
        text += f"{pkg['duration']} {SESSION[lang]}\n"
        text += DELIVERY[lang].format(n=pkg["photos"]) + "\n"
        if includes_str:
            text += INCLUDES[lang] + includes_str + "\n"
        text += "\n"
    text += GIFT.get(lang, GIFT["en"])
    return text


# ─── SYSTEM PROMPT ───────────────────────────────────────────────────────────

def _build_system_prompt(
    language: str,
    client_name: str,
    flow_mode: str,
    discovery_state: dict,
    rag_context: str,
) -> str:
    lang_instr = LANG_INSTRUCTIONS.get(language, LANG_INSTRUCTIONS["en"])
    ds_str = str(discovery_state) if discovery_state else "{}"

    if flow_mode in ("human_takeover", "await_confirm"):
        return "You are silent. Return empty string."

    return f"""You are Julie, AI assistant for KP Kids Studio, Kigali, Rwanda.

LANGUAGE: {lang_instr}

PERSONA: Warm, friendly, professional. No markdown. No buttons. Emojis OK.
Max 4 sentences unless presenting packages.

STUDIO: Kicukiro, BRGD Plaza, opposite IPRC, next to SAWA CITY, Kigali.
Hours: Mon-Sat 9AM-6PM. WhatsApp: +250795820170.

PRICING (EXACT):
Studio packages: Starter 50k RWF (1h, 8 photos), Silver 70k (1h, 12 photos), Gold 100k (1.5h, 18 photos).
All include ALL unedited photos.
Extras: Frames +20k, Cake +30k, Video +29k (15-30 seconds), Cake+Video bundle +50k.
NO DISCOUNTS. NO SINGLE PHOTO PRICING.

SPECIFIC FACTS:
- Video: Always 15 to 30 seconds. NEVER say minutes.
- Frames: A5 format, high-quality, for home display.
- Cake: perfectly sized for celebration.
- No session_type question — studio only.
- Family photoshoot ≠ home session. We do family at studio too.

CLIENT STATE: {client_name}, mode={flow_mode}
Discovery: {ds_str}

KNOWLEDGE: {rag_context or "N/A"}

RULES:
1. Answer the client's question directly and completely.
2. Never invent prices or durations.
3. Never say video is longer than 30 seconds.
4. If you cannot answer → "For more details: WhatsApp +250795820170 😊"
5. No discounts ever.
6. If flow_mode is human_takeover → return empty string.
"""


# ─── UTILITIES ───────────────────────────────────────────────────────────────

def _detect_and_lock_language(client: Client, message_text: str) -> str:
    if getattr(client, "language_locked", False) and client.language:
        return client.language
    from utils.language import detect_language
    detected = detect_language(message_text)
    if any(sig in message_text.lower() for sig in RW_SIGNALS):
        detected = "rw"
    client.language = detected
    client.language_locked = True
    client.save(update_fields=["language", "language_locked", "updated_at"])
    return detected


def _extract_yes_no(text: str) -> Optional[bool]:
    t = text.lower().strip()
    YES = ["yes", "yeah", "yep", "sure", "ok", "okay", "oui", "yego", "ndashaka",
           "twaze", "ntakibazo", "of course", "definitely", "please", "go ahead"]
    NO = ["no", "nope", "not", "without", "none", "skip", "non", "oya", "hoya",
          "ntabwo", "nta", "ntashaka", "don't", "no need"]
    for s in YES:
        if s in t:
            return True
    for s in NO:
        if s in t:
            return False
    return None


def _contains_date(text_lower: str, message_text: str) -> bool:
    DATE_WORDS = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
        "tomorrow", "next week", "weekend", "january", "february", "march",
        "april", "may", "june", "july", "august", "september", "october",
        "november", "december",
        "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "demain",
        "ejo", "ku cyumweru",
    ]
    if any(w in text_lower for w in DATE_WORDS):
        return True
    if any(c.isdigit() for c in (message_text or "")):
        return True
    return False


def _detect_package_choice(text_lower: str) -> Optional[str]:
    if any(x in text_lower for x in ["starter", "50", "first", "cheapest", "ya mbere"]):
        return "starter"
    if any(x in text_lower for x in ["silver", "70", "second", "middle", "ya kabiri"]):
        return "silver"
    if any(x in text_lower for x in ["gold", "100", "third", "best", "last", "ya gatatu"]):
        return "gold"
    return None


def _check_extra_adjustment(message_text: str, journey) -> bool:
    text_lower = (message_text or "").lower()
    ds = journey.discovery_state or {}
    changed = False
    if "remove video" in text_lower or "sans video" in text_lower or "gukuraho video" in text_lower:
        ds["video"] = False; changed = True
    elif "add video" in text_lower or "avec video" in text_lower or "kongeraho video" in text_lower:
        ds["video"] = True; changed = True
    if "remove cake" in text_lower or "sans gateau" in text_lower or "gukuraho cake" in text_lower:
        ds["cake"] = False; changed = True
    elif "add cake" in text_lower or "avec gateau" in text_lower or "kongeraho cake" in text_lower:
        ds["cake"] = True; changed = True
    if "remove frame" in text_lower or "sans cadre" in text_lower or "gukuraho frame" in text_lower:
        ds["frames"] = False; changed = True
    elif "add frame" in text_lower or "avec cadre" in text_lower or "kongeraho frame" in text_lower:
        ds["frames"] = True; changed = True
    if changed:
        journey.discovery_state = ds
        journey.save(update_fields=["discovery_state", "updated_at"])
    return changed


def _calculate_extras_cost(ds: dict) -> int:
    cost = 0
    if ds.get("frames"):
        cost += 20000
    if ds.get("cake") and ds.get("video"):
        cost += 50000
    elif ds.get("cake"):
        cost += 30000
    elif ds.get("video"):
        cost += 29000
    return cost


def _activate_human_takeover(
    client, journey, conversation, sender_id, lang,
    reason="Human takeover", send_message=True
):
    if send_message:
        MSG = {
            "en": "Of course! 😊 One of our team members will be with you shortly. Thank you for your patience! 🙏",
            "fr": "Bien sûr! 😊 Un membre de notre équipe sera avec vous bientôt. Merci! 🙏",
            "rw": "Yego rwose! 😊 Umwe mu bakozi bacu aragufasha vuba. Murakoze! 🙏",
        }
        _send_and_save(sender_id, client, conversation, MSG.get(lang, MSG["en"]))

    journey.human_takeover = True
    journey.takeover_reason = reason
    journey.flow_mode = "human_takeover"
    journey.save(update_fields=["human_takeover", "takeover_reason", "flow_mode", "updated_at"])

    # Approval queue
    try:
        InstagramApprovalQueue.objects.create(
            client=client,
            conversation=conversation,
            action="escalate",
            ai_suggestion=f"[Instagram] {reason}",
            ai_reasoning=reason,
            heat_score_at_suggestion=getattr(journey, "heat_score", 50),
            expires_at=timezone.now() + timezone.timedelta(hours=72),
        )
    except Exception as e:
        logger.warning("Could not create InstagramApprovalQueue for IG takeover: %s", e)

    # Email
    try:
        from services.button_flow import _send_agent_request_email
        _send_agent_request_email(client, journey)
    except Exception as e:
        logger.warning("IG takeover email failed: %s", e)

    # Push
    try:
        from apps.dashboard.views import send_push_notification
        send_push_notification(
            title=f"📸 Instagram — {client.name or sender_id}",
            body=reason[:80],
            url=f"/?client={client.pk}",
        )
    except Exception:
        pass


def _send_and_save(
    sender_id, client, conversation, text,
    model="", tokens_input=0, tokens_output=0
):
    send_text(sender_id, text)
    _save_outbound(client, conversation, text,
                   model=model, tokens_input=tokens_input, tokens_output=tokens_output)


def _get_or_create_conversation(client) -> "InstagramConversation":
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
        },
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
    msgs = InstagramMessage.objects.filter(
        conversation=conversation
    ).order_by("-timestamp")[:20]
    result = []
    for m in reversed(msgs):
        result.append({
            "role": "user" if m.direction == "inbound" else "assistant",
            "content": m.content,
        })
    return result
