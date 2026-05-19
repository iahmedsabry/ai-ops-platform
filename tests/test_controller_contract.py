"""HTTP contract tests for agent-controller (mocked Gemini + sandbox)."""

from __future__ import annotations

from typing import Any, Optional

import json

import pytest
from fastapi.testclient import TestClient

from agent_controller.gemini_client import GeminiClient
from agent_controller.main import app
from agent_controller.sandbox_client import SandboxClient
from agent_controller.tool_summaries import build_executive_summary


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_root(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status")


def test_get_chat_metadata(client: TestClient) -> None:
    r = client.get("/chat")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert "model" in body
    assert isinstance(body.get("prompt_modes"), list)


def test_post_chat_conversation_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_generate(
        self: GeminiClient,
        prompt: str,
        inline_images: Optional[list] = None,
    ) -> dict[str, Any]:
        _ = inline_images
        if "TOOL DIRECTORY" in prompt or "planning READ-ONLY" in prompt:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": '{"needs_tools": false}'},
                            ],
                        },
                    },
                ],
            }
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Hello from test"}],
                    },
                },
            ],
        }

    monkeypatch.setattr(GeminiClient, "generate", fake_generate)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("mode") == "conversation"
    assert "Hello from test" in data.get("response", "")


def test_post_chat_tool_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_generate(
        self: GeminiClient,
        prompt: str,
        inline_images: Optional[list] = None,
    ) -> dict[str, Any]:
        _ = inline_images
        if "TOOL DIRECTORY" in prompt or "planning READ-ONLY" in prompt:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"needs_tools": true, "tool_calls": '
                                        '[{"tool": "list_namespaces", '
                                        '"arguments": {}}]}'
                                    ),
                                },
                            ],
                        },
                    },
                ],
            }
        if "staff-level SRE" in prompt:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Analysis complete."},
                            ],
                        },
                    },
                ],
            }
        return {"candidates": [{"content": {"parts": [{"text": ""}]}}]}

    def fake_execute(
        self: SandboxClient,
        tool: str,
        arguments: dict,
    ) -> tuple[int, str, Any]:
        _ = arguments
        assert tool == "list_namespaces"
        payload = {
            "tool": "list_namespaces",
            "count": 1,
            "namespaces": [{"name": "default", "status": "Active"}],
        }
        return 200, json.dumps(payload), payload

    monkeypatch.setattr(GeminiClient, "generate", fake_generate)
    monkeypatch.setattr(SandboxClient, "execute", fake_execute)
    r = client.post("/chat", json={"message": "list namespaces"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("mode") == "tool_analysis"
    assert data.get("response") == "Analysis complete."


def test_ingress_summary_calls_out_missing_backend_service() -> None:
    lines = build_executive_summary(
        [
            {
                "tool": "list_ingresses",
                "result": {
                    "ingresses": [
                        {
                            "name": "backend-ingress",
                            "namespace": "backend",
                            "hosts": ["example.internal"],
                            "invalid_backends": [
                                {
                                    "reason": "service_missing",
                                    "service_name": "backend-outage-drill",
                                    "host": "example.internal",
                                    "path": "/backend",
                                }
                            ],
                        }
                    ]
                },
            }
        ]
    )

    assert any(
        "missing Service backend-outage-drill" in line
        for line in lines
    )


def test_routing_summary_calls_out_selector_and_endpoint_issues() -> None:
    lines = build_executive_summary(
        [
            {
                "tool": "diagnose_service_routing",
                "result": {
                    "issues": [
                        {
                            "kind": "Service",
                            "namespace": "backend",
                            "name": "api",
                            "reason": "selector_matches_no_pods",
                        },
                        {
                            "kind": "Ingress",
                            "namespace": "backend",
                            "name": "api-ing",
                            "reason": "backend_service_has_no_ready_endpoints",
                        },
                    ]
                },
            }
        ]
    )

    assert any(
        "selector_matches_no_pods" in line
        for line in lines
    )
    assert any(
        "backend_service_has_no_ready_endpoints" in line
        for line in lines
    )


def test_aws_cost_summary_includes_total_and_forecast() -> None:
    lines = build_executive_summary(
        [
            {
                "tool": "aws_cost_overview",
                "result": {
                    "time_period": {
                        "Start": "2026-04-15",
                        "End": "2026-05-15",
                    },
                    "total_cost": {
                        "amount": 321.09,
                        "unit": "USD",
                    },
                    "top_services": [
                        {
                            "name": "Amazon Elastic Compute Cloud - Compute",
                            "amount": 120.50,
                            "unit": "USD",
                        }
                    ],
                    "forecast": {
                        "mean_value": 355.0,
                        "unit": "USD",
                        "time_period": {
                            "Start": "2026-05-15",
                            "End": "2026-06-14",
                        },
                    },
                },
            }
        ]
    )

    assert any("321.09 USD" in line for line in lines)
    assert any("Amazon Elastic Compute Cloud - Compute" in line for line in lines)
    assert any("355.0 USD" in line for line in lines)
