from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen
import zipfile

from deepscientist.config import ConfigManager
from deepscientist.benchstore import BenchStoreService
from deepscientist.daemon.app import DaemonApp
from deepscientist.daemon.api.handlers import ApiHandlers
from deepscientist.home import ensure_home_layout
from deepscientist.shared import ensure_dir, write_text, write_yaml


def _make_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    ensure_dir(repo_root / "AISB" / "catalog")
    ensure_dir(repo_root / "src" / "prompts" / "benchstore")
    write_text(
        repo_root / "src" / "prompts" / "benchstore" / "system.md",
        "You are the BenchStore setup agent.",
    )
    return repo_root


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http_ready(url: str, *, timeout_seconds: float = 5.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url) as response:  # noqa: S310
                if int(response.status) == 200:
                    return
        except Exception:
            time.sleep(0.05)
    raise AssertionError(url)


def _get_json(url: str):
    with urlopen(url) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _hardware_payload() -> dict:
    return {
        "prompt_hardware_summary": "CPU: Test CPU (16 logical cores) | Memory: 32GB | Disk: 120GB free on / | GPUs: 0:Test GPU 16GB | Selected GPUs: 0",
        "system": {
            "cpu": {"logical_cores": 16},
            "memory": {"total_gb": 32},
            "disks": [{"free_gb": 120}],
            "gpus": [{"gpu_id": "0", "name": "Test GPU", "memory_total_gb": 16}],
        },
        "preferences": {
            "gpu_selection_mode": "all",
            "effective_gpu_ids": ["0"],
        },
    }


def _weak_hardware_payload() -> dict:
    return {
        "prompt_hardware_summary": "CPU: Tiny CPU (2 logical cores) | Memory: 4GB | Disk: 20GB free on / | GPUs: none | Selected GPUs: none",
        "system": {
            "cpu": {"logical_cores": 2},
            "memory": {"total_gb": 4},
            "disks": [{"free_gb": 20}],
            "gpus": [],
        },
        "preferences": {
            "gpu_selection_mode": "all",
            "effective_gpu_ids": [],
        },
    }


def test_benchstore_service_lists_valid_entries_and_reports_invalid_files(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "aisb.t3.sample.yaml",
        {
            "name": "Sample Benchmark",
            "id": "aisb.t3.sample",
            "one_line": "Short summary",
            "snapshot_status": "runnable",
            "support_level": "turnkey",
            "primary_outputs": ["accuracy", "evaluation_report"],
            "launch_profiles": [
                {
                    "id": "quick_check",
                    "label": "Quick Check",
                    "description": "Run the smallest safe route first.",
                }
            ],
            "dataset_download": {
                "primary_method": "mixed",
                "sources": [
                    {
                        "kind": "huggingface",
                        "url": "https://huggingface.co/datasets/example/sample",
                        "access": "public",
                        "note": "Primary sample dataset.",
                    }
                ],
                "notes": ["Convert the raw split into benchmark JSON before training."],
            },
            "credential_requirements": {
                "mode": "conditional",
                "items": ["OPENAI_API_KEY"],
                "notes": ["Only needed for the optional evaluator route."],
            },
            "environment": {
                "python": "3.10",
                "cuda": "12.1",
                "key_packages": ["torch==2.4.0"],
                "notes": ["Use the local requirements file."],
            },
            "metadata": {"owner": "search-team", "channel": "vision"},
            "paper": {
                "title": "Sample Paper",
                "venue": "BenchConf",
                "year": 2026,
                "authors": ["Search Author"],
            },
            "resources": {
                "minimum": {"cpu_cores": 8, "ram_gb": 16, "gpu_count": 1, "gpu_vram_gb": 8},
                "recommended": {"cpu_cores": 12, "ram_gb": 24, "gpu_count": 1, "gpu_vram_gb": 12},
            },
        },
    )
    write_yaml(catalog_root / "broken.yaml", {"one_line": "missing name"})

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    payload = service.list_entries(hardware_payload=_hardware_payload())

    assert payload["ok"] is True
    assert payload["total"] == 1
    assert len(payload["invalid_entries"]) == 1
    assert payload["items"][0]["id"] == "aisb.t3.sample"
    assert payload["items"][0]["environment"]["python"] == "3.10"
    assert payload["items"][0]["snapshot_status"] == "runnable"
    assert payload["items"][0]["support_level"] == "turnkey"
    assert payload["items"][0]["primary_outputs"] == ["accuracy", "evaluation_report"]
    assert payload["items"][0]["launch_profiles"][0]["id"] == "quick_check"
    assert payload["items"][0]["dataset_download"]["primary_method"] == "mixed"
    assert payload["items"][0]["dataset_download"]["sources"][0]["kind"] == "huggingface"
    assert payload["items"][0]["credential_requirements"]["items"] == ["OPENAI_API_KEY"]
    assert payload["items"][0]["compatibility"]["recommended_ok"] is True
    assert payload["items"][0]["compatibility"]["minimum_ok"] is True
    assert payload["device_capacity"]["capacity_class"] in {"medium", "high"}
    assert "best_match_ids" in payload["shelves"]
    assert "requires_execution" in payload["filter_options"]


def test_benchstore_recommendations_exclude_risk_marked_entries(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    base_entry = {
        "task_description": "Run a benchmark with valid hardware fit.",
        "resources": {
            "minimum": {"cpu_cores": 4, "ram_gb": 8, "gpu_count": 1, "gpu_vram_gb": 8},
            "recommended": {"cpu_cores": 8, "ram_gb": 16, "gpu_count": 1, "gpu_vram_gb": 12},
        },
    }
    write_yaml(
        catalog_root / "safe.yaml",
        {
            **base_entry,
            "name": "Safe Benchmark",
            "id": "safe.benchmark",
        },
    )
    write_yaml(
        catalog_root / "risky.yaml",
        {
            **base_entry,
            "name": "Risky Benchmark",
            "id": "risky.benchmark",
            "risk_flags": ["route_caveat"],
            "risk_notes": ["Benchmark route is fragmented across multiple scripts."],
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    payload = service.list_entries(hardware_payload=_hardware_payload())
    items = {item["id"]: item for item in payload["items"]}

    assert items["safe.benchmark"]["recommendation"]["shelf_bucket"] == "best_match"
    assert items["risky.benchmark"]["recommendation"]["shelf_bucket"] == "risk_flagged"
    assert items["risky.benchmark"]["risk_flags"] == ["route_caveat"]
    assert items["risky.benchmark"]["risk_notes"] == ["Benchmark route is fragmented across multiple scripts."]
    assert "safe.benchmark" in payload["shelves"]["best_match_ids"]
    assert "risky.benchmark" not in payload["shelves"]["best_match_ids"]


def test_benchstore_recommendations_parse_open_ended_day_time_bands(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    base_entry = {
        "task_description": "Benchmark entry used to verify time-band parsing.",
        "requires_execution": True,
        "requires_paper": True,
        "resources": {
            "minimum": {"cpu_cores": 4, "ram_gb": 8, "gpu_count": 1, "gpu_vram_gb": 8},
            "recommended": {"cpu_cores": 8, "ram_gb": 16, "gpu_count": 1, "gpu_vram_gb": 12},
        },
    }
    write_yaml(
        catalog_root / "short.yaml",
        {
            **base_entry,
            "name": "Short Benchmark",
            "id": "short.benchmark",
            "time_band": "2-6h",
        },
    )
    write_yaml(
        catalog_root / "oneday.yaml",
        {
            **base_entry,
            "name": "One Day Plus Benchmark",
            "id": "one.day.plus",
            "time_band": "1d+",
        },
    )
    write_yaml(
        catalog_root / "multiday.yaml",
        {
            **base_entry,
            "name": "Four Day Plus Benchmark",
            "id": "four.day.plus",
            "time_band": "4d+",
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    payload = service.list_entries(hardware_payload=_hardware_payload())
    items = {item["id"]: item for item in payload["items"]}

    assert items["short.benchmark"]["recommendation"]["time_upper_hours"] == 6.0
    assert items["one.day.plus"]["recommendation"]["time_upper_hours"] == 24.0
    assert items["four.day.plus"]["recommendation"]["time_upper_hours"] == 96.0
    assert items["short.benchmark"]["recommendation"]["score"] > items["four.day.plus"]["recommendation"]["score"]


def test_benchstore_entry_detail_includes_setup_prompt_preview(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "bench.yaml",
        {
            "name": "Device Aware Benchmark",
            "id": "device.aware",
            "task_description": "Run a benchmark with hardware-aware planning.",
            "paper": {
                "title": "Hardware Fit Paper",
                "venue": "TestConf",
                "year": 2026,
                "authors": ["Alice", "Bob"],
            },
            "environment": {
                "python": "3.11",
                "pytorch": "2.5.1",
                "notes": ["CPU-only execution is supported."],
            },
            "display": {
                "palette_seed": "warm-slate",
                "art_style": "ops-clean",
                "accent_priority": "medium",
                "summary_cards": ["status", "metrics"],
            },
            "metadata": {"owner": "bench-team", "pass": 2},
            "risk_flags": ["route_caveat"],
            "risk_notes": ["This benchmark keeps multiple competing launcher routes."],
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    payload = service.get_entry("device.aware", hardware_payload=_hardware_payload())

    assert payload["ok"] is True
    assert payload["entry"]["id"] == "device.aware"
    assert payload["entry"]["environment"]["python"] == "3.11"
    assert payload["entry"]["risk_flags"] == ["route_caveat"]
    assert payload["entry"]["risk_notes"] == ["This benchmark keeps multiple competing launcher routes."]
    assert payload["entry"]["raw_payload"]["metadata"]["owner"] == "bench-team"
    assert payload["entry"]["raw_payload"]["paper"]["authors"] == ["Alice", "Bob"]
    assert payload["entry"]["raw_payload"]["display"]["summary_cards"] == ["status", "metrics"]
    assert "Device Aware Benchmark" in payload["entry"]["setup_prompt_preview"]
    assert "prompt_hardware_summary" in payload["entry"]["setup_prompt_preview"]
    assert "Runtime Environment" in payload["entry"]["setup_prompt_preview"]


def test_benchstore_extended_catalog_fields_surface_cleanly(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "extended.yaml",
        {
            "name": "Extended Benchmark",
            "id": "aisb.extended",
            "one_line": "Extended metadata smoke.",
            "homepage": "https://example.org/bench",
            "official_links": {
                "homepage": "https://example.org/bench",
                "github": "https://github.com/example/bench",
                "docs": "https://example.org/docs",
            },
            "discovery": {
                "collection": "AISB Featured",
                "collection_priority": 3,
                "recommendation_weight": 7,
                "featured": True,
                "featured_reason": "Important benchmark",
            },
            "display": {
                "placement": "hero",
                "card_size": "xl",
                "badge": "Featured",
            },
        },
    )
    write_yaml(
        catalog_root / "legacy.yaml",
        {
            "name": "Legacy Benchmark",
            "id": "aisb.legacy",
            "one_line": "Legacy metadata smoke.",
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    payload = service.get_entry("aisb.extended", hardware_payload=_hardware_payload())
    entry = payload["entry"]

    assert entry["homepage"] == "https://example.org/bench"
    assert entry["official_links"] == {
        "homepage": "https://example.org/bench",
        "github": "https://github.com/example/bench",
        "docs": "https://example.org/docs",
    }
    assert entry["discovery"] == {
        "collection": "AISB Featured",
        "collection_priority": 3,
        "recommendation_weight": 7,
        "featured": True,
        "featured_reason": "Important benchmark",
    }
    assert entry["display"]["placement"] == "hero"
    assert entry["display"]["card_size"] == "xl"
    assert entry["display"]["badge"] == "Featured"
    assert entry["raw_payload"]["official_links"]["github"] == "https://github.com/example/bench"

    setup_prompt = entry["setup_prompt_preview"]
    assert "- homepage: https://example.org/bench" in setup_prompt
    assert "## Official Links" in setup_prompt
    assert "- github: https://github.com/example/bench" in setup_prompt
    assert "## Discovery" in setup_prompt
    assert "- collection: AISB Featured" in setup_prompt
    assert "- collection_priority: 3" in setup_prompt
    assert "- recommendation_weight: 7" in setup_prompt
    assert "- featured_reason: Important benchmark" in setup_prompt

    packet = service.build_setup_packet(entry_id="aisb.extended", hardware_payload=_hardware_payload())
    context = packet["launch_payload"]["startup_contract"]["benchstore_context"]
    assert context["homepage"] == "https://example.org/bench"
    assert context["official_links"]["docs"] == "https://example.org/docs"
    assert context["discovery"]["featured"] is True
    assert context["display"]["placement"] == "hero"

    legacy_entry = service.get_entry("aisb.legacy")["entry"]
    legacy_prompt = legacy_entry["setup_prompt_preview"]
    assert legacy_entry["official_links"] == {}
    assert legacy_entry["discovery"] == {}
    assert "## Official Links" not in legacy_prompt
    assert "## Discovery" not in legacy_prompt


def test_benchstore_api_handlers_surface_catalog_and_detail(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    write_yaml(
        repo_root / "AISB" / "catalog" / "bench.yaml",
        {
            "name": "Handler Benchmark",
            "id": "handler.benchmark",
        },
    )
    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    app = SimpleNamespace(
        benchstore_service=service,
        admin_service=SimpleNamespace(system_hardware=lambda refresh=False: _hardware_payload()),
        home=tmp_path / "home",
        skill_installer=None,
        repo_root=repo_root,
    )
    handlers = ApiHandlers(app)

    listing = handlers.benchstore_entries()
    detail = handlers.benchstore_entry("handler.benchmark")
    image = handlers.benchstore_entry_image("handler.benchmark")

    assert listing["ok"] is True
    assert listing["total"] == 1
    assert detail["ok"] is True
    assert detail["entry"]["name"] == "Handler Benchmark"
    assert image[0] == 404


def test_benchstore_setup_packet_respects_install_and_device_fit(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "bench.yaml",
        {
            "name": "Launch Ready Benchmark",
            "id": "launch.ready",
            "task_description": "Run the local benchmark and prepare an autonomous launch packet.",
            "requires_execution": True,
            "requires_paper": True,
            "environment": {
                "python": "3.10",
                "cuda": "12.1",
                "key_packages": ["flash-attn==2.7.0.post2"],
            },
            "resources": {
                "minimum": {"cpu_cores": 8, "ram_gb": 16, "gpu_count": 1, "gpu_vram_gb": 8},
            },
        },
    )
    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    install_dir = service.entry_install_dir({"id": "launch.ready", "name": "Launch Ready Benchmark", "download": {}})
    ensure_dir(install_dir)
    ensure_dir(install_dir / "datasets")
    write_text(install_dir / "latex.md", "# latex entry\n")
    service.write_install_record(
        "launch.ready",
        {
            "entry_id": "launch.ready",
            "status": "installed",
            "local_path": str(install_dir),
        },
    )

    packet = service.build_setup_packet(entry_id="launch.ready", hardware_payload=_hardware_payload(), locale="zh")
    assert packet["assistant_label"] == "BenchStore Setup Agent · Codex"
    assert packet["device_fit"] in {"recommended", "minimum"}
    assert "launch.ready" == packet["entry_id"]
    assert "startup_contract" in packet["launch_payload"]
    context = packet["launch_payload"]["startup_contract"]["benchstore_context"]
    assert context["environment"]["python"] == "3.10"
    assert packet["benchmark_local_path"] == str(install_dir)
    assert packet["latex_markdown_path"] == str(install_dir / "latex.md")
    assert str(install_dir / "datasets") in (packet["local_dataset_paths"] or [])
    suggested_form = packet["suggested_form"]
    assert str(install_dir) in str(suggested_form["baseline_urls"])
    assert str(install_dir / "datasets") in str(suggested_form["baseline_urls"])
    assert str(install_dir / "latex.md") in str(suggested_form["paper_urls"])


def test_benchstore_setup_packet_ignores_unrelated_invalid_catalog_entries(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "valid.yaml",
        {
            "name": "Valid Bench",
            "id": "valid.bench",
            "task_description": "A valid benchmark entry used to verify setup packet lookup.",
            "requires_execution": True,
            "requires_paper": True,
            "download": {
                "url": "https://example.com/valid.zip",
                "archive_type": "zip",
                "local_dir_name": "valid-bench",
            },
        },
    )
    write_yaml(
        catalog_root / "broken-risk-notes.yaml",
        {
            "name": "Broken Bench",
            "id": "broken.bench",
            "risk_notes": "this should have been a list",
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    install_dir = service.install_root / "valid-bench"
    ensure_dir(install_dir / "dataset")
    write_text(install_dir / "latex.md", "# latex\n")
    service.write_install_record(
        "valid.bench",
        {
            "entry_id": "valid.bench",
            "entry_name": "Valid Bench",
            "status": "installed",
            "task_id": "task-valid",
            "local_path": str(install_dir),
            "download_url": "https://example.com/valid.zip",
            "archive_type": "zip",
            "installed_at": "2026-04-10T00:00:00+00:00",
            "updated_at": "2026-04-10T00:00:00+00:00",
        },
    )

    packet = service.build_setup_packet(
        entry_id="valid.bench",
        hardware_payload=_hardware_payload(),
        locale="en",
    )

    assert packet["entry_id"] == "valid.bench"
    assert packet["benchmark_local_path"] == str(install_dir)
    assert packet["latex_markdown_path"] == str(install_dir / "latex.md")


def test_benchstore_setup_packet_allows_launch_even_when_device_is_below_minimum(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "bench.yaml",
        {
            "name": "Heavy Benchmark",
            "id": "heavy.launch",
            "task_description": "Benchmark that normally expects a stronger local machine.",
            "requires_execution": True,
            "resources": {
                "minimum": {"cpu_cores": 16, "ram_gb": 64, "gpu_count": 2, "gpu_vram_gb": 24},
                "recommended": {"cpu_cores": 32, "ram_gb": 128, "gpu_count": 4, "gpu_vram_gb": 48},
            },
        },
    )
    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    install_dir = service.entry_install_dir({"id": "heavy.launch", "name": "Heavy Benchmark", "download": {}})
    ensure_dir(install_dir)
    service.write_install_record(
        "heavy.launch",
        {
            "entry_id": "heavy.launch",
            "status": "installed",
            "local_path": str(install_dir),
        },
    )

    packet = service.build_setup_packet(entry_id="heavy.launch", hardware_payload=_weak_hardware_payload(), locale="zh")

    assert packet["device_fit"] == "unsupported"
    constraints_text = "\n".join(packet["constraints"] or [])
    assert "仍允许启动" in constraints_text
    assert "launch_payload" in packet


def test_benchstore_image_route_serves_catalog_preview(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    image_dir = tmp_path / "AISB" / "image"
    ensure_dir(image_dir)
    image_path = image_dir / "bench.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xd9")
    write_yaml(
        repo_root / "AISB" / "catalog" / "bench.yaml",
        {
            "name": "Image Benchmark",
            "id": "image.benchmark",
            "image_path": "../../../AISB/image/bench.jpg",
        },
    )
    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    app = SimpleNamespace(
        benchstore_service=service,
        admin_service=SimpleNamespace(system_hardware=lambda refresh=False: _hardware_payload()),
        home=tmp_path / "home",
        skill_installer=None,
        repo_root=repo_root,
    )
    handlers = ApiHandlers(app)

    status, headers, content = handlers.benchstore_entry_image("image.benchmark")

    assert status == 200
    assert headers["Content-Type"] == "image/jpeg"
    assert content == b"\xff\xd8\xff\xd9"


def test_benchstore_install_task_downloads_and_extracts_local_zip(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    zip_path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("fixture-root/README.txt", "bench fixture")
    write_yaml(
        repo_root / "AISB" / "catalog" / "bench.yaml",
        {
            "name": "Zip Fixture Benchmark",
            "id": "zip.fixture",
            "download": {
                "url": zip_path.as_uri(),
                "archive_type": "zip",
                "local_dir_name": "zip_fixture",
            },
        },
    )
    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)

    class _Reporter:
        def __init__(self) -> None:
            self.messages: list[tuple[str, dict]] = []

        def start(self, **kwargs):
            self.messages.append(("start", kwargs))
            return kwargs

        def progress(self, **kwargs):
            self.messages.append(("progress", kwargs))
            return kwargs

        def complete(self, **kwargs):
            self.messages.append(("complete", kwargs))
            return kwargs

    reporter = _Reporter()
    record = service.run_install_task(entry_id="zip.fixture", reporter=reporter, task_id="admintask-bench-001")

    assert record["status"] == "installed"
    installed_path = Path(str(record["local_path"]))
    assert installed_path.exists()
    assert (installed_path / "README.txt").exists()


def test_benchstore_http_flow_installs_builds_setup_packet_and_launches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = _make_repo_root(tmp_path)
    zip_path = tmp_path / "fixture-http.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("fixture-root/README.txt", "bench fixture http")
    write_yaml(
        repo_root / "AISB" / "catalog" / "bench.yaml",
        {
            "name": "HTTP Flow Benchmark",
            "id": "http.flow",
            "task_description": "Run the benchmark and prepare an autonomous launch packet.",
            "requires_execution": True,
            "requires_paper": True,
            "download": {
                "url": zip_path.as_uri(),
                "archive_type": "zip",
                "local_dir_name": "http_flow",
            },
            "resources": {
                "minimum": {"cpu_cores": 8, "ram_gb": 16, "gpu_count": 1, "gpu_vram_gb": 8},
            },
        },
    )

    monkeypatch.setattr("deepscientist.daemon.app.repo_root", lambda: repo_root)
    ensure_home_layout(tmp_path / "home")
    ConfigManager(tmp_path / "home").ensure_files()

    app = DaemonApp(tmp_path / "home")
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    app.schedule_turn = lambda quest_id, reason="user_message": {  # type: ignore[method-assign]
        "scheduled": True,
        "started": False,
        "queued": True,
        "reason": reason,
    }

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/api/health")
        listing = _get_json(f"{base_url}/api/benchstore/entries")
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == "http.flow"

        install_request = Request(
            f"{base_url}/api/benchstore/entries/http.flow/install",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        install_response = json.loads(urlopen(install_request).read().decode("utf-8"))  # noqa: S310
        task_id = install_response["task"]["task_id"]
        deadline = time.time() + 20
        task_status = None
        while time.time() < deadline:
            task_payload = _get_json(f"{base_url}/api/system/tasks/{task_id}")
            task_status = str(task_payload["task"]["status"])
            if task_status in {"completed", "failed"}:
                break
            time.sleep(0.1)
        assert task_status == "completed"

        detail = _get_json(f"{base_url}/api/benchstore/entries/http.flow")
        assert detail["entry"]["install_state"]["status"] == "installed"

        setup_packet = _get_json(f"{base_url}/api/benchstore/entries/http.flow/setup-packet")
        assert setup_packet["setup_packet"]["assistant_label"] == "BenchStore Setup Agent · Codex"
        assert setup_packet["setup_packet"]["benchmark_local_path"]

        launch_request = Request(
            f"{base_url}/api/benchstore/entries/http.flow/launch",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        launch_payload = json.loads(urlopen(launch_request).read().decode("utf-8"))  # noqa: S310
        quest_id = str(launch_payload["snapshot"]["quest_id"])
        assert quest_id.startswith("B-")
        session_payload = _get_json(f"{base_url}/api/quests/{quest_id}/session")
        startup_contract = dict(session_payload["snapshot"].get("startup_contract") or {})
        benchstore_context = dict(startup_contract.get("benchstore_context") or {})
        assert benchstore_context["entry_id"] == "http.flow"
        assert session_payload["snapshot"]["workspace_mode"] == "autonomous"
        assert session_payload["snapshot"]["quest_class"] == "benchstore"
        assert session_payload["snapshot"]["listed_in_projects"] is False
    finally:
        app.request_shutdown(source="test-benchstore-http-flow")
        server_thread.join(timeout=10)


def test_benchstore_http_launch_allows_unsupported_device_when_benchmark_is_installed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = _make_repo_root(tmp_path)
    write_yaml(
        repo_root / "AISB" / "catalog" / "bench.yaml",
        {
            "name": "Unsupported Device Benchmark",
            "id": "unsupported.launch",
            "task_description": "Should still launch even if this machine is below target.",
            "requires_execution": True,
            "resources": {
                "minimum": {"cpu_cores": 16, "ram_gb": 64, "gpu_count": 2, "gpu_vram_gb": 24},
            },
        },
    )

    monkeypatch.setattr("deepscientist.daemon.app.repo_root", lambda: repo_root)
    ensure_home_layout(tmp_path / "home")
    ConfigManager(tmp_path / "home").ensure_files()

    app = DaemonApp(tmp_path / "home")
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    app.schedule_turn = lambda quest_id, reason="user_message": {  # type: ignore[method-assign]
        "scheduled": True,
        "started": False,
        "queued": True,
        "reason": reason,
    }
    app.admin_service.system_hardware = lambda refresh=False: _weak_hardware_payload()  # type: ignore[method-assign]

    service = app.benchstore_service
    install_dir = service.entry_install_dir({"id": "unsupported.launch", "name": "Unsupported Device Benchmark", "download": {}})
    ensure_dir(install_dir)
    service.write_install_record(
        "unsupported.launch",
        {
            "entry_id": "unsupported.launch",
            "status": "installed",
            "local_path": str(install_dir),
        },
    )

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/api/health")
        launch_request = Request(
            f"{base_url}/api/benchstore/entries/unsupported.launch/launch",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        launch_payload = json.loads(urlopen(launch_request).read().decode("utf-8"))  # noqa: S310
        assert launch_payload["ok"] is True
        assert str(launch_payload["snapshot"]["quest_id"]).startswith("B-")
        assert launch_payload["snapshot"]["workspace_mode"] == "autonomous"
    finally:
        app.request_shutdown(source="test-benchstore-http-launch-unsupported")
        server_thread.join(timeout=10)


def test_benchstore_recommendations_use_snapshot_and_support_status(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    common = {
        "task_description": "Benchmark entry used to verify snapshot-aware recommendation scoring.",
        "resources": {
            "minimum": {"cpu_cores": 4, "ram_gb": 8, "gpu_count": 1, "gpu_vram_gb": 8},
            "recommended": {"cpu_cores": 8, "ram_gb": 16, "gpu_count": 1, "gpu_vram_gb": 12},
        },
    }
    write_yaml(
        catalog_root / "runnable.yaml",
        {
            **common,
            "name": "Runnable Turnkey Benchmark",
            "id": "runnable.turnkey",
            "snapshot_status": "runnable",
            "support_level": "turnkey",
        },
    )
    write_yaml(
        catalog_root / "recovery.yaml",
        {
            **common,
            "name": "Recovery Benchmark",
            "id": "recovery.benchmark",
            "snapshot_status": "restore_needed",
            "support_level": "recovery",
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    payload = service.list_entries(hardware_payload=_hardware_payload())
    items = {item["id"]: item for item in payload["items"]}

    assert items["runnable.turnkey"]["recommendation"]["score"] > items["recovery.benchmark"]["recommendation"]["score"]
    reasons = " | ".join(items["recovery.benchmark"]["recommendation"]["reasons"])
    assert "restoration" in reasons.lower() or "recovery" in reasons.lower()


def test_benchstore_prefers_locale_specific_catalog_file(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "locale.sample.yaml",
        {
            "name": "English Benchmark",
            "id": "locale.sample",
            "one_line": "English summary",
        },
    )
    write_yaml(
        catalog_root / "locale.sample.zh.yaml",
        {
            "name": "中文基准",
            "id": "locale.sample",
            "one_line": "中文简介",
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    en_listing = service.list_entries(locale="en")
    zh_listing = service.list_entries(locale="zh")
    zh_detail = service.get_entry("locale.sample", locale="zh")

    assert en_listing["items"][0]["name"] == "English Benchmark"
    assert zh_listing["items"][0]["name"] == "中文基准"
    assert zh_detail["entry"]["one_line"] == "中文简介"


def test_benchstore_setup_packet_localizes_prefilled_form_by_locale(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "locale.launch.yaml",
        {
            "name": "English Benchmark",
            "id": "locale.launch",
            "one_line": "English summary",
            "task_description": "English benchmark description.",
            "requires_paper": True,
        },
    )
    write_yaml(
        catalog_root / "locale.launch.zh.yaml",
        {
            "name": "中文基准",
            "id": "locale.launch",
            "one_line": "中文摘要",
            "task_description": "中文 benchmark 描述。",
            "requires_paper": True,
        },
    )

    service = BenchStoreService(tmp_path / "home", repo_root=repo_root)
    en_packet = service.build_setup_packet(entry_id="locale.launch", hardware_payload=_hardware_payload(), locale="en")
    zh_packet = service.build_setup_packet(entry_id="locale.launch", hardware_payload=_hardware_payload(), locale="zh")

    assert en_packet["project_title"] == "English Benchmark Autonomous Research"
    assert zh_packet["project_title"] == "中文基准 全自动研究"
    assert "English benchmark description." in str(en_packet["suggested_form"]["goal"])
    assert "Main research target" in str(en_packet["suggested_form"]["goal"])
    assert "中文 benchmark 描述。" in str(zh_packet["suggested_form"]["goal"])
    assert "核心研究目标" in str(zh_packet["suggested_form"]["goal"])
    assert "faithful, comparable, reusable baseline" in str(en_packet["suggested_form"]["objectives"])
    assert "Robustly surpass strong baselines / SoTA" in str(en_packet["suggested_form"]["objectives"])
    assert "faithful, comparable, reusable baseline" not in str(zh_packet["suggested_form"]["objectives"])
    assert "可比较、可复用的 baseline" in str(zh_packet["suggested_form"]["objectives"])
    assert "稳健超越强基线 / SoTA" in str(zh_packet["suggested_form"]["objectives"])
    assert "full research task rather than a baseline-only reproduction task" in str(en_packet["suggested_form"]["custom_brief"])
    assert "完整研究，而不是 baseline-only 复现" in str(zh_packet["suggested_form"]["custom_brief"])
    assert "Primary Benchmark Goal" in str(en_packet["startup_instruction"])
    assert "核心 benchmark 目标" in str(zh_packet["startup_instruction"])
    assert en_packet["suggested_form"]["user_language"] == "en"
    assert zh_packet["suggested_form"]["user_language"] == "zh"


def test_benchstore_http_routes_preserve_locale_query_for_catalog_and_detail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "locale.http.yaml",
        {
            "name": "English Title",
            "id": "locale.http",
            "one_line": "English summary",
            "task_description": "English description",
        },
    )
    write_yaml(
        catalog_root / "locale.http.zh.yaml",
        {
            "name": "中文标题",
            "id": "locale.http",
            "one_line": "中文摘要",
            "task_description": "中文描述",
        },
    )

    monkeypatch.setattr("deepscientist.daemon.app.repo_root", lambda: repo_root)
    ensure_home_layout(tmp_path / "home")
    ConfigManager(tmp_path / "home").ensure_files()

    app = DaemonApp(tmp_path / "home")
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_thread = threading.Thread(target=app.serve, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    try:
        _wait_for_http_ready(f"{base_url}/api/health")
        zh_listing = _get_json(f"{base_url}/api/benchstore/entries?locale=zh")
        zh_detail = _get_json(f"{base_url}/api/benchstore/entries/locale.http?locale=zh")

        assert zh_listing["items"][0]["name"] == "中文标题"
        assert zh_listing["items"][0]["one_line"] == "中文摘要"
        assert zh_listing["items"][0]["source_file"].endswith(".zh.yaml")
        assert zh_detail["entry"]["name"] == "中文标题"
        assert zh_detail["entry"]["one_line"] == "中文摘要"
        assert zh_detail["entry"]["task_description"] == "中文描述"
        assert zh_detail["entry"]["source_file"].endswith(".zh.yaml")
    finally:
        app.request_shutdown(source="test-benchstore-http-locale")
        server_thread.join(timeout=10)


def test_benchstore_setup_packet_uses_global_default_runner_label(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    catalog_root = repo_root / "AISB" / "catalog"
    write_yaml(
        catalog_root / "runner.label.yaml",
        {
            "name": "Runner Label Benchmark",
            "id": "runner.label",
            "one_line": "Verify setup packet runner label follows global selection.",
        },
    )
    home = tmp_path / "home"
    ensure_home_layout(home)
    manager = ConfigManager(home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["default_runner"] = "claude"
    write_yaml(manager.path_for("config"), config)

    service = BenchStoreService(home, repo_root=repo_root)
    packet = service.build_setup_packet(entry_id="runner.label", hardware_payload=_hardware_payload())

    assert packet["assistant_label"] == "BenchStore Setup Agent · Claude"
