"""
Token estimation utilities.
Used to enforce conversation budgets before calling Claude.
"""

import logging

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Fast token estimate without loading tiktoken (saves memory)."""
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens for a list of {role, content} messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        total += estimate_tokens(str(content)) + 4
    return total
