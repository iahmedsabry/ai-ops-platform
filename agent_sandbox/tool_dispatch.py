"""Per-tool cluster reads; one dispatch function until split into registry callables."""
from kubernetes.client.rest import ApiException
import requests
import datetime
from collections import Counter

from agent_sandbox.clients import (
    PROMETHEUS_URL,
    COMMON_PROM_QUERIES,
    apps_v1,
    autoscaling_v2,
    batch_v1,
    core_v1,
    custom_api,
    networking_v1,
    storage_v1,
    _clamp_int,
    _prometheus_query_one,
    _truncate_text,
)


def _labels_match_selector(labels, selector):
    if not selector:
        return False
    pod_labels = labels or {}
    for key, value in selector.items():
        if pod_labels.get(key) != value:
            return False
    return True


def _service_port_value(service_port):
    return (
        getattr(service_port, "number", None)
        or getattr(service_port, "name", None)
    )


def _parse_cpu_to_cores(value):
    if value in (None, ""):
        return 0.0
    text = str(value).strip()
    if text.endswith("m"):
        return float(text[:-1]) / 1000.0
    return float(text)


def _parse_bytes(value):
    if value in (None, ""):
        return 0.0
    text = str(value).strip()
    units = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "Ti": 1024 ** 4,
        "Pi": 1024 ** 5,
        "K": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3,
        "T": 1000 ** 4,
        "P": 1000 ** 5,
    }
    for suffix, multiplier in units.items():
        if text.endswith(suffix):
            return float(text[:-len(suffix)]) * multiplier
    return float(text)


def _percentile_threshold(values, percentile):
    if not values:
        return 0.0
    ranked = sorted(values)
    idx = int((len(ranked) - 1) * (percentile / 100.0))
    return ranked[idx]


def _build_service_topology(namespace=None):
    if namespace:
        pods = core_v1.list_namespaced_pod(namespace).items
        services = core_v1.list_namespaced_service(namespace).items
        endpoints = core_v1.list_namespaced_endpoints(namespace).items
        ingresses = networking_v1.list_namespaced_ingress(namespace).items
        deployments = apps_v1.list_namespaced_deployment(namespace).items
        stateful_sets = apps_v1.list_namespaced_stateful_set(namespace).items
        daemon_sets = apps_v1.list_namespaced_daemon_set(namespace).items
    else:
        pods = core_v1.list_pod_for_all_namespaces().items
        services = core_v1.list_service_for_all_namespaces().items
        endpoints = core_v1.list_endpoints_for_all_namespaces().items
        ingresses = networking_v1.list_ingress_for_all_namespaces().items
        deployments = apps_v1.list_deployment_for_all_namespaces().items
        stateful_sets = apps_v1.list_stateful_set_for_all_namespaces().items
        daemon_sets = apps_v1.list_daemon_set_for_all_namespaces().items

    pod_index = {}

    for pod in pods:
        ns = pod.metadata.namespace
        pod_index.setdefault(ns, []).append(pod)

    endpoint_index = {}

    for endpoint in endpoints:
        key = (
            endpoint.metadata.namespace,
            endpoint.metadata.name,
        )
        addresses = []
        not_ready = []
        for subset in endpoint.subsets or []:
            for addr in subset.addresses or []:
                addresses.append(addr.ip)
            for addr in subset.not_ready_addresses or []:
                not_ready.append(addr.ip)
        endpoint_index[key] = {
            "ready_addresses": addresses,
            "not_ready_addresses": not_ready,
        }

    workload_index = {}

    for workload_kind, items in (
        ("Deployment", deployments),
        ("StatefulSet", stateful_sets),
        ("DaemonSet", daemon_sets),
    ):
        for item in items:
            selector = (
                getattr(item.spec.selector, "match_labels", None)
                or {}
            )
            workload_index.setdefault(item.metadata.namespace, []).append({
                "kind": workload_kind,
                "name": item.metadata.name,
                "selector": selector,
            })

    return {
        "pods": pods,
        "pod_index": pod_index,
        "services": services,
        "ingresses": ingresses,
        "endpoint_index": endpoint_index,
        "workload_index": workload_index,
    }


def dispatch_tool(tool: str, arguments: dict):
    if tool == "list_pods":

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

    elif tool == "get_logs":

        namespace = arguments.get(
            "namespace",
            "default"
        )

        app_label = arguments.get(
            "app_label"
        )

        pod_name_arg = arguments.get(
            "pod_name"
        )

        container_name = arguments.get(
            "container_name"
        )

        tail_lines = _clamp_int(
            arguments.get(
                "tail_lines",
                200,
            ),
            default=200,
            minimum=1,
            maximum=2500,
        )

        previous_logs = (
            bool(
                arguments.get(
                    "previous_container",
                    False,
                )
            )
        )

        timestamps_enabled = (
            bool(
                arguments.get(
                    "timestamps",
                    False,
                )
            )
        )

        try:

            if pod_name_arg:

                kw = dict(
                    name=pod_name_arg,
                    namespace=namespace,
                    tail_lines=tail_lines,
                    previous=previous_logs,
                    timestamps=timestamps_enabled,
                )

                if container_name:

                    kw["container"] = container_name

                logs = core_v1.read_namespaced_pod_log(
                    **kw
                )

                return {
                    "tool": "get_logs",
                    "pod": pod_name_arg,
                    "namespace": namespace,
                    "tail_lines": tail_lines,
                    "previous_container": (
                        previous_logs
                    ),
                    "timestamps": (
                        timestamps_enabled
                    ),
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
                previous=previous_logs,
                timestamps=timestamps_enabled,
            )

            if container_name:

                kw["container"] = container_name

            logs = core_v1.read_namespaced_pod_log(
                **kw
            )

            return {
                "tool": "get_logs",
                "pod": pod_name,
                "namespace": namespace,
                "tail_lines": tail_lines,
                "previous_container": (
                    previous_logs
                ),
                "timestamps": (
                    timestamps_enabled
                ),
                "logs": logs
            }

        except ApiException as exc:

            return {
                "error": (
                    f"k8s {exc.status}: {exc.reason} "
                    f"{_truncate_text(exc.body, 400)}"
                ),
            }

    # =====================================================
    # Tool: get_pod_details
    # (describe-equivalent subset: probes, exits, waits)
    # =====================================================

    elif tool == "get_pod_details":

        namespace = (
            arguments.get(
                "namespace",
                "default",
            )
        )

        pod_name_arg = (
            arguments.get(
                "pod_name",
            )
        )

        if not pod_name_arg:

            return {
                "error": "pod_name is required",
            }

        try:

            pod_obj = core_v1.read_namespaced_pod(
                pod_name_arg,
                namespace,
            )

        except ApiException as exc:

            return {
                "error": (
                    f"k8s {exc.status}: {exc.reason} "
                    f"{_truncate_text(exc.body, 400)}"
                ),
            }

        def collect_container_rows(
            status_list,
        ):

            rows = []

            if not status_list:

                return rows

            for cs in status_list:

                row = {
                    "name": cs.name,
                    "restart_count": (
                        cs.restart_count
                    ),
                    "ready": cs.ready,
                }

                if cs.state:

                    if cs.state.waiting:

                        wa = cs.state.waiting

                        row["waiting"] = {
                            "reason": wa.reason,
                            "message": (
                                _truncate_text(
                                    wa.message,
                                    800,
                                )
                            ),
                        }

                    if cs.state.terminated:

                        te = cs.state.terminated

                        row["terminated"] = {
                            "exit_code": (
                                te.exit_code
                            ),
                            "reason": te.reason,
                            "message": (
                                _truncate_text(
                                    te.message,
                                    800,
                                )
                            ),
                        }

                rows.append(row)

            return rows

        condition_rows = []

        for item in pod_obj.status.conditions or []:

            condition_rows.append({
                "type": item.type,
                "status": item.status,
                "reason": item.reason,
                "message": (
                    _truncate_text(
                        item.message,
                        600,
                    )
                ),
            })

        pvc_names = []

        for vol in pod_obj.spec.volumes or []:

            if (
                vol.persistent_volume_claim
                and (
                    vol.persistent_volume_claim.claim_name
                )
            ):

                pvc_names.append(
                    vol.persistent_volume_claim.claim_name,
                )

        owners = []

        for ref in (
            pod_obj.metadata.owner_references
            or []
        ):

            owners.append({
                "kind": ref.kind,
                "name": ref.name,
            })

        probes_out = []

        for ctr in pod_obj.spec.containers or []:

            flags = []

            if ctr.liveness_probe:

                flags.append("liveness_probe")

            if ctr.readiness_probe:

                flags.append("readiness_probe")

            if ctr.startup_probe:

                flags.append("startup_probe")

            probes_out.append({
                "container": ctr.name,
                "probe_kinds": flags,
            })

        return {
            "tool": "get_pod_details",
            "namespace": namespace,
            "pod_name": pod_name_arg,
            "phase": pod_obj.status.phase,
            "qos_class": (
                pod_obj.status.qos_class
            ),
            "pod_ip": pod_obj.status.pod_ip,
            "host_ip": pod_obj.status.host_ip,
            "node_name": (
                pod_obj.spec.node_name
            ),
            "conditions": condition_rows,
            "containers": (
                collect_container_rows(
                    pod_obj.status.container_statuses,
                )
            ),
            "init_containers": (
                collect_container_rows(
                    pod_obj.status.init_container_statuses,
                )
            ),
            "volume_claims": pvc_names,
            "owner_references": owners,
            "probes_defined": probes_out,
        }

    # =====================================================
    # Tool: get_deployment_rollout_status
    # =====================================================

    elif tool == "get_deployment_rollout_status":

        namespace = (
            arguments.get(
                "namespace",
                "default",
            )
        )

        deployment_name = (
            arguments.get(
                "deployment_name",
            )
        )

        if not deployment_name:

            return {
                "error": (
                    "deployment_name is required"
                ),
            }

        try:

            dep = (
                apps_v1.read_namespaced_deployment(
                    deployment_name,
                    namespace,
                )
            )

        except ApiException as exc:

            return {
                "error": (
                    f"k8s {exc.status}: {exc.reason} "
                    f"{_truncate_text(exc.body, 400)}"
                ),
            }

        strat = getattr(
            dep.spec.strategy,
            "type",
            None,
        )

        rev = (
            (
                dep.metadata.annotations
                or {}
            ).get(
                "deployment.kubernetes.io/revision",
            )
        )

        statuses = (
            getattr(
                dep.status,
                "conditions",
                None,
            )
        )

        cond_rows = []

        for row in statuses or []:

            cond_rows.append({
                "type": row.type,
                "status": row.status,
                "reason": row.reason,
                "message": (
                    _truncate_text(
                        row.message,
                        600,
                    )
                ),
            })

        return {
            "tool": "get_deployment_rollout_status",
            "namespace": namespace,
            "deployment_name": deployment_name,
            "replicas_desired": (
                dep.spec.replicas or 0
            ),
            "ready_replicas": (
                getattr(
                    dep.status,
                    "ready_replicas",
                    None,
                )
                or 0
            ),
            "updated_replicas": (
                getattr(
                    dep.status,
                    "updated_replicas",
                    None,
                )
                or 0
            ),
            "available_replicas": (
                getattr(
                    dep.status,
                    "available_replicas",
                    None,
                )
                or 0
            ),
            "unavailable_replicas": (
                getattr(
                    dep.status,
                    "unavailable_replicas",
                    None,
                )
                or 0
            ),
            "observed_generation": (
                getattr(
                    dep.status,
                    "observed_generation",
                    None,
                )
            ),
            "spec_generation": (
                getattr(
                    dep.metadata,
                    "generation",
                    None,
                )
            ),
            "strategy": strat,
            "paused": (
                getattr(
                    dep.spec,
                    "paused",
                    False,
                )
            ),
            "revision_annotation": rev,
            "conditions": cond_rows,
        }

    # =====================================================
    # Tool: get_config_map_data
    # =====================================================

    elif tool == "get_config_map_data":

        namespace = (
            arguments.get(
                "namespace",
                "default",
            )
        )

        cm_name = (
            arguments.get(
                "config_map_name",
            )
            or (
                arguments.get(
                    "name",
                )
            )
        )

        if not cm_name:

            return {
                "error": (
                    "config_map_name (or name) "
                    "is required"
                ),
            }

        key_filter_raw = (
            arguments.get("keys")
        )

        if key_filter_raw is None:

            key_filter = None

        elif isinstance(key_filter_raw, list):

            key_filter = {
                str(k).strip()
                for k in key_filter_raw
                if str(k).strip()
            }

        else:

            key_filter = {
                str(key_filter_raw).strip(),
            }

        CM_MAX_KEYS = 32

        VALUE_CAP_INT = (
            _clamp_int(
                arguments.get(
                    "max_value_chars",
                    14000,
                ),
                default=14000,
                minimum=500,
                maximum=64000,
            )
        )

        try:

            cm_obj = core_v1.read_namespaced_config_map(
                cm_name,
                namespace,
            )

        except ApiException as exc:

            return {
                "error": (
                    f"k8s {exc.status}: {exc.reason} "
                    f"{_truncate_text(exc.body, 400)}"
                ),
            }

        data_map = cm_obj.data or {}

        omitted_due_budget = []

        truncated_value_keys = []

        extracted = {}

        sorted_keys = sorted(data_map.keys())

        for key in sorted_keys:

            if key_filter is not None and (
                key not in key_filter
            ):

                continue

            if len(extracted) >= CM_MAX_KEYS:

                omitted_due_budget.append(key)

                continue

            payload = (
                data_map[key]
                or ""
            )

            display = payload

            if len(display) > VALUE_CAP_INT:

                display = _truncate_text(
                    display,
                    VALUE_CAP_INT,
                )

                truncated_value_keys.append(key)

            extracted[key] = display

        binary_block = getattr(
            cm_obj,
            "binary_data",
            None,
        ) or {}

        binary_summary = []

        if binary_block:

            for bk in sorted(binary_block.keys()):

                if key_filter is not None and bk not in key_filter:

                    continue

                size = (
                    len(
                        binary_block[bk]
                        or b""
                    )
                )

                binary_summary.append(
                    f"{bk}: <binary {size} bytes>"
                )

        return {
            "tool": "get_config_map_data",
            "namespace": namespace,
            "config_map_name": cm_name,
            "keys_returned": list(
                extracted.keys(),
            ),
            "data": extracted,
            "value_was_truncated_for_keys": (
                truncated_value_keys
            ),
            "keys_omitted_due_to_budget": (
                omitted_due_budget
            ),
            "binary_keys_summary": binary_summary,
        }

    # =====================================================
    # Tool: list_deployments
    # =====================================================

    elif tool == "list_deployments":

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

    elif tool == "list_services":

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
                    for p in (svc.spec.ports or [])
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

    elif tool == "list_ingresses":

        services = core_v1.list_service_for_all_namespaces()

        endpoints = (
            core_v1
            .list_endpoints_for_all_namespaces()
        )

        ingresses = (
            networking_v1
            .list_ingress_for_all_namespaces()
        )

        existing_services = {
            (
                svc.metadata.namespace,
                svc.metadata.name,
            )
            for svc in services.items
        }

        endpoint_addresses = {}

        for ep in endpoints.items:

            addresses = []

            if ep.subsets:

                for subset in ep.subsets:

                    if subset.addresses:

                        for addr in subset.addresses:

                            addresses.append(addr.ip)

            endpoint_addresses[
                (
                    ep.metadata.namespace,
                    ep.metadata.name,
                )
            ] = addresses

        results = []

        for ing in ingresses.items:

            hosts = []

            backend_refs = []

            invalid_backends = []

            if getattr(ing.spec, "default_backend", None):

                default_backend = ing.spec.default_backend

                if getattr(default_backend, "service", None):

                    service_name = (
                        default_backend.service.name
                    )

                    service_key = (
                        ing.metadata.namespace,
                        service_name,
                    )

                    addresses = endpoint_addresses.get(
                        service_key,
                        [],
                    )

                    backend_row = {
                        "host": None,
                        "path": None,
                        "path_type": None,
                        "service_name": service_name,
                        "service_port": (
                            getattr(
                                default_backend.service.port,
                                "number",
                                None,
                            )
                            or getattr(
                                default_backend.service.port,
                                "name",
                                None,
                            )
                        ),
                        "service_exists": (
                            service_key in existing_services
                        ),
                        "endpoint_count": len(addresses),
                        "has_endpoints": bool(addresses),
                    }

                    backend_refs.append(backend_row)

                    if not backend_row["service_exists"]:

                        invalid_backends.append({
                            "reason": "service_missing",
                            "service_name": service_name,
                            "host": None,
                            "path": None,
                        })

                    elif not backend_row["has_endpoints"]:

                        invalid_backends.append({
                            "reason": "service_has_no_endpoints",
                            "service_name": service_name,
                            "host": None,
                            "path": None,
                        })

            if ing.spec.rules:

                for rule in ing.spec.rules:

                    hosts.append(rule.host)

                    http_block = getattr(
                        rule,
                        "http",
                        None,
                    )

                    for path_obj in (
                        getattr(http_block, "paths", None)
                        or []
                    ):

                        backend = getattr(
                            path_obj,
                            "backend",
                            None,
                        )

                        service = getattr(
                            backend,
                            "service",
                            None,
                        )

                        if not service:
                            continue

                        service_name = service.name

                        service_key = (
                            ing.metadata.namespace,
                            service_name,
                        )

                        addresses = endpoint_addresses.get(
                            service_key,
                            [],
                        )

                        backend_row = {
                            "host": rule.host,
                            "path": path_obj.path,
                            "path_type": path_obj.path_type,
                            "service_name": service_name,
                            "service_port": (
                                getattr(
                                    service.port,
                                    "number",
                                    None,
                                )
                                or getattr(
                                    service.port,
                                    "name",
                                    None,
                                )
                            ),
                            "service_exists": (
                                service_key in existing_services
                            ),
                            "endpoint_count": len(addresses),
                            "has_endpoints": bool(addresses),
                        }

                        backend_refs.append(backend_row)

                        if not backend_row["service_exists"]:

                            invalid_backends.append({
                                "reason": "service_missing",
                                "service_name": service_name,
                                "host": rule.host,
                                "path": path_obj.path,
                            })

                        elif not backend_row["has_endpoints"]:

                            invalid_backends.append({
                                "reason": "service_has_no_endpoints",
                                "service_name": service_name,
                                "host": rule.host,
                                "path": path_obj.path,
                            })

            results.append({
                "name": ing.metadata.name,
                "namespace": (
                    ing.metadata.namespace
                ),
                "hosts": hosts,
                "backend_services": backend_refs,
                "invalid_backends": invalid_backends,
            })

        return {
            "tool": "list_ingresses",
            "count": len(results),
            "ingresses": results
        }

    # =====================================================
    # Tool: list_namespaces
    # =====================================================

    elif tool == "list_namespaces":

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

    elif tool == "list_nodes":

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

            labels = (
                node.metadata.labels
                or {}
            )

            instance_type_label = (
                labels.get(
                    "node.kubernetes.io/instance-type",
                )
                or labels.get(
                    "beta.kubernetes.io/instance-type",
                )
            )

            results.append({
                "name": node.metadata.name,

                "instance_type": instance_type_label,

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

    elif tool == "list_events":

        namespace = arguments.get(
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

    elif tool == "list_argocd_applications":

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

    elif tool == "query_prometheus":

        query = arguments.get(
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

    elif tool == "prometheus_common_metrics":

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
    # Tool: finops_cluster_signals
    # (cloud-agnostic: node SKUs/zones via labels + Prometheus
    # requests / PVC signals when kube-state-metrics exists)
    # =====================================================

    elif tool == "finops_cluster_signals":

        nodes_resp = core_v1.list_node()
        nodes_items = nodes_resp.items

        sku_mix = Counter()
        zone_mix = Counter()
        provider_hints = []

        for node in nodes_items:

            labels = (
                node.metadata.labels
                or {}
            )

            sku = (
                labels.get(
                    "node.kubernetes.io/instance-type",
                )
                or labels.get(
                    "beta.kubernetes.io/instance-type",
                )
                or "unknown"
            )

            sku_mix[sku] += 1

            zn = (
                labels.get(
                    "topology.kubernetes.io/zone",
                )
                or labels.get(
                    "failure-domain.beta.kubernetes.io/zone",
                )
                or "unknown"
            )

            zone_mix[zn] += 1

            for lk in (
                "eks.amazonaws.com/nodegroup",
                "cloud.google.com/gke-nodepool",
                "kubernetes.azure.com/agentpool",
            ):

                hint = labels.get(lk)

                if hint:

                    provider_hints.append(f"{lk}={hint}")

        fin_queries = [
            (
                "requests_cpu_namespace",
                (
                    "topk(45, sum by (namespace) ("
                    "kube_pod_container_resource_requests{resource=\"cpu\"}))"
                ),
            ),
            (
                "requests_memory_namespace",
                (
                    "topk(45, sum by (namespace) ("
                    "kube_pod_container_resource_requests{resource=\"memory\"}))"
                ),
            ),
            (
                "pvc_storage_requested_namespace",
                (
                    "topk(45, sum by (namespace) ("
                    "kube_persistentvolumeclaim_resource_requests_"
                    "storage_bytes))"
                ),
            ),
            (
                "node_allocatable_cpu_sum",
                'sum(kube_node_status_allocatable{resource="cpu"})',
            ),
            (
                "node_allocatable_memory_sum",
                'sum(kube_node_status_allocatable{resource="memory"})',
            ),
        ]

        prom_rows = []

        for label_key, pq in fin_queries:

            prom_rows.append({
                "name": label_key,
                "query": pq,
                "result": (
                    _prometheus_query_one(
                        pq,
                    )
                ),
            })

        return {
            "tool": "finops_cluster_signals",
            "node_count": len(nodes_items),
            "instance_mix": dict(sku_mix),
            "zone_mix": dict(zone_mix),
            "cloud_hints": sorted(
                list(
                    frozenset(
                        provider_hints,
                    ),
                ),
            ),
            "prometheus": prom_rows,
        }

    # =====================================================
    # Tool: list_stateful_sets
    # =====================================================

    elif tool == "list_stateful_sets":

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

    elif tool == "list_daemon_sets":

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

    elif tool == "list_cron_jobs":

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

    elif tool == "list_jobs":

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
            arguments.get("limit", 120)
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

    elif tool == "list_horizontal_pod_autoscalers":

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

    elif tool == "list_pvcs":

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

    elif tool == "list_pvs":

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

    elif tool == "list_storage_classes":

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

    elif tool == "list_resource_quotas":

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

    elif tool == "list_limit_ranges":

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

    elif tool == "list_endpoints":

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
    # Tool: list_cron_jobs
    # =====================================================
    elif tool == "list_cron_jobs":
        items = batch_v1.list_cron_job_for_all_namespaces().items
        results = []
        for cj in items:
            results.append({
                "name": cj.metadata.name,
                "namespace": cj.metadata.namespace,
                "schedule": cj.spec.schedule,
                "suspend": getattr(cj.spec, 'suspend', False),
                "last_schedule": str(cj.status.last_schedule_time or ""),
                "timezone": getattr(cj.spec, 'timezone', 'UTC'),
            })
        return {
            "tool": "list_cron_jobs",
            "count": len(results),
            "cron_jobs": results,
        }

    # =====================================================
    # Tool: list_jobs
    # =====================================================
    elif tool == "list_jobs":
        items = batch_v1.list_job_for_all_namespaces().items
        sorted_items = sorted(
            items,
            key=lambda j: j.metadata.creation_timestamp or "",
            reverse=True
        )
        limit = _clamp_int(
            arguments.get("limit", 120),
            default=120,
            minimum=1,
            maximum=300,
        )
        trimmed = sorted_items[:limit]
        results = []
        for job in trimmed:
            status = job.status
            results.append({
                "name": job.metadata.name,
                "namespace": job.metadata.namespace,
                "active": status.active or 0,
                "succeeded": status.succeeded or 0,
                "failed": status.failed or 0,
                "creation_time": str(job.metadata.creation_timestamp or ""),
                "completion_time": str(status.completion_time or ""),
            })
        return {
            "tool": "list_jobs",
            "count": len(results),
            "jobs": results,
        }

    # =====================================================
    # Tool: list_horizontal_pod_autoscalers
    # =====================================================
    elif tool == "list_horizontal_pod_autoscalers":
        items = autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces().items
        results = []
        for hpa in items:
            target = hpa.spec.scale_target_ref
            metrics = []
            for metric in (hpa.spec.metrics or []):
                m_type = metric.type or "unknown"
                m_info = {"type": m_type}
                if metric.resource:
                    m_info["target"] = getattr(metric.resource, 'target', {})
                metrics.append(m_info)
            results.append({
                "name": hpa.metadata.name,
                "namespace": hpa.metadata.namespace,
                "target_kind": target.kind,
                "target_name": target.name,
                "min_replicas": hpa.spec.min_replicas or 1,
                "max_replicas": hpa.spec.max_replicas,
                "current_replicas": hpa.status.current_replicas or 0,
                "desired_replicas": hpa.status.desired_replicas or 0,
                "metrics": metrics,
            })
        return {
            "tool": "list_horizontal_pod_autoscalers",
            "count": len(results),
            "hpas": results,
        }

    # =====================================================
    # Tool: trace_pod_dependencies
    # =====================================================
    elif tool == "trace_pod_dependencies":
        namespace = arguments.get("namespace", "default")
        pod_name = arguments.get("pod_name")
        app_label = arguments.get("app_label")
        
        try:
            if pod_name:
                pods = [core_v1.read_namespaced_pod(pod_name, namespace)]
            elif app_label:
                selector = f"app={app_label}"
                pods = core_v1.list_namespaced_pod(namespace, label_selector=selector).items
            else:
                pods = core_v1.list_namespaced_pod(namespace).items
            
            dependencies = []
            for pod in pods:
                pod_deps = {
                    "pod_name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "outbound_services": [],
                    "environment_refs": [],
                }
                
                for container in pod.spec.containers or []:
                    for env in container.env or []:
                        if env.value_from and env.value_from.config_map_key_ref:
                            pod_deps["environment_refs"].append({
                                "name": env.name,
                                "source": "ConfigMap",
                                "source_name": env.value_from.config_map_key_ref.name,
                            })
                        elif env.value_from and env.value_from.secret_key_ref:
                            pod_deps["environment_refs"].append({
                                "name": env.name,
                                "source": "Secret",
                                "source_name": env.value_from.secret_key_ref.name,
                            })
                
                services = core_v1.list_namespaced_service(namespace).items
                for svc in services:
                    for port in svc.spec.ports or []:
                        pod_deps["outbound_services"].append({
                            "service": svc.metadata.name,
                            "port": port.port,
                            "target_port": port.target_port,
                        })
                
                dependencies.append(pod_deps)
            
            return {
                "tool": "trace_pod_dependencies",
                "namespace": namespace,
                "dependencies": dependencies,
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
                "details": _truncate_text(exc.body, 400),
            }

    # =====================================================
    # Tool: analyze_crash_loop
    # =====================================================
    elif tool == "analyze_crash_loop":
        namespace = arguments.get("namespace")
        pod_name = arguments.get("pod_name")
        
        if not namespace or not pod_name:
            return {"error": "namespace and pod_name are required"}
        
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
            events_list = core_v1.list_namespaced_event(namespace)
            
            analysis = {
                "pod_name": pod_name,
                "namespace": namespace,
                "current_phase": pod.status.phase,
                "containers": [],
                "recent_events": [],
            }
            
            for container in pod.status.container_statuses or []:
                container_info = {
                    "name": container.name,
                    "ready": container.ready,
                    "restart_count": container.restart_count,
                }
                
                if container.state.waiting:
                    container_info["waiting_reason"] = container.state.waiting.reason
                    container_info["waiting_message"] = _truncate_text(
                        container.state.waiting.message or "", 600
                    )
                
                if container.state.terminated:
                    container_info["exit_code"] = container.state.terminated.exit_code
                    container_info["termination_reason"] = container.state.terminated.reason
                    container_info["termination_message"] = _truncate_text(
                        container.state.terminated.message or "", 600
                    )
                
                analysis["containers"].append(container_info)
            
            for event in events_list.items:
                if event.involved_object.name == pod_name and event.type != "Normal":
                    analysis["recent_events"].append({
                        "reason": event.reason,
                        "message": _truncate_text(event.message or "", 400),
                        "timestamp": str(event.last_timestamp or event.event_time or ""),
                    })
            
            return {
                "tool": "analyze_crash_loop",
                "analysis": analysis,
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
                "details": _truncate_text(exc.body, 400),
            }

    # =====================================================
    # Tool: event_history
    # =====================================================
    elif tool == "event_history":
        namespace = arguments.get("namespace")
        hours_back = arguments.get("hours_back", 24)
        severity = arguments.get("severity")
        
        try:
            if namespace:
                events = core_v1.list_namespaced_event(namespace).items
            else:
                events = core_v1.list_event_for_all_namespaces().items
            
            filtered_events = []
            for event in events:
                if severity and event.type not in (severity, "Warning", "Error"):
                    continue
                filtered_events.append({
                    "namespace": event.metadata.namespace,
                    "type": event.type,
                    "reason": event.reason,
                    "message": _truncate_text(event.message or "", 300),
                    "involved_object": event.involved_object.kind,
                    "object_name": event.involved_object.name,
                    "count": event.count or 1,
                    "timestamp": str(event.last_timestamp or event.event_time or ""),
                })
            
            reason_counts = Counter()
            for evt in filtered_events:
                reason_counts[evt["reason"]] += 1
            
            return {
                "tool": "event_history",
                "total_events": len(filtered_events),
                "events": filtered_events[:100],
                "reason_summary": dict(reason_counts.most_common(20)),
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: cost_breakdown_by_namespace
    # =====================================================
    elif tool == "cost_breakdown_by_namespace":
        try:
            namespaces = core_v1.list_namespace().items
            breakdown = []
            
            for ns in namespaces:
                ns_name = ns.metadata.name
                pods = core_v1.list_namespaced_pod(ns_name).items
                
                cpu_requests = 0.0
                memory_requests = 0.0
                pod_count = 0
                
                for pod in pods:
                    for container in pod.spec.containers or []:
                        if container.resources and container.resources.requests:
                            cpu_str = container.resources.requests.get("cpu", "0")
                            mem_str = container.resources.requests.get("memory", "0")
                            
                            try:
                                cpu_val = float(str(cpu_str).replace("m", "")) / 1000.0 if "m" in str(cpu_str) else float(cpu_str)
                                memory_val = float(str(mem_str).replace("Mi", "").replace("Gi", "")) 
                                cpu_requests += cpu_val
                                memory_requests += memory_val
                            except:
                                pass
                        pod_count += 1
                
                breakdown.append({
                    "namespace": ns_name,
                    "pod_count": pod_count,
                    "cpu_requests_cores": round(cpu_requests, 2),
                    "memory_requests_gb": round(memory_requests / 1024, 2),
                    "estimated_daily_cost": round((cpu_requests * 0.05 + memory_requests / 1024 * 0.01) * 24, 2),
                })
            
            return {
                "tool": "cost_breakdown_by_namespace",
                "breakdown": sorted(breakdown, key=lambda x: x["estimated_daily_cost"], reverse=True),
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: resource_efficiency_analysis
    # =====================================================
    elif tool == "resource_efficiency_analysis":
        namespace = arguments.get("namespace")
        threshold = arguments.get("threshold_percent", 20)
        
        try:
            if namespace:
                deployments = apps_v1.list_namespaced_deployment(namespace).items
            else:
                deployments = apps_v1.list_deployment_for_all_namespaces().items
            
            inefficient = []
            
            for dep in deployments:
                for container in dep.spec.template.spec.containers or []:
                    if container.resources and container.resources.requests:
                        requests = container.resources.requests
                        cpu_req = str(requests.get("cpu", "0"))
                        
                        if int(dep.spec.replicas or 1) < 2:
                            inefficient.append({
                                "type": "deployment",
                                "name": dep.metadata.name,
                                "namespace": dep.metadata.namespace,
                                "issue": f"Single replica: {dep.spec.replicas or 1} - consider HPA or multi-replica setup",
                                "severity": "medium",
                            })
            
            return {
                "tool": "resource_efficiency_analysis",
                "inefficient_workloads": inefficient,
                "optimization_count": len(inefficient),
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: analyze_rbac
    # =====================================================
    elif tool == "analyze_rbac":
        namespace = arguments.get("namespace")
        
        try:
            rbac_summary = {
                "cluster_roles": 0,
                "cluster_role_bindings": 0,
                "roles": 0,
                "role_bindings": 0,
                "service_accounts": 0,
                "overpermissive_found": False,
            }
            
            try:
                crs = custom_api.list_cluster_custom_object(
                    group="rbac.authorization.k8s.io",
                    version="v1",
                    plural="clusterroles"
                )
                rbac_summary["cluster_roles"] = len(crs.get("items", []))
            except:
                pass
            
            try:
                crbs = custom_api.list_cluster_custom_object(
                    group="rbac.authorization.k8s.io",
                    version="v1",
                    plural="clusterrolebindings"
                )
                rbac_summary["cluster_role_bindings"] = len(crbs.get("items", []))
            except:
                pass
            
            sas = core_v1.list_service_account_for_all_namespaces().items
            rbac_summary["service_accounts"] = len(sas)
            
            return {
                "tool": "analyze_rbac",
                "rbac_summary": rbac_summary,
                "audit_recommendation": "Use least-privilege RBAC with explicit allow rules, avoid wildcards",
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: check_network_policies
    # =====================================================
    elif tool == "check_network_policies":
        namespace = arguments.get("namespace")
        
        try:
            if namespace:
                nps = networking_v1.list_namespaced_network_policy(namespace).items
            else:
                nps = networking_v1.list_network_policy_for_all_namespaces().items
            
            policy_summary = {
                "total_policies": len(nps),
                "namespaces_with_policies": set(),
                "pods_likely_unprotected": 0,
            }
            
            for np in nps:
                policy_summary["namespaces_with_policies"].add(np.metadata.namespace)
            
            if namespace:
                pods = core_v1.list_namespaced_pod(namespace).items
                policy_ns = set(n.metadata.namespace for np in nps for n in [np])
                if namespace not in policy_ns:
                    policy_summary["pods_likely_unprotected"] = len(pods)
            
            return {
                "tool": "check_network_policies",
                "summary": {
                    "total_policies": policy_summary["total_policies"],
                    "namespaces_protected": len(policy_summary["namespaces_with_policies"]),
                    "recommendation": "Enable NetworkPolicy admission controller and define default-deny egress/ingress",
                },
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: analyze_pod_security
    # =====================================================
    elif tool == "analyze_pod_security":
        namespace = arguments.get("namespace")
        
        try:
            if namespace:
                pods = core_v1.list_namespaced_pod(namespace).items
            else:
                pods = core_v1.list_pod_for_all_namespaces().items
            
            security_issues = []
            
            for pod in pods:
                for container in pod.spec.containers or []:
                    if container.security_context:
                        sc = container.security_context
                        if sc.run_as_user == 0:
                            security_issues.append({
                                "pod": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "issue": "Running as root (UID 0)",
                                "severity": "high",
                            })
                        if sc.privileged:
                            security_issues.append({
                                "pod": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "issue": "Running in privileged mode",
                                "severity": "high",
                            })
                        if sc.read_only_root_filesystem is False:
                            security_issues.append({
                                "pod": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "issue": "Writable root filesystem",
                                "severity": "medium",
                            })
            
            return {
                "tool": "analyze_pod_security",
                "security_issues_found": len(security_issues),
                "issues": security_issues[:50],
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: list_secrets_audit
    # =====================================================
    elif tool == "list_secrets_audit":
        namespace = arguments.get("namespace")
        
        try:
            if namespace:
                secrets = core_v1.list_namespaced_secret(namespace).items
            else:
                secrets = core_v1.list_secret_for_all_namespaces().items
            
            audit_info = []
            for secret in secrets:
                audit_info.append({
                    "name": secret.metadata.name,
                    "namespace": secret.metadata.namespace,
                    "type": secret.type,
                    "key_count": len(secret.data or {}),
                    "age_days": (
                        (datetime.datetime.now() - secret.metadata.creation_timestamp.replace(tzinfo=None)).days
                        if secret.metadata.creation_timestamp else "unknown"
                    ),
                })
            
            return {
                "tool": "list_secrets_audit",
                "total_secrets": len(audit_info),
                "secrets": audit_info,
                "note": "Secret values are NOT returned; this is read-only audit only",
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: analyze_image_security
    # =====================================================
    elif tool == "analyze_image_security":
        namespace = arguments.get("namespace")
        
        try:
            if namespace:
                pods = core_v1.list_namespaced_pod(namespace).items
            else:
                pods = core_v1.list_pod_for_all_namespaces().items
            
            image_issues = []
            
            for pod in pods:
                for container in pod.spec.containers or []:
                    image = container.image or ""
                    
                    if ":latest" in image or ":" not in image:
                        image_issues.append({
                            "pod": pod.metadata.name,
                            "namespace": pod.metadata.namespace,
                            "image": image,
                            "issue": "Using :latest or untagged image",
                            "severity": "high",
                        })
                    
                    pull_policy = container.image_pull_policy
                    if pull_policy != "IfNotPresent":
                        image_issues.append({
                            "pod": pod.metadata.name,
                            "namespace": pod.metadata.namespace,
                            "image": image,
                            "issue": f"Pull policy is {pull_policy} (should be IfNotPresent)",
                            "severity": "medium",
                        })
            
            return {
                "tool": "analyze_image_security",
                "image_issues_found": len(image_issues),
                "issues": image_issues[:50],
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: identify_resource_bottlenecks
    # =====================================================
    elif tool == "identify_resource_bottlenecks":
        namespace = arguments.get("namespace")
        
        try:
            if namespace:
                pods = core_v1.list_namespaced_pod(namespace).items
            else:
                pods = core_v1.list_pod_for_all_namespaces().items
            
            bottlenecks = []
            
            for pod in pods:
                for container in pod.spec.containers or []:
                    if container.resources and container.resources.limits:
                        limits = container.resources.limits
                        cpu_limit = limits.get("cpu")
                        mem_limit = limits.get("memory")
                        
                        if cpu_limit or mem_limit:
                            bottlenecks.append({
                                "pod": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "container": container.name,
                                "cpu_limit": cpu_limit,
                                "memory_limit": mem_limit,
                                "status": "resource_constrained",
                            })
            
            return {
                "tool": "identify_resource_bottlenecks",
                "bottlenecks_found": len(bottlenecks),
                "constrained_resources": bottlenecks[:50],
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: analyze_argocd_sync_status
    # =====================================================
    elif tool == "analyze_argocd_sync_status":
        try:
            apps = custom_api.list_cluster_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                plural="applications"
            )
            
            sync_summary = {
                "total_apps": len(apps.get("items", [])),
                "synced": 0,
                "out_of_sync": 0,
                "error": 0,
            }
            
            for app in apps.get("items", []):
                status = app.get("status", {})
                sync_status = status.get("sync", {}).get("status", "Unknown")
                
                if sync_status == "Synced":
                    sync_summary["synced"] += 1
                elif sync_status == "OutOfSync":
                    sync_summary["out_of_sync"] += 1
                else:
                    sync_summary["error"] += 1
            
            return {
                "tool": "analyze_argocd_sync_status",
                "summary": sync_summary,
            }
        except:
            return {
                "tool": "analyze_argocd_sync_status",
                "status": "ArgoCD not available in cluster",
            }

    # =====================================================
    # Tool: get_deployment_history
    # =====================================================
    elif tool == "get_deployment_history":
        namespace = arguments.get("namespace")
        deployment_name = arguments.get("deployment_name")
        limit = arguments.get("limit", 10)
        
        if not namespace or not deployment_name:
            return {"error": "namespace and deployment_name are required"}
        
        try:
            dep = apps_v1.read_namespaced_deployment(deployment_name, namespace)
            rs_list = apps_v1.list_namespaced_replica_set(namespace).items
            
            related_rs = [
                rs for rs in rs_list
                if any(
                    ref.name == deployment_name and ref.kind == "Deployment"
                    for ref in rs.metadata.owner_references or []
                )
            ]
            
            history = []
            for rs in related_rs[:limit]:
                history.append({
                    "revision": rs.metadata.annotations.get("deployment.kubernetes.io/revision", "unknown"),
                    "name": rs.metadata.name,
                    "replicas": rs.spec.replicas or 0,
                    "ready_replicas": rs.status.ready_replicas or 0,
                    "creation_time": str(rs.metadata.creation_timestamp or ""),
                })
            
            return {
                "tool": "get_deployment_history",
                "deployment": deployment_name,
                "namespace": namespace,
                "history": history,
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: cluster_health_summary
    # =====================================================
    elif tool == "cluster_health_summary":
        try:
            nodes = core_v1.list_node().items
            ready_nodes = sum(1 for n in nodes if any(
                c.type == "Ready" and c.status == "True"
                for c in n.status.conditions or []
            ))
            
            pods = core_v1.list_pod_for_all_namespaces().items
            running_pods = sum(1 for p in pods if p.status.phase == "Running")
            failed_pods = sum(1 for p in pods if p.status.phase == "Failed")
            
            return {
                "tool": "cluster_health_summary",
                "nodes": {
                    "total": len(nodes),
                    "ready": ready_nodes,
                },
                "pods": {
                    "total": len(pods),
                    "running": running_pods,
                    "failed": failed_pods,
                },
                "health_status": "healthy" if ready_nodes == len(nodes) and failed_pods == 0 else "degraded",
            }
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
            }

    # =====================================================
    # Tool: map_cluster_topology
    # =====================================================

    elif tool == "map_cluster_topology":

        namespace = arguments.get("namespace")

        try:
            topology = _build_service_topology(namespace)
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
                "details": _truncate_text(exc.body, 400),
            }

        namespace_rows = {}

        for service in topology["services"]:
            ns = service.metadata.namespace
            selector = service.spec.selector or {}
            matching_pods = []

            for pod in topology["pod_index"].get(ns, []):
                if _labels_match_selector(
                    pod.metadata.labels,
                    selector,
                ):
                    matching_pods.append({
                        "name": pod.metadata.name,
                        "phase": pod.status.phase,
                    })

            workloads = []
            for workload in topology["workload_index"].get(ns, []):
                if selector and selector == workload["selector"]:
                    workloads.append({
                        "kind": workload["kind"],
                        "name": workload["name"],
                    })

            endpoint_state = topology["endpoint_index"].get(
                (ns, service.metadata.name),
                {
                    "ready_addresses": [],
                    "not_ready_addresses": [],
                },
            )

            ns_row = namespace_rows.setdefault(ns, {
                "namespace": ns,
                "services": [],
                "ingresses": [],
                "workloads": [],
            })

            ns_row["services"].append({
                "name": service.metadata.name,
                "type": service.spec.type,
                "selector": selector,
                "ports": [
                    {
                        "port": port.port,
                        "target_port": port.target_port,
                    }
                    for port in (service.spec.ports or [])
                ],
                "matching_pods": matching_pods[:20],
                "matching_pod_count": len(matching_pods),
                "backing_workloads": workloads,
                "ready_endpoint_count": len(
                    endpoint_state["ready_addresses"]
                ),
                "not_ready_endpoint_count": len(
                    endpoint_state["not_ready_addresses"]
                ),
            })

        for ingress in topology["ingresses"]:
            ns = ingress.metadata.namespace
            ns_row = namespace_rows.setdefault(ns, {
                "namespace": ns,
                "services": [],
                "ingresses": [],
                "workloads": [],
            })

            routes = []

            if getattr(ingress.spec, "default_backend", None):
                service = getattr(
                    ingress.spec.default_backend,
                    "service",
                    None,
                )
                if service:
                    routes.append({
                        "host": None,
                        "path": None,
                        "service_name": service.name,
                        "service_port": _service_port_value(service.port),
                    })

            for rule in ingress.spec.rules or []:
                for path_obj in (
                    getattr(rule.http, "paths", None)
                    or []
                ):
                    service = getattr(path_obj.backend, "service", None)
                    if service:
                        routes.append({
                            "host": rule.host,
                            "path": path_obj.path,
                            "service_name": service.name,
                            "service_port": _service_port_value(service.port),
                        })

            ns_row["ingresses"].append({
                "name": ingress.metadata.name,
                "routes": routes,
            })

        for ns, workloads in topology["workload_index"].items():
            ns_row = namespace_rows.setdefault(ns, {
                "namespace": ns,
                "services": [],
                "ingresses": [],
                "workloads": [],
            })
            ns_row["workloads"] = workloads

        return {
            "tool": "map_cluster_topology",
            "namespace_count": len(namespace_rows),
            "namespaces": sorted(
                namespace_rows.values(),
                key=lambda row: row["namespace"],
            ),
        }

    # =====================================================
    # Tool: diagnose_service_routing
    # =====================================================

    elif tool == "diagnose_service_routing":

        namespace = arguments.get("namespace")
        service_name_filter = arguments.get("service_name")
        ingress_name_filter = arguments.get("ingress_name")

        try:
            topology = _build_service_topology(namespace)
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
                "details": _truncate_text(exc.body, 400),
            }

        service_keys = {
            (
                service.metadata.namespace,
                service.metadata.name,
            )
            for service in topology["services"]
        }

        issues = []

        for service in topology["services"]:
            ns = service.metadata.namespace
            selector = service.spec.selector or {}

            if service_name_filter and service.metadata.name != service_name_filter:
                continue

            if not selector:
                issues.append({
                    "kind": "Service",
                    "namespace": ns,
                    "name": service.metadata.name,
                    "severity": "warning",
                    "reason": "selector_missing",
                    "detail": "Service has no selector; verify it is managed by manual Endpoints or EndpointSlice objects.",
                })
                continue

            matching_pods = [
                pod for pod in topology["pod_index"].get(ns, [])
                if _labels_match_selector(
                    pod.metadata.labels,
                    selector,
                )
            ]

            endpoint_state = topology["endpoint_index"].get(
                (ns, service.metadata.name),
                {
                    "ready_addresses": [],
                    "not_ready_addresses": [],
                },
            )

            if not matching_pods:
                issues.append({
                    "kind": "Service",
                    "namespace": ns,
                    "name": service.metadata.name,
                    "severity": "critical",
                    "reason": "selector_matches_no_pods",
                    "detail": f"Selector {selector} does not match any current Pods.",
                })
            elif not endpoint_state["ready_addresses"]:
                issues.append({
                    "kind": "Service",
                    "namespace": ns,
                    "name": service.metadata.name,
                    "severity": "critical",
                    "reason": "no_ready_endpoints",
                    "detail": f"Service matches {len(matching_pods)} Pods but has 0 ready endpoints.",
                })

        for ingress in topology["ingresses"]:
            ns = ingress.metadata.namespace

            if ingress_name_filter and ingress.metadata.name != ingress_name_filter:
                continue

            def _check_route(service_name, host, path):
                if service_name_filter and service_name != service_name_filter:
                    return
                service_key = (ns, service_name)
                endpoint_state = topology["endpoint_index"].get(
                    service_key,
                    {
                        "ready_addresses": [],
                        "not_ready_addresses": [],
                    },
                )
                if service_key not in service_keys:
                    issues.append({
                        "kind": "Ingress",
                        "namespace": ns,
                        "name": ingress.metadata.name,
                        "severity": "critical",
                        "reason": "backend_service_missing",
                        "detail": f"Route host={host or '*'} path={path or '<default>'} points to missing Service {service_name}.",
                    })
                elif not endpoint_state["ready_addresses"]:
                    issues.append({
                        "kind": "Ingress",
                        "namespace": ns,
                        "name": ingress.metadata.name,
                        "severity": "critical",
                        "reason": "backend_service_has_no_ready_endpoints",
                        "detail": f"Route host={host or '*'} path={path or '<default>'} points to Service {service_name} with 0 ready endpoints.",
                    })

            if getattr(ingress.spec, "default_backend", None):
                service = getattr(
                    ingress.spec.default_backend,
                    "service",
                    None,
                )
                if service:
                    _check_route(service.name, None, None)

            for rule in ingress.spec.rules or []:
                for path_obj in (
                    getattr(rule.http, "paths", None)
                    or []
                ):
                    service = getattr(path_obj.backend, "service", None)
                    if service:
                        _check_route(
                            service.name,
                            rule.host,
                            path_obj.path,
                        )

        return {
            "tool": "diagnose_service_routing",
            "issue_count": len(issues),
            "issues": issues,
        }

    # =====================================================
    # Tool: cost_anomaly_detection
    # =====================================================

    elif tool == "cost_anomaly_detection":

        percentile = _clamp_int(
            arguments.get("percentile_threshold", 80),
            default=80,
            minimum=50,
            maximum=99,
        )

        metrics_requested = arguments.get("metric") or "all"

        pods = core_v1.list_pod_for_all_namespaces().items
        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces().items

        cpu_rows = []
        memory_rows = []
        storage_rows = []

        for pod in pods:
            for container in pod.spec.containers or []:
                requests = container.resources.requests or {}
                cpu_value = _parse_cpu_to_cores(requests.get("cpu"))
                memory_value = _parse_bytes(requests.get("memory"))
                cpu_rows.append({
                    "namespace": pod.metadata.namespace,
                    "pod": pod.metadata.name,
                    "container": container.name,
                    "value": cpu_value,
                })
                memory_rows.append({
                    "namespace": pod.metadata.namespace,
                    "pod": pod.metadata.name,
                    "container": container.name,
                    "value": memory_value,
                })

        for pvc in pvcs:
            requested = (
                (pvc.spec.resources.requests or {}).get("storage")
            )
            storage_rows.append({
                "namespace": pvc.metadata.namespace,
                "pvc": pvc.metadata.name,
                "value": _parse_bytes(requested),
            })

        findings = []

        def add_findings(metric_name, rows, formatter):
            threshold = _percentile_threshold(
                [row["value"] for row in rows if row["value"] > 0],
                percentile,
            )
            if threshold <= 0:
                return
            for row in rows:
                if row["value"] >= threshold and row["value"] > 0:
                    findings.append(formatter(row, threshold))

        if metrics_requested in ("all", "cpu_requests"):
            add_findings(
                "cpu_requests",
                cpu_rows,
                lambda row, threshold: {
                    "metric": "cpu_requests",
                    "severity": "high" if row["value"] >= threshold * 1.5 else "medium",
                    "namespace": row["namespace"],
                    "object": f"{row['pod']}:{row['container']}",
                    "value": round(row["value"], 3),
                    "threshold": round(threshold, 3),
                    "detail": "CPU request is above the configured percentile threshold.",
                },
            )

        if metrics_requested in ("all", "memory_requests"):
            add_findings(
                "memory_requests",
                memory_rows,
                lambda row, threshold: {
                    "metric": "memory_requests",
                    "severity": "high" if row["value"] >= threshold * 1.5 else "medium",
                    "namespace": row["namespace"],
                    "object": f"{row['pod']}:{row['container']}",
                    "value_bytes": int(row["value"]),
                    "threshold_bytes": int(threshold),
                    "detail": "Memory request is above the configured percentile threshold.",
                },
            )

        if metrics_requested in ("all", "storage_size"):
            add_findings(
                "storage_size",
                storage_rows,
                lambda row, threshold: {
                    "metric": "storage_size",
                    "severity": "high" if row["value"] >= threshold * 1.5 else "medium",
                    "namespace": row["namespace"],
                    "object": row["pvc"],
                    "value_bytes": int(row["value"]),
                    "threshold_bytes": int(threshold),
                    "detail": "PVC requested storage is above the configured percentile threshold.",
                },
            )

        findings.sort(
            key=lambda row: (
                row.get("severity") == "high",
                row.get("value", row.get("value_bytes", 0)),
            ),
            reverse=True,
        )

        return {
            "tool": "cost_anomaly_detection",
            "percentile_threshold": percentile,
            "finding_count": len(findings),
            "findings": findings[:50],
        }

    # =====================================================
    # Tool: analyze_pod_performance
    # =====================================================

    elif tool == "analyze_pod_performance":

        namespace = arguments.get("namespace")
        pod_name = arguments.get("pod_name")

        if not namespace or not pod_name:
            return {"error": "namespace and pod_name are required"}

        prom_queries = {
            "cpu_5m_cores": (
                f"sum(rate(container_cpu_usage_seconds_total{{namespace=\"{namespace}\",pod=\"{pod_name}\",container!=\"\",container!=\"POD\"}}[5m]))"
            ),
            "memory_working_set_bytes": (
                f"sum(container_memory_working_set_bytes{{namespace=\"{namespace}\",pod=\"{pod_name}\",container!=\"\",container!=\"POD\"}})"
            ),
            "network_receive_bytes_5m": (
                f"sum(rate(container_network_receive_bytes_total{{namespace=\"{namespace}\",pod=\"{pod_name}\"}}[5m]))"
            ),
            "network_transmit_bytes_5m": (
                f"sum(rate(container_network_transmit_bytes_total{{namespace=\"{namespace}\",pod=\"{pod_name}\"}}[5m]))"
            ),
            "restart_count": (
                f"sum(kube_pod_container_status_restarts_total{{namespace=\"{namespace}\",pod=\"{pod_name}\"}})"
            ),
        }

        metrics = []
        for label, query in prom_queries.items():
            metrics.append({
                "name": label,
                "query": query,
                "result": _prometheus_query_one(query),
            })

        return {
            "tool": "analyze_pod_performance",
            "namespace": namespace,
            "pod_name": pod_name,
            "metrics": metrics,
        }

    # =====================================================
    # Tool: find_slow_queries
    # =====================================================

    elif tool == "find_slow_queries":

        percentile = _clamp_int(
            arguments.get("percentile", 95),
            default=95,
            minimum=50,
            maximum=99,
        )

        label_filters = arguments.get("search_labels") or {}
        matcher = ""
        for key, value in label_filters.items():
            matcher += f', {key}=\"{value}\"'

        prom_query = (
            f"topk(20, histogram_quantile(0.{percentile}, "
            f"sum by (le, namespace, service, route) ("
            f"rate({{__name__=~\"http_request_duration_seconds_bucket|http_server_request_duration_seconds_bucket|request_duration_seconds_bucket\"{matcher}}}[5m]))))"
        )

        return {
            "tool": "find_slow_queries",
            "percentile": percentile,
            "query": prom_query,
            "result": _prometheus_query_one(prom_query),
        }

    # =====================================================
    # Tool: check_pod_disruption_budgets
    # =====================================================

    elif tool == "check_pod_disruption_budgets":

        namespace = arguments.get("namespace")
        try:
            pdb_resp = custom_api.list_cluster_custom_object(
                group="policy",
                version="v1",
                plural="poddisruptionbudgets",
            )
            pdb_items = [
                item for item in pdb_resp.get("items", [])
                if not namespace or item.get("metadata", {}).get("namespace") == namespace
            ]
            deployments = (
                apps_v1.list_namespaced_deployment(namespace).items
                if namespace else apps_v1.list_deployment_for_all_namespaces().items
            )
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
                "details": _truncate_text(exc.body, 400),
            }

        uncovered = []

        for deployment in deployments:
            pod_labels = deployment.spec.template.metadata.labels or {}
            covered = False
            for pdb in pdb_items:
                selector = (
                    pdb.get("spec", {})
                    .get("selector", {})
                    .get("matchLabels", {})
                )
                if selector and _labels_match_selector(pod_labels, selector):
                    covered = True
                    break
            if not covered:
                uncovered.append({
                    "namespace": deployment.metadata.namespace,
                    "deployment": deployment.metadata.name,
                })

        return {
            "tool": "check_pod_disruption_budgets",
            "pdb_count": len(pdb_items),
            "deployments_without_pdb": uncovered,
        }

    # =====================================================
    # Tool: check_resource_quotas_compliance
    # =====================================================

    elif tool == "check_resource_quotas_compliance":

        namespace = arguments.get("namespace")
        namespaces = (
            [core_v1.read_namespace(namespace)]
            if namespace else core_v1.list_namespace().items
        )
        quota_items = core_v1.list_resource_quota_for_all_namespaces().items
        limit_items = core_v1.list_limit_range_for_all_namespaces().items

        quota_namespaces = {item.metadata.namespace for item in quota_items}
        limit_namespaces = {item.metadata.namespace for item in limit_items}

        rows = []
        for ns in namespaces:
            rows.append({
                "namespace": ns.metadata.name,
                "has_resource_quota": ns.metadata.name in quota_namespaces,
                "has_limit_range": ns.metadata.name in limit_namespaces,
            })

        return {
            "tool": "check_resource_quotas_compliance",
            "namespaces": rows,
            "missing_resource_quota": [
                row["namespace"] for row in rows if not row["has_resource_quota"]
            ],
            "missing_limit_range": [
                row["namespace"] for row in rows if not row["has_limit_range"]
            ],
        }

    # =====================================================
    # Tool: audit_cluster_policies
    # =====================================================

    elif tool == "audit_cluster_policies":

        try:
            pods = core_v1.list_pod_for_all_namespaces().items
            namespaces = core_v1.list_namespace().items
            network_policies = networking_v1.list_network_policy_for_all_namespaces().items
            pdb_resp = custom_api.list_cluster_custom_object(
                group="policy",
                version="v1",
                plural="poddisruptionbudgets",
            )
            cluster_roles = custom_api.list_cluster_custom_object(
                group="rbac.authorization.k8s.io",
                version="v1",
                plural="clusterroles",
            )
        except ApiException as exc:
            return {
                "error": f"k8s {exc.status}: {exc.reason}",
                "details": _truncate_text(exc.body, 400),
            }

        risky_pods = 0
        for pod in pods:
            for container in pod.spec.containers or []:
                sc = container.security_context
                if not sc:
                    continue
                if sc.privileged or sc.run_as_user == 0 or sc.read_only_root_filesystem is False:
                    risky_pods += 1
                    break

        np_namespaces = {item.metadata.namespace for item in network_policies}
        namespaces_without_np = [
            ns.metadata.name for ns in namespaces if ns.metadata.name not in np_namespaces
        ]

        overpermissive_roles = []
        for role in cluster_roles.get("items", []):
            for rule in role.get("rules", []):
                if "*" in rule.get("verbs", []) or "*" in rule.get("resources", []):
                    overpermissive_roles.append(role.get("metadata", {}).get("name"))
                    break

        return {
            "tool": "audit_cluster_policies",
            "summary": {
                "risky_pod_count": risky_pods,
                "namespaces_without_network_policy": namespaces_without_np,
                "pod_disruption_budget_count": len(pdb_resp.get("items", [])),
                "overpermissive_cluster_roles": sorted(overpermissive_roles),
            },
        }

    return {
        "error": (
            f"Unknown tool: "
            f"{tool}"
        )
    }

