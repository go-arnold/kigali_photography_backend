"""
Media Service — Supabase Storage
==================================
Stocke les fichiers media sur Supabase Storage (persistant entre déploiements).
Le filesystem local Koyeb est éphémère — tout fichier local disparaît au redéploiement.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET_NAME = "whatsappMedia"

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
    "audio/webm": ".webm",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}

WA_AUDIO_SUPPORTED = {"audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"}


def _get_supabase():
    """Retourne le client Supabase."""
    from supabase import create_client
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def upload_to_supabase(file_bytes: bytes, filename: str, mime_type: str) -> Optional[str]:
    """
    Upload un fichier sur Supabase Storage.
    Retourne l'URL publique ou None si échec.
    """
    try:
        supabase = _get_supabase()
        
        # Upload avec upsert=True pour éviter les conflits
        supabase.storage.from_(BUCKET_NAME).upload(
            path=filename,
            file=file_bytes,
            file_options={
                "content-type": mime_type or "application/octet-stream",
                "upsert": "true",
            },
        )
        
        # Récupérer l'URL publique
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        logger.info("Uploaded to Supabase | file=%s size=%s", filename, len(file_bytes))
        return public_url
        
    except Exception as exc:
        logger.error("Supabase upload failed | file=%s error=%s", filename, exc)
        return None


def download_and_save_media(
    media_id: str,
    mime_type: str = "",
    filename: str = "",
) -> Optional[str]:
    """
    Télécharge un media WhatsApp et l'upload sur Supabase Storage.
    Retourne l'URL publique Supabase, ou None si échec.
    """
    try:
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
            ext = _guess_extension_from_bytes(file_bytes)

        unique_name = f"{uuid.uuid4().hex[:16]}{ext}"
        
        # Déduire le MIME si absent
        if not mime_type:
            mime_type = _guess_mime_from_bytes(file_bytes)

        public_url = upload_to_supabase(file_bytes, unique_name, mime_type)
        
        if public_url:
            logger.info(
                "Media saved to Supabase | media_id=%s mime=%s size=%s url=%s",
                media_id, mime_type, len(file_bytes), public_url
            )
        
        return public_url

    except Exception as exc:
        logger.error("download_and_save_media failed | media_id=%s error=%s", media_id, exc)
        return None


def prepare_agent_media_for_whatsapp(
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
) -> tuple[Optional[str], str, str]:
    """
    Prépare un fichier envoyé par l'agent pour WhatsApp.
    Convertit l'audio si nécessaire, upload sur Supabase.
    
    Retourne (public_url, final_mime_type, msg_type).
    """
    # Conversion audio si nécessaire
    final_bytes = file_bytes
    final_mime = mime_type
    
    if mime_type.startswith("audio/") and mime_type not in WA_AUDIO_SUPPORTED:
        converted = _convert_audio_bytes(file_bytes, mime_type)
        if converted:
            final_bytes, final_mime = converted

    # Déterminer le type de message
    if final_mime.startswith("image/"):
        msg_type = "image"
        ext = MIME_EXTENSIONS.get(final_mime, ".jpg")
    elif final_mime.startswith("audio/"):
        msg_type = "audio"
        ext = MIME_EXTENSIONS.get(final_mime, ".ogg")
    else:
        msg_type = "document"
        ext = Path(original_filename).suffix or ".bin"

    unique_name = f"agent_{uuid.uuid4().hex[:12]}{ext}"
    public_url = upload_to_supabase(final_bytes, unique_name, final_mime)
    
    return public_url, final_mime, msg_type


def _convert_audio_bytes(file_bytes: bytes, original_mime: str) -> Optional[tuple[bytes, str]]:
    """
    Convertit les bytes audio en ogg/opus via ffmpeg.
    Retourne (converted_bytes, new_mime) ou None si échec.
    """
    import tempfile
    import subprocess
    
    # Extension source
    src_ext = ".webm" if "webm" in original_mime else ".bin"
    
    try:
        with tempfile.NamedTemporaryFile(suffix=src_ext, delete=False) as src_f:
            src_f.write(file_bytes)
            src_path = src_f.name
        
        dst_path = src_path.replace(src_ext, ".ogg")
        
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-vn",
             "-acodec", "libopus", "-b:a", "128k", dst_path],
            capture_output=True, timeout=30,
        )
        
        if result.returncode == 0 and os.path.exists(dst_path):
            with open(dst_path, "rb") as f:
                converted = f.read()
            logger.info("Audio converted to ogg | size=%s", len(converted))
            return converted, "audio/ogg"
        else:
            logger.warning("ffmpeg failed: %s", result.stderr.decode()[:200])
            # Fallback: renommer en .ogg (fonctionne sur la plupart des clients)
            return file_bytes, "audio/ogg"
            
    except FileNotFoundError:
        logger.warning("ffmpeg not found — sending audio as-is with ogg mime")
        return file_bytes, "audio/ogg"
    except Exception as exc:
        logger.warning("Audio conversion error: %s", exc)
        return None
    finally:
        for p in [src_path, dst_path if 'dst_path' in locals() else ""]:
            try:
                if p and os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


def _guess_extension_from_bytes(data: bytes) -> str:
    if data[:3] == b'\xff\xd8\xff':
        return ".jpg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return ".png"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return ".webp"
    if data[:4] == b'OggS':
        return ".ogg"
    if data[:3] == b'ID3' or data[:2] == b'\xff\xfb':
        return ".mp3"
    if data[:4] == b'%PDF':
        return ".pdf"
    return ".jpg"  # fallback image plutôt que .bin


def _guess_mime_from_bytes(data: bytes) -> str:
    if data[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:4] == b'OggS':
        return "audio/ogg"
    if data[:3] == b'ID3':
        return "audio/mpeg"
    if data[:4] == b'%PDF':
        return "application/pdf"
    return "image/jpeg"


def get_public_url(relative_url: str) -> str:
    """Rétrocompatibilité — retourne l'URL telle quelle si déjà absolue."""
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