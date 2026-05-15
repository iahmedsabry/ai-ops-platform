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
