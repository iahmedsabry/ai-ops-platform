# `agent-sandbox/` Folder (Hyphenated)

This is the Docker packaging wrapper for the agent sandbox.

## Purpose

The underscored folder `agent_sandbox/` contains the actual Python source code. The hyphenated folder `agent-sandbox/` packages that code for Docker: it holds the Dockerfile, requirements, and a thin shim so `docker build` works correctly.

## Files

### `agent-sandbox/Dockerfile`
- Builds the sandbox Docker image.
- Installs dependencies from `agent-sandbox/requirements.txt`.
- Copies the actual source code from `agent_sandbox/` into the image.
- Copies the shared code from `shared/` into the image.
- Copies the shim `agent-sandbox/app.py` so `uvicorn app:app` works.
- Build command: `docker build -f agent-sandbox/Dockerfile -t your-registry/agent-sandbox:tag .` (run from repo root).

### `agent-sandbox/requirements.txt`
- Python dependencies for the sandbox: FastAPI, uvicorn, Kubernetes client, Prometheus client, boto3.
- Used only during `docker build`.

### `agent-sandbox/app.py`
- A thin shim that imports from the real implementation.
- Simply does: `from agent_sandbox.main import app`.
- Exists so `uvicorn app:app` can find the app without path manipulation.

## How it fits in the project

- Docker build context folder for the sandbox.
- Kept separate from the actual source code so that both are clean.
- The build copies `agent_sandbox/`, `shared/`, and this folder's files into the image.
- After build, the image has the full app and runs with `uvicorn app:app`.

## Simple takeaway

- Keep this folder.
- It is needed for Docker builds.
- Do not edit the source code here; edit the files in `agent_sandbox/` instead.
- If you change dependencies, update `agent-sandbox/requirements.txt`.
