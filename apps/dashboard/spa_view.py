"""
Dashboard SPA view — serves the HTML frontend.
Kept separate to avoid touching the large views.py.
"""

from django.shortcuts import render
from django.views import View


class DashboardAppView(View):
    """
    Serves the single-page dashboard frontend.
    Authentication is handled client-side — the SPA checks /api/dashboard/stats/
    and redirects to the login form if it gets a 401/403.
    """

    def get(self, request):
        return render(request, "dashboard/dashboard.html")
