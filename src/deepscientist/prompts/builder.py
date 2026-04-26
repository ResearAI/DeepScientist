from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..artifact.experience_distill import (
    evaluate_distill_gate_for_quest,
    is_distill_on,
    is_recall_priors_on,
)
from ..connector_runtime import normalize_conversation_id, parse_conversation_id
from ..config import ConfigManager
from ..home import repo_root
from ..memory import MemoryService
from ..memory.frontmatter import load_markdown_document
from ..quest import QuestService
from ..registries import BaselineRegistry
from ..shared import read_json, read_text, read_yaml
from ..skills import SkillInstaller, companion_skill_ids, stage_skill_ids

# Backward-compatible snapshots for modules or tests that still import these names directly.
# Runtime routing should call `current_standard_skills(...)` / `current_companion_skills(...)`.
STANDARD_SKILLS = stage_skill_ids(repo_root())

_AUTO_CONTINUE_MONITOR_INTERVAL_SECONDS = 240

COMPANION_SKILLS = companion_skill_ids(repo_root())

STAGE_MEMORY_PLAN = {
    "scout": {
        "quest": ("papers", "knowledge", "decisions"),
        "global": ("papers", "knowledge", "templates"),
    },
    "baseline": {
        "quest": ("papers", "decisions", "episodes", "knowledge"),
        "global": ("knowledge", "templates", "papers"),
    },
    "idea": {
        "quest": ("papers", "ideas", "decisions", "knowledge"),
        "global": ("papers", "knowledge", "templates"),
    },
    "optimize": {
        "quest": ("episodes", "decisions", "ideas", "knowledge"),
        "global": ("knowledge", "templates"),
    },
    "experiment": {
        "quest": ("ideas", "decisions", "episodes", "knowledge"),
        "global": ("knowledge", "templates"),
    },
    "analysis-campaign": {
        "quest": ("ideas", "decisions", "episodes", "knowledge", "papers"),
        "global": ("knowledge", "templates", "papers"),
    },
    "write": {
        "quest": ("papers", "decisions", "knowledge", "ideas"),
        "global": ("templates", "knowledge", "papers"),
    },
    "finalize": {
        "quest": ("decisions", "knowledge", "episodes"),
        "global": ("knowledge", "templates"),
    },
    "decision": {
        "quest": ("decisions", "knowledge", "episodes", "ideas"),
        "global": ("knowledge", "templates"),
    },
}


def current_standard_skills(repo_root_path: Path | None = None) -> tuple[str, ...]:
    return stage_skill_ids(repo_root_path or repo_root())


def current_companion_skills(repo_root_path: Path | None = None) -> tuple[str, ...]:
    return companion_skill_ids(repo_root_path or repo_root())


def classify_turn_intent(user_message: str) -> str:
    text = str(user_message or "").strip()
    if not text:
        return "continue_stage"
    normalized = " ".join(text.split()).lower()
    structured_bootstrap_markers = (
        "project bootstrap",
        "primary research request",
        "research goals",
        "baseline context",
        "reference papers",
        "operational constraints",
        "research delivery mode",
        "decision handling mode",
        "launch mode",
        "research contract",
        "mandatory working rules",
    )
    structured_hit_count = sum(1 for marker in structured_bootstrap_markers if marker in normalized)
    if structured_hit_count >= 2:
        return "continue_stage"
    if normalized.startswith("/new ") or normalized.startswith("/new\n"):
        return "continue_stage"
    question_markers = ["?", "？", "现在进展", "全局", "多久", "什么情况", "在哪", "在哪里", "how long", "what", "where"]
    if any(marker in normalized for marker in question_markers):
        return "answer_user_question_first"
    command_markers = ["继续", "发给我", "发送", "运行", "启动", "resume", "send", "run", "launch"]
    if any(marker in normalized for marker in command_markers):
        return "execute_user_command_first"
    return "continue_stage"


class PromptBuilder:
    def __init__(self, repo_root: Path, home: Path, *, prompt_version_selection: str | None = None) -> None:
        self.repo_root = repo_root
        self.home = home
        self.quest_service = QuestService(home)
        self.memory_service = MemoryService(home)
        self.baseline_registry = BaselineRegistry(home)
        self.config_manager = ConfigManager(home)
        self.skill_installer = SkillInstaller(repo_root, home)
        self.prompt_version_selection = str(prompt_version_selection or "").strip() or None

    def build(
        self,
        *,
        quest_id: str,
        skill_id: str,
        user_message: str,
        model: str,
        turn_reason: str = "user_message",
        turn_intent: str | None = None,
        turn_mode: str | None = None,
        retry_context: dict | None = None,
        runner_name: str = "codex",
    ) -> str:
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_config = self.config_manager.load_named("config")
        connectors_config = self.config_manager.load_named_normalized("connectors")
        quest_root = Path(snapshot["quest_root"])
        self.skill_installer.sync_quest_prompts(quest_root)
        active_anchor = str(snapshot.get("active_anchor") or skill_id)
        default_locale = str(runtime_config.get("default_locale") or "en-US")
        workspace_mode = self._workspace_mode(snapshot)
        custom_profile = self._custom_profile(snapshot)
        start_setup_session = self._start_setup_session(snapshot)
        system_block = self._prompt_fragment(
            Path("start_setup") / "system.md"
            if start_setup_session
            else ("system_copilot.md" if workspace_mode == "copilot" else "system.md"),
            quest_root=quest_root,
        )
        shared_interaction_block = self._prompt_fragment(
            Path("contracts") / "shared_interaction.md",
            quest_root=quest_root,
        )
        admin_ops_contract_block = ""
        admin_ops_knowledge_block = ""
        admin_ops_session_block = ""
        settings_issue_session_block = ""
        start_setup_session_block = ""
        if custom_profile == "admin_ops":
            admin_ops_contract_block = self._prompt_fragment(
                Path("contracts") / "admin_ops.md",
                quest_root=quest_root,
            )
            admin_ops_knowledge_block = self._prompt_fragment(
                Path("contracts") / "admin_ops_knowledge.md",
                quest_root=quest_root,
            )
            admin_ops_session_block = self._admin_ops_session_block(snapshot)
        if custom_profile == "settings_issue":
            settings_issue_session_block = self._settings_issue_session_block(snapshot)
        if start_setup_session:
            start_setup_session_block = self._start_setup_session_block(snapshot)
        connector_contract_block = self._connector_contract_block(quest_id=quest_id, snapshot=snapshot)
        hardware_block = self._local_runtime_hardware_block(runtime_config=runtime_config)
        deepxiv_block = self._deepxiv_capability_block(runtime_config=runtime_config)
        sections = [
            system_block,
            "",
            shared_interaction_block,
            "",
        ]
        if admin_ops_contract_block:
            sections.extend([admin_ops_contract_block, ""])
        if start_setup_session_block:
            sections.extend(["## Start Setup Session", start_setup_session_block, ""])
        if admin_ops_session_block:
            sections.extend(["## Admin Ops Session Packet", admin_ops_session_block, ""])
        if settings_issue_session_block:
            sections.extend(["## Settings Issue Session Packet", settings_issue_session_block, ""])
        if admin_ops_knowledge_block:
            sections.extend([admin_ops_knowledge_block, ""])
        if custom_profile == "settings_issue":
            built_in_namespaces = "artifact, bash_exec"
            mcp_namespace_note = "mcp_namespace_note: only `artifact.prepare_github_issue(...)` and `bash_exec(...)` are available in this session."
        elif start_setup_session:
            built_in_namespaces = "artifact, bash_exec"
            mcp_namespace_note = "mcp_namespace_note: only `artifact.prepare_start_setup_form(...)` and `bash_exec(...)` are available in this session."
        else:
            built_in_namespaces = "memory, artifact, bash_exec"
            mcp_namespace_note = "mcp_namespace_note: use `bash_exec(...)` for all CLI commands."
        runner_tool_name_note = ""
        normalized_runner_name = str(runner_name or "").strip().lower()
        if normalized_runner_name in {"claude", "kimi", "opencode", "codex"}:
            if custom_profile == "settings_issue":
                runner_tool_name_note = (
                    "runner_tool_name_note: this runner may expose MCP tools with names like "
                    "`mcp__artifact__prepare_github_issue` and `mcp__bash_exec__bash_exec`; "
                    "if the tool picker is namespaced, call those exact `mcp__...` names instead of inventing a bare "
                    "`artifact.prepare_github_issue(...)` or `bash_exec(...)` tool name."
                )
            elif start_setup_session:
                runner_tool_name_note = (
                    "runner_tool_name_note: this runner may expose MCP tools with names like "
                    "`mcp__artifact__prepare_start_setup_form` and `mcp__bash_exec__bash_exec`; "
                    "if the tool picker is namespaced, call those exact `mcp__...` names instead of inventing a bare "
                    "`artifact.prepare_start_setup_form(...)` or `bash_exec(...)` tool name."
                )
            else:
                runner_tool_name_note = (
                    "runner_tool_name_note: this runner may expose MCP tools with names like "
                    "`mcp__memory__search`, `mcp__artifact__get_quest_state`, and `mcp__bash_exec__bash_exec`; "
                    "if the tool picker is namespaced, call those exact `mcp__...` names instead of inventing a bare "
                    "`memory.*`, `artifact.*`, or `bash_exec(...)` tool name."
                )

        sections.extend(
            [
                "## Runtime Context",
                f"ds_home: {self.home.resolve()}",
                f"quest_id: {quest_id}",
                f"quest_root: {quest_root}",
                f"research_head_branch: {snapshot.get('research_head_branch') or 'none'}",
                f"research_head_worktree_root: {snapshot.get('research_head_worktree_root') or 'none'}",
                f"current_workspace_branch: {snapshot.get('current_workspace_branch') or 'none'}",
                f"current_workspace_root: {snapshot.get('current_workspace_root') or 'none'}",
                f"active_idea_id: {snapshot.get('active_idea_id') or 'none'}",
                f"active_analysis_campaign_id: {snapshot.get('active_analysis_campaign_id') or 'none'}",
                f"active_anchor: {active_anchor}",
                f"active_branch: {snapshot.get('branch')}",
                f"requested_skill: {skill_id}",
                f"runner_name: {runner_name}",
                f"model: {model}",
                f"conversation_id: quest:{quest_id}",
                f"default_locale: {default_locale}",
                f"built_in_mcp_namespaces: {built_in_namespaces}",
                mcp_namespace_note,
                *( [runner_tool_name_note] if runner_tool_name_note else [] ),
                "",
                "Canonical stage skills root:",
                str((self.repo_root / "src" / "skills").resolve()),
                "",
                "Standard stage skill paths:",
                self._skill_paths_block(),
                "",
                "Companion skill paths:",
                self._companion_skill_paths_block(),
                "",
                "## Active Communication Surface",
                self._active_communication_surface_block(
                    quest_id=quest_id,
                    snapshot=snapshot,
                    runtime_config=runtime_config,
                    connectors_config=connectors_config,
                ),
            ]
        )
        if hardware_block:
            sections.extend(["", "## Local Runtime Hardware", hardware_block])
        if deepxiv_block:
            sections.extend(["", "## DeepXiv Capability", deepxiv_block])
        if connector_contract_block:
            sections.extend(
                [
                    "",
                    "## Connector Contract",
                    connector_contract_block,
                ]
            )
        sections.extend(
            [
                "",
                "## Turn Driver",
                self._turn_driver_block(
                    turn_reason=turn_reason,
                    user_message=user_message,
                    turn_intent=turn_intent,
                    turn_mode=turn_mode,
                ),
                "",
                "## Continuation Guard",
                self._continuation_guard_block(
                    snapshot=snapshot,
                    quest_root=quest_root,
                    turn_reason=turn_reason,
                    user_message=user_message,
                ),
                "",
                "## Active User Requirements",
                self._active_user_requirements_block(quest_root),
                "",
                "## Quest Context",
                self._quest_context_block(quest_root),
                "",
                "## Recent Durable State",
                self._durable_state_block(snapshot, quest_root),
                "",
                "## Research Delivery Policy",
                self._research_delivery_policy_block(snapshot),
                "",
                "## Optimization Frontier Snapshot",
                self._optimization_frontier_block(snapshot, quest_root),
                "",
                "## Paper And Evidence Snapshot",
                self._paper_and_evidence_block(snapshot, quest_root),
                "",
                "## Retry Recovery Packet",
                self._retry_recovery_block(retry_context),
                "",
                "## Recovery Resume Packet",
                self._recovery_resume_block(snapshot=snapshot, turn_reason=turn_reason),
                "",
                "## Resume Context Spine",
                self._resume_context_spine_block(
                    quest_id=quest_id,
                    quest_root=quest_root,
                    snapshot=snapshot,
                    turn_reason=turn_reason,
                ),
                "",
                "## Interaction Style",
                self._interaction_style_block(default_locale=default_locale, user_message=user_message, snapshot=snapshot),
                "",
                "## Priority Memory For This Turn",
                self._priority_memory_block(
                    quest_root,
                    skill_id=skill_id,
                    active_anchor=active_anchor,
                    user_message=user_message,
                ),
                "",
                "## Recent Conversation Window",
                self._special_conversation_block(snapshot, quest_id=quest_id),
                "",
                "## Current Turn Attachments",
                self._current_turn_attachments_block(
                    quest_id=quest_id,
                    user_message=user_message,
                    turn_reason=turn_reason,
                ),
                "",
                "## Current User Message",
                self._current_user_message_block(turn_reason=turn_reason, user_message=user_message),
            ]
        )
        return "\n\n".join(sections).strip() + "\n"

    def _turn_driver_block(
        self,
        *,
        turn_reason: str,
        user_message: str,
        turn_intent: str | None = None,
        turn_mode: str | None = None,
    ) -> str:
        normalized_reason = str(turn_reason or "user_message").strip() or "user_message"
        lines = [f"- turn_reason: {normalized_reason}"]
        if normalized_reason == "auto_continue":
            lines.extend(
                [
                    "- this turn was started by the runtime because the quest is still unfinished and no blocking user decision is currently pending",
                    "- there is no new user message attached to this turn; continue from the current durable quest state, active user requirements, recent conversation, and the latest artifacts",
                    "- do not reinterpret the last user message as if it were newly sent again",
                ]
            )
        elif normalized_reason == "queued_user_messages":
            lines.extend(
                [
                    "- this turn resumed because queued user messages are waiting in the mailbox path",
                    "- handle the newest runtime-delivered user requirements first, then continue the main quest route",
                ]
            )
        elif normalized_reason == "immediate_read":
            lines.extend(
                [
                    "- this turn was explicitly restarted because the user clicked immediate read for queued user messages",
                    "- the attached user_message already contains the runtime-prepared queued-message bundle; treat it as freshly delivered and handle it before resuming other work",
                ]
            )
        else:
            preview = " ".join(str(user_message or "").split())
            if len(preview) > 220:
                preview = preview[:217].rstrip() + "..."
            resolved_turn_intent = str(turn_intent or self._turn_intent(user_message)).strip() or "continue_stage"
            resolved_turn_mode = str(turn_mode or "stage_execution").strip() or "stage_execution"
            lines.append(f"- turn_intent: {resolved_turn_intent}")
            lines.append(f"- turn_mode: {resolved_turn_mode}")
            if resolved_turn_intent == "answer_user_question_first":
                lines.append(
                    "- answer_first_rule: the user primarily asked a direct question. Answer it in plain language before resuming any background stage work or generating new route artifacts."
                )
                lines.append(
                    "- direct_answer_tool_rule: if the question is about overall progress, paper readiness, current best result, or next step, call artifact.get_global_status(detail='brief'|'full', locale='zh'|'en') before answering from memory or local stage context."
                )
                lines.append(
                    "- node_progress_tool_rule: if the question is about the active node, research head, canvas-like global progress, branch switching, or which durable line is currently live, call artifact.get_research_map_status(detail='summary'|'full', locale='zh'|'en') before answering."
                )
                lines.append(
                    "- node_progress_dedupe_rule: if research_map_status shows the same current node, research head, and blocker/route state as the last judgment, do not loop on more map reads or branch-switch chatter; continue the current action."
                )
            elif resolved_turn_intent == "execute_user_command_first":
                lines.append(
                    "- command_first_rule: the user primarily gave a concrete instruction. Execute or acknowledge that instruction first before resuming background stage narration."
                )
            lines.append(f"- direct_user_message_preview: {preview or 'none'}")
        return "\n".join(lines)

    @staticmethod
    def _turn_intent(user_message: str) -> str:
        return classify_turn_intent(user_message)

    def _active_communication_surface_block(
        self,
        *,
        quest_id: str,
        snapshot: dict,
        runtime_config: dict,
        connectors_config: dict,
    ) -> str:
        surface_context = self._surface_context(quest_id=quest_id, snapshot=snapshot)
        source = surface_context["latest_user_source"]
        surface = surface_context["active_surface"]
        connector = surface_context["active_connector"]
        chat_type = surface_context["active_chat_type"]
        chat_id = surface_context["active_chat_id"]
        lines = [
            f"- latest_user_source: {source}",
            f"- active_surface: {surface}",
            f"- active_connector: {connector}",
            f"- active_chat_type: {chat_type}",
            f"- active_chat_id: {chat_id}",
            f"- active_connector_origin: {surface_context['active_connector_origin']}",
            f"- bound_external_connector_count: {surface_context['bound_external_connector_count']}",
            "- surface_rule: treat web, TUI, and connector threads as one continuous quest, but adapt the amount of detail to the active surface.",
            "- surface_reply_rule: use artifact.interact(...) for durable user-visible continuity; do not dump raw internal tool chatter into connector replies.",
            "- connector_contract_rule: choose the active connector surface from the latest inbound external user turn when one exists; otherwise fall back to the bound external connector; keep purely local web/TUI turns on the local surface even if the quest is externally bound.",
        ]

        if connector == "qq":
            lines.extend(
                [
                    "- qq_surface_rule: QQ is a milestone-report surface, not a full artifact browser.",
                    "- qq_reply_rule: keep outbound replies concise, respectful, text-first, and progress-aware.",
                    "- qq_detail_rule: rely on the QQ connector contract for detailed surface formatting instead of expanding it here.",
                ]
            )
        elif connector == "weixin":
            lines.extend(
                [
                    "- weixin_surface_rule: Weixin is a concise operator surface, not a full artifact browser.",
                    "- weixin_reply_rule: keep outbound replies concise, respectful, text-first, and progress-aware.",
                    "- weixin_detail_rule: rely on the Weixin connector contract for detailed transport formatting instead of expanding it here.",
                ]
            )
        else:
            lines.append("- connector_media_rule: if the active surface is not QQ, keep using the general artifact interaction discipline for milestone delivery.")

        return "\n".join(lines)

    def _surface_context(self, *, quest_id: str, snapshot: dict) -> dict[str, str | int]:
        latest_user = self._latest_user_message(quest_id)
        latest_user_source = str((latest_user or {}).get("source") or "local:default").strip() or "local:default"
        latest_user_parsed = parse_conversation_id(normalize_conversation_id(latest_user_source))
        bound_sources = snapshot.get("bound_conversations") or []
        bound_external: list[dict[str, str]] = []
        for raw in bound_sources:
            parsed = parse_conversation_id(normalize_conversation_id(raw))
            if parsed is None:
                continue
            if str(parsed.get("connector") or "").strip().lower() == "local":
                continue
            bound_external.append(parsed)
        latest_connector = str((latest_user_parsed or {}).get("connector") or "").strip().lower()
        if latest_connector and latest_connector != "local":
            active = latest_user_parsed
            origin = "latest_user_source"
        elif latest_user is not None:
            return {
                "latest_user_source": latest_user_source,
                "active_surface": "local",
                "active_connector": "local",
                "active_chat_type": "local",
                "active_chat_id": "default",
                "active_connector_origin": "latest_user_source_local",
                "bound_external_connector_count": len(bound_external),
            }
        else:
            active = bound_external[0] if bound_external else None
            origin = "bound_external_binding" if active is not None else "none"
        if active is None:
            return {
                "latest_user_source": latest_user_source,
                "active_surface": "local",
                "active_connector": "local",
                "active_chat_type": "local",
                "active_chat_id": "default",
                "active_connector_origin": "none",
                "bound_external_connector_count": len(bound_external),
            }
        return {
            "latest_user_source": latest_user_source,
            "active_surface": "connector",
            "active_connector": str(active.get("connector") or "connector"),
            "active_chat_type": str(active.get("chat_type") or "direct"),
            "active_chat_id": str(active.get("chat_id") or "unknown"),
            "active_connector_origin": origin,
            "bound_external_connector_count": len(bound_external),
        }

    def _active_external_connector_name(self, *, quest_id: str, snapshot: dict) -> str | None:
        surface_context = self._surface_context(quest_id=quest_id, snapshot=snapshot)
        connector = str(surface_context.get("active_connector") or "").strip().lower()
        if not connector or connector == "local":
            return None
        return connector

    def _deepxiv_capability_block(self, *, runtime_config: dict) -> str:
        literature = runtime_config.get("literature") if isinstance(runtime_config.get("literature"), dict) else {}
        deepxiv = literature.get("deepxiv") if isinstance(literature.get("deepxiv"), dict) else {}
        enabled = bool(deepxiv.get("enabled"))
        direct_token = str(deepxiv.get("token") or "").strip()
        token_env_name = str(deepxiv.get("token_env") or "").strip()
        env_token = str(os.environ.get(token_env_name) or "").strip() if token_env_name else ""
        configured = enabled and bool(direct_token or env_token)
        lines = [
            f"- deepxiv_available: {configured}",
            f"- deepxiv_enabled: {enabled}",
            f"- deepxiv_base_url: {str(deepxiv.get('base_url') or 'https://data.rag.ac.cn').strip() or 'https://data.rag.ac.cn'}",
            f"- deepxiv_default_result_size: {int(deepxiv.get('default_result_size') or 10)}",
            f"- deepxiv_preview_characters: {int(deepxiv.get('preview_characters') or 1200)}",
        ]
        if configured:
            lines.extend([
                "- deepxiv_rule: DeepXiv is configured in this runtime. For paper-centric literature discovery and shortlist paper triage, prefer the DeepXiv route before broad open-web search when it can answer the question more directly.",
                "- deepxiv_preferred_path: use `artifact.deepxiv(...)` for paper retrieval and structured DeepXiv reads when that tool is available in this runtime.",
                "- deepxiv_fallback_rule: if the runtime does not expose a DeepXiv tool, or if DeepXiv is insufficient for the needed paper detail, fall back to the legacy route: memory reuse, web discovery, and `artifact.arxiv(...)`."
            ])
        else:
            lines.extend([
                "- deepxiv_forbidden_rule: DeepXiv is not configured in this runtime. Do not rely on DeepXiv or assume its token exists.",
                "- deepxiv_required_fallback: use the legacy route only: memory reuse, web discovery, and `artifact.arxiv(...)`."
            ])
        return "\n".join(lines)

    def _connector_contract_block(self, *, quest_id: str, snapshot: dict) -> str:
        connector = self._active_external_connector_name(quest_id=quest_id, snapshot=snapshot)
        if connector is None:
            return ""
        quest_root = Path(snapshot["quest_root"])
        path = self._prompt_path(Path("connectors") / f"{connector}.md", quest_root=quest_root)
        if not path.exists():
            return ""
        return self._markdown_body(path)

    def _local_runtime_hardware_block(self, *, runtime_config: dict) -> str:
        hardware = runtime_config.get("hardware") if isinstance(runtime_config.get("hardware"), dict) else {}
        selection_mode = str(hardware.get("gpu_selection_mode") or "all").strip().lower() or "all"
        if selection_mode not in {"all", "selected"}:
            selection_mode = "all"
        selected_gpu_ids = [str(item).strip() for item in (hardware.get("selected_gpu_ids") or []) if str(item).strip()]
        include_summary = bool(hardware.get("include_system_hardware_in_prompt", True))
        cache = read_json(self.home / "runtime" / "admin" / "cache" / "system_hardware.json", {})
        preferences = cache.get("preferences") if isinstance(cache.get("preferences"), dict) else {}
        system = cache.get("system") if isinstance(cache.get("system"), dict) else {}
        effective_gpu_ids = [
            str(item).strip()
            for item in (
                preferences.get("effective_gpu_ids")
                if isinstance(preferences.get("effective_gpu_ids"), list)
                else selected_gpu_ids
            )
            if str(item).strip()
        ]
        if selection_mode == "all" and not include_summary:
            return ""
        lines = [
            "- hardware_scope_rule: treat the configured local hardware summary and selected GPUs as an operator-provided device boundary for local compute rather than as optional flavor text.",
            f"- gpu_selection_mode: {selection_mode}",
            f"- selected_gpu_ids: {', '.join(selected_gpu_ids) if selected_gpu_ids else ('all' if selection_mode == 'all' else 'none')}",
            f"- effective_gpu_ids: {', '.join(effective_gpu_ids) if effective_gpu_ids else ('none' if selection_mode == 'selected' else 'all-detected-or-unset')}",
            f"- cuda_visible_devices_hint: {str(preferences.get('cuda_visible_devices') or '').strip() or ('unset' if selection_mode == 'all' else 'none')}",
        ]
        if selection_mode == "selected":
            if effective_gpu_ids:
                lines.append("- gpu_boundary_rule: when launching local GPU workloads, stay within the selected GPU ids instead of assuming every detected GPU is available.")
            else:
                lines.append("- gpu_boundary_rule: no GPU is currently selected; treat local GPU workloads as unavailable unless the operator changes Admin hardware selection.")
        if not include_summary:
            lines.append("- hardware_summary_visibility: disabled by config; use the GPU boundary above but do not rely on a fuller hardware summary.")
            return "\n".join(lines)
        cpu = system.get("cpu") if isinstance(system.get("cpu"), dict) else {}
        memory = system.get("memory") if isinstance(system.get("memory"), dict) else {}
        disks = system.get("disks") if isinstance(system.get("disks"), list) else []
        gpus = system.get("gpus") if isinstance(system.get("gpus"), list) else []
        cpu_model = str(cpu.get("model") or "unknown cpu").strip()
        logical_cores = str(cpu.get("logical_cores") or "unknown").strip()
        memory_total_gb = str(memory.get("total_gb") or "unknown").strip()
        disk_free = "unknown"
        if disks and isinstance(disks[0], dict):
            disk_free = f"{disks[0].get('free_gb') or 'unknown'}GB free on {disks[0].get('mount') or '/'}"
        lines.extend(
            [
                f"- cpu_summary: {cpu_model} | logical_cores={logical_cores}",
                f"- memory_total_gb: {memory_total_gb}",
                f"- root_disk_summary: {disk_free}",
            ]
        )
        if gpus:
            gpu_parts = []
            for item in gpus[:8]:
                if not isinstance(item, dict):
                    continue
                gpu_id = str(item.get("gpu_id") or "").strip() or "?"
                name = str(item.get("name") or "GPU").strip()
                memory_total = item.get("memory_total_gb")
                gpu_parts.append(f"{gpu_id}:{name}{f' {memory_total}GB' if memory_total is not None else ''}")
            lines.append(f"- gpu_inventory: {'; '.join(gpu_parts) or 'none'}")
        else:
            lines.append("- gpu_inventory: none detected")
        return "\n".join(lines)

    def _deepxiv_capability_block(self, *, runtime_config: dict) -> str:
        literature = runtime_config.get("literature") if isinstance(runtime_config.get("literature"), dict) else {}
        deepxiv = literature.get("deepxiv") if isinstance(literature.get("deepxiv"), dict) else {}
        enabled = bool(deepxiv.get("enabled"))
        direct_token = str(deepxiv.get("token") or "").strip()
        token_env_name = str(deepxiv.get("token_env") or "").strip()
        env_token = str(__import__("os").environ.get(token_env_name) or "").strip() if token_env_name else ""
        configured = enabled and bool(direct_token or env_token)
        lines = [
            f"- deepxiv_available: {configured}",
            f"- deepxiv_enabled: {enabled}",
            f"- deepxiv_base_url: {str(deepxiv.get('base_url') or 'https://data.rag.ac.cn').strip() or 'https://data.rag.ac.cn'}",
            f"- deepxiv_default_result_size: {int(deepxiv.get('default_result_size') or 20)}",
            f"- deepxiv_preview_characters: {int(deepxiv.get('preview_characters') or 5000)}",
        ]
        if configured:
            lines.extend(
                [
                    "- deepxiv_rule: DeepXiv is configured in this runtime. For paper-centric literature discovery and shortlist paper triage, prefer the DeepXiv route before broad open-web search when it can answer the question more directly.",
                    "- deepxiv_preferred_path: use `artifact.deepxiv(...)` for paper retrieval and structured DeepXiv reads when that tool is available in this runtime.",
                    "- deepxiv_fallback_rule: if the runtime does not expose a DeepXiv tool, or if DeepXiv is insufficient for the needed paper detail, fall back to the legacy route: memory reuse, web discovery, and `artifact.arxiv(...)`.",
                ]
            )
        else:
            lines.extend(
                [
                    "- deepxiv_forbidden_rule: DeepXiv is not configured in this runtime. Do not rely on DeepXiv or assume its token exists.",
                    "- deepxiv_required_fallback: use the legacy route only: memory reuse, web discovery, and `artifact.arxiv(...)`.",
                ]
            )
        return "\n".join(lines)

    def _local_daemon_api_block(self, *, include_benchstore: bool = False, include_admin: bool = False) -> str:
        runtime_config = self.config_manager.load_named("config")
        ui_config = runtime_config.get("ui") if isinstance(runtime_config.get("ui"), dict) else {}
        host = str(ui_config.get("host") or "0.0.0.0").strip() or "0.0.0.0"
        raw_port = ui_config.get("port")
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            port = 20999
        daemon_state = read_json(self.home / "runtime" / "daemon.json", {})
        daemon_url = str((daemon_state.get("url") if isinstance(daemon_state, dict) else "") or "").strip()
        bind_url = str((daemon_state.get("bind_url") if isinstance(daemon_state, dict) else "") or "").strip()
        if not daemon_url:
            normalized_host = "127.0.0.1" if host in {"0.0.0.0", "::", "[::]", ""} else host
            rendered_host = normalized_host if ":" not in normalized_host or normalized_host.startswith("[") else f"[{normalized_host}]"
            daemon_url = f"http://{rendered_host}:{port}"
        if not bind_url:
            bind_url = f"http://{host}:{port}"
        auth_enabled = bool((daemon_state.get("auth_enabled") if isinstance(daemon_state, dict) else False))
        auth_token = str((daemon_state.get("auth_token") if isinstance(daemon_state, dict) else "") or "").strip() or None

        lines = [
            f"- local_daemon_api_base_url: {daemon_url}",
            f"- local_daemon_bind_url: {bind_url}",
            f"- local_daemon_auth_enabled: {auth_enabled}",
            f"- local_daemon_auth_token: {auth_token or 'none'}",
            "- local_daemon_api_call_rule: if you need direct daemon API state beyond the MCP surface, use `bash_exec(...)` to call the local daemon over HTTP.",
            "- local_daemon_api_auth_rule: when `local_daemon_auth_enabled` is true, include header `Authorization: Bearer <local_daemon_auth_token>` in those HTTP calls.",
            "- local_daemon_api_health_endpoint: GET /api/health",
        ]
        if include_benchstore:
            lines.extend(
                [
                    "- local_daemon_api_benchstore_endpoints:",
                    "  - GET /api/benchstore/entries",
                    "  - GET /api/benchstore/entries/:entry_id",
                    "  - GET /api/benchstore/entries/:entry_id/setup-packet",
                    "  - POST /api/benchstore/entries/:entry_id/install",
                    "  - POST /api/benchstore/entries/:entry_id/launch",
                ]
            )
        if include_admin:
            lines.extend(
                [
                    "- local_daemon_api_admin_endpoints:",
                    "  - GET /api/system/overview",
                    "  - GET /api/system/hardware",
                    "  - GET /api/system/logs/sources",
                    "  - GET /api/system/logs/tail?source=<source>&line_count=<n>",
                    "  - GET /api/system/quests",
                    "  - GET /api/system/quests/:quest_id/summary",
                    "  - GET /api/system/repairs",
                    "  - POST /api/system/repairs",
                    "  - GET /api/system/tasks",
                    "  - GET /api/system/tasks/:task_id",
                ]
            )
        return "\n".join(lines)

    def _admin_ops_session_block(self, snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if not isinstance(startup_contract, dict):
            return "- none"
        admin_session = startup_contract.get("admin_session")
        if not isinstance(admin_session, dict):
            return "- none"

        repair_id = str(admin_session.get("repair_id") or "none").strip() or "none"
        scope = str(admin_session.get("scope") or "system").strip() or "system"
        repair_policy = str(admin_session.get("repair_policy") or "diagnose_only").strip() or "diagnose_only"
        source_page = str(admin_session.get("source_page") or "/admin").strip() or "/admin"
        targets = admin_session.get("targets")
        selected_paths = [str(item).strip() for item in (admin_session.get("selected_paths") or []) if str(item).strip()]
        knowledge_refs = [str(item).strip() for item in (admin_session.get("knowledge_refs") or []) if str(item).strip()]

        lines = [
            f"- repair_id: {repair_id}",
            f"- scope: {scope}",
            f"- repair_policy: {repair_policy}",
            f"- source_page: {source_page}",
            f"- local_repo_root: {self.repo_root.resolve()}",
            self._local_daemon_api_block(include_admin=True),
            f"- launcher_entry: {(self.repo_root / 'bin' / 'ds.js').resolve()}",
            f"- python_runtime_root: {(self.repo_root / 'src' / 'deepscientist').resolve()}",
            f"- web_ui_root: {(self.repo_root / 'src' / 'ui').resolve()}",
            f"- tui_root: {(self.repo_root / 'src' / 'tui').resolve()}",
            "- install_path_rule: treat the paths above as the active local checkout / install roots for this admin session unless fresh evidence proves a different deployed copy is in use.",
            "- github_origin: https://github.com/ResearAI/DeepScientist",
        ]
        if isinstance(targets, dict) and targets:
            lines.extend(
                [
                    "- targets_json:",
                    "```json",
                    json.dumps(targets, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        else:
            lines.append("- targets_json: {}")
        if selected_paths:
            lines.append("- selected_paths:")
            lines.extend([f"  - {item}" for item in selected_paths[:20]])
        else:
            lines.append("- selected_paths: none")
        lines.append("- source_address_rule: when proposing or applying source changes, always cite exact repo-relative file paths; when useful, also cite the absolute path anchored at `local_repo_root`.")
        lines.append("- selected_paths_rule: treat `selected_paths` as the first-priority source scope for SEARCH / REPRO / PATCH / VERIFY whenever it is non-empty.")
        lines.append("- command_forms_available: INSPECT, LOGS, SEARCH, REPRO, PATCH, VERIFY, ISSUE, PR")
        if knowledge_refs:
            lines.append("- recommended_knowledge_refs:")
            lines.extend([f"  - {item}" for item in knowledge_refs[:24]])
        else:
            lines.append("- recommended_knowledge_refs: none")
        return "\n".join(lines)

    def _active_user_requirements_block(self, quest_root: Path) -> str:
        path = self.quest_service._active_user_requirements_path(quest_root)
        if not path.exists():
            return "- none"
        text = read_text(path).strip()
        if not text:
            return "- none"
        return "\n".join(
            [
                f"- path: {path}",
                "- rule: treat this file as the highest-priority durable summary of the user's current requirements and constraints",
                "",
                text,
            ]
        )

    def _continuation_guard_block(
        self,
        *,
        snapshot: dict,
        quest_root: Path,
        turn_reason: str,
        user_message: str,
    ) -> str:
        waiting_interaction_id = str(snapshot.get("waiting_interaction_id") or "").strip() or None
        status = str(snapshot.get("runtime_status") or snapshot.get("status") or "unknown").strip() or "unknown"
        unfinished = status != "completed"
        active_requirement = self._active_requirement_text(
            snapshot=snapshot,
            quest_root=quest_root,
            turn_reason=turn_reason,
            user_message=user_message,
        )
        next_step = self._next_required_step(snapshot=snapshot)
        lines = [
            f"- quest_not_finished: {unfinished}",
            f"- current_task_status: {'the quest is still unfinished' if unfinished else 'the quest is already completed'}",
            f"- active_objective: {active_requirement}",
            "- early_stop_forbidden: do not stop, pause, or call artifact.complete_quest(...) just because one turn, one stage, one run, or one checkpoint finished",
            "- completion_rule: only call artifact.complete_quest(...) after a blocking completion approval request was sent and the user explicitly approved quest completion",
        ]
        if waiting_interaction_id:
            lines.extend(
                [
                    f"- blocking_decision_active: true ({waiting_interaction_id})",
                    "- must_continue_rule: do not silently end the quest; resolve the blocking interaction first, then continue from the updated durable state",
                ]
            )
        else:
            lines.extend(
                [
                    "- blocking_decision_active: false",
                    "- must_continue_rule: unless there is a real blocking user decision, keep advancing the quest automatically from durable state",
                ]
            )
        bash_running_count = int(((snapshot.get("counts") or {}).get("bash_running_count")) or 0)
        if bash_running_count > 0:
            lines.extend(
                [
                    f"- active_bash_run_count: {bash_running_count}",
                    "- long_run_watchdog_rule: while an important long-running bash_exec session is active, inspect real logs/status periodically instead of parking or busy-looping",
                ]
            )
        if str(turn_reason or "").strip() == "auto_continue":
            lines.extend(
                [
                    "- auto_continue_rule: this turn has no new user message; continue from the active requirements, durable artifacts, current quest state, current workspace checklist/plan state, and resume context spine instead of replaying the previous user message",
                    f"- auto_continue_interval_rule: when a real long-running external task is already active, background-progress auto-continue becomes a low-frequency monitoring pass, about every {_AUTO_CONTINUE_MONITOR_INTERVAL_SECONDS} seconds rather than rapid polling",
                    "- autonomous_prepare_rule: in autonomous mode, if no real long-running external task is active yet, use the next turns to prepare, launch, or durably close the next real unit of work instead of parking idly",
                    "- copilot_park_rule: in copilot mode, once the current requested unit is complete, it is normal to park and wait for the next user message or `/resume` instead of continuing autonomously",
                ]
            )
        else:
            lines.append(
                "- auto_continue_rule: if the runtime later starts an auto_continue turn, treat it as a direct instruction to keep going from durable state"
            )
        lines.append(f"- next_required_step: {next_step}")
        return "\n".join(lines)

    def _active_requirement_text(
        self,
        *,
        snapshot: dict,
        quest_root: Path,
        turn_reason: str,
        user_message: str,
    ) -> str:
        if str(turn_reason or "").strip() != "auto_continue":
            preview = " ".join(str(user_message or "").split())
            if preview:
                return preview[:257].rstrip() + "..." if len(preview) > 260 else preview
        for item in reversed(self.quest_service.history(str(snapshot.get("quest_id") or quest_root.name), limit=80)):
            if str(item.get("role") or "") != "user":
                continue
            preview = " ".join(str(item.get("content") or "").split())
            if preview:
                return preview[:257].rstrip() + "..." if len(preview) > 260 else preview
        title = str(snapshot.get("title") or "").strip()
        return title or "Continue the unfinished quest according to the durable quest documents."

    def _next_required_step(self, *, snapshot: dict) -> str:
        waiting_interaction_id = str(snapshot.get("waiting_interaction_id") or "").strip()
        if waiting_interaction_id:
            return f"Resolve the blocking interaction `{waiting_interaction_id}` before any further route change or quest completion."
        pending_user_count = int(snapshot.get("pending_user_message_count") or 0)
        if pending_user_count > 0:
            return f"Poll artifact.interact(...) and handle the {pending_user_count} queued user message(s) first."
        continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip().lower() or "auto"
        continuation_anchor = str(snapshot.get("continuation_anchor") or "").strip()
        if continuation_policy == "wait_for_user_or_resume":
            if continuation_anchor:
                return (
                    f"The quest is intentionally parked after the latest durable checkpoint. Wait for a new user message or "
                    f"`/resume`, then continue from `{continuation_anchor}` instead of auto-continuing the previous stage."
                )
            return "The quest is intentionally parked after the latest durable checkpoint. Wait for a new user message or `/resume`."
        if continuation_policy == "none":
            return "Do not auto-continue this quest. Wait for an explicit new user instruction before doing more work."
        active_anchor = str(snapshot.get("active_anchor") or "decision").strip() or "decision"
        if continuation_anchor:
            active_anchor = continuation_anchor
        active_idea_id = str(snapshot.get("active_idea_id") or "").strip()
        next_slice_id = str(snapshot.get("next_pending_slice_id") or "").strip()
        active_campaign_id = str(snapshot.get("active_analysis_campaign_id") or "").strip()
        if active_campaign_id and next_slice_id:
            return (
                f"Continue analysis campaign `{active_campaign_id}` and process the next pending slice `{next_slice_id}`."
            )
        if active_idea_id and active_anchor in {"experiment", "analysis-campaign", "write", "finalize"}:
            return f"Continue the `{active_anchor}` stage on the current idea `{active_idea_id}` from the latest durable evidence."
        if active_anchor == "baseline":
            return "Continue baseline only until one comparator is durably trustworthy enough for the next scientific step, then leave baseline immediately."
        if active_anchor == "idea":
            return (
                "Continue idea analysis and route selection until the next durable idea branch is submitted "
                "with `lineage_intent='continue_line'` or `lineage_intent='branch_alternative'`."
            )
        if active_anchor == "optimize":
            return "Continue the optimization loop from the current frontier, candidate pool, durable runs, and branch state."
        if active_anchor == "experiment":
            return "Continue the main experiment workflow from the current workspace, logs, and recorded evidence."
        if active_anchor == "analysis-campaign":
            return "Continue the analysis campaign from the current recorded slices and campaign state."
        if active_anchor == "write":
            return "Continue drafting or evidence-backed revision from the selected outline, draft, and paper state."
        if active_anchor == "finalize":
            return "Continue final consolidation, summary, and closure checks without ending the quest early."
        return "Continue the current quest from the latest durable state instead of stopping early."

    @staticmethod
    def _current_user_message_block(*, turn_reason: str, user_message: str) -> str:
        if str(turn_reason or "").strip() == "auto_continue":
            return "(no new user message for this turn; continue from active user requirements and durable state)"
        text = user_message.strip()
        return text or "(empty)"

    def _current_turn_attachments_block(
        self,
        *,
        quest_id: str,
        user_message: str,
        turn_reason: str,
    ) -> str:
        if str(turn_reason or "").strip() == "auto_continue":
            return "- none"
        latest_user = self._latest_user_message(quest_id)
        if not isinstance(latest_user, dict):
            return "- none"
        latest_content = str(latest_user.get("content") or "").strip()
        current_content = str(user_message or "").strip()
        if current_content and latest_content and latest_content != current_content:
            return "- none"

        attachments = [dict(item) for item in (latest_user.get("attachments") or []) if isinstance(item, dict)]
        if not attachments:
            return "- none"

        lines = [
            f"- attachment_count: {len(attachments)}",
            "- attachment_handling_rule: prefer readable sidecars such as extracted text, OCR text, or archive manifests when they exist; use raw binaries only when the readable sidecar is insufficient.",
            "- attachment_handling_rule_2: if the attachment belongs to a prior idea or experiment line, treat it as reference material rather than the active contract unless durable evidence promotes it.",
            "- attachment_handling_rule_3: do not assume raw image/video/audio binaries can be injected directly into the runner prompt; when no readable sidecar exists, treat the binary as non-inline reference material.",
        ]
        for index, item in enumerate(attachments[:6], start=1):
            preferred_read_path = (
                str(item.get("extracted_text_path") or item.get("ocr_text_path") or item.get("archive_manifest_path") or "").strip()
                or "none"
            )
            label = str(item.get("name") or item.get("file_name") or item.get("path") or item.get("url") or f"attachment-{index}").strip()
            kind = str(item.get("kind") or "attachment").strip()
            content_type = str(item.get("content_type") or item.get("mime_type") or "unknown").strip()
            binary_path = str(item.get("path") or "").strip() or "none"
            binary_hidden = preferred_read_path == "none" and binary_path != "none"
            lines.append(
                f"- attachment_{index}: label={label} | kind={kind} | content_type={content_type} | preferred_read_path={preferred_read_path} | raw_binary_path={'hidden' if binary_hidden else binary_path}"
            )
        if len(attachments) > 6:
            lines.append(f"- remaining_attachment_count: {len(attachments) - 6}")
        return "\n".join(lines)

    def _resume_context_spine_block(self, *, quest_id: str, quest_root: Path, snapshot: dict, turn_reason: str) -> str:
        if str(turn_reason or "").strip() != "auto_continue":
            return "- none"
        lines = [
            "- resume_spine_rule: on auto_continue turns, first continue from the latest durable user requirement, the latest assistant checkpoint, the latest run summary, the current workspace checklist/plan state, and recent memory cues instead of reconstructing intent from scratch",
        ]
        bash_running_count = int(((snapshot.get("counts") or {}).get("bash_running_count")) or 0)
        latest_bash_session = (
            dict((snapshot.get("summary") or {}).get("latest_bash_session") or {})
            if isinstance((snapshot.get("summary") or {}).get("latest_bash_session"), dict)
            else {}
        )
        lines.append(f"- active_bash_exec_run_count: {bash_running_count}")
        if latest_bash_session:
            command_preview = " ".join(str(latest_bash_session.get("command") or "").split())
            if len(command_preview) > 180:
                command_preview = command_preview[:177].rstrip() + "..."
            lines.append(
                f"- latest_bash_exec_session: bash_id={str(latest_bash_session.get('bash_id') or 'none')} | "
                f"status={str(latest_bash_session.get('status') or 'unknown')} | "
                f"command={command_preview or 'none'}"
            )
        latest_user = self._latest_user_message(quest_id)
        if latest_user is not None:
            preview = " ".join(str(latest_user.get("content") or "").split())
            if len(preview) > 320:
                preview = preview[:317].rstrip() + "..."
            lines.append(
                f"- latest_user_message: {str(latest_user.get('created_at') or 'unknown')} | "
                f"source={str(latest_user.get('source') or 'unknown')} | "
                f"reply_to={str(latest_user.get('reply_to_interaction_id') or 'none')} | "
                f"preview={preview or 'none'}"
            )
        latest_assistant = self._latest_assistant_message(quest_id)
        if latest_assistant is not None:
            preview = " ".join(str(latest_assistant.get("content") or "").split())
            if len(preview) > 360:
                preview = preview[:357].rstrip() + "..."
            lines.append(
                f"- latest_assistant_checkpoint: {str(latest_assistant.get('created_at') or 'unknown')} | "
                f"skill={str(latest_assistant.get('skill_id') or 'none')} | "
                f"run_id={str(latest_assistant.get('run_id') or 'none')} | "
                f"preview={preview or 'none'}"
            )
        latest_run = self._latest_run_result(quest_root)
        if latest_run is not None:
            preview = " ".join(str(latest_run.get("preview") or "").split())
            if len(preview) > 360:
                preview = preview[:357].rstrip() + "..."
            lines.append(
                f"- latest_run_result: {str(latest_run.get('completed_at') or 'unknown')} | "
                f"run_id={str(latest_run.get('run_id') or 'none')} | "
                f"exit_code={latest_run.get('exit_code') if latest_run.get('exit_code') is not None else 'none'} | "
                f"preview={preview or 'none'}"
            )
        lines.append("- workspace_checklist_rule: before changing route on auto_continue turns, reopen current workspace `CHECKLIST.md` / `REPRO_CHECKLIST.md` and continue from the latest completed and in-progress items.")
        lines.append("- workspace_plan_rule: if checklist state is ambiguous, reopen current workspace `PLAN.md` / `analysis_plan.md` before changing direction.")
        recent_memory = self.memory_service.list_recent(scope="quest", quest_root=quest_root, limit=3)
        if recent_memory:
            lines.append("- recent_memory_cues:")
            for item in recent_memory:
                title = str(item.get("title") or "memory").strip() or "memory"
                card_type = str(item.get("type") or "memory").strip() or "memory"
                excerpt = " ".join(str(item.get("excerpt") or "").split())
                if len(excerpt) > 200:
                    excerpt = excerpt[:197].rstrip() + "..."
                lines.append(f"  - [{card_type}] {title}: {excerpt or 'no excerpt'}")
        else:
            lines.append("- recent_memory_cues: none")
        lines.append("- resume_spine_conflict_rule: if these spine items conflict with newer durable files or artifacts, trust the newer durable state and update the summary rather than replaying the older plan verbatim")
        return "\n".join(lines)

    def _retry_recovery_block(self, retry_context: dict | None) -> str:
        if not isinstance(retry_context, dict) or not retry_context:
            return "- none"

        lines = [
            f"- retry_attempt: {retry_context.get('attempt_index') or '?'} / {retry_context.get('max_attempts') or '?'}",
            f"- previous_run_id: {retry_context.get('previous_run_id') or 'none'}",
            f"- previous_exit_code: {retry_context.get('previous_exit_code') if retry_context.get('previous_exit_code') is not None else 'none'}",
            f"- failure_kind: {retry_context.get('failure_kind') or 'unknown'}",
            f"- failure_summary: {retry_context.get('failure_summary') or 'none'}",
            "- retry_rule: continue from the current workspace state and current durable artifacts; do not restart the quest from scratch.",
            "- retry_rule_2: reuse prior search/tool/file progress unless the failure summary proves that progress is invalid or incomplete.",
        ]

        previous_output = str(retry_context.get("previous_output_text") or "").strip()
        if previous_output:
            lines.extend(["", "Previous model output tail:", previous_output])

        stderr_tail = str(retry_context.get("stderr_tail") or "").strip()
        if stderr_tail:
            lines.extend(["", "Previous stderr tail:", stderr_tail])

        recent_messages = retry_context.get("recent_messages")
        if isinstance(recent_messages, list) and recent_messages:
            lines.extend(["", "Recent message/reasoning traces:"])
            for item in recent_messages:
                if isinstance(item, str) and item.strip():
                    lines.append(f"- {item.strip()}")

        tool_progress = retry_context.get("tool_progress")
        if isinstance(tool_progress, list) and tool_progress:
            lines.extend(["", "Observed tool progress before failure:"])
            for item in tool_progress:
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("tool_name") or "tool").strip() or "tool"
                status = str(item.get("status") or "").strip()
                args = str(item.get("args") or "").strip()
                output = str(item.get("output") or "").strip()
                parts = [tool_name]
                if status:
                    parts.append(f"[{status}]")
                if args:
                    parts.append(f"args={args}")
                if output:
                    parts.append(f"output={output}")
                lines.append(f"- {' '.join(parts)}")

        workspace = retry_context.get("workspace_summary")
        if isinstance(workspace, dict) and workspace:
            lines.extend(["", "Current workspace summary:"])
            branch = str(workspace.get("branch") or "").strip()
            if branch:
                lines.append(f"- branch: {branch}")
            git_status = workspace.get("git_status")
            if isinstance(git_status, list) and git_status:
                lines.append("- git_status:")
                for item in git_status:
                    if isinstance(item, str) and item.strip():
                        lines.append(f"  - {item.strip()}")
            bash_sessions = workspace.get("bash_sessions")
            if isinstance(bash_sessions, list) and bash_sessions:
                lines.append("- bash_sessions:")
                for item in bash_sessions:
                    if not isinstance(item, dict):
                        continue
                    summary = " · ".join(
                        part
                        for part in (
                            str(item.get("bash_id") or "").strip(),
                            str(item.get("status") or "").strip(),
                            str(item.get("command") or "").strip(),
                        )
                        if part
                    )
                    if summary:
                        lines.append(f"  - {summary}")

        recent_artifacts = retry_context.get("recent_artifacts")
        if isinstance(recent_artifacts, list) and recent_artifacts:
            lines.extend(["", "Recent durable artifacts from the same quest:"])
            for item in recent_artifacts:
                if isinstance(item, str) and item.strip():
                    lines.append(f"- {item.strip()}")

        return "\n".join(lines)

    @staticmethod
    def _recovery_resume_block(*, snapshot: dict, turn_reason: str) -> str:
        if str(turn_reason or "").strip() != "auto_continue":
            return "- none"
        source = str(snapshot.get("last_resume_source") or "").strip()
        if not source.startswith("auto:daemon-recovery"):
            return "- none"
        lines = [
            f"- resume_source: {source}",
            f"- resumed_at: {snapshot.get('last_resume_at') or 'unknown'}",
            f"- abandoned_run_id: {snapshot.get('last_recovery_abandoned_run_id') or 'none'}",
            f"- recovery_summary: {snapshot.get('last_recovery_summary') or 'none'}",
            "- recovery_rule: this turn exists because the daemon/runtime previously died or stale running state was reconciled; first re-establish the current truth before continuing any old stage loop.",
            "- recovery_rule_2: if there is any new user message, handle that before blindly resuming the older subtask.",
            "- recovery_rule_3: do not assume the previous branch-local route is still the right immediate action until branch/workspace, run state, and user intent are checked together.",
        ]
        return "\n".join(lines)

    def _prompt_fragment(self, relative_path: str | Path, *, quest_root: Path | None = None) -> str:
        path = self._prompt_path(relative_path, quest_root=quest_root)
        return self._markdown_body(path)

    def _prompt_path(self, relative_path: str | Path, *, quest_root: Path | None = None) -> Path:
        normalized = Path(relative_path)
        if quest_root is not None:
            selected_version = str(self.prompt_version_selection or "").strip()
            if selected_version and selected_version not in {"latest", "current", "active"}:
                selected_root = self.skill_installer.resolve_prompt_version_root(quest_root, selected_version)
                if selected_root is None:
                    raise FileNotFoundError(
                        f"Prompt version `{selected_version}` is unavailable for quest `{quest_root.name}`."
                    )
                selected_path = selected_root / normalized
                if not selected_path.exists():
                    raise FileNotFoundError(
                        f"Prompt version `{selected_version}` does not include `{normalized.as_posix()}` for quest `{quest_root.name}`."
                    )
                return selected_path
            quest_path = quest_root / ".codex" / "prompts" / normalized
            if quest_path.exists():
                return quest_path
        return self.repo_root / "src" / "prompts" / normalized

    def _latest_user_message(self, quest_id: str) -> dict | None:
        for item in reversed(self.quest_service.history(quest_id, limit=80)):
            if str(item.get("role") or "") == "user":
                return item
        return None

    def _latest_assistant_message(self, quest_id: str) -> dict | None:
        for item in reversed(self.quest_service.history(quest_id, limit=120)):
            if str(item.get("role") or "") == "assistant":
                return item
        return None

    @staticmethod
    def _latest_run_result(quest_root: Path) -> dict[str, object] | None:
        runs_root = quest_root / ".ds" / "runs"
        if not runs_root.exists():
            return None
        candidates = [path for path in runs_root.glob("*/result.json") if path.is_file()]
        if not candidates:
            return None
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        payload = read_json(latest, {})
        if not isinstance(payload, dict):
            return None
        preview = (
            str(payload.get("output_text") or "").strip()
            or str(payload.get("stderr_text") or "").strip()
        )
        return {
            "run_id": latest.parent.name,
            "completed_at": str(payload.get("completed_at") or "").strip() or None,
            "exit_code": payload.get("exit_code"),
            "preview": preview,
        }

    def _skill_paths_block(self) -> str:
        lines = []
        for skill_id in current_standard_skills(self.repo_root):
            primary = (self.repo_root / "src" / "skills" / skill_id / "SKILL.md").resolve()
            lines.append(f"- {skill_id}: primary={primary}")
        return "\n".join(lines)

    def _companion_skill_paths_block(self) -> str:
        lines = []
        for skill_id in current_companion_skills(self.repo_root):
            primary = (self.repo_root / "src" / "skills" / skill_id / "SKILL.md").resolve()
            lines.append(f"- {skill_id}: primary={primary}")
        return "\n".join(lines)

    @staticmethod
    def _need_research_paper(snapshot: dict) -> bool:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = startup_contract.get("need_research_paper")
            if isinstance(value, bool):
                return value
        return True

    @staticmethod
    def _workspace_mode(snapshot: dict) -> str:
        value = str(snapshot.get("workspace_mode") or "").strip().lower()
        if value in {"copilot", "autonomous"}:
            return value
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("workspace_mode") or "").strip().lower()
            if value in {"copilot", "autonomous"}:
                return value
        return "autonomous"

    @staticmethod
    def _decision_policy(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("decision_policy") or "").strip().lower()
            if value in {"autonomous", "user_gated"}:
                return value
        return "user_gated"

    @staticmethod
    def _launch_mode(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("launch_mode") or "").strip().lower()
            if value in {"standard", "custom"}:
                return value
        return "standard"

    @staticmethod
    def _standard_profile(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("standard_profile") or "").strip().lower()
            if value in {"canonical_research_graph", "optimization_task"}:
                return value
        return "canonical_research_graph"

    @staticmethod
    def _custom_profile(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("custom_profile") or "").strip().lower()
            if value in {"continue_existing_state", "review_audit", "revision_rebuttal", "admin_ops", "settings_issue", "freeform"}:
                return value
        return "freeform"

    @staticmethod
    def _start_setup_session(snapshot: dict) -> dict[str, Any] | None:
        startup_contract = snapshot.get("startup_contract")
        if not isinstance(startup_contract, dict):
            return None
        payload = startup_contract.get("start_setup_session")
        if isinstance(payload, dict):
            return dict(payload)
        return None

    def _start_setup_session_block(self, snapshot: dict) -> str:
        payload = self._start_setup_session(snapshot) or {}
        locale = str(payload.get("locale") or "zh").strip().lower() or "zh"
        source = str(payload.get("source") or "manual").strip() or "manual"
        benchmark_context = payload.get("benchmark_context") if isinstance(payload.get("benchmark_context"), dict) else {}
        suggested_form = payload.get("suggested_form") if isinstance(payload.get("suggested_form"), dict) else {}
        lines = [
            f"- session_kind: autonomous_start_setup",
            f"- source: {source}",
            f"- preferred_language: {locale}",
            "- reply_language_rule: answer in the user's own language when it is clear from their latest message or the preferred language injected into this session.",
            self._local_daemon_api_block(include_benchstore=True),
            "- mission: help the user complete the autonomous start form and stop there; do not begin the real research workflow",
            "- context_first_rule: before asking the user for missing information, first read the current setup state and use the information already present in the form or benchmark context",
            "- start_setup_prepare_tool_rule: when you want to update the left-side form, prefer `artifact.prepare_start_setup_form(form_patch={...})` so the browser can patch the form automatically",
            "- start_setup_prepare_signature_rule: use `form_patch={...}` when the launch form itself changes, `session_patch={...}` when fit judgment or preview-plan state changes, and make sure at least one of them is non-empty; do not hide patch JSON inside `message`.",
            "- start_setup_session_patch_rule: when you learn or revise launch-fit judgment, missing confirmations, or the launch preview plan, write them back through the optional `session_patch={...}` argument on `artifact.prepare_start_setup_form(...)` so the browser can show them durably.",
            "- start_setup_session_shape_rule: keep `session_patch.fit_assessment` as an object with verdict, reason, confidence, and optional risk_notes; keep `session_patch.preview_plan.markdown` as structured user-facing Markdown, plus optional phases and risks arrays.",
            "- start_setup_tool_discovery_rule: before claiming the form writeback tool is unavailable, first try the runner-exposed tool name if it is shown (for example `mcp__artifact__prepare_start_setup_form`).",
            "- start_setup_context_rule: the current suggested form and benchmark context are already injected into this prompt; do not assume `memory.*` or other `artifact.*` helpers are available here",
            "- mode_fit_rule: explicitly judge whether the task is a good fit for autonomous mode, a provisional fit that still needs key confirmations, or should instead move to copilot / collaboration mode.",
            "- copilot_recommendation_rule: recommend copilot mode when the work cannot mainly run inside the computer system for long horizons, depends heavily on repeated human judgment, or is not primarily a method-optimization research loop.",
            "- preview_plan_rule: before you treat the setup as complete, submit a structured Markdown launch preview plan through `session_patch.preview_plan`; do not print that plan in the normal visible reply.",
            "- preview_plan_template_rule: when enough information exists, structure the plan like a Deep Research plan: conclusion and mode recommendation, key questions the main agent should verify, materials/sources table, future execution steps, risks/confirmations, and conditions that should switch the user to copilot mode.",
            "- preview_plan_reviewability_rule: keep the Markdown preview compact enough for the user to review before launch; it is a confirmation artifact, not a hidden scheduler trace.",
            "- no_self_execution_rule: the preview plan is explanatory only. Do not start baseline work, experiments, analysis campaigns, or paper drafting from this setup session.",
            "- research_mainline_rule: when the user wants a real research project rather than a baseline-only task, the launch form should make the mainline explicit: baseline is only the starting point, then autonomous optimization and repeated performance improvement, then robust surpassing of strong baselines / SoTA with novelty, then analysis experiments, then literature / figures / paper-writing collaboration.",
            "- baseline_not_endpoint_rule: do not frame the mission as 'reproduce a baseline and stop' unless the user explicitly wants a baseline-only task.",
            "- novelty_confirmation_rule: if the user expects paper-level research or method contribution, explicitly confirm that the goal is not only to beat the baseline but to do so with a sufficiently novel and defensible method direction.",
            "- sequencing_confirmation_rule: if the long-term plan is still unclear, ask the user to confirm the intended sequence among baseline, optimization beyond SoTA, analysis experiments, and later literature / figure / writing work.",
            "- benchmark_context_source_rule: if `benchmark_context.raw_payload` exists, treat it as the full benchmark description file for this setup session rather than relying only on the shorter summary fields.",
            "- start_setup_context_injection_rule: the current setup session state is injected below by the system; use it as hidden planning context and never ask the user to paste or repeat this context.",
            "- start_setup_user_message_rule: treat the latest user message as the user's literal text only. Do not expect hidden planning XML or JSON to be embedded in the user message.",
            "- aisb_selection_rule: when the user asks you to choose or recommend a task, prefer the existing AISB / BenchStore catalog first instead of asking the user to invent a task from scratch.",
            "- aisb_selection_path: use `bash_exec(...)` against the injected local daemon BenchStore endpoints to inspect current catalog entries, then recommend the best fit based on both the user's stated needs and the current device boundary.",
            "- aisb_selection_truncation_rule: if you inspect BenchStore output through `head`, `tail`, `sed -n`, or another clipped shell window, explicitly treat it as truncated / partial output and never infer the global entry count from that preview alone.",
            "- aisb_selection_count_rule: before claiming how many BenchStore entries exist, read an explicit count such as `total`, `count`, or `items | length` from the daemon API result.",
            "- aisb_selection_output_rule: when multiple AISB candidates fit, summarize the top 1 to 3 options briefly, recommend one first, and then patch the form toward that recommendation.",
            "- performance_fit_rule: combine the user's requested task shape with the current machine boundary; if the machine is weak, prefer API-only, low-compute, short-cycle, and benchmark-faithful routes.",
            "- output_rule: do not emit fenced `start_setup_patch` or JSON patch blocks in the visible reply. If the prepare tool is unavailable, ask a short plain-language question or say the setup tool is temporarily unavailable instead of printing structured data.",
            "- tool_submission_rule: submit structured form/session data through `artifact.prepare_start_setup_form(...)`; never put JSON patches or structured drafts in the visible assistant message.",
            "- start_setup_prepare_schema_summary:",
            "```json",
            json.dumps(
                {
                    "tool": "prepare_start_setup_form",
                    "runner_namespaced_tool": "mcp__artifact__prepare_start_setup_form",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "form_patch": {
                                "type": "object",
                                "description": "Optional top-level form patch containing only the launch-form fields that should change.",
                            },
                            "session_patch": {
                                "type": "object",
                                "description": "Optional durable setup-session metadata such as fit assessment, recommended workspace mode, missing confirmations, preview plan, and materials summary.",
                            },
                            "message": {
                                "type": "string",
                                "description": "Optional short user-facing note.",
                            },
                            "comment": {
                                "type": ["string", "object", "null"],
                                "description": "Optional internal note.",
                            },
                        },
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "- patch_rule: keep the patch small; only include fields that truly need to change, and do not emit an empty `form_patch` + empty `session_patch` pair",
            "- session_patch_fields_rule: use `session_patch.fit_assessment`, `session_patch.recommended_workspace_mode`, `session_patch.launch_readiness`, `session_patch.missing_confirmations`, `session_patch.preview_plan`, and `session_patch.materials_summary` when those values become clear enough to persist durably.",
            "- no_black_talk_rule: use natural user-facing language and avoid internal words like route, taxonomy, stage, slice, trace, checkpoint, or contract unless the user explicitly asks for them",
            "- no_research_execution_rule: do not start baseline work, experiments, analysis campaigns, or paper drafting in this setup session",
            "- user_choice_rule: if the user already filled the form clearly enough, say so and avoid unnecessary follow-up questions",
            "- ask_rule: only ask short questions when a missing answer would materially change what gets submitted",
            "- mandatory_confirmation_rule: do not guess critical operator-controlled resources. If GPU scope, GPU count, explicit GPU ids, external LLM/API usage, API keys, tokens, paid-call permission, large-download permission, or privacy boundaries would change the launch plan, you must ask the user to confirm them before treating the form as launch-ready.",
            "- credential_confirmation_rule: if the task or benchmark would rely on an external API key, token, or account and that credential is not already explicitly available in context, proactively ask the user whether they want to provide it or switch to a different route.",
            "- gpu_confirmation_rule: do not assume every detected GPU is available. If the allowed GPU scope is unclear and local GPU usage matters, ask the user how many GPUs or which GPU ids may be used.",
            "- gated_patch_rule: if critical resource confirmations are still missing, patch only safe partial fields through the tool, set `launch_readiness=needs_confirmation`, and ask questions only; do not show a provisional draft in prose.",
            "- question_categories: when user input is incomplete, ask at most for these practical categories: task goal, current materials, runtime limits, whether they prefer paper-facing delivery or result-first delivery, and whether the real target is baseline-only or iterative performance improvement beyond SoTA with novelty.",
            "- field_mapping_rule: treat title as a short project name, goal as the real mission, baseline_urls as baseline/code/data inputs, paper_urls as paper or benchmark references, runtime_constraints as hard limits, objectives as the first 2-4 near-term outcomes, and custom_brief as extra preferences",
        ]
        if benchmark_context:
            lines.extend(
                [
                    "- benchmark_context_json:",
                    "```json",
                    json.dumps(benchmark_context, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        else:
            lines.append("- benchmark_context_json: {}")
        if suggested_form:
            lines.extend(
                [
                    "- current_suggested_form_json:",
                    "```json",
                    json.dumps(suggested_form, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        else:
            lines.append("- current_suggested_form_json: {}")
        setup_state = {
            "recommended_workspace_mode": payload.get("recommended_workspace_mode") or "unknown",
            "launch_readiness": payload.get("launch_readiness") or "unknown",
            "fit_assessment": payload.get("fit_assessment") if isinstance(payload.get("fit_assessment"), dict) else None,
            "missing_confirmations": payload.get("missing_confirmations") if isinstance(payload.get("missing_confirmations"), list) else [],
            "materials_summary": payload.get("materials_summary") if isinstance(payload.get("materials_summary"), list) else [],
            "preview_plan": payload.get("preview_plan") if isinstance(payload.get("preview_plan"), dict) else None,
        }
        lines.extend(
            [
                "- current_start_setup_state_json:",
                "```json",
                json.dumps(setup_state, ensure_ascii=False, indent=2),
                "```",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _baseline_execution_policy(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("baseline_execution_policy") or "").strip().lower()
            if value in {"auto", "must_reproduce_or_verify", "reuse_existing_only", "skip_unless_blocking"}:
                return value
        return "auto"

    @staticmethod
    def _baseline_source_mode(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("baseline_source_mode") or "").strip().lower()
            if value in {
                "auto",
                "verify_local_existing",
                "attach_registry_baseline",
                "reproduce_from_source",
                "repair_existing_baseline",
                "skip_until_blocking",
            }:
                return value
        return "auto"

    @staticmethod
    def _execution_start_mode(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("execution_start_mode") or "").strip().lower()
            if value in {"plan_then_execute", "execute_immediately"}:
                return value
        return "execute_immediately"

    @staticmethod
    def _baseline_acceptance_target(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("baseline_acceptance_target") or "").strip().lower()
            if value in {"comparison_ready", "paper_repro_ready", "registry_publishable"}:
                return value
        return "comparison_ready"

    @staticmethod
    def _review_followup_policy(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("review_followup_policy") or "").strip().lower()
            if value in {"audit_only", "auto_execute_followups", "user_gated_followups"}:
                return value
        return "audit_only"

    @staticmethod
    def _manuscript_edit_mode(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("manuscript_edit_mode") or "").strip().lower()
            if value in {"none", "copy_ready_text", "latex_required"}:
                return value
        return "none"

    def _settings_issue_session_block(self, snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if not isinstance(startup_contract, dict):
            return "- none"
        lines = [
            self._local_daemon_api_block(include_benchstore=True, include_admin=True),
            f"- local_repo_root: {self.repo_root.resolve()}",
            f"- launcher_entry: {(self.repo_root / 'bin' / 'ds.js').resolve()}",
            f"- python_runtime_root: {(self.repo_root / 'src' / 'deepscientist').resolve()}",
            f"- web_ui_root: {(self.repo_root / 'src' / 'ui').resolve()}",
            "- settings_issue_context_rule: the operator message history is expanded explicitly below; absorb that full conversation before asking for clarification.",
            "- settings_issue_issue_rule: the final output should still converge on `artifact.prepare_github_issue(...)`, but the draft must reflect the real daemon/settings state you verified.",
            "- settings_issue_tool_schema_summary:",
            "```json",
            json.dumps(
                {
                    "tool": "prepare_github_issue",
                    "runner_namespaced_tool": "mcp__artifact__prepare_github_issue",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "user_notes": {"type": "string"},
                            "include_doctor": {"type": "boolean"},
                            "include_logs": {"type": "boolean"},
                            "open_settings_page": {"type": "boolean"},
                            "comment": {"type": ["string", "object", "null"]},
                        },
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
        ]
        return "\n".join(lines)

    def _research_delivery_policy_block(self, snapshot: dict) -> str:
        start_setup_session = self._start_setup_session(snapshot)
        if start_setup_session:
            locale = str(start_setup_session.get("locale") or "zh").strip().lower() or "zh"
            lines = [
                "- workspace_mode: start_setup",
                "- delivery_goal: fill the autonomous start form well enough that the user can launch confidently",
                "- hard_boundary: this is a setup session, not the real research session",
                "- start_setup_rule: organize the user's task, materials, and runtime limits into a clean launch-ready form",
                "- mode_recommendation_rule: explicitly judge whether autonomous mode is truly the right fit or whether copilot / collaboration mode is safer.",
                "- launch_preview_rule: only submit the preview through `session_patch.preview_plan` after launch readiness is `ready`; do not print it in the normal reply.",
                "- patch_protocol: use `artifact.prepare_start_setup_form(form_patch={...}, session_patch={...})` for all structured form/session updates; do not use fenced `start_setup_patch` blocks in the visible reply",
                "- completion_rule: once the form is good enough to launch, say so clearly and stop asking for more unless the user requests changes",
                "- directness_rule: if the current information is already sufficient, tell the user they can launch now",
                "- ask_rule: only ask short practical questions that directly affect what gets submitted",
                "- critical_confirmation_rule: treat GPU scope, explicit GPU ids, API keys, external credentials, paid-service permission, large-download permission, and privacy boundaries as mandatory confirmations when they would materially affect launch readiness; do not silently assume them.",
            ]
            if locale.startswith("zh"):
                lines.extend(
                    [
                        "- example_hint: 可以自然说“还差 2 件事就可以判断是否启动”；不要说“整理出草案”，也不要在正文展示草案。",
                    ]
                )
            else:
                lines.extend(
                    [
                        "- example_hint: natural lines like 'Two details remain before launch' are preferred; do not say you drafted a version or show draft content in prose.",
                    ]
                )
            return "\n".join(lines)
        if self._workspace_mode(snapshot) == "copilot":
            return "\n".join(
                [
                    "- workspace_mode: copilot",
                    "- delivery_goal: complete the user-requested unit of work instead of forcing the full research graph by default.",
                    "- task_scope_rule: arbitrary research tasks such as reading, coding, debugging, experiment design, run inspection, analysis, writing, and planning can all be handled directly in this mode.",
                    "- autonomy_boundary: only expand into longer autonomous continuation when the user explicitly asks for end-to-end or unattended progress.",
                    "- routing_rule: open only the skills actually needed for the current request.",
                    "- durability_rule: keep important plan, evidence, decisions, and outputs durable in quest files or artifacts so later turns can resume cleanly.",
                    "- completion_rule: after the requested unit is complete, summarize what changed and stop instead of auto-continuing.",
                ]
            )
        need_research_paper = self._need_research_paper(snapshot)
        launch_mode = self._launch_mode(snapshot)
        standard_profile = self._standard_profile(snapshot)
        custom_profile = self._custom_profile(snapshot)
        baseline_execution_policy = self._baseline_execution_policy(snapshot)
        baseline_source_mode = self._baseline_source_mode(snapshot)
        execution_start_mode = self._execution_start_mode(snapshot)
        baseline_acceptance_target = self._baseline_acceptance_target(snapshot)
        review_followup_policy = self._review_followup_policy(snapshot)
        manuscript_edit_mode = self._manuscript_edit_mode(snapshot)
        lines = [
            f"- need_research_paper: {need_research_paper}",
            f"- launch_mode: {launch_mode}",
            f"- standard_profile: {standard_profile if launch_mode == 'standard' else 'n/a'}",
            f"- custom_profile: {custom_profile if launch_mode == 'custom' else 'n/a'}",
            f"- baseline_source_mode: {baseline_source_mode}",
            f"- execution_start_mode: {execution_start_mode}",
            f"- baseline_acceptance_target: {baseline_acceptance_target}",
            f"- review_followup_policy: {review_followup_policy if custom_profile == 'review_audit' else 'n/a'}",
            f"- baseline_execution_policy: {baseline_execution_policy if launch_mode == 'custom' else 'n/a'}",
            f"- manuscript_edit_mode: {manuscript_edit_mode if custom_profile in {'review_audit', 'revision_rebuttal'} else 'n/a'}",
            f"- delivery_mode: {'paper_required' if need_research_paper else 'algorithm_first'}",
            "- requested_skill_rule: stage-specific execution detail lives in the requested skill; this block only adds runtime launch policy.",
            "- idea_stage_rule: every accepted idea submission should normally create a new branch/worktree and a new user-visible research node.",
            "- lineage_rule: normal idea routing uses exactly two lineage intents: `continue_line` creates a child of the current active branch; `branch_alternative` creates a sibling-like branch from the current branch's parent foundation.",
            "- revise_rule: `artifact.submit_idea(mode='revise', ...)` is maintenance-only compatibility for the same branch and should not be the default research-route mechanism.",
            "- post_main_result_rule: after every `artifact.record_main_experiment(...)`, first interpret the measured result and only then choose the next route.",
            "- foundation_selection_rule: for a genuinely new idea round, default to the current research head but feel free to choose another durable foundation when it is cleaner or stronger; inspect `artifact.list_research_branches(...)` first when the best foundation is not obvious.",
        ]
        if execution_start_mode == "plan_then_execute":
            lines.extend(
                [
                    "- plan_first_entry_rule: this execution-start preference applies to the startup baseline route only. Before heavy baseline reproduction or expensive baseline setup at quest entry, first produce a bounded execution plan and wait for explicit user approval instead of executing immediately.",
                ]
            )
        if baseline_source_mode == "verify_local_existing":
            lines.extend(
                [
                    "- baseline_source_rule: if local code or a local service already exists and the metric path is concrete, verify that local existing system first instead of defaulting into from-scratch source reproduction.",
                ]
            )
        elif baseline_source_mode == "attach_registry_baseline":
            lines.extend(
                [
                    "- baseline_source_rule: prefer attaching and verifying a reusable registered baseline before considering a full source reproduction path.",
                ]
            )
        elif baseline_source_mode == "reproduce_from_source":
            lines.extend(
                [
                    "- baseline_source_rule: treat source reproduction as the expected startup baseline path unless a clearly stronger local shortcut becomes trustworthy after inspection.",
                ]
            )
        elif baseline_source_mode == "repair_existing_baseline":
            lines.extend(
                [
                    "- baseline_source_rule: prefer repairing the stale existing baseline before restarting from a clean-slate reproduction.",
                ]
            )
        elif baseline_source_mode == "skip_until_blocking":
            lines.extend(
                [
                    "- baseline_source_rule: do not front-load baseline work at quest entry unless the missing comparator is actually blocking the next scientific step.",
                ]
            )
        else:
            lines.extend(
                [
                    "- baseline_source_rule: auto mode prefers verify/reuse/attach before source reproduction.",
                ]
            )
        if baseline_acceptance_target == "comparison_ready":
            lines.extend(
                [
                    "- baseline_acceptance_rule: once the comparator is trustworthy enough for the next scientific step, move forward immediately. Prefer attach / import / verify-local-existing over full reproduction whenever those lighter routes already satisfy `comparison_ready`, and do not escalate to heavier baseline work without naming one explicit unresolved comparison risk.",
                ]
            )
        elif baseline_acceptance_target == "paper_repro_ready":
            lines.extend(
                [
                    "- baseline_acceptance_rule: keep startup baseline work primary until the comparator is strong enough to support paper-facing claims, not just one quick comparison.",
                ]
            )
        else:
            lines.extend(
                [
                    "- baseline_acceptance_rule: treat the startup baseline as incomplete until it is reusable and clean enough to publish as a registry-quality baseline package.",
                ]
            )

        if launch_mode == "custom":
            lines.extend(
                [
                    "- custom_launch_rule: do not force the canonical full-research path when the custom startup contract is narrower.",
                    "- custom_context_rule: treat `entry_state_summary`, `review_summary`, `review_materials`, and `custom_brief` as active runtime context rather than decorative metadata.",
                ]
            )
            if custom_profile == "continue_existing_state":
                lines.extend(
                    [
                        "- existing_state_entry_rule: if reusable baselines, runs, drafts, or review assets already exist, open `intake-audit` before restarting baseline discovery or new experiments.",
                        "- reuse_first_rule: trust-rank and reconcile existing assets before deciding to rerun anything costly.",
                    ]
                )
            elif custom_profile == "review_audit":
                lines.extend(
                    [
                        "- review_entry_rule: treat the current draft/paper state as the active contract; open `review` before more writing or finalization.",
                        "- review_routing_rule: if that audit finds real evidence gaps, route to `analysis-campaign`, `baseline`, `scout`, or `write` instead of polishing blindly.",
                    ]
                )
                if review_followup_policy == "auto_execute_followups":
                    lines.extend(
                        [
                            "- review_followup_rule: after the audit artifacts are durable, continue automatically into the required experiments, manuscript deltas, and review-closure work instead of stopping at the audit report.",
                        ]
                    )
                elif review_followup_policy == "user_gated_followups":
                    lines.extend(
                        [
                            "- review_followup_rule: after the audit artifacts are durable, package the next expensive follow-up step into one structured decision instead of continuing silently.",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            "- review_followup_rule: stop after the durable audit artifacts and route recommendation unless the user later asks for execution follow-up.",
                        ]
                    )
            elif custom_profile == "revision_rebuttal":
                lines.extend(
                    [
                        "- rebuttal_entry_rule: treat reviewer comments and the current paper state as the active contract; open `rebuttal` before ordinary writing.",
                        "- rebuttal_routing_rule: route supplementary reviewer-facing evidence through `analysis-campaign` and manuscript deltas through `write`, but let `rebuttal` orchestrate that mapping.",
                    ]
                )
            elif custom_profile == "admin_ops":
                lines.extend(
                    [
                        "- admin_ops_entry_rule: this is an administrator diagnosis / repair session for the local DeepScientist runtime rather than an ordinary end-user research quest.",
                        "- admin_ops_scope_rule: treat `startup_contract.admin_session`, `entry_state_summary`, `custom_brief`, and `review_materials` as the active incident context packet.",
                        "- admin_ops_truth_rule: prefer documented daemon APIs, durable quest files, config files, connector state, runtime logs, and bounded `bash_exec(...)` inspection over speculation.",
                        "- admin_ops_repair_rule: diagnose first, then apply the smallest safe fix allowed by the repair policy; avoid direct mutation of undocumented `.ds/*` internals when a safer route exists.",
                        "- admin_ops_output_rule: separate diagnosis, fix, verification, and residual risk; keep summaries operational and explicit about blast radius.",
                    ]
                )
            elif custom_profile == "settings_issue":
                lines.extend(
                    [
                        "- settings_issue_entry_rule: this is a settings-only GitHub issue drafting session rather than a general research or admin repair session.",
                        "- settings_issue_tool_surface_rule: prefer `artifact.prepare_github_issue(...)` for the final issue draft, but rely on the injected daemon API context and explicit message history first so the issue reflects the full settings conversation.",
                        "- settings_issue_bash_rule: `bash_exec(...)` remains available for bounded local inspection or daemon checks when needed, and should be used to verify live settings/runtime behavior before the final draft.",
                        "- settings_issue_execution_rule: collect the issue summary and user notes, call `artifact.prepare_github_issue(...)`, and rely on the browser prefill flow instead of hand-writing a separate issue body when the tool can provide it.",
                    ]
                )
            else:
                lines.extend(
                    [
                        "- freeform_entry_rule: prefer the custom brief over the default stage order and open only the skills actually needed.",
                    ]
                )
            if baseline_execution_policy == "must_reproduce_or_verify":
                lines.extend(
                    [
                        "- baseline_execution_rule: before reviewer-linked follow-up work, explicitly verify or recover the rebuttal-critical baseline/comparator instead of assuming the stored evidence is still trustworthy.",
                    ]
                )
            elif baseline_execution_policy == "reuse_existing_only":
                lines.extend(
                    [
                        "- baseline_execution_rule: prefer the existing trusted baseline/results and do not rerun them unless you find concrete inconsistency, corruption, or missing-evidence problems.",
                    ]
                )
            elif baseline_execution_policy == "skip_unless_blocking":
                lines.extend(
                    [
                        "- baseline_execution_rule: do not spend time on baseline reruns by default; only open `baseline` if a named review/rebuttal issue truly depends on a missing comparator or unusable prior evidence.",
                    ]
                )
            if manuscript_edit_mode == "latex_required":
                lines.extend(
                    [
                        "- manuscript_edit_rule: when manuscript revision is needed, treat the provided LaTeX tree or `paper/latex/` as the authoritative writing surface; if LaTeX source is unavailable, produce LaTeX-ready replacement text and make that blocker explicit instead of pretending the manuscript was edited.",
                    ]
                )
            elif manuscript_edit_mode == "copy_ready_text":
                lines.extend(
                    [
                        "- manuscript_edit_rule: when manuscript revision is needed, provide section-level copy-ready replacement text and explicit deltas even if no LaTeX source is available.",
                    ]
                )
        elif standard_profile == "optimization_task":
            lines.extend(
                [
                    "- standard_optimization_entry_rule: this standard entry is explicitly optimization-only; treat repeated implementation attempts and measured main-experiment results as the primary progress loop.",
                    "- standard_optimization_no_analysis_default: do not route into `analysis-campaign` by default; only run extra analysis when it directly validates a suspected win, disambiguates a frontier decision, or exposes a concrete failure mode that changes the next optimization move.",
                    "- standard_optimization_no_writing_default: do not route into `write`, `review`, or `finalize` while this optimization task profile remains active unless the user explicitly broadens scope.",
                    "- standard_optimization_iteration_rule: prefer more justified optimization attempts, branch promotion, or frontier cleanup over paper-facing packaging.",
                ]
            )
        if need_research_paper:
            lines.extend(
                [
                    "- delivery_goal: the default paper-facing goal is at least one paper-like deliverable, but do not force every later stage when the nearer gate for this turn is already open.",
                    "- main_result_rule: a strong main experiment is evidence, not the endpoint; often continue into analysis, writing, or strengthening work when the current contract really needs it.",
                    "- paper_branch_rule: writing should normally continue on a dedicated `paper/*` branch/worktree derived from the evidence line rather than mutating the evidence branch itself.",
                    "- review_gate_rule: when a paper draft becomes substantial, consider opening `review` for an independent skeptical audit before calling it done; if that audit finds serious gaps, route to analysis, baseline, scout, or more writing instead of stopping.",
                    "- stop_rule: do not stop with only an improved algorithm or isolated run logs unless the user explicitly narrows scope.",
                ]
            )
        else:
            lines.extend(
                [
                    "- delivery_goal: the quest should pursue the strongest justified algorithmic result rather than paper packaging.",
                    "- optimization_object_rule: distinguish candidate briefs, durable optimization lines, and implementation-level optimization candidates; do not treat them as one object type.",
                    "- optimization_frontier_rule: before major route selection in algorithm-first work, read `artifact.get_optimization_frontier(...)` and treat the current frontier as the primary optimize-state summary.",
                    "- optimization_promotion_rule: `submission_mode='candidate'` is branchless pre-promotion state, while `submission_mode='line'` is a committed durable line with a branch/worktree.",
                    "- main_result_rule: use each measured main-experiment result to decide whether to create a `continue_line` child branch, create a `branch_alternative` sibling-like branch, run more analysis, or stop.",
                    "- no_paper_rule: do not default into `artifact.submit_paper_outline(...)`, `artifact.submit_paper_bundle(...)`, or `finalize` while this mode remains active.",
                    "- autonomy_rule: choose the next optimization foundation from durable evidence such as baseline state, the current research head, and recent main-experiment results; do not routinely ask the user to choose that.",
                    "- persistence_rule: even without paper writing, keep all major decisions, runs, evidence, failures, and conclusions durable so the next round can build on them cleanly.",
                ]
            )
        return "\n".join(lines)

    def _optimization_frontier_block(self, snapshot: dict, quest_root: Path) -> str:
        active_anchor = str(snapshot.get("active_anchor") or "").strip().lower()
        if self._need_research_paper(snapshot) and active_anchor != "optimize":
            return "- not primary in the current delivery mode"

        try:
            from ..artifact import ArtifactService

            payload = ArtifactService(self.home).get_optimization_frontier(quest_root)
        except Exception:
            payload = {"ok": False}

        frontier = (
            dict(payload.get("optimization_frontier") or {})
            if isinstance(payload, dict) and isinstance(payload.get("optimization_frontier"), dict)
            else {}
        )
        if not frontier:
            return "- unavailable"

        best_branch = dict(frontier.get("best_branch") or {}) if isinstance(frontier.get("best_branch"), dict) else {}
        best_run = dict(frontier.get("best_run") or {}) if isinstance(frontier.get("best_run"), dict) else {}
        backlog = dict(frontier.get("candidate_backlog") or {}) if isinstance(frontier.get("candidate_backlog"), dict) else {}
        next_actions = [str(item).strip() for item in (frontier.get("recommended_next_actions") or []) if str(item).strip()]
        stagnant = frontier.get("stagnant_branches") or []
        fusion = frontier.get("fusion_candidates") or []
        local_attempts = [
            dict(item)
            for item in (frontier.get("best_branch_recent_candidates") or [])
            if isinstance(item, dict)
        ]

        lines = [
            f"- frontier_mode: {str(frontier.get('mode') or 'unknown')}",
            f"- frontier_reason: {str(frontier.get('frontier_reason') or 'none')}",
            f"- frontier_best_branch: {str(best_branch.get('branch_name') or best_branch.get('branch_no') or 'none')}",
            f"- frontier_best_run: {str(best_run.get('run_id') or 'none')}",
            f"- frontier_candidate_briefs: {int(backlog.get('candidate_brief_count') or 0)}",
            f"- frontier_active_implementation_candidates: {int(backlog.get('active_implementation_candidate_count') or 0)}",
            f"- frontier_failed_implementation_candidates: {int(backlog.get('failed_implementation_candidate_count') or 0)}",
            f"- frontier_stagnant_branch_count: {len([item for item in stagnant if isinstance(item, dict)])}",
            f"- frontier_fusion_candidate_count: {len([item for item in fusion if isinstance(item, dict)])}",
            "- optimization_frontier_rule: in algorithm-first work, treat this block as the primary route-selection surface before relying on paper-facing state.",
        ]
        if local_attempts:
            parts: list[str] = []
            for item in local_attempts[-3:]:
                summary_bits = [
                    str(item.get("candidate_id") or "").strip() or "candidate",
                    str(item.get("status") or "").strip() or "unknown",
                    str(item.get("strategy") or "").strip() or None,
                    str(item.get("mechanism_family") or "").strip() or None,
                    str(item.get("failure_kind") or "").strip() or None,
                ]
                parts.append(" / ".join(bit for bit in summary_bits if bit))
            lines.append(f"- frontier_same_line_local_attempt_memory: {' | '.join(parts)}")
            lines.append(
                "- optimization_local_memory_rule: before seed, loop, or debug work on the leading line, inspect this same-line local attempt memory so you do not repeat a near-duplicate change blindly."
            )
        if next_actions:
            lines.append(f"- frontier_next_actions: {' | '.join(next_actions[:3])}")
        return "\n".join(lines)

    def _interaction_style_block(self, *, default_locale: str, user_message: str, snapshot: dict) -> str:
        normalized_locale = str(default_locale or "").lower()
        chinese_turn = normalized_locale.startswith("zh") or bool(re.search(r"[\u4e00-\u9fff]", user_message))
        if self._workspace_mode(snapshot) == "copilot":
            lines = [
                f"- configured_default_locale: {default_locale}",
                f"- current_turn_language_bias: {'zh' if chinese_turn else 'en'}",
                "- collaboration_mode: user-directed copilot",
                "- freeform_task_rule: if the user asks for a concrete research task, solve that task directly before introducing stage-routing language.",
                "- requested_skill_hint_rule: in copilot mode, treat `requested_skill` as a lightweight routing hint, not as an instruction to default into `decision` for ordinary direct tasks.",
                "- turn_self_routing_rule: before substantial work, classify the current turn as `direct_answer`, `direct_action`, `stage_continue`, or `route_decision`.",
                "- direct_answer_rule: if the user mainly wants an answer or clarification, answer with the narrowest sufficient context and avoid reading large stage state unless needed.",
                "- direct_action_rule: if the user mainly wants one concrete task, execute the smallest useful unit first and do not expand into background research continuation in the same turn unless the user asked for it.",
                "- stage_continue_rule: if the user mainly wants the quest to keep moving, continue from the active durable stage state after acknowledging the request.",
                "- route_decision_rule: switch into `decision`-style reasoning only when safe continuation depends on a real route, scope, cost, branch, or scientific-direction judgment.",
                "- decision_skill_escalation_rule: if a turn upgrades into `route_decision`, explicitly read the `decision` skill before substantial route-changing work.",
                "- mailbox_protocol: artifact.interact(include_recent_inbound_messages=True) remains the queued human-message mailbox and should be checked whenever human continuity matters.",
                "- planning_rule: before non-trivial execution, make the immediate plan explicit and keep the first step small.",
                "- tool_rule: use memory for durable recall, artifact for quest state and git-aware research operations, and bash_exec for terminal execution.",
                "- copilot_sop_rule: classify the request first, choose the narrowest correct tool path, execute the smallest useful unit, persist the important result, then answer plainly.",
                "- shell_tool_mandate: **for any shell, CLI, Python, bash, node, git, npm, uv, or environment command execution, use `bash_exec(...)`; do not use native `shell_command` or Codex `command_execution`.**",
                "- git_tool_mandate: for git work inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.",
                "- git_test_rule: if the user wants a generic git smoke test rather than a quest-repo mutation, use `bash_exec(...)` in an isolated scratch repository.",
                "- decision_entry_rule: use `decision` only for real route, scope, cost, branch, or scientific-direction judgments; do not default to it for ordinary repo, code, environment, or execution tasks.",
                "- micro_task_stop_rule: after finishing a `direct_answer` or `direct_action` turn, report the result plainly and wait instead of auto-continuing.",
                "- stop_rule: once the current requested unit is done, send a concise update and wait for the next message or `/resume`.",
                "- escalation_rule: if a route change materially affects cost, scope, or scientific direction, ask before proceeding.",
                "- connector_style_rule: connector-facing tone and report style live in the active connector contract rather than in this runtime block.",
            ]
            return "\n".join(lines)
        bound_conversations = snapshot.get("bound_conversations") or []
        need_research_paper = self._need_research_paper(snapshot)
        decision_policy = self._decision_policy(snapshot)
        launch_mode = self._launch_mode(snapshot)
        standard_profile = self._standard_profile(snapshot)
        custom_profile = self._custom_profile(snapshot)
        lines = [
            f"- configured_default_locale: {default_locale}",
            f"- current_turn_language_bias: {'zh' if chinese_turn else 'en'}",
            f"- bound_conversation_count: {len(bound_conversations)}",
            f"- decision_policy: {decision_policy}",
            f"- launch_mode: {launch_mode}",
            f"- standard_profile: {standard_profile if launch_mode == 'standard' else 'n/a'}",
            f"- custom_profile: {custom_profile if launch_mode == 'custom' else 'n/a'}",
            "- collaboration_mode: long-horizon, continuity-first, artifact-aware",
            "- user_turn_self_routing_rule: on a fresh user message, first classify the turn as `direct_answer`, `direct_action`, `stage_continue`, or `route_decision` before reading additional skills or large quest context.",
            "- direct_answer_rule: if the user mainly wants an answer or clarification, answer with the narrowest sufficient context and avoid reading large stage state unless needed.",
            "- direct_action_rule: if the user mainly wants one concrete task, execute the smallest useful unit first and do not silently expand into broader autonomous continuation in the same turn unless the user asked for it.",
            "- stage_continue_rule: if the user is clearly asking to continue quest progress, resume from the active durable stage state.",
            "- route_decision_rule: open `decision`-style reasoning only when safe continuation genuinely depends on a real route, scope, cost, branch, or scientific-direction judgment.",
            "- decision_skill_escalation_rule: if a fresh user-message turn upgrades into `route_decision`, explicitly read the `decision` skill before substantial route-changing work.",
            "- interaction_protocol: first message may be plain conversation; after that, treat artifact.interact threads and mailbox polls as the main continuity spine across TUI, web, and connectors",
            "- shared_interaction_contract_precedence: use the shared interaction contract as the default user-facing cadence; the rules below add runtime-specific execution behavior instead of restating the same chat cadence",
            "- shell_tool_mandate: **native `shell_command` / `command_execution` is forbidden; all shell-like execution must use `bash_exec(...)`.**",
            "- mailbox_protocol: artifact.interact(include_recent_inbound_messages=True) is the queued human-message mailbox; when it returns user text, treat that input as higher priority than background subtasks until it has been acknowledged",
            "- acknowledgment_protocol: after artifact.interact returns any human message, immediately send one substantive artifact.interact(...) follow-up; if the active connector runtime already emitted a transport-level receipt acknowledgement, do not send a redundant receipt-only message; if answerable, answer directly, otherwise state the short plan, nearest checkpoint, and that the current background subtask is paused",
            "- subtask_boundary_protocol: send a user-visible update whenever the active subtask changes materially, especially across intake -> audit, audit -> experiment planning, experiment planning -> run launch, run result -> drafting, or drafting -> review/rebuttal",
            "- smoke_then_detach_protocol: for baseline reproduction, main experiments, and analysis experiments, use a bounded smoke test only when the command path, output schema, or environment viability is still unverified; otherwise launch the real long run directly with bash_exec(mode='detach', ...) and usually leave timeout_seconds unset rather than guessing a fake deadline",
            "- progress_first_monitoring_protocol: judge health by forward progress in logs, metrics, new artifacts, or checkpoints rather than by wall-clock silence alone.",
            "- intervention_threshold_protocol: intervene only when the run shows a concrete blocker such as repeated hard errors, no forward progress across multiple checks, exhausted resources, or clearly invalid outputs.",
            "- timeout_protocol: do not kill or restart a run merely because a short watch window passed without final completion; use timeout_seconds for bounded command setup or watch windows, not as a fake experiment deadline.",
            "- long_run_reporting_protocol: inspect real logs/status after each meaningful await cycle and at least once every 30 minutes at worst, but only send a user-visible update when there is a human-meaningful delta, blocker, recovery, route change, or the visibility bound would otherwise be exceeded",
            f"- auto_continue_monitoring_protocol: if the runtime schedules background-progress auto_continue turns while a real external task is already active, treat them as low-frequency monitoring passes roughly every {_AUTO_CONTINUE_MONITOR_INTERVAL_SECONDS} seconds rather than as a fast polling loop",
            "- long_run_ownership_protocol: real long-running execution should stay alive in detached bash_exec sessions or the runtime process it launched; do not rely on repeated model turns to simulate continuous execution",
            "- auto_continue_resume_protocol: on auto_continue turns, read the resume context spine first and continue from the latest durable user requirement, latest assistant checkpoint, latest run summary, recent memory cues, and current bash_exec state before changing route",
            "- decision_dedupe_rule: if no new durable evidence, blocker change, or user requirement appeared since the last route judgment, do not restate the same decision; continue the current action or remain waiting.",
            "- blocking_protocol: use reply_mode='blocking' only for true unresolved user decisions; ordinary progress updates should stay threaded and non-blocking",
            "- credential_blocking_protocol: if continuation requires user-supplied external credentials or secrets such as an API key, GitHub key/token, or Hugging Face key/token, emit one structured blocking decision request that asks the user to provide the credential or choose an alternative route; do not invent placeholders or silently skip the blocked step",
            "- credential_wait_protocol: if that credential request remains unanswered, keep the quest waiting rather than self-resolving; if you are resumed without new credentials and no other work is possible, a long low-frequency park such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable to avoid busy-looping",
            f"- standby_prefix_rule: when you intentionally leave one blocking standby interaction after task completion, prefix it with {'[等待决策]' if chinese_turn else '[Waiting for decision]'} and wait for a new user reply before continuing",
            "- stop_notice_protocol: if work must pause or stop, send a user-visible notice that explains why, confirms preserved context, and states that any new message or `/resume` will continue from the same quest",
            "- micro_task_stop_rule: after a fresh user-message turn that was only `direct_answer` or `direct_action`, finish that unit and do not silently turn the same turn into a broader autonomous stage pass unless the user asked for it.",
            "- watchdog_payload_protocol: if a tool result includes `watchdog_notes`, `progress_watchdog_note`, `visibility_watchdog_note`, or `state_change_watchdog_note`, treat that as an action item to inspect state and decide whether a fresh user-visible update is actually needed; do not emit duplicate progress by reflex",
            "- stage_contract_protocol: stage-specific plan/checklist rules, milestone rules, literature rules, and writing rules belong in the requested skill; do not expect this runtime block to restate them",
            "- connector_style_rule: connector-facing tone and report style live in the active connector contract rather than in this runtime block.",
            "- workspace_discipline: read and modify code inside current_workspace_root; treat quest_root as the canonical repo identity and durable runtime root",
            "- binary_safety: do not open or rewrite large binary assets unless truly necessary; prefer summaries, metadata, and targeted inspection first",
        ]
        if re.search(r"(understand|easy|simple|plain|non-technical|更新|看懂|易懂|通俗)", user_message, re.IGNORECASE):
            lines.append(
                "- novice_context_protocol: when the user asks for accessible updates, omit file paths, file names, internal ids, retry counters, and low-level monitor narration; translate them into user-facing meaning such as baseline record, draft, experiment result, or supplementary run."
            )
        if decision_policy == "autonomous":
            lines.extend(
                [
                    "- autonomous_decision_protocol: ordinary route choices belong to you; do not emit `artifact.interact(kind='decision_request', ...)` for routine branching, baseline, cost, or experiment-selection ambiguity.",
                    "- autonomous_continuation_protocol: decide from local evidence, record the chosen route durably, and continue automatically after a milestone unless the next step is genuinely unsafe.",
                    "- completion_approval_exception: explicit quest-completion approval is still allowed as the one normal blocking decision request when you believe the quest is truly complete.",
                ]
            )
        else:
            lines.extend(
                [
                    "- user_gated_decision_protocol: when continuation truly depends on user preference, approval, or scope choice, use one structured blocking decision request with 1 to 3 concrete options; for each option say what it means, how strongly you recommend it, and what impact it would have on speed, quality, cost, or risk.",
                    "- user_gated_restraint: even in user-gated mode, do not turn ordinary progress or ordinary stage completion into blocking interrupts.",
                ]
            )
        if need_research_paper:
            lines.append(
                "- completion_protocol: for full_research and similarly end-to-end quests, do not self-stop after one stage or one launched detached run; keep advancing until a paper-like deliverable exists unless the user explicitly stops or narrows scope"
            )
        else:
            lines.append(
                "- completion_protocol: when `startup_contract.need_research_paper` is false, the quest goal is the strongest justified algorithmic result; keep iterating from measured main-experiment results and do not self-route into paper work by default"
            )
        if launch_mode == "standard" and standard_profile == "optimization_task":
            lines.append(
                "- standard_optimization_completion_protocol: in this entry profile, do not treat missing paper artifacts or missing analysis-campaign artifacts as unfinished work by themselves; keep pushing the optimization frontier until the result plateaus, a blocker appears, or the user changes scope."
            )
        if chinese_turn:
            lines.extend(
                [
                    "- connector_reply_hint: 在聊天面里优先简明说明当前状态、下一步动作、预计回传内容。",
                ]
            )
        else:
            lines.extend(
                [
                    "- connector_reply_hint: keep chat replies concise but operational, with explicit next steps and evidence targets.",
                ]
            )
        return "\n".join(lines)

    def _quest_context_block(self, quest_root: Path) -> str:
        return "\n".join(
            [
                "- quest_context_rule: quest documents are durable but not pre-expanded here.",
                "- quest_documents_tool: call artifact.read_quest_documents(names=['brief','plan','status','summary'], mode='excerpt'|'full') when document detail is needed.",
                "- active_user_requirements_tool: call artifact.read_quest_documents(names=['active_user_requirements'], mode='full') when exact current durable user requirements matter.",
                "- research_map_tool: call artifact.get_research_map_status(detail='summary'|'full') when the current active node, research head, node history, canvas progress, or activation refs matter.",
                "- research_map_usage_rule: use `summary` for ordinary recovery/status/switch questions and `full` only when you need the full node list or edge payload.",
                "- workspace_execution_rule: on resume/restart/auto_continue turns, read current workspace `PLAN.md` / `CHECKLIST.md` (or aliases) before inventing a new route.",
            ]
        )

    def _durable_state_block(self, snapshot: dict, quest_root: Path) -> str:
        confirmed_baseline_ref = (
            dict(snapshot.get("confirmed_baseline_ref") or {})
            if isinstance(snapshot.get("confirmed_baseline_ref"), dict)
            else {}
        )
        confirmed_metric_contract_json_rel_path = str(
            confirmed_baseline_ref.get("metric_contract_json_rel_path") or ""
        ).strip()
        lines = [
            f"- baseline_gate: {snapshot.get('baseline_gate') or 'pending'}",
            f"- active_baseline_id: {snapshot.get('active_baseline_id') or 'none'}",
            f"- active_run_id: {snapshot.get('active_run_id') or 'none'}",
            f"- active_idea_id: {snapshot.get('active_idea_id') or 'none'}",
            f"- active_analysis_campaign_id: {snapshot.get('active_analysis_campaign_id') or 'none'}",
            f"- active_paper_line_ref: {snapshot.get('active_paper_line_ref') or 'none'}",
            f"- current_workspace_branch: {snapshot.get('current_workspace_branch') or 'none'}",
            f"- current_workspace_root: {snapshot.get('current_workspace_root') or 'none'}",
            f"- workspace_mode: {snapshot.get('workspace_mode') or 'quest'}",
            f"- runtime_status: {snapshot.get('runtime_status') or snapshot.get('status') or 'unknown'}",
            f"- waiting_interaction_id: {snapshot.get('waiting_interaction_id') or 'none'}",
            f"- pending_user_message_count: {snapshot.get('pending_user_message_count') or 0}",
            f"- continuation_policy: {snapshot.get('continuation_policy') or 'auto'}",
            f"- continuation_anchor: {snapshot.get('continuation_anchor') or 'none'}",
            "- quest_state_tool: call artifact.get_quest_state(detail='summary'|'full') for current runtime refs, interactions, recent artifacts, and recent runs.",
        ]
        if confirmed_metric_contract_json_rel_path:
            lines.extend(
                [
                    f"- active_baseline_metric_contract_json: {confirmed_metric_contract_json_rel_path}",
                    "- active_baseline_metric_contract_rule: before planning or running `experiment` or `analysis-campaign`, read this JSON file and treat it as the canonical baseline comparison contract unless a newer confirmed baseline explicitly replaces it.",
                ]
            )
        return "\n".join(lines)

    def _paper_and_evidence_block(self, snapshot: dict, quest_root: Path) -> str:
        paper_contract = (
            dict(snapshot.get("paper_contract") or {})
            if isinstance(snapshot.get("paper_contract"), dict)
            else {}
        )
        lines = [
            f"- selected_outline_ref: {str(paper_contract.get('selected_outline_ref') or 'none')}",
            f"- selected_outline_title: {str(paper_contract.get('title') or 'none')}",
        ]
        paper_contract_health = (
            dict(snapshot.get("paper_contract_health") or {})
            if isinstance(snapshot.get("paper_contract_health"), dict)
            else {}
        )
        if paper_contract_health:
            primary_blocker = str(
                ((paper_contract_health.get("blocking_reasons") or [None])[0]) or "none"
            ).strip() or "none"
            lines.extend(
                [
                    (
                        "- paper_contract_health: "
                        f"evidence_ready={bool(paper_contract_health.get('evidence_ready', paper_contract_health.get('writing_ready')))}, "
                        f"analysis_ready={bool(paper_contract_health.get('analysis_ready', paper_contract_health.get('writing_ready')))}, "
                        f"draft_checkpoint_ready={bool(paper_contract_health.get('draft_checkpoint_ready'))}, "
                        f"manuscript_ready={bool(paper_contract_health.get('manuscript_ready'))}, "
                        f"submission_ready={bool(paper_contract_health.get('submission_ready'))}"
                    ),
                    f"- paper_health_counts: unresolved_required={int(paper_contract_health.get('unresolved_required_count') or 0)}, unmapped_completed={int(paper_contract_health.get('unmapped_completed_count') or 0)}, blocking_pending={int(paper_contract_health.get('blocking_open_supplementary_count') or 0)}",
                    f"- paper_package_type: {str(paper_contract_health.get('package_type') or 'draft_checkpoint')}",
                    f"- paper_recommended_next_stage: {str(paper_contract_health.get('recommended_next_stage') or 'none')}",
                    f"- paper_recommended_action: {str(paper_contract_health.get('recommended_action') or 'none')}",
                    f"- paper_primary_blocker: {primary_blocker}",
                    "- paper_contract_tool: call artifact.get_paper_contract(detail='full') before evidence-grounded paper prose.",
                    "- paper_health_tool: call artifact.get_paper_contract_health(detail='full') before write/finalize routing.",
                    "- paper_coverage_tool: call artifact.validate_manuscript_coverage(detail='full') before full-manuscript or submission claims.",
                    "- paper_outline_tool: call artifact.list_paper_outlines(...) when outline inventory or a valid outline_id is needed.",
                    "- paper_campaign_tool: call artifact.get_analysis_campaign(campaign_id='active') when exact supplementary slice status matters.",
                ]
            )
            lines.append(
                "- paper_contract_rule: do not finalize unless submission_ready is true."
            )
        return "\n".join(lines)

    def _priority_memory_block(
        self,
        quest_root: Path,
        *,
        skill_id: str,
        active_anchor: str,
        user_message: str,
    ) -> str:
        stage = active_anchor if active_anchor in STAGE_MEMORY_PLAN else skill_id
        plan = STAGE_MEMORY_PLAN.get(stage, STAGE_MEMORY_PLAN["decision"])
        quest_kinds = ", ".join(plan.get("quest", ())) or "none"
        global_kinds = ", ".join(plan.get("global", ())) or "none"
        lines = [
            f"- stage_memory_rule: for `{stage}`, prefer quest memory kinds [{quest_kinds}] and global memory kinds [{global_kinds}] when memory lookup is needed.",
            "- memory_lookup_tool: call memory.list_recent(...) after pause/restart and memory.search(...) before repeating old work or reopening an old baseline route.",
            "- checkpoint_memory_lookup_rule: on resume/restart/auto_continue turns and continue/status questions, look for the latest checkpoint-style quest memory that states the current route, current active node, node history, what not to reopen, the next resume step, and the first files to read.",
            "- memory_injection_rule: keep the injected memory compact, but do not drop all continuity on auto_continue turns; reuse a few recent durable cues directly when they materially anchor the next action.",
        ]
        if is_recall_priors_on(quest_root) and skill_id in STANDARD_SKILLS:
            lines.append(
                "- recall_priors_rule: before generating new ideas, baselines, or experiment plans, "
                "call `memory.list_knowledge_summaries(scope='global')` once and scan the returned "
                "rows for any `task:` tag, claim, or keyword that overlaps your current quest. "
                "Read the full card via `memory.read_card` for any candidate that looks relevant. "
                "If nothing matches, say so explicitly in your reasoning and proceed."
            )
        if is_distill_on(quest_root) and skill_id in STANDARD_SKILLS:
            gate_payload = evaluate_distill_gate_for_quest(quest_root)
            if gate_payload is not None:
                pending_ids = ", ".join(gate_payload.get("pending_distill_ids") or []) or "(none listed)"
                lines.append(
                    "- distill_required_rule: there are "
                    f"{gate_payload['pending_distill_count']} completed run(s) without a "
                    f"distill_review (ids: {pending_ids}). Before calling "
                    "`submit_paper_bundle` or `complete_quest`, run the distill skill and "
                    "`artifact.record(kind='distill_review', ...)` covering the pending runs. "
                    "Both closure tools hard-reject until the review lands."
                )
        selected: list[dict] = []
        seen_paths: set[str] = set()
        for kind in plan.get("quest", ())[:2]:
            for card in self.memory_service.list_recent(scope="quest", quest_root=quest_root, limit=2, kind=kind)[:1]:
                self._append_priority_memory(
                    selected,
                    seen_paths,
                    card=card,
                    scope="quest",
                    quest_root=quest_root,
                    reason=f"recent quest memory for stage `{stage}`",
                )
        for kind in plan.get("global", ())[:2]:
            for card in self.memory_service.list_recent(scope="global", limit=2, kind=kind)[:1]:
                self._append_priority_memory(
                    selected,
                    seen_paths,
                    card=card,
                    scope="global",
                    quest_root=quest_root,
                    reason=f"recent global memory for stage `{stage}`",
                )
        for query in self._memory_queries(user_message)[:2]:
            for scope in ("quest", "global"):
                for card in self.memory_service.search(
                    query,
                    scope=scope if scope == "global" else "quest",
                    quest_root=quest_root if scope == "quest" else None,
                    limit=1,
                ):
                    self._append_priority_memory(
                        selected,
                        seen_paths,
                        card=card,
                        scope=scope,
                        quest_root=quest_root,
                        reason=f"matched current-turn query `{query}`",
                    )
        for query in self._checkpoint_memory_queries(stage=stage, user_message=user_message):
            for card in self.memory_service.search(
                query,
                scope="quest",
                quest_root=quest_root,
                limit=1,
            ):
                self._append_priority_memory(
                    selected,
                    seen_paths,
                    card=card,
                    scope="quest",
                    quest_root=quest_root,
                    reason=f"matched checkpoint-memory query `{query}`",
                )
        lines.extend(["- selected_memory:", self._format_priority_memory(selected)])
        return "\n".join(lines)

    def _append_priority_memory(
        self,
        selected: list[dict],
        seen_paths: set[str],
        *,
        card: dict,
        scope: str,
        quest_root: Path,
        reason: str,
    ) -> None:
        path = str(card.get("path") or "")
        if not path or path in seen_paths:
            return
        full = self.memory_service.read_card(
            path=path,
            scope=scope,
            quest_root=quest_root if scope == "quest" else None,
        )
        excerpt = " ".join(str(full.get("body") or "").split())
        if len(excerpt) > 260:
            excerpt = excerpt[:257].rstrip() + "..."
        selected.append(
            {
                "scope": scope,
                "type": full.get("type") or card.get("type") or "memory",
                "title": full.get("title") or card.get("title") or Path(path).stem,
                "path": path,
                "reason": reason,
                "excerpt": excerpt or str(card.get("excerpt") or ""),
            }
        )
        seen_paths.add(path)

    @staticmethod
    def _format_priority_memory(selected: list[dict]) -> str:
        if not selected:
            return "- none"
        lines: list[str] = []
        for item in selected:
            lines.append(f"- [{item['scope']}|{item['type']}] {item['title']} ({item['path']})")
            lines.append(f"  reason: {item['reason']}")
            if item.get("excerpt"):
                lines.append(f"  excerpt: {item['excerpt']}")
        return "\n".join(lines)

    @staticmethod
    def _memory_queries(user_message: str) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for token in re.findall(r"[A-Za-z0-9_./:-]{4,}|[\u4e00-\u9fff]{2,}", user_message):
            cleaned = token.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            tokens.append(cleaned)
            if len(tokens) >= 6:
                break
        return tokens

    @staticmethod
    def _checkpoint_memory_queries(*, stage: str, user_message: str) -> list[str]:
        normalized = str(user_message or "").strip().lower()
        continue_markers = ("继续", "resume", "status", "进展", "当前", "checkpoint", "next")
        if stage not in {"decision", "finalize", "write", "experiment", "analysis-campaign"} and not any(
            marker in normalized for marker in continue_markers
        ):
            return []
        return [
            "current checkpoint",
            "current node",
            "node history",
            "continue-later",
            "superseded",
            "reopen condition",
            "what should be read first",
            "do not repeat",
        ]

    def _conversation_block(self, quest_id: str, limit: int = 12) -> str:
        return "\n".join(
            [
                "- conversation_context_rule: recent conversation is not pre-expanded here.",
                f"- conversation_tool: call artifact.get_conversation_context(limit={limit}, include_attachments=False) when earlier turn continuity matters.",
            ]
        )

    def _expanded_conversation_block(self, quest_id: str, *, limit: int = 200, char_budget: int = 24000) -> str:
        history = self.quest_service.history(quest_id, limit=limit)
        if not history:
            return "- none"
        lines = [
            f"- conversation_injection_rule: the recent {len(history)} message(s) are expanded below so you do not need to ask the user to restate them.",
        ]
        used = sum(len(line) for line in lines)
        for index, item in enumerate(history, start=1):
            role = str(item.get("role") or "unknown").strip() or "unknown"
            source = str(item.get("source") or "unknown").strip() or "unknown"
            created_at = str(item.get("created_at") or "").strip() or "unknown-time"
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            line = f"{index}. [{role}|{source}|{created_at}] {content}"
            if used + len(line) > char_budget:
                lines.append(
                    f"- conversation_injection_truncated: stopped after {index - 1} message(s) to stay within prompt budget."
                )
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)

    def _special_conversation_block(self, snapshot: dict, *, quest_id: str) -> str:
        if self._start_setup_session(snapshot) or self._custom_profile(snapshot) in {"settings_issue", "admin_ops"}:
            return self._expanded_conversation_block(quest_id)
        return self._conversation_block(quest_id)

    def _markdown_body(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            _metadata, body = self._split_frontmatter(path)
            return body.strip()
        return text.strip()

    @staticmethod
    def _split_frontmatter(path: Path) -> tuple[dict, str]:
        metadata, body = load_markdown_document(path)
        return metadata, body
