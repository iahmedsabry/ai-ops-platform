from fastapi import FastAPI
from pydantic import BaseModel

# Kubernetes config
from kubernetes import config

# Kubernetes APIs
from kubernetes.client import (
    CoreV1Api,
    AppsV1Api,
    NetworkingV1Api,
    StorageV1Api,
    BatchV1Api,
    AutoscalingV2Api,
    CustomObjectsApi,
)

# Prometheus HTTP client
import requests

app = FastAPI()

# =========================================================
# Kubernetes authentication
# =========================================================
config.load_incluster_config()

# =========================================================
# Kubernetes API clients
# =========================================================

core_v1 = CoreV1Api()
apps_v1 = AppsV1Api()
networking_v1 = NetworkingV1Api()
storage_v1 = StorageV1Api()
batch_v1 = BatchV1Api()
autoscaling_v2 = AutoscalingV2Api()
custom_api = CustomObjectsApi()

# =========================================================
# Prometheus configuration
# =========================================================

PROMETHEUS_URL = (
    "http://prometheus.monitoring.svc.cluster.local:9090"
)

# Lightweight bundle when the orchestrator has not chosen exact PromQL yet.
COMMON_PROM_QUERIES = [
    ("up_scrapes_sample", "up"),
    (
        "container_cpu_namespace_5m",
        'topk(40, sum by (namespace) ('
        'rate(container_cpu_usage_seconds_total{container!="",container!="POD"}[5m])))'
    ),
    (
        "container_mem_working_set_namespace",
        'topk(40, sum by (namespace) ('
        'container_memory_working_set_bytes{container!="",container!="POD"})))'
    ),
    (
        "kube_pod_status_phase",
        'sum by (namespace, phase) (kube_pod_status_phase{phase=~"Pending|Unknown|Failed"} == 1)'
    ),
]


def _prometheus_query_one(query):

    """
    Runs a single instant PromQL query.
    """

    try:

        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=12
        )

        if response.status_code != 200:

            return {
                "ok": False,
                "status_code": (
                    response.status_code
                ),
                "snippet": (
                    response.text[:500]
                ),
            }

        try:

            return {
                "ok": True,
                "body": (
                    response.json()
                ),
            }

        except Exception:

            return {
                "ok": False,
                "error": "invalid_json",
                "snippet": (
                    response.text[:500]
                ),
            }

    except Exception as exc:

        return {
            "ok": False,
            "error": str(exc),
        }


# =========================================================
# Allowed tools
# =========================================================

ALLOWED_TOOLS = {
    "list_pods",
    "get_logs",
    "list_deployments",
    "list_services",
    "list_endpoints",
    "list_ingresses",
    "list_namespaces",
    "list_nodes",
    "list_events",
    "list_argocd_applications",
    "query_prometheus",
    "prometheus_common_metrics",
    "list_stateful_sets",
    "list_daemon_sets",
    "list_cron_jobs",
    "list_jobs",
    "list_horizontal_pod_autoscalers",
    "list_pvcs",
    "list_pvs",
    "list_storage_classes",
    "list_resource_quotas",
    "list_limit_ranges",
}

# =========================================================
# Request model
# =========================================================
class ToolRequest(BaseModel):
    tool: str
    arguments: dict = {}


# =========================================================
# Health check
# =========================================================
@app.get("/")
def root():

    return {
        "status": "sandbox running"
    }


# =========================================================
# Main execution endpoint
# =========================================================
@app.post("/execute")
def execute(request: ToolRequest):

    # =====================================================
    # Tool allow-list enforcement
    # =====================================================

    if request.tool not in ALLOWED_TOOLS:

        return {
            "error": (
                f"Tool not allowed: "
                f"{request.tool}"
            )
        }

    # =====================================================
    # Tool: list_pods
    # =====================================================

    if request.tool == "list_pods":

        pods = (
            core_v1.list_pod_for_all_namespaces()
        )

        results = []

        for pod in pods.items:

            restart_count = 0

            container_states = []

            ready_containers = 0
            total_containers = 0

            if pod.status.container_statuses:

                total_containers = len(
                    pod.status.container_statuses
                )

                for container in (
                    pod.status.container_statuses
                ):

                    restart_count += (
                        container.restart_count
                    )

                    if container.ready:
                        ready_containers += 1

                    state = "unknown"

                    if container.state.running:
                        state = "running"

                    elif container.state.waiting:
                        state = (
                            container.state.waiting.reason
                        )

                    elif container.state.terminated:
                        state = (
                            container.state.terminated.reason
                        )

                    container_states.append({
                        "name": container.name,
                        "ready": container.ready,
                        "restart_count": (
                            container.restart_count
                        ),
                        "state": state
                    })

            resources = []

            for container in pod.spec.containers:

                resources.append({
                    "container": container.name,
                    "requests": (
                        container.resources.requests
                        or {}
                    ),
                    "limits": (
                        container.resources.limits
                        or {}
                    )
                })

            results.append({
                "name": pod.metadata.name,
                "namespace": (
                    pod.metadata.namespace
                ),
                "status": pod.status.phase,
                "node": pod.spec.node_name,
                "pod_ip": pod.status.pod_ip,
                "host_ip": pod.status.host_ip,
                "start_time": str(
                    pod.status.start_time
                ),
                "restarts": restart_count,
                "ready_containers": (
                    ready_containers
                ),
                "total_containers": (
                    total_containers
                ),
                "container_states": (
                    container_states
                ),
                "resources": resources
            })

        return {
            "tool": "list_pods",
            "count": len(results),
            "pods": results
        }

    # =====================================================
    # Tool: get_logs
    # =====================================================

    elif request.tool == "get_logs":

        namespace = request.arguments.get(
            "namespace",
            "default"
        )

        app_label = request.arguments.get(
            "app_label"
        )

        pod_name_arg = request.arguments.get(
            "pod_name"
        )

        container_name = request.arguments.get(
            "container_name"
        )

        tail_lines = request.arguments.get(
            "tail_lines",
            200
        )

        if pod_name_arg:

            kw = dict(
                name=pod_name_arg,
                namespace=namespace,
                tail_lines=tail_lines,
            )

            if container_name:
                kw["container"] = container_name

            logs = core_v1.read_namespaced_pod_log(**kw)

            return {
                "tool": "get_logs",
                "pod": pod_name_arg,
                "namespace": namespace,
                "logs": logs,
            }

        label_selector = (
            f"app={app_label}"
            if app_label
            else ""
        )

        pods = core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector
        )

        if not pods.items:

            return {
                "error": "No pods found"
            }

        pod_name = None

        for pod in pods.items:

            if pod.status.phase == "Running":

                pod_name = (
                    pod.metadata.name
                )

                break

        if not pod_name:

            return {
                "error": (
                    "No running pods found"
                )
            }

        kw = dict(
            name=pod_name,
            namespace=namespace,
            tail_lines=tail_lines,
        )

        if container_name:
            kw["container"] = container_name

        logs = core_v1.read_namespaced_pod_log(**kw)

        return {
            "tool": "get_logs",
            "pod": pod_name,
            "namespace": namespace,
            "logs": logs
        }

    # =====================================================
    # Tool: list_deployments
    # =====================================================

    elif request.tool == "list_deployments":

        deployments = (
            apps_v1.list_deployment_for_all_namespaces()
        )

        results = []

        for dep in deployments.items:

            strategy = None

            if dep.spec.strategy:
                strategy = dep.spec.strategy.type

            results.append({
                "name": dep.metadata.name,

                "namespace": (
                    dep.metadata.namespace
                ),

                "replicas": (
                    dep.spec.replicas or 0
                ),

                "ready_replicas": (
                    dep.status.ready_replicas or 0
                ),

                "available_replicas": (
                    dep.status.available_replicas
                    or 0
                ),

                "updated_replicas": (
                    dep.status.updated_replicas
                    or 0
                ),

                "unavailable_replicas": (
                    dep.status.unavailable_replicas
                    or 0
                ),

                "strategy": strategy
            })

        return {
            "tool": "list_deployments",
            "count": len(results),
            "deployments": results
        }

    # =====================================================
    # Tool: list_services
    # =====================================================

    elif request.tool == "list_services":

        services = (
            core_v1.list_service_for_all_namespaces()
        )

        results = []

        for svc in services.items:

            results.append({
                "name": svc.metadata.name,
                "namespace": (
                    svc.metadata.namespace
                ),
                "type": svc.spec.type,
                "cluster_ip": (
                    svc.spec.cluster_ip
                ),

                "ports": [
                    {
                        "port": p.port,
                        "target_port": (
                            p.target_port
                        ),
                        "protocol": p.protocol
                    }
                    for p in svc.spec.ports
                ]
            })

        return {
            "tool": "list_services",
            "count": len(results),
            "services": results
        }

    # =====================================================
    # Tool: list_ingresses
    # =====================================================

    elif request.tool == "list_ingresses":

        ingresses = (
            networking_v1
            .list_ingress_for_all_namespaces()
        )

        results = []

        for ing in ingresses.items:

            hosts = []

            if ing.spec.rules:

                for rule in ing.spec.rules:

                    hosts.append(rule.host)

            results.append({
                "name": ing.metadata.name,
                "namespace": (
                    ing.metadata.namespace
                ),
                "hosts": hosts
            })

        return {
            "tool": "list_ingresses",
            "count": len(results),
            "ingresses": results
        }

    # =====================================================
    # Tool: list_namespaces
    # =====================================================

    elif request.tool == "list_namespaces":

        namespaces = (
            core_v1.list_namespace()
        )

        results = []

        for ns in namespaces.items:

            results.append({
                "name": ns.metadata.name,
                "status": ns.status.phase
            })

        return {
            "tool": "list_namespaces",
            "count": len(results),
            "namespaces": results
        }

    # =====================================================
    # Tool: list_nodes
    # =====================================================

    elif request.tool == "list_nodes":

        nodes = core_v1.list_node()

        results = []

        for node in nodes.items:

            conditions = {}

            for condition in (
                node.status.conditions
            ):

                conditions[
                    condition.type
                ] = condition.status

            results.append({
                "name": node.metadata.name,

                "instance_type": (
                    node.metadata.labels.get(
                        "node.kubernetes.io/instance-type"
                    )
                ),

                "kubernetes_version": (
                    node.status.node_info.kubelet_version
                ),

                "os_image": (
                    node.status.node_info.os_image
                ),

                "container_runtime": (
                    node.status.node_info
                    .container_runtime_version
                ),

                "conditions": conditions,

                "allocatable": (
                    node.status.allocatable
                ),

                "capacity": (
                    node.status.capacity
                )
            })

        return {
            "tool": "list_nodes",
            "count": len(results),
            "nodes": results
        }

    # =====================================================
    # Tool: list_events
    # =====================================================

    elif request.tool == "list_events":

        namespace = request.arguments.get(
            "namespace"
        )

        if namespace:

            events = (
                core_v1.list_namespaced_event(
                    namespace
                )
            )

        else:

            events = (
                core_v1
                .list_event_for_all_namespaces()
            )

        results = []

        for event in events.items:

            # Filter noisy Normal events
            if event.type != "Warning":
                continue

            results.append({
                "namespace": (
                    event.metadata.namespace
                ),

                "type": event.type,

                "reason": event.reason,

                "message": event.message,

                "involved_object": (
                    event.involved_object.kind
                ),

                "object_name": (
                    event.involved_object.name
                ),

                "timestamp": str(
                    event.last_timestamp
                    or event.event_time
                    or event.first_timestamp
                )
            })

        return {
            "tool": "list_events",
            "count": len(results),
            "events": results
        }

    # =====================================================
    # Tool: list_argocd_applications
    # =====================================================

    elif request.tool == "list_argocd_applications":

        apps = (
            custom_api
            .list_cluster_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                plural="applications"
            )
        )

        results = []

        for app_obj in apps.get("items", []):

            status = app_obj.get(
                "status",
                {}
            )

            health = (
                status.get("health", {})
                .get("status")
            )

            sync = (
                status.get("sync", {})
                .get("status")
            )

            results.append({
                "name": (
                    app_obj["metadata"]["name"]
                ),

                "namespace": (
                    app_obj["metadata"]
                    ["namespace"]
                ),

                "health": health,

                "sync_status": sync
            })

        return {
            "tool": "list_argocd_applications",
            "count": len(results),
            "applications": results
        }

    # =====================================================
    # Tool: query_prometheus
    # =====================================================

    elif request.tool == "query_prometheus":

        query = request.arguments.get(
            "query"
        )

        if not query:

            return {
                "error": (
                    "Prometheus query "
                    "is required"
                )
            }

        try:

            response = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=10
            )

            print(
                "Prometheus status code:",
                response.status_code
            )

            print(
                "Prometheus raw response:"
            )

            print(response.text)

            # =================================================
            # Handle non-200 responses
            # =================================================

            if response.status_code != 200:

                return {
                    "error": (
                        f"Prometheus returned "
                        f"{response.status_code}"
                    ),
                    "raw_response": (
                        response.text
                    )
                }

            # =================================================
            # Safely parse JSON
            # =================================================

            try:

                parsed_json = (
                    response.json()
                )

            except Exception as json_error:

                return {
                    "error": (
                        "Failed to parse "
                        "Prometheus JSON"
                    ),

                    "raw_response": (
                        response.text
                    ),

                    "exception": (
                        str(json_error)
                    )
                }

            return {
                "tool": "query_prometheus",
                "query": query,
                "result": parsed_json
            }

        except Exception as request_error:

            return {
                "error": str(request_error)
            }

    # =====================================================
    # Tool: prometheus_common_metrics
    # =====================================================

    elif request.tool == "prometheus_common_metrics":

        bundle_results = []

        for label, query in COMMON_PROM_QUERIES:

            outcome = _prometheus_query_one(query)

            bundle_results.append({
                "name": label,
                "query": query,
                "result": outcome,
            })

        return {
            "tool": (
                "prometheus_common_metrics"
            ),
            "queries_run": (
                len(bundle_results)
            ),
            "bundle": bundle_results,
        }

    # =====================================================
    # Tool: list_stateful_sets
    # =====================================================

    elif request.tool == "list_stateful_sets":

        items = (
            apps_v1.list_stateful_set_for_all_namespaces().items
        )

        results = []

        for sts in items:

            results.append({
                "name": sts.metadata.name,

                "namespace": (
                    sts.metadata.namespace
                ),

                "replicas": sts.spec.replicas or 0,

                "ready_replicas": (
                    sts.status.ready_replicas or 0
                ),

                "updated_replicas": (
                    getattr(sts.status, 'updated_replicas', None)
                    or 0
                ),
            })

        return {
            "tool": "list_stateful_sets",
            "count": len(results),
            "stateful_sets": results,
        }

    # =====================================================
    # Tool: list_daemon_sets
    # =====================================================

    elif request.tool == "list_daemon_sets":

        items = (
            apps_v1.list_daemon_set_for_all_namespaces().items
        )

        results = []

        for ds in items:

            desired = ds.status.desired_number_scheduled or 0

            ready = ds.status.number_ready or 0

            results.append({
                "name": ds.metadata.name,

                "namespace": (
                    ds.metadata.namespace
                ),

                "desired_scheduled": desired,

                "ready": ready,

                "updated_scheduled": (
                    ds.status.updated_number_scheduled
                    or 0
                ),
            })

        return {
            "tool": "list_daemon_sets",
            "count": len(results),
            "daemon_sets": results,
        }

    # =====================================================
    # Tool: list_cron_jobs
    # =====================================================

    elif request.tool == "list_cron_jobs":

        items = (
            batch_v1.list_cron_job_for_all_namespaces().items
        )

        results = []

        for cj in items:

            suspended = False

            if cj.spec.suspend:

                suspended = True

            results.append({
                "name": cj.metadata.name,

                "namespace": (
                    cj.metadata.namespace
                ),

                "schedule": cj.spec.schedule,

                "suspend": suspended,

                "active_jobs": (
                    len(cj.status.active or [])
                ),

                "last_schedule_time": str(
                    cj.status.last_schedule_time or ""
                ),
            })

        return {
            "tool": "list_cron_jobs",
            "count": len(results),
            "cron_jobs": results,
        }

    # =====================================================
    # Tool: list_jobs
    # =====================================================

    elif request.tool == "list_jobs":

        items = (
            batch_v1.list_job_for_all_namespaces().items
        )

        def sort_key(job):

            ts = job.metadata.creation_timestamp

            if ts is None:

                return ""

            return ts.isoformat()

        sorted_items = sorted(
            items,
            key=sort_key,
            reverse=True,
        )

        limit = int(
            request.arguments.get("limit", 120)
        )

        if limit < 1:

            limit = 120

        if limit > 300:

            limit = 300

        trimmed = sorted_items[:limit]

        results = []

        for job in trimmed:

            status = job.status

            results.append({
                "name": job.metadata.name,

                "namespace": (
                    job.metadata.namespace
                ),

                "active": (
                    status.active or 0
                ),

                "succeeded": (
                    status.succeeded or 0
                ),

                "failed": (
                    status.failed or 0
                ),

                "creation_time": str(
                    job.metadata.creation_timestamp
                    or ""
                ),

                "completion_time": str(
                    status.completion_time or ""
                ),
            })

        return {
            "tool": "list_jobs",
            "count": len(results),
            "jobs": results,
        }

    # =====================================================
    # Tool: list_horizontal_pod_autoscalers
    # =====================================================

    elif request.tool == "list_horizontal_pod_autoscalers":

        items = (
            autoscaling_v2
            .list_horizontal_pod_autoscaler_for_all_namespaces()
            .items
        )

        results = []

        for hpa in items:

            ref = hpa.spec.scale_target_ref

            results.append({
                "name": hpa.metadata.name,

                "namespace": (
                    hpa.metadata.namespace
                ),

                "target_kind": ref.kind,

                "target_name": ref.name,

                "min_replicas": (
                    hpa.spec.min_replicas
                ),

                "max_replicas": (
                    hpa.spec.max_replicas
                ),

                "current_replicas": (
                    hpa.status.current_replicas
                ),

                "desired_replicas": (
                    hpa.status.desired_replicas
                ),
            })

        return {
            "tool": (
                "list_horizontal_pod_autoscalers"
            ),
            "count": len(results),
            "hpas": results,
        }

    # =====================================================
    # Tool: list_pvcs
    # =====================================================

    elif request.tool == "list_pvcs":

        items = (
            core_v1
            .list_persistent_volume_claim_for_all_namespaces()
            .items
        )

        results = []

        for pvc in items:

            results.append({
                "name": pvc.metadata.name,

                "namespace": (
                    pvc.metadata.namespace
                ),

                "status_phase": (
                    pvc.status.phase
                ),

                "storage_class": (
                    pvc.spec.storage_class_name
                ),

                "volume_name": (
                    pvc.spec.volume_name
                ),

                "requests": (
                    pvc.spec.resources.requests
                    if pvc.spec.resources
                    else {}
                ),
            })

        return {
            "tool": "list_pvcs",
            "count": len(results),
            "pvcs": results,
        }

    # =====================================================
    # Tool: list_pvs
    # =====================================================

    elif request.tool == "list_pvs":

        items = core_v1.list_persistent_volume().items

        results = []

        for pv in items:

            results.append({
                "name": pv.metadata.name,

                "status_phase": (
                    pv.status.phase
                ),

                "storage_class": (
                    pv.spec.storage_class_name
                ),

                "capacity": (
                    pv.spec.capacity
                    if pv.spec.capacity
                    else {}
                ),

                "claim_ref": (
                    {
                        "namespace": (
                            pv.spec.claim_ref.namespace
                        ),
                        "name": (
                            pv.spec.claim_ref.name
                        ),
                    }
                    if pv.spec.claim_ref
                    else None
                ),
            })

        return {
            "tool": "list_pvs",
            "count": len(results),
            "pvs": results,
        }

    # =====================================================
    # Tool: list_storage_classes
    # =====================================================

    elif request.tool == "list_storage_classes":

        items = (
            storage_v1.list_storage_class().items
        )

        results = []

        for sc in items:

            results.append({
                "name": sc.metadata.name,

                "provisioner": sc.provisioner,

                "reclaim_policy": (
                    sc.reclaim_policy
                ),

                "volume_binding_mode": (
                    sc.volume_binding_mode
                ),
            })

        return {
            "tool": "list_storage_classes",
            "count": len(results),
            "storage_classes": results,
        }

    # =====================================================
    # Tool: list_resource_quotas
    # =====================================================

    elif request.tool == "list_resource_quotas":

        items = (
            core_v1
            .list_resource_quota_for_all_namespaces()
            .items
        )

        results = []

        for rq in items:

            results.append({
                "name": rq.metadata.name,

                "namespace": (
                    rq.metadata.namespace
                ),

                "hard": rq.spec.hard or {},

                "used": (
                    rq.status.used or {}
                ),
            })

        return {
            "tool": "list_resource_quotas",
            "count": len(results),
            "resource_quotas": results,
        }

    # =====================================================
    # Tool: list_limit_ranges
    # =====================================================

    elif request.tool == "list_limit_ranges":

        items = (
            core_v1
            .list_limit_range_for_all_namespaces()
            .items
        )

        results = []

        for lr in items:

            limits_out = []

            if lr.spec.limits:

                for lim in lr.spec.limits:

                    limits_out.append({
                        "type": lim.type,

                        "default": (
                            lim.default or {}
                        ),

                        "default_request": (
                            lim.default_request or {}
                        ),

                        "max": lim.max or {},

                        "min": lim.min or {},
                    })

            results.append({
                "name": lr.metadata.name,

                "namespace": (
                    lr.metadata.namespace
                ),

                "limits": limits_out,
            })

        return {
            "tool": "list_limit_ranges",
            "count": len(results),
            "limit_ranges": results,
        }

    # =====================================================
    # Tool: list_endpoints
    # =====================================================

    elif request.tool == "list_endpoints":

        endpoints = (
            core_v1
            .list_endpoints_for_all_namespaces()
        )

        results = []

        for ep in endpoints.items:

            addresses = []

            if ep.subsets:

                for subset in ep.subsets:

                    if subset.addresses:

                        for addr in (
                            subset.addresses
                        ):

                            addresses.append(
                                addr.ip
                            )

            results.append({
                "name": ep.metadata.name,
                "namespace": (
                    ep.metadata.namespace
                ),
                "addresses": addresses
            })

        return {
            "tool": "list_endpoints",
            "count": len(results),
            "endpoints": results
        }

    # =====================================================
    # Unknown tool
    # =====================================================

    return {
        "error": (
            f"Unknown tool: "
            f"{request.tool}"
        )
    }