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
    path("bookings/", views.BookingListCreateView.as_view()),
    path("bookings/<int:pk>/", views.BookingDetailView.as_view()),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    path("clients/<int:pk>/messages/", views.ClientMessagesView.as_view(), name="client-messages"), #message dashboard
    path("clients/<int:pk>/media/", views.ManualMediaView.as_view(), name="client-media"),

]

#Notifications added
from .views import PushSubscriptionView, PushVapidKeyView

urlpatterns += [
    path("push/subscribe/", PushSubscriptionView.as_view()),
    path("push/vapid-key/", PushVapidKeyView.as_view()),
    path("instagram/clients/", views.InstagramClientListView.as_view()),
    path("instagram/clients/<str:ig_user_id>/messages/", views.InstagramMessagesView.as_view()),
    path("instagram/clients/<str:ig_user_id>/message/", views.InstagramManualMessageView.as_view()),
    path("instagram/approvals/", views.InstagramApprovalQueueListView.as_view()),
    path("instagram/approvals/<int:pk>/approve/", views.InstagramApprovalApproveView.as_view()),
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