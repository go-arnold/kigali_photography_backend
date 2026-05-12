from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.dashboard.spa_view import DashboardAppView
from apps.webhook.views import  ping
from apps.dashboard import views


urlpatterns = [
    path("", DashboardAppView.as_view(), name="app"),
    path("admin/", admin.site.urls),
    path("api/webhook/", include("apps.webhook.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/instagram/", include("apps.instagram.urls")),
    path("ping/", ping),
    path("test-push/", views.test_push),

    
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(debug_toolbar.urls)),
    ]

from django.views.generic import TemplateView

urlpatterns += [
    path("sw.js", TemplateView.as_view(
        template_name="sw.js",
        content_type="application/javascript",
    ), name="sw"),
]