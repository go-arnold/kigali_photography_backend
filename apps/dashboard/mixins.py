"""
Dashboard view mixins — shared behaviour across all dashboard views.
"""

import logging
from rest_framework.exceptions import NotFound
from apps.conversations.models import ApprovalQueue, ApprovalStatus

logger = logging.getLogger(__name__)


class ApprovalObjectMixin:
    """
    Mixin for views that operate on a single ApprovalQueue item.
    Provides get_approval() with status validation.
    """

    def get_approval(self, pk, expected_status=ApprovalStatus.PENDING):
        try:
            obj = ApprovalQueue.objects.select_related("client", "conversation").get(
                pk=pk
            )
        except ApprovalQueue.DoesNotExist:
            raise NotFound(f"Approval item {pk} not found.")

        if expected_status and obj.status != expected_status:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(f"Item is already '{obj.status}' — cannot action.")
        return obj


class ClientLookupMixin:
    """
    Mixin for views that need a client by pk or wa_number.
    """

    def get_client(self, lookup):
        from apps.clients.models import Client

        try:
            # Phone numbers start with + e.g. +250700000000
            if str(lookup).startswith("+"):
                return Client.objects.get(wa_number=lookup)
            # Numeric-only = primary key
            return Client.objects.get(pk=lookup)
        except Client.DoesNotExist:
            raise NotFound(f"Client '{lookup}' not found.")
