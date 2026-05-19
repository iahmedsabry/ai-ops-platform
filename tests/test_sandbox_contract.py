"""HTTP tests for agent-sandbox /execute."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_sandbox.main import app
from agent_sandbox.tool_dispatch import dispatch_tool


@pytest.fixture
def sclient() -> TestClient:
    return TestClient(app)


def test_root(sclient: TestClient) -> None:
    r = sclient.get("/")
    assert r.status_code == 200


def test_execute_rejects_unknown_tool(sclient: TestClient) -> None:
    r = sclient.post(
        "/execute",
        json={"tool": "not_a_real_tool_ever", "arguments": {}},
    )
    assert r.status_code == 200
    assert "error" in r.json()


def test_execute_mocked_handler(
    sclient: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_sandbox import registry

    def _fake(arguments: dict) -> dict:
        _ = arguments
        return {"tool": "list_namespaces", "count": 0, "namespaces": []}

    monkeypatch.setitem(registry.HANDLERS, "list_namespaces", _fake)
    r = sclient.post(
        "/execute",
        json={"tool": "list_namespaces", "arguments": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("tool") == "list_namespaces"
    assert body.get("count") == 0


def test_list_ingresses_flags_missing_backend_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from agent_sandbox import tool_dispatch

    ingress = SimpleNamespace(
        metadata=SimpleNamespace(
            name="backend-ingress",
            namespace="backend",
        ),
        spec=SimpleNamespace(
            default_backend=None,
            rules=[
                SimpleNamespace(
                    host="example.internal",
                    http=SimpleNamespace(
                        paths=[
                            SimpleNamespace(
                                path="/backend",
                                path_type="Prefix",
                                backend=SimpleNamespace(
                                    service=SimpleNamespace(
                                        name="backend-outage-drill",
                                        port=SimpleNamespace(
                                            number=80,
                                            name=None,
                                        ),
                                    )
                                ),
                            )
                        ]
                    ),
                )
            ],
        ),
    )

    service = SimpleNamespace(
        metadata=SimpleNamespace(
            name="backend",
            namespace="backend",
        )
    )

    monkeypatch.setattr(
        tool_dispatch.networking_v1,
        "list_ingress_for_all_namespaces",
        lambda: SimpleNamespace(items=[ingress]),
    )
    monkeypatch.setattr(
        tool_dispatch.core_v1,
        "list_service_for_all_namespaces",
        lambda: SimpleNamespace(items=[service]),
    )
    monkeypatch.setattr(
        tool_dispatch.core_v1,
        "list_endpoints_for_all_namespaces",
        lambda: SimpleNamespace(items=[]),
    )

    result = dispatch_tool("list_ingresses", {})

    assert result["tool"] == "list_ingresses"
    invalid = result["ingresses"][0]["invalid_backends"]
    assert invalid == [
        {
            "reason": "service_missing",
            "service_name": "backend-outage-drill",
            "host": "example.internal",
            "path": "/backend",
        }
    ]


def test_catalog_tools_have_dispatch_implementation() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = yaml.safe_load(
        (root / "shared" / "tools.yaml").read_text(encoding="utf-8")
    )
    dispatch_text = (
        root / "agent_sandbox" / "tool_dispatch.py"
    ).read_text(encoding="utf-8")

    tool_names = {
        entry["name"]
        for entry in catalog.get("tools", [])
    }
    implemented = set(
        re.findall(
            r'(?:if|elif) tool == "([^"]+)"',
            dispatch_text,
        )
    )

    assert tool_names == implemented


def test_aws_cost_overview_uses_cost_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_sandbox import tool_dispatch

    class FakeCostExplorer:
        def get_cost_and_usage(self, **kwargs):
            group_by = kwargs.get("GroupBy") or []
            if group_by:
                return {
                    "ResultsByTime": [
                        {
                            "TimePeriod": {
                                "Start": "2026-05-01",
                                "End": "2026-05-15",
                            },
                            "Groups": [
                                {
                                    "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                                    "Metrics": {
                                        "UnblendedCost": {
                                            "Amount": "42.50",
                                            "Unit": "USD",
                                        }
                                    },
                                },
                                {
                                    "Keys": ["Amazon Simple Storage Service"],
                                    "Metrics": {
                                        "UnblendedCost": {
                                            "Amount": "10.00",
                                            "Unit": "USD",
                                        }
                                    },
                                },
                            ],
                        }
                    ]
                }

            return {
                "ResultsByTime": [
                    {
                        "TimePeriod": {
                            "Start": "2026-05-01",
                            "End": "2026-05-02",
                        },
                        "Total": {
                            "UnblendedCost": {
                                "Amount": "5.25",
                                "Unit": "USD",
                            }
                        },
                    },
                    {
                        "TimePeriod": {
                            "Start": "2026-05-02",
                            "End": "2026-05-03",
                        },
                        "Total": {
                            "UnblendedCost": {
                                "Amount": "4.75",
                                "Unit": "USD",
                            }
                        },
                    },
                ]
            }

        def get_cost_forecast(self, **kwargs):
            _ = kwargs
            return {
                "Total": {"Amount": "123.45", "Unit": "USD"},
                "ForecastResultsByTime": [
                    {
                        "TimePeriod": {
                            "Start": "2026-05-15",
                            "End": "2026-06-14",
                        },
                        "PredictionIntervalLowerBound": {"Amount": "110.00"},
                        "PredictionIntervalUpperBound": {"Amount": "140.00"},
                    }
                ],
            }

    class FakeSts:
        def get_caller_identity(self):
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/agent-sandbox/test",
            }

    monkeypatch.setattr(
        tool_dispatch,
        "cost_explorer_client",
        lambda: FakeCostExplorer(),
    )
    monkeypatch.setattr(
        tool_dispatch,
        "sts_client",
        lambda: FakeSts(),
    )

    result = dispatch_tool(
        "aws_cost_overview",
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-15",
            "include_forecast": True,
        },
    )

    assert result["tool"] == "aws_cost_overview"
    assert result["total_cost"]["amount"] == 10.0
    assert result["account"]["account_id"] == "123456789012"
    assert result["top_services"][0]["name"] == "Amazon Elastic Compute Cloud - Compute"
    assert result["forecast"]["mean_value"] == 123.45


def test_aws_cost_by_tag_requires_tag_key() -> None:
    result = dispatch_tool("aws_cost_by_tag", {})

    assert result == {"error": "tag_key is required"}
