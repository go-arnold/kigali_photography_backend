import logging
import os
import uuid
from pathlib import Path
from typing import Optional
 
import httpx
from django.conf import settings
 
logger = logging.getLogger(__name__)
 
# Dossier local temporaire (pour conversion audio)
MEDIA_DIR = Path(settings.MEDIA_ROOT) / "whatsapp"
MEDIA_URL = getattr(settings, "MEDIA_URL", "/media/")
 
MIME_EXTENSIONS = {
    "image/jpeg":       ".jpg",
    "image/png":        ".png",
    "image/webp":       ".webp",
    "image/gif":        ".gif",
    "audio/ogg":        ".ogg",
    "audio/mpeg":       ".mp3",
    "audio/mp4":        ".m4a",
    "audio/aac":        ".aac",
    "audio/amr":        ".amr",
    "audio/webm":       ".webm",
    "application/pdf":  ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain":       ".txt",
}
 
WA_AUDIO_SUPPORTED = {"audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"}
 
 
# ── Supabase helpers ──────────────────────────────────────────────────────────
 
def _supabase_upload(file_path: Path, dest_filename: str, mime_type: str) -> Optional[str]:
    """
    Upload un fichier vers Supabase Storage et retourne l\'URL publique.
    Retourne None si l\'upload échoue.
    """
    try:
        supabase_url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
        supabase_key = getattr(settings, "SUPABASE_KEY", "")
        bucket       = getattr(settings, "SUPABASE_BUCKET", "media")
 
        if not supabase_url or not supabase_key:
            logger.warning("SUPABASE_URL or SUPABASE_KEY not configured — cannot upload")
            return None
 
        upload_url = f"{supabase_url}/storage/v1/object/{bucket}/whatsapp/{dest_filename}"
 
        with open(file_path, "rb") as f:
            file_bytes = f.read()
 
        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": mime_type,
            "x-upsert": "true",   # écrase si existe déjà
        }
 
        with httpx.Client(timeout=30) as client:
            resp = client.post(upload_url, content=file_bytes, headers=headers)
 
        if resp.status_code not in (200, 201):
            logger.error(
                "Supabase upload failed | status=%s body=%s",
                resp.status_code, resp.text[:200]
            )
            return None
 
        # URL publique : supabase.co/storage/v1/object/public/{bucket}/whatsapp/{filename}
        public_url = f"{supabase_url}/storage/v1/object/public/{bucket}/whatsapp/{dest_filename}"
        logger.info("Supabase upload OK | %s → %s", file_path.name, public_url)
        return public_url
 
    except Exception as exc:
        logger.error("_supabase_upload error: %s", exc)
        return None
 
 
# ── Download from Meta ────────────────────────────────────────────────────────
 
def download_and_save_media(
    media_id: str,
    mime_type: str = "",
    filename: str = "",
) -> Optional[str]:
    """
    Télécharge un media WhatsApp, le sauvegarde localement ET l\'uploade vers Supabase.
    Retourne l\'URL publique Supabase (ou URL locale en fallback).
    """
    try:
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
 
        download_url = _get_media_download_url(media_id)
        if not download_url:
            return None
 
        file_bytes = _download_file(download_url)
        if not file_bytes:
            return None
 
        ext = MIME_EXTENSIONS.get(mime_type, "")
        if not ext and filename:
            ext = Path(filename).suffix
        if not ext:
            ext = ".bin"
 
        unique_name = f"{uuid.uuid4().hex[:16]}{ext}"
        file_path = MEDIA_DIR / unique_name
 
        with open(file_path, "wb") as f:
            f.write(file_bytes)
 
        logger.info("Media saved locally | %s (%s bytes)", unique_name, len(file_bytes))
 
        # ← NOUVEAU : uploader vers Supabase
        public_url = _supabase_upload(file_path, unique_name, mime_type or "application/octet-stream")
        if public_url:
            return public_url
 
        # Fallback : URL locale (fonctionne pour dashboard mais pas WhatsApp)
        site_url = getattr(settings, "SITE_URL", "").rstrip("/")
        return f"{site_url}{MEDIA_URL}whatsapp/{unique_name}"
 
    except Exception as exc:
        logger.error("download_and_save_media failed | media_id=%s: %s", media_id, exc)
        return None
 
 
# ── Audio conversion ──────────────────────────────────────────────────────────
 
def convert_audio_for_whatsapp(file_path: Path, original_mime: str) -> tuple[Path, str]:
    """
    Convertit webm → ogg si ffmpeg disponible.
    WhatsApp supporte: audio/aac, audio/mp4, audio/mpeg, audio/amr, audio/ogg
    """
    if original_mime in WA_AUDIO_SUPPORTED:
        return file_path, original_mime
 
    if original_mime in ("audio/webm", "video/webm") or file_path.suffix == ".webm":
        ogg_path = file_path.with_suffix(".ogg")
        try:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(file_path),
                 "-vn", "-acodec", "libopus", "-b:a", "128k", str(ogg_path)],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0 and ogg_path.exists():
                logger.info("Audio converted webm→ogg | %s", ogg_path.name)
                return ogg_path, "audio/ogg"
            else:
                logger.warning("ffmpeg failed: %s", result.stderr.decode()[:200])
        except FileNotFoundError:
            logger.warning("ffmpeg not found — copying as .ogg")
        except Exception as exc:
            logger.warning("Audio conversion error: %s", exc)
 
        # Fallback: copier en .ogg
        try:
            import shutil
            shutil.copy2(str(file_path), str(ogg_path))
            return ogg_path, "audio/ogg"
        except Exception as exc:
            logger.warning("Audio copy failed: %s", exc)
 
    return file_path, original_mime
 
 
def prepare_media_for_sending(file_path: Path, mime_type: str) -> tuple[Path, str]:
    """
    Prépare un fichier avant envoi WhatsApp.
    Pour audio: convertit si nécessaire, puis uploade vers Supabase.
    Retourne (send_path, send_mime, public_url).
    """
    if mime_type.startswith("audio/"):
        send_path, send_mime = convert_audio_for_whatsapp(file_path, mime_type)
    else:
        send_path, send_mime = file_path, mime_type
 
    return send_path, send_mime
 
 
def get_public_url(file_path: Path, mime_type: str) -> str:
    """
    Upload le fichier vers Supabase et retourne l\'URL publique.
    Utilisé pour l\'envoi WhatsApp depuis le dashboard.
    """
    public_url = _supabase_upload(file_path, file_path.name, mime_type)
    if public_url:
        return public_url
 
    # Fallback URL locale
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{site_url}{MEDIA_URL}whatsapp/{file_path.name}"
 
 
def _get_media_download_url(media_id: str) -> Optional[str]:
    try:
        url = f"https://graph.facebook.com/v20.0/{media_id}"
        headers = {"Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}"}
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("url")
    except Exception as exc:
        logger.error("_get_media_download_url failed | media_id=%s: %s", media_id, exc)
        return None
 
 
def _download_file(url: str) -> Optional[bytes]:
    try:
        headers = {"Authorization": f"Bearer {settings.WHATSAPP['ACCESS_TOKEN']}"}
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.error("_download_file failed: %s", exc)
        return None