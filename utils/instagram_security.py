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
    # Use the underlying Django request if this is a DRF Request object
    # to ensure we get the original raw body before any parsing.
    raw_request = getattr(request, "_request", request)
    
    signature_256 = raw_request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
    signature_sha1 = raw_request.META.get("HTTP_X_HUB_SIGNATURE", "")
    
    if not signature_256 and not signature_sha1:
        logger.warning("No Instagram signature header found in request")
        return False

    # Get App Secret from settings. Strip whitespace to prevent common .env errors.
    # Fallback to WA_APP_SECRET if IG_APP_SECRET is not provided, 
    # as they often share the same Meta App.
    app_secret = (settings.INSTAGRAM.get("APP_SECRET") or settings.WHATSAPP.get("APP_SECRET", "")).strip()
    
    if not app_secret:
        logger.error("Instagram/WhatsApp App Secret not configured")
        return False
        
    app_secret_bytes = app_secret.encode("utf-8")
    body = raw_request.body

    # 1. Try SHA256 (Primary)
    if signature_256 and signature_256.startswith("sha256="):
        expected_sig = signature_256[7:].strip()
        computed = hmac.new(app_secret_bytes, body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed.lower(), expected_sig.lower()):
            return True
        logger.debug("Instagram SHA256 signature mismatch. Body length: %d", len(body))

    # 2. Try SHA1 (Fallback for older implementations)
    if signature_sha1 and signature_sha1.startswith("sha1="):
        expected_sig = signature_sha1[5:].strip()
        computed = hmac.new(app_secret_bytes, body, hashlib.sha1).hexdigest()
        if hmac.compare_digest(computed.lower(), expected_sig.lower()):
            return True
        logger.debug("Instagram SHA1 signature mismatch. Body length: %d", len(body))

    logger.warning("Instagram signature verification failed (all attempts). Check IG_APP_SECRET.")
    return False
