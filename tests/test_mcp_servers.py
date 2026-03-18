from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.mcp.context import McpContext
from deepscientist.mcp.server import build_artifact_server, build_bash_exec_server, build_memory_server
from deepscientist.quest import QuestService
from deepscientist.shared import read_jsonl, write_yaml
from deepscientist.skills import SkillInstaller


def _unwrap_tool_result(result):
    if isinstance(result, tuple) and len(result) == 2:
        return result[1]
    return result


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

        assert [tool.name for tool in await server.list_tools()] == [
            "write",
            "read",
            "search",
            "list_recent",
            "promote_to_global",
        ]

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

        assert [tool.name for tool in await server.list_tools()] == [
            "record",
            "checkpoint",
            "prepare_branch",
            "submit_idea",
            "list_research_branches",
            "resolve_runtime_refs",
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
            "waive_baseline",
            "arxiv",
            "refresh_summary",
            "render_git_graph",
            "interact",
            "complete_quest",
        ]

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

        branches_after_run = _unwrap_tool_result(await server.call_tool("list_research_branches", {}))
        assert branches_after_run["ok"] is True
        assert branches_after_run["count"] == 1
        assert branches_after_run["branches"][0]["branch_no"] == "001"
        assert branches_after_run["branches"][0]["branch_name"] == idea_result["branch"]
        assert branches_after_run["branches"][0]["latest_main_experiment"]["run_id"] == "main-mcp-001"

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
        assert branches_after_second_idea["count"] == 2
        by_branch = {item["branch_name"]: item for item in branches_after_second_idea["branches"]}
        assert by_branch[idea_result["branch"]]["branch_no"] == "001"
        assert by_branch[idea_result["branch"]]["latest_main_experiment"]["run_id"] == "main-mcp-001"
        assert by_branch[second_idea_result["branch"]]["branch_no"] == "002"
        assert by_branch[second_idea_result["branch"]]["foundation_ref"]["kind"] == "run"
        assert by_branch[second_idea_result["branch"]]["foundation_reason"] == "Carry forward the strongest measured branch."

        outlines_before = _unwrap_tool_result(await server.call_tool("list_paper_outlines", {}))
        assert outlines_before["selected_outline_ref"] is None
        assert outlines_before["count"] == 0

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
        assert slice_result["returned_to_branch"] == second_idea_result["branch"]
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
        calls: list[tuple[str, bool]] = []

        def fake_arxiv(self, paper_id: str, *, full_text: bool = False) -> dict[str, object]:  # noqa: ANN001
            calls.append((paper_id, full_text))
            return {
                "ok": True,
                "paper_id": paper_id,
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
        assert calls == [("2010.11929", True)]

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
