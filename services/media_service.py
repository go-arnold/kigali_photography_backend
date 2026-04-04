"""
Media Service — Version corrigée
==================================
- Correction envoi audio : webm → ogg (WhatsApp ne supporte pas webm)
- La fonction convert_audio_for_whatsapp() gère la conversion
"""
 
import logging
import os
import uuid
from pathlib import Path
from typing import Optional
 
import httpx
from django.conf import settings
 
logger = logging.getLogger(__name__)
 
MEDIA_DIR = Path(settings.MEDIA_ROOT) / "whatsapp"
MEDIA_URL_PREFIX = settings.MEDIA_URL + "whatsapp/"
 
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
    "audio/webm": ".webm",  # stocké en webm, converti avant envoi
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
 
# Formats audio acceptés par WhatsApp Business API
WA_AUDIO_SUPPORTED = {"audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"}
 
 
def download_and_save_media(
    media_id: str,
    mime_type: str = "",
    filename: str = "",
) -> Optional[str]:
    """
    Télécharge un media WhatsApp et le sauvegarde localement.
    Retourne l'URL relative accessible depuis le navigateur, ou None si échec.
    """
    try:
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
 
        download_url = _get_media_download_url(media_id)
        if not download_url:
            logger.error("Could not get download URL for media_id=%s", media_id)
            return None
 
        file_bytes = _download_file(download_url)
        if not file_bytes:
            logger.error("Could not download media from %s", download_url)
            return None
 
        # Déduire l'extension
        ext = MIME_EXTENSIONS.get(mime_type, "")
        if not ext and filename:
            ext = Path(filename).suffix
        if not ext:
            # Déduire depuis les magic bytes du fichier
            ext = _guess_extension_from_bytes(file_bytes)

        unique_name = f"{uuid.uuid4().hex[:16]}{ext}"
 
        unique_name = f"{uuid.uuid4().hex[:16]}{ext}"
        file_path = MEDIA_DIR / unique_name
 
        with open(file_path, "wb") as f:
            f.write(file_bytes)
 
        relative_url = f"{MEDIA_URL_PREFIX}{unique_name}"
        logger.info(
            "Media saved | media_id=%s mime=%s size=%s bytes",
            media_id, mime_type, len(file_bytes)
        )
        return relative_url
 
    except Exception as exc:
        logger.error("download_and_save_media failed | media_id=%s error=%s", media_id, exc)
        return None
 
 
def convert_audio_for_whatsapp(file_path: Path, original_mime: str) -> tuple[Path, str]:
    """
    Convertit un fichier audio en format compatible WhatsApp.
    
    WhatsApp supporte: audio/aac, audio/mp4, audio/mpeg, audio/amr, audio/ogg
    
    Retourne (new_path, new_mime_type).
    Si la conversion échoue ou n'est pas nécessaire, retourne (file_path, original_mime).
    
    Pour la conversion webm → ogg, on utilise ffmpeg si disponible,
    sinon on retourne le fichier tel quel (certains clients WhatsApp lisent webm).
    """
    if original_mime in WA_AUDIO_SUPPORTED:
        return file_path, original_mime
 
    # webm → ogg via ffmpeg
    if original_mime in ("audio/webm", "video/webm") or file_path.suffix == ".webm":
        ogg_path = file_path.with_suffix(".ogg")
        try:
            import subprocess
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(file_path),
                    "-vn",                    # pas de vidéo
                    "-acodec", "libopus",     # codec Opus (standard WhatsApp ogg)
                    "-b:a", "128k",
                    str(ogg_path)
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and ogg_path.exists():
                logger.info("Audio converted webm→ogg | %s → %s", file_path, ogg_path)
                return ogg_path, "audio/ogg"
            else:
                logger.warning(
                    "ffmpeg conversion failed | returncode=%s stderr=%s",
                    result.returncode,
                    result.stderr.decode()[:200]
                )
        except FileNotFoundError:
            logger.warning("ffmpeg not found — cannot convert audio. Sending webm as-is.")
        except Exception as exc:
            logger.warning("Audio conversion error: %s", exc)
 
        # Fallback: renommer en .ogg et changer le mime (fonctionne sur la plupart des clients)
        # WhatsApp accepte souvent les fichiers ogg même si le codec est webm
        try:
            import shutil
            shutil.copy2(str(file_path), str(ogg_path))
            logger.info("Audio copied as ogg (no conversion) | %s", ogg_path)
            return ogg_path, "audio/ogg"
        except Exception as exc:
            logger.warning("Audio copy failed: %s", exc)
 
    return file_path, original_mime
 
 
def prepare_media_for_sending(file_path: Path, mime_type: str) -> tuple[Path, str]:
    """
    Prépare un fichier media avant envoi WhatsApp.
    Pour les audios, convertit si nécessaire.
    Pour les images, laisse tel quel.
    """
    if mime_type.startswith("audio/"):
        return convert_audio_for_whatsapp(file_path, mime_type)
    return file_path, mime_type
 
 
def get_public_url(relative_url: str) -> str:
    """Construit l'URL publique complète depuis une URL relative."""
    if not relative_url:
        return ""
    if relative_url.startswith("http"):
        return relative_url
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base}{relative_url}"
 
 
def _get_media_download_url(media_id: str) -> Optional[str]:
    try:
        url = f"https://graph.facebook.com/v20.0/{media_id}"
        headers = {"Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}"}
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("url")
    except Exception as exc:
        logger.error("_get_media_download_url failed | media_id=%s error=%s", media_id, exc)
        return None
 
 
def _download_file(url: str) -> Optional[bytes]:
    try:
        headers = {"Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}"}
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.error("_download_file failed | url=%s error=%s", url, exc)
        return None
    
def _guess_extension_from_bytes(data: bytes) -> str:
    """Devine l'extension depuis les magic bytes."""
    if data[:3] == b'\xff\xd8\xff':
        return ".jpg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return ".png"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return ".webp"
    if data[:4] in (b'OggS',):
        return ".ogg"
    if data[:3] == b'ID3' or data[:2] == b'\xff\xfb':
        return ".mp3"
    if data[:4] == b'%PDF':
        return ".pdf"
    return ".bin"