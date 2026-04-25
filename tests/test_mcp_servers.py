from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.bash_exec import BashExecService
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.memory import MemoryService
from deepscientist.mcp.context import McpContext
from deepscientist.mcp.server import build_artifact_server, build_bash_exec_server, build_memory_server
from deepscientist.quest import QuestService
from deepscientist.shared import read_json, read_jsonl, write_json, write_yaml
from deepscientist.skills import SkillInstaller


def _unwrap_tool_result(result):
    if isinstance(result, tuple) and len(result) == 2:
        return result[1]
    return result


def _detailed_metric_contract(
    metric_ids: list[str],
    *,
    primary_metric_id: str | None = None,
    directions: dict[str, str] | None = None,
    evaluation_protocol: dict[str, object] | None = None,
) -> dict[str, object]:
    resolved_directions = directions or {}
    payload: dict[str, object] = {
        "primary_metric_id": primary_metric_id or (metric_ids[0] if metric_ids else None),
        "metrics": [
            {
                "metric_id": metric_id,
                "label": metric_id,
                "direction": resolved_directions.get(metric_id, "maximize"),
                "description": f"Canonical metric `{metric_id}`.",
                "derivation": f"Read `{metric_id}` from the canonical evaluation output.",
                "source_ref": "paper table + eval.py",
                "required": True,
            }
            for metric_id in metric_ids
        ],
    }
    if evaluation_protocol:
        payload["evaluation_protocol"] = evaluation_protocol
    return payload


def test_artifact_mcp_server_confirm_baseline_schema_exposes_structured_metric_contract_fields(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp schema quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-schema",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)
        tools = await server.list_tools()
        confirm_tool = next(tool for tool in tools if tool.name == "confirm_baseline")
        schema_text = json.dumps(confirm_tool.inputSchema, ensure_ascii=False)

        assert '"MetricContractPayload"' in schema_text
        assert '"MetricEntryPayload"' in schema_text
        assert '"PrimaryMetricPayload"' in schema_text
        assert '"origin_path"' in schema_text
        assert '"source_ref"' in schema_text
        assert '"derivation"' in schema_text
        assert '"description"' in schema_text

    asyncio.run(scenario())


def _write_fake_bash_session(
    temp_home: Path,
    quest_root: Path,
    bash_id: str,
    *,
    log_lines: list[str],
    status: str = "completed",
) -> None:
    service = BashExecService(temp_home)
    session_dir = service.session_dir(quest_root, bash_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        service.meta_path(quest_root, bash_id),
        {
            "id": bash_id,
            "bash_id": bash_id,
            "quest_id": quest_root.name,
            "status": status,
            "kind": "exec",
            "command": "printf 'fixture\\n'",
            "workdir": "",
            "started_at": "2026-03-20T00:00:00+00:00",
            "finished_at": "2026-03-20T00:00:01+00:00",
            "updated_at": "2026-03-20T00:00:01+00:00",
        },
    )
    terminal_log = service.terminal_log_path(quest_root, bash_id)
    terminal_log.write_text(
        "\n".join(log_lines) + ("\n" if log_lines else ""),
        encoding="utf-8",
    )
    service.log_path(quest_root, bash_id).write_text("", encoding="utf-8")


def test_memory_mcp_server_tools_cover_core_flows(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp memory quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-memory",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_memory_server(context)

        tools = await server.list_tools()
        assert [tool.name for tool in tools] == [
            "write",
            "read",
            "search",
            "list_recent",
            "promote_to_global",
        ]
        tool_map = {tool.name: tool for tool in tools}
        assert tool_map["read"].annotations.readOnlyHint is True
        assert tool_map["search"].annotations.readOnlyHint is True
        assert tool_map["list_recent"].annotations.readOnlyHint is True

        write_result = _unwrap_tool_result(
            await server.call_tool(
                "write",
                {
                    "kind": "knowledge",
                    "title": "MCP Memory Demo",
                    "body": "memory body",
                    "tags": ["mcp"],
                },
            )
        )
        assert write_result["scope"] == "quest"
        assert Path(write_result["path"]).exists()
        assert write_result["metadata"]["tags"] == ["mcp"]

        string_tags_result = _unwrap_tool_result(
            await server.call_tool(
                "write",
                {
                    "kind": "decisions",
                    "title": "String tags coercion",
                    "body": "string tags body",
                    "tags": "stage:baseline, quest:test, type:route-decision",
                },
            )
        )
        assert string_tags_result["metadata"]["tags"] == [
            "stage:baseline",
            "quest:test",
            "type:route-decision",
        ]
        assert Path(string_tags_result["path"]).exists()

        read_result = _unwrap_tool_result(await server.call_tool("read", {"card_id": write_result["id"]}))
        assert read_result["id"] == write_result["id"]
        assert "memory body" in read_result["body"]

        search_result = _unwrap_tool_result(await server.call_tool("search", {"query": "memory", "scope": "quest"}))
        assert search_result["ok"] is True
        assert search_result["count"] >= 1
        assert any(item["id"] == write_result["id"] for item in search_result["items"])

        recent_result = _unwrap_tool_result(await server.call_tool("list_recent", {"scope": "both"}))
        assert recent_result["ok"] is True
        assert recent_result["count"] >= 1

        promote_result = _unwrap_tool_result(await server.call_tool("promote_to_global", {"card_id": write_result["id"]}))
        assert promote_result["scope"] == "global"
        assert Path(promote_result["path"]).exists()

    asyncio.run(scenario())


def test_memory_mcp_server_searches_shared_quest_memory_when_runtime_mode_enabled(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        config_manager = ConfigManager(temp_home)
        config_manager.ensure_files()
        quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
        local_quest = quest_service.create("mcp shared local quest")
        remote_quest = quest_service.create("mcp shared remote quest")
        memory = MemoryService(temp_home)

        memory.write_card(
            scope="quest",
            kind="knowledge",
            title="Remote shared lesson",
            body="cross quest searchable lesson",
            quest_root=Path(remote_quest["quest_root"]),
            quest_id=remote_quest["quest_id"],
        )

        config = config_manager.load_runtime_config()
        config["memory"] = {"read_visibility_mode": "shared_across_quests"}
        config_manager.save_named_payload("config", config)

        context = McpContext(
            home=temp_home,
            quest_id=local_quest["quest_id"],
            quest_root=Path(local_quest["quest_root"]),
            run_id="run-mcp-shared-memory",
            active_anchor="baseline",
            conversation_id="quest:test-shared",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_memory_server(context)

        search_result = _unwrap_tool_result(
            await server.call_tool("search", {"query": "cross quest searchable lesson", "scope": "quest"})
        )
        assert search_result["ok"] is True
        assert search_result["count"] == 1
        assert search_result["items"][0]["document_id"].startswith(f"sharedmemory::{remote_quest['quest_id']}::")
        assert search_result["items"][0]["source_quest_id"] == remote_quest["quest_id"]

        recent_result = _unwrap_tool_result(await server.call_tool("list_recent", {"scope": "quest"}))
        assert recent_result["ok"] is True
        assert any(
            str(item.get("document_id") or "").startswith(f"sharedmemory::{remote_quest['quest_id']}::")
            for item in recent_result["items"]
        )

    asyncio.run(scenario())


def test_artifact_mcp_server_interact_delivers_to_bound_qq_connector(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        manager = ConfigManager(temp_home)
        manager.ensure_files()
        connectors = manager.load_named("connectors")
        connectors["qq"]["enabled"] = True
        connectors["qq"]["profiles"] = [
            {
                "profile_id": "qq-main",
                "app_id": "test-app",
                "app_secret": "test-secret",
                "main_chat_id": "CF8D2D559AA956B48751539ADFB98865",
            }
        ]
        write_yaml(manager.path_for("connectors"), connectors)

        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp artifact qq quest")
        quest_root = Path(quest["quest_root"])
        conversation_id = "qq:direct:CF8D2D559AA956B48751539ADFB98865"
        (quest_root / ".ds" / "bindings.json").write_text(
            json.dumps({"sources": ["local:default", conversation_id]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        connector_root = temp_home / "logs" / "connectors" / "qq"
        connector_root.mkdir(parents=True, exist_ok=True)
        (connector_root / "bindings.json").write_text(
            json.dumps(
                {
                    "bindings": {
                        conversation_id: {
                            "quest_id": quest["quest_id"],
                            "updated_at": "2026-03-14T09:10:33+00:00",
                        }
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        deliveries: list[dict] = []

        def fake_deliver(self, payload, config):  # noqa: ANN001
            deliveries.append({"payload": dict(payload), "config": dict(config or {})})
            return {"ok": True, "transport": "qq-http"}

        monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_deliver)

        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-artifact-qq",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        interact_result = _unwrap_tool_result(
            await server.call_tool(
                "interact",
                {
                    "kind": "progress",
                    "message": "mcp artifact qq delivery ok",
                    "deliver_to_bound_conversations": True,
                    "include_recent_inbound_messages": False,
                },
            )
        )

        assert interact_result["status"] == "ok"
        assert interact_result["delivered"] is True
        assert conversation_id in interact_result["delivery_targets"]
        assert "local:default" in interact_result["delivery_targets"]
        assert len(deliveries) == 1
        assert deliveries[0]["payload"]["conversation_id"] == conversation_id
        assert deliveries[0]["payload"]["text"] == "mcp artifact qq delivery ok"
        outbox = read_jsonl(connector_root / "outbox.jsonl")
        assert outbox
        assert outbox[-1]["conversation_id"] == conversation_id
        assert outbox[-1]["delivery"]["ok"] is True

    asyncio.run(scenario())


def test_artifact_mcp_server_tools_cover_core_flows(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp artifact quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-artifact",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        tools = await server.list_tools()
        assert [tool.name for tool in tools] == [
            "record",
            "checkpoint",
            "git",
            "prepare_branch",
            "activate_branch",
            "submit_idea",
            "list_research_branches",
            "resolve_runtime_refs",
            "get_paper_contract",
            "get_paper_contract_health",
            "validate_manuscript_coverage",
            "get_quest_state",
            "get_global_status",
            "get_research_map_status",
            "get_benchstore_catalog",
            "get_start_setup_context",
            "get_method_scoreboard",
            "get_optimization_frontier",
            "read_quest_documents",
            "get_conversation_context",
            "get_analysis_campaign",
            "record_main_experiment",
            "create_analysis_campaign",
            "submit_paper_outline",
            "list_paper_outlines",
            "submit_paper_bundle",
            "record_analysis_slice",
            "publish_baseline",
            "attach_baseline",
            "confirm_baseline",
            "overwrite_baseline",
            "waive_baseline",
            "arxiv",
            "refresh_summary",
            "render_git_graph",
            "interact",
            "complete_quest",
        ]
        tool_map = {tool.name: tool for tool in tools}
        assert tool_map["get_quest_state"].annotations.readOnlyHint is True
        assert tool_map["read_quest_documents"].annotations.readOnlyHint is True
        assert tool_map["get_conversation_context"].annotations.readOnlyHint is True
        assert tool_map["get_research_map_status"].annotations.readOnlyHint is True

        research_map_result = _unwrap_tool_result(
            await server.call_tool(
                "get_research_map_status",
                {
                    "detail": "summary",
                    "locale": "en",
                },
            )
        )
        assert research_map_result["ok"] is True
        assert research_map_result["detail"] == "summary"
        snapshot = research_map_result["research_map_status"]
        assert "canvas_summary" in snapshot
        assert "runtime_refs" in snapshot
        assert "activation_refs" in snapshot
        assert "recommended_activation_ref" in snapshot
        assert "node_history" in snapshot
        assert "usage_notes" in snapshot
        assert "git" in snapshot
        assert snapshot["git"]["head_commit"]

        record_result = _unwrap_tool_result(
            await server.call_tool(
                "record",
                {
                    "payload": {
                        "kind": "report",
                        "status": "completed",
                        "report_type": "mcp-test",
                        "summary": "artifact record ok",
                    }
                },
            )
        )
        assert record_result["ok"] is True
        assert record_result["record"]["source"]["role"] == "pi"
        assert record_result["record"]["run_id"] == "run-mcp-artifact"
        assert Path(record_result["path"]).exists()

        checkpoint_result = _unwrap_tool_result(
            await server.call_tool(
                "checkpoint",
                {
                    "message": "mcp artifact checkpoint",
                    "allow_empty": True,
                },
            )
        )
        assert checkpoint_result["ok"] is True
        assert "head" in checkpoint_result

        git_status = _unwrap_tool_result(await server.call_tool("git", {"action": "status"}))
        assert git_status["ok"] is True
        assert git_status["action"] == "status"
        assert git_status["result"]["repo"] == str(quest_root)

        git_commit = _unwrap_tool_result(
            await server.call_tool(
                "git",
                {
                    "action": "commit",
                    "message": "mcp git checkpoint",
                    "allow_empty": True,
                },
            )
        )
        assert git_commit["ok"] is True
        assert git_commit["action"] == "commit"
        assert git_commit["result"]["committed"] is True
        assert git_commit["result"]["subject"] == "mcp git checkpoint"

        branch_result = _unwrap_tool_result(
            await server.call_tool(
                "prepare_branch",
                {
                    "run_id": "run-branch-001",
                    "branch_kind": "run",
                    "create_worktree_flag": False,
                },
            )
        )
        assert branch_result["ok"] is True
        assert branch_result["branch"].startswith("run/")

        publish_result = _unwrap_tool_result(
            await server.call_tool(
                "publish_baseline",
                {
                    "payload": {
                        "baseline_id": "mcp-baseline",
                        "name": "MCP Baseline",
                        "summary": "published from mcp server test",
                        "primary_metric": {"name": "accuracy", "value": 0.9},
                        "metrics_summary": {"accuracy": 0.9},
                        "metric_contract": _detailed_metric_contract(
                            ["accuracy"],
                            primary_metric_id="accuracy",
                            evaluation_protocol={
                                "scope_id": "full",
                                "code_paths": ["eval.py"],
                            },
                        ),
                        "baseline_variants": [{"variant_id": "main", "label": "Main"}],
                        "default_variant_id": "main",
                    }
                },
            )
        )
        assert publish_result["ok"] is True
        assert publish_result["baseline_registry_entry"]["baseline_id"] == "mcp-baseline"
        baseline_root = quest_root / "baselines" / "local" / "mcp-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# MCP Baseline\n", encoding="utf-8")

        attach_result = _unwrap_tool_result(
            await server.call_tool(
                "attach_baseline",
                {
                    "baseline_id": "mcp-baseline",
                    "variant_id": "main",
                },
            )
        )
        assert attach_result["ok"] is True
        assert attach_result["attachment"]["source_variant_id"] == "main"

        confirm_result = _unwrap_tool_result(
            await server.call_tool(
                "confirm_baseline",
                {
                    "baseline_path": "baselines/imported/mcp-baseline",
                    "baseline_id": "mcp-baseline",
                    "variant_id": "main",
                    "summary": "MCP baseline confirmed",
                },
            )
        )
        assert confirm_result["ok"] is True
        assert confirm_result["baseline_gate"] == "confirmed"
        assert confirm_result["confirmed_baseline_ref"]["baseline_id"] == "mcp-baseline"

        idea_result = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "lineage_intent": "continue_line",
                    "title": "Adapter route",
                    "problem": "Baseline saturates.",
                    "hypothesis": "A lightweight adapter helps.",
                    "mechanism": "Insert a residual adapter.",
                    "decision_reason": "Promote the strongest current idea.",
                    "draft_markdown": "# Adapter route draft\n\n## Code-Level Change Plan\n\nInsert a residual adapter.\n",
                },
            )
        )
        assert idea_result["ok"] is True
        assert idea_result["branch"].startswith(f"idea/{quest['quest_id']}-")
        assert idea_result["lineage_intent"] == "continue_line"
        assert Path(idea_result["worktree_root"]).exists()
        assert Path(idea_result["idea_draft_path"]).exists()

        main_result = _unwrap_tool_result(
            await server.call_tool(
                "record_main_experiment",
                {
                    "run_id": "main-mcp-001",
                    "title": "Main MCP run",
                    "hypothesis": "Adapter improves accuracy.",
                    "setup": "Use baseline recipe.",
                    "execution": "Ran full validation.",
                    "results": "Accuracy improved.",
                    "conclusion": "Ready for follow-up.",
                    "metric_rows": [{"metric_id": "accuracy", "value": 0.93}],
                    "evaluation_summary": {
                        "takeaway": "The MCP run clears the accepted baseline.",
                        "claim_update": "strengthens",
                        "baseline_relation": "better",
                        "comparability": "high",
                        "failure_mode": "none",
                        "next_action": "analysis_campaign",
                    },
                },
            )
        )
        assert main_result["ok"] is True
        assert Path(main_result["result_json_path"]).exists()
        assert main_result["progress_eval"]["breakthrough"] is True
        assert main_result["evaluation_summary"]["next_action"] == "analysis_campaign"

        refs_after_main = _unwrap_tool_result(await server.call_tool("resolve_runtime_refs", {}))
        assert refs_after_main["latest_main_run_id"] == "main-mcp-001"
        assert refs_after_main["active_idea_id"] == idea_result["idea_id"]
        quest_state_summary = _unwrap_tool_result(await server.call_tool("get_quest_state", {"detail": "summary"}))
        assert quest_state_summary["ok"] is True
        assert quest_state_summary["quest_state"]["active_idea_id"] == idea_result["idea_id"]
        docs_excerpt = _unwrap_tool_result(
            await server.call_tool(
                "read_quest_documents",
                {"names": ["brief", "status"], "mode": "excerpt"},
            )
        )
        assert docs_excerpt["ok"] is True
        assert docs_excerpt["count"] == 2
        convo_context = _unwrap_tool_result(await server.call_tool("get_conversation_context", {"limit": 5}))
        assert convo_context["ok"] is True
        assert convo_context["count"] >= 0

        branches_after_run = _unwrap_tool_result(await server.call_tool("list_research_branches", {}))
        assert branches_after_run["ok"] is True
        assert branches_after_run["count"] == 2
        by_branch_after_run = {item["branch_name"]: item for item in branches_after_run["branches"]}
        assert by_branch_after_run[idea_result["branch"]]["branch_no"] == "001"
        assert by_branch_after_run["run/main-mcp-001"]["latest_main_experiment"]["run_id"] == "main-mcp-001"
        assert by_branch_after_run["run/main-mcp-001"]["has_main_result"] is True

        second_idea_result = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "lineage_intent": "continue_line",
                    "title": "Run-informed route",
                    "problem": "Need a follow-up route grounded in the measured win.",
                    "hypothesis": "The best measured branch is the right foundation.",
                    "mechanism": "Extend the winning adapter logic into a new branch.",
                    "decision_reason": "Use the best measured main run as the next foundation.",
                    "foundation_ref": {"kind": "run", "ref": "main-mcp-001"},
                    "foundation_reason": "Carry forward the strongest measured branch.",
                },
            )
        )
        assert second_idea_result["ok"] is True
        assert second_idea_result["branch_no"] == "002"
        assert second_idea_result["lineage_intent"] == "continue_line"
        assert second_idea_result["foundation_ref"]["kind"] == "run"
        assert second_idea_result["foundation_ref"]["ref"] == "main-mcp-001"
        assert Path(second_idea_result["worktree_root"]).exists()

        branches_after_second_idea = _unwrap_tool_result(await server.call_tool("list_research_branches", {}))
        assert branches_after_second_idea["ok"] is True
        assert branches_after_second_idea["count"] == 3
        by_branch = {item["branch_name"]: item for item in branches_after_second_idea["branches"]}
        assert by_branch[idea_result["branch"]]["branch_no"] == "001"
        assert by_branch[second_idea_result["branch"]]["branch_no"] == "002"
        assert by_branch["run/main-mcp-001"]["latest_main_experiment"]["run_id"] == "main-mcp-001"
        assert by_branch[second_idea_result["branch"]]["foundation_ref"]["kind"] == "run"
        assert by_branch[second_idea_result["branch"]]["foundation_reason"] == "Carry forward the strongest measured branch."

        activated = _unwrap_tool_result(
            await server.call_tool(
                "activate_branch",
                {
                    "branch": idea_result["branch"],
                },
            )
        )
        assert activated["ok"] is True
        assert activated["branch"] == idea_result["branch"]
        assert activated["idea_id"] == idea_result["idea_id"]
        assert activated["next_anchor"] == "decision"

        refs_after_activate = _unwrap_tool_result(await server.call_tool("resolve_runtime_refs", {}))
        assert refs_after_activate["current_workspace_branch"] == idea_result["branch"]
        assert refs_after_activate["research_head_branch"] == second_idea_result["branch"]

        outlines_before = _unwrap_tool_result(await server.call_tool("list_paper_outlines", {}))
        assert outlines_before["selected_outline_ref"] is None
        assert outlines_before["count"] == 0
        paper_health_before = _unwrap_tool_result(
            await server.call_tool("get_paper_contract_health", {"detail": "summary"})
        )
        assert paper_health_before["ok"] is False

        campaign_result = _unwrap_tool_result(
            await server.call_tool(
                "create_analysis_campaign",
                {
                    "campaign_title": "Ablation suite",
                    "campaign_goal": "Stress-test the promoted idea.",
                    "slices": [
                        {
                            "slice_id": "ablation",
                            "title": "Adapter ablation",
                            "goal": "Disable the adapter and compare.",
                            "required_changes": "Disable adapter only.",
                            "metric_contract": "Report full validation metrics.",
                            "required_baselines": [
                                {
                                    "baseline_id": "mcp-analysis-baseline",
                                    "reason": "Need a dedicated analysis comparator.",
                                }
                            ],
                        }
                    ],
                },
            )
        )
        assert campaign_result["ok"] is True
        assert campaign_result["campaign_id"]
        assert campaign_result["parent_branch"] == "run/main-mcp-001"
        assert Path(campaign_result["slices"][0]["worktree_root"]).exists()
        assert campaign_result["slices"][0]["required_baselines"][0]["baseline_id"] == "mcp-analysis-baseline"
        analysis_baseline_root = quest_root / "baselines" / "local" / "mcp-analysis-baseline"
        analysis_baseline_root.mkdir(parents=True, exist_ok=True)
        (analysis_baseline_root / "README.md").write_text("# MCP Analysis Baseline\n", encoding="utf-8")

        campaign_view = _unwrap_tool_result(
            await server.call_tool(
                "get_analysis_campaign",
                {
                    "campaign_id": "active",
                },
            )
        )
        assert campaign_view["campaign_id"] == campaign_result["campaign_id"]
        assert campaign_view["next_pending_slice_id"] == "ablation"

        slice_result = _unwrap_tool_result(
            await server.call_tool(
                "record_analysis_slice",
                {
                    "campaign_id": campaign_result["campaign_id"],
                    "slice_id": "ablation",
                    "setup": "Disable the adapter only.",
                    "execution": "Ran the full validation sweep.",
                    "results": "Accuracy dropped as expected.",
                    "metric_rows": [{"name": "acc", "value": 0.84}],
                    "evidence_paths": ["experiments/analysis/ablation/result.json"],
                    "comparison_baselines": [
                        {
                            "baseline_id": "mcp-analysis-baseline",
                            "baseline_root_rel_path": "baselines/local/mcp-analysis-baseline",
                            "metrics_summary": {"acc": 0.8},
                        }
                    ],
                    "evaluation_summary": {
                        "takeaway": "Removing the adapter weakens the result as expected.",
                        "claim_update": "strengthens",
                        "baseline_relation": "better",
                        "comparability": "high",
                        "failure_mode": "none",
                        "next_action": "write",
                    },
                },
            )
        )
        assert slice_result["ok"] is True
        assert slice_result["completed"] is True
        assert slice_result["returned_to_branch"] == campaign_result["parent_branch"]
        assert Path(slice_result["result_json_path"]).exists()
        assert slice_result["evaluation_summary"]["takeaway"].startswith("Removing the adapter")

        summary_result = _unwrap_tool_result(await server.call_tool("refresh_summary", {"reason": "mcp test"}))
        assert summary_result["ok"] is True
        assert Path(summary_result["summary_path"]).exists()

        graph_result = _unwrap_tool_result(await server.call_tool("render_git_graph", {}))
        assert graph_result["ok"] is True
        assert Path(graph_result["graph"]["json_path"]).exists()

        interact_result = _unwrap_tool_result(
            await server.call_tool(
                "interact",
                {
                    "kind": "progress",
                    "message": "mcp interact ok",
                    "deliver_to_bound_conversations": False,
                },
            )
        )
        assert interact_result["status"] == "ok"
        assert interact_result["delivered"] is False

        completion_request = _unwrap_tool_result(
            await server.call_tool(
                "interact",
                {
                    "kind": "decision_request",
                    "message": "May I end this quest now?",
                    "deliver_to_bound_conversations": False,
                    "include_recent_inbound_messages": False,
                    "reply_mode": "blocking",
                    "reply_schema": {"decision_type": "quest_completion_approval"},
                },
            )
        )
        QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).append_message(
            quest["quest_id"],
            role="user",
            content="approve",
            source="tui-ink",
            reply_to_interaction_id=completion_request["interaction_id"],
        )
        completion_result = _unwrap_tool_result(
            await server.call_tool(
                "complete_quest",
                {
                    "summary": "Quest complete after MCP verification.",
                },
            )
        )
        assert completion_result["ok"] is True
        assert completion_result["snapshot"]["status"] == "completed"

    asyncio.run(scenario())


def test_artifact_overwrite_baseline_tool_refreshes_confirmed_ref(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp overwrite baseline quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-overwrite-baseline",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        artifact = ArtifactService(temp_home)
        baseline_root = quest_root / "baselines" / "local" / "mcp-overwrite-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# MCP Overwrite Baseline\n", encoding="utf-8")
        artifact.confirm_baseline(
            quest_root,
            baseline_path=str(baseline_root),
            baseline_id="mcp-overwrite-baseline",
            summary="Initial MCP overwrite baseline",
            metrics_summary={"acc": 0.8},
            primary_metric={"metric_id": "acc", "value": 0.8},
            metric_contract=_detailed_metric_contract(["acc"]),
            strict_metric_contract=True,
        )

        overwritten = _unwrap_tool_result(
            await server.call_tool(
                "overwrite_baseline",
                {
                    "baseline_id": "mcp-overwrite-baseline",
                    "baseline_path": "baselines/local/mcp-overwrite-baseline",
                    "change_summary": "Add a canonical f1 metric after the second baseline pass.",
                    "metrics_summary": {"acc": 0.82, "f1": 0.79},
                    "primary_metric": {"metric_id": "acc", "value": 0.82},
                    "metric_contract": _detailed_metric_contract(["acc", "f1"]),
                },
            )
        )

        assert overwritten["ok"] is True
        assert overwritten["compatibility_verdict"] == "metrics_only_safe"
        confirmed_ref = overwritten["confirmed_baseline_ref"]
        assert confirmed_ref["baseline_id"] == "mcp-overwrite-baseline"
        assert confirmed_ref["overwrite"]["change_summary"] == "Add a canonical f1 metric after the second baseline pass."
        metric_contract_payload = read_json(Path(overwritten["metric_contract_json_path"]), {})
        assert metric_contract_payload["overwrite"]["compatibility_verdict"] == "metrics_only_safe"

    asyncio.run(scenario())


def test_artifact_mcp_create_analysis_campaign_returns_guided_fix_steps_for_missing_outline(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp missing outline guidance quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-missing-outline-guidance",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)
        artifact = ArtifactService(temp_home)

        baseline_root = quest_root / "baselines" / "local" / "mcp-outline-gate"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# MCP outline gate baseline\n", encoding="utf-8")
        artifact.confirm_baseline(
            quest_root,
            baseline_path=str(baseline_root),
            baseline_id="mcp-outline-gate",
            summary="Outline gate baseline",
            metrics_summary={"acc": 0.8},
            primary_metric={"metric_id": "acc", "value": 0.8},
            metric_contract=_detailed_metric_contract(["acc"], primary_metric_id="acc"),
        )
        artifact.submit_idea(
            quest_root,
            mode="create",
            title="Need writing-facing analysis",
            problem="The analysis campaign should guide the next fix when no outline is selected.",
            hypothesis="Returning guidance is better than a bare exception.",
            mechanism="Attach concrete next actions to the MCP error payload.",
            decision_reason="Prepare the route before writing-facing analysis.",
        )
        artifact.submit_paper_outline(
            quest_root,
            mode="candidate",
            title="Candidate outline only",
            detailed_outline={"title": "Candidate outline only"},
        )

        result = _unwrap_tool_result(
            await server.call_tool(
                "create_analysis_campaign",
                {
                    "campaign_title": "Missing outline guidance",
                    "campaign_goal": "This should fail with explicit next steps.",
                    "research_questions": ["RQ-main"],
                    "experimental_designs": ["ED-main"],
                    "todo_items": [
                        {
                            "todo_id": "todo-001",
                            "slice_id": "slice-001",
                            "title": "Slice 001",
                            "research_question": "RQ-main",
                            "experimental_design": "ED-main",
                            "completion_condition": "Complete one slice.",
                        }
                    ],
                    "slices": [
                        {
                            "slice_id": "slice-001",
                            "title": "Slice 001",
                            "goal": "Run one writing-facing slice.",
                        }
                    ],
                },
            )
        )

        assert result["ok"] is False
        assert "selected_outline_ref" in result["message"]
        assert "submit_paper_outline" in "\n".join(result["guidance"])
        assert "analysis-lite" in "\n".join(result["guidance"])
        assert result["outline_candidates"]
        assert any(item["name"].startswith("artifact.submit_paper_outline") for item in result["suggested_artifact_calls"])

    asyncio.run(scenario())


def test_artifact_prepare_github_issue_tool_returns_route_effect(
    temp_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp issue draft quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-issue-draft",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
            custom_profile="settings_issue",
        )
        server = build_artifact_server(context)

        monkeypatch.setattr(
            "deepscientist.mcp.server._prepare_github_issue_payload_via_daemon",
            lambda home, **kwargs: {
                "ok": True,
                "title": "GPU scheduling issue on local daemon",
                "body_markdown": "# Summary\n\nGPU scheduling issue on local daemon\n",
                "issue_url_base": "https://github.com/ResearAI/DeepScientist/issues/new",
                "repo_url": "https://github.com/ResearAI/DeepScientist",
                "generated_at": "2026-04-14T00:00:00+00:00",
            },
        )

        result = _unwrap_tool_result(
            await server.call_tool(
                "prepare_github_issue",
                {
                    "summary": "GPU scheduling issue on local daemon",
                    "user_notes": "Generated from MCP test.",
                },
            )
        )

        assert result["ok"] is True
        assert result["title"] == "GPU scheduling issue on local daemon"
        assert result["ui_effects"][0]["name"] == "route:navigate"
        assert result["ui_effects"][0]["data"]["to"] == "/settings/issues"
        assert result["ui_effects"][0]["data"]["issueDraft"]["title"] == result["title"]

    asyncio.run(scenario())


def test_settings_issue_profile_artifact_server_exposes_only_issue_tool(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("settings issue profile quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-settings-issue",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
            custom_profile="settings_issue",
        )
        server = build_artifact_server(context)
        tools = await server.list_tools()
        assert [tool.name for tool in tools] == ["prepare_github_issue"]

    asyncio.run(scenario())


def test_start_setup_prepare_profile_artifact_server_exposes_only_prepare_form_tool(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("start setup prepare profile quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-start-setup-prepare",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
            custom_profile="start_setup_prepare",
        )
        server = build_artifact_server(context)
        tools = await server.list_tools()
        assert [tool.name for tool in tools] == ["prepare_start_setup_form"]

        result = _unwrap_tool_result(
            await server.call_tool(
                "prepare_start_setup_form",
                {
                    "form_patch": {
                        "title": "Bench Demo Autonomous Research",
                        "goal": "Run the benchmark faithfully.",
                        "need_research_paper": True,
                    },
                    "session_patch": {
                        "recommended_workspace_mode": "copilot",
                        "launch_readiness": "needs_confirmation",
                        "missing_confirmations": ["Clarify whether paid APIs are allowed."],
                        "fit_assessment": {
                            "verdict": "copilot_recommended",
                            "summary": "Human collaboration is still needed before an autonomous launch is safe.",
                        },
                    },
                    "message": "Prepared the launch form.",
                },
            )
        )
        assert result["ok"] is True
        assert result["form_patch"]["title"] == "Bench Demo Autonomous Research"
        assert result["suggested_form"]["title"] == "Bench Demo Autonomous Research"
        assert result["ui_effects"][0]["name"] == "start_setup:patch"
        assert result["ui_effects"][0]["data"]["patch"]["goal"] == "Run the benchmark faithfully."
        assert result["session_patch"]["recommended_workspace_mode"] == "copilot"
        persisted = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).read_quest_yaml(quest_root)
        startup_contract = persisted.get("startup_contract") if isinstance(persisted.get("startup_contract"), dict) else {}
        start_setup_session = (
            startup_contract.get("start_setup_session")
            if isinstance(startup_contract, dict) and isinstance(startup_contract.get("start_setup_session"), dict)
            else {}
        )
        suggested_form = start_setup_session.get("suggested_form") if isinstance(start_setup_session, dict) else {}
        assert suggested_form["title"] == "Bench Demo Autonomous Research"
        assert suggested_form["goal"] == "Run the benchmark faithfully."
        assert suggested_form["need_research_paper"] is True
        assert start_setup_session["recommended_workspace_mode"] == "copilot"
        assert start_setup_session["fit_assessment"]["verdict"] == "copilot_recommended"

    asyncio.run(scenario())


def test_artifact_mcp_copilot_workspace_keeps_branch_graph_visible(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp copilot graph quest",
            startup_contract={"workspace_mode": "copilot"},
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-copilot-graph",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        artifact = ArtifactService(temp_home)
        baseline_root = quest_root / "baselines" / "local" / "copilot-mcp-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# Copilot MCP Baseline\n", encoding="utf-8")
        artifact.confirm_baseline(
            quest_root,
            baseline_path=str(baseline_root),
            baseline_id="copilot-mcp-baseline",
            summary="Confirmed copilot baseline",
            metrics_summary={"acc": 0.8},
            primary_metric={"name": "acc", "value": 0.8},
            metric_contract={
                "primary_metric_id": "acc",
                "metrics": [{"metric_id": "acc", "direction": "higher"}],
            },
        )

        first_idea = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "lineage_intent": "continue_line",
                    "title": "Copilot route",
                    "problem": "Copilot mode should still generate a real branch graph.",
                    "hypothesis": "The branch graph should not collapse into a commit list.",
                    "mechanism": "Open a durable idea branch from copilot mode.",
                    "decision_reason": "Start the first branch in copilot mode.",
                },
            )
        )
        assert first_idea["ok"] is True

        main_run = _unwrap_tool_result(
            await server.call_tool(
                "record_main_experiment",
                {
                    "run_id": "main-copilot-mcp-001",
                    "title": "Copilot MCP main run",
                    "hypothesis": "The copilot route improves the metric.",
                    "setup": "Use the confirmed baseline recipe.",
                    "execution": "Ran the comparable main validation pass.",
                    "results": "The copilot route improved accuracy.",
                    "conclusion": "Use the measured result as the next branch foundation.",
                    "metric_rows": [{"metric_id": "acc", "value": 0.91}],
                },
            )
        )
        assert main_run["ok"] is True

        second_idea = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "lineage_intent": "continue_line",
                    "title": "Run-informed copilot route",
                    "problem": "Need a follow-up route from the measured run.",
                    "hypothesis": "The best measured run is the right foundation.",
                    "mechanism": "Continue from the strongest measured branch.",
                    "decision_reason": "Branch from the main measured run.",
                    "foundation_ref": {"kind": "run", "ref": "main-copilot-mcp-001"},
                    "foundation_reason": "Carry forward the strongest measured branch.",
                },
            )
        )
        assert second_idea["ok"] is True

        activated = _unwrap_tool_result(
            await server.call_tool(
                "activate_branch",
                {
                    "branch": first_idea["branch"],
                },
            )
        )
        assert activated["ok"] is True

        branches_after = _unwrap_tool_result(await server.call_tool("list_research_branches", {}))
        assert branches_after["ok"] is True
        by_branch = {item["branch_name"]: item for item in branches_after["branches"]}
        assert by_branch[first_idea["branch"]]["branch_no"] == "001"
        assert by_branch["run/main-copilot-mcp-001"]["latest_main_experiment"]["run_id"] == "main-copilot-mcp-001"
        assert by_branch[second_idea["branch"]]["branch_no"] == "002"
        assert by_branch[second_idea["branch"]]["foundation_reason"] == "Carry forward the strongest measured branch."

        refs = _unwrap_tool_result(await server.call_tool("resolve_runtime_refs", {}))
        assert refs["current_workspace_branch"] == first_idea["branch"]

        app = DaemonApp(temp_home)
        graph_payload = app.handlers.git_branches(quest["quest_id"])
        nodes = {item["ref"]: item for item in graph_payload["nodes"]}
        assert graph_payload["workspace_mode"] == "copilot"
        assert any(
            edge["from"] == "run/main-copilot-mcp-001" and edge["to"] == second_idea["branch"]
            for edge in graph_payload["edges"]
        )
        assert nodes[second_idea["branch"]]["foundation_reason"] == "Carry forward the strongest measured branch."

    asyncio.run(scenario())


def test_artifact_mcp_submit_idea_supports_candidate_submission_mode(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp candidate idea quest")
        quest_root = Path(quest["quest_root"])
        server = build_artifact_server(
            McpContext(
                home=temp_home,
                quest_id=quest["quest_id"],
                quest_root=quest_root,
                run_id="run-mcp-candidate",
                active_anchor="baseline",
                conversation_id="quest:test",
                agent_role="baseline",
                worker_id="worker-main",
                worktree_root=None,
                team_mode="single",
            )
        )
        artifact = ArtifactService(temp_home)
        baseline_root = quest_root / "baselines" / "local" / "mcp-candidate-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        write_json(
            baseline_root / "RESULT.json",
            {
                "metrics_summary": {"accuracy": 0.81},
                "metric_contract": _detailed_metric_contract(["accuracy"]),
                "primary_metric": {"metric_id": "accuracy", "value": 0.81, "direction": "maximize"},
            },
        )
        artifact.confirm_baseline(
            quest_root,
            baseline_path="baselines/local/mcp-candidate-baseline",
            baseline_id="mcp-candidate-baseline",
            summary="Candidate-mode baseline",
        )

        candidate = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "submission_mode": "candidate",
                    "title": "Candidate route",
                    "problem": "Need a lightweight candidate before promotion.",
                    "hypothesis": "A candidate adapter may improve the tail.",
                    "mechanism": "Try a narrow adapter before the head.",
                    "method_brief": "Keep the route branchless until ranking is done.",
                    "selection_scores": {"utility": 0.8, "distinctness": 0.64},
                    "mechanism_family": "adapter",
                    "change_layer": "Tier2",
                    "source_lens": "baseline_refinement",
                    "decision_reason": "Record the candidate first.",
                    "next_target": "optimize",
                },
            )
        )
        assert candidate["ok"] is True
        assert candidate["submission_mode"] == "candidate"
        assert candidate["method_brief"] == "Keep the route branchless until ranking is done."
        assert candidate["selection_scores"] == {"utility": 0.8, "distinctness": 0.64}
        assert candidate["mechanism_family"] == "adapter"
        assert candidate["change_layer"] == "Tier2"
        assert candidate["source_lens"] == "baseline_refinement"
        assert "branch" not in candidate
        assert Path(candidate["candidate_root"]).exists()

        promoted = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "submission_mode": "line",
                    "source_candidate_id": candidate["idea_id"],
                    "title": "Promoted route",
                    "problem": "Promote the candidate into a durable line.",
                    "hypothesis": "The candidate is strong enough for a real branch.",
                    "mechanism": "Carry the candidate plan into a branch-backed line.",
                    "method_brief": "Promote the branchless route into a durable optimization line.",
                    "selection_scores": {"utility": 0.88, "distinctness": 0.59},
                    "mechanism_family": "adapter",
                    "change_layer": "Tier2",
                    "source_lens": "baseline_refinement",
                    "decision_reason": "Promote the candidate into the active optimization line.",
                    "next_target": "optimize",
                },
            )
        )
        assert promoted["ok"] is True
        assert promoted["submission_mode"] == "line"
        assert promoted["source_candidate_id"] == candidate["idea_id"]
        assert promoted["method_brief"] == "Promote the branchless route into a durable optimization line."
        assert promoted["selection_scores"] == {"utility": 0.88, "distinctness": 0.59}
        assert promoted["mechanism_family"] == "adapter"
        assert promoted["change_layer"] == "Tier2"
        assert promoted["source_lens"] == "baseline_refinement"
        assert Path(promoted["worktree_root"]).exists()

    asyncio.run(scenario())


def test_artifact_mcp_get_optimization_frontier_returns_candidate_and_line_state(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp frontier quest",
            startup_contract={"need_research_paper": False},
        )
        quest_root = Path(quest["quest_root"])
        artifact = ArtifactService(temp_home)
        baseline_root = quest_root / "baselines" / "local" / "mcp-frontier-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        write_json(
            baseline_root / "RESULT.json",
            {
                "metrics_summary": {"accuracy": 0.81},
                "metric_contract": _detailed_metric_contract(["accuracy"]),
                "primary_metric": {"metric_id": "accuracy", "value": 0.81, "direction": "maximize"},
            },
        )
        artifact.confirm_baseline(
            quest_root,
            baseline_path="baselines/local/mcp-frontier-baseline",
            baseline_id="mcp-frontier-baseline",
            summary="Frontier baseline",
        )

        candidate = artifact.submit_idea(
            quest_root,
            mode="create",
            submission_mode="candidate",
            title="Frontier candidate",
            problem="Keep a branchless candidate in the pool.",
            hypothesis="A branchless brief may still be worth later promotion.",
            mechanism="Delay branch creation until ranking is finished.",
            method_brief="Preserve the direction as a method brief before promotion.",
            selection_scores={"utility": 0.71, "distinctness": 0.66},
            mechanism_family="ranking_gate",
            change_layer="Tier1",
            source_lens="search_widening",
            decision_reason="Record the candidate first.",
            next_target="optimize",
        )
        line = artifact.submit_idea(
            quest_root,
            mode="create",
            submission_mode="line",
            title="Frontier line",
            problem="Promote the strongest current line.",
            hypothesis="A durable line should now be optimized.",
            mechanism="Use a residual adapter.",
            decision_reason="Open the current incumbent line.",
            next_target="optimize",
        )
        artifact.record_main_experiment(
            quest_root,
            run_id="main-mcp-frontier-001",
            title="Frontier main run",
            hypothesis="The frontier line helps.",
            setup="Use baseline recipe.",
            execution="Ran validation.",
            results="Accuracy improved.",
            conclusion="Use this line as the current incumbent.",
            metric_rows=[{"metric_id": "accuracy", "value": 0.9}],
        )
        artifact.record(
            quest_root,
            {
                "kind": "report",
                "status": "proposed",
                "report_type": "optimization_candidate",
                "candidate_id": "cand-mcp-frontier-001",
                "idea_id": line["idea_id"],
                "branch": line["branch"],
                "strategy": "exploit",
                "summary": "Queued candidate for smoke.",
                "details": {"candidate_id": "cand-mcp-frontier-001"},
            },
            workspace_root=Path(line["worktree_root"]),
        )

        server = build_artifact_server(
            McpContext(
                home=temp_home,
                quest_id=quest["quest_id"],
                quest_root=quest_root,
                run_id="run-mcp-frontier",
                active_anchor="optimize",
                conversation_id="quest:test",
                agent_role="optimize",
                worker_id="worker-main",
                worktree_root=None,
                team_mode="single",
            )
        )

        frontier = _unwrap_tool_result(await server.call_tool("get_optimization_frontier", {}))
        assert frontier["ok"] is True
        payload = frontier["optimization_frontier"]
        assert payload["mode"] == "exploit"
        assert payload["candidate_backlog"]["candidate_brief_count"] == 1
        assert payload["candidate_briefs"][0]["idea_id"] == candidate["idea_id"]
        assert payload["candidate_briefs"][0]["method_brief"] == "Preserve the direction as a method brief before promotion."
        assert payload["candidate_briefs"][0]["selection_scores"] == {"utility": 0.71, "distinctness": 0.66}
        assert payload["candidate_briefs"][0]["mechanism_family"] == "ranking_gate"
        assert payload["candidate_briefs"][0]["change_layer"] == "Tier1"
        assert payload["candidate_briefs"][0]["source_lens"] == "search_widening"
        assert payload["best_run"]["run_id"] == "main-mcp-frontier-001"
        assert payload["implementation_candidates"][0]["candidate_id"] == "cand-mcp-frontier-001"

    asyncio.run(scenario())


def test_artifact_mcp_server_returns_structured_metric_contract_failures(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp metric validation quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-metrics",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        baseline_root = quest_root / "baselines" / "local" / "mcp-local-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# MCP Local Baseline\n", encoding="utf-8")

        baseline_failure = _unwrap_tool_result(
            await server.call_tool(
                "confirm_baseline",
                {
                    "baseline_path": "baselines/local/mcp-local-baseline",
                    "baseline_id": "mcp-local-baseline",
                    "summary": "Missing metric explanations should fail.",
                    "metrics_summary": {"acc": 0.9},
                    "primary_metric": {"metric_id": "acc", "value": 0.9},
                    "metric_contract": {
                        "primary_metric_id": "acc",
                        "metrics": [{"metric_id": "acc", "direction": "maximize"}],
                    },
                },
            )
        )
        assert baseline_failure["ok"] is False
        assert baseline_failure["error_code"] == "baseline_metric_explanations_missing"
        assert baseline_failure["validation_stage"] == "baseline"
        assert baseline_failure["baseline_metric_details"][0]["metric_id"] == "acc"

        baseline_success = _unwrap_tool_result(
            await server.call_tool(
                "confirm_baseline",
                {
                    "baseline_path": "baselines/local/mcp-local-baseline",
                    "baseline_id": "mcp-local-baseline",
                    "summary": "Strict baseline should now succeed.",
                    "metrics_summary": {"acc": 0.9, "f1": 0.87},
                    "primary_metric": {"metric_id": "acc", "value": 0.9},
                    "metric_contract": _detailed_metric_contract(
                        ["acc", "f1"],
                        primary_metric_id="acc",
                        evaluation_protocol={
                            "scope_id": "full",
                            "code_paths": ["eval.py"],
                        },
                    ),
                },
            )
        )
        assert baseline_success["ok"] is True

        main_failure = _unwrap_tool_result(
            await server.call_tool(
                "record_main_experiment",
                {
                    "run_id": "main-missing-f1",
                    "title": "Missing F1",
                    "hypothesis": "This run omits one canonical metric.",
                    "setup": "Reuse accepted baseline settings.",
                    "execution": "Run evaluation once.",
                    "results": "Only accuracy was reported.",
                    "conclusion": "Should fail strict validation.",
                    "metric_rows": [{"metric_id": "acc", "value": 0.93, "scope_id": "full"}],
                },
            )
        )
        assert main_failure["ok"] is False
        assert main_failure["error_code"] == "main_experiment_metric_validation_failed"
        assert main_failure["validation_stage"] == "main_experiment"
        assert main_failure["baseline_metric_ids"] == ["acc", "f1"]
        assert main_failure["missing_metric_ids"] == ["f1"]
        assert main_failure["extra_metric_ids"] == []

    asyncio.run(scenario())


def test_artifact_mcp_server_confirm_baseline_accepts_metric_directions(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp metric directions quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-directions",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        baseline_root = quest_root / "baselines" / "local" / "mcp-direction-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# MCP Direction Baseline\n", encoding="utf-8")

        confirm_result = _unwrap_tool_result(
            await server.call_tool(
                "confirm_baseline",
                {
                    "baseline_path": "baselines/local/mcp-direction-baseline",
                    "baseline_id": "mcp-direction-baseline",
                    "summary": "Use lower-is-better overrides",
                    "metrics_summary": {"sigma_max": 0.6921, "raw_false": 0.2149},
                    "primary_metric": {"metric_id": "sigma_max", "value": 0.6921},
                    "metric_contract": _detailed_metric_contract(
                        ["sigma_max", "raw_false"],
                        primary_metric_id="sigma_max",
                        directions={
                            "sigma_max": "maximize",
                            "raw_false": "maximize",
                        },
                        evaluation_protocol={
                            "scope_id": "full",
                            "code_paths": ["eval.py"],
                        },
                    ),
                    "metric_directions": {
                        "sigma_max": "lower_better",
                        "raw_false": "lower_better",
                    },
                },
            )
        )

        assert confirm_result["ok"] is True
        contract_json_path = quest_root / confirm_result["confirmed_baseline_ref"]["metric_contract_json_rel_path"]
        payload = read_json(contract_json_path, {})
        directions = {
            item["metric_id"]: item["direction"]
            for item in payload["metric_contract"]["metrics"]
        }
        assert directions["sigma_max"] == "minimize"
        assert directions["raw_false"] == "minimize"

    asyncio.run(scenario())


def test_artifact_mcp_server_analysis_campaign_infers_parent_main_run_from_runtime_refs(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp analysis parent run inference quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="worker-context-run",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        baseline_root = quest_root / "baselines" / "local" / "mcp-parent-run-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# MCP baseline\n", encoding="utf-8")

        confirm_result = _unwrap_tool_result(
            await server.call_tool(
                "confirm_baseline",
                {
                    "baseline_path": str(baseline_root),
                    "baseline_id": "mcp-parent-run-baseline",
                    "summary": "Confirmed baseline for parent run inference.",
                    "metrics_summary": {"acc": 0.8},
                    "primary_metric": {"metric_id": "acc", "value": 0.8},
                    "metric_contract": _detailed_metric_contract(["acc"], primary_metric_id="acc"),
                },
            )
        )
        assert confirm_result["ok"] is True

        idea_result = _unwrap_tool_result(
            await server.call_tool(
                "submit_idea",
                {
                    "mode": "create",
                    "title": "Parent-run inference route",
                    "problem": "The writing-facing analysis campaign must bind to the true main run.",
                    "hypothesis": "The latest main run should be reused, not the MCP worker run id.",
                    "mechanism": "Create a paper branch, then launch analysis without an explicit parent_run_id.",
                    "decision_reason": "Prepare a realistic MCP flow.",
                },
            )
        )
        assert idea_result["ok"] is True

        main_result = _unwrap_tool_result(
            await server.call_tool(
                "record_main_experiment",
                {
                    "run_id": "main-parent-001",
                    "title": "Parent run",
                    "hypothesis": "This is the true parent run.",
                    "setup": "Standard setup.",
                    "execution": "Ran the main evaluation once.",
                    "results": "The main run is ready for analysis.",
                    "conclusion": "Launch one writing-facing analysis slice.",
                    "metric_rows": [{"metric_id": "acc", "value": 0.86, "direction": "higher_better"}],
                    "evaluation_summary": {
                        "takeaway": "The main run beats the baseline.",
                        "claim_update": "strengthens",
                        "baseline_relation": "better",
                        "comparability": "high",
                        "failure_mode": "none",
                        "next_action": "analysis_campaign",
                    },
                },
            )
        )
        assert main_result["ok"] is True

        outline_candidate = _unwrap_tool_result(
            await server.call_tool(
                "submit_paper_outline",
                {
                    "mode": "candidate",
                    "outline_id": "outline-parent-run",
                    "title": "Parent run outline",
                    "note": "Bind analysis to the selected outline.",
                    "detailed_outline": {
                        "title": "Parent run outline",
                        "research_questions": ["RQ-parent"],
                        "experimental_designs": ["Ablation-parent"],
                        "contributions": ["C-parent"],
                    },
                },
            )
        )
        assert outline_candidate["outline_id"] == "outline-parent-run"

        selected_outline = _unwrap_tool_result(
            await server.call_tool(
                "submit_paper_outline",
                {
                    "mode": "select",
                    "outline_id": "outline-parent-run",
                    "selected_reason": "Writing-facing analysis requires a selected outline.",
                },
            )
        )
        assert selected_outline["outline_id"] == "outline-parent-run"

        campaign = _unwrap_tool_result(
            await server.call_tool(
                "create_analysis_campaign",
                {
                    "campaign_title": "Parent run inference campaign",
                    "campaign_goal": "Verify parent_run_id inference from the latest main run.",
                    "selected_outline_ref": "outline-parent-run",
                    "research_questions": ["RQ-parent"],
                    "experimental_designs": ["Ablation-parent"],
                    "todo_items": [
                        {
                            "exp_id": "EXP-PARENT-001",
                            "todo_id": "todo-parent-001",
                            "slice_id": "ablation",
                            "title": "Parent ablation",
                            "research_question": "RQ-parent",
                            "experimental_design": "Ablation-parent",
                            "tier": "main_required",
                            "paper_placement": "main_text",
                            "paper_role": "main_text",
                            "section_id": "parent-analysis",
                            "item_id": "AN-PARENT-001",
                            "claim_links": ["C-parent"],
                            "completion_condition": "Complete one comparable ablation.",
                        }
                    ],
                    "slices": [
                        {
                            "slice_id": "ablation",
                            "title": "Parent ablation",
                            "goal": "Disable the main component and compare.",
                            "required_changes": "Disable the main component only.",
                            "metric_contract": "Keep the same evaluation protocol.",
                            "section_id": "parent-analysis",
                            "item_id": "AN-PARENT-001",
                            "paper_role": "main_text",
                            "claim_links": ["C-parent"],
                        }
                    ],
                },
            )
        )
        assert campaign["manifest"]["parent_run_id"] == "main-parent-001"
        assert campaign["manifest"]["parent_run_id"] != "worker-context-run"

        completed = _unwrap_tool_result(
            await server.call_tool(
                "record_analysis_slice",
                {
                    "campaign_id": campaign["campaign_id"],
                    "slice_id": "ablation",
                    "setup": "Disable the main component only.",
                    "execution": "Ran the ablation once.",
                    "results": "The analysis slice finished cleanly.",
                    "metric_rows": [{"metric_id": "acc", "value": 0.84, "direction": "higher_better"}],
                    "evaluation_summary": {
                        "takeaway": "The ablation still stays above baseline.",
                        "claim_update": "strengthens",
                        "baseline_relation": "better",
                        "comparability": "high",
                        "failure_mode": "none",
                        "next_action": "write",
                    },
                },
        )
        )
        assert completed["completed"] is True
        assert completed["returned_to_branch"] == "run/main-parent-001"
        assert completed["writing_branch"] == "paper/main-parent-001"

        refs = _unwrap_tool_result(await server.call_tool("resolve_runtime_refs", {}))
        assert refs["current_workspace_branch"] == "paper/main-parent-001"

    asyncio.run(scenario())


def test_artifact_mcp_server_arxiv_tool_calls_service(temp_home: Path, monkeypatch) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp arxiv quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-arxiv",
            active_anchor="scout",
            conversation_id="quest:test",
            agent_role="scout",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        calls: list[tuple[str | None, str, bool, str]] = []

        def fake_arxiv(  # noqa: ANN001
            self,
            paper_id: str | None = None,
            *,
            mode: str = "read",
            full_text: bool = False,
            quest_root: Path | None = None,
        ) -> dict[str, object]:
            calls.append((paper_id, mode, full_text, str(quest_root) if quest_root else ""))
            return {
                "ok": True,
                "paper_id": paper_id,
                "mode": mode,
                "requested_full_text": full_text,
                "content_mode": "overview",
                "source": "test",
                "content": "# Fake Paper",
            }

        monkeypatch.setattr(ArtifactService, "arxiv", fake_arxiv)
        server = build_artifact_server(context)
        result = _unwrap_tool_result(
            await server.call_tool(
                "arxiv",
                {
                    "paper_id": "2010.11929",
                    "full_text": True,
                },
            )
        )

        assert result["ok"] is True
        assert result["paper_id"] == "2010.11929"
        assert result["mode"] == "read"
        assert calls == [("2010.11929", "read", True, str(quest_root))]

    asyncio.run(scenario())


def test_artifact_mcp_server_arxiv_list_mode_calls_service(temp_home: Path, monkeypatch) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp arxiv list quest")
        quest_root = Path(quest["quest_root"])
        calls: list[tuple[str | None, str, bool, str]] = []

        def fake_arxiv(  # noqa: ANN001
            self,
            paper_id: str | None = None,
            *,
            mode: str = "read",
            full_text: bool = False,
            quest_root: Path | None = None,
        ) -> dict[str, object]:
            calls.append((paper_id, mode, full_text, str(quest_root) if quest_root else ""))
            return {
                "ok": True,
                "mode": mode,
                "items": [
                    {
                        "arxiv_id": "2010.11929",
                        "title": "Vision Transformers",
                        "abstract": "A concise summary.",
                        "status": "ready",
                    }
                ],
                "count": 1,
            }

        monkeypatch.setattr(ArtifactService, "arxiv", fake_arxiv)
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-arxiv-list",
            active_anchor="scout",
            conversation_id="quest:test",
            agent_role="scout",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)
        result = _unwrap_tool_result(await server.call_tool("arxiv", {"mode": "list"}))

        assert result["ok"] is True
        assert result["mode"] == "list"
        assert result["count"] == 1
        assert result["items"][0]["arxiv_id"] == "2010.11929"
        assert calls == [(None, "list", False, str(quest_root))]

    asyncio.run(scenario())


def test_bash_exec_mcp_server_supports_detach_read_list_and_kill(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp bash quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-bash",
            active_anchor="experiment",
            conversation_id=f"quest:{quest['quest_id']}",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_bash_exec_server(context)

        assert [tool.name for tool in await server.list_tools()] == ["bash_exec"]

        detached = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": "printf 'alpha\\n'; sleep 1; printf 'omega\\n'; sleep 30",
                    "mode": "detach",
                    "comment": {"stage": "baseline", "goal": "smoke"},
                },
            )
        )
        assert detached["status"] == "running"
        assert detached["kind"] == "exec"
        assert detached["comment"] == {"stage": "baseline", "goal": "smoke"}
        assert detached["cwd"] == str(quest_root)
        assert detached["watchdog_after_seconds"] == 1800
        bash_id = detached["bash_id"]
        await asyncio.sleep(0.6)

        listing = _unwrap_tool_result(await server.call_tool("bash_exec", {"mode": "list"}))
        assert listing["count"] >= 1
        assert any(item["bash_id"] == bash_id for item in listing["items"])
        assert listing["summary"]["running_count"] >= 1
        assert any(bash_id in line for line in listing["history_lines"])

        exec_listing = _unwrap_tool_result(await server.call_tool("bash_exec", {"mode": "list", "kind": "exec"}))
        assert any(item["bash_id"] == bash_id for item in exec_listing["items"])

        history = _unwrap_tool_result(await server.call_tool("bash_exec", {"mode": "history"}))
        assert any(bash_id in line for line in history["lines"])

        read_back = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": bash_id,
                    "tail_limit": 5,
                    "order": "desc",
                },
            )
        )
        assert read_back["bash_id"] == bash_id
        assert read_back["comment"] == {"stage": "baseline", "goal": "smoke"}
        assert read_back["cwd"] == str(quest_root)
        assert any("alpha" in str(item.get("line") or "") for item in read_back["tail"])
        assert read_back["tail_limit"] == 5
        assert read_back["order"] == "desc"
        assert isinstance(read_back["silent_seconds"], int)
        assert read_back["watchdog_after_seconds"] == 1800
        last_seen_seq = int(read_back["latest_seq"] or 0)

        await asyncio.sleep(1.2)
        incremental = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": bash_id,
                    "after_seq": last_seen_seq,
                    "tail_limit": 10,
                    "order": "asc",
                },
            )
        )
        assert incremental["after_seq"] == last_seen_seq
        assert any("omega" in str(item.get("line") or "") for item in incremental["tail"])

        stopped = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "kill",
                    "id": bash_id,
                    "reason": "pytest-stop",
                    "force": True,
                    "wait": True,
                    "timeout_seconds": 10,
                },
            )
        )
        assert stopped["bash_id"] == bash_id
        assert stopped["status"] == "terminated"
        assert Path(quest_root / stopped["log_path"]).exists()

    asyncio.run(scenario())


def test_bash_exec_sleep_protocol_supports_sleep_and_existing_session_waits(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp bash sleep quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-bash-sleep",
            active_anchor="experiment",
            conversation_id=f"quest:{quest['quest_id']}",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_bash_exec_server(context)

        sleep_ok = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": "sleep 1",
                    "mode": "await",
                    "timeout_seconds": 3,
                    "comment": {"stage": "experiment", "goal": "sleep-check"},
                },
            )
        )
        assert sleep_ok["status"] == "completed"
        assert sleep_ok["exit_code"] == 0

        sleep_timeout = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": "sleep 3",
                    "mode": "await",
                    "timeout_seconds": 1,
                    "comment": {"stage": "experiment", "goal": "sleep-timeout-check"},
                },
            )
        )
        timeout_bash_id = sleep_timeout["bash_id"]
        timeout_final = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "await",
                    "id": timeout_bash_id,
                    "timeout_seconds": 5,
                },
            )
        )
        assert timeout_final["status"] == "terminated"
        assert timeout_final["stop_reason"] == "timeout"

        bounded_wait = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": "sleep 2; printf 'bounded-wait-done\\n'",
                    "mode": "await",
                    "timeout_seconds": 5,
                    "wait_timeout_seconds": 1,
                    "comment": {"stage": "experiment", "goal": "bounded-await-running-notice"},
                },
            )
        )
        bounded_wait_bash_id = bounded_wait["bash_id"]
        assert bounded_wait["status"] == "running"
        assert bounded_wait["still_running"] is True
        assert bounded_wait["wait_timed_out"] is True
        assert bounded_wait["wait_timeout_seconds"] == 1
        assert bounded_wait["suggested_poll_interval_seconds"] == 1800
        assert f"bash_exec(mode='read', id='{bounded_wait_bash_id}')" == bounded_wait["suggested_read_command"]
        assert (
            f"bash_exec(mode='await', id='{bounded_wait_bash_id}', wait_timeout_seconds=1800)"
            == bounded_wait["suggested_await_command"]
        )
        assert "still running" in str(bounded_wait["long_wait_notice"]).lower()

        bounded_wait_final = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "await",
                    "id": bounded_wait_bash_id,
                    "wait_timeout_seconds": 5,
                },
            )
        )
        assert bounded_wait_final["status"] == "completed"
        assert bounded_wait_final["exit_code"] == 0
        assert "wait_timed_out" not in bounded_wait_final

        detached = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": "sleep 2; printf 'done\\n'",
                    "mode": "detach",
                    "comment": {"stage": "experiment", "goal": "await-existing-session"},
                },
            )
        )
        detached_bash_id = detached["bash_id"]

        early_wait = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "await",
                    "id": detached_bash_id,
                    "timeout_seconds": 1,
                },
            )
        )
        assert early_wait["bash_id"] == detached_bash_id
        assert early_wait["status"] == "running"
        assert early_wait["wait_timed_out"] is True
        assert early_wait["still_running"] is True
        assert early_wait["wait_timeout_seconds"] == 1
        assert early_wait["suggested_poll_interval_seconds"] == 1800

        final_wait = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "await",
                    "id": detached_bash_id,
                    "timeout_seconds": 5,
                },
            )
        )
        assert final_wait["status"] == "completed"
        assert final_wait["exit_code"] == 0

        read_back = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": detached_bash_id,
                    "tail_limit": 10,
                    "order": "desc",
                },
            )
        )
        assert any("done" in str(item.get("line") or "") for item in read_back["tail"])

    asyncio.run(scenario())


def test_bash_exec_mcp_server_normalizes_list_wrapped_commands(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("mcp bash list command quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-bash-list-command",
            active_anchor="experiment",
            conversation_id=f"quest:{quest['quest_id']}",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_bash_exec_server(context)

        singleton = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": ["printf 'singleton-list-ok\n'"],
                    "mode": "await",
                    "timeout_seconds": 5,
                },
            )
        )
        assert singleton["status"] == "completed"
        assert singleton["command"] == "printf 'singleton-list-ok\n'"

        argv_style = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "command": ["printf", "argv-style-ok\n"],
                    "mode": "await",
                    "timeout_seconds": 5,
                },
            )
        )
        assert argv_style["status"] == "completed"
        assert "printf" in str(argv_style["command"] or "")

    asyncio.run(scenario())


def test_bash_exec_mcp_server_default_read_truncates_long_logs_with_hint(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp bash long log quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-bash-long-log",
            active_anchor="experiment",
            conversation_id=f"quest:{quest['quest_id']}",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        _write_fake_bash_session(
            temp_home,
            quest_root,
            "bash-long-preview",
            log_lines=[f"line-{index}" for index in range(1, 2301)],
        )
        server = build_bash_exec_server(context)

        result = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": "bash-long-preview",
                },
            )
        )

        assert result["bash_id"] == "bash-long-preview"
        assert result["log_truncated"] is True
        assert result["log_line_count"] == 2300
        assert result["log_preview_head_lines"] == 500
        assert result["log_preview_tail_lines"] == 1500
        assert result["log_preview_omitted_lines"] == 300
        assert result["log_is_partial"] is True
        assert result["seq_has_more_after"] is True
        assert result["seqs_after_window"] == 300
        assert "partial window" in result["log_truncation_notice"].lower() or "truncated" in result["log_truncation_notice"].lower()
        assert "line-1" in result["log"]
        assert "line-500" in result["log"]
        assert "line-501" not in result["log"]
        assert "line-800" not in result["log"]
        assert "line-801" in result["log"]
        assert "line-2300" in result["log"]
        assert "start=..., tail=..." in result["log_read_hint"]

    asyncio.run(scenario())


def test_bash_exec_mcp_server_read_supports_start_and_tail_windows(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp bash start window quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-bash-start-window",
            active_anchor="experiment",
            conversation_id=f"quest:{quest['quest_id']}",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        _write_fake_bash_session(
            temp_home,
            quest_root,
            "bash-window-preview",
            log_lines=[f"line-{index}" for index in range(1, 41)],
        )
        server = build_bash_exec_server(context)

        result = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": "bash-window-preview",
                    "start": 11,
                    "tail": 5,
                },
            )
        )

        assert result["bash_id"] == "bash-window-preview"
        assert result["log_windowed"] is True
        assert result["log_line_count"] == 40
        assert result["line_start"] == 11
        assert result["line_end"] == 15
        assert result["line_limit"] == 5
        assert result["returned_line_count"] == 5
        assert result["has_more_before"] is True
        assert result["has_more_after"] is True
        assert result["log_is_partial"] is True
        assert result["log_lines_before_window"] == 10
        assert result["log_lines_after_window"] == 25
        assert result["seqs_before_window"] == 10
        assert result["seqs_after_window"] == 25
        assert result["log"] == "\n".join([f"line-{index}" for index in range(11, 16)])

        latest = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": "bash-window-preview",
                    "tail": 3,
                },
            )
        )
        assert latest["line_start"] == 38
        assert latest["line_end"] == 40
        assert latest["seqs_before_window"] == 37
        assert latest["seqs_after_window"] == 0
        assert latest["log"] == "line-38\nline-39\nline-40"

    asyncio.run(scenario())


def test_bash_exec_mcp_server_seq_tail_reports_remaining_seq_ranges(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "mcp bash seq tail quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-mcp-bash-seq-tail",
            active_anchor="experiment",
            conversation_id=f"quest:{quest['quest_id']}",
            agent_role="pi",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        _write_fake_bash_session(
            temp_home,
            quest_root,
            "bash-seq-preview",
            log_lines=[f"line-{index}" for index in range(1, 41)],
        )
        service = BashExecService(temp_home)
        log_path = service.log_path(quest_root, "bash-seq-preview")
        entries = [
            {
                "seq": index,
                "stream": "stdout",
                "line": f"line-{index}",
                "timestamp": "2026-03-20T00:00:00+00:00",
            }
            for index in range(1, 41)
        ]
        log_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n", encoding="utf-8")
        meta_path = service.meta_path(quest_root, "bash-seq-preview")
        meta = read_json(meta_path, {})
        meta["latest_seq"] = 40
        meta["last_output_seq"] = 40
        write_json(meta_path, meta)

        server = build_bash_exec_server(context)
        result = _unwrap_tool_result(
            await server.call_tool(
                "bash_exec",
                {
                    "mode": "read",
                    "id": "bash-seq-preview",
                    "tail_limit": 5,
                    "after_seq": 10,
                },
            )
        )

        assert result["tail_is_partial"] is True
        assert result["seq_window_start"] == 36
        assert result["seq_window_end"] == 40
        assert result["seq_has_more_before"] is True
        assert result["seqs_before_window"] == 35
        assert result["seq_has_more_after"] is False
        assert result["seqs_after_window"] == 0
        assert "partial window" in result["log_truncation_notice"].lower()

    asyncio.run(scenario())


def test_bash_exec_watchdog_warns_after_many_calls_without_artifact_interact(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("bash watchdog quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-watchdog",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        artifact_server = build_artifact_server(context)
        interact_result = _unwrap_tool_result(
            await artifact_server.call_tool(
                "interact",
                {"kind": "progress", "message": "watchdog reset", "deliver_to_bound_conversations": False},
            )
        )
        assert interact_result["interaction_watchdog"]["tool_calls_since_last_artifact_interact"] == 0

        bash_server = build_bash_exec_server(context)
        result = None
        for _ in range(25):
            result = _unwrap_tool_result(await bash_server.call_tool("bash_exec", {"mode": "list"}))

        assert result is not None
        assert result["interaction_watchdog"]["tool_calls_since_last_artifact_interact"] >= 25
        assert result["interaction_watchdog"]["inspection_due"] is True
        assert result["interaction_watchdog"]["user_update_due"] is False
        assert "progress_watchdog_note" in result
        assert "artifact.interact" in str(result["progress_watchdog_note"])
        assert "watchdog_notes" in result
        assert any(item["kind"] == "progress" for item in result["watchdog_notes"])
        assert result["history_lines"] == []

    asyncio.run(scenario())


def test_bash_exec_watchdog_warns_after_visibility_gap_without_mutating_log_fields(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
        quest = quest_service.create("bash visibility watchdog quest")
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-visibility-watchdog",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )

        stale_at = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
        quest_service.update_runtime_state(
            quest_root=quest_root,
            last_artifact_interact_at=stale_at,
            last_tool_activity_at=stale_at,
            last_tool_activity_name="artifact.interact",
            tool_calls_since_last_artifact_interact=0,
        )

        bash_server = build_bash_exec_server(context)
        result = _unwrap_tool_result(await bash_server.call_tool("bash_exec", {"mode": "list"}))

        assert result["interaction_watchdog"]["tool_calls_since_last_artifact_interact"] == 1
        assert result["interaction_watchdog"]["inspection_due"] is True
        assert "visibility_watchdog_note" in result
        assert "artifact.interact" in str(result["visibility_watchdog_note"])
        assert any(item["kind"] == "visibility" for item in result["watchdog_notes"])
        assert result["history_lines"] == []

    asyncio.run(scenario())


def test_artifact_confirm_baseline_state_change_watchdog_requires_follow_up_update(temp_home: Path) -> None:
    async def scenario() -> None:
        ensure_home_layout(temp_home)
        ConfigManager(temp_home).ensure_files()
        quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create(
            "artifact state change watchdog quest"
        )
        quest_root = Path(quest["quest_root"])
        context = McpContext(
            home=temp_home,
            quest_id=quest["quest_id"],
            quest_root=quest_root,
            run_id="run-artifact-state-watchdog",
            active_anchor="baseline",
            conversation_id="quest:test",
            agent_role="baseline",
            worker_id="worker-main",
            worktree_root=None,
            team_mode="single",
        )
        server = build_artifact_server(context)

        baseline_root = quest_root / "baselines" / "local" / "watchdog-baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        (baseline_root / "README.md").write_text("# Watchdog Baseline\n", encoding="utf-8")

        result = _unwrap_tool_result(
            await server.call_tool(
                "confirm_baseline",
                {
                    "baseline_path": "baselines/local/watchdog-baseline",
                    "baseline_id": "watchdog-baseline",
                    "summary": "Confirm baseline and require a visible follow-up summary.",
                    "metrics_summary": {"acc": 0.91},
                    "primary_metric": {"metric_id": "acc", "value": 0.91},
                    "metric_contract": _detailed_metric_contract(
                        ["acc"],
                        primary_metric_id="acc",
                        evaluation_protocol={
                            "scope_id": "full",
                            "code_paths": ["eval.py"],
                        },
                    ),
                },
            )
        )

        assert result["ok"] is True
        assert result["interaction_watchdog"]["tool_calls_since_last_artifact_interact"] == 1
        assert "state_change_watchdog_note" in result
        assert "artifact.interact" in str(result["state_change_watchdog_note"])
        assert any(item["kind"] == "state_change" for item in result["watchdog_notes"])

    asyncio.run(scenario())


def test_list_distill_candidates_returns_pending_only(tmp_path):
    """Quest with two completed main_experiments and one already-reviewed; only the unreviewed one returns."""
    from deepscientist.artifact import ArtifactService
    from deepscientist.config import ConfigManager
    from deepscientist.home import ensure_home_layout, repo_root
    from deepscientist.quest import QuestService
    from deepscientist.skills import SkillInstaller
    import yaml

    home = tmp_path / "DSHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("Distill candidates demo")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id

    # Enable distill
    quest_yaml = quest_root / "quest.yaml"
    payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    contract = payload.get("startup_contract") if isinstance(payload.get("startup_contract"), dict) else {}
    contract["experience_distill"] = {"mode": "on"}
    payload["startup_contract"] = contract
    quest_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    service = ArtifactService(home)
    # Two completed main_experiments
    run_a = service.record(quest_root, {"kind": "run", "run_kind": "main_experiment", "status": "completed", "run_id": "main:1", "summary": "A"})
    run_b = service.record(quest_root, {"kind": "run", "run_kind": "main_experiment", "status": "completed", "run_id": "main:2", "summary": "B"})
    # Mark run A as reviewed
    service.record(quest_root, {
        "kind": "distill_review",
        "reviewed_run_ids": [run_a["artifact_id"]],
        "cards_written": [],
        "reason_if_empty": "smoke test",
    })

    result = service.list_distill_candidates(quest_root)
    assert result["ok"] is True
    assert result["experience_distill_on"] is True
    assert run_a["artifact_id"] in result["reviewed_run_ids"]
    candidate_ids = {c["artifact_id"] for c in result["candidates"]}
    assert candidate_ids == {run_b["artifact_id"]}


def test_list_distill_candidates_distill_off_returns_empty(tmp_path):
    """Quest with experience_distill: false. Expect empty candidates regardless of run state."""
    from deepscientist.artifact import ArtifactService
    from deepscientist.config import ConfigManager
    from deepscientist.home import ensure_home_layout, repo_root
    from deepscientist.quest import QuestService
    from deepscientist.skills import SkillInstaller

    home = tmp_path / "DSHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("Distill off demo")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id  # NOT enabled

    service = ArtifactService(home)
    service.record(quest_root, {"kind": "run", "run_kind": "main_experiment", "status": "completed", "run_id": "main:1", "summary": "A"})

    result = service.list_distill_candidates(quest_root)
    assert result["ok"] is True
    assert result["experience_distill_on"] is False
    assert result["candidates"] == []
    assert result["reviewed_run_ids"] == []


def test_list_distill_candidates_includes_summary_metadata(tmp_path):
    """Each candidate dict carries artifact_id, run_kind, status, summary, branch, created_at, path."""
    from deepscientist.artifact import ArtifactService
    from deepscientist.config import ConfigManager
    from deepscientist.home import ensure_home_layout, repo_root
    from deepscientist.quest import QuestService
    from deepscientist.skills import SkillInstaller
    import yaml

    home = tmp_path / "DSHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("Distill metadata demo")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id

    quest_yaml = quest_root / "quest.yaml"
    payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    contract = payload.get("startup_contract") if isinstance(payload.get("startup_contract"), dict) else {}
    contract["experience_distill"] = {"mode": "on"}
    payload["startup_contract"] = contract
    quest_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    service = ArtifactService(home)
    service.record(quest_root, {
        "kind": "run", "run_kind": "experiment", "status": "completed",
        "run_id": "exp:1", "summary": "Ablation A vs B",
    })

    result = service.list_distill_candidates(quest_root)
    assert len(result["candidates"]) == 1
    cand = result["candidates"][0]
    for key in ("artifact_id", "run_kind", "status", "summary", "branch", "created_at", "path"):
        assert key in cand, f"missing {key}"
    assert cand["run_kind"] == "experiment"
    assert cand["status"] == "completed"
    assert cand["summary"] == "Ablation A vs B"
