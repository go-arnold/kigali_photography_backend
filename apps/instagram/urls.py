from django.urls import path
from .views import InstagramWebhookView, InstagramSendView

urlpatterns = [
    path("webhook/", InstagramWebhookView.as_view(), name="ig-webhook"),
    path("send/", InstagramSendView.as_view(), name="ig-send"),  
]
