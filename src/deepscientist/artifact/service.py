from __future__ import annotations

import copy
import json
import re
import shutil
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

from ..arxiv_library import ArxivLibraryService
from ..benchstore import BenchStoreService
from ..bridges import register_builtin_connector_bridges
from ..channels import get_channel_factory, register_builtin_channels
from ..config import ConfigManager
from ..connector_runtime import conversation_identity_key, infer_connector_transport, normalize_conversation_id
from ..gitops import (
    branch_exists,
    canonical_worktree_root,
    checkpoint_repo,
    commit_detail,
    compare_refs,
    create_worktree,
    current_branch,
    diff_file_between_refs,
    diff_file_for_commit,
    ensure_branch,
    export_git_graph,
    head_commit,
    log_ref_history,
)
from ..home import repo_root
from ..registries import BaselineRegistry
from ..shared import (
    append_jsonl,
    ensure_dir,
    generate_id,
    read_json,
    read_jsonl,
    read_text,
    read_yaml,
    resolve_within,
    run_command,
    sha256_text,
    slugify,
    utc_now,
    write_json,
    write_text,
    write_yaml,
)
from ..quest import QuestService
from ..memory.frontmatter import dump_markdown_document, load_markdown_document
from .arxiv import fetch_arxiv_metadata, read_arxiv_content
from .charts import render_main_experiment_metric_timeline_chart
from .guidance import build_guidance_for_record, guidance_summary
from .metrics import (
    baseline_metric_lines,
    build_metrics_timeline,
    canonicalize_baseline_submission,
    compare_with_baseline,
    compute_progress_eval,
    MetricContractValidationError,
    normalize_metric_contract,
    normalize_metric_direction,
    normalize_metric_rows,
    normalize_metrics_summary,
    selected_baseline_metrics,
    to_number,
    validate_baseline_metric_contract_submission,
    validate_main_experiment_against_baseline_contract,
)
from .schemas import ARTIFACT_DIRS, guidance_for_kind, validate_artifact_payload

QUEST_COMPLETION_DECISION_TYPE = "quest_completion_approval"
_COMPLETION_APPROVAL_TERMS = (
    "同意完成",
    "确认完成",
    "可以完成",
    "结束任务",
    "同意",
    "approve",
    "approved",
    "complete quest",
    "finish quest",
    "quest complete",
    "yes",
)
_COMPLETION_REJECTION_TERMS = (
    "不同意",
    "不要完成",
    "先不要完成",
    "不要结束",
    "not approve",
    "don't approve",
    "do not approve",
    "do not complete",
    "not yet",
    "keep going",
    "continue instead",
)
_ASCII_COMPLETION_APPROVAL_TERMS = tuple(term for term in _COMPLETION_APPROVAL_TERMS if term.isascii())
_ASCII_COMPLETION_REJECTION_TERMS = tuple(term for term in _COMPLETION_REJECTION_TERMS if term.isascii())
_NON_ASCII_COMPLETION_APPROVAL_TERMS = tuple(term for term in _COMPLETION_APPROVAL_TERMS if not term.isascii())
_NON_ASCII_COMPLETION_REJECTION_TERMS = tuple(term for term in _COMPLETION_REJECTION_TERMS if not term.isascii())
_START_SETUP_FORM_META_KEYS = {"form_patch", "session_patch"}


def _normalize_start_setup_payload_parts(
    form_patch: dict[str, Any] | None,
    session_patch: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    next_form_patch = dict(form_patch or {}) if isinstance(form_patch, dict) else {}
    next_session_patch = dict(session_patch or {}) if isinstance(session_patch, dict) else {}
    nested_form_patch = next_form_patch.get("form_patch")
    nested_session_patch = next_form_patch.get("session_patch")
    nested_suggested_form = next_form_patch.get("suggested_form")
    if isinstance(nested_suggested_form, dict):
        if not isinstance(nested_form_patch, dict) and isinstance(nested_suggested_form.get("form_patch"), dict):
            nested_form_patch = nested_suggested_form.get("form_patch")
        if not isinstance(nested_session_patch, dict) and isinstance(nested_suggested_form.get("session_patch"), dict):
            nested_session_patch = nested_suggested_form.get("session_patch")
    if isinstance(nested_form_patch, dict):
        next_form_patch = dict(nested_form_patch)
    else:
        next_form_patch = {key: value for key, value in next_form_patch.items() if key not in _START_SETUP_FORM_META_KEYS}
    if isinstance(nested_session_patch, dict):
        next_session_patch = {**dict(nested_session_patch), **next_session_patch}
    return next_form_patch, next_session_patch


def _clean_start_setup_suggested_form(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if key not in _START_SETUP_FORM_META_KEYS}


class ArtifactService:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.baselines = BaselineRegistry(home)
        self.quest_service = QuestService(home)
        self.benchstore_service = BenchStoreService(home, repo_root=repo_root())
        self.arxiv_library = ArxivLibraryService()
        self._optimization_frontier_cache_lock = threading.Lock()
        self._optimization_frontier_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _notification_text(value: object) -> str | None:
        text = str(value or "")
        if not text.strip():
            return None
        normalized_lines: list[str] = []
        for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            cleaned = re.sub(r"[ \t]+", " ", raw_line).strip()
            if not cleaned:
                if normalized_lines and normalized_lines[-1] != "":
                    normalized_lines.append("")
                continue
            normalized_lines.append(cleaned)
        while normalized_lines and normalized_lines[-1] == "":
            normalized_lines.pop()
        rendered = "\n".join(normalized_lines).strip()
        return rendered or None

    @classmethod
    def _notification_block(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            lines: list[str] = []
            for key, item in value.items():
                label = cls._format_route_label(key) or str(key).strip()
                block = cls._notification_block(item)
                if not label or not block:
                    continue
                block_lines = block.splitlines()
                if len(block_lines) == 1:
                    lines.append(f"- {label}: {block_lines[0]}")
                    continue
                lines.append(f"- {label}:")
                lines.extend(f"  {line}" if line else "" for line in block_lines)
            return "\n".join(lines).strip() or None
        if isinstance(value, (list, tuple, set)):
            lines = []
            for item in value:
                block = cls._notification_block(item)
                if not block:
                    continue
                block_lines = block.splitlines()
                if not block_lines:
                    continue
                lines.append(f"- {block_lines[0]}")
                lines.extend(f"  {line}" if line else "" for line in block_lines[1:])
            return "\n".join(lines).strip() or None
        return cls._notification_text(value)

    @classmethod
    def _append_notification_section(cls, lines: list[str], label: str, value: object) -> None:
        block = cls._notification_block(value)
        if not block:
            return
        lines.extend(["", f"{label}:", block])

    @staticmethod
    def _append_notification_file_section(lines: list[str], entries: list[tuple[str, str | None]]) -> None:
        normalized = [
            (label, str(path).strip())
            for label, path in entries
            if str(path or "").strip()
        ]
        if not normalized:
            return
        lines.extend(["", "Files:"])
        for label, path in normalized:
            lines.append(f"- {label}: `{path}`")

    def _normalize_evaluation_summary(self, payload: dict[str, Any] | None) -> dict[str, str] | None:
        if not isinstance(payload, dict):
            return None
        normalized: dict[str, str] = {}
        for key in (
            "takeaway",
            "claim_update",
            "baseline_relation",
            "comparability",
            "failure_mode",
            "next_action",
        ):
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                normalized[key] = text
        return normalized or None

    def _evaluation_summary_markdown_lines(self, payload: dict[str, Any] | None) -> list[str]:
        normalized = self._normalize_evaluation_summary(payload)
        if not normalized:
            return ["- Not recorded."]
        labels = (
            ("takeaway", "Takeaway"),
            ("claim_update", "Claim Update"),
            ("baseline_relation", "Baseline Relation"),
            ("comparability", "Comparability"),
            ("failure_mode", "Failure Mode"),
            ("next_action", "Next Action"),
        )
        lines = [f"- {label}: {normalized[key]}" for key, label in labels if normalized.get(key)]
        return lines or ["- Not recorded."]

    @staticmethod
    def _format_route_label(value: object) -> str | None:
        normalized = str(value or "").strip().replace("_", " ").replace("-", " ")
        if not normalized:
            return None
        return " ".join(part.capitalize() for part in normalized.split())

    def _format_foundation_label(self, foundation_ref: dict[str, Any] | None, *, fallback: str | None = None) -> str:
        payload = dict(foundation_ref or {})
        label = self._notification_text(payload.get("label"))
        if label:
            return label
        kind = self._notification_text(payload.get("kind"))
        ref = self._notification_text(payload.get("ref"))
        branch = self._notification_text(payload.get("branch"))
        if kind and ref:
            return f"{kind} {ref}"
        if branch:
            return branch
        return fallback or "current head"

    @staticmethod
    def _clean_text(value: object) -> str | None:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            return None
        return text

    @staticmethod
    def _summary_preview_text(value: object, *, limit: int = 220) -> str | None:
        text = ArtifactService._clean_text(value)
        if not text:
            return None
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _build_idea_interaction_message(
        self,
        *,
        quest_root: Path,
        action: str,
        idea_id: str,
        title: str | None,
        mechanism: str | None,
        method_brief: str | None,
        foundation_label: str | None,
        branch_name: str,
        change_layer: str | None,
        source_lens: str | None,
        expected_gain: str | None,
        next_target: str | None,
    ) -> str:
        normalized_title = self._clean_text(title or idea_id) or idea_id
        design_text = self._clean_text(method_brief or mechanism) or self.quest_service.localized_copy(
            quest_root=quest_root,
            zh="核心设计还未写清楚",
            en="the core design is not written clearly yet",
        )
        compared_target = self._clean_text(foundation_label) or self.quest_service.localized_copy(
            quest_root=quest_root,
            zh="当前方案",
            en="the current approach",
        )
        delta_parts: list[str] = []
        if change_layer:
            delta_parts.append(
                self.quest_service.localized_copy(
                    quest_root=quest_root,
                    zh=f"重点改 `{self._clean_text(change_layer) or change_layer}`",
                    en=f"changes `{self._clean_text(change_layer) or change_layer}` first",
                )
            )
        if source_lens:
            delta_parts.append(
                self.quest_service.localized_copy(
                    quest_root=quest_root,
                    zh=f"引入 `{self._clean_text(source_lens) or source_lens}` 的设计视角",
                    en=f"adds a `{self._clean_text(source_lens) or source_lens}` design angle",
                )
            )
        if not delta_parts:
            delta_parts.append(
                self.quest_service.localized_copy(
                    quest_root=quest_root,
                    zh=f"把 `{design_text}` 直接加到主设计里",
                    en=f"directly adds `{design_text}` into the main design",
                )
            )
        delta_text = self._clean_text("；".join(delta_parts)) or delta_parts[0]
        expected_text = self._clean_text(expected_gain)
        next_target_text = self._format_route_label(next_target) if next_target else None
        if action == "candidate":
            headline = self.quest_service.localized_copy(
                quest_root=quest_root,
                zh=f"收到 idea 候选：{normalized_title}",
                en=f"Idea candidate recorded: {normalized_title}",
            )
        elif action == "revise":
            headline = self.quest_service.localized_copy(
                quest_root=quest_root,
                zh=f"已更新 idea：{normalized_title}（{branch_name}）",
                en=f"Idea updated: {normalized_title} ({branch_name})",
            )
        else:
            headline = self.quest_service.localized_copy(
                quest_root=quest_root,
                zh=f"新 idea：{normalized_title}（{branch_name}）",
                en=f"New idea: {normalized_title} ({branch_name})",
            )
        lines = [
            headline,
            self.quest_service.localized_copy(
                quest_root=quest_root,
                zh=f"创新点：{design_text}",
                en=f"Innovation: {design_text}",
            ),
            self.quest_service.localized_copy(
                quest_root=quest_root,
                zh=f"相对 {compared_target}：{delta_text}",
                en=f"Compared with {compared_target}: {delta_text}",
            ),
        ]
        if expected_text:
            lines.append(
                self.quest_service.localized_copy(
                    quest_root=quest_root,
                    zh=f"预期收益：{expected_text}",
                    en=f"Expected gain: {expected_text}",
                )
            )
        elif next_target_text:
            lines.append(
                self.quest_service.localized_copy(
                    quest_root=quest_root,
                    zh=f"下一步：{next_target_text}",
                    en=f"Next step: {next_target_text}",
                )
            )
        return "\n".join(lines)

    def _build_main_experiment_interaction_message(
        self,
        *,
        run_id: str,
        branch_name: str,
        verdict: str,
        primary_metric_id: str | None,
        primary_value: object,
        primary_baseline: object,
        primary_delta: object,
        decimals: int | None,
        conclusion: str | None,
        evaluation_summary: dict[str, str] | None,
        breakthrough_level: str | None,
        recommended_next_route: str | None,
        run_md_rel_path: str | None,
        result_json_rel_path: str | None,
    ) -> str:
        lines = [f"Main experiment `{run_id}` finished on branch `{branch_name}`."]
        outcome_lines: list[str] = []
        if primary_metric_id and primary_value is not None:
            metric_text = f"{primary_metric_id}={self._format_metric_value(primary_value, decimals)}"
            if primary_baseline is not None and primary_delta is not None:
                metric_text += (
                    f", baseline={self._format_metric_value(primary_baseline, decimals)}, "
                    f"delta={self._format_metric_value(primary_delta, decimals)}"
                )
            outcome_lines.append(f"- Metric: {metric_text}")
        outcome_lines.append(f"- Verdict: {self._format_route_label(verdict) or verdict}")
        if self._notification_text(breakthrough_level):
            outcome_lines.append(f"- Breakthrough level: {self._notification_text(breakthrough_level)}")
        if recommended_next_route:
            outcome_lines.append(
                f"- Recommended next route: {self._format_route_label(recommended_next_route) or recommended_next_route}"
            )
        if outcome_lines:
            lines.extend(["", "Outcome:", *outcome_lines])
        self._append_notification_section(
            lines,
            "Conclusion",
            self._notification_text(conclusion) or (evaluation_summary or {}).get("takeaway"),
        )
        normalized_evaluation_summary = self._normalize_evaluation_summary(evaluation_summary)
        if normalized_evaluation_summary:
            lines.extend(["", "Evaluation summary:", *self._evaluation_summary_markdown_lines(normalized_evaluation_summary)])
        self._append_notification_file_section(
            lines,
            [
                ("Run log", run_md_rel_path),
                ("Result", result_json_rel_path),
            ],
        )
        return "\n".join(lines)

    def _main_experiment_chart_dir(self, workspace_root: Path, *, run_id: str) -> Path:
        return ensure_dir(workspace_root / "experiments" / "main" / run_id / "connector-charts")

    def _generate_main_experiment_metric_charts(
        self,
        quest_root: Path,
        *,
        workspace_root: Path,
        run_id: str,
    ) -> list[dict[str, Any]]:
        timeline = self.quest_service.metrics_timeline(self._quest_id(quest_root))
        chart_dir = self._main_experiment_chart_dir(workspace_root, run_id=run_id)
        charts: list[dict[str, Any]] = []
        for series in timeline.get("series") or []:
            if not isinstance(series, dict):
                continue
            points = [dict(item) for item in (series.get("points") or []) if isinstance(item, dict)]
            if not points:
                continue
            latest_point = points[-1]
            if str(latest_point.get("run_id") or "").strip() != run_id:
                continue
            metric_id = str(series.get("metric_id") or "").strip()
            if not metric_id:
                continue
            output_path = chart_dir / f"{slugify(metric_id, 'metric')}-timeline.png"
            chart_payload = render_main_experiment_metric_timeline_chart(
                series=series,
                output_path=output_path,
            )
            charts.append(chart_payload)
        return charts

    def _auto_metric_chart_targets(
        self,
        quest_root: Path,
        *,
        connectors: dict[str, Any],
    ) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for target in self._bound_conversations(quest_root):
            channel_name = self._normalize_channel_name(target)
            if channel_name not in {"qq", "weixin"}:
                continue
            channel_config = connectors.get(channel_name) if isinstance(connectors.get(channel_name), dict) else {}
            if not bool(channel_config.get("enabled", False)):
                continue
            if not bool(channel_config.get("auto_send_main_experiment_png", True)):
                continue
            targets.append((target, channel_name))
        return targets

    def _send_main_experiment_metric_charts(
        self,
        quest_root: Path,
        *,
        run_id: str,
        title: str,
        charts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        connectors = self._connectors_config()
        targets = self._auto_metric_chart_targets(quest_root, connectors=connectors)
        if not charts or not targets:
            return {
                "enabled": False,
                "chart_count": len(charts),
                "target_count": len(targets),
                "targets": [target for target, _ in targets],
                "deliveries": [],
            }

        deliveries: list[dict[str, Any]] = []
        for chart_index, chart in enumerate(charts):
            label = str(chart.get("label") or chart.get("metric_id") or "metric").strip() or "metric"
            path = str(chart.get("path") or "").strip()
            if not path:
                continue
            message = f"Main experiment metric chart · {label}"
            attachments = [
                {
                    "kind": "path",
                    "path": path,
                    "label": label,
                    "content_type": "image/png",
                    "connector_delivery": {
                        "qq": {
                            "media_kind": "image",
                            "allow_internal_auto_media": True,
                        },
                        "weixin": {
                            "media_kind": "image",
                        },
                    },
                }
            ]
            for target, channel_name in targets:
                payload = {
                    "quest_root": str(quest_root),
                    "quest_id": self._quest_id(quest_root),
                    "conversation_id": target,
                    "kind": "main_experiment_metric_chart",
                    "message": message,
                    "response_phase": "push",
                    "importance": "info",
                    "attachments": attachments,
                }
                delivery_result = self._deliver_to_channel(
                    channel_name,
                    payload,
                    connectors=connectors,
                )
                deliveries.append(
                    {
                        "target": target,
                        "channel": channel_name,
                        "metric_id": chart.get("metric_id"),
                        "label": label,
                        "path": path,
                        "delivery": delivery_result,
                    }
                )
            if chart_index < len(charts) - 1:
                time.sleep(2.0)
        return {
            "enabled": True,
            "run_id": run_id,
            "title": title,
            "chart_count": len(charts),
            "target_count": len(targets),
            "targets": [target for target, _ in targets],
            "deliveries": deliveries,
        }

    def _build_outline_interaction_message(
        self,
        *,
        action: str,
        outline_id: str,
        title: str | None,
        selected_reason: str | None,
        story: str | None,
        research_questions: object,
        experimental_designs: object,
        selected_outline_rel_path: str | None,
        outline_selection_rel_path: str | None,
        revised_outline_rel_path: str | None = None,
    ) -> str:
        verb = "selected" if action == "select" else "revised"
        lines = [f"Paper outline `{outline_id}` was {verb} and promoted into the writing stage."]
        self._append_notification_section(lines, "Title", title)
        self._append_notification_section(lines, "Reason", selected_reason)
        self._append_notification_section(lines, "Story", story)
        self._append_notification_section(lines, "Research questions", research_questions)
        self._append_notification_section(lines, "Experimental designs", experimental_designs)
        self._append_notification_section(
            lines,
            "Next route",
            "Continue writing on the paper branch, or launch outline-bound analysis if evidence is still missing.",
        )
        self._append_notification_file_section(
            lines,
            [
                ("Selected outline", selected_outline_rel_path),
                ("Selection note", outline_selection_rel_path),
                ("Revision record", revised_outline_rel_path),
            ],
        )
        return "\n".join(lines)

    def _build_analysis_campaign_interaction_message(
        self,
        *,
        campaign_id: str,
        goal: str | None,
        parent_branch: str,
        selected_outline_ref: str | None,
        first_slice: dict[str, Any],
        todo_manifest_rel_path: str | None,
    ) -> str:
        lines = [f"Analysis campaign `{campaign_id}` is ready from parent branch `{parent_branch}`."]
        self._append_notification_section(lines, "Goal", goal)
        if selected_outline_ref:
            self._append_notification_section(lines, "Selected outline", f"`{selected_outline_ref}`")
        next_slice_lines = [
            f"- Slice: `{first_slice.get('slice_id')}`",
            f"- Branch: `{first_slice.get('branch')}`",
        ]
        if self._notification_text(first_slice.get("title")):
            next_slice_lines.append(f"- Focus: {self._notification_text(first_slice.get('title'))}")
        lines.extend(["", "Next slice:", *next_slice_lines])
        requirement = self._notification_text(first_slice.get("must_not_simplify") or first_slice.get("goal"))
        if requirement:
            self._append_notification_section(lines, "Core requirement", requirement)
        self._append_notification_file_section(lines, [("Todo manifest", todo_manifest_rel_path)])
        return "\n".join(lines)

    def _build_analysis_slice_interaction_message(
        self,
        *,
        campaign_id: str,
        slice_id: str,
        evaluation_summary: dict[str, str] | None,
        claim_impact: str | None,
        next_slice: dict[str, Any],
        mirror_rel_path: str | None,
    ) -> str:
        lines = [f"Analysis slice `{slice_id}` from campaign `{campaign_id}` is complete."]
        normalized_evaluation_summary = self._normalize_evaluation_summary(evaluation_summary)
        if normalized_evaluation_summary:
            lines.extend(["", "Evaluation summary:", *self._evaluation_summary_markdown_lines(normalized_evaluation_summary)])
        self._append_notification_section(lines, "Claim impact", claim_impact)
        lines.extend(
            [
                "",
                "Next slice:",
                f"- Slice: `{next_slice.get('slice_id')}`",
                f"- Branch: `{next_slice.get('branch')}`",
            ]
        )
        requirement = self._notification_text(next_slice.get("must_not_simplify") or next_slice.get("goal"))
        if requirement:
            self._append_notification_section(lines, "Core requirement", requirement)
        self._append_notification_file_section(lines, [("Parent mirror", mirror_rel_path)])
        return "\n".join(lines)

    def _build_analysis_complete_interaction_message(
        self,
        *,
        campaign_id: str,
        completed_slices: list[dict[str, Any]],
        summary_rel_path: str | None,
        writing_branch: str | None,
        writing_worktree_rel_path: str | None,
    ) -> str:
        lines = [f"Analysis campaign `{campaign_id}` is complete."]
        overview_lines = [f"- Completed slices: {len(completed_slices)}"]
        if writing_branch:
            overview_lines.append(f"- Next route: writing is active on branch `{writing_branch}`")
            if writing_worktree_rel_path:
                overview_lines.append(f"- Writing workspace: `{writing_worktree_rel_path}`")
        else:
            overview_lines.append("- Next route: make the next durable decision from the merged analysis evidence.")
        lines.extend(["", "Overview:", *overview_lines])
        completed_slice_lines: list[str] = []
        for item in completed_slices:
            slice_id = str(item.get("slice_id") or "").strip() or "unknown"
            title = self._notification_text(item.get("title"))
            lead = f"- `{slice_id}`"
            if title:
                lead += f": {title}"
            completed_slice_lines.append(lead)
            takeaway = self._notification_text(
                ((item.get("evaluation_summary") or {}) if isinstance(item.get("evaluation_summary"), dict) else {}).get(
                    "takeaway"
                )
            )
            if takeaway:
                completed_slice_lines.append(f"  Takeaway: {takeaway}")
            claim_impact = self._notification_text(item.get("claim_impact"))
            if claim_impact:
                completed_slice_lines.append(f"  Claim impact: {claim_impact}")
        if completed_slice_lines:
            lines.extend(["", "Completed slices:", *completed_slice_lines])
        self._append_notification_file_section(lines, [("Summary", summary_rel_path)])
        return "\n".join(lines)

    def _build_paper_bundle_interaction_message(
        self,
        *,
        title: str | None,
        summary: str | None,
        package_type: str | None,
        paper_branch: str | None,
        source_branch: str | None,
        source_run_id: str | None,
        selected_outline_ref: str | None,
        manifest_rel_path: str | None,
        draft_rel_path: str | None,
        writing_plan_rel_path: str | None,
        references_rel_path: str | None,
        claim_evidence_map_rel_path: str | None,
        evidence_ledger_rel_path: str | None,
        compile_report_rel_path: str | None,
        pdf_rel_path: str | None,
        latex_root_rel_path: str | None,
        baseline_inventory_rel_path: str | None,
        open_source_manifest_rel_path: str | None,
    ) -> str:
        bundle_label = self._notification_text(title) or "paper"
        normalized_package = str(package_type or "draft_checkpoint").strip() or "draft_checkpoint"
        lines = [
            f"Paper {normalized_package.replace('_', ' ')} `{bundle_label}` is recorded on branch `{paper_branch or 'paper'}`."
        ]
        overview_lines: list[str] = []
        if source_branch:
            overview_lines.append(f"- Source branch: `{source_branch}`")
        if source_run_id:
            overview_lines.append(f"- Source run: `{source_run_id}`")
        if selected_outline_ref:
            overview_lines.append(f"- Selected outline: `{selected_outline_ref}`")
        if overview_lines:
            lines.extend(["", "Overview:", *overview_lines])
        self._append_notification_section(lines, "Summary", summary)
        self._append_notification_file_section(
            lines,
            [
                ("Bundle manifest", manifest_rel_path),
                ("Draft", draft_rel_path),
                ("Writing plan", writing_plan_rel_path),
                ("References", references_rel_path),
                ("Claim-evidence map", claim_evidence_map_rel_path),
                ("Evidence ledger", evidence_ledger_rel_path),
                ("Compile report", compile_report_rel_path),
                ("PDF", pdf_rel_path),
                ("LaTeX root", latex_root_rel_path),
                ("Baseline inventory", baseline_inventory_rel_path),
                ("Open-source manifest", open_source_manifest_rel_path),
            ],
        )
        self._append_notification_section(
            lines,
            "Next route",
            (
                "Continue writing/review unless manuscript coverage and submission readiness are both explicit; "
                "only a submission-ready package should route to finalize."
            ),
        )
        return "\n".join(lines)

    def _load_metric_contract_payload(self, quest_root: Path, metric_contract_json_rel_path: str | None) -> dict[str, Any] | None:
        rel_path = str(metric_contract_json_rel_path or "").strip()
        if not rel_path:
            return None
        try:
            resolved_path = resolve_within(quest_root, rel_path)
        except ValueError:
            return None
        if not resolved_path.exists():
            return None
        payload = read_json(resolved_path, {})
        return payload if isinstance(payload, dict) and payload else None

    def _normalize_metric_directions(self, metric_directions: object) -> dict[str, str]:
        if not isinstance(metric_directions, dict):
            return {}
        normalized: dict[str, str] = {}
        for raw_metric_id, raw_direction in metric_directions.items():
            metric_id = str(raw_metric_id or "").strip()
            if not metric_id:
                continue
            normalized[metric_id] = normalize_metric_direction(raw_direction, metric_id=metric_id)
        return normalized

    def _apply_metric_directions_to_contract(
        self,
        *,
        metric_contract: object,
        metric_directions: object,
        baseline_id: str | None = None,
        metrics_summary: object = None,
        metric_rows: object = None,
        primary_metric: object = None,
        baseline_variants: object = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        normalized_contract = normalize_metric_contract(
            metric_contract,
            baseline_id=baseline_id,
            metrics_summary=metrics_summary,
            metric_rows=metric_rows,
            primary_metric=primary_metric,
            baseline_variants=baseline_variants,
        )
        normalized_primary_metric = dict(primary_metric or {}) if isinstance(primary_metric, dict) else None
        overrides = self._normalize_metric_directions(metric_directions)
        if not overrides:
            return normalized_contract, normalized_primary_metric

        metrics_by_id: dict[str, dict[str, Any]] = {}
        ordered_metric_ids: list[str] = []
        for raw_metric in normalized_contract.get("metrics", []):
            if not isinstance(raw_metric, dict):
                continue
            metric_id = str(raw_metric.get("metric_id") or "").strip()
            if not metric_id:
                continue
            metrics_by_id[metric_id] = dict(raw_metric)
            ordered_metric_ids.append(metric_id)
        for metric_id, direction in overrides.items():
            current = metrics_by_id.get(metric_id)
            if current is None:
                current = {
                    "metric_id": metric_id,
                    "label": metric_id,
                    "direction": direction,
                    "unit": None,
                    "decimals": None,
                    "chart_group": "default",
                }
                ordered_metric_ids.append(metric_id)
            else:
                current = {
                    **current,
                    "direction": direction,
                }
            metrics_by_id[metric_id] = current

        primary_metric_id = str(
            (normalized_primary_metric or {}).get("metric_id")
            or (normalized_primary_metric or {}).get("name")
            or (normalized_primary_metric or {}).get("id")
            or normalized_contract.get("primary_metric_id")
            or ""
        ).strip()
        if normalized_primary_metric and primary_metric_id in overrides:
            normalized_primary_metric = {
                **normalized_primary_metric,
                "direction": overrides[primary_metric_id],
            }

        return {
            **normalized_contract,
            "metrics": [metrics_by_id[metric_id] for metric_id in ordered_metric_ids if metric_id in metrics_by_id],
        }, normalized_primary_metric

    def _merge_run_metric_contract(
        self,
        *,
        baseline_metric_contract: object,
        baseline_primary_metric: object,
        baseline_variants: object,
        run_metric_contract: object,
        metrics_summary: object,
        metric_rows: object,
        baseline_id: str | None = None,
    ) -> dict[str, Any]:
        baseline_contract = normalize_metric_contract(
            baseline_metric_contract,
            baseline_id=baseline_id,
            metrics_summary=metrics_summary,
            metric_rows=metric_rows,
            primary_metric=baseline_primary_metric,
            baseline_variants=baseline_variants,
        )
        if not isinstance(run_metric_contract, dict) or not run_metric_contract:
            return baseline_contract

        overlay_contract = normalize_metric_contract(
            run_metric_contract,
            baseline_id=baseline_id,
            metrics_summary=metrics_summary,
            metric_rows=metric_rows,
            primary_metric=baseline_contract.get("primary_metric_id"),
        )
        overlay_metrics: dict[str, dict[str, Any]] = {}
        for raw_metric in overlay_contract.get("metrics", []):
            if not isinstance(raw_metric, dict):
                continue
            metric_id = str(raw_metric.get("metric_id") or "").strip()
            if metric_id:
                overlay_metrics[metric_id] = raw_metric

        merged_metrics: list[dict[str, Any]] = []
        seen_metric_ids: set[str] = set()
        for raw_metric in baseline_contract.get("metrics", []):
            if not isinstance(raw_metric, dict):
                continue
            metric_id = str(raw_metric.get("metric_id") or "").strip()
            if not metric_id:
                continue
            patch = overlay_metrics.get(metric_id) or {}
            merged = dict(raw_metric)
            for field in (
                "label",
                "unit",
                "decimals",
                "chart_group",
                "description",
                "derivation",
                "source_ref",
                "required",
                "origin_path",
            ):
                value = patch.get(field)
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                merged[field] = value
            merged_metrics.append(merged)
            seen_metric_ids.add(metric_id)

        for metric_id, raw_metric in overlay_metrics.items():
            if metric_id in seen_metric_ids:
                continue
            merged_metrics.append(dict(raw_metric))

        merged_contract = {
            **baseline_contract,
            "metrics": merged_metrics,
        }
        if not merged_contract.get("evaluation_protocol") and overlay_contract.get("evaluation_protocol") is not None:
            merged_contract["evaluation_protocol"] = overlay_contract.get("evaluation_protocol")
        for key, value in overlay_contract.items():
            if key in {"contract_id", "primary_metric_id", "metrics", "evaluation_protocol"}:
                continue
            if key not in merged_contract and value is not None:
                merged_contract[key] = value
        return merged_contract

    def _workspace_root_for(self, quest_root: Path, workspace_root: Path | None = None) -> Path:
        if workspace_root is not None:
            return workspace_root
        return self.quest_service.active_workspace_root(quest_root)

    def _workspace_relative(self, quest_root: Path, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return path.resolve().relative_to(quest_root.resolve()).as_posix()
        except ValueError:
            return str(path)

    def _paper_bundle_relative_path(
        self,
        quest_root: Path,
        path: Path | None,
        *,
        workspace_root: Path | None = None,
    ) -> str | None:
        if path is None:
            return None
        resolved = path.resolve()
        roots = [self._workspace_root_for(quest_root, workspace_root), quest_root]
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                return resolved.relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
        return str(path)

    @staticmethod
    def _branch_kind_from_name(branch_name: str | None) -> str:
        normalized = str(branch_name or "").strip()
        if normalized in {"main", "master"} or normalized.startswith("quest/"):
            return "quest"
        if normalized.startswith("idea/"):
            return "idea"
        if normalized.startswith("analysis/"):
            return "analysis"
        if normalized.startswith("paper/"):
            return "paper"
        if normalized.startswith("run/"):
            return "run"
        return "branch"

    def _workspace_mode_for_branch(self, branch_name: str | None, *, has_idea: bool = False) -> str:
        branch_kind = self._branch_kind_from_name(branch_name)
        if branch_kind == "paper":
            return "paper"
        if branch_kind == "analysis":
            return "analysis"
        if branch_kind == "run":
            return "run"
        if branch_kind == "idea" or has_idea:
            return "idea"
        return "quest"

    @staticmethod
    def _collaboration_workspace_mode(state: dict[str, Any]) -> str | None:
        normalized = str(state.get("workspace_mode") or "").strip().lower()
        if normalized in {"copilot", "autonomous"}:
            return normalized
        return None

    def _resolve_workspace_modes(
        self,
        state: dict[str, Any],
        *,
        branch_name: str | None,
        has_idea: bool = False,
    ) -> tuple[str, str]:
        branch_mode = self._workspace_mode_for_branch(branch_name, has_idea=has_idea)
        collaboration_mode = self._collaboration_workspace_mode(state)
        return collaboration_mode or branch_mode, branch_mode

    @staticmethod
    def _active_workspace_branch_mode(state: dict[str, Any], *, branch_name: str | None) -> str:
        normalized = str(state.get("workspace_branch_mode") or "").strip().lower()
        if normalized:
            return normalized
        legacy = str(state.get("workspace_mode") or "").strip().lower()
        if legacy in {"idea", "run", "analysis", "paper", "quest"}:
            return legacy
        branch_kind = str(branch_name or "").strip().lower()
        if branch_kind.startswith("paper/") or branch_kind == "paper":
            return "paper"
        if branch_kind.startswith("analysis/") or branch_kind == "analysis":
            return "analysis"
        if branch_kind.startswith("run/") or branch_kind == "run":
            return "run"
        if branch_kind.startswith("idea/") or branch_kind == "idea":
            return "idea"
        return "quest"

    def _prepare_branch_worktree_root(
        self,
        quest_root: Path,
        *,
        branch_name: str,
        branch_kind: str,
        run_id: str | None = None,
        idea_id: str | None = None,
    ) -> Path:
        normalized_kind = str(branch_kind or "").strip().lower() or "run"
        normalized_run_id = str(run_id or "").strip() or None
        normalized_idea_id = str(idea_id or "").strip() or None
        if normalized_kind == "idea" and normalized_idea_id:
            return canonical_worktree_root(quest_root, f"idea-{normalized_idea_id}")
        if normalized_kind == "paper":
            return canonical_worktree_root(
                quest_root,
                f"paper-{normalized_run_id or slugify(branch_name, 'paper')}",
            )
        if normalized_kind == "run" and normalized_run_id:
            return canonical_worktree_root(quest_root, normalized_run_id)
        return canonical_worktree_root(quest_root, slugify(branch_name, "branch"))

    def _latest_prepare_branch_record(self, quest_root: Path, branch_name: str) -> dict[str, Any]:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            return {}
        for item in reversed(self.quest_service._collect_artifacts(quest_root)):
            payload = dict(item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}
            if not payload:
                continue
            if str(payload.get("kind") or "").strip() != "decision":
                continue
            if str(payload.get("action") or "").strip() != "prepare_branch":
                continue
            if str(payload.get("branch") or "").strip() != normalized_branch:
                continue
            return payload
        return {}

    def _git_config(self) -> dict[str, Any]:
        config = ConfigManager(self.home).load_named("config")
        payload = config.get("git") if isinstance(config.get("git"), dict) else {}
        return payload if isinstance(payload, dict) else {}

    def _should_auto_push(self) -> bool:
        return bool(self._git_config().get("auto_push", False))

    def _default_remote(self) -> str:
        return str(self._git_config().get("default_remote") or "origin").strip() or "origin"

    def _checkpoint_with_optional_push(
        self,
        workspace_root: Path,
        *,
        message: str,
        allow_empty: bool = False,
        push: bool | None = None,
    ) -> dict[str, Any]:
        commit_result = checkpoint_repo(workspace_root, message, allow_empty=allow_empty)
        push_enabled = self._should_auto_push() if push is None else bool(push)
        push_result: dict[str, Any] | None = None
        if push_enabled and bool(commit_result.get("committed")):
            branch = str(commit_result.get("branch") or current_branch(workspace_root) or "")
            remote = self._default_remote()
            result = run_command(["git", "push", remote, branch], cwd=workspace_root, check=False)
            push_result = {
                "attempted": True,
                "ok": result.returncode == 0,
                "remote": remote,
                "branch": branch,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        elif push_enabled:
            push_result = {
                "attempted": False,
                "ok": False,
                "remote": self._default_remote(),
                "branch": str(commit_result.get("branch") or current_branch(workspace_root) or ""),
                "stdout": "",
                "stderr": "No new commit was created.",
            }
        return {
            **commit_result,
            "push": push_result,
        }

    def _build_idea_markdown(
        self,
        *,
        idea_id: str,
        quest_id: str,
        title: str,
        problem: str,
        hypothesis: str,
        mechanism: str,
        expected_gain: str,
        risks: list[str],
        evidence_paths: list[str],
        decision_reason: str,
        next_target: str,
        branch: str,
        worktree_root: Path,
        method_brief: str = "",
        selection_scores: dict[str, Any] | None = None,
        mechanism_family: str = "",
        change_layer: str = "",
        source_lens: str = "",
        foundation_ref: dict[str, Any] | None = None,
        foundation_reason: str = "",
        lineage_intent: str | None = None,
        created_at: str | None = None,
    ) -> str:
        normalized_foundation = dict(foundation_ref or {})
        normalized_lineage_intent = str(lineage_intent or "").strip().lower() or None
        normalized_method_brief = str(method_brief or "").strip()
        normalized_selection_scores = self._normalize_selection_scores(selection_scores)
        normalized_mechanism_family = str(mechanism_family or "").strip() or None
        normalized_change_layer = str(change_layer or "").strip() or None
        normalized_source_lens = str(source_lens or "").strip() or None
        tags = [f"branch:{branch}", f"next:{next_target}"]
        if normalized_lineage_intent:
            tags.append(f"lineage:{normalized_lineage_intent}")
        if normalized_mechanism_family:
            tags.append(f"family:{slugify(normalized_mechanism_family, 'family')}")
        metadata = {
            "id": idea_id,
            "type": "ideas",
            "kind": "idea",
            "title": title,
            "quest_id": quest_id,
            "scope": "quest",
            "branch": branch,
            "worktree_root": str(worktree_root),
            "next_target": next_target,
            "method_brief": normalized_method_brief or None,
            "selection_scores": normalized_selection_scores or None,
            "mechanism_family": normalized_mechanism_family,
            "change_layer": normalized_change_layer,
            "source_lens": normalized_source_lens,
            "foundation_ref": normalized_foundation or None,
            "foundation_reason": foundation_reason.strip() or None,
            "lineage_intent": normalized_lineage_intent,
            "created_at": created_at or utc_now(),
            "updated_at": utc_now(),
            "tags": tags,
        }
        body_lines = [
            f"# {title}",
            "",
            "## Problem",
            "",
            problem.strip() or "TBD",
            "",
            "## Hypothesis",
            "",
            hypothesis.strip() or "TBD",
            "",
            "## Mechanism",
            "",
            mechanism.strip() or "TBD",
            "",
            "## Method Brief",
            "",
            normalized_method_brief or "Not recorded",
            "",
            "## Expected Gain",
            "",
            expected_gain.strip() or "TBD",
            "",
            "## Selection Scores",
            "",
            *self._selection_score_lines(normalized_selection_scores),
            "",
            "## Diversity Tags",
            "",
            f"- Mechanism family: {normalized_mechanism_family or 'Not recorded'}",
            f"- Change layer: {normalized_change_layer or 'Not recorded'}",
            f"- Source lens: {normalized_source_lens or 'Not recorded'}",
            "",
            "## Decision Reason",
            "",
            decision_reason.strip() or "TBD",
            "",
            "## Foundation",
            "",
        ]
        if normalized_foundation:
            body_lines.extend(
                [
                    f"- Lineage Intent: `{normalized_lineage_intent or 'manual'}`",
                    f"- Kind: `{normalized_foundation.get('kind') or 'unknown'}`",
                    f"- Ref: `{normalized_foundation.get('ref') or 'none'}`",
                    f"- Branch: `{normalized_foundation.get('branch') or 'none'}`",
                    f"- Worktree: `{normalized_foundation.get('worktree_root') or 'none'}`",
                    f"- Reason: {foundation_reason.strip() or 'No explicit reason recorded.'}",
                    "",
                ]
            )
        else:
            body_lines.extend(["- Default current head foundation.", "", ""])
        body_lines.extend(
            [
            "## Risks",
            "",
            ]
        )
        if risks:
            body_lines.extend([f"- {item}" for item in risks])
        else:
            body_lines.append("- None recorded yet.")
        body_lines.extend(["", "## Evidence Paths", ""])
        if evidence_paths:
            body_lines.extend([f"- `{item}`" for item in evidence_paths])
        else:
            body_lines.append("- None recorded yet.")
        body_lines.extend(
            [
                "",
                "## Next Target",
                "",
                next_target.strip() or "experiment",
                "",
            ]
        )
        return dump_markdown_document(metadata, "\n".join(body_lines).rstrip() + "\n")

    def _build_idea_draft_markdown(
        self,
        *,
        idea_id: str,
        quest_id: str,
        title: str,
        problem: str,
        hypothesis: str,
        mechanism: str,
        expected_gain: str,
        risks: list[str],
        evidence_paths: list[str],
        decision_reason: str,
        next_target: str,
        branch: str,
        worktree_root: Path,
        method_brief: str = "",
        selection_scores: dict[str, Any] | None = None,
        mechanism_family: str = "",
        change_layer: str = "",
        source_lens: str = "",
        foundation_ref: dict[str, Any] | None = None,
        foundation_reason: str = "",
        lineage_intent: str | None = None,
        created_at: str | None = None,
        draft_markdown: str = "",
    ) -> str:
        normalized_foundation = dict(foundation_ref or {})
        normalized_lineage_intent = str(lineage_intent or "").strip().lower() or None
        normalized_method_brief = str(method_brief or "").strip()
        normalized_selection_scores = self._normalize_selection_scores(selection_scores)
        normalized_mechanism_family = str(mechanism_family or "").strip() or None
        normalized_change_layer = str(change_layer or "").strip() or None
        normalized_source_lens = str(source_lens or "").strip() or None
        metadata = {
            "id": f"{idea_id}-draft",
            "type": "ideas",
            "kind": "idea_draft",
            "title": f"{title} Draft",
            "idea_id": idea_id,
            "quest_id": quest_id,
            "scope": "quest",
            "branch": branch,
            "worktree_root": str(worktree_root),
            "next_target": next_target,
            "method_brief": normalized_method_brief or None,
            "selection_scores": normalized_selection_scores or None,
            "mechanism_family": normalized_mechanism_family,
            "change_layer": normalized_change_layer,
            "source_lens": normalized_source_lens,
            "foundation_ref": normalized_foundation or None,
            "foundation_reason": foundation_reason.strip() or None,
            "lineage_intent": normalized_lineage_intent,
            "created_at": created_at or utc_now(),
            "updated_at": utc_now(),
            "tags": [
                f"branch:{branch}",
                "idea-draft",
                *( [f"lineage:{normalized_lineage_intent}"] if normalized_lineage_intent else []),
            ],
        }
        body = str(draft_markdown or "").strip()
        if not body:
            foundation_label = (
                normalized_foundation.get("label")
                or normalized_foundation.get("branch")
                or normalized_foundation.get("ref")
                or "current head"
            )
            risk_lines = "\n".join(f"- {item}" for item in risks) if risks else "- None recorded yet."
            evidence_lines = (
                "\n".join(f"- `{item}`" for item in evidence_paths)
                if evidence_paths
                else "- None recorded yet."
            )
            selection_score_lines = (
                "\n".join(self._selection_score_lines(normalized_selection_scores))
                if normalized_selection_scores
                else "- Not recorded"
            )
            body = "\n".join(
                [
                    f"# {title}",
                    "",
                    "## Executive Summary",
                    "",
                    decision_reason.strip() or "This draft records the selected idea before implementation.",
                    "",
                    "## Limitation / Bottleneck",
                    "",
                    problem.strip() or "TBD",
                    "",
                    "## Selected Claim",
                    "",
                    hypothesis.strip() or "TBD",
                    "",
                    "## Theory and Method",
                    "",
                    mechanism.strip() or "TBD",
                    "",
                    "## Method Brief",
                    "",
                    normalized_method_brief or "Not recorded",
                    "",
                    "## Selection Scores",
                    "",
                    selection_score_lines,
                    "",
                    "## Diversity Tags",
                    "",
                    f"- Mechanism family: {normalized_mechanism_family or 'Not recorded'}",
                    f"- Change layer: {normalized_change_layer or 'Not recorded'}",
                    f"- Source lens: {normalized_source_lens or 'Not recorded'}",
                    "",
                    "## Code-Level Change Plan",
                    "",
                    mechanism.strip() or "TBD",
                    "",
                    "## Evaluation / Falsification Plan",
                    "",
                    expected_gain.strip() or "TBD",
                    "",
                    "## Risks / Caveats / Implementation Notes",
                    "",
                    risk_lines,
                    "",
                    "## Evidence / References",
                    "",
                    evidence_lines,
                    "",
                    "## Foundation Choice",
                    "",
                    f"- Lineage intent: `{normalized_lineage_intent or 'manual'}`",
                    f"- Foundation: `{foundation_label}`",
                    f"- Reason: {foundation_reason.strip() or 'Use the current active foundation.'}",
                    "",
                    "## Next Target",
                    "",
                    next_target.strip() or "experiment",
                    "",
                ]
        )
        return dump_markdown_document(metadata, body.rstrip() + "\n")

    def _idea_candidate_root(self, quest_root: Path, idea_id: str) -> Path:
        return ensure_dir(quest_root / "memory" / "ideas" / "_candidates" / idea_id)

    def _build_candidate_idea_markdown(
        self,
        *,
        idea_id: str,
        quest_id: str,
        title: str,
        problem: str,
        hypothesis: str,
        mechanism: str,
        expected_gain: str,
        risks: list[str],
        evidence_paths: list[str],
        decision_reason: str,
        next_target: str,
        candidate_root: Path,
        method_brief: str = "",
        selection_scores: dict[str, Any] | None = None,
        mechanism_family: str = "",
        change_layer: str = "",
        source_lens: str = "",
        foundation_ref: dict[str, Any] | None = None,
        foundation_reason: str = "",
        lineage_intent: str | None = None,
    ) -> str:
        normalized_foundation = dict(foundation_ref or {})
        normalized_lineage_intent = str(lineage_intent or "").strip().lower() or None
        normalized_method_brief = str(method_brief or "").strip()
        normalized_selection_scores = self._normalize_selection_scores(selection_scores)
        normalized_mechanism_family = str(mechanism_family or "").strip() or None
        normalized_change_layer = str(change_layer or "").strip() or None
        normalized_source_lens = str(source_lens or "").strip() or None
        metadata = {
            "id": idea_id,
            "type": "ideas",
            "kind": "idea_candidate",
            "title": title,
            "quest_id": quest_id,
            "scope": "quest",
            "submission_mode": "candidate",
            "candidate_root": str(candidate_root),
            "next_target": next_target,
            "method_brief": normalized_method_brief or None,
            "selection_scores": normalized_selection_scores or None,
            "mechanism_family": normalized_mechanism_family,
            "change_layer": normalized_change_layer,
            "source_lens": normalized_source_lens,
            "foundation_ref": normalized_foundation or None,
            "foundation_reason": foundation_reason.strip() or None,
            "lineage_intent": normalized_lineage_intent,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "tags": [
                "idea-candidate",
                f"next:{next_target}",
                *( [f"lineage:{normalized_lineage_intent}"] if normalized_lineage_intent else []),
            ],
        }
        body_lines = [
            f"# {title}",
            "",
            "## Candidate Summary",
            "",
            decision_reason.strip() or "This candidate is recorded for later ranking or promotion.",
            "",
            "## Problem",
            "",
            problem.strip() or "TBD",
            "",
            "## Hypothesis",
            "",
            hypothesis.strip() or "TBD",
            "",
            "## Mechanism",
            "",
            mechanism.strip() or "TBD",
            "",
            "## Method Brief",
            "",
            normalized_method_brief or "Not recorded",
            "",
            "## Expected Gain",
            "",
            expected_gain.strip() or "TBD",
            "",
            "## Selection Scores",
            "",
            *self._selection_score_lines(normalized_selection_scores),
            "",
            "## Diversity Tags",
            "",
            f"- Mechanism family: {normalized_mechanism_family or 'Not recorded'}",
            f"- Change layer: {normalized_change_layer or 'Not recorded'}",
            f"- Source lens: {normalized_source_lens or 'Not recorded'}",
            "",
            "## Risks",
            "",
        ]
        if risks:
            body_lines.extend([f"- {item}" for item in risks])
        else:
            body_lines.append("- None recorded yet.")
        body_lines.extend(["", "## Evidence Paths", ""])
        if evidence_paths:
            body_lines.extend([f"- `{item}`" for item in evidence_paths])
        else:
            body_lines.append("- None recorded yet.")
        body_lines.extend(["", "## Foundation", ""])
        if normalized_foundation:
            body_lines.extend(
                [
                    f"- Lineage intent: `{normalized_lineage_intent or 'manual'}`",
                    f"- Kind: `{normalized_foundation.get('kind') or 'unknown'}`",
                    f"- Ref: `{normalized_foundation.get('ref') or 'none'}`",
                    f"- Branch: `{normalized_foundation.get('branch') or 'none'}`",
                    f"- Reason: {foundation_reason.strip() or 'No explicit reason recorded.'}",
                ]
            )
        else:
            body_lines.append("- Default current head foundation.")
        body_lines.extend(
            [
                "",
                "## Next Target",
                "",
                next_target.strip() or "experiment",
                "",
            ]
        )
        return dump_markdown_document(metadata, "\n".join(body_lines).rstrip() + "\n")

    def _build_candidate_idea_draft_markdown(
        self,
        *,
        idea_id: str,
        quest_id: str,
        title: str,
        problem: str,
        hypothesis: str,
        mechanism: str,
        expected_gain: str,
        risks: list[str],
        evidence_paths: list[str],
        decision_reason: str,
        next_target: str,
        candidate_root: Path,
        method_brief: str = "",
        selection_scores: dict[str, Any] | None = None,
        mechanism_family: str = "",
        change_layer: str = "",
        source_lens: str = "",
        foundation_ref: dict[str, Any] | None = None,
        foundation_reason: str = "",
        lineage_intent: str | None = None,
        draft_markdown: str = "",
    ) -> str:
        normalized_foundation = dict(foundation_ref or {})
        normalized_lineage_intent = str(lineage_intent or "").strip().lower() or None
        normalized_method_brief = str(method_brief or "").strip()
        normalized_selection_scores = self._normalize_selection_scores(selection_scores)
        normalized_mechanism_family = str(mechanism_family or "").strip() or None
        normalized_change_layer = str(change_layer or "").strip() or None
        normalized_source_lens = str(source_lens or "").strip() or None
        metadata = {
            "id": f"{idea_id}-candidate-draft",
            "type": "ideas",
            "kind": "idea_candidate_draft",
            "title": f"{title} Candidate Draft",
            "idea_id": idea_id,
            "quest_id": quest_id,
            "scope": "quest",
            "submission_mode": "candidate",
            "candidate_root": str(candidate_root),
            "next_target": next_target,
            "method_brief": normalized_method_brief or None,
            "selection_scores": normalized_selection_scores or None,
            "mechanism_family": normalized_mechanism_family,
            "change_layer": normalized_change_layer,
            "source_lens": normalized_source_lens,
            "foundation_ref": normalized_foundation or None,
            "foundation_reason": foundation_reason.strip() or None,
            "lineage_intent": normalized_lineage_intent,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "tags": [
                "idea-candidate-draft",
                f"next:{next_target}",
                *( [f"lineage:{normalized_lineage_intent}"] if normalized_lineage_intent else []),
            ],
        }
        body = str(draft_markdown or "").strip()
        if not body:
            risk_lines = "\n".join(f"- {item}" for item in risks) if risks else "- None recorded yet."
            evidence_lines = "\n".join(f"- `{item}`" for item in evidence_paths) if evidence_paths else "- None recorded yet."
            selection_score_lines = (
                "\n".join(self._selection_score_lines(normalized_selection_scores))
                if normalized_selection_scores
                else "- Not recorded"
            )
            foundation_label = (
                normalized_foundation.get("label")
                or normalized_foundation.get("branch")
                or normalized_foundation.get("ref")
                or "current head"
            )
            body = "\n".join(
                [
                    f"# {title}",
                    "",
                    "## Executive Summary",
                    "",
                    decision_reason.strip() or "This candidate draft records a possible optimization line before promotion.",
                    "",
                    "## Limitation / Bottleneck",
                    "",
                    problem.strip() or "TBD",
                    "",
                    "## Selected Claim",
                    "",
                    hypothesis.strip() or "TBD",
                    "",
                    "## Theory and Method",
                    "",
                    mechanism.strip() or "TBD",
                    "",
                    "## Method Brief",
                    "",
                    normalized_method_brief or "Not recorded",
                    "",
                    "## Selection Scores",
                    "",
                    selection_score_lines,
                    "",
                    "## Diversity Tags",
                    "",
                    f"- Mechanism family: {normalized_mechanism_family or 'Not recorded'}",
                    f"- Change layer: {normalized_change_layer or 'Not recorded'}",
                    f"- Source lens: {normalized_source_lens or 'Not recorded'}",
                    "",
                    "## Code-Level Change Plan",
                    "",
                    mechanism.strip() or "TBD",
                    "",
                    "## Evaluation / Falsification Plan",
                    "",
                    expected_gain.strip() or "TBD",
                    "",
                    "## Risks / Caveats / Implementation Notes",
                    "",
                    risk_lines,
                    "",
                    "## Evidence / References",
                    "",
                    evidence_lines,
                    "",
                    "## Foundation Choice",
                    "",
                    f"- Lineage intent: `{normalized_lineage_intent or 'manual'}`",
                    f"- Foundation: `{foundation_label}`",
                    f"- Reason: {foundation_reason.strip() or 'Use the current active foundation.'}",
                    "",
                    "## Next Target",
                    "",
                    next_target.strip() or "experiment",
                    "",
                ]
            )
        return dump_markdown_document(metadata, body.rstrip() + "\n")

    @staticmethod
    def _normalize_selection_scores(value: object) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            if isinstance(raw_value, bool):
                normalized[key] = raw_value
                continue
            numeric = to_number(raw_value)
            if numeric is not None:
                normalized[key] = int(numeric) if float(numeric).is_integer() else float(numeric)
                continue
            text = str(raw_value or "").strip()
            if text:
                normalized[key] = text
        return normalized or None

    @staticmethod
    def _selection_score_lines(selection_scores: dict[str, Any] | None) -> list[str]:
        if not selection_scores:
            return ["- Not recorded"]
        lines: list[str] = []
        for key, value in selection_scores.items():
            if isinstance(value, float):
                rendered = f"{value:.4f}".rstrip("0").rstrip(".")
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
        return lines

    def _analysis_manifest_path(self, quest_root: Path, campaign_id: str) -> Path:
        return ensure_dir(quest_root / ".ds" / "analysis_campaigns") / f"{campaign_id}.json"

    def _read_analysis_manifest(self, quest_root: Path, campaign_id: str) -> dict[str, Any]:
        path = self._analysis_manifest_path(quest_root, campaign_id)
        payload = read_json(path, {})
        if not isinstance(payload, dict) or not payload:
            raise FileNotFoundError(f"Unknown analysis campaign `{campaign_id}`.")
        return payload

    def _write_analysis_manifest(self, quest_root: Path, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._analysis_manifest_path(quest_root, campaign_id)
        normalized = {**payload, "campaign_id": campaign_id, "updated_at": utc_now()}
        write_json(path, normalized)
        return normalized

    def _analysis_baseline_inventory_path(self, quest_root: Path) -> Path:
        return ensure_dir(quest_root / "artifacts" / "baselines") / "analysis_inventory.json"

    def _read_analysis_baseline_inventory(self, quest_root: Path) -> dict[str, Any]:
        path = self._analysis_baseline_inventory_path(quest_root)
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        return {
            "schema_version": 1,
            "entries": [dict(item) for item in entries if isinstance(item, dict)],
            "updated_at": payload.get("updated_at"),
        }

    def _write_analysis_baseline_inventory(self, quest_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._analysis_baseline_inventory_path(quest_root)
        normalized_entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        normalized = {
            "schema_version": 1,
            "entries": [dict(item) for item in normalized_entries if isinstance(item, dict)],
            "updated_at": utc_now(),
        }
        write_json(path, normalized)
        return normalized

    def _normalize_baseline_root_rel_path(
        self,
        quest_root: Path,
        baseline_root_rel_path: str | None,
        *,
        baseline_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        raw = str(baseline_root_rel_path or "").strip()
        if not raw:
            return None, None
        candidate = Path(raw)
        resolved = candidate.resolve() if candidate.is_absolute() else resolve_within(quest_root, raw)
        if not resolved.exists():
            raise FileNotFoundError(f"Baseline root does not exist: {resolved}")
        try:
            relative = resolved.relative_to(quest_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("`baseline_root_rel_path` must stay within quest_root.") from exc
        parts = Path(relative).parts
        if len(parts) < 3 or parts[0] != "baselines" or parts[1] not in {"local", "imported"}:
            raise ValueError(
                "`baseline_root_rel_path` must live under `baselines/local/<baseline_id>/...` or "
                "`baselines/imported/<baseline_id>/...`."
            )
        normalized_baseline_id = str(baseline_id or parts[2]).strip() or None
        if normalized_baseline_id and parts[2] != normalized_baseline_id:
            raise ValueError(
                f"`baseline_root_rel_path` points to baseline `{parts[2]}`, which does not match `{normalized_baseline_id}`."
            )
        return relative, parts[1]

    @staticmethod
    def _analysis_baseline_label(payload: dict[str, Any]) -> str:
        baseline_id = str(payload.get("baseline_id") or "baseline").strip() or "baseline"
        parts = [f"`{baseline_id}`"]
        variant_id = str(payload.get("variant_id") or "").strip()
        if variant_id:
            parts.append(f"variant `{variant_id}`")
        benchmark = str(payload.get("benchmark") or "").strip()
        split = str(payload.get("split") or "").strip()
        if benchmark and split:
            parts.append(f"benchmark `{benchmark}` / split `{split}`")
        elif benchmark:
            parts.append(f"benchmark `{benchmark}`")
        elif split:
            parts.append(f"split `{split}`")
        reason = str(payload.get("reason") or "").strip()
        if reason:
            parts.append(f"reason: {reason}")
        return " · ".join(parts)

    def _normalize_required_baselines(self, quest_root: Path, values: list[object] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in values or []:
            if not isinstance(raw, dict):
                continue
            baseline_id = str(raw.get("baseline_id") or "").strip()
            if not baseline_id:
                continue
            baseline_root_rel_path, storage_mode = self._normalize_baseline_root_rel_path(
                quest_root,
                raw.get("baseline_root_rel_path"),
                baseline_id=baseline_id,
            )
            normalized.append(
                {
                    "baseline_id": baseline_id,
                    "variant_id": str(raw.get("variant_id") or "").strip() or None,
                    "reason": str(raw.get("reason") or "").strip() or None,
                    "benchmark": str(raw.get("benchmark") or "").strip() or None,
                    "split": str(raw.get("split") or "").strip() or None,
                    "baseline_root_rel_path": baseline_root_rel_path,
                    "storage_mode": storage_mode or (str(raw.get("storage_mode") or "").strip() or None),
                    "usage_scope": "supplementary",
                }
            )
        return normalized

    def _normalize_comparison_baselines(self, quest_root: Path, values: list[object] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in values or []:
            if not isinstance(raw, dict):
                continue
            baseline_id = str(raw.get("baseline_id") or "").strip()
            if not baseline_id:
                continue
            baseline_root_rel_path, storage_mode = self._normalize_baseline_root_rel_path(
                quest_root,
                raw.get("baseline_root_rel_path"),
                baseline_id=baseline_id,
            )
            metrics_summary = (
                normalize_metrics_summary(raw.get("metrics_summary"))
                if isinstance(raw.get("metrics_summary"), dict)
                else {}
            )
            normalized.append(
                {
                    "baseline_id": baseline_id,
                    "variant_id": str(raw.get("variant_id") or "").strip() or None,
                    "benchmark": str(raw.get("benchmark") or "").strip() or None,
                    "split": str(raw.get("split") or "").strip() or None,
                    "reason": str(raw.get("reason") or "").strip() or None,
                    "metrics_summary": metrics_summary,
                    "evidence_paths": [
                        str(item).strip() for item in (raw.get("evidence_paths") or []) if str(item).strip()
                    ],
                    "baseline_root_rel_path": baseline_root_rel_path,
                    "storage_mode": storage_mode or (str(raw.get("storage_mode") or "").strip() or None),
                    "usage_scope": "supplementary",
                    "published": bool(raw.get("published", False)),
                    "published_entry_id": str(raw.get("published_entry_id") or "").strip() or None,
                    "status": str(raw.get("status") or "registered").strip() or "registered",
                }
            )
        return normalized

    @staticmethod
    def _analysis_inventory_entry_key(payload: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
        origin = dict(payload.get("origin") or {}) if isinstance(payload.get("origin"), dict) else {}
        return (
            str(payload.get("baseline_id") or "").strip(),
            str(payload.get("variant_id") or "").strip(),
            str(origin.get("campaign_id") or "").strip(),
            str(origin.get("slice_id") or "").strip(),
            str(payload.get("benchmark") or "").strip(),
            str(payload.get("split") or "").strip(),
        )

    @staticmethod
    def _merge_analysis_inventory_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in incoming.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, dict)) and not value:
                continue
            merged[key] = value
        merged["updated_at"] = utc_now()
        merged.setdefault("created_at", existing.get("created_at") or incoming.get("created_at") or utc_now())
        return merged

    def _upsert_analysis_baseline_inventory(self, quest_root: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
        inventory = self._read_analysis_baseline_inventory(quest_root)
        existing_entries = [dict(item) for item in (inventory.get("entries") or []) if isinstance(item, dict)]
        by_key = {
            self._analysis_inventory_entry_key(item): dict(item)
            for item in existing_entries
            if str(item.get("baseline_id") or "").strip()
        }
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            entry = dict(raw)
            if not str(entry.get("baseline_id") or "").strip():
                continue
            key = self._analysis_inventory_entry_key(entry)
            current = by_key.get(key)
            if current is None:
                stamped = dict(entry)
                stamped.setdefault("created_at", utc_now())
                stamped["updated_at"] = utc_now()
                by_key[key] = stamped
                continue
            by_key[key] = self._merge_analysis_inventory_entry(current, entry)
        normalized = self._write_analysis_baseline_inventory(
            quest_root,
            {
                "entries": list(by_key.values()),
            },
        )
        return normalized

    def _paper_root(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        prefer_workspace: bool = True,
        create: bool = False,
    ) -> Path:
        roots: list[Path] = []
        if prefer_workspace:
            roots.append(self._workspace_root_for(quest_root, workspace_root))
        roots.append(quest_root)
        seen: set[str] = set()
        first_candidate: Path | None = None
        for root in roots:
            key = str(root.resolve())
            if key in seen:
                continue
            seen.add(key)
            candidate = root / "paper"
            if first_candidate is None:
                first_candidate = candidate
            if candidate.exists():
                return candidate
        fallback = first_candidate or (quest_root / "paper")
        return ensure_dir(fallback) if create else fallback

    def _paper_outline_candidates_root(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return ensure_dir(self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "outlines" / "candidates")

    def _paper_outline_revisions_root(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return ensure_dir(self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "outlines" / "revisions")

    def _paper_selected_outline_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root) / "selected_outline.json"

    def _paper_outline_selection_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "outline_selection.md"

    def _paper_bundle_manifest_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "paper_bundle_manifest.json"

    def _paper_evidence_ledger_path(self, quest_root: Path) -> Path:
        return ensure_dir(quest_root / "paper") / "evidence_ledger.json"

    def _paper_evidence_ledger_markdown_path(self, quest_root: Path) -> Path:
        return ensure_dir(quest_root / "paper") / "evidence_ledger.md"

    def _paper_experiment_matrix_json_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "paper_experiment_matrix.json"

    def _paper_line_state_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "paper_line_state.json"

    def _paper_manuscript_coverage_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "manuscript_coverage.json"

    def _paper_outline_root(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        create: bool = False,
    ) -> Path:
        root = self._paper_root(quest_root, workspace_root=workspace_root, create=create) / "outline"
        return ensure_dir(root) if create else root

    def _paper_outline_manifest_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_outline_root(quest_root, workspace_root=workspace_root, create=True) / "manifest.json"

    def _paper_outline_sections_root(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return ensure_dir(self._paper_outline_root(quest_root, workspace_root=workspace_root, create=True) / "sections")

    def _paper_outline_section_dir(
        self,
        quest_root: Path,
        section_id: str,
        *,
        workspace_root: Path | None = None,
    ) -> Path:
        return ensure_dir(self._paper_outline_sections_root(quest_root, workspace_root=workspace_root) / section_id)

    def _paper_active_sync_roots(self, quest_root: Path, *, workspace_root: Path | None = None) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()
        base_roots = [quest_root] if workspace_root is None else [workspace_root, quest_root]
        for root in base_roots:
            paper_root = root / "paper"
            key = str(paper_root.resolve(strict=False))
            if key in seen:
                continue
            seen.add(key)
            roots.append(ensure_dir(paper_root))
        return roots

    def _paper_sync_roots(self, quest_root: Path) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()
        for workspace_root in self.quest_service.workspace_roots(quest_root):
            paper_root = workspace_root / "paper"
            if not paper_root.exists() or not paper_root.is_dir():
                continue
            key = str(paper_root.resolve())
            if key in seen:
                continue
            seen.add(key)
            roots.append(paper_root)
        canonical = ensure_dir(quest_root / "paper")
        canonical_key = str(canonical.resolve())
        if canonical_key not in seen:
            roots.append(canonical)
        return roots

    def _paper_line_id(
        self,
        *,
        paper_branch: str | None,
        outline_id: str | None,
        source_run_id: str | None,
    ) -> str:
        seed = "::".join(
            [
                str(paper_branch or "").strip() or "paper",
                str(outline_id or "").strip() or "outline",
                str(source_run_id or "").strip() or "run",
            ]
        )
        return slugify(seed, "paper-line")

    @staticmethod
    def _paper_ready_status(status: object) -> bool:
        normalized = str(status or "").strip().lower()
        return normalized in {"ready", "completed", "analyzed", "written", "recorded", "supported"}

    @staticmethod
    def _normalize_paper_bundle_package_type(value: object, *, strict: bool = True) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        aliases = {
            "": "draft_checkpoint",
            "draft": "draft_checkpoint",
            "memo": "draft_checkpoint",
            "paper_memo": "draft_checkpoint",
            "checkpoint": "draft_checkpoint",
            "draft_checkpoint": "draft_checkpoint",
            "review": "review_package",
            "review_bundle": "review_package",
            "review_package": "review_package",
            "final": "submission_package",
            "final_bundle": "submission_package",
            "submission": "submission_package",
            "submission_bundle": "submission_package",
            "submission_package": "submission_package",
        }
        resolved = aliases.get(normalized)
        if resolved:
            return resolved
        if strict:
            raise ValueError(
                "`package_type` must be one of `draft_checkpoint`, `review_package`, or `submission_package`."
            )
        return "draft_checkpoint"

    def _resolve_paper_material_path(
        self,
        quest_root: Path,
        raw_path: object,
        *,
        workspace_root: Path | None = None,
    ) -> Path | None:
        raw = str(raw_path or "").strip()
        if not raw:
            return None
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
        roots = [self._workspace_root_for(quest_root, workspace_root), quest_root]
        seen: set[str] = set()
        fallback: Path | None = None
        for root in roots:
            key = str(root.resolve())
            if key in seen:
                continue
            seen.add(key)
            resolved = (root / candidate).resolve()
            fallback = fallback or resolved
            if resolved.exists():
                return resolved
        return fallback

    @staticmethod
    def _read_text_sample(path: Path, *, max_chars: int = 200_000) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except OSError:
            return ""

    def _paper_manuscript_coverage_payload(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        evidence_gate: dict[str, Any] | None = None,
        pending_slices: int | None = None,
        minimum_sections: int = 5,
        minimum_analysis_groups: int = 5,
    ) -> dict[str, Any]:
        workspace = self._workspace_root_for(quest_root, workspace_root)
        paper_root = self._paper_root(quest_root, workspace_root=workspace, create=True)
        manifest_path = self._paper_bundle_manifest_path(quest_root, workspace_root=workspace)
        manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}
        manifest = manifest if isinstance(manifest, dict) else {}
        package_type = self._normalize_paper_bundle_package_type(manifest.get("package_type"), strict=False)

        draft_path = self._resolve_paper_material_path(
            quest_root,
            manifest.get("draft_path") or "paper/draft.md",
            workspace_root=workspace,
        )
        pdf_path = self._resolve_paper_material_path(
            quest_root,
            manifest.get("pdf_path") or "paper/paper.pdf",
            workspace_root=workspace,
        )
        compile_report_path = self._resolve_paper_material_path(
            quest_root,
            manifest.get("compile_report_path") or "paper/build/compile_report.json",
            workspace_root=workspace,
        )
        latex_root = self._resolve_paper_material_path(
            quest_root,
            manifest.get("latex_root_path") or "paper/latex",
            workspace_root=workspace,
        )
        if latex_root and latex_root.is_file():
            latex_root = latex_root.parent
        if (not latex_root or not latex_root.exists()) and (paper_root / "latex").exists():
            latex_root = paper_root / "latex"

        tex_paths: list[Path] = []
        if latex_root and latex_root.exists():
            if latex_root.is_file() and latex_root.suffix == ".tex":
                tex_paths = [latex_root]
            elif latex_root.is_dir():
                tex_paths = sorted(path for path in latex_root.rglob("*.tex") if path.is_file())[:80]

        draft_text = self._read_text_sample(draft_path) if draft_path and draft_path.exists() and draft_path.is_file() else ""
        tex_texts = [self._read_text_sample(path) for path in tex_paths]
        manuscript_text = "\n".join([draft_text, *tex_texts])
        normalized_text = manuscript_text.lower()

        section_titles: list[str] = []
        for text in tex_texts:
            section_titles.extend(
                match.strip()
                for match in re.findall(r"\\(?:section|subsection)\*?\{([^{}]{1,160})\}", text)
                if match.strip()
            )
        section_titles.extend(
            match.strip()
            for match in re.findall(r"(?m)^#{1,3}\s+(.{1,160})$", draft_text)
            if match.strip()
        )
        if tex_paths:
            section_titles.extend(
                path.stem.replace("_", " ").replace("-", " ")
                for path in tex_paths
                if path.stem.lower() not in {"main", "preamble", "macros"}
            )
        normalized_titles = {
            re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
            for title in section_titles
            if title.strip()
        }
        section_like_count = len(normalized_titles)
        if tex_paths:
            section_like_count = max(
                section_like_count,
                len([path for path in tex_paths if path.stem.lower() not in {"main", "preamble", "macros"}]),
            )

        canonical_patterns = {
            "introduction": ("introduction", "intro"),
            "related_work": ("related work", "background", "prior work"),
            "method": ("method", "approach", "algorithm", "model", "design"),
            "experiments": ("experiment", "evaluation", "result"),
            "analysis": ("analysis", "ablation", "robustness", "sensitivity", "failure"),
            "limitations": ("limitation", "discussion"),
            "conclusion": ("conclusion", "future work"),
        }
        title_blob = "\n".join(sorted(normalized_titles)) + "\n" + normalized_text
        canonical_sections = {
            key: any(pattern in title_blob for pattern in patterns)
            for key, patterns in canonical_patterns.items()
        }
        core_section_keys = ("introduction", "method", "experiments", "conclusion")
        missing_core_sections = [key for key in core_section_keys if not canonical_sections.get(key)]

        figure_count = len(re.findall(r"\\begin\{figure\}|\\includegraphics|!\[[^\]]*\]\(", manuscript_text))
        table_count = len(re.findall(r"\\begin\{table\}|\\begin\{tabular\}", manuscript_text))
        table_count += len(re.findall(r"^\s*\|.+\|\s*$", manuscript_text, flags=re.MULTILINE))
        display_count = figure_count + table_count

        matrix_path = paper_root / "paper_experiment_matrix.json"
        matrix = read_json(matrix_path, {}) if matrix_path.exists() else {}
        matrix = matrix if isinstance(matrix, dict) else {}
        matrix_rows = [dict(item) for item in (matrix.get("rows") or []) if isinstance(item, dict)]
        analysis_keys: set[tuple[str, str, str, str, str, str]] = set()
        ready_analysis_keys: set[tuple[str, str, str, str, str, str]] = set()
        for row in matrix_rows:
            item_id = str(row.get("item_id") or "").strip()
            if not item_id:
                continue
            key = (
                str(row.get("section_id") or "").strip(),
                item_id,
                str(row.get("kind") or "").strip(),
                str(row.get("campaign_id") or "").strip(),
                str(row.get("slice_id") or "").strip(),
                str(row.get("run_id") or "").strip(),
            )
            analysis_keys.add(key)
            if self._paper_ready_status(row.get("status")):
                ready_analysis_keys.add(key)

        gate = evidence_gate if isinstance(evidence_gate, dict) else self._paper_bundle_gate_status(quest_root, workspace_root=workspace)
        evidence_ready = bool(gate.get("ok"))
        normalized_pending_slices = max(0, int(pending_slices or 0))
        analysis_ready = evidence_ready and normalized_pending_slices == 0
        draft_present = bool(draft_path and draft_path.exists() and draft_path.is_file()) or bool(tex_paths)
        pdf_present = bool(pdf_path and pdf_path.exists() and pdf_path.is_file())
        compile_report_present = bool(compile_report_path and compile_report_path.exists())
        compile_report = read_json(compile_report_path, {}) if compile_report_present and compile_report_path else {}
        compile_report = compile_report if isinstance(compile_report, dict) else {}
        compile_ok = bool(compile_report.get("ok") or compile_report.get("success")) if compile_report_present else False

        analysis_group_count = len(analysis_keys)
        ready_analysis_group_count = len(ready_analysis_keys)
        draft_checkpoint_ready = draft_present or bool(manifest_path.exists())
        manuscript_blockers: list[str] = []
        if not analysis_ready:
            manuscript_blockers.append("paper evidence or required analysis is not ready")
        if not draft_present:
            manuscript_blockers.append("no draft or LaTeX source detected")
        if section_like_count < minimum_sections:
            manuscript_blockers.append(f"manuscript has fewer than {minimum_sections} section-like units")
        if missing_core_sections:
            manuscript_blockers.append("missing core paper sections: " + ", ".join(missing_core_sections))
        if display_count <= 0:
            manuscript_blockers.append("no paper-facing figures or tables detected")
        if ready_analysis_group_count < minimum_analysis_groups:
            manuscript_blockers.append(
                f"fewer than {minimum_analysis_groups} ready paper-facing experiment/analysis groups recorded"
            )
        manuscript_ready = not manuscript_blockers

        checklist_path = paper_root / "review" / "submission_checklist.json"
        checklist = read_json(checklist_path, {}) if checklist_path.exists() else {}
        checklist = checklist if isinstance(checklist, dict) else {}
        checklist_status = str(checklist.get("overall_status") or manifest.get("status") or "").strip().lower()
        checklist_ready = checklist_status in {
            "ready",
            "passed",
            "complete",
            "completed",
            "submission_ready",
            "accepted",
            "delivered",
        }
        submission_blockers = list(manuscript_blockers)
        if package_type != "submission_package":
            submission_blockers.append("bundle package_type is not submission_package")
        if not pdf_present:
            submission_blockers.append("compiled PDF is missing")
        if not checklist_ready:
            submission_blockers.append("submission checklist is missing or not ready")
        submission_ready = not submission_blockers

        return {
            "schema_version": 1,
            "package_type": package_type,
            "paper_root": str(paper_root),
            "manifest_path": str(manifest_path) if manifest_path.exists() else None,
            "draft_path": str(draft_path) if draft_path and draft_path.exists() else None,
            "latex_root_path": str(latex_root) if latex_root and latex_root.exists() else None,
            "pdf_path": str(pdf_path) if pdf_path and pdf_path.exists() else None,
            "compile_report_path": str(compile_report_path) if compile_report_present and compile_report_path else None,
            "draft_present": draft_present,
            "pdf_present": pdf_present,
            "compile_report_present": compile_report_present,
            "compile_ok": compile_ok,
            "tex_file_count": len(tex_paths),
            "tex_files": [self._paper_bundle_relative_path(quest_root, path, workspace_root=workspace) for path in tex_paths[:40]],
            "section_like_count": section_like_count,
            "minimum_section_count": minimum_sections,
            "one_section_only": section_like_count <= 1,
            "canonical_sections": canonical_sections,
            "missing_core_sections": missing_core_sections,
            "figure_count": figure_count,
            "table_count": table_count,
            "display_count": display_count,
            "analysis_group_count": analysis_group_count,
            "ready_analysis_group_count": ready_analysis_group_count,
            "minimum_analysis_group_count": minimum_analysis_groups,
            "analysis_quantity_ready": ready_analysis_group_count >= minimum_analysis_groups,
            "evidence_ready": evidence_ready,
            "analysis_ready": analysis_ready,
            "draft_checkpoint_ready": draft_checkpoint_ready,
            "manuscript_ready": manuscript_ready,
            "submission_ready": submission_ready,
            "manuscript_blockers": manuscript_blockers,
            "submission_blockers": submission_blockers,
            "updated_at": utc_now(),
        }

    def _normalize_outline_evidence_contract(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        return {
            "main_text_items_must_be_ready": bool(payload.get("main_text_items_must_be_ready", True)),
            "appendix_items_may_be_ready_or_reference_only": bool(
                payload.get("appendix_items_may_be_ready_or_reference_only", True)
            ),
            "record_results_back_into_outline": bool(payload.get("record_results_back_into_outline", True)),
            "result_table_required": bool(payload.get("result_table_required", True)),
        }

    def _normalize_outline_result_table(self, values: object) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in values or [] if isinstance(values, list) else []:
            if not isinstance(raw, dict):
                continue
            row = {
                "item_id": str(raw.get("item_id") or "").strip() or None,
                "title": str(raw.get("title") or "").strip() or None,
                "kind": str(raw.get("kind") or "").strip() or None,
                "campaign_id": str(raw.get("campaign_id") or "").strip() or None,
                "slice_id": str(raw.get("slice_id") or "").strip() or None,
                "run_id": str(raw.get("run_id") or "").strip() or None,
                "paper_role": str(raw.get("paper_role") or raw.get("paper_placement") or "").strip() or None,
                "status": str(raw.get("status") or "").strip() or None,
                "claim_links": self._normalize_string_list(raw.get("claim_links")),
                "setup_note": str(raw.get("setup_note") or raw.get("setup") or "").strip() or None,
                "metric_summary": str(raw.get("metric_summary") or "").strip() or None,
                "result_summary": str(raw.get("result_summary") or "").strip() or None,
                "impact_summary": str(raw.get("impact_summary") or raw.get("claim_impact") or "").strip() or None,
                "source_paths": self._normalize_string_list(raw.get("source_paths")),
                "updated_at": str(raw.get("updated_at") or "").strip() or None,
            }
            if row["item_id"] or row["title"] or row["result_summary"]:
                rows.append(row)
        return rows

    def _normalize_outline_sections(
        self,
        values: object,
        *,
        experimental_designs: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        if isinstance(values, list):
            for index, raw in enumerate(values, start=1):
                if not isinstance(raw, dict):
                    continue
                title = str(raw.get("title") or raw.get("name") or raw.get("section_id") or "").strip()
                section_id = str(raw.get("section_id") or "").strip() or slugify(title or f"section-{index}", f"section-{index}")
                if not title:
                    title = section_id
                sections.append(
                    {
                        "section_id": section_id,
                        "title": title,
                        "paper_role": str(raw.get("paper_role") or raw.get("paper_placement") or "main_text").strip() or "main_text",
                        "claims": self._normalize_string_list(raw.get("claims")),
                        "required_items": self._normalize_string_list(raw.get("required_items")),
                        "optional_items": self._normalize_string_list(raw.get("optional_items")),
                        "status": str(raw.get("status") or "planned").strip() or "planned",
                        "note": str(raw.get("note") or "").strip() or None,
                        "result_table": self._normalize_outline_result_table(raw.get("result_table")),
                    }
                )
        if sections:
            return sections
        generated: list[dict[str, Any]] = []
        for index, item in enumerate(experimental_designs or [], start=1):
            title = str(item or "").strip()
            if not title:
                continue
            generated.append(
                {
                    "section_id": slugify(title, f"section-{index}"),
                    "title": title,
                    "paper_role": "main_text",
                    "claims": [],
                    "required_items": [],
                    "optional_items": [],
                    "status": "planned",
                    "note": None,
                    "result_table": [],
                }
            )
        return generated

    def _paper_baseline_inventory_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._paper_root(quest_root, workspace_root=workspace_root, create=True) / "baseline_inventory.json"

    def _paper_bundle_path_candidates(
        self,
        quest_root: Path,
        raw_path: object,
        *,
        workspace_root: Path | None = None,
    ) -> list[Path]:
        text = str(raw_path or "").strip()
        if not text:
            return []
        candidate = Path(text).expanduser()
        roots = [self._workspace_root_for(quest_root, workspace_root), quest_root]
        resolved: list[Path] = []
        if candidate.is_absolute():
            try:
                resolved.append(candidate.resolve())
            except OSError:
                return []
        else:
            for root in roots:
                try:
                    resolved.append((root / candidate).resolve())
                except OSError:
                    continue
        deduped: list[Path] = []
        seen: set[str] = set()
        for item in resolved:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _paper_bundle_compile_report(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        compile_report_path: object = None,
    ) -> dict[str, Any]:
        for candidate in self._paper_bundle_path_candidates(
            quest_root,
            compile_report_path,
            workspace_root=workspace_root,
        ):
            if not candidate.exists() or not candidate.is_file():
                continue
            payload = read_json(candidate, {})
            if isinstance(payload, dict):
                return payload
        return {}

    def _normalize_paper_bundle_latex_root_path(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        latex_root_path: object = None,
        compile_report_path: object = None,
    ) -> str | None:
        compile_report = self._paper_bundle_compile_report(
            quest_root,
            workspace_root=workspace_root,
            compile_report_path=compile_report_path,
        )
        for raw in (
            latex_root_path,
            compile_report.get("latex_root_path"),
            compile_report.get("main_file_path"),
        ):
            text = str(raw or "").strip()
            if not text:
                continue
            for candidate in self._paper_bundle_path_candidates(
                quest_root,
                text,
                workspace_root=workspace_root,
            ):
                if candidate.exists() and candidate.is_dir():
                    return self._paper_bundle_relative_path(quest_root, candidate, workspace_root=workspace_root) or text
                if candidate.suffix.lower() == ".tex":
                    return self._paper_bundle_relative_path(
                        quest_root,
                        candidate.parent,
                        workspace_root=workspace_root,
                    ) or PurePosixPath(text).parent.as_posix()
            if Path(text).suffix.lower() == ".tex":
                parent = PurePosixPath(text).parent.as_posix()
                if parent not in {"", "."}:
                    return parent
            return text
        return None

    def _open_source_root(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        prefer_workspace: bool = True,
        create: bool = False,
    ) -> Path:
        roots: list[Path] = []
        if prefer_workspace:
            roots.append(self._workspace_root_for(quest_root, workspace_root))
        roots.append(quest_root)
        seen: set[str] = set()
        first_candidate: Path | None = None
        for root in roots:
            key = str(root.resolve())
            if key in seen:
                continue
            seen.add(key)
            candidate = root / "release" / "open_source"
            if first_candidate is None:
                first_candidate = candidate
            if candidate.exists():
                return candidate
        fallback = first_candidate or (quest_root / "release" / "open_source")
        return ensure_dir(fallback) if create else fallback

    def _open_source_manifest_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._open_source_root(quest_root, workspace_root=workspace_root, create=True) / "manifest.json"

    def _open_source_cleanup_plan_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._open_source_root(quest_root, workspace_root=workspace_root, create=True) / "cleanup_plan.md"

    def _open_source_include_paths_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._open_source_root(quest_root, workspace_root=workspace_root, create=True) / "include_paths.json"

    def _open_source_exclude_paths_path(self, quest_root: Path, *, workspace_root: Path | None = None) -> Path:
        return self._open_source_root(quest_root, workspace_root=workspace_root, create=True) / "exclude_paths.json"

    def _write_paper_baseline_inventory(self, quest_root: Path, *, workspace_root: Path | None = None) -> dict[str, Any]:
        quest_yaml = self.quest_service.read_quest_yaml(quest_root)
        confirmed_baseline_ref = (
            dict(quest_yaml.get("confirmed_baseline_ref") or {})
            if isinstance(quest_yaml.get("confirmed_baseline_ref"), dict)
            else None
        )
        analysis_inventory = self._read_analysis_baseline_inventory(quest_root)
        payload = {
            "schema_version": 1,
            "canonical_baseline_ref": confirmed_baseline_ref,
            "supplementary_baselines": [
                dict(item) for item in (analysis_inventory.get("entries") or []) if isinstance(item, dict)
            ],
            "updated_at": utc_now(),
        }
        write_json(self._paper_baseline_inventory_path(quest_root, workspace_root=workspace_root), payload)
        return payload

    def _ensure_open_source_prep(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None,
        source_branch: str | None,
        source_bundle_manifest_path: str,
        baseline_inventory_path: str,
    ) -> dict[str, Any]:
        root = self._open_source_root(quest_root, workspace_root=workspace_root, create=True)
        cleanup_plan_path = self._open_source_cleanup_plan_path(quest_root, workspace_root=workspace_root)
        include_paths_path = self._open_source_include_paths_path(quest_root, workspace_root=workspace_root)
        exclude_paths_path = self._open_source_exclude_paths_path(quest_root, workspace_root=workspace_root)
        manifest_path = self._open_source_manifest_path(quest_root, workspace_root=workspace_root)
        if not cleanup_plan_path.exists():
            write_text(
                cleanup_plan_path,
                "\n".join(
                    [
                        "# Open Source Cleanup Plan",
                        "",
                        "## Goal",
                        "",
                        "Prepare a clean public code branch from the finalized paper line.",
                        "",
                        "## Keep",
                        "",
                        "- Core training / evaluation code needed to reproduce the public results.",
                        "",
                        "## Remove Or Private",
                        "",
                        "- Temporary logs, scratch files, local secrets, and unrelated experimental debris.",
                        "",
                        "## Before Release",
                        "",
                        "- Confirm README, license, and benchmark instructions are complete.",
                        "- Confirm only necessary files remain in scope.",
                        "",
                    ]
                ).rstrip()
                + "\n",
            )
        if not include_paths_path.exists():
            write_json(include_paths_path, {"paths": []})
        if not exclude_paths_path.exists():
            write_json(exclude_paths_path, {"paths": []})
        existing = read_json(manifest_path, {})
        existing = existing if isinstance(existing, dict) else {}
        manifest = {
            **existing,
            "schema_version": 1,
            "status": str(existing.get("status") or "draft").strip() or "draft",
            "source_branch": str(existing.get("source_branch") or source_branch or "").strip() or None,
            "release_branch": str(existing.get("release_branch") or "").strip() or None,
            "source_bundle_manifest_path": str(
                existing.get("source_bundle_manifest_path") or source_bundle_manifest_path or ""
            ).strip()
            or source_bundle_manifest_path,
            "baseline_inventory_path": str(existing.get("baseline_inventory_path") or baseline_inventory_path or "").strip()
            or baseline_inventory_path,
            "cleanup_plan_path": str(
                existing.get("cleanup_plan_path") or self._workspace_relative(quest_root, cleanup_plan_path) or ""
            ).strip()
            or "release/open_source/cleanup_plan.md",
            "include_paths_path": str(
                existing.get("include_paths_path") or self._workspace_relative(quest_root, include_paths_path) or ""
            ).strip()
            or "release/open_source/include_paths.json",
            "exclude_paths_path": str(
                existing.get("exclude_paths_path") or self._workspace_relative(quest_root, exclude_paths_path) or ""
            ).strip()
            or "release/open_source/exclude_paths.json",
            "created_at": existing.get("created_at") or utc_now(),
            "updated_at": utc_now(),
        }
        write_json(manifest_path, manifest)
        return manifest

    def _next_paper_outline_id(self, quest_root: Path) -> str:
        max_index = 0
        for root in (self._paper_outline_candidates_root(quest_root), self._paper_outline_revisions_root(quest_root)):
            for path in root.glob("outline-*.json"):
                suffix = path.stem.removeprefix("outline-")
                if suffix.isdigit():
                    max_index = max(max_index, int(suffix))
        _, selected_outline = self._read_selected_outline_record(quest_root)
        selected_id = str((selected_outline or {}).get("outline_id") or "").strip()
        if selected_id.startswith("outline-") and selected_id.removeprefix("outline-").isdigit():
            max_index = max(max_index, int(selected_id.removeprefix("outline-")))
        return f"outline-{max_index + 1:03d}"

    @staticmethod
    def _normalize_string_list(values: list[object] | None) -> list[str]:
        return [str(item).strip() for item in (values or []) if str(item).strip()]

    def _normalize_campaign_origin(self, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        origin_kind = str(payload.get("kind") or "analysis").strip().lower() or "analysis"
        normalized = {
            "kind": origin_kind,
            "reason": str(payload.get("reason") or "").strip() or None,
            "source_artifact_id": str(payload.get("source_artifact_id") or "").strip() or None,
            "source_outline_ref": str(payload.get("source_outline_ref") or "").strip() or None,
            "source_review_round": str(payload.get("source_review_round") or "").strip() or None,
            "reviewer_item_ids": self._normalize_string_list(payload.get("reviewer_item_ids")),
        }
        if not any(value for key, value in normalized.items() if key != "kind"):
            normalized["reason"] = None
        return normalized

    def _normalize_campaign_todo_items(self, todo_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized_items: list[dict[str, Any]] = []
        for raw in todo_items or []:
            if not isinstance(raw, dict):
                continue
            normalized_items.append(
                {
                    "exp_id": str(raw.get("exp_id") or "").strip() or None,
                    "todo_id": str(raw.get("todo_id") or raw.get("slice_id") or "").strip() or None,
                    "slice_id": str(raw.get("slice_id") or "").strip() or None,
                    "title": str(raw.get("title") or "").strip() or None,
                    "status": str(raw.get("status") or "pending").strip() or "pending",
                    "research_question": str(raw.get("research_question") or "").strip() or None,
                    "experimental_design": str(raw.get("experimental_design") or "").strip() or None,
                    "tier": str(raw.get("tier") or "").strip() or None,
                    "paper_placement": str(raw.get("paper_placement") or "").strip() or None,
                    "paper_role": str(raw.get("paper_role") or raw.get("paper_placement") or "").strip() or None,
                    "section_id": str(raw.get("section_id") or "").strip() or None,
                    "item_id": str(raw.get("item_id") or raw.get("exp_id") or raw.get("slice_id") or "").strip() or None,
                    "claim_links": self._normalize_string_list(raw.get("claim_links")),
                    "completion_condition": str(raw.get("completion_condition") or "").strip() or None,
                    "why_now": str(raw.get("why_now") or "").strip() or None,
                    "success_criteria": str(raw.get("success_criteria") or "").strip() or None,
                    "abandonment_criteria": str(raw.get("abandonment_criteria") or "").strip() or None,
                    "reviewer_item_ids": self._normalize_string_list(raw.get("reviewer_item_ids")),
                    "manuscript_targets": self._normalize_string_list(raw.get("manuscript_targets")),
                }
            )
        return normalized_items

    def _normalize_paper_outline_record(
        self,
        *,
        outline_id: str,
        title: str | None,
        note: str | None,
        story: str | None,
        ten_questions: list[object] | None,
        detailed_outline: dict[str, Any] | None,
        review_result: str | None,
        status: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        normalized_detailed = dict(detailed_outline or {})
        experimental_designs = self._normalize_string_list(normalized_detailed.get("experimental_designs"))
        sections = self._normalize_outline_sections(
            normalized_detailed.get("sections"),
            experimental_designs=experimental_designs,
        )
        resolved_title = (
            str(title or normalized_detailed.get("title") or outline_id).strip()
            or outline_id
        )
        record = {
            "schema_version": 1,
            "outline_id": outline_id,
            "status": status,
            "title": resolved_title,
            "note": str(note or "").strip() or None,
            "story": str(story or "").strip() or None,
            "ten_questions": self._normalize_string_list(ten_questions),
            "detailed_outline": {
                "title": str(normalized_detailed.get("title") or resolved_title).strip() or resolved_title,
                "abstract": str(normalized_detailed.get("abstract") or "").strip() or None,
                "research_questions": self._normalize_string_list(normalized_detailed.get("research_questions")),
                "methodology": str(normalized_detailed.get("methodology") or "").strip() or None,
                "experimental_designs": experimental_designs,
                "contributions": self._normalize_string_list(normalized_detailed.get("contributions")),
            },
            "sections": sections,
            "evidence_contract": self._normalize_outline_evidence_contract(
                normalized_detailed.get("evidence_contract")
            ),
            "review_result": str(review_result or "").strip() or None,
            "created_at": created_at or utc_now(),
            "updated_at": utc_now(),
        }
        return record

    def _render_outline_section_markdown(self, section: dict[str, Any]) -> str:
        lines = [
            f"# {str(section.get('title') or section.get('section_id') or 'Section').strip() or 'Section'}",
            "",
            f"- Section id: `{str(section.get('section_id') or 'unknown').strip() or 'unknown'}`",
            f"- Paper role: `{str(section.get('paper_role') or 'main_text').strip() or 'main_text'}`",
            f"- Status: `{str(section.get('status') or 'planned').strip() or 'planned'}`",
            "",
            "## Claims",
            "",
        ]
        claims = self._normalize_string_list(section.get("claims"))
        lines.extend([f"- `{item}`" for item in claims] or ["- None recorded."])
        lines.extend(["", "## Required Items", ""])
        required_items = self._normalize_string_list(section.get("required_items"))
        lines.extend([f"- `{item}`" for item in required_items] or ["- None recorded."])
        lines.extend(["", "## Optional Items", ""])
        optional_items = self._normalize_string_list(section.get("optional_items"))
        lines.extend([f"- `{item}`" for item in optional_items] or ["- None recorded."])
        lines.extend(["", "## Note", "", str(section.get("note") or "Not recorded."), ""])
        return "\n".join(lines).rstrip() + "\n"

    def _render_outline_section_setup_markdown(self, section: dict[str, Any]) -> str:
        rows = [dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)]
        setup_notes = []
        for row in rows:
            setup_text = str(row.get("setup_note") or row.get("setup") or "").strip()
            if setup_text and setup_text not in setup_notes:
                setup_notes.append(setup_text)
        lines = [
            f"# Setup · {str(section.get('title') or section.get('section_id') or 'Section').strip() or 'Section'}",
            "",
            "## Recorded Setup Notes",
            "",
        ]
        lines.extend([f"- {item}" for item in setup_notes] or ["- None recorded yet."])
        lines.append("")
        return "\n".join(lines)

    def _render_outline_section_findings_markdown(self, section: dict[str, Any]) -> str:
        rows = [dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)]
        lines = [
            f"# Findings · {str(section.get('title') or section.get('section_id') or 'Section').strip() or 'Section'}",
            "",
            "## Result Highlights",
            "",
        ]
        highlights = []
        for row in rows:
            result_summary = str(row.get("result_summary") or "").strip()
            metric_summary = str(row.get("metric_summary") or "").strip()
            title = str(row.get("title") or row.get("item_id") or "item").strip() or "item"
            if result_summary or metric_summary:
                suffix = f" ({metric_summary})" if metric_summary else ""
                highlights.append(f"- `{title}`: {result_summary or 'No summary recorded.'}{suffix}")
        lines.extend(highlights or ["- None recorded yet."])
        lines.append("")
        return "\n".join(lines)

    def _render_outline_section_impact_markdown(self, section: dict[str, Any]) -> str:
        rows = [dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)]
        impacts = []
        for row in rows:
            impact_text = str(row.get("impact_summary") or row.get("claim_impact") or "").strip()
            title = str(row.get("title") or row.get("item_id") or "item").strip() or "item"
            if impact_text:
                impacts.append(f"- `{title}`: {impact_text}")
        lines = [
            f"# Impact · {str(section.get('title') or section.get('section_id') or 'Section').strip() or 'Section'}",
            "",
            "## Claim Links",
            "",
        ]
        claim_links = self._normalize_string_list(section.get("claims"))
        lines.extend([f"- `{item}`" for item in claim_links] or ["- None recorded."])
        lines.extend(["", "## Impact Notes", ""])
        lines.extend(impacts or ["- None recorded yet."])
        lines.append("")
        return "\n".join(lines)

    def _outline_folder_exists(self, quest_root: Path, *, workspace_root: Path | None = None) -> bool:
        root = self._paper_outline_root(quest_root, workspace_root=workspace_root, create=False)
        return (root / "manifest.json").exists()

    def _write_outline_folder_from_record(
        self,
        quest_root: Path,
        record: dict[str, Any],
        *,
        workspace_root: Path | None = None,
    ) -> None:
        sections = self._normalize_outline_sections(
            record.get("sections"),
            experimental_designs=self._normalize_string_list(
                ((record.get("detailed_outline") or {}) if isinstance(record.get("detailed_outline"), dict) else {}).get(
                    "experimental_designs"
                )
            ),
        )
        manifest = {
            "schema_version": 1,
            "outline_id": str(record.get("outline_id") or "").strip() or None,
            "status": str(record.get("status") or "selected").strip() or "selected",
            "title": str(record.get("title") or "").strip() or None,
            "note": str(record.get("note") or "").strip() or None,
            "story": str(record.get("story") or "").strip() or None,
            "ten_questions": self._normalize_string_list(record.get("ten_questions")),
            "detailed_outline": (
                dict(record.get("detailed_outline") or {})
                if isinstance(record.get("detailed_outline"), dict)
                else {}
            ),
            "evidence_contract": self._normalize_outline_evidence_contract(record.get("evidence_contract")),
            "section_order": [
                str(section.get("section_id") or "").strip()
                for section in sections
                if str(section.get("section_id") or "").strip()
            ],
            "sections": [
                {
                    "section_id": str(section.get("section_id") or "").strip() or None,
                    "title": str(section.get("title") or "").strip() or None,
                    "paper_role": str(section.get("paper_role") or "main_text").strip() or "main_text",
                    "claims": self._normalize_string_list(section.get("claims")),
                    "required_items": self._normalize_string_list(section.get("required_items")),
                    "optional_items": self._normalize_string_list(section.get("optional_items")),
                    "status": str(section.get("status") or "planned").strip() or "planned",
                    "note": str(section.get("note") or "").strip() or None,
                }
                for section in sections
            ],
            "created_at": str(record.get("created_at") or "").strip() or utc_now(),
            "updated_at": utc_now(),
        }
        for paper_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            outline_root = ensure_dir(paper_root / "outline")
            write_json(outline_root / "manifest.json", manifest)
            sections_root = ensure_dir(outline_root / "sections")
            expected: set[str] = set()
            for section in sections:
                section_id = str(section.get("section_id") or "").strip()
                if not section_id:
                    continue
                expected.add(section_id)
                section_dir = ensure_dir(sections_root / section_id)
                write_text(section_dir / "section.md", self._render_outline_section_markdown(section))
                write_json(
                    section_dir / "result_table.json",
                    {
                        "schema_version": 1,
                        "section_id": section_id,
                        "title": str(section.get("title") or section_id).strip() or section_id,
                        "rows": [dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)],
                        "updated_at": utc_now(),
                    },
                )
                write_text(section_dir / "experiment_setup.md", self._render_outline_section_setup_markdown(section))
                write_text(section_dir / "findings.md", self._render_outline_section_findings_markdown(section))
                write_text(section_dir / "impact.md", self._render_outline_section_impact_markdown(section))
            for existing in sorted(sections_root.iterdir()):
                if not existing.is_dir() or existing.name in expected:
                    continue
                shutil.rmtree(existing)

    def _read_outline_folder_to_record(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        outline_root = self._paper_outline_root(quest_root, workspace_root=workspace_root, create=False)
        manifest_path = outline_root / "manifest.json"
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict) or not manifest:
            return {}
        manifest_sections = [dict(item) for item in (manifest.get("sections") or []) if isinstance(item, dict)]
        section_order = [
            str(item).strip() for item in (manifest.get("section_order") or []) if str(item).strip()
        ]
        by_id = {
            str(item.get("section_id") or "").strip(): dict(item)
            for item in manifest_sections
            if str(item.get("section_id") or "").strip()
        }
        for section_id in section_order:
            by_id.setdefault(
                section_id,
                {
                    "section_id": section_id,
                    "title": section_id,
                    "paper_role": "main_text",
                    "claims": [],
                    "required_items": [],
                    "optional_items": [],
                    "status": "planned",
                },
            )
        sections_root = outline_root / "sections"
        if sections_root.exists():
            for section_dir in sorted(sections_root.iterdir()):
                if not section_dir.is_dir():
                    continue
                section_id = section_dir.name
                section = dict(by_id.get(section_id) or {})
                section.setdefault("section_id", section_id)
                section.setdefault("title", section_id)
                result_table_payload = read_json(section_dir / "result_table.json", {})
                rows = result_table_payload.get("rows") if isinstance(result_table_payload, dict) else []
                section["result_table"] = self._normalize_outline_result_table(rows)
                by_id[section_id] = section
        ordered_sections: list[dict[str, Any]] = []
        emitted: set[str] = set()
        for section_id in section_order:
            section = by_id.get(section_id)
            if section is None:
                continue
            ordered_sections.append(section)
            emitted.add(section_id)
        for section_id, section in by_id.items():
            if section_id in emitted:
                continue
            ordered_sections.append(section)
        record = {
            "schema_version": 1,
            "outline_id": str(manifest.get("outline_id") or "").strip() or None,
            "status": str(manifest.get("status") or "selected").strip() or "selected",
            "title": str(manifest.get("title") or "").strip() or None,
            "note": str(manifest.get("note") or "").strip() or None,
            "story": str(manifest.get("story") or "").strip() or None,
            "ten_questions": self._normalize_string_list(manifest.get("ten_questions")),
            "detailed_outline": (
                dict(manifest.get("detailed_outline") or {})
                if isinstance(manifest.get("detailed_outline"), dict)
                else {}
            ),
            "sections": ordered_sections,
            "evidence_contract": self._normalize_outline_evidence_contract(manifest.get("evidence_contract")),
            "created_at": str(manifest.get("created_at") or "").strip() or None,
            "updated_at": str(manifest.get("updated_at") or "").strip() or utc_now(),
        }
        return record

    def _read_selected_outline_record(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
    ) -> tuple[Path | None, dict[str, Any]]:
        candidates: list[tuple[tuple[str, float], Path, dict[str, Any]]] = []
        for paper_root in self._paper_sync_roots(quest_root):
            outline_root = paper_root / "outline"
            manifest_path = outline_root / "manifest.json"
            if manifest_path.exists():
                record = self._read_outline_folder_to_record(quest_root, workspace_root=paper_root.parent)
                if record:
                    candidates.append(
                        (
                            (
                                str(record.get("updated_at") or record.get("created_at") or ""),
                                manifest_path.stat().st_mtime if manifest_path.exists() else 0.0,
                            ),
                            manifest_path,
                            record,
                        )
                    )
                    continue
            selected_outline_path = paper_root / "selected_outline.json"
            if not selected_outline_path.exists():
                continue
            payload = read_json(selected_outline_path, {})
            if not isinstance(payload, dict) or not payload:
                continue
            candidates.append(
                (
                    (
                        str(payload.get("updated_at") or payload.get("created_at") or ""),
                        selected_outline_path.stat().st_mtime if selected_outline_path.exists() else 0.0,
                    ),
                    selected_outline_path,
                    payload,
                )
            )
        if not candidates:
            return None, {}
        candidates.sort(key=lambda item: item[0])
        _, path, payload = candidates[-1]
        return path, payload

    def _compile_selected_outline_json(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        record = self._read_outline_folder_to_record(quest_root, workspace_root=workspace_root)
        if not record:
            return {}
        for paper_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            write_json(paper_root / "selected_outline.json", record)
        return record

    def _read_paper_evidence_ledger(self, quest_root: Path) -> dict[str, Any]:
        candidates: list[tuple[tuple[str, float], dict[str, Any]]] = []
        for paper_root in self._paper_sync_roots(quest_root):
            path = paper_root / "evidence_ledger.json"
            if not path.exists():
                continue
            payload = read_json(path, {})
            if not isinstance(payload, dict) or not payload:
                continue
            candidates.append(
                (
                    (
                        str(payload.get("updated_at") or payload.get("created_at") or ""),
                        path.stat().st_mtime if path.exists() else 0.0,
                    ),
                    payload,
                )
            )
        if not candidates:
            return {
                "schema_version": 1,
                "selected_outline_ref": None,
                "items": [],
                "updated_at": utc_now(),
            }
        candidates.sort(key=lambda item: item[0])
        payload = candidates[-1][1]
        items = [dict(item) for item in (payload.get("items") or []) if isinstance(item, dict)]
        return {
            "schema_version": 1,
            "selected_outline_ref": str(payload.get("selected_outline_ref") or "").strip() or None,
            "items": items,
            "updated_at": str(payload.get("updated_at") or payload.get("created_at") or "").strip() or utc_now(),
        }

    def _paper_evidence_key_metrics(
        self,
        *,
        metric_rows: list[dict[str, Any]] | None = None,
        metrics_summary: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in metric_rows or []:
            if not isinstance(row, dict):
                continue
            metric_id = str(row.get("metric_id") or row.get("name") or "").strip()
            if not metric_id or metric_id in seen:
                continue
            seen.add(metric_id)
            rows.append(
                {
                    "metric_id": metric_id,
                    "value": row.get("value"),
                    "direction": str(row.get("direction") or "").strip() or None,
                    "decimals": row.get("decimals"),
                }
            )
            if len(rows) >= 6:
                return rows
        for metric_id, value in (metrics_summary or {}).items():
            text = str(metric_id or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            rows.append({"metric_id": text, "value": value, "direction": None, "decimals": None})
            if len(rows) >= 6:
                break
        return rows

    def _paper_metric_summary_text(self, key_metrics: list[dict[str, Any]] | None) -> str | None:
        parts: list[str] = []
        for item in key_metrics or []:
            if not isinstance(item, dict):
                continue
            metric_id = str(item.get("metric_id") or "").strip()
            if not metric_id:
                continue
            parts.append(
                f"{metric_id}={self._format_metric_value(item.get('value'), item.get('decimals'))}"
            )
        return "; ".join(parts) if parts else None

    def _render_paper_evidence_ledger_markdown(self, payload: dict[str, Any]) -> str:
        items = [dict(item) for item in (payload.get("items") or []) if isinstance(item, dict)]
        lines = [
            "# Paper Evidence Ledger",
            "",
            f"- Selected outline: `{str(payload.get('selected_outline_ref') or 'none').strip() or 'none'}`",
            f"- Item count: `{len(items)}`",
            f"- Updated at: `{str(payload.get('updated_at') or utc_now()).strip() or utc_now()}`",
            "",
            "| Item | Kind | Section | Role | Status | Metrics | Source |",
            "|---|---|---|---|---|---|---|",
        ]
        for item in items:
            metrics_text = self._paper_metric_summary_text(
                [dict(metric) for metric in (item.get("key_metrics") or []) if isinstance(metric, dict)]
            ) or "-"
            source_paths = [str(path).strip() for path in (item.get("source_paths") or []) if str(path).strip()]
            source_text = ", ".join(f"`{path}`" for path in source_paths[:2]) or "-"
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{str(item.get('item_id') or 'unknown').strip() or 'unknown'}`",
                        str(item.get("kind") or "-"),
                        str(item.get("section_id") or "-"),
                        str(item.get("paper_role") or "-"),
                        str(item.get("status") or "-"),
                        metrics_text,
                        source_text,
                    ]
                )
                + " |"
            )
        if not items:
            lines.extend(["| - | - | - | - | - | - | - |", ""])
        else:
            lines.append("")
        for item in items:
            lines.extend(
                [
                    f"## {str(item.get('item_id') or 'unknown').strip() or 'unknown'}",
                    "",
                    f"- Title: {str(item.get('title') or item.get('item_id') or 'Unknown').strip() or 'Unknown'}",
                    f"- Kind: `{str(item.get('kind') or 'unknown').strip() or 'unknown'}`",
                    f"- Section: `{str(item.get('section_id') or 'unmapped').strip() or 'unmapped'}`",
                    f"- Role: `{str(item.get('paper_role') or 'unmapped').strip() or 'unmapped'}`",
                    f"- Status: `{str(item.get('status') or 'unknown').strip() or 'unknown'}`",
                    f"- Claims: {', '.join(str(value).strip() for value in (item.get('claim_links') or []) if str(value).strip()) or 'none'}",
                    "",
                    "### Setup",
                    "",
                    str(item.get("setup") or "Not recorded."),
                    "",
                    "### Result Summary",
                    "",
                    str(item.get("result_summary") or "Not recorded."),
                    "",
                    "### Source Paths",
                    "",
                ]
            )
            if source_paths := [str(path).strip() for path in (item.get("source_paths") or []) if str(path).strip()]:
                lines.extend([f"- `{path}`" for path in source_paths])
            else:
                lines.append("- None recorded.")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _build_paper_experiment_matrix_payload(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        outline_path, record = self._read_selected_outline_for_sync(quest_root, workspace_root=workspace_root)
        record = record if isinstance(record, dict) else {}
        detailed_outline = (
            dict(record.get("detailed_outline") or {})
            if isinstance(record.get("detailed_outline"), dict)
            else {}
        )
        sections = self._normalize_outline_sections(
            record.get("sections"),
            experimental_designs=self._normalize_string_list(detailed_outline.get("experimental_designs")),
        )
        paper_line_state = read_json(self._paper_line_state_path(quest_root, workspace_root=workspace_root), {})
        paper_line_state = paper_line_state if isinstance(paper_line_state, dict) else {}
        selected_outline_ref = str(record.get("outline_id") or "").strip() or None
        paper_line_id = str(paper_line_state.get("paper_line_id") or "").strip() or None
        rows: list[dict[str, Any]] = []
        for section in sections:
            section_id = str(section.get("section_id") or "").strip() or None
            section_title = str(section.get("title") or section_id or "Section").strip() or "Section"
            paper_role = str(section.get("paper_role") or "main_text").strip() or "main_text"
            claims = self._normalize_string_list(section.get("claims"))
            required_items = self._normalize_string_list(section.get("required_items"))
            optional_items = self._normalize_string_list(section.get("optional_items"))
            result_rows = [
                dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)
            ]
            represented_keys: set[tuple[str, str, str, str, str]] = set()
            represented_item_ids: set[str] = set()
            for row in result_rows:
                item_id = str(row.get("item_id") or "").strip()
                if not item_id:
                    continue
                represented_item_ids.add(item_id)
                represented_keys.add(
                    (
                        item_id,
                        str(row.get("kind") or "").strip(),
                        str(row.get("campaign_id") or "").strip(),
                        str(row.get("slice_id") or "").strip(),
                        str(row.get("run_id") or "").strip(),
                    )
                )
                row_paper_role = str(row.get("paper_role") or paper_role).strip() or paper_role
                source_paths = self._normalize_string_list(row.get("source_paths"))
                rows.append(
                    {
                        "selected_outline_ref": selected_outline_ref,
                        "paper_line_id": paper_line_id,
                        "section_id": section_id,
                        "section_title": section_title,
                        "paper_role": row_paper_role,
                        "required": item_id in required_items,
                        "optional": item_id in optional_items and item_id not in required_items,
                        "item_id": item_id,
                        "title": str(row.get("title") or item_id).strip() or item_id,
                        "kind": str(row.get("kind") or "").strip() or None,
                        "campaign_id": str(row.get("campaign_id") or "").strip() or None,
                        "slice_id": str(row.get("slice_id") or "").strip() or None,
                        "run_id": str(row.get("run_id") or "").strip() or None,
                        "status": str(row.get("status") or section.get("status") or "planned").strip() or "planned",
                        "claim_links": self._normalize_string_list(row.get("claim_links")) or claims,
                        "metric_summary": str(row.get("metric_summary") or "").strip() or None,
                        "result_summary": str(row.get("result_summary") or "").strip() or None,
                        "impact_summary": str(row.get("impact_summary") or "").strip() or None,
                        "source_paths": source_paths,
                    }
                )
            for item_id in [*required_items, *optional_items]:
                key = (item_id, "", "", "", "")
                if item_id in represented_item_ids or key in represented_keys:
                    continue
                row_paper_role = paper_role
                rows.append(
                    {
                        "selected_outline_ref": selected_outline_ref,
                        "paper_line_id": paper_line_id,
                        "section_id": section_id,
                        "section_title": section_title,
                        "paper_role": row_paper_role,
                        "required": item_id in required_items,
                        "optional": item_id in optional_items and item_id not in required_items,
                        "item_id": item_id,
                        "title": item_id,
                        "kind": None,
                        "campaign_id": None,
                        "slice_id": None,
                        "run_id": None,
                        "status": str(section.get("status") or "planned").strip() or "planned",
                        "claim_links": claims,
                        "metric_summary": None,
                        "result_summary": None,
                        "impact_summary": None,
                        "source_paths": [],
                    }
                )
        rows.sort(
            key=lambda item: (
                str(item.get("section_id") or ""),
                0 if item.get("required") else 1,
                str(item.get("item_id") or ""),
                str(item.get("kind") or ""),
                str(item.get("campaign_id") or ""),
                str(item.get("slice_id") or item.get("run_id") or ""),
            )
        )
        return {
            "schema_version": 1,
            "selected_outline_ref": selected_outline_ref,
            "paper_line_id": paper_line_id,
            "outline_path": str(outline_path) if outline_path else None,
            "row_count": len(rows),
            "required_row_count": sum(1 for item in rows if bool(item.get("required"))),
            "ready_row_count": sum(
                1 for item in rows if self._paper_ready_status(item.get("status"))
            ),
            "rows": rows,
            "updated_at": utc_now(),
        }

    def _render_paper_experiment_matrix_markdown(self, payload: dict[str, Any]) -> str:
        rows = [dict(item) for item in (payload.get("rows") or []) if isinstance(item, dict)]
        lines = [
            "# Paper Experiment Matrix",
            "",
            f"- Selected outline: `{str(payload.get('selected_outline_ref') or 'none').strip() or 'none'}`",
            f"- Paper line: `{str(payload.get('paper_line_id') or 'none').strip() or 'none'}`",
            f"- Row count: `{int(payload.get('row_count') or 0)}`",
            f"- Required rows: `{int(payload.get('required_row_count') or 0)}`",
            f"- Ready rows: `{int(payload.get('ready_row_count') or 0)}`",
            "",
            "| Item | Kind | Section | Role | Status | Metrics | Claims | Summary |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            claims_text = ", ".join(f"`{item}`" for item in self._normalize_string_list(row.get("claim_links"))) or "-"
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{str(row.get('item_id') or 'unknown').strip() or 'unknown'}`",
                        str(row.get("kind") or row.get("campaign_id") or row.get("run_id") or "-"),
                        str(row.get("section_id") or "-"),
                        str(row.get("paper_role") or "-"),
                        str(row.get("status") or "-"),
                        str(row.get("metric_summary") or "-"),
                        claims_text,
                        str(row.get("result_summary") or row.get("impact_summary") or "-"),
                    ]
                )
                + " |"
            )
        if not rows:
            lines.extend(["| - | - | - | - | - | - | - | - |", ""])
        else:
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _write_paper_experiment_matrix(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        payload = self._build_paper_experiment_matrix_payload(quest_root, workspace_root=workspace_root)
        markdown = self._render_paper_experiment_matrix_markdown(payload)
        for paper_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            write_json(paper_root / "paper_experiment_matrix.json", payload)
            write_text(paper_root / "paper_experiment_matrix.md", markdown)
        return payload

    def _write_paper_evidence_ledger(
        self,
        quest_root: Path,
        payload: dict[str, Any],
        *,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        normalized = {
            "schema_version": 1,
            "selected_outline_ref": str(payload.get("selected_outline_ref") or "").strip() or None,
            "items": [dict(item) for item in (payload.get("items") or []) if isinstance(item, dict)],
            "updated_at": utc_now(),
        }
        markdown = self._render_paper_evidence_ledger_markdown(normalized)
        for paper_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            write_json(paper_root / "evidence_ledger.json", normalized)
            write_text(paper_root / "evidence_ledger.md", markdown)
        return normalized

    def _read_selected_outline_for_sync(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
    ) -> tuple[Path | None, dict[str, Any]]:
        return self._read_selected_outline_record(quest_root, workspace_root=workspace_root)

    def _write_selected_outline_sync(
        self,
        quest_root: Path,
        payload: dict[str, Any],
        *,
        workspace_root: Path | None = None,
    ) -> None:
        outline_id = str(payload.get("outline_id") or "").strip()
        self._write_outline_folder_from_record(quest_root, payload, workspace_root=workspace_root)
        compiled = self._compile_selected_outline_json(quest_root, workspace_root=workspace_root) or dict(payload)
        canonical_path = ensure_dir(quest_root / "paper") / "selected_outline.json"
        write_json(canonical_path, compiled)
        for paper_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            path = paper_root / "selected_outline.json"
            if path.resolve() == canonical_path.resolve():
                continue
            existing = read_json(path, {}) if path.exists() else {}
            if path.exists():
                existing_outline_id = str(existing.get("outline_id") or "").strip() if isinstance(existing, dict) else ""
                if existing_outline_id and existing_outline_id != outline_id:
                    continue
            write_json(path, compiled)
        self._write_paper_experiment_matrix(quest_root, workspace_root=workspace_root)

    def _outline_status_from_rows(self, section: dict[str, Any]) -> str:
        rows = [dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)]
        by_item = {
            str(item.get("item_id") or "").strip(): str(item.get("status") or "").strip() or "pending"
            for item in rows
            if str(item.get("item_id") or "").strip()
        }
        required_items = self._normalize_string_list(section.get("required_items"))
        if required_items:
            ready_count = sum(1 for item_id in required_items if self._paper_ready_status(by_item.get(item_id)))
            present_count = sum(1 for item_id in required_items if item_id in by_item)
            if ready_count == len(required_items):
                return "ready"
            if ready_count > 0:
                return "partial"
            if present_count > 0:
                return "pending"
            return "planned"
        if any(self._paper_ready_status(item.get("status")) for item in rows):
            return "ready"
        if rows:
            return "pending"
        return str(section.get("status") or "planned").strip() or "planned"

    def _sync_outline_sections(
        self,
        quest_root: Path,
        *,
        items: list[dict[str, Any]],
        workspace_root: Path | None = None,
    ) -> dict[str, Any] | None:
        outline_path, record = self._read_selected_outline_for_sync(quest_root, workspace_root=workspace_root)
        if outline_path is None or not record:
            return None
        detailed_outline = (
            dict(record.get("detailed_outline") or {})
            if isinstance(record.get("detailed_outline"), dict)
            else {}
        )
        sections = self._normalize_outline_sections(
            record.get("sections"),
            experimental_designs=self._normalize_string_list(detailed_outline.get("experimental_designs")),
        )
        if not sections:
            sections = self._normalize_outline_sections([], experimental_designs=["Main Results"])
        by_id = {
            str(section.get("section_id") or "").strip(): dict(section)
            for section in sections
            if str(section.get("section_id") or "").strip()
        }
        for raw in items:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("item_id") or "").strip()
            if not item_id:
                continue
            section_id = str(raw.get("section_id") or "").strip() or "main-results"
            section = dict(by_id.get(section_id) or {})
            if not section:
                section = {
                    "section_id": section_id,
                    "title": str(raw.get("section_title") or raw.get("title") or section_id).strip() or section_id,
                    "paper_role": str(raw.get("paper_role") or "main_text").strip() or "main_text",
                    "claims": [],
                    "required_items": [],
                    "optional_items": [],
                    "status": "planned",
                    "note": None,
                    "result_table": [],
                }
            claims = self._normalize_string_list(section.get("claims"))
            for claim in self._normalize_string_list(raw.get("claim_links")):
                if claim not in claims:
                    claims.append(claim)
            section["claims"] = claims
            paper_role = str(raw.get("paper_role") or section.get("paper_role") or "main_text").strip() or "main_text"
            section["paper_role"] = paper_role
            required_items = self._normalize_string_list(section.get("required_items"))
            optional_items = self._normalize_string_list(section.get("optional_items"))
            target_list = required_items if paper_role == "main_text" else optional_items
            if item_id not in target_list:
                target_list.append(item_id)
            if paper_role == "main_text":
                optional_items = [value for value in optional_items if value != item_id]
            else:
                required_items = [value for value in required_items if value != item_id]
            section["required_items"] = required_items
            section["optional_items"] = optional_items
            row = {
                "item_id": item_id,
                "title": str(raw.get("title") or item_id).strip() or item_id,
                "kind": str(raw.get("kind") or "").strip() or None,
                "campaign_id": str(raw.get("campaign_id") or "").strip() or None,
                "slice_id": str(raw.get("slice_id") or "").strip() or None,
                "run_id": str(raw.get("run_id") or "").strip() or None,
                "paper_role": paper_role,
                "status": str(raw.get("status") or "pending").strip() or "pending",
                "claim_links": self._normalize_string_list(raw.get("claim_links")),
                "setup_note": str(raw.get("setup_note") or raw.get("setup") or "").strip() or None,
                "metric_summary": str(raw.get("metric_summary") or "").strip() or None,
                "result_summary": str(raw.get("result_summary") or "").strip() or None,
                "impact_summary": str(raw.get("impact_summary") or raw.get("claim_impact") or "").strip() or None,
                "source_paths": self._normalize_string_list(raw.get("source_paths")),
                "updated_at": utc_now(),
            }
            existing_rows = [
                dict(item) for item in (section.get("result_table") or []) if isinstance(item, dict)
            ]
            row_identity = (
                item_id,
                str(row.get("kind") or "").strip(),
                str(row.get("campaign_id") or "").strip(),
                str(row.get("slice_id") or "").strip(),
                str(row.get("run_id") or "").strip(),
            )
            merged_rows: list[dict[str, Any]] = []
            replaced = False
            for existing in existing_rows:
                existing_identity = (
                    str(existing.get("item_id") or "").strip(),
                    str(existing.get("kind") or "").strip(),
                    str(existing.get("campaign_id") or "").strip(),
                    str(existing.get("slice_id") or "").strip(),
                    str(existing.get("run_id") or "").strip(),
                )
                if existing_identity != row_identity:
                    merged_rows.append(existing)
                    continue
                merged = dict(existing)
                for key, value in row.items():
                    if value in (None, "", []):
                        continue
                    merged[key] = value
                merged_rows.append(merged)
                replaced = True
            if not replaced:
                merged_rows.append(row)
            section["result_table"] = merged_rows
            section["status"] = self._outline_status_from_rows(section)
            by_id[section_id] = section
        record["sections"] = list(by_id.values())
        record["evidence_contract"] = self._normalize_outline_evidence_contract(record.get("evidence_contract"))
        record["updated_at"] = utc_now()
        self._write_selected_outline_sync(quest_root, record, workspace_root=workspace_root)
        return record

    @staticmethod
    def _paper_evidence_item_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(item.get("item_id") or "").strip(),
            str(item.get("kind") or "").strip(),
            str(item.get("campaign_id") or "").strip(),
            str(item.get("slice_id") or item.get("run_id") or "").strip(),
        )

    def _upsert_paper_evidence_item(
        self,
        quest_root: Path,
        item: dict[str, Any],
        *,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        ledger = self._read_paper_evidence_ledger(quest_root)
        items = [dict(entry) for entry in (ledger.get("items") or []) if isinstance(entry, dict)]
        key = self._paper_evidence_item_key(item)
        merged_items: list[dict[str, Any]] = []
        replaced = False
        for existing in items:
            if self._paper_evidence_item_key(existing) != key:
                merged_items.append(existing)
                continue
            merged = dict(existing)
            for field, value in item.items():
                if value in (None, "", []):
                    continue
                merged[field] = value
            merged["updated_at"] = utc_now()
            merged_items.append(merged)
            replaced = True
        if not replaced:
            merged_items.append({**item, "created_at": utc_now(), "updated_at": utc_now()})
        merged_items.sort(
            key=lambda payload: (
                str(payload.get("section_id") or ""),
                str(payload.get("item_id") or ""),
                str(payload.get("updated_at") or ""),
            )
        )
        written = self._write_paper_evidence_ledger(
            quest_root,
            {
                "selected_outline_ref": item.get("selected_outline_ref") or ledger.get("selected_outline_ref"),
                "items": merged_items,
            },
            workspace_root=workspace_root,
        )
        metric_summary = self._paper_metric_summary_text(
            [dict(metric) for metric in (item.get("key_metrics") or []) if isinstance(metric, dict)]
        )
        self._sync_outline_sections(
            quest_root,
            items=[
                {
                    "item_id": item.get("item_id"),
                    "title": item.get("title"),
                    "kind": item.get("kind"),
                    "campaign_id": item.get("campaign_id"),
                    "slice_id": item.get("slice_id"),
                    "run_id": item.get("run_id"),
                    "paper_role": item.get("paper_role"),
                    "status": item.get("status"),
                    "claim_links": item.get("claim_links"),
                    "section_id": item.get("section_id"),
                    "setup": item.get("setup"),
                    "metric_summary": metric_summary,
                    "result_summary": item.get("result_summary"),
                    "claim_impact": item.get("claim_impact"),
                    "source_paths": item.get("source_paths"),
                }
            ],
            workspace_root=workspace_root,
        )
        self._write_paper_experiment_matrix(quest_root, workspace_root=workspace_root)
        self._write_paper_line_state(quest_root, workspace_root=workspace_root)
        return written

    def _paper_bundle_gate_status(self, quest_root: Path, *, workspace_root: Path | None = None) -> dict[str, Any]:
        outline_path, selected_outline = self._read_selected_outline_for_sync(quest_root, workspace_root=workspace_root)
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        detailed_outline = (
            dict(selected_outline.get("detailed_outline") or {})
            if isinstance(selected_outline.get("detailed_outline"), dict)
            else {}
        )
        sections = self._normalize_outline_sections(
            selected_outline.get("sections"),
            experimental_designs=self._normalize_string_list(detailed_outline.get("experimental_designs")),
        )
        ledger = self._read_paper_evidence_ledger(quest_root)
        ledger_items = [dict(item) for item in (ledger.get("items") or []) if isinstance(item, dict)]
        ledger_items_by_item: dict[str, list[dict[str, Any]]] = {}
        for item in ledger_items:
            item_id = str(item.get("item_id") or "").strip()
            if item_id:
                ledger_items_by_item.setdefault(item_id, []).append(dict(item))

        def ready_ledger_item_for(item_id: str) -> dict[str, Any] | None:
            candidates = ledger_items_by_item.get(item_id) or []
            ready_candidates = [item for item in candidates if self._paper_ready_status(item.get("status"))]
            if ready_candidates:
                main_candidates = [
                    item for item in ready_candidates if str(item.get("paper_role") or "").strip() == "main_text"
                ]
                return main_candidates[0] if main_candidates else ready_candidates[0]
            return candidates[0] if candidates else None

        unresolved_required_items: list[dict[str, Any]] = []
        ready_sections = 0
        for section in sections:
            required_items = self._normalize_string_list(section.get("required_items"))
            section_ready = True
            for item_id in required_items:
                ledger_item = ready_ledger_item_for(item_id)
                if ledger_item is None or not self._paper_ready_status(ledger_item.get("status")):
                    unresolved_required_items.append(
                        {
                            "section_id": section.get("section_id"),
                            "section_title": section.get("title"),
                            "item_id": item_id,
                            "status": ledger_item.get("status") if isinstance(ledger_item, dict) else None,
                        }
                    )
                    section_ready = False
            if section_ready and required_items:
                ready_sections += 1
        selected_outline_ref = str(selected_outline.get("outline_id") or ledger.get("selected_outline_ref") or "").strip() or None
        completed_analysis: list[dict[str, Any]] = []
        campaigns_root = quest_root / ".ds" / "analysis_campaigns"
        if campaigns_root.exists():
            for path in sorted(campaigns_root.glob("analysis-*.json")):
                manifest = read_json(path, {})
                if not isinstance(manifest, dict) or not manifest:
                    continue
                manifest_outline_ref = str(manifest.get("selected_outline_ref") or "").strip() or None
                if selected_outline_ref and manifest_outline_ref != selected_outline_ref:
                    continue
                for slice_item in manifest.get("slices") or []:
                    if not isinstance(slice_item, dict):
                        continue
                    status = str(slice_item.get("status") or "").strip().lower()
                    if status in {"", "pending"}:
                        continue
                    completed_analysis.append(
                        {
                            "campaign_id": str(manifest.get("campaign_id") or "").strip() or None,
                            "slice_id": str(slice_item.get("slice_id") or "").strip() or None,
                            "item_id": str(slice_item.get("item_id") or "").strip() or None,
                            "section_id": str(slice_item.get("section_id") or "").strip() or None,
                            "status": status,
                            "title": str(slice_item.get("title") or slice_item.get("slice_id") or "").strip() or None,
                        }
                    )
        unmapped_completed_items: list[dict[str, Any]] = []
        for item in completed_analysis:
            item_id = str(item.get("item_id") or "").strip()
            if not item_id:
                unmapped_completed_items.append(item)
                continue
            ledger_candidates = ledger_items_by_item.get(item_id) or []
            campaign_id = str(item.get("campaign_id") or "").strip()
            slice_id = str(item.get("slice_id") or "").strip()
            mapped = False
            for ledger_item in ledger_candidates:
                if not str(ledger_item.get("section_id") or "").strip():
                    continue
                if campaign_id and str(ledger_item.get("campaign_id") or "").strip() != campaign_id:
                    continue
                if slice_id and str(ledger_item.get("slice_id") or "").strip() != slice_id:
                    continue
                mapped = True
                break
            if not mapped:
                unmapped_completed_items.append(item)
        return {
            "ok": not unresolved_required_items and not unmapped_completed_items,
            "outline_path": str(outline_path) if outline_path else None,
            "selected_outline_ref": selected_outline_ref,
            "section_count": len(sections),
            "ready_section_count": ready_sections,
            "ledger_item_count": len(ledger_items),
            "unresolved_required_items": unresolved_required_items,
            "unmapped_completed_items": unmapped_completed_items,
        }

    def _paper_contract_health_payload(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        pending_slices: int | None = None,
    ) -> dict[str, Any]:
        gate_status = self._paper_bundle_gate_status(quest_root, workspace_root=workspace_root)
        paper_root = self._paper_root(quest_root, workspace_root=workspace_root, create=True)
        bundle_manifest_path = paper_root / "paper_bundle_manifest.json"
        bundle_manifest = read_json(bundle_manifest_path, {}) if bundle_manifest_path.exists() else {}
        bundle_manifest = bundle_manifest if isinstance(bundle_manifest, dict) else {}
        submission_checklist_path = paper_root / "review" / "submission_checklist.json"
        submission_checklist = read_json(submission_checklist_path, {}) if submission_checklist_path.exists() else {}
        submission_checklist = submission_checklist if isinstance(submission_checklist, dict) else {}
        unresolved_required_items = [
            dict(item) for item in (gate_status.get("unresolved_required_items") or []) if isinstance(item, dict)
        ]
        unmapped_completed_items = [
            dict(item) for item in (gate_status.get("unmapped_completed_items") or []) if isinstance(item, dict)
        ]
        normalized_pending_slices = max(0, int(pending_slices or 0))
        blocking_reasons: list[str] = []
        if unmapped_completed_items:
            blocking_reasons.append("completed analysis remains unmapped into the paper contract")
        if unresolved_required_items:
            blocking_reasons.append("required outline items are still unresolved")
        if normalized_pending_slices > 0:
            blocking_reasons.append("paper-facing supplementary slices are still pending")

        contract_ok = not unresolved_required_items and not unmapped_completed_items
        writing_ready = contract_ok and normalized_pending_slices == 0
        coverage = self._paper_manuscript_coverage_payload(
            quest_root,
            workspace_root=workspace_root,
            evidence_gate=gate_status,
            pending_slices=normalized_pending_slices,
        )
        package_type = str(coverage.get("package_type") or "draft_checkpoint").strip() or "draft_checkpoint"
        evidence_ready = bool(coverage.get("evidence_ready"))
        analysis_ready = bool(coverage.get("analysis_ready"))
        draft_checkpoint_ready = bool(coverage.get("draft_checkpoint_ready"))
        manuscript_ready = bool(coverage.get("manuscript_ready"))
        submission_ready = bool(coverage.get("submission_ready"))
        overall_status = str(submission_checklist.get("overall_status") or bundle_manifest.get("status") or "").strip().lower()
        delivered_at = str(
            bundle_manifest.get("paper_delivered_to_user_at")
            or bundle_manifest.get("delivered_at")
            or submission_checklist.get("paper_delivered_to_user_at")
            or ""
        ).strip() or None
        bundle_present = bundle_manifest_path.exists()
        delivery_state = "not_ready"
        closure_state = "bundle_not_ready"
        keep_bundle_fixed_by_default = False
        if submission_ready:
            delivery_state = "submission_ready"
            closure_state = "delivery_ready"
        elif manuscript_ready:
            delivery_state = "manuscript_ready"
            closure_state = "review_before_submission"
        elif draft_checkpoint_ready or bundle_present:
            delivery_state = "draft_checkpoint_ready"
            closure_state = "draft_checkpoint_continue_writing"
        if delivered_at or "delivered" in overall_status:
            delivery_state = "delivered"
            closure_state = "delivered_continue_research" if "continue" in overall_status else "delivered_parked"
            keep_bundle_fixed_by_default = True

        if unmapped_completed_items:
            recommended_next_stage = "write"
            recommended_action = "sync_paper_contract"
        elif unresolved_required_items or normalized_pending_slices > 0:
            recommended_next_stage = "analysis-campaign"
            recommended_action = "complete_required_supplementary"
        elif not draft_checkpoint_ready:
            recommended_next_stage = "write"
            recommended_action = "draft_paper"
        elif not bundle_present:
            recommended_next_stage = "write"
            recommended_action = "submit_draft_checkpoint"
        elif not manuscript_ready:
            recommended_next_stage = "write"
            recommended_action = "expand_manuscript_and_figures"
        elif not submission_ready:
            recommended_next_stage = "review"
            recommended_action = "prepare_submission_package"
        else:
            recommended_next_stage = "finalize"
            recommended_action = "finalize_paper_line"

        return {
            "contract_ok": contract_ok,
            "writing_ready": writing_ready,
            "evidence_ready": evidence_ready,
            "analysis_ready": analysis_ready,
            "draft_checkpoint_ready": draft_checkpoint_ready,
            "manuscript_ready": manuscript_ready,
            "submission_ready": submission_ready,
            "finalize_ready": submission_ready,
            "package_type": package_type,
            "bundle_present": bundle_present,
            "delivery_state": delivery_state,
            "closure_state": closure_state,
            "delivered_at": delivered_at,
            "keep_bundle_fixed_by_default": keep_bundle_fixed_by_default,
            "selected_outline_ref": gate_status.get("selected_outline_ref"),
            "section_count": int(gate_status.get("section_count") or 0),
            "ready_section_count": int(gate_status.get("ready_section_count") or 0),
            "ledger_item_count": int(gate_status.get("ledger_item_count") or 0),
            "unresolved_required_count": len(unresolved_required_items),
            "unmapped_completed_count": len(unmapped_completed_items),
            "open_supplementary_count": normalized_pending_slices,
            "blocking_reasons": blocking_reasons,
            "manuscript_blocking_reasons": list(coverage.get("manuscript_blockers") or []),
            "submission_blocking_reasons": list(coverage.get("submission_blockers") or []),
            "recommended_next_stage": recommended_next_stage,
            "recommended_action": recommended_action,
            "manuscript_coverage": coverage,
            "unresolved_required_items": unresolved_required_items[:12],
            "unmapped_completed_items": unmapped_completed_items[:12],
        }

    def _write_paper_line_state(
        self,
        quest_root: Path,
        *,
        workspace_root: Path | None = None,
        source_branch: str | None = None,
        source_run_id: str | None = None,
        source_idea_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        selected_outline_path, selected_outline = self._read_selected_outline_for_sync(
            quest_root,
            workspace_root=workspace_root,
        )
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        detailed_outline = (
            dict(selected_outline.get("detailed_outline") or {})
            if isinstance(selected_outline.get("detailed_outline"), dict)
            else {}
        )
        sections = self._normalize_outline_sections(
            selected_outline.get("sections"),
            experimental_designs=self._normalize_string_list(detailed_outline.get("experimental_designs")),
        )
        paper_root = self._paper_root(quest_root, workspace_root=workspace_root, create=True)
        paper_branch = current_branch(paper_root.parent)
        ledger = self._read_paper_evidence_ledger(quest_root)
        draft_path = paper_root / "draft.md"
        bundle_path = paper_root / "paper_bundle_manifest.json"
        pending_slices = 0
        campaigns_root = quest_root / ".ds" / "analysis_campaigns"
        selected_outline_ref = str(selected_outline.get("outline_id") or ledger.get("selected_outline_ref") or "").strip() or None
        if campaigns_root.exists():
            for path in sorted(campaigns_root.glob("analysis-*.json")):
                manifest = read_json(path, {})
                if not isinstance(manifest, dict) or not manifest:
                    continue
                manifest_outline_ref = str(manifest.get("selected_outline_ref") or "").strip() or None
                if selected_outline_ref and manifest_outline_ref != selected_outline_ref:
                    continue
                pending_slices += sum(
                    1
                    for item in (manifest.get("slices") or [])
                    if isinstance(item, dict) and str(item.get("status") or "pending").strip() == "pending"
                )
        health = self._paper_contract_health_payload(
            quest_root,
            workspace_root=workspace_root,
            pending_slices=pending_slices,
        )
        coverage = (
            dict(health.get("manuscript_coverage") or {})
            if isinstance(health.get("manuscript_coverage"), dict)
            else {}
        )
        required_count = sum(len(self._normalize_string_list(section.get("required_items"))) for section in sections)
        ready_required_count = required_count - int(health.get("unresolved_required_count") or 0)
        payload = {
            "schema_version": 1,
            "paper_line_id": self._paper_line_id(
                paper_branch=paper_branch,
                outline_id=selected_outline_ref,
                source_run_id=source_run_id or str(state.get("paper_parent_run_id") or "").strip() or None,
            ),
            "paper_branch": paper_branch,
            "paper_root": str(paper_root),
            "workspace_root": str(paper_root.parent),
            "source_branch": source_branch or str(state.get("paper_parent_branch") or "").strip() or None,
            "source_run_id": source_run_id or str(state.get("paper_parent_run_id") or "").strip() or None,
            "source_idea_id": source_idea_id or str(state.get("active_idea_id") or "").strip() or None,
            "selected_outline_ref": selected_outline_ref,
            "selected_outline_path": str(selected_outline_path) if selected_outline_path else None,
            "title": str(selected_outline.get("title") or "").strip() or None,
            "required_count": required_count,
            "ready_required_count": max(0, ready_required_count),
            "section_count": len(sections),
            "ready_section_count": int(health.get("ready_section_count") or 0),
            "unmapped_count": int(health.get("unmapped_completed_count") or 0),
            "open_supplementary_count": pending_slices,
            "contract_ok": bool(health.get("contract_ok")),
            "writing_ready": bool(health.get("writing_ready")),
            "evidence_ready": bool(health.get("evidence_ready")),
            "analysis_ready": bool(health.get("analysis_ready")),
            "draft_checkpoint_ready": bool(health.get("draft_checkpoint_ready")),
            "manuscript_ready": bool(health.get("manuscript_ready")),
            "submission_ready": bool(health.get("submission_ready")),
            "finalize_ready": bool(health.get("finalize_ready")),
            "package_type": str(health.get("package_type") or "").strip() or None,
            "closure_state": str(health.get("closure_state") or "").strip() or None,
            "delivery_state": str(health.get("delivery_state") or "").strip() or None,
            "delivered_at": str(health.get("delivered_at") or "").strip() or None,
            "keep_bundle_fixed_by_default": bool(health.get("keep_bundle_fixed_by_default")),
            "unresolved_required_count": int(health.get("unresolved_required_count") or 0),
            "unmapped_completed_count": int(health.get("unmapped_completed_count") or 0),
            "blocking_reasons": list(health.get("blocking_reasons") or []),
            "manuscript_blocking_reasons": list(health.get("manuscript_blocking_reasons") or []),
            "submission_blocking_reasons": list(health.get("submission_blocking_reasons") or []),
            "recommended_next_stage": str(health.get("recommended_next_stage") or "").strip() or None,
            "recommended_action": str(health.get("recommended_action") or "").strip() or None,
            "draft_status": "present" if bool(coverage.get("draft_present")) or draft_path.exists() else "missing",
            "bundle_status": "present" if bundle_path.exists() else "missing",
            "manuscript_coverage_path": str(self._paper_manuscript_coverage_path(quest_root, workspace_root=workspace_root)),
            "updated_at": utc_now(),
        }
        for paper_sync_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            write_json(paper_sync_root / "paper_line_state.json", payload)
            write_json(paper_sync_root / "manuscript_coverage.json", coverage)
        return payload

    def _active_baseline_attachment(self, quest_root: Path, workspace_root: Path | None = None) -> dict[str, Any] | None:
        target_root = self._workspace_root_for(quest_root, workspace_root)
        attachments: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for root in (target_root, quest_root):
            attachment_root = root / "baselines" / "imported"
            if not attachment_root.exists():
                continue
            for path in sorted(attachment_root.glob("*/attachment.yaml")):
                key = str(path.resolve())
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                payload = read_yaml(path, {})
                baseline_id = str(payload.get("source_baseline_id") or "").strip() if isinstance(payload, dict) else ""
                if baseline_id and self.baselines.is_deleted(baseline_id):
                    continue
                if isinstance(payload, dict) and payload:
                    attachments.append(payload)
        if not attachments:
            return None
        return max(
            attachments,
            key=lambda item: (
                str(item.get("attached_at") or ""),
                str(item.get("source_baseline_id") or ""),
            ),
        )

    def _baseline_workspace_roots(self, quest_root: Path) -> list[Path]:
        roots: list[Path] = [quest_root]
        research_state = read_json(quest_root / ".ds" / "research_state.json", {})
        if isinstance(research_state, dict):
            for key in (
                "research_head_worktree_root",
                "current_workspace_root",
                "analysis_parent_worktree_root",
                "paper_parent_worktree_root",
            ):
                raw = str(research_state.get(key) or "").strip()
                if raw:
                    roots.append(Path(raw))
        worktrees_root = quest_root / ".ds" / "worktrees"
        if worktrees_root.exists():
            roots.extend(path for path in sorted(worktrees_root.iterdir()) if path.is_dir())
        deduped: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve(strict=False))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root)
        return deduped

    @staticmethod
    def _remove_baseline_materialization(root: Path, baseline_id: str) -> list[str]:
        deleted_paths: list[str] = []
        for candidate in (
            root / "baselines" / "imported" / baseline_id,
            root / "baselines" / "local" / baseline_id,
        ):
            if not candidate.exists():
                continue
            if candidate.is_dir():
                shutil.rmtree(candidate)
            else:
                candidate.unlink()
            deleted_paths.append(str(candidate))
        return deleted_paths

    def _resolve_baseline_path(
        self,
        quest_root: Path,
        baseline_path: str,
        *,
        baseline_id: str | None = None,
    ) -> dict[str, Any]:
        raw = str(baseline_path or "").strip()
        if not raw:
            raise ValueError("`baseline_path` is required.")
        candidate = Path(raw)
        resolved = candidate.resolve() if candidate.is_absolute() else resolve_within(quest_root, raw)
        if not resolved.exists():
            raise FileNotFoundError(f"Baseline path does not exist: {resolved}")
        try:
            relative = resolved.relative_to(quest_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("`baseline_path` must stay within quest_root.") from exc
        parts = Path(relative).parts
        if len(parts) < 3 or parts[0] != "baselines" or parts[1] not in {"local", "imported"}:
            raise ValueError(
                "`baseline_path` must live under `baselines/local/<baseline_id>/...` or "
                "`baselines/imported/<baseline_id>/...`."
            )
        source_mode = "local" if parts[1] == "local" else "imported"
        inferred_baseline_id = str(baseline_id or parts[2]).strip()
        baseline_root = quest_root / parts[0] / parts[1] / parts[2]
        return {
            "resolved_path": resolved,
            "relative_path": relative,
            "baseline_root": baseline_root,
            "baseline_root_rel_path": baseline_root.relative_to(quest_root).as_posix(),
            "source_mode": source_mode,
            "baseline_id": inferred_baseline_id,
        }

    def _latest_baseline_record(self, quest_root: Path, baseline_id: str) -> dict[str, Any] | None:
        matches: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for root in self.quest_service.workspace_roots(quest_root):
            artifacts_root = root / "artifacts" / "baselines"
            if not artifacts_root.exists():
                continue
            for path in sorted(artifacts_root.glob("*.json")):
                if not path.is_file():
                    continue
                key = str(path.resolve())
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                payload = read_json(path, {})
                if not isinstance(payload, dict) or not payload:
                    continue
                if str(payload.get("baseline_id") or "").strip() != baseline_id:
                    continue
                matches.append(payload)
        if not matches:
            return None
        return max(matches, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""))

    def _baseline_entry_from_local_state(
        self,
        quest_root: Path,
        *,
        baseline_id: str,
        baseline_root: Path,
        variant_id: str | None,
        summary: str | None,
        baseline_kind: str | None,
        metric_contract: dict[str, Any] | None,
        metrics_summary: dict[str, Any] | None,
        primary_metric: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        existing = self._latest_baseline_record(quest_root, baseline_id) or {}
        normalized_metrics = normalize_metrics_summary(metrics_summary or existing.get("metrics_summary"))
        existing_variants = existing.get("baseline_variants") if isinstance(existing.get("baseline_variants"), list) else []
        normalized_variant_id = str(variant_id or existing.get("default_variant_id") or "").strip() or None
        baseline_variants = existing_variants
        if normalized_variant_id and not baseline_variants:
            baseline_variants = [
                {
                    "variant_id": normalized_variant_id,
                    "label": normalized_variant_id,
                    "metrics_summary": normalized_metrics,
                }
            ]
        default_variant_id = normalized_variant_id or existing.get("default_variant_id")
        if baseline_variants and default_variant_id is None and len(baseline_variants) == 1:
            default_variant_id = baseline_variants[0].get("variant_id")
        selected_variant = None
        if baseline_variants:
            selected_variant = next(
                (
                    item
                    for item in baseline_variants
                    if str(item.get("variant_id") or "").strip() == str(default_variant_id or "").strip()
                ),
                baseline_variants[0],
            )
        normalized_contract = normalize_metric_contract(
            metric_contract or existing.get("metric_contract"),
            baseline_id=baseline_id,
            metrics_summary=normalized_metrics,
            primary_metric=primary_metric or existing.get("primary_metric"),
            baseline_variants=baseline_variants,
        )
        entry = {
            "registry_kind": "baseline",
            "schema_version": 1,
            "entry_id": baseline_id,
            "baseline_id": baseline_id,
            "status": "quest_local",
            "created_at": existing.get("created_at") or utc_now(),
            "updated_at": utc_now(),
            "path": str(baseline_root),
            "summary": summary or existing.get("summary") or "",
            "baseline_kind": baseline_kind or existing.get("baseline_kind") or "reproduced",
            "primary_metric": primary_metric or existing.get("primary_metric"),
            "metrics_summary": normalized_metrics,
            "baseline_variants": baseline_variants,
            "default_variant_id": default_variant_id,
            "metric_contract": normalized_contract,
        }
        return entry, selected_variant

    def _write_confirmed_baseline_attachment(
        self,
        quest_root: Path,
        *,
        baseline_id: str,
        variant_id: str | None,
        entry: dict[str, Any],
        selected_variant: dict[str, Any] | None,
        source_mode: str,
        baseline_root: Path,
        comment: str | dict[str, Any] | None,
        metric_contract_json_path: str | None,
        metric_contract_json_rel_path: str | None,
    ) -> dict[str, Any]:
        attachment_root = ensure_dir(quest_root / "baselines" / "imported" / baseline_id)
        attachment_path = attachment_root / "attachment.yaml"
        existing = read_yaml(attachment_path, {})
        if not isinstance(existing, dict):
            existing = {}
        attachment = {
            **existing,
            "attached_at": utc_now(),
            "source_baseline_id": baseline_id,
            "source_variant_id": variant_id,
            "entry": entry,
            "selected_variant": selected_variant,
            "confirmation": {
                "source_mode": source_mode,
                "baseline_root": str(baseline_root),
                "comment": comment,
                "metric_contract_json_path": metric_contract_json_path,
                "metric_contract_json_rel_path": metric_contract_json_rel_path,
            },
        }
        write_yaml(attachment_path, attachment)
        return attachment

    def _write_baseline_metric_contract_json(
        self,
        quest_root: Path,
        *,
        baseline_root: Path,
        baseline_root_rel_path: str,
        baseline_id: str,
        variant_id: str | None,
        entry: dict[str, Any],
        selected_variant: dict[str, Any] | None,
        source_mode: str,
    ) -> dict[str, Any]:
        metric_contract = (
            dict(entry.get("metric_contract") or {})
            if isinstance(entry.get("metric_contract"), dict)
            else {}
        )
        metrics_summary = selected_baseline_metrics(entry, variant_id)
        if not metrics_summary and isinstance(selected_variant, dict):
            metrics_summary = normalize_metrics_summary(selected_variant.get("metrics_summary"))
        payload = {
            "schema_version": 1,
            "kind": "baseline_metric_contract",
            "baseline_id": baseline_id,
            "variant_id": variant_id,
            "source_mode": source_mode,
            "baseline_root_rel_path": baseline_root_rel_path,
            "written_at": utc_now(),
            "metric_contract": metric_contract,
            "primary_metric": entry.get("primary_metric"),
            "metrics_summary": metrics_summary,
            "metric_details": entry.get("metric_details") or [],
        }
        json_path = ensure_dir(baseline_root / "json") / "metric_contract.json"
        write_json(json_path, payload)
        return {
            "path": str(json_path),
            "rel_path": self._workspace_relative(quest_root, json_path),
            "payload": payload,
        }

    def _copy_tree_contents(self, source_root: Path, target_root: Path) -> None:
        ensure_dir(target_root)
        for child in sorted(source_root.iterdir()):
            if child.name == "attachment.yaml":
                continue
            target = target_root / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
                continue
            ensure_dir(target.parent)
            shutil.copy2(child, target)

    def _materialize_baseline_attachment(self, quest_root: Path, attachment: dict[str, Any]) -> dict[str, Any]:
        baseline_id = str(attachment.get("source_baseline_id") or "").strip()
        if not baseline_id:
            raise ValueError("Attachment is missing `source_baseline_id`.")
        entry = dict(attachment.get("entry") or {}) if isinstance(attachment.get("entry"), dict) else {}
        source_raw = str(entry.get("path") or "").strip()
        target_root = ensure_dir(quest_root / "baselines" / "imported" / baseline_id)
        materialized: dict[str, Any] = {**attachment}
        materialized["materialization"] = {
            "status": "skipped",
            "source_path": source_raw or None,
            "target_path": str(target_root),
            "error": None,
        }

        if source_raw:
            source_root = Path(source_raw).expanduser().resolve()
            if source_root.exists() and source_root.is_dir():
                if source_root != target_root.resolve():
                    self._copy_tree_contents(source_root, target_root)
                materialized["materialized_at"] = utc_now()
                materialized["materialized_path"] = str(target_root)
                materialized["source_path"] = str(source_root)
                materialized["materialization"] = {
                    "status": "ok",
                    "source_path": str(source_root),
                    "target_path": str(target_root),
                    "error": None,
                }
            else:
                materialized["materialization"] = {
                    "status": "error",
                    "source_path": str(source_root),
                    "target_path": str(target_root),
                    "error": "source_path_missing_or_not_directory",
                }
        write_yaml(target_root / "attachment.yaml", materialized)
        return materialized

    def _sync_confirmed_baseline_registry_entry(
        self,
        *,
        quest_root: Path,
        baseline_id: str,
        variant_id: str | None,
        entry: dict[str, Any],
        selected_variant: dict[str, Any] | None,
        resolved_root: Path,
        summary: str | None,
        source_mode: str,
    ) -> dict[str, Any]:
        source_path = str(entry.get("path") or "").strip() or str(resolved_root)
        materializable = bool(source_path) and Path(source_path).expanduser().is_dir()
        registry_payload = {
            **entry,
            "baseline_id": baseline_id,
            "entry_id": baseline_id,
            "status": "quest_confirmed",
            "summary": summary or entry.get("summary") or "",
            "path": source_path,
            "source_mode": source_mode,
            "source_quest_id": quest_root.name,
            "source_baseline_path": source_path,
            "confirmed_at": utc_now(),
            "selected_variant_id": variant_id or (selected_variant or {}).get("variant_id"),
            "materializable": materializable,
            "availability": "ready" if materializable else "missing",
            "default_variant_id": entry.get("default_variant_id"),
            "baseline_variants": entry.get("baseline_variants") or [],
            "metric_contract": entry.get("metric_contract"),
            "primary_metric": entry.get("primary_metric"),
            "metrics_summary": entry.get("metrics_summary") or {},
        }
        return self.baselines.publish(registry_payload)

    def _baseline_current_confirmation_context(self, quest_root: Path) -> dict[str, Any]:
        quest_yaml = self.quest_service.read_quest_yaml(quest_root)
        confirmed_ref = (
            dict(quest_yaml.get("confirmed_baseline_ref") or {})
            if isinstance(quest_yaml.get("confirmed_baseline_ref"), dict)
            else {}
        )
        attachment = self._active_baseline_attachment(quest_root, workspace_root=quest_root)
        attachment_entry = (
            dict(attachment.get("entry") or {})
            if isinstance(attachment, dict) and isinstance(attachment.get("entry"), dict)
            else {}
        )
        current_baseline_id = (
            str(confirmed_ref.get("baseline_id") or "").strip()
            or (str(attachment.get("source_baseline_id") or "").strip() if isinstance(attachment, dict) else "")
            or None
        )
        current_variant_id = (
            str(confirmed_ref.get("variant_id") or "").strip()
            or (str(attachment.get("source_variant_id") or "").strip() if isinstance(attachment, dict) else "")
            or None
        )
        current_baseline_root_rel_path = str(confirmed_ref.get("baseline_root_rel_path") or "").strip() or None
        if (
            current_baseline_root_rel_path is None
            and isinstance(attachment, dict)
            and isinstance(attachment.get("confirmation"), dict)
            and str((attachment.get("confirmation") or {}).get("baseline_root") or "").strip()
        ):
            current_baseline_root_rel_path = self._workspace_relative(
                quest_root,
                Path(str((attachment.get("confirmation") or {}).get("baseline_root") or "")).expanduser(),
            )
        current_source_mode = (
            str(confirmed_ref.get("source_mode") or "").strip()
            or (
                str(((attachment or {}).get("confirmation") or {}).get("source_mode") or "").strip()
                if isinstance(attachment, dict) and isinstance(attachment.get("confirmation"), dict)
                else ""
            )
            or None
        )
        metric_contract_json_rel_path = str(confirmed_ref.get("metric_contract_json_rel_path") or "").strip() or None
        metric_contract_payload = self._load_metric_contract_payload(quest_root, metric_contract_json_rel_path)
        current_entry = attachment_entry
        if not current_entry and current_baseline_id:
            current_entry = self._latest_baseline_record(quest_root, current_baseline_id) or {}
        if not current_entry and current_baseline_id:
            registry_entry = self.baselines.get(current_baseline_id)
            current_entry = dict(registry_entry or {}) if isinstance(registry_entry, dict) else {}
        current_metric_contract = (
            dict(metric_contract_payload.get("metric_contract") or {})
            if isinstance(metric_contract_payload, dict) and isinstance(metric_contract_payload.get("metric_contract"), dict)
            else dict(current_entry.get("metric_contract") or {})
            if isinstance(current_entry.get("metric_contract"), dict)
            else {}
        )
        current_metrics_summary = (
            normalize_metrics_summary(metric_contract_payload.get("metrics_summary"))
            if isinstance(metric_contract_payload, dict) and isinstance(metric_contract_payload.get("metrics_summary"), dict)
            else selected_baseline_metrics(current_entry, current_variant_id)
        )
        current_primary_metric = (
            dict(metric_contract_payload.get("primary_metric") or {})
            if isinstance(metric_contract_payload, dict) and isinstance(metric_contract_payload.get("primary_metric"), dict)
            else dict(current_entry.get("primary_metric") or {})
            if isinstance(current_entry.get("primary_metric"), dict)
            else {}
        )
        return {
            "confirmed_ref": confirmed_ref,
            "attachment": attachment,
            "entry": current_entry,
            "baseline_id": current_baseline_id,
            "variant_id": current_variant_id,
            "baseline_root_rel_path": current_baseline_root_rel_path,
            "source_mode": current_source_mode,
            "metric_contract_payload": metric_contract_payload,
            "metric_contract": current_metric_contract,
            "metrics_summary": current_metrics_summary,
            "primary_metric": current_primary_metric,
        }

    @staticmethod
    def _metric_direction_map(metric_contract: dict[str, Any] | None) -> dict[str, str]:
        if not isinstance(metric_contract, dict):
            return {}
        result: dict[str, str] = {}
        for item in metric_contract.get("metrics") or []:
            if not isinstance(item, dict):
                continue
            metric_id = str(item.get("metric_id") or "").strip()
            if not metric_id:
                continue
            result[metric_id] = normalize_metric_direction(item.get("direction"), metric_id=metric_id)
        return result

    @staticmethod
    def _primary_metric_id(primary_metric: dict[str, Any] | None, metric_contract: dict[str, Any] | None) -> str | None:
        if isinstance(primary_metric, dict):
            metric_id = str(primary_metric.get("metric_id") or primary_metric.get("name") or primary_metric.get("id") or "").strip()
            if metric_id:
                return metric_id
        if isinstance(metric_contract, dict):
            metric_id = str(metric_contract.get("primary_metric_id") or "").strip()
            if metric_id:
                return metric_id
        return None

    @staticmethod
    def _normalize_overwrite_scope(value: str | None) -> str:
        normalized = str(value or "full_refresh").strip().lower() or "full_refresh"
        allowed = {"metrics_only", "variants_and_metrics", "full_refresh"}
        if normalized not in allowed:
            raise ValueError(f"`overwrite_scope` must be one of: {', '.join(sorted(allowed))}.")
        return normalized

    def _baseline_overwrite_preflight(
        self,
        quest_root: Path,
        *,
        baseline_id: str | None,
        baseline_path: str | None,
        variant_id: str | None,
        metric_contract: dict[str, Any] | None,
        metric_directions: dict[str, str] | None,
        metrics_summary: dict[str, Any] | None,
        primary_metric: dict[str, Any] | None,
        allow_path_change: bool,
        allow_protocol_breaking_change: bool,
        overwrite_scope: str,
    ) -> dict[str, Any]:
        current = self._baseline_current_confirmation_context(quest_root)
        current_baseline_id = str(current.get("baseline_id") or "").strip()
        if not current_baseline_id:
            raise ValueError(
                "`artifact.overwrite_baseline(...)` requires an already accepted baseline. "
                "Use `artifact.confirm_baseline(...)` first."
            )

        target_baseline_id = str(baseline_id or current_baseline_id).strip()
        if target_baseline_id != current_baseline_id:
            raise ValueError(
                "Baseline overwrite only supports the currently active baseline id. "
                "Use a new `baseline_id` or a new `variant_id` instead of overwriting a different baseline in place."
            )

        current_source_mode = str(current.get("source_mode") or "").strip().lower() or None
        resolved_baseline_path = (
            str(baseline_path or "").strip()
            or str((current.get("confirmed_ref") or {}).get("baseline_path") or "").strip()
            or str((current.get("entry") or {}).get("path") or "").strip()
        )
        if not resolved_baseline_path:
            raise ValueError("`baseline_path` is required when the current confirmed baseline path is unavailable.")
        resolved = self._resolve_baseline_path(quest_root, resolved_baseline_path, baseline_id=target_baseline_id)
        resolved_source_mode = str(resolved.get("source_mode") or "").strip().lower() or None
        if current_source_mode == "imported" and resolved_source_mode == "imported":
            raise ValueError(
                "In-place overwrite of an imported baseline is not allowed. "
                "Materialize the updated comparator under `baselines/local/...` or create a new baseline id / variant."
            )

        current_root_rel_path = str(current.get("baseline_root_rel_path") or "").strip() or None
        target_root_rel_path = str(resolved.get("baseline_root_rel_path") or "").strip() or None
        path_changed = bool(current_root_rel_path and target_root_rel_path and current_root_rel_path != target_root_rel_path)
        if path_changed and not allow_path_change:
            raise ValueError(
                "Baseline root changed. Set `allow_path_change=true` only when the new root is still the same comparator "
                "and you explicitly want an in-place baseline refresh."
            )

        current_entry = dict(current.get("entry") or {})
        current_variants = copy.deepcopy(current_entry.get("baseline_variants")) if isinstance(current_entry.get("baseline_variants"), list) else []
        normalized_variant_id = str(
            variant_id
            or current.get("variant_id")
            or current_entry.get("default_variant_id")
            or ""
        ).strip() or None
        if normalized_variant_id and not current_variants:
            current_variants = [
                {
                    "variant_id": normalized_variant_id,
                    "label": normalized_variant_id,
                    "metrics_summary": normalize_metrics_summary(metrics_summary or current.get("metrics_summary")),
                }
            ]
        elif normalized_variant_id and all(
            str(item.get("variant_id") or "").strip() != normalized_variant_id
            for item in current_variants
            if isinstance(item, dict)
        ):
            current_variants.append(
                {
                    "variant_id": normalized_variant_id,
                    "label": normalized_variant_id,
                    "metrics_summary": normalize_metrics_summary(metrics_summary or {}),
                }
            )

        current_metrics_summary = normalize_metrics_summary(current.get("metrics_summary"))
        proposed_metrics_summary = normalize_metrics_summary(metrics_summary or current_metrics_summary)
        current_primary_metric = dict(current.get("primary_metric") or {}) if isinstance(current.get("primary_metric"), dict) else {}
        proposed_primary_metric = dict(primary_metric or current_primary_metric)
        current_metric_contract = normalize_metric_contract(
            current.get("metric_contract"),
            baseline_id=target_baseline_id,
            metrics_summary=current_metrics_summary,
            primary_metric=current_primary_metric,
            baseline_variants=current_variants,
        )
        proposed_metric_contract = normalize_metric_contract(
            metric_contract or current_metric_contract,
            baseline_id=target_baseline_id,
            metrics_summary=proposed_metrics_summary,
            primary_metric=proposed_primary_metric,
            baseline_variants=current_variants,
        )
        if metric_directions:
            proposed_metric_contract = {
                **proposed_metric_contract,
                "metrics": [
                    (
                        {**item, "direction": metric_directions[str(item.get("metric_id") or "").strip()]}
                        if isinstance(item, dict)
                        and str(item.get("metric_id") or "").strip() in metric_directions
                        else dict(item)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in (proposed_metric_contract.get("metrics") or [])
                ],
            }

        current_direction_map = self._metric_direction_map(current_metric_contract)
        proposed_direction_map = self._metric_direction_map(proposed_metric_contract)
        current_metric_ids = set(current_direction_map.keys())
        proposed_metric_ids = set(proposed_direction_map.keys())
        added_metric_ids = sorted(proposed_metric_ids - current_metric_ids)
        removed_metric_ids = sorted(current_metric_ids - proposed_metric_ids)
        direction_changed_metric_ids = sorted(
            metric_id
            for metric_id in (current_metric_ids & proposed_metric_ids)
            if current_direction_map.get(metric_id) != proposed_direction_map.get(metric_id)
        )
        current_primary_metric_id = self._primary_metric_id(current_primary_metric, current_metric_contract)
        proposed_primary_metric_id = self._primary_metric_id(proposed_primary_metric, proposed_metric_contract)
        evaluation_protocol_changed = (
            (current_metric_contract.get("evaluation_protocol") or None)
            != (proposed_metric_contract.get("evaluation_protocol") or None)
        )
        variant_changed = bool(normalized_variant_id and normalized_variant_id != str(current.get("variant_id") or "").strip())

        protocol_breaking_reasons: list[str] = []
        if removed_metric_ids:
            protocol_breaking_reasons.append("required metric coverage would shrink")
        if direction_changed_metric_ids:
            protocol_breaking_reasons.append("metric directions changed")
        if current_primary_metric_id and proposed_primary_metric_id and current_primary_metric_id != proposed_primary_metric_id:
            protocol_breaking_reasons.append("primary metric changed")
        if evaluation_protocol_changed:
            protocol_breaking_reasons.append("evaluation protocol changed")
        if current_source_mode and resolved_source_mode and current_source_mode != resolved_source_mode:
            protocol_breaking_reasons.append("baseline source mode changed")
        if protocol_breaking_reasons and not allow_protocol_breaking_change:
            raise ValueError(
                "This overwrite would change baseline comparability in a protocol-breaking way: "
                + "; ".join(protocol_breaking_reasons)
                + ". Use a new baseline id or variant instead, unless you explicitly allow the breaking change."
            )

        if protocol_breaking_reasons:
            compatibility_verdict = "protocol_breaking_change_forced"
            risk_level = "high"
        elif added_metric_ids and not variant_changed and not path_changed:
            compatibility_verdict = "metrics_only_safe"
            risk_level = "low"
        elif variant_changed and not path_changed:
            compatibility_verdict = "variant_refresh_safe"
            risk_level = "medium"
        elif path_changed:
            compatibility_verdict = "path_changed_but_compatible"
            risk_level = "medium"
        else:
            compatibility_verdict = "same_comparator_refresh_safe"
            risk_level = "low"

        return {
            "current": current,
            "resolved": resolved,
            "baseline_id": target_baseline_id,
            "variant_id": normalized_variant_id,
            "overwrite_scope": overwrite_scope,
            "added_metric_ids": added_metric_ids,
            "removed_metric_ids": removed_metric_ids,
            "direction_changed_metric_ids": direction_changed_metric_ids,
            "current_primary_metric_id": current_primary_metric_id,
            "proposed_primary_metric_id": proposed_primary_metric_id,
            "evaluation_protocol_changed": evaluation_protocol_changed,
            "path_changed": path_changed,
            "variant_changed": variant_changed,
            "protocol_breaking_reasons": protocol_breaking_reasons,
            "compatibility_verdict": compatibility_verdict,
            "risk_level": risk_level,
        }

    def _refresh_analysis_inventory_for_overwrite(
        self,
        quest_root: Path,
        *,
        baseline_id: str,
        variant_id: str | None,
        baseline_root_rel_path: str | None,
        source_mode: str | None,
        metrics_summary: dict[str, Any],
        supplementary_baselines: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        inventory = self._read_analysis_baseline_inventory(quest_root)
        changed = False
        refreshed_entries: list[dict[str, Any]] = []
        for raw in inventory.get("entries") or []:
            if not isinstance(raw, dict):
                continue
            entry = dict(raw)
            if str(entry.get("baseline_id") or "").strip() != baseline_id:
                refreshed_entries.append(entry)
                continue
            entry_variant_id = str(entry.get("variant_id") or "").strip() or None
            if variant_id and entry_variant_id and entry_variant_id != variant_id:
                refreshed_entries.append(entry)
                continue
            if baseline_root_rel_path and entry.get("baseline_root_rel_path") != baseline_root_rel_path:
                entry["baseline_root_rel_path"] = baseline_root_rel_path
                changed = True
            if source_mode and entry.get("storage_mode") != source_mode:
                entry["storage_mode"] = source_mode
                changed = True
            if metrics_summary and entry.get("metrics_summary") != metrics_summary:
                entry["metrics_summary"] = dict(metrics_summary)
                changed = True
            entry["updated_at"] = utc_now()
            refreshed_entries.append(entry)
        if changed:
            inventory = self._write_analysis_baseline_inventory(quest_root, {"entries": refreshed_entries})
        if supplementary_baselines:
            normalized_supplementary = self._normalize_comparison_baselines(quest_root, supplementary_baselines)
            inventory = self._upsert_analysis_baseline_inventory(quest_root, normalized_supplementary)
        return inventory if changed or supplementary_baselines else None

    def _invalidate_baseline_view_caches(self, quest_root: Path) -> list[str]:
        removed: list[str] = []
        for path in (
            self.quest_service._metrics_timeline_cache_path(quest_root),
            self.quest_service._baseline_compare_cache_path(quest_root),
        ):
            if path.exists():
                path.unlink()
                removed.append(str(path))
        return removed

    def _build_overwrite_baseline_interaction_message(
        self,
        *,
        baseline_id: str,
        variant_id: str | None,
        compatibility_verdict: str | None,
        change_summary: str,
        added_metric_ids: list[str] | None,
        risk_level: str | None,
    ) -> str:
        lines = [
            f"Baseline `{baseline_id}` has been refreshed.",
        ]
        if variant_id:
            lines.append(f"Active variant: `{variant_id}`.")
        if compatibility_verdict:
            lines.append(f"Compatibility verdict: `{compatibility_verdict}`.")
        if added_metric_ids:
            lines.append(f"Added canonical metrics: {', '.join(f'`{metric_id}`' for metric_id in added_metric_ids)}.")
        lines.append(f"Change summary: {change_summary}")
        if risk_level and risk_level != "low":
            lines.append(f"Risk level: `{risk_level}`.")
        return "\n".join(lines)

    def overwrite_baseline(
        self,
        quest_root: Path,
        *,
        baseline_id: str | None = None,
        baseline_path: str | None = None,
        variant_id: str | None = None,
        summary: str | None = None,
        change_summary: str,
        baseline_kind: str | None = None,
        metric_contract: dict[str, Any] | None = None,
        metric_directions: dict[str, str] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        primary_metric: dict[str, Any] | None = None,
        supplementary_baselines: list[dict[str, Any]] | None = None,
        overwrite_scope: str = "full_refresh",
        allow_path_change: bool = False,
        allow_protocol_breaking_change: bool = False,
        sync_requested_baseline_ref: bool = True,
        refresh_analysis_inventory: bool = True,
        refresh_paper_inventory: bool = True,
        auto_advance: bool = True,
        strict_metric_contract: bool = False,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_change_summary = str(change_summary or "").strip()
        if not normalized_change_summary:
            raise ValueError("`change_summary` is required for `artifact.overwrite_baseline(...)`.")
        normalized_scope = self._normalize_overwrite_scope(overwrite_scope)
        preflight = self._baseline_overwrite_preflight(
            quest_root,
            baseline_id=baseline_id,
            baseline_path=baseline_path,
            variant_id=variant_id,
            metric_contract=metric_contract,
            metric_directions=metric_directions,
            metrics_summary=metrics_summary,
            primary_metric=primary_metric,
            allow_path_change=allow_path_change,
            allow_protocol_breaking_change=allow_protocol_breaking_change,
            overwrite_scope=normalized_scope,
        )
        current = dict(preflight.get("current") or {})
        resolved = dict(preflight.get("resolved") or {})
        target_baseline_id = str(preflight.get("baseline_id") or "").strip()
        target_variant_id = str(preflight.get("variant_id") or "").strip() or None
        overwrite_metadata = {
            "overwritten_at": utc_now(),
            "change_summary": normalized_change_summary,
            "overwrite_scope": normalized_scope,
            "compatibility_verdict": preflight.get("compatibility_verdict"),
            "risk_level": preflight.get("risk_level"),
            "allow_path_change": bool(allow_path_change),
            "allow_protocol_breaking_change": bool(allow_protocol_breaking_change),
            "superseded_baseline_ref": dict(current.get("confirmed_ref") or {}) or None,
            "superseded_metric_contract_json_rel_path": str(
                ((current.get("confirmed_ref") or {}).get("metric_contract_json_rel_path") or "")
            ).strip()
            or None,
            "added_metric_ids": list(preflight.get("added_metric_ids") or []),
            "removed_metric_ids": list(preflight.get("removed_metric_ids") or []),
            "direction_changed_metric_ids": list(preflight.get("direction_changed_metric_ids") or []),
            "path_changed": bool(preflight.get("path_changed")),
            "variant_changed": bool(preflight.get("variant_changed")),
            "protocol_breaking_reasons": list(preflight.get("protocol_breaking_reasons") or []),
        }
        effective_comment = (
            f"{comment}\n\nOverwrite baseline change summary: {normalized_change_summary}"
            if isinstance(comment, str) and comment.strip()
            else {"comment": comment, "change_summary": normalized_change_summary}
            if comment is not None
            else f"Overwrite baseline change summary: {normalized_change_summary}"
        )
        confirm_result = self.confirm_baseline(
            quest_root,
            baseline_path=str(resolved.get("relative_path") or baseline_path or ""),
            comment=effective_comment,
            baseline_id=target_baseline_id,
            variant_id=target_variant_id,
            summary=summary,
            baseline_kind=baseline_kind,
            metric_contract=metric_contract,
            metric_directions=metric_directions,
            metrics_summary=metrics_summary,
            primary_metric=primary_metric,
            auto_advance=auto_advance,
            strict_metric_contract=strict_metric_contract,
        )
        confirmed_ref = dict(confirm_result.get("confirmed_baseline_ref") or {})
        confirmed_ref["overwrite"] = overwrite_metadata
        quest_state = self.quest_service.update_baseline_state(
            quest_root,
            baseline_gate="confirmed",
            confirmed_baseline_ref=confirmed_ref,
            active_anchor=str((confirm_result.get("snapshot") or {}).get("active_anchor") or "baseline"),
        )
        if sync_requested_baseline_ref:
            self.quest_service.update_startup_context(
                quest_root,
                requested_baseline_ref={
                    "baseline_id": target_baseline_id,
                    "variant_id": target_variant_id,
                },
            )

        attachment_path = quest_root / "baselines" / "imported" / target_baseline_id / "attachment.yaml"
        attachment = read_yaml(attachment_path, {}) if attachment_path.exists() else {}
        if isinstance(attachment, dict):
            attachment["overwrite"] = overwrite_metadata
            write_yaml(attachment_path, attachment)

        metric_contract_json_path = str(confirm_result.get("metric_contract_json_path") or "").strip()
        if metric_contract_json_path:
            metric_contract_payload = read_json(Path(metric_contract_json_path), {})
            if isinstance(metric_contract_payload, dict):
                metric_contract_payload["overwrite"] = overwrite_metadata
                write_json(Path(metric_contract_json_path), metric_contract_payload)

        registry_entry = (
            dict(confirm_result.get("baseline_registry_entry") or {})
            if isinstance(confirm_result.get("baseline_registry_entry"), dict)
            else {}
        )
        if registry_entry:
            registry_entry["overwrite"] = overwrite_metadata
            registry_entry = self.baselines.publish(registry_entry)

        analysis_inventory = None
        if refresh_analysis_inventory:
            analysis_inventory = self._refresh_analysis_inventory_for_overwrite(
                quest_root,
                baseline_id=target_baseline_id,
                variant_id=target_variant_id,
                baseline_root_rel_path=str(confirmed_ref.get("baseline_root_rel_path") or "").strip() or None,
                source_mode=str(confirmed_ref.get("source_mode") or "").strip() or None,
                metrics_summary=normalize_metrics_summary(
                    metrics_summary
                    or (registry_entry or {}).get("metrics_summary")
                    or ((attachment.get("entry") or {}) if isinstance(attachment, dict) else {}).get("metrics_summary")
                ),
                supplementary_baselines=supplementary_baselines,
            )

        paper_inventory = self._write_paper_baseline_inventory(quest_root) if refresh_paper_inventory else None
        invalidated_cache_paths = self._invalidate_baseline_view_caches(quest_root)
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=self._build_overwrite_baseline_interaction_message(
                baseline_id=target_baseline_id,
                variant_id=target_variant_id,
                compatibility_verdict=str(preflight.get("compatibility_verdict") or "").strip() or None,
                change_summary=normalized_change_summary,
                added_metric_ids=list(preflight.get("added_metric_ids") or []),
                risk_level=str(preflight.get("risk_level") or "").strip() or None,
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "baseline_overwrite",
                    "baseline_id": target_baseline_id,
                    "variant_id": target_variant_id,
                    "compatibility_verdict": preflight.get("compatibility_verdict"),
                    "risk_level": preflight.get("risk_level"),
                }
            ],
        )

        confirm_result["confirmed_baseline_ref"] = quest_state.get("confirmed_baseline_ref")
        confirm_result["snapshot"] = self.quest_service.snapshot(self._quest_id(quest_root))
        confirm_result["baseline_registry_entry"] = registry_entry or confirm_result.get("baseline_registry_entry")
        confirm_result["attachment"] = attachment or confirm_result.get("attachment")
        confirm_result["analysis_baseline_inventory"] = analysis_inventory
        confirm_result["paper_baseline_inventory"] = paper_inventory
        confirm_result["invalidated_cache_paths"] = invalidated_cache_paths
        confirm_result["interaction"] = interaction
        confirm_result["overwrite"] = overwrite_metadata
        confirm_result["overwrite_action"] = "in_place_refresh"
        confirm_result["compatibility_verdict"] = preflight.get("compatibility_verdict")
        confirm_result["risk_level"] = preflight.get("risk_level")
        confirm_result["legacy_guidance"] = (
            "Baseline overwrite completed. The active baseline reference and downstream inventories were refreshed."
        )
        return confirm_result

    def _require_baseline_gate_open(self, quest_root: Path, *, action: str) -> None:
        quest_yaml = self.quest_service.read_quest_yaml(quest_root)
        if str(quest_yaml.get("baseline_gate") or "pending").strip().lower() in {"confirmed", "waived"}:
            return
        raise ValueError(
            f"`{action}` requires a confirmed or waived baseline gate. "
            "Use `artifact.confirm_baseline(...)` or `artifact.waive_baseline(...)` first."
        )

    @staticmethod
    def _artifact_record_identity(path: Path, payload: dict[str, Any], *, kind: str | None = None) -> str:
        normalized_kind = str(kind or payload.get("kind") or path.parent.name or "artifact").strip() or "artifact"
        branch_name = str(payload.get("branch") or "").strip()
        run_id = str(payload.get("run_id") or "").strip()
        if normalized_kind == "run" and run_id and branch_name:
            return f"{normalized_kind}:branch_run:{branch_name}:{run_id}"
        artifact_id = str(payload.get("artifact_id") or payload.get("id") or "").strip()
        if artifact_id:
            return f"{normalized_kind}:artifact:{artifact_id}"
        if normalized_kind == "run" and run_id:
            return f"{normalized_kind}:run:{run_id}"
        idea_id = str(payload.get("idea_id") or "").strip()
        if normalized_kind == "idea" and idea_id and branch_name:
            return f"{normalized_kind}:branch_idea:{branch_name}:{idea_id}"
        if normalized_kind == "idea" and idea_id:
            return f"{normalized_kind}:idea:{idea_id}"
        baseline_id = str(payload.get("baseline_id") or payload.get("entry_id") or "").strip()
        if baseline_id:
            return f"{normalized_kind}:baseline:{baseline_id}"
        interaction_id = str(payload.get("interaction_id") or "").strip()
        if interaction_id:
            return f"{normalized_kind}:interaction:{interaction_id}"
        return f"path:{path.resolve()}"

    @staticmethod
    def _artifact_record_rank(payload: dict[str, Any], *, path: Path, mtime_ns: int) -> tuple[str, str, int, int, str]:
        return (
            str(payload.get("updated_at") or ""),
            str(payload.get("created_at") or ""),
            len(payload),
            mtime_ns,
            str(path),
        )

    def _main_run_artifacts(self, quest_root: Path) -> list[dict[str, Any]]:
        records_by_identity: dict[str, dict[str, Any]] = {}
        for root in self.quest_service.workspace_roots(quest_root):
            artifacts_root = root / "artifacts" / "runs"
            if not artifacts_root.exists():
                continue
            for path in sorted(artifacts_root.glob("*.json")):
                if not path.is_file():
                    continue
                payload = read_json(path, {})
                if not isinstance(payload, dict) or not payload:
                    continue
                if str(payload.get("run_kind") or "").strip() != "main_experiment":
                    continue
                enriched = dict(payload)
                enriched["_artifact_path"] = str(path)
                try:
                    enriched["_artifact_mtime_ns"] = path.stat().st_mtime_ns
                except OSError:
                    enriched["_artifact_mtime_ns"] = 0
                identity = self._artifact_record_identity(path, enriched, kind="run")
                existing = records_by_identity.get(identity)
                if existing is None or self._artifact_record_rank(
                    enriched,
                    path=path,
                    mtime_ns=int(enriched.get("_artifact_mtime_ns") or 0),
                ) >= self._artifact_record_rank(
                    existing,
                    path=Path(str(existing.get("_artifact_path") or path)),
                    mtime_ns=int(existing.get("_artifact_mtime_ns") or 0),
                ):
                    records_by_identity[identity] = enriched
        records = list(records_by_identity.values())
        records.sort(
            key=lambda item: (
                str(item.get("updated_at") or item.get("created_at") or ""),
                int(item.get("_artifact_mtime_ns") or 0),
                str(item.get("_artifact_path") or ""),
            )
        )
        return records

    def _idea_artifacts(self, quest_root: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in self.quest_service._collect_artifacts(quest_root):
            payload = dict(item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}
            if not payload:
                continue
            if str(payload.get("kind") or "").strip() != "idea":
                continue
            enriched = dict(payload)
            artifact_path = str(item.get("path") or "").strip()
            enriched["_artifact_path"] = artifact_path
            try:
                enriched["_artifact_mtime_ns"] = Path(artifact_path).stat().st_mtime_ns if artifact_path else 0
            except OSError:
                enriched["_artifact_mtime_ns"] = 0
            records.append(enriched)
        records.sort(
            key=lambda item: (
                str(item.get("updated_at") or item.get("created_at") or ""),
                int(item.get("_artifact_mtime_ns") or 0),
                str(item.get("_artifact_path") or ""),
            )
        )
        return records

    @staticmethod
    def _semantic_stage_fingerprint(snapshot: dict[str, Any]) -> str:
        paper_health = (
            dict(snapshot.get("paper_contract_health") or {})
            if isinstance(snapshot.get("paper_contract_health"), dict)
            else {}
        )
        payload = {
            "active_anchor": str(snapshot.get("active_anchor") or "").strip() or None,
            "active_run_id": str(snapshot.get("active_run_id") or "").strip() or None,
            "active_analysis_campaign_id": str(snapshot.get("active_analysis_campaign_id") or "").strip() or None,
            "next_pending_slice_id": str(snapshot.get("next_pending_slice_id") or "").strip() or None,
            "current_workspace_branch": str(snapshot.get("current_workspace_branch") or "").strip() or None,
            "continuation_policy": str(snapshot.get("continuation_policy") or "").strip() or None,
            "paper": {
                "closure_state": str(paper_health.get("closure_state") or "").strip() or None,
                "delivery_state": str(paper_health.get("delivery_state") or "").strip() or None,
                "blocking_reasons": list(paper_health.get("blocking_reasons") or []),
                "recommended_next_stage": str(paper_health.get("recommended_next_stage") or "").strip() or None,
                "recommended_action": str(paper_health.get("recommended_action") or "").strip() or None,
                "writing_ready": bool(paper_health.get("writing_ready")),
                "finalize_ready": bool(paper_health.get("finalize_ready")),
                "keep_bundle_fixed_by_default": bool(paper_health.get("keep_bundle_fixed_by_default")),
            },
        }
        return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _semantic_record_key(self, quest_root: Path, payload: dict[str, Any], *, workspace_root: Path | None = None) -> str | None:
        explicit = str(payload.get("semantic_key") or "").strip()
        if explicit:
            return explicit
        kind = str(payload.get("kind") or "").strip()
        if kind not in {"decision", "report"}:
            return None
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        fingerprint = self._semantic_stage_fingerprint(snapshot)
        stage = str(payload.get("stage") or payload.get("anchor") or snapshot.get("active_anchor") or "").strip() or "unknown"
        if kind == "decision":
            action = str(payload.get("action") or "").strip() or "none"
            verdict = str(payload.get("verdict") or "").strip() or "none"
            return f"decision:{stage}:{action}:{verdict}:{fingerprint}"
        report_type = str(payload.get("report_type") or payload.get("flow_type") or "").strip() or "report"
        protocol_step = str(payload.get("protocol_step") or "").strip() or "none"
        return f"report:{stage}:{report_type}:{protocol_step}:{fingerprint}"

    def _latest_semantically_equivalent_artifact(
        self,
        quest_root: Path,
        *,
        kind: str,
        semantic_key: str,
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for item in self.quest_service._collect_artifacts(quest_root):
            payload = dict(item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}
            if not payload or str(payload.get("kind") or "").strip() != kind:
                continue
            if str(payload.get("semantic_key") or "").strip() != semantic_key:
                continue
            candidates.append(
                {
                    "path": str(item.get("path") or "").strip() or None,
                    "payload": payload,
                }
            )
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                str(((item.get("payload") or {}).get("updated_at") or "")),
                str(((item.get("payload") or {}).get("created_at") or "")),
                str(item.get("path") or ""),
            )
        )
        return candidates[-1]

    def _idea_candidate_artifacts(self, quest_root: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for record in self._idea_artifacts(quest_root):
            details = dict(record.get("details") or {}) if isinstance(record.get("details"), dict) else {}
            protocol_step = str(record.get("protocol_step") or "").strip().lower()
            submission_mode = str(
                details.get("submission_mode") or record.get("submission_mode") or ""
            ).strip().lower()
            if protocol_step != "candidate" and submission_mode != "candidate":
                continue
            paths = dict(record.get("paths") or {}) if isinstance(record.get("paths"), dict) else {}
            records.append(
                {
                    "idea_id": str(record.get("idea_id") or "").strip() or None,
                    "title": str(details.get("title") or "").strip() or None,
                    "problem": str(details.get("problem") or "").strip() or None,
                    "hypothesis": str(details.get("hypothesis") or "").strip() or None,
                    "mechanism": str(details.get("mechanism") or "").strip() or None,
                    "method_brief": str(details.get("method_brief") or "").strip() or None,
                    "selection_scores": self._normalize_selection_scores(details.get("selection_scores")),
                    "mechanism_family": str(details.get("mechanism_family") or "").strip() or None,
                    "change_layer": str(details.get("change_layer") or "").strip() or None,
                    "source_lens": str(details.get("source_lens") or "").strip() or None,
                    "expected_gain": str(details.get("expected_gain") or "").strip() or None,
                    "next_target": str(details.get("next_target") or record.get("next_target") or "").strip() or None,
                    "lineage_intent": str(record.get("lineage_intent") or details.get("lineage_intent") or "").strip() or None,
                    "parent_branch": str(record.get("parent_branch") or details.get("parent_branch") or "").strip() or None,
                    "foundation_ref": record.get("foundation_ref") or details.get("foundation_ref"),
                    "foundation_reason": str(record.get("foundation_reason") or details.get("foundation_reason") or "").strip() or None,
                    "candidate_root": str(paths.get("candidate_root") or "").strip() or None,
                    "idea_md_path": str(paths.get("idea_md") or "").strip() or None,
                    "idea_draft_path": str(paths.get("idea_draft_md") or "").strip() or None,
                    "status": str(record.get("status") or "").strip() or None,
                    "updated_at": str(record.get("updated_at") or record.get("created_at") or "").strip() or None,
                }
            )
        records.sort(key=lambda item: str(item.get("updated_at") or ""))
        return records

    def _optimization_candidate_reports(self, quest_root: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in self.quest_service._collect_artifacts(quest_root):
            payload = dict(item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}
            if not payload:
                continue
            if str(payload.get("kind") or "").strip() != "report":
                continue
            report_type = str(payload.get("report_type") or "").strip().lower()
            if report_type != "optimization_candidate":
                continue
            details = dict(payload.get("details") or {}) if isinstance(payload.get("details"), dict) else {}
            artifact_path = str(item.get("path") or "").strip() or None
            records.append(
                {
                    "artifact_id": str(payload.get("artifact_id") or payload.get("id") or "").strip() or None,
                    "candidate_id": str(payload.get("candidate_id") or details.get("candidate_id") or "").strip() or None,
                    "parent_candidate_id": str(payload.get("parent_candidate_id") or details.get("parent_candidate_id") or "").strip() or None,
                    "idea_id": str(payload.get("idea_id") or details.get("idea_id") or "").strip() or None,
                    "branch": str(payload.get("branch") or details.get("branch") or "").strip() or None,
                    "strategy": str(payload.get("strategy") or details.get("strategy") or "").strip() or None,
                    "status": str(payload.get("status") or details.get("status") or "").strip() or None,
                    "mechanism_family": str(payload.get("mechanism_family") or details.get("mechanism_family") or "").strip() or None,
                    "change_layer": str(payload.get("change_layer") or details.get("change_layer") or "").strip() or None,
                    "source_lens": str(payload.get("source_lens") or details.get("source_lens") or "").strip() or None,
                    "summary": str(payload.get("summary") or "").strip() or None,
                    "change_plan": str(payload.get("change_plan") or details.get("change_plan") or "").strip() or None,
                    "expected_gain": str(payload.get("expected_gain") or details.get("expected_gain") or "").strip() or None,
                    "linked_run_id": str(payload.get("linked_run_id") or details.get("linked_run_id") or "").strip() or None,
                    "failure_kind": str(payload.get("failure_kind") or details.get("failure_kind") or "").strip() or None,
                    "metrics_snapshot": payload.get("metrics_snapshot") or details.get("metrics_snapshot"),
                    "updated_at": str(payload.get("updated_at") or payload.get("created_at") or "").strip() or None,
                    "artifact_path": artifact_path,
                }
            )
        records.sort(key=lambda item: str(item.get("updated_at") or ""))
        return records

    @staticmethod
    def _frontier_branch_rank(branch: dict[str, Any]) -> tuple[int, int, float, str, str]:
        latest = dict(branch.get("latest_main_experiment") or {}) if isinstance(branch.get("latest_main_experiment"), dict) else {}
        recommended_route = str(latest.get("recommended_next_route") or "").strip().lower()
        route_score = {
            "iterate": 4,
            "analysis_or_write": 4,
            "continue": 3,
            "revise_idea": 1,
        }.get(recommended_route, 0)
        breakthrough = 1 if bool(latest.get("breakthrough")) else 0
        delta = to_number(latest.get("delta_vs_baseline"))
        delta_score = float(delta) if delta is not None else float("-inf")
        return (
            1 if bool(branch.get("has_main_result")) else 0,
            route_score + breakthrough,
            delta_score,
            str(branch.get("updated_at") or ""),
            str(branch.get("branch_name") or ""),
        )

    def _optimization_frontier_state(self, quest_root: Path) -> dict[str, Any]:
        return {
            "artifact_projection": self.quest_service._json_compatible_state(
                self.quest_service._path_state(self.quest_service._artifact_projection_path(quest_root))
            ),
            "research_state": self.quest_service._json_compatible_state(
                self.quest_service._path_state(self.quest_service._research_state_path(quest_root))
            ),
            "quest_yaml": self.quest_service._json_compatible_state(
                self.quest_service._path_state(self.quest_service._quest_yaml_path(quest_root))
            ),
        }

    def get_optimization_frontier(self, quest_root: Path) -> dict[str, Any]:
        cache_key = str(quest_root.resolve())
        state = self._optimization_frontier_state(quest_root)
        with self._optimization_frontier_cache_lock:
            cached = self._optimization_frontier_cache.get(cache_key)
            if cached and cached.get("state") == state:
                return copy.deepcopy(cached.get("payload") or {"ok": False})

        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        branches_payload = self.list_research_branches(quest_root)
        branches = [dict(item) for item in (branches_payload.get("branches") or []) if isinstance(item, dict)]
        candidate_briefs = self._idea_candidate_artifacts(quest_root)
        implementation_candidates = self._optimization_candidate_reports(quest_root)

        branches.sort(key=self._frontier_branch_rank, reverse=True)
        top_branches = branches[:3]

        active_candidate_statuses = {"proposed", "smoke_running", "smoke_passed", "promoted", "full_eval_running"}
        active_implementation_candidates = [
            item for item in implementation_candidates if str(item.get("status") or "").strip().lower() in active_candidate_statuses
        ]

        stagnant_branch_names: set[str] = set()
        branch_candidate_failures: dict[str, int] = {}
        for item in implementation_candidates:
            branch_name = str(item.get("branch") or "").strip()
            if not branch_name:
                continue
            status = str(item.get("status") or "").strip().lower()
            if status in {"failed", "smoke_failed", "archived"}:
                branch_candidate_failures[branch_name] = branch_candidate_failures.get(branch_name, 0) + 1
        for branch in branches:
            branch_name = str(branch.get("branch_name") or "").strip()
            latest = dict(branch.get("latest_main_experiment") or {}) if isinstance(branch.get("latest_main_experiment"), dict) else {}
            recommended_route = str(latest.get("recommended_next_route") or "").strip().lower()
            if branch_candidate_failures.get(branch_name, 0) >= 2:
                stagnant_branch_names.add(branch_name)
            elif recommended_route in {"continue", "revise_idea"} and bool(branch.get("has_main_result")):
                stagnant_branch_names.add(branch_name)
        stagnant_branches = [branch for branch in branches if str(branch.get("branch_name") or "") in stagnant_branch_names]

        successful_branches = [branch for branch in branches if bool(branch.get("has_main_result"))]
        fusion_candidates = [
            {
                "branch_name": str(branch.get("branch_name") or "").strip() or None,
                "idea_id": branch.get("idea_id"),
                "idea_title": branch.get("idea_title"),
                "latest_main_run_id": str((dict(branch.get("latest_main_experiment") or {}) if isinstance(branch.get("latest_main_experiment"), dict) else {}).get("run_id") or "").strip() or None,
                "strength_signal": {
                    "recommended_next_route": str((dict(branch.get("latest_main_experiment") or {}) if isinstance(branch.get("latest_main_experiment"), dict) else {}).get("recommended_next_route") or "").strip() or None,
                    "delta_vs_baseline": (dict(branch.get("latest_main_experiment") or {}) if isinstance(branch.get("latest_main_experiment"), dict) else {}).get("delta_vs_baseline"),
                    "breakthrough": (dict(branch.get("latest_main_experiment") or {}) if isinstance(branch.get("latest_main_experiment"), dict) else {}).get("breakthrough"),
                },
            }
            for branch in successful_branches[:3]
        ]

        if active_implementation_candidates:
            mode = "exploit"
            reason = "At least one implementation-level candidate is already active, so the frontier should stay focused on execution and result conversion."
        elif candidate_briefs and len(top_branches) <= 1:
            mode = "explore"
            reason = "Candidate briefs exist but the durable line set is still thin, so widening or ranking the brief pool is the best next move."
        elif len(fusion_candidates) >= 2 and stagnant_branches:
            mode = "fusion"
            reason = "Multiple result-bearing branches exist and at least one line is stagnating, so cross-line fusion is now justified."
        elif top_branches:
            mode = "exploit"
            reason = "A durable line already exists and no broader frontier condition dominates, so focus should stay on the strongest current line."
        else:
            mode = "stop"
            reason = "No durable optimization line or candidate pool is active, so there is no meaningful frontier to continue automatically."

        recommended_next_actions: list[str] = []
        if mode == "explore":
            recommended_next_actions.extend(
                [
                    "Create or refine candidate briefs before promoting new lines.",
                    "Rank the candidate brief pool and promote only the strongest 1 to 3 directions.",
                ]
            )
        elif mode == "fusion":
            recommended_next_actions.extend(
                [
                    "Compare the strongest result-bearing lines for complementary mechanisms.",
                    "Open a fusion candidate only if the line strengths are complementary rather than redundant.",
                ]
            )
        elif mode == "exploit":
            recommended_next_actions.extend(
                [
                    "Keep the active line focused and advance the most promising implementation candidates first.",
                    "Use smoke checks before promoting more candidates into full evaluation.",
                ]
            )
        else:
            recommended_next_actions.append("Record a stop or park decision before closing the optimization loop.")

        candidate_backlog = {
            "candidate_brief_count": len(candidate_briefs),
            "implementation_candidate_count": len(implementation_candidates),
            "active_implementation_candidate_count": len(active_implementation_candidates),
            "failed_implementation_candidate_count": sum(
                1 for item in implementation_candidates if str(item.get("status") or "").strip().lower() in {"failed", "smoke_failed", "archived"}
            ),
        }

        best_branch = top_branches[0] if top_branches else None
        best_run = (
            dict(best_branch.get("latest_main_experiment") or {})
            if isinstance((best_branch or {}).get("latest_main_experiment"), dict)
            else None
        )
        best_branch_name = str((best_branch or {}).get("branch_name") or "").strip() or None
        best_idea_id = str((best_branch or {}).get("idea_id") or "").strip() or None
        best_branch_recent_candidates = [
            {
                "candidate_id": str(item.get("candidate_id") or "").strip() or None,
                "strategy": str(item.get("strategy") or "").strip() or None,
                "status": str(item.get("status") or "").strip() or None,
                "mechanism_family": str(item.get("mechanism_family") or "").strip() or None,
                "change_layer": str(item.get("change_layer") or "").strip() or None,
                "source_lens": str(item.get("source_lens") or "").strip() or None,
                "change_plan": str(item.get("change_plan") or "").strip() or None,
                "failure_kind": str(item.get("failure_kind") or "").strip() or None,
                "linked_run_id": str(item.get("linked_run_id") or "").strip() or None,
                "updated_at": str(item.get("updated_at") or "").strip() or None,
            }
            for item in implementation_candidates
            if (
                (best_branch_name and str(item.get("branch") or "").strip() == best_branch_name)
                or (best_idea_id and str(item.get("idea_id") or "").strip() == best_idea_id)
            )
        ][-4:]

        payload = {
            "ok": True,
            "optimization_frontier": {
                "mode": mode,
                "frontier_reason": reason,
                "active_anchor": snapshot.get("active_anchor"),
                "best_branch": best_branch,
                "best_run": best_run,
                "top_branches": top_branches,
                "candidate_briefs": candidate_briefs,
                "implementation_candidates": implementation_candidates[-8:],
                "best_branch_recent_candidates": best_branch_recent_candidates,
                "candidate_backlog": candidate_backlog,
                "stagnant_branches": stagnant_branches,
                "fusion_candidates": fusion_candidates,
                "recommended_next_actions": recommended_next_actions,
            },
        }
        with self._optimization_frontier_cache_lock:
            self._optimization_frontier_cache[cache_key] = {
                "state": copy.deepcopy(state),
                "payload": copy.deepcopy(payload),
            }
        return payload

    @staticmethod
    def _format_branch_number(index: int) -> str:
        if index < 1000:
            return f"{index:03d}"
        return str(index)

    def _recorded_branch_numbers(self, quest_root: Path) -> tuple[dict[str, int], int]:
        recorded: dict[str, int] = {}
        max_index = 0
        for record in self._idea_artifacts(quest_root):
            branch_name = str(record.get("branch") or "").strip()
            if not branch_name:
                continue
            details = dict(record.get("details") or {}) if isinstance(record.get("details"), dict) else {}
            raw_branch_no = str(record.get("branch_no") or details.get("branch_no") or "").strip()
            if not raw_branch_no.isdigit():
                continue
            numeric_branch_no = int(raw_branch_no)
            previous = recorded.get(branch_name)
            if previous is None or numeric_branch_no < previous:
                recorded[branch_name] = numeric_branch_no
            if numeric_branch_no > max_index:
                max_index = numeric_branch_no
        return recorded, max_index

    def _next_branch_number(self, quest_root: Path) -> str:
        recorded_branch_numbers, max_recorded_index = self._recorded_branch_numbers(quest_root)
        if recorded_branch_numbers:
            return self._format_branch_number(max_recorded_index + 1)
        existing_branches = {
            str(record.get("branch") or "").strip()
            for record in self._idea_artifacts(quest_root)
            if str(record.get("branch") or "").strip()
        }
        return self._format_branch_number(len(existing_branches) + 1)

    def _branch_workspace_root(self, quest_root: Path, branch_name: str) -> Path | None:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            return None
        for root in self.quest_service.workspace_roots(quest_root):
            try:
                if current_branch(root) == normalized_branch:
                    return root
            except Exception:
                continue
        return None

    def _branch_activation_worktree_root(
        self,
        quest_root: Path,
        *,
        branch_name: str,
        idea_id: str | None = None,
        run_id: str | None = None,
    ) -> Path:
        normalized_branch = str(branch_name or "").strip()
        branch_kind = self._branch_kind_from_name(normalized_branch)
        normalized_idea_id = str(idea_id or "").strip() or None
        if branch_kind == "paper":
            normalized_run_id = str(run_id or "").strip() or None
            return canonical_worktree_root(
                quest_root,
                f"paper-{normalized_run_id or slugify(normalized_branch, 'paper')}",
            )
        if normalized_idea_id and branch_kind == "idea":
            return canonical_worktree_root(quest_root, f"idea-{normalized_idea_id}")
        normalized_run_id = str(run_id or "").strip() or None
        if normalized_run_id and branch_kind == "run":
            return canonical_worktree_root(quest_root, normalized_run_id)
        return canonical_worktree_root(quest_root, f"branch-{slugify(normalized_branch, 'branch')}")

    @staticmethod
    def _resolve_activate_branch_anchor(
        *,
        anchor: str | None,
        has_idea: bool,
        has_main_result: bool,
    ) -> str:
        normalized_anchor = str(anchor or "auto").strip().lower() or "auto"
        if normalized_anchor == "auto":
            if has_main_result:
                return "decision"
            if has_idea:
                return "experiment"
            return "idea"
        aliases = {
            "analysis": "analysis-campaign",
        }
        resolved_anchor = aliases.get(normalized_anchor, normalized_anchor)
        allowed = {
            "scout",
            "baseline",
            "idea",
            "experiment",
            "analysis-campaign",
            "write",
            "finalize",
            "decision",
        }
        if resolved_anchor not in allowed:
            allowed_text = ", ".join(sorted(allowed | {"auto"}))
            raise ValueError(f"Unsupported activate_branch anchor `{anchor}`. Allowed values: {allowed_text}.")
        return resolved_anchor

    def _resolve_branch_activation_target(
        self,
        quest_root: Path,
        *,
        branch: str | None = None,
        idea_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        provided = sum(
            1
            for value in (
                str(branch or "").strip(),
                str(idea_id or "").strip(),
                str(run_id or "").strip(),
            )
            if value
        )
        if provided != 1:
            raise ValueError("activate_branch requires exactly one of `branch`, `idea_id`, or `run_id`.")

        latest_idea: dict[str, Any] | None = None
        latest_run: dict[str, Any] | None = None
        normalized_branch = str(branch or "").strip()
        normalized_idea_id = str(idea_id or "").strip()
        normalized_run_id = str(run_id or "").strip()

        if normalized_idea_id:
            candidates = [
                item for item in self._idea_artifacts(quest_root) if str(item.get("idea_id") or "").strip() == normalized_idea_id
            ]
            if not candidates:
                raise FileNotFoundError(f"Unknown idea `{normalized_idea_id}`.")
            latest_idea = candidates[-1]
            normalized_branch = str(latest_idea.get("branch") or "").strip()
        elif normalized_run_id:
            candidates = [
                item for item in self._main_run_artifacts(quest_root) if str(item.get("run_id") or "").strip() == normalized_run_id
            ]
            if not candidates:
                raise FileNotFoundError(f"Unknown main run `{normalized_run_id}`.")
            latest_run = candidates[-1]
            normalized_branch = str(latest_run.get("branch") or "").strip()
        else:
            if normalized_branch.startswith("analysis/"):
                raise ValueError(
                    "activate_branch only supports durable idea/main branches. "
                    "Analysis slice branches remain managed by analysis campaigns."
                )
            if not branch_exists(quest_root, normalized_branch):
                raise FileNotFoundError(f"Unknown branch `{normalized_branch}`.")

        if not normalized_branch:
            raise ValueError("Unable to resolve a durable branch to activate.")

        prepare_record = self._latest_prepare_branch_record(quest_root, normalized_branch)
        prepare_details = dict(prepare_record.get("details") or {}) if isinstance(prepare_record.get("details"), dict) else {}
        recorded_parent_branch = (
            str(prepare_record.get("parent_branch") or prepare_details.get("parent_branch") or "").strip() or None
        )
        recorded_branch_kind = (
            str(prepare_record.get("branch_kind") or prepare_details.get("branch_kind") or "").strip().lower()
            or self._branch_kind_from_name(normalized_branch)
        )

        latest_idea = latest_idea or self._latest_idea_for_branch(quest_root, normalized_branch)
        latest_run = latest_run or self._latest_main_run_for_branch(quest_root, normalized_branch)
        if not latest_run and recorded_branch_kind == "idea":
            latest_run = self._latest_child_main_run_for_branch(quest_root, normalized_branch)
        if not latest_run and recorded_parent_branch:
            latest_run = self._latest_main_run_for_branch(quest_root, recorded_parent_branch)
        resolved_idea_id = (
            normalized_idea_id
            or str((latest_run or {}).get("idea_id") or "").strip()
            or str((latest_idea or {}).get("idea_id") or "").strip()
            or str(prepare_record.get("idea_id") or "").strip()
            or self._latest_branch_idea_id(quest_root, normalized_branch)
            or None
        )
        idea_paths = dict((latest_idea or {}).get("paths") or {}) if isinstance((latest_idea or {}).get("paths"), dict) else {}
        recorded_root = (
            str((latest_idea or {}).get("worktree_root") or "").strip()
            or str((latest_run or {}).get("worktree_root") or "").strip()
            or str(prepare_record.get("worktree_root") or "").strip()
            or None
        )
        return {
            "branch": normalized_branch,
            "idea_id": resolved_idea_id,
            "run_id": normalized_run_id or str((latest_run or {}).get("run_id") or "").strip() or None,
            "has_main_result": bool((latest_run or {}).get("run_id")),
            "latest_idea": latest_idea,
            "latest_main_run": latest_run,
            "branch_kind": recorded_branch_kind,
            "parent_branch": recorded_parent_branch,
            "recorded_worktree_root": recorded_root,
            "idea_md_path": str(idea_paths.get("idea_md") or "").strip() or None,
            "idea_draft_path": str(idea_paths.get("idea_draft_md") or "").strip() or None,
            "suggested_worktree_root": self._branch_activation_worktree_root(
                quest_root,
                branch_name=normalized_branch,
                idea_id=resolved_idea_id,
                run_id=(
                    normalized_run_id
                    or str(prepare_record.get("run_id") or "").strip()
                    or str((latest_run or {}).get("run_id") or "").strip()
                    or None
                ),
            ),
        }

    def _normalize_foundation_ref(self, foundation_ref: dict[str, Any] | str | None) -> dict[str, Any]:
        if foundation_ref is None:
            return {"kind": "current_head", "ref": None}
        if isinstance(foundation_ref, str):
            normalized = foundation_ref.strip()
            if not normalized:
                return {"kind": "current_head", "ref": None}
            return {"kind": "branch", "ref": normalized}
        if not isinstance(foundation_ref, dict):
            return {"kind": "current_head", "ref": None}
        normalized_kind = str(foundation_ref.get("kind") or "current_head").strip().lower() or "current_head"
        normalized_ref = (
            foundation_ref.get("ref")
            or foundation_ref.get("branch")
            or foundation_ref.get("idea_id")
            or foundation_ref.get("run_id")
            or foundation_ref.get("baseline_id")
        )
        return {
            "kind": normalized_kind,
            "ref": str(normalized_ref).strip() if normalized_ref is not None and str(normalized_ref).strip() else None,
        }

    def _resolve_idea_foundation(
        self,
        quest_root: Path,
        *,
        state: dict[str, Any],
        foundation_ref: dict[str, Any] | str | None,
    ) -> dict[str, Any]:
        normalized = self._normalize_foundation_ref(foundation_ref)
        kind = str(normalized.get("kind") or "current_head").strip().lower() or "current_head"
        ref = str(normalized.get("ref") or "").strip() or None

        if kind in {"current_head", "current_branch", "head"}:
            foundation_branch = (
                str(state.get("research_head_branch") or "").strip()
                or str(state.get("current_workspace_branch") or "").strip()
            )
            foundation_workspace_root = None
            preferred_root = str(state.get("research_head_worktree_root") or "").strip()
            if preferred_root:
                candidate = Path(preferred_root)
                if candidate.exists():
                    foundation_workspace_root = candidate
            if foundation_workspace_root is None:
                foundation_workspace_root = self._workspace_root_for(quest_root)
            if not foundation_branch:
                foundation_branch = current_branch(foundation_workspace_root)
            return {
                "kind": "current_head",
                "ref": ref or foundation_branch,
                "branch": foundation_branch,
                "worktree_root": str(foundation_workspace_root),
                "label": f"Current head `{foundation_branch}`",
            }

        if kind == "baseline":
            snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
            baseline_id = ref or str(snapshot.get("active_baseline_id") or "").strip() or "baseline"
            foundation_branch = current_branch(quest_root)
            return {
                "kind": "baseline",
                "ref": baseline_id,
                "branch": foundation_branch,
                "worktree_root": str(quest_root),
                "baseline_id": baseline_id,
                "label": f"Baseline foundation `{baseline_id}` on `{foundation_branch}`",
            }

        if kind == "idea":
            idea_id = ref
            if not idea_id:
                raise ValueError("foundation_ref(kind='idea') requires `ref` or `idea_id`.")
            candidates = [item for item in self._idea_artifacts(quest_root) if str(item.get("idea_id") or "").strip() == idea_id]
            if not candidates:
                raise FileNotFoundError(f"Unknown idea foundation `{idea_id}`.")
            payload = candidates[-1]
            foundation_branch = str(payload.get("branch") or "").strip()
            foundation_workspace_root = (
                Path(str(payload.get("worktree_root") or "").strip())
                if str(payload.get("worktree_root") or "").strip()
                else self._branch_workspace_root(quest_root, foundation_branch)
            )
            return {
                "kind": "idea",
                "ref": idea_id,
                "branch": foundation_branch,
                "worktree_root": str(foundation_workspace_root) if foundation_workspace_root else None,
                "idea_id": idea_id,
                "label": f"Idea `{idea_id}` on `{foundation_branch}`",
            }

        if kind == "run":
            run_id = ref
            if not run_id:
                raise ValueError("foundation_ref(kind='run') requires `ref` or `run_id`.")
            candidates = [item for item in self._main_run_artifacts(quest_root) if str(item.get("run_id") or "").strip() == run_id]
            if not candidates:
                raise FileNotFoundError(f"Unknown run foundation `{run_id}`.")
            payload = candidates[-1]
            foundation_branch = str(payload.get("branch") or "").strip()
            foundation_workspace_root = (
                Path(str(payload.get("worktree_root") or "").strip())
                if str(payload.get("worktree_root") or "").strip()
                else self._branch_workspace_root(quest_root, foundation_branch)
            )
            return {
                "kind": "run",
                "ref": run_id,
                "branch": foundation_branch,
                "worktree_root": str(foundation_workspace_root) if foundation_workspace_root else None,
                "run_id": run_id,
                "label": f"Run `{run_id}` on `{foundation_branch}`",
            }

        if kind == "branch":
            branch_name = ref
            if not branch_name:
                raise ValueError("foundation_ref(kind='branch') requires `ref` or `branch`.")
            foundation_workspace_root = self._branch_workspace_root(quest_root, branch_name)
            return {
                "kind": "branch",
                "ref": branch_name,
                "branch": branch_name,
                "worktree_root": str(foundation_workspace_root) if foundation_workspace_root else None,
                "label": f"Branch `{branch_name}`",
            }

        raise ValueError(f"Unsupported idea foundation kind `{kind}`.")

    @staticmethod
    def _normalize_lineage_intent(lineage_intent: str | None) -> str | None:
        raw = str(lineage_intent or "").strip().lower()
        if not raw:
            return None
        aliases = {
            "continue": "continue_line",
            "continue-line": "continue_line",
            "child": "continue_line",
            "branch": "branch_alternative",
            "branch-alt": "branch_alternative",
            "branch-alternative": "branch_alternative",
            "alternative": "branch_alternative",
            "sibling": "branch_alternative",
        }
        normalized = aliases.get(raw, raw)
        if normalized not in {"continue_line", "branch_alternative"}:
            raise ValueError(
                "`lineage_intent` must be one of: continue_line, branch_alternative."
            )
        return normalized

    @staticmethod
    def _artifact_details(record: dict[str, Any]) -> dict[str, Any]:
        return dict(record.get("details") or {}) if isinstance(record.get("details"), dict) else {}

    def _latest_main_run_for_branch(self, quest_root: Path, branch_name: str) -> dict[str, Any] | None:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            return None
        candidates = [
            item
            for item in self._main_run_artifacts(quest_root)
            if str(item.get("branch") or "").strip() == normalized_branch
        ]
        return candidates[-1] if candidates else None

    def _latest_child_main_run_for_branch(self, quest_root: Path, branch_name: str) -> dict[str, Any] | None:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            return None
        candidates = [
            item
            for item in self._main_run_artifacts(quest_root)
            if str(item.get("parent_branch") or "").strip() == normalized_branch
        ]
        return candidates[-1] if candidates else None

    def _latest_idea_for_branch(self, quest_root: Path, branch_name: str) -> dict[str, Any] | None:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            return None
        candidates = [
            item
            for item in self._idea_artifacts(quest_root)
            if str(item.get("branch") or "").strip() == normalized_branch
        ]
        return candidates[-1] if candidates else None

    def _latest_branch_idea_id(self, quest_root: Path, branch_name: str) -> str | None:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            return None
        latest_idea = self._latest_idea_for_branch(quest_root, normalized_branch)
        if isinstance(latest_idea, dict):
            candidate = str(latest_idea.get("idea_id") or "").strip()
            if candidate:
                return candidate
        latest_main_run = self._latest_main_run_for_branch(quest_root, normalized_branch)
        if isinstance(latest_main_run, dict):
            candidate = str(latest_main_run.get("idea_id") or "").strip()
            if candidate:
                return candidate
        latest_match: tuple[str, int, str] | None = None
        latest_candidate: str | None = None
        for item in self.quest_service._collect_artifacts(quest_root):
            payload = dict(item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}
            if not payload:
                continue
            if str(payload.get("branch") or "").strip() != normalized_branch:
                continue
            candidate = str(payload.get("idea_id") or "").strip()
            if not candidate:
                continue
            artifact_path = str(item.get("path") or "")
            try:
                artifact_mtime_ns = Path(artifact_path).stat().st_mtime_ns if artifact_path else 0
            except OSError:
                artifact_mtime_ns = 0
            sort_key = (
                str(payload.get("updated_at") or payload.get("created_at") or ""),
                artifact_mtime_ns,
                artifact_path,
            )
            if latest_match is None or sort_key > latest_match:
                latest_match = sort_key
                latest_candidate = candidate
        if latest_match is not None and latest_candidate:
            return latest_candidate
        return None

    def _resolve_analysis_parent_context(
        self,
        quest_root: Path,
        *,
        state: dict[str, Any],
    ) -> tuple[str, Path, str | None]:
        current_root_raw = str(state.get("current_workspace_root") or "").strip()
        head_root_raw = str(state.get("research_head_worktree_root") or "").strip()
        paper_parent_root_raw = str(state.get("paper_parent_worktree_root") or "").strip()
        current_branch_raw = str(state.get("current_workspace_branch") or "").strip()
        research_head_branch_raw = str(state.get("research_head_branch") or "").strip()
        paper_parent_branch_raw = str(state.get("paper_parent_branch") or "").strip()
        branch_mode = self._active_workspace_branch_mode(state, branch_name=current_branch_raw)
        prefer_paper_parent = branch_mode == "paper" or self._branch_kind_from_name(current_branch_raw) == "paper"
        parent_worktree_root: Path | None = None
        root_candidates = (
            (paper_parent_root_raw, head_root_raw, current_root_raw)
            if prefer_paper_parent
            else (current_root_raw, head_root_raw, paper_parent_root_raw)
        )
        for raw in root_candidates:
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.exists():
                parent_worktree_root = candidate
                break
        if parent_worktree_root is None:
            parent_worktree_root = self._workspace_root_for(quest_root)

        parent_branch = (
            (
                paper_parent_branch_raw
                or research_head_branch_raw
                or current_branch_raw
                or current_branch(parent_worktree_root)
                or current_branch(self._workspace_root_for(quest_root))
            )
            if prefer_paper_parent
            else (
                current_branch_raw
                or research_head_branch_raw
                or paper_parent_branch_raw
                or current_branch(parent_worktree_root)
                or current_branch(self._workspace_root_for(quest_root))
            )
        )
        parent_branch = str(parent_branch or "").strip()
        if not parent_branch:
            raise ValueError("Unable to resolve a parent branch for the analysis campaign.")

        if self._branch_kind_from_name(parent_branch) == "idea":
            latest_child_run = self._latest_child_main_run_for_branch(quest_root, parent_branch)
            if isinstance(latest_child_run, dict) and str(latest_child_run.get("branch") or "").strip():
                parent_branch = str(latest_child_run.get("branch") or "").strip()
                recorded_worktree_root = str(latest_child_run.get("worktree_root") or "").strip()
                if recorded_worktree_root:
                    candidate = Path(recorded_worktree_root)
                    if candidate.exists():
                        parent_worktree_root = candidate

        idea_id = self._latest_branch_idea_id(quest_root, parent_branch) or str(state.get("active_idea_id") or "").strip() or None
        return parent_branch, parent_worktree_root, idea_id

    def _idea_parent_branch(self, record: dict[str, Any] | None) -> str | None:
        if not isinstance(record, dict) or not record:
            return None
        details = self._artifact_details(record)
        parent_branch = str(record.get("parent_branch") or details.get("parent_branch") or "").strip()
        if parent_branch:
            return parent_branch
        foundation_ref = record.get("foundation_ref") or details.get("foundation_ref") or {}
        if isinstance(foundation_ref, dict):
            foundation_branch = str(foundation_ref.get("branch") or "").strip()
            if foundation_branch:
                return foundation_branch
        return None

    def _default_idea_foundation_for_branch(
        self,
        quest_root: Path,
        *,
        state: dict[str, Any],
        branch_name: str,
    ) -> dict[str, Any]:
        normalized_branch = str(branch_name or "").strip()
        if not normalized_branch:
            raise ValueError("A branch foundation requires a branch name.")
        latest_run = self._latest_main_run_for_branch(quest_root, normalized_branch)
        if isinstance(latest_run, dict) and str(latest_run.get("run_id") or "").strip():
            return self._resolve_idea_foundation(
                quest_root,
                state=state,
                foundation_ref={"kind": "run", "ref": str(latest_run.get("run_id") or "").strip()},
            )
        latest_idea = self._latest_idea_for_branch(quest_root, normalized_branch)
        if isinstance(latest_idea, dict) and str(latest_idea.get("idea_id") or "").strip():
            return self._resolve_idea_foundation(
                quest_root,
                state=state,
                foundation_ref={"kind": "idea", "ref": str(latest_idea.get("idea_id") or "").strip()},
            )
        current_workspace_branch = str(state.get("current_workspace_branch") or "").strip()
        research_head_branch = str(state.get("research_head_branch") or "").strip()
        active_branch = (
            current_workspace_branch
            or research_head_branch
            or current_branch(self._workspace_root_for(quest_root))
        )
        if normalized_branch and active_branch and normalized_branch == active_branch:
            return self._resolve_idea_foundation(
                quest_root,
                state=state,
                foundation_ref=(
                    {"kind": "branch", "ref": normalized_branch}
                    if current_workspace_branch and research_head_branch and current_workspace_branch != research_head_branch
                    else None
                ),
            )
        return self._resolve_idea_foundation(
            quest_root,
            state=state,
            foundation_ref={"kind": "branch", "ref": normalized_branch},
        )

    def _infer_lineage_intent_from_parent_branch(
        self,
        *,
        active_branch: str,
        active_parent_branch: str | None,
        parent_branch: str,
    ) -> str | None:
        normalized_parent = str(parent_branch or "").strip()
        normalized_active = str(active_branch or "").strip()
        normalized_active_parent = str(active_parent_branch or "").strip()
        if normalized_parent and normalized_active and normalized_parent == normalized_active:
            return "continue_line"
        if (
            normalized_parent
            and normalized_active_parent
            and normalized_parent == normalized_active_parent
            and normalized_parent != normalized_active
        ):
            return "branch_alternative"
        return None

    def _infer_default_idea_lineage(
        self,
        quest_root: Path,
        *,
        state: dict[str, Any],
        lineage_intent: str | None,
    ) -> tuple[str, str, dict[str, Any]]:
        normalized_intent = self._normalize_lineage_intent(lineage_intent) or "continue_line"
        active_branch = (
            str(state.get("current_workspace_branch") or "").strip()
            or str(state.get("research_head_branch") or "").strip()
        )
        if not active_branch:
            active_branch = current_branch(self._workspace_root_for(quest_root))
        active_record = self._latest_idea_for_branch(quest_root, active_branch)
        active_parent_branch = self._idea_parent_branch(active_record)

        if normalized_intent == "branch_alternative":
            parent_branch = active_parent_branch or active_branch
        else:
            parent_branch = active_branch
        if not parent_branch:
            raise ValueError("Unable to infer a parent branch for the next idea.")
        effective_state = dict(state)
        if not str(effective_state.get("research_head_branch") or "").strip():
            effective_state["research_head_branch"] = active_branch
        if not str(effective_state.get("current_workspace_branch") or "").strip():
            effective_state["current_workspace_branch"] = active_branch
        foundation = self._default_idea_foundation_for_branch(
            quest_root,
            state=effective_state,
            branch_name=parent_branch,
        )
        return normalized_intent, parent_branch, foundation

    def list_research_branches(self, quest_root: Path) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        active_head_branch = str(state.get("research_head_branch") or "").strip() or None
        active_workspace_branch = str(state.get("current_workspace_branch") or "").strip() or None
        idea_records = self._idea_artifacts(quest_root)
        main_runs = self._main_run_artifacts(quest_root)

        grouped: dict[str, dict[str, Any]] = {}

        def ensure_branch_entry(branch_name: str) -> dict[str, Any]:
            entry = grouped.get(branch_name)
            if entry is not None:
                return entry
            workspace_root = self._branch_workspace_root(quest_root, branch_name)
            entry = {
                "branch_name": branch_name,
                "worktree_root": str(workspace_root) if workspace_root else None,
                "ideas": [],
                "experiments": [],
                "first_seen_at": None,
            }
            grouped[branch_name] = entry
            return entry

        for record in idea_records:
            branch_name = str(record.get("branch") or "").strip()
            if not branch_name:
                continue
            entry = ensure_branch_entry(branch_name)
            created_at = str(record.get("created_at") or record.get("updated_at") or "").strip() or None
            if entry["first_seen_at"] is None or (created_at and str(entry["first_seen_at"]) > created_at):
                entry["first_seen_at"] = created_at
            details = dict(record.get("details") or {}) if isinstance(record.get("details"), dict) else {}
            paths = dict(record.get("paths") or {}) if isinstance(record.get("paths"), dict) else {}
            entry["ideas"].append(
                {
                    "idea_id": record.get("idea_id"),
                    "title": details.get("title"),
                    "problem": details.get("problem"),
                    "method_brief": details.get("method_brief"),
                    "selection_scores": self._normalize_selection_scores(details.get("selection_scores")),
                    "mechanism_family": details.get("mechanism_family"),
                    "change_layer": details.get("change_layer"),
                    "source_lens": details.get("source_lens"),
                    "next_target": details.get("next_target") or record.get("next_target"),
                    "lineage_intent": record.get("lineage_intent") or details.get("lineage_intent"),
                    "protocol_step": record.get("protocol_step"),
                    "parent_branch": record.get("parent_branch") or details.get("parent_branch"),
                    "foundation_ref": record.get("foundation_ref") or details.get("foundation_ref"),
                    "foundation_reason": record.get("foundation_reason") or details.get("foundation_reason"),
                    "idea_md_path": paths.get("idea_md"),
                    "idea_draft_path": paths.get("idea_draft_md") or details.get("idea_draft_path"),
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                    "order": len(entry["ideas"]),
                }
            )

        for record in main_runs:
            branch_name = str(record.get("branch") or "").strip()
            if not branch_name:
                continue
            entry = ensure_branch_entry(branch_name)
            created_at = str(record.get("created_at") or record.get("updated_at") or "").strip() or None
            if entry["first_seen_at"] is None or (created_at and str(entry["first_seen_at"]) > created_at):
                entry["first_seen_at"] = created_at
            details = dict(record.get("details") or {}) if isinstance(record.get("details"), dict) else {}
            delivery_policy = dict(record.get("delivery_policy") or {}) if isinstance(record.get("delivery_policy"), dict) else {}
            entry["experiments"].append(
                {
                    "run_id": record.get("run_id"),
                    "summary": record.get("summary"),
                    "verdict": record.get("verdict"),
                    "status": record.get("status"),
                    "idea_id": record.get("idea_id"),
                    "parent_branch": record.get("parent_branch"),
                    "primary_metric_id": details.get("primary_metric_id"),
                    "primary_value": details.get("primary_value"),
                    "delta_vs_baseline": details.get("delta_vs_baseline"),
                    "breakthrough": details.get("breakthrough"),
                    "breakthrough_level": details.get("breakthrough_level"),
                    "recommended_next_route": delivery_policy.get("recommended_next_route"),
                    "updated_at": record.get("updated_at"),
                }
            )

        if active_head_branch:
            ensure_branch_entry(active_head_branch)
        if active_workspace_branch:
            ensure_branch_entry(active_workspace_branch)

        ordered_branches = sorted(
            grouped.values(),
            key=lambda item: (
                str(item.get("first_seen_at") or ""),
                str(item.get("branch_name") or ""),
            ),
        )

        recorded_branch_numbers, max_recorded_index = self._recorded_branch_numbers(quest_root)
        next_fallback_branch_index = max_recorded_index
        branches: list[dict[str, Any]] = []
        for index, item in enumerate(ordered_branches, start=1):
            branch_name = str(item.get("branch_name") or "").strip()
            ideas = list(item.get("ideas") or [])
            experiments = list(item.get("experiments") or [])
            latest_idea = (
                max(
                    ideas,
                    key=lambda entry: (
                        str(entry.get("updated_at") or entry.get("created_at") or ""),
                        1 if str(entry.get("protocol_step") or "").strip() == "revise" else 0,
                        int(entry.get("order") or 0),
                    ),
                )
                if ideas
                else {}
            )
            latest_experiment = experiments[-1] if experiments else None
            latest_foundation = (
                dict(latest_idea.get("foundation_ref") or {})
                if isinstance(latest_idea.get("foundation_ref"), dict)
                else {}
            )
            parent_branch = str(latest_idea.get("parent_branch") or "").strip() or None
            experiment_parent_branch = (
                str((latest_experiment or {}).get("parent_branch") or "").strip()
                if isinstance(latest_experiment, dict)
                else None
            ) or None
            foundation_branch = (
                str(latest_foundation.get("branch") or latest_foundation.get("ref") or "").strip() or None
            )
            resolved_parent_branch = parent_branch or experiment_parent_branch or foundation_branch
            has_main_result = isinstance(latest_experiment, dict) and bool(latest_experiment.get("run_id"))
            numeric_branch_no = recorded_branch_numbers.get(branch_name)
            if numeric_branch_no is None:
                if recorded_branch_numbers:
                    next_fallback_branch_index += 1
                    numeric_branch_no = next_fallback_branch_index
                else:
                    numeric_branch_no = index
            branches.append(
                {
                    "branch_no": self._format_branch_number(numeric_branch_no),
                    "branch_name": branch_name,
                    "worktree_root": item.get("worktree_root"),
                    "is_active_head": branch_name == active_head_branch,
                    "is_active_workspace": branch_name == active_workspace_branch,
                    "idea_id": latest_idea.get("idea_id") or (latest_experiment.get("idea_id") if isinstance(latest_experiment, dict) else None),
                    "idea_title": latest_idea.get("title"),
                    "idea_problem": latest_idea.get("problem"),
                    "method_brief": latest_idea.get("method_brief"),
                    "selection_scores": self._normalize_selection_scores(latest_idea.get("selection_scores")),
                    "mechanism_family": latest_idea.get("mechanism_family"),
                    "change_layer": latest_idea.get("change_layer"),
                    "source_lens": latest_idea.get("source_lens"),
                    "next_target": latest_idea.get("next_target"),
                    "lineage_intent": latest_idea.get("lineage_intent"),
                    "parent_branch": resolved_parent_branch,
                    "foundation_ref": latest_idea.get("foundation_ref"),
                    "foundation_reason": latest_idea.get("foundation_reason"),
                    "idea_md_path": latest_idea.get("idea_md_path"),
                    "idea_draft_path": latest_idea.get("idea_draft_path"),
                    "latest_main_experiment": latest_experiment,
                    "has_main_result": has_main_result,
                    "round_state": "post_result" if has_main_result else "pre_result",
                    "experiments": experiments,
                    "idea_history": ideas,
                    "experiment_count": len(experiments),
                    "updated_at": (
                        latest_experiment.get("updated_at")
                        if isinstance(latest_experiment, dict)
                        else latest_idea.get("updated_at")
                    )
                    or item.get("first_seen_at"),
                }
            )

        branches.sort(
            key=lambda item: (
                0 if item.get("is_active_head") else 1,
                str(item.get("branch_no") or ""),
            ),
            reverse=False,
        )

        return {
            "ok": True,
            "active_head_branch": active_head_branch,
            "active_workspace_branch": active_workspace_branch,
            "count": len(branches),
            "branches": branches,
        }

    def resolve_runtime_refs(self, quest_root: Path) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        active_campaign_id = str(state.get("active_analysis_campaign_id") or "").strip() or None
        analysis_parent_branch = str(state.get("analysis_parent_branch") or "").strip() or None
        paper_parent_branch = str(state.get("paper_parent_branch") or "").strip() or None
        current_workspace_branch = str(state.get("current_workspace_branch") or "").strip() or None
        research_head_branch = str(state.get("research_head_branch") or "").strip() or None
        canonical_branch = analysis_parent_branch or paper_parent_branch or current_workspace_branch or research_head_branch
        latest_main_run = self._latest_main_run_for_branch(quest_root, canonical_branch or "")
        _, selected_outline = self._read_selected_outline_record(quest_root)
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        active_campaign = (
            self._read_analysis_manifest(quest_root, active_campaign_id)
            if active_campaign_id
            else {}
        )
        active_campaign = active_campaign if isinstance(active_campaign, dict) else {}
        latest_paths = (
            dict(latest_main_run.get("paths") or {})
            if isinstance(latest_main_run, dict) and isinstance(latest_main_run.get("paths"), dict)
            else {}
        )
        return {
            "ok": True,
            "active_idea_id": str(state.get("active_idea_id") or "").strip() or None,
            "research_head_branch": research_head_branch,
            "research_head_worktree_root": str(state.get("research_head_worktree_root") or "").strip() or None,
            "current_workspace_branch": current_workspace_branch,
            "current_workspace_root": str(state.get("current_workspace_root") or "").strip() or None,
            "analysis_parent_branch": analysis_parent_branch,
            "analysis_parent_worktree_root": str(state.get("analysis_parent_worktree_root") or "").strip() or None,
            "current_canonical_branch": canonical_branch,
            "active_analysis_campaign_id": active_campaign_id,
            "active_campaign_title": str(active_campaign.get("title") or "").strip() or None,
            "next_pending_slice_id": str(state.get("next_pending_slice_id") or "").strip() or None,
            "latest_main_run_id": str((latest_main_run or {}).get("run_id") or "").strip() or None,
            "latest_main_run_branch": str((latest_main_run or {}).get("branch") or "").strip() or None,
            "latest_main_result_json": str(latest_paths.get("result_json") or "").strip() or None,
            "selected_outline_ref": str(selected_outline.get("outline_id") or "").strip() or None,
            "default_reply_interaction_id": str(snapshot.get("default_reply_interaction_id") or "").strip() or None,
        }

    @staticmethod
    def _node_activation_ref(node: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None
        ref = str(node.get("ref") or "").strip()
        if not ref:
            return None
        return {
            "ref": ref,
            "branch_kind": str(node.get("branch_kind") or "").strip() or None,
            "idea_id": str(node.get("idea_id") or "").strip() or None,
            "run_id": str(
                node.get("run_id")
                or ((node.get("latest_main_experiment") or {}) if isinstance(node.get("latest_main_experiment"), dict) else {}).get("run_id")
                or ((node.get("latest_result") or {}) if isinstance(node.get("latest_result"), dict) else {}).get("run_id")
                or ""
            ).strip() or None,
            "paper_line_id": str(node.get("paper_line_id") or "").strip() or None,
            "worktree_root": str(node.get("worktree_root") or "").strip() or None,
            "compare_base": str(node.get("compare_base") or "").strip() or None,
            "head_commit": str(node.get("head") or "").strip() or None,
        }

    @staticmethod
    def _node_history_payload(
        node: dict[str, Any] | None,
        *,
        node_by_ref: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None
        ref = str(node.get("ref") or "").strip()
        if not ref:
            return None
        parent_chain: list[str] = []
        cursor = str(node.get("parent_ref") or "").strip() or None
        seen: set[str] = {ref}
        while cursor and cursor not in seen and len(parent_chain) < 12:
            parent_chain.append(cursor)
            seen.add(cursor)
            parent_node = node_by_ref.get(cursor)
            cursor = str((parent_node or {}).get("parent_ref") or "").strip() or None
        source_refs = [
            item
            for item in [
                str(node.get("parent_ref") or "").strip() or None,
                str(node.get("parent_branch") or "").strip() or None,
                str(node.get("source_branch") or "").strip() or None,
                str(node.get("compare_base") or "").strip() or None,
                str(((node.get("foundation_ref") or {}) if isinstance(node.get("foundation_ref"), dict) else {}).get("branch") or "").strip() or None,
            ]
            if item
        ]
        deduped_source_refs: list[str] = []
        seen_source: set[str] = set()
        for item in source_refs:
            if item in seen_source:
                continue
            seen_source.add(item)
            deduped_source_refs.append(item)
        return {
            "current_ref": ref,
            "branch_no": str(node.get("branch_no") or "").strip() or None,
            "branch_kind": str(node.get("branch_kind") or "").strip() or None,
            "tier": str(node.get("tier") or "").strip() or None,
            "parent_ref": str(node.get("parent_ref") or "").strip() or None,
            "ancestor_refs": parent_chain,
            "compare_base": str(node.get("compare_base") or "").strip() or None,
            "source_refs": deduped_source_refs,
            "idea_id": str(node.get("idea_id") or "").strip() or None,
            "run_id": str(
                node.get("run_id")
                or ((node.get("latest_main_experiment") or {}) if isinstance(node.get("latest_main_experiment"), dict) else {}).get("run_id")
                or ((node.get("latest_result") or {}) if isinstance(node.get("latest_result"), dict) else {}).get("run_id")
                or ""
            ).strip() or None,
            "paper_line_id": str(node.get("paper_line_id") or "").strip() or None,
            "foundation_ref": dict(node.get("foundation_ref") or {}) if isinstance(node.get("foundation_ref"), dict) else None,
            "latest_metric": dict(node.get("latest_metric") or {}) if isinstance(node.get("latest_metric"), dict) else None,
            "latest_result_summary": str(
                node.get("latest_summary")
                or ((node.get("latest_result") or {}) if isinstance(node.get("latest_result"), dict) else {}).get("summary")
                or ""
            ).strip() or None,
            "workflow_state": dict(node.get("workflow_state") or {}) if isinstance(node.get("workflow_state"), dict) else None,
        }

    @staticmethod
    def _recommended_activation_ref(
        *,
        current_node: dict[str, Any] | None,
        research_head_node: dict[str, Any] | None,
        current_ref: dict[str, Any] | None,
        research_head_ref: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if current_ref is None and research_head_ref is None:
            return None
        if current_ref and research_head_ref and str(current_ref.get("ref") or "") == str(research_head_ref.get("ref") or ""):
            return {
                **dict(current_ref),
                "reason": "Current workspace ref and research head already agree; continue on the same durable node.",
                "why_now": "No branch switch is needed unless a later route decision explicitly changes foundation.",
            }
        if current_ref:
            branch_kind = str(((current_node or {}).get("branch_kind") or current_ref.get("branch_kind") or "")).strip().lower()
            reason = (
                "The runtime's active workspace differs from the newest durable research head; prefer the active workspace for immediate continuation and branch-local actions."
            )
            if branch_kind == "paper":
                reason = "The active workspace is the paper line; continue there for writing/finalize work unless a route decision explicitly reactivates another branch."
            elif branch_kind == "analysis":
                reason = "The active workspace is an analysis branch; continue there for slice-local work unless the analysis route is being closed or superseded."
            return {
                **dict(current_ref),
                "reason": reason,
                "why_now": "This ref is the safest activation target for immediate continuation because it matches the runtime's current workspace.",
                "alternate_research_head_ref": dict(research_head_ref or {}),
            }
        return {
            **dict(research_head_ref or {}),
            "reason": "No active workspace ref is available, so fall back to the newest durable research head.",
            "why_now": "This is the best available durable activation target when runtime workspace state is incomplete.",
        }

    def _resolve_canvas_workflow_state(
        self,
        *,
        ref: str,
        summary: dict[str, Any] | None,
        active_anchor: str,
        active_analysis_campaign_id: str | None,
        current_workspace_branch: str | None,
        workspace_mode: str,
        paper_parent_branch: str | None,
        paper_parent_run_id: str | None,
        next_pending_slice_id: str | None,
        campaign_parent_branch: str | None,
        campaign_paper_line_branch: str | None,
        campaign_total_slices: int,
        campaign_completed_slices: int,
        slice_by_branch: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        branch_kind = self._branch_kind_from_name(ref)
        has_main_result = bool((summary or {}).get("has_main_result"))
        workflow_state: dict[str, Any] = {
            "analysis_state": "none",
            "writing_state": "not_ready",
            "analysis_campaign_id": active_analysis_campaign_id,
            "total_slices": campaign_total_slices or None,
            "completed_slices": campaign_completed_slices or None,
            "next_pending_slice_id": next_pending_slice_id,
            "paper_parent_branch": paper_parent_branch,
            "paper_parent_run_id": paper_parent_run_id,
            "status_reason": None,
        }
        if branch_kind == "analysis":
            slice_entry = slice_by_branch.get(ref)
            slice_status = str((slice_entry or {}).get("status") or "pending").strip().lower() or "pending"
            if slice_status == "completed":
                workflow_state["analysis_state"] = "completed"
                workflow_state["status_reason"] = "Analysis slice completed."
            elif ref == current_workspace_branch or str((slice_entry or {}).get("slice_id") or "").strip() == next_pending_slice_id:
                workflow_state["analysis_state"] = "active"
                workflow_state["status_reason"] = (
                    f"Analysis {campaign_completed_slices}/{campaign_total_slices} done"
                    if campaign_total_slices
                    else "Analysis slice active."
                )
            else:
                workflow_state["analysis_state"] = "pending"
                workflow_state["status_reason"] = "Analysis slice pending."
            return workflow_state
        if branch_kind == "paper":
            if campaign_paper_line_branch and ref == campaign_paper_line_branch and next_pending_slice_id is not None:
                workflow_state["analysis_state"] = "active"
                workflow_state["writing_state"] = "blocked_by_analysis"
                workflow_state["status_reason"] = (
                    f"Analysis {campaign_completed_slices}/{campaign_total_slices} done"
                    + (f" · next: {next_pending_slice_id}" if next_pending_slice_id else "")
                )
                return workflow_state
            if ref == current_workspace_branch and workspace_mode == "paper":
                workflow_state["writing_state"] = "completed" if active_anchor == "finalize" else "active"
                workflow_state["status_reason"] = (
                    "Writing finalized." if active_anchor == "finalize" else "Writing workspace active."
                )
            else:
                workflow_state["writing_state"] = "ready"
                workflow_state["status_reason"] = "Writing workspace prepared."
            return workflow_state
        if campaign_parent_branch and not campaign_paper_line_branch and ref == campaign_parent_branch:
            workflow_state["analysis_state"] = "completed" if next_pending_slice_id is None else "active"
            if has_main_result:
                workflow_state["writing_state"] = "ready" if next_pending_slice_id is None else "blocked_by_analysis"
            workflow_state["status_reason"] = (
                "Analysis complete. Ready for writing."
                if next_pending_slice_id is None
                else (
                    f"Analysis {campaign_completed_slices}/{campaign_total_slices} done"
                    + (f" · next: {next_pending_slice_id}" if next_pending_slice_id else "")
                )
            )
            return workflow_state
        if has_main_result:
            workflow_state["writing_state"] = "ready"
            workflow_state["status_reason"] = "Main experiment recorded. Ready for writing."
            return workflow_state
        workflow_state["status_reason"] = "Awaiting main experiment result."
        return workflow_state

    def get_research_canvas(self, quest_root: Path) -> dict[str, Any]:
        quest_id = self._quest_id(quest_root)
        payload = self.quest_service.git_branch_canvas(quest_id)
        research_state = self.quest_service.read_research_state(quest_root)
        active_workspace_branch = str(research_state.get("current_workspace_branch") or "").strip() or None
        research_head_branch = str(research_state.get("research_head_branch") or "").strip() or None
        payload["active_workspace_ref"] = active_workspace_branch
        payload["research_head_ref"] = research_head_branch
        payload["workspace_mode"] = str(research_state.get("workspace_mode") or "quest").strip() or "quest"
        projection_state = str(((payload or {}).get("projection_status") or {}).get("state") or "").strip().lower()
        if projection_state and projection_state != "ready" and not (payload.get("nodes") or []):
            payload["current_node"] = None
            payload["research_head_node"] = None
            payload["activation_refs"] = {"current": None, "research_head": None}
            payload["node_count"] = 0
            payload["edge_count"] = 0
            return payload

        quest_data = self.quest_service.read_quest_yaml(quest_root)
        active_anchor = str(quest_data.get("active_anchor") or "").strip().lower()
        active_analysis_campaign_id = str(research_state.get("active_analysis_campaign_id") or "").strip() or None
        current_workspace_branch = str(research_state.get("current_workspace_branch") or "").strip() or None
        workspace_mode = str(research_state.get("workspace_mode") or "").strip().lower() or "quest"
        paper_parent_branch = str(research_state.get("paper_parent_branch") or "").strip() or None
        paper_parent_run_id = str(research_state.get("paper_parent_run_id") or "").strip() or None
        next_pending_slice_id = str(research_state.get("next_pending_slice_id") or "").strip() or None
        try:
            branch_summary = self.list_research_branches(quest_root)
        except Exception:
            branch_summary = {"branches": []}
        try:
            optimization_frontier = self.get_optimization_frontier(quest_root)
        except Exception:
            optimization_frontier = {"ok": False}
        branch_summary_by_name = {
            str(item.get("branch_name") or "").strip(): item
            for item in (branch_summary.get("branches") or [])
            if isinstance(item, dict) and str(item.get("branch_name") or "").strip()
        }
        frontier_payload = (
            dict(optimization_frontier.get("optimization_frontier") or {})
            if isinstance(optimization_frontier, dict)
            and isinstance(optimization_frontier.get("optimization_frontier"), dict)
            else {}
        )
        best_branch_name = str(((frontier_payload.get("best_branch") or {}) if isinstance(frontier_payload.get("best_branch"), dict) else {}).get("branch_name") or "").strip() or None
        stagnant_branch_names = {
            str(item.get("branch_name") or "").strip()
            for item in (frontier_payload.get("stagnant_branches") or [])
            if isinstance(item, dict) and str(item.get("branch_name") or "").strip()
        }
        fusion_candidate_names = {
            str(item.get("branch_name") or "").strip()
            for item in (frontier_payload.get("fusion_candidates") or [])
            if isinstance(item, dict) and str(item.get("branch_name") or "").strip()
        }
        candidate_count_by_branch: dict[str, int] = {}
        for item in frontier_payload.get("implementation_candidates") or []:
            if not isinstance(item, dict):
                continue
            branch_name = str(item.get("branch") or "").strip()
            if not branch_name:
                continue
            candidate_count_by_branch[branch_name] = candidate_count_by_branch.get(branch_name, 0) + 1
        active_campaign: dict[str, Any] = {}
        if active_analysis_campaign_id:
            try:
                active_campaign = self.get_analysis_campaign(
                    quest_root,
                    campaign_id=active_analysis_campaign_id,
                )
            except Exception:
                active_campaign = {}
        campaign_parent_branch = str(active_campaign.get("parent_branch") or "").strip() or None if isinstance(active_campaign, dict) else None
        campaign_paper_line_branch = str(active_campaign.get("paper_line_branch") or "").strip() or None if isinstance(active_campaign, dict) else None
        campaign_slices = [dict(item) for item in ((active_campaign or {}).get("slices") or []) if isinstance(item, dict)]
        campaign_total_slices = len(campaign_slices)
        campaign_completed_slices = sum(1 for item in campaign_slices if str(item.get("status") or "").strip().lower() == "completed")
        slice_by_branch = {
            str(item.get("branch") or "").strip(): item
            for item in campaign_slices
            if str(item.get("branch") or "").strip()
        }

        for node in payload.get("nodes", []):
            ref = str(node.get("ref") or "").strip()
            if not ref:
                continue
            summary = branch_summary_by_name.get(ref)
            node["active_workspace"] = ref == active_workspace_branch
            node["research_head"] = ref == research_head_branch
            node["workflow_state"] = self._resolve_canvas_workflow_state(
                ref=ref,
                summary=summary if isinstance(summary, dict) else None,
                active_anchor=active_anchor,
                active_analysis_campaign_id=active_analysis_campaign_id,
                current_workspace_branch=current_workspace_branch,
                workspace_mode=workspace_mode,
                paper_parent_branch=paper_parent_branch,
                paper_parent_run_id=paper_parent_run_id,
                next_pending_slice_id=next_pending_slice_id,
                campaign_parent_branch=campaign_parent_branch,
                campaign_paper_line_branch=campaign_paper_line_branch,
                campaign_total_slices=campaign_total_slices,
                campaign_completed_slices=campaign_completed_slices,
                slice_by_branch=slice_by_branch,
            )
            if not isinstance(summary, dict):
                continue
            node["branch_no"] = summary.get("branch_no")
            node["idea_title"] = summary.get("idea_title")
            node["idea_problem"] = summary.get("idea_problem")
            node["next_target"] = summary.get("next_target")
            node["lineage_intent"] = summary.get("lineage_intent")
            node["parent_branch"] = summary.get("parent_branch")
            node["foundation_ref"] = summary.get("foundation_ref")
            node["foundation_reason"] = summary.get("foundation_reason")
            node["idea_md_path"] = summary.get("idea_md_path")
            node["idea_draft_path"] = summary.get("idea_draft_path")
            node["latest_main_experiment"] = summary.get("latest_main_experiment")
            node["experiment_count"] = summary.get("experiment_count")
            node["has_main_result"] = summary.get("has_main_result")
            node["optimization_mode"] = frontier_payload.get("mode")
            node["optimization_best"] = ref == best_branch_name
            node["optimization_stagnant"] = ref in stagnant_branch_names
            node["optimization_fusion_candidate"] = ref in fusion_candidate_names
            node["optimization_candidate_count"] = candidate_count_by_branch.get(ref, 0)

        node_by_ref = {
            str(item.get("ref") or "").strip(): item
            for item in (payload.get("nodes") or [])
            if isinstance(item, dict) and str(item.get("ref") or "").strip()
        }
        current_node_ref = active_workspace_branch or str(payload.get("current_ref") or "").strip() or None
        research_head_ref = research_head_branch or current_node_ref
        current_node = node_by_ref.get(current_node_ref or "")
        research_head_node = node_by_ref.get(research_head_ref or "")
        payload["current_node"] = current_node
        payload["research_head_node"] = research_head_node
        current_activation_ref = self._node_activation_ref(current_node)
        research_head_activation_ref = self._node_activation_ref(research_head_node)
        payload["activation_refs"] = {
            "current": current_activation_ref,
            "research_head": research_head_activation_ref,
            "recommended": self._recommended_activation_ref(
                current_node=current_node,
                research_head_node=research_head_node,
                current_ref=current_activation_ref,
                research_head_ref=research_head_activation_ref,
            ),
        }
        payload["node_history"] = {
            "current": self._node_history_payload(current_node, node_by_ref=node_by_ref),
            "research_head": self._node_history_payload(research_head_node, node_by_ref=node_by_ref),
        }
        payload["node_count"] = len(payload.get("nodes") or [])
        payload["edge_count"] = len(payload.get("edges") or [])
        return payload

    def get_research_map_status(
        self,
        quest_root: Path,
        *,
        detail: str = "summary",
        locale: str = "zh",
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "summary").strip().lower() or "summary"
        if normalized_detail not in {"summary", "full"}:
            raise ValueError("get_research_map_status detail must be `summary` or `full`.")
        normalized_locale = str(locale or "zh").strip().lower() or "zh"
        quest_id = self._quest_id(quest_root)
        canvas = self.get_research_canvas(quest_root)
        git_canvas = self.quest_service.git_commit_canvas(quest_id)
        runtime_refs = self.resolve_runtime_refs(quest_root)
        quest_state = self.get_quest_state(
            quest_root,
            detail="full" if normalized_detail == "full" else "summary",
        )
        global_status = self.get_global_status(
            quest_root,
            detail="full" if normalized_detail == "full" else "brief",
            locale=normalized_locale,
        )
        scoreboard = self.refresh_method_scoreboard(quest_root)
        scoreboard_payload = dict(scoreboard.get("scoreboard") or {}) if isinstance(scoreboard.get("scoreboard"), dict) else {}
        current_node = dict(canvas.get("current_node") or {}) if isinstance(canvas.get("current_node"), dict) else None
        head_node = dict(canvas.get("research_head_node") or {}) if isinstance(canvas.get("research_head_node"), dict) else None
        quest_state_payload = dict(quest_state.get("quest_state") or {}) if isinstance(quest_state.get("quest_state"), dict) else {}
        global_status_payload = dict(global_status.get("global_status") or {}) if isinstance(global_status.get("global_status"), dict) else {}

        summary_zh = (
            f"当前节点进展以 `{str((canvas.get('active_workspace_ref') or canvas.get('current_ref') or 'none'))}` 为主。"
            f" 研究头是 `{str((canvas.get('research_head_ref') or 'none'))}`。"
            f" 当前阶段 `{str(quest_state_payload.get('active_anchor') or 'unknown')}`。"
            f"{(' 当前 incumbent 是 `' + str(scoreboard_payload.get('incumbent_title') or '') + '`。' if str(scoreboard_payload.get('incumbent_title') or '').strip() else '')}"
        ).strip()
        summary_en = (
            f"Current node progress is anchored on `{str((canvas.get('active_workspace_ref') or canvas.get('current_ref') or 'none'))}`."
            f" Research head: `{str((canvas.get('research_head_ref') or 'none'))}`."
            f" Current stage: `{str(quest_state_payload.get('active_anchor') or 'unknown')}`."
            f"{(' Current incumbent: `' + str(scoreboard_payload.get('incumbent_title') or '') + '`.' if str(scoreboard_payload.get('incumbent_title') or '').strip() else '')}"
        ).strip()

        payload: dict[str, Any] = {
            "quest_id": quest_id,
            "title": quest_state_payload.get("title"),
            "summary_text": summary_zh if normalized_locale.startswith("zh") else summary_en,
            "usage_notes": {
                "summary_mode": "Use detail='summary' for ordinary recovery, status answers, and branch-switch checks.",
                "full_mode": "Use detail='full' only when you need the full node list, edge payload, or optimization frontier details.",
                "activation_rule": "Prefer `recommended_activation_ref` when reactivating a durable node unless a later route decision explicitly points elsewhere.",
                "dedupe_rule": "If current node, research head, and blocker/route state did not change, continue the current action instead of repeatedly re-reading the research map.",
            },
            "active_ids": {
                "active_idea_id": runtime_refs.get("active_idea_id"),
                "latest_main_run_id": runtime_refs.get("latest_main_run_id"),
                "active_analysis_campaign_id": runtime_refs.get("active_analysis_campaign_id"),
                "selected_outline_ref": runtime_refs.get("selected_outline_ref"),
            },
            "git": {
                "head_commit": canvas.get("head"),
                "current_ref": canvas.get("current_ref"),
                "active_workspace_ref": canvas.get("active_workspace_ref"),
                "research_head_ref": canvas.get("research_head_ref"),
                "workspace_mode": canvas.get("workspace_mode"),
            },
            "activation_refs": dict(canvas.get("activation_refs") or {}),
            "current_node": current_node,
            "research_head_node": head_node,
            "node_history": dict(canvas.get("node_history") or {}),
            "recommended_activation_ref": dict(((canvas.get("activation_refs") or {}) if isinstance(canvas.get("activation_refs"), dict) else {}).get("recommended") or {}) or None,
            "projection_status": {
                "canvas": canvas.get("projection_status"),
                "git_canvas": git_canvas.get("projection_status"),
            },
            "quest_state": quest_state_payload,
            "runtime_refs": runtime_refs,
            "global_status": global_status_payload,
            "method_scoreboard": scoreboard_payload,
            "canvas_summary": {
                "node_count": int(canvas.get("node_count") or len(canvas.get("nodes") or [])),
                "edge_count": int(canvas.get("edge_count") or len(canvas.get("edges") or [])),
                "default_ref": canvas.get("default_ref"),
                "views": canvas.get("views"),
            },
            "git_canvas_summary": {
                "node_count": len(git_canvas.get("nodes") or []),
                "edge_count": len(git_canvas.get("edges") or []),
                "head": git_canvas.get("head"),
                "current_ref": git_canvas.get("current_ref"),
            },
        }
        if normalized_detail == "full":
            payload["canvas"] = canvas
            payload["git_canvas"] = git_canvas
            payload["branch_summary"] = self.list_research_branches(quest_root)
            payload["optimization_frontier"] = self.get_optimization_frontier(quest_root)
        return {
            "ok": True,
            "detail": normalized_detail,
            "locale": normalized_locale,
            "research_map_status": payload,
        }

    def get_paper_contract_health(
        self,
        quest_root: Path,
        *,
        detail: str = "summary",
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "summary").strip().lower() or "summary"
        if normalized_detail not in {"summary", "full"}:
            raise ValueError("get_paper_contract_health detail must be `summary` or `full`.")
        workspace_root = self.quest_service.active_workspace_root(quest_root)
        paper_contract = self.quest_service._paper_contract_payload(quest_root, workspace_root)
        paper_evidence = self.quest_service._paper_evidence_payload(quest_root, workspace_root)
        analysis_inventory = self.quest_service._analysis_inventory_payload(quest_root, workspace_root)
        paper_lines, active_paper_line_ref = self.quest_service._paper_lines_payload(quest_root, workspace_root)
        if not paper_contract:
            return {
                "ok": False,
                "message": "No active paper contract is available for the current quest state.",
                "active_paper_line_ref": active_paper_line_ref,
                "paper_lines": paper_lines,
            }
        selected_outline_ref = str(paper_contract.get("selected_outline_ref") or "").strip() or None
        if not selected_outline_ref:
            outlines = self.list_paper_outlines(quest_root)
            candidate_outline_ids = [
                str(item.get("outline_id") or "").strip()
                for item in (outlines.get("outlines") or [])
                if str(item.get("status") or "").strip() in {"candidate", "revised"}
                and str(item.get("outline_id") or "").strip()
            ]
            candidate_hint = (
                f" Available candidates: {', '.join(candidate_outline_ids[:5])}."
                if candidate_outline_ids
                else ""
            )
            return {
                "ok": False,
                "message": (
                    "No selected outline is available for the current quest state."
                    + candidate_hint
                    + " Select or revise one with `artifact.submit_paper_outline(mode='select'| 'revise', ...)` "
                    + "before launching a writing-facing analysis campaign."
                ),
                "active_paper_line_ref": active_paper_line_ref,
                "paper_lines": paper_lines,
                "outline_candidates": outlines.get("outlines") if isinstance(outlines, dict) else [],
            }
        payload = self.quest_service._paper_contract_health_payload(
            paper_contract=paper_contract,
            paper_evidence=paper_evidence,
            analysis_inventory=analysis_inventory,
            paper_lines=paper_lines,
            active_paper_line_ref=active_paper_line_ref,
        )
        payload = dict(payload or {})
        if normalized_detail == "summary":
            payload.pop("unresolved_required_items", None)
            payload.pop("unmapped_completed_items", None)
            payload.pop("blocking_pending_slices", None)
            payload.pop("manuscript_coverage", None)
        return {
            "ok": True,
            "detail": normalized_detail,
            "active_paper_line_ref": active_paper_line_ref,
            "active_workspace_root": str(workspace_root),
            "paper_contract_health": payload,
        }

    def validate_manuscript_coverage(
        self,
        quest_root: Path,
        *,
        detail: str = "summary",
        minimum_sections: int = 5,
        minimum_analysis_groups: int = 5,
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "summary").strip().lower() or "summary"
        if normalized_detail not in {"summary", "full"}:
            raise ValueError("validate_manuscript_coverage detail must be `summary` or `full`.")
        workspace_root = self.quest_service.active_workspace_root(quest_root)
        gate_status = self._paper_bundle_gate_status(quest_root, workspace_root=workspace_root)
        coverage = self._paper_manuscript_coverage_payload(
            quest_root,
            workspace_root=workspace_root,
            evidence_gate=gate_status,
            minimum_sections=max(1, int(minimum_sections or 5)),
            minimum_analysis_groups=max(0, int(minimum_analysis_groups or 5)),
        )
        for paper_root in self._paper_active_sync_roots(quest_root, workspace_root=workspace_root):
            write_json(paper_root / "manuscript_coverage.json", coverage)
        result_coverage = dict(coverage)
        if normalized_detail == "summary":
            result_coverage.pop("tex_files", None)
        return {
            "ok": True,
            "detail": normalized_detail,
            "coverage_path": str(self._paper_manuscript_coverage_path(quest_root, workspace_root=workspace_root)),
            "manuscript_coverage": result_coverage,
        }

    def get_paper_contract(
        self,
        quest_root: Path,
        *,
        detail: str = "full",
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "full").strip().lower() or "full"
        if normalized_detail not in {"summary", "full"}:
            raise ValueError("get_paper_contract detail must be `summary` or `full`.")
        workspace_root = self.quest_service.active_workspace_root(quest_root)
        paper_contract = self.quest_service._paper_contract_payload(quest_root, workspace_root)
        paper_evidence = self.quest_service._paper_evidence_payload(quest_root, workspace_root)
        analysis_inventory = self.quest_service._analysis_inventory_payload(quest_root, workspace_root)
        paper_lines, active_paper_line_ref = self.quest_service._paper_lines_payload(quest_root, workspace_root)
        if not paper_contract:
            return {
                "ok": False,
                "message": "No active paper contract is available for the current quest state.",
                "active_paper_line_ref": active_paper_line_ref,
                "paper_lines": paper_lines,
            }
        matrix_payload = self._build_paper_experiment_matrix_payload(quest_root, workspace_root=Path(str(paper_contract.get("workspace_root") or workspace_root)))
        health = self.quest_service._paper_contract_health_payload(
            paper_contract=paper_contract,
            paper_evidence=paper_evidence,
            analysis_inventory=analysis_inventory,
            paper_lines=paper_lines,
            active_paper_line_ref=active_paper_line_ref,
        )
        payload: dict[str, Any] = {
            "selected_outline_ref": paper_contract.get("selected_outline_ref"),
            "paper_line_id": paper_contract.get("paper_line_id"),
            "paper_contract": paper_contract,
            "paper_evidence": paper_evidence,
            "analysis_inventory": analysis_inventory,
            "paper_lines": paper_lines,
            "active_paper_line_ref": active_paper_line_ref,
            "paper_contract_health": health,
            "paper_experiment_matrix": matrix_payload,
        }
        if normalized_detail == "summary":
            contract = dict(paper_contract)
            contract["sections"] = [
                {
                    "section_id": str(item.get("section_id") or "").strip() or None,
                    "title": str(item.get("title") or "").strip() or None,
                    "paper_role": str(item.get("paper_role") or "").strip() or None,
                    "status": str(item.get("status") or "").strip() or None,
                    "required_item_count": len(self._normalize_string_list(item.get("required_items"))),
                    "optional_item_count": len(self._normalize_string_list(item.get("optional_items"))),
                    "result_row_count": len([row for row in (item.get("result_table") or []) if isinstance(row, dict)]),
                }
                for item in (paper_contract.get("sections") or [])
                if isinstance(item, dict)
            ]
            evidence = dict(paper_evidence or {}) if isinstance(paper_evidence, dict) else {}
            evidence["items"] = [dict(item) for item in (evidence.get("items") or [])[:12] if isinstance(item, dict)]
            inventory = dict(analysis_inventory or {}) if isinstance(analysis_inventory, dict) else {}
            inventory["campaigns"] = [dict(item) for item in (inventory.get("campaigns") or [])[:6] if isinstance(item, dict)]
            matrix = dict(matrix_payload)
            matrix["rows"] = [dict(item) for item in (matrix_payload.get("rows") or [])[:20] if isinstance(item, dict)]
            payload = {
                "selected_outline_ref": contract.get("selected_outline_ref"),
                "paper_line_id": contract.get("paper_line_id"),
                "paper_contract": contract,
                "paper_evidence": evidence,
                "analysis_inventory": inventory,
                "paper_lines": paper_lines[:6],
                "active_paper_line_ref": active_paper_line_ref,
                "paper_contract_health": health,
                "paper_experiment_matrix": matrix,
            }
        return {
            "ok": True,
            "detail": normalized_detail,
            "active_workspace_root": str(workspace_root),
            "paper_contract_bundle": payload,
        }

    def get_quest_state(
        self,
        quest_root: Path,
        *,
        detail: str = "summary",
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "summary").strip().lower() or "summary"
        if normalized_detail not in {"summary", "full"}:
            raise ValueError("get_quest_state detail must be `summary` or `full`.")
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        payload: dict[str, Any] = {
            "quest_id": snapshot.get("quest_id"),
            "title": snapshot.get("title"),
            "active_anchor": snapshot.get("active_anchor"),
            "continuation_policy": snapshot.get("continuation_policy"),
            "continuation_anchor": snapshot.get("continuation_anchor"),
            "continuation_reason": snapshot.get("continuation_reason"),
            "baseline_gate": snapshot.get("baseline_gate"),
            "active_baseline_id": snapshot.get("active_baseline_id"),
            "active_baseline_variant_id": snapshot.get("active_baseline_variant_id"),
            "active_run_id": snapshot.get("active_run_id"),
            "active_idea_id": snapshot.get("active_idea_id"),
            "active_analysis_campaign_id": snapshot.get("active_analysis_campaign_id"),
            "active_idea_line_ref": snapshot.get("active_idea_line_ref"),
            "active_paper_line_ref": snapshot.get("active_paper_line_ref"),
            "current_workspace_branch": snapshot.get("current_workspace_branch"),
            "current_workspace_root": snapshot.get("current_workspace_root"),
            "research_head_branch": snapshot.get("research_head_branch"),
            "research_head_worktree_root": snapshot.get("research_head_worktree_root"),
            "workspace_mode": snapshot.get("workspace_mode"),
            "runtime_status": snapshot.get("runtime_status"),
            "display_status": snapshot.get("display_status"),
            "waiting_interaction_id": snapshot.get("waiting_interaction_id"),
            "pending_user_message_count": snapshot.get("pending_user_message_count"),
            "next_pending_slice_id": snapshot.get("next_pending_slice_id"),
            "paper_contract_health": snapshot.get("paper_contract_health"),
        }
        if normalized_detail == "full":
            payload.update(
                {
                    "startup_contract": snapshot.get("startup_contract"),
                    "requested_baseline_ref": snapshot.get("requested_baseline_ref"),
                    "confirmed_baseline_ref": snapshot.get("confirmed_baseline_ref"),
                    "counts": snapshot.get("counts"),
                    "paths": snapshot.get("paths"),
                    "active_interactions": snapshot.get("active_interactions"),
                    "recent_reply_threads": snapshot.get("recent_reply_threads"),
                    "recent_artifacts": snapshot.get("recent_artifacts"),
                    "recent_runs": snapshot.get("recent_runs"),
                    "idea_lines": snapshot.get("idea_lines"),
                    "paper_lines": snapshot.get("paper_lines"),
                }
            )
        return {
            "ok": True,
            "detail": normalized_detail,
            "quest_state": payload,
        }

    def get_global_status(
        self,
        quest_root: Path,
        *,
        detail: str = "brief",
        locale: str = "zh",
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "brief").strip().lower() or "brief"
        if normalized_detail not in {"brief", "full"}:
            raise ValueError("get_global_status detail must be `brief` or `full`.")
        normalized_locale = str(locale or "zh").strip().lower() or "zh"
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        scoreboard = self.refresh_method_scoreboard(quest_root)
        scoreboard_payload = dict(scoreboard.get("scoreboard") or {}) if isinstance(scoreboard.get("scoreboard"), dict) else {}
        counts = dict(snapshot.get("counts") or {}) if isinstance(snapshot.get("counts"), dict) else {}
        paper_health = (
            dict(snapshot.get("paper_contract_health") or {})
            if isinstance(snapshot.get("paper_contract_health"), dict)
            else {}
        )
        recent_runs = [dict(item) for item in (snapshot.get("recent_runs") or []) if isinstance(item, dict)]
        latest_run = recent_runs[-1] if recent_runs else {}
        latest_run_summary = str(latest_run.get("summary") or "").strip() or None
        status_line = (
            str(((snapshot.get("summary") or {}) if isinstance(snapshot.get("summary"), dict) else {}).get("status_line") or "").strip()
            or None
        )
        claim_boundary = {
            "supported": int(paper_health.get("supported_claim_count") or 0),
            "partial": int(paper_health.get("partial_claim_count") or 0),
            "unsupported": int(paper_health.get("unsupported_claim_count") or 0),
            "deferred": int(paper_health.get("deferred_claim_count") or 0),
        }
        paper_ready = bool(paper_health.get("writing_ready"))
        bundle_ready = bool(paper_health.get("finalize_ready"))
        closure_state = str(paper_health.get("closure_state") or "").strip() or None
        delivery_state = str(paper_health.get("delivery_state") or "").strip() or None
        stage = str(snapshot.get("active_anchor") or "decision").strip() or "decision"
        continuation_policy = str(snapshot.get("continuation_policy") or "auto").strip() or "auto"
        next_stage = str(paper_health.get("recommended_next_stage") or stage).strip() or stage
        next_action = str(paper_health.get("recommended_action") or "continue").strip() or "continue"
        brief_summary_zh = (
            f"当前阶段是 `{stage}`。"
            f"{(' 论文线当前状态是 `' + closure_state + '`。' if closure_state else '')}"
            f"{(' 论文线已达到 bundle-ready。' if bundle_ready and not closure_state else '')}"
            f"{(' 当前是停驻等待新消息，不会继续自动空转。' if continuation_policy == 'wait_for_user_or_resume' else '')}"
            f"{(' 最近主结果：' + latest_run_summary) if latest_run_summary else ''}"
        ).strip()
        brief_summary_en = (
            f"Current stage: `{stage}`."
            f"{(' Paper closure state: `' + closure_state + '`.' if closure_state else '')}"
            f"{(' The paper line is bundle-ready.' if bundle_ready and not closure_state else '')}"
            f"{(' The quest is currently parked and will not auto-spin until a new user message or resume.' if continuation_policy == 'wait_for_user_or_resume' else '')}"
            f"{(' Latest run: ' + latest_run_summary) if latest_run_summary else ''}"
        ).strip()
        payload: dict[str, Any] = {
            "quest_id": snapshot.get("quest_id"),
            "title": snapshot.get("title"),
            "current_stage": stage,
            "continuation_policy": continuation_policy,
            "continuation_anchor": snapshot.get("continuation_anchor"),
            "status_line": status_line,
            "latest_run_id": latest_run.get("run_id"),
            "latest_run_summary": latest_run_summary,
            "method_scoreboard_path": scoreboard.get("json_path"),
            "incumbent_method": scoreboard_payload.get("incumbent_title"),
            "paper_contract_health": {
                "writing_ready": paper_ready,
                "finalize_ready": bundle_ready,
                "closure_state": closure_state,
                "delivery_state": delivery_state,
                "delivered_at": paper_health.get("delivered_at"),
                "keep_bundle_fixed_by_default": bool(paper_health.get("keep_bundle_fixed_by_default")),
                "recommended_next_stage": next_stage,
                "recommended_action": next_action,
            },
            "claim_boundary": claim_boundary,
            "pending_user_message_count": int(snapshot.get("pending_user_message_count") or 0),
            "bash_running_count": int(counts.get("bash_running_count") or 0),
            "summary_text": brief_summary_zh if normalized_locale.startswith("zh") else brief_summary_en,
        }
        if normalized_detail == "full":
            payload.update(
                {
                    "runtime_status": snapshot.get("runtime_status"),
                    "display_status": snapshot.get("display_status"),
                    "baseline_gate": snapshot.get("baseline_gate"),
                    "active_baseline_id": snapshot.get("active_baseline_id"),
                    "active_idea_id": snapshot.get("active_idea_id"),
                    "active_analysis_campaign_id": snapshot.get("active_analysis_campaign_id"),
                    "current_workspace_branch": snapshot.get("current_workspace_branch"),
                    "recent_runs": recent_runs[-5:],
                    "paper_lines": snapshot.get("paper_lines"),
                    "idea_lines": snapshot.get("idea_lines"),
                    "method_scoreboard": scoreboard_payload,
                }
            )
        return {
            "ok": True,
            "detail": normalized_detail,
            "locale": normalized_locale,
            "global_status": payload,
        }

    def get_benchstore_catalog(
        self,
        quest_root: Path,
        *,
        detail: str = "summary",
    ) -> dict[str, Any]:
        normalized_detail = str(detail or "summary").strip().lower() or "summary"
        if normalized_detail not in {"summary", "full"}:
            raise ValueError("get_benchstore_catalog detail must be `summary` or `full`.")
        hardware_payload = read_json(self.home / "runtime" / "admin" / "cache" / "system_hardware.json", {})
        catalog = self.benchstore_service.list_entries(hardware_payload=hardware_payload if isinstance(hardware_payload, dict) else {})
        if normalized_detail == "full":
            return catalog
        items = catalog.get("items") if isinstance(catalog.get("items"), list) else []
        summarized_items = []
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            summarized_items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "one_line": item.get("one_line"),
                    "task_description": item.get("task_description"),
                    "aisb_direction": item.get("aisb_direction"),
                    "task_mode": item.get("task_mode"),
                    "cost_band": item.get("cost_band"),
                    "time_band": item.get("time_band"),
                    "difficulty": item.get("difficulty"),
                    "paper": item.get("paper"),
                    "download": item.get("download"),
                    "resources": item.get("resources"),
                    "environment": item.get("environment"),
                    "capability_tags": item.get("capability_tags"),
                    "track_fit": item.get("track_fit"),
                    "image_path": item.get("image_path"),
                    "image_url": item.get("image_url"),
                    "source_file": item.get("source_file"),
                    "compatibility": item.get("compatibility"),
                    "recommendation": item.get("recommendation"),
                    "install_state": item.get("install_state"),
                }
            )
        return {
            "ok": True,
            "device_summary": catalog.get("device_summary"),
            "device_capacity": catalog.get("device_capacity"),
            "filter_options": catalog.get("filter_options"),
            "shelves": catalog.get("shelves"),
            "items": summarized_items,
            "total": catalog.get("total"),
        }

    def get_start_setup_context(self, quest_root: Path) -> dict[str, Any]:
        quest_data = self.quest_service.read_quest_yaml(quest_root)
        startup_contract = quest_data.get("startup_contract") if isinstance(quest_data.get("startup_contract"), dict) else {}
        payload = startup_contract.get("start_setup_session") if isinstance(startup_contract, dict) and isinstance(startup_contract.get("start_setup_session"), dict) else {}
        return {
            "ok": True,
            "quest_id": quest_root.name,
            "start_setup_session": payload,
            "suggested_form": payload.get("suggested_form") if isinstance(payload.get("suggested_form"), dict) else {},
            "benchmark_context": payload.get("benchmark_context") if isinstance(payload.get("benchmark_context"), dict) else {},
            "locale": payload.get("locale"),
            "source": payload.get("source"),
        }

    def apply_start_setup_form_patch(
        self,
        quest_root: Path,
        *,
        form_patch: dict[str, Any] | None = None,
        session_patch: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        form_patch, session_patch = _normalize_start_setup_payload_parts(form_patch, session_patch)
        quest_data = self.quest_service.read_quest_yaml(quest_root)
        startup_contract = (
            dict(quest_data.get("startup_contract") or {})
            if isinstance(quest_data.get("startup_contract"), dict)
            else {}
        )
        start_setup_session = (
            dict(startup_contract.get("start_setup_session") or {})
            if isinstance(startup_contract.get("start_setup_session"), dict)
            else {}
        )
        previous_suggested_form = (
            _clean_start_setup_suggested_form(dict(start_setup_session.get("suggested_form") or {}))
            if isinstance(start_setup_session.get("suggested_form"), dict)
            else {}
        )
        next_suggested_form = {**previous_suggested_form, **dict(form_patch or {})}
        start_setup_session["suggested_form"] = next_suggested_form
        if isinstance(session_patch, dict) and session_patch:
            for key, value in session_patch.items():
                start_setup_session[key] = value
        startup_contract["start_setup_session"] = start_setup_session
        updated_quest = self.quest_service.update_startup_context(
            quest_root,
            startup_contract=startup_contract,
        )
        return {
            "ok": True,
            "quest_id": quest_root.name,
            "form_patch": dict(form_patch or {}),
            "suggested_form": next_suggested_form,
            "session_patch": dict(session_patch or {}),
            "message": str(message or "").strip() or None,
            "start_setup_session": (
                updated_quest.get("startup_contract", {}).get("start_setup_session")
                if isinstance(updated_quest.get("startup_contract"), dict)
                else start_setup_session
            ),
        }

    def refresh_method_scoreboard(self, quest_root: Path) -> dict[str, Any]:
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        ideas = self._idea_artifacts(quest_root)
        main_runs = self._main_run_artifacts(quest_root)
        entries_by_key: dict[str, dict[str, Any]] = {}
        idea_titles_by_id: dict[str, str] = {}

        for idea in ideas:
            idea_id = str(idea.get("idea_id") or "").strip()
            if not idea_id:
                continue
            idea_details = dict(idea.get("details") or {}) if isinstance(idea.get("details"), dict) else {}
            idea_title = str(idea.get("title") or idea_details.get("title") or idea_id).strip() or idea_id
            idea_titles_by_id[idea_id] = idea_title
            entries_by_key[idea_id] = {
                "line_key": idea_id,
                "idea_id": idea_id,
                "title": idea_title,
                "branch": str(idea.get("branch") or "").strip() or None,
                "status": "candidate",
                "latest_run_id": None,
                "latest_run_summary": None,
                "updated_at": str(idea.get("updated_at") or idea.get("created_at") or "").strip() or None,
                "incumbent": False,
            }

        for run in main_runs:
            idea_id = str(run.get("idea_id") or "").strip()
            key = idea_id or str(run.get("branch") or run.get("run_id") or "run").strip()
            entry = dict(entries_by_key.get(key) or {})
            entry.update(
                {
                    "line_key": key,
                    "idea_id": idea_id or entry.get("idea_id"),
                    "title": str(
                        entry.get("title")
                        or idea_titles_by_id.get(idea_id or "")
                        or run.get("title")
                        or run.get("run_id")
                        or key
                    ).strip()
                    or key,
                    "branch": str(run.get("branch") or entry.get("branch") or "").strip() or None,
                    "status": "main_verified" if str(run.get("status") or "").strip() == "completed" else "candidate",
                    "latest_run_id": str(run.get("run_id") or "").strip() or None,
                    "latest_run_summary": str(run.get("summary") or "").strip() or None,
                    "updated_at": str(run.get("updated_at") or run.get("created_at") or "").strip() or entry.get("updated_at"),
                    "incumbent": False,
                }
            )
            entries_by_key[key] = entry

        entries = sorted(
            entries_by_key.values(),
            key=lambda item: str(item.get("updated_at") or ""),
        )
        if entries:
            entries[-1]["incumbent"] = True
        incumbent = next((item for item in entries if item.get("incumbent")), None)

        scoreboard_payload = {
            "schema_version": 1,
            "quest_id": snapshot.get("quest_id"),
            "updated_at": utc_now(),
            "entry_count": len(entries),
            "incumbent_line_key": str((incumbent or {}).get("line_key") or "").strip() or None,
            "incumbent_title": str((incumbent or {}).get("title") or "").strip() or None,
            "entries": entries,
        }
        status_root = ensure_dir(quest_root / "artifacts" / "status")
        json_path = status_root / "method_scoreboard.json"
        md_path = status_root / "method_scoreboard.md"
        write_json(json_path, scoreboard_payload)
        lines = [
            "# Method Scoreboard",
            "",
            f"- Updated at: {scoreboard_payload['updated_at']}",
            f"- Incumbent: {scoreboard_payload.get('incumbent_title') or 'none'}",
            "",
            "## Entries",
            "",
        ]
        if entries:
            for item in entries:
                incumbent_tag = " [incumbent]" if item.get("incumbent") else ""
                lines.append(
                    f"- `{item.get('line_key')}`{incumbent_tag}: {item.get('title') or item.get('line_key')} | status={item.get('status') or 'unknown'} | branch={item.get('branch') or 'none'} | latest_run={item.get('latest_run_id') or 'none'}"
                )
                if item.get("latest_run_summary"):
                    lines.append(f"  - summary: {item['latest_run_summary']}")
        else:
            lines.append("- none")
        write_text(md_path, "\n".join(lines).rstrip() + "\n")
        return {
            "ok": True,
            "json_path": str(json_path),
            "md_path": str(md_path),
            "scoreboard": scoreboard_payload,
        }

    def read_quest_documents(
        self,
        quest_root: Path,
        *,
        names: list[str] | None = None,
        mode: str = "excerpt",
        max_lines: int = 12,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "excerpt").strip().lower() or "excerpt"
        if normalized_mode not in {"excerpt", "full"}:
            raise ValueError("read_quest_documents mode must be `excerpt` or `full`.")
        requested = [str(item or "").strip().lower() for item in (names or []) if str(item or "").strip()]
        if not requested:
            requested = ["brief", "plan", "status", "summary", "active_user_requirements"]
        document_paths = {
            "brief": quest_root / "brief.md",
            "plan": quest_root / "plan.md",
            "status": quest_root / "status.md",
            "summary": quest_root / "SUMMARY.md",
            "active_user_requirements": self.quest_service._active_user_requirements_path(quest_root),
        }
        items: list[dict[str, Any]] = []
        for name in requested:
            path = document_paths.get(name)
            if path is None:
                continue
            exists = path.exists()
            text = read_text(path, "") if exists else ""
            if normalized_mode == "excerpt":
                lines = [line.rstrip() for line in text.splitlines() if line.strip()]
                content = "\n".join(lines[:max_lines]).strip()
            else:
                content = text.strip()
            items.append(
                {
                    "name": name,
                    "path": str(path),
                    "exists": exists,
                    "content": content or None,
                }
            )
        return {
            "ok": True,
            "mode": normalized_mode,
            "count": len(items),
            "items": items,
        }

    def get_conversation_context(
        self,
        quest_root: Path,
        *,
        limit: int = 12,
        include_attachments: bool = False,
    ) -> dict[str, Any]:
        quest_id = self._quest_id(quest_root)
        records = self.quest_service.history(quest_id, limit=max(1, limit))
        items: list[dict[str, Any]] = []
        for record in records[-max(1, limit) :]:
            item = {
                "id": record.get("id"),
                "role": record.get("role"),
                "source": record.get("source"),
                "content": record.get("content"),
                "created_at": record.get("created_at"),
                "reply_to_interaction_id": record.get("reply_to_interaction_id"),
                "run_id": record.get("run_id"),
                "skill_id": record.get("skill_id"),
            }
            if include_attachments:
                item["attachments"] = [dict(value) for value in (record.get("attachments") or []) if isinstance(value, dict)]
            items.append(item)
        latest_user = next((item for item in reversed(items) if str(item.get("role") or "") == "user"), None)
        return {
            "ok": True,
            "count": len(items),
            "items": items,
            "latest_user_message": latest_user,
        }

    def get_analysis_campaign(self, quest_root: Path, campaign_id: str | None = None) -> dict[str, Any]:
        resolved_campaign_id = str(campaign_id or "").strip()
        if not resolved_campaign_id or resolved_campaign_id == "active":
            state = self.quest_service.read_research_state(quest_root)
            resolved_campaign_id = str(state.get("active_analysis_campaign_id") or "").strip()
        if not resolved_campaign_id:
            raise ValueError("No active analysis campaign is available.")
        manifest = self._read_analysis_manifest(quest_root, resolved_campaign_id)
        slices = [dict(item) for item in (manifest.get("slices") or []) if isinstance(item, dict)]
        pending_slices = [item for item in slices if str(item.get("status") or "pending").strip() == "pending"]
        completed_slices = [item for item in slices if str(item.get("status") or "").strip() != "pending"]
        next_pending_slice = pending_slices[0] if pending_slices else None
        return {
            "ok": True,
            "campaign_id": resolved_campaign_id,
            "title": str(manifest.get("title") or "").strip() or None,
            "goal": str(manifest.get("goal") or "").strip() or None,
            "active_idea_id": str(manifest.get("active_idea_id") or "").strip() or None,
            "parent_run_id": str(manifest.get("parent_run_id") or "").strip() or None,
            "parent_branch": str(manifest.get("parent_branch") or "").strip() or None,
            "parent_worktree_root": str(manifest.get("parent_worktree_root") or "").strip() or None,
            "paper_line_id": str(manifest.get("paper_line_id") or "").strip() or None,
            "paper_line_branch": str(manifest.get("paper_line_branch") or "").strip() or None,
            "paper_line_root": str(manifest.get("paper_line_root") or "").strip() or None,
            "selected_outline_ref": str(manifest.get("selected_outline_ref") or "").strip() or None,
            "campaign_origin": dict(manifest.get("campaign_origin") or {}) if isinstance(manifest.get("campaign_origin"), dict) else None,
            "todo_items": [dict(item) for item in (manifest.get("todo_items") or []) if isinstance(item, dict)],
            "slices": slices,
            "next_pending_slice_id": str((next_pending_slice or {}).get("slice_id") or "").strip() or None,
            "pending_slice_count": len(pending_slices),
            "completed_slice_count": len(completed_slices),
            "manifest": manifest,
        }

    def list_distill_candidates(self, quest_root: Path) -> dict[str, Any]:
        """Return undistilled completed-run candidates for the active quest.

        Result shape:
          {
            "ok": True,
            "experience_distill_on": bool,
            "reviewed_run_ids": list[str],
            "candidates": [
              {artifact_id, run_kind, status, summary, branch, created_at, path},
              ...
            ],
            "candidate_run_kinds": list[str],
          }
        """
        from .experience_distill import (
            DISTILL_CANDIDATE_RUN_KINDS,
            collect_reviewed_run_ids,
            read_distill_reviews,
            is_distill_on,
            iter_distill_candidate_records,
        )

        write_root = self._workspace_root_for(quest_root)
        artifacts_dir = write_root / "artifacts"
        if not is_distill_on(quest_root):
            return {
                "ok": True,
                "experience_distill_on": False,
                "reviewed_run_ids": [],
                "candidates": [],
                "candidate_run_kinds": sorted(DISTILL_CANDIDATE_RUN_KINDS),
                "cursor_run_created_at": None,
            }
        reviews = read_distill_reviews(artifacts_dir)
        reviewed_set, cursor_run_created_at = collect_reviewed_run_ids(reviews)
        candidates = []
        for record in iter_distill_candidate_records(artifacts_dir):
            aid = str(record.get("artifact_id") or "")
            if aid in reviewed_set:
                continue
            candidates.append(
                {
                    "artifact_id": aid,
                    "run_id": str(record.get("run_id") or ""),
                    "run_kind": str(record.get("run_kind") or ""),
                    "status": str(record.get("status") or ""),
                    # Truncate summary to keep MCP response payload bounded; the skill reads the full record via "path".
                    "summary": str(record.get("summary") or "")[:400],
                    "branch": str(record.get("branch") or ""),
                    "created_at": str(record.get("created_at") or ""),
                    "path": str(record.get("path") or ""),
                }
            )
        return {
            "ok": True,
            "experience_distill_on": True,
            "reviewed_run_ids": sorted(reviewed_set),
            "candidates": candidates,
            "candidate_run_kinds": sorted(DISTILL_CANDIDATE_RUN_KINDS),
            "cursor_run_created_at": cursor_run_created_at,
        }

    def list_paper_outlines(self, quest_root: Path) -> dict[str, Any]:
        selected_outline_path, selected_outline = self._read_selected_outline_record(quest_root)
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}

        selected_outline_id = str(selected_outline.get("outline_id") or "").strip()
        status_rank = {"candidate": 1, "revised": 2, "selected": 3}
        outlines_by_id: dict[str, dict[str, Any]] = {}
        seen_paper_roots: set[str] = set()
        paper_roots: list[Path] = []
        for root in (self._paper_root(quest_root), quest_root / "paper"):
            try:
                key = str(root.resolve())
            except FileNotFoundError:
                key = str(root)
            if key in seen_paper_roots:
                continue
            seen_paper_roots.add(key)
            paper_roots.append(root)

        for paper_root in paper_roots:
            for default_status, relative_parts in (
                ("candidate", ("outlines", "candidates")),
                ("revised", ("outlines", "revisions")),
            ):
                root = paper_root.joinpath(*relative_parts)
                if not root.exists():
                    continue
                for path in sorted(root.glob("outline-*.json")):
                    record = read_json(path, {})
                    if not isinstance(record, dict) or not record:
                        continue
                    outline_id = str(record.get("outline_id") or path.stem).strip() or path.stem
                    item = {
                        "outline_id": outline_id,
                        "title": str(record.get("title") or outline_id).strip() or outline_id,
                        "status": str(record.get("status") or default_status).strip() or default_status,
                        "review_result": str(record.get("review_result") or "").strip() or None,
                        "path": str(path),
                        "is_selected": outline_id == selected_outline_id,
                    }
                    current = outlines_by_id.get(outline_id)
                    if current is None or status_rank.get(str(item.get("status") or ""), 0) >= status_rank.get(
                        str(current.get("status") or ""),
                        0,
                    ):
                        outlines_by_id[outline_id] = item

        if selected_outline_id:
            selected_item = {
                "outline_id": selected_outline_id,
                "title": str(selected_outline.get("title") or selected_outline_id).strip() or selected_outline_id,
                "status": str(selected_outline.get("status") or "selected").strip() or "selected",
                "review_result": str(selected_outline.get("review_result") or "").strip() or None,
                "path": str(selected_outline_path),
                "is_selected": True,
            }
            current = outlines_by_id.get(selected_outline_id)
            if current is None or status_rank.get(str(selected_item.get("status") or ""), 0) >= status_rank.get(
                str(current.get("status") or ""),
                0,
            ):
                outlines_by_id[selected_outline_id] = selected_item
            else:
                current["is_selected"] = True

        outlines = list(outlines_by_id.values())
        outlines.sort(key=lambda item: (str(item.get("outline_id") or ""), str(item.get("status") or "")))
        return {
            "ok": True,
            "selected_outline_ref": selected_outline_id or None,
            "selected_outline": selected_outline or None,
            "count": len(outlines),
            "outlines": outlines,
        }

    def _previous_primary_best(
        self,
        quest_root: Path,
        *,
        primary_metric_id: str | None,
        direction: str | None,
    ) -> float | None:
        metric_id = str(primary_metric_id or "").strip()
        normalized_direction = str(direction or "maximize").strip().lower() or "maximize"
        if not metric_id:
            return None
        best: float | None = None
        for record in self._main_run_artifacts(quest_root):
            summary = normalize_metrics_summary(record.get("metrics_summary"))
            value = to_number(summary.get(metric_id))
            if value is None:
                continue
            if best is None:
                best = value
                continue
            if normalized_direction == "maximize":
                if value > best:
                    best = value
            elif value < best:
                best = value
        return best

    def _format_metric_value(self, value: object, decimals: int | None = None) -> str:
        numeric = to_number(value)
        if numeric is None:
            return str(value)
        if decimals is None:
            return f"{numeric:.4f}".rstrip("0").rstrip(".")
        return f"{numeric:.{decimals}f}"

    def _git_changed_files(self, workspace_root: Path) -> list[str]:
        result = run_command(["git", "status", "--porcelain"], cwd=workspace_root, check=False)
        if result.returncode != 0:
            return []
        paths: list[str] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            raw = line[3:].strip() if len(line) >= 4 else line.strip()
            if " -> " in raw:
                raw = raw.split(" -> ", 1)[1].strip()
            if raw:
                paths.append(raw)
        deduped: list[str] = []
        seen: set[str] = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)
        return deduped

    @staticmethod
    def _arxiv_content_from_item(item: dict[str, Any]) -> str:
        title = str(item.get("title") or item.get("display_name") or item.get("arxiv_id") or "arXiv paper").strip()
        authors = [str(author).strip() for author in (item.get("authors") or []) if str(author).strip()]
        categories = [str(category).strip() for category in (item.get("categories") or []) if str(category).strip()]
        abstract = str(item.get("abstract") or "").strip() or "Abstract unavailable."
        overview = str(item.get("overview") or "").strip()
        lines = [f"# {title}", "", f"- paper_id: {str(item.get('arxiv_id') or '').strip()}"]
        if item.get("metadata_source"):
            lines.append(f"- metadata_source: {item['metadata_source']}")
        if item.get("summary_source"):
            lines.append(f"- summary_source: {item['summary_source']}")
        if authors:
            lines.append(f"- authors: {', '.join(authors)}")
        if categories:
            lines.append(f"- categories: {', '.join(categories)}")
        if item.get("published_at"):
            lines.append(f"- published_at: {item['published_at']}")
        if item.get("version") is not None:
            lines.append(f"- version: v{item['version']}")
        if overview:
            lines.extend(["", "## Summary", "", overview])
            if abstract and abstract != overview:
                lines.extend(["", "## Abstract", "", abstract])
        else:
            lines.extend(["", "## Abstract", "", abstract])
        return "\n".join(lines).strip()

    @staticmethod
    def _arxiv_item_needs_refresh(item: dict[str, Any] | None) -> bool:
        if not isinstance(item, dict):
            return False
        title = str(item.get("title") or "").strip()
        lowered_title = title.lower()
        authors = item.get("authors") or []
        categories = item.get("categories") or []
        published_at = str(item.get("published_at") or "").strip()
        metadata_source = str(item.get("metadata_source") or "").strip()
        bibtex = str(item.get("bibtex") or "").strip()
        overview = str(item.get("overview") or "").strip()
        overview_markdown = str(item.get("overview_markdown") or "").strip()
        overview_source = str(item.get("overview_source") or "").strip()
        return (
            not title
            or title.startswith("#")
            or lowered_title.startswith("research paper analysis")
            or lowered_title.startswith("## research paper analysis")
            or not authors
            or not categories
            or not published_at
            or not metadata_source
            or not bibtex
            or (not overview and not overview_markdown and not overview_source)
        )

    def _refresh_arxiv_item_metadata(self, quest_root: Path, item: dict[str, Any]) -> dict[str, Any]:
        arxiv_id = str(item.get("arxiv_id") or "").strip()
        if not arxiv_id:
            return item
        metadata = fetch_arxiv_metadata(arxiv_id)
        if not metadata.get("ok"):
            return item
        summary = read_arxiv_content(arxiv_id, full_text=False)
        summary_source = summary.get("summary_source") if summary.get("ok") else None
        overview_source = summary.get("overview_source") if summary.get("ok") else None
        return self.arxiv_library.upsert_item(
            quest_root,
            {
                **item,
                "arxiv_id": metadata.get("paper_id") or arxiv_id,
                "title": metadata.get("title") or item.get("title") or arxiv_id,
                "display_name": metadata.get("title") or item.get("display_name") or arxiv_id,
                "authors": metadata.get("authors") or item.get("authors") or [],
                "categories": metadata.get("categories") or item.get("categories") or [],
                "abstract": metadata.get("abstract") or item.get("abstract") or "",
                "published_at": metadata.get("published_at") or item.get("published_at") or "",
                "version": metadata.get("version") if metadata.get("version") is not None else item.get("version"),
                "primary_class": metadata.get("primary_class") or item.get("primary_class") or "",
                "metadata_source": metadata.get("metadata_source") or item.get("metadata_source"),
                "metadata_status": "ready",
                "overview": summary.get("overview") or item.get("overview") or "",
                "overview_markdown": summary.get("overview_markdown") or item.get("overview_markdown") or "",
                "summary_source": summary_source or item.get("summary_source"),
                "overview_source": overview_source or summary_source or item.get("overview_source"),
                "bibtex": metadata.get("bibtex") or item.get("bibtex"),
                "abs_url": metadata.get("abs_url") or item.get("abs_url"),
                "pdf_url": metadata.get("pdf_url") or item.get("pdf_url"),
            },
        )

    @staticmethod
    def _arxiv_file_payload(quest_root: Path, item: dict[str, Any]) -> dict[str, Any]:
        relative = str(item.get("path") or "").strip()
        if not relative:
            return {}
        document_id = str(item.get("document_id") or f"questpath::{relative}").strip()
        return {
            "path": relative,
            "document_id": document_id,
            "pdf_rel_path": relative,
            "pdf_url": f"/api/quests/{quest_root.name}/documents/asset?document_id={document_id}",
        }

    def arxiv(
        self,
        paper_id: str | None = None,
        *,
        full_text: bool = False,
        mode: str = "read",
        quest_root: Path | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "read").strip().lower() or "read"
        if normalized_mode == "list":
            if quest_root is None:
                return {
                    "ok": False,
                    "mode": "list",
                    "error": "`quest_root` is required for `artifact.arxiv(mode='list')`.",
                }
            items = self.arxiv_library.list_items(quest_root)
            refreshed_any = False
            for item in items[:]:
                if not self._arxiv_item_needs_refresh(item):
                    continue
                refreshed = self._refresh_arxiv_item_metadata(quest_root, item)
                if refreshed != item:
                    refreshed_any = True
            if refreshed_any:
                items = self.arxiv_library.list_items(quest_root)
            return {
                "ok": True,
                "mode": "list",
                "items": items,
                "count": len(items),
            }

        if paper_id is None:
            return {
                "ok": False,
                "mode": normalized_mode,
                "error": "`paper_id` is required for `artifact.arxiv(mode='read')`.",
            }

        if quest_root is None:
            return {
                **read_arxiv_content(paper_id, full_text=full_text),
                "mode": normalized_mode,
            }

        entry = self.arxiv_library.mark_processing(quest_root, paper_id)
        cached_entry = self.arxiv_library.get_item(quest_root, paper_id)
        if cached_entry and self._arxiv_item_needs_refresh(cached_entry):
            refreshed = self._refresh_arxiv_item_metadata(quest_root, cached_entry)
            if refreshed:
                cached_entry = refreshed
        if (
            cached_entry
            and not full_text
            and cached_entry.get("abstract")
            and (cached_entry.get("summary_source") or cached_entry.get("metadata_status") == "pending")
        ):
            paper_ref = str(cached_entry.get("arxiv_id") or paper_id).strip()
            self.arxiv_library.queue_pdf_download(quest_root, str(cached_entry.get("arxiv_id") or paper_id))
            return {
                "ok": True,
                "mode": normalized_mode,
                "paper_id": paper_ref,
                "requested_full_text": full_text,
                "content_mode": "abstract",
                "source": "quest_arxiv_library",
                "source_url": f"https://arxiv.org/abs/{paper_ref}",
                "title": cached_entry.get("title"),
                "authors": cached_entry.get("authors") or [],
                "categories": cached_entry.get("categories") or [],
                "abstract": cached_entry.get("abstract") or "",
                "overview": cached_entry.get("overview") or "",
                "overview_markdown": cached_entry.get("overview_markdown") or "",
                "summary_source": cached_entry.get("summary_source"),
                "overview_source": cached_entry.get("overview_source"),
                "metadata_source": cached_entry.get("metadata_source"),
                "published_at": cached_entry.get("published_at") or "",
                "version": cached_entry.get("version"),
                "primary_class": cached_entry.get("primary_class") or "",
                "bibtex": cached_entry.get("bibtex") or "",
                "status": cached_entry.get("status"),
                "metadata_status": cached_entry.get("metadata_status"),
                "abs_url": f"https://arxiv.org/abs/{paper_ref}",
                "pdf_url": f"https://arxiv.org/pdf/{paper_ref}.pdf",
                "content": self._arxiv_content_from_item(cached_entry),
                "attempts": [],
                **self._arxiv_file_payload(quest_root, cached_entry),
            }

        fetched = read_arxiv_content(str(entry.get("arxiv_id") or paper_id), full_text=full_text)
        if not fetched.get("ok"):
            normalized_id = str(entry.get("arxiv_id") or paper_id).strip()
            placeholder = self.arxiv_library.upsert_item(
                quest_root,
                {
                    **(cached_entry or {}),
                    "arxiv_id": normalized_id,
                    "title": str((cached_entry or {}).get("title") or normalized_id).strip(),
                    "display_name": str((cached_entry or {}).get("display_name") or normalized_id).strip(),
                    "status": str((cached_entry or {}).get("status") or "processing").strip() or "processing",
                    "metadata_status": "pending",
                    "error": None,
                    "pdf_rel_path": self.arxiv_library.pdf_relative_path(normalized_id),
                    "abs_url": str((cached_entry or {}).get("abs_url") or f"https://arxiv.org/abs/{normalized_id}"),
                    "pdf_url": str((cached_entry or {}).get("pdf_url") or f"https://arxiv.org/pdf/{normalized_id}.pdf"),
                },
            )
            self.arxiv_library.queue_pdf_download(
                quest_root,
                normalized_id,
                pdf_url=str(placeholder.get("pdf_url") or "").strip() or None,
            )
            latest = self.arxiv_library.get_item(quest_root, normalized_id) or placeholder
            return {
                "ok": True,
                "mode": normalized_mode,
                "paper_id": normalized_id,
                "requested_full_text": full_text,
                "content_mode": "pending",
                "source": "quest_arxiv_library_partial",
                "source_url": latest.get("abs_url") or f"https://arxiv.org/abs/{normalized_id}",
                "title": latest.get("title"),
                "authors": latest.get("authors") or [],
                "categories": latest.get("categories") or [],
                "abstract": latest.get("abstract") or "",
                "overview": latest.get("overview") or "",
                "overview_markdown": latest.get("overview_markdown") or "",
                "summary_source": latest.get("summary_source"),
                "overview_source": latest.get("overview_source"),
                "metadata_source": latest.get("metadata_source"),
                "published_at": latest.get("published_at") or "",
                "version": latest.get("version"),
                "primary_class": latest.get("primary_class") or "",
                "bibtex": latest.get("bibtex") or "",
                "status": latest.get("status"),
                "metadata_status": "pending",
                "metadata_pending": True,
                "message": "Metadata is temporarily unavailable. Open the arXiv link directly while DeepScientist retries later.",
                "abs_url": latest.get("abs_url") or f"https://arxiv.org/abs/{normalized_id}",
                "pdf_url": latest.get("pdf_url") or f"https://arxiv.org/pdf/{normalized_id}.pdf",
                "content": self._arxiv_content_from_item(latest),
                "attempts": fetched.get("attempts") or [],
                "guidance": fetched.get("guidance"),
                **self._arxiv_file_payload(quest_root, latest),
            }

        saved = self.arxiv_library.upsert_item(
            quest_root,
            {
                **(cached_entry or {}),
                "arxiv_id": fetched.get("paper_id") or str(entry.get("arxiv_id") or paper_id),
                "title": fetched.get("title") or cached_entry.get("title") if cached_entry else fetched.get("title"),
                "authors": fetched.get("authors") or (cached_entry.get("authors") if cached_entry else []),
                "categories": fetched.get("categories") or (cached_entry.get("categories") if cached_entry else []),
                "abstract": fetched.get("abstract") or (cached_entry.get("abstract") if cached_entry else ""),
                "overview": fetched.get("overview") or (cached_entry.get("overview") if cached_entry else ""),
                "overview_markdown": fetched.get("overview_markdown") or (cached_entry.get("overview_markdown") if cached_entry else ""),
                "summary_source": fetched.get("summary_source") or (cached_entry.get("summary_source") if cached_entry else None),
                "overview_source": fetched.get("overview_source") or (cached_entry.get("overview_source") if cached_entry else None),
                "metadata_source": fetched.get("metadata_source") or (cached_entry.get("metadata_source") if cached_entry else None),
                "published_at": fetched.get("published_at") or (cached_entry.get("published_at") if cached_entry else ""),
                "version": fetched.get("version") if fetched.get("version") is not None else (cached_entry.get("version") if cached_entry else None),
                "primary_class": fetched.get("primary_class") or (cached_entry.get("primary_class") if cached_entry else ""),
                "bibtex": fetched.get("bibtex") or (cached_entry.get("bibtex") if cached_entry else None),
                "abs_url": fetched.get("abs_url") or (cached_entry.get("abs_url") if cached_entry else None),
                "pdf_url": fetched.get("pdf_url") or (cached_entry.get("pdf_url") if cached_entry else None),
                "display_name": fetched.get("title") or fetched.get("paper_id") or str(entry.get("arxiv_id") or paper_id),
                "pdf_rel_path": self.arxiv_library.pdf_relative_path(str(fetched.get("paper_id") or entry.get("arxiv_id") or paper_id)),
                "status": "processing",
                "metadata_status": "ready",
                "error": None,
            },
        )
        self.arxiv_library.queue_pdf_download(
            quest_root,
            str(saved.get("arxiv_id") or paper_id),
            pdf_url=str(fetched.get("pdf_url") or "").strip() or None,
        )
        latest = self.arxiv_library.get_item(quest_root, str(saved.get("arxiv_id") or paper_id)) or saved
        return {
            **fetched,
            "mode": normalized_mode,
            "status": latest.get("status"),
            "metadata_status": latest.get("metadata_status"),
            **self._arxiv_file_payload(quest_root, latest),
        }

    def record(
        self,
        quest_root: Path,
        payload: dict,
        *,
        checkpoint: bool | None = None,
        workspace_root: Path | None = None,
        commit_message: str | None = None,
        push: bool | None = None,
    ) -> dict:
        errors = validate_artifact_payload(payload)
        if errors:
            return {
                "ok": False,
                "errors": errors,
                "warnings": [],
            }

        write_root = self._workspace_root_for(quest_root, workspace_root)
        semantic_key = self._semantic_record_key(quest_root, payload, workspace_root=write_root)
        suppress_equivalent = (
            bool(payload.get("suppress_if_semantically_equivalent"))
            if "suppress_if_semantically_equivalent" in payload
            else str(payload.get("kind") or "").strip() in {"decision", "report"}
        )
        if suppress_equivalent and semantic_key:
            existing = self._latest_semantically_equivalent_artifact(
                quest_root,
                kind=str(payload.get("kind") or "").strip(),
                semantic_key=semantic_key,
            )
            if existing is not None:
                existing_record = dict(existing.get("payload") or {})
                guidance_vm = dict(existing_record.get("guidance_vm") or {}) if isinstance(existing_record.get("guidance_vm"), dict) else {}
                try:
                    from .experience_distill import maybe_inject_distill_finalize_gate

                    guidance_vm = maybe_inject_distill_finalize_gate(
                        quest_root, write_root / "artifacts", existing_record, guidance_vm,
                    )
                except Exception:
                    pass
                guidance_text = guidance_summary(guidance_vm) or guidance_for_kind(str(existing_record.get("kind") or payload.get("kind") or "report"))
                return {
                    "ok": True,
                    "status": "semantically_equivalent",
                    "artifact_id": existing_record.get("artifact_id"),
                    "path": str(existing.get("path") or ""),
                    "guidance": guidance_text,
                    "guidance_vm": guidance_vm,
                    "next_anchor": str(guidance_vm.get("recommended_skill") or "").strip() or None,
                    "recommended_skill_reads": [str(guidance_vm.get("recommended_skill") or "").strip()] if str(guidance_vm.get("recommended_skill") or "").strip() else [],
                    "suggested_artifact_calls": guidance_vm.get("suggested_artifact_calls") if isinstance(guidance_vm.get("suggested_artifact_calls"), list) else [],
                    "next_instruction": guidance_text,
                    "graph": None,
                    "recorded": existing_record.get("kind"),
                    "record": existing_record,
                    "workspace_root": str(existing_record.get("workspace_root") or write_root),
                    "artifact_path": str(existing.get("path") or ""),
                    "checkpoint": None,
                    "baseline_registry_entry": None,
                    "semantic_key": semantic_key,
                    "suppressed": True,
                }
        if (
            str(payload.get("kind") or "") == "decision"
            and str(payload.get("action") or "") == "distill_review"
        ):
            from .experience_distill import (
                iter_distill_candidate_records,
                _quest_workspace_artifact_dirs,
            )
            # Aggregate known run ids across every workspace's artifacts dir
            # (quest_root + each .ds/worktrees/*) — matches the multi-workspace
            # scan used by list_distill_candidates and evaluate_distill_gate_for_quest.
            # The MCP wrapper sets DS_WORKTREE_ROOT once at server start (= quest root)
            # and does not refresh it when activate_branch swaps the active worktree,
            # so write_root here is the quest root even when the run lives in a
            # worktree's artifacts/.
            known_run_ids: set[str] = set()
            for artifacts_dir in _quest_workspace_artifact_dirs(quest_root):
                for r in iter_distill_candidate_records(artifacts_dir):
                    known_run_ids.add(str(r.get("artifact_id") or ""))
                # Broader index scan: a distill_review can cite a run that was
                # previously a candidate but has since been excluded by run_kind.
                index_path = artifacts_dir / "_index.jsonl"
                if index_path.exists():
                    import json as _json
                    for line in index_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = _json.loads(line)
                        except Exception:
                            continue
                        if entry.get("kind") == "run":
                            known_run_ids.add(str(entry.get("artifact_id") or ""))
            unknown = [
                str(rid) for rid in (payload.get("reviewed_run_ids") or [])
                if str(rid) not in known_run_ids
            ]
            if unknown:
                raise ValueError(
                    "distill_review decision references unknown run artifact_ids: "
                    f"{unknown}"
                )
        record = self._build_record(quest_root, payload, workspace_root=write_root)
        if semantic_key:
            record["semantic_key"] = semantic_key
        guidance_vm = build_guidance_for_record(record)
        try:
            from .experience_distill import (
                maybe_inject_distill_finalize_gate,
                maybe_inject_distill_routing,
            )

            guidance_vm = maybe_inject_distill_routing(quest_root, record, guidance_vm)
            guidance_vm = maybe_inject_distill_finalize_gate(
                quest_root, write_root / "artifacts", record, guidance_vm,
            )
        except Exception:
            pass
        record["guidance_vm"] = guidance_vm
        guidance_text = guidance_summary(guidance_vm) or guidance_for_kind(record["kind"])
        recommended_skill = (
            str(guidance_vm.get("recommended_skill") or "").strip()
            if isinstance(guidance_vm, dict)
            else ""
        )
        recommended_skill_reads = [recommended_skill] if recommended_skill else []
        suggested_artifact_calls = (
            guidance_vm.get("suggested_artifact_calls") if isinstance(guidance_vm, dict) else []
        )
        if not isinstance(suggested_artifact_calls, list):
            suggested_artifact_calls = []
        next_anchor = recommended_skill or None
        next_instruction = guidance_text
        artifact_id = record["artifact_id"]
        artifact_path = self._artifact_path(write_root, record["kind"], artifact_id)
        previous_projection_state_kind, previous_projection_state = self.quest_service._artifact_projection_state(quest_root)
        write_json(artifact_path, record)
        append_jsonl(write_root / "artifacts" / "_index.jsonl", self._index_line(record, artifact_path))
        current_projection_state_kind, current_projection_state = self.quest_service._artifact_projection_state(quest_root)
        try:
            self.quest_service.update_artifact_projection(
                quest_root,
                record=record,
                artifact_path=artifact_path,
                workspace_root=write_root,
                previous_state_kind=previous_projection_state_kind,
                previous_state=previous_projection_state,
                current_state_kind=current_projection_state_kind,
                current_state=current_projection_state,
            )
        except Exception:
            pass
        try:
            self.quest_service.schedule_projection_refresh(
                quest_root,
                kinds=("details", "canvas", "git_canvas"),
                throttle_seconds=0.0,
            )
        except Exception:
            pass

        should_checkpoint = self._should_checkpoint(record["kind"]) if checkpoint is None else checkpoint
        checkpoint_result = None
        if should_checkpoint:
            checkpoint_result = self._checkpoint_with_optional_push(
                write_root,
                message=commit_message or f"artifact: {record['kind']} {artifact_id}",
                allow_empty=False,
                push=push,
            )
        graph_manifest = None
        if record["kind"] in {"baseline", "decision", "milestone", "run", "report", "approval", "graph"}:
            graph_manifest = export_git_graph(quest_root, ensure_dir(quest_root / "artifacts" / "graphs"))
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "type": "artifact.recorded",
                "quest_id": record["quest_id"],
                "artifact_id": artifact_id,
                "kind": record["kind"],
                "recorded_at": record["updated_at"],
                "status": record.get("status"),
                "summary": record.get("summary") or record.get("message"),
                "reason": record.get("reason"),
                "guidance": guidance_text,
                "guidance_vm": guidance_vm,
                "paths": record.get("paths") or {},
                "interaction_id": record.get("interaction_id"),
                "expects_reply": record.get("expects_reply"),
                "reply_mode": record.get("reply_mode"),
                "options": record.get("options") or [],
                "allow_free_text": record.get("allow_free_text"),
                "reply_schema": record.get("reply_schema") or {},
                "reply_to_interaction_id": record.get("reply_to_interaction_id"),
                "attachments": record.get("attachments") or [],
                "artifact_path": str(artifact_path),
                "workspace_root": str(write_root),
                "branch": record.get("branch"),
                "head_commit": record.get("head_commit"),
                "flow_type": record.get("flow_type"),
                "protocol_step": record.get("protocol_step"),
                "idea_id": record.get("idea_id"),
                "campaign_id": record.get("campaign_id"),
                "slice_id": record.get("slice_id"),
                "details": record.get("details") or {},
                "checkpoint": checkpoint_result,
            },
        )
        self._touch_quest_updated_at(quest_root)

        baseline_registry_entry = None
        if record["kind"] == "baseline" and record.get("publish_global"):
            baseline_registry_entry = self.baselines.publish(
                {
                    "baseline_id": record.get("baseline_id", artifact_id),
                    "name": record.get("name", record.get("baseline_id", artifact_id)),
                    "source": record.get(
                        "source",
                        {
                            "kind": "artifact_publish",
                            "quest_id": record["quest_id"],
                            "quest_root": str(quest_root),
                            "git_commit": head_commit(write_root),
                        },
                    ),
                    "path": record.get(
                        "path",
                        str(write_root / "baselines" / "local" / record.get("baseline_id", artifact_id)),
                    ),
                    "baseline_kind": record.get("baseline_kind", "reproduced"),
                    "task": record.get("task"),
                    "dataset": record.get("dataset"),
                    "primary_metric": record.get("primary_metric"),
                    "metrics_summary": record.get("metrics_summary", {}),
                    "environment": record.get("environment", {}),
                    "tags": record.get("tags", []),
                    "summary": record.get("summary", ""),
                    "codebase_id": record.get("codebase_id"),
                    "codebase_root_path": record.get("codebase_root_path"),
                    "default_variant_id": record.get("default_variant_id"),
                    "baseline_variants": record.get("baseline_variants", []),
                    "metric_contract": record.get("metric_contract"),
                    "metric_objectives": record.get("metric_objectives", []),
                    "baseline_metrics_path": record.get("baseline_metrics_path"),
                    "baseline_results_index_path": record.get("baseline_results_index_path"),
                }
            )
        if record["kind"] == "approval":
            close_target = str(record.get("reply_to_interaction_id") or record.get("decision_id") or "").strip()
            if close_target:
                self._close_interaction_request(
                    quest_root,
                    interaction_id=close_target,
                    closing_artifact_id=artifact_id,
                )

        return {
            "ok": True,
            "artifact_id": artifact_id,
            "path": str(artifact_path),
            "guidance": guidance_text,
            "guidance_vm": guidance_vm,
            "next_anchor": next_anchor,
            "recommended_skill_reads": recommended_skill_reads,
            "suggested_artifact_calls": suggested_artifact_calls,
            "next_instruction": next_instruction,
            "graph": graph_manifest,
            "recorded": record["kind"],
            "record": record,
            "workspace_root": str(write_root),
            "artifact_path": str(artifact_path),
            "checkpoint": checkpoint_result,
            "baseline_registry_entry": baseline_registry_entry,
        }

    def checkpoint(self, quest_root: Path, message: str, *, allow_empty: bool = False) -> dict:
        result = checkpoint_repo(quest_root, message, allow_empty=allow_empty)
        self._touch_quest_updated_at(quest_root)
        self._refresh_git_surfaces(quest_root)
        return {
            "ok": True,
            "message": message,
            "guidance": "Checkpoint created. Continue from the updated quest branch state.",
            **result,
        }

    def _refresh_git_surfaces(self, quest_root: Path) -> dict[str, Any]:
        projection_refresh = {
            "details": True,
            "canvas": True,
            "git_canvas": True,
            "graph": True,
        }
        try:
            self.quest_service.schedule_projection_refresh(
                quest_root,
                kinds=("details", "canvas", "git_canvas"),
                throttle_seconds=0.0,
            )
        except Exception:
            pass
        try:
            export_git_graph(quest_root, ensure_dir(quest_root / "artifacts" / "graphs"))
        except Exception:
            projection_refresh["graph"] = False
        return projection_refresh

    def _append_git_event(
        self,
        quest_root: Path,
        *,
        action: str,
        repo: Path,
        result: dict[str, Any],
    ) -> None:
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "type": "artifact.git",
                "quest_id": quest_root.name,
                "action": action,
                "repo": str(repo),
                "result": result,
                "recorded_at": utc_now(),
            },
        )

    def _record_git_operation_artifact(
        self,
        quest_root: Path,
        *,
        repo: Path,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        state = self.quest_service.read_research_state(quest_root)
        if self._collaboration_workspace_mode(state) != "copilot":
            return None

        normalized_action = str(action or "").strip().lower()
        before_branch = str(payload.get("before_branch") or "").strip() or None
        payload_branch = str(payload.get("branch") or "").strip() or None
        after_branch = (
            str(payload.get("after_branch") or "").strip()
            or payload_branch
            or before_branch
        )
        target_ref = str(payload.get("target_ref") or payload.get("target") or "").strip() or after_branch
        before_head = str(payload.get("before_head") or "").strip() or None
        after_head = str(payload.get("after_head") or payload.get("head") or payload.get("sha") or "").strip() or None
        commit_subject = str(payload.get("subject") or "").strip() or None
        changed_files = [
            str(item.get("path") or "").strip()
            for item in (payload.get("files") or [])
            if isinstance(item, dict) and str(item.get("path") or "").strip()
        ]

        should_record = False
        summary = ""
        reason = ""
        status = "completed"
        record_branch = after_branch
        parent_branch: str | None = None

        if normalized_action == "commit":
            if bool(payload.get("committed")) and after_branch:
                should_record = True
                record_branch = after_branch
                summary = (
                    f"Committed on `{after_branch}`: {commit_subject}"
                    if commit_subject
                    else f"Committed changes on `{after_branch}`."
                )
                reason = "A durable Git commit changed the active branch state."
        elif normalized_action == "branch":
            created = bool(payload.get("created"))
            switched = bool(after_branch and before_branch and after_branch != before_branch)
            create_from = str(payload.get("create_from") or "").strip() or before_branch
            if created or switched:
                should_record = True
                record_branch = target_ref or after_branch or payload_branch or before_branch
                if created and switched:
                    summary = f"Created and switched to `{target_ref}`."
                elif created:
                    summary = f"Created branch `{target_ref}`."
                else:
                    summary = f"Switched to existing branch `{after_branch}`."
                reason = "A durable Git branch operation changed the available branch graph."
                status = "completed" if created else "existing"
                if created:
                    parent_branch = create_from
        elif normalized_action == "checkout":
            switched = bool(after_branch and before_branch and after_branch != before_branch)
            moved_head = bool(after_head and before_head and after_head != before_head)
            if bool(payload.get("ok")) and (switched or moved_head):
                should_record = True
                record_branch = after_branch or target_ref
                summary = (
                    f"Checked out `{target_ref}`."
                    if target_ref
                    else f"Switched workspace branch from `{before_branch or 'unknown'}` to `{after_branch or 'unknown'}`."
                )
                reason = "A Git checkout changed the active branch or HEAD for the workspace."

        if not should_record or not record_branch:
            return None

        worktree_root: str | None = None
        worktree_rel_path: str | None = None
        if after_branch and record_branch == after_branch:
            worktree_root = str(repo)
            worktree_rel_path = self._workspace_relative(quest_root, repo)

        return self.record(
            quest_root,
            {
                "kind": "report",
                "status": status,
                "report_type": "git_operation",
                "suppress_if_semantically_equivalent": False,
                "report_id": generate_id("report"),
                "summary": summary,
                "reason": reason,
                "branch": record_branch,
                "parent_branch": parent_branch,
                "head_commit": after_head,
                "worktree_root": worktree_root,
                "worktree_rel_path": worktree_rel_path,
                "flow_type": "git_operation",
                "protocol_step": normalized_action,
                "paths": {
                    "workspace_root": str(repo),
                },
                "details": {
                    "git_action": normalized_action,
                    "target_ref": target_ref,
                    "create_from": str(payload.get("create_from") or "").strip() or None,
                    "before_branch": before_branch,
                    "after_branch": after_branch,
                    "record_branch": record_branch,
                    "before_head": before_head,
                    "after_head": after_head,
                    "commit_subject": commit_subject,
                    "changed_files": changed_files,
                },
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=False,
            workspace_root=repo,
        )

    def _git_status_payload(self, repo: Path) -> dict[str, Any]:
        result = run_command(["git", "status", "--porcelain", "-b"], cwd=repo, check=False)
        lines = [line.rstrip() for line in str(result.stdout or "").splitlines()]
        branch_line = lines[0] if lines else ""
        changes: list[dict[str, Any]] = []
        staged_count = 0
        unstaged_count = 0
        untracked_count = 0
        for raw in lines[1:]:
            if not raw:
                continue
            status = raw[:2]
            path = raw[3:].strip() if len(raw) > 3 else raw.strip()
            staged = status[0] not in {" ", "?"}
            unstaged = status[1] not in {" "}
            untracked = status == "??"
            if staged:
                staged_count += 1
            if unstaged:
                unstaged_count += 1
            if untracked:
                untracked_count += 1
            changes.append(
                {
                    "path": path,
                    "status": status,
                    "staged": staged,
                    "unstaged": unstaged,
                    "untracked": untracked,
                }
            )
        return {
            "ok": result.returncode == 0,
            "repo": str(repo),
            "branch": current_branch(repo),
            "head": head_commit(repo),
            "branch_status": branch_line[3:].strip() if branch_line.startswith("## ") else None,
            "has_changes": bool(changes),
            "staged_count": staged_count,
            "unstaged_count": unstaged_count,
            "untracked_count": untracked_count,
            "changes": changes,
        }

    def git_action(
        self,
        quest_root: Path,
        *,
        action: str,
        workspace_root: Path | None = None,
        message: str | None = None,
        ref: str | None = None,
        base: str | None = None,
        head: str | None = None,
        sha: str | None = None,
        path: str | None = None,
        branch: str | None = None,
        create_from: str | None = None,
        limit: int = 30,
        allow_empty: bool = False,
        checkout_new_branch: bool = False,
    ) -> dict[str, Any]:
        resolved_action = str(action or "").strip().lower()
        repo = self._workspace_root_for(quest_root, workspace_root=workspace_root)
        before_branch = current_branch(repo)
        before_head = head_commit(repo)
        projection_refresh = {
            "details": False,
            "canvas": False,
            "git_canvas": False,
            "graph": False,
        }

        if resolved_action == "status":
            result = self._git_status_payload(repo)
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": result,
            }

        if resolved_action == "commit":
            commit_message = str(message or "").strip() or "Update workspace"
            result = checkpoint_repo(repo, commit_message, allow_empty=allow_empty)
            self._touch_quest_updated_at(quest_root)
            projection_refresh = self._refresh_git_surfaces(quest_root)
            if result.get("committed"):
                head_sha = str(result.get("head") or "").strip()
                if head_sha:
                    try:
                        detail = commit_detail(repo, sha=head_sha)
                    except Exception:
                        detail = {
                            "sha": head_sha,
                            "short_sha": head_sha[:7],
                            "subject": commit_message,
                            "parents": [],
                        }
                else:
                    detail = {
                        "sha": None,
                        "short_sha": None,
                        "subject": commit_message,
                        "parents": [],
                    }
            else:
                detail = {
                    "sha": result.get("head"),
                    "short_sha": str(result.get("head") or "")[:7] or None,
                    "subject": commit_message,
                    "parents": [],
                }
            payload = {
                "committed": bool(result.get("committed")),
                "branch": result.get("branch"),
                "head": result.get("head"),
                "before_branch": before_branch,
                "before_head": before_head,
                "after_branch": result.get("branch"),
                "after_head": result.get("head"),
                "target_ref": result.get("branch") or before_branch,
                "stdout": result.get("stdout"),
                "stderr": result.get("stderr"),
                **detail,
            }
            self._append_git_event(quest_root, action=resolved_action, repo=repo, result=payload)
            self._record_git_operation_artifact(
                quest_root,
                repo=repo,
                action=resolved_action,
                payload=payload,
            )
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": payload,
            }

        if resolved_action == "branch":
            branch_name = str(branch or "").strip()
            if not branch_name:
                return {"ok": False, "action": resolved_action, "message": "`branch` is required."}
            result = ensure_branch(repo, branch_name, start_point=create_from, checkout=checkout_new_branch)
            payload = {
                **result,
                "before_branch": before_branch,
                "before_head": before_head,
                "after_branch": current_branch(repo),
                "after_head": head_commit(repo),
                "target_ref": branch_name,
                "create_from": str(create_from or "").strip() or before_branch,
            }
            self._touch_quest_updated_at(quest_root)
            projection_refresh = self._refresh_git_surfaces(quest_root)
            self._append_git_event(quest_root, action=resolved_action, repo=repo, result=payload)
            self._record_git_operation_artifact(
                quest_root,
                repo=repo,
                action=resolved_action,
                payload=payload,
            )
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": payload,
            }

        if resolved_action == "checkout":
            target = str(branch or ref or sha or head or "").strip()
            if not target:
                return {"ok": False, "action": resolved_action, "message": "One of `branch`, `ref`, `sha`, or `head` is required."}
            result = run_command(["git", "checkout", target], cwd=repo, check=False)
            payload = {
                "ok": result.returncode == 0,
                "target": target,
                "branch": current_branch(repo),
                "head": head_commit(repo),
                "before_branch": before_branch,
                "before_head": before_head,
                "after_branch": current_branch(repo),
                "after_head": head_commit(repo),
                "target_ref": target,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            self._touch_quest_updated_at(quest_root)
            projection_refresh = self._refresh_git_surfaces(quest_root)
            self._append_git_event(quest_root, action=resolved_action, repo=repo, result=payload)
            self._record_git_operation_artifact(
                quest_root,
                repo=repo,
                action=resolved_action,
                payload=payload,
            )
            return {
                "ok": result.returncode == 0,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": payload,
            }

        if resolved_action == "log":
            target_ref = str(ref or branch or "").strip() or current_branch(repo)
            result = log_ref_history(repo, ref=target_ref, base=(base or "").strip() or None, limit=limit)
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": result,
            }

        if resolved_action == "show":
            target_sha = str(sha or ref or head or "").strip()
            if not target_sha:
                return {"ok": False, "action": resolved_action, "message": "`sha` or `ref` is required."}
            result = commit_detail(repo, sha=target_sha)
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": result,
            }

        if resolved_action == "diff":
            target_path = str(path or "").strip() or None
            if sha:
                result = commit_detail(repo, sha=sha) if not target_path else diff_file_for_commit(repo, sha=sha, path=target_path)
            elif base and head:
                result = (
                    diff_file_between_refs(repo, base=base, head=head, path=target_path)
                    if target_path
                    else compare_refs(repo, base=base, head=head)
                )
            else:
                return {
                    "ok": False,
                    "action": resolved_action,
                    "message": "Provide `sha` for commit diff or `base` and `head` for compare diff.",
                }
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": result,
            }

        if resolved_action == "graph":
            projection_refresh = self._refresh_git_surfaces(quest_root)
            return {
                "ok": True,
                "action": resolved_action,
                "quest_id": quest_root.name,
                "current_ref": current_branch(repo),
                "head": head_commit(repo),
                "projection_refresh": projection_refresh,
                "result": self.quest_service.git_commit_canvas(quest_root.name),
            }

        return {
            "ok": False,
            "action": resolved_action,
            "message": "Unsupported git action. Use status, commit, branch, checkout, log, show, diff, or graph.",
        }

    def prepare_branch(
        self,
        quest_root: Path,
        *,
        run_id: str | None = None,
        idea_id: str | None = None,
        branch: str | None = None,
        branch_kind: str = "run",
        create_worktree_flag: bool = True,
        start_point: str | None = None,
    ) -> dict:
        state = self.quest_service.read_research_state(quest_root)
        parent_branch = (
            str(start_point or "").strip()
            or str(state.get("current_workspace_branch") or "").strip()
            or str(state.get("research_head_branch") or "").strip()
            or current_branch(self._workspace_root_for(quest_root))
            or current_branch(quest_root)
        )
        start_ref = start_point or parent_branch
        branch_name = branch or self._default_branch_name(quest_root, run_id=run_id, idea_id=idea_id, branch_kind=branch_kind)
        branch_result = ensure_branch(quest_root, branch_name, start_point=start_ref, checkout=False)
        worktree_result = None
        worktree_root = None
        if create_worktree_flag:
            worktree_root = self._prepare_branch_worktree_root(
                quest_root,
                branch_name=branch_name,
                branch_kind=branch_kind,
                run_id=run_id,
                idea_id=idea_id,
            )
            worktree_result = create_worktree(
                quest_root,
                branch=branch_name,
                worktree_root=worktree_root,
                start_point=start_ref,
            )
        artifact_result = self.record(
            quest_root,
            {
                "kind": "decision",
                "status": "prepared",
                "verdict": "prepared",
                "action": "prepare_branch",
                "reason": f"Prepared branch `{branch_name}` for the next quest step.",
                "branch": branch_name,
                "run_id": run_id,
                "idea_id": idea_id,
                "branch_kind": branch_kind,
                "parent_branch": parent_branch,
                "start_point": start_ref,
                "worktree_root": str(worktree_root) if worktree_root else None,
                "workspace_mode": self._workspace_mode_for_branch(branch_name, has_idea=bool(idea_id)),
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=False,
            workspace_root=worktree_root if worktree_root else None,
        )
        return {
            "ok": True,
            "branch": branch_name,
            "branch_result": branch_result,
            "worktree": worktree_result,
            "worktree_root": str(worktree_root) if worktree_root else None,
            "parent_branch": parent_branch,
            "start_point": start_ref,
            "guidance": "Use this branch/worktree for the isolated idea or run. Keep durable outputs under quest_root.",
            "artifact": artifact_result,
        }

    def activate_branch(
        self,
        quest_root: Path,
        *,
        branch: str | None = None,
        idea_id: str | None = None,
        run_id: str | None = None,
        anchor: str | None = "auto",
        promote_to_head: bool = False,
        create_worktree_if_missing: bool = True,
    ) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        active_campaign_id = str(state.get("active_analysis_campaign_id") or "").strip() or None
        if active_campaign_id:
            raise ValueError(
                "activate_branch cannot run while an analysis campaign is active. "
                "Finish or close the campaign first."
            )

        target = self._resolve_branch_activation_target(
            quest_root,
            branch=branch,
            idea_id=idea_id,
            run_id=run_id,
        )
        branch_name = str(target.get("branch") or "").strip()
        if str(target.get("branch_kind") or self._branch_kind_from_name(branch_name)).strip().lower() != "paper":
            self._require_baseline_gate_open(quest_root, action="activate_branch")
        resolved_idea_id = str(target.get("idea_id") or "").strip() or None
        latest_main_run = (
            dict(target.get("latest_main_run") or {})
            if isinstance(target.get("latest_main_run"), dict)
            else {}
        )
        latest_idea = (
            dict(target.get("latest_idea") or {})
            if isinstance(target.get("latest_idea"), dict)
            else {}
        )
        branch_kind = str(target.get("branch_kind") or self._branch_kind_from_name(branch_name)).strip().lower() or "branch"
        source_parent_branch = str(target.get("parent_branch") or "").strip() or None

        workspace_root = self._branch_workspace_root(quest_root, branch_name)
        worktree_result = None
        worktree_created = False
        if workspace_root is None:
            recorded_root = str(target.get("recorded_worktree_root") or "").strip()
            if recorded_root:
                candidate = Path(recorded_root)
                if candidate.exists():
                    workspace_root = candidate
            if workspace_root is None:
                if not create_worktree_if_missing:
                    raise FileNotFoundError(
                        f"No existing worktree is available for branch `{branch_name}` and create_worktree_if_missing=False."
                    )
                workspace_root = Path(target.get("suggested_worktree_root") or "")
                worktree_result = create_worktree(
                    quest_root,
                    branch=branch_name,
                    worktree_root=workspace_root,
                    start_point=branch_name,
                )
                if not bool(worktree_result.get("ok")):
                    raise RuntimeError(
                        f"Failed to activate branch `{branch_name}`: {worktree_result.get('stderr') or 'worktree creation failed.'}"
                    )
                worktree_created = True

        resolved_workspace_root = workspace_root or quest_root
        idea_md_path = (
            str(target.get("idea_md_path") or "").strip()
            or str((dict(latest_idea.get("paths") or {}) if isinstance(latest_idea.get("paths"), dict) else {}).get("idea_md") or "").strip()
            or (str(resolved_workspace_root / "memory" / "ideas" / resolved_idea_id / "idea.md") if resolved_idea_id else "")
        )
        idea_draft_path = (
            str(target.get("idea_draft_path") or "").strip()
            or str((dict(latest_idea.get("paths") or {}) if isinstance(latest_idea.get("paths"), dict) else {}).get("idea_draft_md") or "").strip()
            or (str(resolved_workspace_root / "memory" / "ideas" / resolved_idea_id / "draft.md") if resolved_idea_id else "")
        )
        resolved_idea_md_path = idea_md_path if resolved_idea_id else None
        resolved_idea_draft_path = idea_draft_path if resolved_idea_id else None
        has_main_result = bool(latest_main_run.get("run_id"))
        if branch_kind == "paper":
            next_anchor = "write" if str(anchor or "auto").strip().lower() == "auto" else self._resolve_activate_branch_anchor(
                anchor=anchor,
                has_idea=bool(resolved_idea_id),
                has_main_result=has_main_result,
            )
        else:
            next_anchor = self._resolve_activate_branch_anchor(
                anchor=anchor,
                has_idea=bool(resolved_idea_id),
                has_main_result=has_main_result,
            )
        workspace_mode, branch_mode = self._resolve_workspace_modes(
            state,
            branch_name=branch_name,
            has_idea=bool(resolved_idea_id),
        )
        source_run_id = (
            str(target.get("run_id") or "").strip()
            or str(latest_main_run.get("run_id") or "").strip()
            or None
        )

        artifact = self.record(
            quest_root,
            {
                "kind": "decision",
                "status": "completed",
                "verdict": "continue",
                "action": "activate_branch",
                "summary": f"Activated durable branch `{branch_name}` as the current workspace.",
                "reason": (
                    "Return to an existing research branch without creating a new lineage node, "
                    "so follow-up experiments or decisions continue from the correct historical context."
                ),
                "idea_id": resolved_idea_id,
                "run_id": str(latest_main_run.get("run_id") or "").strip() or None,
                "branch": branch_name,
                "worktree_root": str(resolved_workspace_root),
                "worktree_rel_path": self._workspace_relative(quest_root, resolved_workspace_root),
                "flow_type": "branch_activation",
                "protocol_step": "activate",
                "details": {
                    "activate_branch_by": (
                        "idea_id"
                        if str(idea_id or "").strip()
                        else "run_id"
                        if str(run_id or "").strip()
                        else "branch"
                    ),
                    "promote_to_head": bool(promote_to_head),
                    "worktree_created": worktree_created,
                    "next_anchor": next_anchor,
                    "workspace_mode": branch_mode,
                    "latest_main_run_id": str(latest_main_run.get("run_id") or "").strip() or None,
                    "branch_kind": branch_kind,
                    "paper_parent_branch": source_parent_branch if branch_kind == "paper" else None,
                },
            },
            checkpoint=False,
            workspace_root=resolved_workspace_root,
        )

        research_state_updates: dict[str, Any] = {
            "active_idea_id": resolved_idea_id,
            "current_workspace_branch": branch_name,
            "current_workspace_root": str(resolved_workspace_root),
            "active_idea_md_path": resolved_idea_md_path,
            "active_idea_draft_path": resolved_idea_draft_path,
            "active_analysis_campaign_id": None,
            "analysis_parent_branch": None,
            "analysis_parent_worktree_root": None,
            "paper_parent_branch": source_parent_branch if branch_kind == "paper" else None,
            "paper_parent_worktree_root": (
                str(self._branch_workspace_root(quest_root, source_parent_branch))
                if branch_kind == "paper" and source_parent_branch and self._branch_workspace_root(quest_root, source_parent_branch)
                else None
            ),
            "paper_parent_run_id": source_run_id if branch_kind == "paper" else None,
            "next_pending_slice_id": None,
            "workspace_mode": workspace_mode,
            "workspace_branch_mode": branch_mode,
            "last_flow_type": "branch_activation",
        }
        if promote_to_head:
            research_state_updates["research_head_branch"] = branch_name
            research_state_updates["research_head_worktree_root"] = str(resolved_workspace_root)
        research_state = self.quest_service.update_research_state(quest_root, **research_state_updates)
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor=next_anchor)

        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=(
                f"Activated branch `{branch_name}`.\n"
                f"- Worktree: `{resolved_workspace_root}`\n"
                f"- Active idea: `{resolved_idea_id or 'none'}`\n"
                f"- Latest main run: `{str(latest_main_run.get('run_id') or '').strip() or 'none'}`\n"
                f"- Promoted to head: `{bool(promote_to_head)}`\n"
                f"- Next anchor: `{next_anchor}`"
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "branch_activation",
                    "branch": branch_name,
                    "worktree_root": str(resolved_workspace_root),
                    "idea_id": resolved_idea_id,
                    "latest_main_run_id": str(latest_main_run.get("run_id") or "").strip() or None,
                    "next_anchor": next_anchor,
                    "promote_to_head": bool(promote_to_head),
                }
            ],
        )
        return {
            "ok": True,
            "branch": branch_name,
            "worktree_root": str(resolved_workspace_root),
            "idea_id": resolved_idea_id,
            "latest_main_run_id": str(latest_main_run.get("run_id") or "").strip() or None,
            "branch_kind": branch_kind,
            "source_parent_branch": source_parent_branch,
            "idea_md_path": resolved_idea_md_path,
            "idea_draft_path": resolved_idea_draft_path,
            "workspace_mode": workspace_mode,
            "next_anchor": next_anchor,
            "promote_to_head": bool(promote_to_head),
            "worktree_created": worktree_created,
            "worktree": worktree_result,
            "artifact": artifact,
            "interaction": interaction,
            "research_state": research_state,
        }

    def _promote_workspace_to_run_branch(
        self,
        quest_root: Path,
        *,
        run_id: str,
        idea_id: str | None,
        workspace_root: Path,
        current_branch_name: str,
    ) -> tuple[str, str | None, bool]:
        branch_kind = self._branch_kind_from_name(current_branch_name)
        if branch_kind == "paper":
            raise ValueError(
                "record_main_experiment cannot run while the active workspace is a paper branch. "
                "Return to the evidence branch or create a new run branch first."
            )
        if branch_kind == "run":
            prepare_record = self._latest_prepare_branch_record(quest_root, current_branch_name)
            parent_branch = str(prepare_record.get("parent_branch") or "").strip() or None
            return current_branch_name, parent_branch, False

        target_branch = self._default_branch_name(quest_root, run_id=run_id, idea_id=idea_id, branch_kind="run")
        if branch_exists(quest_root, target_branch):
            raise ValueError(
                f"Run branch `{target_branch}` already exists. Reuse that run branch or choose a new `run_id`."
            )

        ensure_branch(quest_root, target_branch, start_point=current_branch_name, checkout=False)
        run_command(["git", "switch", target_branch], cwd=workspace_root, check=True)
        self.record(
            quest_root,
            {
                "kind": "decision",
                "status": "prepared",
                "verdict": "prepared",
                "action": "prepare_branch",
                "reason": f"Materialized a dedicated main-experiment branch `{target_branch}` before durable recording.",
                "branch": target_branch,
                "run_id": run_id,
                "idea_id": idea_id,
                "branch_kind": "run",
                "parent_branch": current_branch_name,
                "start_point": current_branch_name,
                "worktree_root": str(workspace_root),
                "workspace_mode": "run",
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=False,
            workspace_root=workspace_root,
        )
        current_state = self.quest_service.read_research_state(quest_root)
        workspace_mode, branch_mode = self._resolve_workspace_modes(
            current_state,
            branch_name=target_branch,
            has_idea=bool(idea_id),
        )
        self.quest_service.update_research_state(
            quest_root,
            active_idea_id=idea_id,
            current_workspace_branch=target_branch,
            current_workspace_root=str(workspace_root),
            research_head_branch=target_branch,
            research_head_worktree_root=str(workspace_root),
            active_analysis_campaign_id=None,
            analysis_parent_branch=None,
            analysis_parent_worktree_root=None,
            paper_parent_branch=None,
            paper_parent_worktree_root=None,
            paper_parent_run_id=None,
            workspace_mode=workspace_mode,
            workspace_branch_mode=branch_mode,
            last_flow_type="main_experiment_branch",
        )
        return target_branch, current_branch_name, True

    def _ensure_active_paper_workspace(
        self,
        quest_root: Path,
        *,
        source_branch: str | None = None,
        source_run_id: str | None = None,
        source_idea_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        current_branch_name = (
            str(state.get("current_workspace_branch") or "").strip()
            or current_branch(self._workspace_root_for(quest_root))
        )
        current_workspace_root = self._workspace_root_for(quest_root)
        if self._active_workspace_branch_mode(state, branch_name=current_branch_name) == "paper":
            return {
                "ok": True,
                "branch": current_branch_name,
                "worktree_root": str(current_workspace_root),
                "source_branch": str(state.get("paper_parent_branch") or "").strip() or None,
                "source_run_id": str(state.get("paper_parent_run_id") or "").strip() or None,
                "source_idea_id": str(state.get("active_idea_id") or "").strip() or None,
            }

        resolved_source_branch = (
            str(source_branch or "").strip()
            or str(state.get("paper_parent_branch") or "").strip()
            or str(state.get("current_workspace_branch") or "").strip()
            or str(state.get("research_head_branch") or "").strip()
            or current_branch(current_workspace_root)
        )
        if not resolved_source_branch:
            raise ValueError("Unable to resolve the source branch for the paper workspace.")

        latest_main_run = self._latest_main_run_for_branch(quest_root, resolved_source_branch)
        resolved_run_id = (
            str(source_run_id or "").strip()
            or str((latest_main_run or {}).get("run_id") or "").strip()
            or None
        )
        resolved_idea_id = (
            str(source_idea_id or "").strip()
            or str((latest_main_run or {}).get("idea_id") or "").strip()
            or str(state.get("active_idea_id") or "").strip()
            or None
        )
        paper_branch = (
            self._default_branch_name(quest_root, run_id=resolved_run_id, idea_id=resolved_idea_id, branch_kind="paper")
            if resolved_run_id
            else f"paper/{slugify(resolved_source_branch, 'paper')}"
        )
        if not branch_exists(quest_root, paper_branch):
            self.prepare_branch(
                quest_root,
                run_id=resolved_run_id,
                idea_id=resolved_idea_id,
                branch=paper_branch,
                branch_kind="paper",
                create_worktree_flag=True,
                start_point=resolved_source_branch,
            )
        activated = self.activate_branch(
            quest_root,
            branch=paper_branch,
            anchor="write",
            promote_to_head=False,
            create_worktree_if_missing=True,
        )
        return {
            **activated,
            "source_branch": resolved_source_branch,
            "source_run_id": resolved_run_id,
            "source_idea_id": resolved_idea_id,
        }

    def submit_idea(
        self,
        quest_root: Path,
        *,
        mode: str = "create",
        submission_mode: str = "line",
        idea_id: str | None = None,
        lineage_intent: str | None = None,
        title: str,
        problem: str = "",
        hypothesis: str = "",
        mechanism: str = "",
        method_brief: str = "",
        selection_scores: dict[str, Any] | None = None,
        mechanism_family: str = "",
        change_layer: str = "",
        source_lens: str = "",
        expected_gain: str = "",
        evidence_paths: list[str] | None = None,
        risks: list[str] | None = None,
        decision_reason: str = "",
        foundation_ref: dict[str, Any] | str | None = None,
        foundation_reason: str = "",
        next_target: str = "experiment",
        draft_markdown: str = "",
        source_candidate_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "create").strip().lower()
        if normalized_mode not in {"create", "revise"}:
            raise ValueError("submit_idea mode must be `create` or `revise`.")
        normalized_submission_mode = str(submission_mode or "line").strip().lower() or "line"
        if normalized_submission_mode not in {"line", "candidate"}:
            raise ValueError("submit_idea submission_mode must be `line` or `candidate`.")
        self._require_baseline_gate_open(quest_root, action="submit_idea")

        quest_id = self._quest_id(quest_root)
        state = self.quest_service.read_research_state(quest_root)
        normalized_method_brief = str(method_brief or "").strip()
        normalized_selection_scores = self._normalize_selection_scores(selection_scores)
        normalized_mechanism_family = str(mechanism_family or "").strip() or None
        normalized_change_layer = str(change_layer or "").strip() or None
        normalized_source_lens = str(source_lens or "").strip() or None
        evidence_paths = [str(item).strip() for item in (evidence_paths or []) if str(item).strip()]
        risks = [str(item).strip() for item in (risks or []) if str(item).strip()]
        next_target = str(next_target or "experiment").strip().lower() or "experiment"
        normalized_lineage_intent = self._normalize_lineage_intent(lineage_intent)
        from ..prompts.builder import current_standard_skills

        next_anchor = next_target if next_target in current_standard_skills(repo_root()) else "experiment"

        if normalized_mode == "create":
            resolved_idea_id = str(idea_id or generate_id("idea")).strip()
            active_branch = (
                str(state.get("current_workspace_branch") or "").strip()
                or str(state.get("research_head_branch") or "").strip()
                or current_branch(self._workspace_root_for(quest_root))
            )
            active_parent_branch = self._idea_parent_branch(self._latest_idea_for_branch(quest_root, active_branch))
            if foundation_ref is None:
                normalized_lineage_intent, parent_branch, foundation = self._infer_default_idea_lineage(
                    quest_root,
                    state=state,
                    lineage_intent=normalized_lineage_intent,
                )
            else:
                foundation = self._resolve_idea_foundation(
                    quest_root,
                    state=state,
                    foundation_ref=foundation_ref,
                )
                parent_branch = str(foundation.get("branch") or "").strip()
                if not normalized_lineage_intent:
                    normalized_lineage_intent = self._infer_lineage_intent_from_parent_branch(
                        active_branch=active_branch,
                        active_parent_branch=active_parent_branch,
                        parent_branch=parent_branch,
                    )
            if not parent_branch:
                raise ValueError("Unable to resolve a starting branch for the new idea.")
            if normalized_submission_mode == "candidate":
                candidate_root = self._idea_candidate_root(quest_root, resolved_idea_id)
                idea_md_path = candidate_root / "idea.md"
                idea_draft_path = candidate_root / "draft.md"
                markdown = self._build_candidate_idea_markdown(
                    idea_id=resolved_idea_id,
                    quest_id=quest_id,
                    title=title,
                    problem=problem,
                    hypothesis=hypothesis,
                    mechanism=mechanism,
                    expected_gain=expected_gain,
                    risks=risks,
                    evidence_paths=evidence_paths,
                    decision_reason=decision_reason,
                    next_target=next_target,
                    candidate_root=candidate_root,
                    method_brief=normalized_method_brief,
                    selection_scores=normalized_selection_scores,
                    mechanism_family=normalized_mechanism_family or "",
                    change_layer=normalized_change_layer or "",
                    source_lens=normalized_source_lens or "",
                    foundation_ref=foundation,
                    foundation_reason=foundation_reason,
                    lineage_intent=normalized_lineage_intent,
                )
                draft = self._build_candidate_idea_draft_markdown(
                    idea_id=resolved_idea_id,
                    quest_id=quest_id,
                    title=title,
                    problem=problem,
                    hypothesis=hypothesis,
                    mechanism=mechanism,
                    expected_gain=expected_gain,
                    risks=risks,
                    evidence_paths=evidence_paths,
                    decision_reason=decision_reason,
                    next_target=next_target,
                    candidate_root=candidate_root,
                    method_brief=normalized_method_brief,
                    selection_scores=normalized_selection_scores,
                    mechanism_family=normalized_mechanism_family or "",
                    change_layer=normalized_change_layer or "",
                    source_lens=normalized_source_lens or "",
                    foundation_ref=foundation,
                    foundation_reason=foundation_reason,
                    lineage_intent=normalized_lineage_intent,
                    draft_markdown=draft_markdown,
                )
                write_text(idea_md_path, markdown)
                write_text(idea_draft_path, draft)
                artifact = self.record(
                    quest_root,
                    {
                        "kind": "idea",
                        "status": "candidate",
                        "summary": f"Idea candidate `{resolved_idea_id}` recorded for later ranking or promotion.",
                        "reason": decision_reason or "A candidate optimization direction was recorded before promotion into a durable branch.",
                        "idea_id": resolved_idea_id,
                        "lineage_intent": normalized_lineage_intent,
                        "branch": None,
                        "parent_branch": parent_branch,
                        "foundation_ref": foundation,
                        "foundation_reason": foundation_reason.strip() or None,
                        "flow_type": "idea_submission",
                        "protocol_step": "candidate",
                        "paths": {
                            "idea_md": str(idea_md_path),
                            "idea_draft_md": str(idea_draft_path),
                            "candidate_root": str(candidate_root),
                        },
                        "details": {
                            "title": title,
                            "problem": problem,
                            "hypothesis": hypothesis,
                            "mechanism": mechanism,
                            "method_brief": normalized_method_brief or None,
                            "selection_scores": normalized_selection_scores or None,
                            "mechanism_family": normalized_mechanism_family,
                            "change_layer": normalized_change_layer,
                            "source_lens": normalized_source_lens,
                            "expected_gain": expected_gain,
                            "next_target": next_target,
                            "lineage_intent": normalized_lineage_intent,
                            "parent_branch": parent_branch,
                            "foundation_ref": foundation,
                            "foundation_reason": foundation_reason.strip() or None,
                            "idea_draft_path": str(idea_draft_path),
                            "evidence_paths": evidence_paths,
                            "risks": risks,
                            "submission_mode": normalized_submission_mode,
                            "source_candidate_id": str(source_candidate_id or "").strip() or None,
                        },
                    },
                    checkpoint=False,
                    workspace_root=quest_root,
                )
                interaction = self.interact(
                    quest_root,
                    kind="progress",
                    message=self._build_idea_interaction_message(
                        quest_root=quest_root,
                        action="candidate",
                        idea_id=resolved_idea_id,
                        title=title,
                        mechanism=mechanism,
                        method_brief=normalized_method_brief,
                        foundation_label=self._format_foundation_label(
                            foundation,
                            fallback=foundation.get("branch") or "current head",
                        ),
                        branch_name="candidate",
                        change_layer=normalized_change_layer,
                        source_lens=normalized_source_lens,
                        expected_gain=expected_gain,
                        next_target=next_target,
                    ),
                    deliver_to_bound_conversations=True,
                    include_recent_inbound_messages=False,
                    attachments=[
                        {
                            "kind": "idea_candidate",
                            "idea_id": resolved_idea_id,
                            "candidate_root": str(candidate_root),
                            "parent_branch": parent_branch,
                            "foundation_ref": foundation,
                            "submission_mode": normalized_submission_mode,
                            "source_candidate_id": str(source_candidate_id or "").strip() or None,
                            "method_brief": normalized_method_brief or None,
                            "selection_scores": normalized_selection_scores or None,
                            "mechanism_family": normalized_mechanism_family,
                            "change_layer": normalized_change_layer,
                            "source_lens": normalized_source_lens,
                            "next_target": next_target,
                        }
                    ],
                )
                return {
                    "ok": True,
                    "mode": normalized_mode,
                    "submission_mode": normalized_submission_mode,
                    "guidance": artifact.get("guidance"),
                    "guidance_vm": artifact.get("guidance_vm"),
                    "next_anchor": artifact.get("next_anchor"),
                    "recommended_skill_reads": artifact.get("recommended_skill_reads"),
                    "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
                    "next_instruction": artifact.get("next_instruction"),
                    "idea_id": resolved_idea_id,
                    "lineage_intent": normalized_lineage_intent,
                    "parent_branch": parent_branch,
                    "foundation_ref": foundation,
                    "foundation_reason": foundation_reason.strip() or None,
                    "candidate_root": str(candidate_root),
                    "idea_md_path": str(idea_md_path),
                    "idea_draft_path": str(idea_draft_path),
                    "artifact": artifact,
                    "interaction": interaction,
                    "promotable": True,
                    "source_candidate_id": str(source_candidate_id or "").strip() or None,
                    "method_brief": normalized_method_brief or None,
                    "selection_scores": normalized_selection_scores or None,
                    "mechanism_family": normalized_mechanism_family,
                    "change_layer": normalized_change_layer,
                    "source_lens": normalized_source_lens,
                }
            branch_name = f"idea/{quest_id}-{resolved_idea_id}"
            worktree_root = canonical_worktree_root(quest_root, f"idea-{resolved_idea_id}")
            branch_result = ensure_branch(quest_root, branch_name, start_point=parent_branch, checkout=False)
            worktree_result = create_worktree(
                quest_root,
                branch=branch_name,
                worktree_root=worktree_root,
                start_point=parent_branch,
            )
            ensure_dir(worktree_root / "memory" / "ideas" / resolved_idea_id)
            idea_md_path = worktree_root / "memory" / "ideas" / resolved_idea_id / "idea.md"
            idea_draft_path = worktree_root / "memory" / "ideas" / resolved_idea_id / "draft.md"
            markdown = self._build_idea_markdown(
                idea_id=resolved_idea_id,
                quest_id=quest_id,
                title=title,
                problem=problem,
                hypothesis=hypothesis,
                mechanism=mechanism,
                expected_gain=expected_gain,
                risks=risks,
                evidence_paths=evidence_paths,
                decision_reason=decision_reason,
                next_target=next_target,
                branch=branch_name,
                worktree_root=worktree_root,
                method_brief=normalized_method_brief,
                selection_scores=normalized_selection_scores,
                mechanism_family=normalized_mechanism_family or "",
                change_layer=normalized_change_layer or "",
                source_lens=normalized_source_lens or "",
                foundation_ref=foundation,
                foundation_reason=foundation_reason,
                lineage_intent=normalized_lineage_intent,
            )
            draft = self._build_idea_draft_markdown(
                idea_id=resolved_idea_id,
                quest_id=quest_id,
                title=title,
                problem=problem,
                hypothesis=hypothesis,
                mechanism=mechanism,
                expected_gain=expected_gain,
                risks=risks,
                evidence_paths=evidence_paths,
                decision_reason=decision_reason,
                next_target=next_target,
                branch=branch_name,
                worktree_root=worktree_root,
                method_brief=normalized_method_brief,
                selection_scores=normalized_selection_scores,
                mechanism_family=normalized_mechanism_family or "",
                change_layer=normalized_change_layer or "",
                source_lens=normalized_source_lens or "",
                foundation_ref=foundation,
                foundation_reason=foundation_reason,
                lineage_intent=normalized_lineage_intent,
                draft_markdown=draft_markdown,
            )
            write_text(idea_md_path, markdown)
            write_text(idea_draft_path, draft)
            branch_no = self._next_branch_number(quest_root)
            artifact = self.record(
                quest_root,
                {
                    "kind": "idea",
                    "status": "completed",
                    "summary": f"Idea `{resolved_idea_id}` created and promoted to the active research head.",
                    "reason": decision_reason or "A concrete idea was selected for continued research and implementation.",
                    "idea_id": resolved_idea_id,
                    "lineage_intent": normalized_lineage_intent,
                    "branch": branch_name,
                    "parent_branch": parent_branch,
                    "foundation_ref": foundation,
                    "foundation_reason": foundation_reason.strip() or None,
                    "worktree_root": str(worktree_root),
                    "worktree_rel_path": self._workspace_relative(quest_root, worktree_root),
                    "flow_type": "idea_submission",
                    "protocol_step": "create",
                    "paths": {
                        "idea_md": str(idea_md_path),
                        "idea_draft_md": str(idea_draft_path),
                        "worktree_root": str(worktree_root),
                    },
                    "details": {
                        "title": title,
                        "problem": problem,
                        "hypothesis": hypothesis,
                        "mechanism": mechanism,
                        "method_brief": normalized_method_brief or None,
                        "selection_scores": normalized_selection_scores or None,
                        "mechanism_family": normalized_mechanism_family,
                        "change_layer": normalized_change_layer,
                        "source_lens": normalized_source_lens,
                        "expected_gain": expected_gain,
                        "next_target": next_target,
                        "branch_no": branch_no,
                        "lineage_intent": normalized_lineage_intent,
                        "parent_branch": parent_branch,
                        "foundation_ref": foundation,
                        "foundation_reason": foundation_reason.strip() or None,
                        "idea_draft_path": str(idea_draft_path),
                        "evidence_paths": evidence_paths,
                        "risks": risks,
                        "submission_mode": normalized_submission_mode,
                        "source_candidate_id": str(source_candidate_id or "").strip() or None,
                    },
                },
                checkpoint=False,
                workspace_root=worktree_root,
            )
            current_state = self.quest_service.read_research_state(quest_root)
            workspace_mode, branch_mode = self._resolve_workspace_modes(
                current_state,
                branch_name=branch_name,
                has_idea=bool(resolved_idea_id),
            )
            research_state = self.quest_service.update_research_state(
                quest_root,
                active_idea_id=resolved_idea_id,
                research_head_branch=branch_name,
                research_head_worktree_root=str(worktree_root),
                current_workspace_branch=branch_name,
                current_workspace_root=str(worktree_root),
                active_idea_md_path=str(idea_md_path),
                active_idea_draft_path=str(idea_draft_path),
                active_analysis_campaign_id=None,
                analysis_parent_branch=None,
                analysis_parent_worktree_root=None,
                next_pending_slice_id=None,
                workspace_mode=workspace_mode,
                workspace_branch_mode=branch_mode,
                last_flow_type="idea_submission",
            )
            self.quest_service.update_settings(quest_id, active_anchor=next_anchor)
            checkpoint_result = self._checkpoint_with_optional_push(
                worktree_root,
                message=f"idea: create {resolved_idea_id}",
            )
            interaction = self.interact(
                quest_root,
                kind="milestone",
                message=self._build_idea_interaction_message(
                    quest_root=quest_root,
                    action="create",
                    idea_id=resolved_idea_id,
                    title=title,
                    mechanism=mechanism,
                    method_brief=normalized_method_brief,
                    foundation_label=self._format_foundation_label(
                        foundation,
                        fallback=foundation.get("branch") or "current head",
                    ),
                    branch_name=branch_name,
                    change_layer=normalized_change_layer,
                    source_lens=normalized_source_lens,
                    expected_gain=expected_gain,
                    next_target=next_target,
                ),
                deliver_to_bound_conversations=True,
                include_recent_inbound_messages=False,
                attachments=[
                    {
                        "kind": "idea_submission",
                        "idea_id": resolved_idea_id,
                        "branch_no": branch_no,
                        "branch": branch_name,
                        "lineage_intent": normalized_lineage_intent,
                        "parent_branch": parent_branch,
                        "foundation_ref": foundation,
                        "foundation_reason": foundation_reason.strip() or None,
                        "worktree_root": str(worktree_root),
                        "idea_md_path": str(idea_md_path),
                        "idea_draft_path": str(idea_draft_path),
                        "submission_mode": normalized_submission_mode,
                        "source_candidate_id": str(source_candidate_id or "").strip() or None,
                        "method_brief": normalized_method_brief or None,
                        "selection_scores": normalized_selection_scores or None,
                        "mechanism_family": normalized_mechanism_family,
                        "change_layer": normalized_change_layer,
                        "source_lens": normalized_source_lens,
                        "next_target": next_target,
                    }
                ],
            )
            return {
                "ok": True,
                "mode": normalized_mode,
                "submission_mode": normalized_submission_mode,
                "guidance": artifact.get("guidance"),
                "guidance_vm": artifact.get("guidance_vm"),
                "next_anchor": artifact.get("next_anchor"),
                "recommended_skill_reads": artifact.get("recommended_skill_reads"),
                "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
                "next_instruction": artifact.get("next_instruction"),
                "idea_id": resolved_idea_id,
                "branch_no": branch_no,
                "branch": branch_name,
                "lineage_intent": normalized_lineage_intent,
                "parent_branch": parent_branch,
                "foundation_ref": foundation,
                "foundation_reason": foundation_reason.strip() or None,
                "worktree_root": str(worktree_root),
                "idea_md_path": str(idea_md_path),
                "idea_draft_path": str(idea_draft_path),
                "branch_result": branch_result,
                "worktree": worktree_result,
                "artifact": artifact,
                "checkpoint": checkpoint_result,
                "interaction": interaction,
                "research_state": research_state,
                "source_candidate_id": str(source_candidate_id or "").strip() or None,
                "method_brief": normalized_method_brief or None,
                "selection_scores": normalized_selection_scores or None,
                "mechanism_family": normalized_mechanism_family,
                "change_layer": normalized_change_layer,
                "source_lens": normalized_source_lens,
            }

        resolved_idea_id = str(idea_id or state.get("active_idea_id") or "").strip()
        if not resolved_idea_id:
            raise ValueError("submit_idea(mode='revise') requires an existing active `idea_id`.")
        if normalized_submission_mode != "line":
            raise ValueError("submit_idea(mode='revise') currently only supports submission_mode='line'.")
        if normalized_lineage_intent:
            raise ValueError("submit_idea(mode='revise') does not accept `lineage_intent`; use mode='create' for new branch lineage.")
        branch_name = str(
            state.get("current_workspace_branch")
            or state.get("research_head_branch")
            or f"idea/{quest_id}-{resolved_idea_id}"
        ).strip()
        worktree_root = Path(
            str(
                state.get("current_workspace_root")
                or state.get("research_head_worktree_root")
                or canonical_worktree_root(quest_root, f"idea-{resolved_idea_id}")
            )
        )
        ensure_dir(worktree_root / "memory" / "ideas" / resolved_idea_id)
        idea_md_path = worktree_root / "memory" / "ideas" / resolved_idea_id / "idea.md"
        idea_draft_path = worktree_root / "memory" / "ideas" / resolved_idea_id / "draft.md"
        created_at = None
        draft_created_at = None
        existing_foundation_ref = None
        existing_foundation_reason = None
        existing_method_brief = None
        existing_selection_scores = None
        existing_mechanism_family = None
        existing_change_layer = None
        existing_source_lens = None
        if idea_md_path.exists():
            metadata, _body = load_markdown_document(idea_md_path)
            created_at = metadata.get("created_at")
            existing_foundation_ref = (
                dict(metadata.get("foundation_ref") or {})
                if isinstance(metadata.get("foundation_ref"), dict)
                else None
            )
            existing_foundation_reason = str(metadata.get("foundation_reason") or "").strip() or None
            existing_method_brief = str(metadata.get("method_brief") or "").strip() or None
            existing_selection_scores = self._normalize_selection_scores(metadata.get("selection_scores"))
            existing_mechanism_family = str(metadata.get("mechanism_family") or "").strip() or None
            existing_change_layer = str(metadata.get("change_layer") or "").strip() or None
            existing_source_lens = str(metadata.get("source_lens") or "").strip() or None
        if idea_draft_path.exists():
            draft_metadata, _draft_body = load_markdown_document(idea_draft_path)
            draft_created_at = draft_metadata.get("created_at")
            if existing_method_brief is None:
                existing_method_brief = str(draft_metadata.get("method_brief") or "").strip() or None
            if existing_selection_scores is None:
                existing_selection_scores = self._normalize_selection_scores(draft_metadata.get("selection_scores"))
            if existing_mechanism_family is None:
                existing_mechanism_family = str(draft_metadata.get("mechanism_family") or "").strip() or None
            if existing_change_layer is None:
                existing_change_layer = str(draft_metadata.get("change_layer") or "").strip() or None
            if existing_source_lens is None:
                existing_source_lens = str(draft_metadata.get("source_lens") or "").strip() or None
        revised_method_brief = normalized_method_brief or existing_method_brief or ""
        revised_selection_scores = normalized_selection_scores or existing_selection_scores
        revised_mechanism_family = normalized_mechanism_family or existing_mechanism_family
        revised_change_layer = normalized_change_layer or existing_change_layer
        revised_source_lens = normalized_source_lens or existing_source_lens
        markdown = self._build_idea_markdown(
            idea_id=resolved_idea_id,
            quest_id=quest_id,
            title=title,
            problem=problem,
            hypothesis=hypothesis,
            mechanism=mechanism,
            expected_gain=expected_gain,
            risks=risks,
            evidence_paths=evidence_paths,
            decision_reason=decision_reason,
            next_target=next_target,
            branch=branch_name,
            worktree_root=worktree_root,
            method_brief=revised_method_brief,
            selection_scores=revised_selection_scores,
            mechanism_family=revised_mechanism_family or "",
            change_layer=revised_change_layer or "",
            source_lens=revised_source_lens or "",
            foundation_ref=existing_foundation_ref,
            foundation_reason=foundation_reason.strip() or existing_foundation_reason or "",
            lineage_intent=None,
            created_at=str(created_at) if created_at else None,
        )
        draft = self._build_idea_draft_markdown(
            idea_id=resolved_idea_id,
            quest_id=quest_id,
            title=title,
            problem=problem,
            hypothesis=hypothesis,
            mechanism=mechanism,
            expected_gain=expected_gain,
            risks=risks,
            evidence_paths=evidence_paths,
            decision_reason=decision_reason,
            next_target=next_target,
            branch=branch_name,
            worktree_root=worktree_root,
            method_brief=revised_method_brief,
            selection_scores=revised_selection_scores,
            mechanism_family=revised_mechanism_family or "",
            change_layer=revised_change_layer or "",
            source_lens=revised_source_lens or "",
            foundation_ref=existing_foundation_ref,
            foundation_reason=foundation_reason.strip() or existing_foundation_reason or "",
            lineage_intent=None,
            created_at=str(draft_created_at or created_at) if (draft_created_at or created_at) else None,
            draft_markdown=draft_markdown,
        )
        write_text(idea_md_path, markdown)
        write_text(idea_draft_path, draft)
        parent_branch = self._idea_parent_branch(self._latest_idea_for_branch(quest_root, branch_name))
        artifact = self.record(
            quest_root,
            {
                "kind": "idea",
                "status": "completed",
                "summary": f"Idea `{resolved_idea_id}` revised on the active research branch.",
                "reason": decision_reason or "The current idea was refined before launching the next stage.",
                "idea_id": resolved_idea_id,
                "branch": branch_name,
                "parent_branch": parent_branch,
                "foundation_ref": existing_foundation_ref,
                "foundation_reason": foundation_reason.strip() or existing_foundation_reason or None,
                "worktree_root": str(worktree_root),
                "worktree_rel_path": self._workspace_relative(quest_root, worktree_root),
                "flow_type": "idea_submission",
                "protocol_step": "revise",
                "paths": {
                    "idea_md": str(idea_md_path),
                    "idea_draft_md": str(idea_draft_path),
                    "worktree_root": str(worktree_root),
                },
                "details": {
                    "title": title,
                    "problem": problem,
                    "hypothesis": hypothesis,
                    "mechanism": mechanism,
                    "method_brief": revised_method_brief or None,
                    "selection_scores": revised_selection_scores or None,
                    "mechanism_family": revised_mechanism_family,
                    "change_layer": revised_change_layer,
                    "source_lens": revised_source_lens,
                    "expected_gain": expected_gain,
                    "next_target": next_target,
                    "parent_branch": parent_branch,
                    "foundation_ref": existing_foundation_ref,
                    "foundation_reason": foundation_reason.strip() or existing_foundation_reason or None,
                    "idea_draft_path": str(idea_draft_path),
                    "evidence_paths": evidence_paths,
                    "risks": risks,
                    "submission_mode": normalized_submission_mode,
                },
            },
            checkpoint=False,
            workspace_root=worktree_root,
        )
        research_state_updates: dict[str, Any] = {
            "active_idea_id": resolved_idea_id,
            "current_workspace_branch": branch_name,
            "current_workspace_root": str(worktree_root),
            "active_idea_md_path": str(idea_md_path),
            "active_idea_draft_path": str(idea_draft_path),
            "workspace_mode": "idea",
            "last_flow_type": "idea_revision",
        }
        current_head_branch = str(state.get("research_head_branch") or "").strip()
        if not current_head_branch or current_head_branch == branch_name:
            research_state_updates["research_head_branch"] = branch_name
            research_state_updates["research_head_worktree_root"] = str(worktree_root)
        research_state = self.quest_service.update_research_state(
            quest_root,
            **research_state_updates,
        )
        self.quest_service.update_settings(quest_id, active_anchor=next_anchor)
        checkpoint_result = self._checkpoint_with_optional_push(
            worktree_root,
            message=f"idea: revise {resolved_idea_id}",
        )
        interaction = self.interact(
            quest_root,
            kind="progress",
            message=self._build_idea_interaction_message(
                quest_root=quest_root,
                action="revise",
                idea_id=resolved_idea_id,
                title=title,
                mechanism=mechanism,
                method_brief=revised_method_brief,
                foundation_label=self._format_foundation_label(
                    existing_foundation_ref,
                    fallback=(existing_foundation_ref or {}).get("branch") or "current head",
                ),
                branch_name=branch_name,
                change_layer=revised_change_layer,
                source_lens=revised_source_lens,
                expected_gain=expected_gain,
                next_target=next_target,
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "idea_revision",
                    "idea_id": resolved_idea_id,
                    "branch": branch_name,
                    "foundation_ref": existing_foundation_ref,
                    "foundation_reason": foundation_reason.strip() or existing_foundation_reason or None,
                    "worktree_root": str(worktree_root),
                    "idea_md_path": str(idea_md_path),
                    "idea_draft_path": str(idea_draft_path),
                    "submission_mode": normalized_submission_mode,
                    "method_brief": revised_method_brief or None,
                    "selection_scores": revised_selection_scores or None,
                    "mechanism_family": revised_mechanism_family,
                    "change_layer": revised_change_layer,
                    "source_lens": revised_source_lens,
                    "next_target": next_target,
                }
            ],
        )
        return {
            "ok": True,
            "mode": normalized_mode,
            "submission_mode": normalized_submission_mode,
            "guidance": artifact.get("guidance"),
            "guidance_vm": artifact.get("guidance_vm"),
            "next_anchor": artifact.get("next_anchor"),
            "recommended_skill_reads": artifact.get("recommended_skill_reads"),
            "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
            "next_instruction": artifact.get("next_instruction"),
            "idea_id": resolved_idea_id,
            "branch": branch_name,
            "parent_branch": parent_branch,
            "foundation_ref": existing_foundation_ref,
            "foundation_reason": foundation_reason.strip() or existing_foundation_reason or None,
            "worktree_root": str(worktree_root),
            "idea_md_path": str(idea_md_path),
            "idea_draft_path": str(idea_draft_path),
            "method_brief": revised_method_brief or None,
            "selection_scores": revised_selection_scores or None,
            "mechanism_family": revised_mechanism_family,
            "change_layer": revised_change_layer,
            "source_lens": revised_source_lens,
            "artifact": artifact,
            "checkpoint": checkpoint_result,
            "interaction": interaction,
            "research_state": research_state,
        }

    def _main_experiment_delivery_policy(
        self,
        quest_root: Path,
        *,
        progress_eval: dict[str, Any],
    ) -> dict[str, Any]:
        quest_data = self.quest_service.read_quest_yaml(quest_root)
        startup_contract = (
            dict(quest_data.get("startup_contract") or {})
            if isinstance(quest_data.get("startup_contract"), dict)
            else {}
        )
        raw_need_research_paper = startup_contract.get("need_research_paper")
        need_research_paper = raw_need_research_paper if isinstance(raw_need_research_paper, bool) else True
        breakthrough = bool(progress_eval.get("breakthrough"))
        beats_baseline = progress_eval.get("beats_baseline")

        if need_research_paper:
            if breakthrough or beats_baseline is True:
                recommended_next_route = "analysis_or_write"
                reason = (
                    "Research paper mode is enabled. The run looks promising, so the next route should usually "
                    "strengthen the evidence and move toward analysis or writing rather than stopping at the algorithm result alone."
                )
            elif beats_baseline is False:
                recommended_next_route = "revise_idea"
                reason = (
                    "Research paper mode is enabled, but the current run does not beat the baseline clearly enough. "
                    "Revise the direction or strengthen the method before writing."
                )
            else:
                recommended_next_route = "continue"
                reason = (
                    "Research paper mode is enabled. The current result should inform the next route, but more evidence "
                    "is still needed before committing to writing."
                )
        else:
            if breakthrough or beats_baseline is True:
                recommended_next_route = "iterate"
                reason = (
                    "Research paper mode is disabled. Use this measured result to launch the next optimization round "
                    "instead of defaulting into paper work."
                )
            elif beats_baseline is False:
                recommended_next_route = "revise_idea"
                reason = (
                    "Research paper mode is disabled and the run is not yet strong enough. Revise the idea using this "
                    "measured failure signal and continue optimization."
                )
            else:
                recommended_next_route = "continue"
                reason = (
                    "Research paper mode is disabled. Keep optimizing from the measured result and defer paper work unless "
                    "the user later changes scope."
                )

        return {
            "need_research_paper": need_research_paper,
            "recommended_next_route": recommended_next_route,
            "reason": reason,
            "startup_contract": startup_contract,
        }

    def _startup_contract(self, quest_root: Path) -> dict[str, Any]:
        quest_data = self.quest_service.read_quest_yaml(quest_root)
        if isinstance(quest_data.get("startup_contract"), dict):
            return dict(quest_data.get("startup_contract") or {})
        return {}

    def _post_baseline_anchor(self, quest_root: Path) -> str:
        startup_contract = self._startup_contract(quest_root)
        raw_need_research_paper = startup_contract.get("need_research_paper")
        need_research_paper = raw_need_research_paper if isinstance(raw_need_research_paper, bool) else True
        return "idea" if need_research_paper else "optimize"

    def _decision_policy(self, quest_root: Path) -> str:
        value = str(self._startup_contract(quest_root).get("decision_policy") or "").strip().lower()
        if value in {"autonomous", "user_gated"}:
            return value
        return "user_gated"

    @staticmethod
    def _blocking_wait_reasons() -> set[str]:
        return {
            "completion_approval",
            "credential_required",
            "privacy_or_data_export_boundary",
            "large_cost_or_external_paid_api",
            "user_gated_decision_request",
        }

    def _waiting_notice_payload(
        self,
        quest_root: Path,
        *,
        status: str,
        reason: str,
        message: str,
        decision_policy: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reason": str(reason or "").strip() or None,
            "message": message,
            "decision_policy": decision_policy,
            "created_at": utc_now(),
            "label": self.quest_service.localized_copy(
                quest_root=quest_root,
                zh="等待反馈" if status == "waiting" else "自动继续",
                en="Waiting for feedback" if status == "waiting" else "Auto-resumed",
            ),
        }

    def _set_waiting_or_auto_resume(
        self,
        quest_root: Path,
        *,
        reason: str,
        anchor: str | None = "decision",
        force_wait: bool = False,
    ) -> dict[str, Any]:
        normalized_reason = str(reason or "").strip() or "waiting_for_feedback"
        decision_policy = self._decision_policy(quest_root)
        should_wait = force_wait or decision_policy != "autonomous" or normalized_reason in self._blocking_wait_reasons()
        if should_wait:
            message = self.quest_service.localized_copy(
                quest_root=quest_root,
                zh=f"【等待反馈】当前任务已暂停自动推进：{normalized_reason}。请回复你的选择；任何新消息都会从当前状态继续。",
                en=f"[Waiting for feedback] This quest paused automatic continuation: {normalized_reason}. Reply with your choice to continue.",
            )
            notice = self._waiting_notice_payload(
                quest_root,
                status="waiting",
                reason=normalized_reason,
                message=message,
                decision_policy=decision_policy,
            )
            state = self.quest_service.update_runtime_state(
                quest_root=quest_root,
                continuation_policy="wait_for_user_or_resume",
                continuation_anchor=anchor,
                continuation_reason=normalized_reason,
                waiting_notice=notice,
            )
            self.interact(
                quest_root,
                kind="progress",
                message=message,
                deliver_to_bound_conversations=True,
                include_recent_inbound_messages=False,
                dedupe_key=f"waiting-feedback:{normalized_reason}",
                min_interval_seconds=60,
            )
            return {"action": "waiting", "runtime_state": state, "waiting_notice": notice}

        message = self.quest_service.localized_copy(
            quest_root=quest_root,
            zh=f"【自动继续】系统检测到当前为无需询问模式，本次“等待反馈”已自动转换为继续执行。原因：{normalized_reason}。",
            en=f"[Auto-resumed] This quest is in autonomous decision mode, so the waiting state was converted back to automatic continuation. Reason: {normalized_reason}.",
        )
        notice = self._waiting_notice_payload(
            quest_root,
            status="auto_resumed",
            reason=normalized_reason,
            message=message,
            decision_policy=decision_policy,
        )
        state = self.quest_service.update_runtime_state(
            quest_root=quest_root,
            continuation_policy="auto",
            continuation_anchor=anchor,
            continuation_reason=f"{normalized_reason}_auto_resumed",
            waiting_notice=notice,
        )
        self.interact(
            quest_root,
            kind="progress",
            message=message,
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            dedupe_key=f"auto-resumed-wait:{normalized_reason}",
            min_interval_seconds=60,
        )
        return {"action": "auto_resumed", "runtime_state": state, "waiting_notice": notice}

    def record_main_experiment(
        self,
        quest_root: Path,
        *,
        run_id: str,
        title: str = "",
        hypothesis: str = "",
        setup: str = "",
        execution: str = "",
        results: str = "",
        conclusion: str = "",
        metric_rows: list[dict[str, Any]] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        metric_contract: dict[str, Any] | None = None,
        evidence_paths: list[str] | None = None,
        changed_files: list[str] | None = None,
        config_paths: list[str] | None = None,
        notes: list[str] | None = None,
        dataset_scope: str = "full",
        verdict: str = "",
        status: str = "completed",
        baseline_id: str | None = None,
        baseline_variant_id: str | None = None,
        evaluation_summary: dict[str, Any] | None = None,
        strict_metric_contract: bool = False,
    ) -> dict[str, Any]:
        self._require_baseline_gate_open(quest_root, action="record_main_experiment")
        state = self.quest_service.read_research_state(quest_root)
        branch_mode = self._active_workspace_branch_mode(
            state,
            branch_name=str(state.get("current_workspace_branch") or "").strip(),
        )
        if branch_mode == "analysis":
            raise ValueError(
                "record_main_experiment cannot run while the active workspace is an analysis slice. "
                "Finish or close the analysis campaign first."
            )
        if branch_mode == "paper":
            raise ValueError(
                "record_main_experiment cannot run while the active workspace is a paper branch. "
                "Return to the source evidence branch or create a new run branch first."
            )

        run_identifier = str(run_id or "").strip()
        if not run_identifier:
            raise ValueError("record_main_experiment requires `run_id`.")

        active_idea_id = str(state.get("active_idea_id") or "").strip() or None
        workspace_root = self._workspace_root_for(quest_root)
        current_branch_name = str(
            state.get("current_workspace_branch")
            or state.get("research_head_branch")
            or current_branch(workspace_root)
        ).strip()
        branch_name, parent_branch, auto_promoted_run_branch = self._promote_workspace_to_run_branch(
            quest_root,
            run_id=run_identifier,
            idea_id=active_idea_id,
            workspace_root=workspace_root,
            current_branch_name=current_branch_name,
        )
        attachment = self._active_baseline_attachment(quest_root, workspace_root=workspace_root)
        baseline_entry = dict(attachment.get("entry") or {}) if isinstance(attachment, dict) else {}
        selected_variant = dict(attachment.get("selected_variant") or {}) if isinstance(attachment, dict) else {}
        resolved_baseline_id = (
            str(baseline_id or attachment.get("source_baseline_id") or baseline_entry.get("baseline_id") or "").strip() or None
            if isinstance(attachment, dict)
            else str(baseline_id or "").strip() or None
        )
        resolved_variant_id = (
            str(baseline_variant_id or attachment.get("source_variant_id") or selected_variant.get("variant_id") or "").strip()
            or None
            if isinstance(attachment, dict)
            else str(baseline_variant_id or "").strip() or None
        )
        baseline_confirmation = (
            dict(attachment.get("confirmation") or {})
            if isinstance(attachment, dict) and isinstance(attachment.get("confirmation"), dict)
            else {}
        )
        metric_contract_json_rel_path = str(baseline_confirmation.get("metric_contract_json_rel_path") or "").strip() or None

        normalized_metrics_summary = normalize_metrics_summary(metrics_summary)
        normalized_metric_rows = normalize_metric_rows(metric_rows or [], metrics_summary=normalized_metrics_summary)
        if not normalized_metrics_summary:
            normalized_metrics_summary = {
                str(item.get("metric_id") or "").strip(): item.get("value")
                for item in normalized_metric_rows
                if str(item.get("metric_id") or "").strip()
            }
        baseline_contract_payload = self._load_metric_contract_payload(quest_root, metric_contract_json_rel_path)
        baseline_metric_contract = baseline_entry.get("metric_contract")
        baseline_primary_metric = baseline_entry.get("primary_metric")
        if isinstance(baseline_contract_payload, dict) and baseline_contract_payload:
            payload_metric_contract = baseline_contract_payload.get("metric_contract")
            if isinstance(payload_metric_contract, dict) and payload_metric_contract:
                baseline_metric_contract = payload_metric_contract
            payload_primary_metric = baseline_contract_payload.get("primary_metric")
            if isinstance(payload_primary_metric, dict) and payload_primary_metric:
                baseline_primary_metric = payload_primary_metric
        effective_metric_contract = (
            self._merge_run_metric_contract(
                baseline_metric_contract=baseline_metric_contract,
                baseline_primary_metric=baseline_primary_metric,
                baseline_variants=baseline_entry.get("baseline_variants"),
                run_metric_contract=metric_contract,
                metrics_summary=normalized_metrics_summary,
                metric_rows=normalized_metric_rows,
                baseline_id=resolved_baseline_id,
            )
            if isinstance(baseline_metric_contract, dict) and baseline_metric_contract
            else normalize_metric_contract(
                metric_contract or baseline_entry.get("metric_contract"),
                baseline_id=resolved_baseline_id,
                metrics_summary=normalized_metrics_summary,
                metric_rows=normalized_metric_rows,
                primary_metric=baseline_primary_metric,
                baseline_variants=baseline_entry.get("baseline_variants"),
            )
        )
        metric_validation: dict[str, Any] | None = None
        if strict_metric_contract:
            metric_validation = validate_main_experiment_against_baseline_contract(
                baseline_contract_payload=baseline_contract_payload,
                run_metric_contract=effective_metric_contract,
                metric_rows=normalized_metric_rows,
                metrics_summary=normalized_metrics_summary,
                dataset_scope=dataset_scope,
            )
        baseline_metrics = selected_baseline_metrics(baseline_entry, resolved_variant_id)
        comparisons = compare_with_baseline(
            metrics_summary=normalized_metrics_summary,
            metric_rows=normalized_metric_rows,
            metric_contract=effective_metric_contract,
            baseline_metrics=baseline_metrics,
        )
        previous_primary_best = self._previous_primary_best(
            quest_root,
            primary_metric_id=comparisons.get("primary_metric_id"),
            direction=((comparisons.get("primary") or {}).get("direction") if isinstance(comparisons, dict) else None),
        )
        progress_eval = compute_progress_eval(
            comparisons=comparisons,
            previous_primary_best=previous_primary_best,
        )
        delivery_policy = self._main_experiment_delivery_policy(
            quest_root,
            progress_eval=progress_eval,
        )
        resolved_changed_files = [str(item).strip() for item in (changed_files or []) if str(item).strip()]
        if not resolved_changed_files:
            resolved_changed_files = self._git_changed_files(workspace_root)
        resolved_evidence_paths = [str(item).strip() for item in (evidence_paths or []) if str(item).strip()]
        resolved_config_paths = [str(item).strip() for item in (config_paths or []) if str(item).strip()]
        resolved_notes = [str(item).strip() for item in (notes or []) if str(item).strip()]
        normalized_dataset_scope = str(dataset_scope or "full").strip().lower() or "full"
        normalized_evaluation_summary = self._normalize_evaluation_summary(evaluation_summary)
        primary = comparisons.get("primary") if isinstance(comparisons, dict) else {}
        primary_metric_id = str(progress_eval.get("primary_metric_id") or comparisons.get("primary_metric_id") or "").strip() or None
        primary_value = primary.get("run_value") if isinstance(primary, dict) else None
        primary_baseline = primary.get("baseline_value") if isinstance(primary, dict) else None
        primary_delta = progress_eval.get("delta_vs_baseline")
        decimals = primary.get("decimals") if isinstance(primary, dict) else None
        if not verdict:
            if progress_eval.get("breakthrough"):
                verdict = "supported"
            elif progress_eval.get("beats_baseline") is False:
                verdict = "inconclusive"
            else:
                verdict = "recorded"

        main_dir = ensure_dir(workspace_root / "experiments" / "main" / run_identifier)
        run_md_path = main_dir / "RUN.md"
        result_json_path = main_dir / "RESULT.json"

        summary_parts = [f"Main experiment `{run_identifier}` recorded on `{branch_name}`."]
        if primary_metric_id and primary_value is not None:
            summary_parts.append(
                f"{primary_metric_id}={self._format_metric_value(primary_value, decimals)}"
            )
        if primary_metric_id and primary_baseline is not None and primary_delta is not None:
            delta_text = self._format_metric_value(primary_delta, decimals)
            baseline_text = self._format_metric_value(primary_baseline, decimals)
            summary_parts.append(f"vs baseline {baseline_text} (Δ {delta_text})")
        if progress_eval.get("breakthrough"):
            summary_parts.append(f"Breakthrough: {progress_eval.get('breakthrough_level')}")
        summary = " ".join(summary_parts)

        run_lines = [
            f"# {title.strip() or run_identifier}",
            "",
            f"- Run id: `{run_identifier}`",
            f"- Branch: `{branch_name}`",
            f"- Parent branch: `{parent_branch or 'none'}`",
            f"- Worktree: `{workspace_root}`",
            f"- Idea: `{active_idea_id or 'none'}`",
            f"- Baseline: `{resolved_baseline_id or 'none'}`",
            f"- Baseline variant: `{resolved_variant_id or 'none'}`",
            f"- Dataset scope: `{normalized_dataset_scope}`",
            f"- Verdict: `{verdict}`",
            f"- Status: `{status}`",
            "",
            "## Hypothesis",
            "",
            hypothesis.strip() or "TBD",
            "",
            "## Setup",
            "",
            setup.strip() or "TBD",
            "",
            "## Execution",
            "",
            execution.strip() or "TBD",
            "",
            "## Results",
            "",
            results.strip() or "TBD",
            "",
            "## Conclusion",
            "",
            conclusion.strip() or progress_eval.get("reason") or "TBD",
            "",
            "## Metrics Summary",
            "",
        ]
        if normalized_metrics_summary:
            for metric_id, value in normalized_metrics_summary.items():
                run_lines.append(f"- `{metric_id}` = {self._format_metric_value(value)}")
        else:
            run_lines.append("- No metrics recorded.")
        run_lines.extend(["", "## Baseline Comparison", ""])
        comparison_items = comparisons.get("items") if isinstance(comparisons, dict) else []
        if comparison_items:
            for item in comparison_items:
                metric_id = str(item.get("metric_id") or "").strip() or "metric"
                run_value = self._format_metric_value(item.get("run_value"), item.get("decimals"))
                baseline_value = self._format_metric_value(item.get("baseline_value"), item.get("decimals"))
                delta_value = item.get("delta")
                delta_text = self._format_metric_value(delta_value, item.get("decimals")) if delta_value is not None else "n/a"
                verdict_text = (
                    "better"
                    if item.get("better") is True
                    else "worse"
                    if item.get("better") is False
                    else "not comparable"
                )
                run_lines.append(
                    f"- `{metric_id}`: run={run_value} baseline={baseline_value} delta={delta_text} ({verdict_text})"
                )
        else:
            run_lines.append("- No comparable baseline metrics found.")
        run_lines.extend(["", "## Changed Files", ""])
        if resolved_changed_files:
            run_lines.extend([f"- `{item}`" for item in resolved_changed_files])
        else:
            run_lines.append("- None recorded.")
        run_lines.extend(["", "## Evidence Paths", ""])
        if resolved_evidence_paths:
            run_lines.extend([f"- `{item}`" for item in resolved_evidence_paths])
        else:
            run_lines.append("- None recorded.")
        if resolved_config_paths:
            run_lines.extend(["", "## Config Paths", ""])
            run_lines.extend([f"- `{item}`" for item in resolved_config_paths])
        if resolved_notes:
            run_lines.extend(["", "## Notes", ""])
            run_lines.extend([f"- {item}" for item in resolved_notes])
        run_lines.extend(["", "## Evaluation Summary", ""])
        run_lines.extend(self._evaluation_summary_markdown_lines(normalized_evaluation_summary))
        run_lines.extend(
            [
                "",
                "## Delivery Policy",
                "",
                f"- Research paper required: `{delivery_policy.get('need_research_paper')}`",
                f"- Recommended next route: `{delivery_policy.get('recommended_next_route')}`",
                f"- Reason: {delivery_policy.get('reason') or 'n/a'}",
            ]
        )
        write_text(run_md_path, "\n".join(run_lines).rstrip() + "\n")

        result_payload = {
            "schema_version": 1,
            "result_kind": "main_experiment",
            "quest_id": self._quest_id(quest_root),
            "run_id": run_identifier,
            "title": title.strip() or run_identifier,
            "status": status,
            "verdict": verdict,
            "idea_id": active_idea_id,
            "branch": branch_name,
            "parent_branch": parent_branch,
            "worktree_root": str(workspace_root),
            "head_commit": head_commit(workspace_root),
            "baseline_ref": {
                "baseline_id": resolved_baseline_id,
                "variant_id": resolved_variant_id,
                "metric_contract_json_rel_path": metric_contract_json_rel_path,
                "metric_contract": effective_metric_contract,
                "metric_lines": baseline_metric_lines(baseline_entry, resolved_variant_id),
            },
            "run_context": {
                "dataset_scope": normalized_dataset_scope,
                "config_paths": resolved_config_paths,
                "notes": resolved_notes,
            },
            "hypothesis": hypothesis.strip(),
            "setup": setup.strip(),
            "execution": execution.strip(),
            "results_summary": results.strip(),
            "conclusion": conclusion.strip() or progress_eval.get("reason"),
            "metrics_summary": normalized_metrics_summary,
            "metric_rows": normalized_metric_rows,
            "metric_contract": effective_metric_contract,
            "baseline_comparisons": {
                key: value for key, value in comparisons.items() if key != "primary"
            },
            "progress_eval": progress_eval,
            "evaluation_summary": normalized_evaluation_summary,
            "delivery_policy": delivery_policy,
            "startup_contract": delivery_policy.get("startup_contract") or None,
            "evidence_paths": resolved_evidence_paths,
            "files_changed": resolved_changed_files,
            "run_md_path": str(run_md_path),
            "metric_validation": metric_validation,
        }
        write_json(result_json_path, result_payload)
        metric_charts: list[dict[str, Any]] = []

        artifact = self.record(
            quest_root,
            {
                "kind": "run",
                "status": status,
                "run_id": run_identifier,
                "run_kind": "main_experiment",
                "summary": summary,
                "reason": conclusion.strip() or progress_eval.get("reason") or "Main experiment result recorded.",
                "idea_id": active_idea_id,
                "branch": branch_name,
                "parent_branch": parent_branch,
                "worktree_root": str(workspace_root),
                "worktree_rel_path": self._workspace_relative(quest_root, workspace_root),
                "flow_type": "main_experiment",
                "protocol_step": "record",
                "paths": {
                    "run_md": str(run_md_path),
                    "result_json": str(result_json_path),
                    **(
                        {
                            "connector_chart_dir": str(self._main_experiment_chart_dir(workspace_root, run_id=run_identifier))
                        }
                        if metric_charts
                        else {}
                    ),
                },
                "details": {
                    "title": title.strip() or run_identifier,
                    "verdict": verdict,
                    "primary_metric_id": primary_metric_id,
                    "primary_value": primary_value,
                    "baseline_value": primary_baseline,
                    "delta_vs_baseline": primary_delta,
                    "breakthrough": progress_eval.get("breakthrough"),
                    "breakthrough_level": progress_eval.get("breakthrough_level"),
                    "need_research_paper": delivery_policy.get("need_research_paper"),
                    "recommended_next_route": delivery_policy.get("recommended_next_route"),
                    "auto_promoted_run_branch": auto_promoted_run_branch,
                    "changed_file_count": len(resolved_changed_files),
                    "evidence_count": len(resolved_evidence_paths),
                    "connector_chart_count": 0,
                    "evaluation_summary": normalized_evaluation_summary,
                },
                "delivery_policy": delivery_policy,
                "startup_contract": delivery_policy.get("startup_contract") or None,
                "baseline_ref": {
                    "baseline_id": resolved_baseline_id,
                    "variant_id": resolved_variant_id,
                    "metric_contract_json_rel_path": metric_contract_json_rel_path,
                },
                "metrics_summary": normalized_metrics_summary,
                "metric_rows": normalized_metric_rows,
                "metric_contract": effective_metric_contract,
                "baseline_comparisons": {
                    key: value for key, value in comparisons.items() if key != "primary"
                },
                "progress_eval": progress_eval,
                "evaluation_summary": normalized_evaluation_summary,
                "metric_validation": metric_validation,
                "files_changed": resolved_changed_files,
                "evidence_paths": resolved_evidence_paths,
                "verdict": verdict,
            },
            commit_message=f"experiment: record main {run_identifier}",
            workspace_root=workspace_root,
        )
        metric_charts = self._generate_main_experiment_metric_charts(
            quest_root,
            workspace_root=workspace_root,
            run_id=run_identifier,
        )
        if metric_charts:
            result_payload["connector_metric_charts"] = metric_charts
            write_json(result_json_path, result_payload)
            artifact_record = dict(artifact.get("record") or {}) if isinstance(artifact.get("record"), dict) else {}
            artifact_record["connector_metric_charts"] = metric_charts
            details = dict(artifact_record.get("details") or {}) if isinstance(artifact_record.get("details"), dict) else {}
            details["connector_chart_count"] = len(metric_charts)
            artifact_record["details"] = details
            artifact["record"] = artifact_record
            artifact_path = Path(str(artifact.get("path") or ""))
            if artifact_path:
                write_json(artifact_path, artifact_record)
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=self._build_main_experiment_interaction_message(
                run_id=run_identifier,
                branch_name=branch_name,
                verdict=verdict,
                primary_metric_id=primary_metric_id,
                primary_value=primary_value,
                primary_baseline=primary_baseline,
                primary_delta=primary_delta,
                decimals=decimals if isinstance(decimals, int) else None,
                conclusion=conclusion.strip() or progress_eval.get("reason"),
                evaluation_summary=normalized_evaluation_summary,
                breakthrough_level=str(progress_eval.get("breakthrough_level") or "").strip() or None,
                recommended_next_route=str(delivery_policy.get("recommended_next_route") or "").strip() or None,
                run_md_rel_path=self._workspace_relative(quest_root, run_md_path),
                result_json_rel_path=self._workspace_relative(quest_root, result_json_path),
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "main_experiment_recorded",
                    "run_id": run_identifier,
                    "branch": branch_name,
                    "worktree_root": str(workspace_root),
                    "run_md_path": str(run_md_path),
                    "result_json_path": str(result_json_path),
                    "verdict": verdict,
                    "primary_metric_id": primary_metric_id,
                    "delta_vs_baseline": primary_delta,
                    "breakthrough": progress_eval.get("breakthrough"),
                    "breakthrough_level": progress_eval.get("breakthrough_level"),
                    "need_research_paper": delivery_policy.get("need_research_paper"),
                    "recommended_next_route": delivery_policy.get("recommended_next_route"),
                    "evaluation_summary": normalized_evaluation_summary,
                    "connector_metric_charts": metric_charts,
                }
            ],
        )
        chart_delivery = self._send_main_experiment_metric_charts(
            quest_root,
            run_id=run_identifier,
            title=title.strip() or run_identifier,
            charts=metric_charts,
        )
        best_paper_root = self.quest_service._best_paper_root(quest_root, workspace_root)
        paper_sync_workspace_root = best_paper_root.parent if best_paper_root is not None else None
        paper_line_state = (
            self._write_paper_line_state(
                quest_root,
                workspace_root=paper_sync_workspace_root,
                source_branch=branch_name,
                source_run_id=run_identifier,
                source_idea_id=active_idea_id,
            )
            if paper_sync_workspace_root is not None
            else {}
        )
        outline_path, selected_outline = self._read_selected_outline_for_sync(
            quest_root,
            workspace_root=paper_sync_workspace_root,
        )
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        detailed_outline = (
            dict(selected_outline.get("detailed_outline") or {})
            if isinstance(selected_outline.get("detailed_outline"), dict)
            else {}
        )
        outline_sections = self._normalize_outline_sections(
            selected_outline.get("sections"),
            experimental_designs=self._normalize_string_list(detailed_outline.get("experimental_designs")),
        )
        section_id = next(
            (
                str(section.get("section_id") or "").strip()
                for section in outline_sections
                if run_identifier in self._normalize_string_list(section.get("required_items"))
                or run_identifier in self._normalize_string_list(section.get("optional_items"))
            ),
            None,
        )
        if not section_id:
            section_id = next(
                (
                    str(section.get("section_id") or "").strip()
                    for section in outline_sections
                    if str(section.get("paper_role") or "main_text").strip() == "main_text"
                ),
                None,
            )
        if not section_id:
            section_id = str((outline_sections[0] or {}).get("section_id") or "").strip() if outline_sections else "main-results"
        paper_role = "main_text"
        self._upsert_paper_evidence_item(
            quest_root,
            {
                "item_id": run_identifier,
                "title": title.strip() or run_identifier,
                "kind": "main_experiment",
                "status": status,
                "paper_role": paper_role,
                "section_id": section_id,
                "claim_links": [],
                "setup": setup.strip() or None,
                "result_summary": results.strip() or conclusion.strip() or progress_eval.get("reason"),
                "key_metrics": self._paper_evidence_key_metrics(
                    metric_rows=normalized_metric_rows,
                    metrics_summary=normalized_metrics_summary,
                ),
                "source_paths": [
                    value
                    for value in [
                        self._workspace_relative(quest_root, run_md_path),
                        self._workspace_relative(quest_root, result_json_path),
                        *resolved_evidence_paths,
                    ]
                    if value
                ],
                "run_id": run_identifier,
                "selected_outline_ref": str(selected_outline.get("outline_id") or "").strip() or None,
                "paper_line_id": str(paper_line_state.get("paper_line_id") or "").strip() or None,
                "evaluation_summary": normalized_evaluation_summary,
            },
            workspace_root=paper_sync_workspace_root,
        )
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="decision")
        current_state = self.quest_service.read_research_state(quest_root)
        workspace_mode, branch_mode = self._resolve_workspace_modes(
            current_state,
            branch_name=branch_name,
            has_idea=bool(active_idea_id),
        )
        research_state = self.quest_service.update_research_state(
            quest_root,
            active_idea_id=active_idea_id,
            current_workspace_branch=branch_name,
            current_workspace_root=str(workspace_root),
            research_head_branch=branch_name,
            research_head_worktree_root=str(workspace_root),
            active_analysis_campaign_id=None,
            analysis_parent_branch=None,
            analysis_parent_worktree_root=None,
            paper_parent_branch=None,
            paper_parent_worktree_root=None,
            paper_parent_run_id=None,
            workspace_mode=workspace_mode,
            workspace_branch_mode=branch_mode,
            last_flow_type="main_experiment_recorded",
        )
        return {
            "ok": True,
            "guidance": artifact.get("guidance"),
            "guidance_vm": artifact.get("guidance_vm"),
            "next_anchor": artifact.get("next_anchor"),
            "recommended_skill_reads": artifact.get("recommended_skill_reads"),
            "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
            "next_instruction": artifact.get("next_instruction"),
            "run_id": run_identifier,
            "branch": branch_name,
            "parent_branch": parent_branch,
            "auto_promoted_run_branch": auto_promoted_run_branch,
            "run_md_path": str(run_md_path),
            "result_json_path": str(result_json_path),
            "artifact": artifact,
            "interaction": interaction,
            "connector_metric_charts": metric_charts,
            "connector_metric_chart_delivery": chart_delivery,
            "research_state": research_state,
            "metrics_summary": normalized_metrics_summary,
            "baseline_comparisons": {
                key: value for key, value in comparisons.items() if key != "primary"
            },
            "progress_eval": progress_eval,
            "evaluation_summary": normalized_evaluation_summary,
            "delivery_policy": delivery_policy,
            "metric_validation": metric_validation,
        }

    def create_analysis_campaign(
        self,
        quest_root: Path,
        *,
        campaign_title: str,
        campaign_goal: str,
        parent_run_id: str | None = None,
        slices: list[dict[str, Any]],
        campaign_origin: dict[str, Any] | None = None,
        selected_outline_ref: str | None = None,
        research_questions: list[str] | None = None,
        experimental_designs: list[str] | None = None,
        todo_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._require_baseline_gate_open(quest_root, action="create_analysis_campaign")
        state = self.quest_service.read_research_state(quest_root)
        parent_branch, parent_worktree_root, resolved_idea_id = self._resolve_analysis_parent_context(
            quest_root,
            state=state,
        )
        runtime_refs = self.resolve_runtime_refs(quest_root)
        resolved_parent_run_id = (
            str(parent_run_id or "").strip()
            or str(state.get("paper_parent_run_id") or "").strip()
            or str((self._latest_main_run_for_branch(quest_root, parent_branch) or {}).get("run_id") or "").strip()
            or str(runtime_refs.get("latest_main_run_id") or "").strip()
            or None
        )
        active_idea_id = str(resolved_idea_id or "").strip()
        if not active_idea_id:
            raise ValueError("An active idea is required before starting an analysis campaign.")
        if not slices:
            raise ValueError("At least one analysis slice is required.")
        campaign_id = generate_id("analysis")
        charter_dir = ensure_dir(parent_worktree_root / "experiments" / "analysis-results" / campaign_id)
        charter_path = charter_dir / "campaign.md"
        normalized_campaign_origin = self._normalize_campaign_origin(campaign_origin)
        resolved_outline_ref = str(selected_outline_ref or "").strip() or None
        normalized_research_questions = self._normalize_string_list(research_questions)
        normalized_experimental_designs = self._normalize_string_list(experimental_designs)
        normalized_todo_items = self._normalize_campaign_todo_items(todo_items)
        quest_data = self.quest_service.read_quest_yaml(quest_root)
        active_anchor = str(quest_data.get("active_anchor") or "").strip().lower()
        campaign_origin_kind = (
            str(normalized_campaign_origin.get("kind") or "").strip().lower()
            if isinstance(normalized_campaign_origin, dict)
            else ""
        )
        writing_facing = bool(
            resolved_outline_ref
            or normalized_research_questions
            or normalized_experimental_designs
            or normalized_todo_items
            or self._active_workspace_branch_mode(
                state,
                branch_name=str(state.get("current_workspace_branch") or "").strip(),
            ) == "paper"
            or active_anchor == "write"
            or campaign_origin_kind in {"write", "paper", "rebuttal", "revision"}
        )
        if writing_facing:
            if not resolved_outline_ref:
                outlines = self.list_paper_outlines(quest_root)
                candidate_outline_ids = [
                    str(item.get("outline_id") or "").strip()
                    for item in (outlines.get("outlines") or [])
                    if str(item.get("status") or "").strip() in {"candidate", "revised"}
                    and str(item.get("outline_id") or "").strip()
                ]
                candidate_hint = (
                    f" Candidate outlines: {', '.join(candidate_outline_ids[:5])}."
                    if candidate_outline_ids
                    else ""
                )
                raise ValueError(
                    "Writing-facing analysis campaigns require `selected_outline_ref` before slices can be launched."
                    + candidate_hint
                    + " Fix this by selecting or revising an outline with "
                    + "`artifact.submit_paper_outline(mode='select'|'revise', ...)`, "
                    + "or downgrade this work to a pre-outline analysis-lite / non-writing-facing campaign if it is only exploratory evidence."
                )
            if not normalized_research_questions:
                raise ValueError(
                    "Writing-facing analysis campaigns require non-empty `research_questions`."
                )
            if not normalized_experimental_designs:
                raise ValueError(
                    "Writing-facing analysis campaigns require non-empty `experimental_designs`."
                )
            if not normalized_todo_items:
                raise ValueError(
                    "Writing-facing analysis campaigns require non-empty `todo_items`."
                )
            todo_slice_ids = {
                str(item.get("slice_id") or "").strip()
                for item in normalized_todo_items
                if str(item.get("slice_id") or "").strip()
            }
            missing_slice_ids = [
                str(raw.get("slice_id") or "").strip()
                for raw in slices
                if str(raw.get("slice_id") or "").strip() and str(raw.get("slice_id") or "").strip() not in todo_slice_ids
            ]
            if missing_slice_ids:
                raise ValueError(
                    "Writing-facing analysis campaigns require one todo item per slice. "
                    f"Missing todo items for: {', '.join(missing_slice_ids)}."
                )
            missing_contract_fields: list[str] = []
            for item in normalized_todo_items:
                title = str(item.get("title") or item.get("slice_id") or item.get("todo_id") or "todo").strip() or "todo"
                for field in ("section_id", "item_id", "paper_role"):
                    if str(item.get(field) or "").strip():
                        continue
                    missing_contract_fields.append(f"{title}:{field}")
                if not self._normalize_string_list(item.get("claim_links")):
                    missing_contract_fields.append(f"{title}:claim_links")
            if missing_contract_fields:
                raise ValueError(
                    "Writing-facing analysis campaigns require outline-bound paper contract fields for every todo item. "
                    f"Missing: {', '.join(missing_contract_fields[:8])}."
                )
        paper_line_branch: str | None = None
        paper_line_root: str | None = None
        paper_line_id: str | None = None
        if writing_facing:
            paper_context = self._ensure_active_paper_workspace(
                quest_root,
                source_branch=parent_branch,
                source_run_id=resolved_parent_run_id,
                source_idea_id=active_idea_id,
            )
            paper_line_branch = str(paper_context.get("branch") or "").strip() or None
            paper_line_root = str(paper_context.get("worktree_root") or "").strip() or None
            paper_line_id = self._paper_line_id(
                paper_branch=paper_line_branch,
                outline_id=resolved_outline_ref,
                source_run_id=resolved_parent_run_id,
            )
            if paper_line_root:
                self._write_paper_line_state(
                    quest_root,
                    workspace_root=Path(paper_line_root),
                    source_branch=parent_branch,
                    source_run_id=resolved_parent_run_id,
                    source_idea_id=active_idea_id,
                )
        slice_contexts: list[dict[str, Any]] = []
        inventory_entries: list[dict[str, Any]] = []
        for index, raw in enumerate(slices, start=1):
            slice_id = str(raw.get("slice_id") or generate_id("slice")).strip()
            title = str(raw.get("title") or slice_id).strip() or slice_id
            matched_todo = next(
                (
                    item
                    for item in normalized_todo_items
                    if str(item.get("slice_id") or "").strip() == slice_id
                ),
                normalized_todo_items[index - 1] if index - 1 < len(normalized_todo_items) else {},
            )
            branch = f"analysis/{active_idea_id}/{campaign_id}-{slugify(slice_id, 'slice')}"
            worktree_root = canonical_worktree_root(quest_root, f"analysis-{campaign_id}-{slice_id}")
            ensure_branch(quest_root, branch, start_point=parent_branch, checkout=False)
            create_worktree(
                quest_root,
                branch=branch,
                worktree_root=worktree_root,
                start_point=parent_branch,
            )
            reviewer_item_ids = self._normalize_string_list(
                raw.get("reviewer_item_ids") or matched_todo.get("reviewer_item_ids")
            )
            manuscript_targets = self._normalize_string_list(
                raw.get("manuscript_targets") or matched_todo.get("manuscript_targets")
            )
            section_id = str(raw.get("section_id") or matched_todo.get("section_id") or "").strip() or None
            item_id = str(raw.get("item_id") or matched_todo.get("item_id") or slice_id).strip() or slice_id
            claim_links = self._normalize_string_list(raw.get("claim_links") or matched_todo.get("claim_links"))
            paper_role = (
                str(raw.get("paper_role") or matched_todo.get("paper_role") or matched_todo.get("paper_placement") or "").strip()
                or None
            )
            paper_placement = (
                str(raw.get("paper_placement") or matched_todo.get("paper_placement") or paper_role or "").strip()
                or None
            )
            tier = str(raw.get("tier") or matched_todo.get("tier") or "").strip() or None
            exp_id = str(raw.get("exp_id") or matched_todo.get("exp_id") or "").strip() or None
            why_now = str(raw.get("why_now") or matched_todo.get("why_now") or "").strip()
            success_criteria = str(raw.get("success_criteria") or matched_todo.get("success_criteria") or "").strip()
            abandonment_criteria = str(
                raw.get("abandonment_criteria") or matched_todo.get("abandonment_criteria") or ""
            ).strip()
            required_baselines = self._normalize_required_baselines(
                quest_root,
                raw.get("required_baselines") or matched_todo.get("required_baselines"),
            )
            plan_dir = ensure_dir(worktree_root / "experiments" / "analysis" / campaign_id / slice_id)
            plan_path = plan_dir / "plan.md"
            requirement_lines = [
                f"# {title}",
                "",
                "## Goal",
                "",
                str(raw.get("goal") or "").strip() or "TBD",
                "",
                "## Research Question",
                "",
                str(raw.get("research_question") or matched_todo.get("research_question") or "").strip() or "TBD",
                "",
                    "## Experimental Design",
                    "",
                    str(raw.get("experimental_design") or matched_todo.get("experimental_design") or "").strip() or "TBD",
                    "",
                    "## Paper Contract Binding",
                    "",
                    f"- Section id: `{section_id or 'none'}`",
                    f"- Item id: `{item_id}`",
                    f"- Exp id: `{exp_id or 'none'}`",
                    f"- Paper role: `{paper_role or 'none'}`",
                    f"- Paper placement: `{paper_placement or 'none'}`",
                    f"- Tier: `{tier or 'none'}`",
                    f"- Claim links: {', '.join(claim_links) or 'none'}",
                    "",
                    "## Why Now",
                    "",
                    why_now or "TBD",
                    "",
                "## Hypothesis",
                "",
                str(raw.get("hypothesis") or "").strip() or "TBD",
                "",
                "## Required Changes",
                "",
                str(raw.get("required_changes") or "").strip() or "TBD",
                "",
                "## Required Baselines",
                "",
            ]
            if required_baselines:
                requirement_lines.extend([f"- {self._analysis_baseline_label(item)}" for item in required_baselines])
            else:
                requirement_lines.append("- None recorded.")
            requirement_lines.extend(
                [
                    "",
                    "## Metric Contract",
                    "",
                    str(raw.get("metric_contract") or "").strip() or "TBD",
                    "",
                    "## Environment Notes",
                    "",
                    str(raw.get("environment_notes") or "").strip() or "TBD",
                    "",
                    "## Must Not Simplify",
                    "",
                    str(raw.get("must_not_simplify") or "").strip() or "Full dataset / full protocol only unless explicitly approved.",
                    "",
                    "## Success Criteria",
                    "",
                    success_criteria or "TBD",
                    "",
                    "## Abandonment Criteria",
                    "",
                    abandonment_criteria or "TBD",
                    "",
                    "## Completion Condition",
                    "",
                    str(raw.get("completion_condition") or matched_todo.get("completion_condition") or "").strip()
                    or str(raw.get("must_not_simplify") or matched_todo.get("must_not_simplify") or "").strip()
                    or "Complete the planned analysis slice and mirror the durable result back to the parent branch.",
                    "",
                ]
            )
            requirement_lines.extend(["## Reviewer Item IDs", ""])
            if reviewer_item_ids:
                requirement_lines.extend([f"- `{item}`" for item in reviewer_item_ids])
            else:
                requirement_lines.append("- None recorded.")
            requirement_lines.extend(["", "## Manuscript Targets", ""])
            if manuscript_targets:
                requirement_lines.extend([f"- {item}" for item in manuscript_targets])
            else:
                requirement_lines.append("- None recorded.")
            requirement_lines.append("")
            write_text(plan_path, "\n".join(requirement_lines))
            slice_contexts.append(
                {
                    "index": index,
                    "slice_id": slice_id,
                    "title": title,
                    "status": "pending",
                    "branch": branch,
                    "worktree_root": str(worktree_root),
                    "plan_path": str(plan_path),
                    "run_kind": str(raw.get("run_kind") or "analysis.slice").strip() or "analysis.slice",
                    "goal": str(raw.get("goal") or "").strip(),
                    "research_question": str(
                        raw.get("research_question") or matched_todo.get("research_question") or ""
                    ).strip(),
                    "experimental_design": str(
                        raw.get("experimental_design") or matched_todo.get("experimental_design") or ""
                    ).strip(),
                    "section_id": section_id,
                    "item_id": item_id,
                    "exp_id": exp_id,
                    "paper_role": paper_role,
                    "paper_placement": paper_placement,
                    "tier": tier,
                    "claim_links": claim_links,
                    "why_now": why_now,
                    "hypothesis": str(raw.get("hypothesis") or "").strip(),
                    "required_changes": str(raw.get("required_changes") or "").strip(),
                    "metric_contract": str(raw.get("metric_contract") or "").strip(),
                    "environment_notes": str(raw.get("environment_notes") or "").strip(),
                    "must_not_simplify": str(raw.get("must_not_simplify") or "").strip(),
                    "success_criteria": success_criteria,
                    "abandonment_criteria": abandonment_criteria,
                    "completion_condition": str(
                        raw.get("completion_condition") or matched_todo.get("completion_condition") or ""
                    ).strip(),
                    "required_baselines": required_baselines,
                    "reviewer_item_ids": reviewer_item_ids,
                    "manuscript_targets": manuscript_targets,
                }
                )
            inventory_entries.extend(
                [
                    {
                        "baseline_id": item.get("baseline_id"),
                        "variant_id": item.get("variant_id"),
                        "usage_scope": "supplementary",
                        "status": "required",
                        "reason": item.get("reason"),
                        "benchmark": item.get("benchmark"),
                        "split": item.get("split"),
                        "baseline_root_rel_path": item.get("baseline_root_rel_path"),
                        "storage_mode": item.get("storage_mode"),
                        "origin": {
                            "stage": "analysis_campaign",
                            "campaign_id": campaign_id,
                            "slice_id": slice_id,
                        },
                    }
                    for item in required_baselines
                ]
            )

        todo_manifest = {
            "schema_version": 1,
            "campaign_id": campaign_id,
            "campaign_origin": normalized_campaign_origin,
            "selected_outline_ref": resolved_outline_ref,
            "research_questions": normalized_research_questions,
            "experimental_designs": normalized_experimental_designs,
            "todo_items": [
                {
                    "exp_id": str(item.get("exp_id") or context.get("exp_id") or "").strip() or None,
                    "todo_id": str(item.get("todo_id") or item.get("slice_id") or context["slice_id"]).strip() or context["slice_id"],
                    "slice_id": context["slice_id"],
                    "title": str(item.get("title") or context["title"]).strip() or context["title"],
                    "status": str(item.get("status") or "pending").strip() or "pending",
                    "research_question": item.get("research_question") or context.get("research_question"),
                    "experimental_design": item.get("experimental_design") or context.get("experimental_design"),
                    "tier": item.get("tier") or context.get("tier"),
                    "paper_placement": item.get("paper_placement") or context.get("paper_placement"),
                    "paper_role": item.get("paper_role") or context.get("paper_role"),
                    "section_id": item.get("section_id") or context.get("section_id"),
                    "item_id": item.get("item_id") or context.get("item_id"),
                    "claim_links": item.get("claim_links") or context.get("claim_links") or [],
                    "completion_condition": item.get("completion_condition") or context.get("completion_condition") or context.get("must_not_simplify"),
                    "why_now": item.get("why_now") or context.get("why_now"),
                    "success_criteria": item.get("success_criteria") or context.get("success_criteria"),
                    "abandonment_criteria": item.get("abandonment_criteria") or context.get("abandonment_criteria"),
                    "required_baselines": item.get("required_baselines") or context.get("required_baselines") or [],
                    "reviewer_item_ids": item.get("reviewer_item_ids") or context.get("reviewer_item_ids") or [],
                    "manuscript_targets": item.get("manuscript_targets") or context.get("manuscript_targets") or [],
                }
                for context, item in zip(slice_contexts, normalized_todo_items + [{}] * max(0, len(slice_contexts) - len(normalized_todo_items)))
            ],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        todo_manifest_path = charter_dir / "todo_manifest.json"
        write_json(todo_manifest_path, todo_manifest)

        charter_lines = [
            f"# {campaign_title}",
            "",
            "## Goal",
            "",
            campaign_goal.strip() or "TBD",
            "",
            "## Parent Branch",
            "",
            f"`{parent_branch}`",
            "",
            "## Parent Worktree",
            "",
            f"`{parent_worktree_root}`",
            "",
            "## Selected Outline",
            "",
            f"`{resolved_outline_ref or 'none'}`",
            "",
            "## Campaign Origin",
            "",
            f"- Kind: `{(normalized_campaign_origin or {}).get('kind') or 'analysis'}`",
            f"- Reason: {str((normalized_campaign_origin or {}).get('reason') or 'Not recorded')}",
            f"- Source Artifact: `{str((normalized_campaign_origin or {}).get('source_artifact_id') or 'none')}`",
            f"- Source Outline: `{str((normalized_campaign_origin or {}).get('source_outline_ref') or 'none')}`",
            f"- Source Review Round: `{str((normalized_campaign_origin or {}).get('source_review_round') or 'none')}`",
            "",
            "## Slices",
            "",
        ]
        for item in slice_contexts:
            charter_lines.extend(
                [
                    f"### {item['slice_id']} · {item['title']}",
                    "",
                    f"- Branch: `{item['branch']}`",
                    f"- Worktree: `{item['worktree_root']}`",
                    f"- Plan: `{item['plan_path']}`",
                    f"- Run kind: `{item['run_kind']}`",
                    f"- Goal: {item['goal'] or 'TBD'}",
                    f"- Research question: {item['research_question'] or 'TBD'}",
                    f"- Experimental design: {item['experimental_design'] or 'TBD'}",
                    f"- Section id: `{item['section_id'] or 'none'}`",
                    f"- Item id: `{item['item_id'] or 'none'}`",
                    f"- Exp id: `{item['exp_id'] or 'none'}`",
                    f"- Paper role: `{item['paper_role'] or 'none'}`",
                    f"- Claim links: {', '.join(item['claim_links']) or 'none'}",
                    f"- Why now: {item['why_now'] or 'TBD'}",
                    f"- Required baselines: {', '.join(self._analysis_baseline_label(entry) for entry in item['required_baselines']) or 'none'}",
                    f"- Success criteria: {item['success_criteria'] or 'TBD'}",
                    f"- Abandonment criteria: {item['abandonment_criteria'] or 'TBD'}",
                    f"- Completion condition: {item['completion_condition'] or item['must_not_simplify'] or 'TBD'}",
                    f"- Requirement: {item['must_not_simplify'] or 'TBD'}",
                    f"- Reviewer items: {', '.join(item['reviewer_item_ids']) or 'none'}",
                    f"- Manuscript targets: {', '.join(item['manuscript_targets']) or 'none'}",
                    "",
                ]
            )
        write_text(charter_path, "\n".join(charter_lines).rstrip() + "\n")
        manifest = self._write_analysis_manifest(
            quest_root,
            campaign_id,
            {
                "title": campaign_title,
                "goal": campaign_goal,
                "parent_run_id": resolved_parent_run_id,
                "active_idea_id": active_idea_id,
                "parent_branch": parent_branch,
                "parent_worktree_root": str(parent_worktree_root),
                "paper_line_id": paper_line_id,
                "paper_line_branch": paper_line_branch,
                "paper_line_root": paper_line_root,
                "campaign_origin": normalized_campaign_origin,
                "selected_outline_ref": resolved_outline_ref,
                "research_questions": normalized_research_questions,
                "experimental_designs": normalized_experimental_designs,
                "todo_items": todo_manifest["todo_items"],
                "todo_manifest_path": str(todo_manifest_path),
                "charter_path": str(charter_path),
                "slices": slice_contexts,
                "created_at": utc_now(),
            },
        )
        for item in slice_contexts:
            self.record(
                quest_root,
                {
                    "kind": "milestone",
                    "status": "prepared",
                    "summary": f"Analysis slice `{item['slice_id']}` prepared as a child branch.",
                    "reason": "Expose the pending follow-up branch durably so Canvas and Git lineage stay visible before execution.",
                    "idea_id": active_idea_id,
                    "campaign_id": campaign_id,
                    "slice_id": item["slice_id"],
                    "branch": item["branch"],
                    "parent_branch": parent_branch,
                    "worktree_root": item["worktree_root"],
                    "worktree_rel_path": self._workspace_relative(quest_root, Path(item["worktree_root"])),
                    "flow_type": "analysis_slice",
                    "protocol_step": "prepare",
                    "paths": {
                        "plan_md": item["plan_path"],
                    },
                    "details": {
                        "title": item["title"],
                        "goal": item["goal"],
                        "run_kind": item["run_kind"],
                        "research_question": item["research_question"],
                        "experimental_design": item["experimental_design"],
                        "section_id": item["section_id"],
                        "item_id": item["item_id"],
                        "exp_id": item["exp_id"],
                        "paper_role": item["paper_role"],
                        "paper_placement": item["paper_placement"],
                        "tier": item["tier"],
                        "claim_links": item["claim_links"],
                        "why_now": item["why_now"],
                        "completion_condition": item["completion_condition"] or item["must_not_simplify"],
                        "must_not_simplify": item["must_not_simplify"],
                        "required_baselines": item["required_baselines"],
                        "success_criteria": item["success_criteria"],
                        "abandonment_criteria": item["abandonment_criteria"],
                        "reviewer_item_ids": item["reviewer_item_ids"],
                        "manuscript_targets": item["manuscript_targets"],
                    },
                },
                checkpoint=False,
                workspace_root=Path(item["worktree_root"]),
            )
        first_slice = slice_contexts[0]
        artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": "analysis_campaign_create",
                "summary": f"Analysis campaign `{campaign_id}` created with {len(slice_contexts)} slices.",
                "reason": "The main experiment completed and now requires structured follow-up analysis slices.",
                "idea_id": active_idea_id,
                "campaign_id": campaign_id,
                "branch": parent_branch,
                "worktree_root": str(parent_worktree_root),
                "flow_type": "analysis_campaign",
                "protocol_step": "create",
                "paths": {
                    "campaign_md": str(charter_path),
                },
                "details": {
                    "campaign_title": campaign_title,
                    "campaign_goal": campaign_goal,
                    "parent_run_id": resolved_parent_run_id,
                    "paper_line_id": paper_line_id,
                    "paper_line_branch": paper_line_branch,
                    "paper_line_root": paper_line_root,
                    "campaign_origin": normalized_campaign_origin,
                    "selected_outline_ref": resolved_outline_ref,
                    "todo_manifest_path": str(todo_manifest_path),
                    "slice_count": len(slice_contexts),
                    "slices": [
                        {
                            "slice_id": item["slice_id"],
                            "title": item["title"],
                            "branch": item["branch"],
                            "worktree_root": item["worktree_root"],
                            "run_kind": item["run_kind"],
                            "goal": item["goal"],
                            "research_question": item["research_question"],
                            "experimental_design": item["experimental_design"],
                            "section_id": item["section_id"],
                            "item_id": item["item_id"],
                            "exp_id": item["exp_id"],
                            "paper_role": item["paper_role"],
                            "paper_placement": item["paper_placement"],
                            "tier": item["tier"],
                            "claim_links": item["claim_links"],
                            "why_now": item["why_now"],
                            "completion_condition": item["completion_condition"] or item["must_not_simplify"],
                            "must_not_simplify": item["must_not_simplify"],
                            "required_baselines": item["required_baselines"],
                            "success_criteria": item["success_criteria"],
                            "abandonment_criteria": item["abandonment_criteria"],
                            "reviewer_item_ids": item["reviewer_item_ids"],
                            "manuscript_targets": item["manuscript_targets"],
                        }
                        for item in slice_contexts
                    ],
                },
            },
            checkpoint=False,
            workspace_root=parent_worktree_root,
        )
        if writing_facing:
            self._sync_outline_sections(
                quest_root,
                items=[
                    {
                        "item_id": item.get("item_id"),
                        "title": item.get("title"),
                        "kind": "analysis_slice",
                        "paper_role": item.get("paper_role"),
                        "status": "pending",
                        "claim_links": item.get("claim_links"),
                        "section_id": item.get("section_id"),
                        "source_paths": [self._workspace_relative(quest_root, Path(item["plan_path"]))] if item.get("plan_path") else [],
                    }
                    for item in slice_contexts
                ],
                workspace_root=Path(paper_line_root) if paper_line_root else None,
            )
            if paper_line_root:
                self._write_paper_line_state(
                    quest_root,
                    workspace_root=Path(paper_line_root),
                    source_branch=parent_branch,
                    source_run_id=resolved_parent_run_id,
                    source_idea_id=active_idea_id,
                )
        current_state = self.quest_service.read_research_state(quest_root)
        workspace_mode, branch_mode = self._resolve_workspace_modes(
            current_state,
            branch_name=first_slice["branch"],
        )
        research_state = self.quest_service.update_research_state(
            quest_root,
            active_idea_id=active_idea_id,
            active_analysis_campaign_id=campaign_id,
            analysis_parent_branch=parent_branch,
            analysis_parent_worktree_root=str(parent_worktree_root),
            next_pending_slice_id=first_slice["slice_id"],
            current_workspace_branch=first_slice["branch"],
            current_workspace_root=first_slice["worktree_root"],
            workspace_mode=workspace_mode,
            workspace_branch_mode=branch_mode,
            last_flow_type="analysis_campaign",
        )
        baseline_inventory = self._upsert_analysis_baseline_inventory(quest_root, inventory_entries) if inventory_entries else None
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="analysis-campaign")
        checkpoint_result = self._checkpoint_with_optional_push(
            parent_worktree_root,
            message=f"analysis: create {campaign_id}",
        )
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=self._build_analysis_campaign_interaction_message(
                campaign_id=campaign_id,
                goal=campaign_goal,
                parent_branch=parent_branch,
                selected_outline_ref=resolved_outline_ref,
                first_slice=first_slice,
                todo_manifest_rel_path=self._workspace_relative(quest_root, todo_manifest_path),
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "analysis_campaign",
                    "campaign_id": campaign_id,
                    "parent_branch": parent_branch,
                    "parent_worktree_root": str(parent_worktree_root),
                    "campaign_origin": normalized_campaign_origin,
                    "selected_outline_ref": resolved_outline_ref,
                    "todo_manifest_path": str(todo_manifest_path),
                    "next_slice": first_slice,
                    "todo_items": todo_manifest["todo_items"],
                    "slices": slice_contexts,
                }
            ],
        )
        return {
            "ok": True,
            "guidance": artifact.get("guidance"),
            "guidance_vm": artifact.get("guidance_vm"),
            "next_anchor": artifact.get("next_anchor"),
            "recommended_skill_reads": artifact.get("recommended_skill_reads"),
            "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
            "next_instruction": artifact.get("next_instruction"),
            "campaign_id": campaign_id,
            "parent_branch": parent_branch,
            "parent_worktree_root": str(parent_worktree_root),
            "campaign_origin": normalized_campaign_origin,
            "charter_path": str(charter_path),
            "slices": slice_contexts,
            "manifest": manifest,
            "analysis_baseline_inventory": baseline_inventory,
            "todo_manifest_path": str(todo_manifest_path),
            "artifact": artifact,
            "checkpoint": checkpoint_result,
            "interaction": interaction,
            "research_state": research_state,
        }

    def submit_paper_outline(
        self,
        quest_root: Path,
        *,
        mode: str = "candidate",
        outline_id: str | None = None,
        title: str = "",
        note: str = "",
        story: str = "",
        ten_questions: list[str] | None = None,
        detailed_outline: dict[str, Any] | None = None,
        review_result: str | None = None,
        selected_reason: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "candidate").strip().lower()
        if normalized_mode not in {"candidate", "select", "revise"}:
            raise ValueError("submit_paper_outline mode must be `candidate`, `select`, or `revise`.")

        paper_context = (
            self._ensure_active_paper_workspace(quest_root)
            if normalized_mode in {"select", "revise"}
            else {
                "worktree_root": str(self._workspace_root_for(quest_root)),
                "branch": str(self.quest_service.read_research_state(quest_root).get("current_workspace_branch") or "").strip() or None,
            }
        )
        workspace_root = Path(str(paper_context.get("worktree_root") or self._workspace_root_for(quest_root)))
        paper_root = (
            ensure_dir(workspace_root / "paper")
            if normalized_mode in {"select", "revise"}
            else self._paper_root(quest_root, workspace_root=workspace_root, create=True)
        )
        if normalized_mode in {"select", "revise"}:
            selected_outline_path = paper_root / "selected_outline.json"
        else:
            selected_outline_path = self._paper_selected_outline_path(quest_root, workspace_root=workspace_root)
        _, existing_selected = self._read_selected_outline_record(quest_root, workspace_root=workspace_root)
        existing_selected = existing_selected if isinstance(existing_selected, dict) else {}
        if normalized_mode == "candidate":
            resolved_outline_id = str(outline_id or self._next_paper_outline_id(quest_root)).strip()
            candidate_path = self._paper_outline_candidates_root(quest_root, workspace_root=workspace_root) / f"{resolved_outline_id}.json"
            canonical_candidate_path = quest_root / "paper" / "outlines" / "candidates" / f"{resolved_outline_id}.json"
            existing = read_json(candidate_path, {})
            existing = existing if isinstance(existing, dict) else {}
            record = self._normalize_paper_outline_record(
                outline_id=resolved_outline_id,
                title=title or existing.get("title"),
                note=note or existing.get("note"),
                story=story or existing.get("story"),
                ten_questions=ten_questions or existing.get("ten_questions"),
                detailed_outline=detailed_outline or existing.get("detailed_outline"),
                review_result=review_result or existing.get("review_result"),
                status="candidate",
                created_at=str(existing.get("created_at") or "") or None,
            )
            write_json(candidate_path, record)
            if canonical_candidate_path.resolve() != candidate_path.resolve():
                write_json(canonical_candidate_path, record)
            artifact = self.record(
                quest_root,
                {
                    "kind": "report",
                    "status": "completed",
                    "report_type": "paper_outline_candidate",
                    "summary": f"Paper outline candidate `{resolved_outline_id}` submitted.",
                    "reason": note or "Paper outline candidate recorded for later comparison and selection.",
                    "flow_type": "paper_outline",
                    "protocol_step": "candidate",
                    "paths": {
                        "outline_json": str(candidate_path),
                    },
                    "details": {
                        "outline_id": resolved_outline_id,
                        "title": record.get("title"),
                        "review_result": record.get("review_result"),
                    },
                },
                checkpoint=False,
                workspace_root=workspace_root,
            )
            return {
                "ok": True,
                "mode": normalized_mode,
                "outline_id": resolved_outline_id,
                "outline_path": str(candidate_path),
                "record": record,
                "artifact": artifact,
            }

        source_outline_id = str(outline_id or existing_selected.get("outline_id") or "").strip()
        if not source_outline_id:
            raise ValueError("submit_paper_outline(select/revise) requires an existing `outline_id` or selected outline.")
        source_candidate_path = paper_root / "outlines" / "candidates" / f"{source_outline_id}.json"
        source_record = read_json(source_candidate_path, {})
        if not isinstance(source_record, dict) or not source_record:
            fallback_candidate_path = quest_root / "paper" / "outlines" / "candidates" / f"{source_outline_id}.json"
            source_record = read_json(fallback_candidate_path, {})
            if isinstance(source_record, dict) and source_record:
                source_candidate_path = fallback_candidate_path
        if not isinstance(source_record, dict) or not source_record:
            source_record = existing_selected if str(existing_selected.get("outline_id") or "").strip() == source_outline_id else {}
        if not source_record:
            raise FileNotFoundError(f"Unknown paper outline `{source_outline_id}`.")

        source_detailed_outline = (
            dict(detailed_outline or {})
            if isinstance(detailed_outline, dict)
            else dict(source_record.get("detailed_outline") or {})
            if isinstance(source_record.get("detailed_outline"), dict)
            else {}
        )
        if "sections" not in source_detailed_outline and isinstance(source_record.get("sections"), list):
            source_detailed_outline["sections"] = [dict(item) for item in source_record.get("sections") or [] if isinstance(item, dict)]

        resolved_record = self._normalize_paper_outline_record(
            outline_id=source_outline_id,
            title=title or source_record.get("title"),
            note=note or source_record.get("note"),
            story=story or source_record.get("story"),
            ten_questions=ten_questions or source_record.get("ten_questions"),
            detailed_outline=source_detailed_outline,
            review_result=review_result or source_record.get("review_result"),
            status="selected" if normalized_mode == "select" else "revised",
            created_at=str(source_record.get("created_at") or "") or None,
        )

        self._write_selected_outline_sync(quest_root, resolved_record, workspace_root=workspace_root)
        existing_ledger = self._read_paper_evidence_ledger(quest_root)
        existing_items = [dict(item) for item in (existing_ledger.get("items") or []) if isinstance(item, dict)]
        if existing_items:
            self._sync_outline_sections(
                quest_root,
                items=[
                    {
                        "item_id": item.get("item_id"),
                        "title": item.get("title"),
                        "kind": item.get("kind"),
                        "paper_role": item.get("paper_role"),
                        "status": item.get("status"),
                        "claim_links": item.get("claim_links"),
                        "section_id": item.get("section_id"),
                        "setup": item.get("setup"),
                        "metric_summary": self._paper_metric_summary_text(
                            [dict(metric) for metric in (item.get("key_metrics") or []) if isinstance(metric, dict)]
                        ),
                        "result_summary": item.get("result_summary"),
                        "claim_impact": item.get("claim_impact"),
                        "source_paths": item.get("source_paths"),
                    }
                    for item in existing_items
                ],
                workspace_root=workspace_root,
            )
        selected_outline_path = paper_root / "selected_outline.json"
        if source_candidate_path.exists():
            source_record["status"] = "selected" if normalized_mode == "select" else "revised"
            source_record["updated_at"] = utc_now()
            write_json(source_candidate_path, source_record)
        revised_outline_path = None
        if normalized_mode == "revise":
            revised_outline_path = ensure_dir(paper_root / "outlines" / "revisions") / f"{source_outline_id}.json"
            write_json(revised_outline_path, resolved_record)
            canonical_revised_outline_path = quest_root / "paper" / "outlines" / "revisions" / f"{source_outline_id}.json"
            if canonical_revised_outline_path.resolve() != revised_outline_path.resolve():
                write_json(canonical_revised_outline_path, resolved_record)

        outline_selection_path = paper_root / "outline_selection.md"
        action_label = "selected" if normalized_mode == "select" else "revised"
        selection_lines = [
            f"# Outline {normalized_mode.capitalize()}",
            "",
            f"- Outline ID: `{source_outline_id}`",
            f"- Title: {resolved_record.get('title') or source_outline_id}",
            f"- Mode: `{normalized_mode}`",
            f"- Reason: {str(selected_reason or note or 'Not recorded').strip() or 'Not recorded'}",
            "",
            "## Note",
            "",
            str(resolved_record.get("note") or "Not recorded"),
            "",
        ]
        write_text(outline_selection_path, "\n".join(selection_lines).rstrip() + "\n")
        paper_line_state = self._write_paper_line_state(
            quest_root,
            workspace_root=workspace_root,
            source_branch=str(paper_context.get("source_branch") or "").strip() or None,
            source_run_id=str(paper_context.get("source_run_id") or "").strip() or None,
            source_idea_id=str(paper_context.get("source_idea_id") or "").strip() or None,
        )
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="write")
        artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": "paper_outline_selected" if normalized_mode == "select" else "paper_outline_revised",
                "summary": f"Paper outline `{source_outline_id}` {action_label}.",
                "reason": selected_reason or note or "Paper outline promoted into the active paper stage.",
                "flow_type": "paper_outline",
                "protocol_step": "select" if normalized_mode == "select" else "revise",
                "paths": {
                    "selected_outline_json": str(selected_outline_path),
                    "outline_manifest_json": str(self._paper_outline_manifest_path(quest_root, workspace_root=workspace_root)),
                    "outline_selection_md": str(outline_selection_path),
                    "paper_line_state_json": str(self._paper_line_state_path(quest_root, workspace_root=workspace_root)),
                    **({"revised_outline_json": str(revised_outline_path)} if revised_outline_path else {}),
                },
                "details": {
                    "outline_id": source_outline_id,
                    "title": resolved_record.get("title"),
                    "selected_reason": selected_reason,
                    "paper_line_id": paper_line_state.get("paper_line_id"),
                    "paper_branch": paper_line_state.get("paper_branch"),
                },
            },
            checkpoint=False,
            workspace_root=workspace_root,
        )
        selected_outline_rel_path = self._workspace_relative(quest_root, selected_outline_path)
        outline_selection_rel_path = self._workspace_relative(quest_root, outline_selection_path)
        revised_outline_rel_path = self._workspace_relative(quest_root, revised_outline_path) if revised_outline_path else None
        interaction = self.interact(
            quest_root,
            kind="milestone" if normalized_mode == "select" else "progress",
            message=self._build_outline_interaction_message(
                action=normalized_mode,
                outline_id=source_outline_id,
                title=str(resolved_record.get("title") or "").strip() or source_outline_id,
                selected_reason=selected_reason or note,
                story=str(resolved_record.get("story") or "").strip() or None,
                research_questions=(
                    (resolved_record.get("detailed_outline") or {})
                    if isinstance(resolved_record.get("detailed_outline"), dict)
                    else {}
                ).get("research_questions"),
                experimental_designs=(
                    (resolved_record.get("detailed_outline") or {})
                    if isinstance(resolved_record.get("detailed_outline"), dict)
                    else {}
                ).get("experimental_designs"),
                selected_outline_rel_path=selected_outline_rel_path,
                outline_selection_rel_path=outline_selection_rel_path,
                revised_outline_rel_path=revised_outline_rel_path,
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "paper_outline_selected" if normalized_mode == "select" else "paper_outline_revised",
                    "outline_id": source_outline_id,
                    "title": resolved_record.get("title"),
                    "selected_reason": selected_reason,
                    "selected_outline_path": str(selected_outline_path),
                    "outline_manifest_path": str(self._paper_outline_manifest_path(quest_root, workspace_root=workspace_root)),
                    "paper_line_state_path": str(self._paper_line_state_path(quest_root, workspace_root=workspace_root)),
                    "outline_selection_path": str(outline_selection_path),
                    "revised_outline_path": str(revised_outline_path) if revised_outline_path else None,
                }
            ],
        )
        return {
            "ok": True,
            "mode": normalized_mode,
            "outline_id": source_outline_id,
            "selected_outline_path": str(selected_outline_path),
            "outline_manifest_path": str(self._paper_outline_manifest_path(quest_root, workspace_root=workspace_root)),
            "paper_line_state_path": str(self._paper_line_state_path(quest_root, workspace_root=workspace_root)),
            "outline_selection_path": str(outline_selection_path),
            "revised_outline_path": str(revised_outline_path) if revised_outline_path else None,
            "record": resolved_record,
            "paper_line_state": paper_line_state,
            "artifact": artifact,
            "interaction": interaction,
        }

    def submit_paper_bundle(
        self,
        quest_root: Path,
        *,
        title: str | None = None,
        summary: str = "",
        outline_path: str | None = None,
        draft_path: str | None = None,
        writing_plan_path: str | None = None,
        references_path: str | None = None,
        claim_evidence_map_path: str | None = None,
        compile_report_path: str | None = None,
        pdf_path: str | None = None,
        latex_root_path: str | None = None,
        package_type: str = "draft_checkpoint",
        prepare_open_source: bool = False,
    ) -> dict[str, Any]:
        from .experience_distill import evaluate_distill_gate_for_quest

        gate_payload = evaluate_distill_gate_for_quest(quest_root)
        if gate_payload is not None:
            pending_ids = ", ".join(gate_payload.get("pending_distill_ids") or []) or "(none listed)"
            raise ValueError(
                "submit_paper_bundle blocked: experience_distill is on and "
                f"{gate_payload['pending_distill_count']} completed run(s) lack a "
                f"distill_review (pending: {pending_ids}). "
                "Run the distill skill and record an "
                "artifact.record(kind='decision', action='distill_review', ...) before resubmitting."
            )
        normalized_package_type = self._normalize_paper_bundle_package_type(package_type)
        paper_context = self._ensure_active_paper_workspace(quest_root)
        workspace_root = Path(str(paper_context.get("worktree_root") or self._workspace_root_for(quest_root)))
        paper_root = self._paper_root(quest_root, workspace_root=workspace_root, create=True)
        selected_outline_path, selected_outline = self._read_selected_outline_record(
            quest_root,
            workspace_root=workspace_root,
        )
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        if not selected_outline and not str(outline_path or "").strip():
            raise ValueError("submit_paper_bundle requires a selected outline or explicit `outline_path`.")
        gate_status = self._paper_bundle_gate_status(quest_root, workspace_root=workspace_root)
        if gate_status.get("unresolved_required_items") or gate_status.get("unmapped_completed_items"):
            problems: list[str] = []
            if gate_status.get("unresolved_required_items"):
                preview = [
                    f"{item.get('section_id') or 'section'}:{item.get('item_id') or 'item'}"
                    for item in (gate_status.get("unresolved_required_items") or [])[:5]
                    if isinstance(item, dict)
                ]
                problems.append(
                    "unresolved required outline items"
                    + (f" ({', '.join(preview)})" if preview else "")
                )
            if gate_status.get("unmapped_completed_items"):
                preview = [
                    f"{item.get('campaign_id') or 'analysis'}:{item.get('slice_id') or item.get('item_id') or 'slice'}"
                    for item in (gate_status.get("unmapped_completed_items") or [])[:5]
                    if isinstance(item, dict)
                ]
                problems.append(
                    "completed analysis results still unmapped into the paper contract"
                    + (f" ({', '.join(preview)})" if preview else "")
                )
            raise ValueError(
                "submit_paper_bundle blocked because the paper evidence contract is incomplete: "
                + "; ".join(problems)
                + "."
            )

        manifest_path = self._paper_bundle_manifest_path(quest_root, workspace_root=workspace_root)
        baseline_inventory = self._write_paper_baseline_inventory(quest_root, workspace_root=workspace_root)
        baseline_inventory_path = self._paper_baseline_inventory_path(quest_root, workspace_root=workspace_root)
        evidence_ledger_path = self._paper_evidence_ledger_path(quest_root)
        if not evidence_ledger_path.exists():
            self._write_paper_evidence_ledger(
                quest_root,
                {
                    "selected_outline_ref": str(selected_outline.get("outline_id") or "").strip() or None,
                    "items": [],
                },
                workspace_root=workspace_root,
            )
        self._write_paper_experiment_matrix(quest_root, workspace_root=workspace_root)
        experiment_matrix_path = paper_root / "paper_experiment_matrix.md"
        experiment_matrix_json_path = self._paper_experiment_matrix_json_path(quest_root, workspace_root=workspace_root)
        source_branch = str(paper_context.get("source_branch") or "").strip() or None
        paper_branch = str(paper_context.get("branch") or "").strip() or current_branch(workspace_root)
        source_run_id = str(paper_context.get("source_run_id") or "").strip() or None
        source_idea_id = str(paper_context.get("source_idea_id") or "").strip() or None
        paper_manifest_rel = self._workspace_relative(quest_root, manifest_path) or "paper/paper_bundle_manifest.json"
        paper_inventory_rel = self._workspace_relative(quest_root, baseline_inventory_path) or "paper/baseline_inventory.json"
        open_source_manifest = (
            self._ensure_open_source_prep(
                quest_root,
                workspace_root=workspace_root,
                source_branch=source_branch,
                source_bundle_manifest_path=paper_manifest_rel,
                baseline_inventory_path=paper_inventory_rel,
            )
            if prepare_open_source
            else {}
        )
        default_draft_path = self._workspace_relative(quest_root, paper_root / "draft.md") or "paper/draft.md"
        default_writing_plan_path = self._workspace_relative(quest_root, paper_root / "writing_plan.md") or "paper/writing_plan.md"
        default_references_path = self._workspace_relative(quest_root, paper_root / "references.bib") or "paper/references.bib"
        default_claim_map_path = (
            self._workspace_relative(quest_root, paper_root / "claim_evidence_map.json") or "paper/claim_evidence_map.json"
        )
        default_compile_report_path = (
            self._workspace_relative(quest_root, paper_root / "build" / "compile_report.json") or "paper/build/compile_report.json"
        )
        normalized_latex_root_path = self._normalize_paper_bundle_latex_root_path(
            quest_root,
            workspace_root=workspace_root,
            latex_root_path=latex_root_path,
            compile_report_path=compile_report_path or default_compile_report_path,
        )
        manifest = {
            "schema_version": 1,
            "title": str(
                title
                or selected_outline.get("title")
                or ((selected_outline.get("detailed_outline") or {}) if isinstance(selected_outline.get("detailed_outline"), dict) else {}).get("title")
                or "paper"
            ).strip()
            or "paper",
            "summary": str(summary or "").strip() or None,
            "package_type": normalized_package_type,
            "outline_path": str(outline_path or selected_outline_path).strip() or None,
            "paper_branch": paper_branch,
            "source_branch": source_branch,
            "source_run_id": source_run_id,
            "source_idea_id": source_idea_id,
            "draft_path": str(draft_path or default_draft_path).strip() or None,
            "writing_plan_path": str(writing_plan_path or default_writing_plan_path).strip() or None,
            "references_path": str(references_path or default_references_path).strip() or None,
            "claim_evidence_map_path": str(claim_evidence_map_path or default_claim_map_path).strip() or None,
            "evidence_ledger_path": self._workspace_relative(quest_root, evidence_ledger_path) or "paper/evidence_ledger.json",
            "experiment_matrix_path": (
                self._workspace_relative(quest_root, experiment_matrix_path) if experiment_matrix_path.exists() else None
            ),
            "experiment_matrix_json_path": (
                self._workspace_relative(quest_root, experiment_matrix_json_path)
                if experiment_matrix_json_path.exists()
                else None
            ),
            "compile_report_path": str(compile_report_path or default_compile_report_path).strip() or None,
            "pdf_path": str(pdf_path or "").strip() or None,
            "latex_root_path": normalized_latex_root_path,
            "baseline_inventory_path": paper_inventory_rel,
            "prepare_open_source": bool(prepare_open_source),
            "open_source_manifest_path": (
                self._workspace_relative(
                    quest_root,
                    self._open_source_manifest_path(quest_root, workspace_root=workspace_root),
                )
                if prepare_open_source
                else None
            ),
            "open_source_cleanup_plan_path": (
                str(open_source_manifest.get("cleanup_plan_path") or "").strip() or None
            )
            if prepare_open_source
            else None,
            "selected_outline_ref": str(selected_outline.get("outline_id") or "").strip() or None,
            "evidence_gate": gate_status,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        write_json(manifest_path, manifest)
        paper_line_state = self._write_paper_line_state(
            quest_root,
            workspace_root=workspace_root,
            source_branch=source_branch,
            source_run_id=source_run_id,
            source_idea_id=source_idea_id,
        )
        if bool(paper_line_state.get("submission_ready")):
            next_anchor = "finalize"
            continuation_reason = "paper_submission_package_submitted"
        elif normalized_package_type in {"review_package", "submission_package"}:
            next_anchor = "review"
            continuation_reason = "paper_review_package_submitted"
        else:
            next_anchor = "write"
            continuation_reason = "paper_draft_checkpoint_submitted"
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor=next_anchor)
        continuation_result = self._set_waiting_or_auto_resume(
            quest_root,
            anchor="decision",
            reason=continuation_reason,
        )
        artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": (
                    "paper_submission_package"
                    if normalized_package_type == "submission_package"
                    else "paper_review_package"
                    if normalized_package_type == "review_package"
                    else "paper_draft_checkpoint"
                ),
                "summary": summary or f"Paper {normalized_package_type.replace('_', ' ')} manifest submitted.",
                "reason": (
                    "Paper drafting outputs were consolidated into a durable manifest; "
                    "finalization is gated by manuscript and submission readiness."
                ),
                "flow_type": "paper_bundle",
                "protocol_step": normalized_package_type,
                "paths": {
                    "paper_bundle_manifest_json": str(manifest_path),
                    "outline_path": manifest.get("outline_path"),
                    "draft_path": manifest.get("draft_path"),
                    "pdf_path": manifest.get("pdf_path"),
                    "evidence_ledger_path": str(evidence_ledger_path) if evidence_ledger_path.exists() else None,
                    "baseline_inventory_path": str(baseline_inventory_path),
                    "open_source_manifest_path": (
                        str(self._open_source_manifest_path(quest_root, workspace_root=workspace_root))
                        if prepare_open_source
                        else None
                    ),
                },
                "details": {
                    "title": manifest.get("title"),
                    "package_type": normalized_package_type,
                    "selected_outline_ref": manifest.get("selected_outline_ref"),
                    "ready_section_count": gate_status.get("ready_section_count"),
                    "section_count": gate_status.get("section_count"),
                    "ledger_item_count": gate_status.get("ledger_item_count"),
                    "paper_line_id": paper_line_state.get("paper_line_id"),
                    "draft_checkpoint_ready": paper_line_state.get("draft_checkpoint_ready"),
                    "manuscript_ready": paper_line_state.get("manuscript_ready"),
                    "submission_ready": paper_line_state.get("submission_ready"),
                    "baseline_inventory_count": len(baseline_inventory.get("supplementary_baselines") or []),
                    "open_source_status": open_source_manifest.get("status") if prepare_open_source else None,
                    "paper_branch": paper_branch,
                    "source_branch": source_branch,
                    "source_run_id": source_run_id,
                    "prepare_open_source": bool(prepare_open_source),
                },
            },
            checkpoint=False,
            workspace_root=workspace_root,
        )
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=self._build_paper_bundle_interaction_message(
                title=str(manifest.get("title") or "").strip() or None,
                summary=str(manifest.get("summary") or "").strip() or None,
                package_type=normalized_package_type,
                paper_branch=paper_branch,
                source_branch=source_branch,
                source_run_id=source_run_id,
                selected_outline_ref=str(manifest.get("selected_outline_ref") or "").strip() or None,
                manifest_rel_path=self._workspace_relative(quest_root, manifest_path),
                draft_rel_path=str(manifest.get("draft_path") or "").strip() or None,
                writing_plan_rel_path=str(manifest.get("writing_plan_path") or "").strip() or None,
                references_rel_path=str(manifest.get("references_path") or "").strip() or None,
                claim_evidence_map_rel_path=str(manifest.get("claim_evidence_map_path") or "").strip() or None,
                evidence_ledger_rel_path=str(manifest.get("evidence_ledger_path") or "").strip() or None,
                compile_report_rel_path=str(manifest.get("compile_report_path") or "").strip() or None,
                pdf_rel_path=str(manifest.get("pdf_path") or "").strip() or None,
                latex_root_rel_path=str(manifest.get("latex_root_path") or "").strip() or None,
                baseline_inventory_rel_path=paper_inventory_rel,
                open_source_manifest_rel_path=str(manifest.get("open_source_manifest_path") or "").strip() or None,
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": normalized_package_type,
                    "title": manifest.get("title"),
                    "package_type": normalized_package_type,
                    "paper_branch": paper_branch,
                    "source_branch": source_branch,
                    "source_run_id": source_run_id,
                    "selected_outline_ref": manifest.get("selected_outline_ref"),
                    "manifest_path": str(manifest_path),
                    "draft_path": manifest.get("draft_path"),
                    "writing_plan_path": manifest.get("writing_plan_path"),
                    "references_path": manifest.get("references_path"),
                    "claim_evidence_map_path": manifest.get("claim_evidence_map_path"),
                    "evidence_ledger_path": manifest.get("evidence_ledger_path"),
                    "compile_report_path": manifest.get("compile_report_path"),
                    "pdf_path": manifest.get("pdf_path"),
                    "latex_root_path": manifest.get("latex_root_path"),
                    "baseline_inventory_path": str(baseline_inventory_path),
                    "prepare_open_source": bool(prepare_open_source),
                    "open_source_manifest_path": (
                        str(self._open_source_manifest_path(quest_root, workspace_root=workspace_root))
                        if prepare_open_source
                        else None
                    ),
                }
            ],
        )
        return {
            "ok": True,
            "manifest_path": str(manifest_path),
            "manifest": manifest,
            "baseline_inventory_path": str(baseline_inventory_path),
            "evidence_ledger_path": str(evidence_ledger_path),
            "paper_line_state_path": str(self._paper_line_state_path(quest_root, workspace_root=workspace_root)),
            "paper_line_state": paper_line_state,
            "manuscript_coverage_path": str(self._paper_manuscript_coverage_path(quest_root, workspace_root=workspace_root)),
            "open_source_manifest_path": (
                str(self._open_source_manifest_path(quest_root, workspace_root=workspace_root))
                if prepare_open_source
                else None
            ),
            "artifact": artifact,
            "interaction": interaction,
            "continuation": continuation_result,
        }

    def record_analysis_slice(
        self,
        quest_root: Path,
        *,
        campaign_id: str,
        slice_id: str,
        status: str = "completed",
        setup: str = "",
        execution: str = "",
        results: str = "",
        evidence_paths: list[str] | None = None,
        metric_rows: list[dict[str, Any]] | None = None,
        deviations: list[str] | None = None,
        claim_impact: str | None = None,
        reviewer_resolution: str | None = None,
        manuscript_update_hint: str | None = None,
        next_recommendation: str | None = None,
        dataset_scope: str = "full",
        subset_approval_ref: str | None = None,
        comparison_baselines: list[dict[str, Any]] | None = None,
        evaluation_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        manifest = self._read_analysis_manifest(quest_root, campaign_id)
        slices = [dict(item) for item in (manifest.get("slices") or [])]
        target = next((item for item in slices if str(item.get("slice_id") or "").strip() == slice_id), None)
        if target is None:
            raise FileNotFoundError(f"Unknown analysis slice `{slice_id}` in campaign `{campaign_id}`.")
        normalized_scope = str(dataset_scope or "full").strip().lower() or "full"
        if normalized_scope == "subset" and not str(subset_approval_ref or "").strip():
            raise ValueError("Subset analysis requires `subset_approval_ref`.")

        evidence_paths = [str(item).strip() for item in (evidence_paths or []) if str(item).strip()]
        deviations = [str(item).strip() for item in (deviations or []) if str(item).strip()]
        normalized_metric_rows = normalize_metric_rows(metric_rows or [])
        normalized_metrics_summary = {
            str(item.get("metric_id") or "").strip(): item.get("value")
            for item in normalized_metric_rows
            if str(item.get("metric_id") or "").strip()
        }
        normalized_metric_contract = normalize_metric_contract(
            {},
            metrics_summary=normalized_metrics_summary,
            metric_rows=normalized_metric_rows,
        )
        normalized_comparison_baselines = self._normalize_comparison_baselines(quest_root, comparison_baselines)
        normalized_claim_impact = str(claim_impact or "").strip() or None
        normalized_reviewer_resolution = str(reviewer_resolution or "").strip() or None
        normalized_manuscript_update_hint = str(manuscript_update_hint or "").strip() or None
        normalized_next_recommendation = str(next_recommendation or "").strip() or None
        normalized_evaluation_summary = self._normalize_evaluation_summary(evaluation_summary)
        slice_worktree_root = Path(str(target.get("worktree_root") or ""))
        parent_worktree_root = Path(str(manifest.get("parent_worktree_root") or ""))
        parent_branch = str(manifest.get("parent_branch") or "")

        result_dir = ensure_dir(slice_worktree_root / "experiments" / "analysis" / campaign_id / slice_id)
        result_path = result_dir / "RESULT.md"
        result_json_path = result_dir / "RESULT.json"
        result_lines = [
            f"# {target.get('title') or slice_id}",
            "",
            f"- Campaign: `{campaign_id}`",
            f"- Slice: `{slice_id}`",
            f"- Branch: `{target.get('branch')}`",
            f"- Worktree: `{slice_worktree_root}`",
            f"- Status: `{status}`",
            f"- Dataset scope: `{normalized_scope}`",
            "",
            "## Setup",
            "",
            setup.strip() or "TBD",
            "",
            "## Execution",
            "",
            execution.strip() or "TBD",
            "",
            "## Results",
            "",
            results.strip() or "TBD",
            "",
            "## Claim Impact",
            "",
            normalized_claim_impact or "Not recorded.",
            "",
            "## Reviewer Resolution",
            "",
            normalized_reviewer_resolution or "Not recorded.",
            "",
            "## Manuscript Update Hint",
            "",
            normalized_manuscript_update_hint or "Not recorded.",
            "",
            "## Next Recommendation",
            "",
            normalized_next_recommendation or "Not recorded.",
            "",
            "## Evaluation Summary",
            "",
            *self._evaluation_summary_markdown_lines(normalized_evaluation_summary),
            "",
            "## Deviations",
            "",
        ]
        if deviations:
            result_lines.extend([f"- {item}" for item in deviations])
        else:
            result_lines.append("- None recorded.")
        result_lines.extend(["", "## Evidence Paths", ""])
        if evidence_paths:
            result_lines.extend([f"- `{item}`" for item in evidence_paths])
        else:
            result_lines.append("- None recorded.")
        if normalized_metric_rows:
            result_lines.extend(["", "## Metric Rows", ""])
            for row in normalized_metric_rows:
                result_lines.append(f"- `{row}`")
        result_lines.extend(["", "## Comparison Baselines", ""])
        if normalized_comparison_baselines:
            for entry in normalized_comparison_baselines:
                result_lines.append(f"- {self._analysis_baseline_label(entry)}")
                if entry.get("baseline_root_rel_path"):
                    result_lines.append(f"  - Root: `{entry['baseline_root_rel_path']}`")
                if entry.get("metrics_summary"):
                    result_lines.append(f"  - Metrics: `{entry['metrics_summary']}`")
                if entry.get("published"):
                    result_lines.append(
                        f"  - Published: `{entry.get('published_entry_id') or entry.get('baseline_id')}`"
                    )
        else:
            result_lines.append("- None recorded.")
        if subset_approval_ref:
            result_lines.extend(["", "## Subset Approval", "", f"`{subset_approval_ref}`"])
        write_text(result_path, "\n".join(result_lines).rstrip() + "\n")

        result_payload = {
            "schema_version": 1,
            "result_kind": "analysis_slice",
            "campaign_id": campaign_id,
            "slice_id": slice_id,
            "selected_outline_ref": str(manifest.get("selected_outline_ref") or "").strip() or None,
            "status": status,
            "title": target.get("title"),
            "goal": target.get("goal"),
            "run_kind": target.get("run_kind"),
            "exp_id": target.get("exp_id"),
            "section_id": target.get("section_id"),
            "item_id": target.get("item_id"),
            "paper_role": target.get("paper_role"),
            "paper_placement": target.get("paper_placement"),
            "tier": target.get("tier"),
            "claim_links": target.get("claim_links") or [],
            "required_baselines": target.get("required_baselines") or [],
            "comparison_baselines": normalized_comparison_baselines,
            "metrics_summary": normalized_metrics_summary,
            "metric_rows": normalized_metric_rows,
            "metric_contract": normalized_metric_contract,
            "dataset_scope": normalized_scope,
            "subset_approval_ref": subset_approval_ref,
            "setup": setup.strip() or None,
            "execution": execution.strip() or None,
            "results": results.strip() or None,
            "claim_impact": normalized_claim_impact,
            "reviewer_resolution": normalized_reviewer_resolution,
            "manuscript_update_hint": normalized_manuscript_update_hint,
            "next_recommendation": normalized_next_recommendation,
            "evaluation_summary": normalized_evaluation_summary,
            "deviations": deviations,
            "evidence_paths": evidence_paths,
            "source_branch": str(target.get("branch") or ""),
            "source_worktree_root": str(slice_worktree_root),
            "updated_at": utc_now(),
        }
        write_json(result_json_path, result_payload)

        mirror_dir = ensure_dir(parent_worktree_root / "experiments" / "analysis-results" / campaign_id)
        mirror_path = mirror_dir / f"{slice_id}.md"
        mirror_lines = [
            f"# {target.get('title') or slice_id}",
            "",
            f"- Source branch: `{target.get('branch')}`",
            f"- Source worktree: `{slice_worktree_root}`",
            f"- Source result: `{result_path}`",
            f"- Status: `{status}`",
            "",
            "## Goal",
            "",
            str(target.get("goal") or "").strip() or "TBD",
            "",
            "## Paper Contract Binding",
            "",
            f"- Selected outline: `{str(manifest.get('selected_outline_ref') or 'none').strip() or 'none'}`",
            f"- Section id: `{str(target.get('section_id') or 'none').strip() or 'none'}`",
            f"- Item id: `{str(target.get('item_id') or slice_id).strip() or slice_id}`",
            f"- Exp id: `{str(target.get('exp_id') or 'none').strip() or 'none'}`",
            f"- Paper role: `{str(target.get('paper_role') or 'none').strip() or 'none'}`",
            f"- Claim links: {', '.join(str(value).strip() for value in (target.get('claim_links') or []) if str(value).strip()) or 'none'}",
            "",
            "## Core Requirement",
            "",
            str(target.get("must_not_simplify") or "").strip() or "Full protocol only.",
            "",
            "## Setup",
            "",
            setup.strip() or "TBD",
            "",
            "## Execution",
            "",
            execution.strip() or "TBD",
            "",
            "## Results",
            "",
            results.strip() or "TBD",
            "",
            "## Claim Impact",
            "",
            normalized_claim_impact or "Not recorded.",
            "",
            "## Manuscript Update Hint",
            "",
            normalized_manuscript_update_hint or "Not recorded.",
            "",
            "## Evaluation Summary",
            "",
            *self._evaluation_summary_markdown_lines(normalized_evaluation_summary),
            "",
        ]
        mirror_lines.extend(["## Comparison Baselines", ""])
        if normalized_comparison_baselines:
            mirror_lines.extend([f"- {self._analysis_baseline_label(entry)}" for entry in normalized_comparison_baselines])
        else:
            mirror_lines.append("- None recorded.")
        mirror_lines.append("")
        write_text(mirror_path, "\n".join(mirror_lines).rstrip() + "\n")

        artifact = self.record(
            quest_root,
            {
                "kind": "run",
                "status": status,
                "run_id": f"{campaign_id}:{slice_id}",
                "run_kind": str(target.get("run_kind") or "analysis.slice"),
                "summary": f"Analysis slice `{slice_id}` recorded with status `{status}`.",
                "reason": "Each analysis slice must durably record setup, execution, results, and evidence.",
                "idea_id": manifest.get("active_idea_id"),
                "campaign_id": campaign_id,
                "slice_id": slice_id,
                "branch": str(target.get("branch") or ""),
                "parent_branch": parent_branch,
                "worktree_root": str(slice_worktree_root),
                "worktree_rel_path": self._workspace_relative(quest_root, slice_worktree_root),
                "metrics_summary": normalized_metrics_summary,
                "metric_rows": normalized_metric_rows,
                "metric_contract": normalized_metric_contract,
                "comparison_baselines": normalized_comparison_baselines,
                "evidence_paths": evidence_paths,
                "flow_type": "analysis_slice",
                "protocol_step": "record",
                "paths": {
                    "slice_result_md": str(result_path),
                    "slice_result_json": str(result_json_path),
                    "parent_result_md": str(mirror_path),
                },
                "details": {
                    "title": target.get("title"),
                    "goal": target.get("goal"),
                    "must_not_simplify": target.get("must_not_simplify"),
                    "dataset_scope": normalized_scope,
                    "subset_approval_ref": subset_approval_ref,
                    "selected_outline_ref": str(manifest.get("selected_outline_ref") or "").strip() or None,
                    "section_id": target.get("section_id"),
                    "item_id": target.get("item_id"),
                    "exp_id": target.get("exp_id"),
                    "paper_role": target.get("paper_role"),
                    "paper_placement": target.get("paper_placement"),
                    "tier": target.get("tier"),
                    "claim_links": target.get("claim_links") or [],
                    "metric_rows": normalized_metric_rows,
                    "claim_impact": normalized_claim_impact,
                    "reviewer_resolution": normalized_reviewer_resolution,
                    "manuscript_update_hint": normalized_manuscript_update_hint,
                    "next_recommendation": normalized_next_recommendation,
                    "deviations": deviations,
                    "evidence_paths": evidence_paths,
                    "required_baselines": target.get("required_baselines") or [],
                    "comparison_baselines": normalized_comparison_baselines,
                    "evaluation_summary": normalized_evaluation_summary,
                },
                "evaluation_summary": normalized_evaluation_summary,
            },
            checkpoint=False,
            workspace_root=slice_worktree_root,
        )
        slice_checkpoint = self._checkpoint_with_optional_push(
            slice_worktree_root,
            message=f"analysis: complete {campaign_id}/{slice_id}",
        )
        parent_checkpoint = self._checkpoint_with_optional_push(
            parent_worktree_root,
            message=f"analysis: mirror {campaign_id}/{slice_id}",
        )

        updated_slices: list[dict[str, Any]] = []
        for item in slices:
            if str(item.get("slice_id") or "") != slice_id:
                updated_slices.append(item)
                continue
            updated = dict(item)
            updated["status"] = status
            updated["completed_at"] = utc_now()
            updated["result_path"] = str(result_path)
            updated["result_json_path"] = str(result_json_path)
            updated["mirror_path"] = str(mirror_path)
            updated["selected_outline_ref"] = str(manifest.get("selected_outline_ref") or "").strip() or None
            updated["claim_impact"] = normalized_claim_impact
            updated["reviewer_resolution"] = normalized_reviewer_resolution
            updated["manuscript_update_hint"] = normalized_manuscript_update_hint
            updated["next_recommendation"] = normalized_next_recommendation
            updated["metrics_summary"] = normalized_metrics_summary
            updated["metric_rows"] = normalized_metric_rows
            updated["comparison_baselines"] = normalized_comparison_baselines
            updated["evaluation_summary"] = normalized_evaluation_summary
            updated_slices.append(updated)
        next_slice = next((item for item in updated_slices if str(item.get("status") or "") == "pending"), None)
        manifest = self._write_analysis_manifest(
            quest_root,
            campaign_id,
            {
                **manifest,
                "slices": updated_slices,
            },
        )
        paper_line_root = str(manifest.get("paper_line_root") or "").strip() or None
        self._upsert_paper_evidence_item(
            quest_root,
            {
                "item_id": str(target.get("item_id") or slice_id).strip() or slice_id,
                "title": str(target.get("title") or slice_id).strip() or slice_id,
                "kind": "analysis_slice",
                "status": status,
                "paper_role": str(target.get("paper_role") or target.get("paper_placement") or "").strip() or None,
                "section_id": str(target.get("section_id") or "").strip() or None,
                "claim_links": self._normalize_string_list(target.get("claim_links")),
                "setup": setup.strip() or None,
                "result_summary": results.strip() or normalized_claim_impact or normalized_manuscript_update_hint or None,
                "key_metrics": self._paper_evidence_key_metrics(
                    metric_rows=normalized_metric_rows,
                    metrics_summary=normalized_metrics_summary,
                ),
                "source_paths": [
                    value
                    for value in [
                        self._workspace_relative(quest_root, result_path),
                        self._workspace_relative(quest_root, result_json_path),
                        self._workspace_relative(quest_root, mirror_path),
                        *evidence_paths,
                    ]
                    if value
                ],
                "campaign_id": campaign_id,
                "slice_id": slice_id,
                "selected_outline_ref": str(manifest.get("selected_outline_ref") or "").strip() or None,
                "paper_line_id": str(manifest.get("paper_line_id") or "").strip() or None,
                "evaluation_summary": normalized_evaluation_summary,
                "claim_impact": normalized_claim_impact,
            },
            workspace_root=Path(paper_line_root) if paper_line_root else None,
        )
        if paper_line_root:
            self._write_paper_line_state(
                quest_root,
                workspace_root=Path(paper_line_root),
                source_branch=str(manifest.get("parent_branch") or "").strip() or None,
                source_run_id=str(manifest.get("parent_run_id") or "").strip() or None,
                source_idea_id=str(manifest.get("active_idea_id") or "").strip() or None,
            )
        baseline_inventory = (
            self._upsert_analysis_baseline_inventory(
                quest_root,
                [
                    {
                        "baseline_id": entry.get("baseline_id"),
                        "variant_id": entry.get("variant_id"),
                        "usage_scope": "supplementary",
                        "status": "registered",
                        "reason": entry.get("reason"),
                        "benchmark": entry.get("benchmark"),
                        "split": entry.get("split"),
                        "baseline_root_rel_path": entry.get("baseline_root_rel_path"),
                        "storage_mode": entry.get("storage_mode"),
                        "metrics_summary": entry.get("metrics_summary"),
                        "evidence_paths": entry.get("evidence_paths"),
                        "published": entry.get("published"),
                        "published_entry_id": entry.get("published_entry_id"),
                        "origin": {
                            "stage": "analysis_campaign",
                            "campaign_id": campaign_id,
                            "slice_id": slice_id,
                        },
                    }
                    for entry in normalized_comparison_baselines
                ],
            )
            if normalized_comparison_baselines
            else self._read_analysis_baseline_inventory(quest_root)
        )

        if next_slice is not None:
            current_state = self.quest_service.read_research_state(quest_root)
            workspace_mode, branch_mode = self._resolve_workspace_modes(
                current_state,
                branch_name=next_slice.get("branch"),
            )
            research_state = self.quest_service.update_research_state(
                quest_root,
                active_analysis_campaign_id=campaign_id,
                next_pending_slice_id=next_slice.get("slice_id"),
                current_workspace_branch=next_slice.get("branch"),
                current_workspace_root=next_slice.get("worktree_root"),
                workspace_mode=workspace_mode,
                workspace_branch_mode=branch_mode,
                last_flow_type="analysis_slice",
            )
            self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="analysis-campaign")
            interaction = self.interact(
                quest_root,
                kind="progress",
                message=self._build_analysis_slice_interaction_message(
                    campaign_id=campaign_id,
                    slice_id=slice_id,
                    evaluation_summary=normalized_evaluation_summary,
                    claim_impact=normalized_claim_impact,
                    next_slice=next_slice,
                    mirror_rel_path=self._workspace_relative(quest_root, mirror_path),
                ),
                deliver_to_bound_conversations=True,
                include_recent_inbound_messages=False,
                attachments=[
                    {
                        "kind": "analysis_slice",
                        "campaign_id": campaign_id,
                        "completed_slice_id": slice_id,
                        "next_slice": next_slice,
                        "parent_result_md": str(mirror_path),
                    }
                ],
            )
            return {
                "ok": True,
                "campaign_id": campaign_id,
                "slice_id": slice_id,
                "status": status,
                "result_path": str(result_path),
                "result_json_path": str(result_json_path),
                "mirror_path": str(mirror_path),
                "artifact": artifact,
                "slice_checkpoint": slice_checkpoint,
                "parent_checkpoint": parent_checkpoint,
                "next_slice": next_slice,
                "manifest": manifest,
                "analysis_baseline_inventory": baseline_inventory,
                "interaction": interaction,
                "research_state": research_state,
                "evaluation_summary": normalized_evaluation_summary,
                "completed": False,
            }

        summary_path = mirror_dir / "SUMMARY.md"
        summary_lines = [
            f"# Analysis Campaign {campaign_id}",
            "",
            f"- Parent branch: `{parent_branch}`",
            f"- Parent worktree: `{parent_worktree_root}`",
            "",
            "## Completed Slices",
            "",
        ]
        for item in updated_slices:
            summary_lines.append(
                f"- `{item['slice_id']}` · {item.get('status', 'completed')} · `{item.get('mirror_path') or item.get('result_path')}`"
            )
        write_text(summary_path, "\n".join(summary_lines).rstrip() + "\n")
        summary_artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": "analysis_campaign_summary",
                "summary": f"Analysis campaign `{campaign_id}` is complete and merged back into the parent experiment branch.",
                "reason": "All configured analysis slices completed, so the quest can return to writing on the parent branch.",
                "idea_id": manifest.get("active_idea_id"),
                "campaign_id": campaign_id,
                "branch": parent_branch,
                "worktree_root": str(parent_worktree_root),
                "flow_type": "analysis_campaign",
                "protocol_step": "complete",
                "paths": {
                    "summary_md": str(summary_path),
                },
                "details": {
                    "slice_count": len(updated_slices),
                    "completed_slices": [
                        {
                            "slice_id": item.get("slice_id"),
                            "status": item.get("status"),
                            "mirror_path": item.get("mirror_path"),
                        }
                        for item in updated_slices
                    ],
                },
            },
            checkpoint=False,
            workspace_root=parent_worktree_root,
        )
        parent_summary_checkpoint = self._checkpoint_with_optional_push(
            parent_worktree_root,
            message=f"analysis: summarize {campaign_id}",
        )
        restored_idea_id = self._latest_branch_idea_id(quest_root, parent_branch) or str(manifest.get("active_idea_id") or "").strip() or None
        startup_contract = self._startup_contract(quest_root)
        raw_need_research_paper = startup_contract.get("need_research_paper")
        need_research_paper = raw_need_research_paper if isinstance(raw_need_research_paper, bool) else True
        current_state = self.quest_service.read_research_state(quest_root)
        workspace_mode, branch_mode = self._resolve_workspace_modes(
            current_state,
            branch_name=parent_branch,
        )
        base_research_state = self.quest_service.update_research_state(
            quest_root,
            active_idea_id=restored_idea_id,
            active_analysis_campaign_id=None,
            analysis_parent_branch=None,
            analysis_parent_worktree_root=None,
            paper_parent_branch=None,
            paper_parent_worktree_root=None,
            paper_parent_run_id=None,
            next_pending_slice_id=None,
            current_workspace_branch=parent_branch,
            current_workspace_root=str(parent_worktree_root),
            workspace_mode=workspace_mode,
            workspace_branch_mode=branch_mode,
            last_flow_type="analysis_campaign_complete",
        )
        writing_workspace: dict[str, Any] | None = None
        if need_research_paper:
            try:
                writing_workspace = self._ensure_active_paper_workspace(
                    quest_root,
                    source_branch=parent_branch,
                    source_run_id=str(manifest.get("parent_run_id") or "").strip() or None,
                    source_idea_id=restored_idea_id,
                )
            except Exception:
                writing_workspace = None

        if writing_workspace:
            research_state = self.quest_service.read_research_state(quest_root)
            self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="write")
        else:
            research_state = base_research_state
            self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="decision")
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=self._build_analysis_complete_interaction_message(
                campaign_id=campaign_id,
                completed_slices=updated_slices,
                summary_rel_path=self._workspace_relative(quest_root, summary_path),
                writing_branch=writing_workspace.get("branch") if writing_workspace else None,
                writing_worktree_rel_path=(
                    self._workspace_relative(quest_root, Path(str(writing_workspace.get("worktree_root"))))
                    if writing_workspace and str(writing_workspace.get("worktree_root") or "").strip()
                    else None
                ),
            ),
            deliver_to_bound_conversations=True,
            include_recent_inbound_messages=False,
            attachments=[
                {
                    "kind": "analysis_campaign_complete",
                    "campaign_id": campaign_id,
                    "parent_branch": parent_branch,
                    "parent_worktree_root": str(parent_worktree_root),
                    "summary_path": str(summary_path),
                    "writing_branch": writing_workspace.get("branch") if writing_workspace else None,
                    "writing_worktree_root": writing_workspace.get("worktree_root") if writing_workspace else None,
                }
            ],
        )
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "slice_id": slice_id,
            "status": status,
            "result_path": str(result_path),
            "result_json_path": str(result_json_path),
            "mirror_path": str(mirror_path),
            "artifact": artifact,
            "slice_checkpoint": slice_checkpoint,
            "parent_checkpoint": parent_checkpoint,
            "summary_artifact": summary_artifact,
            "summary_checkpoint": parent_summary_checkpoint,
            "summary_path": str(summary_path),
            "manifest": manifest,
            "analysis_baseline_inventory": baseline_inventory,
            "interaction": interaction,
            "research_state": research_state,
            "evaluation_summary": normalized_evaluation_summary,
            "completed": True,
            "returned_to_branch": parent_branch,
            "returned_to_worktree_root": str(parent_worktree_root),
            "writing_branch": writing_workspace.get("branch") if writing_workspace else None,
            "writing_worktree_root": writing_workspace.get("worktree_root") if writing_workspace else None,
        }

    def publish_baseline(self, quest_root: Path, payload: dict) -> dict:
        data = dict(payload)
        data["kind"] = "baseline"
        data["publish_global"] = True
        return self.record(quest_root, data)

    def attach_baseline(self, quest_root: Path, baseline_id: str, variant_id: str | None = None) -> dict:
        attachment = self.baselines.attach(quest_root, baseline_id, variant_id)
        materialized = self._materialize_baseline_attachment(quest_root, attachment)
        materialization = (
            dict(materialized.get("materialization") or {})
            if isinstance(materialized.get("materialization"), dict)
            else {}
        )
        materialization_status = str(materialization.get("status") or "").strip().lower()
        if materialization_status and materialization_status != "ok":
            return {
                "ok": False,
                "attachment": materialized,
                "message": "Baseline attachment metadata was written, but the baseline source could not be materialized into this quest.",
                "guidance": "Fix the baseline registry source path or select another baseline before continuing.",
            }
        artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": "baseline_attachment",
                "report_id": generate_id("report"),
                "summary": f"Attached baseline `{baseline_id}`.",
                "reason": "Baseline reuse avoids repeating an already stable reproduction.",
                "baseline_id": baseline_id,
                "baseline_variant_id": materialized.get("source_variant_id"),
                "paths": {
                    "attachment_yaml": str(quest_root / "baselines" / "imported" / baseline_id / "attachment.yaml"),
                    "baseline_root": str(quest_root / "baselines" / "imported" / baseline_id),
                    "source_path": str(materialized.get("source_path") or ""),
                },
                "source": {"kind": "system", "role": "artifact"},
            },
        )
        return {
            "ok": True,
            "attachment": materialized,
            "artifact": artifact,
            "guidance": "The selected baseline is now attached under baselines/imported. Reuse it before considering a fresh reproduction.",
        }

    def delete_baseline(self, baseline_id: str) -> dict[str, Any]:
        existing = self.baselines.get(baseline_id, include_deleted=True)
        if existing is None:
            raise FileNotFoundError(f"Unknown baseline: {baseline_id}")

        normalized_baseline_id = str(existing.get("baseline_id") or existing.get("entry_id") or baseline_id).strip()
        already_deleted = self.baselines.is_deleted(normalized_baseline_id)
        deleted_entry = self.baselines.delete(normalized_baseline_id) if not already_deleted else dict(existing)

        affected_quest_ids: list[str] = []
        cleared_requested_refs = 0
        cleared_confirmed_refs = 0
        deleted_paths: list[str] = []
        warnings: list[str] = []
        quests_root = self.home / "quests"

        for quest_yaml in sorted(quests_root.glob("*/quest.yaml")):
            quest_root = quest_yaml.parent
            quest_id = quest_root.name
            quest_touched = False
            quest_payload = self.quest_service.read_quest_yaml(quest_root)

            requested_ref = (
                dict(quest_payload.get("requested_baseline_ref") or {})
                if isinstance(quest_payload.get("requested_baseline_ref"), dict)
                else {}
            )
            if str(requested_ref.get("baseline_id") or "").strip() == normalized_baseline_id:
                self.quest_service.update_startup_context(quest_root, requested_baseline_ref=None)
                cleared_requested_refs += 1
                quest_touched = True

            confirmed_ref = (
                dict(quest_payload.get("confirmed_baseline_ref") or {})
                if isinstance(quest_payload.get("confirmed_baseline_ref"), dict)
                else {}
            )
            if str(confirmed_ref.get("baseline_id") or "").strip() == normalized_baseline_id:
                self.quest_service.update_baseline_state(
                    quest_root,
                    baseline_gate="pending",
                    confirmed_baseline_ref=None,
                    active_anchor="baseline",
                )
                cleared_confirmed_refs += 1
                quest_touched = True

            for root in self._baseline_workspace_roots(quest_root):
                try:
                    removed = self._remove_baseline_materialization(root, normalized_baseline_id)
                except OSError as exc:
                    warnings.append(
                        f"Unable to remove baseline materialization under `{root}` for quest `{quest_id}`: {exc}"
                    )
                    continue
                if removed:
                    deleted_paths.extend(removed)
                    quest_touched = True

            if quest_touched:
                affected_quest_ids.append(quest_id)

        return {
            "ok": True,
            "baseline_id": normalized_baseline_id,
            "deleted": not already_deleted,
            "already_deleted": already_deleted,
            "baseline_registry_entry": deleted_entry,
            "affected_quest_ids": affected_quest_ids,
            "cleared_requested_refs": cleared_requested_refs,
            "cleared_confirmed_refs": cleared_confirmed_refs,
            "deleted_paths": deleted_paths,
            "warnings": warnings,
        }

    def confirm_baseline(
        self,
        quest_root: Path,
        *,
        baseline_path: str,
        comment: str | dict[str, Any] | None = None,
        baseline_id: str | None = None,
        variant_id: str | None = None,
        summary: str | None = None,
        baseline_kind: str | None = None,
        metric_contract: dict[str, Any] | None = None,
        metric_directions: dict[str, str] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        primary_metric: dict[str, Any] | None = None,
        auto_advance: bool = True,
        strict_metric_contract: bool = False,
    ) -> dict[str, Any]:
        resolved = self._resolve_baseline_path(quest_root, baseline_path, baseline_id=baseline_id)
        resolved_baseline_id = str(resolved["baseline_id"] or "").strip()
        if not resolved_baseline_id:
            raise ValueError("Resolved baseline id is empty.")
        source_mode = str(resolved["source_mode"])
        resolved_root = Path(resolved["baseline_root"])
        resolved_root_rel_path = str(resolved["baseline_root_rel_path"])

        if source_mode == "imported":
            existing_attachment = self._active_baseline_attachment(quest_root, workspace_root=quest_root)
            existing_entry = None
            selected_variant = None
            if (
                isinstance(existing_attachment, dict)
                and str(existing_attachment.get("source_baseline_id") or "").strip() == resolved_baseline_id
            ):
                existing_entry = (
                    dict(existing_attachment.get("entry") or {})
                    if isinstance(existing_attachment.get("entry"), dict)
                    else None
                )
                selected_variant = (
                    dict(existing_attachment.get("selected_variant") or {})
                    if isinstance(existing_attachment.get("selected_variant"), dict)
                    else None
                )
                materialization = (
                    dict(existing_attachment.get("materialization") or {})
                    if isinstance(existing_attachment.get("materialization"), dict)
                    else {}
                )
                materialization_status = str(materialization.get("status") or "").strip().lower()
                if materialization_status and materialization_status != "ok":
                    raise FileNotFoundError(
                        "Imported baseline attachment exists, but its baseline files were not materialized successfully."
                    )
            if existing_entry is None:
                registry_entry = self.baselines.get(resolved_baseline_id)
                existing_entry = dict(registry_entry or {}) if isinstance(registry_entry, dict) else None
            if existing_entry is None:
                existing_entry, selected_variant = self._baseline_entry_from_local_state(
                    quest_root,
                    baseline_id=resolved_baseline_id,
                    baseline_root=resolved_root,
                    variant_id=variant_id,
                    summary=summary,
                    baseline_kind=baseline_kind,
                    metric_contract=metric_contract,
                    metrics_summary=metrics_summary,
                    primary_metric=primary_metric,
                )
            resolved_variant_id = str(
                variant_id
                or (selected_variant or {}).get("variant_id")
                or existing_entry.get("default_variant_id")
                or ""
            ).strip() or None
            if existing_entry.get("baseline_variants"):
                selected_variant = next(
                    (
                        item
                        for item in existing_entry.get("baseline_variants", [])
                        if str(item.get("variant_id") or "").strip() == str(resolved_variant_id or "").strip()
                    ),
                    selected_variant,
                )
            entry = {
                **existing_entry,
                "path": existing_entry.get("path") or str(resolved_root),
                "summary": summary or existing_entry.get("summary") or "",
            }
        else:
            entry, selected_variant = self._baseline_entry_from_local_state(
                quest_root,
                baseline_id=resolved_baseline_id,
                baseline_root=resolved_root,
                variant_id=variant_id,
                summary=summary,
                baseline_kind=baseline_kind,
                metric_contract=metric_contract,
                metrics_summary=metrics_summary,
                primary_metric=primary_metric,
            )
            resolved_variant_id = str(
                variant_id
                or (selected_variant or {}).get("variant_id")
                or entry.get("default_variant_id")
                or ""
            ).strip() or None

        source_metrics_summary = (
            selected_variant.get("metrics_summary")
            if isinstance(selected_variant, dict) and selected_variant.get("metrics_summary") is not None
            else entry.get("metrics_summary")
        )
        entry_metric_contract, entry_primary_metric = self._apply_metric_directions_to_contract(
            metric_contract=entry.get("metric_contract"),
            metric_directions=metric_directions,
            baseline_id=resolved_baseline_id,
            metrics_summary=source_metrics_summary,
            primary_metric=entry.get("primary_metric"),
            baseline_variants=entry.get("baseline_variants"),
        )
        entry = {
            **entry,
            "metric_contract": entry_metric_contract,
            "primary_metric": entry_primary_metric or entry.get("primary_metric"),
        }
        canonical_baseline = (
            validate_baseline_metric_contract_submission(
                metric_contract=entry.get("metric_contract"),
                metrics_summary=source_metrics_summary,
                primary_metric=entry.get("primary_metric"),
            )
            if strict_metric_contract
            else canonicalize_baseline_submission(
                metric_contract=entry.get("metric_contract"),
                metrics_summary=source_metrics_summary,
                primary_metric=entry.get("primary_metric"),
            )
        )
        entry = {
            **entry,
            "metrics_summary": canonical_baseline["metrics_summary"],
            "metric_contract": canonical_baseline["metric_contract"],
            "metric_details": canonical_baseline["metric_details"],
        }
        if isinstance(selected_variant, dict):
            selected_variant = {
                **selected_variant,
                "metrics_summary": canonical_baseline["metrics_summary"],
            }
        if isinstance(entry.get("baseline_variants"), list):
            entry["baseline_variants"] = [
                (
                    {
                        **variant,
                        "metrics_summary": canonical_baseline["metrics_summary"],
                    }
                    if isinstance(variant, dict)
                    and str(variant.get("variant_id") or "").strip() == str(resolved_variant_id or "").strip()
                    else variant
                )
                for variant in entry.get("baseline_variants", [])
            ]
        primary_metric_id = str(
            (entry.get("primary_metric") or {}).get("metric_id")
            or (entry.get("primary_metric") or {}).get("name")
            or (entry.get("primary_metric") or {}).get("id")
            or (canonical_baseline["metric_contract"] or {}).get("primary_metric_id")
            or ""
        ).strip()
        if primary_metric_id and primary_metric_id in canonical_baseline["metrics_summary"]:
            primary_metric_meta = next(
                (
                    item
                    for item in (canonical_baseline["metric_contract"] or {}).get("metrics", [])
                    if isinstance(item, dict) and str(item.get("metric_id") or "").strip() == primary_metric_id
                ),
                {},
            )
            entry["primary_metric"] = {
                **(dict(entry.get("primary_metric") or {}) if isinstance(entry.get("primary_metric"), dict) else {}),
                "metric_id": primary_metric_id,
                "value": canonical_baseline["metrics_summary"][primary_metric_id],
                "direction": primary_metric_meta.get("direction")
                or (entry.get("primary_metric") or {}).get("direction"),
            }

        metric_contract_json = self._write_baseline_metric_contract_json(
            quest_root,
            baseline_root=resolved_root,
            baseline_root_rel_path=resolved_root_rel_path,
            baseline_id=resolved_baseline_id,
            variant_id=resolved_variant_id,
            entry=entry,
            selected_variant=selected_variant,
            source_mode=source_mode,
        )
        attachment = self._write_confirmed_baseline_attachment(
            quest_root,
            baseline_id=resolved_baseline_id,
            variant_id=resolved_variant_id,
            entry=entry,
            selected_variant=selected_variant,
            source_mode=source_mode,
            baseline_root=resolved_root,
            comment=comment,
            metric_contract_json_path=str(metric_contract_json.get("path") or ""),
            metric_contract_json_rel_path=str(metric_contract_json.get("rel_path") or ""),
        )

        summary_text = summary or f"Baseline `{resolved_baseline_id}` confirmed for downstream comparison."
        reason_text = comment if isinstance(comment, str) and comment.strip() else "Baseline gate confirmed."
        artifact = self.record(
            quest_root,
            {
                "kind": "baseline",
                "status": "confirmed",
                "summary": summary_text,
                "reason": reason_text,
                "baseline_id": resolved_baseline_id,
                "baseline_variant_id": resolved_variant_id,
                "baseline_kind": entry.get("baseline_kind") or baseline_kind or source_mode,
                "default_variant_id": entry.get("default_variant_id"),
                "baseline_variants": entry.get("baseline_variants") or [],
                "metric_contract": entry.get("metric_contract"),
                "primary_metric": entry.get("primary_metric"),
                "metrics_summary": entry.get("metrics_summary") or {},
                "path": str(resolved_root),
                "paths": {
                    "baseline_root": str(resolved_root),
                    "attachment_yaml": str(quest_root / "baselines" / "imported" / resolved_baseline_id / "attachment.yaml"),
                    "metric_contract_json": str(metric_contract_json.get("path") or ""),
                },
                "flow_type": "baseline_gate",
                "protocol_step": "confirm",
                "details": {
                    "baseline_gate": "confirmed",
                    "baseline_path": str(resolved["resolved_path"]),
                    "baseline_root_rel_path": resolved_root_rel_path,
                    "metric_contract_json_rel_path": str(metric_contract_json.get("rel_path") or ""),
                    "source_mode": source_mode,
                    "comment": comment,
                },
                "startup_contract": self._startup_contract(quest_root) or None,
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=True,
        )
        confirmed_ref = {
            "baseline_id": resolved_baseline_id,
            "variant_id": resolved_variant_id,
            "baseline_path": str(resolved_root),
            "baseline_root_rel_path": resolved_root_rel_path,
            "metric_contract_json_path": str(metric_contract_json.get("path") or ""),
            "metric_contract_json_rel_path": str(metric_contract_json.get("rel_path") or ""),
            "source_mode": source_mode,
            "confirmed_at": utc_now(),
            "comment": comment,
        }
        quest_state = self.quest_service.update_baseline_state(
            quest_root,
            baseline_gate="confirmed",
            confirmed_baseline_ref=confirmed_ref,
            active_anchor=self._post_baseline_anchor(quest_root) if auto_advance else "baseline",
        )
        registry_entry = self._sync_confirmed_baseline_registry_entry(
            quest_root=quest_root,
            baseline_id=resolved_baseline_id,
            variant_id=resolved_variant_id,
            entry=entry,
            selected_variant=selected_variant,
            resolved_root=resolved_root,
            summary=summary_text,
            source_mode=source_mode,
        )
        return {
            "ok": True,
            "guidance": artifact.get("guidance"),
            "guidance_vm": artifact.get("guidance_vm"),
            "next_anchor": artifact.get("next_anchor"),
            "recommended_skill_reads": artifact.get("recommended_skill_reads"),
            "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
            "next_instruction": artifact.get("next_instruction"),
            "baseline_gate": quest_state.get("baseline_gate"),
            "confirmed_baseline_ref": quest_state.get("confirmed_baseline_ref"),
            "attachment": attachment,
            "artifact": artifact,
            "baseline_registry_entry": registry_entry,
            "snapshot": self.quest_service.snapshot(self._quest_id(quest_root)),
            "metric_details": canonical_baseline["metric_details"],
            "legacy_guidance": "Baseline gate confirmed. Idea selection is now the default next anchor.",
            "metric_contract_json_path": str(metric_contract_json.get("path") or ""),
            "metric_contract_json_rel_path": str(metric_contract_json.get("rel_path") or ""),
        }

    def waive_baseline(
        self,
        quest_root: Path,
        *,
        reason: str,
        comment: str | dict[str, Any] | None = None,
        auto_advance: bool = True,
    ) -> dict[str, Any]:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("`reason` is required to waive the baseline gate.")
        artifact = self.record(
            quest_root,
            {
                "kind": "decision",
                "status": "completed",
                "verdict": "waived",
                "action": "waive_baseline",
                "reason": normalized_reason,
                "summary": "Baseline gate waived explicitly for this quest.",
                "flow_type": "baseline_gate",
                "protocol_step": "waive",
                "details": {
                    "baseline_gate": "waived",
                    "comment": comment,
                },
                "startup_contract": self._startup_contract(quest_root) or None,
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=True,
        )
        quest_state = self.quest_service.update_baseline_state(
            quest_root,
            baseline_gate="waived",
            confirmed_baseline_ref=None,
            active_anchor=self._post_baseline_anchor(quest_root) if auto_advance else "baseline",
        )
        return {
            "ok": True,
            "guidance": artifact.get("guidance"),
            "guidance_vm": artifact.get("guidance_vm"),
            "next_anchor": artifact.get("next_anchor"),
            "recommended_skill_reads": artifact.get("recommended_skill_reads"),
            "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
            "next_instruction": artifact.get("next_instruction"),
            "baseline_gate": quest_state.get("baseline_gate"),
            "artifact": artifact,
            "snapshot": self.quest_service.snapshot(self._quest_id(quest_root)),
            "legacy_guidance": "Baseline gate waived. Continue carefully and keep the waiver rationale explicit downstream.",
        }

    def refresh_summary(self, quest_root: Path, *, reason: str | None = None) -> dict:
        workspace_root = self._workspace_root_for(quest_root)
        recent = self.recent(quest_root, limit=20)
        latest_runs = [item for item in recent if item.get("kind") == "runs"][-5:]
        latest_decisions = [item for item in recent if item.get("kind") == "decisions"][-5:]
        lines = [
            "# Quest Summary",
            "",
            f"- Updated at: {utc_now()}",
            f"- Branch: `{current_branch(workspace_root)}`",
            f"- Head: `{head_commit(workspace_root) or 'none'}`",
        ]
        if reason:
            lines.extend(["", f"- Refresh reason: {reason}"])
        if latest_decisions:
            lines.extend(["", "## Recent decisions"])
            for item in latest_decisions:
                payload = read_json(Path(item["path"]), {})
                lines.append(f"- `{payload.get('artifact_id')}`: {payload.get('reason', 'No reason provided.')}")
        if latest_runs:
            lines.extend(["", "## Recent runs"])
            for item in latest_runs:
                payload = read_json(Path(item["path"]), {})
                summary = payload.get("summary") or "No summary provided."
                lines.append(f"- `{payload.get('run_id') or payload.get('artifact_id')}`: {summary}")
        summary_path = workspace_root / "SUMMARY.md"
        write_text(summary_path, "\n".join(lines).rstrip() + "\n")
        artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": "summary_refresh",
                "report_id": generate_id("report"),
                "summary": "Quest summary refreshed from recent artifacts.",
                "reason": reason or "Summary refreshed after artifact updates.",
                "paths": {"summary_md": str(summary_path)},
                "source": {"kind": "system", "role": "artifact"},
            },
            workspace_root=workspace_root,
        )
        return {
            "ok": True,
            "summary_path": str(summary_path),
            "artifact": artifact,
            "guidance": "Use the refreshed SUMMARY.md as the compact quest state for the next turn.",
        }

    def render_git_graph(self, quest_root: Path) -> dict:
        graph_manifest = export_git_graph(quest_root, ensure_dir(quest_root / "artifacts" / "graphs"))
        artifact = self.record(
            quest_root,
            {
                "kind": "graph",
                "status": "generated",
                "graph_id": generate_id("graph"),
                "graph_type": "git_history",
                "summary": "Quest git graph exported.",
                "branch_summary": [graph_manifest.get("branch")],
                "head_commit": graph_manifest.get("head"),
                "commit_count": len(graph_manifest.get("lines", [])),
                "paths": {
                    "svg": graph_manifest.get("svg_path"),
                    "png": graph_manifest.get("png_path"),
                    "json": graph_manifest.get("json_path"),
                },
                "source": {"kind": "daemon"},
            },
            checkpoint=False,
        )
        return {
            "ok": True,
            "guidance": "Share the graph preview when you need to explain the research history or branching state.",
            "graph": graph_manifest,
            "artifact": artifact,
        }

    def interact(
        self,
        quest_root: Path,
        *,
        kind: str = "progress",
        message: str = "",
        summary_preview: str | None = None,
        response_phase: str = "ack",
        importance: str = "info",
        deliver_to_bound_conversations: bool = True,
        include_recent_inbound_messages: bool = True,
        recent_message_limit: int = 8,
        attachments: list[dict[str, Any]] | None = None,
        interaction_id: str | None = None,
        expects_reply: bool | None = None,
        reply_mode: str | None = None,
        options: list[dict[str, Any]] | None = None,
        surface_actions: list[dict[str, Any]] | None = None,
        connector_hints: dict[str, Any] | None = None,
        allow_free_text: bool = True,
        reply_schema: dict[str, Any] | None = None,
        reply_to_interaction_id: str | None = None,
        supersede_open_requests: bool = True,
        dedupe_key: str | None = None,
        suppress_if_unchanged: bool | None = None,
        min_interval_seconds: int | None = None,
    ) -> dict:
        durable_kind = {
            "progress": "progress",
            "answer": "answer",
            "milestone": "milestone",
            "decision_request": "decision",
            "approval_result": "approval",
        }.get(kind, "progress")
        full_message = str(message or "").strip()
        summary_preview_resolved = (
            self._summary_preview_text(summary_preview, limit=220)
            if summary_preview is not None
            else self._summary_preview_text(full_message, limit=220)
        )
        options_resolved = options or []
        surface_actions_resolved = [dict(item) for item in (surface_actions or []) if isinstance(item, dict)]
        connector_hints_resolved = self._normalize_connector_hints(connector_hints)
        attachments_resolved, attachment_issues = self._normalize_interaction_attachments(quest_root, attachments)
        reply_schema_resolved = reply_schema if isinstance(reply_schema, dict) else {}
        reply_mode_resolved = str(
            reply_mode
            or ("blocking" if kind == "decision_request" else "threaded" if kind in {"progress", "milestone", "answer"} else "none")
        ).strip().lower()
        if reply_mode_resolved not in {"none", "threaded", "blocking"}:
            reply_mode_resolved = "blocking" if kind == "decision_request" else "threaded"
        expects_reply_resolved = bool(expects_reply) if expects_reply is not None else reply_mode_resolved == "blocking"
        decision_policy = self._decision_policy(quest_root)
        decision_type = self._interaction_decision_type({"reply_schema": reply_schema_resolved})
        if (
            kind == "decision_request"
            and decision_policy == "autonomous"
            and decision_type != QUEST_COMPLETION_DECISION_TYPE
        ):
            mailbox_payload = {
                "delivery_batch": None,
                "recent_inbound_messages": [],
                "recent_interaction_records": [],
                "agent_instruction": self.quest_service.localized_copy(
                    quest_root=quest_root,
                    zh=(
                        "当前 quest 处于 autonomous 决策模式。不要把普通路线选择交还给用户；"
                        "请基于本地证据自行记录决策并继续推进。只有真正准备结束 quest 时，"
                        "才允许请求显式 completion approval。"
                    ),
                    en=(
                        "This quest is in autonomous decision mode. Do not hand ordinary route choices back "
                        "to the user; record the decision from local evidence and continue. The normal blocking "
                        "exception is explicit quest-completion approval when the quest is truly finished."
                    ),
                ),
                "queued_message_count_before_delivery": 0,
                "queued_message_count_after_delivery": 0,
            }
            if include_recent_inbound_messages:
                mailbox_payload = self.quest_service.consume_pending_user_messages(
                    quest_root,
                    interaction_id=None,
                    limit=recent_message_limit,
                )
            interaction_state = self._read_interaction_state(quest_root)
            waiting_requests = [
                dict(item)
                for item in (interaction_state.get("open_requests") or [])
                if str(item.get("status") or "") == "waiting"
            ]
            guidance = self.quest_service.localized_copy(
                quest_root=quest_root,
                zh="autonomous 模式已拦截本次 decision_request。请自行做出决策，记录原因，并继续执行。",
                en="Autonomous mode intercepted this decision_request. Decide yourself, record the reason, and continue.",
            )
            return {
                "status": "autonomous_redirected",
                "artifact_id": None,
                "interaction_id": None,
                "expects_reply": False,
                "reply_mode": "none",
                "delivered": False,
                "delivery_results": [],
                "response_phase": response_phase,
                "delivery_targets": [],
                "delivery_policy": self._delivery_policy(self._connectors_config()),
                "preferred_connector": self._preferred_connector(self._connectors_config()),
                "connector_hints": connector_hints_resolved,
                "normalized_attachments": attachments_resolved,
                "attachment_issues": attachment_issues,
                "recent_inbound_messages": mailbox_payload.get("recent_inbound_messages") or [],
                "delivery_batch": mailbox_payload.get("delivery_batch"),
                "recent_interaction_records": mailbox_payload.get("recent_interaction_records") or [],
                "agent_instruction": mailbox_payload.get("agent_instruction"),
                "queued_message_count_before_delivery": mailbox_payload.get("queued_message_count_before_delivery", 0),
                "queued_message_count_after_delivery": mailbox_payload.get("queued_message_count_after_delivery", 0),
                "open_request_count": len(waiting_requests),
                "active_request": waiting_requests[-1] if waiting_requests else None,
                "default_reply_interaction_id": interaction_state.get("default_reply_interaction_id"),
                "decision_policy": decision_policy,
                "decision_type": decision_type or None,
                "guidance": guidance,
            }
        suppress_resolved = (kind == "progress") if suppress_if_unchanged is None else bool(suppress_if_unchanged)
        dedupe_key_resolved = str(dedupe_key or self._normalize_interaction_message(full_message)).strip() or None
        pending_user_message_count = int(self.quest_service.snapshot(self._quest_id(quest_root)).get("pending_user_message_count") or 0)
        if (
            kind == "progress"
            and suppress_resolved
            and dedupe_key_resolved
            and pending_user_message_count == 0
        ):
            prior_interaction = self._latest_duplicate_progress_interaction(
                quest_root,
                dedupe_key=dedupe_key_resolved,
                min_interval_seconds=min_interval_seconds,
            )
            if prior_interaction is not None:
                interaction_state = self._read_interaction_state(quest_root)
                waiting_requests = [
                    dict(item)
                    for item in (interaction_state.get("open_requests") or [])
                    if str(item.get("status") or "") == "waiting"
                ]
                return {
                    "status": "suppressed_duplicate",
                    "artifact_id": prior_interaction.get("artifact_id"),
                    "interaction_id": prior_interaction.get("interaction_id"),
                    "expects_reply": False,
                    "reply_mode": "threaded",
                    "surface_actions": [],
                    "connector_hints": connector_hints_resolved,
                    "normalized_attachments": attachments_resolved,
                    "attachment_issues": attachment_issues,
                    "delivered": False,
                    "delivery_results": [],
                    "response_phase": response_phase,
                    "delivery_targets": [],
                    "delivery_policy": self._delivery_policy(self._connectors_config()),
                    "preferred_connector": self._preferred_connector(self._connectors_config()),
                    "recent_inbound_messages": [],
                    "delivery_batch": None,
                    "recent_interaction_records": self.quest_service.latest_artifact_interaction_records(quest_root, limit=10),
                    "agent_instruction": self.quest_service.localized_copy(
                        quest_root=quest_root,
                        zh="当前用户可见状态没有变化，不需要再发送一条重复 progress。继续工作，等出现真实变化再汇报。",
                        en="The user-visible state has not changed. Do not send another duplicate progress update; continue working until there is a real change.",
                    ),
                    "queued_message_count_before_delivery": 0,
                    "queued_message_count_after_delivery": 0,
                    "open_request_count": len(waiting_requests),
                    "active_request": waiting_requests[-1] if waiting_requests else None,
                    "default_reply_interaction_id": interaction_state.get("default_reply_interaction_id"),
                    "guidance": "Duplicate progress was suppressed because the latest user-visible state is unchanged.",
                    "suppressed_reason": "unchanged_progress",
                    "dedupe_key": dedupe_key_resolved,
                }
        if (
            kind == "answer"
            and not deliver_to_bound_conversations
            and dedupe_key_resolved
            and pending_user_message_count == 0
        ):
            prior_answer = self._latest_duplicate_answer_fallback_interaction(
                quest_root,
                dedupe_key=dedupe_key_resolved,
                min_interval_seconds=120,
            )
            if prior_answer is not None:
                interaction_state = self._read_interaction_state(quest_root)
                waiting_requests = [
                    dict(item)
                    for item in (interaction_state.get("open_requests") or [])
                    if str(item.get("status") or "") == "waiting"
                ]
                return {
                    "status": "suppressed_duplicate",
                    "artifact_id": prior_answer.get("artifact_id"),
                    "interaction_id": prior_answer.get("interaction_id"),
                    "expects_reply": False,
                    "reply_mode": "threaded",
                    "surface_actions": [],
                    "connector_hints": connector_hints_resolved,
                    "normalized_attachments": attachments_resolved,
                    "attachment_issues": attachment_issues,
                    "delivered": False,
                    "delivery_results": [],
                    "response_phase": response_phase,
                    "delivery_targets": [],
                    "delivery_policy": self._delivery_policy(self._connectors_config()),
                    "preferred_connector": self._preferred_connector(self._connectors_config()),
                    "recent_inbound_messages": [],
                    "delivery_batch": None,
                    "recent_interaction_records": self.quest_service.latest_artifact_interaction_records(quest_root, limit=10),
                    "agent_instruction": self.quest_service.localized_copy(
                        quest_root=quest_root,
                        zh="这一轮里相同内容的 answer 已经发出过一次，不要再为本地 fallback 额外创建第二条。",
                        en="An identical answer was already emitted in this user turn. Do not create a second local-only fallback copy.",
                    ),
                    "queued_message_count_before_delivery": 0,
                    "queued_message_count_after_delivery": 0,
                    "open_request_count": len(waiting_requests),
                    "active_request": waiting_requests[-1] if waiting_requests else None,
                    "default_reply_interaction_id": interaction_state.get("default_reply_interaction_id"),
                    "guidance": "Duplicate answer fallback was suppressed because the same answer was already recorded in the current user turn.",
                    "suppressed_reason": "duplicate_answer_fallback",
                    "dedupe_key": dedupe_key_resolved,
                }
        resolved_artifact_id = generate_id(durable_kind)
        resolved_interaction_id = interaction_id or (
            resolved_artifact_id if reply_mode_resolved != "none" or reply_to_interaction_id else None
        )
        payload: dict[str, Any] = {
            "kind": durable_kind,
            "artifact_id": resolved_artifact_id,
            "status": "completed" if kind == "answer" else "active" if durable_kind == "progress" else "completed",
            "message": full_message,
            "summary": summary_preview_resolved or full_message,
            "summary_preview": summary_preview_resolved,
            "interaction_phase": "request" if kind == "decision_request" else response_phase,
            "importance": importance,
            "attachments": attachments_resolved,
            "interaction_id": resolved_interaction_id,
            "expects_reply": expects_reply_resolved,
            "reply_mode": reply_mode_resolved,
            "options": options_resolved,
            "surface_actions": surface_actions_resolved,
            "connector_hints": connector_hints_resolved,
            "allow_free_text": allow_free_text,
            "reply_schema": reply_schema_resolved,
            "reply_to_interaction_id": reply_to_interaction_id,
            "source": {"kind": "agent", "role": "pi"},
        }
        if durable_kind == "decision":
            payload.update(
                {
                    "verdict": "pending_user",
                    "action": "request_user_decision",
                    "reason": full_message or "Decision request emitted for user review.",
                }
            )
        if durable_kind == "approval":
            payload.setdefault("reason", full_message or "Approval result emitted.")
        artifact = self.record(
            quest_root,
            payload,
            checkpoint=durable_kind in {"milestone", "decision", "approval"},
        )
        request_state = self._update_interaction_state(
            quest_root,
            artifact=artifact.get("record") or {},
            kind=kind,
            expects_reply=expects_reply_resolved,
            reply_mode=reply_mode_resolved,
            message=full_message,
            options=options_resolved,
            allow_free_text=allow_free_text,
            reply_schema=reply_schema_resolved,
            reply_to_interaction_id=reply_to_interaction_id,
            supersede_open_requests=supersede_open_requests,
        )
        delivery_targets: list[str] = []
        delivered = False
        delivery_results: list[dict[str, Any]] = []
        if deliver_to_bound_conversations:
            connectors = self._connectors_config()
            targets = self._select_delivery_targets(
                self._bound_conversations(quest_root),
                connectors=connectors,
            )
            for target in targets:
                channel_name = self._normalize_channel_name(target)
                payload = {
                    "quest_root": str(quest_root),
                    "quest_id": self._quest_id(quest_root),
                    "conversation_id": target,
                    "kind": kind,
                    "message": full_message,
                    "response_phase": response_phase,
                    "importance": importance,
                    "artifact_id": artifact.get("artifact_id"),
                    "interaction_id": request_state.get("interaction_id"),
                    "expects_reply": expects_reply_resolved,
                    "reply_mode": reply_mode_resolved,
                    "options": options_resolved,
                    "surface_actions": surface_actions_resolved,
                    "connector_hints": connector_hints_resolved,
                    "allow_free_text": allow_free_text,
                    "reply_schema": reply_schema_resolved,
                    "reply_to_interaction_id": reply_to_interaction_id,
                    "attachments": attachments_resolved,
                }
                delivery_result = self._deliver_to_channel(channel_name, payload, connectors=connectors)
                delivery_result["conversation_id"] = target
                delivery_results.append(delivery_result)
                if delivery_result.get("ok", False) or delivery_result.get("queued", False):
                    delivery_targets.append(target)
                    delivered = True
        counts_as_visible = (not deliver_to_bound_conversations) or (not delivery_results) or any(
            bool(item.get("ok", False)) for item in delivery_results
        )

        mailbox_payload = {
            "delivery_batch": None,
            "recent_inbound_messages": [],
            "recent_interaction_records": [],
            "agent_instruction": self.quest_service.localized_copy(
                quest_root=quest_root,
                zh="当前用户并没有发送任何消息，请按照用户的要求继续进行任务。",
                en="No new user message has arrived. Continue the task according to the user's requirements.",
            ),
            "queued_message_count_before_delivery": 0,
            "queued_message_count_after_delivery": 0,
        }
        if include_recent_inbound_messages:
            mailbox_payload = self.quest_service.consume_pending_user_messages(
                quest_root,
                interaction_id=request_state.get("interaction_id"),
                limit=recent_message_limit,
            )
        self.quest_service.record_artifact_interaction(
            quest_root,
            interaction_id=request_state.get("interaction_id"),
            artifact_id=artifact.get("artifact_id"),
            kind=kind,
            message=full_message,
            summary_preview=summary_preview_resolved,
            dedupe_key=dedupe_key_resolved,
            response_phase=response_phase,
            reply_mode=reply_mode_resolved,
            surface_actions=surface_actions_resolved,
            connector_hints=connector_hints_resolved,
            created_at=(artifact.get("record") or {}).get("updated_at"),
            counts_as_visible=counts_as_visible,
            deliver_to_bound_conversations=deliver_to_bound_conversations,
        )

        return {
            "status": "ok",
            "artifact_id": artifact.get("artifact_id"),
            "interaction_id": request_state.get("interaction_id"),
            "expects_reply": expects_reply_resolved,
            "reply_mode": reply_mode_resolved,
            "surface_actions": surface_actions_resolved,
            "connector_hints": connector_hints_resolved,
            "normalized_attachments": attachments_resolved,
            "attachment_issues": attachment_issues,
            "delivered": delivered,
            "delivery_results": delivery_results,
            "response_phase": response_phase,
            "delivery_targets": delivery_targets,
            "delivery_policy": self._delivery_policy(self._connectors_config()),
            "preferred_connector": self._preferred_connector(self._connectors_config()),
            "recent_inbound_messages": mailbox_payload.get("recent_inbound_messages") or [],
            "delivery_batch": mailbox_payload.get("delivery_batch"),
            "recent_interaction_records": mailbox_payload.get("recent_interaction_records") or [],
            "agent_instruction": mailbox_payload.get("agent_instruction"),
            "queued_message_count_before_delivery": mailbox_payload.get("queued_message_count_before_delivery", 0),
            "queued_message_count_after_delivery": mailbox_payload.get("queued_message_count_after_delivery", 0),
            "open_request_count": request_state.get("open_request_count", 0),
            "active_request": request_state.get("active_request"),
            "default_reply_interaction_id": request_state.get("default_reply_interaction_id"),
            "guidance": "如果收到新的用户要求，请先吸收这些要求；如果没有新消息，请继续当前任务并在真实检查点再次汇报。",
        }

    @staticmethod
    def _normalize_interaction_message(message: str) -> str:
        return " ".join(str(message or "").split())

    def _latest_duplicate_progress_interaction(
        self,
        quest_root: Path,
        *,
        dedupe_key: str,
        min_interval_seconds: int | None,
    ) -> dict[str, Any] | None:
        recent = self.quest_service.latest_artifact_interaction_records(quest_root, limit=40)
        for item in reversed(recent):
            record_type = str(item.get("type") or "").strip()
            if record_type == "user_inbound":
                return None
            if record_type != "artifact_outbound":
                continue
            if str(item.get("kind") or "").strip() != "progress":
                continue
            previous_key = str(item.get("dedupe_key") or self._normalize_interaction_message(item.get("message") or "")).strip()
            if previous_key != dedupe_key:
                continue
            if min_interval_seconds:
                seconds_since = self.quest_service._seconds_since_iso_timestamp(item.get("created_at"))
                if seconds_since is not None and seconds_since > int(min_interval_seconds):
                    return None
            return dict(item)
        return None

    def _latest_duplicate_answer_fallback_interaction(
        self,
        quest_root: Path,
        *,
        dedupe_key: str,
        min_interval_seconds: int | None,
    ) -> dict[str, Any] | None:
        recent = self.quest_service.latest_artifact_interaction_records(quest_root, limit=40)
        for item in reversed(recent):
            record_type = str(item.get("type") or "").strip()
            if record_type == "user_inbound":
                return None
            if record_type != "artifact_outbound":
                continue
            if str(item.get("kind") or "").strip() != "answer":
                continue
            if not bool(item.get("deliver_to_bound_conversations")):
                continue
            previous_key = str(item.get("dedupe_key") or self._normalize_interaction_message(item.get("message") or "")).strip()
            if previous_key != dedupe_key:
                continue
            if min_interval_seconds:
                seconds_since = self.quest_service._seconds_since_iso_timestamp(item.get("created_at"))
                if seconds_since is not None and seconds_since > int(min_interval_seconds):
                    return None
            return dict(item)
        return None

    def complete_quest(
        self,
        quest_root: Path,
        *,
        summary: str = "",
    ) -> dict[str, Any]:
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        if str(snapshot.get("status") or "") == "completed":
            return {
                "ok": True,
                "status": "already_completed",
                "quest_id": snapshot.get("quest_id"),
                "message": "Quest is already marked as completed.",
                "snapshot": snapshot,
            }

        from .experience_distill import evaluate_distill_gate_for_quest

        gate_payload = evaluate_distill_gate_for_quest(quest_root)
        if gate_payload is not None:
            return {
                "ok": False,
                "status": "distill_required",
                "quest_id": snapshot.get("quest_id"),
                "pending_distill_count": gate_payload["pending_distill_count"],
                "pending_distill_ids": gate_payload["pending_distill_ids"],
                "message": (
                    "Quest completion blocked: experience_distill is on and "
                    f"{gate_payload['pending_distill_count']} completed run(s) lack a "
                    "distill_review. Run the distill skill and "
                    "artifact.record(kind='decision', action='distill_review', ...) covering the pending runs."
                ),
            }

        completion_request = self._latest_completion_request(quest_root)
        if completion_request is None:
            return {
                "ok": False,
                "status": "approval_required",
                "quest_id": snapshot.get("quest_id"),
                "message": (
                    "Quest completion requires a blocking user approval request first. "
                    "Ask via artifact.interact(kind='decision_request', reply_mode='blocking', "
                    f"reply_schema={{'decision_type': '{QUEST_COMPLETION_DECISION_TYPE}'}})."
                ),
            }

        interaction_id = str(completion_request.get("interaction_id") or completion_request.get("artifact_id") or "").strip()
        reply_message = self._latest_interaction_reply_message(quest_root, interaction_id=interaction_id)
        if reply_message is None:
            return {
                "ok": False,
                "status": "waiting_for_user",
                "quest_id": snapshot.get("quest_id"),
                "interaction_id": interaction_id,
                "message": "The completion approval request is still waiting for an explicit user reply.",
            }

        approval_text = str(reply_message.get("content") or "").strip()
        if not self._has_explicit_completion_approval(approval_text):
            return {
                "ok": False,
                "status": "approval_not_explicit",
                "quest_id": snapshot.get("quest_id"),
                "interaction_id": interaction_id,
                "approval_message_id": reply_message.get("id"),
                "message": (
                    "Quest completion was not approved explicitly. "
                    "Ask the user to reply with an explicit approval such as `同意完成` or `approve`."
                ),
            }

        completion_summary = summary.strip() or self.quest_service.localized_copy(
            quest_root=quest_root,
            zh="研究主线已完成，且用户已明确同意结束当前 quest。",
            en="The main research line is complete and the user explicitly approved ending this quest.",
        )
        approval_excerpt = approval_text if len(approval_text) <= 240 else approval_text[:237].rstrip() + "..."
        approval = self.record(
            quest_root,
            {
                "kind": "approval",
                "decision_id": interaction_id,
                "reason": f"Quest completion approved by user reply: {approval_excerpt}",
                "reply_to_interaction_id": interaction_id,
                "approval_message_id": reply_message.get("id"),
                "approval_message_text": approval_text,
                "source": {
                    "kind": "user",
                    "surface": str(reply_message.get("source") or "local"),
                },
            },
            checkpoint=False,
        )
        decision = self.record(
            quest_root,
            {
                "kind": "decision",
                "status": "completed",
                "verdict": "good",
                "action": "stop",
                "reason": completion_summary,
                "summary": completion_summary,
                "decision_scope": "quest_completion",
                "interaction_phase": "completion_approved",
                "approved_by_interaction_id": interaction_id,
                "approval_artifact_id": approval.get("artifact_id"),
                "approval_message_id": reply_message.get("id"),
                "user_approval_excerpt": approval_excerpt,
            },
            checkpoint=True,
        )
        completed_snapshot = self.quest_service.mark_completed(
            str(snapshot.get("quest_id") or self._quest_id(quest_root)),
            stop_reason="completed_by_user_approval",
        )
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "type": "quest.completed",
                "quest_id": completed_snapshot.get("quest_id"),
                "interaction_id": interaction_id,
                "approval_message_id": reply_message.get("id"),
                "decision_artifact_id": decision.get("artifact_id"),
                "approval_artifact_id": approval.get("artifact_id"),
                "summary": completion_summary,
                "created_at": utc_now(),
            },
        )
        return {
            "ok": True,
            "status": "completed",
            "quest_id": completed_snapshot.get("quest_id"),
            "interaction_id": interaction_id,
            "approval_message_id": reply_message.get("id"),
            "message": completion_summary,
            "approval": approval,
            "decision": decision,
            "snapshot": completed_snapshot,
        }

    def recent(self, quest_root: Path, limit: int = 20) -> list[dict]:
        items: list[dict] = []
        seen: set[str] = set()
        for root in self.quest_service.workspace_roots(quest_root):
            artifacts_root = root / "artifacts"
            if not artifacts_root.exists():
                continue
            for folder in sorted(artifacts_root.glob("*")):
                if not folder.is_dir():
                    continue
                for path in sorted(folder.glob("*.json")):
                    key = str(path.resolve())
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append({"path": str(path), "name": path.name, "kind": folder.name, "workspace_root": str(root)})
        return items[-limit:]

    def _build_record(self, quest_root: Path, payload: dict, *, workspace_root: Path | None = None) -> dict:
        timestamp = utc_now()
        kind = payload["kind"]
        artifact_id = payload.get("artifact_id") or payload.get("id") or generate_id(kind)
        quest_id = payload.get("quest_id") or self._quest_id(quest_root)
        status = payload.get("status") or self._default_status(kind)
        source = payload.get("source") or {"kind": "agent"}
        resolved_workspace = self._workspace_root_for(quest_root, workspace_root)
        active_branch = current_branch(resolved_workspace)
        active_head = head_commit(resolved_workspace)
        return {
            "kind": kind,
            "schema_version": 1,
            "artifact_id": artifact_id,
            "id": artifact_id,
            "quest_id": quest_id,
            "created_at": payload.get("created_at", timestamp),
            "updated_at": timestamp,
            "source": source,
            "status": status,
            "branch": payload.get("branch") or active_branch,
            "head_commit": payload.get("head_commit") or active_head,
            "workspace_root": payload.get("workspace_root") or str(resolved_workspace),
            "workspace_rel_path": payload.get("workspace_rel_path") or self._workspace_relative(quest_root, resolved_workspace),
            **payload,
        }

    def _artifact_path(self, quest_root: Path, kind: str, artifact_id: str) -> Path:
        directory = ensure_dir(quest_root / "artifacts" / ARTIFACT_DIRS[kind])
        return directory / f"{artifact_id}.json"

    @staticmethod
    def _index_line(record: dict, artifact_path: Path) -> dict:
        return {
            "artifact_id": record.get("artifact_id"),
            "kind": record.get("kind"),
            "status": record.get("status"),
            "quest_id": record.get("quest_id"),
            "path": str(artifact_path),
            "summary": record.get("summary") or record.get("message"),
            "updated_at": record.get("updated_at"),
        }

    @staticmethod
    def _default_status(kind: str) -> str:
        return {
            "progress": "active",
            "answer": "completed",
            "decision": "pending",
            "approval": "accepted",
            "graph": "generated",
        }.get(kind, "completed")

    @staticmethod
    def _should_checkpoint(kind: str) -> bool:
        return kind in {"baseline", "decision", "milestone", "run", "report", "approval"}

    def _touch_quest_updated_at(self, quest_root: Path) -> None:
        quest_path = quest_root / "quest.yaml"
        quest_data = read_yaml(quest_path, {})
        quest_data["updated_at"] = utc_now()
        write_yaml(quest_path, quest_data)

    def _set_quest_status(self, quest_root: Path, status: str) -> None:
        self.quest_service.update_runtime_state(
            quest_root=quest_root,
            status=status,
            stop_reason=None,
        )

    def _quest_id(self, quest_root: Path) -> str:
        quest_yaml = read_yaml(quest_root / "quest.yaml", {})
        return str(quest_yaml.get("quest_id") or quest_root.name)

    def _default_branch_name(
        self,
        quest_root: Path,
        *,
        run_id: str | None,
        idea_id: str | None,
        branch_kind: str,
    ) -> str:
        quest_id = self._quest_id(quest_root)
        if branch_kind == "idea" and idea_id:
            return f"idea/{quest_id}-{idea_id}"
        if branch_kind == "quest":
            return f"quest/{quest_id}"
        if branch_kind == "paper":
            return f"paper/{run_id or generate_id('paper')}"
        return f"run/{run_id or generate_id('run')}"

    def _bound_conversations(self, quest_root: Path) -> list[str]:
        quest_id = self._quest_id(quest_root)
        sources = [
            self._normalize_conversation_id(str(item))
            for item in self.quest_service.binding_sources(quest_id)
        ]
        authoritative_keys = {conversation_identity_key(item) for item in sources}
        connector_sources = [
            item
            for item in self._connector_bound_conversations(quest_id)
            if conversation_identity_key(item) in authoritative_keys
        ]
        connector_by_identity = {
            conversation_identity_key(item): item
            for item in connector_sources
        }
        resolved: list[str] = []
        for item in sources:
            identity = conversation_identity_key(item)
            channel = self._normalize_channel_name(item)
            if channel == "local":
                resolved.append(item)
                continue
            resolved.append(connector_by_identity.get(identity, item))
        for item in connector_sources:
            identity = conversation_identity_key(item)
            if identity not in {conversation_identity_key(existing) for existing in resolved}:
                resolved.append(item)
        return self._dedupe_targets(resolved)

    def _connector_bound_conversations(self, quest_id: str) -> list[str]:
        root = self.home / "logs" / "connectors"
        if not root.exists():
            return []
        targets: list[str] = []
        for bindings_path in sorted(root.glob("*/bindings.json")):
            payload = read_json(bindings_path, {})
            bindings = payload.get("bindings") if isinstance(payload.get("bindings"), dict) else {}
            for conversation_id, binding in bindings.items():
                if not isinstance(binding, dict):
                    continue
                if str(binding.get("quest_id") or "").strip() != quest_id:
                    continue
                normalized = self._normalize_conversation_id(str(conversation_id))
                if normalized:
                    targets.append(normalized)
        return targets

    def _connectors_config(self) -> dict[str, Any]:
        manager = ConfigManager(self.home)
        raw_connectors = manager.load_named("connectors")
        connectors = manager.load_named_normalized("connectors")
        for name, config in list(connectors.items()):
            if str(name).startswith("_") or not isinstance(config, dict):
                continue
            raw_config = raw_connectors.get(name) if isinstance(raw_connectors.get(name), dict) else {}
            if "enabled" in raw_config:
                config["enabled"] = bool(raw_config.get("enabled"))
            if not manager.is_connector_system_enabled(str(name)):
                config["enabled"] = False
        return connectors

    @staticmethod
    def _delivery_policy(connectors: dict[str, Any]) -> str:
        routing = connectors.get("_routing") if isinstance(connectors.get("_routing"), dict) else {}
        policy = str(routing.get("artifact_delivery_policy") or "fanout_all").strip().lower()
        if policy in {"fanout_all", "primary_only", "primary_plus_local"}:
            return policy
        return "fanout_all"

    @staticmethod
    def _enabled_connectors(connectors: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for name, config in connectors.items():
            if str(name).startswith("_") or name == "local":
                continue
            if isinstance(config, dict) and bool(config.get("enabled", False)):
                names.append(str(name).strip().lower())
        return names

    def _preferred_connector(self, connectors: dict[str, Any]) -> str | None:
        routing = connectors.get("_routing") if isinstance(connectors.get("_routing"), dict) else {}
        enabled = self._enabled_connectors(connectors)
        preferred = str(routing.get("primary_connector") or "").strip().lower()
        if preferred and preferred in enabled:
            return preferred
        if len(enabled) == 1:
            return enabled[0]
        return None

    @staticmethod
    def _normalize_connector_hints(connector_hints: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(connector_hints, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, value in connector_hints.items():
            name = str(key or "").strip().lower()
            if not name or not isinstance(value, dict):
                continue
            normalized[name] = dict(value)
        return normalized

    def _normalize_interaction_attachments(
        self,
        quest_root: Path,
        attachments: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        normalized: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for index, raw_item in enumerate(attachments or [], start=1):
            if not isinstance(raw_item, dict):
                issues.append(
                    {
                        "attachment_index": index,
                        "error": "attachment must be an object",
                    }
                )
                continue
            item = dict(raw_item)
            path_value = str(item.get("path") or "").strip()
            if path_value:
                resolved_path = Path(path_value).expanduser()
                if not resolved_path.is_absolute():
                    resolved_path = (quest_root / resolved_path).resolve()
                else:
                    resolved_path = resolved_path.resolve()
                item["path"] = str(resolved_path)
                if not resolved_path.exists():
                    item["path_error"] = "path_not_found"
                    issues.append(
                        {
                            "attachment_index": index,
                            "path": str(resolved_path),
                            "error": "attachment path does not exist",
                        }
                    )
            connector_delivery = item.get("connector_delivery")
            if isinstance(connector_delivery, dict):
                normalized_delivery: dict[str, Any] = {}
                for key, value in connector_delivery.items():
                    name = str(key or "").strip().lower()
                    if not name or not isinstance(value, dict):
                        continue
                    normalized_delivery[name] = dict(value)
                if normalized_delivery:
                    item["connector_delivery"] = normalized_delivery
                else:
                    item.pop("connector_delivery", None)
            normalized.append(item)
        return normalized, issues

    def _select_delivery_targets(self, targets: list[str], *, connectors: dict[str, Any]) -> list[str]:
        if not targets:
            return ["local:default"]
        policy = self._delivery_policy(connectors)
        preferred = self._preferred_connector(connectors)
        if policy == "fanout_all" or (policy == "primary_plus_local" and preferred is None):
            return self._dedupe_targets(targets)

        local_targets = [target for target in targets if self._normalize_channel_name(target) == "local"]
        preferred_targets = [
            target for target in targets if preferred and self._normalize_channel_name(target) == preferred
        ]
        non_local_targets = [target for target in targets if self._normalize_channel_name(target) != "local"]
        fallback_primary = preferred_targets or non_local_targets[:1]

        if policy == "primary_only":
            selected = fallback_primary or local_targets or targets[:1]
            return self._dedupe_targets(selected)

        selected = [*local_targets, *fallback_primary]
        if not selected:
            selected = targets[:1]
        return self._dedupe_targets(selected)

    @staticmethod
    def _dedupe_targets(targets: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for target in targets:
            normalized = str(target or "").strip()
            identity = conversation_identity_key(normalized)
            if not normalized or identity in seen:
                continue
            seen.add(identity)
            ordered.append(normalized)
        return ordered

    @staticmethod
    def _normalize_channel_name(target: str) -> str:
        source = (target or "local:default").split(":", 1)[0].strip().lower()
        if source in {"web", "cli", "api", "command", "local", "local-ui"}:
            return "local"
        return source or "local"

    def _deliver_to_channel(
        self,
        channel_name: str,
        payload: dict[str, Any],
        *,
        connectors: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_connectors = connectors or self._connectors_config()
        channel_config = resolved_connectors.get(channel_name, {})
        def finish(result: dict[str, Any]) -> dict[str, Any]:
            self._record_connector_outbound_event(
                channel_name,
                payload=payload,
                result=result,
                connectors=resolved_connectors,
            )
            return result
        if channel_name != "local":
            if not isinstance(channel_config, dict) or not bool(channel_config.get("enabled", False)):
                return finish({
                    "ok": False,
                    "queued": False,
                    "channel": channel_name,
                    "payload": payload,
                    "delivery": None,
                    "error": f"Connector `{channel_name}` is disabled.",
                })
        try:
            register_builtin_connector_bridges()
            register_builtin_channels(home=self.home, connectors_config=resolved_connectors)
            factory = get_channel_factory(channel_name)
        except Exception as exc:
            return finish({
                "ok": False,
                "queued": False,
                "channel": channel_name,
                "payload": payload,
                "delivery": None,
                "error": str(exc),
            })
        try:
            channel = factory(home=self.home, config=channel_config)
            result = channel.send(payload)
        except Exception as exc:
            return finish({
                "ok": False,
                "queued": False,
                "channel": channel_name,
                "payload": payload,
                "delivery": None,
                "error": str(exc),
            })
        delivery = result.get("delivery") if isinstance(result.get("delivery"), dict) else None
        ok = bool(delivery.get("ok", False)) if delivery is not None else bool(result.get("ok", False))
        queued = bool(delivery.get("queued", False)) if delivery is not None else bool(result.get("queued", False))
        return finish({
            "ok": ok,
            "queued": queued,
            "channel": channel_name,
            "payload": result.get("payload") if isinstance(result.get("payload"), dict) else payload,
            "delivery": delivery,
            "result": result,
        })

    def _send_to_channel(self, channel_name: str, payload: dict[str, Any], *, connectors: dict[str, Any] | None = None) -> bool:
        result = self._deliver_to_channel(channel_name, payload, connectors=connectors)
        return bool(result.get("ok", False) or result.get("queued", False))

    def _record_connector_outbound_event(
        self,
        channel_name: str,
        *,
        payload: dict[str, Any],
        result: dict[str, Any],
        connectors: dict[str, Any],
    ) -> None:
        if channel_name == "local":
            return
        conversation_id = str(payload.get("conversation_id") or "").strip()
        if not conversation_id:
            return
        quest_root = self._outbound_event_quest_root(payload)
        if quest_root is None:
            return
        quest_id = str(payload.get("quest_id") or "").strip() or self._quest_id(quest_root)
        delivery = result.get("delivery") if isinstance(result.get("delivery"), dict) else {}
        channel_config = connectors.get(channel_name, {}) if isinstance(connectors, dict) else {}
        transport = str(
            delivery.get("transport")
            or infer_connector_transport(channel_name, channel_config if isinstance(channel_config, dict) else {})
            or channel_name
        ).strip()
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "type": "connector.outbound",
                "quest_id": quest_id,
                "conversation_id": conversation_id,
                "channel": channel_name,
                "kind": str(payload.get("kind") or "message").strip() or "message",
                "ok": bool(result.get("ok", False)),
                "queued": bool(result.get("queued", False)),
                "transport": transport,
                "response_phase": str(payload.get("response_phase") or "").strip() or None,
                "importance": str(payload.get("importance") or "").strip() or None,
                "artifact_id": str(payload.get("artifact_id") or "").strip() or None,
                "interaction_id": str(payload.get("interaction_id") or "").strip() or None,
                "surface_actions": payload.get("surface_actions") if isinstance(payload.get("surface_actions"), list) else [],
                "connector_hints": payload.get("connector_hints") if isinstance(payload.get("connector_hints"), dict) else {},
                "delivery_parts": delivery.get("parts") if isinstance(delivery.get("parts"), list) else [],
                "error": str(result.get("error") or delivery.get("error") or "").strip() or None,
                "created_at": utc_now(),
            },
        )

    def _outbound_event_quest_root(self, payload: dict[str, Any]) -> Path | None:
        quest_id = str(payload.get("quest_id") or "").strip()
        if quest_id:
            try:
                return self.quest_service._quest_root(quest_id)
            except FileNotFoundError:
                return None
        raw_quest_root = str(payload.get("quest_root") or "").strip()
        if not raw_quest_root:
            return None
        quest_root = Path(raw_quest_root).expanduser()
        if not quest_root.joinpath("quest.yaml").exists():
            return None
        return quest_root

    def _recent_inbound_messages(self, quest_root: Path, *, limit: int) -> list[dict]:
        conversation_path = quest_root / ".ds" / "conversations" / "main.jsonl"
        cursor = self._read_interaction_state(quest_root)
        last_seen_id = cursor.get("last_seen_user_message_id")
        messages = [item for item in read_jsonl(conversation_path) if item.get("role") == "user"]
        unseen: list[dict] = []
        if last_seen_id:
            seen = False
            for item in messages:
                if seen:
                    unseen.append(item)
                elif item.get("id") == last_seen_id:
                    seen = True
            if not seen:
                unseen = messages[-limit:]
        else:
            unseen = messages[-limit:]
        if unseen:
            cursor["last_seen_user_message_id"] = unseen[-1].get("id")
            self._write_interaction_state(quest_root, cursor)
        serialized: list[dict[str, Any]] = []
        for item in unseen[-limit:]:
            conversation_id = self._normalize_conversation_id(str(item.get("source") or "local"))
            payload: dict[str, Any] = {
                "message_id": item.get("id"),
                "source": conversation_id.split(":", 1)[0],
                "conversation_id": conversation_id,
                "sender": item.get("role"),
                "created_at": item.get("created_at"),
                "text": item.get("content") or "",
                "content": item.get("content") or "",
            }
            reply_to = str(item.get("reply_to_interaction_id") or "").strip()
            if reply_to:
                payload["reply_to_interaction_id"] = reply_to
            serialized.append(payload)
        return serialized

    def _read_interaction_state(self, quest_root: Path) -> dict[str, Any]:
        state = read_json(self._interaction_state_path(quest_root), {})
        state.setdefault("open_requests", [])
        state.setdefault("recent_threads", [])
        return state

    def _write_interaction_state(self, quest_root: Path, state: dict[str, Any]) -> None:
        write_json(self._interaction_state_path(quest_root), state)

    @staticmethod
    def _interaction_state_path(quest_root: Path) -> Path:
        return quest_root / ".ds" / "interaction_state.json"

    @staticmethod
    def _interaction_decision_type(item: dict[str, Any]) -> str:
        reply_schema = item.get("reply_schema") if isinstance(item.get("reply_schema"), dict) else {}
        return str(reply_schema.get("decision_type") or "").strip()

    def _latest_completion_request(self, quest_root: Path) -> dict[str, Any] | None:
        state = self._read_interaction_state(quest_root)
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for bucket in ("open_requests", "recent_threads"):
            for item in reversed(list(state.get(bucket) or [])):
                if not isinstance(item, dict):
                    continue
                if self._interaction_decision_type(item) != QUEST_COMPLETION_DECISION_TYPE:
                    continue
                if str(item.get("reply_mode") or "") != "blocking":
                    continue
                interaction_id = str(item.get("interaction_id") or item.get("artifact_id") or "").strip()
                if not interaction_id or interaction_id in seen:
                    continue
                seen.add(interaction_id)
                candidates.append(dict(item))
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: str(item.get("updated_at") or item.get("answered_at") or item.get("created_at") or ""),
        )

    def _latest_interaction_reply_message(
        self,
        quest_root: Path,
        *,
        interaction_id: str,
    ) -> dict[str, Any] | None:
        target = str(interaction_id or "").strip()
        if not target:
            return None
        for item in reversed(self.quest_service.history(self._quest_id(quest_root), limit=400)):
            if str(item.get("role") or "") != "user":
                continue
            if str(item.get("reply_to_interaction_id") or "").strip() == target:
                return item
        return None

    @staticmethod
    def _has_explicit_completion_approval(text: str) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        if any(term in normalized for term in _NON_ASCII_COMPLETION_REJECTION_TERMS):
            return False
        if any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in _ASCII_COMPLETION_REJECTION_TERMS):
            return False
        if any(term in normalized for term in _NON_ASCII_COMPLETION_APPROVAL_TERMS):
            return True
        return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in _ASCII_COMPLETION_APPROVAL_TERMS)

    def _update_interaction_state(
        self,
        quest_root: Path,
        *,
        artifact: dict[str, Any],
        kind: str,
        expects_reply: bool,
        reply_mode: str,
        message: str,
        options: list[dict[str, Any]],
        allow_free_text: bool,
        reply_schema: dict[str, Any],
        reply_to_interaction_id: str | None,
        supersede_open_requests: bool,
    ) -> dict[str, Any]:
        state = self._read_interaction_state(quest_root)
        open_requests = [dict(item) for item in (state.get("open_requests") or [])]
        recent_threads = [dict(item) for item in (state.get("recent_threads") or [])]
        interaction_id = str(artifact.get("interaction_id") or artifact.get("artifact_id") or generate_id("interact"))
        now = utc_now()

        if reply_to_interaction_id:
            open_requests = self._close_interaction_request_in_memory(
                open_requests,
                interaction_id=str(reply_to_interaction_id),
                closing_artifact_id=str(artifact.get("artifact_id") or ""),
                closed_at=now,
            )

        if reply_mode in {"threaded", "blocking"}:
            thread_record = {
                "interaction_id": interaction_id,
                "artifact_id": artifact.get("artifact_id"),
                "kind": kind,
                "reply_mode": reply_mode,
                "status": "waiting" if reply_mode == "blocking" else "active",
                "message": message,
                "options": options,
                "allow_free_text": allow_free_text,
                "reply_schema": reply_schema,
                "created_at": artifact.get("updated_at") or now,
                "updated_at": artifact.get("updated_at") or now,
            }
            recent_threads = self._upsert_recent_thread(recent_threads, thread_record)
            state["last_outbound_interaction_id"] = interaction_id
            state["latest_thread_interaction_id"] = interaction_id

        active_request: dict[str, Any] | None = None
        if reply_mode == "blocking":
            if supersede_open_requests:
                for index, item in enumerate(open_requests):
                    if item.get("status") not in {"waiting", "answered"}:
                        continue
                    updated = dict(item)
                    updated["status"] = "superseded"
                    updated["closed_at"] = now
                    updated["superseded_by"] = interaction_id
                    open_requests[index] = updated
            active_request = {
                "interaction_id": interaction_id,
                "artifact_id": artifact.get("artifact_id"),
                "kind": kind,
                "status": "waiting",
                "message": message,
                "options": options,
                "allow_free_text": allow_free_text,
                "reply_schema": reply_schema,
                "created_at": artifact.get("updated_at") or now,
            }
            open_requests.append(active_request)
            self._set_quest_status(quest_root, "waiting_for_user")

        state["open_requests"] = open_requests[-20:]
        state["recent_threads"] = recent_threads[-30:]
        state["default_reply_interaction_id"] = self._default_reply_interaction_id(
            open_requests=state["open_requests"],
            recent_threads=state["recent_threads"],
        )
        self._write_interaction_state(quest_root, state)
        waiting = [item for item in state["open_requests"] if str(item.get("status") or "") == "waiting"]
        if not waiting:
            self._resume_from_waiting_if_needed(quest_root)
        return {
            "interaction_id": interaction_id,
            "open_request_count": len(waiting),
            "active_request": active_request,
            "default_reply_interaction_id": state.get("default_reply_interaction_id"),
        }

    @staticmethod
    def _normalize_conversation_id(source: str) -> str:
        return normalize_conversation_id(source)

    def _close_interaction_request(
        self,
        quest_root: Path,
        *,
        interaction_id: str,
        closing_artifact_id: str,
    ) -> None:
        state = self._read_interaction_state(quest_root)
        open_requests = self._close_interaction_request_in_memory(
            list(state.get("open_requests") or []),
            interaction_id=interaction_id,
            closing_artifact_id=closing_artifact_id,
            closed_at=utc_now(),
        )
        state["open_requests"] = open_requests[-20:]
        state["default_reply_interaction_id"] = self._default_reply_interaction_id(
            open_requests=state["open_requests"],
            recent_threads=state.get("recent_threads") or [],
        )
        self._write_interaction_state(quest_root, state)
        if not any(str(item.get("status") or "") == "waiting" for item in open_requests):
            self._resume_from_waiting_if_needed(quest_root)

    @staticmethod
    def _close_interaction_request_in_memory(
        open_requests: list[dict[str, Any]],
        *,
        interaction_id: str,
        closing_artifact_id: str,
        closed_at: str,
    ) -> list[dict[str, Any]]:
        updated_requests = [dict(item) for item in open_requests]
        for index, item in enumerate(updated_requests):
            candidate_ids = {
                str(item.get("interaction_id") or "").strip(),
                str(item.get("artifact_id") or "").strip(),
            }
            if str(interaction_id) not in candidate_ids:
                continue
            updated = dict(item)
            updated["status"] = "closed"
            updated["closed_at"] = closed_at
            updated["closed_by_artifact_id"] = closing_artifact_id
            updated_requests[index] = updated
        return updated_requests

    @staticmethod
    def _upsert_recent_thread(
        recent_threads: list[dict[str, Any]],
        thread_record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        updated_threads = [dict(item) for item in recent_threads]
        interaction_id = str(thread_record.get("interaction_id") or "")
        for index, item in enumerate(updated_threads):
            candidate_ids = {
                str(item.get("interaction_id") or "").strip(),
                str(item.get("artifact_id") or "").strip(),
            }
            if interaction_id in candidate_ids:
                updated_threads[index] = {**item, **thread_record}
                return updated_threads
        updated_threads.append(thread_record)
        return updated_threads

    @staticmethod
    def _default_reply_interaction_id(
        *,
        open_requests: list[dict[str, Any]],
        recent_threads: list[dict[str, Any]],
    ) -> str | None:
        for item in reversed(open_requests):
            if str(item.get("status") or "") != "waiting":
                continue
            interaction_id = str(item.get("interaction_id") or item.get("artifact_id") or "").strip()
            if interaction_id:
                return interaction_id
        for item in reversed(recent_threads):
            if str(item.get("reply_mode") or "") not in {"threaded", "blocking"}:
                continue
            if str(item.get("status") or "") in {"closed", "superseded"}:
                continue
            interaction_id = str(item.get("interaction_id") or item.get("artifact_id") or "").strip()
            if interaction_id:
                return interaction_id
        return None

    def _resume_from_waiting_if_needed(self, quest_root: Path) -> None:
        runtime_state = self.quest_service._read_runtime_state(quest_root)
        if str(runtime_state.get("status") or "") != "waiting_for_user":
            return
        self.quest_service.update_runtime_state(
            quest_root=quest_root,
            status="running" if runtime_state.get("active_run_id") else "active",
            stop_reason=None,
        )
