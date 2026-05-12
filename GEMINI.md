# GEMINI.md — Instagram Bot Implementation Guide
# KP Kids Studio — WhatsApp + Instagram AI Bot System
# =====================================================
# READ THIS ENTIRE FILE BEFORE TOUCHING ANY CODE.
# This is your single source of truth.

---

## 🚨 CRITICAL RULE — NON-NEGOTIABLE

**THE WHATSAPP SYSTEM MUST NOT BE TOUCHED IN ANY WAY.**

WhatsApp is fully operational in production with real clients. Every file listed
under "DO NOT MODIFY" is off-limits. Your job is purely additive: you add
Instagram support alongside the existing system without altering a single line
of WhatsApp logic.

If you are ever unsure whether a change affects WhatsApp → DO NOT MAKE IT.
Ask for clarification instead.

---

## Project Overview

KP Kids Studio is a children's photography studio in Kigali, Rwanda. They have
a fully operational WhatsApp chatbot (using Meta Cloud API) backed by a Django +
Celery backend. The bot handles bookings, package discovery, payments, and human
takeover via a custom dashboard.

**Your task:** Add an Instagram DM bot that uses the same AI pipeline, runs in
parallel, and never interferes with WhatsApp.

**Stack:**
- Backend: Django 4.x + Celery + Redis (deployed on Koyeb)
- AI: OpenAI GPT-4o-mini (default) / GPT-4o (escalation)
- WhatsApp: Meta Cloud API (FULLY OPERATIONAL — DO NOT TOUCH)
- Instagram: Meta Graph API Instagram Messaging (TO BE ADDED)
- Storage: Supabase Storage (media files)
- Dashboard: Vanilla JS SPA (single HTML page)
- Database: PostgreSQL (Supabase hosted)

---

## Existing Project Structure

```
KIGALI_PHOTOGRA.../
├── apps/
│   ├── automation/        ← Celery tasks (process_inbound_message, scheduled msgs)
│   ├── clients/           ← Client, JourneyState, Child models
│   ├── conversations/     ← Message, Conversation, ApprovalQueue, Booking models
│   ├── dashboard/         ← Dashboard API views + permissions + serializers
│   ├── rag/               ← RAG knowledge base models
│   └── webhook/           ← WhatsApp webhook receiver (DO NOT MODIFY)
├── chats/                 ← (unused placeholder)
├── config/
│   ├── settings.py        ← All settings including WHATSAPP, OPENAI, SUPABASE
│   ├── urls.py            ← Main URL routing
│   ├── celery.py          ← Celery app config
│   └── wsgi.py
├── services/
│   ├── button_flow.py     ← WhatsApp button flow logic (DO NOT MODIFY)
│   ├── client_service.py  ← Client onboarding, token recording
│   ├── claude.py          ← (legacy, replaced by openai_service)
│   ├── heat_engine.py     ← Heat score calculation
│   ├── journey_orchestrator.py ← Main AI pipeline (DO NOT MODIFY)
│   ├── media_service.py   ← Supabase Storage upload/download
│   ├── openai_service.py  ← OpenAI calls, prompts, build_system_prompt
│   ├── rag_indexer.py     ← RAG indexing
│   ├── rag_service.py     ← RAG retrieval
│   └── whatsapp.py        ← WhatsApp send functions (DO NOT MODIFY)
├── static/
│   └── js/dashboard.js    ← Frontend SPA (to be extended for Instagram)
├── templates/
│   └── dashboard.html     ← Single HTML file loading dashboard.js
├── utils/
│   ├── language.py        ← Language detection
│   └── tokens.py          ← Token estimation
├── .env                   ← Environment variables (see .env.example)
├── .env.example           ← Template for all env vars
└── requirements.txt
```

---

## Files — DO NOT MODIFY (WhatsApp System)

```
apps/webhook/                    ← HANDS OFF — WhatsApp webhook
services/whatsapp.py             ← HANDS OFF — WhatsApp send functions  
services/button_flow.py          ← HANDS OFF — WhatsApp button flow
services/journey_orchestrator.py ← HANDS OFF — Main AI pipeline
apps/automation/tasks.py         ← HANDS OFF — Celery tasks for WhatsApp
apps/conversations/models.py     ← READ ONLY — you can import, never alter
apps/clients/models.py           ← READ ONLY — you can import, never alter
config/settings.py               ← EXTEND ONLY — add new settings, never remove
config/urls.py                   ← EXTEND ONLY — add new paths, never remove
```

---

## Files — TO CREATE (New Instagram System)

```
apps/instagram/
├── __init__.py
├── apps.py
├── views.py          ← Instagram webhook receiver + message sender
├── urls.py           ← /api/instagram/ routes
├── models.py         ← InstagramConversation, InstagramMessage models
├── serializers.py    ← DRF serializers for dashboard
└── migrations/
    └── __init__.py

services/
└── instagram_service.py  ← Instagram Graph API: send text, image, audio

static/js/
└── instagram_dashboard.js  ← Instagram tab in dashboard (separate from WA)
```

---

## Files — TO EXTEND (Minimal, Safe)

```
config/settings.py     ← Add INSTAGRAM config block (append only)
config/urls.py         ← Add path("api/instagram/", ...) (append only)
apps/dashboard/views.py ← Add InstagramClientListView, InstagramMessagesView
static/js/dashboard.js ← Add Instagram tab (append JS only, never touch WA logic)
requirements.txt       ← Add any new packages needed
```

---

## Key Architectural Decision

Instagram and WhatsApp share:
- The same `Client` model (identified by wa_number for WA, ig_user_id for IG)
- The same `openai_service.py` for AI responses
- The same `media_service.py` for Supabase uploads
- The same `rag_service.py` for knowledge retrieval
- The same dashboard (new tab added)

Instagram and WhatsApp DO NOT share:
- Webhook receivers (separate apps)
- Message sending functions (separate service files)
- Button/interactive flows (Instagram has different interactive elements)
- Celery task names (use new task names for Instagram)

---

## Critical Differences: WhatsApp vs Instagram DM

### 1. User Identification
```
WhatsApp  : client identified by phone number  e.g. "250735851750"
Instagram : client identified by ig_user_id    e.g. "17841400000000000"
            (this is a numeric string, NOT a phone number)
```
The `Client` model needs a new optional field `ig_user_id` (CharField, null=True).
When a client messages on Instagram, look up by ig_user_id. If not found, create
a new Client with ig_user_id set and wa_number left empty or set to ig_user_id
prefixed with "ig_" to avoid conflicts.

### 2. Interactive Messages (Buttons)
```
WhatsApp  : send_buttons() with up to 3 buttons → renders as tappable buttons
Instagram : NO equivalent of WhatsApp interactive buttons
            Instagram supports "Quick Replies" but only in limited contexts
            Instagram supports Generic Templates (carousel) for some use cases
            
SOLUTION  : For Instagram, use text-based menu instead of buttons.
            Example: instead of 3 buttons, send:
            "Please reply with:
             1️⃣ Book a Session
             2️⃣ View Prices  
             3️⃣ Ask a Question"
            Then detect "1", "book", "session" etc. in the reply.
```

### 3. Templates / Outbound Messages
```
WhatsApp  : Requires pre-approved Meta templates for outbound (after 24h window)
Instagram : NO template system. You can message users who have messaged you
            within 7 days (not 24h like WhatsApp).
            After 7 days of inactivity → cannot send messages at all.
```

### 4. Media Support
```
WhatsApp  : image, audio, video, document, sticker, voice
Instagram : image, video (no audio-only, no documents, no stickers)
            Audio messages from users arrive as audio type but you cannot
            send audio back (only image and video outbound).
```

### 5. Message Window
```
WhatsApp  : 24-hour customer service window
Instagram : 7-day messaging window
            Standard messaging: within 7 days of last user message
            After 7 days: cannot send (no template fallback like WA)
```

### 6. Webhook Structure
```
WhatsApp webhook path  : /api/webhook/whatsapp/
Instagram webhook path : /api/instagram/webhook/
                         (same verify_token can be used, different endpoint)

WhatsApp webhook object field  : "whatsapp_business_account"
Instagram webhook object field : "instagram" 
                                  OR "page" with messaging field
```

### 7. Message Object Structure Differences
```python
# WhatsApp inbound message
{
  "from": "250735851750",
  "id": "wamid.xxx",
  "type": "text",
  "text": {"body": "Hello"},
  "timestamp": "1234567890"
}

# Instagram inbound message  
{
  "sender": {"id": "17841400000000000"},
  "recipient": {"id": "your_page_id"},
  "timestamp": 1234567890,
  "message": {
    "mid": "m_xxx",
    "text": "Hello"
  }
}
```

### 8. Sending Messages
```
WhatsApp : POST to graph.facebook.com/v20.0/{phone_number_id}/messages
Instagram: POST to graph.facebook.com/v20.0/me/messages
           with recipient: {"id": ig_user_id}
           (uses Page Access Token, not WhatsApp token)
```

---

## Instagram API Setup Requirements

The following environment variables need to be added to `.env`:

```bash
# Instagram Bot (NEW — add these, never remove WA vars)
IG_PAGE_ACCESS_TOKEN=    # Page Access Token from Meta (long-lived)
IG_APP_SECRET=           # App Secret for webhook signature verification  
IG_WEBHOOK_VERIFY_TOKEN= # Your chosen verify token string (can reuse WA one)
IG_PAGE_ID=              # Your Facebook Page ID linked to Instagram
IG_INSTAGRAM_ACCOUNT_ID= # Your Instagram Business Account ID
```

Add to `config/settings.py` (append, never replace):
```python
INSTAGRAM = {
    "PAGE_ACCESS_TOKEN": env("IG_PAGE_ACCESS_TOKEN", default=""),
    "APP_SECRET": env("IG_APP_SECRET", default=""),
    "WEBHOOK_VERIFY_TOKEN": env("IG_WEBHOOK_VERIFY_TOKEN", default=""),
    "PAGE_ID": env("IG_PAGE_ID", default=""),
    "INSTAGRAM_ACCOUNT_ID": env("IG_INSTAGRAM_ACCOUNT_ID", default=""),
    "BASE_URL": "https://graph.facebook.com/v20.0",
}
```

---

## Instagram Service (services/instagram_service.py)

Create this file. It mirrors whatsapp.py but for Instagram Graph API.

Key functions to implement:
```python
def send_text(to: str, message: str) -> dict
def send_image(to: str, image_url: str) -> dict  
def mark_as_seen(sender_id: str) -> dict
def get_user_profile(ig_user_id: str) -> dict  # get name from Instagram
```

DO NOT put any WhatsApp logic here. This file is Instagram-only.

---

## Instagram Webhook (apps/instagram/)

### views.py structure:
```python
class InstagramWebhookView(View):
    def get(self, request):
        # Webhook verification (same pattern as WhatsApp)
        
    def post(self, request):
        # Parse Instagram message format (different from WhatsApp)
        # Extract: sender_id, message_text, message_id, timestamp
        # Dispatch to Celery task: process_instagram_message
```

### Key parsing logic:
```python
# Instagram webhook payload structure:
# body["entry"][0]["messaging"][0] contains the message
# sender_id = entry["messaging"][0]["sender"]["id"]
# text = entry["messaging"][0]["message"]["text"]
# mid = entry["messaging"][0]["message"]["mid"]  ← message ID for dedup
```

### Celery task (add to apps/automation/tasks.py — APPEND ONLY):
```python
@shared_task(name="automation.process_instagram_message", ...)
def process_instagram_message(sender_id, message_text, message_id, timestamp):
    # Similar to process_inbound_message but for Instagram
    # Uses instagram_orchestrator (new file) not journey_orchestrator
```

---

## Instagram Orchestrator (services/instagram_orchestrator.py)

Create a NEW file. Do NOT modify journey_orchestrator.py.

This file handles the Instagram AI pipeline:
1. Look up or create Client by ig_user_id
2. Save inbound message  
3. Human takeover check
4. Call openai_service.build_system_prompt() — REUSE AS-IS
5. Call openai_service.call_openai() — REUSE AS-IS
6. Save outbound message
7. Send via instagram_service.send_text()

The text-based menu flow for Instagram goes here (no button_flow dependency).

---

## Client Model Extension

Add to `apps/clients/models.py` Client class (ONE new field only):
```python
ig_user_id = models.CharField(
    max_length=50, blank=True, default="",
    db_index=True,
    help_text="Instagram sender ID for DM bot"
)
```
Run: `python manage.py makemigrations clients && python manage.py migrate`

---

## Dashboard Extension

Add a new "Instagram" tab to the existing dashboard. The existing WhatsApp
tabs (Overview, Approvals, Clients, Bookings, Analytics) must remain 100% unchanged.

Add to `static/js/dashboard.js` (APPEND ONLY — never modify existing functions):
- `pageInstagram()` function — list Instagram conversations
- `openInstagramChat(igUserId, name)` — open Instagram chat modal
- New nav item: `{ id: "instagram", icon: "📷", label: "Instagram DM" }`
- New API calls: `fetchInstagramClients()`, `fetchInstagramMessages(igUserId)`

---

## URL Configuration

Append to `config/urls.py`:
```python
path("api/instagram/", include("apps.instagram.urls")),
```

In `apps/instagram/urls.py`:
```python
urlpatterns = [
    path("webhook/", InstagramWebhookView.as_view(), name="ig-webhook"),
    path("send/", InstagramSendView.as_view(), name="ig-send"),  
]
```

In `apps/dashboard/urls.py` (APPEND):
```python
path("instagram/clients/", InstagramClientListView.as_view()),
path("instagram/clients/<str:ig_user_id>/messages/", InstagramMessagesView.as_view()),
path("instagram/clients/<str:ig_user_id>/message/", InstagramManualMessageView.as_view()),
```

---

## Text-Based Flow for Instagram (replaces button_flow.py)

Since Instagram doesn't support WhatsApp-style buttons, create a text menu system.

```python
# In services/instagram_orchestrator.py

INSTAGRAM_WELCOME = """Hello! 😊 Welcome to *KP Kids Studio*.

Please reply with a number to continue:
1️⃣ Book a photoshoot session
2️⃣ View our packages and prices
3️⃣ Ask a question

Reply *1*, *2*, or *3* to get started!"""

def _detect_instagram_intent(text: str) -> str:
    """Map free text to intent for Instagram menu."""
    text = text.lower().strip()
    if any(x in text for x in ["1", "book", "session", "reserve", "kwifotoza"]):
        return "book"
    if any(x in text for x in ["2", "price", "cost", "how much", "ibiciro"]):
        return "prices"  
    if any(x in text for x in ["3", "question", "ask", "help", "info"]):
        return "question"
    return "unknown"
```

---

## Meta Developer Console Setup for Instagram

When you are ready to configure webhooks:

1. Go to developers.facebook.com → your app "Kigali Photography"
2. Add product: **Messenger** (Instagram uses Messenger API)
3. Under Messenger → Instagram settings → Connect Instagram account
4. Webhooks → Subscribe to: `messages`, `messaging_postbacks`
5. Webhook URL: `https://your-domain.koyeb.app/api/instagram/webhook/`
6. Verify token: value of `IG_WEBHOOK_VERIFY_TOKEN` in your .env

**Important:** The webhook for Instagram goes through the Messenger product,
NOT the WhatsApp product. They are completely separate in the Meta console.

---

## Git Branch Strategy

Before writing any code, Gemini must:

```bash
# 1. Ensure you are on main/master with all current work
git status  # must be clean
git pull origin main

# 2. Create the Instagram feature branch
git checkout -b feature/instagram-bot

# 3. All Instagram work goes on this branch
# WhatsApp production continues running on main

# 4. When Instagram is ready and tested:
git checkout main
git merge feature/instagram-bot --no-ff -m "feat: add Instagram DM bot"
git push origin main

# 5. Keep main as emergency fallback
# If Instagram causes any issue → git checkout main → redeploy
```

---

## Implementation Order (Step by Step)

Gemini must implement in this exact order:

```
STEP 1 — Branch
  git checkout -b feature/instagram-bot

STEP 2 — Client model extension
  Add ig_user_id field to Client
  makemigrations + migrate

STEP 3 — Instagram service  
  Create services/instagram_service.py
  Functions: send_text, send_image, mark_as_seen, get_user_profile

STEP 4 — Instagram app scaffold
  Create apps/instagram/ with all files
  Register in INSTALLED_APPS (settings.py — append only)

STEP 5 — Instagram webhook
  apps/instagram/views.py — webhook GET (verify) + POST (receive)
  apps/instagram/urls.py
  config/urls.py — append path

STEP 6 — Instagram orchestrator
  Create services/instagram_orchestrator.py
  Text-based menu flow
  Reuse openai_service as-is

STEP 7 — Celery task
  Append process_instagram_message to apps/automation/tasks.py

STEP 8 — Dashboard extension
  Append Instagram tab to static/js/dashboard.js
  Append Instagram views to apps/dashboard/views.py
  Append Instagram urls to apps/dashboard/urls.py

STEP 9 — README2.md
  Create testing guide (see below)

STEP 10 — Local test
  Follow README2.md

STEP 11 — Git commit
  git add .
  git commit -m "feat: Instagram DM bot — complete implementation"
```

---

## README2.md — What Gemini Must Generate

Gemini must create a file `README2.md` with the following sections:

### Section 1 — Local Development Setup
- How to run ngrok to expose localhost for Meta webhooks
- `ngrok http 8000` → copy the https URL
- Set IG_WEBHOOK_VERIFY_TOKEN in .env

### Section 2 — Meta Console Configuration (Test Account)
- How to create a test Instagram account
- How to link it to the Facebook Page in Business Manager
- How to configure Messenger webhook in developers.facebook.com
- Exact subscription fields needed: messages, messaging_postbacks
- How to get a temporary Page Access Token for testing
- How to send a test message and verify it hits the webhook

### Section 3 — Testing Locally
- Start Django: `python manage.py runserver`
- Start Celery: `celery -A config worker -l info`
- Start Celery Beat: `celery -A config beat -l info`
- Send a DM from test Instagram account
- Verify logs show message received
- Verify AI response is sent back
- Verify message appears in dashboard Instagram tab

### Section 4 — Moving to Production Instagram Account
- How to switch from test to real Instagram account
- Replace IG_PAGE_ACCESS_TOKEN with permanent token from System User
- Update IG_INSTAGRAM_ACCOUNT_ID  
- Test with studio's real Instagram account
- Verify existing WhatsApp still works (send a test WA message)

### Section 5 — Rollback Procedure
- If anything breaks: `git checkout main && git push origin main`
- Redeploy on Koyeb from main branch
- WhatsApp will be unaffected (it was never on the feature branch)

---

## What Gemini Must NOT Do

```
❌ Modify any file in apps/webhook/
❌ Modify services/whatsapp.py
❌ Modify services/button_flow.py
❌ Modify services/journey_orchestrator.py
❌ Modify apps/automation/tasks.py process_inbound_message task
❌ Remove or rename any existing URL patterns
❌ Change any existing Django model fields
❌ Modify existing dashboard.js functions (only append new ones)
❌ Change CELERY_BEAT_SCHEDULE existing entries
❌ Touch any WhatsApp-related environment variables
❌ Merge to main before local tests pass
```

---

## Reusable Services (Use As-Is, Import Only)

```python
# These work for Instagram too — import and call directly:
from services.openai_service import build_system_prompt, call_openai
from services.rag_service import retrieve_context
from services.media_service import upload_to_supabase, download_and_save_media
from services.client_service import record_tokens
from utils.language import detect_language
from utils.tokens import estimate_tokens
```

---

## .env.example Reference

See `.env.example` in the project root for all existing variables.
The following are already in use (DO NOT RENAME OR REMOVE):
```
SECRET_KEY, DATABASE_URL, REDIS_URL
WA_PHONE_NUMBER_ID, WA_ACCESS_TOKEN, WA_WEBHOOK_VERIFY_TOKEN, WA_APP_SECRET
OPENAI_API_KEY, OPENAI_MAX_INPUT_TOKENS, OPENAI_MAX_OUTPUT_TOKENS
SUPABASE_URL, SUPABASE_KEY, SITE_URL
EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, STUDIO_NOTIFICATION_EMAIL
STUDIO_NAME, STUDIO_WHATSAPP, STUDIO_LOCATION, STUDIO_HOURS, BOOKING_FEE_RWF
VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS_EMAIL
```

New variables to add (Instagram):
```
IG_PAGE_ACCESS_TOKEN
IG_APP_SECRET
IG_WEBHOOK_VERIFY_TOKEN
IG_PAGE_ID
IG_INSTAGRAM_ACCOUNT_ID
```

---

## Final Checklist Before Any Code

- [ ] Read this entire file
- [ ] Read .env.example
- [ ] Run `git status` — ensure clean working tree
- [ ] Run `git checkout -b feature/instagram-bot`
- [ ] Confirm you understand the Client model (apps/clients/models.py)
- [ ] Confirm you understand the Message model (apps/conversations/models.py)
- [ ] Confirm you will NOT touch WhatsApp files
- [ ] Confirm you will create README2.md

---

*This document was generated for Gemini AI to implement Instagram DM bot*
*for KP Kids Studio alongside the existing WhatsApp system.*
*Last updated: May 2026*
