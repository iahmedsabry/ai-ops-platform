    # url = (
    #     "https://generativelanguage.googleapis.com/"
    #     f"v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    # )

    # url = (
    #     "https://generativelanguage.googleapis.com/"
    #     f"v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    # )

    # url = (
    #     "https://generativelanguage.googleapis.com/"
    #     f"v1beta/models/gemini-2.5-flash-lite:generateContent?key={api_key}"
    # )

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import base64
import re
import requests
import os
import json
from pathlib import Path

app = FastAPI()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash",
)

GEMINI_TIMEOUT = int(
    os.getenv("GEMINI_TIMEOUT", "90")
)

SANDBOX_TIMEOUT = int(
    os.getenv("SANDBOX_TIMEOUT", "90")
)

MAX_TOOL_CONTEXT_CHARS = int(
    os.getenv("MAX_TOOL_CONTEXT_CHARS", "120000")
)

MAX_CHAT_IMAGES = int(os.getenv("MAX_CHAT_IMAGES", "6"))

MAX_IMAGE_BYTES = int(
    os.getenv("MAX_IMAGE_BYTES", str(4 * 1024 * 1024))
)

_ALLOWED_IMAGE_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)


# =========================================================
# Prompt modes (per-focus instructions from prompt_modes/*.txt)
# =========================================================
_PROMPT_STEM_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _load_prompt_mode_files():

    base = Path(__file__).resolve().parent / "prompt_modes"
    out = {}

    if not base.is_dir():

        return out

    for path in sorted(base.glob("*.txt")):

        stem = path.stem.lower()

        if not _PROMPT_STEM_PATTERN.match(stem):

            continue

        try:

            text = path.read_text(encoding="utf-8").strip()

        except OSError:

            continue

        if not text:

            continue

        out[stem] = text

    return out


PROMPT_MODE_FILES = _load_prompt_mode_files()

ALLOWED_PROMPT_MODES = frozenset(
    set(PROMPT_MODE_FILES.keys()) | {"general"}
)


def normalize_prompt_mode(
    mode: Optional[str],
) -> str:

    if mode is None:

        return "general"

    cleaned = str(mode).strip().lower()

    if cleaned in ALLOWED_PROMPT_MODES:

        return cleaned

    return "general"


def focus_instruction_block(
    mode: str,
) -> str:

    if mode == "general":

        return ""

    return PROMPT_MODE_FILES.get(mode, "")


# =========================================================
# Request model
# =========================================================
class ChatImagePart(BaseModel):
    """Single image as base64 (no data: URL prefix required)."""

    mime_type: str
    data: str


class ChatRequest(BaseModel):
    message: str
    images: Optional[List[ChatImagePart]] = None
    prompt_mode: Optional[str] = None


# =========================================================
# Health check
# =========================================================
@app.get("/")
def root():
    return {"status": "Agent Controller running"}


# =========================================================
# Multipart images for Gemini
# =========================================================
def sanitize_chat_images(
    images: Optional[List[ChatImagePart]],
):

    if not images:
        return []

    cleaned = []

    for img in images[:MAX_CHAT_IMAGES]:

        mime = (img.mime_type or "").strip().lower()

        if mime == "image/jpg":
            mime = "image/jpeg"

        if mime not in _ALLOWED_IMAGE_MIME:
            continue

        raw = (img.data or "").strip()

        if raw.startswith("data:") and ";base64," in raw:
            raw = raw.split(";base64,", 1)[1]

        raw = "".join(raw.split())

        try:
            blob = base64.b64decode(raw, validate=False)
        except Exception:
            continue

        if len(blob) < 32 or len(blob) > MAX_IMAGE_BYTES:
            continue

        b64_out = base64.standard_b64encode(blob).decode("ascii")

        cleaned.append(
            {
                "mime_type": mime,
                "data": b64_out,
            }
        )

    return cleaned


def build_gemini_parts_from_inline(
    prompt: str,
    inline_items: List[dict],
):

    parts = [{"text": prompt}]

    for item in inline_items:

        parts.append(
            {
                "inline_data": {
                    "mime_type": item["mime_type"],
                    "data": item["data"],
                }
            }
        )

    return parts


# =========================================================
# Gemini API call
# =========================================================
def call_gemini(
    prompt: str,
    inline_images: Optional[List[dict]] = None,
):

    import time

    inlined = inline_images if inline_images is not None else []

    parts = build_gemini_parts_from_inline(prompt, inlined)

    api_key = os.getenv("GEMINI_API_KEY")

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    )

    max_retries = 3

    for attempt in range(max_retries):

        try:

            response = requests.post(
                url,
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "contents": [
                        {
                            "parts": parts
                        }
                    ]
                },
                timeout=GEMINI_TIMEOUT
            )

            print("Gemini status code:", response.status_code)
            print("Gemini raw response:")
            print(response.text)

            # =================================================
            # Success
            # =================================================

            if response.status_code == 200:

                try:

                    return response.json()

                except Exception as json_error:

                    return {
                        "error": "Failed to parse Gemini JSON",
                        "raw_response": response.text,
                        "exception": str(json_error)
                    }

            # =================================================
            # Retryable errors
            # =================================================

            if response.status_code in [429, 500, 502, 503, 504]:

                print(
                    f"Retryable Gemini error: "
                    f"{response.status_code}"
                )

                # Exponential backoff
                time.sleep(2 ** attempt)

                continue

            # =================================================
            # Other errors
            # =================================================

            return {
                "error": f"Gemini API returned {response.status_code}",
                "raw_response": response.text
            }

        except Exception as request_error:

            print("Gemini request failed:", str(request_error))

            time.sleep(2 ** attempt)

    return {
        "error": "Gemini API failed after retries"
    }


# =========================================================
# Extract Gemini text safely
# =========================================================
def extract_text(gemini_response):

    try:

        print("Gemini parsed response:")
        print(json.dumps(gemini_response, indent=2))

        # Handle API errors
        if gemini_response.get("error"):

            return ""

        candidates = gemini_response.get("candidates", [])

        if not candidates:
            return ""

        content = candidates[0].get("content", {})

        parts = content.get("parts", [])

        if not parts:
            return ""

        chunks = []

        for part in parts:

            fragment = part.get("text")

            if fragment:

                chunks.append(fragment)

        return "\n".join(chunks).strip()

    except Exception as e:

        print("Extract text error:", str(e))

        return ""

# =========================================================
# Safe join helper
# =========================================================
def safe_join(values, limit=None):

    if values is None:
        return ""

    cleaned = []

    for value in values:

        if value is None:
            continue

        cleaned.append(str(value))

    if limit:
        cleaned = cleaned[:limit]

    return ", ".join(cleaned)

# =========================================================
# Tool catalog (sandbox allow-list + planner hints)
# =========================================================
TOOL_CATALOG = [
    {
        "name": "list_pods",
        "arguments": {},
        "detail": (
            "Pods in all namespaces: status, restarts, "
            "per-container requests/limits, node, IPs."
        ),
    },
    {
        "name": "list_deployments",
        "arguments": {},
        "detail": "Replica health, strategy, availability per Deployment.",
    },
    {
        "name": "list_stateful_sets",
        "arguments": {},
        "detail": "Stateful app footprint and replica readiness.",
    },
    {
        "name": "list_daemon_sets",
        "arguments": {},
        "detail": "Node daemons/system agents coverage.",
    },
    {
        "name": "list_cron_jobs",
        "arguments": {},
        "detail": "Scheduled batch work, suspend state, schedules.",
    },
    {
        "name": "list_jobs",
        "arguments": {
            "limit": "optional int, max 300; recent Jobs first.",
        },
        "detail": "Recent batch Jobs and completion/failure counts.",
    },
    {
        "name": "list_services",
        "arguments": {},
        "detail": "ClusterIP/LB/NodePort footprint and ports.",
    },
    {
        "name": "list_endpoints",
        "arguments": {},
        "detail": "Whether Services actually have backing pods.",
    },
    {
        "name": "list_ingresses",
        "arguments": {},
        "detail": "External hostnames and ingress exposure.",
    },
    {
        "name": "list_namespaces",
        "arguments": {},
        "detail": "Namespace inventory and phase.",
    },
    {
        "name": "list_nodes",
        "arguments": {},
        "detail": (
            "Capacity/allocatable, instance type, kubelet version, "
            "Ready status."
        ),
    },
    {
        "name": "list_events",
        "arguments": {
            "namespace": "optional; omit for cluster-wide Warnings.",
        },
        "detail": "Recent Warning events (noise filtered).",
    },
    {
        "name": "list_horizontal_pod_autoscalers",
        "arguments": {},
        "detail": "Autoscaling targets, min/max, current/desired.",
    },
    {
        "name": "list_pvcs",
        "arguments": {},
        "detail": "Claim sizes, storage class, binding state.",
    },
    {
        "name": "list_pvs",
        "arguments": {},
        "detail": "Cluster storage volumes and claims (cost context).",
    },
    {
        "name": "list_storage_classes",
        "arguments": {},
        "detail": "Provisioners and reclaim/binding modes.",
    },
    {
        "name": "list_resource_quotas",
        "arguments": {},
        "detail": "Namespace hard limits vs observed usage.",
    },
    {
        "name": "list_limit_ranges",
        "arguments": {},
        "detail": "Default/min/max constraints for workloads.",
    },
    {
        "name": "list_argocd_applications",
        "arguments": {},
        "detail": "GitOps health and sync status.",
    },
    {
        "name": "get_logs",
        "arguments": {
            "namespace": "default default",
            "pod_name": "optional explicit pod",
            "app_label": "optional app= selector",
            "container_name": "optional multi-container pods",
            "tail_lines": "default 200 (max 2500)",
            "previous_container": (
                "boolean; set true right after restarts for the "
                "last crashed instance's log"
            ),
            "timestamps": "boolean prefix each line with k8s timestamps",
        },
        "detail": (
            "Container logs — use when events/pods show crashes "
            "or errors, not only when user types 'logs'."
        ),
    },
    {
        "name": "get_pod_details",
        "arguments": {
            "namespace": "default default",
            "pod_name": "required",
        },
        "detail": (
            "Deep pod view: phase, conditions, per-container "
            "waiting/termination reasons, restarts, QoS, probes, "
            "PVC volume claims, owners — use for CrashLoop, Pending, "
            "ImagePull failures, or before previous_container logs."
        ),
    },
    {
        "name": "get_deployment_rollout_status",
        "arguments": {
            "namespace": "default default",
            "deployment_name": "required Deployment name",
        },
        "detail": (
            "Rollout health: desired vs ready/available/updated, "
            "pause flag, strategy, Deployment status conditions "
            "(Progressing/Available ReplicaFailure messages)."
        ),
    },
    {
        "name": "get_config_map_data",
        "arguments": {
            "namespace": "default default",
            "config_map_name": (
                "required; alias key 'name' accepted"
            ),
            "keys": "optional list — only return these data keys",
            "max_value_chars": "optional 500–64000 per string value",
        },
        "detail": (
            "Reads ConfigMap string data (budget-capped) — for bad "
            "config, wrong URLs, feature flags, Helm-created values. "
            "Does not return Secret contents."
        ),
    },
    {
        "name": "query_prometheus",
        "arguments": {
            "query": "required PromQL instant query",
        },
        "detail": "Custom metrics — CPU, memory, SLIs, kube-state metrics.",
    },
    {
        "name": "prometheus_common_metrics",
        "arguments": {},
        "detail": (
            "Runs a small curated bundle (scrape health, CPU/memory "
            "by namespace, failing pod phases). Use for cost/capacity "
            "when exact PromQL is unknown."
        ),
    },
    {
        "name": "finops_cluster_signals",
        "arguments": {},
        "detail": (
            "Summarizes node SKU mix across zones plus optional "
            "cloud/node-pool hints (AWS EKS/GKE/AKS labels when present) "
            "and Prometheus signals for requests vs allocations (PVC, "
            "CPU/memory requests, allocatables) — works wherever standard "
            "kube-state-metrics + cAdvisor-compatible series exist."
        ),
    },
]


AVAILABLE_TOOLS = [entry["name"] for entry in TOOL_CATALOG]


def default_wide_tool_plan():

    return [
        {"tool": "list_pods", "arguments": {}},
        {"tool": "list_deployments", "arguments": {}},
        {"tool": "list_stateful_sets", "arguments": {}},
        {"tool": "list_daemon_sets", "arguments": {}},
        {"tool": "list_cron_jobs", "arguments": {}},
        {"tool": "list_jobs", "arguments": {"limit": 120}},
        {"tool": "list_services", "arguments": {}},
        {"tool": "list_endpoints", "arguments": {}},
        {"tool": "list_ingresses", "arguments": {}},
        {"tool": "list_namespaces", "arguments": {}},
        {"tool": "list_nodes", "arguments": {}},
        {"tool": "list_events", "arguments": {}},
        {"tool": "list_horizontal_pod_autoscalers", "arguments": {}},
        {"tool": "list_pvcs", "arguments": {}},
        {"tool": "list_pvs", "arguments": {}},
        {"tool": "list_storage_classes", "arguments": {}},
        {"tool": "list_resource_quotas", "arguments": {}},
        {"tool": "list_limit_ranges", "arguments": {}},
        {"tool": "list_argocd_applications", "arguments": {}},
        {"tool": "finops_cluster_signals", "arguments": {}},
        {"tool": "prometheus_common_metrics", "arguments": {}},
    ]

def truncate_context_block(text, max_chars):

    if len(text) <= max_chars:

        return text

    head = max_chars // 2 - 50

    tail = max_chars - head - 50

    if head < 1000:

        head = 1000

    if tail < 1000:

        tail = 1000

    return (
        text[:head]
        + "\n\n... [truncated middle to fit model context] ...\n\n"
        + text[-tail:]
    )


def pack_tool_results_payload(tool_results):

    blocks = []

    for item in tool_results:

        payload = {
            "tool": item.get("tool"),
            "result": item.get("result"),
        }

        blocks.append(
            json.dumps(payload, indent=2, default=str)
        )

    combined = "\n\n--- TOOL SEPARATOR ---\n\n".join(blocks)

    return truncate_context_block(
        combined,
        MAX_TOOL_CONTEXT_CHARS,
    )


# Lightweight metadata for the chat UI (same path as POST; different verb).
GEMINI_DISPLAY_API = os.getenv(
    "GEMINI_DISPLAY_API",
    "https://generativelanguage.googleapis.com/v1beta",
)


@app.get("/chat")
def chat_metadata():

    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "api_base_display": GEMINI_DISPLAY_API.strip(),
        "supports_post": True,
        "supports_images": True,
        "max_chat_images": MAX_CHAT_IMAGES,
        "max_image_bytes": MAX_IMAGE_BYTES,
        "prompt_modes": sorted(ALLOWED_PROMPT_MODES),
    }


# =========================================================
@app.post("/chat")
def chat(request: ChatRequest):

    try:

        inline_visuals = sanitize_chat_images(request.images)
        has_screenshots = len(inline_visuals) > 0

        user_msg_stripped = (
            (request.message or "").strip()
        )

        effective_mode = normalize_prompt_mode(
            request.prompt_mode,
        )

        focus_extra = focus_instruction_block(
            effective_mode,
        )

        focus_section = ""

        if focus_extra.strip():

            focus_section = f"""

=========================================================
USER SELECTED FOCUS (bias tool choice and analysis toward this)
=========================================================

{focus_extra.strip()}

"""

        prompt_focus_separator = (
            focus_section if focus_section else "\n\n"
        )

        screenshot_primary_question = (
            has_screenshots
            and len(user_msg_stripped) < 100
        )

        visual_planner_intro = ""

        if has_screenshots:

            visual_planner_intro = """
=========================================================
VISUAL INPUT (SCREENSHOTS / DIAGRAMS)
=========================================================

Raster images are appended to this message after your text. The user expects
the SAME automated read-only sandbox investigation path as for text-heavy
requests — not a generic canned checklist unsupported by live cluster data.

• ALWAYS set \"needs_tools\": true unless EVERY image obviously has NOTHING
  to do with infrastructure (vacation photo, meme, unrelated document).

• Read visible pixels like an SRE dashboard: ingress/LB/console/kubectl/
  Grafana/Prometheus/Argo/CDN/TLS/pod events/CrashLoop/503 plain-text/HTML
  error pages/stack traces/GitOps statuses.

• SCHEDULE targeted tools inferred from clues you read (examples):
    – Hostname / path / 502–504 / LB name / certificate / stale backend → list_ingresses, list_services,
      list_endpoints; pair with list_events; add get_logs if you can confidently name pod/namespace —
      otherwise omit specific pod arguments.
    – Namespace + workload names shown → biased list_deployments/list_pods
      when arguments are obvious; otherwise keep arguments empty cluster-wide snapshots.
    – GitOps anomalies → list_argocd_applications.
    – Utilization dashboards → prometheus_common_metrics and optionally query_prometheus only if screenshot PromQL/context is actionable.
    – Storage errors → pvc/pv/events tools as hinted.
    – Pod stuck / CrashLoop / ImagePull / probe failures → **get_pod_details** on the offender, then **get_logs** (`previous_container` true after restart); for bad mounted app config pair **get_config_map_data** when the ConfigMap name is known from pod volumes or GitOps manifests.
    – Deployment not becoming ready → **get_deployment_rollout_status** on that Deployment plus neighboring **list_events**.

• This step outputs JSON ONLY (needs_tools / tool_calls). Do NOT spell out remediation steps prose here —
  remediation happens AFTER tools return live JSON.

"""

        tool_prompt = f"""{visual_planner_intro}
You are planning READ-ONLY Kubernetes investigation steps for an agent
that runs tools in a locked-down sandbox. Pick tools so the downstream LLM
receives enough real cluster data to answer code, application, cost,
capacity, GitOps, reliability, and observability questions accurately.

=========================================================
TOOL DIRECTORY (name / arguments / what it returns)
=========================================================

{json.dumps(TOOL_CATALOG, indent=2)}

=========================================================
PLANNING RULES
=========================================================

1. NEVER invent tool names — only names from the directory above.
2. NEVER answer the user's question here; output JSON only.
3. If the user mentions the cluster, workloads, health, cost, capacity,
   deploys, GitOps, networking, storage, jobs, or metrics: set needs_tools true.
4. For broad or underspecified questions ("how is my cluster", "what should
   we optimize", "any problems") choose a WIDE set of complementary list
   tools (workloads + networking + capacity + storage signals + events).
5. Include prometheus_common_metrics whenever cost, utilization, right-
   sizing, performance, or anomalies are relevant; add query_prometheus with
   tailored PromQL when you know the exact metric/question. For COST / FinOps /
   spend / billing / savings / waste / SKU / utilization vs allocation ASKS,
   always include **finops_cluster_signals** alongside prometheus_common_metrics
   (and usually list_pvcs + list_resource_quotas + list_nodes + HPAs): it
   gathers node mix & Prometheus request/PVC footprints even though kubectl
   cannot see cloud-provider invoices themselves.
6. Include list_events when diagnosing instability. For crash loops, probe
   failures, Pending, or ImagePullBackOff: call **get_pod_details** (namespace+
   pod_name) then **get_logs** — use `previous_container: true` on logs when the
   pod restarted. For stalled rollouts call **get_deployment_rollout_status**.
   When misconfiguration comes from mounted ConfigMaps and the name is known,
   add **get_config_map_data**. Pass explicit namespace/pod/deployment whenever
   events or list_* output provides them.
7. It is acceptable to schedule many tools in parallel — prefer missing
   signals over saving API calls.
8. Skip setting needs_tools ONLY for obvious non-infra chat with NO relevant
   screenshots supplied (vacation snaps, greetings). If VISUAL INPUT block is
   present above, IGNORE this excuse — screenshots override small-talk.
9. When screenshots imply incidents, regressions, or misconfiguration tied to Kubernetes,
   cloud load balancers, or GitOps tooling, SCHEDULE LIVE TOOLS IMMEDIATELY even if USER REQUEST text says only "ideas" / "thoughts".
{prompt_focus_separator}=========================================================
RESPONSE FORMAT (JSON ONLY)
=========================================================

If tools are needed:
{{
  "needs_tools": true,
  "tool_calls": [
    {{"tool": "list_pods", "arguments": {{}} }},
    {{"tool": "prometheus_common_metrics", "arguments": {{}} }}
  ]
}}

If tools are NOT needed:
{{
  "needs_tools": false
}}

- No markdown, no code fences, no comments, no extra keys beyond needs_tools
  and tool_calls.
- arguments must be JSON objects (possibly empty).

=========================================================
USER REQUEST
=========================================================

{request.message}
"""

        tool_decision = call_gemini(
            tool_prompt,
            inline_visuals,
        )

        # Handle Gemini API errors
        if tool_decision.get("error"):

            return {
                "error": tool_decision.get("error"),
                "details": tool_decision.get("raw_response", "")
            }

        decision_text = extract_text(tool_decision)

        print("Tool decision:")
        print(decision_text)

        # =================================================
        # STEP 2: Parse tool decision
        # =================================================

        try:

            decision_json = json.loads(decision_text)

        except Exception:

            print("Failed to parse tool decision JSON")

            kubernetes_keywords = [
                "cluster",
                "kube",
                "k8s",
                "kubernetes",
                "pod",
                "pods",
                "deployment",
                "deployments",
                "stateful",
                "daemon",
                "cron",
                "job",
                "hpa",
                "autoscal",
                "service",
                "services",
                "ingress",
                "argocd",
                "application",
                "applications",
                "gitops",
                "cost",
                "billing",
                "optimize",
                "optimization",
                "right-size",
                "resource",
                "memory",
                "cpu",
                "node",
                "nodes",
                "namespace",
                "prometheus",
                "monitoring",
                "metrics",
                "logs",
                "events",
                "health",
                "incident",
                "outage",
                "latency",
                "endpoints",
                "connectivity",
                "traffic",
                "routing",
                "network",
                "pvc",
                "persistent",
                "storage",
                "volume",
                "quota",
                "limitrange",
                "sandbox",
                "workload",
                "finops",
                "budget",
                "spend",
                "savings",
                "waste",
                "crash",
                "crashloop",
                "rollout",
                "configmap",
                "troubleshoot",
                "restart",
                "imagepull",
                "pending",
            ]

            message_lower = request.message.lower()

            should_use_tools = has_screenshots or any(
                keyword in message_lower
                for keyword in kubernetes_keywords
            )

            if should_use_tools:

                decision_json = {
                    "needs_tools": True,
                    "tool_calls": default_wide_tool_plan(),
                }

            else:

                decision_json = {
                    "needs_tools": False
                }

        needs_tools = decision_json.get("needs_tools", False)

        if has_screenshots and (
            (not needs_tools)
            or (not decision_json.get("tool_calls"))
        ):

            needs_tools = True
            decision_json["needs_tools"] = True

            if not decision_json.get("tool_calls"):

                decision_json["tool_calls"] = (
                    default_wide_tool_plan()
                )

        # =================================================
        # STEP 3: Normal conversation
        # =================================================

        if not needs_tools:

            normal_prompt = f"""
You are a concise Kubernetes and DevOps assistant.

Rules:
• Short, friendly answers unless the user asks for depth (aim under ~180 words normally).
• No unnecessary preamble (“Certainly!”, “I'd be happy to…”).
• Use ### for a heading and bullets (**-**) when listing steps is clearer.

{prompt_focus_separator}User message:
{request.message}
"""

            response = call_gemini(
                normal_prompt,
                inline_visuals,
            )

            # Handle Gemini errors
            if response.get("error"):

                return {
                    "error": response.get("error"),
                    "details": response.get("raw_response", "")
                }

            return {
                "mode": "conversation",
                "response": extract_text(response)
            }

        # =================================================
        # STEP 4: Execute tools
        # =================================================

        tool_results = []

        tool_calls = decision_json.get("tool_calls", [])

        for tool_call in tool_calls:

            tool_name = tool_call.get("tool")
            arguments = tool_call.get("arguments", {})

            if tool_name not in AVAILABLE_TOOLS:
                continue

            print(f"Executing tool: {tool_name}")

            try:

                sandbox_response = requests.post(
                    "http://agent-sandbox/execute",
                    json={
                        "tool": tool_name,
                        "arguments": arguments
                    },
                    timeout=SANDBOX_TIMEOUT
                )

                print("Sandbox status code:", sandbox_response.status_code)
                print("Sandbox raw response:")
                print(sandbox_response.text)

                try:

                    parsed_result = sandbox_response.json()

                except Exception as json_error:

                    parsed_result = {
                        "error": "Invalid JSON response from sandbox",
                        "raw_response": sandbox_response.text,
                        "exception": str(json_error)
                    }

                tool_results.append({
                    "tool": tool_name,
                    "result": parsed_result
                })

            except Exception as tool_error:

                tool_results.append({
                    "tool": tool_name,
                    "result": {
                        "error": str(tool_error)
                    }
                })

        # =================================================
        # STEP 5A: Build enriched operational summary
        # =================================================

        summary = []

        for item in tool_results:

            tool = item.get("tool")
            result = item.get("result", {})

            # =================================================
            # Tool execution errors
            # =================================================

            if result.get("error"):

                summary.append(
                    f"{tool}: ERROR -> "
                    f"{result.get('error')}"
                )

                continue

            # =================================================
            # Pods
            # =================================================

            if tool == "list_pods":

                pods = result.get("pods", [])

                running = 0
                unhealthy = 0

                restarting = []
                pending = []
                failed = []

                namespaces = set()

                total_restarts = 0

                for pod in pods:

                    status = pod.get(
                        "status",
                        "Unknown"
                    )

                    namespace = pod.get(
                        "namespace",
                        "unknown"
                    )

                    restarts = pod.get(
                        "restarts",
                        0
                    )

                    namespaces.add(namespace)

                    total_restarts += restarts

                    if status == "Running":
                        running += 1
                    else:
                        unhealthy += 1

                    if restarts > 0:

                        restarting.append(
                            f"{namespace}/"
                            f"{pod.get('name')} "
                            f"(restarts={restarts})"
                        )

                    if status == "Pending":

                        pending.append(
                            f"{namespace}/"
                            f"{pod.get('name')}"
                        )

                    if status in [
                        "Failed",
                        "CrashLoopBackOff"
                    ]:

                        failed.append(
                            f"{namespace}/"
                            f"{pod.get('name')}"
                        )

                summary.append(
                    f"Pods: {len(pods)} total, "
                    f"{running} running, "
                    f"{unhealthy} unhealthy, "
                    f"{total_restarts} total restarts"
                )

                summary.append(
                    f"Pod namespaces: "
                    f"{safe_join(sorted(namespaces))}"
                )

                if restarting:

                    summary.append(
                        "Restarting pods: "
                        + safe_join(
                            restarting,
                            limit=10
                        )
                    )

                if pending:

                    summary.append(
                        "Pending pods: "
                        + safe_join(
                            pending,
                            limit=10
                        )
                    )

                if failed:

                    summary.append(
                        "Failed pods: "
                        + safe_join(
                            failed,
                            limit=10
                        )
                    )

            # =================================================
            # Pod diagnostics
            # =================================================

            elif tool == "get_pod_details":

                phase = (
                    result.get("phase")
                    or "?"
                )

                summary.append(
                    f"Pod detail {result.get('namespace')}/"
                    f"{result.get('pod_name')}: phase={phase}, "
                    f"node={result.get('node_name')}"
                )

                bad_bits = []

                for row in (
                    (result.get("containers") or [])
                    + (result.get("init_containers") or [])
                ):

                    if row.get("waiting"):

                        w = row["waiting"]

                        bad_bits.append(
                            f"{row.get('name')}: "
                            f"waiting="
                            f"{w.get('reason')}"
                        )

                    if row.get("terminated"):

                        t = row["terminated"]

                        if (
                            t.get("exit_code")
                            not in (None, 0)
                        ):

                            bad_bits.append(
                                f"{row.get('name')}: "
                                f"exit={t.get('exit_code')} "
                                f"{t.get('reason')}"
                            )

                if bad_bits:

                    summary.append(
                        "Container signals: "
                        + safe_join(
                            bad_bits,
                            limit=6,
                        )
                    )

                warns = []

                for cond in (
                    result.get("conditions") or []
                ):

                    if (
                        cond.get("status") == "False"
                        and (
                            cond.get("type")
                            in (
                                "Ready",
                                "ContainersReady",
                                "PodScheduled",
                            )
                        )
                    ):

                        warns.append(
                            f"{cond.get('type')} "
                            f"({cond.get('reason')}): "
                            f"{cond.get('message', '')}"
                        )

                if warns:

                    summary.append(
                        "Blocking conditions: "
                        + safe_join(
                            warns,
                            limit=3,
                        )
                    )

            elif tool == "get_logs":

                logs_blob = (
                    result.get("logs")
                    or ""
                )

                line_estimate = (
                    logs_blob.count("\n")
                    + (1 if logs_blob else 0)
                )

                tail_meta = []

                tail_meta.append(
                    f"{line_estimate} lines (tail="
                    f"{result.get('tail_lines', '?')})"
                )

                if result.get("previous_container"):

                    tail_meta.append("previous crashed container")

                if result.get("timestamps"):

                    tail_meta.append("with timestamps")

                summary.append(
                    f"Logs {result.get('namespace')}/"
                    f"{result.get('pod')}: "
                    + ", ".join(tail_meta)
                )

            elif tool == (
                "get_deployment_rollout_status"
            ):

                want = (
                    result.get(
                        "replicas_desired",
                    )
                    or 0
                )

                avail = (
                    result.get(
                        "available_replicas",
                    )
                    or 0
                )

                summary.append(
                    f"Deployment {result.get('namespace')}/"
                    f"{result.get('deployment_name')}: "
                    f"avail={avail}/"
                    f"{want}; "
                    f"unavail="
                    f"{result.get('unavailable_replicas', 0)}"
                )

                if result.get("paused"):

                    summary.append(
                        "Deployment is PAUSED"
                    )

                dep_msgs = []

                for cd in (
                    result.get("conditions") or []
                ):

                    ctype = cd.get("type")
                    cstat = cd.get("status")

                    if (
                        ctype == "ReplicaFailure"
                        and cstat == "True"
                    ):

                        dep_msgs.append(
                            f"{ctype}: "
                            f"{cd.get('message', '')}"
                        )

                    elif (
                        ctype in (
                            "Available",
                            "Progressing",
                        )
                        and cstat == "False"
                    ):

                        dep_msgs.append(
                            f"{ctype}: "
                            f"{cd.get('message', '')}"
                        )

                if dep_msgs:

                    summary.append(
                        "Conditions: "
                        + safe_join(
                            dep_msgs,
                            limit=3,
                        )
                    )

            elif tool == (
                "get_config_map_data"
            ):

                keys_out = (
                    result.get(
                        "keys_returned",
                        [],
                    )
                )

                summary.append(
                    f"ConfigMap {result.get('namespace')}/"
                    f"{result.get('config_map_name')}: "
                    f"{len(keys_out)} string keys fetched"
                )

                truncated = (
                    result.get(
                        "value_was_truncated_for_keys",
                    )
                    or []
                )

                if truncated:

                    summary.append(
                        "CM values clipped (keys): "
                        + safe_join(
                            truncated,
                            limit=10,
                        )
                    )

                budget_skip = (
                    result.get(
                        "keys_omitted_due_to_budget",
                    )
                    or []
                )

                if budget_skip:

                    summary.append(
                        "Additional CM keys omitted by budget "
                        f"({len(budget_skip)})"
                    )

            # =================================================
            # Deployments
            # =================================================

            elif tool == "list_deployments":

                deployments = result.get(
                    "deployments",
                    []
                )

                unhealthy_deployments = []

                total_replicas = 0
                total_available = 0

                for dep in deployments:

                    replicas = (
                        dep.get("replicas")
                        or 0
                    )

                    available = (
                        dep.get(
                            "available_replicas"
                        )
                        or 0
                    )

                    total_replicas += replicas
                    total_available += available

                    if available < replicas:

                        unhealthy_deployments.append(
                            f"{dep.get('namespace')}/"
                            f"{dep.get('name')} "
                            f"(available="
                            f"{available}/"
                            f"{replicas})"
                        )

                summary.append(
                    f"Deployments: "
                    f"{len(deployments)} total, "
                    f"{total_available}/"
                    f"{total_replicas} "
                    f"replicas available"
                )

                if unhealthy_deployments:

                    summary.append(
                        "Degraded deployments: "
                        + safe_join(
                            unhealthy_deployments,
                            limit=10
                        )
                    )

            # =================================================
            # Services
            # =================================================

            elif tool == "list_services":

                services = result.get(
                    "services",
                    []
                )

                cluster_ip = 0
                load_balancer = 0
                node_port = 0

                for svc in services:

                    svc_type = svc.get("type")

                    if svc_type == "ClusterIP":
                        cluster_ip += 1

                    elif svc_type == "LoadBalancer":
                        load_balancer += 1

                    elif svc_type == "NodePort":
                        node_port += 1

                summary.append(
                    f"Services: "
                    f"{len(services)} total "
                    f"(ClusterIP={cluster_ip}, "
                    f"LoadBalancer="
                    f"{load_balancer}, "
                    f"NodePort={node_port})"
                )

            # =================================================
            # Endpoints
            # =================================================

            elif tool == "list_endpoints":

                endpoints = result.get(
                    "endpoints",
                    []
                )

                missing = []

                for ep in endpoints:

                    addresses = ep.get(
                        "addresses",
                        []
                    )

                    if not addresses:

                        missing.append(
                            f"{ep.get('namespace')}/"
                            f"{ep.get('name')}"
                        )

                summary.append(
                    f"Endpoints: "
                    f"{len(endpoints)} total"
                )

                if missing:

                    summary.append(
                        "Services without "
                        "endpoints: "
                        + safe_join(
                            missing,
                            limit=10
                        )
                    )

            # =================================================
            # Ingresses
            # =================================================

            elif tool == "list_ingresses":

                ingresses = result.get(
                    "ingresses",
                    []
                )

                hosts = []

                for ing in ingresses:

                    ingress_hosts = (
                        ing.get("hosts", [])
                    )

                    for host in ingress_hosts:

                        if host is not None:
                            hosts.append(host)

                summary.append(
                    f"Ingresses: "
                    f"{len(ingresses)} total"
                )

                if hosts:

                    summary.append(
                        "Ingress hosts: "
                        + safe_join(
                            hosts,
                            limit=10
                        )
                    )

            # =================================================
            # Namespaces
            # =================================================

            elif tool == "list_namespaces":

                namespaces = result.get(
                    "namespaces",
                    []
                )

                active = 0

                for ns in namespaces:

                    if (
                        ns.get("status")
                        == "Active"
                    ):
                        active += 1

                summary.append(
                    f"Namespaces: "
                    f"{len(namespaces)} total, "
                    f"{active} active"
                )

            # =================================================
            # Nodes
            # =================================================

            elif tool == "list_nodes":

                nodes = result.get(
                    "nodes",
                    []
                )

                ready_nodes = 0
                unhealthy_nodes = []

                for node in nodes:

                    conditions = node.get(
                        "conditions",
                        {}
                    )

                    ready = (
                        conditions.get("Ready")
                    )

                    if ready == "True":

                        ready_nodes += 1

                    else:

                        unhealthy_nodes.append(
                            node.get("name")
                        )

                summary.append(
                    f"Nodes: "
                    f"{len(nodes)} total, "
                    f"{ready_nodes} ready"
                )

                if unhealthy_nodes:

                    summary.append(
                        "Unhealthy nodes: "
                        + safe_join(
                            unhealthy_nodes
                        )
                    )

            # =================================================
            # Events
            # =================================================

            elif tool == "list_events":

                events = result.get(
                    "events",
                    []
                )

                warnings = []

                for event in events:

                    if (
                        event.get("type")
                        == "Warning"
                    ):

                        warnings.append(
                            f"{event.get('namespace')} "
                            f"- "
                            f"{event.get('reason')}: "
                            f"{event.get('message')}"
                        )

                summary.append(
                    f"Events: "
                    f"{len(events)} total"
                )

                if warnings:

                    summary.append(
                        "Warning events: "
                        + safe_join(
                            warnings,
                            limit=5
                        )
                    )

            # =================================================
            # Argo CD Applications
            # =================================================

            elif tool == (
                "list_argocd_applications"
            ):

                apps = result.get(
                    "applications",
                    []
                )

                unhealthy_apps = []
                out_of_sync = []

                for app_obj in apps:

                    health = app_obj.get(
                        "health"
                    )

                    sync = app_obj.get(
                        "sync_status"
                    )

                    if health != "Healthy":

                        unhealthy_apps.append(
                            f"{app_obj.get('name')} "
                            f"(health={health})"
                        )

                    if sync != "Synced":

                        out_of_sync.append(
                            f"{app_obj.get('name')} "
                            f"(sync={sync})"
                        )

                summary.append(
                    f"Argo CD applications: "
                    f"{len(apps)} total"
                )

                if unhealthy_apps:

                    summary.append(
                        "Unhealthy Argo CD apps: "
                        + safe_join(
                            unhealthy_apps,
                            limit=10
                        )
                    )

                if out_of_sync:

                    summary.append(
                        "Out-of-sync Argo CD apps: "
                        + safe_join(
                            out_of_sync,
                            limit=10
                        )
                    )

            # =================================================
            # FinOps / capacity signals (SKU + Prom bundle)
            # =================================================

            elif tool == "finops_cluster_signals":

                summary.append(
                    "FinOps snapshot: "
                    f"{result.get('node_count')} nodes, "
                    f"{len(result.get('instance_mix', {}))} instance labels"
                )

                zmix = result.get("zone_mix") or {}

                if zmix:

                    summary.append(
                        f"Zones touched: {len(zmix)} AZs"
                    )

                cloud_hints = (
                    result.get("cloud_hints") or []
                )

                if cloud_hints:

                    summary.append(
                        "Managed nodegroup/pool hints: "
                        + safe_join(
                            cloud_hints,
                            limit=6,
                        )
                    )

                prom_rows = result.get("prometheus") or []

                prom_ok = sum(
                    1
                    for row in prom_rows
                    if row.get("result", {}).get("ok") is True
                )

                summary.append(
                    f"FinOps Prom probes: {prom_ok}/"
                    f"{len(prom_rows)} returned data"
                )

            # =================================================
            # Prometheus bundle snapshot
            # =================================================

            elif tool == "prometheus_common_metrics":

                bundle = result.get("bundle", [])

                ok_n = sum(
                    1
                    for entry in bundle
                    if entry.get(
                        "result",
                        {},
                    ).get(
                        "ok",
                    )
                )

                summary.append(
                    "Prometheus bundle: "
                    f"{ok_n}/"
                    f"{len(bundle)} canned queries OK"
                )

                miss_labels = []

                for entry in bundle:

                    if not entry.get(
                        "result",
                        {},
                    ).get(
                        "ok",
                    ):

                        miss_labels.append(
                            entry.get(
                                "name",
                                "?",
                            )
                        )

                if miss_labels:

                    summary.append(
                        "Prometheus bundle errs: "
                        + safe_join(
                            miss_labels,
                            limit=10,
                        )
                    )

            # =================================================
            # Prometheus
            # =================================================

            elif tool == "query_prometheus":

                query = result.get(
                    "query"
                )

                prom_result = result.get(
                    "result",
                    {}
                )

                status = prom_result.get(
                    "status"
                )

                if status == "success":

                    data = prom_result.get(
                        "data",
                        {}
                    )

                    result_count = len(
                        data.get(
                            "result",
                            []
                        )
                    )

                    summary.append(
                        f"Prometheus query "
                        f"succeeded "
                        f"(query={query}, "
                        f"results="
                        f"{result_count})"
                    )

                else:

                    summary.append(
                        f"Prometheus query "
                        f"failed "
                        f"(query={query})"
                    )
        # =================================================
        # Serialize raw sandbox outputs for the model (primary)
        # =================================================

        investigation_payload = pack_tool_results_payload(
            tool_results
        )

        # =================================================
        # STEP 5B: Ask Gemini to analyze tool data
        # =================================================

        analysis_visual_intro = ""

        visual_scope_notice = ""

        if screenshot_primary_question:

            visual_scope_notice = """
=========================================================
SCREENSHOT-FIRST (USER TEXT SHORT OR EMPTY)
=========================================================
The user leaned on screenshot(s); do **not** turn this into an infrastructure survey.

• Aim **≤ ~200 words** unless the screenshots plus user text clearly demand a deeper runbook.
• Use **≤ 2 headings** (### …). Prefer: what the error likely is → what to verify next → stop.
• **Do not** add “Other observations”, “aside”, “monitoring posture”, capacity-planning asides,
  Prometheus catalog walk-throughs, or empty-time-series detective work unless that signal **directly**
  proves or falsifies **the screenshot’s error**.
• Prometheus / kube-state empties and canned-query failures inside the sandbox are **background noise** here:
  do **not** mention them at all unless you need them for one sentence to explain the failing **service/path**
  the user showed.
"""

        elif inline_visuals:

            visual_scope_notice = """
=========================================================
VISUALS PRESENT — STAY ON-ASK
=========================================================
Screenshots are clues (exact message, hostname, dashboard). Prefer answering the user’s **stated**
question plus what the image shows — avoid broad “audit the cluster” narration or filler sections.

"""

        if inline_visuals:

            analysis_visual_intro = f"""
=========================================================
SCREENSHOTS / VISUALS (MATCH TO LIVE SIGNALS BELOW)
=========================================================

Treat pixels as USER-facing evidence only (URLs, hostnames, error text, panels). Tie conclusions to SANDBOX JSON;
if live data contradicts the image, say so once plainly. Avoid generic remediation not grounded in retrieved data.

{visual_scope_notice}
"""

        analysis_prompt = f"""{analysis_visual_intro}
You are a staff-level SRE answering Kubernetes / GitOps questions
from read-only sandbox data supplied below.

=========================================================
FACTS VS NOISE — CRITICAL OUTPUT RULES
=========================================================

Ground every concrete claim in the JSON data. Internally rely on RAW TOOL OUTPUTS first,
then the EXECUTIVE SUMMARY. When you write for the USER:

• Write for a human chat: short, direct, pleasant to skim.
• Default length **about 180–340 words**. If the VISUAL-FIRST block above applied, obey its tighter limit.
• For narrow asks (single error screenshot, single symptom): **prioritize diagnosis + next checks** —
  omit unrelated tooling outcomes the user never asked about.
• Lead with **one short paragraph**: the takeaway + top 2–3 actions when relevant.
• Use at most **3 section headings** (### Heading). **Never** use headings like “Other observations” only to dump
  tangential findings (Prom scrape gaps, empty kube-state panels, canned PromQL quirks) unrelated to the user’s thread.
• Use short bullets (**-** item). No wall of bullets — merge overlapping points.
• **Never** cite tools, endpoints, JSON keys, or phrases like “RAW TOOL OUTPUTS”, “list_pods”,
  “according to EXECUTIVE SUMMARY”, or `(tool: …)`. The user never saw those internals.
• **Never** duplicate the same observation in multiple sections.
• Omit “Observed facts / Known issues / Disclaimer” scaffolding unless essential.
• If metrics are missing or Prom queries failed, mention **only when** skipping it would confuse the diagnosis you are
  delivering **for this thread** — never as a standalone monitoring sermon.

{prompt_focus_separator}=========================================================
USER REQUEST
=========================================================

{request.message}

=========================================================
EXECUTIVE SUMMARY (DIGEST)
=========================================================

{chr(10).join(summary)}

=========================================================
RAW TOOL OUTPUTS (JSON TEXT)
=========================================================

{investigation_payload}

=========================================================
STYLE
=========================================================

Markdown is OK: ### headings, **bold**, hyphen bullets **-**.
No ASCII tables or HTML. No preamble like “Here's an analysis of…”.
"""

        analysis_response = call_gemini(
            analysis_prompt,
            inline_visuals,
        )

        # Handle Gemini errors
        if analysis_response.get("error"):

            return {
                "error": analysis_response.get("error"),
                "details": analysis_response.get("raw_response", ""),
                "summary": summary
            }

        final_response = extract_text(analysis_response)

        return {
            "mode": "tool_analysis",
            "summary": summary,
            "response": final_response
        }

    except Exception as e:

        return {
            "error": str(e)
        }