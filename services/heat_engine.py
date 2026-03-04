"""
Heat Score Engine
=================
Calculates and updates client engagement scores in real-time.

Heat score: 0 (cold) → 100 (hot)
Default: 50 (neutral)

Signals measured:
  - Reply speed (time since last outbound)
  - Message length (proxy for engagement depth)
  - Question count (specific interest)
  - Emotional language detection
  - Consistency of engagement

Every change is logged to HeatEvent for the learning feedback loop.
"""

import logging
import re
from datetime import timedelta


logger = logging.getLogger(__name__)

# Each signal contributes a delta. Sum of all deltas is clamped to [0, 100].

_REPLY_SPEED_DELTAS = {
    "immediate": +15,  # < 5 minutes
    "fast": +10,  # 5–30 minutes
    "same_day": +5,  # 30 min – 6 hours
    "slow": -5,  # 6–24 hours
    "very_slow": -10,  # > 24 hours
    "unknown": 0,
}

_LENGTH_DELTAS = {
    "detailed": +10,  # > 80 chars
    "moderate": +5,  # 30–80 chars
    "brief": 0,  # 10–30 chars
    "minimal": -5,  # < 10 chars
}

_QUESTION_DELTA = +8  # Per question detected (max applied once)
_EMOTIONAL_DELTA = +10  # Emotional / excited language detected
_COMMITMENT_DELTA = +20  # Explicit commitment signal ("I want to book", "let's do it")
_OBJECTION_DELTA = -10  # Price/timing objection signals cooling


_QUESTION_RE = re.compile(r"\?|how much|when|what|which|can you|do you|is it", re.I)
_EMOTIONAL_RE = re.compile(
    r"\b(love|excited|amazing|beautiful|perfect|wonderful|can\'t wait|so happy|great)\b",
    re.I,
)
_COMMITMENT_RE = re.compile(
    r"\b(book|reserve|confirm|let\'s do|i want to|i\'d like to|when can we|i\'m ready|ready to)\b",
    re.I,
)
_OBJECTION_RE = re.compile(
    r"\b(expensive|too much|budget|afford|maybe later|not sure|need to think|check with|ask my)\b",
    re.I,
)


def calculate_heat_delta(
    message_text: str,
    last_outbound_at=None,
    message_received_at=None,
) -> dict:
    """
    Calculate heat score delta from a single inbound message.

    Returns:
        {
          "total_delta": int,
          "signals": [list of signal names triggered],
          "breakdown": {signal: delta}
        }
    """
    signals = []
    breakdown = {}

    # 1. Reply speed 
    if last_outbound_at and message_received_at:
        elapsed = message_received_at - last_outbound_at
        speed_key = _classify_reply_speed(elapsed)
        delta = _REPLY_SPEED_DELTAS[speed_key]
        if delta != 0:
            signals.append(f"reply_speed_{speed_key}")
            breakdown["reply_speed"] = delta
    else:
        breakdown["reply_speed"] = 0

    # 2. Message length
    length_key = _classify_length(message_text)
    length_delta = _LENGTH_DELTAS[length_key]
    if length_delta != 0:
        signals.append(f"length_{length_key}")
    breakdown["message_length"] = length_delta

    # 3. Question depth 
    if _QUESTION_RE.search(message_text):
        signals.append("question_detected")
        breakdown["question_depth"] = _QUESTION_DELTA
    else:
        breakdown["question_depth"] = 0

    # 4. Emotional language 
    if _EMOTIONAL_RE.search(message_text):
        signals.append("emotional_language")
        breakdown["emotional_tone"] = _EMOTIONAL_DELTA
    else:
        breakdown["emotional_tone"] = 0

    # 5. Commitment signals 
    if _COMMITMENT_RE.search(message_text):
        signals.append("commitment_signal")
        breakdown["commitment"] = _COMMITMENT_DELTA
    else:
        breakdown["commitment"] = 0

    # 6. Objection signals 
    if _OBJECTION_RE.search(message_text):
        signals.append("objection_detected")
        breakdown["objection"] = _OBJECTION_DELTA
    else:
        breakdown["objection"] = 0

    total = sum(breakdown.values())

    return {
        "total_delta": total,
        "signals": signals,
        "breakdown": breakdown,
    }


def update_heat_score(
    journey_state, delta: int, signal_type: str, reason: str = ""
) -> int:
    """
    Apply delta to client's heat score. Clamp to [0, 100].
    Log to HeatEvent for audit trail.
    Returns new heat score.
    """
    from apps.conversations.models import HeatEvent

    score_before = journey_state.heat_score
    score_after = max(0, min(100, score_before + delta))

    if score_before == score_after:
        return score_after  # No change — skip DB write

    journey_state.heat_score = score_after
    journey_state.save(update_fields=["heat_score", "updated_at"])

    try:
        conversation = (
            journey_state.client.conversations.filter(window_status="open")
            .order_by("-started_at")
            .first()
        )
        if conversation:
            HeatEvent.objects.create(
                client=journey_state.client,
                conversation=conversation,
                signal_type=signal_type,
                delta=delta,
                score_before=score_before,
                score_after=score_after,
                reason=reason[:200] if reason else "",
            )
    except Exception as exc:
        logger.warning("Failed to log HeatEvent: %s", exc)

    logger.debug(
        "Heat updated | client=%s %s→%s (delta=%+d signal=%s)",
        journey_state.client.wa_number,
        score_before,
        score_after,
        delta,
        signal_type,
    )

    return score_after


def get_followup_timing(heat_label: str, followup_count: int) -> timedelta:
    """
    Return the timedelta to wait before next follow-up based on heat.

    HIGH:   3-6 hours first, 24h second (max 2 without reply)
    MEDIUM: 24h first, 72h second
    LOW:    48h minimum, single check only
    """
    timing_map = {
        "HIGH": [timedelta(hours=4), timedelta(hours=24)],
        "MEDIUM": [timedelta(hours=24), timedelta(hours=72)],
        "LOW": [timedelta(hours=48)],
    }
    schedule = timing_map.get(heat_label, timing_map["MEDIUM"])
    idx = min(followup_count, len(schedule) - 1)
    return schedule[idx]


def should_send_followup(heat_label: str, followup_count: int) -> bool:
    """
    CRITICAL RULE: Never send 2 follow-ups without reply unless HIGH heat.
    HIGH heat max: 2 follow-ups
    MEDIUM/LOW: max 1 follow-up
    """
    if heat_label == "HIGH":
        return followup_count < 2
    return followup_count < 1




def _classify_reply_speed(elapsed: timedelta) -> str:
    minutes = elapsed.total_seconds() / 60
    if minutes < 5:
        return "immediate"
    if minutes < 30:
        return "fast"
    if minutes < 360:
        return "same_day"
    if minutes < 1440:
        return "slow"
    return "very_slow"


def _classify_length(text: str) -> str:
    length = len(text.strip())
    if length > 80:
        return "detailed"
    if length > 30:
        return "moderate"
    if length > 10:
        return "brief"
    return "minimal"
