"""
Reusable decorators for the webhook and task layer.
"""

import logging
from functools import wraps

from django.core.cache import cache
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def idempotent_webhook(key_func, ttl: int = 300):
    """
    Reject duplicate webhook deliveries within `ttl` seconds.
    `key_func(request)` must return a unique string (e.g. WhatsApp message_id).
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(self, request, *args, **kwargs):
            key = f"idempotency:{key_func(request)}"
            if cache.get(key):
                logger.debug("Duplicate webhook ignored: %s", key)
                return Response({"status": "duplicate"}, status=200)
            cache.set(key, 1, ttl)
            return view_func(self, request, *args, **kwargs)

        return wrapped

    return decorator


def signature_required(view_func):
    """
    Validate X-Hub-Signature-256 from Meta before processing.
    Applied on the WhatsApp webhook POST endpoint.
    """

    @wraps(view_func)
    def wrapped(self, request, *args, **kwargs):
        from utils.whatsapp_security import verify_signature

        if not verify_signature(request):
            logger.warning(
                "Invalid webhook signature from %s", request.META.get("REMOTE_ADDR")
            )
            return Response({"error": "Invalid signature"}, status=403)
        return view_func(self, request, *args, **kwargs)

    return wrapped
