"""Orchestrates planner, sandbox tools, and final analysis using an LLM."""

from __future__ import annotations

import json
from typing import Any, Optional

from shared.tool_catalog import allowed_tool_names, load_tool_entries

from agent_controller.config import Settings
from agent_controller.llm_client import LLMClient, extract_text
from agent_controller.images import sanitize_chat_images
from agent_controller.models import ChatRequest
from agent_controller.planner import (
    KUBERNETES_KEYWORDS,
    default_wide_tool_plan,
)
from agent_controller.prompt_modes import (
    ALLOWED_PROMPT_MODES,
    focus_instruction_block,
    normalize_prompt_mode,
)
from agent_controller.prompts import load_prompt_template
from agent_controller.sandbox_client import SandboxClient
from agent_controller.text_utils import pack_tool_results_payload
from agent_controller.tool_summaries import build_executive_summary

TOOL_CATALOG: list[dict[str, Any]] = load_tool_entries()
AVAILABLE_TOOLS = allowed_tool_names(TOOL_CATALOG)


class ChatOrchestrator:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm: Optional[LLMClient] = None,
        sandbox: Optional[SandboxClient] = None,
    ):
        self.settings = settings or Settings()
        self.llm = llm or LLMClient(self.settings)
        self.sandbox = sandbox or SandboxClient(self.settings)

    def chat_metadata(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "provider": self.settings.llm_provider,
            "api_style": self.settings.llm_api_style,
            "model": self.settings.llm_model,
            "api_base_display": self.settings.llm_display_api,
            "supports_post": True,
            "supports_images": True,
            "max_chat_images": self.settings.max_chat_images,
            "max_image_bytes": self.settings.max_image_bytes,
            "prompt_modes": sorted(ALLOWED_PROMPT_MODES),
        }

    def handle_chat(self, request: ChatRequest) -> dict[str, Any]:
        try:
            return self._handle_chat_inner(request)
        except Exception as e:
            return {"error": str(e)}

    def _handle_chat_inner(self, request: ChatRequest) -> dict[str, Any]:
        inline_visuals = sanitize_chat_images(
            request.images,
            self.settings.max_chat_images,
            self.settings.max_image_bytes,
        )
        has_screenshots = len(inline_visuals) > 0
        user_msg_stripped = (request.message or "").strip()
        effective_mode = normalize_prompt_mode(request.prompt_mode)
        focus_extra = focus_instruction_block(effective_mode)
        focus_section = ""
        if focus_extra.strip():
            focus_section = f"""

=========================================================
USER SELECTED FOCUS (bias tool choice and analysis toward this)
=========================================================

{focus_extra.strip()}

"""
        prompt_focus_separator = (
            focus_section if focus_section else "\n\n"
        )
        screenshot_primary_question = (
            has_screenshots and len(user_msg_stripped) < 100
        )
        visual_planner_intro = ""
        if has_screenshots:
            visual_planner_intro = load_prompt_template(
                "visual_input_block.txt"
            )
        planner_body = load_prompt_template("planner_tool_system.txt")
        planner_body = (
            planner_body.replace(
                "<<<TOOL_CATALOG_JSON>>>",
                json.dumps(TOOL_CATALOG, indent=2),
            )
            .replace("<<<PROMPT_FOCUS_SEPARATOR>>>", prompt_focus_separator)
            .replace("<<<USER_MESSAGE>>>", request.message or "")
        )
        tool_prompt = visual_planner_intro + planner_body
        tool_decision = self.llm.generate(tool_prompt, inline_visuals)
        if tool_decision.get("error"):
            return {
                "error": tool_decision.get("error"),
                "details": tool_decision.get("raw_response", ""),
            }
        decision_text = extract_text(
            tool_decision,
            self.settings.llm_api_style,
        )
        print("Tool decision:")
        print(decision_text)
        try:
            decision_json = json.loads(decision_text)
        except Exception:
            print("Failed to parse tool decision JSON")
            message_lower = request.message.lower()
            should_use_tools = has_screenshots or any(
                kw in message_lower for kw in KUBERNETES_KEYWORDS
            )
            if should_use_tools:
                decision_json = {
                    "needs_tools": True,
                    "tool_calls": default_wide_tool_plan(),
                }
            else:
                decision_json = {"needs_tools": False}
        needs_tools = decision_json.get("needs_tools", False)
        if has_screenshots and (
            (not needs_tools)
            or (not decision_json.get("tool_calls"))
        ):
            needs_tools = True
            decision_json["needs_tools"] = True
            if not decision_json.get("tool_calls"):
                decision_json["tool_calls"] = default_wide_tool_plan()
        if not needs_tools:
            normal_tpl = load_prompt_template("normal_conversation.txt")
            normal_prompt = (
                normal_tpl.replace(
                    "<<<PROMPT_FOCUS_SEPARATOR>>>",
                    prompt_focus_separator.rstrip(),
                ).replace("<<<USER_MESSAGE>>>", request.message or "")
            )
            response = self.llm.generate(normal_prompt, inline_visuals)
            if response.get("error"):
                return {
                    "error": response.get("error"),
                    "details": response.get("raw_response", ""),
                }
            return {
                "mode": "conversation",
                "response": extract_text(
                    response,
                    self.settings.llm_api_style,
                ),
            }
        tool_results: list[dict[str, Any]] = []
        tool_calls = decision_json.get("tool_calls", [])
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool")
            arguments = tool_call.get("arguments", {})
            if tool_name not in AVAILABLE_TOOLS:
                continue
            print(f"Executing tool: {tool_name}")
            try:
                status_code, text, parsed_result = self.sandbox.execute(
                    tool_name, arguments
                )
                print("Sandbox status code:", status_code)
                print("Sandbox raw response:")
                print(text)
                if parsed_result is None:
                    parsed_result = {
                        "error": "Invalid JSON response from sandbox",
                        "raw_response": text,
                    }
                tool_results.append(
                    {"tool": tool_name, "result": parsed_result}
                )
            except Exception as tool_error:
                tool_results.append(
                    {
                        "tool": tool_name,
                        "result": {"error": str(tool_error)},
                    }
                )
        summary = build_executive_summary(tool_results)
        investigation_payload = pack_tool_results_payload(
            tool_results,
            self.settings.max_tool_context_chars,
        )
        visual_scope_notice = ""
        if screenshot_primary_question:
            visual_scope_notice = load_prompt_template(
                "analysis_scope_screenshot_first.txt"
            )
        elif inline_visuals:
            visual_scope_notice = load_prompt_template(
                "analysis_scope_visuals_present.txt"
            )
        analysis_visual_intro = ""
        if inline_visuals:
            intro_tpl = load_prompt_template(
                "analysis_visual_intro_wrap.txt"
            )
            analysis_visual_intro = intro_tpl.replace(
                "<<<VISUAL_SCOPE_NOTICE>>>",
                visual_scope_notice,
            )
        analysis_body = load_prompt_template("analysis_body.txt")
        summary_text = "\n".join(summary)
        analysis_body = (
            analysis_body.replace(
                "<<<PROMPT_FOCUS_SEPARATOR>>>",
                prompt_focus_separator.rstrip(),
            )
            .replace("<<<USER_MESSAGE>>>", request.message or "")
            .replace("<<<SUMMARY_TEXT>>>", summary_text)
            .replace("<<<INVESTIGATION_PAYLOAD>>>", investigation_payload)
        )
        analysis_prompt = analysis_visual_intro + analysis_body
        analysis_response = self.llm.generate(
            analysis_prompt,
            inline_visuals,
        )
        if analysis_response.get("error"):
            return {
                "error": analysis_response.get("error"),
                "details": analysis_response.get("raw_response", ""),
                "summary": summary,
            }
        final_response = extract_text(
            analysis_response,
            self.settings.llm_api_style,
        )
        return {
            "mode": "tool_analysis",
            "summary": summary,
            "response": final_response,
        }
