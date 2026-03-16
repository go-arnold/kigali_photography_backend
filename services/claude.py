"""
Claude Service
==============
All interactions with the Anthropic API go through here.

Cost protection layers (in order):
  1. Conversation budget check before every call
  2. Sliding window context (last N messages only)
  3. ConversationSummary replaces old messages
  4. RAG injects only top-K chunks (not full KB)
  5. Hard max_tokens on every request
  6. Haiku by default — Sonnet only for sales resistance escalation
  7. System prompt rebuilt per turn but kept compact

Response guarantee:
  - Never raises to caller on API error — returns a safe fallback + logs
  - Caller always gets a ClaudeResponse dataclass with full metadata
"""

import logging
from dataclasses import dataclass
from typing import Optional

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

_SLIDING_WINDOW = 10
_RAG_TOP_K = 3
_HAIKU = settings.CLAUDE["DEFAULT_MODEL"]
_SONNET = settings.CLAUDE["ESCALATION_MODEL"]
_MAX_INPUT = settings.CLAUDE["MAX_INPUT_TOKENS"]
_MAX_OUTPUT = settings.CLAUDE["MAX_OUTPUT_TOKENS"]

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.CLAUDE["API_KEY"])
    return _client


@dataclass
class ClaudeResponse:
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
) -> str:
    """
    Build system prompt. Compact by design — every token here
    is paid for on EVERY message.
    """
    studio = settings.STUDIO

    lang_instruction = (
        "Respond in Kinyarwanda." if language == "rw" else "Respond in English."
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

    return (
        f"You are the AI assistant for {studio['NAME']}, a premium children's photography studio in Kigali, Rwanda.\n\n"
        f"CURRENT CONTEXT:\n"
        f"- Client: {client_name}\n"
        f"- Journey: {journey_phase} / {journey_step}\n"
        f"- Heat: {heat_label} — {heat_strategy}\n"
        f"- Language: {lang_instruction}"
        f"{children_block}\n\n"
        f"YOUR ROLE:\n"
        f"- Warm, professional, personal. Never robotic.\n"
        f"- Build emotional connection around preserving precious childhood memories.\n"
        f"- Guide client: introduction → packages → booking → prep → delivery → feedback.\n\n"
        f"ABSOLUTE RULES:\n"
        f"- NEVER reduce price for same service.\n"
        f"- NEVER send bonuses automatically — only suggest, human approves.\n"
        f"- NEVER pretend to be human if directly asked.\n"
        f"- NEVER send 2 follow-ups without a reply (unless HIGH heat).\n"
        f"- Keep responses concise — WhatsApp, not email. Max 3-4 very short paragraphs.\n"
        f"- Output must be plain text only.\n"
        f"- Do NOT use emojis.\n"
        f"- Do NOT use markdown or formatting of any kind.\n"
        f"- Do NOT use bold (**text**), italics (*text* or _text_), strikethrough (~~text~~), backticks (`text`), headings (#).\n"
        f"- Do NOT use special characters for styling.\n"
        f"- No decorative symbols.\n"
        f"- If client says stop/opt-out, acknowledge immediately and cease."
        f"{rag_block}\n\n"
        f"Studio: {studio['LOCATION']} | {studio['HOURS']} | Booking fee: {studio['BOOKING_FEE_RWF']:,} RWF"
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


def call_claude(
    system_prompt: str,
    messages: list,
    escalate: bool = False,
) -> ClaudeResponse:
    """
    Make a single API call. Always returns ClaudeResponse — never raises.

    Args:
        escalate: If True, uses Sonnet. Only for sales resistance.
    """
    model = _SONNET if escalate else _HAIKU

    from utils.tokens import estimate_messages_tokens, estimate_tokens

    estimated_input = estimate_tokens(system_prompt) + estimate_messages_tokens(
        messages
    )

    if estimated_input > _MAX_INPUT:
        logger.warning(
            "Estimated input %s > limit %s — truncating", estimated_input, _MAX_INPUT
        )
        messages = _truncate_messages(
            messages, _MAX_INPUT - estimate_tokens(system_prompt)
        )

    try:
        response = _get_client().messages.create(
            model=model,
            max_tokens=_MAX_OUTPUT,
            system=system_prompt,
            messages=messages,
        )
        text = _extract_text(response)
        result = ClaudeResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            stop_reason=response.stop_reason,
        )
        logger.info(
            "Claude OK | model=%s in=%s out=%s stop=%s",
            result.model,
            result.input_tokens,
            result.output_tokens,
            result.stop_reason,
        )
        return result

    except anthropic.RateLimitError as exc:
        logger.error("Claude rate limit: %s", exc)
        return ClaudeResponse(text=_safe_fallback(), error=f"rate_limit: {exc}")
    except anthropic.APIStatusError as exc:
        logger.error("Claude API %s: %s", exc.status_code, exc.message)
        return ClaudeResponse(
            text=_safe_fallback(), error=f"api_error_{exc.status_code}"
        )
    except Exception as exc:
        logger.exception("Claude unexpected error: %s", exc)
        return ClaudeResponse(text=_safe_fallback(), error=f"unexpected: {exc}")


def summarize_conversation(messages: list, client_name: str) -> ClaudeResponse:
    """
    Compress old messages into a ~150 word summary.
    Saves 60-70% tokens on subsequent turns.
    Always Haiku — cheap utility call.
    """
    if not messages:
        return ClaudeResponse(text="", error="no_messages")

    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    system = (
        "You are a conversation summarizer for a photography studio CRM. "
        "Create a brief factual summary. Include: client needs, children names/ages, "
        "package interest, objections raised, current sentiment. Max 90 words."
    )

    return call_claude(
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
) -> ClaudeResponse:
    """
    Lightweight classification — detects intent, objection type, heat signals.
    Returns JSON string for parsing. Always Haiku.
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

    return call_claude(
        system_prompt=system,
        messages=[{"role": "user", "content": f"{context_block}Message: {message}"}],
        escalate=False,
    )


def _extract_text(response) -> str:
    return "\n".join(
        block.text for block in response.content if hasattr(block, "text")
    ).strip()


def _safe_fallback() -> str:
    return (
        "Thank you for your message! Our team will get back to you shortly. "
        "We appreciate your patience. 📸"
    )


def _truncate_messages(messages: list, token_budget: int) -> list:
    from utils.tokens import estimate_messages_tokens

    while len(messages) > 2 and estimate_messages_tokens(messages) > token_budget:
        messages = messages[1:]
    return messages
