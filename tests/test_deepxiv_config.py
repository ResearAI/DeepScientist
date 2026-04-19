from __future__ import annotations

import json
from pathlib import Path

import deepscientist.config.service as config_service_module
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_deepxiv_test_payload_returns_preview_and_uses_transformers(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    payload = manager.load_named_normalized("config")
    payload["literature"]["deepxiv"] = {
        "enabled": True,
        "base_url": "https://data.rag.ac.cn",
        "token": "token-123",
        "token_env": None,
        "default_result_size": 20,
        "preview_characters": 5000,
        "request_timeout_seconds": 90,
    }
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return _FakeResponse({
            "total": 1,
            "took": 12,
            "results": [{"title": "Transformers for Science", "paper_id": "2501.00001"}],
        })

    monkeypatch.setattr(config_service_module, "urlopen", fake_urlopen)

    result = manager.test_deepxiv_payload(payload)

    assert result["ok"] is True
    assert "transformers" in str(captured["url"])
    assert captured["auth"] == "Bearer token-123"
    assert captured["timeout"] == 90
    assert result["details"]["result_count"] == 1
    assert "Transformers for Science" in result["preview"]


def test_deepxiv_test_payload_reports_empty_results(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    payload = manager.load_named_normalized("config")
    payload["literature"]["deepxiv"] = {
        "enabled": True,
        "base_url": "https://data.rag.ac.cn",
        "token": "token-123",
        "token_env": None,
        "default_result_size": 20,
        "preview_characters": 5000,
        "request_timeout_seconds": 90,
    }

    monkeypatch.setattr(
        config_service_module,
        "urlopen",
        lambda request, timeout=None: _FakeResponse({"total": 0, "took": 3, "results": []}),
    )

    result = manager.test_deepxiv_payload(payload)

    assert result["ok"] is False
    assert result["details"]["result_count"] == 0
    assert result["errors"] == ["No results were returned for `transformers`."]
