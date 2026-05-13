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
import requests
import os
import json

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


# =========================================================
# Request model
# =========================================================
class ChatRequest(BaseModel):
    message: str


# =========================================================
# Health check
# =========================================================
@app.get("/")
def root():
    return {"status": "Agent Controller running"}


# =========================================================
# Gemini API call
# =========================================================
def call_gemini(prompt):

    import time

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
                            "parts": [
                                {"text": prompt}
                            ]
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

        text = parts[0].get("text", "")

        return text.strip()

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
            "tail_lines": "default 200",
        },
        "detail": (
            "Container logs — use when events/pods show crashes "
            "or errors, not only when user types 'logs'."
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
]


AVAILABLE_TOOLS = [entry["name"] for entry in TOOL_CATALOG]


# =========================================================
# Context packing for final LLM synthesis
# =========================================================
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
    }


# =========================================================
@app.post("/chat")
def chat(request: ChatRequest):

    try:

        # =================================================
        # STEP 1: Ask Gemini if tools are needed
        # =================================================

        tool_prompt = f"""
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
   tailored PromQL when you know the exact metric/question.
6. Include list_events when diagnosing instability; include get_logs when
   pods/events point to crash loops or Failed phases (pass namespace/pod_name
   when inferable, otherwise use app_label or namespace-only discovery).
7. It is acceptable to schedule many tools in parallel — prefer missing
   signals over saving API calls.
8. Skip tools only when obviously unrelated (e.g. pure generic small-talk).

=========================================================
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

        tool_decision = call_gemini(tool_prompt)

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
            ]

            message_lower = request.message.lower()

            should_use_tools = any(
                keyword in message_lower
                for keyword in kubernetes_keywords
            )

            if should_use_tools:

                decision_json = {
                    "needs_tools": True,

                    # Safe wide snapshot when Gemini's JSON planner output
                    # is unparsable.
                    "tool_calls": [
                        {"tool": "list_pods", "arguments": {}},
                        {"tool": "list_deployments", "arguments": {}},
                        {
                            "tool": "list_stateful_sets",
                            "arguments": {},
                        },
                        {
                            "tool": "list_daemon_sets",
                            "arguments": {},
                        },
                        {
                            "tool": "list_cron_jobs",
                            "arguments": {},
                        },
                        {
                            "tool": "list_jobs",
                            "arguments": {"limit": 120},
                        },
                        {"tool": "list_services", "arguments": {}},
                        {"tool": "list_endpoints", "arguments": {}},
                        {"tool": "list_ingresses", "arguments": {}},
                        {"tool": "list_namespaces", "arguments": {}},
                        {"tool": "list_nodes", "arguments": {}},
                        {
                            "tool": "list_events",
                            "arguments": {},
                        },
                        {
                            "tool": ("list_horizontal_pod_autoscalers"),
                            "arguments": {},
                        },
                        {"tool": "list_pvcs", "arguments": {}},
                        {"tool": "list_pvs", "arguments": {}},
                        {
                            "tool": "list_storage_classes",
                            "arguments": {},
                        },
                        {
                            "tool": "list_resource_quotas",
                            "arguments": {},
                        },
                        {
                            "tool": "list_limit_ranges",
                            "arguments": {},
                        },
                        {
                            "tool": "list_argocd_applications",
                            "arguments": {},
                        },
                        {
                            "tool": ("prometheus_common_metrics"),
                            "arguments": {},
                        },
                    ],
                }

            else:

                decision_json = {
                    "needs_tools": False
                }

        needs_tools = decision_json.get("needs_tools", False)

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

User message:
{request.message}
"""

            response = call_gemini(normal_prompt)

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
            # Prometheus bundle snapshot
            # =================================================

            elif tool == "prometheus_common_metrics":

                bundle = result.get("bundle", [])

                summary.append(
                    "Prometheus bundle: "
                    f"{len(bundle)} canned queries"
                )

                for entry in bundle[:6]:

                    label = entry.get("name", "?")

                    outcome = entry.get("result", {})

                    if outcome.get("ok"):

                        summary.append(
                            f"- {label}: OK"
                        )

                    else:

                        extra = outcome.get(
                            "status_code"
                        ) or outcome.get(
                            "error",
                            "",
                        )

                        summary.append(
                            f"- {label}: ERR "
                            f"{extra}"
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

        analysis_prompt = f"""
You are a staff-level SRE answering Kubernetes / GitOps / capacity questions
from read-only sandbox data supplied below.

=========================================================
FACTS VS NOISE — CRITICAL OUTPUT RULES
=========================================================

Ground every concrete claim in the JSON data. Internally rely on RAW TOOL OUTPUTS first,
then the EXECUTIVE SUMMARY. When you write for the USER:

• Write for a human chat: short, direct, pleasant to skim.
• Default length: about 250–450 words. Go shorter for simple asks; stretch only when the question truly needs depth.
• Lead with **one short paragraph**: the takeaway + top 2–3 actions.
• Use at most **3 section headings** (use ### Heading). Skip filler sections entirely.
• Use short bullets (**-** item). No wall of bullets — merge overlapping points.
• **Never** cite tools, endpoints, JSON keys, or phrases like “RAW TOOL OUTPUTS”, “list_pods”,
  “according to EXECUTIVE SUMMARY”, or `(tool: …)`. The user never saw those internals.
• **Never** duplicate the same observation in multiple sections.
• Omit “Observed facts / Known issues / Disclaimer” scaffolding unless essential.
• If metrics are missing or Prom queries failed, say it once in plain language — no sermon on scrape config.

=========================================================
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

        analysis_response = call_gemini(analysis_prompt)

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