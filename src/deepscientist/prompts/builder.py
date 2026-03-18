from __future__ import annotations

import json
import re
from pathlib import Path

from ..connector_runtime import normalize_conversation_id, parse_conversation_id
from ..config import ConfigManager
from ..memory import MemoryService
from ..memory.frontmatter import load_markdown_document
from ..quest import QuestService
from ..registries import BaselineRegistry
from ..shared import read_json, read_text, read_yaml

STANDARD_SKILLS = (
    "scout",
    "baseline",
    "idea",
    "experiment",
    "analysis-campaign",
    "write",
    "finalize",
    "decision",
)

COMPANION_SKILLS = (
    "figure-polish",
    "intake-audit",
    "review",
    "rebuttal",
)

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


class PromptBuilder:
    def __init__(self, repo_root: Path, home: Path) -> None:
        self.repo_root = repo_root
        self.home = home
        self.quest_service = QuestService(home)
        self.memory_service = MemoryService(home)
        self.baseline_registry = BaselineRegistry(home)
        self.config_manager = ConfigManager(home)

    def build(
        self,
        *,
        quest_id: str,
        skill_id: str,
        user_message: str,
        model: str,
        turn_reason: str = "user_message",
        retry_context: dict | None = None,
    ) -> str:
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_config = self.config_manager.load_named("config")
        connectors_config = self.config_manager.load_named_normalized("connectors")
        quest_root = Path(snapshot["quest_root"])
        active_anchor = str(snapshot.get("active_anchor") or skill_id)
        default_locale = str(runtime_config.get("default_locale") or "zh-CN")
        system_block = self._prompt_fragment("src/prompts/system.md")
        connector_contract_block = self._connector_contract_block(quest_id=quest_id, snapshot=snapshot)
        sections = [
            system_block,
            "",
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
            f"runner_name: codex",
            f"model: {model}",
            f"conversation_id: quest:{quest_id}",
            f"default_locale: {default_locale}",
            "built_in_mcp_namespaces: memory, artifact, bash_exec",
            "mcp_namespace_note: any shell-like command execution must use bash_exec, including curl/python/bash/node and similar CLI tools; do not use transient shell snippets.",
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
                self._turn_driver_block(turn_reason=turn_reason, user_message=user_message),
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
                "## Paper And Evidence Snapshot",
                self._paper_and_evidence_block(snapshot, quest_root),
                "",
                "## Retry Recovery Packet",
                self._retry_recovery_block(retry_context),
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
                self._conversation_block(quest_id),
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

    def _turn_driver_block(self, *, turn_reason: str, user_message: str) -> str:
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
        else:
            preview = " ".join(str(user_message or "").split())
            if len(preview) > 220:
                preview = preview[:217].rstrip() + "..."
            lines.append(f"- direct_user_message_preview: {preview or 'none'}")
        return "\n".join(lines)

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
        qq_config = connectors_config.get("qq") if isinstance(connectors_config.get("qq"), dict) else {}

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
            "- connector_contract_rule: load connector-specific prompt fragments only for the active or bound external connector; do not load unused connector contracts.",
        ]

        if connector == "qq":
            lines.extend(
                [
                    "- qq_surface_rule: QQ is a milestone-report surface, not a full artifact browser.",
                    "- qq_default_mode: keep outbound replies concise, respectful, text-first, and progress-aware.",
                    "- qq_detail_rule: do not proactively dump file inventories, path lists, or low-level file details unless the user explicitly asked for them.",
                    "- qq_length_rule: for ordinary QQ progress replies, normally use only 2 to 4 short sentences, or 3 very short bullets at most.",
                    "- qq_summary_first_rule: start with the user-facing conclusion, then the immediate meaning, then the next action; do not make the user reverse-engineer the status from telemetry.",
                    "- qq_internal_signal_rule: omit worker names, heartbeat timestamps, retry counters, pending/running/completed counts, file names, and monitor-window narration unless that detail is necessary for a user decision or to explain a real risk.",
                    "- qq_translation_rule: translate internal actions into user value, for example say that you organized the baseline record for easier comparison later instead of listing the files you touched.",
                    "- qq_eta_rule: for baseline reproduction, main experiments, analysis experiments, and other important long-running research phases, include a rough ETA for the next meaningful result, next step, or next update; if the runtime is uncertain, say that directly and still give the next check-in window.",
                    f"- qq_auto_send_main_experiment_png: {bool(qq_config.get('auto_send_main_experiment_png', True))}",
                    f"- qq_auto_send_analysis_summary_png: {bool(qq_config.get('auto_send_analysis_summary_png', True))}",
                    f"- qq_auto_send_slice_png: {bool(qq_config.get('auto_send_slice_png', False))}",
                    f"- qq_auto_send_paper_pdf: {bool(qq_config.get('auto_send_paper_pdf', True))}",
                    f"- qq_enable_markdown_send: {bool(qq_config.get('enable_markdown_send', False))}",
                    f"- qq_enable_file_upload_experimental: {bool(qq_config.get('enable_file_upload_experimental', False))}",
                    "- qq_visual_rule: follow the fixed Morandi palette guide defined in the system prompt and active stage skill; do not assume per-install palette config exists.",
                    "- qq_media_rule: auto-send only high-value milestone media such as a main-experiment summary PNG, an aggregated analysis summary PNG, or the final paper PDF when available and configured.",
                    "- qq_media_rule_2: do not auto-send every slice image, every debug plot, or draft paper figures unless the user explicitly asked for them.",
                    "- qq_structured_delivery_rule: when you want native QQ markdown or native QQ image/file delivery, request it through artifact.interact(connector_hints=..., attachments=[...]) instead of inventing connector-specific inline tag syntax.",
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
        active = bound_external[0] if bound_external else None
        origin = "bound_external_binding" if active is not None else "latest_user_source"
        if active is None and latest_user_parsed is not None:
            latest_connector = str(latest_user_parsed.get("connector") or "").strip().lower()
            if latest_connector and latest_connector != "local":
                active = latest_user_parsed
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

    def _connector_contract_block(self, *, quest_id: str, snapshot: dict) -> str:
        connector = self._active_external_connector_name(quest_id=quest_id, snapshot=snapshot)
        if connector is None:
            return ""
        path = self.repo_root / "src" / "prompts" / "connectors" / f"{connector}.md"
        if not path.exists():
            return ""
        return self._markdown_body(path)

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
                    "- long_run_watchdog_rule: while an important long-running bash_exec session is active, never let more than 30 minutes pass without inspecting real logs/status and sending a concise artifact.interact progress update if the run is still ongoing",
                ]
            )
        if str(turn_reason or "").strip() == "auto_continue":
            lines.append(
                "- auto_continue_rule: this turn has no new user message; continue from the active requirements, durable artifacts, and current quest state instead of replaying the previous user message"
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
        active_anchor = str(snapshot.get("active_anchor") or "decision").strip() or "decision"
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
            return "Continue baseline establishment, verification, or reuse until the baseline gate is durably resolved."
        if active_anchor == "idea":
            return (
                "Continue idea analysis and route selection until the next durable idea branch is submitted "
                "with `lineage_intent='continue_line'` or `lineage_intent='branch_alternative'`."
            )
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
        ]
        for index, item in enumerate(attachments[:6], start=1):
            preferred_read_path = (
                str(item.get("extracted_text_path") or item.get("ocr_text_path") or item.get("archive_manifest_path") or item.get("path") or "").strip()
                or "none"
            )
            label = str(item.get("name") or item.get("file_name") or item.get("path") or item.get("url") or f"attachment-{index}").strip()
            kind = str(item.get("kind") or "attachment").strip()
            content_type = str(item.get("content_type") or item.get("mime_type") or "unknown").strip()
            lines.append(
                f"- attachment_{index}: label={label} | kind={kind} | content_type={content_type} | preferred_read_path={preferred_read_path}"
            )
        if len(attachments) > 6:
            lines.append(f"- remaining_attachment_count: {len(attachments) - 6}")
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

    def _prompt_fragment(self, relative_path: str) -> str:
        path = self.repo_root / relative_path
        return self._markdown_body(path)

    def _latest_user_message(self, quest_id: str) -> dict | None:
        for item in reversed(self.quest_service.history(quest_id, limit=80)):
            if str(item.get("role") or "") == "user":
                return item
        return None

    def _skill_paths_block(self) -> str:
        lines = []
        for skill_id in STANDARD_SKILLS:
            primary = (self.repo_root / "src" / "skills" / skill_id / "SKILL.md").resolve()
            lines.append(f"- {skill_id}: primary={primary}")
        return "\n".join(lines)

    def _companion_skill_paths_block(self) -> str:
        lines = []
        for skill_id in COMPANION_SKILLS:
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
    def _custom_profile(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("custom_profile") or "").strip().lower()
            if value in {"continue_existing_state", "revision_rebuttal", "freeform"}:
                return value
        return "freeform"

    def _research_delivery_policy_block(self, snapshot: dict) -> str:
        need_research_paper = self._need_research_paper(snapshot)
        launch_mode = self._launch_mode(snapshot)
        custom_profile = self._custom_profile(snapshot)
        lines = [
            f"- need_research_paper: {need_research_paper}",
            f"- launch_mode: {launch_mode}",
            f"- custom_profile: {custom_profile if launch_mode == 'custom' else 'n/a'}",
            f"- delivery_mode: {'paper_required' if need_research_paper else 'algorithm_first'}",
            "- idea_stage_rule: every accepted idea submission should normally create a new branch/worktree and a new user-visible research node.",
            "- idea_draft_rule: before `artifact.submit_idea(...)`, first finish a concise durable Markdown draft for the chosen route; keep `idea.md` compact and `draft.md` richer.",
            "- lineage_rule: normal idea routing uses exactly two lineage intents: `continue_line` creates a child of the current active branch; `branch_alternative` creates a sibling-like branch from the current branch's parent foundation.",
            "- revise_rule: `artifact.submit_idea(mode='revise', ...)` is maintenance-only compatibility for the same branch and should not be the default research-route mechanism.",
            "- post_main_result_rule: after every `artifact.record_main_experiment(...)`, first interpret the measured result and only then choose the next route.",
            "- foundation_selection_rule: for a genuinely new idea round, default to the current research head but feel free to choose another durable foundation when it is cleaner or stronger; inspect `artifact.list_research_branches(...)` first when the best foundation is not obvious.",
        ]
        if launch_mode == "custom":
            lines.extend(
                [
                    "- custom_launch_rule: do not force the canonical full-research path when the custom startup contract is narrower.",
                    "- custom_context_rule: treat `entry_state_summary`, `review_summary`, and `custom_brief` as active runtime context rather than decorative metadata.",
                ]
            )
            if custom_profile == "continue_existing_state":
                lines.extend(
                    [
                        "- existing_state_entry_rule: if reusable baselines, runs, drafts, or review assets already exist, open `intake-audit` before restarting baseline discovery or new experiments.",
                        "- reuse_first_rule: trust-rank and reconcile existing assets before deciding to rerun anything costly.",
                    ]
                )
            elif custom_profile == "revision_rebuttal":
                lines.extend(
                    [
                        "- rebuttal_entry_rule: treat reviewer comments and the current paper state as the active contract; open `rebuttal` before ordinary writing.",
                        "- rebuttal_routing_rule: route supplementary reviewer-facing evidence through `analysis-campaign` and manuscript deltas through `write`, but let `rebuttal` orchestrate that mapping.",
                    ]
                )
            else:
                lines.extend(
                    [
                        "- freeform_entry_rule: prefer the custom brief over the default stage order and open only the skills actually needed.",
                    ]
                )
        if need_research_paper:
            lines.extend(
                [
                    "- delivery_goal: the quest should normally continue until at least one paper-like deliverable exists.",
                    "- main_result_rule: a strong main experiment is evidence, not the endpoint; usually continue into the necessary analysis, writing, or further strengthening work.",
                    "- writing_rule: when the evidence becomes strong enough, analysis and paper writing remain in scope by default.",
                    "- review_gate_rule: before declaring a substantial paper/draft task done, open `review` for an independent skeptical audit; if that audit finds serious gaps, route to `analysis-campaign`, `baseline`, `scout`, or `write` instead of stopping.",
                    "- stop_rule: do not stop with only an improved algorithm or isolated run logs unless the user explicitly narrows scope.",
                ]
            )
        else:
            lines.extend(
                [
                    "- delivery_goal: the quest should pursue the strongest justified algorithmic result rather than paper packaging.",
                    "- main_result_rule: use each measured main-experiment result to decide whether to create a `continue_line` child branch, create a `branch_alternative` sibling-like branch, run more analysis, or stop.",
                    "- no_paper_rule: do not default into `artifact.submit_paper_outline(...)`, `artifact.submit_paper_bundle(...)`, or `finalize` while this mode remains active.",
                    "- autonomy_rule: choose the next optimization foundation from durable evidence such as baseline state, the current research head, and recent main-experiment results; do not routinely ask the user to choose that.",
                    "- persistence_rule: even without paper writing, keep all major decisions, runs, evidence, failures, and conclusions durable so the next round can build on them cleanly.",
                ]
            )
        return "\n".join(lines)

    def _interaction_style_block(self, *, default_locale: str, user_message: str, snapshot: dict) -> str:
        normalized_locale = str(default_locale or "").lower()
        chinese_turn = normalized_locale.startswith("zh") or bool(re.search(r"[\u4e00-\u9fff]", user_message))
        bound_conversations = snapshot.get("bound_conversations") or []
        need_research_paper = self._need_research_paper(snapshot)
        decision_policy = self._decision_policy(snapshot)
        launch_mode = self._launch_mode(snapshot)
        custom_profile = self._custom_profile(snapshot)
        lines = [
            f"- configured_default_locale: {default_locale}",
            f"- current_turn_language_bias: {'zh' if chinese_turn else 'en'}",
            f"- bound_conversation_count: {len(bound_conversations)}",
            f"- decision_policy: {decision_policy}",
            f"- launch_mode: {launch_mode}",
            f"- custom_profile: {custom_profile if launch_mode == 'custom' else 'n/a'}",
            "- collaboration_mode: long-horizon, continuity-first, artifact-aware",
            "- response_pattern: say what changed -> say what it means -> say what happens next",
            "- interaction_protocol: first message may be plain conversation; after that, treat artifact.interact threads and mailbox polls as the main continuity spine across TUI, web, and connectors",
            "- mailbox_protocol: artifact.interact(include_recent_inbound_messages=True) is the queued human-message mailbox; when it returns user text, treat that input as higher priority than background subtasks until it has been acknowledged",
            "- acknowledgment_protocol: after artifact.interact returns any human message, immediately call artifact.interact(...) again to confirm receipt; if answerable, answer directly, otherwise state the short plan, nearest checkpoint, and that the current background subtask is paused",
            "- progress_protocol: emit artifact.interact(kind='progress', reply_mode='threaded', ...) at real human-meaningful checkpoints; if no natural checkpoint appears during active user-relevant work, send a concise keepalive before you drift beyond roughly 10 to 30 tool calls without a user-visible update",
            "- smoke_then_detach_protocol: for baseline reproduction, main experiments, and analysis experiments, first validate the command path with a bounded smoke test; once the smoke test passes, launch the real long run with bash_exec(mode='detach', ...) and usually leave timeout_seconds unset rather than guessing a fake deadline",
            "- long_run_reporting_protocol: for long-running bash_exec monitoring loops, inspect real logs or status after each completed sleep/await cycle and at least once every 30 minutes at worst, then report real evidence plus the next planned check time and estimated next reply time",
            "- long_run_watchdog_protocol: for baseline reproduction, baseline-running stages, main experiments, and other important detached runs, do not let more than 30 minutes pass without a real progress inspection and, if the run is still active, a user-visible artifact.interact progress update",
            "- tail_monitoring_protocol: when monitoring a detached run, prefer bash_exec(mode='read', id=..., tail_limit=..., order='desc') so you inspect the newest evidence first instead of re-reading full logs every time",
            "- managed_recovery_protocol: if a detached baseline, main-experiment, or analysis run is clearly invalid, wedged, or superseded, stop it with bash_exec(mode='kill', id=...), document the reason, fix the issue, and relaunch cleanly instead of letting a bad run linger",
            "- timeout_protocol: before using bash_exec(mode='await', ...), estimate whether the command can finish within the selected wait window; if runtime is uncertain or likely longer, use bash_exec(mode='detach', ...) and monitor, or set timeout_seconds intentionally",
            "- blocking_protocol: use reply_mode='blocking' only for true unresolved user decisions; ordinary progress updates should stay threaded and non-blocking",
            "- credential_blocking_protocol: if continuation requires user-supplied external credentials or secrets such as an API key, GitHub key/token, or Hugging Face key/token, emit one structured blocking decision request that asks the user to provide the credential or choose an alternative route; do not invent placeholders or silently skip the blocked step",
            "- credential_wait_protocol: if that credential request remains unanswered, keep the quest waiting rather than self-resolving; if you are resumed without new credentials and no other work is possible, a long low-frequency park such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable to avoid busy-looping",
            f"- standby_prefix_rule: when you intentionally leave one blocking standby interaction after task completion, prefix it with {'[等待决策]' if chinese_turn else '[Waiting for decision]'} and wait for a new user reply before continuing",
            "- stop_notice_protocol: if work must pause or stop, send a user-visible notice that explains why, confirms preserved context, and states that any new message or `/resume` will continue from the same quest",
            "- respect_protocol: write user-facing updates as natural, respectful, easy-to-follow chat; do not sound like a formal status report or internal tool log",
            "- omission_protocol: for ordinary user-facing updates, omit file paths, artifact ids, branch/worktree ids, session ids, raw commands, raw logs, and internal tool names unless the user asked for them or needs them to act",
            "- compaction_protocol: ordinary artifact.interact progress updates should usually fit in 2 to 4 short sentences and should not read like a monitoring transcript or execution diary",
            "- tool_call_keepalive_protocol: for active multi-step work outside long detached experiment waits, if you have spent roughly 10 to 30 tool calls without a user-visible checkpoint, send one concise artifact.interact progress update before continuing",
            "- human_progress_shape_protocol: ordinary progress updates should usually make three things explicit in human language: the current task, the main difficulty or latest real progress, and the concrete next measure you will take",
            "- eta_visibility_protocol: for baseline reproduction, main experiments, analysis experiments, and other important long-running phases, progress updates should also make the expected time to the next meaningful result, next milestone, or next user-visible update explicit; use roughly 10 to 30 minutes as the normal update window, and if the ETA is unreliable, say that and give a realistic next check-in window instead",
            "- teammate_voice_protocol: write like a calm capable teammate using natural first-person phrasing when helpful, for example 'I'm working on ...', 'The main issue right now is ...', 'Next I'll ...'; do not sound like a dashboard or incident log",
            "- tqdm_progress_protocol: when you control the experiment code for baseline reproduction, main experiments, or analysis experiments, instrument long loops with a throttled tqdm-style progress reporter when feasible and also prefer periodic __DS_PROGRESS__ JSON markers so monitoring stays both human-readable and machine-usable",
            "- translation_protocol: convert internal actions into user-facing meaning; describe what was finished and why it matters instead of naming every touched file, counter, timestamp, or subprocess",
            "- detail_gate_protocol: include exact counters, worker labels, timestamps, retry counts, or file names only when the user explicitly asked for them, when they change the recommended action, or when they are the only honest way to explain a real blocker",
            "- monitoring_summary_protocol: for long-running monitoring loops, summarize the frontier state in plain language such as still progressing, temporarily stalled, recovered, or needs intervention; do not narrate each watch window unless the boundary itself matters",
            "- preflight_rewrite_protocol: before sending artifact.interact, quickly self-check whether the draft reads like a monitoring log, file inventory, or internal diary; if it mentions watch windows, heartbeats, retry counters, raw counts, timestamps, or multiple file names without being necessary for user action, rewrite it into conclusion -> meaning -> next step first",
            "- non_research_mode_protocol: if the user message looks like a non-research request, ask for a second confirmation before engaging stage skills or research workflow; after completion, leave one blocking standby interaction instead of repeatedly pinging",
            "- workspace_discipline: read and modify code inside current_workspace_root; treat quest_root as the canonical repo identity and durable runtime root",
            "- binary_safety: do not open or rewrite large binary assets unless truly necessary; prefer summaries, metadata, and targeted inspection first",
        ]
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
                    "- user_gated_decision_protocol: when continuation truly depends on user preference, approval, or scope choice, use one structured blocking decision request with 1 to 3 concrete options.",
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
        if chinese_turn:
            lines.extend(
                [
                    "- tone_hint: 使用自然、礼貌、专业、偏正式的中文；必要时可自然称呼用户为“老师”，但不要每句重复；避免机械模板腔。",
                    "- connector_reply_hint: 在聊天面里优先简明说明当前状态、下一步动作、预计回传内容。",
                ]
            )
        else:
            lines.extend(
                [
                    "- tone_hint: use a polite, professional, gentlemanly English tone.",
                    "- connector_reply_hint: keep chat replies concise but operational, with explicit next steps and evidence targets.",
                ]
            )
        return "\n".join(lines)

    def _quest_context_block(self, quest_root: Path) -> str:
        parts = []
        for title, filename in (
            ("Brief", "brief.md"),
            ("Plan", "plan.md"),
            ("Status", "status.md"),
            ("Summary", "SUMMARY.md"),
        ):
            text = read_text(quest_root / filename).strip() or "(empty)"
            parts.extend([f"{title} ({filename}):", text, ""])
        return "\n".join(parts).strip()

    def _durable_state_block(self, snapshot: dict, quest_root: Path) -> str:
        requested_baseline_ref = (
            dict(snapshot.get("requested_baseline_ref") or {})
            if isinstance(snapshot.get("requested_baseline_ref"), dict)
            else None
        )
        startup_contract = (
            dict(snapshot.get("startup_contract") or {})
            if isinstance(snapshot.get("startup_contract"), dict)
            else None
        )
        confirmed_baseline_ref = (
            dict(snapshot.get("confirmed_baseline_ref") or {})
            if isinstance(snapshot.get("confirmed_baseline_ref"), dict)
            else None
        )
        requested_baseline_id = str((requested_baseline_ref or {}).get("baseline_id") or "").strip()
        confirmed_baseline_id = str((confirmed_baseline_ref or {}).get("baseline_id") or "").strip()
        confirmed_baseline_rel_path = str(
            (confirmed_baseline_ref or {}).get("baseline_root_rel_path") or ""
        ).strip()
        confirmed_metric_contract_json_rel_path = str(
            (confirmed_baseline_ref or {}).get("metric_contract_json_rel_path") or ""
        ).strip()
        prebound_baseline_ready = bool(
            requested_baseline_id
            and confirmed_baseline_id
            and requested_baseline_id == confirmed_baseline_id
            and str(snapshot.get("baseline_gate") or "").strip().lower() == "confirmed"
        )
        lines = [
            f"- baseline_gate: {snapshot.get('baseline_gate') or 'pending'}",
            f"- active_baseline_id: {snapshot.get('active_baseline_id') or 'none'}",
            f"- active_baseline_variant_id: {snapshot.get('active_baseline_variant_id') or 'none'}",
            f"- requested_baseline_ref: {json.dumps(requested_baseline_ref, ensure_ascii=False, sort_keys=True) if requested_baseline_ref else 'none'}",
            f"- startup_contract: {json.dumps(startup_contract, ensure_ascii=False, sort_keys=True) if startup_contract else 'none'}",
            f"- startup_decision_policy: {self._decision_policy(snapshot)}",
            f"- confirmed_baseline_ref: {json.dumps(confirmed_baseline_ref, ensure_ascii=False, sort_keys=True) if confirmed_baseline_ref else 'none'}",
            f"- confirmed_baseline_import_root: {confirmed_baseline_rel_path or 'none'}",
            f"- prebound_baseline_ready: {prebound_baseline_ready}",
            f"- active_run_id: {snapshot.get('active_run_id') or 'none'}",
            f"- research_head_branch: {snapshot.get('research_head_branch') or 'none'}",
            f"- research_head_worktree_root: {snapshot.get('research_head_worktree_root') or 'none'}",
            f"- current_workspace_branch: {snapshot.get('current_workspace_branch') or 'none'}",
            f"- current_workspace_root: {snapshot.get('current_workspace_root') or 'none'}",
            f"- active_idea_id: {snapshot.get('active_idea_id') or 'none'}",
            f"- active_idea_md_path: {snapshot.get('active_idea_md_path') or 'none'}",
            f"- active_analysis_campaign_id: {snapshot.get('active_analysis_campaign_id') or 'none'}",
            f"- next_pending_slice_id: {snapshot.get('next_pending_slice_id') or 'none'}",
            f"- workspace_mode: {snapshot.get('workspace_mode') or 'quest'}",
            f"- runtime_status: {snapshot.get('runtime_status') or snapshot.get('status') or 'unknown'}",
            f"- stop_reason: {snapshot.get('stop_reason') or 'none'}",
            f"- pending_decisions: {', '.join(snapshot.get('pending_decisions') or []) or 'none'}",
            f"- pending_user_message_count: {snapshot.get('pending_user_message_count') or 0}",
            f"- active_interaction_count: {len(snapshot.get('active_interactions') or [])}",
            f"- waiting_interaction_id: {snapshot.get('waiting_interaction_id') or 'none'}",
            f"- latest_thread_interaction_id: {snapshot.get('latest_thread_interaction_id') or 'none'}",
            f"- default_reply_interaction_id: {snapshot.get('default_reply_interaction_id') or 'none'}",
            f"- last_artifact_interact_at: {snapshot.get('last_artifact_interact_at') or 'none'}",
            f"- last_delivered_batch_id: {snapshot.get('last_delivered_batch_id') or 'none'}",
            f"- bound_conversations: {', '.join(snapshot.get('bound_conversations') or []) or 'none'}",
            f"- cloud_linked: {snapshot.get('cloud', {}).get('linked', False)}",
        ]
        if prebound_baseline_ready and confirmed_baseline_rel_path:
            lines.extend(
                [
                    "- prebound_baseline_execution_policy: runtime already attached and confirmed the requested baseline before this turn.",
                    f"- prebound_baseline_runtime_path: {confirmed_baseline_rel_path}",
                    "- prebound_baseline_agent_rule: do not redo baseline discovery or reproduction unless you find a concrete incompatibility, corruption, or missing evidence problem.",
                ]
            )
        active_workspace_root = Path(str(snapshot.get("current_workspace_root") or quest_root))
        attachment_root = active_workspace_root / "baselines" / "imported"
        if attachment_root.exists():
            attachments = [read_yaml(path, {}) for path in sorted(attachment_root.glob("*/attachment.yaml"))]
            attachments = [item for item in attachments if isinstance(item, dict) and item]
            if attachments:
                attachment = max(
                    attachments,
                    key=lambda item: (
                        str(item.get("attached_at") or ""),
                        str(item.get("source_baseline_id") or ""),
                    ),
                )
                entry = attachment.get("entry") if isinstance(attachment.get("entry"), dict) else {}
                confirmation = attachment.get("confirmation") if isinstance(attachment.get("confirmation"), dict) else {}
                if not confirmed_metric_contract_json_rel_path:
                    confirmed_metric_contract_json_rel_path = str(
                        confirmation.get("metric_contract_json_rel_path") or ""
                    ).strip()
                contract = entry.get("metric_contract") if isinstance(entry.get("metric_contract"), dict) else {}
                primary_metric_id = str(contract.get("primary_metric_id") or "").strip() or "none"
                metric_ids = [
                    str(item.get("metric_id") or "").strip()
                    for item in contract.get("metrics", [])
                    if isinstance(item, dict) and str(item.get("metric_id") or "").strip()
                ]
                lines.extend(
                    [
                        f"- active_baseline_primary_metric_id: {primary_metric_id}",
                        f"- active_baseline_metric_ids: {', '.join(metric_ids) or 'none'}",
                    ]
                )
        if (
            not confirmed_metric_contract_json_rel_path
            and confirmed_baseline_rel_path
            and (quest_root / confirmed_baseline_rel_path / "json" / "metric_contract.json").exists()
        ):
            confirmed_metric_contract_json_rel_path = str(
                Path(confirmed_baseline_rel_path, "json", "metric_contract.json").as_posix()
            )
        if confirmed_metric_contract_json_rel_path:
            lines.extend(
                [
                    f"- active_baseline_metric_contract_json: {confirmed_metric_contract_json_rel_path}",
                    "- active_baseline_metric_contract_rule: before planning or running `experiment` or `analysis-campaign`, read this JSON file and treat it as the canonical baseline comparison contract unless a newer confirmed baseline explicitly replaces it.",
                ]
            )
        analysis_baseline_inventory = read_json(quest_root / "artifacts" / "baselines" / "analysis_inventory.json", {})
        analysis_baseline_inventory = analysis_baseline_inventory if isinstance(analysis_baseline_inventory, dict) else {}
        analysis_inventory_entries = (
            analysis_baseline_inventory.get("entries") if isinstance(analysis_baseline_inventory.get("entries"), list) else []
        )
        registered_count = sum(
            1
            for item in analysis_inventory_entries
            if isinstance(item, dict) and str(item.get("status") or "").strip().lower() == "registered"
        )
        if analysis_inventory_entries:
            lines.extend(
                [
                    f"- supplementary_baseline_inventory_status: artifacts/baselines/analysis_inventory.json [exists]",
                    f"- supplementary_baseline_count: {len(analysis_inventory_entries)}",
                    f"- supplementary_baseline_registered_count: {registered_count}",
                ]
            )
        else:
            lines.append("- supplementary_baseline_inventory_status: artifacts/baselines/analysis_inventory.json [missing]")
        lines.extend(["", "Active interactions:"])
        active_interactions = snapshot.get("active_interactions") or []
        if active_interactions:
            for item in active_interactions[-3:]:
                interaction_id = item.get("interaction_id") or item.get("artifact_id") or "interaction"
                status = item.get("status") or "unknown"
                message = str(item.get("message") or "").strip().replace("\n", " ")
                if len(message) > 180:
                    message = message[:177].rstrip() + "..."
                lines.append(f"- {interaction_id} [{status}] {message or '(no message)'}")
        else:
            lines.append("- none")
        if int(snapshot.get("pending_user_message_count") or 0) > 0:
            lines.extend(
                [
                    "",
                    "Queued user-message notice:",
                    "- There are queued user messages waiting to be picked up via artifact.interact(include_recent_inbound_messages=True).",
                    "- Before continuing a resumed or follow-up turn, retrieve that mailbox payload first.",
                    "- After the mailbox returns user text, immediately send a follow-up artifact.interact acknowledgement or direct answer before resuming background work.",
                ]
            )

        lines.extend(
            [
                "",
                "Recent artifacts:",
            ]
        )
        recent_artifacts = snapshot.get("recent_artifacts") or []
        if recent_artifacts:
            for item in recent_artifacts[-5:]:
                payload = item.get("payload") or {}
                label = payload.get("artifact_id") or Path(item.get("path", "")).stem or "artifact"
                summary = payload.get("summary") or payload.get("reason") or "No summary provided."
                lines.append(f"- {item.get('kind')}: {label} -> {summary}")
        else:
            lines.append("- none")

        lines.extend(["", "Recent runs:"])
        recent_runs = snapshot.get("recent_runs") or []
        if recent_runs:
            for item in recent_runs[-5:]:
                run_id = item.get("run_id") or "unknown-run"
                summary = item.get("summary") or "No summary provided."
                lines.append(f"- {run_id}: {summary}")
        else:
            lines.append("- none")

        lines.extend(["", "Recent quest memory cards:"])
        quest_cards = self.memory_service.list_recent(scope="quest", quest_root=quest_root, limit=5)
        if quest_cards:
            for card in quest_cards:
                lines.append(f"- {card.get('type')}: {card.get('title')} ({card.get('path')})")
        else:
            lines.append("- none")

        lines.extend(["", "Recent global memory cards:"])
        global_cards = self.memory_service.list_recent(scope="global", limit=3)
        if global_cards:
            for card in global_cards:
                lines.append(f"- {card.get('type')}: {card.get('title')} ({card.get('path')})")
        else:
            lines.append("- none")

        lines.extend(["", "Reusable baselines:"])
        baseline_entries = self.baseline_registry.list_entries()[-5:]
        if baseline_entries:
            for entry in baseline_entries:
                baseline_id = entry.get("baseline_id") or entry.get("entry_id") or "unknown-baseline"
                summary = entry.get("summary") or entry.get("task") or "No summary provided."
                status = str(entry.get("status") or "unknown").strip() or "unknown"
                lines.append(f"- {baseline_id} [{status}]: {summary}")
        else:
            lines.append("- none")
        return "\n".join(lines)

    def _paper_and_evidence_block(self, snapshot: dict, quest_root: Path) -> str:
        paper_root = quest_root / "paper"
        selected_outline = read_json(paper_root / "selected_outline.json", {})
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        detailed_outline = (
            dict(selected_outline.get("detailed_outline") or {})
            if isinstance(selected_outline.get("detailed_outline"), dict)
            else {}
        )
        bundle_manifest = read_json(paper_root / "paper_bundle_manifest.json", {})
        bundle_manifest = bundle_manifest if isinstance(bundle_manifest, dict) else {}
        paper_baseline_inventory = read_json(paper_root / "baseline_inventory.json", {})
        paper_baseline_inventory = paper_baseline_inventory if isinstance(paper_baseline_inventory, dict) else {}
        claim_evidence_map = read_json(paper_root / "claim_evidence_map.json", {})
        claim_evidence_map = claim_evidence_map if isinstance(claim_evidence_map, dict) else {}
        compile_report = read_json(paper_root / "build" / "compile_report.json", {})
        compile_report = compile_report if isinstance(compile_report, dict) else {}
        open_source_manifest = read_json(quest_root / "release" / "open_source" / "manifest.json", {})
        open_source_manifest = open_source_manifest if isinstance(open_source_manifest, dict) else {}

        selected_outline_ref = str(
            selected_outline.get("outline_id") or bundle_manifest.get("selected_outline_ref") or ""
        ).strip()
        selected_outline_title = str(
            detailed_outline.get("title") or selected_outline.get("title") or bundle_manifest.get("title") or ""
        ).strip()
        research_questions_raw = detailed_outline.get("research_questions")
        research_questions: list[str] = []
        if isinstance(research_questions_raw, list):
            for item in research_questions_raw:
                if isinstance(item, dict):
                    question = str(item.get("question_text") or item.get("title") or item.get("id") or "").strip()
                else:
                    question = str(item or "").strip()
                if question:
                    research_questions.append(question)

        lines = [
            f"- selected_outline_ref: {selected_outline_ref or 'none'}",
            f"- selected_outline_title: {selected_outline_title or 'none'}",
            f"- selected_outline_story_present: {bool(selected_outline.get('story'))}",
            f"- selected_outline_ten_questions_present: {bool(selected_outline.get('ten_questions'))}",
            f"- active_research_question_count: {len(research_questions)}",
        ]
        if research_questions:
            for index, question in enumerate(research_questions[:3], start=1):
                lines.append(f"- active_research_question_{index}: {question}")

        def _path_status(path_str: str | None, *, fallback: str) -> str:
            resolved = str(path_str or fallback).strip() or fallback
            exists = (quest_root / resolved).exists()
            return f"{resolved} [{'exists' if exists else 'missing'}]"

        lines.extend(
            [
                f"- writing_plan_status: {_path_status(bundle_manifest.get('writing_plan_path'), fallback='paper/writing_plan.md')}",
                f"- draft_status: {_path_status(bundle_manifest.get('draft_path'), fallback='paper/draft.md')}",
                f"- references_status: {_path_status(bundle_manifest.get('references_path'), fallback='paper/references.bib')}",
                f"- claim_evidence_map_status: {_path_status(bundle_manifest.get('claim_evidence_map_path'), fallback='paper/claim_evidence_map.json')}",
                f"- baseline_inventory_status: {_path_status(bundle_manifest.get('baseline_inventory_path'), fallback='paper/baseline_inventory.json')}",
                f"- review_status: {'paper/review/review.md [exists]' if (paper_root / 'review' / 'review.md').exists() else 'paper/review/review.md [missing]'}",
                f"- proofing_report_status: {'paper/proofing/proofing_report.md [exists]' if (paper_root / 'proofing' / 'proofing_report.md').exists() else 'paper/proofing/proofing_report.md [missing]'}",
                f"- page_images_manifest_status: {'paper/proofing/page_images_manifest.json [exists]' if (paper_root / 'proofing' / 'page_images_manifest.json').exists() else 'paper/proofing/page_images_manifest.json [missing]'}",
            ]
        )

        if bundle_manifest:
            pdf_rel_path = str(bundle_manifest.get("pdf_path") or "").strip()
            compile_rel_path = str(bundle_manifest.get("compile_report_path") or "").strip()
            latex_root_path = str(bundle_manifest.get("latex_root_path") or "").strip()
            lines.extend(
                [
                    "- paper_bundle_manifest_present: True",
                    f"- bundle_pdf_status: {_path_status(pdf_rel_path, fallback='paper/paper.pdf')}",
                    f"- bundle_compile_report_status: {_path_status(compile_rel_path, fallback='paper/build/compile_report.json')}",
                    f"- bundle_latex_root: {latex_root_path or 'none'}",
                    f"- open_source_manifest_status: {_path_status(bundle_manifest.get('open_source_manifest_path'), fallback='release/open_source/manifest.json')}",
                    f"- open_source_cleanup_plan_status: {_path_status(bundle_manifest.get('open_source_cleanup_plan_path'), fallback='release/open_source/cleanup_plan.md')}",
                ]
            )
        else:
            lines.append("- paper_bundle_manifest_present: False")

        claims = claim_evidence_map.get("claims") if isinstance(claim_evidence_map.get("claims"), list) else []
        counts = {"supported": 0, "partial": 0, "unsupported": 0, "deferred": 0}
        unresolved: list[str] = []
        for item in claims:
            if not isinstance(item, dict):
                continue
            status = str(item.get("support_status") or "").strip().lower()
            if status in counts:
                counts[status] += 1
            if status in {"partial", "unsupported", "deferred"}:
                claim_id = str(item.get("claim_id") or item.get("claim_text") or "claim").strip()
                unresolved.append(f"{claim_id} [{status}]")
        lines.append(
            "- claim_status_counts: "
            + ", ".join(f"{key}={value}" for key, value in counts.items())
        )
        if unresolved:
            lines.append(f"- downgrade_watchlist: {'; '.join(unresolved[:5])}")
        else:
            lines.append("- downgrade_watchlist: none")

        if compile_report:
            lines.append(f"- compile_report_ok: {compile_report.get('ok') if 'ok' in compile_report else 'unknown'}")
        supplementary_baselines = (
            paper_baseline_inventory.get("supplementary_baselines")
            if isinstance(paper_baseline_inventory.get("supplementary_baselines"), list)
            else []
        )
        if paper_baseline_inventory:
            lines.append(f"- paper_supplementary_baseline_count: {len(supplementary_baselines)}")
        if open_source_manifest:
            lines.append(
                f"- open_source_release_branch: {str(open_source_manifest.get('release_branch') or '').strip() or 'none'}"
            )

        lines.extend(["", "Recent supporting runs:"])
        recent_runs = snapshot.get("recent_runs") or []
        supporting_runs = [
            item
            for item in recent_runs
            if isinstance(item, dict) and str(item.get("run_id") or "").strip()
        ]
        if supporting_runs:
            for item in supporting_runs[-3:]:
                run_id = str(item.get("run_id") or "run").strip()
                summary = str(item.get("summary") or "").strip() or "No summary provided."
                lines.append(f"- {run_id}: {summary}")
        else:
            lines.append("- none")

        lines.append("")
        lines.append(
            "- paper_state_rule: when drafting, reviewing, bundling, or finalizing, treat the selected outline, claim-evidence map, bundle manifest, proofing outputs, and downgrade watchlist as the active writing truth surface."
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
        selected: list[dict] = []
        seen_paths: set[str] = set()

        for scope in ("quest", "global"):
            for kind in plan.get(scope, ()):
                cards = self.memory_service.list_recent(
                    scope=scope,
                    quest_root=quest_root if scope == "quest" else None,
                    kind=kind,
                    limit=2,
                )
                if not cards:
                    continue
                self._append_priority_memory(
                    selected,
                    seen_paths,
                    card=cards[-1],
                    scope=scope,
                    quest_root=quest_root,
                    reason=f"recent {stage} {kind} memory",
                )
                if len(selected) >= 6:
                    return self._format_priority_memory(selected)

        for query in self._memory_queries(user_message):
            matches = self.memory_service.search(query, scope="both", quest_root=quest_root, limit=6)
            for card in matches:
                scope = str(card.get("scope") or "quest")
                self._append_priority_memory(
                    selected,
                    seen_paths,
                    card=card,
                    scope=scope,
                    quest_root=quest_root,
                    reason=f"matches current user message: `{query}`",
                )
                if len(selected) >= 8:
                    return self._format_priority_memory(selected)

        return self._format_priority_memory(selected)

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

    def _conversation_block(self, quest_id: str, limit: int = 12) -> str:
        records = self.quest_service.history(quest_id, limit=limit)
        if not records:
            return "- none"
        lines = []
        for item in records[-limit:]:
            role = str(item.get("role") or "unknown")
            source = str(item.get("source") or "unknown")
            content = str(item.get("content") or "").strip().replace("\n", " ")
            if len(content) > 400:
                content = content[:397].rstrip() + "..."
            reply_to = str(item.get("reply_to_interaction_id") or "").strip()
            suffix = f" -> reply_to:{reply_to}" if reply_to else ""
            lines.append(f"- [{role}|{source}]{suffix} {content}")
        return "\n".join(lines)

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
