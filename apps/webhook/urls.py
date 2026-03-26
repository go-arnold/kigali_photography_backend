from django.urls import path
from .views import WhatsAppWebhookView, ping

app_name = "webhook"

urlpatterns = [
    path("whatsapp/", WhatsAppWebhookView.as_view(), name="whatsapp"),
    path("ping/", ping),

]