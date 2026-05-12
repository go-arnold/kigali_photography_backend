import hashlib
import hmac
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def verify_instagram_signature(request) -> bool:
    """
    Verify the signature header sent by Meta for Instagram.
    Supports X-Hub-Signature-256 (preferred) and X-Hub-Signature (fallback).
    """
    signature_256 = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
    signature_sha1 = request.META.get("HTTP_X_HUB_SIGNATURE", "")
    
    if not signature_256 and not signature_sha1:
        logger.warning("No Instagram signature header found")
        return False

    # Try to get IG_APP_SECRET, fallback to WA_APP_SECRET if same app is used
    app_secret = settings.INSTAGRAM.get("APP_SECRET") or settings.WHATSAPP.get("APP_SECRET")
    
    if not app_secret:
        logger.error("Instagram/WhatsApp App Secret not configured")
        return False
        
    app_secret_bytes = app_secret.encode()
    body = request.body

    # 1. Try SHA256
    if signature_256 and signature_256.startswith("sha256="):
        expected_sig = signature_256[7:]
        computed = hmac.new(app_secret_bytes, body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed, expected_sig):
            return True
        logger.debug("Instagram SHA256 signature mismatch")

    # 2. Try SHA1 fallback
    if signature_sha1 and signature_sha1.startswith("sha1="):
        expected_sig = signature_sha1[5:]
        computed = hmac.new(app_secret_bytes, body, hashlib.sha1).hexdigest()
        if hmac.compare_digest(computed, expected_sig):
            return True
        logger.debug("Instagram SHA1 signature mismatch")

    logger.warning("Instagram signature verification failed (all attempts)")
    return False
