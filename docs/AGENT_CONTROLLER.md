# `agent_controller/` Folder

This is the main backend service that handles chat conversations with the LLM.

## Purpose

The controller receives chat messages from the frontend, orchestrates the conversation with a configurable LLM provider (the LLM decides if tools are needed), calls the sandbox to run tools if requested, and returns the final answer to the frontend.

## Files

### `agent_controller/__init__.py`
- Marks `agent_controller` as a Python package.
- Lets other code import from this folder cleanly.

### `agent_controller/main.py`
- FastAPI app entry point.
- Creates the HTTP server that the frontend talks to.
- Registers the `/chat` route from `routes/`.

### `agent_controller/chat_orchestrator.py`
- Core orchestration logic.
- Sends messages to the configured LLM; the LLM decides if tools are needed (returns `needs_tools: true/false` in JSON).
- If the LLM says yes, calls the sandbox to execute the requested tools.
- Sends tool results back to the LLM for final synthesis and answer.
- This is the brain of the entire flow.

### `agent_controller/config.py`
- Runtime configuration: API keys, model names, URLs.
- Reads environment variables for settings like `LLM_API_KEY`, `LLM_MODEL`, and `LLM_API_STYLE`.
- Provides defaults for local/dev testing.

### `agent_controller/llm_client.py`
- Wraps provider-specific API calls behind one interface.
- Supports multiple API styles (currently Gemini and OpenAI-compatible chat).
- Handles parsing and retries.

### `agent_controller/variables.py`
- Central editable string values for provider, model, API base URL, API key, and timeouts.
- Makes local tuning easy without editing logic code.
- Works with env var overrides for production deployment.

### `agent_controller/sandbox_client.py`
- HTTP client that calls `http://agent-sandbox/execute`.
- Sends tool requests to the sandbox and gets back results.
- Handles communication between controller and sandbox.

### `agent_controller/planner.py`
- Builds prompts that list available tools for the LLM to consider.
- Maps user keywords to relevant tools (e.g., "cost" → cost tools, "pods" → workload tools).
- Provides hints about which tools might be useful (the LLM makes the final decision).

### `agent_controller/prompt_modes.py`
- Defines different conversation modes (e.g., "cost", "security", "reliability").
- Each mode tweaks the prompt to focus on different aspects of the cluster.
- Normalizes and validates mode names.

### `agent_controller/prompts.py`
- Loads prompt templates from `prompt_templates/` folder.
- Provides text building blocks for different parts of the conversation.

### `agent_controller/models.py`
- Pydantic data models for request/response validation.
- Defines the shape of chat messages and metadata.

### `agent_controller/images.py`
- Sanitizes and processes image uploads from the frontend.
- Prepares images for the configured LLM payload format.

### `agent_controller/text_utils.py`
- String manipulation utilities: truncation, formatting, JSON packing.

### `agent_controller/tool_summaries.py`
- Converts raw tool results into human-readable executive summaries.
- Makes tool output clearer for the LLM and frontend.

### `agent_controller/routes/`
- Contains HTTP route handlers.
- `routes/chat.py`: Defines two endpoints:
  - `GET /chat`: Returns metadata (LLM model name, available prompt modes, image support).
  - `POST /chat`: Accepts a chat message (with optional image), orchestrates the full flow, returns the analysis result.

### `agent_controller/prompt_modes/`
- Text files for each conversation mode (e.g., "cost.txt", "security.txt").
- Stored as separate files so they can be updated without changing Python code.

### `agent_controller/prompt_templates/`
- Template text files for different conversation scenarios.
- Examples: "normal_conversation.txt", "multistep_analysis.txt".
- Reused across multiple prompts to keep things DRY.

## How it fits in the project

- Receives HTTP requests from the frontend at `/chat`.
- Orchestrates the conversation flow using a configurable LLM provider and the sandbox.
- Returns final answers to the frontend.
- The controller is the most stateful and business-logic-heavy part of the app.

## Simple takeaway

- Keep this folder.
- It is the main logic layer of the entire platform.
