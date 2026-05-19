# `frontend/` Folder

This is the web UI that users interact with.

## Purpose

The frontend is a single-page web app (SPA) that lets users chat with the AI ops platform, upload screenshots, see tool outputs, and review Kubernetes cluster analysis.

## Files

### `frontend/index.html`
- The main HTML file.
- Contains the chat interface, message history, image upload, and results display.
- Includes inline JavaScript for chat logic, event handling, and API calls.
- Fetches from the same origin at `POST /chat` and `GET /chat`.

### `frontend/package.json`
- Defines npm dependencies: currently just Vite for bundling.
- Scripts: `npm run dev` for local development, `npm run build` for production build.

### `frontend/vite.config.js`
- Vite build configuration.
- Configures the dev server and production bundle output.
- Tells Vite how to handle assets and modules.

### `frontend/Dockerfile`
- Builds the frontend SPA and serves it with nginx.
- Stages: `npm run build` to create static files, then copies them to nginx.
- Listens on port 80.
- Used to build the `iahmedsabry/kai-frontend` Docker image.

### `frontend/.gitignore`
- Excludes `node_modules/`, `dist/`, and other build artifacts from version control.

### `frontend/.dockerignore`
- Excludes files from the Docker build context.
- Keeps `node_modules/` out of the final image (dependencies are installed fresh).

### `frontend/README.md`
- Brief development instructions and setup info.

### `frontend/nginx/`
- `default.conf`: nginx configuration for serving the SPA.
- Routes `/kai` to static files, `/chat` to the controller backend.
- Handles CORS and API proxying if needed.

### `frontend/scripts/`
- `build-static.mjs`: Custom build script (Node.js).
- Can be used instead of standard Vite build for special packaging.

## How it fits in the project

- Users open the SPA in a browser.
- The SPA calls `GET /chat` to fetch metadata (LLM model name, available prompt modes).
- Users type a message or upload an image.
- The SPA calls `POST /chat` with the message/image.
- The controller responds with the analysis result.
- The SPA displays the result and chat history.

## Deployment

- Runs inside Kubernetes as a Deployment (`kai-frontend` pod).
- Served via an Ingress at path `/kai`.
- The API path `/chat` is routed to the controller at the same Ingress.
- Static assets are bundled at build time; no runtime build needed in the pod.

## Simple takeaway

- Keep this folder.
- It is the user-facing interface of the platform.
- Compile it with `docker build -f frontend/Dockerfile` from the repo root.
