"""Provider-agnostic LLM client supporting multiple API styles."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import requests

from agent_controller.config import Settings
from agent_controller.images import (
    build_gemini_parts_from_inline,
    build_openai_content_from_inline,
)


def extract_text(llm_response: dict, api_style: str) -> str:
    style = (api_style or "").strip().lower()
    if style == "gemini":
        return _extract_text_gemini(llm_response)
    if style in {"openai", "openai_chat"}:
        return _extract_text_openai_chat(llm_response)
    return ""


def _extract_text_gemini(gemini_response: dict) -> str:
    try:
        print("LLM parsed response (gemini):")
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
        print("Extract text error (gemini):", str(e))
        return ""


def _extract_text_openai_chat(openai_response: dict) -> str:
    try:
        print("LLM parsed response (openai_chat):")
        print(json.dumps(openai_response, indent=2))
        if openai_response.get("error"):
            return ""
        choices = openai_response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        chunks.append(str(text))
            return "\n".join(chunks).strip()
        return ""
    except Exception as e:
        print("Extract text error (openai_chat):", str(e))
        return ""


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or Settings()

    def generate(
        self,
        prompt: str,
        inline_images: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        inlined = inline_images if inline_images is not None else []
        style = (self._settings.llm_api_style or "").strip().lower()
        max_retries = max(self._settings.llm_max_retries, 1)
        started_at = time.time()
        last_status_code: Optional[int] = None
        last_response_body = ""
        last_exception = ""
        last_error_type = "unknown"
        for attempt in range(max_retries):
            try:
                request_args = self._build_request(style, prompt, inlined)
                response = requests.post(
                    request_args["url"],
                    headers=request_args["headers"],
                    params=request_args.get("params"),
                    json=request_args["body"],
                    timeout=self._settings.llm_timeout,
                )
                last_status_code = response.status_code
                last_response_body = response.text
                print("LLM status code:", response.status_code)
                print("LLM raw response:")
                print(response.text)
                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as json_error:
                        elapsed_ms = int((time.time() - started_at) * 1000)
                        return {
                            "error": "Failed to parse LLM JSON",
                            "error_type": "json_parse_error",
                            "attempts": attempt + 1,
                            "elapsed_ms": elapsed_ms,
                            "provider": self._settings.llm_provider,
                            "api_style": self._settings.llm_api_style,
                            "model": self._settings.llm_model,
                            "raw_response": response.text,
                            "exception": str(json_error),
                        }
                if (
                    response.status_code
                    in self._settings.llm_retryable_status_codes
                ):
                    last_error_type = "retryable_http_error"
                    print(
                        "Retryable LLM error:",
                        response.status_code,
                    )
                    time.sleep(2**attempt)
                    continue
                elapsed_ms = int((time.time() - started_at) * 1000)
                last_error_type = "http_error"
                return {
                    "error": f"LLM API returned {response.status_code}",
                    "error_type": last_error_type,
                    "attempts": attempt + 1,
                    "elapsed_ms": elapsed_ms,
                    "provider": self._settings.llm_provider,
                    "api_style": self._settings.llm_api_style,
                    "model": self._settings.llm_model,
                    "last_status_code": response.status_code,
                    "raw_response": response.text,
                }
            except requests.Timeout as request_error:
                last_error_type = "timeout"
                last_exception = str(request_error)
                print("LLM request timed out:", last_exception)
                time.sleep(2**attempt)
            except requests.RequestException as request_error:
                last_error_type = "request_exception"
                last_exception = str(request_error)
                print("LLM request failed:", last_exception)
                time.sleep(2**attempt)
            except Exception as request_error:
                last_error_type = "unexpected_exception"
                last_exception = str(request_error)
                print("LLM request failed:", last_exception)
                time.sleep(2**attempt)
        elapsed_ms = int((time.time() - started_at) * 1000)
        return {
            "error": "LLM API failed after retries",
            "error_type": last_error_type,
            "attempts": max_retries,
            "elapsed_ms": elapsed_ms,
            "provider": self._settings.llm_provider,
            "api_style": self._settings.llm_api_style,
            "model": self._settings.llm_model,
            "last_status_code": last_status_code,
            "last_exception": last_exception,
            "raw_response": last_response_body,
        }

    def _build_request(
        self,
        api_style: str,
        prompt: str,
        inline_images: list[dict],
    ) -> dict[str, Any]:
        style = api_style.strip().lower()
        if style == "gemini":
            return self._build_gemini_request(prompt, inline_images)
        if style in {"openai", "openai_chat"}:
            return self._build_openai_chat_request(prompt, inline_images)
        raise ValueError(
            "Unsupported LLM_API_STYLE. Use 'gemini' or 'openai_chat'."
        )

    def _build_gemini_request(
        self,
        prompt: str,
        inline_images: list[dict],
    ) -> dict[str, Any]:
        parts = build_gemini_parts_from_inline(prompt, inline_images)
        endpoint = self._settings.llm_endpoint_path.strip()
        if not endpoint:
            endpoint = f"models/{self._settings.llm_model}:generateContent"
        base = self._settings.llm_base_url.rstrip("/")
        url = f"{base}/{endpoint.lstrip('/')}"
        params: dict[str, str] | None = None
        if self._settings.llm_api_key:
            params = {"key": self._settings.llm_api_key}
        return {
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "params": params,
            "body": {"contents": [{"parts": parts}]},
        }

    def _build_openai_chat_request(
        self,
        prompt: str,
        inline_images: list[dict],
    ) -> dict[str, Any]:
        content = build_openai_content_from_inline(prompt, inline_images)
        endpoint = self._settings.llm_endpoint_path.strip() or "chat/completions"
        base = self._settings.llm_base_url.rstrip("/")
        url = f"{base}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if self._settings.llm_api_key:
            auth_value = self._settings.llm_api_key
            if self._settings.llm_auth_scheme:
                auth_value = (
                    f"{self._settings.llm_auth_scheme} {self._settings.llm_api_key}"
                )
            headers[self._settings.llm_auth_header] = auth_value
        return {
            "url": url,
            "headers": headers,
            "body": {
                "model": self._settings.llm_model,
                "messages": [{"role": "user", "content": content}],
            },
        }
