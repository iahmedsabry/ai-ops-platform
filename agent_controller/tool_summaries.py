"""Digest sandbox tool JSON into short lines for the analysis prompt."""

from agent_controller.text_utils import safe_join


def build_executive_summary(tool_results):
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
    return summary
