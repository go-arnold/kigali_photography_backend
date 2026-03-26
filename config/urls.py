from django.contrib import admin
from django.urls import path, include
from django.conf import settings

from apps.dashboard.spa_view import DashboardAppView
from apps.webhook.views import  ping


urlpatterns = [
    path("", DashboardAppView.as_view(), name="app"),
    path("admin/", admin.site.urls),
    path("api/webhook/", include("apps.webhook.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("ping/", ping),

]


if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(debug_toolbar.urls)),
    ]
