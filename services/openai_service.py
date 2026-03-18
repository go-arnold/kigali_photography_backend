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

_SLIDING_WINDOW = 10
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
        f"- You follow the KP Kids Studio prospect playbook.\n"
        f"- On FIRST message: warmly introduce the studio in ONE sentence, then ask ONLY the parent's name and how you can help. Nothing else.\n"
        f"- NEVER ask more than ONE question per message. Send one question, wait for answer, then ask the next.\n"
        f"- NEVER dump a price list immediately — ask discovery questions first.\n"
        f"- When client insists on price: use the Quick Reset script from the playbook.\n"
        f"- After all discovery questions answered: present EXACTLY 2 package options.\n"
        f"- Use client's name and child's name in every message after learning them.\n"
        f"- Short messages only — WhatsApp style, one idea per message.\n"
        f"- Match the language the client uses (EN / RW / FR mix).\n"
        f"- Guide client: discovery → 2 options → booking fee → form → prep → delivery → feedback.\n\n"
        f"ABSOLUTE RULES:\n"
        f"- Do not use one client data —name, age,...— in someone else's conversation"
        f"- Do not mix clients conversations"
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
        f"- NEVER use bullet points, dashes, or lists of any kind — not even with symbols like • or -.\n"
        f"- ONE question per message maximum — never combine multiple questions.\n"
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
