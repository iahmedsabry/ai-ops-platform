"""Validate and normalize chat images before sending to Gemini."""

from __future__ import annotations

import base64
from typing import List, Optional

from agent_controller.models import ChatImagePart

_ALLOWED_IMAGE_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)


def sanitize_chat_images(
    images: Optional[List[ChatImagePart]],
    max_chat_images: int,
    max_image_bytes: int,
) -> list[dict]:
    if not images:
        return []
    cleaned = []
    for img in images[:max_chat_images]:
        mime = (img.mime_type or "").strip().lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in _ALLOWED_IMAGE_MIME:
            continue
        raw = (img.data or "").strip()
        if raw.startswith("data:") and ";base64," in raw:
            raw = raw.split(";base64,", 1)[1]
        raw = "".join(raw.split())
        try:
            blob = base64.b64decode(raw, validate=False)
        except Exception:
            continue
        if len(blob) < 32 or len(blob) > max_image_bytes:
            continue
        b64_out = base64.standard_b64encode(blob).decode("ascii")
        cleaned.append(
            {
                "mime_type": mime,
                "data": b64_out,
            }
        )
    return cleaned


def build_gemini_parts_from_inline(
    prompt: str,
    inline_items: list[dict],
) -> list[dict]:
    parts: list[dict] = [{"text": prompt}]
    for item in inline_items:
        parts.append(
            {
                "inline_data": {
                    "mime_type": item["mime_type"],
                    "data": item["data"],
                }
            }
        )
    return parts
