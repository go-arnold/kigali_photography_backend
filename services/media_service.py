"""
Media Service
=============
Télécharge et sert les fichiers media WhatsApp.

Flow:
  1. Client envoie image/audio/document
  2. Meta nous envoie un media_id
  3. On appelle l'API Meta pour obtenir l'URL du fichier
  4. On télécharge le fichier
  5. On le sauvegarde dans MEDIA_ROOT/whatsapp/
  6. On retourne l'URL locale servable par Django

Le media_id Meta est valide 30 jours.
"""
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Dossier de stockage des media
MEDIA_DIR = Path(settings.MEDIA_ROOT) / "whatsapp"
MEDIA_URL_PREFIX = settings.MEDIA_URL + "whatsapp/"

# Extensions par MIME type
MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}


def download_and_save_media(
    media_id: str,
    mime_type: str = "",
    filename: str = "",
) -> Optional[str]:
    """
    Télécharge un media WhatsApp et le sauvegarde localement.
    Retourne l'URL relative accessible depuis le navigateur, ou None si échec.
    
    Usage:
        url = download_and_save_media(media_id, "image/jpeg")
        # → "/media/whatsapp/img_abc123.jpg"
    """
    try:
        # Créer le dossier si pas encore existant
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)

        # Étape 1: Récupérer l'URL de téléchargement depuis Meta
        download_url = _get_media_download_url(media_id)
        if not download_url:
            logger.error("Could not get download URL for media_id=%s", media_id)
            return None

        # Étape 2: Télécharger le fichier
        file_bytes = _download_file(download_url)
        if not file_bytes:
            logger.error("Could not download media from %s", download_url)
            return None

        # Étape 3: Déterminer l'extension
        ext = MIME_EXTENSIONS.get(mime_type, "")
        if not ext and filename:
            # Utiliser l'extension du nom de fichier original
            ext = Path(filename).suffix
        if not ext:
            ext = ".bin"

        # Étape 4: Nom de fichier unique
        unique_name = f"{uuid.uuid4().hex[:16]}{ext}"
        file_path = MEDIA_DIR / unique_name

        # Étape 5: Sauvegarder
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Retourner l'URL relative
        relative_url = f"{MEDIA_URL_PREFIX}{unique_name}"
        logger.info(
            "Media saved | media_id=%s mime=%s size=%s bytes path=%s",
            media_id, mime_type, len(file_bytes), file_path
        )
        return relative_url

    except Exception as exc:
        logger.error("download_and_save_media failed | media_id=%s error=%s", media_id, exc)
        return None


def _get_media_download_url(media_id: str) -> Optional[str]:
    """
    Appelle l'API Meta pour récupérer l'URL de téléchargement du media.
    GET https://graph.facebook.com/v20.0/{media_id}
    """
    try:
        url = f"https://graph.facebook.com/v20.0/{media_id}"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}",
        }
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("url")
    except Exception as exc:
        logger.error("_get_media_download_url failed | media_id=%s error=%s", media_id, exc)
        return None


def _download_file(url: str) -> Optional[bytes]:
    """Télécharge le fichier depuis l'URL signée Meta."""
    try:
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}",
        }
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.error("_download_file failed | url=%s error=%s", url, exc)
        return None


def get_media_absolute_url(relative_url: str, request=None) -> str:
    """
    Convertit une URL relative en URL absolue.
    Utilisé pour l'envoi dans le dashboard.
    """
    if not relative_url:
        return ""
    if relative_url.startswith("http"):
        return relative_url
    
    # Utiliser SITE_URL des settings si défini
    base = getattr(settings, "SITE_URL", "")
    if not base and request:
        base = request.build_absolute_uri("/").rstrip("/")
    
    return f"{base}{relative_url}"
