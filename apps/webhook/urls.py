from django.urls import path
from .views import WhatsAppWebhookView

app_name = "webhook"


urlpatterns = [
    path("whatsapp/", WhatsAppWebhookView.as_view(), name="whatsapp"),
    # path("whatsapp", WhatsAppWebhookView.as_view(), name="whatsapp-noslash"),
]