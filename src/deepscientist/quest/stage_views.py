from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from ..memory.frontmatter import load_markdown_document
from ..shared import read_json, read_text, read_yaml

_STAGE_KEY_ALIASES = {
    "analysis-campaign": "analysis",
    "analysis_campaign": "analysis",
    "analysis_slice": "analysis",
    "experiment": "experiment",
    "finalize": "paper",
    "paper": "paper",
    "write": "paper",
    "writing": "paper",
}


def normalize_stage_key(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    if not normalized:
        return "baseline"
    return _STAGE_KEY_ALIASES.get(normalized, normalized)


def stage_label(value: object) -> str:
    normalized = normalize_stage_key(value)
    return " ".join(part.capitalize() for part in normalized.split("-"))


def _compact(value: object, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _field_id(label: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in label).strip("-")


def _field(label: str, value: object, *, tone: str = "default") -> dict[str, Any]:
    return {
        "id": _field_id(label),
        "label": label,
        "value": value,
        "display_value": _compact(value, limit=400),
        "tone": tone,
    }


def _selection_score_summary(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    for key, raw in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        if isinstance(raw, float):
            rendered = f"{raw:.4f}".rstrip("0").rstrip(".")
        else:
            rendered = str(raw).strip()
        if not rendered:
            continue
        parts.append(f"{name}={rendered}")
        if len(parts) >= 4:
            break
    return " · ".join(parts) or None


def _evaluation_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key in (
        "takeaway",
        "claim_update",
        "baseline_relation",
        "comparability",
        "failure_mode",
        "next_action",
    ):
        raw = value.get(key)
        text = str(raw).strip() if raw is not None else ""
        if text:
            normalized[key] = text
    return normalized


def _evaluation_summary_fields(value: object, *, prefix: str = "Evaluation") -> list[dict[str, Any]]:
    summary = _evaluation_summary(value)
    labels = (
        ("takeaway", f"{prefix} Takeaway"),
        ("claim_update", f"{prefix} Claim Update"),
        ("baseline_relation", f"{prefix} Baseline Relation"),
        ("comparability", f"{prefix} Comparability"),
        ("failure_mode", f"{prefix} Failure Mode"),
        ("next_action", f"{prefix} Next Action"),
    )
    return [_field(label, summary[key]) for key, label in labels if summary.get(key)]


def _artifact_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    return (
        str(payload.get("updated_at") or payload.get("created_at") or ""),
        str(item.get("path") or ""),
    )


class QuestStageViewBuilder:
    def __init__(
        self,
        quest_service: Any,
        quest_root: Path,
        *,
        snapshot: dict[str, Any],
        selection: dict[str, Any],
        trace: dict[str, Any] | None,
    ) -> None:
        self.quest_service = quest_service
        self.quest_root = quest_root
        self.snapshot = dict(snapshot or {})
        self.selection = dict(selection or {})
        self.trace = dict(trace or {})
        self.workspace_root = self._resolve_workspace_root()
        self.branch_name = (
            str(
                self.selection.get("branch_name")
                or self.trace.get("branch_name")
                or self.snapshot.get("current_workspace_branch")
                or self.snapshot.get("research_head_branch")
                or self.snapshot.get("branch")
                or "main"
            ).strip()
            or "main"
        )
        self.stage_key = normalize_stage_key(
            self.selection.get("stage_key") or self.trace.get("stage_key") or self.snapshot.get("active_anchor") or "baseline"
        )
        self.stage_status = str(self.selection.get("status") or self.trace.get("status") or "").strip() or None
        self.artifacts = sorted(list(self.quest_service._collect_artifacts(quest_root)), key=_artifact_sort_key)

    def _resolve_workspace_root(self) -> Path:
        for raw in (
            self.selection.get("worktree_rel_path"),
            self.trace.get("worktree_rel_path"),
            self.selection.get("worktree_root"),
            self.trace.get("worktree_root"),
            self.snapshot.get("active_workspace_root"),
        ):
            text = str(raw or "").strip()
            if not text:
                continue
            candidate = Path(text)
            if not candidate.is_absolute():
                candidate = (self.quest_root / text).resolve()
            if candidate.exists():
                return candidate
        return self.quest_root

    def _infer_stage_from_branch_name(self) -> str | None:
        normalized = str(self.branch_name or "").strip().lower()
        if not normalized:
            return None
        if normalized.startswith("analysis/"):
            return "analysis"
        if normalized.startswith("run/"):
            return "experiment"
        if normalized.startswith("idea/"):
            return "idea"
        if normalized.startswith("paper/") or normalized.startswith("write/"):
            return "paper"
        if normalized.startswith("baseline/"):
            return "baseline"
        return None

    def _has_paper_state(self) -> bool:
        paper_root = self._paper_root()
        return bool(
            self._paper_candidates()
            or (paper_root / "selected_outline.json").exists()
            or (paper_root / "draft.md").exists()
            or self._paper_bundle_manifest()
        )

    def _resolve_effective_stage_key(self) -> str:
        normalized = normalize_stage_key(self.stage_key)
        if normalized in {"baseline", "idea", "experiment", "analysis", "paper"}:
            return normalized
        if normalized != "general":
            return normalized

        inferred = self._infer_stage_from_branch_name()
        if inferred:
            return inferred
        if self._analysis_stage_items(None):
            return "analysis"
        if self._experiment_stage_items():
            return "experiment"
        if self._idea_stage_items():
            return "idea"
        if self._has_paper_state():
            return "paper"
        if self._baseline_stage_items():
            return "baseline"
        return normalized

    @staticmethod
    def _artifact_detail(item: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(payload, dict) or not payload:
            return None
        record = dict(item or {})
        return {
            "artifact_id": payload.get("artifact_id") or payload.get("id"),
            "artifact_kind": payload.get("kind"),
            "artifact_path": record.get("path"),
            "payload": payload,
        }

    def build(self) -> dict[str, Any]:
        selection_type = str(self.selection.get("selection_type") or "").strip()
        explicit_stage_key = str(self.selection.get("stage_key") or "").strip()
        self.stage_key = self._resolve_effective_stage_key()
        if selection_type == "idea_candidate":
            return self._build_idea_candidate()
        if selection_type == "branch_node" and explicit_stage_key in {"", "idea"}:
            return self._build_branch()
        if self.stage_key == "baseline":
            return self._build_baseline()
        if self.stage_key == "idea":
            return self._build_idea()
        if self.stage_key == "experiment":
            return self._build_experiment()
        if self.stage_key == "analysis":
            return self._build_analysis()
        return self._build_paper()

    def _base_payload(
        self,
        *,
        title: str,
        note: str,
        status: str | None,
        tags: list[str],
        overview: list[dict[str, Any]],
        key_facts: list[dict[str, Any]],
        key_files: list[dict[str, Any]],
        history: list[dict[str, Any]],
        details: dict[str, Any] | None = None,
        lineage_intent: str | None = None,
        idea_draft_path: str | None = None,
        draft_available: bool = False,
        subviews: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "quest_id": self.snapshot.get("quest_id") or self.quest_root.name,
            "stage_key": self.stage_key,
            "stage_label": stage_label(self.stage_key),
            "selection_ref": self.selection.get("selection_ref") or self.trace.get("selection_ref"),
            "selection_type": self.selection.get("selection_type") or self.trace.get("selection_type") or "stage_node",
            "branch_name": self.branch_name,
            "title": title,
            "note": note,
            "status": status,
            "tags": [item for item in tags if item],
            "scope_paths": self._resolve_scope_paths(),
            "compare_base": self.selection.get("compare_base") or self.selection.get("compareBase"),
            "compare_head": self.selection.get("compare_head") or self.selection.get("compareHead"),
            "snapshot_revision": self.selection.get("compare_head")
            or self.selection.get("compareHead")
            or self.snapshot.get("head"),
            "lineage_intent": lineage_intent,
            "idea_draft_path": idea_draft_path,
            "draft_available": draft_available,
            "subviews": list(subviews or []),
            "sections": {
                "overview": [item for item in overview if item.get("display_value")],
                "key_facts": [item for item in key_facts if item.get("display_value")],
                "key_files": key_files,
                "history": history,
            },
            "details": details or {},
        }

    def _resolve_scope_paths(self) -> list[str]:
        raw = self.selection.get("scope_paths") or self.selection.get("scopePaths")
        if isinstance(raw, list):
            normalized = [str(item).strip() for item in raw if str(item).strip()]
            if normalized:
                return normalized
        if str(self.selection.get("selection_type") or "").strip() == "idea_candidate":
            return self._idea_candidate_scope_paths()
        if str(self.selection.get("selection_type") or "").strip() == "branch_node":
            return self._branch_scope_paths()
        defaults = {
            "baseline": self._baseline_scope_paths(),
            "idea": self._idea_scope_paths(),
            "experiment": self._experiment_scope_paths(None),
            "analysis": self._analysis_scope_paths(None),
            "paper": self._paper_scope_paths(),
        }
        return defaults.get(self.stage_key, [])

    def _latest_artifact(self, predicate) -> dict[str, Any] | None:
        items = [item for item in self.artifacts if predicate(self._payload(item))]
        return items[-1] if items else None

    @staticmethod
    def _payload(item: dict[str, Any]) -> dict[str, Any]:
        payload = item.get("payload")
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _artifact_history(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for item in sorted(items, key=_artifact_sort_key):
            payload = self._payload(item)
            kind = str(payload.get("kind") or item.get("kind") or "artifact").strip() or "artifact"
            report_type = str(payload.get("report_type") or "").strip()
            run_kind = str(payload.get("run_kind") or "").strip()
            title = (
                payload.get("summary")
                or payload.get("message")
                or payload.get("reason")
                or report_type
                or run_kind
                or kind
            )
            history.append(
                {
                    "id": str(payload.get("artifact_id") or item.get("path") or len(history)),
                    "artifact_id": payload.get("artifact_id"),
                    "artifact_kind": kind,
                    "title": _compact(title, limit=140) or kind,
                    "summary": _compact(payload.get("reason") or payload.get("message") or payload.get("summary"), limit=240),
                    "status": payload.get("status"),
                    "created_at": payload.get("updated_at") or payload.get("created_at"),
                    "path": str(item.get("path") or ""),
                    "document_id": self._document_id_for_path(item.get("path")),
                    "run_id": payload.get("run_id"),
                    "campaign_id": payload.get("campaign_id"),
                    "slice_id": payload.get("slice_id"),
                }
            )
        return history

    def _branch_matches(self, payload: dict[str, Any], *, allow_parent: bool = False, include_unscoped: bool = True) -> bool:
        branch = str(payload.get("branch") or "").strip()
        parent_branch = str(payload.get("parent_branch") or "").strip()
        if branch == self.branch_name:
            return True
        if allow_parent and parent_branch == self.branch_name:
            return True
        if include_unscoped and not branch and not parent_branch:
            return True
        return False

    def _path_in_quest(self, raw_path: object) -> tuple[Path, str, str] | None:
        text = str(raw_path or "").strip()
        if not text:
            return None
        path = Path(text)
        candidates: list[Path] = []
        if not path.is_absolute():
            for base in (self.workspace_root, self.quest_root):
                try:
                    candidates.append((base / text).resolve())
                except OSError:
                    continue
        else:
            try:
                candidates.append(path.resolve())
            except OSError:
                return None

        if not candidates:
            return None

        seen: set[str] = set()
        unique_candidates: list[Path] = []
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate)

        existing_candidates: list[Path] = []
        missing_candidates: list[Path] = []
        for candidate in unique_candidates:
            try:
                if candidate.exists():
                    existing_candidates.append(candidate)
                else:
                    missing_candidates.append(candidate)
            except OSError:
                missing_candidates.append(candidate)

        ordered = [*existing_candidates, *missing_candidates]

        workspace_root = self.workspace_root.resolve()
        quest_root = self.quest_root.resolve()
        for candidate in ordered:
            if candidate.exists():
                try:
                    relative = candidate.relative_to(workspace_root).as_posix()
                    return candidate, relative, "path"
                except ValueError:
                    pass
            try:
                relative = candidate.relative_to(quest_root).as_posix()
                return candidate, relative, "questpath"
            except ValueError:
                pass
            try:
                relative = candidate.relative_to(workspace_root).as_posix()
                return candidate, relative, "path"
            except ValueError:
                continue
        return None

    def _document_id_for_path(self, raw_path: object) -> str | None:
        resolved = self._path_in_quest(raw_path)
        if resolved is None:
            return None
        path, relative, document_scope = resolved
        if path.exists() and path.is_file():
            return f"{document_scope}::{relative}"
        return None

    def _relative_path_or_raw(self, raw_path: object) -> str | None:
        resolved = self._path_in_quest(raw_path)
        if resolved is not None:
            _path, relative, _document_scope = resolved
            return relative
        text = str(raw_path or "").strip()
        return text or None

    def _markdown_body_for_path(self, raw_path: object) -> str | None:
        resolved = self._path_in_quest(raw_path)
        if resolved is None:
            return None
        path, _relative, _document_scope = resolved
        if not path.exists() or not path.is_file():
            return None
        try:
            _metadata, body = load_markdown_document(path)
        except Exception:
            body = read_text(path, "")
        text = str(body or "").strip()
        return text or None

    def _recent_trace_actions(self, *, limit: int = 6) -> list[dict[str, Any]]:
        raw_actions = self.trace.get("actions") if isinstance(self.trace, dict) else []
        if not isinstance(raw_actions, list) or not raw_actions:
            return []
        normalized: list[dict[str, Any]] = []
        for item in raw_actions[-limit:]:
            if not isinstance(item, dict):
                continue
            summary = _compact(item.get("summary") or item.get("output") or item.get("args"), limit=1000)
            normalized.append(
                {
                    "action_id": item.get("action_id"),
                    "title": item.get("title") or item.get("tool_name") or item.get("raw_event_type") or item.get("kind"),
                    "summary": summary,
                    "status": item.get("status"),
                    "created_at": item.get("created_at"),
                    "tool_name": item.get("tool_name"),
                    "artifact_kind": item.get("artifact_kind"),
                }
            )
        return normalized

    def _trace_summary(self) -> str | None:
        if not isinstance(self.trace, dict):
            return None
        return _compact(
            self.trace.get("summary")
            or self.selection.get("summary")
            or self.trace.get("title"),
            limit=600,
        )

    def _trace_markdown(self, *, limit: int = 5) -> str | None:
        items = self._recent_trace_actions(limit=limit)
        if not items:
            return None
        lines: list[str] = []
        for item in items:
            title = str(item.get("title") or "Trace").strip() or "Trace"
            summary = str(item.get("summary") or "").strip()
            if summary:
                lines.append(f"- **{title}**: {summary}")
            else:
                lines.append(f"- **{title}**")
        return "\n".join(lines) if lines else None

    def _file_entry(
        self,
        raw_path: object,
        *,
        label: str,
        description: str | None = None,
        expected_kind: str = "file",
    ) -> dict[str, Any] | None:
        text = str(raw_path or "").strip()
        if not text:
            return None
        resolved = self._path_in_quest(text)
        if resolved is None:
            path = Path(text)
            return {
                "id": text,
                "label": label,
                "description": description,
                "path": text,
                "absolute_path": str(path),
                "document_id": None,
                "kind": expected_kind,
                "exists": path.exists(),
                "scope": "external",
            }
        path, relative, document_scope = resolved
        exists = path.exists()
        kind = "directory" if (exists and path.is_dir()) or expected_kind == "directory" else "file"
        scope = self.quest_service._classify_relative_scope(relative)[0]
        return {
            "id": relative,
            "label": label,
            "description": description,
            "path": relative,
            "absolute_path": str(path),
            "document_id": f"{document_scope}::{relative}" if exists and path.is_file() else None,
            "kind": kind,
            "exists": exists,
            "scope": scope,
        }

    def _paper_bundle_manifest(self) -> dict[str, Any]:
        payload = read_json(self._paper_root() / "paper_bundle_manifest.json", {})
        return payload if isinstance(payload, dict) else {}

    def _paper_root(self) -> Path:
        candidates = [self.workspace_root / "paper", self.quest_root / "paper"]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _paper_scope_paths(self) -> list[str]:
        try:
            return [self._paper_root().relative_to(self.quest_root).as_posix()]
        except ValueError:
            return ["paper"]

    def _open_source_root(self) -> Path:
        candidates = [self.workspace_root / "release" / "open_source", self.quest_root / "release" / "open_source"]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _paper_relative_path(self, raw_path: object) -> str | None:
        resolved = self._path_in_quest(raw_path)
        if resolved is None:
            return None
        _path, relative, _document_scope = resolved
        return relative

    def _paper_latex_root(
        self,
        bundle_manifest: dict[str, Any],
        *,
        compile_report: dict[str, Any] | None = None,
    ) -> str | None:
        for candidate in (
            bundle_manifest.get("latex_root_path"),
            (compile_report or {}).get("latex_root_path"),
            (compile_report or {}).get("main_file_path"),
        ):
            resolved = self._path_in_quest(candidate)
            if resolved is None:
                continue
            path, relative, _document_scope = resolved
            if path.is_dir():
                return relative
            if path.suffix.lower() == ".tex":
                return PurePosixPath(relative).parent.as_posix()
        paper_root = self._paper_root()
        for candidate in (paper_root / "latex", paper_root / "tex"):
            if candidate.exists():
                try:
                    return candidate.relative_to(self.workspace_root.resolve()).as_posix()
                except ValueError:
                    return candidate.relative_to(self.quest_root).as_posix()
        return None

    def _paper_main_tex(
        self,
        latex_root_rel: str | None,
        *,
        bundle_manifest: dict[str, Any] | None = None,
        compile_report: dict[str, Any] | None = None,
    ) -> str | None:
        for candidate in (
            (compile_report or {}).get("main_file_path"),
            bundle_manifest.get("main_tex_path") if isinstance(bundle_manifest, dict) else None,
            bundle_manifest.get("latex_root_path") if isinstance(bundle_manifest, dict) else None,
            (compile_report or {}).get("latex_root_path"),
        ):
            resolved = self._path_in_quest(candidate)
            if resolved is None:
                continue
            path, relative, _document_scope = resolved
            if path.suffix.lower() == ".tex":
                return relative
            if path.is_dir():
                preferred = path / "main.tex"
                if preferred.exists():
                    nested = self._path_in_quest(preferred)
                    if nested is not None:
                        _resolved_path, nested_relative, _nested_scope = nested
                        return nested_relative
        if not latex_root_rel:
            return None
        latex_root = (self.workspace_root / latex_root_rel).resolve()
        if not latex_root.exists():
            latex_root = (self.quest_root / latex_root_rel).resolve()
        if latex_root.is_file() and latex_root.suffix.lower() == ".tex":
            nested = self._path_in_quest(latex_root)
            if nested is not None:
                _resolved_path, nested_relative, _nested_scope = nested
                return nested_relative
            return None
        preferred = latex_root / "main.tex"
        if preferred.exists():
            nested = self._path_in_quest(preferred)
            if nested is not None:
                _resolved_path, nested_relative, _nested_scope = nested
                return nested_relative
        candidates = sorted(latex_root.glob("*.tex"))
        if not candidates:
            return None
        nested = self._path_in_quest(candidates[0])
        if nested is None:
            return None
        _resolved_path, nested_relative, _nested_scope = nested
        return nested_relative

    def _paper_pdf_candidates(
        self,
        bundle_manifest: dict[str, Any],
        *,
        main_tex_rel: str | None = None,
    ) -> list[str]:
        candidates: list[str] = []
        explicit = self._paper_relative_path(bundle_manifest.get("pdf_path"))
        if explicit:
            candidates.append(explicit)
        if main_tex_rel:
            guessed = str(PurePosixPath(main_tex_rel).with_suffix(".pdf"))
            if (self.quest_root / guessed).exists():
                candidates.append(guessed)
        for path in sorted(self._paper_root().glob("*.pdf")):
            candidates.append(path.relative_to(self.quest_root).as_posix())
        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    @staticmethod
    def _dedupe_files(items: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not item:
                continue
            key = str(item.get("kind") or "") + "::" + str(item.get("path") or item.get("absolute_path") or "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _baseline_scope_paths(self) -> list[str]:
        baseline_id = str(self.snapshot.get("active_baseline_id") or "").strip()
        return [
            *( [f"baselines/imported/{baseline_id}"] if baseline_id else []),
            *( [f"baselines/local/{baseline_id}"] if baseline_id else []),
            "artifacts/baselines",
        ]

    def _idea_scope_paths(self) -> list[str]:
        idea_id = str(self.snapshot.get("active_idea_id") or "").strip()
        return [
            *( [f"memory/ideas/{idea_id}"] if idea_id else []),
            "literature",
            "artifacts/ideas",
            "artifacts/reports",
        ]

    def _idea_candidate_scope_paths(self) -> list[str]:
        candidate_id = str(self.selection.get("selection_ref") or self.selection.get("idea_id") or "").strip()
        return [
            *( [f"memory/ideas/_candidates/{candidate_id}"] if candidate_id else []),
            "artifacts/reports",
        ]

    def _experiment_scope_paths(self, run_id: str | None) -> list[str]:
        return [
            *( [f"experiments/main/{run_id}"] if run_id else []),
            "artifacts/runs",
        ]

    def _analysis_scope_paths(self, campaign_id: str | None) -> list[str]:
        return [
            "experiments/analysis",
            *( [f"experiments/analysis-results/{campaign_id}"] if campaign_id else []),
            "artifacts/runs",
            "artifacts/reports",
        ]

    @staticmethod
    def _normalize_path_list(values: list[object] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values or []:
            value = str(raw or "").strip().strip("/")
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _branch_scope_paths(self) -> list[str]:
        idea_items = [
            item
            for item in self.artifacts
            if str(self._payload(item).get("kind") or "").strip() == "idea"
            and self._branch_matches(self._payload(item), include_unscoped=False)
        ]
        latest_idea_item = idea_items[-1] if idea_items else None
        latest_idea_payload = self._payload(latest_idea_item or {})
        latest_idea_details = (
            dict(latest_idea_payload.get("details") or {})
            if isinstance(latest_idea_payload.get("details"), dict)
            else {}
        )
        experiment_items = self._experiment_stage_items()
        latest_experiment_item = experiment_items[-1] if experiment_items else None
        latest_experiment_payload = self._payload(latest_experiment_item or {})
        analysis_items = self._analysis_stage_items(None)
        latest_analysis_item = analysis_items[-1] if analysis_items else None
        latest_analysis_payload = self._payload(latest_analysis_item or {})
        foundation_ref = latest_idea_payload.get("foundation_ref") or latest_idea_details.get("foundation_ref") or {}
        foundation_ref = dict(foundation_ref) if isinstance(foundation_ref, dict) else {}

        paths: list[str] = [
            "brief.md",
            "plan.md",
            "status.md",
            "SUMMARY.md",
            "artifacts/ideas",
            "artifacts/runs",
            "artifacts/reports",
        ]
        idea_id = str(latest_idea_payload.get("idea_id") or "").strip()
        if idea_id:
            paths.extend([f"memory/ideas/{idea_id}", "literature"])
        run_id = str(latest_experiment_payload.get("run_id") or "").strip()
        if run_id:
            paths.append(f"experiments/main/{run_id}")
        campaign_id = str(latest_analysis_payload.get("campaign_id") or "").strip()
        if campaign_id:
            paths.extend(["experiments/analysis", f"experiments/analysis-results/{campaign_id}"])
        foundation_kind = str(foundation_ref.get("kind") or "").strip().lower()
        foundation_name = str(foundation_ref.get("ref") or "").strip()
        if foundation_kind == "baseline" and foundation_name:
            paths.extend([f"baselines/imported/{foundation_name}", f"baselines/local/{foundation_name}"])
        if self.stage_key == "paper":
            paths.append("paper")
        return self._normalize_path_list(paths)

    def _baseline_stage_items(self) -> list[dict[str, Any]]:
        def predicate(payload: dict[str, Any]) -> bool:
            flow_type = str(payload.get("flow_type") or "").strip()
            report_type = str(payload.get("report_type") or "").strip()
            action = str(payload.get("action") or "").strip()
            kind = str(payload.get("kind") or "").strip()
            return (
                kind == "baseline"
                or flow_type == "baseline_gate"
                or report_type == "baseline_attachment"
                or action == "waive_baseline"
            )

        return [item for item in self.artifacts if predicate(self._payload(item))]

    def _build_baseline(self) -> dict[str, Any]:
        attachment = self.quest_service._active_baseline_attachment(self.quest_root, self.workspace_root)
        confirmed_ref = (
            dict(self.snapshot.get("confirmed_baseline_ref") or {})
            if isinstance(self.snapshot.get("confirmed_baseline_ref"), dict)
            else {}
        )
        baseline_items = self._baseline_stage_items()
        latest = baseline_items[-1] if baseline_items else None
        latest_payload = self._payload(latest or {})
        entry = dict(attachment.get("entry") or {}) if isinstance(attachment, dict) else {}
        confirmation = dict(attachment.get("confirmation") or {}) if isinstance(attachment, dict) else {}

        baseline_id = (
            str(
                self.snapshot.get("active_baseline_id")
                or confirmed_ref.get("baseline_id")
                or (attachment or {}).get("source_baseline_id")
                or latest_payload.get("baseline_id")
                or "pending"
            ).strip()
            or "pending"
        )
        variant_id = (
            str(
                self.snapshot.get("active_baseline_variant_id")
                or confirmed_ref.get("variant_id")
                or (attachment or {}).get("source_variant_id")
                or latest_payload.get("baseline_variant_id")
                or ""
            ).strip()
            or None
        )
        source_mode = (
            str(
                confirmed_ref.get("source_mode")
                or confirmation.get("source_mode")
                or ((latest_payload.get("details") or {}) if isinstance(latest_payload.get("details"), dict) else {}).get("source_mode")
                or entry.get("source_mode")
                or ""
            ).strip()
            or None
        )
        baseline_kind = (
            str(latest_payload.get("baseline_kind") or entry.get("baseline_kind") or source_mode or "").strip()
            or None
        )
        baseline_gate = str(self.snapshot.get("baseline_gate") or "pending").strip() or "pending"
        note = (
            str(latest_payload.get("summary") or latest_payload.get("reason") or "").strip()
            or ("Baseline gate has been waived for this quest." if baseline_gate == "waived" else "No confirmed baseline yet.")
        )
        metrics_summary = latest_payload.get("metrics_summary") or entry.get("metrics_summary") or {}
        metric_contract = latest_payload.get("metric_contract") or entry.get("metric_contract") or {}
        primary_metric = latest_payload.get("primary_metric") or entry.get("primary_metric")
        comment = (
            ((latest_payload.get("details") or {}) if isinstance(latest_payload.get("details"), dict) else {}).get("comment")
            or confirmed_ref.get("comment")
            or confirmation.get("comment")
        )
        baseline_root = (
            latest_payload.get("path")
            or confirmed_ref.get("baseline_path")
            or confirmation.get("baseline_root")
            or (entry.get("path") if isinstance(entry, dict) else None)
            or (str(self.quest_root / "baselines" / "imported" / baseline_id) if baseline_id != "pending" else None)
        )
        attachment_path = (
            str(self.quest_root / "baselines" / "imported" / baseline_id / "attachment.yaml")
            if baseline_id != "pending"
            else None
        )
        title = f"Baseline · {baseline_id}"
        files = self._dedupe_files(
            [
                self._file_entry(attachment_path, label="Attachment", description="Confirmed baseline attachment metadata."),
                self._file_entry(baseline_root, label="Baseline Root", description="Confirmed baseline directory.", expected_kind="directory"),
                self._file_entry(latest.get("path") if latest else None, label="Baseline Artifact", description="Latest baseline gate artifact."),
            ]
        )
        return self._base_payload(
            title=title,
            note=note,
            status=baseline_gate,
            tags=[baseline_gate, source_mode or "", baseline_kind or ""],
            overview=[
                _field("Baseline ID", baseline_id),
                _field("Variant ID", variant_id or "default"),
                _field("Source Mode", source_mode or "unknown"),
                _field("Baseline Gate", baseline_gate),
                _field("Baseline Kind", baseline_kind or "unknown"),
            ],
            key_facts=[
                _field("Primary Metric", primary_metric or "Not recorded"),
                _field("Metric Contract", metric_contract or "Not recorded"),
                _field("Metrics Summary", metrics_summary or "Not recorded"),
                _field("Confirmation Comment", comment or "Not recorded"),
                _field("Baseline Root", baseline_root or "Not recorded"),
                _field("Attachment Path", attachment_path or "Not recorded"),
            ],
            key_files=files,
            history=self._artifact_history(baseline_items),
            details={
                "baseline": {
                    "baseline_id": baseline_id,
                    "variant_id": variant_id,
                    "source_mode": source_mode,
                    "baseline_gate": baseline_gate,
                    "baseline_kind": baseline_kind,
                    "primary_metric": primary_metric,
                    "metric_contract": metric_contract,
                    "metrics_summary": metrics_summary,
                    "confirmation_comment": comment,
                    "baseline_root": baseline_root,
                    "attachment_path": attachment_path,
                }
            },
        )

    def _idea_stage_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in self.artifacts:
            payload = self._payload(item)
            flow_type = str(payload.get("flow_type") or "").strip()
            kind = str(payload.get("kind") or "").strip()
            if flow_type == "idea_submission" or kind == "idea":
                if self._branch_matches(payload):
                    items.append(item)
                    continue
                idea_id = str(payload.get("idea_id") or "").strip()
                if idea_id and idea_id == str(self.snapshot.get("active_idea_id") or "").strip():
                    items.append(item)
        return items

    def _idea_candidate_stage_items(self) -> list[dict[str, Any]]:
        candidate_id = str(self.selection.get("selection_ref") or self.selection.get("idea_id") or "").strip()
        if not candidate_id:
            return []
        items: list[dict[str, Any]] = []
        for item in self.artifacts:
            payload = self._payload(item)
            if str(payload.get("kind") or "").strip() != "idea":
                continue
            if str(payload.get("idea_id") or "").strip() != candidate_id:
                continue
            flow_type = str(payload.get("flow_type") or "").strip()
            protocol_step = str(payload.get("protocol_step") or "").strip()
            details = dict(payload.get("details") or {}) if isinstance(payload.get("details"), dict) else {}
            submission_mode = str(details.get("submission_mode") or payload.get("submission_mode") or "").strip().lower()
            if flow_type == "idea_submission" and (protocol_step == "candidate" or submission_mode == "candidate"):
                items.append(item)
        return items

    def _build_idea(self) -> dict[str, Any]:
        idea_items = self._idea_stage_items()
        latest = idea_items[-1] if idea_items else None
        payload = self._payload(latest or {})
        details = dict(payload.get("details") or {}) if isinstance(payload.get("details"), dict) else {}
        idea_id = str(payload.get("idea_id") or self.snapshot.get("active_idea_id") or "idea").strip() or "idea"
        title_text = str(details.get("title") or idea_id).strip() or idea_id
        worktree_root = (
            str(payload.get("worktree_root") or self.snapshot.get("research_head_worktree_root") or self.workspace_root).strip()
            or str(self.workspace_root)
        )
        idea_md_path = (
            ((payload.get("paths") or {}) if isinstance(payload.get("paths"), dict) else {}).get("idea_md")
            or self.snapshot.get("active_idea_md_path")
            or str(Path(worktree_root) / "memory" / "ideas" / idea_id / "idea.md")
        )
        draft_md_path = (
            ((payload.get("paths") or {}) if isinstance(payload.get("paths"), dict) else {}).get("idea_draft_md")
            or details.get("idea_draft_path")
            or self.snapshot.get("active_idea_draft_path")
            or str(Path(worktree_root) / "memory" / "ideas" / idea_id / "draft.md")
        )
        idea_markdown = self._markdown_body_for_path(idea_md_path)
        idea_md_rel_path = self._relative_path_or_raw(idea_md_path)
        draft_md_rel_path = self._relative_path_or_raw(draft_md_path)
        draft_markdown = self._markdown_body_for_path(draft_md_path)
        lineage_intent = str(payload.get("lineage_intent") or details.get("lineage_intent") or "").strip() or None
        selection_scores = details.get("selection_scores")
        selection_score_summary = _selection_score_summary(selection_scores)
        note = (
            str(payload.get("summary") or payload.get("reason") or "").strip()
            or "No durable idea submission has been recorded yet."
        )
        literature_files = self._dedupe_files(
            [
                *[
                    self._file_entry(path, label=f"Literature · {path.name}", description="Literature note or survey file.")
                    for path in sorted((Path(worktree_root) / "literature").glob("**/*.md"))[:6]
                ],
                *[
                    self._file_entry(path, label=f"Memory · {path.name}", description="Reusable idea memory card.")
                    for path in sorted((Path(worktree_root) / "memory" / "ideas" / idea_id).glob("**/*.md"))[:6]
                ],
            ]
        )
        history_items = list(idea_items)
        history_items.extend(
            item
            for item in self.artifacts
            if str(self._payload(item).get("kind") or "") == "decision" and self._branch_matches(self._payload(item))
        )
        return self._base_payload(
            title=f"Idea · {title_text}",
            note=note,
            status=str(payload.get("status") or self.stage_status or "ready").strip() or "ready",
            tags=[
                str(payload.get("protocol_step") or "").strip(),
                str(details.get("next_target") or "").strip(),
                lineage_intent or "",
                self.branch_name,
            ],
            overview=[
                _field("Title", title_text),
                _field("Next Target", details.get("next_target") or "experiment"),
                _field("Branch", str(payload.get("branch") or self.branch_name)),
                _field("Worktree", worktree_root),
                _field("Active Idea ID", idea_id),
            ],
            key_facts=[
                _field("Problem", details.get("problem") or "Not recorded"),
                _field("Hypothesis", details.get("hypothesis") or "Not recorded"),
                _field("Mechanism", details.get("mechanism") or "Not recorded"),
                _field("Method Brief", details.get("method_brief") or "Not recorded"),
                _field("Selection Scores", selection_score_summary or "Not recorded"),
                _field("Mechanism Family", details.get("mechanism_family") or "Not recorded"),
                _field("Change Layer", details.get("change_layer") or "Not recorded"),
                _field("Source Lens", details.get("source_lens") or "Not recorded"),
                _field("Expected Gain", details.get("expected_gain") or "Not recorded"),
                _field("Risks", details.get("risks") or "Not recorded"),
                _field("Evidence Paths", details.get("evidence_paths") or "Not recorded"),
            ],
            key_files=self._dedupe_files(
                [
                    self._file_entry(idea_md_path, label="Idea Markdown", description="Selected idea durable document."),
                    self._file_entry(draft_md_path, label="Idea Draft", description="Long-form ideation draft in Markdown."),
                    *literature_files,
                ]
            ),
            history=self._artifact_history(history_items),
            details={
                "idea": {
                    "idea_id": idea_id,
                    "title": title_text,
                    "next_target": details.get("next_target") or "experiment",
                    "branch": str(payload.get("branch") or self.branch_name),
                    "worktree_root": worktree_root,
                    "problem": details.get("problem"),
                    "hypothesis": details.get("hypothesis"),
                    "mechanism": details.get("mechanism"),
                    "method_brief": details.get("method_brief"),
                    "selection_scores": selection_scores or None,
                    "mechanism_family": details.get("mechanism_family"),
                    "change_layer": details.get("change_layer"),
                    "source_lens": details.get("source_lens"),
                    "expected_gain": details.get("expected_gain"),
                    "risks": details.get("risks") or [],
                    "evidence_paths": details.get("evidence_paths") or [],
                    "lineage_intent": lineage_intent,
                    "idea_path": idea_md_rel_path,
                    "idea_markdown": idea_markdown,
                    "draft_path": draft_md_rel_path,
                    "draft_markdown": draft_markdown,
                    "literature_files": literature_files,
                    "decision_reason": payload.get("reason"),
                },
                "latest_artifact": self._artifact_detail(latest, payload),
            },
            lineage_intent=lineage_intent,
            idea_draft_path=draft_md_rel_path,
            draft_available=bool(draft_markdown),
            subviews=["overview", "details", "draft"] if draft_markdown else ["overview", "details"],
        )

    def _build_idea_candidate(self) -> dict[str, Any]:
        candidate_items = self._idea_candidate_stage_items()
        latest = candidate_items[-1] if candidate_items else None
        payload = self._payload(latest or {})
        details = dict(payload.get("details") or {}) if isinstance(payload.get("details"), dict) else {}
        candidate_id = str(self.selection.get("selection_ref") or payload.get("idea_id") or "candidate").strip() or "candidate"
        title_text = (
            str(details.get("title") or self.selection.get("label") or candidate_id).strip() or candidate_id
        )
        paths = dict(payload.get("paths") or {}) if isinstance(payload.get("paths"), dict) else {}
        candidate_root = paths.get("candidate_root") or str(self.quest_root / "memory" / "ideas" / "_candidates" / candidate_id)
        idea_md_path = paths.get("idea_md") or str(Path(candidate_root) / "idea.md")
        draft_md_path = paths.get("idea_draft_md") or details.get("idea_draft_path") or str(Path(candidate_root) / "draft.md")
        idea_markdown = self._markdown_body_for_path(idea_md_path)
        draft_markdown = self._markdown_body_for_path(draft_md_path)
        idea_md_rel_path = self._relative_path_or_raw(idea_md_path)
        draft_md_rel_path = self._relative_path_or_raw(draft_md_path)
        candidate_root_rel_path = self._relative_path_or_raw(candidate_root)
        selection_scores = details.get("selection_scores")
        selection_score_summary = _selection_score_summary(selection_scores)
        note = (
            str(payload.get("summary") or payload.get("reason") or self.selection.get("summary") or "").strip()
            or "No durable candidate brief summary has been recorded yet."
        )
        lineage_intent = str(payload.get("lineage_intent") or details.get("lineage_intent") or "").strip() or None
        parent_branch = str(payload.get("parent_branch") or details.get("parent_branch") or self.selection.get("branch_name") or "").strip() or None
        foundation_reason = str(payload.get("foundation_reason") or details.get("foundation_reason") or "").strip() or None
        return self._base_payload(
            title=f"Candidate Brief · {title_text}",
            note=note,
            status=str(payload.get("status") or "candidate").strip() or "candidate",
            tags=[
                "candidate-brief",
                details.get("mechanism_family") or "",
                details.get("change_layer") or "",
                details.get("source_lens") or "",
                lineage_intent or "",
            ],
            overview=[
                _field("Candidate ID", candidate_id),
                _field("Parent Branch", parent_branch or "Not recorded"),
                _field("Next Target", details.get("next_target") or "optimize"),
                _field("Candidate Root", candidate_root_rel_path or candidate_root),
            ],
            key_facts=[
                _field("Problem", details.get("problem") or "Not recorded"),
                _field("Hypothesis", details.get("hypothesis") or "Not recorded"),
                _field("Mechanism", details.get("mechanism") or "Not recorded"),
                _field("Method Brief", details.get("method_brief") or "Not recorded"),
                _field("Selection Scores", selection_score_summary or "Not recorded"),
                _field("Mechanism Family", details.get("mechanism_family") or "Not recorded"),
                _field("Change Layer", details.get("change_layer") or "Not recorded"),
                _field("Source Lens", details.get("source_lens") or "Not recorded"),
                _field("Expected Gain", details.get("expected_gain") or "Not recorded"),
                _field("Foundation Reason", foundation_reason or "Not recorded"),
            ],
            key_files=self._dedupe_files(
                [
                    self._file_entry(candidate_root, label="Candidate Root", description="Branchless candidate brief workspace.", expected_kind="directory"),
                    self._file_entry(idea_md_path, label="Candidate Markdown", description="Durable candidate brief document."),
                    self._file_entry(draft_md_path, label="Candidate Draft", description="Long-form candidate brief draft."),
                ]
            ),
            history=self._artifact_history(candidate_items),
            details={
                "idea": {
                    "idea_id": candidate_id,
                    "title": title_text,
                    "problem": details.get("problem"),
                    "hypothesis": details.get("hypothesis"),
                    "mechanism": details.get("mechanism"),
                    "method_brief": details.get("method_brief"),
                    "selection_scores": selection_scores or None,
                    "mechanism_family": details.get("mechanism_family"),
                    "change_layer": details.get("change_layer"),
                    "source_lens": details.get("source_lens"),
                    "expected_gain": details.get("expected_gain"),
                    "next_target": details.get("next_target") or "optimize",
                    "lineage_intent": lineage_intent,
                    "parent_branch": parent_branch,
                    "candidate_root": candidate_root_rel_path or candidate_root,
                    "idea_path": idea_md_rel_path,
                    "idea_markdown": idea_markdown,
                    "draft_path": draft_md_rel_path,
                    "draft_markdown": draft_markdown,
                    "decision_reason": payload.get("reason"),
                },
                "latest_artifact": self._artifact_detail(latest, payload),
            },
            lineage_intent=lineage_intent,
            idea_draft_path=draft_md_rel_path,
            draft_available=bool(draft_markdown),
            subviews=["overview", "details", "draft"] if draft_markdown else ["overview", "details"],
        )

    def _build_branch(self) -> dict[str, Any]:
        idea_items = [
            item
            for item in self.artifacts
            if str(self._payload(item).get("kind") or "").strip() == "idea"
            and self._branch_matches(self._payload(item), include_unscoped=False)
        ]
        latest_idea_item = idea_items[-1] if idea_items else None
        latest_idea_payload = self._payload(latest_idea_item or {})
        latest_idea_details = (
            dict(latest_idea_payload.get("details") or {})
            if isinstance(latest_idea_payload.get("details"), dict)
            else {}
        )
        branch_no = str(
            latest_idea_payload.get("branch_no")
            or latest_idea_details.get("branch_no")
            or ""
        ).strip() or None
        idea_title = str(latest_idea_details.get("title") or "").strip() or None
        idea_problem = str(latest_idea_details.get("problem") or "").strip() or None
        next_target = str(latest_idea_details.get("next_target") or "").strip() or None
        selection_scores = latest_idea_details.get("selection_scores")
        selection_score_summary = _selection_score_summary(selection_scores)
        lineage_intent = str(
            latest_idea_payload.get("lineage_intent")
            or latest_idea_details.get("lineage_intent")
            or ""
        ).strip() or None
        parent_branch = str(
            latest_idea_payload.get("parent_branch")
            or self.selection.get("compare_base")
            or ""
        ).strip() or None
        foundation_ref = latest_idea_payload.get("foundation_ref") or latest_idea_details.get("foundation_ref") or {}
        foundation_ref = dict(foundation_ref) if isinstance(foundation_ref, dict) else {}
        foundation_reason = str(
            latest_idea_payload.get("foundation_reason")
            or latest_idea_details.get("foundation_reason")
            or ""
        ).strip() or None
        foundation_kind = str(foundation_ref.get("kind") or "").strip() or None
        foundation_branch = str(foundation_ref.get("branch") or "").strip() or None
        foundation_ref_name = str(foundation_ref.get("ref") or "").strip() or None
        foundation_label = None
        if foundation_kind and foundation_ref_name:
            foundation_label = f"{foundation_kind} · {foundation_ref_name}"
        elif foundation_branch:
            foundation_label = foundation_branch
        elif parent_branch:
            foundation_label = parent_branch

        experiment_items = self._experiment_stage_items()
        latest_experiment_item = experiment_items[-1] if experiment_items else None
        latest_experiment_payload = self._payload(latest_experiment_item or {})
        latest_experiment_paths = (
            dict(latest_experiment_payload.get("paths") or {})
            if isinstance(latest_experiment_payload.get("paths"), dict)
            else {}
        )
        latest_run_markdown = self._markdown_body_for_path(latest_experiment_paths.get("run_md"))
        latest_result_payload = (
            read_json(Path(str(latest_experiment_paths.get("result_json"))), {})
            if str(latest_experiment_paths.get("result_json") or "").strip()
            else {}
        )
        if not isinstance(latest_result_payload, dict):
            latest_result_payload = {}
        latest_progress_eval = (
            latest_experiment_payload.get("progress_eval")
            if isinstance(latest_experiment_payload.get("progress_eval"), dict)
            else latest_result_payload.get("progress_eval")
            if isinstance(latest_result_payload.get("progress_eval"), dict)
            else {}
        )
        latest_metrics_summary = latest_experiment_payload.get("metrics_summary") or latest_result_payload.get("metrics_summary") or {}
        latest_run_id = str(latest_experiment_payload.get("run_id") or "").strip() or None
        latest_evaluation_summary = _evaluation_summary(
            latest_experiment_payload.get("evaluation_summary") or latest_result_payload.get("evaluation_summary")
        )

        analysis_manifests = self._analysis_manifests()
        analysis_manifest = next(
            (
                item
                for item in reversed(analysis_manifests)
                if str(item.get("parent_branch") or "").strip() == self.branch_name
            ),
            None,
        )
        analysis_manifest = dict(analysis_manifest or {})
        analysis_summary_path = (
            str(self.quest_root / "experiments" / "analysis-results" / str(analysis_manifest.get("campaign_id") or "").strip() / "SUMMARY.md")
            if str(analysis_manifest.get("campaign_id") or "").strip()
            else None
        )
        analysis_summary_markdown = self._markdown_body_for_path(analysis_summary_path)

        branch_items = [
            item
            for item in self.artifacts
            if self._branch_matches(self._payload(item), allow_parent=True, include_unscoped=False)
        ]
        latest_branch_payload = self._payload(branch_items[-1] if branch_items else {})
        note = (
            str(
                latest_experiment_payload.get("summary")
                or latest_idea_payload.get("summary")
                or latest_idea_payload.get("reason")
                or latest_branch_payload.get("summary")
                or latest_branch_payload.get("message")
                or latest_branch_payload.get("reason")
                or self.trace.get("summary")
                or self.selection.get("summary")
                or ""
            ).strip()
            or "No durable branch summary has been recorded yet."
        )

        title_suffix = idea_title or self.branch_name
        title_prefix = f"Branch #{branch_no}" if branch_no else "Branch"
        idea_draft_path = (
            ((latest_idea_payload.get("paths") or {}) if isinstance(latest_idea_payload.get("paths"), dict) else {}).get("idea_draft_md")
            or latest_idea_details.get("idea_draft_path")
        )
        idea_draft_rel_path = self._relative_path_or_raw(idea_draft_path)
        idea_draft_markdown = self._markdown_body_for_path(idea_draft_path)
        payload = self._base_payload(
            title=f"{title_prefix} · {title_suffix}",
            note=note,
            status=str(self.trace.get("status") or latest_experiment_payload.get("status") or latest_idea_payload.get("status") or "ready").strip() or "ready",
            tags=[
                self.branch_name,
                self.stage_key,
                lineage_intent or "",
                branch_no or "",
            ],
            overview=[
                _field("Branch No", branch_no or "Not assigned"),
                _field("Branch", self.branch_name),
                _field("Stage", stage_label(self.stage_key)),
                _field("Parent Branch", parent_branch or "Not recorded"),
                _field("Compare", f"{self.selection.get('compare_base') or parent_branch or 'main'} → {self.selection.get('compare_head') or self.branch_name}"),
            ],
            key_facts=[
                _field("Idea Title", idea_title or "Not recorded"),
                _field("Idea Problem", idea_problem or "Not recorded"),
                _field("Method Brief", latest_idea_details.get("method_brief") or "Not recorded"),
                _field("Selection Scores", selection_score_summary or "Not recorded"),
                _field("Mechanism Family", latest_idea_details.get("mechanism_family") or "Not recorded"),
                _field("Change Layer", latest_idea_details.get("change_layer") or "Not recorded"),
                _field("Source Lens", latest_idea_details.get("source_lens") or "Not recorded"),
                _field("Foundation", foundation_label or "Current head"),
                _field("Foundation Reason", foundation_reason or "Not recorded"),
                _field("Next Target", next_target or "Not recorded"),
                _field("Latest Run", latest_run_id or "Not recorded"),
                _field("Latest Metrics", latest_metrics_summary or "Not recorded"),
                _field("Delta vs Baseline", latest_progress_eval.get("delta_vs_baseline") or "Not recorded"),
                _field("Breakthrough", latest_progress_eval.get("breakthrough_level") or "Not recorded"),
                *_evaluation_summary_fields(latest_evaluation_summary),
            ],
            key_files=self._dedupe_files(
                [
                    self._file_entry(
                        ((latest_idea_payload.get("paths") or {}) if isinstance(latest_idea_payload.get("paths"), dict) else {}).get("idea_md"),
                        label="Idea Markdown",
                        description="Active branch idea document.",
                    ),
                    self._file_entry(
                        idea_draft_path,
                        label="Idea Draft",
                        description="Long-form ideation draft for this branch.",
                    ),
                    self._file_entry(
                        latest_experiment_paths.get("run_md"),
                        label="Run Markdown",
                        description="Latest main experiment narrative.",
                    ),
                    self._file_entry(
                        latest_experiment_paths.get("result_json"),
                        label="Result JSON",
                        description="Latest structured main experiment result.",
                    ),
                    self._file_entry(
                        analysis_summary_path,
                        label="Analysis Summary",
                        description="Merged analysis summary for this branch.",
                    ),
                    self._file_entry(
                        (self._paper_root() / "selected_outline.json") if (self._paper_root() / "selected_outline.json").exists() else None,
                        label="Selected Outline",
                        description="Current selected paper outline.",
                    ),
                ]
            ),
            history=self._artifact_history(branch_items),
            details={
                "branch": {
                    "branch_no": branch_no,
                    "branch_name": self.branch_name,
                    "parent_branch": parent_branch,
                    "foundation_ref": foundation_ref or None,
                    "foundation_reason": foundation_reason,
                    "foundation_label": foundation_label,
                    "lineage_intent": lineage_intent,
                    "idea_title": idea_title,
                    "idea_problem": idea_problem,
                    "method_brief": latest_idea_details.get("method_brief"),
                    "selection_scores": selection_scores or None,
                    "mechanism_family": latest_idea_details.get("mechanism_family"),
                    "change_layer": latest_idea_details.get("change_layer"),
                    "source_lens": latest_idea_details.get("source_lens"),
                    "next_target": next_target,
                    "idea_draft_path": idea_draft_rel_path,
                    "idea_draft_markdown": idea_draft_markdown,
                    "idea_hypothesis": latest_idea_details.get("hypothesis"),
                    "idea_mechanism": latest_idea_details.get("mechanism"),
                    "idea_expected_gain": latest_idea_details.get("expected_gain"),
                    "idea_risks": latest_idea_details.get("risks") or [],
                    "decision_reason": latest_idea_payload.get("reason"),
                    "latest_main_experiment": {
                        "run_id": latest_run_id,
                        "summary": latest_experiment_payload.get("summary"),
                        "status": latest_experiment_payload.get("status"),
                        "verdict": latest_experiment_payload.get("verdict"),
                        "metrics_summary": latest_metrics_summary,
                        "progress_eval": latest_progress_eval,
                        "evaluation_summary": latest_evaluation_summary,
                        "run_md_path": latest_experiment_paths.get("run_md"),
                        "run_markdown": latest_run_markdown,
                        "result_json_path": latest_experiment_paths.get("result_json"),
                        "result_payload": latest_result_payload,
                    }
                    if latest_run_id
                    else None,
                    "analysis_summary_path": self._relative_path_or_raw(analysis_summary_path),
                    "analysis_summary_markdown": analysis_summary_markdown,
                },
                "latest_artifact": self._artifact_detail(latest_experiment_item or latest_idea_item, latest_experiment_payload or latest_idea_payload),
            },
            lineage_intent=lineage_intent,
            idea_draft_path=idea_draft_rel_path,
            draft_available=bool(idea_draft_markdown),
            subviews=["overview", "details", "draft"] if idea_draft_markdown else ["overview", "details"],
        )
        payload["branch_no"] = branch_no
        payload["parent_branch"] = parent_branch
        payload["foundation_ref"] = foundation_ref or None
        payload["foundation_reason"] = foundation_reason
        payload["foundation_label"] = foundation_label
        payload["lineage_intent"] = lineage_intent
        return payload

    def _experiment_stage_items(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.artifacts
            if (
                str(self._payload(item).get("flow_type") or "").strip() == "main_experiment"
                or str(self._payload(item).get("run_kind") or "").strip() == "main_experiment"
            )
            and self._branch_matches(self._payload(item))
        ]

    def _build_experiment(self) -> dict[str, Any]:
        experiment_items = self._experiment_stage_items()
        latest = experiment_items[-1] if experiment_items else None
        payload = self._payload(latest or {})
        paths = dict(payload.get("paths") or {}) if isinstance(payload.get("paths"), dict) else {}
        result_payload = read_json(Path(paths.get("result_json")), {}) if str(paths.get("result_json") or "").strip() else {}
        progress_eval = payload.get("progress_eval") or result_payload.get("progress_eval") or {}
        baseline_ref = payload.get("baseline_ref") or result_payload.get("baseline_ref") or {}
        evaluation_summary = _evaluation_summary(payload.get("evaluation_summary") or result_payload.get("evaluation_summary"))
        run_id = str(payload.get("run_id") or "pending").strip() or "pending"
        run_markdown = self._markdown_body_for_path(paths.get("run_md"))
        trace_summary = self._trace_summary()
        trace_markdown = self._trace_markdown()
        note = (
            str(
                payload.get("summary")
                or result_payload.get("conclusion")
                or (progress_eval or {}).get("reason")
                or trace_summary
                or ""
            ).strip()
            or "No durable main experiment result has been recorded yet."
        )
        title = f"Experiment · {run_id}"
        worktree_root = str(payload.get("worktree_root") or self.workspace_root).strip() or str(self.workspace_root)
        metrics_summary = payload.get("metrics_summary") or result_payload.get("metrics_summary") or {}
        key_files = self._dedupe_files(
            [
                self._file_entry(paths.get("run_md"), label="Run Markdown", description="Durable main experiment narrative."),
                self._file_entry(paths.get("result_json"), label="Result JSON", description="Structured main experiment result."),
                *[
                    self._file_entry(path, label=f"Changed File · {Path(str(path)).name}", description="Changed file captured in the main run.")
                    for path in (payload.get("files_changed") or [])
                ],
                *[
                    self._file_entry(path, label=f"Evidence · {Path(str(path)).name}", description="Evidence path attached to the run.")
                    for path in (payload.get("evidence_paths") or [])
                ],
            ]
        )
        return self._base_payload(
            title=title,
            note=note,
            status=str(payload.get("status") or self.stage_status or "ready").strip() or "ready",
            tags=[
                str(payload.get("verdict") or "").strip(),
                str(payload.get("status") or "").strip(),
                self.branch_name,
            ],
            overview=[
                _field("Run ID", run_id),
                _field("Verdict", payload.get("verdict") or result_payload.get("verdict") or "Not recorded"),
                _field("Status", payload.get("status") or result_payload.get("status") or "Not recorded"),
                _field("Branch", str(payload.get("branch") or self.branch_name)),
                _field("Idea ID", payload.get("idea_id") or result_payload.get("idea_id") or self.snapshot.get("active_idea_id")),
                _field("Baseline Ref", baseline_ref or "Not recorded"),
            ],
            key_facts=[
                _field("Hypothesis", result_payload.get("hypothesis") or "Not recorded"),
                _field("Setup", result_payload.get("setup") or "Not recorded"),
                _field("Execution", result_payload.get("execution") or "Not recorded"),
                _field("Results", result_payload.get("results_summary") or "Not recorded"),
                _field("Conclusion", result_payload.get("conclusion") or "Not recorded"),
                _field("Dataset Scope", ((result_payload.get("run_context") or {}) if isinstance(result_payload.get("run_context"), dict) else {}).get("dataset_scope") or "Not recorded"),
                _field("Metrics Summary", metrics_summary or "Not recorded"),
                _field("Delta vs Baseline", (progress_eval or {}).get("delta_vs_baseline") or "Not recorded"),
                _field("Breakthrough Level", (progress_eval or {}).get("breakthrough_level") or "Not recorded"),
                *_evaluation_summary_fields(evaluation_summary),
            ],
            key_files=key_files,
            history=self._artifact_history(experiment_items),
            details={
                "experiment": {
                    "run_id": run_id,
                    "branch": str(payload.get("branch") or self.branch_name),
                    "worktree_root": worktree_root,
                    "idea_id": payload.get("idea_id") or result_payload.get("idea_id"),
                    "baseline_ref": baseline_ref,
                    "metrics_summary": metrics_summary,
                    "progress_eval": progress_eval,
                    "evaluation_summary": evaluation_summary,
                    "run_path": self._relative_path_or_raw(paths.get("run_md")),
                    "run_markdown": run_markdown,
                    "result_json_path": self._relative_path_or_raw(paths.get("result_json")),
                    "result_payload": result_payload,
                    "trace_summary": trace_summary,
                    "trace_markdown": trace_markdown,
                    "trace_actions": self._recent_trace_actions(),
                },
                "latest_artifact": self._artifact_detail(latest, payload),
            },
        )

    def _analysis_manifests(self) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        root = self.quest_root / ".ds" / "analysis_campaigns"
        if not root.exists():
            return manifests
        for path in sorted(root.glob("*.json")):
            payload = read_json(path, {})
            if not isinstance(payload, dict) or not payload:
                continue
            payload["_manifest_path"] = str(path)
            manifests.append(payload)
        manifests.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or item.get("campaign_id") or ""))
        return manifests

    def _analysis_stage_items(self, campaign_id: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in self.artifacts:
            payload = self._payload(item)
            flow_type = str(payload.get("flow_type") or "").strip()
            if flow_type not in {"analysis_campaign", "analysis_slice"}:
                continue
            if campaign_id:
                if str(payload.get("campaign_id") or "").strip() == campaign_id:
                    items.append(item)
                continue
            if self._branch_matches(payload, allow_parent=True, include_unscoped=False):
                items.append(item)
        return items

    def _build_analysis(self) -> dict[str, Any]:
        manifests = self._analysis_manifests()
        selected_manifest = None
        active_campaign_id = str(self.snapshot.get("active_analysis_campaign_id") or "").strip()
        for manifest in reversed(manifests):
            parent_branch = str(manifest.get("parent_branch") or "").strip()
            campaign_id = str(manifest.get("campaign_id") or "").strip()
            if active_campaign_id and campaign_id == active_campaign_id:
                selected_manifest = manifest
                break
            if parent_branch == self.branch_name:
                selected_manifest = manifest
                break
        if selected_manifest is None and manifests:
            selected_manifest = manifests[-1]
        manifest = dict(selected_manifest or {})
        campaign_id = str(manifest.get("campaign_id") or active_campaign_id or "pending").strip() or "pending"
        stage_items = self._analysis_stage_items(campaign_id if campaign_id != "pending" else None)
        latest = stage_items[-1] if stage_items else None
        latest_payload = self._payload(latest or {})
        slices = [dict(item) for item in (manifest.get("slices") or []) if isinstance(item, dict)]
        manifest_todo_items = [dict(item) for item in (manifest.get("todo_items") or []) if isinstance(item, dict)]
        todo_items = manifest_todo_items or [
            {
                "todo_id": str(item.get("slice_id") or f"slice-{index}"),
                "slice_id": str(item.get("slice_id") or f"slice-{index}"),
                "title": item.get("title"),
                "status": item.get("status") or "pending",
                "research_question": item.get("research_question"),
                "experimental_design": item.get("experimental_design"),
                "completion_condition": item.get("must_not_simplify") or item.get("goal") or "Complete the planned analysis slice.",
                "why_now": item.get("why_now"),
                "success_criteria": item.get("success_criteria"),
                "abandonment_criteria": item.get("abandonment_criteria"),
                "reviewer_item_ids": item.get("reviewer_item_ids") or [],
                "manuscript_targets": item.get("manuscript_targets") or [],
            }
            for index, item in enumerate(slices, start=1)
        ]
        slice_rows = []
        for item in slices:
            run_artifact = next(
                (
                    artifact
                    for artifact in reversed(stage_items)
                    if str(self._payload(artifact).get("slice_id") or "").strip() == str(item.get("slice_id") or "").strip()
                ),
                None,
            )
            run_payload = self._payload(run_artifact or {})
            detail_payload = dict(run_payload.get("details") or {}) if isinstance(run_payload.get("details"), dict) else {}
            slice_rows.append(
                {
                    "slice_id": item.get("slice_id"),
                    "title": item.get("title"),
                    "run_kind": item.get("run_kind"),
                    "question": item.get("research_question") or detail_payload.get("question"),
                    "hypothesis": item.get("hypothesis"),
                    "why_now": item.get("why_now"),
                    "success_criteria": item.get("success_criteria"),
                    "abandonment_criteria": item.get("abandonment_criteria"),
                    "reviewer_item_ids": item.get("reviewer_item_ids") or [],
                    "manuscript_targets": item.get("manuscript_targets") or [],
                    "status": item.get("status") or run_payload.get("status") or "pending",
                    "metric_summary": run_payload.get("metrics_summary") or {},
                    "claim_impact": detail_payload.get("claim_impact"),
                    "reviewer_resolution": detail_payload.get("reviewer_resolution"),
                    "manuscript_update_hint": detail_payload.get("manuscript_update_hint"),
                    "next_recommendation": detail_payload.get("next_recommendation"),
                    "evaluation_summary": _evaluation_summary(
                        run_payload.get("evaluation_summary") or detail_payload.get("evaluation_summary")
                    ),
                    "deviations": detail_payload.get("deviations") or [],
                    "evidence_paths": detail_payload.get("evidence_paths") or [],
                    "plan_path": item.get("plan_path"),
                    "result_path": item.get("result_path"),
                    "mirror_path": item.get("mirror_path"),
                    "plan_markdown": self._markdown_body_for_path(item.get("plan_path")),
                    "result_markdown": self._markdown_body_for_path(item.get("result_path")),
                    "mirror_markdown": self._markdown_body_for_path(item.get("mirror_path")),
                }
            )
        title = f"Analysis · {campaign_id}"
        trace_summary = self._trace_summary()
        note = (
            str(latest_payload.get("summary") or manifest.get("goal") or trace_summary or "").strip()
            or "No durable analysis campaign has been created yet."
        )
        summary_path = (
            self.quest_root / "experiments" / "analysis-results" / campaign_id / "SUMMARY.md"
            if campaign_id != "pending"
            else None
        )
        summary_markdown = self._markdown_body_for_path(summary_path) if summary_path else None
        key_files = self._dedupe_files(
            [
                self._file_entry(manifest.get("_manifest_path"), label="Campaign Manifest", description="Structured analysis campaign manifest."),
                self._file_entry(manifest.get("charter_path"), label="Campaign Charter", description="Human-readable campaign charter."),
                self._file_entry(manifest.get("todo_manifest_path"), label="Todo Manifest", description="Outline-driven analysis todo manifest."),
                *[
                    self._file_entry(item.get("plan_path"), label=f"Slice Plan · {item.get('slice_id')}", description="Analysis slice plan.")
                    for item in slices
                ],
                *[
                    self._file_entry(item.get("result_path"), label=f"Slice Result · {item.get('slice_id')}", description="Slice durable result.")
                    for item in slices
                ],
                *[
                    self._file_entry(item.get("mirror_path"), label=f"Mirror Result · {item.get('slice_id')}", description="Merged parent-branch mirror result.")
                    for item in slices
                ],
            ]
        )
        completed_count = sum(1 for item in slices if str(item.get("status") or "") == "completed")
        return self._base_payload(
            title=title,
            note=note,
            status="completed" if slices and completed_count == len(slices) else "active" if slices else "pending",
            tags=[
                f"{completed_count}/{len(slices)} done" if slices else "",
                str(manifest.get("parent_branch") or self.branch_name),
            ],
            overview=[
                _field("Campaign ID", campaign_id),
                _field("Title", manifest.get("title") or "Not recorded"),
                _field("Goal", manifest.get("goal") or "Not recorded"),
                _field("Parent Run", manifest.get("parent_run_id") or "Not recorded"),
                _field("Parent Branch", manifest.get("parent_branch") or self.branch_name),
                _field("Selected Outline Ref", manifest.get("selected_outline_ref") or "Not recorded"),
            ],
            key_facts=[
                _field("Todo Count", len(todo_items)),
                _field("Completed Todo", completed_count),
                _field("Next Pending Slice", self.snapshot.get("next_pending_slice_id") or "None"),
                _field("Campaign Summary", latest_payload.get("summary") or "Not recorded"),
            ],
            key_files=key_files,
            history=self._artifact_history(stage_items),
            details={
                "analysis": {
                    "campaign_id": campaign_id,
                    "title": manifest.get("title"),
                    "goal": manifest.get("goal"),
                    "parent_run_id": manifest.get("parent_run_id"),
                    "parent_branch": manifest.get("parent_branch") or self.branch_name,
                    "campaign_origin": manifest.get("campaign_origin"),
                    "selected_outline_ref": manifest.get("selected_outline_ref"),
                    "todo_items": todo_items,
                    "slices": slice_rows,
                    "summary": latest_payload.get("summary"),
                    "manifest_path": manifest.get("_manifest_path"),
                    "charter_path": manifest.get("charter_path"),
                    "charter_markdown": self._markdown_body_for_path(manifest.get("charter_path")),
                    "todo_manifest_path": manifest.get("todo_manifest_path"),
                    "todo_manifest_markdown": self._markdown_body_for_path(manifest.get("todo_manifest_path")),
                    "summary_path": self._relative_path_or_raw(summary_path) if summary_path else None,
                    "summary_markdown": summary_markdown,
                    "manifest_payload": manifest,
                    "trace_summary": trace_summary,
                    "trace_markdown": self._trace_markdown(),
                    "trace_actions": self._recent_trace_actions(),
                },
                "latest_artifact": self._artifact_detail(latest, latest_payload),
            },
        )

    def _paper_files(self, *, compile_report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        bundle_manifest = self._paper_bundle_manifest()
        compile_report = compile_report if isinstance(compile_report, dict) else {}
        latex_root_rel = self._paper_latex_root(bundle_manifest, compile_report=compile_report)
        main_tex_rel = self._paper_main_tex(latex_root_rel, bundle_manifest=bundle_manifest, compile_report=compile_report)
        pdf_candidates = self._paper_pdf_candidates(bundle_manifest, main_tex_rel=main_tex_rel)
        paper_root = self._paper_root()
        open_source_root = self._open_source_root()
        candidates = sorted((paper_root / "outlines" / "candidates").glob("*.json"))
        files: list[dict[str, Any] | None] = [
            *[
                self._file_entry(path, label=f"Outline Candidate · {path.stem}", description="Paper outline candidate JSON.")
                for path in candidates
            ],
            self._file_entry(paper_root / "selected_outline.json", label="Selected Outline", description="Chosen paper outline."),
            self._file_entry(paper_root / "outline" / "manifest.json", label="Outline Manifest", description="Author-facing paper outline manifest."),
            self._file_entry(paper_root / "outline_selection.md", label="Outline Selection Note", description="Outline selection rationale."),
            self._file_entry(paper_root / "draft.md", label="Draft Markdown", description="Current paper draft."),
            self._file_entry(paper_root / "writing_plan.md", label="Writing Plan", description="Paper writing plan."),
            self._file_entry(paper_root / "references.bib", label="References", description="Bibliography file."),
            self._file_entry(paper_root / "claim_evidence_map.json", label="Claim-Evidence Map", description="Claim to evidence mapping."),
            self._file_entry(paper_root / "paper_line_state.json", label="Paper Line State", description="Derived summary state for the active paper line."),
            self._file_entry(paper_root / "baseline_inventory.json", label="Baseline Inventory", description="Canonical and supplementary baseline inventory for writing."),
            self._file_entry(paper_root / "build" / "compile_report.json", label="Compile Report", description="Paper build/compile report."),
            self._file_entry(paper_root / "paper_bundle_manifest.json", label="Bundle Manifest", description="Final paper bundle manifest."),
            self._file_entry(open_source_root / "manifest.json", label="Open Source Manifest", description="Open-source cleanup and release preparation manifest."),
            self._file_entry(open_source_root / "cleanup_plan.md", label="Open Source Cleanup Plan", description="Checklist for cleaning the paper branch into a public release."),
            self._file_entry(latex_root_rel, label="LaTeX Sources", description="LaTeX source folder.", expected_kind="directory"),
            self._file_entry(main_tex_rel, label="Main TeX", description="Primary TeX source file."),
        ]
        for pdf_rel in pdf_candidates[:3]:
            files.append(self._file_entry(pdf_rel, label=f"PDF · {Path(pdf_rel).name}", description="Paper PDF output."))
        return self._dedupe_files(files)

    def _paper_candidates(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for path in sorted((self._paper_root() / "outlines" / "candidates").glob("*.json")):
            payload = read_json(path, {})
            if not isinstance(payload, dict):
                payload = {}
            detailed = dict(payload.get("detailed_outline") or {}) if isinstance(payload.get("detailed_outline"), dict) else {}
            candidates.append(
                {
                    "candidate_id": path.stem,
                    "path": path.relative_to(self.quest_root).as_posix(),
                    "document_id": f"questpath::{path.relative_to(self.quest_root).as_posix()}",
                    "title": payload.get("title") or detailed.get("title") or path.stem,
                    "note": payload.get("note") or payload.get("summary"),
                    "review_result": payload.get("review_result"),
                    "status": payload.get("status") or "candidate",
                }
            )
        return candidates

    def _build_paper(self) -> dict[str, Any]:
        paper_items = [
            item
            for item in self.artifacts
            if (
                "paper" in str(self._payload(item).get("report_type") or "").strip()
                or "outline" in str(self._payload(item).get("report_type") or "").strip()
                or normalize_stage_key(self._payload(item).get("flow_type")) == "paper"
            )
            and self._branch_matches(self._payload(item), allow_parent=True)
        ]
        paper_root = self._paper_root()
        selected_outline_path = paper_root / "selected_outline.json"
        selected_outline = read_json(selected_outline_path, {}) if selected_outline_path.exists() else {}
        if not isinstance(selected_outline, dict):
            selected_outline = {}
        detailed = (
            dict(selected_outline.get("detailed_outline") or {})
            if isinstance(selected_outline.get("detailed_outline"), dict)
            else {}
        )
        candidates = self._paper_candidates()
        compile_report = read_json(paper_root / "build" / "compile_report.json", {})
        if not isinstance(compile_report, dict):
            compile_report = {}
        bundle_manifest = self._paper_bundle_manifest()
        latex_root_rel = self._paper_latex_root(bundle_manifest, compile_report=compile_report)
        main_tex_rel = self._paper_main_tex(latex_root_rel, bundle_manifest=bundle_manifest, compile_report=compile_report)
        references_bib = read_text(paper_root / "references.bib", "")
        references_count = sum(1 for line in references_bib.splitlines() if line.lstrip().startswith("@"))
        pdf_paths = self._paper_pdf_candidates(bundle_manifest, main_tex_rel=main_tex_rel)
        draft_rel = self._paper_relative_path(paper_root / "draft.md") or "paper/draft.md"
        writing_plan_rel = self._paper_relative_path(paper_root / "writing_plan.md") or "paper/writing_plan.md"
        claim_map_rel = self._paper_relative_path(paper_root / "claim_evidence_map.json") or "paper/claim_evidence_map.json"
        selected_title = str(
            detailed.get("title") or selected_outline.get("title") or bundle_manifest.get("title") or "Drafting"
        ).strip() or "Drafting"
        note = (
            str(selected_outline.get("note") or bundle_manifest.get("summary") or "").strip()
            or "No selected outline has been durably submitted yet."
        )
        return self._base_payload(
            title=f"Paper · {selected_title}",
            note=note,
            status="selected" if selected_outline else "pending",
            tags=[
                "outline-selected" if selected_outline else "outline-pending",
                "bundle-ready" if bundle_manifest else "",
            ],
            overview=[
                _field("Selected Outline", selected_title if selected_outline else "Not selected"),
                _field("Candidate Count", len(candidates)),
                _field("Draft Status", "present" if (paper_root / "draft.md").exists() else "missing"),
                _field("Bundle Status", "present" if bundle_manifest else "missing"),
            ],
            key_facts=[
                _field("Story", selected_outline.get("story") or "Not recorded"),
                _field("Ten Questions", selected_outline.get("ten_questions") or "Not recorded"),
                _field("Research Questions", detailed.get("research_questions") or "Not recorded"),
                _field("Experimental Designs", detailed.get("experimental_designs") or "Not recorded"),
                _field("Contributions", detailed.get("contributions") or "Not recorded"),
                _field("References Count", references_count),
                _field("PDF Path", pdf_paths[0] if pdf_paths else "Not recorded"),
                _field("LaTeX Root", latex_root_rel or "Not recorded"),
                _field("Main TeX", main_tex_rel or "Not recorded"),
            ],
            key_files=self._paper_files(compile_report=compile_report),
            history=self._artifact_history(paper_items),
            details={
                "paper": {
                    "outline_candidates": candidates,
                    "selected_outline": selected_outline,
                    "drafting": {
                        "writing_plan_path": writing_plan_rel,
                        "draft_path": draft_rel,
                        "references_count": references_count,
                        "claim_evidence_map_path": claim_map_rel,
                    },
                    "build": {
                        "compile_report": compile_report,
                        "bundle_manifest": bundle_manifest,
                        "pdf_paths": pdf_paths,
                        "pdf_path": pdf_paths[0] if pdf_paths else None,
                        "latex_root_path": latex_root_rel,
                        "main_tex_path": main_tex_rel,
                    },
                },
                "latest_artifact": self._artifact_detail(paper_items[-1] if paper_items else None, self._payload(paper_items[-1] if paper_items else {})),
            },
        )
