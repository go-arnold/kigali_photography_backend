# INSTAGRAM_AI.md — v3 (FINAL)
# Instagram DM Bot — AI Conversation System
# KP Kids Studio | Kigali, Rwanda
# =====================================================
# This file documents the v3 instagram_orchestrator.py
# which has ALREADY BEEN WRITTEN and provided separately.
# This file explains the logic so Gemini/Claude can:
#   (a) apply the new file correctly into the project
#   (b) verify imports and model fields are compatible
#   (c) make small adjustments if project structure differs
# =====================================================

---

## 🚨 WHAT CHANGED FROM v2 → v3

```
REMOVED ENTIRELY:
  - session_type question (studio vs home) — NO MORE HOME SESSIONS
  - DISCOVERY_QUESTIONS dict with 5 separate questions asked one by one
  - photo_type question
  - _process_discovery_answer() one-question-at-a-time logic
  - _get_next_discovery_question()
  - _is_discovery_complete()
  - WELCOME_MESSAGES as a separate first-contact-only block

NEW BEHAVIOR:
  - Studio-only. All packages are studio packages (Starter/Silver/Gold).
  - Discovery is now a SINGLE combined question about all 3 extras
    (frames, cake, video) asked together in one message.
  - Multi-intent first messages (greeting + location + price all in
    one or across multiple messages) are detected and answered together.
  - Client can answer extras in any order, across multiple messages,
    mentioning 1, 2, or 3 extras — system tracks what's been decided
    and only asks about what's still pending.
  - "No" to extras → immediately show base packages (no extra cost).
  - "Yes" without specifics → ask which ones.
  - Specific extras named → mark those True, others default False
    once message processed (one-shot decision per message round).
  - Questions about specific extras (frame size, cake size, video
    duration) are answered directly via _get_extra_info_answer(),
    then re-prompt for extras choice.
  - After packages shown:
      - discount request → refuse (escalate at 3rd) → re-ask package choice
      - "other packages?" → refuse politely → re-ask package choice
      - extra add/remove → recalculate → re-show packages
      - package chosen → ask date/time
  - Date given → acknowledge + immediate human takeover + email + push
  - "Talk to human" / agent signals → immediate takeover from ANY state
  - Language locked on FIRST message only — never changes after
```

---

## 🚨 CRITICAL RULES (UNCHANGED)

1. **NO BUTTONS. NO QUICK REPLIES. NO MARKDOWN.** Pure text. Emojis OK.
2. **DO NOT TOUCH WHATSAPP FILES.** Only Instagram-related files.
3. **PRICES MUST BE EXACT.** Starter 50k/Silver 70k/Gold 100k.
   Extras: Frames +20k, Cake +30k, Video +29k, Cake+Video bundle +50k.
4. **LANGUAGE LOCKED FOREVER** on first message (en/fr/rw).
5. **STUDIO ONLY** — no home session, no session_type question at all.

---

## File Structure — What Exists Now

```
services/instagram_orchestrator.py   ← REPLACED ENTIRELY with v3 (provided)
services/INSTAGRAM_AI.md             ← this file (documentation only)
apps/instagram/models.py             ← UNCHANGED — verify fields below
apps/instagram/views.py              ← UNCHANGED — webhook parsing
services/instagram_service.py        ← UNCHANGED — send_text, mark_as_seen, get_user_profile
services/button_flow.py              ← READ ONLY — _send_agent_request_email() reused
services/openai_service.py           ← READ ONLY — call_openai, build_messages_context reused
services/rag_service.py              ← READ ONLY — retrieve_context reused
services/client_service.py           ← READ ONLY — onboard_client, record_tokens reused
utils/language.py                    ← READ ONLY — detect_language reused
```

---

## Required Model Field Verification

Before applying instagram_orchestrator.py v3, verify these fields exist:

### apps/clients/models.py — Client model
```python
language          # CharField — already exists
language_locked   # BooleanField — already exists (used in v2, kept in v3)
ig_user_id        # CharField — added in earlier Instagram setup
update_last_contact()  # method — already exists
```

### apps/clients/models.py — JourneyState model
```python
flow_mode          # CharField — values now used:
                   #   "new", "active", "discovery", "packages_shown",
                   #   "awaiting_datetime", "human_takeover", "await_confirm"
                   #   NOTE: "await_confirm" kept for compatibility but
                   #   v3 goes directly to "human_takeover" after date.
discovery_state    # JSONField — NEW STRUCTURE in v3:
                   #   {"frames": None|True|False,
                   #    "cake": None|True|False,
                   #    "video": None|True|False,
                   #    "_discount_count": int}
                   #   ⚠️ OLD STRUCTURE had photo_type/session_type —
                   #   these keys are simply ignored/dropped now.
                   #   No migration needed since JSONField is schemaless,
                   #   but EXISTING in-progress conversations with old
                   #   discovery_state shape will be reset naturally
                   #   (the new code only reads frames/cake/video keys).
selected_package   # CharField — "starter"|"silver"|"gold" (no more "premium")
human_takeover     # BooleanField — unchanged
takeover_reason    # CharField/TextField — unchanged
heat_score         # IntField — unchanged, used as fallback
phase              # CharField — unchanged, passed to retrieve_context
```

### apps/instagram/models.py
```python
InstagramConversation
  - client (FK)
  - is_open (Bool)
  - touch() method

InstagramMessage
  - ig_mid (unique)
  - conversation (FK)
  - client (FK)
  - direction ("inbound"|"outbound")
  - content (Text)
  - model_used, tokens_input, tokens_output
  - timestamp

InstagramApprovalQueue  ← imported but NOT directly used in v3
                          (v3 uses apps.conversations.models.ApprovalQueue
                           + ApprovalAction.ESCALATE instead — see note below)
```

### ⚠️ IMPORTANT — ApprovalQueue Model Choice

v3's `_activate_human_takeover()` uses:
```python
from apps.conversations.models import ApprovalQueue, ApprovalAction
ApprovalQueue.objects.create(
    client=client,
    conversation=conversation,   # <- InstagramConversation instance
    action=ApprovalAction.ESCALATE,
    ...
)
```

**Action required:** Verify that `apps.conversations.models.ApprovalQueue.conversation`
field accepts an `InstagramConversation` instance (i.e. it's a generic FK,
or there's a separate `ig_conversation` field, or the FK is loosely typed).

If `ApprovalQueue.conversation` is strictly a ForeignKey to
`apps.conversations.models.Conversation` (the WhatsApp conversation model)
and CANNOT accept an `InstagramConversation`, then:

**Option A (preferred, minimal change):** Use `InstagramApprovalQueue`
instead (it already exists per v2's import). Replace the block with:
```python
from apps.instagram.models import InstagramApprovalQueue
InstagramApprovalQueue.objects.create(
    client=client,
    conversation=conversation,
    action="escalate",  # or InstagramApprovalQueue.ApprovalAction.ESCALATE
    ai_suggestion=f"[Instagram] {reason}",
    ai_reasoning=reason,
    expires_at=timezone.now() + timezone.timedelta(hours=72),
)
```

**Option B:** If the dashboard's approval queue view only reads from
`apps.conversations.models.ApprovalQueue`, and you want Instagram
escalations to show up in the SAME dashboard approval list, then leave
`conversation=None` (or omit it) and just pass `client=client`:
```python
from apps.conversations.models import ApprovalQueue, ApprovalAction
ApprovalQueue.objects.create(
    client=client,
    conversation=None,
    action=ApprovalAction.ESCALATE,
    ai_suggestion=f"[Instagram] {reason}",
    ai_reasoning=reason,
    heat_score_at_suggestion=getattr(journey, "heat_score", 50),
    expires_at=timezone.now() + timezone.timedelta(hours=72),
)
```

**Gemini/Claude: inspect both models and choose the option that doesn't
break either dashboard's approval list. Test that the approval appears
in the dashboard after a date is provided on Instagram.**

---

## Multi-Message Context Handling — How It Works

Instagram users often split their thoughts across multiple messages sent
seconds apart (e.g. "Hi" then "where are you" then "prices?"). Since each
webhook call processes ONE message independently, v3 handles this via:

```python
recent_history = _get_recent_messages(conversation)  # last 20 messages
```

In `_handle_active_message()`, the function checks BOTH:
1. The current message's text for location/price/greeting signals
2. The last 4 messages from the client (recent_history) for the same signals

This means: if message 1 was "Hi" (answered with greeting), message 2 is
"where are you" (answered with location), and message 3 is "prices?" —
by message 3, `combined_text` includes all 3 messages' content, so even
if greeting/location were already answered, the price intent in message 3
triggers correctly and starts discovery.

**Known limitation:** If the SAME intent (e.g. location) appears in both
the current message and history, it could theoretically be answered twice
across separate webhook calls. This is ACCEPTABLE — it's better to
over-answer than under-answer on Instagram, and repeating a short location
answer once is not jarring. Do not add deduplication logic that risks
under-answering instead.

---

## Conversation Flow Reference (for testing)

```
┌─────────────────────────────────────────────────────────────┐
│ flow_mode = "new" / "active"                                  │
│  - Greeting detected → friendly welcome (short)               │
│  - Location detected → address + hours                        │
│  - Price/package/booking detected →                           │
│      "We don't charge per photo... want extras?"              │
│      → flow_mode = "discovery"                                │
│  - All combined in ONE response if multiple intents detected  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ flow_mode = "discovery"                                       │
│  - "No" (no extras mentioned) → ds={frames:F,cake:F,video:F}  │
│      → show packages (no extra cost) → packages_shown         │
│  - "Yes" (no specifics) → ask which ones (list all 3)         │
│  - Specific extras named (1, 2, or 3, across messages) →       │
│      mark True for named ones, False for unmentioned          │
│      once all 3 keys are non-None → show packages             │
│  - Question about an extra (frame size/cake size/video len) → │
│      answer directly + re-ask "want any extras?"               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ flow_mode = "packages_shown"                                  │
│  - Discount request → refuse (1st/2nd) → re-ask choice         │
│                        3rd → human takeover                    │
│  - "other packages?" → refuse politely → re-ask choice         │
│  - "remove/add cake/video/frame" → recalc → re-show packages   │
│  - "Starter"/"Silver"/"Gold" → confirm + ask date               │
│      → flow_mode = "awaiting_datetime"                          │
│  - Anything else → AI answers + re-asks "which package?"        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ flow_mode = "awaiting_datetime"                               │
│  - Date/time detected → acknowledge + human_takeover + email   │
│      + push notification + ApprovalQueue entry                 │
│  - Not a date → AI answers + re-ask "preferred date?"           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ flow_mode = "human_takeover"                                  │
│  - AI completely silent. Agent handles via dashboard.          │
└─────────────────────────────────────────────────────────────┘

ANYTIME (any flow_mode except human_takeover/await_confirm):
  - "talk to agent"/"human"/etc → immediate human_takeover
```

---

## What Gemini/Claude Must Do — Step by Step

```
STEP 1 — Backup
  git checkout feature/instagram-bot  (or current IG branch)
  git add -A && git commit -m "checkpoint before v3 orchestrator"

STEP 2 — Replace the orchestrator file
  Replace the ENTIRE content of services/instagram_orchestrator.py
  with the v3 file provided separately (instagram_orchestrator.py).

STEP 3 — Verify imports resolve
  Open apps/conversations/models.py
  Confirm ApprovalQueue + ApprovalAction exist and check the
  `conversation` field's FK target (see "IMPORTANT — ApprovalQueue
  Model Choice" section above). Apply Option A or B accordingly.

STEP 4 — Verify apps/instagram/models.py
  Confirm InstagramConversation has .touch() and is_open field.
  Confirm InstagramMessage has all fields used in _save_inbound/_save_outbound.

STEP 5 — Verify apps/instagram/views.py webhook
  Confirm it calls handle_instagram_message(sender_id, message_text,
  message_id, timestamp_ms) with this exact signature — v3 keeps the
  same signature as v2, so no webhook changes should be needed.

STEP 6 — Verify services/instagram_service.py
  Confirm send_text(recipient_id, text), mark_as_seen(sender_id),
  and get_user_profile(sender_id) exist with these signatures.
  v3 uses send_text and mark_as_seen exactly as v2 did.

STEP 7 — Verify services/button_flow.py
  Confirm _send_agent_request_email(client, journey) exists and
  works when called with an Instagram client (wa_number starting
  with "ig_"). If it requires a real phone number for WhatsApp
  sending internally, wrap in try/except (already done in v3) so
  a failure here does not break the takeover flow — only the email
  notification is best-effort.

STEP 8 — Run migrations if needed
  No new model fields required by v3. If discovery_state previously
  had a NOT NULL constraint expecting old keys, no action needed
  (JSONField is schemaless). Skip migrations unless Step 3/4 reveal
  missing fields.

STEP 9 — Test scenarios (see Testing Checklist below)

STEP 10 — Commit
  git add -A
  git commit -m "feat: instagram orchestrator v3 - studio-only,
  combined extras discovery, multi-intent handling"
```

---

## Testing Checklist

```
[ ] "Hi" → short greeting + offer to help (NOT the long v2 welcome)
[ ] "Hi" then "where are you" then "prices?" (3 separate messages)
    → by 3rd message, bot responds with price intro + extras question
    → (greeting/location may have been answered in earlier turns,
       that's fine)
[ ] Single message "Hi, where are you, and what are your prices?"
    → ONE response covering greeting + location + price intro

[ ] In discovery, client says "No" → packages shown immediately,
    no extra cost, 3 packages (50k/70k/100k)

[ ] In discovery, client says "Yes" → bot asks "which ones?"
    listing frames/cake/video
    → client replies "cake and video" → packages shown with
      cake+video bundle (+50k, NOT +59k)

[ ] In discovery, client says "I want frames" (1st message)
    then "and a cake too" (2nd message)
    → after 2nd message, frames=True, cake=True, video=False
      (assumed not wanted since never mentioned)
    → packages shown with frames + cake costs (+20k +30k = +50k)

[ ] In discovery, client asks "how long is the video?"
    → bot answers "15 to 30 seconds" + re-asks "want any extras?"

[ ] After packages shown, "do you have a discount?"
    → polite refusal + "which package would you like?"
    → repeat 2 more times → 3rd time → human takeover

[ ] After packages shown, "any other packages?"
    → polite refusal explaining these reflect quality
    → "which package would you like?"

[ ] After packages shown, "remove the cake" (if cake was included)
    → recalculated packages shown again without cake cost

[ ] After packages shown, "Silver" → confirm Silver + total price
    → ask for date/time → flow_mode = "awaiting_datetime"

[ ] In awaiting_datetime, "next Saturday at 2pm"
    → acknowledge + human_takeover activated + email sent
    + push notification + ApprovalQueue/InstagramApprovalQueue entry
    visible in dashboard

[ ] In awaiting_datetime, "is parking available?" (not a date)
    → AI answers parking question + re-asks "preferred date?"

[ ] At ANY point, "I want to talk to a real person"
    → immediate human_takeover, AI goes silent

[ ] Kinyarwanda message first → ALL subsequent responses in
    Kinyarwanda even if client later writes in English/French

[ ] French message first → ALL subsequent responses in French

[ ] Video duration ALWAYS phrased as "15 to 30 seconds" — never
    "minutes" anywhere in any language
```

---

## Pricing Reference (for verification against button_flow.py)

```
Studio packages (base):
  Starter: 50,000 RWF | 1h | 8 edited photos + all unedited
  Silver:  70,000 RWF | 1h | 12 edited photos + all unedited
  Gold:    100,000 RWF | 1.5h | 18 edited photos + all unedited

Extras:
  Frames:        +20,000 RWF
  Cake:          +30,000 RWF
  Video:         +29,000 RWF (15-30 seconds)
  Cake + Video bundle: +50,000 RWF (NOT 30k+29k=59k)

Examples:
  Starter + nothing        = 50,000 RWF
  Silver + frames           = 90,000 RWF
  Gold + cake + video        = 150,000 RWF (100k + 50k bundle)
  Gold + frames + cake + video = 170,000 RWF (100k + 20k + 50k)
```

