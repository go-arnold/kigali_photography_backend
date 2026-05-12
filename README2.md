# KP Kids Studio — Instagram DM Bot Testing & Deployment Guide

This guide covers how to test the new Instagram DM bot locally and move it to production.

---

## Section 1 — Local Development Setup

To receive webhooks from Meta on your local machine, you must expose your local server to the internet.

1. **Install ngrok:** (if you don't have it)
   `npm install -g ngrok`
2. **Expose port 8000:**
   `ngrok http 8000`
3. **Copy the HTTPS URL:**
   Example: `https://abcd-123-456.ngrok-free.app`
4. **Update .env:**
   Set `IG_WEBHOOK_VERIFY_TOKEN` to a secret string of your choice.
   (Optional) Update `ALLOWED_HOSTS` in `config/settings/base.py` if needed, but usually not required for local testing with ngrok.

---

## Section 2 — Meta Console Configuration (Test Account)

1. **Meta Developer App:**
   - Go to [developers.facebook.com](https://developers.facebook.com) -> your app "Kigali Photography".
2. **Add Messenger Product:**
   - Instagram messaging is handled through the Messenger product.
   - Go to **Messenger** -> **Instagram Settings**.
3. **Link Instagram Account:**
   - Connect your test Instagram Professional account to a Facebook Page.
   - Link that Facebook Page in the Meta App settings.
4. **Configure Webhooks:**
   - Callback URL: `https://your-ngrok-url.ngrok-free.app/api/instagram/webhook/`
   - Verify Token: The value you set in `IG_WEBHOOK_VERIFY_TOKEN`.
   - **Fields to subscribe:** `messages`, `messaging_postbacks`.
5. **Access Token:**
   - Generate a Page Access Token for the linked Facebook Page.
   - Add it to your `.env` as `IG_PAGE_ACCESS_TOKEN`.

---

## Section 3 — Testing Locally

1. **Start Services:**
   - Django: `.\env\Scripts\python.exe manage.py runserver`
   - Redis: (Ensure Redis is running)
   - Celery Worker: `.\env\Scripts\python.exe -m celery -A config worker -l info`
2. **Send a DM:**
   - Send a message from a personal Instagram account to your test Instagram Professional account.
3. **Verify Pipeline:**
   - Check Django logs for webhook receipt.
   - Check Celery logs for `automation.process_instagram_message` execution.
   - Verify that an AI response is sent back to Instagram.
4. **Dashboard Check:**
   - Open the dashboard, go to the **Instagram DM** tab.
   - Verify the conversation and messages appear there.

---

## Section 4 — Moving to Production

1. **Permanent Token:**
   - In the Meta Developer console, use a **System User** to generate a permanent Page Access Token.
2. **Update Environment Variables:**
   - Set `IG_PAGE_ACCESS_TOKEN`, `IG_APP_SECRET`, `IG_PAGE_ID`, and `IG_INSTAGRAM_ACCOUNT_ID` in your production environment (e.g., Koyeb).
3. **Final Test:**
   - Send a DM to the studio's real Instagram account.
   - **CRITICAL:** Send a test WhatsApp message to ensure the production WhatsApp system is still 100% functional.

---

## Section 5 — Rollback Procedure

If any issue is detected with the existing WhatsApp system or the new Instagram bot:

1. **Revert to main:**
   `git checkout main`
2. **Redeploy:**
   `git push origin main` (or trigger manual redeploy on Koyeb)
3. **Confirmation:**
   Since the Instagram bot was developed on a separate branch and never touched WhatsApp files, reverting to `main` immediately restores the known-good state.
