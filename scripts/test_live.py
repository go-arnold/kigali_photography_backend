#!/usr/bin/env python
"""
Live Integration Test Script
Run with: python scripts/test_live.py [--phone +250700...] [--skip-claude]
"""

import os, sys, argparse, django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()


def ok(label, fn):
    try:
        result = fn()
        print(f"  v {label}" + (f" -- {result}" if result else ""))
        return True
    except Exception as e:
        print(f"  X {label} -- {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", default=None)
    parser.add_argument("--skip-claude", action="store_true")
    args = parser.parse_args()
    failures = []

    print()
    print("=" * 52)
    print("  KIGALI PHOTOGRAPHY -- LIVE INTEGRATION TEST")
    print("=" * 52)
    print()

    print("1. Database")

    def test_db():
        from apps.clients.models import Client

        return f"{Client.objects.count()} clients in DB"

    if not ok("PostgreSQL connection", test_db):
        failures.append("database")
        print("  STOP: fix database first.")
        return False

    print()
    print("2. Redis")

    def test_redis():
        from django.core.cache import cache

        cache.set("live_ping", "pong", 10)
        assert cache.get("live_ping") == "pong"
        return "read/write OK"

    if not ok("Redis connection", test_redis):
        failures.append("redis")

    print()
    print("3. Knowledge Base")

    def test_kb():
        from apps.rag.models import KnowledgeDocument, KnowledgeChunk

        docs = KnowledgeDocument.objects.filter(is_active=True).count()
        chunks = KnowledgeChunk.objects.count()
        if docs == 0:
            raise Exception(
                "No docs -- run: python manage.py index_knowledge_base --seed"
            )
        if chunks == 0:
            raise Exception(
                "No chunks -- run: python manage.py index_knowledge_base --seed"
            )
        return f"{docs} docs, {chunks} chunks"

    if not ok("Documents seeded + indexed", test_kb):
        failures.append("knowledge_base")

    def test_retrieval():
        from services.rag_service import retrieve_context

        result = retrieve_context("What packages do you offer?", "booking", "en")
        if not result:
            raise Exception("Empty -- check chunks exist")
        return f"{len(result)} chars retrieved"

    if not ok("RAG retrieval returns content", test_retrieval):
        failures.append("rag")

    print()
    print("4. Heat Engine (no API calls)")

    def test_heat_positive():
        from services.heat_engine import calculate_heat_delta

        r = calculate_heat_delta("I love your photos! Can I book for next Saturday?")
        assert r["total_delta"] > 0
        return f"delta=+{r['total_delta']} signals={r['signals'][:2]}"

    if not ok("Positive signals raise heat", test_heat_positive):
        failures.append("heat")

    def test_heat_objection():
        from services.heat_engine import calculate_heat_delta

        r = calculate_heat_delta("That is too expensive for my budget")
        assert r["breakdown"]["objection"] < 0
        return f"objection_delta={r['breakdown']['objection']}"

    if not ok("Objection lowers heat", test_heat_objection):
        failures.append("heat_obj")

    def test_followup_limits():
        from services.heat_engine import should_send_followup

        assert should_send_followup("HIGH", 0) is True
        assert should_send_followup("HIGH", 2) is False
        assert should_send_followup("MEDIUM", 1) is False
        assert should_send_followup("LOW", 1) is False
        return "HIGH=2max, MEDIUM=1max, LOW=1max"

    if not ok("Follow-up limits enforced", test_followup_limits):
        failures.append("followup")

    print()
    print("5. Claude API")
    if args.skip_claude:
        print("  (skipped)")
    else:

        def test_haiku():
            from services.claude import call_claude

            r = call_claude(
                system_prompt="Reply with exactly one word: PONG",
                messages=[{"role": "user", "content": "PING"}],
            )
            if not r.ok:
                raise Exception(r.error)
            return f"tokens={r.total_tokens} reply={r.text[:30]!r}"

        if not ok("Haiku call (approx /bin/sh.00002)", test_haiku):
            failures.append("claude")

        def test_intent():
            import json
            from services.claude import analyze_intent_and_heat

            r = analyze_intent_and_heat("I want to book a session for my daughter!")
            if not r.ok:
                raise Exception(r.error)
            raw = r.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)
            return f"intent={data.get('intent')} heat_delta={data.get('heat_delta')}"

        if not ok("Intent analysis returns valid JSON", test_intent):
            failures.append("claude_intent")

    print()
    print("6. Full Pipeline (real Claude, WhatsApp mocked)")
    if args.skip_claude:
        print("  (skipped)")
    else:

        def test_en_pipeline():
            from unittest.mock import patch

            with (
                patch("services.whatsapp.send_text") as mock_send,
                patch("services.whatsapp.mark_as_read"),
            ):
                from services.journey_orchestrator import handle_inbound_message

                r = handle_inbound_message(
                    message_id="live_en_001",
                    from_number="+250700099001",
                    from_name="Test EN",
                    msg_type="text",
                    text="Hello! I would like to book a session for my 2-year-old.",
                    timestamp="1700000000",
                )
                if not r.success:
                    raise Exception(r.error)
                sent = mock_send.called
            return f"action={r.action} tokens={r.tokens_used} wa_mocked={sent}"

        if not ok("English client -- full pipeline", test_en_pipeline):
            failures.append("pipeline_en")

        def test_rw_pipeline():
            from unittest.mock import patch

            with (
                patch("services.whatsapp.send_text"),
                patch("services.whatsapp.mark_as_read"),
            ):
                from services.journey_orchestrator import handle_inbound_message

                r = handle_inbound_message(
                    message_id="live_rw_001",
                    from_number="+250700099002",
                    from_name="Test RW",
                    msg_type="text",
                    text="Muraho! Ndashaka gufotorwa umwana wanjye.",
                    timestamp="1700000001",
                )
                if not r.success:
                    raise Exception(r.error)
            from apps.clients.models import Client

            c = Client.objects.get(wa_number="+250700099002")
            return f"action={r.action} language_detected={c.language}"

        if not ok("Kinyarwanda detected + response", test_rw_pipeline):
            failures.append("pipeline_rw")

        def test_opt_out():
            from unittest.mock import patch

            with (
                patch("services.whatsapp.send_text"),
                patch("services.whatsapp.mark_as_read"),
            ):
                from services.journey_orchestrator import handle_inbound_message

                r = handle_inbound_message(
                    message_id="live_opt_001",
                    from_number="+250700099003",
                    from_name="Opt Test",
                    msg_type="text",
                    text="STOP",
                    timestamp="1700000002",
                )
            from apps.clients.models import Client

            c = Client.objects.get(wa_number="+250700099003")
            if not c.is_opted_out:
                raise Exception("Client not marked opted out")
            return f"action={r.action} is_opted_out={c.is_opted_out}"

        if not ok("STOP keyword -- opt out", test_opt_out):
            failures.append("opt_out")

        def test_budget_guard():
            from unittest.mock import patch
            from datetime import timedelta
            from django.utils import timezone
            from apps.clients.models import Client, JourneyState
            from apps.conversations.models import Conversation

            c = Client.objects.create(wa_number="+250700099004")
            JourneyState.objects.create(client=c)
            Conversation.objects.create(
                client=c,
                token_budget=10,
                tokens_used=999,
                window_expires_at=timezone.now() + timedelta(hours=24),
            )
            with (
                patch("services.whatsapp.send_text"),
                patch("services.whatsapp.mark_as_read"),
            ):
                from services.journey_orchestrator import handle_inbound_message

                r = handle_inbound_message(
                    message_id="live_budget_001",
                    from_number="+250700099004",
                    from_name="Budget Test",
                    msg_type="text",
                    text="hello",
                    timestamp="1700000003",
                )
            if r.action != "human_takeover":
                raise Exception(f"Expected human_takeover, got {r.action}")
            return "budget exceeded -- takeover, no Claude call"

        if not ok(
            "Budget exceeded -- human takeover (no Claude call)", test_budget_guard
        ):
            failures.append("budget")

        def test_human_takeover_silences_ai():
            from unittest.mock import patch
            from apps.clients.models import Client, JourneyState

            c = Client.objects.create(wa_number="+250700099005")
            JourneyState.objects.create(client=c, human_takeover=True)
            with (
                patch("services.claude.call_claude") as mock_claude,
                patch("services.whatsapp.send_text"),
                patch("services.whatsapp.mark_as_read"),
            ):
                from services.journey_orchestrator import handle_inbound_message

                r = handle_inbound_message(
                    message_id="live_takeover_001",
                    from_number="+250700099005",
                    from_name="Takeover",
                    msg_type="text",
                    text="hello",
                    timestamp="1700000004",
                )
                assert not mock_claude.called, (
                    "Claude called despite human_takeover=True"
                )
            return f"action={r.action}, claude_called=False"

        if not ok(
            "Human takeover -- AI completely silenced", test_human_takeover_silences_ai
        ):
            failures.append("takeover")

    print()
    print("7. WhatsApp Real Send")
    if not args.phone:
        print("  (skipped -- pass --phone +250700XXXXXXX to also send a real message)")
    else:

        def test_wa():
            from services.whatsapp import send_text

            r = send_text(
                to=args.phone,
                message=(
                    "Kigali Photography Bot -- live test OK! "
                    "Reply to this message and the full bot will respond. "
                ),
            )
            wamid = r.get("messages", [{}])[0].get("id", "?")
            return f"wamid={wamid}"

        if not ok(f"Real WhatsApp send to {args.phone}", test_wa):
            failures.append("whatsapp")

    print()
    print("=" * 52)
    if not failures:
        print("  ALL TESTS PASSED")
        print()
        if not args.phone:
            print("  Next steps:")
            print("  1. ngrok http 8000")
            print("  2. Register ngrok URL in Meta dashboard")
            print("  3. Start Celery:  celery -A config worker -l info")
            print("  4. python scripts/test_live.py --phone +250700XXXXXXX")
            print("  5. Send messages from your personal WhatsApp")
    else:
        print(f"  FAILED ({len(failures)}): {chr(44).join(failures)}")
    print("=" * 52)
    print()

    try:
        from apps.clients.models import Client

        Client.objects.filter(wa_number__startswith="+25070009900").delete()
    except Exception:
        pass

    return len(failures) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
