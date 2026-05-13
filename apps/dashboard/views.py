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
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser


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

        if serializer.validated_data["send_immediately"]:
            try:
                from services.whatsapp import send_text, send_buttons

                client = approval.client
                lang = getattr(client, "language", "en") or "en"

                # ── Détecter si c'est un booking message (contient MTN MoMo) ──
                is_booking_message = "798741" in (approval.ai_suggestion or "")

                # ── Détecter si c'est la suggestion de disponibilité (contient le séparateur) ──
                #is_availability_suggestion = "CHECK BOOKING TABLE" in (approval.ai_suggestion or "")

                if is_booking_message:
                    # Extraire uniquement le message client (après "MESSAGE TO SEND IF AVAILABLE:")
                    raw = approval.ai_suggestion
                    marker = "MESSAGE TO SEND IF AVAILABLE:\n\n"
                    if marker in raw:
                        client_message = raw.split(marker, 1)[1].strip()
                    else:
                        client_message = raw

                    # Envoyer le booking message au client
                    send_text(to=client.wa_number, message=client_message)

                    try:
                        from services.journey_orchestrator import advance_journey
                        advance_journey(client.journey_state, "booking", "finalizing")
                        # Mettre à jour le statut client
                        client.status = "booked"
                        client.save(update_fields=["status", "updated_at"])
                    except Exception:
                        pass

                    # Envoyer les boutons de paiement
                    paid_titles  = {"en": "✅ I've Sent Payment", "rw": "✅ Nishyuye", "fr": "✅ J'ai Envoyé"}
                    agent_titles = {"en": "🧑 Talk to Agent", "rw": "🧑 Vugana n'Umukozi", "fr": "🧑 Parler à un Agent"}
                    bodies       = {"en": "What would you like to do next?", "rw": "Ni iki mushaka gukora?", "fr": "Que souhaitez-vous faire ensuite?"}

                    send_buttons(
                        to=client.wa_number,
                        body=bodies.get(lang, bodies["en"]),
                        buttons=[
                            {"id": "btn_paid",  "title": paid_titles.get(lang,  paid_titles["en"])},
                            {"id": "btn_agent", "title": agent_titles.get(lang, agent_titles["en"])},
                        ],
                    )
                    try:
                        from services.journey_orchestrator import advance_journey
                        advance_journey(client.journey_state, "booking", "awaiting_payment")
                    except Exception:
                        pass

                    # ── Désactiver le human takeover → l'IA reprend si besoin ──
                    # Mais on met flow_mode = "awaiting_payment" pour que
                    # les boutons btn_paid/btn_agent fonctionnent normalement
                    try:
                        journey = client.journey_state
                        journey.human_takeover = False
                        journey.takeover_reason = ""
                        journey.flow_mode = "awaiting_payment"
                        journey.save(update_fields=[
                            "human_takeover", "takeover_reason",
                            "flow_mode", "updated_at"
                        ])
                        logger.info(
                            "Human takeover released after availability confirmed | client=%s",
                            client.wa_number,
                        )
                    except Exception as exc:
                        logger.warning("Could not release human takeover: %s", exc)

                    _record_approved_outbound(approval, request.user)

                else:
                    # Message normal (pas un booking avec disponibilité)
                    send_text(to=client.wa_number, message=approval.ai_suggestion)
                    _record_approved_outbound(approval, request.user)

                logger.info(
                    "Approved + sent | approval=%s client=%s by=%s",
                    pk, client.wa_number, request.user.username,
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
                "msg_type": m.msg_type, 
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
            # Notifications added
            send_push_notification(
                title=f"👤 Client needs help — {client.name or client.wa_number}",
                body=reason[:100],
                url=f"/?client={client.pk}",
            )

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


class BookingListCreateView(APIView):
    """
    GET  /dashboard/bookings/   → list all bookings
    POST /dashboard/bookings/   → create new booking
    """
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.conversations.models import Booking
        qs = Booking.objects.select_related("client", "created_by").order_by("booking_day", "booking_time")
        
        # Filter by upcoming/past
        filter_type = request.query_params.get("filter", "upcoming")
        today = timezone.now().date()
        if filter_type == "upcoming":
            qs = qs.filter(booking_day__gte=today)
        elif filter_type == "past":
            qs = qs.filter(booking_day__lt=today)

        data = [_serialize_booking(b) for b in qs]
        return Response(data)

    def post(self, request):
        from apps.conversations.models import Booking
        d = request.data
        
        try:
            booking = Booking.objects.create(
            parent_name      = d.get("parent_name", ""),
            phone            = d.get("phone", ""),
            booking_day      = _parse_date(d["booking_day"]),
            booking_time     = _parse_time(d["booking_time"]),
            package          = d.get("package", "starter"),
            extras           = d.get("extras", ""),
            occasion         = d.get("occasion", "child_celebration"),
            photo_type       = d.get("photo_type", "child"),   # ← NEW
            child_name       = d.get("child_name", ""),
            child_birthday   = _parse_date(d.get("child_birthday")),
            child_gender     = d.get("child_gender", ""),
            preferred_outfit = d.get("preferred_outfit", ""),
            notes            = d.get("notes", ""),
            created_by       = request.user,
        )
            # Auto-schedule birthday messages if birthday provided
            if booking.child_birthday:
                _schedule_birthday_messages(booking)
            
            logger.info("Booking created | id=%s child=%s by=%s", booking.pk, booking.child_name, request.user.username)
            return Response(_serialize_booking(booking), status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.error("Booking create failed: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class BookingDetailView(APIView):
    """
    GET    /dashboard/bookings/{id}/  → get booking
    PATCH  /dashboard/bookings/{id}/  → update booking
    DELETE /dashboard/bookings/{id}/  → delete booking
    """
    permission_classes = [IsStudioStaff]

    def get(self, request, pk):
        from apps.conversations.models import Booking
        try:
            booking = Booking.objects.get(pk=pk)
            return Response(_serialize_booking(booking))
        except Booking.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        from apps.conversations.models import Booking
        try:
            booking = Booking.objects.get(pk=pk)
            d = request.data
            had_birthday = bool(booking.child_birthday)
            
            field_parsers = {
                "booking_day": _parse_date,
                "booking_time": _parse_time,
                "child_birthday": _parse_date,
            }

            for field in ["parent_name", "phone", "child_name", "child_gender",
                        "child_age", "child_birthday", "occasion", "package",
                        "extras", "preferred_outfit", "notes", "booking_day", "booking_time"]:
                if field in d:
                    val = d[field]
                    if field in field_parsers:
                        val = field_parsers[field](val) if val else None
                    setattr(booking, field, val)
            
            booking.save()
            
            # Re-schedule birthday messages if birthday was added/changed
            if booking.child_birthday and not had_birthday:
                _schedule_birthday_messages(booking)
            
            logger.info("Booking updated | id=%s by=%s", pk, request.user.username)
            return Response(_serialize_booking(booking))
        except Booking.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        from apps.conversations.models import Booking
        try:
            booking = Booking.objects.get(pk=pk)
            name = booking.child_name
            booking.delete()
            logger.info("Booking deleted | id=%s child=%s by=%s", pk, name, request.user.username)
            return Response({"status": "deleted"})
        except Booking.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_booking(b):
    return {
        "id":              b.pk,
        "parent_name":     b.parent_name,
        "phone":           b.phone,
        "booking_day":     b.booking_day.isoformat(),
        "booking_time":    b.booking_time.strftime("%H:%M"),
        "package":         b.package,
        "extras":          b.extras,
        "occasion":        b.occasion,
        "photo_type":      b.photo_type,       # ← NOUVEAU
        "child_name":      b.child_name,
        "child_birthday":  b.child_birthday.isoformat() if b.child_birthday else None,
        "child_gender":    b.child_gender,
        "preferred_outfit": b.preferred_outfit,
        "notes":           b.notes,
        "created_at":      b.created_at.isoformat(),
        "created_by":      b.created_by.username if b.created_by else "—",
    }


def _schedule_birthday_messages(booking):
    from apps.conversations.models import ScheduledMessage, ScheduledMessageType
    from apps.clients.models import Client
    import datetime

    birthday = booking.child_birthday
    today = timezone.now().date()

    this_year_bday = birthday.replace(year=today.year)
    if this_year_bday < today:
        next_bday = birthday.replace(year=today.year + 1)
    else:
        next_bday = this_year_bday

    client = booking.client
    if not client:
        try:
            client = Client.objects.get(wa_number=booking.phone)
        except Client.DoesNotExist:
            client = None

    if not client:
        logger.warning("Cannot schedule birthday messages — no client linked for booking %s", booking.pk)
        return

    nine_am = datetime.time(9, 0, 0)  # ← Fix: datetime.time() direct, pas de .replace()

    # Juste avant la définition de schedules
    pronoun = {"boy": "him", "girl": "her"}.get(booking.child_gender or "", "them")
    parent_name = booking.parent_name or "there"

    schedules = [
        (next_bday - datetime.timedelta(days=7), ScheduledMessageType.BIRTHDAY_REMINDER,
        f"Hey {parent_name}! It’s Julie from Kp kids studio 😊. I noticed that {booking.child_name} has birthday coming up next week, just wanted to wish {pronoun}, A happy birthday in advance and hope it’s a special one for your family. It’s been some time since we last worked together, and I just wanted to reconnect and say hello."),
        (next_bday - datetime.timedelta(days=1), ScheduledMessageType.BIRTHDAY_REMINDER,
        f"Hey {parent_name}! Tomorrow is {booking.child_name}'s big day! 🎉 Wishing you a wonderful celebration!"),
        (next_bday, ScheduledMessageType.BIRTHDAY_WISH,
        f"parent:{parent_name}|child:{booking.child_name}|pronoun:{pronoun}"),
        #Hey Judith! 😊  
        # It’s Elyse from Kp kids studio.

        # I noticed that today is Elga's birthday 🎉  
        # Just wanted to wish her a happy birthday and hope you have a beautiful celebration planned.

        # Sending you and your family good vibes and hopefully we’ll get to create more memories together again sometime.
        (next_bday.replace(year=next_bday.year + 1) - datetime.timedelta(days=7), ScheduledMessageType.BIRTHDAY_REMINDER,
        f"Hey! {booking.child_name}'s birthday is coming up again 🎂 Time flies! Would you like to book a session to capture this year's milestone?"),
    ]

    created = 0
    for send_date, msg_type, content in schedules:
        dedup_key = f"{msg_type}:{client.pk}:{send_date.year}:{send_date.month}"
        send_at = timezone.make_aware(
            datetime.datetime.combine(send_date, nine_am)  # ← Fix: datetime.datetime, pas timezone.datetime
        )
        try:
            ScheduledMessage.objects.get_or_create(
                dedup_key=dedup_key,
                defaults={
                    "client": client,
                    "message_type": msg_type,
                    "content": content,
                    "language": "en",
                    "send_at": send_at,
                    "status": ScheduledMessage.SendStatus.PENDING,
                }
            )
            created += 1
        except Exception as exc:
            logger.warning("Could not schedule birthday message: %s", exc)

    logger.info("Scheduled %s birthday messages for %s (booking %s)", created, booking.child_name, booking.pk)

def _parse_date(val):
    from datetime import date
    if not val:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))

def _parse_time(val):
    from datetime import time
    if not val:
        return None
    if isinstance(val, time):
        return val
    return time.fromisoformat(str(val)[:5])

#STATS

class AnalyticsView(APIView):
    """
    GET /dashboard/analytics/?period=7d
    GET /dashboard/analytics/?period=30d  
    GET /dashboard/analytics/?from=2026-01-01&to=2026-03-31
    """
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.clients.models import Client, JourneyState
        from apps.conversations.models import Conversation, Message, ApprovalQueue
        from django.db.models import Count, Avg, Q
        import json

        # ── Période ──────────────────────────────────────────────────────────
        period = request.query_params.get("period", "30d")
        date_from_str = request.query_params.get("from")
        date_to_str   = request.query_params.get("to")

        now = timezone.now()
        if date_from_str and date_to_str:
            try:
                from datetime import datetime
                date_from = timezone.make_aware(datetime.strptime(date_from_str, "%Y-%m-%d"))
                date_to   = timezone.make_aware(datetime.strptime(date_to_str,   "%Y-%m-%d").replace(hour=23, minute=59))
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)
        elif period == "7d":
            date_from = now - timezone.timedelta(days=7)
            date_to   = now
        elif period == "90d":
            date_from = now - timezone.timedelta(days=90)
            date_to   = now
        else:  # 30d default
            date_from = now - timezone.timedelta(days=30)
            date_to   = now

        # ── Clients dans la période ──────────────────────────────────────────
        clients_qs = Client.objects.filter(created_at__gte=date_from, created_at__lte=date_to)
        total_clients = clients_qs.count()

        # ── Funnel ───────────────────────────────────────────────────────────
        # Clients avec au moins un message inbound
        started = clients_qs.filter(messages__direction="inbound").distinct().count()

        # Clients qui ont complété discovery (discovery_state a les 4 champs non-null)
        journeys_in_period = JourneyState.objects.filter(
            client__created_at__gte=date_from,
            client__created_at__lte=date_to,
        )

        completed_discovery = 0
        saw_packages = 0
        chose_package = 0
        confirmed_payment = 0

        discovery_studio = 0
        discovery_home   = 0
        discovery_frames_yes = 0
        discovery_frames_no  = 0
        discovery_cake_yes   = 0
        discovery_cake_no    = 0
        discovery_video_yes  = 0
        discovery_video_no   = 0

        # Combos populaires
        combo_counts = {}

        for j in journeys_in_period:
            state = j.discovery_state or {}
            fm = j.flow_mode or ""
 
            # Discovery complète si session_type est défini
            if state.get("session_type"):
                completed_discovery += 1
                if state.get("session_type") == "home":
                    discovery_home += 1
                else:
                    discovery_studio += 1
 
                f = state.get("frames", False)
                c = state.get("cake",   False)
                v = state.get("video",  False)
 
                if f:  discovery_frames_yes += 1
                else:  discovery_frames_no  += 1
                if c:  discovery_cake_yes   += 1
                else:  discovery_cake_no    += 1
                if v:  discovery_video_yes  += 1
                else:  discovery_video_no   += 1
 
                combo = (
                    ("Frames " if f else "") +
                    ("Cake "   if c else "") +
                    ("Video"   if v else "")
                ).strip() or "No extras"
                combo_counts[combo] = combo_counts.get(combo, 0) + 1
 
            # ── saw_packages : client a VU les packages ────────────────────────
            # ← CORRECTION : accolades {} pas parenthèses () — c'est un SET
            SAW_PACKAGE_MODES = {
                 "packages_presented","awaiting_datetime", "await_confirm",
                "awaiting_payment", "payment_confirmed",
            }
            if fm in SAW_PACKAGE_MODES or j.selected_package:
                saw_packages += 1
 
            # ── chose_package : client a CHOISI un package ────────────────────
            if j.selected_package:
                chose_package += 1
 
            # ── confirmed_payment : client a PAYÉ ─────────────────────────────
            # flow_mode = "payment_confirmed" (bouton btn_paid)
            # OU step = "payment_confirmation" / "finalizing" (pipeline IA)
            PAYMENT_CONFIRMED_MODES = {"payment_confirmed", "finalizing"}
            PAYMENT_CONFIRMED_STEPS = {"payment_confirmation", "finalizing"}
            if fm in PAYMENT_CONFIRMED_MODES or j.step in PAYMENT_CONFIRMED_STEPS:
                confirmed_payment += 1

        # ── Talk to Agent ────────────────────────────────────────────────────
        talk_to_agent_count = ApprovalQueue.objects.filter(
            created_at__gte=date_from,
            created_at__lte=date_to,
            ai_reasoning__icontains="requested human agent",
        ).count()

        # ── Abandons par phase ───────────────────────────────────────────────
        phase_counts = {}
        for j in journeys_in_period:
            phase = j.phase or "entry"
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        # ── Langues ──────────────────────────────────────────────────────────
        lang_counts = dict(
            clients_qs.values("language")
            .annotate(count=Count("id"))
            .values_list("language", "count")
        )

        # ── Tokens & coût ────────────────────────────────────────────────────
        convs_in_period = Conversation.objects.filter(
            started_at__gte=date_from, started_at__lte=date_to
        )
        token_agg = convs_in_period.aggregate(
            total=models_F_sum("tokens_used"),
            avg=models_F_avg("tokens_used"),
        )
        total_tokens = token_agg["total"] or 0
        avg_tokens   = round(token_agg["avg"] or 0)
        estimated_cost = round(
            (total_tokens * 0.6 / 1_000_000) * 0.80 +
            (total_tokens * 0.4 / 1_000_000) * 4.00, 4
        )

        # ── Human takeover ───────────────────────────────────────────────────
        takeover_count = journeys_in_period.filter(human_takeover=True).count()

        # ── Top combos (sorted) ──────────────────────────────────────────────
        top_combos = sorted(combo_counts.items(), key=lambda x: x[1], reverse=True)[:6]

        return Response({
            "period": {
                "from": date_from.strftime("%Y-%m-%d"),
                "to":   date_to.strftime("%Y-%m-%d"),
            },
            "funnel": {
                "total_clients":        total_clients,
                "started_conversation": started,
                "completed_discovery":  completed_discovery,
                "saw_packages":         saw_packages,
                "chose_package":        chose_package,
                "confirmed_payment":    confirmed_payment,
            },
            "discovery": {
                "session": {
                    "studio": discovery_studio,
                    "home":   discovery_home,
                },
                "frames": {"yes": discovery_frames_yes, "no": discovery_frames_no},
                "cake":   {"yes": discovery_cake_yes,   "no": discovery_cake_no},
                "video":  {"yes": discovery_video_yes,  "no": discovery_video_no},
                "top_combos": [{"combo": k, "count": v} for k, v in top_combos],
            },
            "behavior": {
                "talk_to_agent":    talk_to_agent_count,
                "human_takeovers":  takeover_count,
                "languages":        lang_counts,
                "phase_distribution": phase_counts,
            },
            "ai_performance": {
                "total_tokens":    total_tokens,
                "avg_tokens_per_conv": avg_tokens,
                "estimated_cost_usd":  estimated_cost,
                "total_conversations": convs_in_period.count(),
            },
        })


def models_F_sum(field):
    from django.db.models import Sum
    return Sum(field)

def models_F_avg(field):
    from django.db.models import Avg
    return Avg(field)


## Modification Messages View chew le dashboard:

class ClientMessagesView(ClientLookupMixin, APIView):
    """
    GET /dashboard/clients/{id}/messages/?since=<timestamp>
    Retourne les messages depuis un timestamp donné.
    Utilisé par le chat en temps réel (polling toutes les 10s).
    """
    permission_classes = [IsStudioStaff]

    def get(self, request, pk):
        client = self.get_client(pk)
        from apps.conversations.models import Message

        since = request.query_params.get("since")
        qs = Message.objects.filter(client=client).order_by("timestamp")

        if since:
            try:
                from datetime import datetime
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                qs = qs.filter(timestamp__gt=since_dt)
            except Exception:
                pass

        qs = qs[:100]

        messages = [
            {
                "id": m.pk,
                "direction": m.direction,
                "content": m.content,
                "msg_type": m.msg_type,
                "timestamp": m.timestamp.isoformat(),
                "generated_by_ai": m.generated_by_ai,
                "approved_by_human": m.approved_by_human,
                "media_url": m.media_url or "",           # ← NOUVEAU
                "media_mime_type": m.media_mime_type or "", # ← NOUVEAU
                "media_filename": m.media_filename or "",   # ← NOUVEAU
            }
            for m in qs
        ]
        return Response({
            "messages": messages,
            "client_id": pk,
            "human_takeover": getattr(
                getattr(client, "journey_state", None), "human_takeover", False
            ),
        })

class ManualMediaView(ClientLookupMixin, APIView):
    """
    POST /dashboard/clients/{id}/media/
    Envoie un fichier media (image, audio, document) vers le client WhatsApp.
    Seulement si human_takeover est actif.
    """
    permission_classes = [IsStudioStaff]
    parser_classes = [MultiPartParser, FormParser]
 
    def post(self, request, pk):
        from services.whatsapp import (
            send_image, send_audio, send_document,
            upload_media, send_audio_by_id,
        )
        from services.media_service import MEDIA_DIR, prepare_media_for_sending, get_public_url
        import uuid as _uuid
        from pathlib import Path
 
        client = self.get_client(pk)
 
        journey = getattr(client, "journey_state", None)
        if not journey or not journey.human_takeover:
            return Response({"error": "Human takeover must be active"}, status=status.HTTP_403_FORBIDDEN)
 
        uploaded_file = request.FILES.get("file")
        caption = request.data.get("caption", "")
 
        if not uploaded_file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
 
        if uploaded_file.size == 0:
            return Response({"error": "Empty file received"}, status=status.HTTP_400_BAD_REQUEST)
 
        try:
            MEDIA_DIR.mkdir(parents=True, exist_ok=True)
 
            original_mime = uploaded_file.content_type or ""
            original_name = uploaded_file.name or "file"
            ext = Path(original_name).suffix.lower() or ".bin"
            unique_name = f"agent_{_uuid.uuid4().hex[:12]}{ext}"
            file_path = MEDIA_DIR / unique_name
 
            with open(file_path, "wb") as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
 
            logger.info("Agent file | %s mime=%s size=%s",
                       unique_name, original_mime, file_path.stat().st_size)
 
            send_path, send_mime = prepare_media_for_sending(file_path, original_mime)
 
            # ← TOUJOURS uploader vers Supabase pour avoir une URL d'affichage
            display_url = get_public_url(send_path, send_mime) or ""
            logger.info("Supabase display URL: %s", display_url)
 
            sent = False
            msg_type = "document"
 
            if send_mime.startswith("image/"):
                msg_type = "image"
                if display_url:
                    send_image(to=client.wa_number, image_url=display_url, caption=caption)
                    sent = True
 
            elif send_mime.startswith("audio/"):
                msg_type = "audio"
                # Méthode 1 : upload direct WhatsApp (plus fiable)
                media_id = upload_media(send_path, send_mime)
                if media_id:
                    send_audio_by_id(to=client.wa_number, media_id=media_id)
                    sent = True
                    logger.info("Audio sent via WA media_id=%s", media_id)
                elif display_url:
                    # Fallback URL
                    send_audio(to=client.wa_number, audio_url=display_url)
                    sent = True
                    logger.info("Audio sent via Supabase URL fallback")
 
            else:
                msg_type = "document"
                if display_url:
                    send_document(to=client.wa_number, document_url=display_url,
                                 filename=original_name, caption=caption)
                    sent = True
 
            if not sent:
                return Response({"error": "Send failed — check storage config"},
                               status=status.HTTP_502_BAD_GATEWAY)
 
            # Enregistrer en DB avec display_url
            from apps.conversations.models import Message, MessageDirection, MessageStatus
            conv = client.conversations.filter(window_status="open").first()
            if conv:
                msg_defaults = {
                    "conversation": conv,
                    "client": client,
                    "direction": MessageDirection.OUTBOUND,
                    "status": MessageStatus.SENT,
                    "content": caption or f"[{msg_type} sent by agent]",
                    "msg_type": msg_type,
                    "generated_by_ai": False,
                    "approved_by_human": True,
                    "timestamp": timezone.now(),
                }
                mf = {f.name for f in Message._meta.get_fields()}
                if "media_url" in mf:
                    msg_defaults["media_url"] = display_url  # ← toujours rempli maintenant
                if "media_mime_type" in mf:
                    msg_defaults["media_mime_type"] = send_mime
                if "media_filename" in mf:
                    msg_defaults["media_filename"] = original_name
 
                Message.objects.create(
                    wa_message_id=f"agent_media_{_uuid.uuid4().hex[:12]}",
                    **msg_defaults,
                )
 
            return Response({"status": "sent", "msg_type": msg_type, "url": display_url})
 
        except Exception as exc:
            logger.error("ManualMediaView failed: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        

#Notifications added
class PushSubscriptionView(APIView):
    """
    POST /dashboard/push/subscribe/   → sauvegarder subscription
    DELETE /dashboard/push/subscribe/ → supprimer subscription
    """
    permission_classes = [IsStudioStaff]

    def post(self, request):
        from apps.dashboard.models import PushSubscription
        sub_data = request.data.get("subscription")
        if not sub_data:
            return Response({"error": "No subscription data"}, status=400)
        
        PushSubscription.objects.update_or_create(
            user=request.user,
            defaults={"subscription_json": sub_data},
        )
        return Response({"status": "subscribed"})

    def delete(self, request):
        from apps.dashboard.models import PushSubscription
        PushSubscription.objects.filter(user=request.user).delete()
        return Response({"status": "unsubscribed"})


class PushVapidKeyView(APIView):
    """GET /dashboard/push/vapid-key/ → retourne la clé publique VAPID"""
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from django.conf import settings
        return Response({"public_key": settings.VAPID_PUBLIC_KEY})

def send_push_notification(title: str, body: str, url: str = "/"):
    """
    Envoie une notification push à tous les agents abonnés.
    Appelé depuis ManualTakeoverView, webhook, etc.
    """
    print("🚀 send_push_notification CALLED")
    try:
        from apps.dashboard.models import PushSubscription
        from pywebpush import webpush, WebPushException
        from django.conf import settings
        import json

        subscriptions = PushSubscription.objects.all()
        if not subscriptions.exists():
            return

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "icon": "/static/img/logo.png",
        })

        import json
        from pywebpush import webpush, WebPushException

        for sub in subscriptions:
            try:
                subscription_info = sub.subscription_json
                if isinstance(subscription_info, str):
                    subscription_info = json.loads(subscription_info)
                    print(subscription_info["endpoint"])

                    print("📤 SENDING PUSH TO:", subscription_info)
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={
                        "sub": f"mailto:{settings.VAPID_CLAIMS_EMAIL}"
                    },
                    headers={"TTL": "60"},
                )

            except WebPushException as exc:
                print("🔥 WEBPUSH ERROR:", repr(exc))
                
                if exc.response:
                    print("🔥 RESPONSE:", exc.response.text)
                else:
                    print("🔥 NO RESPONSE FROM PUSH SERVICE")
    except Exception as exc:
        logger.error("send_push_notification failed: %s", exc)

def test_push(request):
    send_push_notification("TEST", "HELLO")
    return JsonResponse({"ok": True})

class InstagramClientListView(APIView):
    """List Instagram clients."""
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.clients.models import Client
        from apps.instagram.serializers import InstagramClientSerializer
        
        # Only clients with an Instagram ID
        qs = Client.objects.filter(ig_user_id__isnull=False).exclude(ig_user_id="").order_by("-last_contact")
        
        serializer = InstagramClientSerializer(qs, many=True)
        return Response(serializer.data)

class InstagramMessagesView(APIView):
    """Get Instagram messages for a specific client."""
    permission_classes = [IsStudioStaff]

    def get(self, request, ig_user_id):
        from apps.instagram.models import InstagramMessage
        from apps.instagram.serializers import InstagramMessageSerializer
        
        qs = InstagramMessage.objects.filter(client__ig_user_id=ig_user_id).order_by("timestamp")
        serializer = InstagramMessageSerializer(qs, many=True)
        return Response(serializer.data)

class InstagramManualMessageView(APIView):
    """Send a manual message to an Instagram client from the dashboard."""
    permission_classes = [IsStudioStaff]

    def post(self, request, ig_user_id):
        from apps.clients.models import Client
        from services.instagram_service import send_text
        from apps.instagram.models import InstagramConversation, InstagramMessage
        import uuid

        try:
            client = Client.objects.get(ig_user_id=ig_user_id)
        except Client.DoesNotExist:
            return Response({"error": "Client not found"}, status=404)

        text = request.data.get("message")
        
        if not text:
            return Response({"error": "Missing message"}, status=400)

        try:
            # Send to Instagram
            send_text(ig_user_id, text)
            
            # Record in DB
            conversation = InstagramConversation.objects.filter(client=client, is_open=True).first()
            if not conversation:
                conversation = InstagramConversation.objects.create(client=client)
                
            InstagramMessage.objects.create(
                ig_mid=f"manual_{uuid.uuid4().hex[:12]}",
                conversation=conversation,
                client=client,
                direction="outbound",
                content=text,
                timestamp=timezone.now(),
            )
            
            logger.info("Manual IG message sent to %s by %s", ig_user_id, request.user.username)
            return Response({"status": "sent"})
        except Exception as e:
            logger.error("Failed to send manual IG message: %s", e)
            return Response({"error": str(e)}, status=500)

class InstagramApprovalQueueListView(APIView):
    """List pending Instagram approval items."""
    permission_classes = [IsStudioStaff]

    def get(self, request):
        from apps.instagram.models import InstagramApprovalQueue
        from apps.instagram.serializers import InstagramApprovalQueueSerializer

        status_filter = request.query_params.get("status", "pending")
        qs = InstagramApprovalQueue.objects.filter(status=status_filter).select_related("client").order_by("-created_at")
        serializer = InstagramApprovalQueueSerializer(qs, many=True)
        return Response(serializer.data)

class InstagramApprovalApproveView(APIView):
    """Approve an Instagram AI suggestion."""
    permission_classes = [IsStudioStaff]

    def post(self, request, pk):
        from apps.instagram.models import InstagramApprovalQueue
        from services.instagram_service import send_text

        try:
            approval = InstagramApprovalQueue.objects.get(pk=pk)
        except InstagramApprovalQueue.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        approval.approve(request.user, notes=request.data.get("notes", ""))
        
        # Send to Instagram
        try:
            send_text(approval.client.ig_user_id, approval.ai_suggestion)
            return Response({"status": "approved"})
        except Exception as e:
            logger.error("Failed to send approved IG message: %s", e)
            return Response({"error": str(e)}, status=500)
