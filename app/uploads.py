import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "frontend" / "uploads"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB


async def save_upload(file: UploadFile, prefix: str) -> str:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type. Use JPEG, PNG, GIF, or WebP.")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 5 MB.")

    suffix = Path(file.filename or "upload").suffix.lower() or ".jpg"
    filename = f"{prefix}_{secrets.token_hex(8)}{suffix}"
    (UPLOADS_DIR / filename).write_bytes(data)
    return f"/uploads/{filename}"
