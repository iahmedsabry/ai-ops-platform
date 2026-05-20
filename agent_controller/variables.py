"""Editable string variables for agent-controller runtime behavior.

Keep values here as strings for quick edits without touching code logic.
Environment variables with matching names can still override these defaults.
"""

# LLM provider configuration
LLM_PROVIDER = "github_models"
LLM_API_STYLE = "openai_chat"
LLM_API_KEY = ""
LLM_MODEL = "openai/gpt-5-mini"
LLM_BASE_URL = "https://models.github.ai/inference"
LLM_ENDPOINT_PATH = ""
LLM_DISPLAY_API = "https://models.github.ai/inference"
LLM_TIMEOUT = "90"
LLM_MAX_RETRIES = "3"
LLM_RETRYABLE_STATUS_CODES = "429,500,502,503,504"
LLM_AUTH_HEADER = "Authorization"
LLM_AUTH_SCHEME = "Bearer"

# Agent controller behavior
SANDBOX_TIMEOUT = "90"
MAX_TOOL_CONTEXT_CHARS = "120000"
MAX_CHAT_IMAGES = "6"
MAX_IMAGE_BYTES = "4194304"
SANDBOX_EXECUTE_URL = "http://agent-sandbox/execute"
