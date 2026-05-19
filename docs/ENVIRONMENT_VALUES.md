# Environment Values (Agents + Frontend)

This document contains only runtime/deployment values for:

- agent-controller
- agent-sandbox
- frontend

LLM-specific settings are documented separately in `LLM_CONFIGURATION.md`.

## Agent Controller

Primary values file:
- `ai-ops-platform-gitops/manifests/agent-controller/app-config.env`

Values to set per environment:

- `SANDBOX_EXECUTE_URL`: In-cluster URL for sandbox execute endpoint.
- `SANDBOX_TIMEOUT`: Timeout for controller -> sandbox tool calls (seconds).
- `MAX_TOOL_CONTEXT_CHARS`: Max serialized tool payload sent back to LLM.
- `MAX_CHAT_IMAGES`: Max user images accepted in one chat request.
- `MAX_IMAGE_BYTES`: Max allowed size per image.

Notes:
- Keep `SANDBOX_EXECUTE_URL` reachable from the controller namespace.
- LLM model/key/timeouts are not documented here; see `LLM_CONFIGURATION.md`.

## Agent Sandbox

Primary values file:
- `ai-ops-platform-gitops/manifests/agent-sandbox/app-config.env`

Values to set per environment:

- `AWS_REGION`: Region used for most AWS API calls.
- `AWS_BILLING_REGION`: Billing/Cost Explorer region (commonly `us-east-1`).
- `PROMETHEUS_URL`: In-cluster Prometheus base URL.

Notes:
- `AWS_REGION` and `AWS_BILLING_REGION` must align with your AWS account setup.
- `PROMETHEUS_URL` must match Service DNS and namespace in your cluster.

## Frontend

Primary deployment values file:
- `ai-ops-platform-gitops/manifests/core-apps/kai-frontend/kustomization.yaml`

Values to set per environment:

- `namespace`: Namespace where frontend resources are deployed.
- `images[].newName`: Frontend image registry/repository.
- `images[].newTag`: Frontend image version/tag.

Ingress routes used by the UI are defined in:
- `ai-ops-platform-gitops/manifests/core-apps/kai-frontend/ingress.yaml`

Key routes:
- `/kai` -> frontend service
- `/chat` -> agent-controller service

## Quick Checklist

Before deploy, verify:

1. Frontend `namespace`, image name, and image tag are set.
2. `SANDBOX_EXECUTE_URL` resolves from agent-controller pod/network.
3. `AWS_REGION`, `AWS_BILLING_REGION`, and `PROMETHEUS_URL` are correct.
4. LLM provider/model/key settings are configured per `LLM_CONFIGURATION.md`.
