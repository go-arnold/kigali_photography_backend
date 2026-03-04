"""
Seed Knowledge Base
====================
Initial knowledge base for Kigali Photography AI assistant.

Categories:
  - package:          Pricing, inclusions, session types
  - policy:           Booking policies, payment terms
  - script:           Approved response templates (EN + RW)
  - objection:        Objection handling scripts
  - faq:              Common client questions
  - location:         Studio location, parking, hours
  - bilingual:        Common phrases in both languages
  - success_pattern:  Proven conversion patterns

Edit freely — this is YOUR knowledge base.
Human staff manages this via Django admin after initial load.
"""

import logging

logger = logging.getLogger(__name__)

#
# SEED DATA
# Each entry: (category, language, title, content)
#

SEED_DOCUMENTS = [
    #  PACKAGES
    (
        "package",
        "both",
        "Session Packages Overview",
        """
KIGALI PHOTOGRAPHY — SESSION PACKAGES

ESSENTIAL PACKAGE — 100,000 RWF
• 45-minute studio session
• 10 professionally edited photos
• Standard frame included
• Digital downloads (high resolution)
• 24-hour delivery guarantee
Best for: First-time families, toddler milestones

PREMIUM PACKAGE — 150,000 RWF
• 60-minute studio session
• 15 professionally edited photos
• Premium frame included
• Digital downloads (high resolution)
• 24-hour delivery guarantee
• Multiple backdrop options
Best for: Growing families, special occasions

SIGNATURE PACKAGE — 200,000 RWF
• 90-minute studio session
• 25 professionally edited photos
• Premium frame + digital album
• Digital downloads (high resolution)
• 24-hour delivery guarantee
• Multiple backdrop options
• Professional styling guidance
• Priority editing queue
Best for: Annual family portraits, milestone celebrations

BOOKING FEE: 20,000 RWF (deducted from final payment)
All packages include: professional lighting, child-friendly environment, complimentary props
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
Best for: Clients who love the photos but want more coverage.
When to offer: HIGH heat clients with price hesitation.

2. FREE HIGHLIGHT REEL
30-second video compilation with music from session photos.
Delivered within 48 hours of photo delivery.
Best for: Social media-active parents, modern families.
When to offer: MEDIUM/HIGH heat clients who seem social-media oriented.

3. FRAME UPGRADE
Upgrade from standard to premium wood frame at no extra cost.
Best for: Clients who value physical products, gift-givers.
When to offer: When client mentions frames, printing, or gifts.

4. PRIORITY EDITING
Jump to front of editing queue (24h delivery is already standard).
Best for: Time-sensitive needs, events happening soon.
When to offer: Clients with upcoming events or tight timelines.

RULE: Never offer more than one bonus per conversation.
RULE: Always flag for human approval — never auto-send.
RULE: Never offer bonuses to LOW heat clients.
""",
    ),
    #  POLICIES
    (
        "policy",
        "both",
        "Booking & Payment Policy",
        """
BOOKING & PAYMENT POLICY

BOOKING FEE
• 20,000 RWF non-refundable booking fee to secure your session date
• Booking fee is deducted from your final package payment
• Session date is NOT confirmed until booking fee is received

PAYMENT METHODS
• Mobile Money (MTN, Airtel)
• Bank transfer
• Cash at studio

RESCHEDULING
• Free rescheduling with 48+ hours notice
• One free reschedule per booking
• Second reschedule: 10,000 RWF fee
• Same-day cancellation: booking fee forfeited

CANCELLATION
• 48+ hours notice: full refund minus booking fee
• Less than 48 hours: no refund

NO DISCOUNT POLICY
• We do not reduce prices for the same service
• We offer value additions, never price reductions
• Package scope can be adjusted — different scope = different price
• This maintains the premium quality standard our clients expect
""",
    ),
    #  FAQ
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
We recommend coordinated (not matching) outfits for family sessions.
Avoid logos and text on clothing.

Q: My child is very active / shy — is that okay?
A: Absolutely! We specialize in children. We have toys, props, and years of
experience making children comfortable. We follow the child's pace — no rushing.

Q: When will I receive my photos?
A: We guarantee delivery within 24 hours of your session. Usually faster.

Q: Can I bring siblings or grandparents?
A: Yes! Family members are welcome. Let us know in advance so we can plan.

Q: Do you do outdoor sessions?
A: Our studio is climate-controlled and optimized for beautiful results.
We currently focus on studio sessions for consistent quality.

Q: Can I see the photos during the session?
A: We show preview images during the session to ensure you love the direction.

Q: What if my child is sick on the day?
A: Please reschedule! A sick child won't enjoy the session. Contact us ASAP
and we'll find a new date. Health always comes first.

Q: Do you edit all the photos?
A: Yes — every delivered photo is professionally retouched: color grading,
skin smoothing, background cleanup, lighting enhancement.

Q: Can I share the photos on social media?
A: Yes! Please tag us @KigaliPhotography — we love seeing our work shared.
""",
    ),
    #  LOCATION
    (
        "location",
        "both",
        "Studio Location & Access",
        """
KIGALI PHOTOGRAPHY STUDIO

LOCATION
KG 123 Street, Kigali
(Exact address shared upon booking confirmation)

HOURS
Monday – Saturday: 9:00 AM – 6:00 PM
Sunday: Closed (private bookings available on request)
Public holidays: Closed

ARRIVAL
• Please arrive 10 minutes before your session time
• Late arrival reduces session time — we cannot extend into next booking
• Free parking available at the building

WHAT TO BRING
• Confirmation message (we'll send it after booking)
• 2-3 outfit options for your child
• Favorite toy or comfort item (helps shy children relax)
• Snack for young children (helps keep energy up)
• Any special props you'd like included

CONTACT
WhatsApp: +250700000000
Hours: Mon-Sat 9AM-6PM
Response time: Within 1 hour during business hours

FINDING US
• We share a pin location via WhatsApp upon booking confirmation
• Easily accessible from Kigali city center
• Landmark: [Add local landmark here]
""",
    ),
    #  SCRIPTS: ENGLISH
    (
        "script",
        "en",
        "Welcome & Introduction Script (English)",
        """
FIRST CONTACT — ENGLISH GREETING

WARM GREETING:
"Hi [Name]! Welcome! I'm so glad you reached out to Kigali Photography.
We specialize in capturing those precious, fleeting moments of childhood —
the kind that you'll treasure for a lifetime. 

I'd love to learn a little about your family! Could you tell me:
• Your little one's name and age?
• What occasion are you celebrating, or is this a general milestone session?
• Do you have a preferred timeframe in mind?"

FOLLOW-UP IF NO RESPONSE TO QUESTIONS:
"No rush at all! Whenever you're ready, just let me know and we'll find the
perfect session for your family. "

KEY PRINCIPLES:
- Use child's name as soon as you learn it
- Express genuine warmth and excitement about their family
- Never rush — let them set the pace
- Build emotional connection before talking packages
""",
    ),
    (
        "script",
        "en",
        "Package Presentation Script (English)",
        """
PACKAGE PRESENTATION — ENGLISH

INTRODUCTION:
"Based on what you've shared, I think you'd love our [PACKAGE NAME] session!
Here's what makes it special: [SPECIFIC VALUE POINTS FOR THEIR SITUATION]

[Present relevant package details]

Our sessions include:
 Professional studio lighting crafted for beautiful, flattering results
 A child-friendly, relaxed environment — no rushing, we follow [child's name]'s pace
 Expert composition and posing guidance (without making it feel forced!)
 Our 24-hour delivery promise — no waiting weeks for your memories
 Professional editing on every single image

To secure your preferred date, we ask for a 20,000 RWF booking fee
(fully deducted from your package). Shall I check available dates for you?"

VALUE REMINDER (if hesitation):
"I know investing in professional photography feels significant — and it is!
These are the photos that will hang in your home, that [child's name] will
look at years from now. That's priceless. "
""",
    ),
    (
        "script",
        "en",
        "Session Preparation Script (English)",
        """
SESSION PREPARATION — ENGLISH

REMINDER (2-3 days before):
"Hi [Name]!  Just a friendly reminder that [child's name]'s session is
coming up on [DATE] at [TIME]. We're so excited to meet your family!

A few tips to make the session magical:
 Bring 2-3 outfit options (solid colors work best)
 Pack [child's name]'s favorite toy or comfort item
 A small snack helps keep little ones happy and energized
Arrive 10 minutes early so [child's name] can settle in

Any questions before the big day? We're here! "

DAY-OF WELCOME:
"Good morning [Name]!  Today is the day — so excited for [child's name]'s session!
Quick reminder: [TIME] at our studio. We're all ready for you!
See you soon! "
""",
    ),
    (
        "script",
        "en",
        "Post-Session & Delivery Script (English)",
        """
POST-SESSION & DELIVERY — ENGLISH

THANK YOU (same day):
"[Name], thank you so much for choosing Kigali Photography today! 
[Child's name] was absolutely wonderful — such a natural in front of the camera!
We're already editing and can't wait to share the results with you.
Our promise: your photos will be ready within 24 hours. "

PHOTO DELIVERY:
"The wait is over!  [Child's name]'s photos are ready!
[Share link/images]

Every image has been carefully retouched with love — color grading, lighting
enhancement, and professional finishing. We hope they take your breath away! 

Please let us know if you'd like any adjustments. Your satisfaction is everything to us."

FEEDBACK REQUEST:
"[Name], we'd love to hear your thoughts! A quick review means the world to
small businesses like ours and helps other families find us.
[Google Review Link]
Thank you for trusting us with [child's name]'s memories! "
""",
    ),
    #  SCRIPTS: KINYARWANDA
    (
        "script",
        "rw",
        "Ubutumire n'Intangiriro (Kinyarwanda)",
        """
INTANGIRIRO — KINYARWANDA

UBUTUMIRE BWO GUKIRA:
"Muraho [Izina]!  Murakaza neza kuri Kigali Photography!
Duhangayikishwa n'ibihe byiza by'ubwana — ibihe bidashobora gusubira,
bikagira akamaro k'iteka ryose. 

Njye ndishimye kumenya umuryango wanyu! Mwashobora kumbwira:
• Izina n'imyaka y'umwana wanyu?
• Ni ihuriro ryihe rifatiye, cyangwa ni igihe cy'ingenzi?
• Mufite igihe mushaka gutekereza?"

INYUNGU NZIZA:
"Ntimugire ikibazo! Iyo mwishyize, nzabashyigikira mu gushyira ahagana
isomo ryiza kuri umuryango wanyu. "
""",
    ),
    (
        "script",
        "rw",
        "Gutanga Amakuru y'Ibikorwa (Kinyarwanda)",
        """
GUTANGA AMAKURU Y'IBIKORWA — KINYARWANDA

IJAMBO RY'INTANGIRIRO:
"Hashingiwe ku bintu mwabwiye, ntekereza ko muzakunda isomo ryacu rya [IZINA RY'ISOMO]!
Dore ibigize agaciro kacyo:

 Urumuri rw'umwuga rwungura ibifoto byiza
 Aho hantu heze, heza, hatoroshya abana — ntaha kigufi, dukurikira iyindi
 Ubuyobozi bw'inzobere mu mashusho
 Amasezerano yo gutanga mu masaha 24 — nta gusubira kongera iminsi
 Gusana nziza kuri buri foto

Kugira ngo mushyire ahagana itariki mushaka, dusaba inyishyura y'igihembwe
ya 20,000 RWF (izasubizwa mu nyishyura y'isomo). Ngishaka kureba iminsi iboneka?"
""",
    ),
    #  OBJECTION HANDLING
    (
        "objection",
        "both",
        "Price Objection Handling",
        """
PRICE OBJECTION RESPONSES

CLIENT SAYS: "It's too expensive" / "Out of my budget" / "Too much"

LEVEL 1 — VALUE REINFORCEMENT:
"I completely understand — it's a real investment! Let me share what makes it
worth every franc:

 Every photo is professionally edited — not just filtered, but carefully
retouched by a skilled editor (skin tones, lighting, background perfection)

 24-hour delivery — most studios take 2-4 weeks. You get your memories tomorrow.

 Child-specialist experience — we know how to get genuine smiles, not forced ones.
[Child's name] will actually enjoy the session.

 These photos will be in your home for decades. Cost per year? A few thousand RWF
for memories that last forever.

Would it help to see some examples of our recent work?"

LEVEL 2 — PACKAGE CONSIDERATION (human must approve first):
"If timing is a consideration, we do have our Essential Package at 100,000 RWF
which still includes 10 professionally edited photos and our full 24-hour delivery.
Would that work better for your family right now?"

LEVEL 3 — PACKAGE ADJUSTMENT (human oversight required):
[Do not auto-respond — flag for human review]
"Let me check with our team about options that might work for your situation.
I'll get back to you shortly!"

NEVER SAY:
- "I can give you a discount"
- "Let me reduce the price"
- "We can do it cheaper"
- Any direct price reduction for the same service
""",
    ),
    (
        "objection",
        "both",
        "Timing Objection Handling",
        """
TIMING OBJECTION RESPONSES

CLIENT SAYS: "Not sure when" / "Maybe later" / "Need to check calendar"

RESPONSE:
"Absolutely no pressure! I completely understand — life gets busy.

A couple of things worth knowing:
 Our calendar books up quickly, especially on weekends
 [Child's name] is only [age] once — these moments are so fleeting
 We're flexible with scheduling once you have a sense of timing

Would it be helpful if I shared our available dates for the next 3-4 weeks?
That way you have the full picture whenever you're ready to decide. No commitment needed! "

IF THEY HAVE A SPECIFIC EVENT:
"Oh, [EVENT]! How exciting! We'd love to capture [child's name] around that time.
Sessions book fast around special occasions — would you like me to hold a tentative spot
while you confirm? We just need the booking fee to secure it fully."

FOLLOW-UP TIMING:
HIGH heat: Follow up in 4-6 hours
MEDIUM heat: Follow up next day
LOW heat: Follow up after 48 hours, once only
""",
    ),
    (
        "objection",
        "both",
        "Competitor Comparison Handling",
        """
COMPETITOR COMPARISON RESPONSES

CLIENT SAYS: "I'm checking other studios" / "What makes you different?" / "[X] is cheaper"

RESPONSE — DIFFERENTIATION (never attack competitors):
"That makes complete sense — you want to find the best fit for your family!

Here's what sets us apart:

 24-HOUR DELIVERY — We're one of the only studios in Kigali with this guarantee.
Most studios take 2-4 weeks. We know memories feel urgent.

 CHILD SPECIALISTS — We don't just photograph children, we specialize in them.
Patience, props, play-based approach. Genuine smiles, not forced ones.

 PROFESSIONAL EDITING — Every photo is individually retouched by a skilled editor,
not just auto-filtered.

 PERSONAL SERVICE — You're not booking a time slot with a receptionist.
You're working with photographers who care about your family's story.

We'd love to be your choice — but most importantly, we want you to find the
perfect fit for [child's name]'s memories. Take your time! "

NEVER:
- Criticize competitors by name
- Make claims you can't back up
- Be defensive or pressured
""",
    ),
    (
        "objection",
        "both",
        "Decision Authority Objection",
        """
DECISION AUTHORITY RESPONSES

CLIENT SAYS: "Need to ask my spouse" / "Family decision" / "I'll discuss with my husband/wife"

RESPONSE:
"Of course! This is absolutely a family decision and it's wonderful that you
make these choices together. 

To make the conversation easy, I can send you:
 A quick summary of the package options and what's included
 Some examples of our recent work to share
 Available dates so you have everything ready

That way you have all the information at hand when you chat.
Would that be helpful? "

FOLLOW-UP:
"Hi [Name]! Just checking in — did you get a chance to chat with [spouse]?
No pressure at all, just want to make sure you have everything you need. "

TIMING: Follow up once after 24-48 hours. Then soft exit if no response.
""",
    ),
    #  BILINGUAL PHRASES
    (
        "bilingual",
        "both",
        "Common Phrases — English & Kinyarwanda",
        """
COMMON PHRASES — BILINGUAL REFERENCE

GREETINGS:
EN: "Hello! Welcome to Kigali Photography! "
RW: "Muraho! Murakaza neza kuri Kigali Photography! "

EN: "Good morning! Hope your day is going wonderfully!"
RW: "Mwaramutse! Twifuriza ko umunsi wanyu ugenda neza!"

EN: "Good afternoon!"
RW: "Mwiriwe!"

THANKS:
EN: "Thank you so much for reaching out!"
RW: "Urakoze cyane kwadusobanukirwa!"

EN: "We appreciate your trust in us."
RW: "Dushimira zikuye ku mutima ko mutizera."

BOOKING CONFIRMATION:
EN: "Your session is confirmed for [DATE] at [TIME]. We can't wait! "
RW: "Isomo ryanyu ryemejwe ku itariki [DATE] saa [TIME]. Tutegereje kubabona! "

PHOTO DELIVERY:
EN: "Your photos are ready! "
RW: "Amafoto yanyu ari tayeri! "

BIRTHDAY WISHES:
EN: "Happy Birthday to the wonderful [NAME]! "
RW: "Isabukuru nziza kuri [NAME] w'umunyarwanda! "

FOLLOW-UP:
EN: "Just checking in — any questions I can help with? "
RW: "Ndashaka kureba — hari ikibazo nabashoborera? "

SOFT EXIT:
EN: "No worries! Feel free to reach out whenever you're ready. We'd love to capture [NAME]'s special moments! "
RW: "Nta nkange! Mutwandikire igihe mushaka. Tuzishima gufotorwa [NAME]! "

OPT-OUT CONFIRMATION:
EN: "You've been unsubscribed. We won't contact you again. Reply START to re-subscribe."
RW: "Mwakuyeho. Ntituzongera kubatumanahana. Subizamo START kugira ngo musubire."
""",
    ),
    #  SUCCESS PATTERNS
    (
        "success_pattern",
        "both",
        "Proven Conversion Patterns",
        """
PROVEN CONVERSION PATTERNS

PATTERN 1: USE THE CHILD'S NAME IMMEDIATELY
Impact: HIGH — personalizes every message from first response
Example: "We'd love to photograph [CHILD_NAME]!" vs "We'd love to photograph your child"
Learning: Messages using child's name convert 40%+ better

PATTERN 2: ANCHOR WITH THE 24-HOUR DELIVERY
Impact: HIGH — unique differentiator, builds confidence
Use in: First package mention, every value reinforcement
Script: "We're one of the only studios delivering within 24 hours — no waiting weeks"

PATTERN 3: MILESTONE FRAMING
Impact: HIGH — creates urgency without pressure
Example: "[Child] is only 2 years old once — these moments are fleeting"
When: Early in conversation before package presentation

PATTERN 4: QUESTION CASCADE
Impact: MEDIUM — increases engagement, gathers data for personalization
Ask max 2-3 questions per message (never a form)
Sequence: Name → Age → Occasion → Timeframe

PATTERN 5: SOCIAL PROOF BRIDGE
Impact: MEDIUM — reduces risk perception
Example: "Families all across Kigali trust us with their most precious moments"
When: After price presentation, before hesitation sets in

PATTERN 6: RECIPROCAL WARMTH
Impact: HIGH — matches client's emotional register
If client is excited → match excitement
If client is reserved → be warm but measured
If client is skeptical → be factual and confident, not defensive

PATTERN 7: GRACEFUL EXIT
Impact: HIGH for brand — never burn bridges
Always end with door open: "Reach out whenever you're ready"
Clients who weren't ready often return months later
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
