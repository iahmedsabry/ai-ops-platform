# `agent-controller/` Folder (Hyphenated)

This is the Docker packaging wrapper for the agent controller.

## Purpose

The underscored folder `agent_controller/` contains the actual Python source code. The hyphenated folder `agent-controller/` packages that code for Docker: it holds the Dockerfile, requirements, and a thin shim so `docker build` works correctly.

## Files

### `agent-controller/Dockerfile`
- Builds the controller Docker image.
- Installs dependencies from `agent-controller/requirements.txt`.
- Copies the actual source code from `agent_controller/` into the image.
- Copies the shared code from `shared/` into the image.
- Copies the shim `agent-controller/app.py` so `uvicorn app:app` works.
- Build command: `docker build -f agent-controller/Dockerfile -t your-registry/agent-controller:tag .` (run from repo root).

### `agent-controller/requirements.txt`
- Python dependencies for the controller: FastAPI, uvicorn, requests, PyYAML.
- Used only during `docker build`.

### `agent-controller/app.py`
- A thin shim that imports from the real implementation.
- Simply does: `from agent_controller.main import app`.
- Exists so `uvicorn app:app` can find the app without path manipulation.

### `agent-controller/prompt_modes/` (if present)
- May contain symlinks or copies of prompt mode files if they differ from the main folder.
- Usually synced with `agent_controller/prompt_modes/`.

## How it fits in the project

- Docker build context folder for the controller.
- Kept separate from the actual source code so that both are clean.
- The build copies `agent_controller/`, `shared/`, and this folder's files into the image.
- After build, the image has the full app and runs with `uvicorn app:app`.

## Simple takeaway

- Keep this folder.
- It is needed for Docker builds.
- Do not edit the source code here; edit the files in `agent_controller/` instead.
- If you change dependencies, update `agent-controller/requirements.txt`.
