"""
Dashboard URL configuration.
All routes prefixed with /api/dashboard/ in config/urls.py
"""
from django.urls import path
from . import views
from .spa_view import DashboardAppView

app_name = "dashboard"

urlpatterns = [
    # ── Dashboard SPA ──────────────────────────────────────────────────────────
    path("", DashboardAppView.as_view(), name="app"),
    # ── Stats ──────────────────────────────────────────────────────────────────
    path("stats/", views.DashboardStatsView.as_view(), name="stats"),
    # ── Approval queue ─────────────────────────────────────────────────────────
    path("approvals/", views.ApprovalQueueListView.as_view(), name="approval-list"),
    path(
        "approvals/<int:pk>/approve/",
        views.ApprovalApproveView.as_view(),
        name="approval-approve",
    ),
    path(
        "approvals/<int:pk>/reject/",
        views.ApprovalRejectView.as_view(),
        name="approval-reject",
    ),
    # ── Clients ────────────────────────────────────────────────────────────────
    path("clients/", views.ClientListView.as_view(), name="client-list"),
    path("clients/<str:pk>/", views.ClientDetailView.as_view(), name="client-detail"),
    path(
        "clients/<str:pk>/message/",
        views.ManualMessageView.as_view(),
        name="client-message",
    ),
    path(
        "clients/<str:pk>/journey/",
        views.JourneyOverrideView.as_view(),
        name="client-journey",
    ),
    path(
        "clients/<str:pk>/takeover/",
        views.HumanTakeoverView.as_view(),
        name="client-takeover",
    ),
    # ── Scheduled messages ─────────────────────────────────────────────────────
    path("scheduled/", views.ScheduledMessageListView.as_view(), name="scheduled-list"),
    path(
        "scheduled/<int:pk>/cancel/",
        views.ScheduledMessageCancelView.as_view(),
        name="scheduled-cancel",
    ),
]



# from django.urls import path
# from . import views

# app_name = "dashboard"

# urlpatterns = [
#     # ── Stats ──────────────────────────────────────────────────────────────────
#     path("stats/", views.DashboardStatsView.as_view(), name="stats"),
#     # ── Approval queue ─────────────────────────────────────────────────────────
#     path("approvals/", views.ApprovalQueueListView.as_view(), name="approval-list"),
#     path(
#         "approvals/<int:pk>/approve/",
#         views.ApprovalApproveView.as_view(),
#         name="approval-approve",
#     ),
#     path(
#         "approvals/<int:pk>/reject/",
#         views.ApprovalRejectView.as_view(),
#         name="approval-reject",
#     ),
#     # ── Clients ────────────────────────────────────────────────────────────────
#     path("clients/", views.ClientListView.as_view(), name="client-list"),
#     path("clients/<str:pk>/", views.ClientDetailView.as_view(), name="client-detail"),
#     path(
#         "clients/<str:pk>/message/",
#         views.ManualMessageView.as_view(),
#         name="client-message",
#     ),
#     path(
#         "clients/<str:pk>/journey/",
#         views.JourneyOverrideView.as_view(),
#         name="client-journey",
#     ),
#     path(
#         "clients/<str:pk>/takeover/",
#         views.HumanTakeoverView.as_view(),
#         name="client-takeover",
#     ),
#     # ── Scheduled messages ─────────────────────────────────────────────────────
#     path("scheduled/", views.ScheduledMessageListView.as_view(), name="scheduled-list"),
#     path(
#         "scheduled/<int:pk>/cancel/",
#         views.ScheduledMessageCancelView.as_view(),
#         name="scheduled-cancel",
#     ),
# ]

# ===