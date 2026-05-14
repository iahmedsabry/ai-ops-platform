"""Kubernetes clients, Prometheus URL, and small helpers for tool handlers."""

from __future__ import annotations

import os

import requests
from kubernetes import config
from kubernetes.client import (
    AppsV1Api,
    AutoscalingV2Api,
    BatchV1Api,
    CoreV1Api,
    CustomObjectsApi,
    NetworkingV1Api,
    StorageV1Api,
)

config.load_incluster_config()

core_v1 = CoreV1Api()
apps_v1 = AppsV1Api()
networking_v1 = NetworkingV1Api()
storage_v1 = StorageV1Api()
batch_v1 = BatchV1Api()
autoscaling_v2 = AutoscalingV2Api()
custom_api = CustomObjectsApi()

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus.monitoring.svc.cluster.local:9090",
)

COMMON_PROM_QUERIES = [
    ("up_scrapes_sample", "up"),
    (
        "container_cpu_namespace_5m",
        "topk(40, sum by (namespace) ("
        "rate(container_cpu_usage_seconds_total{container!=\"\",container!=\"POD\"}[5m])))",
    ),
    (
        "container_mem_working_set_namespace",
        "topk(40, sum by (namespace) ("
        "container_memory_working_set_bytes{container!=\"\",container!=\"POD\"})))",
    ),
    (
        "kube_pod_status_phase",
        'sum by (namespace, phase) (kube_pod_status_phase{phase=~"Pending|Unknown|Failed"} == 1)',
    ),
    (
        "kube_requests_cpu_namespace",
        "topk(45, sum by (namespace) ("
        "kube_pod_container_resource_requests{resource=\"cpu\"}))",
    ),
    (
        "kube_requests_memory_namespace",
        "topk(45, sum by (namespace) ("
        "kube_pod_container_resource_requests{resource=\"memory\"}))",
    ),
    (
        "pvc_storage_requests_namespace",
        "topk(45, sum by (namespace) ("
        "kube_persistentvolumeclaim_resource_requests_storage_bytes))",
    ),
    (
        "pods_running_namespace",
        "topk(50, sum by (namespace) "
        '(kube_pod_status_phase{phase="Running"} == 1))',
    ),
]


def _prometheus_query_one(query: str) -> dict:
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=12,
        )
        if response.status_code != 200:
            return {
                "ok": False,
                "status_code": response.status_code,
                "snippet": response.text[:500],
            }
        try:
            return {"ok": True, "body": response.json()}
        except Exception:
            return {
                "ok": False,
                "error": "invalid_json",
                "snippet": response.text[:500],
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _clamp_int(raw, default, minimum, maximum):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _truncate_text(text, max_chars):
    if text is None:
        return None
    rendered = str(text)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 28] + "\n... [truncated tool-side] ..."
