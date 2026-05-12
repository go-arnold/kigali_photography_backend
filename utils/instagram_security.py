import hashlib
import hmac
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def verify_instagram_signature(request) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by Meta for Instagram.
    """
    signature_header = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[7:]  # strip "sha256="
    # Instagram uses IG_APP_SECRET
    app_secret = settings.INSTAGRAM.get("APP_SECRET", "").encode()
    if not app_secret:
        logger.error("IG_APP_SECRET not configured")
        return False
        
    body = request.body
    computed = hmac.new(app_secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_sig)
