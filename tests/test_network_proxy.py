from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.request import Request

import pytest

from deepscientist.cli import main
from deepscientist.network import configure_runtime_proxy, urlopen_with_proxy, websocket_connect_with_proxy


class _FakeOpener:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    def open(self, request, timeout=None):  # noqa: ANN001
        url = request.full_url if isinstance(request, Request) else str(request)
        self.calls.append((url, timeout))
        return object()


@pytest.fixture(autouse=True)
def _reset_runtime_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)
    configure_runtime_proxy(None)
    yield
    configure_runtime_proxy(None)


def test_urlopen_with_proxy_routes_remote_requests_through_explicit_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_opener = _FakeOpener()
    configure_runtime_proxy("http://127.0.0.1:7890")
    monkeypatch.setattr("deepscientist.network._proxy_opener", lambda proxy_url: fake_opener)

    urlopen_with_proxy(Request("https://example.com/api"), timeout=9)

    assert fake_opener.calls == [("https://example.com/api", 9)]


def test_urlopen_with_proxy_bypasses_proxy_for_local_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_opener = _FakeOpener()
    configure_runtime_proxy("http://127.0.0.1:7890")
    monkeypatch.setattr("deepscientist.network._NO_PROXY_OPENER", fake_opener)
    monkeypatch.setattr("deepscientist.network.stdlib_urlopen", lambda request, timeout=None: (_ for _ in ()).throw(AssertionError("unexpected stdlib urlopen")))

    urlopen_with_proxy(Request("http://127.0.0.1:20999/api/quests"), timeout=3)

    assert fake_opener.calls == [("http://127.0.0.1:20999/api/quests", 3)]


def test_websocket_connect_with_proxy_uses_explicit_proxy_for_remote_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    configure_runtime_proxy("http://127.0.0.1:7890")

    def fake_connect(uri: str, **kwargs):  # noqa: ANN001
        observed["uri"] = uri
        observed["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("deepscientist.network.stdlib_websocket_connect", fake_connect)

    websocket_connect_with_proxy("wss://gateway.discord.gg/?v=10")

    assert observed["uri"] == "wss://gateway.discord.gg/?v=10"
    assert observed["kwargs"]["proxy"] == "http://127.0.0.1:7890"


def test_websocket_connect_with_proxy_disables_proxy_for_local_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    configure_runtime_proxy("http://127.0.0.1:7890")

    def fake_connect(uri: str, **kwargs):  # noqa: ANN001
        observed["uri"] = uri
        observed["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("deepscientist.network.stdlib_websocket_connect", fake_connect)

    websocket_connect_with_proxy("ws://127.0.0.1:20999/terminal/attach")

    assert observed["uri"] == "ws://127.0.0.1:20999/terminal/attach"
    assert observed["kwargs"]["proxy"] is None


def test_main_accepts_global_proxy_flag(monkeypatch: pytest.MonkeyPatch, temp_home: Path) -> None:
    observed: dict[str, object] = {}
    monkeypatch.setattr("deepscientist.cli.configure_runtime_proxy", lambda proxy: observed.setdefault("proxy", proxy))
    monkeypatch.setattr("deepscientist.cli.status_command", lambda home, quest_id: 0)

    exit_code = main(["--home", str(temp_home), "--proxy", "http://127.0.0.1:7890", "status"])

    assert exit_code == 0
    assert observed["proxy"] == "http://127.0.0.1:7890"


def test_runtime_dependencies_include_httpx_socks_for_socks_proxies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    lock = tomllib.loads((repo_root / "uv.lock").read_text(encoding="utf-8"))
    locked_packages = {package["name"]: package for package in lock["package"]}
    locked_deepscientist = locked_packages["deepscientist"]

    assert any(item.startswith("httpx[socks]") for item in dependencies)
    assert "socksio" in locked_packages
    assert {"name": "httpx", "extra": ["socks"]} in locked_deepscientist["dependencies"]
