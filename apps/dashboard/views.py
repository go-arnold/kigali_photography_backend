"""
Dashboard Views
===============
Human oversight and control interface for studio staff.

Endpoints:
  GET  /dashboard/stats/                     → token spend, queue size, takeovers
  GET  /dashboard/approvals/                 → pending approval queue
  POST /dashboard/approvals/{id}/approve/    → approve + send AI suggestion
  POST /dashboard/approvals/{id}/reject/     → reject AI suggestion
  GET  /dashboard/clients/                   → client list with journey context
  GET  /dashboard/clients/{id}/              → full client detail + conversation
  POST /dashboard/clients/{id}/message/      → send manual message to client
  POST /dashboard/clients/{id}/journey/      → override journey state
  POST /dashboard/clients/{id}/takeover/     → toggle human takeover on/off
  GET  /dashboard/scheduled/                 → upcoming scheduled messages
  DEL  /dashboard/scheduled/{id}/cancel/     → cancel a pending scheduled message

Design: thin views, logic in services. Every action logged.
"""
import logging

from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .mixins import ApprovalObjectMixin, ClientLookupMixin
from .permissions import IsStudioStaff
from .serializers import (
    ApprovalActionSerializer, ApprovalQueueSerializer,
    DashboardClientSerializer, JourneyOverrideSerializer,
    ManualMessageSerializer, ScheduledMessageSerializer,
    TokenStatsSerializer,
)

logger = logging.getLogger(__name__)


# Stats 

class DashboardStatsView(APIView):
    """
    High-level KPIs for the dashboard home screen.
    Token spend, queue depth, active takeovers.
    """
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.conversations.models import Conversation, ApprovalQueue, ApprovalStatus
        from apps.clients.models import JourneyState

        # Token stats
        token_agg = Conversation.objects.aggregate(total=Sum("tokens_used"))
        total_tokens = token_agg["total"] or 0

        # Cost estimate: Haiku = $0.80/M input + $4/M output
        # Conservative: assume 60% input, 40% output
        estimated_cost = (
            (total_tokens * 0.6 / 1_000_000) * 0.80 +
            (total_tokens * 0.4 / 1_000_000) * 4.00
        )

        stats = {
            "total_conversations": Conversation.objects.count(),
            "total_tokens_used": total_tokens,
            "estimated_cost_usd": round(estimated_cost, 4),
            "conversations_over_budget": Conversation.objects.filter(
                tokens_used__gte=models_F("token_budget")
            ).count(),
            "pending_approvals": ApprovalQueue.objects.filter(
                status=ApprovalStatus.PENDING
            ).count(),
            "active_human_takeovers": JourneyState.objects.filter(
                human_takeover=True
            ).count(),
        }
        serializer = TokenStatsSerializer(stats)
        return Response(serializer.data)


# Approval Queue 

class ApprovalQueueListView(APIView):
    """List pending approval items, newest first."""
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.conversations.models import ApprovalQueue, ApprovalStatus

        status_filter = request.query_params.get("status", ApprovalStatus.PENDING)
        qs = (
            ApprovalQueue.objects
            .filter(status=status_filter)
            .select_related("client", "conversation", "reviewed_by")
            .order_by("-created_at")
        )
        serializer = ApprovalQueueSerializer(qs, many=True)
        return Response(serializer.data)


class ApprovalApproveView(ApprovalObjectMixin, APIView):
    """
    Approve an AI suggestion and optionally send it immediately.
    POST /dashboard/approvals/{id}/approve/
    Body: {"notes": "Looks good", "send_immediately": true}
    """
    permission_classes = [IsStudioStaff]

    def post(self, request, pk):
        approval = self.get_approval(pk)
        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval.approve(request.user, notes=serializer.validated_data["notes"])

        # Send the message if requested
        if serializer.validated_data["send_immediately"]:
            try:
                from services.whatsapp import send_text
                send_text(
                    to=approval.client.wa_number,
                    message=approval.ai_suggestion,
                )
                # Record the outbound message
                _record_approved_outbound(approval, request.user)
                logger.info(
                    "Approved + sent | approval=%s client=%s by=%s",
                    pk, approval.client.wa_number, request.user.username,
                )
            except Exception as exc:
                logger.error("Failed to send approved message: %s", exc)
                return Response(
                    {"error": f"Approved but send failed: {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        return Response(
            ApprovalQueueSerializer(approval).data,
            status=status.HTTP_200_OK,
        )


class ApprovalRejectView(ApprovalObjectMixin, APIView):
    """
    Reject an AI suggestion.
    POST /dashboard/approvals/{id}/reject/
    Body: {"notes": "Not appropriate — client needs different approach"}
    """
    permission_classes = [IsStudioStaff]

    def post(self, request, pk):
        approval = self.get_approval(pk)
        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval.reject(request.user, notes=serializer.validated_data["notes"])
        logger.info(
            "Rejected | approval=%s client=%s by=%s",
            pk, approval.client.wa_number, request.user.username,
        )
        return Response(ApprovalQueueSerializer(approval).data)


# Client Management 

class ClientListView(APIView):
    """
    All clients with heat + journey context.
    Supports filtering by status and heat label.
    """
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.clients.models import Client

        qs = (
            Client.objects
            .select_related("journey_state")
            .prefetch_related("children", "approval_items", "conversations")
            .order_by("-last_contact")
        )

        # Filters
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        takeover_only = request.query_params.get("takeover_only", "").lower() == "true"
        if takeover_only:
            qs = qs.filter(journey_state__human_takeover=True)

        pending_approval = request.query_params.get("pending_approval", "").lower() == "true"
        if pending_approval:
            qs = qs.filter(approval_items__status="pending").distinct()

        serializer = DashboardClientSerializer(qs, many=True)
        return Response(serializer.data)


class ClientDetailView(ClientLookupMixin, APIView):
    """Full client detail including last 20 messages."""
    permission_classes = [IsStudioStaff]

    def get(self, request, pk):
        client = self.get_client(pk)
        data = DashboardClientSerializer(client).data

        # Add last 20 messages across all conversations
        from apps.conversations.models import Message
        messages = (
            Message.objects
            .filter(client=client)
            .order_by("-timestamp")[:20]
        )
        data["recent_messages"] = [
            {
                "direction": m.direction,
                "content": m.content,
                "timestamp": m.timestamp,
                "generated_by_ai": m.generated_by_ai,
                "tokens": m.total_tokens,
                "model": m.model_used,
            }
            for m in reversed(messages)
        ]

        # Pending approvals for this client
        from apps.conversations.models import ApprovalQueue, ApprovalStatus
        pending = ApprovalQueue.objects.filter(
            client=client, status=ApprovalStatus.PENDING
        ).order_by("-created_at")
        data["pending_approvals_detail"] = ApprovalQueueSerializer(pending, many=True).data

        return Response(data)


class ManualMessageView(ClientLookupMixin, APIView):
    """
    Send a manual message from studio staff to a client.
    POST /dashboard/clients/{id}/message/
    Bypasses AI entirely — direct send.
    """
    permission_classes = [IsStudioStaff]

    def post(self, request, pk):
        client = self.get_client(pk)
        serializer = ManualMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Override `to` with client's actual number (ignore body `to` for safety)
        message = serializer.validated_data["message"]

        try:
            from services.whatsapp import send_text
            send_text(to=client.wa_number, message=message)

            # Record in DB
            import uuid
            from apps.conversations.models import Message, MessageDirection, MessageStatus
            from services.client_service import get_or_create_conversation
            _, conversation = get_or_create_conversation(client), None
            conv = client.conversations.filter(window_status="open").first()
            if conv:
                Message.objects.create(
                    wa_message_id=f"manual_{uuid.uuid4().hex[:12]}",
                    conversation=conv,
                    client=client,
                    direction=MessageDirection.OUTBOUND,
                    status=MessageStatus.SENT,
                    content=message,
                    msg_type="text",
                    generated_by_ai=False,
                    approved_by_human=True,
                    timestamp=timezone.now(),
                )

            logger.info(
                "Manual message sent | client=%s by=%s len=%s",
                client.wa_number, request.user.username, len(message),
            )
            return Response({"status": "sent", "to": client.wa_number})

        except Exception as exc:
            logger.error("Manual send failed for %s: %s", client.wa_number, exc)
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class JourneyOverrideView(ClientLookupMixin, APIView):
    """
    Override client journey state — phase, step, heat score.
    POST /dashboard/clients/{id}/journey/
    """
    permission_classes = [IsStudioStaff]

    def post(self, request, pk):
        client = self.get_client(pk)
        serializer = JourneyOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            journey = client.journey_state
        except Exception:
            from apps.clients.models import JourneyState
            journey, _ = JourneyState.objects.get_or_create(client=client)

        update_fields = ["updated_at"]

        if data.get("phase"):
            journey.phase = data["phase"]
            update_fields.append("phase")
        if data.get("step"):
            journey.step = data["step"]
            update_fields.append("step")
        if "heat_score" in data:
            journey.heat_score = data["heat_score"]
            update_fields.append("heat_score")

        journey.save(update_fields=update_fields)

        logger.info(
            "Journey override | client=%s phase=%s step=%s heat=%s by=%s",
            client.wa_number, journey.phase, journey.step,
            journey.heat_score, request.user.username,
        )
        return Response({
            "phase": journey.phase,
            "step": journey.step,
            "heat_score": journey.heat_score,
            "heat_label": journey.heat_label,
        })


class HumanTakeoverView(ClientLookupMixin, APIView):
    """
    Toggle human takeover on/off for a client.
    POST /dashboard/clients/{id}/takeover/
    Body: {"enable": true, "reason": "Complex objection handling"}
          {"enable": false}  → releases AI
    """
    permission_classes = [IsStudioStaff]

    def post(self, request, pk):
        client = self.get_client(pk)
        enable = request.data.get("enable", True)
        reason = request.data.get("reason", "Manual override by staff")

        try:
            journey = client.journey_state
        except Exception:
            from apps.clients.models import JourneyState
            journey, _ = JourneyState.objects.get_or_create(client=client)

        if enable:
            journey.flag_human_takeover(reason)
            action = "takeover_enabled"
        else:
            journey.human_takeover = False
            journey.takeover_reason = ""
            journey.save(update_fields=["human_takeover", "takeover_reason", "updated_at"])
            action = "takeover_released"

        logger.info(
            "Takeover %s | client=%s reason='%s' by=%s",
            action, client.wa_number, reason, request.user.username,
        )
        return Response({
            "action": action,
            "human_takeover": journey.human_takeover,
            "reason": journey.takeover_reason,
        })


#  Scheduled Messages 

class ScheduledMessageListView(APIView):
    """List upcoming scheduled messages."""
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.conversations.models import ScheduledMessage

        qs = (
            ScheduledMessage.objects
            .filter(status=ScheduledMessage.SendStatus.PENDING)
            .select_related("client")
            .order_by("send_at")
        )
        serializer = ScheduledMessageSerializer(qs, many=True)
        return Response(serializer.data)


class ScheduledMessageCancelView(APIView):
    """Cancel a pending scheduled message."""
    permission_classes = [IsStudioStaff]

    def delete(self, request, pk):
        from apps.conversations.models import ScheduledMessage

        try:
            msg = ScheduledMessage.objects.get(
                pk=pk, status=ScheduledMessage.SendStatus.PENDING
            )
        except ScheduledMessage.DoesNotExist:
            return Response(
                {"error": "Not found or already sent/cancelled."},
                status=status.HTTP_404_NOT_FOUND,
            )

        msg.status = ScheduledMessage.SendStatus.CANCELLED
        msg.save(update_fields=["status"])
        logger.info("Scheduled message #%s cancelled by %s", pk, request.user.username)
        return Response({"status": "cancelled"})


#  Helpers 

def _record_approved_outbound(approval, user):
    """Record a human-approved message send in the conversation."""
    import uuid
    from apps.conversations.models import Message, MessageDirection, MessageStatus

    conv = approval.conversation
    Message.objects.create(
        wa_message_id=f"approved_{uuid.uuid4().hex[:12]}",
        conversation=conv,
        client=approval.client,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        content=approval.ai_suggestion,
        msg_type="text",
        generated_by_ai=True,
        approved_by_human=True,
        timestamp=timezone.now(),
    )


def models_F(field):
    """Lazy import of F() to avoid circular imports at module load."""
    from django.db.models import F
    return F(field)