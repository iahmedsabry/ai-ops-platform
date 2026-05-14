# Request flow: `POST /chat`

This traces one chat turn through [`agent_controller/chat_orchestrator.py`](../agent_controller/chat_orchestrator.py).

1. **HTTP**: [`agent_controller/routes/chat.py`](../agent_controller/routes/chat.py) receives a [`ChatRequest`](../agent_controller/models.py) (`message`, optional `images`, optional `prompt_mode`).
2. **Images**: [`sanitize_chat_images`](../agent_controller/images.py) validates base64, MIME type, and size caps.
3. **Focus mode**: [`normalize_prompt_mode` / `focus_instruction_block`](../agent_controller/prompt_modes.py) loads optional text from `prompt_modes/*.txt`.
4. **Planner prompt**: Templates under [`agent_controller/prompt_templates/`](../agent_controller/prompt_templates) are filled with the shared [`TOOL_CATALOG`](../shared/tools.yaml) JSON and the user message. If screenshots exist, the visual preamble block is prepended.
5. **Gemini (planner)**: [`GeminiClient.generate`](../agent_controller/gemini_client.py) returns JSON text describing `needs_tools` and `tool_calls` (or a heuristic fallback if JSON parse fails — see [`planner.py`](../agent_controller/planner.py)).
6. **Conversation short-circuit**: If `needs_tools` is false, a short “normal conversation” template is sent to Gemini and the text reply is returned as `mode: conversation`.
7. **Sandbox**: For each allowed tool name, [`SandboxClient.execute`](../agent_controller/sandbox_client.py) calls `http://agent-sandbox/execute` (overridable via `SANDBOX_EXECUTE_URL`).
8. **Executive summary**: [`build_executive_summary`](../agent_controller/tool_summaries.py) turns each tool’s JSON into short human-readable lines for the model.
9. **Analysis prompt**: Analysis templates (with optional visual guardrails) include the summary, raw tool JSON (packed/truncated via [`pack_tool_results_payload`](../agent_controller/text_utils.py)), and the user message.
10. **Gemini (analysis)**: Final markdown-friendly answer is returned as `mode: tool_analysis`.

Parallel path: **`GET /chat`** returns model metadata and allowed `prompt_modes` for the UI (same module, metadata-only).
