"""
Meta webhook signature verification.
Docs: https://developers.facebook.com/docs/messenger-platform/webhooks#security
"""

import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def verify_signature(request) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by Meta.
    Returns True if valid, False otherwise.
    """
    signature_header = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[7:]  # strip "sha256="
    app_secret = settings.WHATSAPP["APP_SECRET"].encode()
    body = request.body

    computed = hmac.new(app_secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_sig)
