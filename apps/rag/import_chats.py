"""
Import Real WhatsApp Conversations
====================================
Loads exported WhatsApp chat .txt files into the knowledge base
as success pattern examples for the RAG system.

Usage:
  python manage.py shell -c "
  from apps.rag.import_chats import import_all
  import_all()
  "

"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

# Folder where your exported .txt chat files are placed
CHATS_DIR = "chats/"

# Map filename → document title in the knowledge base
# Add all your chat files here
CHAT_FILES = {
    "kd_alana.txt": "Real conversation — Returning client (Alana)",
    "kd_ghislaine.txt": "Real conversation — Returning client (Ghislaine)",
    "kd_graceMiah.txt": "Real conversation — Returning client (Grace Miah)",
    "kd_louangeM.txt": "Real conversation — Returning client (Louange M)",
    "kd_mamaRabah.txt": "Real conversation — Returning client (Mama Rabah)",
    "kd_mamaShine.txt": "Real conversation — Returning client (Mama Shine)",
    "kd_mamaZola.txt": "Real conversation — Returning client (Mama Zola)",
    "kd_nadege.txt": "Real conversation — Returning client (Nadege)",
    "kd_nadegeAnaya.txt": "Real conversation — Returning client (Nadege Anaya)",
    "kd_numero1.txt": "Real conversation — Returning client (Numero 1)",
    "kd_numero2.txt": "Real conversation — Returning client (Numero 2)",
    "kd_rosetteM.txt": "Real conversation — Returning client (Rosette M)",
    "kd_safideal.txt": "Real conversation — Returning client (Safideal)",

    "WhatsApp Chat - +250 722 273 867.txt": "Real conversation — New prospect (Phone: 250722273867)",
    "WhatsApp Chat - +250 725 027 744.txt": "Real conversation — New prospect (Phone: 250725027744)",
    "WhatsApp Chat - +250 726 995 730.txt": "Real conversation — New prospect (Phone: 250726995730)",
    "WhatsApp Chat - +250 780 068 548.txt": "Real conversation — New prospect (Phone: 250780068548)",
    "WhatsApp Chat - +250 780 724 391.txt": "Real conversation — New prospect (Phone: 250780724391)",
    "WhatsApp Chat - +250 781 219 631.txt": "Real conversation — New prospect (Phone: 250781219631)",
    "WhatsApp Chat - +250 781 518 673.txt": "Real conversation — New prospect (Phone: 250781518673)",
    "WhatsApp Chat - +250 781 563 763.txt": "Real conversation — New prospect (Phone: 250781563763)",
    "WhatsApp Chat - +250 781 897 649.txt": "Real conversation — New prospect (Phone: 250781897649)",
    "WhatsApp Chat - +250 781 921 606.txt": "Real conversation — New prospect (Phone: 250781921606)",
    "WhatsApp Chat - +250 782 120 767.txt": "Real conversation — New prospect (Phone: 250782120767)",
    "WhatsApp Chat - +250 782 339 490.txt": "Real conversation — New prospect (Phone: 250782339490)",
    "WhatsApp Chat - +250 782 635 545.txt": "Real conversation — New prospect (Phone: 250782635545)",
    "WhatsApp Chat - +250 783 192 981.txt": "Real conversation — New prospect (Phone: 250783192981)",
    "WhatsApp Chat - +250 783 594 524.txt": "Real conversation — New prospect (Phone: 250783594524)",
    "WhatsApp Chat - +250 783 629 312.txt": "Real conversation — New prospect (Phone: 250783629312)",
    "WhatsApp Chat - +250 784 070 759.txt": "Real conversation — New prospect (Phone: 250784070759)",
    "WhatsApp Chat - +250 786 072 557.txt": "Real conversation — New prospect (Phone: 250786072557)",
    "WhatsApp Chat - +250 786 186 062.txt": "Real conversation — New prospect (Phone: 250786186062)",
    "WhatsApp Chat - +250 787 723 208.txt": "Real conversation — New prospect (Phone: 250787723208)",
    "WhatsApp Chat - +250 787 954 018.txt": "Real conversation — New prospect (Phone: 250787954018)",
    "WhatsApp Chat - +250 788 221 178.txt": "Real conversation — New prospect (Phone: 250788221178)",
    "WhatsApp Chat - +250 788 442 204.txt": "Real conversation — New prospect (Phone: 250788442204)",
    "WhatsApp Chat - +250 788 716 584.txt": "Real conversation — New prospect (Phone: 250788716584)",
    "WhatsApp Chat - +250 788 818 639.txt": "Real conversation — New prospect (Phone: 250788818639)",
    "WhatsApp Chat - +250 794 271 126.txt": "Real conversation — New prospect (Phone: 250794271126)",

    "WhatsApp Chat - Albertine.txt": "Real conversation — New prospect (Albertine)",
    "WhatsApp Chat - Alice.txt": "Real conversation — New prospect (Alice)",
    "WhatsApp Chat - Alida M. Andrick.txt": "Real conversation — New prospect (Alida M. Andrick)",
    "WhatsApp Chat - Aline Uwineza.txt": "Real conversation — New prospect (Aline Uwineza)",
    "WhatsApp Chat - Ange M. Kenan.txt": "Real conversation — New prospect (Ange M. Kenan)",
    "WhatsApp Chat - Bd Client.txt": "Real conversation — New prospect (Bd Client)",
    "WhatsApp Chat - Client Dinah.txt": "Real conversation — New prospect (Client Dinah)",
    "WhatsApp Chat - Client Kevine.txt": "Real conversation — New prospect (Client Kevine)",
    "WhatsApp Chat - Cyuzuzo.txt": "Real conversation — New prospect (Cyuzuzo)",

    "WhatsApp Chat - KD Ada.txt": "Real conversation — Returning client (KD Ada)",
    "WhatsApp Chat - KD Adeline Seneza.txt": "Real conversation — Returning client (KD Adeline Seneza)",
    "WhatsApp Chat - KD Akariza.txt": "Real conversation — Returning client (KD Akariza)",
    "WhatsApp Chat - KD Aline_rutagarama.txt": "Real conversation — Returning client (KD Aline Rutagarama)",
    "WhatsApp Chat - KD Arlène Mama Willa.txt": "Real conversation — Returning client (KD Arlene Mama Willa)",
    "WhatsApp Chat - Kd bigwi.txt": "Real conversation — Returning client (Kd Bigwi)",
    "WhatsApp Chat - KD Claire.txt": "Real conversation — Returning client (KD Claire)",
    "WhatsApp Chat - KD Clea.txt": "Real conversation — Returning client (KD Clea)",
    "WhatsApp Chat - KD Cléora's Mama.txt": "Real conversation — Returning client (KD Cleora's Mama)",
    "WhatsApp Chat - KD Conso Brissa.txt": "Real conversation — Returning client (KD Conso Brissa)",
    "WhatsApp Chat - KD Divine Dusabe.txt": "Real conversation — Returning client (KD Divine Dusabe)",
    "WhatsApp Chat - KD Fabby.txt": "Real conversation — Returning client (KD Fabby)",
    "WhatsApp Chat - KD Gia.txt": "Real conversation — Returning client (KD Gia)",
    "WhatsApp Chat - KD Gloria Ndoli.txt": "Real conversation — Returning client (KD Gloria Ndoli)",
    "WhatsApp Chat - KD Hoza Mama Heaven.txt": "Real conversation — Returning client (KD Hoza Mama Heaven)",
    "WhatsApp Chat - KD Ihogoza rya shyaka.txt": "Real conversation — Returning client (KD Ihogoza Rya Shyaka)",
    "WhatsApp Chat - KD Ingabire Hope.txt": "Real conversation — Returning client (KD Ingabire Hope)",
    "WhatsApp Chat - KD Ingrid.txt": "Real conversation — Returning client (KD Ingrid)",
    "WhatsApp Chat - KD Jordan.txt": "Real conversation — Returning client (KD Jordan)",
    "WhatsApp Chat - KD Keziah D. Bazoza.txt": "Real conversation — Returning client (KD Keziah D. Bazoza)",
    "WhatsApp Chat - KD Kiomi.txt": "Real conversation — Returning client (KD Kiomi)",
    "WhatsApp Chat - KD Kundwa.txt": "Real conversation — Returning client (KD Kundwa)",
    "WhatsApp Chat - KD Liliane Uwacu .txt": "Real conversation — Returning client (KD Liliane Uwacu)",
    "WhatsApp Chat - Kd Liora (1).txt": "Real conversation — Returning client (Kd Liora)",
    "WhatsApp Chat - Kd Liora.txt": "Real conversation — Returning client (Kd Liora)",
    "WhatsApp Chat - KD Loreto.txt": "Real conversation — Returning client (KD Loreto)",
    "WhatsApp Chat - KD Mama Archie.txt": "Real conversation — Returning client (KD Mama Archie)",
    "WhatsApp Chat - KD Mama Ihsan❤️.txt": "Real conversation — Returning client (KD Mama Ihsan)",
    "WhatsApp Chat - KD Mama Mylan.txt": "Real conversation — Returning client (KD Mama Mylan)",
    "WhatsApp Chat - KD Mila.txt": "Real conversation — Returning client (KD Mila)",
    "WhatsApp Chat - Kd Mrs. Bahizi Nova.txt": "Real conversation — Returning client (Kd Mrs. Bahizi Nova)",
    "WhatsApp Chat - KD Mukundente Hamida.txt": "Real conversation — Returning client (KD Mukundente Hamida)",
    "WhatsApp Chat - KD Sandrine2.txt": "Real conversation — Returning client (KD Sandrine 2)",
    "WhatsApp Chat - KD Tony.txt": "Real conversation — Returning client (KD Tony)",
    "WhatsApp Chat - KD Umutoni Angelique.txt": "Real conversation — Returning client (KD Umutoni Angelique)",
    "WhatsApp Chat - KD Vihang.txt": "Real conversation — Returning client (KD Vihang)",

    "WhatsApp Chat - Mam koen.txt": "Real conversation — Returning client (Mam Koen)",
    "WhatsApp Chat - Mama Jaylen.txt": "Real conversation — Returning client (Mama Jaylen)",
    "WhatsApp Chat - Ms Hense.txt": "Real conversation — New prospect (Ms Hense)",
    "WhatsApp Chat - Mucyo.txt": "Real conversation — New prospect (Mucyo)",
    "WhatsApp Chat - Norah.txt": "Real conversation — New prospect (Norah)",
    "WhatsApp Chat - Sarah M. Mikelle.txt": "Real conversation — New prospect (Sarah M. Mikelle)",
}

# Only import messages from these periods (month, day ranges)
# Messages outside these periods will be excluded
# This filters out Christmas promos, New Year specials, etc.
INCLUDED_PERIODS = [
    (2, 1, 2, 28),   # February
    (3, 1, 3, 31),   # March
    # Add more periods if needed:
    # (4, 1, 4, 30),  # April
]

# ─── DATE FILTERING ───────────────────────────────────────────────────────────

def is_included_date(line: str) -> bool:
    """
    Returns True if the line belongs to an included period.
    Lines that are not dated (continuation lines) are always kept.
    WhatsApp format: [12/16/25, 17:08:53] or [1/15/25, 13:18:14]
    """
    match = re.match(r'\[(\d{1,2})/(\d{1,2})/(\d{2,4}),', line)
    if not match:
        # Not a timestamped line — keep it (it's a continuation of a previous message)
        return True

    month = int(match.group(1))
    day   = int(match.group(2))

    for start_m, start_d, end_m, end_d in INCLUDED_PERIODS:
        if (start_m, start_d) <= (month, day) <= (end_m, end_d):
            return True

    return False


# ─── CLEANING ─────────────────────────────────────────────────────────────────

def clean_chat(raw: str) -> str:
    """
    Clean a raw WhatsApp export:
      - Remove messages outside INCLUDED_PERIODS
      - Remove WhatsApp system messages
      - Remove empty lines
    """
    lines = []
    for line in raw.splitlines():
        if not line.strip():
            continue

        # Skip messages outside included date periods
        if not is_included_date(line):
            continue

        # Skip WhatsApp system messages
        if any(skip in line for skip in [
            "end-to-end encrypted",
            "is a contact",
            "omitted",
            "Missed voice call",
            "Voice call",
            "This message was deleted",
            "You deleted this message",
            "Contact card omitted",
        ]):
            continue

        lines.append(line.strip())

    return "\n".join(lines)


def anonymize(text: str) -> str:
    """
    Replace sensitive data with placeholders.
    Keeps child names — they are part of natural conversation flow.
    """
    # Remove Rwandan phone numbers
    text = re.sub(r'\+?250\s?\d{3}\s?\d{3}\s?\d{3}', '[PHONE]', text)
    text = re.sub(r'\b07\d{8}\b', '[PHONE]', text)

    # Remove MoMo transaction references
    text = re.sub(r'TxId:\S+', '[PAYMENT_REF]', text)

    # Remove full payment confirmation lines
    text = re.sub(
        r'TxId:.*?(?=\n|$)',
        '[PAYMENT_CONFIRMED]',
        text
    )

    # Anonymize pixieset gallery links (keep domain, remove personal path)
    text = re.sub(
        r'https://kigaliphotography\.pixieset\.com/\S+',
        '[GALLERY_LINK]',
        text
    )

    # Remove Google form links
    text = re.sub(
        r'https://docs\.google\.com/forms/\S+',
        '[FEEDBACK_FORM_LINK]',
        text
    )

    # Remove TikTok links
    text = re.sub(r'https://vm\.tiktok\.com/\S+', '[TIKTOK_LINK]', text)

    return text


# ─── IMPORT ───────────────────────────────────────────────────────────────────

def import_chat(filepath: str, title: str) -> bool:
    """
    Import a single chat file into the KnowledgeDocument table.
    Skips if a document with the same title already exists.
    Returns True if created, False if skipped.
    """
    from apps.rag.models import KnowledgeDocument

    if not os.path.exists(filepath):
        logger.warning("File not found: %s", filepath)
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    content = anonymize(clean_chat(raw))

    if len(content) < 100:
        logger.warning(
            "Skipping %s — too short after cleaning (%d chars). "
            "Check your INCLUDED_PERIODS or the file content.",
            filepath, len(content)
        )
        return False

    doc, is_new = KnowledgeDocument.objects.get_or_create(
        title=title,
        defaults={
            "category": "success_pattern",
            "language": "both",
            "content": content,
            "is_active": True,
            "version": 1,
        }
    )

    if is_new:
        logger.info("Imported: %s (%d chars)", title, len(content))
    else:
        logger.debug("Already exists, skipped: %s", title)

    return is_new


def import_all() -> int:
    """
    Import all chat files defined in CHAT_FILES.
    Returns the number of newly created documents.
    """
    created = 0
    skipped = 0
    missing = 0

    for filename, title in CHAT_FILES.items():
        filepath = os.path.join(CHATS_DIR, filename)

        if not os.path.exists(filepath):
            print(f"  NOT FOUND: {filepath}")
            missing += 1
            continue

        result = import_chat(filepath, title)
        if result:
            print(f"  IMPORTED:  {title}")
            created += 1
        else:
            print(f"  SKIPPED:   {title} (already exists or too short)")
            skipped += 1

    print(f"\nDone — {created} imported, {skipped} skipped, {missing} not found.")
    print("Run 'python manage.py index_knowledge_base --force' to reindex.")
    return created