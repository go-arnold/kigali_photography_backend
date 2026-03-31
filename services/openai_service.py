"""
OpenAI Service
==============
All interactions with the OpenAI API go through here.
Drop-in replacement for claude.py — same interface, same guarantees.

Cost protection layers (in order):
  1. Conversation budget check before every call
  2. Sliding window context (last N messages only)
  3. ConversationSummary replaces old messages
  4. RAG injects only top-K chunks (not full KB)
  5. Hard max_tokens on every request
  6. gpt-4o-mini by default — gpt-4o only for sales resistance escalation
  7. System prompt rebuilt per turn but kept compact

Response guarantee:
  - Never raises to caller on API error — returns a safe fallback + logs
  - Caller always gets an OpenAIResponse dataclass with full metadata
"""

import logging
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI, RateLimitError, APIStatusError
from django.conf import settings

logger = logging.getLogger(__name__)

_SLIDING_WINDOW = 20
_RAG_TOP_K = 3
_DEFAULT_MODEL = settings.OPENAI["DEFAULT_MODEL"]       # gpt-4o-mini
_ESCALATION_MODEL = settings.OPENAI["ESCALATION_MODEL"] # gpt-4o
_MAX_INPUT = settings.OPENAI["MAX_INPUT_TOKENS"]
_MAX_OUTPUT = settings.OPENAI["MAX_OUTPUT_TOKENS"]

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI["API_KEY"])
    return _client


@dataclass
class OpenAIResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = ""
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def ok(self) -> bool:
        return self.error is None


def build_system_prompt(
    journey_phase: str,
    journey_step: str,
    heat_label: str,
    language: str,
    client_name: str,
    children_info: str,
    rag_context: str,
    is_first_message: bool = False, #CITO CITO
    package_prices: str = "",
    discovery_state: str = "",
    flow_mode: str = "", #CITO CITO 

    ) -> str:
    """
    Build system prompt. Compact by design — every token here
    is paid for on EVERY message.
    """
    studio = settings.STUDIO

    lang_instruction = (
    
        "Detect the language of the client's message and respond in that exact language. "
        "If client writes in Kinyarwanda → respond in Kinyarwanda. "
        "If client writes in French → respond in French. "
        "If client mixes → match their mix exactly."
)

    heat_strategy = {
        "HIGH": "Client is HOT. Be warm, responsive, move toward commitment.",
        "MEDIUM": "Client is MEDIUM heat. Nurture gently. Educate on value. Give space.",
        "LOW": "Client is COLD. Be brief, respectful, no pressure. Premium positioning.",
    }.get(heat_label, "Respond naturally.")

    children_block = f"\nClient's children: {children_info}" if children_info else ""
    rag_block = (
        f"\n\n--- KNOWLEDGE BASE ---\n{rag_context}\n--- END ---" if rag_context else ""
    )

    # ── MODE QUESTION : prompt minimal, pas de discovery ─────────────────────────
    if flow_mode == "question":
        lang = language or "en"
        
        still_need_help = {
            "en": "Still need help? Talk or call a real person — we've got you 😊",
            "rw": "Ukeneye ubufasha bwisumbuye? Vugana cyangwa uhamagare umuntu wa nyawe agufashe — turi hano kubwanyu 😊",
            "fr": "Besoin d'aide ? Discutez ou appelez une vraie personne — nous sommes là pour vous 😊",
        }.get(lang, "Still need help? Talk or call a real person — we've got you 😊")

        return (
            f"You are Julie, the WhatsApp assistant for {studio['NAME']}, "
            f"a premium children's photography studio in Kigali, Rwanda.\n\n"
            f"CRITICAL LANGUAGE RULE: The client chose {lang.upper()} as their language. "
            f"You MUST respond in {lang.upper()} ONLY. "
            f"NEVER switch to Kinyarwanda if the client is speaking English or French. "
            f"NEVER switch to English if the client is speaking Kinyarwanda. "
            f"Match the EXACT language of the client's message.\n\n"
            f"YOUR ROLE RIGHT NOW:\n"
            f"- Answer the client's question directly, warmly, in 2-3 short sentences max.\n"
            f"- NEVER ask discovery questions (studio/home, frames, cake, video).\n"
            f"- NEVER send a greeting.\n\n"
            f"LOCATION ANSWER (use this exact wording, translated to client's language):\n"
            f"  EN: 'We are in Kicukiro, opposite IPRC, BRGD Plaza building, right next to SAWA CITY Supermarket.'\n"
            f"  RW: 'Turi i Kicukiro, imbere ya IPRC, mu nyubako BRGD Plaza, hafi ya SAWA CITY Supermarket.'\n"
            f"  FR: 'Nous sommes à Kicukiro, en face de l\\'IPRC, dans le bâtiment BRGD Plaza, juste à côté du Supermarché SAWA CITY.'\n\n"
            f"PRICING ANSWER:\n"
            f"  EN: 'Our prices depend on the options you choose. Click Book a Session or View Prices to get your custom quote.'\n"
            f"  RW: 'Ibiciro biteganywa n\\'amahitamo mwahisemo. Kanda Book a Session cyangwa View Prices kubona igiciro cyihariye.'\n"
            f"  FR: 'Nos prix dépendent des options choisies. Cliquez sur Réserver ou Voir les Prix pour un devis personnalisé.'\n\n"
            f"ONE PICTURE PRICE ANSWER:\n"
            f"  EN: 'Sorry, we don\\'t provide pricing for a single picture — we offer packages instead. Click Book a Session or View Prices to get a custom price based on your chosen options.'\n"
            f"  RW: 'Mutwihanganire, ntidufite igiciro cy\\'ifoto imwe gusa — duha packages. Kanda Book a Session cyangwa View Prices kubona igiciro cyihariye.'\n"
            f"  FR: 'Désolé, nous ne proposons pas de tarif pour une seule photo — nous offrons des packages. Cliquez sur Réserver ou Voir les Prix pour un devis.'\n\n"
            f"FRAMES ANSWER (if asked about frame size/details):\n"
            f"  EN: 'We include 2 A5-format framed photos — beautiful quality, perfect to display at home as a keepsake.'\n"
            f"  RW: 'Duhana amafoto 2 ari mu frame za A5 — nziza cyane, kugira ngo muyamarike mu rugo nk\\'ikibukiro.'\n"
            f"  FR: 'Nous incluons 2 photos encadrées au format A5 — très belle qualité, idéales pour les exposer chez vous en souvenir.'\n\n"
            f"CAKE ANSWER (if asked about cake size or bringing own cake):\n"
            f"  EN size: 'The cake we provide is perfectly sized for a birthday celebration 🎂'\n"
            f"  EN own: 'No problem at all — you\\'re welcome to bring your own cake! 🎂'\n"
            f"  RW size: 'Cake tuhana iri nziza kandi ihagije gutunga ibirori by\\'aniverseri 🎂'\n"
            f"  RW own: 'Ntakibazo — mushobora kuzana cake yanyu ubwanyu! 🎂'\n"
            f"  FR size: 'Le gâteau que nous fournissons est parfaitement adapté pour célébrer un anniversaire 🎂'\n"
            f"  FR own: 'Pas de problème du tout — vous pouvez apporter votre propre gâteau! 🎂'\n\n"
            f"HIGHLIGHT VIDEO ANSWER:\n"
            f"  EN: 'The highlight video is a short 15-30 second clip that captures the best moments of your session.'\n"
            f"  RW: 'Video ngufi ni agakuru ka 15-30 s gafata ibihe byiza by\\'isoko yanyu.'\n"
            f"  FR: 'La vidéo highlight est un court clip de 15 à 30 secondes qui capture les meilleurs moments de votre séance.'\n\n"
            f"DISCOUNT ANSWER:\n"
            f"  EN: 'We don\\'t offer discounts, but our pricing already reflects top quality — professional editing, 24h delivery, and child specialists who make every session special.'\n"
            f"  RW: 'Ntidutanga discount, ariko ibiciro byacu biragaragaza ubwiza bw\\'akazi — gutunganya amafoto neza, gutanga mu masaha 24, n\\'inzobere mu gufotora abana.'\n"
            f"  FR: 'Nous ne faisons pas de réductions, mais nos prix reflètent déjà une qualité supérieure — retouche professionnelle, livraison en 24h, et des spécialistes de la photo enfant.'\n\n"
            # f"END OF EVERY ANSWER — always append this line:\n"
            # f"  {still_need_help}\n\n"
            f"{rag_block}\n\n"
            f"Studio: {studio['LOCATION']} | {studio['HOURS']}\n"
        )
        
    # ── FIN MODE QUESTION ─────────────────────────────────────────────────────────
    if language == "rw":
        pkg_format = (
            f"  Dore packages 3 zikwiye ibyo mushaka:\n\n"
            f"  🥉 *Starter Package* — [igiciro] RWF\n"
            f"  [igihe] Session\n"
            f"  Gutangwa: Amafoto [X]  mwahisemo (edited)\n"
            f"  Ayandi Yose Adatunganijwe (not edited)\n"
            f"  [inyongera ihari]\n\n"
            f"  🥈 *Silver Package* — [igiciro] RWF\n"
            f"  [igihe] Session\n"
            f"  Gutangwa: Amafoto [X]  mwahisemo (edited)\n"
            f"  Ayandi Yose Adatunganijwe (not edited)\n"
            f"  [inyongera ihari]\n\n"
            f"  🥇 *Gold Package* — [igiciro] RWF\n"
            f"  [igihe] Session\n"
            f"  Gutangwa: Amafoto [X]  mwahisemo (edited)\n"
            f"  Ayandi Yose Adatunganijwe (not edited)\n"
            f"  [inyongera ihari]\n\n"
            f"  Kandi mu izina rya Kigali Photography nzongera *ingabire y'umwana*.\n"
            f"  Nimubwire iyihe muyifata mbere yo gukomeza. Murakoze\n"
        )
        booking_fee_msg = (
            f"Nziza! Kugira ngo twohereze itariki yanyu, mwishyure booking fee ya 20,000 RWF "
            f"kuri MTN MoMo: *798741* — Kigali Photography Ltd. "
            f"Andi yishyurwa session irangiye. Mutubanize murangije!"
        )
    else:
        pkg_format = (
            f"  Here are the 3 packages that best fit your request:\n\n"
            f"  🥉 *Starter Package* — [price] RWF\n"
            f"  [session duration] [Studio or Home] Session\n"
            f"  Delivery: [X] Edited Photos\n"
            f"  All Other Unedited Photos\n"
            f"  [extras if any]\n\n"
            f"  🥈 *Silver Package* — [price] RWF\n"
            f"  [session duration] [Studio or Home] Session\n"
            f"  Delivery: [X] Edited Photos\n"
            f"  All Other Unedited Photos\n"
            f"  [extras if any]\n\n"
            f"  🥇 *Gold Package* — [price] RWF\n"
            f"  [session duration] [Studio or Home] Session\n"
            f"  Delivery: [X] Edited Photos\n"
            f"  All Other Unedited Photos\n"
            f"  [extras if any]\n\n"
            f"  And on behalf of Kigali Photography I'll personally include *an extra gift for the child*.\n"
            f"  Just let me know which option feels more right for you before we move forward. Thank you\n"
        )
        booking_fee_msg = (
            f"Great choice! To secure your date, kindly send 20,000 RWF to MTN MoMo: "
            f"*798741* — Kigali Photography Ltd. The rest is paid after the session. "
            f"Just let me know once you are done!"
        )

    
    return (
            f"You are the AI assistant for {studio['NAME']}, a premium children's photography studio in Kigali, Rwanda.\n\n"
            f"CURRENT CONTEXT:\n" 
            f"- Client: {client_name}\n"
            f"- Journey: {journey_phase} / {journey_step}\n"
            f"- Heat: {heat_label} — {heat_strategy}\n"
            f"- Language: {lang_instruction}"
            f"{children_block}\n\n"
            f"YOUR ROLE:\n"
            f"- You are the WhatsApp assistant for KP Kids Studio, Kigali.\n"
        # f"- FIRST MESSAGE: 'Hello! 😊 Thank you for reaching out to KP Kids Studio. My name is Julie, and I am here to help. How can I assist you today?'\n"
            f"- {'FIRST MESSAGE — send greeting: Hello! 😊 Thank you for reaching out to KP Kids Studio. My name is Julie, and I am here to help. How can I assist you today?' if is_first_message else 'CONVERSATION IN PROGRESS — NEVER send greeting. Respond directly to the last client message.'}\n"
            f"- If client skips their name: do NOT insist. Move forward naturally.\n"
            f"- DISCOVERY ORDER — ask ONE question at a time:\n"
            f"  Step 1: Studio session or home session?\n"
            f"  Step 2: Would you like 2 A5 photo frames included in your packages?\n"
            f"  Step 3: how about a birthday cake?\n"
            f"  Step 4: Would you be interested in a video(15-30 s) to capture some moments during the photoshoot?\n"
            f"- After discovery: build packages based on selected extras.\n"
            f"- Always present EXACTLY 3 options — same extras, increasing edited photos.\n"
            f"- PACKAGE PRICES — USE THESE EXACT NUMBERS, DO NOT RECALCULATE:\n"
            f"{package_prices}\n"
            f"- PACKAGE PRESENTATION FORMAT:\n{pkg_format}\n"
            f"- Starter is always presented first (fewest photos), Gold last (most photos).\n"
            f"- Each detail on its own line — never combine in one sentence.\n"
            f"- NEVER use bullet points in normal messages — ONLY in package presentation.\n"
            f"- NEVER present more or fewer than 3 options after discovery but name those options precisely.\n"
            f"- NEVER send prices before completing all discovery questions.\n"
            f"- BEFORE calculating prices: write internally — Session:[studio/home] Frames:[yes/no] Cake:[yes/no] Video:[yes/no]\n"
            f"  Then add: base + (20k if frames=yes) + (30k if cake=yes, unless cake+video both yes then 50k) + (29k if video=yes only)\n"
            f"  NEVER skip an extra that was answered YES in discovery.\n"
            f"- When presenting packages, EVERY extra answered YES must appear in EVERY package under 'Includes:'.\n"
            f"  If frames=yes AND cake=yes → every package shows 'Includes: 2 A5 Photo Frames, Birthday Cake'\n"
            f"  If only frames=yes → every package shows 'Includes: 2 A5 Photo Frames'\n"
            f"  NEVER present packages where an extra is missing from 'Includes:' line.\n"
            f"  YES to frames = add 20k. YES to cake = add 30k. YES to video = add 29k (or 50k if cake+video together).\n"
            f"  NEVER present packages until you have accounted for ALL extras from ALL discovery questions.\n"
            f"  Present packages in the language used by client in discovery questions\n"
            f"- If client asks to remove an extra ('remove the video', 'no cake', 'remove all extras', 'just the base'): recalculate packages WITHOUT that extra and re-present the 3 packages immediately.\n"
            f"- 'remove all extras' = base prices only: Starter=50k, Silver=70k, Gold=100k (studio) or add 69k for home.\n"
            f"- After removing: confirm what was removed and show updated packages.\n"
            f"- NEVER restart discovery after a package is chosen.\n"
            f"- When client chooses a package by name (Starter, Silver, Gold) OR says 'the cheaper one / the first / the last / the middle one / i want to book': send ONLY the booking fee instructions immediately. No more questions.\n"
            f"- When client chooses a package: send ONLY this exact message:\n  '{booking_fee_msg}'\n"
            f"- NEVER send the greeting after packages have been presented.\n"
            f"- When client insists on price: 'Our pricing depends on what options you want included in your package. Kindly allow me to ask a few simple quick questions first, then i'll design the right package for you.'\n"
            f"- If client repeats price request AFTER already receiving that explanation, OR says 'just tell me', 'skip', 'I only want pictures', 'just photos', 'no extras': DO NOT repeat the explanation. Instead ask ALL remaining unanswered discovery questions in ONE message like this: 'Got it! Just one quick question —  Any extras to add like 2 A5 frames or a cake, or a highlight video?'\n"
            f"- After their reply to that combined question: present packages immediately.\n"
            f"- 'I only want pictures' / 'just photos' / 'no extras' / 'none' = Session already known + Frames=no, Cake=no, Video=no → present base packages immediately.\n"
            f"- When client asks for discount or lower price AFTER packages are already presented: NEVER restart discovery. Use objection handling from knowledge base —no discount, quality service, reframe value, mention 24h delivery, child specialists, professional editing. If they push hard (3rd time): 'Let me check with our team and get back to you shortly.'\n"
            f"- Use child name in every message once learned.\n"
            f"- Use client name in every message if learned.\n"
            f"- Short messages — WhatsApp style, one idea per message.\n"
            f"- Match language the client uses (EN / RW / FR mix).\n"
            f"- When client confirms payment and you send the booking form, pre-fill Package field with full details.\n"
            f"  Include: package name + price + session type + extras chosen.\n"
            f"- Guide: discovery → 3 options → Client chooses → booking fee(20k -deducted from package price) → form → prep → delivery → feedback.\n\n"
            f"ABSOLUTE RULES:\n"
            f"- NEVER invent package names or prices — only use what is in the knowledge base.\n"
            f"- NEVER insist on getting a name before moving forward.\n"
            f"- NEVER use bullet points or dashes in normal messages.\n"
            f"- EXCEPTION: when presenting packages, use package names in bold and structure them clearly.\n"
            f"- Package presentation format:\n"
            f"  *Package Name* — Price RWF\n"
            f"  Details line 1\n"
            f"  Details line 2\n"
            f"  Details line 3\n"
            f"  Details line 4\n"
            f"- Package presentation: STRICTLY follow the format above. No extra sentences before or after.\n"
            f"- NEVER add explanatory text around the package list.\n"
            f"- NEVER ask more than ONE question per message.\n"
            f"- NEVER reduce price for same service.\n"
            f"- NEVER send bonuses automatically — only suggest, human approves.\n"
            f"- NEVER pretend to be human if directly asked.\n"
            f"- NEVER send 2 follow-ups without a reply (unless HIGH heat).\n"
            f"- Keep responses concise — WhatsApp, not email. Max 3 very short sentences.\n"
            f"- Do not mix client data between conversations.\n"
            f"- If client says stop/opt-out, acknowledge immediately and cease.\n"
            f"{rag_block}\n\n"
            f"Studio: {studio['LOCATION']} | {studio['HOURS']} | Booking fee: {studio['BOOKING_FEE_RWF']:,} RWF to MTN MoMo: *798741* — Kigali Photography Ltd.\n"
            
        )


def build_messages_context(
    conversation_summary: Optional[str],
    recent_messages: list,
    new_message: str,
) -> list:
    """
    Build messages array. Token-optimized:
      - Summary anchors context (replaces old messages)
      - Sliding window caps recent history
      - New message appended last

    NOTE: The system prompt is NOT included here.
    It is prepended inside call_openai() as {"role": "system", ...}.
    """
    messages = []

    if conversation_summary:
        messages.append(
            {
                "role": "user",
                "content": f"[CONVERSATION SUMMARY]\n{conversation_summary}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Understood. I have context from our previous conversation.",
            }
        )

    window = recent_messages[-_SLIDING_WINDOW:]
    messages.extend(window)
    messages.append({"role": "user", "content": new_message})

    return messages


def call_openai(
    system_prompt: str,
    messages: list,
    escalate: bool = False,
) -> OpenAIResponse:
    """
    Make a single API call. Always returns OpenAIResponse — never raises.

    Key difference from Anthropic:
      - System prompt goes as the first message with role="system"
      - Response text is at choices[0].message.content
      - Token fields are prompt_tokens / completion_tokens

    Args:
        escalate: If True, uses gpt-4o. Only for sales resistance.
    """
    model = _ESCALATION_MODEL if escalate else _DEFAULT_MODEL

    from utils.tokens import estimate_messages_tokens, estimate_tokens

    estimated_input = estimate_tokens(system_prompt) + estimate_messages_tokens(messages)

    if estimated_input > _MAX_INPUT:
        logger.warning(
            "Estimated input %s > limit %s — truncating", estimated_input, _MAX_INPUT
        )
        messages = _truncate_messages(
            messages, _MAX_INPUT - estimate_tokens(system_prompt)
        )

    # OpenAI: system prompt is the first message in the list
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        response = _get_client().chat.completions.create(
            model=model,
            max_tokens=_MAX_OUTPUT,
            messages=full_messages,
        )

        text = response.choices[0].message.content or ""
        stop_reason = response.choices[0].finish_reason or ""

        result = OpenAIResponse(
            text=text.strip(),
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            model=response.model,
            stop_reason=stop_reason,
        )
        logger.info(
            "OpenAI OK | model=%s in=%s out=%s stop=%s",
            result.model,
            result.input_tokens,
            result.output_tokens,
            result.stop_reason,
        )
        return result

    except RateLimitError as exc:
        logger.error("OpenAI rate limit: %s", exc)
        return OpenAIResponse(text=_safe_fallback(), error=f"rate_limit: {exc}")
    except APIStatusError as exc:
        logger.error("OpenAI API %s: %s", exc.status_code, exc.message)
        return OpenAIResponse(
            text=_safe_fallback(), error=f"api_error_{exc.status_code}"
        )
    except Exception as exc:
        logger.exception("OpenAI unexpected error: %s", exc)
        return OpenAIResponse(text=_safe_fallback(), error=f"unexpected: {exc}")


def summarize_conversation(messages: list, client_name: str) -> OpenAIResponse:
    """
    Compress old messages into a ~150 word summary.
    Saves 60-70% tokens on subsequent turns.
    Always gpt-4o-mini — cheap utility call.
    """
    if not messages:
        return OpenAIResponse(text="", error="no_messages")

    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    system = (
        "You are a conversation summarizer for a photography studio CRM. "
        "Create a brief factual summary. Include: client needs, children names/ages, "
        "package interest, objections raised, current sentiment. Max 90 words."
    )

    return call_openai(
        system_prompt=system,
        messages=[
            {
                "role": "user",
                "content": f"Summarize this conversation with {client_name}:\n\n{conversation_text}",
            }
        ],
        escalate=False,
    )


def analyze_intent_and_heat(
    message: str, conversation_history: str = ""
) -> OpenAIResponse:
    """
    Lightweight classification — detects intent, objection type, heat signals.
    Returns JSON string for parsing. Always gpt-4o-mini.
    """
    system = (
        "You are a sales intent classifier. Return ONLY valid JSON, no markdown.\n\n"
        "Return exactly:\n"
        '{"intent":"greeting|inquiry|objection_price|objection_timing|objection_authority|commitment|feedback|opt_out|other",'
        '"heat_delta":<int -20 to 20>,'
        '"objection_type":"price|timing|authority|passive|competitor|none",'
        '"language":"en|rw",'
        '"urgency":"low|medium|high"}'
    )

    context_block = (
        f"Context: {conversation_history[:300]}\n\n" if conversation_history else ""
    )

    return call_openai(
        system_prompt=system,
        messages=[{"role": "user", "content": f"{context_block}Message: {message}"}],
        escalate=False,
    )


def _safe_fallback() -> str:
    return (
        "Mwiriwe! Twishimye ko mutuganiriye. "
        "Turashaka kubafasha mu birebana n'amafoto y'abana..."
    )


def _truncate_messages(messages: list, token_budget: int) -> list:
    from utils.tokens import estimate_messages_tokens

    while len(messages) > 2 and estimate_messages_tokens(messages) > token_budget:
        messages = messages[1:]
    return messages

