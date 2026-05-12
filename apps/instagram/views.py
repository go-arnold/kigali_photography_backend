import logging
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from utils.instagram_security import verify_instagram_signature
from apps.automation.tasks import process_instagram_message

logger = logging.getLogger(__name__)

class InstagramWebhookView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        if mode == "subscribe" and token == settings.INSTAGRAM["WEBHOOK_VERIFY_TOKEN"]:
            logger.info("Instagram webhook verified successfully")
            return Response(int(challenge), status=200)

        logger.warning("Instagram webhook verification failed")
        return Response({"error": "Verification failed"}, status=403)

    def post(self, request):
        if not verify_instagram_signature(request):
            logger.warning("Invalid Instagram signature")
            return Response({"error": "Invalid signature"}, status=403)

        body = request.data
        if body.get("object") not in ["instagram", "page"]:
            return Response({"status": "ignored"}, status=200)

        entries = body.get("entry", [])
        for entry in entries:
            messaging = entry.get("messaging", [])
            for message_event in messaging:
                if "message" in message_event:
                    self._handle_message(message_event)
        
        return Response({"status": "ok"}, status=200)

    def _handle_message(self, event):
        sender_id = event["sender"]["id"]
        recipient_id = event["recipient"]["id"]
        message = event["message"]
        
        # Avoid processing our own messages (though normally Meta doesn't send them back in 'messaging')
        if "is_echo" in message:
            return

        mid = message.get("mid")
        text = message.get("text", "")
        timestamp = event.get("timestamp")

        # Dispatch to Celery task
        process_instagram_message.delay(
            sender_id=sender_id,
            message_text=text,
            message_id=mid,
            timestamp=timestamp
        )
        logger.debug("Dispatched Instagram message %s from %s", mid, sender_id)

class InstagramSendView(APIView):
    """
    Manual send via API (optional, but good for testing/dashboard)
    """
    def post(self, request):
        ig_user_id = request.data.get("ig_user_id")
        text = request.data.get("text")
        
        if not ig_user_id or not text:
            return Response({"error": "Missing ig_user_id or text"}, status=400)
            
        from services.instagram_service import send_text
        try:
            result = send_text(ig_user_id, text)
            return Response(result, status=200)
        except Exception as e:
            logger.error("Failed to send manual IG message: %s", e)
            return Response({"error": str(e)}, status=500)
