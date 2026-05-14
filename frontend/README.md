# KAI frontend (static SPA)

Source for the **`kai-frontend`** image used by GitOps / Argo CD.

## Workflow

- Edit **`index.html`** (single-file SPA).
- **`npm run dev`** — local preview with Vite (`/kai/` base).
- **`npm run build`** — copies `index.html` to `dist/` (same as the Docker build stage).
- **`docker build -t your-registry/kai-frontend:tag ./frontend`** (repo root) or rely on **GitHub Actions** [`.github/workflows/frontend-image.yml`](../.github/workflows/frontend-image.yml) (Docker Hub; set `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`).

Production routing is defined in **`nginx/default.conf`** (must stay aligned with ingress `/kai` prefix). The container image is the source of truth for static UI assets.

The production ingress contract is unchanged: UI under `/kai/`, API on the same host at `/chat`.
