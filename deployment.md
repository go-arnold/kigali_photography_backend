# Kigali Photography Bot — Deployment Guide

Complete guide to get the WhatsApp bot running end-to-end.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Local Environment Setup](#2-local-environment-setup)
3. [Database & First Run](#3-database--first-run)
4. [Meta / WhatsApp Setup](#4-meta--whatsapp-setup)
5. [ngrok — Webhook Tunnel](#5-ngrok--webhook-tunnel)
6. [Register Webhook with Meta](#6-register-webhook-with-meta)
7. [Start All Services](#7-start-all-services)
8. [First-Run Checklist](#8-first-run-checklist)
9. [Test Message Walkthrough](#9-test-message-walkthrough)
10. [Production Deployment](#10-production-deployment)
11. [Cost Monitoring](#11-cost-monitoring)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

### Accounts needed
| Service | Where | Purpose |
|---|---|---|
| Meta Developer Account | developers.facebook.com | WhatsApp Cloud API |
| Anthropic | console.anthropic.com | Claude API key |
| PostgreSQL 15+ | local or managed | Main database |
| Redis 7+ | local or managed | Celery broker + cache |
| ngrok | ngrok.com | Local webhook tunnel (dev only) |

### Software
```bash
python --version   # 3.12+
psql --version     # 15+
redis-server --version  # 7+
```

---

## 2. Local Environment Setup

### Clone and install
```bash
cd kigali_photo
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configure environment
```bash
cp .env.example .env
```

Open `.env` and fill in every value:

```env
# Django
SECRET_KEY=django-insecure-generate-a-long-random-string-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (create this DB first)
DATABASE_URL=postgres://kigali:yourpassword@localhost:5432/kigali_photo

# Redis
REDIS_URL=redis://localhost:6379/0

# Meta WhatsApp (filled after Step 4)
WA_PHONE_NUMBER_ID=your_phone_number_id
WA_ACCESS_TOKEN=your_temporary_or_permanent_access_token
WA_WEBHOOK_VERIFY_TOKEN=choose_any_random_string_eg_kigali2024secret
WA_APP_SECRET=your_app_secret_from_meta

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Cost controls (these defaults are conservative — adjust after testing)
CLAUDE_DEFAULT_MODEL=claude-haiku-3-5-20251001
CLAUDE_ESCALATION_MODEL=claude-sonnet-4-6
CLAUDE_MAX_INPUT_TOKENS=2000
CLAUDE_MAX_OUTPUT_TOKENS=500
CLAUDE_CONVERSATION_BUDGET=20000

# Studio info (shown in Claude's system prompt)
STUDIO_NAME=Kigali Photography
STUDIO_WHATSAPP=+250700000000
STUDIO_LOCATION=KG 123 Street, Kigali
STUDIO_HOURS=Mon-Sat 9AM-6PM
BOOKING_FEE_RWF=20000
```

### Create PostgreSQL database
```bash
psql -U postgres
CREATE DATABASE kigali_photo;
CREATE USER kigali WITH PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE kigali_photo TO kigali;
\q
```

---

## 3. Database & First Run

```bash
# Run migrations
python manage.py migrate

# Create admin superuser (for Django admin panel)
python manage.py createsuperuser

# Load knowledge base seed data + index it
python manage.py index_knowledge_base --seed

# Verify indexing worked
python manage.py shell -c "
from apps.rag.models import KnowledgeDocument, KnowledgeChunk
print(f'Documents: {KnowledgeDocument.objects.count()}')
print(f'Chunks: {KnowledgeChunk.objects.count()}')
"
# Expected: Documents: 15+, Chunks: 40+

# Collect static files (admin panel)
python manage.py collectstatic --noinput
```

---

## 4. Meta / WhatsApp Setup

### 4.1 Create Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **My Apps → Create App**
3. Select **Business** type
4. Name: `Kigali Photography Bot`
5. Under **Add Products**, find **WhatsApp** → click **Set Up**

### 4.2 Get Your Credentials

In your app dashboard → **WhatsApp → API Setup**:

| Value | Where to find it | .env variable |
|---|---|---|
| Phone Number ID | Under "From" phone number | `WA_PHONE_NUMBER_ID` |
| Temporary Token | "Temporary access token" box | `WA_ACCESS_TOKEN` |
| App Secret | App Settings → Basic → App Secret | `WA_APP_SECRET` |

> **Note:** The temporary token expires in 24 hours. For production, create a permanent System User token (see Section 10).

### 4.3 Add Your Test Phone Number

In **WhatsApp → API Setup → To** field:
- Click **Manage phone number list**
- Add your personal WhatsApp number
- You'll receive a verification code via WhatsApp

---

## 5. ngrok — Webhook Tunnel

Meta requires a public HTTPS URL to send webhook events. ngrok creates a secure tunnel to your local machine.

### Install ngrok
```bash
# macOS
brew install ngrok

# Linux
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Or download from ngrok.com/download
```

### Start tunnel
```bash
# Terminal 1: Start Django
python manage.py runserver 8000

# Terminal 2: Start ngrok tunnel
ngrok http 8000
```

ngrok will show output like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

**Copy your ngrok HTTPS URL** — you'll need it in Step 6.

> ⚠️ Free ngrok URLs change every time you restart ngrok.
> For stable dev testing, use a paid ngrok account with a fixed subdomain.

---

## 6. Register Webhook with Meta

### 6.1 Configure Webhook URL

In Meta dashboard → **WhatsApp → Configuration → Webhook**:

- **Callback URL:** `https://YOUR_NGROK_URL/api/webhook/whatsapp/`
- **Verify Token:** The exact value of `WA_WEBHOOK_VERIFY_TOKEN` in your `.env`

Click **Verify and Save**.

What happens:
1. Meta sends a GET request to your URL with `hub.challenge`
2. Django verifies the token matches `WA_WEBHOOK_VERIFY_TOKEN`
3. Returns the challenge value → Meta confirms the webhook

You should see ✅ in the Meta dashboard.

### 6.2 Subscribe to Events

Under **Webhook Fields**, enable:
- ✅ `messages` — inbound messages from clients
- ✅ `message_status` — delivery/read receipts

Click **Save**.

### 6.3 Verify Webhook is Receiving

Check Django logs — you should see:
```
[INFO] WhatsApp webhook verified successfully
```

---

## 7. Start All Services

You need 4 processes running simultaneously:

```bash
# Terminal 1: Django development server
python manage.py runserver 8000

# Terminal 2: Celery worker (processes messages async)
celery -A config worker -l info

# Terminal 3: Celery beat (scheduled tasks: birthday wishes, follow-ups)
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

# Terminal 4: ngrok tunnel
ngrok http 8000
```

### Docker Compose (recommended for dev)
```bash
# Starts everything: db, redis, web, celery, celery-beat
docker-compose up

# First time only — run migrations and seed inside container
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
docker-compose exec web python manage.py index_knowledge_base --seed
```

---

## 8. First-Run Checklist

Run through every item before sending the first test message:

### Environment
- [ ] `.env` file exists with all values filled
- [ ] No placeholder values remaining (no `your-secret-key-here`)
- [ ] `SECRET_KEY` is a long random string

### Database
- [ ] `python manage.py migrate` ran without errors
- [ ] Superuser created (`python manage.py createsuperuser`)
- [ ] Knowledge base seeded (`python manage.py index_knowledge_base --seed`)
- [ ] Admin panel accessible at `http://localhost:8000/admin/`

### WhatsApp
- [ ] Phone Number ID set in `.env`
- [ ] Access Token set in `.env` (not expired — temporary tokens last 24h)
- [ ] App Secret set in `.env`
- [ ] Your personal number added to Meta test recipients
- [ ] Webhook URL registered and verified (✅ in Meta dashboard)
- [ ] `messages` and `message_status` webhook fields enabled

### Services
- [ ] Django running on port 8000
- [ ] Celery worker running (check for `[celery@...] ready.` in logs)
- [ ] Celery Beat running
- [ ] ngrok tunnel active (HTTPS URL showing)
- [ ] ngrok URL matches the webhook URL registered in Meta

### Verify Celery Beat Schedules
```bash
python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
print('Beat tasks:', PeriodicTask.objects.count())
for t in PeriodicTask.objects.all():
    print(f'  - {t.name}: {t.enabled}')
"
```

---

## 9. Test Message Walkthrough

Send these messages from your personal WhatsApp to the studio number, watching logs in real time.

### Test 1: Basic inbound → response
```
You send:  "Hello, I'm interested in booking a session"
Expected:  Warm greeting + asks child name/age
Check:     Django logs show "Pipeline result | action=sent"
           Message appears in Django admin under Messages
```

### Test 2: Kinyarwanda detection
```
You send:  "Muraho, ndashaka gufotorwa"
Expected:  Response in Kinyarwanda
Check:     Client.language updated to 'rw' in admin
```

### Test 3: Price inquiry → heat update
```
You send:  "What are your packages? How much do they cost?"
Expected:  Package presentation response
Check:     HeatEvent created (question detected)
           JourneyState.phase may advance to 'booking'
```

### Test 4: Objection → Sales Resistance
```
You send:  "That's too expensive for me"
Expected:  Value reinforcement response (not a discount)
Check:     JourneyState.phase = 'sales_resistance'
           JourneyState.detected_objection = 'price'
           Possible ApprovalQueue item created
```

### Test 5: Opt-out
```
You send:  "STOP"
Expected:  Opt-out confirmation message
Check:     Client.is_opted_out = True in admin
           Subsequent messages ignored
```

### Test 6: Dashboard approval
```
1. Trigger an approval by sending a price objection message
2. Go to http://localhost:8000/api/dashboard/approvals/
   (or use curl: curl -u admin:pass http://localhost:8000/api/dashboard/approvals/)
3. Find the pending item
4. POST to /api/dashboard/approvals/{id}/approve/
   with {"notes": "Looks good", "send_immediately": true}
5. Check your WhatsApp — message should arrive
```

### Monitoring during tests
```bash
# Watch Django logs
tail -f logs/django.log   # if file logging configured
# Or just watch the runserver terminal

# Watch Celery logs
# The celery worker terminal shows all task processing

# Check DB in real time
python manage.py shell -c "
from apps.clients.models import Client
from apps.conversations.models import Message, ApprovalQueue
c = Client.objects.last()
print('Client:', c)
print('Messages:', c.messages.count())
print('Journey:', c.journey_state.phase, c.journey_state.heat_label)
print('Pending approvals:', ApprovalQueue.objects.filter(status='pending').count())
"
```

---

## 10. Production Deployment

### 10.1 Switch to Permanent Token

Temporary tokens expire in 24 hours. For production:

1. Meta Business Suite → **System Users** → Create System User
2. Grant WhatsApp permissions: `whatsapp_business_messaging`, `whatsapp_business_management`
3. Generate token → copy to `WA_ACCESS_TOKEN` in production env

### 10.2 Environment Changes for Production

```env
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgres://user:pass@your-db-host:5432/kigali_photo
REDIS_URL=redis://your-redis-host:6379/0
```

Update `config/settings/production.py` CORS settings:
```python
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
]
```

### 10.3 Recommended Stack

```
Internet → Nginx (reverse proxy + SSL) → Gunicorn → Django
                                       → Celery workers (2-4)
                                       → Celery Beat (1)
PostgreSQL (managed: RDS, Supabase, or Railway)
Redis (managed: Upstash, Railway, or ElastiCache)
```

### 10.4 Deploy Checklist
```bash
# On server
export DJANGO_SETTINGS_MODULE=config.settings.production

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py index_knowledge_base --seed
python manage.py createsuperuser

# Start Gunicorn
gunicorn config.wsgi:application --workers 4 --bind 0.0.0.0:8000

# Start Celery
celery -A config worker -l warning --concurrency 2
celery -A config beat -l warning
```

### 10.5 Replace ngrok with Real Domain

In Meta Dashboard → WhatsApp → Configuration:
- Update Callback URL to: `https://yourdomain.com/api/webhook/whatsapp/`
- Re-verify the webhook

---

## 11. Cost Monitoring

### Claude API costs (approximate)

| Model | Input | Output | Typical turn |
|---|---|---|---|
| Haiku 3.5 | $0.80/M tokens | $4.00/M tokens | ~$0.0003 |
| Sonnet 4.6 | $3.00/M tokens | $15.00/M tokens | ~$0.003 |

With default settings (2000 input, 500 output per turn):
- **Haiku turn:** ~$0.0016 + $0.002 = **~$0.0036 per message**
- **Sonnet turn:** ~$0.006 + $0.0075 = **~$0.014 per message** (only for escalated sales resistance)

### Monitor spend
```bash
# Total tokens used
python manage.py shell -c "
from django.db.models import Sum
from apps.conversations.models import Conversation
from apps.clients.models import Client

total = Conversation.objects.aggregate(t=Sum('tokens_used'))['t'] or 0
haiku_cost = (total * 0.6 / 1e6 * 0.80) + (total * 0.4 / 1e6 * 4.0)
print(f'Total tokens: {total:,}')
print(f'Estimated cost: \${haiku_cost:.4f}')
print(f'Conversations over budget: {Conversation.objects.filter(tokens_used__gte=20000).count()}')
"

# Top token consumers
python manage.py shell -c "
from apps.clients.models import Client
for c in Client.objects.order_by('-lifetime_tokens_used')[:5]:
    print(f'{c.name or c.wa_number}: {c.lifetime_tokens_used:,} tokens')
"
```

### Cost controls
All configurable in `.env` without code changes:
```env
CLAUDE_MAX_INPUT_TOKENS=2000     # Hard cap per turn
CLAUDE_MAX_OUTPUT_TOKENS=500     # Hard cap per turn
CLAUDE_CONVERSATION_BUDGET=20000 # Triggers human takeover
```

---

## 12. Troubleshooting

### Webhook not receiving messages
```bash
# Check 1: ngrok tunnel running?
curl https://YOUR_NGROK_URL/api/webhook/whatsapp/?hub.mode=subscribe&hub.challenge=test&hub.verify_token=YOUR_TOKEN
# Expected: returns "test" as body

# Check 2: Meta webhook verified?
# Look for green checkmark in Meta dashboard

# Check 3: Django receiving requests?
# Check runserver terminal for incoming GET/POST logs
```

### Messages received but no response
```bash
# Check 1: Celery worker running?
celery -A config inspect active

# Check 2: Any task errors?
# Check celery worker terminal for exceptions

# Check 3: Redis connected?
python manage.py shell -c "from django.core.cache import cache; cache.set('test', 1); print(cache.get('test'))"
# Expected: 1
```

### Claude not responding / fallback message sent
```bash
# Check Anthropic API key
python manage.py shell -c "
import anthropic
from django.conf import settings
c = anthropic.Anthropic(api_key=settings.CLAUDE['API_KEY'])
r = c.messages.create(model='claude-haiku-3-5-20251001', max_tokens=50, messages=[{'role':'user','content':'Hi'}])
print('API OK:', r.content[0].text)
"
```

### Human takeover not releasing
```bash
python manage.py shell -c "
from apps.clients.models import Client, JourneyState
c = Client.objects.get(wa_number='+250700000000')
j = c.journey_state
j.human_takeover = False
j.save()
print('Released')
"
# Or use: POST /api/dashboard/clients/{id}/takeover/ with {"enable": false}
```

### Knowledge base returning empty context
```bash
python manage.py shell -c "
from apps.rag.models import KnowledgeDocument, KnowledgeChunk
print('Docs:', KnowledgeDocument.objects.filter(is_active=True).count())
print('Chunks:', KnowledgeChunk.objects.count())
"
# If 0: run python manage.py index_knowledge_base --seed
```

### Duplicate messages being processed
```bash
# This is handled — check Redis cache keys
python manage.py shell -c "
from django.core.cache import cache
# Idempotency keys are stored as 'idempotency:{message_id}'
# Processing locks as 'processing_lock:{message_id}'
print('Cache OK' if cache.get('nonexistent') is None else 'Cache issue')
"
```

### Birthday messages not sending
```bash
# Check Celery Beat is running with correct scheduler
# Check PeriodicTask exists in DB
python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
for t in PeriodicTask.objects.all():
    print(t.name, '- enabled:', t.enabled, '- last run:', t.last_run_at)
"
```

---

## Quick Reference

| URL | Purpose |
|---|---|
| `/admin/` | Django admin — manage everything |
| `/api/webhook/whatsapp/` | Meta webhook endpoint |
| `/api/dashboard/stats/` | Token spend & queue overview |
| `/api/dashboard/approvals/` | Pending AI suggestions |
| `/api/dashboard/clients/` | All clients with journey context |
| `/api/dashboard/scheduled/` | Upcoming birthday/follow-up messages |

| Command | Purpose |
|---|---|
| `python manage.py migrate` | Apply DB migrations |
| `python manage.py index_knowledge_base --seed` | Load + index knowledge base |
| `python manage.py index_knowledge_base --force` | Reindex all documents |
| `celery -A config worker -l info` | Start async task worker |
| `celery -A config beat -l info` | Start scheduled task runner |

---

*Built for Kigali Photography. WhatsApp → Django → Claude → WhatsApp.*