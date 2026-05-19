# LLM Configuration

This document covers the LLM settings used by agent-controller.

## Quick Start

If you are staying on Gemini, you usually only need to set:

- `LLM_API_KEY` in the Kubernetes Secret.
- `LLM_MODEL` in the GitOps env file if you want a model other than the default.

Everything else already has defaults in [agent_controller/variables.py].

## Where To Edit

Use these files depending on what you want to change:

- Secret value: `LLM_API_KEY` in your local secret manifest, then re-seal it for GitOps.
- GitOps runtime overrides: [agent-controller/app-config.env]
- Code defaults: [agent_controller/variables.py]

Runtime precedence is:

1. Environment variables from Kubernetes.
2. Defaults in [agent_controller/variables.py].

## Required Vs Optional

| Variable | Required | Default | When to change it |
| --- | --- | --- | --- |
| `LLM_API_KEY` | Yes | Empty | Always required for authenticated LLM calls. Store it in a Kubernetes Secret. |
| `LLM_MODEL` | Usually yes | `gemini-2.5-flash` | Change it when you want a different model. |
| `LLM_PROVIDER` | Optional | `gemini` | Change only if you want provider metadata to reflect a different backend. |
| `LLM_API_STYLE` | Optional | `gemini` | Change when switching request format, for example to `openai_chat`. |
| `LLM_BASE_URL` | Optional | `https://generativelanguage.googleapis.com/v1beta` | Change when using a non-default provider endpoint. |
| `LLM_ENDPOINT_PATH` | Optional | Empty | Set only if you need to override the style-based default path. |
| `LLM_DISPLAY_API` | Optional | `https://generativelanguage.googleapis.com/v1beta` | Change only if you want chat metadata to show a different API label. |
| `LLM_TIMEOUT` | Optional | `90` | Change if your provider is slower or you want faster failures. |
| `LLM_MAX_RETRIES` | Optional | `3` | Change if you want more or fewer retry attempts. |
| `LLM_RETRYABLE_STATUS_CODES` | Optional | `429,500,502,503,504` | Change only if your provider uses different transient failure codes. |
| `LLM_AUTH_HEADER` | Optional | `Authorization` | Change only for non-standard auth headers. |
| `LLM_AUTH_SCHEME` | Optional | `Bearer` | Change only if your provider does not use bearer tokens. |

## What Is Mandatory In Practice

### Default Gemini setup

Mandatory:

- `LLM_API_KEY`
- `LLM_MODEL` only if you do not want the default `gemini-2.5-flash`

Optional:

- Everything else, unless your environment requires a non-default endpoint or timeout.

### OpenAI-compatible setup

Mandatory:

- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_API_STYLE=openai_chat`
- `LLM_BASE_URL`

Usually also set:

- `LLM_PROVIDER`
- `LLM_ENDPOINT_PATH=chat/completions`

## Minimal Examples

### Minimal Gemini

Use this when you want the built-in defaults and only need to supply credentials.

Secret:

```yaml
stringData:
  LLM_API_KEY: your_gemini_key
```

Optional GitOps override:

```env
LLM_MODEL=gemini-2.5-flash
LLM_TIMEOUT=90
```

### Minimal OpenAI-compatible Chat API

Use this when the endpoint expects OpenAI chat-completions style requests.

```env
LLM_PROVIDER=openai
LLM_API_STYLE=openai_chat
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_ENDPOINT_PATH=chat/completions
```

Add these only if you want to override the defaults explicitly:

```env
LLM_DISPLAY_API=https://api.openai.com/v1
LLM_AUTH_HEADER=Authorization
LLM_AUTH_SCHEME=Bearer
LLM_TIMEOUT=90
LLM_MAX_RETRIES=3
LLM_RETRYABLE_STATUS_CODES=429,500,502,503,504
```

## Editing Rules

- Keep `LLM_API_KEY` in a Kubernetes Secret, not in Git.
- Put deployment-specific overrides in [ai-ops-platform-gitops/manifests/agent-controller/app-config.env](d:/KAI/ai-ops-platform-gitops/manifests/agent-controller/app-config.env).
- If a value is stable across environments, prefer leaving it in [agent_controller/variables.py](d:/KAI/ai-ops-platform/agent_controller/variables.py) instead of repeating it in GitOps.
- `LLM_DISPLAY_API` is informational only. Actual request routing uses `LLM_BASE_URL` and `LLM_ENDPOINT_PATH`.
- `LLM_ENDPOINT_PATH` can be left empty when you want the client to infer the default path from `LLM_API_STYLE`.

## Common Edit Patterns

### Change only the model

Edit [ai-ops-platform-gitops/manifests/agent-controller/app-config.env](d:/KAI/ai-ops-platform-gitops/manifests/agent-controller/app-config.env):

```env
LLM_MODEL=your-new-model
```

### Rotate the API key

1. Update `LLM_API_KEY` in your local `llm-secret.yaml`.
2. Re-run `kubeseal`.
3. Replace [ai-ops-platform-gitops/manifests/secrets/sealed-llm-secret.yaml](d:/KAI/ai-ops-platform-gitops/manifests/secrets/sealed-llm-secret.yaml).

### Switch providers

Set these together:

```env
LLM_PROVIDER=your-provider-name
LLM_API_STYLE=gemini or openai_chat
LLM_MODEL=your-model
LLM_BASE_URL=https://your-provider-base-url
LLM_API_KEY=your-key
```

Then add `LLM_ENDPOINT_PATH`, `LLM_AUTH_HEADER`, and `LLM_AUTH_SCHEME` only if your provider needs non-default values.
