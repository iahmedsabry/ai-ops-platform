"""Pydantic request models for /chat."""

from typing import List, Optional

from pydantic import BaseModel


class ChatImagePart(BaseModel):
    """Single image as base64 (no data: URL prefix required)."""

    mime_type: str
    data: str


class ChatRequest(BaseModel):
    message: str
    images: Optional[List[ChatImagePart]] = None
    prompt_mode: Optional[str] = None
