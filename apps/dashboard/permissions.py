"""
Dashboard permissions.
All dashboard endpoints require authentication.
Studio staff = any authenticated Django user.
"""

from rest_framework.permissions import BasePermission


class IsStudioStaff(BasePermission):
    """
    Allows access to any authenticated user.
    In production: extend to check a 'studio_staff' group or flag.
    """

    message = "Studio staff access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
