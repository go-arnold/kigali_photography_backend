from django.contrib import admin
from .models import Client, Child, JourneyState, ClientNote


class ClientNoteInline(admin.TabularInline):
    model = ClientNote
    extra = 0
    fields = ("content", "source", "is_approved", "created_at")
    readonly_fields = ("created_at",)


class ChildInline(admin.TabularInline):
    model = Child
    extra = 0
    fields = ("name", "birthday", "birthday_wish_sent_year")


class JourneyStateInline(admin.StackedInline):
    model = JourneyState
    extra = 0
    readonly_fields = ("heat_label", "created_at", "updated_at")
    fields = (
        "phase",
        "step",
        "heat_score",
        "heat_label",
        "detected_objection",
        "objection_count",
        "next_followup_at",
        "followup_count",
        "human_takeover",
        "takeover_reason",
        "selected_package",
        "session_date",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Heat Level")
    def heat_label(self, obj):
        return obj.heat_label if obj.pk else "-"


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "wa_number",
        "status",
        "language",
        "total_sessions",
        "lifetime_tokens_used",
        "last_contact",
    )
    list_filter = ("status", "language", "referral_source")
    search_fields = ("name", "wa_number")
    readonly_fields = (
        "first_contact",
        "created_at",
        "updated_at",
        "lifetime_tokens_used",
    )
    inlines = [ChildInline, JourneyStateInline, ClientNoteInline]
    ordering = ["-last_contact"]


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "birthday", "birthday_wish_needed")
    list_filter = ("birthday",)
    search_fields = ("name", "client__name", "client__wa_number")

    @admin.display(boolean=True, description="Wish Needed Today")
    def birthday_wish_needed(self, obj):
        return obj.birthday_wish_needed
