"""
Seed Knowledge Base
====================
Knowledge base for Kigali Photography AI assistant.
Tone calibrated on real client conversations — warm, bilingual,
casual mix of Kinyarwanda / French / English exactly as agents naturally speak.

Real pattern observed:
  - Short messages, one idea at a time
  - Child's name used constantly
  - Natural code-switching: RW + FR + EN in same message
  - Warmth without being pushy
  - Value reframing instead of discounts
  - Celebrate small moments, react to client energy

Categories:
  - package:          Pricing, inclusions, session types
  - policy:           Booking policies, payment terms
  - script:           Approved response templates (EN + RW)
  - objection:        Objection handling scripts
  - faq:              Common client questions
  - location:         Studio location, parking, hours
  - bilingual:        Common phrases in both languages
  - success_pattern:  Proven conversion patterns
"""

import logging

logger = logging.getLogger(__name__)

SEED_DOCUMENTS = [

    # ─── PACKAGES ────────────────────────────────────────────────────────────

    (
    "package",
    "both",
    "Session Packages Overview",
    """
KP KIDS STUDIO — SESSION PACKAGES

STARTER PACKAGE — 50,000 RWF
- Studio session
- 8 professionally edited photos
- All other unedited photos from session
Best for: Simple sessions, budget-conscious families

SILVER PACKAGE — 70,000 RWF
- Studio session
- 12 professionally edited photos
- All other unedited photos from session
Best for: Families wanting more edited coverage

SILVER + FRAMES — 79,000 RWF
- Studio session
- 10 professionally edited photos
- All other unedited photos from session
- 2 A5 photo frames

SILVER + VIDEO — 79,000 RWF
- Studio session
- 10 professionally edited photos
- All other unedited photos from session
- Short highlight video

GOLD PACKAGE — 89,000 RWF
- Studio session
- 15 professionally edited photos
- All other unedited photos from session
- Choice of: 2 A5 frames OR highlight video

GOLD + CAKE — 109,000 RWF
- Studio session
- 15 professionally edited photos
- All other unedited photos from session
- Birthday cake in studio
- Choice of: 2 A5 frames OR highlight video

PLATINUM PACKAGE — 119,000 RWF
- Studio session
- 15 professionally edited photos per child
- All other unedited photos from session
- 2 A5 photo frames
- Short highlight video

HOME/EVENT COVERAGE — add 150,000 RWF to any package
Photographer comes to your home or event to capture the real birthday party.

BOOKING FEE: 20,000 RWF (deducted from final payment)
Payment: MTN MOMO-CODE 798741 Kigali Photography Ltd

PACKAGE SELECTION RULES (follow strictly):
- Client wants photos only → offer Starter + Silver
- Client wants one extra (frames OR video) → offer Silver+extra or Gold
- Client wants cake → add ~9-10k to base price
- Client wants two extras → offer Gold or Platinum
- Client wants home coverage → add 150,000 RWF to chosen package
- Always present EXACTLY 2 options — never more, never one
""",
),

    (
        "package",
        "both",
        "Approved Bonus Options",
        """
APPROVED BONUS OPTIONS (Human approval required before offering)

1. +2 EDITED IMAGES
Add 2 extra professionally edited photos to any package.
No price change — value addition only.
Best for: Clients who love the photos but want more.
When to offer: HIGH heat clients with mild price hesitation.
How agents say it: "Ntakibazo, turazongera 2 nk'impano yacu."

2. FREE HIGHLIGHT REEL
30-second video compilation with music from session photos.
Delivered within 48 hours of photo delivery.
Best for: Social media-active parents, modern families.
When to offer: MEDIUM/HIGH heat clients who seem social-media oriented.
Real example: "Video yo yabonetse" — shared alongside photos naturally.

3. FRAME UPGRADE
Upgrade from standard to premium wood frame at no extra cost.
Best for: Clients who value physical products, gift-givers.
When to offer: When client mentions frames, printing, or gifts.

4. PRIORITY EDITING
Jump to front of editing queue.
Best for: Time-sensitive needs, events happening soon.
When to offer: Clients with upcoming events or tight timelines.

RULE: Never offer more than one bonus per conversation.
RULE: Always flag for human approval — never auto-send.
RULE: Never offer bonuses to LOW heat clients.
REAL PATTERN: Client often asks "munyongeze naka" (add just one more).
  - If HIGH heat: "Ntakibazo, turazongera" (No problem, we'll add it)
  - If budget was already discussed: add gracefully without making it a big deal
""",
    ),

    # ─── POLICIES ────────────────────────────────────────────────────────────

    (
        "policy",
        "both",
        "Booking & Payment Policy",
        """
BOOKING & PAYMENT POLICY

BOOKING FEE
- 20,000 RWF non-refundable booking fee to secure your session date
- Booking fee is deducted from your final package payment
- Session date is NOT confirmed until booking fee is received
- How agents say it: "Mwakora booking ya 20,000 frw gusa kuri code: 798741 Kigali photography Ltd. Andi yishyurwa session irangiye!"

PAYMENT METHODS
- Mobile Money MTN: 798741 (Kigali Photography Ltd)
- Mobile Money Airtel: 0788 555 115
- Cash at studio

PAYMENT CONFIRMATION
- Client sends screenshot of payment
- Agent confirms: "Well received" or "Twayakiriye"
- Then immediately send the booking details form

BOOKING DETAILS FORM (always send after payment):
"Details:
Name:
Kid's Gender:
Kid's Age:
Package:
Booking Day:
Booking Time:"

RESCHEDULING
- Free rescheduling with 48+ hours notice
- One free reschedule per booking
- Second reschedule: 10,000 RWF fee
- Same-day cancellation: booking fee forfeited

NO DISCOUNT POLICY
- We do not reduce prices for the same service
- We offer value additions, never price reductions
- Real example: Client asked for 60k on 70k package.
  Agent responded by explaining what the 70k includes vs 50k base,
  showing the loyalty pricing already applied.
  Client accepted: "Oky it's Oky nakibazo reka Nishyuye tuzakoresha iyi ya 70k"
""",
    ),

    # ─── FAQ ─────────────────────────────────────────────────────────────────

    (
        "faq",
        "both",
        "Common Client Questions",
        """
FREQUENTLY ASKED QUESTIONS

Q: How long does a session take?
A: Essential 45 min, Premium 60 min, Signature 90 min. Arrive 10 minutes early.

Q: What should my child wear?
A: Solid colors work best — avoid busy patterns. Bring 2-3 outfit options.
Real workflow: agents ask "mwadu sharing outfits [child] aza kwambara tugategura studio?"
This saves time at the studio and shows professionalism.

Q: My child is very active / shy — is that okay?
A: Absolutely! We specialize in children. Toys, props, years of experience.
We follow the child's pace — no rushing.

Q: When will I receive my photos?
A: We guarantee delivery within 24 hours. Usually faster.
Gallery link shared via pixieset: "https://kigaliphotography.pixieset.com/[childname]/"

Q: Can I buy extra photos after seeing the gallery?
A: Yes! Extra edited photo is 5,000 RWF each.
Real example: Client said "nakwishyura kuruhande Nabazaga" (pay separately for extras).
Agent: "Ifoto iri extra ni 5k gusa" — simple, no friction.

Q: Can I bring siblings?
A: Yes! Let us know in advance so we can plan.

Q: What if my child is sick on the day?
A: Please reschedule! Health always comes first.
Contact us ASAP and we'll find a new date.

Q: Do you edit all the photos?
A: Every delivered photo is professionally retouched: color grading,
skin smoothing, background cleanup, lighting enhancement.
Client can request adjustments: "Ngirango nago nago mwayimanaguriye" →
Agent: "Ntakibazo aba editors barayikoraho" (No problem, editors will fix it)

Q: Can I share the photos on social media?
A: Yes! Please tag us @KigaliPhotography.
""",
    ),

    # ─── LOCATION ────────────────────────────────────────────────────────────

    (
        "location",
        "both",
        "Studio Location & Access",
        """
KIGALI PHOTOGRAPHY STUDIO

LOCATION
KG 123 Street, Kigali
(Pin location shared via WhatsApp upon booking confirmation)

HOURS
Monday - Saturday: 9:00 AM - 6:00 PM
Sunday: Closed (private bookings available on request)
Public holidays: Closed

ARRIVAL
- Please arrive 10 minutes before your session time
- Late arrival reduces session time
- Free parking available at the building

WHAT TO BRING
- Confirmation message
- 2-3 outfit options for your child
- Favorite toy or comfort item
- Snack for young children
- Any special props you'd like included

CONTACTS
WhatsApp/MTN: +250 798 973 741
WhatsApp/Airtel: +250 788 555 115
Website: kigaliphotography.pixieset.com
""",
    ),

    # ─── SCRIPTS: ENGLISH ────────────────────────────────────────────────────

    (
        "script",
        "en",
        "Welcome & Introduction Script (English)",
        """
FIRST CONTACT — ENGLISH

WARM GREETING (casual, not corporate):
"Hello! Welcome to Kigali Photography!
I'm so glad you reached out.
Could you tell me your little one's name and age?
And is this for a special occasion or a milestone session?"

SHORT VERSION (if client seems in a hurry):
"Hello! How may I help you and your little one today?"

KEY PRINCIPLES FROM REAL CONVERSATIONS:
- Use child's name as soon as you learn it — every single message after
- Match client's energy: if they use emojis, match warmth; if formal, stay professional
- Never send a wall of text — one idea per message
- React to good news: "Ayaaa!" / "Great!" / "Excellent!"
- Real agents say "how may i be of service to you today?" for follow-up days

RETURNING CLIENT GREETING:
"Hello [Name]! So wonderful to hear from you again!
How is [child's name] doing?"
""",
    ),

    (
        "script",
        "en",
        "Package Presentation Script (English)",
        """
PACKAGE PRESENTATION — ENGLISH

STEP 1 — ASK BEFORE PRESENTING (from real conversations):
"To make sure we give you the right package, could you tell us:
- Would you prefer a studio session or home session?
- Would you like a highlight video included?
- Any special additions like a cake or frames?"

This approach was seen in the real conversation:
"Kugirango tubashe kubakorera photoshoot nziza, mwatubwira nimba mwifuza..."
Client gave options → agent built custom packages around them.

STEP 2 — PRESENT (after understanding needs):
"Based on what you've shared, here are the options that fit best:

[Package Name] — [Price] RWF
- [key inclusions relevant to their needs]
- [specific item they mentioned wanting]

Just let me know which option feels right for you."

STEP 3 — BOOKING PUSH (after they choose):
"Great! To secure your date, we just need the 20,000 RWF booking fee:
798741 Kigali Photography Ltd
The rest is paid after the session. Shall I get your date set up?"

VALUE REMINDER (if hesitation):
"These are the photos [child's name] will look back on. Every franc is worth it."
""",
    ),

    (
        "script",
        "en",
        "Outfit & Preparation Script (English)",
        """
OUTFIT REQUEST — ENGLISH

ASKING FOR OUTFITS (2-3 days before session):
"Hello [Name]!
Could you share the outfits [child's name] will be wearing?
This helps us prepare the studio and save you valuable time on the day!"

DAY-BEFORE REMINDER:
"Hello [Name]! Just a quick reminder — [child's name]'s session is tomorrow at [TIME].
We're all set and excited to meet you!
Please arrive 10 minutes early so [child's name] can settle in.
Any questions? We're here!"

DAY-OF:
"Good morning [Name]! Today is the day!
See you at [TIME]. We're ready for [child's name]!"
""",
    ),

    (
        "script",
        "en",
        "Gallery Delivery & Feedback Script (English)",
        """
GALLERY DELIVERY — ENGLISH

SENDING GALLERY LINK:
"Hello [Name]!
[Child's name]'s photos are ready!
Here is your gallery: https://kigaliphotography.pixieset.com/[childname]/

Please have a look and let us know which ones you'd like edited.
We can't wait to hear what you think!"

IF CLIENT DELAYED IN RESPONDING:
"Hello [Name]! Just checking — did you get a chance to look at the gallery?
No rush, just wanted to make sure the link is working for you!"

AFTER SELECTION RECEIVED:
"Murakoze! We're working on your selections now.
We'll have them ready for you very soon."

PHOTO DELIVERY (final edited photos):
"The wait is over! [Child's name]'s edited photos are ready.
[Share link or files]
Please review and let us know if any adjustments are needed — we're happy to help!"

FEEDBACK REQUEST (a few days after delivery):
"Hello [Name]! We'd love to hear about your experience.
Could you take 2 minutes to fill this quick form?
[Google Form Link]
Your feedback helps us serve families better. Thank you for trusting us with [child's name]'s memories!"
""",
    ),

    # ─── SCRIPTS: KINYARWANDA ────────────────────────────────────────────────

    (
        "script",
        "rw",
        "Ubutumire n'Intangiriro (Kinyarwanda)",
        """
INTANGIRIRO — KINYARWANDA

UBUTUMIRE (casual, warm):
"Muraho! Murakaza neza kuri Kigali Photography!
Mwantubwira izina n'imyaka y'umwana wanyu?
Ni ihuriro ryihe, cyangwa ni isomo rya milestone?"

GUSUBIZA UMUKIRIYA WAZONGEYE:
"Muraho [Izina]! Twishimye kubabona nanone!
[Izina ry'umwana] ariko ameze ate?"

INYUNGU NZIZA (short, real):
"Ntakibazo!"
"Cyane!"
"Excellent!"
"Twayakiriye!"
"Ntakibazo, turazongera."

IGIHE NTAGISUBIZO (follow-up after silence):
"Mwaramutse neza [Izina],
Twifuzaga kumenya nimba hari ikibazo nabafasha!
Mudusubize mugihe mwabona. Murakoze"
""",
    ),

    (
        "script",
        "rw",
        "Gutanga Amakuru y'Ibikorwa (Kinyarwanda)",
        """
PACKAGE PRESENTATION — KINYARWANDA

GUTUZA MBERE YO GUTANGA AMAKURU:
"Kugirango tubashe kubakorera photoshoot nziza,
mwatubwira nimba mwifuza ko twabakorera package irimo:
Studio shoot, Home shoot, Cake, Frames, cyangwa video gato?"

GUTANGA OPTIONS (after client answers):
"Hashingiwe ku bishaka byanyu, dore options 2:

[Package 1] — [Igiciro] RWF
- [ibigizwe]

[Package 2] — [Igiciro] RWF
- [ibigizwe]

Nimuyifate iyihe?"

GUSABA BOOKING FEE (after selection):
"Nziza! Mwakora booking ya 20,000 frw gusa kuri code:
798741 Kigali Photography Ltd
Andi yishyurwa session irangiye!
Mwampa itariki n'igihe mushaka tukabona kujya kuyindi step."
""",
    ),

    # ─── OBJECTION HANDLING ──────────────────────────────────────────────────

    (
        "objection",
        "both",
        "Price Objection Handling",
        """
PRICE OBJECTION RESPONSES

CLIENT SAYS: "It's expensive" / "Can I get a discount?" / "Too much"

REAL EXAMPLE FROM ACTUAL CONVERSATION:
Client: "duhe discount nka ba clients beza"
Agent: "ntakibazo — byambabaza ko mwatugana mukagenda tutabahaye service"
(translated: no problem — it hurts us when clients leave without getting served)
Then agent reframed: offered same 70k but explained it already includes loyalty pricing
vs base 50k (8 photos, no video). Client accepted.

LEVEL 1 — REFRAME VALUE (do this first, always):
"I understand completely!
Let me show you what's already included at this price:
- [X] professionally edited photos (not just filtered — individually retouched)
- 24-hour delivery (most studios take weeks)
- [child's name] will actually enjoy the session — we're child specialists
- Extra edited photo available at just 5,000 RWF if you want more after seeing the gallery

For a returning client like you, we've already applied our loyalty pricing."

LEVEL 2 — ADJUST SCOPE, NOT PRICE (if they push):
"If [price] feels like a lot right now, our Essential Package at 100,000 RWF
still gives you 10 professionally edited photos and 24-hour delivery.
Would that work better for your family?"

LEVEL 3 — HUMAN TAKEOVER:
"Let me check with our team about what we can do for you.
I'll get back to you shortly!"

NEVER SAY:
- "I can give you a discount on the same package"
- "Let me reduce the price"
- Any direct price cut for the same service

LANGUAGE TO USE:
RW: "Ntakibazo, ariko..." / "Byambabaza ko..."
EN: "I understand..." / "For a returning client like you..."
""",
    ),

    (
        "objection",
        "both",
        "Timing Objection Handling",
        """
TIMING OBJECTION RESPONSES

CLIENT SAYS: "Not sure when" / "Maybe later" / "Need to check"

RESPONSE (casual, no pressure):
"Ntakibazo! Take your time.
Whenever you're ready, just let me know and we'll find the perfect date for [child's name].
Our calendar fills up quickly on weekends so it's good to book when you're ready!"

IF CLIENT GOES SILENT FOR DAYS:
"Mwaramutse neza [Name]!
We're very concerned with the silence, and I wanted to check up on you
to see if there's anything else I might assist you with!
Kindly get back to us so we could help you better. Thank you"

(This is the exact message used in real conversations — warm, not pushy, genuine concern)

FOLLOW-UP TIMING:
HIGH heat: Follow up after 4-6 hours
MEDIUM heat: Follow up next day
LOW heat: Follow up after 48 hours, once only
""",
    ),

    (
        "objection",
        "both",
        "Extra Photos Request Handling",
        """
EXTRA PHOTOS REQUEST

CLIENT SAYS: "munyongeze naka" / "can you add just one more?" / "byananiye nibikunda munyongeze"

This is extremely common — clients fall in love with photos and want more.

RESPONSE (HIGH heat, after delivery):
"Ntakibazo, turazongera!" (No problem, we'll add it!)
— For 1-2 extras when client is clearly happy and has been a good client.
— Always flag for human approval first.

RESPONSE (paid extras):
"Ifoto iri extra ni 5,000 RWF gusa.
Mwayiduha ntakibazo!" (Just 5k per extra, send payment when ready!)

RESPONSE (large quantity):
"Ntakibazo! Mwampe umubare w'ibitoze mushaka, tubahe igiciro cya buri kimwe."

IMPORTANT: Never automatically add free extras without human approval.
The decision to give a free extra is a human-managed bonus, not an AI decision.
""",
# CLIENT SELECTS MORE THAN THEIR PACKAGE ALLOWS (without asking):
# Example: package = 10 photos, client lists 11 in their selection
# Agent: "Ntago kwishyura, it's a gift from us"
# This is a human decision — flag for approval, never auto-gift.
# But the AI should acknowledge warmly: "Ntakibazo, turabireba!"
    ),

    (
        "objection",
        "both",
        "Competitor Comparison Handling",
        """
COMPETITOR COMPARISON RESPONSES

CLIENT SAYS: "I'm checking other studios" / "What makes you different?"

RESPONSE — DIFFERENTIATION (never attack competitors):
"That makes complete sense — you want the best for [child's name]!

Here's what sets us apart:
- 24-HOUR DELIVERY — most studios take 2-4 weeks
- CHILD SPECIALISTS — we follow [child's name]'s pace, no rushing
- PROFESSIONAL EDITING — every photo individually retouched, not just filtered
- PERSONAL SERVICE — you work directly with people who care

We'd love to be your choice!
Take your time and let us know if you have any questions."

NEVER: Criticize competitors by name
""",
    ),

    (
        "objection",
        "both",
        "Decision Authority Objection",
        """
DECISION AUTHORITY RESPONSES

CLIENT SAYS: "Need to ask my spouse" / "Family decision"

RESPONSE:
"Of course! This is a family decision and it's wonderful that you make these choices together.
I can send you a quick summary of the package options to make the conversation easy.
Would that help?"

FOLLOW-UP (after 24-48h):
"Hello [Name]! Just checking in — did you get a chance to chat with your family?
No pressure at all, just want to make sure you have everything you need!"
""",
    ),

    # ─── BILINGUAL PHRASES ───────────────────────────────────────────────────

    (
        "bilingual",
        "both",
        "Common Phrases — Real Agent Style",
        """
COMMON PHRASES — CALIBRATED ON REAL CONVERSATIONS

GREETINGS:
EN: "Hello! How may I be of service to you today?"
RW: "Muraho! Murakaza neza kuri Kigali Photography!"
FR/RW mix: "Bjr!" (agents commonly use this abbreviation)

GOOD MORNING:
EN: "Good morning!"
RW: "Mwaramutse neza [Name]!"

GOOD AFTERNOON/EVENING:
RW: "Mwiriwe neza!"

ACKNOWLEDGEMENTS (short, real):
"Ntakibazo" — No problem / You're welcome
"Cyane" — Great / A lot / Thank you
"Nziza!" — Great!
"Excellent!" — Excellent!
"Alright!" — Alright!
"Sure" — Sure
"Great!" — Great!
"Twayakiriye" — We've received it
"Murakoze" — Thank you
"Murakoze cyane" — Thank you so much
"Urakoze" — Thank you (singular)

PAYMENT RECEIVED:
EN: "Well received! Thank you."
RW: "Twayakiriye. Murakoze!"

SENDING PAYMENT CODE:
"798741 Kigali Photography Ltd" (always send the number + name together)

BOOKING FORM:
"Details:
Name:
Kid's Gender:
Kid's Age:
Package:
Booking Day:
Booking Time:
May you fill this?"

PHOTO DELIVERY:
EN: "Here is your gallery link!"
RW: "Amafoto yanyu ari tayeri!"

CLIENT ASKS FOR EXTRAS:
RW: "munyongeze naka" = "please add just one more"
Agent: "Ntakibazo, turazongera" = "No problem, we'll add it"

BIRTHDAY WISHES (personal, spontaneous):
"Hey [Name]! It's [Agent] from KP Studio.
I noticed that today is [child]'s birthday!
Just wanted to wish them a happy birthday and hope you have a beautiful celebration planned.
Sending you and your family good vibes!"

SOFT FOLLOW-UP AFTER SILENCE:
"Mwaramutse neza [Name],
We're very concerned with the silence, and I wanted to check up on you
to see if there's anything else I might assist you with!
Kindly get back to us so we could help you better. Thank you"

OPT-OUT CONFIRMATION:
EN: "You've been unsubscribed. We won't contact you again. Reply START to re-subscribe."
RW: "Mwakuyeho. Ntituzongera kubatumanahana. Subizamo START kugira ngo musubire."
""",
    ),

    # ─── SUCCESS PATTERNS ────────────────────────────────────────────────────

    (
        "success_pattern",
        "both",
        "Proven Conversion Patterns from Real Conversations",
        """
PROVEN PATTERNS — CALIBRATED ON REAL CLIENT CONVERSATIONS

PATTERN 1: ASK BEFORE YOU PRESENT
Real example: Instead of dumping all packages, agent asked:
"Mwifuza studio shoot, home shoot, cake, frames, video gato?"
Client gave options → agent built 2 custom packages → client chose one.
Impact: HIGH — client feels heard, not sold to.

PATTERN 2: USE CHILD'S NAME CONSTANTLY
Every message after learning the name uses it.
"We'd love to capture Eilan's special moments" not "your child's"
Impact: HIGH — 40%+ better conversion in real conversations.

PATTERN 3: ONE THING PER MESSAGE
Real agents never send walls of text.
Send the package info → wait for response → then send payment details.
Not everything at once.
Impact: HIGH — keeps conversation alive, easier for client to respond.

PATTERN 4: REACT TO GOOD NEWS WARMLY
Client shares payment screenshot → "Well received!"
Client chooses a package → "Excellent!"
Client shares outfit photos → "Great!"
Small celebrations build rapport.
Impact: HIGH — client feels appreciated, not just processed.

PATTERN 5: SILENCE FOLLOW-UP WITH GENUINE CONCERN
Not: "Are you still interested?"
Real: "We're very concerned with the silence, and I wanted to check up on you..."
Impact: HIGH — non-threatening, client feels cared for not chased.

PATTERN 6: GRACEFUL EXTRAS HANDLING
Client always asks for more photos after delivery. This is normal and expected.
For loyal/happy clients: "Ntakibazo, turazongera" (builds loyalty)
For new/unknown: offer at 5k/photo (fair, transparent)
Never make client feel bad for asking.
Impact: HIGH for repeat bookings and referrals.

PATTERN 7: CODE-SWITCH NATURALLY
Respond in the same language mix the client uses.
If client writes "Bjr, amafoto nimeza" → respond in RW/FR mix
If client writes "Hello, when will photos be ready?" → respond in English
If client mixes → mix back
Impact: HIGH — client feels at home, not like talking to a bot.

PATTERN 8: MILESTONE FRAMING
"[Child] is only 1 year old once — these moments are so fleeting"
Use early in conversation, before package presentation.
Impact: MEDIUM-HIGH — creates gentle urgency without pressure.

PATTERN 9: BIRTHDAY SURPRISE
Know the child's birthday (from booking form) and send a personal message.
"I noticed today is Eilan's birthday!" — unprompted, personal, memorable.
Impact: VERY HIGH for repeat bookings and referrals.

PATTERN 10: NEVER BURN A BRIDGE
Even clients who never booked get: "Feel free to reach out whenever you're ready!"
Real: clients who left came back months later.
Impact: HIGH for long-term business.
""",
    ),
    #Studio facilities logistics
    (
    "faq",
    "both",
    "Studio Facilities & Logistics FAQ",
    """
STUDIO FACILITIES & LOGISTICS

Q: Do you have a changing room?
A: Yes! We have enough room for changing, for both children and adults.
Agent style: "yes! we have enough room for changing!"

Q: Can you deliver frames to our home?
A: Yes! We deliver frames to clients after the session.
Agent asks: "naboneka amafoto turayohereza he? ni murugo tuyohereza?
cyangwa mukorera hafi hari uburyo bundi twayabagezaho?"
(Where shall we deliver — home, or do you work nearby?)

Q: What if we might be late due to traffic?
A: We are flexible. We book a comfortable slot with buffer time.
Agent style: "we saved you a maximum of 2 hours until the next person"
Never pressure the client — acknowledge their concern first, then reassure.

Q: Can we come from far (Ruyenzi, Kicukiro outskirts)?
A: Absolutely. We accommodate clients coming from all areas of Kigali.
Suggest a time slot that avoids peak traffic when possible.
""",
),


]


def load_seed_data() -> int:
    """
    Load all seed documents into the knowledge base.
    Skips documents that already exist (by title) to prevent duplicates.
    Returns count of newly created documents.
    """
    from apps.rag.models import KnowledgeDocument

    created = 0
    for category, language, title, content in SEED_DOCUMENTS:
        doc, is_new = KnowledgeDocument.objects.get_or_create(
            title=title,
            defaults={
                "category": category,
                "language": language,
                "content": content.strip(),
                "is_active": True,
                "version": 1,
            },
        )
        if is_new:
            created += 1
            logger.info("Seeded: [%s] %s", category, title)
        else:
            logger.debug("Skipped (exists): %s", title)

    return created
