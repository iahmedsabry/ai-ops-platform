"""HTTP tests for agent-sandbox /execute."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_sandbox.main import app


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
