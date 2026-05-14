# Deploy KAI on a Kubernetes cluster

This runbook matches the layouts in the GitOps sibling repo **`ai-ops-platform-gitops`** and the images built from **`ai-ops-platform`** (this repo).

## Runtime contract

- Browser loads the UI at **`/kai/`** (`<base href="/kai/">` in the frontend `index.html`).
- The SPA calls **`GET /chat`** and **`POST /chat`** on the **same origin** (`fetch("/chat", …)`). The ingress must send **`/chat`** to **agent-controller**, not the nginx static pod.
- **agent-controller** calls **agent-sandbox** at **`http://agent-sandbox/execute`** (Kubernetes DNS service name in the same namespace). Override with env **`SANDBOX_EXECUTE_URL`** if you use a different service name or port.
- **agent-sandbox** loads in-cluster credentials and uses RBAC from GitOps. Prometheus tools default to **`PROMETHEUS_URL`** (falls back to `http://prometheus.monitoring.svc.cluster.local:9090`). Point a working Prometheus at that address or set the env var on the sandbox Deployment.

## Prerequisites

- A Kubernetes cluster and `kubectl`.
- A **Gemini API key** in a Secret (key `GEMINI_API_KEY`, name `gemini-secret` in the default manifests).
- Images: build from this repo (see Dockerfiles under [`agent-controller`](../agent-controller/Dockerfile) and [`agent-sandbox`](../agent-sandbox/Dockerfile)). Build context must be the **`ai-ops-platform` repository root**:

  ```bash
  docker build -f agent-controller/Dockerfile -t your-registry/agent-controller:tag .
  docker build -f agent-sandbox/Dockerfile -t your-registry/agent-sandbox:tag .
  ```

- (Recommended) Prometheus + kube-state-metrics + cAdvisor-compatible metrics for cost/FinOps tools.

## Install without Argo CD

1. Create the secret:

   ```bash
   kubectl create secret generic gemini-secret \
     --namespace default \
     --from-literal=GEMINI_API_KEY="YOUR_KEY"
   ```

2. Apply **agent-sandbox** RBAC + workload + Service (sibling repo `ai-ops-platform-gitops`, path `manifests/agent-sandbox`):

   ```bash
   kubectl apply -k ../../ai-ops-platform-gitops/manifests/agent-sandbox
   ```

3. Apply **agent-controller** (`../../ai-ops-platform-gitops/manifests/agent-controller`).

4. Apply **frontend** (Deployment **kai-frontend** image + Service + Ingress). Customize **`ingress.yaml`** if you are not on AWS ALB: keep paths **`/kai` → frontend:80** and **`/chat` → agent-controller:80**.

5. Wait for pods `Running`; verify:

   ```bash
   kubectl port-forward svc/agent-controller 8080:80
   curl -s http://127.0.0.1:8080/chat
   ```

## GitOps (Argo CD)

Applications live under `../../ai-ops-platform-gitops/apps`. Point `repoURL` / `targetRevision` at your fork and sync `agent-controller`, `agent-sandbox`, `frontend`, and `secrets`.

## Frontend image and Argo CD

The UI is **not** embedded in a ConfigMap anymore. GitOps [`manifests/core-apps/kai-frontend/deployment.yaml`](../../ai-ops-platform-gitops/manifests/core-apps/kai-frontend/deployment.yaml) uses **`iahmedsabry/kai-frontend:latest`** (adjust registry/name for your environment).

1. **Build and push** from this repo (context = repository root):

   ```bash
   docker build -f frontend/Dockerfile -t your-registry/kai-frontend:latest .
   docker push your-registry/kai-frontend:latest
   ```

2. **CI**: On push to `main`/`master` under `frontend/`, [`.github/workflows/frontend-image.yml`](../.github/workflows/frontend-image.yml) builds and pushes `iahmedsabry/kai-frontend:latest` and `:sha`. Configure repository secrets **`DOCKERHUB_USERNAME`** and **`DOCKERHUB_TOKEN`**. Change `IMAGE_NAME` in the workflow if you use another registry.

3. **Argo CD** keeps syncing the same app path (`manifests/core-apps/kai-frontend`). After a new image is available, either rely on **`imagePullPolicy: Always`** and restart the Deployment, or set a pinned digest/tag in GitOps and commit. Optionally install **Argo CD Image Updater** and uncomment the annotations on the frontend Deployment to write back new tags to Git.

4. **Edit UI**: change [`frontend/index.html`](../frontend/index.html) and [`frontend/nginx/default.conf`](../frontend/nginx/default.conf) (must match `/kai` routing), then push to trigger CI or rebuild locally.

## Customize tools
- Edit [`shared/tools.yaml`](../shared/tools.yaml) (descriptions/arguments for the planner). Implement matching logic in [`agent_sandbox/tool_dispatch.py`](../agent_sandbox/tool_dispatch.py) and rebuild the sandbox image. The allow-list is derived from the YAML at startup.