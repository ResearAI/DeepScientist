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
    "optimize",
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
        turn_intent: str | None = None,
        turn_mode: str | None = None,
        retry_context: dict | None = None,
    ) -> str:
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_config = self.config_manager.load_named("config")
        connectors_config = self.config_manager.load_named_normalized("connectors")
        quest_root = Path(snapshot["quest_root"])
        active_anchor = str(snapshot.get("active_anchor") or skill_id)
        default_locale = str(runtime_config.get("default_locale") or "en-US")
        system_block = self._prompt_fragment("system.md", quest_root=quest_root)
        shared_interaction_block = self._prompt_fragment(
            Path("contracts") / "shared_interaction.md",
            quest_root=quest_root,
        )
        connector_contract_block = self._connector_contract_block(quest_id=quest_id, snapshot=snapshot)
        sections = [
            system_block,
            "",
            shared_interaction_block,
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

    def _connector_contract_block(self, *, quest_id: str, snapshot: dict) -> str:
        connector = self._active_external_connector_name(quest_id=quest_id, snapshot=snapshot)
        if connector is None:
            return ""
        quest_root = Path(snapshot["quest_root"])
        path = self._prompt_path(Path("connectors") / f"{connector}.md", quest_root=quest_root)
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
            return "Continue baseline establishment, verification, or reuse until the baseline gate is durably resolved."
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
            quest_path = quest_root / ".codex" / "prompts" / normalized
            if quest_path.exists():
                return quest_path
        return self.repo_root / "src" / "prompts" / normalized

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
            if value in {"continue_existing_state", "review_audit", "revision_rebuttal", "freeform"}:
                return value
        return "freeform"

    @staticmethod
    def _baseline_execution_policy(snapshot: dict) -> str:
        startup_contract = snapshot.get("startup_contract")
        if isinstance(startup_contract, dict):
            value = str(startup_contract.get("baseline_execution_policy") or "").strip().lower()
            if value in {"auto", "must_reproduce_or_verify", "reuse_existing_only", "skip_unless_blocking"}:
                return value
        return "auto"

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

    def _research_delivery_policy_block(self, snapshot: dict) -> str:
        need_research_paper = self._need_research_paper(snapshot)
        launch_mode = self._launch_mode(snapshot)
        standard_profile = self._standard_profile(snapshot)
        custom_profile = self._custom_profile(snapshot)
        baseline_execution_policy = self._baseline_execution_policy(snapshot)
        review_followup_policy = self._review_followup_policy(snapshot)
        manuscript_edit_mode = self._manuscript_edit_mode(snapshot)
        lines = [
            f"- need_research_paper: {need_research_paper}",
            f"- launch_mode: {launch_mode}",
            f"- standard_profile: {standard_profile if launch_mode == 'standard' else 'n/a'}",
            f"- custom_profile: {custom_profile if launch_mode == 'custom' else 'n/a'}",
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
                    "- delivery_goal: the quest should normally continue until at least one paper-like deliverable exists.",
                    "- main_result_rule: a strong main experiment is evidence, not the endpoint; usually continue into analysis, writing, or strengthening work.",
                    "- paper_branch_rule: writing should normally continue on a dedicated `paper/*` branch/worktree derived from the evidence line rather than mutating the evidence branch itself.",
                    "- review_gate_rule: before declaring a substantial paper/draft task done, open `review` for an independent skeptical audit; if that audit finds serious gaps, route to `analysis-campaign`, `baseline`, `scout`, or `write` instead of stopping.",
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
            "- response_pattern: say what changed -> say what it means -> say what happens next",
            "- interaction_protocol: first message may be plain conversation; after that, treat artifact.interact threads and mailbox polls as the main continuity spine across TUI, web, and connectors",
            "- shared_interaction_contract_precedence: use the shared interaction contract as the default user-facing cadence; the rules below add runtime-specific execution behavior instead of restating the same chat cadence",
            "- mailbox_protocol: artifact.interact(include_recent_inbound_messages=True) is the queued human-message mailbox; when it returns user text, treat that input as higher priority than background subtasks until it has been acknowledged",
            "- acknowledgment_protocol: after artifact.interact returns any human message, immediately send one substantive artifact.interact(...) follow-up; if the active connector runtime already emitted a transport-level receipt acknowledgement, do not send a redundant receipt-only message; if answerable, answer directly, otherwise state the short plan, nearest checkpoint, and that the current background subtask is paused",
            "- subtask_boundary_protocol: send a user-visible update whenever the active subtask changes materially, especially across intake -> audit, audit -> experiment planning, experiment planning -> run launch, run result -> drafting, or drafting -> review/rebuttal",
            "- smoke_then_detach_protocol: for baseline reproduction, main experiments, and analysis experiments, first validate the command path with a bounded smoke test; once the smoke test passes, launch the real long run with bash_exec(mode='detach', ...) and usually leave timeout_seconds unset rather than guessing a fake deadline",
            "- progress_first_monitoring_protocol: when supervising a long-running bash_exec session, judge health by forward progress rather than by whether the final artifact has already appeared within a short window",
            "- long_run_reporting_protocol: inspect real logs/status after each meaningful await cycle and at least once every 30 minutes at worst, but only send a user-visible update when there is a human-meaningful delta, blocker, recovery, route change, or the visibility bound would otherwise be exceeded",
            "- intervention_threshold_protocol: do not kill or restart a run merely because a short watch window passed without final completion; intervene only on explicit failure, clear invalidity, process exit, or no meaningful delta across a sufficiently long observation window",
            "- timeout_protocol: before using bash_exec(mode='await', ...), estimate whether the command can finish within the selected wait window; if runtime is uncertain or likely longer, use bash_exec(mode='detach', ...) and monitor instead of guessing a fake deadline",
            "- blocking_protocol: use reply_mode='blocking' only for true unresolved user decisions; ordinary progress updates should stay threaded and non-blocking",
            "- credential_blocking_protocol: if continuation requires user-supplied external credentials or secrets such as an API key, GitHub key/token, or Hugging Face key/token, emit one structured blocking decision request that asks the user to provide the credential or choose an alternative route; do not invent placeholders or silently skip the blocked step",
            "- credential_wait_protocol: if that credential request remains unanswered, keep the quest waiting rather than self-resolving; if you are resumed without new credentials and no other work is possible, a long low-frequency park such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable to avoid busy-looping",
            f"- standby_prefix_rule: when you intentionally leave one blocking standby interaction after task completion, prefix it with {'[等待决策]' if chinese_turn else '[Waiting for decision]'} and wait for a new user reply before continuing",
            "- stop_notice_protocol: if work must pause or stop, send a user-visible notice that explains why, confirms preserved context, and states that any new message or `/resume` will continue from the same quest",
            "- respect_protocol: write user-facing updates as natural, respectful, easy-to-follow chat; do not sound like a formal status report or internal tool log",
            "- novice_context_protocol: assume the user may not know the repo layout, branch model, artifact schema, or tool names; explain progress in task language first.",
            "- structure_protocol: when explaining 2 to 3 options, tradeoffs, or next steps, prefer a short numbered structure so the user can scan the decision surface quickly.",
            "- example_and_numbers_protocol: when it materially improves understanding, include one short example or 1 to 3 key numbers or comparisons instead of relying only on vague adjectives such as better, slower, or more stable.",
            "- omission_protocol: for ordinary user-facing updates, omit file paths, file names, artifact ids, branch/worktree ids, session ids, raw commands, raw logs, and internal tool names unless the user asked for them or needs them to act",
            "- compaction_protocol: ordinary artifact.interact progress updates should usually fit in 2 to 4 short sentences and should not read like a monitoring transcript or execution diary",
            "- watchdog_payload_protocol: if a tool result includes `watchdog_notes`, `progress_watchdog_note`, `visibility_watchdog_note`, or `state_change_watchdog_note`, treat that as an action item to inspect state and decide whether a fresh user-visible update is actually needed; do not emit duplicate progress by reflex",
            "- human_progress_shape_protocol: ordinary progress updates should usually make three things explicit in human language: the current task, the main difficulty or latest real progress, and the concrete next measure you will take",
            "- stage_contract_protocol: stage-specific plan/checklist rules, milestone rules, literature rules, and writing rules belong in the requested skill; do not expect this runtime block to restate them",
            "- teammate_voice_protocol: write like a calm capable teammate using natural first-person phrasing when helpful, for example 'I'm working on ...', 'The main issue right now is ...', 'Next I'll ...'; do not sound like a dashboard or incident log",
            "- translation_protocol: convert internal actions into user-facing meaning; describe what was finished and why it matters instead of naming every touched file, path, branch, counter, timestamp, or subprocess",
            "- detail_gate_protocol: include exact counters, worker labels, timestamps, retry counts, or file names only when the user explicitly asked for them, when they change the recommended action, or when they are the only honest way to explain a real blocker",
            "- monitoring_summary_protocol: for long-running monitoring loops, summarize the frontier state in plain language such as still progressing, temporarily stalled, recovered, or needs intervention; do not narrate each watch window",
            "- preflight_rewrite_protocol: before sending artifact.interact, quickly self-check whether the draft reads like a monitoring log, file inventory, or internal diary; if it mentions watch windows, heartbeats, retry counters, raw counts, timestamps, or multiple file names without being necessary for user action, rewrite it into conclusion -> meaning -> next step first",
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
        return "\n".join(
            [
                "- quest_context_rule: quest documents are durable but not pre-expanded here.",
                "- quest_documents_tool: call artifact.read_quest_documents(names=['brief','plan','status','summary'], mode='excerpt'|'full') when document detail is needed.",
                "- active_user_requirements_tool: call artifact.read_quest_documents(names=['active_user_requirements'], mode='full') when exact current durable user requirements matter.",
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
                    f"- paper_contract_health: {'ready' if bool(paper_contract_health.get('writing_ready')) else 'blocked'}",
                    f"- paper_health_counts: unresolved_required={int(paper_contract_health.get('unresolved_required_count') or 0)}, unmapped_completed={int(paper_contract_health.get('unmapped_completed_count') or 0)}, blocking_pending={int(paper_contract_health.get('blocking_open_supplementary_count') or 0)}",
                    f"- paper_recommended_next_stage: {str(paper_contract_health.get('recommended_next_stage') or 'none')}",
                    f"- paper_recommended_action: {str(paper_contract_health.get('recommended_action') or 'none')}",
                    f"- paper_primary_blocker: {primary_blocker}",
                    "- paper_health_tool: call artifact.get_paper_contract_health(detail='full') before paper-facing write/finalize work when the exact blocking items matter.",
                    "- paper_outline_tool: call artifact.list_paper_outlines(...) when outline inventory or a valid outline_id is needed.",
                    "- paper_campaign_tool: call artifact.get_analysis_campaign(campaign_id='active') when exact supplementary slice status matters.",
                ]
            )
            lines.append(
                "- paper_contract_rule: if the paper state is blocked, do not stabilize draft prose as if the paper were settled; follow the recommended paper action first."
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
        return "\n".join(
            [
                f"- stage_memory_rule: for `{stage}`, prefer quest memory kinds [{quest_kinds}] and global memory kinds [{global_kinds}] when memory lookup is needed.",
                "- memory_lookup_tool: call memory.list_recent(...) to recover context after pause/restart and memory.search(...) before repeating prior work.",
                "- memory_injection_rule: memory is intentionally not pre-expanded here; pull only the cards that matter now.",
            ]
        )

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
        return "\n".join(
            [
                "- conversation_context_rule: recent conversation is not pre-expanded here.",
                f"- conversation_tool: call artifact.get_conversation_context(limit={limit}, include_attachments=False) when earlier turn continuity matters.",
            ]
        )

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
