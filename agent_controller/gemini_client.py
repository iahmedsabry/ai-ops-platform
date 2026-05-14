"""Google Gemini generateContent client."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import requests

from agent_controller.config import Settings
from agent_controller.images import build_gemini_parts_from_inline


def extract_text(gemini_response: dict) -> str:
    try:
        print("Gemini parsed response:")
        print(json.dumps(gemini_response, indent=2))
        if gemini_response.get("error"):
            return ""
        candidates = gemini_response.get("candidates", [])
        if not candidates:
            return ""
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return ""
        chunks = []
        for part in parts:
            fragment = part.get("text")
            if fragment:
                chunks.append(fragment)
        return "\n".join(chunks).strip()
    except Exception as e:
        print("Extract text error:", str(e))
        return ""


class GeminiClient:
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or Settings()

    def generate(
        self,
        prompt: str,
        inline_images: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        inlined = inline_images if inline_images is not None else []
        parts = build_gemini_parts_from_inline(prompt, inlined)
        api_key = os.getenv("GEMINI_API_KEY")
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{self._settings.gemini_model}:generateContent?key={api_key}"
        )
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": parts}]},
                    timeout=self._settings.gemini_timeout,
                )
                print("Gemini status code:", response.status_code)
                print("Gemini raw response:")
                print(response.text)
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as json_error:
                        return {
                            "error": "Failed to parse Gemini JSON",
                            "raw_response": response.text,
                            "exception": str(json_error),
                        }
                if response.status_code in [429, 500, 502, 503, 504]:
                    print(
                        f"Retryable Gemini error: {response.status_code}"
                    )
                    time.sleep(2**attempt)
                    continue
                return {
                    "error": f"Gemini API returned {response.status_code}",
                    "raw_response": response.text,
                }
            except Exception as request_error:
                print("Gemini request failed:", str(request_error))
                time.sleep(2**attempt)
        return {"error": "Gemini API failed after retries"}
