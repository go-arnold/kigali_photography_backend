"""
Client model unit tests — no DB required for logic tests.
"""
from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.clients.models import Client, Child, JourneyState, JourneyPhase, JourneyStep


class ClientModelTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            wa_number="+250700000001",
            name="Uwase Marie",
            status=Client.Status.NEW if hasattr(Client, 'Status') else "new",
        )

    def test_str(self):
        self.assertIn("Uwase Marie", str(self.client_obj))

    def test_update_last_contact(self):
        before = timezone.now()
        self.client_obj.update_last_contact()
        self.client_obj.refresh_from_db()
        self.assertGreaterEqual(self.client_obj.last_contact, before)

    def test_token_budget_default(self):
        """lifetime_tokens_used starts at 0."""
        self.assertEqual(self.client_obj.lifetime_tokens_used, 0)


class ChildModelTest(TestCase):
    def setUp(self):
        self.parent = Client.objects.create(wa_number="+250700000002", name="Parent")
        today = timezone.now().date()
        self.child = Child.objects.create(
            client=self.parent,
            name="Amina",
            birthday=date(today.year - 3, today.month, today.day),
        )

    def test_birthday_wish_needed_today(self):
        """Child with today's birthday and no wish sent this year needs a wish."""
        self.assertTrue(self.child.birthday_wish_needed)

    def test_birthday_wish_not_needed_after_sent(self):
        today = timezone.now().date()
        self.child.birthday_wish_sent_year = today.year
        self.child.save()
        self.assertFalse(self.child.birthday_wish_needed)

    def test_birthday_wish_not_needed_wrong_day(self):
        self.child.birthday = date(2020, 1, 1)  # Not today
        self.child.save()
        self.assertFalse(self.child.birthday_wish_needed)


class JourneyStateTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(wa_number="+250700000003")
        self.journey = JourneyState.objects.create(client=self.client_obj)

    def test_default_heat_score(self):
        self.assertEqual(self.journey.heat_score, 50)

    def test_heat_label_high(self):
        self.journey.heat_score = 75
        self.assertEqual(self.journey.heat_label, "HIGH")

    def test_heat_label_medium(self):
        self.journey.heat_score = 50
        self.assertEqual(self.journey.heat_label, "MEDIUM")

    def test_heat_label_low(self):
        self.journey.heat_score = 20
        self.assertEqual(self.journey.heat_label, "LOW")

    def test_advance_updates_phase_step(self):
        self.journey.advance(JourneyPhase.BOOKING, JourneyStep.PACKAGE_PRESENTATION)
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.phase, JourneyPhase.BOOKING)
        self.assertEqual(self.journey.step, JourneyStep.PACKAGE_PRESENTATION)

    def test_human_takeover_flag(self):
        self.journey.flag_human_takeover("Budget exceeded")
        self.journey.refresh_from_db()
        self.assertTrue(self.journey.human_takeover)
        self.assertEqual(self.journey.takeover_reason, "Budget exceeded")