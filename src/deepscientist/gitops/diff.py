from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..artifact.metrics import extract_latest_metric
from ..shared import read_json, run_command, slugify
from .service import branch_exists, current_branch, head_commit


def list_branch_canvas(repo: Path, *, quest_id: str) -> dict[str, Any]:
    refs = _list_refs(repo)
    if not refs:
        default_ref = current_branch(repo)
        return {
            "quest_id": quest_id,
            "default_ref": default_ref,
            "current_ref": default_ref,
            "head": head_commit(repo),
            "nodes": [],
            "edges": [],
            "views": {
                "ideas": [],
                "analysis": [],
            },
        }

    default_ref = _default_ref(refs, quest_id=quest_id)
    branch_state = _collect_branch_state(repo)

    classifications: dict[str, dict[str, str]] = {}
    for ref in refs:
        classifications[ref["ref"]] = _classify_ref(ref["ref"], branch_state.get(ref["ref"], {}))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for ref_item in refs:
        ref_name = ref_item["ref"]
        state = branch_state.get(ref_name, {})
        classification = classifications[ref_name]
        parent_ref = _infer_parent_ref(
            ref_name,
            repo=repo,
            state=state,
            default_ref=default_ref,
            quest_id=quest_id,
            refs={item["ref"] for item in refs},
            classifications=classifications,
        )
        compare_base = parent_ref or default_ref
        ahead, behind = _ahead_behind(repo, compare_base, ref_name)
        node = {
            "ref": ref_name,
            "label": ref_name,
            "branch_kind": classification["branch_kind"],
            "tier": classification["tier"],
            "mode": classification["mode"],
            "parent_ref": parent_ref,
            "compare_base": compare_base,
            "current": ref_name == current_branch(repo),
            "head": ref_item["head"],
            "updated_at": ref_item["updated_at"],
            "subject": ref_item["subject"],
            "commit_count": _commit_count(repo, ref_name),
            "ahead": ahead,
            "behind": behind,
            "run_id": state.get("run_id"),
            "run_kind": state.get("run_kind"),
            "idea_id": state.get("idea_id"),
            "paper_line_id": state.get("paper_line_id"),
            "paper_line_branch": state.get("paper_line_branch"),
            "selected_outline_ref": state.get("selected_outline_ref"),
            "source_branch": state.get("source_branch"),
            "source_run_id": state.get("source_run_id"),
            "source_idea_id": state.get("source_idea_id"),
            "parent_branch_recorded": state.get("parent_branch"),
            "worktree_root": state.get("worktree_root"),
            "latest_metric": state.get("latest_metric"),
            "latest_summary": state.get("latest_summary"),
            "latest_result": state.get("latest_result"),
            "breakthrough": state.get("breakthrough", False),
            "breakthrough_level": state.get("breakthrough_level"),
            "recent_artifacts": state.get("recent_artifacts", []),
        }
        nodes.append(node)
        if parent_ref:
            edges.append(
                {
                    "from": parent_ref,
                    "to": ref_name,
                    "relation": "branch",
                    "tier": classification["tier"],
                    "mode": classification["mode"],
                }
            )

    return {
        "quest_id": quest_id,
        "default_ref": default_ref,
        "current_ref": current_branch(repo),
        "head": head_commit(repo),
        "nodes": nodes,
        "edges": edges,
        "views": {
            "ideas": [item["ref"] for item in nodes if item["tier"] == "major" or item["ref"] == default_ref],
            "analysis": [
                item["ref"]
                for item in nodes
                if item["ref"] == default_ref or item["tier"] == "major" or item["branch_kind"] == "analysis"
            ],
        },
    }


def list_commit_canvas(repo: Path, *, quest_id: str, limit: int = 80) -> dict[str, Any]:
    resolved_limit = max(1, min(int(limit), 200))
    head = head_commit(repo)
    current_ref = current_branch(repo)
    commits = _git_commit_canvas_log(repo, limit=resolved_limit)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_shas = {item["sha"] for item in commits if str(item.get("sha") or "").strip()}

    for commit in commits:
        sha = str(commit.get("sha") or "").strip()
        if not sha:
            continue
        detail = commit_detail(repo, sha=sha)
        parents = [str(item).strip() for item in (detail.get("parents") or []) if str(item).strip()]
        files = detail.get("files") or []
        changed_paths = [
            str(item.get("path") or "").strip()
            for item in files
            if str(item.get("path") or "").strip()
        ]
        node = {
            "sha": sha,
            "short_sha": str(detail.get("short_sha") or commit.get("short_sha") or sha[:7]).strip(),
            "parents": parents,
            "subject": str(detail.get("subject") or commit.get("subject") or "").strip() or sha[:7],
            "body_preview": _body_preview(str(detail.get("body") or "").strip()),
            "authored_at": str(detail.get("authored_at") or commit.get("authored_at") or "").strip() or None,
            "author_name": str(detail.get("author_name") or commit.get("author_name") or "").strip() or None,
            "branch_refs": _normalize_branch_refs(commit.get("decorations")),
            "current": bool(head and sha == head),
            "active_workspace": bool(head and sha == head),
            "changed_paths": changed_paths,
            "file_count": int(detail.get("file_count") or len(files)),
            "added": int(((detail.get("stats") or {}) if isinstance(detail.get("stats"), dict) else {}).get("added") or 0),
            "removed": int(((detail.get("stats") or {}) if isinstance(detail.get("stats"), dict) else {}).get("removed") or 0),
            "compare_base": parents[0] if parents else None,
            "compare_head": sha,
            "selection_type": "git_commit_node",
        }
        nodes.append(node)
        for parent in parents:
            if parent in seen_shas:
                edges.append(
                    {
                        "from": parent,
                        "to": sha,
                        "relation": "parent",
                    }
                )

    return {
        "quest_id": quest_id,
        "workspace_mode": "copilot",
        "head": head,
        "current_ref": current_ref,
        "nodes": nodes,
        "edges": edges,
    }


def compare_refs(repo: Path, *, base: str, head: str) -> dict[str, Any]:
    _require_ref(repo, base)
    _require_ref(repo, head)
    merge_base = _git_stdout(repo, ["merge-base", base, head]).strip() or None
    ahead, behind = _ahead_behind(repo, base, head)
    commits = _compare_commits(repo, base=base, head=head)
    files = _compare_files(repo, base=base, head=head)
    return {
        "ok": True,
        "base": base,
        "head": head,
        "merge_base": merge_base,
        "ahead": ahead,
        "behind": behind,
        "commit_count": len(commits),
        "file_count": len(files),
        "commits": commits,
        "files": files,
    }


def diff_file_between_refs(repo: Path, *, base: str, head: str, path: str) -> dict[str, Any]:
    _require_ref(repo, base)
    _require_ref(repo, head)
    safe_path = path.strip().lstrip("/")
    if not safe_path:
        return {
            "ok": False,
            "message": "Path is required.",
            "base": base,
            "head": head,
            "path": path,
            "lines": [],
        }

    compare = compare_refs(repo, base=base, head=head)
    file_meta = next((item for item in compare["files"] if item["path"] == safe_path), None)
    patch = _git_stdout(repo, ["diff", "--find-renames", "--unified=3", "--no-color", f"{base}...{head}", "--", safe_path])
    lines = _normalize_patch_lines(patch)
    return {
        "ok": True,
        "base": base,
        "head": head,
        "path": safe_path,
        "status": file_meta.get("status") if file_meta else "modified",
        "old_path": file_meta.get("old_path") if file_meta else None,
        "added": file_meta.get("added", 0) if file_meta else 0,
        "removed": file_meta.get("removed", 0) if file_meta else 0,
        "binary": file_meta.get("binary", False) if file_meta else False,
        "lines": lines,
        "truncated": False,
    }


def log_ref_history(repo: Path, *, ref: str, base: str | None = None, limit: int = 30) -> dict[str, Any]:
    _require_ref(repo, ref)
    normalized_base = (base or "").strip() or None
    if normalized_base and normalized_base != ref:
        _require_ref(repo, normalized_base)
    revspec = ref if not normalized_base or normalized_base == ref else f"{normalized_base}..{ref}"
    commits = _git_log(repo, revspec=revspec, limit=limit)
    return {
        "ok": True,
        "ref": ref,
        "base": normalized_base,
        "limit": limit,
        "commits": commits,
    }


def commit_detail(repo: Path, *, sha: str) -> dict[str, Any]:
    _require_ref(repo, sha)
    payload = _git_stdout(
        repo,
        [
            "show",
            "--quiet",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%h%x1f%P%x1f%ad%x1f%an%x1f%ae%x1f%s%x1f%b",
            sha,
        ],
    ).strip()
    full_sha, short_sha, parents_raw, authored_at, author_name, author_email, subject, body = (
        payload.split("\x1f") + ["", "", "", "", "", "", "", ""]
    )[:8]
    files = _commit_files(repo, sha=sha)
    return {
        "ok": True,
        "sha": full_sha.strip(),
        "short_sha": short_sha.strip(),
        "parents": [item for item in parents_raw.strip().split() if item],
        "authored_at": authored_at.strip(),
        "author_name": author_name.strip(),
        "author_email": author_email.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "file_count": len(files),
        "files": files,
        "stats": {
            "added": sum(int(item.get("added") or 0) for item in files),
            "removed": sum(int(item.get("removed") or 0) for item in files),
        },
    }


def diff_file_for_commit(repo: Path, *, sha: str, path: str) -> dict[str, Any]:
    _require_ref(repo, sha)
    safe_path = path.strip().lstrip("/")
    if not safe_path:
        return {
            "ok": False,
            "message": "Path is required.",
            "sha": sha,
            "path": path,
            "lines": [],
        }
    detail = commit_detail(repo, sha=sha)
    file_meta = next((item for item in detail["files"] if item["path"] == safe_path), None)
    patch = _git_stdout(repo, ["show", "--find-renames", "--unified=3", "--no-color", sha, "--", safe_path])
    lines = _normalize_patch_lines(patch)
    return {
        "ok": True,
        "sha": sha,
        "path": safe_path,
        "status": file_meta.get("status") if file_meta else "modified",
        "old_path": file_meta.get("old_path") if file_meta else None,
        "added": file_meta.get("added", 0) if file_meta else 0,
        "removed": file_meta.get("removed", 0) if file_meta else 0,
        "binary": file_meta.get("binary", False) if file_meta else False,
        "lines": lines,
        "truncated": False,
    }


def _list_refs(repo: Path) -> list[dict[str, Any]]:
    result = _git_stdout(
        repo,
        [
            "for-each-ref",
            "--sort=-committerdate",
            "--format=%(refname:short)%09%(objectname)%09%(committerdate:iso-strict)%09%(subject)",
            "refs/heads",
        ],
    )
    refs: list[dict[str, Any]] = []
    for line in result.splitlines():
        if not line.strip():
            continue
        ref, sha, updated_at, subject = (line.split("\t") + ["", "", "", ""])[:4]
        refs.append(
            {
                "ref": ref.strip(),
                "head": sha.strip(),
                "updated_at": updated_at.strip(),
                "subject": subject.strip(),
            }
        )
    return refs


def _collect_branch_state(repo: Path) -> dict[str, dict[str, Any]]:
    branch_state: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "recent_artifacts": [],
        }
    )
    artifact_paths: list[Path] = []
    artifact_roots = [repo / "artifacts"]
    worktrees_root = repo / ".ds" / "worktrees"
    if worktrees_root.exists():
        artifact_roots.extend(path / "artifacts" for path in sorted(worktrees_root.iterdir()) if path.is_dir())
    seen_paths: set[str] = set()
    for artifacts_root in artifact_roots:
        if not artifacts_root.exists():
            continue
        for path in sorted(artifacts_root.glob("*/*.json")):
            if not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen_paths:
                continue
            seen_paths.add(key)
            artifact_paths.append(path)
    for path in artifact_paths:
        record = read_json(path, {})
        if not isinstance(record, dict) or not record:
            continue
        branch_name = str(record.get("branch") or "").strip()
        if not branch_name:
            continue
        state = branch_state[branch_name]
        state.setdefault("branch", branch_name)
        artifact_sort_key = _artifact_record_sort_key(record, path)
        current_artifact_sort_key = state.get("_latest_artifact_sort_key")
        if current_artifact_sort_key is None or artifact_sort_key > current_artifact_sort_key:
            state["_latest_artifact_sort_key"] = artifact_sort_key
            state["updated_at"] = record.get("updated_at") or record.get("created_at") or state.get("updated_at")
        if record.get("idea_id"):
            state["idea_id"] = record.get("idea_id")
        if record.get("parent_branch"):
            state["parent_branch"] = record.get("parent_branch")
        if record.get("worktree_root"):
            state["worktree_root"] = record.get("worktree_root")
        resolved_run_result = _resolve_run_result_payload(repo, record)
        latest_metric = extract_latest_metric(resolved_run_result if record.get("kind") == "run" else record)
        if latest_metric is not None:
            state["latest_metric"] = latest_metric
        if record.get("kind") == "run":
            candidate_sort_key = _run_result_sort_key(record, resolved_run_result, path)
            current_sort_key = state.get("_latest_result_sort_key")
            if current_sort_key is None or candidate_sort_key > current_sort_key:
                state["_latest_result_sort_key"] = candidate_sort_key
                state["latest_result"] = resolved_run_result
                state["run_id"] = resolved_run_result.get("run_id") or state.get("run_id")
                state["run_kind"] = resolved_run_result.get("run_kind") or state.get("run_kind")
                progress_eval = (
                    resolved_run_result.get("progress_eval")
                    if isinstance(resolved_run_result.get("progress_eval"), dict)
                    else {}
                )
                state["breakthrough"] = bool(progress_eval.get("breakthrough"))
                state["breakthrough_level"] = progress_eval.get("breakthrough_level")
        if record.get("summary") or record.get("message") or record.get("reason"):
            current_summary_sort_key = state.get("_latest_summary_sort_key")
            if current_summary_sort_key is None or artifact_sort_key > current_summary_sort_key:
                state["_latest_summary_sort_key"] = artifact_sort_key
                state["latest_summary"] = record.get("summary") or record.get("message") or record.get("reason")
        state["recent_artifacts"].append(
            {
                "artifact_id": record.get("artifact_id"),
                "kind": record.get("kind"),
                "summary": record.get("summary") or record.get("message"),
                "reason": record.get("reason"),
                "updated_at": record.get("updated_at"),
                "status": record.get("status"),
                "_sort_key": artifact_sort_key,
            }
        )
        state["recent_artifacts"].sort(key=lambda item: item.get("_sort_key") or ("", 0, ""))
        state["recent_artifacts"] = state["recent_artifacts"][-4:]
    for state in branch_state.values():
        latest_result = state.get("latest_result")
        if isinstance(latest_result, dict):
            result_metric = extract_latest_metric(latest_result)
            if result_metric is not None:
                state["latest_metric"] = result_metric
        for item in state.get("recent_artifacts", []):
            if isinstance(item, dict):
                item.pop("_sort_key", None)
    for workspace_root in _canvas_workspace_roots(repo):
        state_path = workspace_root / "paper" / "paper_line_state.json"
        if not state_path.exists():
            continue
        payload = read_json(state_path, {})
        if not isinstance(payload, dict) or not payload:
            continue
        paper_branch = str(payload.get("paper_branch") or "").strip() or current_branch(workspace_root)
        if not paper_branch:
            continue
        state = branch_state[paper_branch]
        state.setdefault("branch", paper_branch)
        state["worktree_root"] = str(workspace_root)
        state["paper_line_id"] = str(payload.get("paper_line_id") or "").strip() or state.get("paper_line_id")
        state["paper_line_branch"] = paper_branch
        state["selected_outline_ref"] = str(payload.get("selected_outline_ref") or "").strip() or state.get("selected_outline_ref")
        state["source_branch"] = str(payload.get("source_branch") or "").strip() or state.get("source_branch")
        state["source_run_id"] = str(payload.get("source_run_id") or "").strip() or state.get("source_run_id")
        state["source_idea_id"] = str(payload.get("source_idea_id") or "").strip() or state.get("source_idea_id")
        state["updated_at"] = str(payload.get("updated_at") or state.get("updated_at") or "")
        if not state.get("parent_branch") and state.get("source_branch"):
            state["parent_branch"] = state.get("source_branch")
    for workspace_root in _canvas_workspace_roots(repo):
        paper_root = workspace_root / "paper"
        if not paper_root.exists():
            continue
        state_path = paper_root / "paper_line_state.json"
        if state_path.exists():
            continue
        selected_outline = read_json(paper_root / "selected_outline.json", {})
        bundle_manifest = read_json(paper_root / "paper_bundle_manifest.json", {})
        selected_outline = selected_outline if isinstance(selected_outline, dict) else {}
        bundle_manifest = bundle_manifest if isinstance(bundle_manifest, dict) else {}
        if not selected_outline and not bundle_manifest:
            continue
        paper_branch = str(bundle_manifest.get("paper_branch") or "").strip() or current_branch(workspace_root)
        if not paper_branch:
            continue
        selected_outline_ref = str(
            selected_outline.get("outline_id") or bundle_manifest.get("selected_outline_ref") or ""
        ).strip() or None
        source_run_id = str(bundle_manifest.get("source_run_id") or "").strip() or None
        state = branch_state[paper_branch]
        state.setdefault("branch", paper_branch)
        state["worktree_root"] = str(workspace_root)
        state["paper_line_id"] = state.get("paper_line_id") or slugify(
            "::".join([paper_branch or "paper", selected_outline_ref or "outline", source_run_id or "run"]),
            "paper-line",
        )
        state["paper_line_branch"] = paper_branch
        state["selected_outline_ref"] = selected_outline_ref or state.get("selected_outline_ref")
        state["source_branch"] = str(bundle_manifest.get("source_branch") or "").strip() or state.get("source_branch")
        state["source_run_id"] = source_run_id or state.get("source_run_id")
        state["source_idea_id"] = str(bundle_manifest.get("source_idea_id") or "").strip() or state.get("source_idea_id")
        if not state.get("parent_branch") and state.get("source_branch"):
            state["parent_branch"] = state.get("source_branch")
    campaigns_root = repo / ".ds" / "analysis_campaigns"
    if campaigns_root.exists():
        for path in sorted(campaigns_root.glob("*.json")):
            manifest = read_json(path, {})
            if not isinstance(manifest, dict) or not manifest:
                continue
            campaign_id = str(manifest.get("campaign_id") or path.stem).strip() or path.stem
            paper_line_id = str(manifest.get("paper_line_id") or "").strip() or None
            paper_line_branch = str(manifest.get("paper_line_branch") or "").strip() or None
            analysis_parent_branch = str(manifest.get("parent_branch") or "").strip() or None
            selected_outline_ref = str(manifest.get("selected_outline_ref") or "").strip() or None
            source_idea_id = str(manifest.get("active_idea_id") or "").strip() or None
            if not paper_line_branch:
                paper_line_branch = _infer_paper_line_branch_for_campaign(
                    manifest,
                    branch_state=branch_state,
                )
            for item in manifest.get("slices") or []:
                if not isinstance(item, dict):
                    continue
                branch_name = str(item.get("branch") or "").strip()
                if not branch_name:
                    continue
                state = branch_state[branch_name]
                state.setdefault("branch", branch_name)
                state["campaign_id"] = campaign_id
                state["paper_line_id"] = paper_line_id or state.get("paper_line_id")
                state["paper_line_branch"] = paper_line_branch or state.get("paper_line_branch")
                state["analysis_parent_branch"] = analysis_parent_branch or state.get("analysis_parent_branch")
                state["selected_outline_ref"] = selected_outline_ref or state.get("selected_outline_ref")
                state["source_idea_id"] = source_idea_id or state.get("source_idea_id")
                if item.get("worktree_root"):
                    state["worktree_root"] = item.get("worktree_root")
    return branch_state


def _canvas_workspace_roots(repo: Path) -> list[Path]:
    roots: list[Path] = [repo]
    research_state = read_json(repo / ".ds" / "research_state.json", {})
    preferred_raw = str((research_state or {}).get("research_head_worktree_root") or "").strip()
    if preferred_raw:
        preferred = Path(preferred_raw)
        if preferred.exists():
            roots.append(preferred)
    worktrees_root = repo / ".ds" / "worktrees"
    if worktrees_root.exists():
        roots.extend(path for path in sorted(worktrees_root.iterdir()) if path.is_dir())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _infer_paper_line_branch_for_campaign(
    manifest: dict[str, Any],
    *,
    branch_state: dict[str, dict[str, Any]],
) -> str | None:
    selected_outline_ref = str(manifest.get("selected_outline_ref") or "").strip() or None
    source_idea_id = str(manifest.get("active_idea_id") or "").strip() or None
    source_run_id = str(manifest.get("parent_run_id") or "").strip() or None
    source_branch = str(manifest.get("parent_branch") or "").strip() or None
    ranked: list[tuple[int, str]] = []
    for branch_name, state in branch_state.items():
        if not branch_name.startswith("paper/"):
            continue
        score = 0
        candidate_outline = str(state.get("selected_outline_ref") or "").strip() or None
        candidate_idea = str(state.get("source_idea_id") or "").strip() or None
        candidate_run = str(state.get("source_run_id") or "").strip() or None
        candidate_branch = str(state.get("source_branch") or "").strip() or None
        if selected_outline_ref:
            if candidate_outline != selected_outline_ref:
                continue
            score += 2
        if source_idea_id and candidate_idea == source_idea_id:
            score += 4
        if source_run_id and candidate_run == source_run_id:
            score += 3
        if source_branch and candidate_branch == source_branch:
            score += 2
        if score > 0:
            ranked.append((score, branch_name))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _resolve_run_result_payload(repo: Path, record: dict[str, Any]) -> dict[str, Any]:
    details = dict(record.get("details") or {}) if isinstance(record.get("details"), dict) else {}
    paths = dict(record.get("paths") or {}) if isinstance(record.get("paths"), dict) else {}
    result_payload: dict[str, Any] = {}
    result_json_path = _resolve_result_json_path(repo, paths.get("result_json"))
    if result_json_path and result_json_path.exists():
        loaded = read_json(result_json_path, {})
        if isinstance(loaded, dict):
            result_payload = loaded

    evaluation_summary = (
        record.get("evaluation_summary")
        or details.get("evaluation_summary")
        or result_payload.get("evaluation_summary")
        or {}
    )
    progress_eval = record.get("progress_eval")
    if not isinstance(progress_eval, dict):
        progress_eval = result_payload.get("progress_eval") if isinstance(result_payload.get("progress_eval"), dict) else {}

    return {
        "run_id": record.get("run_id") or result_payload.get("run_id"),
        "run_kind": record.get("run_kind") or result_payload.get("run_kind"),
        "status": record.get("status") or result_payload.get("status"),
        "summary": record.get("summary") or record.get("reason") or result_payload.get("summary"),
        "verdict": record.get("verdict") or result_payload.get("verdict"),
        "paths": paths or (result_payload.get("paths") if isinstance(result_payload.get("paths"), dict) else {}) or {},
        "details": details,
        "metrics_summary": record.get("metrics_summary") or result_payload.get("metrics_summary") or {},
        "metric_rows": record.get("metric_rows") or result_payload.get("metric_rows") or [],
        "metric_contract": record.get("metric_contract") or result_payload.get("metric_contract") or {},
        "baseline_ref": record.get("baseline_ref") or result_payload.get("baseline_ref") or {},
        "baseline_comparisons": record.get("baseline_comparisons") or result_payload.get("baseline_comparisons") or {},
        "progress_eval": progress_eval or {},
        "evaluation_summary": evaluation_summary or {},
        "files_changed": record.get("files_changed") or result_payload.get("files_changed") or [],
        "evidence_paths": record.get("evidence_paths") or result_payload.get("evidence_paths") or [],
        "updated_at": record.get("updated_at") or result_payload.get("updated_at"),
    }


def _resolve_result_json_path(repo: Path, raw_path: object) -> Path | None:
    normalized = str(raw_path or "").strip()
    if not normalized:
        return None
    candidate = Path(normalized).expanduser()
    if candidate.is_absolute():
        return candidate
    return repo / candidate


def _artifact_record_sort_key(record: dict[str, Any], path: Path) -> tuple[str, int, str]:
    updated_at = str(record.get("updated_at") or record.get("created_at") or "").strip()
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    return (updated_at, mtime_ns, str(path))


def _run_result_sort_key(record: dict[str, Any], payload: dict[str, Any], path: Path) -> tuple[int, str, int, str]:
    quality = 0
    if extract_latest_metric(payload):
        quality += 8
    if payload.get("baseline_comparisons"):
        quality += 4
    if payload.get("progress_eval"):
        quality += 4
    if payload.get("metrics_summary"):
        quality += 3
    if payload.get("metric_rows"):
        quality += 3
    if payload.get("verdict"):
        quality += 2
    paths = payload.get("paths") if isinstance(payload.get("paths"), dict) else {}
    if paths.get("result_json"):
        quality += 2
    if paths.get("run_md"):
        quality += 1
    updated_at = str(payload.get("updated_at") or record.get("updated_at") or record.get("created_at") or "")
    _, mtime_ns, path_str = _artifact_record_sort_key(record, path)
    return (quality, updated_at, mtime_ns, path_str)


def _classify_ref(ref: str, state: dict[str, Any]) -> dict[str, str]:
    run_id = str(state.get("run_id") or "")
    run_kind = str(state.get("run_kind") or "")
    if ref in {"main", "master"} or ref.startswith("quest/"):
        return {"branch_kind": "quest", "tier": "major", "mode": "ideas"}
    if ref.startswith("idea/"):
        return {"branch_kind": "idea", "tier": "major", "mode": "ideas"}
    if ref.startswith("paper/"):
        return {"branch_kind": "paper", "tier": "major", "mode": "ideas"}
    if ref.startswith("analysis/") or run_id.startswith("analysis") or run_kind == "analysis-campaign":
        return {"branch_kind": "analysis", "tier": "minor", "mode": "analysis"}
    return {"branch_kind": "implementation", "tier": "major", "mode": "ideas"}


def _infer_parent_ref(
    ref: str,
    *,
    repo: Path,
    state: dict[str, Any],
    default_ref: str,
    quest_id: str,
    refs: set[str],
    classifications: dict[str, dict[str, str]],
) -> str | None:
    if ref == default_ref:
        return None
    if classifications[ref]["branch_kind"] == "analysis":
        paper_line_branch = str(state.get("paper_line_branch") or "").strip()
        if paper_line_branch and paper_line_branch in refs and paper_line_branch != ref:
            return paper_line_branch
    parent_branch = str(state.get("parent_branch") or "").strip()
    if parent_branch and parent_branch in refs and parent_branch != ref:
        return parent_branch
    if classifications[ref]["branch_kind"] == "paper":
        source_branch = str(state.get("source_branch") or "").strip()
        if source_branch and source_branch in refs and source_branch != ref:
            return source_branch
    if ref.startswith("idea/"):
        return default_ref
    if state.get("idea_id"):
        candidate = f"idea/{quest_id}-{state['idea_id']}"
        if candidate in refs:
            return candidate
    if classifications[ref]["branch_kind"] == "analysis":
        analysis_parent_branch = str(state.get("analysis_parent_branch") or "").strip()
        if analysis_parent_branch and analysis_parent_branch in refs and analysis_parent_branch != ref:
            return analysis_parent_branch
        major_refs = [
            candidate
            for candidate, meta in classifications.items()
            if candidate != ref and meta["tier"] == "major" and candidate in refs
        ]
        best_parent = _best_merge_base_parent(ref, candidates=major_refs, repo=repo)
        if best_parent:
            return best_parent
    return default_ref


def _best_merge_base_parent(ref: str, *, candidates: list[str], repo: Path) -> str | None:
    best_parent = None
    best_score = None
    for candidate in candidates:
        if not branch_exists(repo, candidate):
            continue
        base = _git_stdout(repo, ["merge-base", candidate, ref]).strip()
        if not base:
            continue
        score = _git_stdout(repo, ["rev-list", "--count", f"{base}..{ref}"]).strip() or "0"
        try:
            numeric_score = int(score)
        except ValueError:
            numeric_score = 0
        if best_score is None or numeric_score < best_score:
            best_score = numeric_score
            best_parent = candidate
    return best_parent


def _default_ref(refs: list[dict[str, Any]], *, quest_id: str) -> str:
    ref_names = {item["ref"] for item in refs}
    quest_ref = f"quest/{quest_id}"
    if quest_ref in ref_names:
        return quest_ref
    if "main" in ref_names:
        return "main"
    return refs[0]["ref"]


def _compare_commits(repo: Path, *, base: str, head: str) -> list[dict[str, Any]]:
    return _git_log(repo, revspec=f"{base}..{head}")


def _compare_files(repo: Path, *, base: str, head: str) -> list[dict[str, Any]]:
    status_lines = _git_stdout(repo, ["diff", "--find-renames", "--name-status", f"{base}...{head}"]).splitlines()
    numstat_lines = _git_stdout(repo, ["diff", "--find-renames", "--numstat", f"{base}...{head}"]).splitlines()
    return _files_from_status_numstat(status_lines, numstat_lines)


def _commit_files(repo: Path, *, sha: str) -> list[dict[str, Any]]:
    status_lines = _git_stdout(repo, ["show", "--find-renames", "--name-status", "--format=", sha]).splitlines()
    numstat_lines = _git_stdout(repo, ["show", "--find-renames", "--numstat", "--format=", sha]).splitlines()
    return _files_from_status_numstat(status_lines, numstat_lines)


def _files_from_status_numstat(status_lines: list[str], numstat_lines: list[str]) -> list[dict[str, Any]]:
    
    by_path: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for line in status_lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0]
        status = _status_label(code)
        if code.startswith("R") and len(parts) >= 3:
            old_path, new_path = parts[1], parts[2]
            path = new_path
            by_path[path] = {
                "path": path,
                "old_path": old_path,
                "status": status,
            }
        elif len(parts) >= 2:
            path = parts[1]
            by_path[path] = {
                "path": path,
                "status": status,
            }
        else:
            continue
        order.append(path)

    for line in numstat_lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, removed_raw = parts[0], parts[1]
        path = parts[-1]
        item = by_path.setdefault(path, {"path": path, "status": "modified"})
        item["binary"] = added_raw == "-" or removed_raw == "-"
        item["added"] = 0 if item["binary"] else int(added_raw or "0")
        item["removed"] = 0 if item["binary"] else int(removed_raw or "0")

    return [by_path[path] for path in order if path in by_path]


def _git_log(repo: Path, *, revspec: str, limit: int = 30) -> list[dict[str, Any]]:
    result = _git_stdout(
        repo,
        [
            "log",
            "--date=iso-strict",
            f"-n{limit}",
            "--pretty=format:%H%x1f%h%x1f%ad%x1f%an%x1f%s",
            revspec,
        ],
    )
    commits: list[dict[str, Any]] = []
    for line in result.splitlines():
        if not line.strip():
            continue
        sha, short_sha, authored_at, author_name, subject = (line.split("\x1f") + ["", "", "", "", ""])[:5]
        commits.append(
            {
                "sha": sha.strip(),
                "short_sha": short_sha.strip(),
                "authored_at": authored_at.strip(),
                "author_name": author_name.strip(),
                "subject": subject.strip(),
            }
        )
    return commits


def _git_commit_canvas_log(repo: Path, *, limit: int = 80) -> list[dict[str, Any]]:
    result = _git_stdout(
        repo,
        [
            "log",
            "--all",
            "--topo-order",
            "--date=iso-strict",
            f"-n{limit}",
            "--decorate=short",
            "--pretty=format:%H%x1f%h%x1f%P%x1f%ad%x1f%an%x1f%s%x1f%b%x1f%D",
        ],
    )
    commits: list[dict[str, Any]] = []
    for line in result.splitlines():
        if not line.strip():
            continue
        sha, short_sha, parents_raw, authored_at, author_name, subject, body, decorations = (
            line.split("\x1f") + ["", "", "", "", "", "", "", ""]
        )[:8]
        commits.append(
            {
                "sha": sha.strip(),
                "short_sha": short_sha.strip(),
                "parents": [item for item in parents_raw.strip().split() if item],
                "authored_at": authored_at.strip(),
                "author_name": author_name.strip(),
                "subject": subject.strip(),
                "body": body.strip(),
                "decorations": decorations.strip(),
            }
        )
    return commits


def _normalize_branch_refs(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    refs: list[str] = []
    for part in text.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        if cleaned.startswith("HEAD -> "):
            cleaned = cleaned[len("HEAD -> ") :].strip()
        if cleaned.startswith("tag: "):
            continue
        if cleaned.startswith("origin/"):
            continue
        if cleaned == "HEAD":
            continue
        refs.append(cleaned)
    return refs


def _body_preview(body: str, *, max_lines: int = 3, max_chars: int = 220) -> str | None:
    if not body:
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return None
    preview = " ".join(lines[:max_lines]).strip()
    if len(preview) > max_chars:
        preview = preview[: max_chars - 1].rstrip() + "…"
    return preview or None


def _normalize_patch_lines(patch: str) -> list[str]:
    lines = [line.rstrip("\n") for line in patch.splitlines()]
    if not lines:
        return []
    first_hunk = next((index for index, line in enumerate(lines) if line.startswith("@@")), None)
    if first_hunk is None:
        return lines
    prefix = [line for line in lines[:first_hunk] if line.startswith("---") or line.startswith("+++")]
    return prefix + lines[first_hunk:]


def _status_label(code: str) -> str:
    if code.startswith("A"):
        return "added"
    if code.startswith("D"):
        return "deleted"
    if code.startswith("R"):
        return "renamed"
    if code.startswith("C"):
        return "copied"
    return "modified"


def _ahead_behind(repo: Path, base: str, head: str) -> tuple[int, int]:
    if not base or not head:
        return 0, 0
    result = _git_stdout(repo, ["rev-list", "--left-right", "--count", f"{base}...{head}"]).strip()
    if not result:
        return 0, 0
    left, right = (result.split() + ["0", "0"])[:2]
    try:
        behind = int(left)
    except ValueError:
        behind = 0
    try:
        ahead = int(right)
    except ValueError:
        ahead = 0
    return ahead, behind


def _commit_count(repo: Path, ref: str) -> int:
    result = _git_stdout(repo, ["rev-list", "--count", ref]).strip()
    try:
        return int(result)
    except ValueError:
        return 0


def _require_ref(repo: Path, ref: str) -> None:
    if not branch_exists(repo, ref):
        result = run_command(["git", "rev-parse", "--verify", ref], cwd=repo, check=False)
        if result.returncode != 0:
            raise ValueError(f"Unknown git ref: {ref}")


def _git_stdout(repo: Path, args: list[str]) -> str:
    result = run_command(["git", *args], cwd=repo, check=False)
    return result.stdout
