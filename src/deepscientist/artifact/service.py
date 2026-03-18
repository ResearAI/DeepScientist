from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ..bridges import register_builtin_connector_bridges
from ..channels import get_channel_factory, register_builtin_channels
from ..config import ConfigManager
from ..connector_runtime import conversation_identity_key, infer_connector_transport, normalize_conversation_id
from ..gitops import (
    canonical_worktree_root,
    checkpoint_repo,
    create_worktree,
    current_branch,
    ensure_branch,
    export_git_graph,
    head_commit,
)
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
    slugify,
    utc_now,
    write_json,
    write_text,
    write_yaml,
)
from ..quest import QuestService
from ..memory.frontmatter import dump_markdown_document, load_markdown_document
from .arxiv import read_arxiv_content
from .guidance import build_guidance_for_record, guidance_summary
from .metrics import (
    baseline_metric_lines,
    build_metrics_timeline,
    compare_with_baseline,
    compute_progress_eval,
    normalize_metric_contract,
    normalize_metric_rows,
    normalize_metrics_summary,
    selected_baseline_metrics,
    to_number,
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


class ArtifactService:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.baselines = BaselineRegistry(home)
        self.quest_service = QuestService(home)

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
        foundation_ref: dict[str, Any] | None = None,
        foundation_reason: str = "",
        lineage_intent: str | None = None,
        created_at: str | None = None,
    ) -> str:
        normalized_foundation = dict(foundation_ref or {})
        normalized_lineage_intent = str(lineage_intent or "").strip().lower() or None
        tags = [f"branch:{branch}", f"next:{next_target}"]
        if normalized_lineage_intent:
            tags.append(f"lineage:{normalized_lineage_intent}")
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
            "## Expected Gain",
            "",
            expected_gain.strip() or "TBD",
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
        foundation_ref: dict[str, Any] | None = None,
        foundation_reason: str = "",
        lineage_intent: str | None = None,
        created_at: str | None = None,
        draft_markdown: str = "",
    ) -> str:
        normalized_foundation = dict(foundation_ref or {})
        normalized_lineage_intent = str(lineage_intent or "").strip().lower() or None
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

    def _paper_root(self, quest_root: Path) -> Path:
        return ensure_dir(quest_root / "paper")

    def _paper_outline_candidates_root(self, quest_root: Path) -> Path:
        return ensure_dir(self._paper_root(quest_root) / "outlines" / "candidates")

    def _paper_outline_revisions_root(self, quest_root: Path) -> Path:
        return ensure_dir(self._paper_root(quest_root) / "outlines" / "revisions")

    def _paper_selected_outline_path(self, quest_root: Path) -> Path:
        return self._paper_root(quest_root) / "selected_outline.json"

    def _paper_outline_selection_path(self, quest_root: Path) -> Path:
        return self._paper_root(quest_root) / "outline_selection.md"

    def _paper_bundle_manifest_path(self, quest_root: Path) -> Path:
        return self._paper_root(quest_root) / "paper_bundle_manifest.json"

    def _paper_baseline_inventory_path(self, quest_root: Path) -> Path:
        return self._paper_root(quest_root) / "baseline_inventory.json"

    def _open_source_root(self, quest_root: Path) -> Path:
        return ensure_dir(quest_root / "release" / "open_source")

    def _open_source_manifest_path(self, quest_root: Path) -> Path:
        return self._open_source_root(quest_root) / "manifest.json"

    def _open_source_cleanup_plan_path(self, quest_root: Path) -> Path:
        return self._open_source_root(quest_root) / "cleanup_plan.md"

    def _open_source_include_paths_path(self, quest_root: Path) -> Path:
        return self._open_source_root(quest_root) / "include_paths.json"

    def _open_source_exclude_paths_path(self, quest_root: Path) -> Path:
        return self._open_source_root(quest_root) / "exclude_paths.json"

    def _write_paper_baseline_inventory(self, quest_root: Path) -> dict[str, Any]:
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
        write_json(self._paper_baseline_inventory_path(quest_root), payload)
        return payload

    def _ensure_open_source_prep(
        self,
        quest_root: Path,
        *,
        source_branch: str | None,
        source_bundle_manifest_path: str,
        baseline_inventory_path: str,
    ) -> dict[str, Any]:
        root = self._open_source_root(quest_root)
        cleanup_plan_path = self._open_source_cleanup_plan_path(quest_root)
        include_paths_path = self._open_source_include_paths_path(quest_root)
        exclude_paths_path = self._open_source_exclude_paths_path(quest_root)
        manifest_path = self._open_source_manifest_path(quest_root)
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
            "cleanup_plan_path": str(existing.get("cleanup_plan_path") or "release/open_source/cleanup_plan.md").strip()
            or "release/open_source/cleanup_plan.md",
            "include_paths_path": str(existing.get("include_paths_path") or "release/open_source/include_paths.json").strip()
            or "release/open_source/include_paths.json",
            "exclude_paths_path": str(existing.get("exclude_paths_path") or "release/open_source/exclude_paths.json").strip()
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
        selected_outline = read_json(self._paper_selected_outline_path(quest_root), {})
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
                    "todo_id": str(raw.get("todo_id") or raw.get("slice_id") or "").strip() or None,
                    "slice_id": str(raw.get("slice_id") or "").strip() or None,
                    "title": str(raw.get("title") or "").strip() or None,
                    "status": str(raw.get("status") or "pending").strip() or "pending",
                    "research_question": str(raw.get("research_question") or "").strip() or None,
                    "experimental_design": str(raw.get("experimental_design") or "").strip() or None,
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
                "experimental_designs": self._normalize_string_list(normalized_detailed.get("experimental_designs")),
                "contributions": self._normalize_string_list(normalized_detailed.get("contributions")),
            },
            "review_result": str(review_result or "").strip() or None,
            "created_at": created_at or utc_now(),
            "updated_at": utc_now(),
        }
        return record

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

    def _require_baseline_gate_open(self, quest_root: Path, *, action: str) -> None:
        quest_yaml = self.quest_service.read_quest_yaml(quest_root)
        if str(quest_yaml.get("baseline_gate") or "pending").strip().lower() in {"confirmed", "waived"}:
            return
        raise ValueError(
            f"`{action}` requires a confirmed or waived baseline gate. "
            "Use `artifact.confirm_baseline(...)` or `artifact.waive_baseline(...)` first."
        )

    def _main_run_artifacts(self, quest_root: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for root in self.quest_service.workspace_roots(quest_root):
            artifacts_root = root / "artifacts" / "runs"
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
                if str(payload.get("run_kind") or "").strip() != "main_experiment":
                    continue
                enriched = dict(payload)
                enriched["_artifact_path"] = str(path)
                try:
                    enriched["_artifact_mtime_ns"] = path.stat().st_mtime_ns
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
        parent_worktree_root: Path | None = None
        for raw in (current_root_raw, head_root_raw):
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.exists():
                parent_worktree_root = candidate
                break
        if parent_worktree_root is None:
            parent_worktree_root = self._workspace_root_for(quest_root)

        parent_branch = (
            str(state.get("current_workspace_branch") or "").strip()
            or str(state.get("research_head_branch") or "").strip()
            or current_branch(parent_worktree_root)
            or current_branch(self._workspace_root_for(quest_root))
        )
        parent_branch = str(parent_branch or "").strip()
        if not parent_branch:
            raise ValueError("Unable to resolve a parent branch for the analysis campaign.")

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
        active_branch = (
            str(state.get("research_head_branch") or "").strip()
            or str(state.get("current_workspace_branch") or "").strip()
        )
        if normalized_branch and active_branch and normalized_branch == active_branch:
            return self._resolve_idea_foundation(
                quest_root,
                state=state,
                foundation_ref=None,
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
            str(state.get("research_head_branch") or "").strip()
            or str(state.get("current_workspace_branch") or "").strip()
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
            foundation_branch = (
                str(latest_foundation.get("branch") or latest_foundation.get("ref") or "").strip() or None
            )
            resolved_parent_branch = parent_branch or foundation_branch
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
                    "idea_id": latest_idea.get("idea_id"),
                    "idea_title": latest_idea.get("title"),
                    "idea_problem": latest_idea.get("problem"),
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
            "count": len(branches),
            "branches": branches,
        }

    def resolve_runtime_refs(self, quest_root: Path) -> dict[str, Any]:
        state = self.quest_service.read_research_state(quest_root)
        snapshot = self.quest_service.snapshot(self._quest_id(quest_root))
        active_campaign_id = str(state.get("active_analysis_campaign_id") or "").strip() or None
        analysis_parent_branch = str(state.get("analysis_parent_branch") or "").strip() or None
        current_workspace_branch = str(state.get("current_workspace_branch") or "").strip() or None
        research_head_branch = str(state.get("research_head_branch") or "").strip() or None
        canonical_branch = analysis_parent_branch or current_workspace_branch or research_head_branch
        latest_main_run = self._latest_main_run_for_branch(quest_root, canonical_branch or "")
        selected_outline = read_json(self._paper_selected_outline_path(quest_root), {})
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
            "selected_outline_ref": str(manifest.get("selected_outline_ref") or "").strip() or None,
            "campaign_origin": dict(manifest.get("campaign_origin") or {}) if isinstance(manifest.get("campaign_origin"), dict) else None,
            "todo_items": [dict(item) for item in (manifest.get("todo_items") or []) if isinstance(item, dict)],
            "slices": slices,
            "next_pending_slice_id": str((next_pending_slice or {}).get("slice_id") or "").strip() or None,
            "pending_slice_count": len(pending_slices),
            "completed_slice_count": len(completed_slices),
            "manifest": manifest,
        }

    def list_paper_outlines(self, quest_root: Path) -> dict[str, Any]:
        selected_outline = read_json(self._paper_selected_outline_path(quest_root), {})
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        outlines: list[dict[str, Any]] = []
        for status, root in (
            ("candidate", self._paper_outline_candidates_root(quest_root)),
            ("revised", self._paper_outline_revisions_root(quest_root)),
        ):
            for path in sorted(root.glob("outline-*.json")):
                record = read_json(path, {})
                if not isinstance(record, dict) or not record:
                    continue
                outline_id = str(record.get("outline_id") or path.stem).strip() or path.stem
                outlines.append(
                    {
                        "outline_id": outline_id,
                        "title": str(record.get("title") or outline_id).strip() or outline_id,
                        "status": str(record.get("status") or status).strip() or status,
                        "review_result": str(record.get("review_result") or "").strip() or None,
                        "path": str(path),
                        "is_selected": outline_id == str(selected_outline.get("outline_id") or "").strip(),
                    }
                )
        outlines.sort(key=lambda item: (str(item.get("outline_id") or ""), str(item.get("status") or "")))
        return {
            "ok": True,
            "selected_outline_ref": str(selected_outline.get("outline_id") or "").strip() or None,
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

    def arxiv(self, paper_id: str, *, full_text: bool = False) -> dict[str, Any]:
        return read_arxiv_content(paper_id, full_text=full_text)

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
        record = self._build_record(quest_root, payload, workspace_root=write_root)
        guidance_vm = build_guidance_for_record(record)
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
        write_json(artifact_path, record)
        append_jsonl(write_root / "artifacts" / "_index.jsonl", self._index_line(record, artifact_path))

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
        return {
            "ok": True,
            "message": message,
            "guidance": "Checkpoint created. Continue from the updated quest branch state.",
            **result,
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
        parent_branch = current_branch(quest_root)
        start_ref = start_point or parent_branch
        branch_name = branch or self._default_branch_name(quest_root, run_id=run_id, idea_id=idea_id, branch_kind=branch_kind)
        branch_result = ensure_branch(quest_root, branch_name, start_point=start_ref, checkout=False)
        worktree_result = None
        worktree_root = None
        if create_worktree_flag:
            worktree_root = canonical_worktree_root(quest_root, run_id or branch_name)
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
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=False,
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

    def submit_idea(
        self,
        quest_root: Path,
        *,
        mode: str = "create",
        idea_id: str | None = None,
        lineage_intent: str | None = None,
        title: str,
        problem: str = "",
        hypothesis: str = "",
        mechanism: str = "",
        expected_gain: str = "",
        evidence_paths: list[str] | None = None,
        risks: list[str] | None = None,
        decision_reason: str = "",
        foundation_ref: dict[str, Any] | str | None = None,
        foundation_reason: str = "",
        next_target: str = "experiment",
        draft_markdown: str = "",
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "create").strip().lower()
        if normalized_mode not in {"create", "revise"}:
            raise ValueError("submit_idea mode must be `create` or `revise`.")
        self._require_baseline_gate_open(quest_root, action="submit_idea")

        quest_id = self._quest_id(quest_root)
        state = self.quest_service.read_research_state(quest_root)
        evidence_paths = [str(item).strip() for item in (evidence_paths or []) if str(item).strip()]
        risks = [str(item).strip() for item in (risks or []) if str(item).strip()]
        next_target = str(next_target or "experiment").strip().lower() or "experiment"
        normalized_lineage_intent = self._normalize_lineage_intent(lineage_intent)

        if normalized_mode == "create":
            resolved_idea_id = str(idea_id or generate_id("idea")).strip()
            active_branch = (
                str(state.get("research_head_branch") or "").strip()
                or str(state.get("current_workspace_branch") or "").strip()
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
                    },
                },
                checkpoint=False,
                workspace_root=worktree_root,
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
                workspace_mode="idea",
                last_flow_type="idea_submission",
            )
            self.quest_service.update_settings(quest_id, active_anchor="experiment")
            checkpoint_result = self._checkpoint_with_optional_push(
                worktree_root,
                message=f"idea: create {resolved_idea_id}",
            )
            interaction = self.interact(
                quest_root,
                kind="milestone",
                message=(
                    f"Idea `{resolved_idea_id}` is now active.\n"
                    f"- Branch no: `{branch_no}`\n"
                    f"- Branch: `{branch_name}`\n"
                    f"- Lineage: `{normalized_lineage_intent or 'manual'}`\n"
                    f"- Foundation: `{foundation.get('label') or foundation.get('branch') or 'current head'}`\n"
                    f"- Worktree: `{worktree_root}`\n"
                    f"- Idea file: `{idea_md_path}`\n"
                    f"- Draft file: `{idea_draft_path}`\n"
                    f"- Next target: `{next_target}`"
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
                        "next_target": next_target,
                    }
                ],
            )
            return {
                "ok": True,
                "mode": normalized_mode,
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
            }

        resolved_idea_id = str(idea_id or state.get("active_idea_id") or "").strip()
        if not resolved_idea_id:
            raise ValueError("submit_idea(mode='revise') requires an existing active `idea_id`.")
        if normalized_lineage_intent:
            raise ValueError("submit_idea(mode='revise') does not accept `lineage_intent`; use mode='create' for new branch lineage.")
        branch_name = str(state.get("research_head_branch") or f"idea/{quest_id}-{resolved_idea_id}").strip()
        worktree_root = Path(
            str(state.get("research_head_worktree_root") or canonical_worktree_root(quest_root, f"idea-{resolved_idea_id}"))
        )
        ensure_dir(worktree_root / "memory" / "ideas" / resolved_idea_id)
        idea_md_path = worktree_root / "memory" / "ideas" / resolved_idea_id / "idea.md"
        idea_draft_path = worktree_root / "memory" / "ideas" / resolved_idea_id / "draft.md"
        created_at = None
        draft_created_at = None
        existing_foundation_ref = None
        existing_foundation_reason = None
        if idea_md_path.exists():
            metadata, _body = load_markdown_document(idea_md_path)
            created_at = metadata.get("created_at")
            existing_foundation_ref = (
                dict(metadata.get("foundation_ref") or {})
                if isinstance(metadata.get("foundation_ref"), dict)
                else None
            )
            existing_foundation_reason = str(metadata.get("foundation_reason") or "").strip() or None
        if idea_draft_path.exists():
            draft_metadata, _draft_body = load_markdown_document(idea_draft_path)
            draft_created_at = draft_metadata.get("created_at")
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
                    "expected_gain": expected_gain,
                    "next_target": next_target,
                    "parent_branch": parent_branch,
                    "foundation_ref": existing_foundation_ref,
                    "foundation_reason": foundation_reason.strip() or existing_foundation_reason or None,
                    "idea_draft_path": str(idea_draft_path),
                    "evidence_paths": evidence_paths,
                    "risks": risks,
                },
            },
            checkpoint=False,
            workspace_root=worktree_root,
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
            workspace_mode="idea",
            last_flow_type="idea_revision",
        )
        self.quest_service.update_settings(quest_id, active_anchor="experiment")
        checkpoint_result = self._checkpoint_with_optional_push(
            worktree_root,
            message=f"idea: revise {resolved_idea_id}",
        )
        interaction = self.interact(
            quest_root,
            kind="progress",
            message=(
                f"Idea `{resolved_idea_id}` was revised.\n"
                f"- Branch: `{branch_name}`\n"
                f"- Foundation: `{(existing_foundation_ref or {}).get('branch') or 'current head'}`\n"
                f"- Worktree: `{worktree_root}`\n"
                f"- Idea file: `{idea_md_path}`\n"
                f"- Draft file: `{idea_draft_path}`\n"
                f"- Next target: `{next_target}`"
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
                    "next_target": next_target,
                }
            ],
        )
        return {
            "ok": True,
            "mode": normalized_mode,
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

    def _decision_policy(self, quest_root: Path) -> str:
        value = str(self._startup_contract(quest_root).get("decision_policy") or "").strip().lower()
        if value in {"autonomous", "user_gated"}:
            return value
        return "user_gated"

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
    ) -> dict[str, Any]:
        self._require_baseline_gate_open(quest_root, action="record_main_experiment")
        state = self.quest_service.read_research_state(quest_root)
        if str(state.get("workspace_mode") or "").strip() == "analysis":
            raise ValueError(
                "record_main_experiment cannot run while the active workspace is an analysis slice. "
                "Finish or close the analysis campaign first."
            )

        run_identifier = str(run_id or "").strip()
        if not run_identifier:
            raise ValueError("record_main_experiment requires `run_id`.")

        active_idea_id = str(state.get("active_idea_id") or "").strip() or None
        workspace_root = self._workspace_root_for(quest_root)
        branch_name = str(state.get("research_head_branch") or current_branch(workspace_root)).strip()
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
        effective_metric_contract = normalize_metric_contract(
            metric_contract or baseline_entry.get("metric_contract"),
            baseline_id=resolved_baseline_id,
            metrics_summary=normalized_metrics_summary,
            primary_metric=baseline_entry.get("primary_metric"),
            baseline_variants=baseline_entry.get("baseline_variants"),
        )
        baseline_metrics = selected_baseline_metrics(baseline_entry, resolved_variant_id)
        comparisons = compare_with_baseline(
            metrics_summary=normalized_metrics_summary,
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
        }
        write_json(result_json_path, result_payload)

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
                "worktree_root": str(workspace_root),
                "worktree_rel_path": self._workspace_relative(quest_root, workspace_root),
                "flow_type": "main_experiment",
                "protocol_step": "record",
                "paths": {
                    "run_md": str(run_md_path),
                    "result_json": str(result_json_path),
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
                    "changed_file_count": len(resolved_changed_files),
                    "evidence_count": len(resolved_evidence_paths),
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
                "files_changed": resolved_changed_files,
                "evidence_paths": resolved_evidence_paths,
                "verdict": verdict,
            },
            commit_message=f"experiment: record main {run_identifier}",
            workspace_root=workspace_root,
        )
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=(
                f"Main experiment `{run_identifier}` has been recorded.\n"
                f"- Branch: `{branch_name}`\n"
                f"- Run log: `{run_md_path}`\n"
                f"- Result: `{result_json_path}`\n"
                f"- Verdict: `{verdict}`\n"
                f"- Breakthrough: `{progress_eval.get('breakthrough_level')}`\n"
                f"- Recommended next route: `{delivery_policy.get('recommended_next_route')}`"
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
                }
            ],
        )
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="decision")
        return {
            "ok": True,
            "guidance": artifact.get("guidance"),
            "guidance_vm": artifact.get("guidance_vm"),
            "next_anchor": artifact.get("next_anchor"),
            "recommended_skill_reads": artifact.get("recommended_skill_reads"),
            "suggested_artifact_calls": artifact.get("suggested_artifact_calls"),
            "next_instruction": artifact.get("next_instruction"),
            "run_id": run_identifier,
            "run_md_path": str(run_md_path),
            "result_json_path": str(result_json_path),
            "artifact": artifact,
            "interaction": interaction,
            "metrics_summary": normalized_metrics_summary,
            "baseline_comparisons": {
                key: value for key, value in comparisons.items() if key != "primary"
            },
            "progress_eval": progress_eval,
            "evaluation_summary": normalized_evaluation_summary,
            "delivery_policy": delivery_policy,
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
                    "todo_id": str(item.get("todo_id") or item.get("slice_id") or context["slice_id"]).strip() or context["slice_id"],
                    "slice_id": context["slice_id"],
                    "title": str(item.get("title") or context["title"]).strip() or context["title"],
                    "status": str(item.get("status") or "pending").strip() or "pending",
                    "research_question": item.get("research_question") or context.get("research_question"),
                    "experimental_design": item.get("experimental_design") or context.get("experimental_design"),
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
                "parent_run_id": parent_run_id,
                "active_idea_id": active_idea_id,
                "parent_branch": parent_branch,
                "parent_worktree_root": str(parent_worktree_root),
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
                    "parent_run_id": parent_run_id,
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
        research_state = self.quest_service.update_research_state(
            quest_root,
            active_idea_id=active_idea_id,
            active_analysis_campaign_id=campaign_id,
            analysis_parent_branch=parent_branch,
            analysis_parent_worktree_root=str(parent_worktree_root),
            next_pending_slice_id=first_slice["slice_id"],
            current_workspace_branch=first_slice["branch"],
            current_workspace_root=first_slice["worktree_root"],
            workspace_mode="analysis",
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
            message=(
                f"Analysis campaign `{campaign_id}` is ready.\n"
                f"- Parent branch: `{parent_branch}`\n"
                f"- Parent worktree: `{parent_worktree_root}`\n"
                f"- Next slice: `{first_slice['slice_id']}`\n"
                f"- Slice branch: `{first_slice['branch']}`\n"
                f"- Slice worktree: `{first_slice['worktree_root']}`\n"
                f"- Core requirement: {first_slice['must_not_simplify'] or 'Follow the full evaluation protocol.'}"
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

        existing_selected = read_json(self._paper_selected_outline_path(quest_root), {})
        existing_selected = existing_selected if isinstance(existing_selected, dict) else {}
        if normalized_mode == "candidate":
            resolved_outline_id = str(outline_id or self._next_paper_outline_id(quest_root)).strip()
            candidate_path = self._paper_outline_candidates_root(quest_root) / f"{resolved_outline_id}.json"
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
                workspace_root=self._workspace_root_for(quest_root),
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
        source_candidate_path = self._paper_outline_candidates_root(quest_root) / f"{source_outline_id}.json"
        source_record = read_json(source_candidate_path, {})
        if not isinstance(source_record, dict) or not source_record:
            source_record = existing_selected if str(existing_selected.get("outline_id") or "").strip() == source_outline_id else {}
        if not source_record:
            raise FileNotFoundError(f"Unknown paper outline `{source_outline_id}`.")

        resolved_record = self._normalize_paper_outline_record(
            outline_id=source_outline_id,
            title=title or source_record.get("title"),
            note=note or source_record.get("note"),
            story=story or source_record.get("story"),
            ten_questions=ten_questions or source_record.get("ten_questions"),
            detailed_outline=detailed_outline or source_record.get("detailed_outline"),
            review_result=review_result or source_record.get("review_result"),
            status="selected" if normalized_mode == "select" else "revised",
            created_at=str(source_record.get("created_at") or "") or None,
        )

        selected_outline_path = self._paper_selected_outline_path(quest_root)
        write_json(selected_outline_path, resolved_record)
        if source_candidate_path.exists():
            source_record["status"] = "selected" if normalized_mode == "select" else "revised"
            source_record["updated_at"] = utc_now()
            write_json(source_candidate_path, source_record)
        revised_outline_path = None
        if normalized_mode == "revise":
            revised_outline_path = self._paper_outline_revisions_root(quest_root) / f"{source_outline_id}.json"
            write_json(revised_outline_path, resolved_record)

        outline_selection_path = self._paper_outline_selection_path(quest_root)
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
                    "outline_selection_md": str(outline_selection_path),
                    **({"revised_outline_json": str(revised_outline_path)} if revised_outline_path else {}),
                },
                "details": {
                    "outline_id": source_outline_id,
                    "title": resolved_record.get("title"),
                    "selected_reason": selected_reason,
                },
            },
            checkpoint=False,
            workspace_root=self._workspace_root_for(quest_root),
        )
        return {
            "ok": True,
            "mode": normalized_mode,
            "outline_id": source_outline_id,
            "selected_outline_path": str(selected_outline_path),
            "outline_selection_path": str(outline_selection_path),
            "revised_outline_path": str(revised_outline_path) if revised_outline_path else None,
            "record": resolved_record,
            "artifact": artifact,
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
    ) -> dict[str, Any]:
        selected_outline_path = self._paper_selected_outline_path(quest_root)
        selected_outline = read_json(selected_outline_path, {})
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        if not selected_outline and not str(outline_path or "").strip():
            raise ValueError("submit_paper_bundle requires a selected outline or explicit `outline_path`.")

        manifest_path = self._paper_bundle_manifest_path(quest_root)
        baseline_inventory = self._write_paper_baseline_inventory(quest_root)
        baseline_inventory_path = self._paper_baseline_inventory_path(quest_root)
        source_branch = (
            str(self.quest_service.read_research_state(quest_root).get("current_workspace_branch") or "").strip()
            or current_branch(self._workspace_root_for(quest_root))
        )
        open_source_manifest = self._ensure_open_source_prep(
            quest_root,
            source_branch=source_branch,
            source_bundle_manifest_path="paper/paper_bundle_manifest.json",
            baseline_inventory_path="paper/baseline_inventory.json",
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
            "outline_path": str(outline_path or selected_outline_path).strip() or None,
            "draft_path": str(draft_path or "paper/draft.md").strip() or None,
            "writing_plan_path": str(writing_plan_path or "paper/writing_plan.md").strip() or None,
            "references_path": str(references_path or "paper/references.bib").strip() or None,
            "claim_evidence_map_path": str(claim_evidence_map_path or "paper/claim_evidence_map.json").strip() or None,
            "compile_report_path": str(compile_report_path or "paper/build/compile_report.json").strip() or None,
            "pdf_path": str(pdf_path or "").strip() or None,
            "latex_root_path": str(latex_root_path or "").strip() or None,
            "baseline_inventory_path": "paper/baseline_inventory.json",
            "open_source_manifest_path": "release/open_source/manifest.json",
            "open_source_cleanup_plan_path": str(open_source_manifest.get("cleanup_plan_path") or "").strip()
            or "release/open_source/cleanup_plan.md",
            "selected_outline_ref": str(selected_outline.get("outline_id") or "").strip() or None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        write_json(manifest_path, manifest)
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="finalize")
        artifact = self.record(
            quest_root,
            {
                "kind": "report",
                "status": "completed",
                "report_type": "paper_bundle",
                "summary": summary or "Paper bundle manifest submitted.",
                "reason": "Paper drafting outputs were consolidated into a durable bundle manifest.",
                "flow_type": "paper_bundle",
                "protocol_step": "submit",
                "paths": {
                    "paper_bundle_manifest_json": str(manifest_path),
                    "outline_path": manifest.get("outline_path"),
                    "draft_path": manifest.get("draft_path"),
                    "pdf_path": manifest.get("pdf_path"),
                    "baseline_inventory_path": str(baseline_inventory_path),
                    "open_source_manifest_path": str(self._open_source_manifest_path(quest_root)),
                },
                "details": {
                    "title": manifest.get("title"),
                    "selected_outline_ref": manifest.get("selected_outline_ref"),
                    "baseline_inventory_count": len(baseline_inventory.get("supplementary_baselines") or []),
                    "open_source_status": open_source_manifest.get("status"),
                },
            },
            checkpoint=False,
            workspace_root=self._workspace_root_for(quest_root),
        )
        return {
            "ok": True,
            "manifest_path": str(manifest_path),
            "manifest": manifest,
            "baseline_inventory_path": str(baseline_inventory_path),
            "open_source_manifest_path": str(self._open_source_manifest_path(quest_root)),
            "artifact": artifact,
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
        metric_rows = [item for item in (metric_rows or []) if isinstance(item, dict)]
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
        if metric_rows:
            result_lines.extend(["", "## Metric Rows", ""])
            for row in metric_rows:
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

        metrics_summary: dict[str, Any] = {}
        for row in metric_rows:
            name = str(row.get("name") or row.get("metric") or "").strip()
            if name:
                metrics_summary[name] = row.get("value")
                continue
            keys = [key for key in row.keys() if key not in {"split", "seed", "note", "notes"}]
            if len(keys) == 1:
                metrics_summary[keys[0]] = row.get(keys[0])

        result_payload = {
            "schema_version": 1,
            "result_kind": "analysis_slice",
            "campaign_id": campaign_id,
            "slice_id": slice_id,
            "status": status,
            "title": target.get("title"),
            "goal": target.get("goal"),
            "run_kind": target.get("run_kind"),
            "required_baselines": target.get("required_baselines") or [],
            "comparison_baselines": normalized_comparison_baselines,
            "metrics_summary": metrics_summary,
            "metric_rows": metric_rows,
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
                "metrics_summary": metrics_summary,
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
                    "metric_rows": metric_rows,
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
            updated["claim_impact"] = normalized_claim_impact
            updated["reviewer_resolution"] = normalized_reviewer_resolution
            updated["manuscript_update_hint"] = normalized_manuscript_update_hint
            updated["next_recommendation"] = normalized_next_recommendation
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
            research_state = self.quest_service.update_research_state(
                quest_root,
                active_analysis_campaign_id=campaign_id,
                next_pending_slice_id=next_slice.get("slice_id"),
                current_workspace_branch=next_slice.get("branch"),
                current_workspace_root=next_slice.get("worktree_root"),
                workspace_mode="analysis",
                last_flow_type="analysis_slice",
            )
            self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="analysis-campaign")
            interaction = self.interact(
                quest_root,
                kind="progress",
                message=(
                    f"Analysis slice `{slice_id}` is complete.\n"
                    f"- Parent branch mirror updated: `{mirror_path}`\n"
                    f"- Next slice: `{next_slice['slice_id']}`\n"
                    f"- Next branch: `{next_slice['branch']}`\n"
                    f"- Next worktree: `{next_slice['worktree_root']}`\n"
                    f"- Core requirement: {next_slice.get('must_not_simplify') or 'Use the full intended evaluation protocol.'}"
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
        research_state = self.quest_service.update_research_state(
            quest_root,
            active_idea_id=restored_idea_id,
            active_analysis_campaign_id=None,
            next_pending_slice_id=None,
            current_workspace_branch=parent_branch,
            current_workspace_root=str(parent_worktree_root),
            workspace_mode="idea",
            last_flow_type="analysis_campaign_complete",
        )
        self.quest_service.update_settings(self._quest_id(quest_root), active_anchor="decision")
        interaction = self.interact(
            quest_root,
            kind="milestone",
            message=(
                f"All analysis slices in `{campaign_id}` are complete.\n"
                f"- Returned to parent branch: `{parent_branch}`\n"
                f"- Parent worktree: `{parent_worktree_root}`\n"
                f"- Analysis summary: `{summary_path}`\n"
                "Use the completed analysis evidence to make the next durable route decision."
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
        metrics_summary: dict[str, Any] | None = None,
        primary_metric: dict[str, Any] | None = None,
        auto_advance: bool = True,
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
            active_anchor="idea" if auto_advance else "baseline",
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
            "legacy_guidance": "Baseline gate confirmed. Idea selection is now the default next anchor.",
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
                "source": {"kind": "system", "role": "artifact"},
            },
            checkpoint=True,
        )
        quest_state = self.quest_service.update_baseline_state(
            quest_root,
            baseline_gate="waived",
            confirmed_baseline_ref=None,
            active_anchor="idea" if auto_advance else "baseline",
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
    ) -> dict:
        durable_kind = {
            "progress": "progress",
            "milestone": "milestone",
            "decision_request": "decision",
            "approval_result": "approval",
        }.get(kind, "progress")
        options_resolved = options or []
        surface_actions_resolved = [dict(item) for item in (surface_actions or []) if isinstance(item, dict)]
        connector_hints_resolved = self._normalize_connector_hints(connector_hints)
        attachments_resolved, attachment_issues = self._normalize_interaction_attachments(quest_root, attachments)
        reply_schema_resolved = reply_schema if isinstance(reply_schema, dict) else {}
        reply_mode_resolved = str(
            reply_mode
            or ("blocking" if kind == "decision_request" else "threaded" if kind in {"progress", "milestone"} else "none")
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
        resolved_artifact_id = generate_id(durable_kind)
        resolved_interaction_id = interaction_id or (
            resolved_artifact_id if reply_mode_resolved != "none" or reply_to_interaction_id else None
        )
        payload: dict[str, Any] = {
            "kind": durable_kind,
            "artifact_id": resolved_artifact_id,
            "status": "active" if durable_kind == "progress" else "completed",
            "message": message,
            "summary": message,
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
                    "reason": message or "Decision request emitted for user review.",
                }
            )
        if durable_kind == "approval":
            payload.setdefault("reason", message or "Approval result emitted.")
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
            message=message,
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
                    "message": message,
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
            message=message,
            response_phase=response_phase,
            reply_mode=reply_mode_resolved,
            surface_actions=surface_actions_resolved,
            connector_hints=connector_hints_resolved,
            created_at=(artifact.get("record") or {}).get("updated_at"),
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
        return f"run/{run_id or generate_id('run')}"

    def _bound_conversations(self, quest_root: Path) -> list[str]:
        state_path = quest_root / ".ds" / "bindings.json"
        payload = read_json(state_path, {"sources": ["local:default"]})
        sources = [self._normalize_conversation_id(str(item)) for item in (payload.get("sources") or ["local:default"])]
        connector_sources = self._connector_bound_conversations(self._quest_id(quest_root))
        return self._dedupe_targets([*connector_sources, *sources])

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
        return ConfigManager(self.home).load_named_normalized("connectors")

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
