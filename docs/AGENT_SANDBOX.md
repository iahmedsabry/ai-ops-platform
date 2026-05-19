# `agent_sandbox/` Folder

This is the secure, isolated execution service that runs tools in the Kubernetes cluster.

## Purpose

The sandbox is a read-only gateway to the cluster. The controller sends tool requests here; the sandbox validates them against an allow-list, executes the tool, and returns the result.

## Files

### `agent_sandbox/__init__.py`
- Marks `agent_sandbox` as a Python package.
- Lets other code import from this folder cleanly.

### `agent_sandbox/main.py`
- FastAPI app entry point.
- Exposes a single `/execute` endpoint that accepts tool requests.
- Validates tool names against the allow-list before executing.
- Returns JSON results back to the controller.

### `agent_sandbox/tool_dispatch.py`
- The heart of the sandbox: implements every allowed tool.
- Uses Kubernetes Python client to query the cluster.
- Uses Prometheus client to fetch metrics.
- Uses AWS SDK to fetch billing data (if IRSA is configured).
- Routes tool requests to their handler functions.
- Handles errors and timeouts gracefully.

### `agent_sandbox/models.py`
- Pydantic data models for request/response validation.
- Defines `ToolRequest` (tool name + arguments) schema.

### `agent_sandbox/registry.py`
- Maps tool names to their handler functions.
- Stores the mapping of allowed tools.
- Used by tests to verify that the catalog matches the implementation.

### `agent_sandbox/clients.py`
- Creates Kubernetes API clients, Prometheus client, AWS client.
- Handles authentication: reads kubeconfig, AWS credentials, Prometheus URL.
- Provides utility functions for common queries.
- Centralizes all external client setup.

## How it fits in the project

- Receives HTTP POST requests from the controller at `/execute`.
- Validates tool name against the allow-list (from `shared/tools.yaml`).
- Executes the tool using Kubernetes/Prometheus/AWS APIs.
- Returns structured JSON back to the controller.
- Runs inside the Kubernetes cluster with restricted RBAC permissions.

## Security Model

- Only allow-listed tools can run (no arbitrary execution).
- Uses Kubernetes RBAC: can read pods, deployments, services, events.
- Cannot write or delete resources (read-only safety).
- Can read AWS billing (if the service account is annotated with the right IAM role).

## Simple takeaway

- Keep this folder.
- It is the execution layer and the security boundary.
- All the actual Kubernetes/cloud queries happen here.
