# Distill Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten distill routing strength, add a `task:` tag convention plus a `keywords` frontmatter field for cross-quest knowledge recall, expose `memory.list_knowledge_summaries`, rewrite the distill skill's neighbor-discovery flow, and add an opt-in `recall_priors` startup contract that injects a prompt cue telling stage skills to scan global knowledge before generating new ideas/baselines/experiments.

**Architecture:** Pure additive change. Phase 2's finalize gate stays; we only sharpen its routing payload. Knowledge cards get two new conventions (a required `task:` tag, an indexable `keywords:` block) that the distill skill enforces — no schema validation. The new MCP tool returns *all* global knowledge cards as ~30 KB compact rows so the LLM (not the service) judges neighbors. `recall_priors` mirrors the existing `experience_distill` opt-in (form field, bool coercion, UI toggle, prompt-builder injection).

**Tech Stack:** Python 3.11 (`src/deepscientist/`), TypeScript/React (`src/ui/`), Markdown skill contracts (`src/skills/distill/`), pytest test suite.

**Reference spec:** [docs/superpowers/specs/2026-04-25-distill-routing-strength-and-keyword-recall.md](../specs/2026-04-25-distill-routing-strength-and-keyword-recall.md)

---

## File structure overview

| File | Responsibility | Tasks touching |
|---|---|---|
| `src/deepscientist/artifact/experience_distill.py` | Finalize-gate routing payload + recall_priors helpers | 1, 5 |
| `src/deepscientist/artifact/schemas.py` | distill_review.neighbor_decisions validation | 2 |
| `src/deepscientist/memory/service.py` | `list_knowledge_summaries` method on MemoryService | 3 |
| `src/deepscientist/mcp/server.py` | MCP tool registration + start_setup form field | 4, 5 |
| `src/deepscientist/runners/codex.py` | Codex tool-approval allowlist | 4 |
| `src/deepscientist/prompts/builder.py` | recall_priors_rule prompt cue injection | 7 |
| `src/skills/distill/SKILL.md` | Skill contract: task tag, keywords, summary-scan flow, neighbor_decisions guidance | 8 |
| `src/ui/src/lib/startResearch.ts` | Form type + defaults + coercion | 6 |
| `src/ui/src/components/projects/CreateProjectDialog.tsx` | recall_priors toggle UI + translations | 6 |
| `tests/test_experience_distill_finalize_gate.py` | Routing strength tests | 1 |
| `tests/test_artifact_schemas_distill_review.py` | neighbor_decisions schema tests | 2 |
| `tests/test_memory_and_artifact.py` | list_knowledge_summaries service tests | 3 |
| `tests/test_mcp_servers.py` | list_knowledge_summaries MCP tool tests | 4 |
| `tests/test_experience_distill_config.py` | recall_priors helper tests + form-field coercion | 5 |
| `tests/test_prompt_builder.py` | recall_priors_rule injection tests | 7 |
| `tests/test_experience_distill_integration.py` | End-to-end routing+recall test | 10 |
| `~/DeepScientist/memory/knowledge/potential-based-reward-shaping-...md` | Backfill: task tag + keywords | 9 |
| `~/DeepScientist/memory/knowledge/symbolic-features-enable-...md` | Backfill: task tag + keywords | 9 |

Total: 10 tasks.

---

### Task 1: Tighten finalize gate routing strength

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py:440-512`
- Test: `tests/test_experience_distill_finalize_gate.py`

The fire branch currently appends a fallback `alternative_routes` entry pointing back to write/finalize and uses descriptive action wording. We drop the append and switch to imperative wording. The clear branch's fallback-filtering loop becomes obsolete.

- [ ] **Step 1.1: Write the failing test for fire branch (no fallback append)**

Add to `tests/test_experience_distill_finalize_gate.py`:

```python
def test_finalize_gate_fire_does_not_append_write_fallback(tmp_path: Path) -> None:
    """When the gate fires, alternative_routes must NOT contain a write/finalize fallback entry."""
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  experience_distill: on\n", encoding="utf-8"
    )
    artifacts_dir = quest_root / "artifacts"
    artifacts_dir.mkdir()
    # Seed one completed run that has not been distilled.
    index = artifacts_dir / "_index.jsonl"
    run_path = artifacts_dir / "runs" / "run-x.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps({
            "kind": "run", "run_kind": "main_experiment",
            "status": "completed", "artifact_id": "run-x",
        }),
        encoding="utf-8",
    )
    index.write_text(
        json.dumps({"kind": "run", "path": str(run_path)}) + "\n", encoding="utf-8"
    )

    decision = {"kind": "decision", "action": "write", "artifact_id": "decision-1"}
    inbound = {"recommended_skill": "write", "recommended_action": "Draft the paper."}

    out = maybe_inject_distill_finalize_gate(quest_root, artifacts_dir, decision, inbound)

    assert out is not None
    assert out["recommended_skill"] == "distill"
    assert out["gate"] == "finalize"
    routes = out.get("alternative_routes") or []
    fallback_entries = [
        r for r in routes
        if isinstance(r, dict) and r.get("recommended_skill") == "write"
    ]
    assert fallback_entries == [], (
        f"Expected no write-fallback in alternative_routes, got: {fallback_entries}"
    )


def test_finalize_gate_fire_uses_imperative_action_wording(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  experience_distill: on\n", encoding="utf-8"
    )
    artifacts_dir = quest_root / "artifacts"
    artifacts_dir.mkdir()
    run_path = artifacts_dir / "runs" / "run-x.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps({
            "kind": "run", "run_kind": "main_experiment",
            "status": "completed", "artifact_id": "run-x",
        }),
        encoding="utf-8",
    )
    (artifacts_dir / "_index.jsonl").write_text(
        json.dumps({"kind": "run", "path": str(run_path)}) + "\n", encoding="utf-8"
    )

    decision = {"kind": "decision", "action": "write", "artifact_id": "decision-1"}
    out = maybe_inject_distill_finalize_gate(quest_root, artifacts_dir, decision, None)

    assert out is not None
    action = str(out["recommended_action"])
    assert "Distill required" in action
    assert "distill_review" in action
    assert "paused" in action
```

Add `import json` and `from pathlib import Path` at the top of the file if not present, plus `from deepscientist.artifact.experience_distill import maybe_inject_distill_finalize_gate`.

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_finalize_gate.py::test_finalize_gate_fire_does_not_append_write_fallback tests/test_experience_distill_finalize_gate.py::test_finalize_gate_fire_uses_imperative_action_wording -v
```

Expected: both FAIL — first assert fails because current code appends a fallback entry; second fails because current `recommended_action` is the soft phrase "Review undistilled completed runs ... before resuming write/finalize".

- [ ] **Step 1.3: Implement the fire-branch change**

Edit `src/deepscientist/artifact/experience_distill.py`. Replace lines 484-512 (the fire branch of `maybe_inject_distill_finalize_gate`) with:

```python
    base = dict(guidance_vm) if isinstance(guidance_vm, dict) else {}
    previous_skill = str(base.get("recommended_skill") or "").strip() or None
    previous_action = str(base.get("recommended_action") or "").strip() or None
    routes = list(base.get("alternative_routes") or []) if isinstance(base.get("alternative_routes"), list) else []
    return {
        **base,
        "recommended_skill": "distill",
        "recommended_action": (
            "Distill required before write/finalize: scan completed runs, "
            "write 0..N knowledge cards, record one distill_review. "
            "The original write/finalize route is paused until distill_review lands."
        ),
        "previous_recommended_skill": previous_skill,
        "previous_recommended_action": previous_action,
        "alternative_routes": routes,
        "experience_distill": True,
        "gate": "finalize",
        "pending_distill_count": gate["pending_distill_count"],
        "pending_distill_ids": gate["pending_distill_ids"],
        "cursor_run_created_at": gate.get("cursor_run_created_at"),
        "source_artifact_id": str(record.get("artifact_id") or ""),
    }
```

(The `if previous_skill and previous_skill != "distill": routes.append(...)` block at lines 488-495 is removed entirely.)

- [ ] **Step 1.4: Simplify the clear branch**

The clear branch (lines 462-482) currently filters `alternative_routes` for `_FINALIZE_GATE_FALLBACK_REASON` entries. Since the fire branch no longer appends those, the filter loop becomes unreachable. Replace lines 462-483 with:

```python
        if isinstance(guidance_vm, dict) and guidance_vm.get("gate") == "finalize":
            base = dict(guidance_vm)
            previous_skill = str(base.get("previous_recommended_skill") or "").strip() or None
            previous_action = str(base.get("previous_recommended_action") or "").strip() or None
            cleared: dict[str, Any] = {
                k: v for k, v in base.items()
                if k not in _FINALIZE_GATE_INJECTED_KEYS
            }
            if previous_skill:
                cleared["recommended_skill"] = previous_skill
            if previous_action:
                cleared["recommended_action"] = previous_action
            return cleared
        return guidance_vm
```

Also delete the now-unused module-level constant at line 440:

```python
_FINALIZE_GATE_FALLBACK_REASON: str = "Original next step before the finalize gate fired."
```

- [ ] **Step 1.5: Run new tests + full file's existing tests to verify nothing regressed**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_finalize_gate.py -v
```

Expected: all tests pass. If existing tests reference `_FINALIZE_GATE_FALLBACK_REASON` or assert a fallback entry in `alternative_routes`, update them to match the new contract — those existing assertions encoded the old behaviour we are intentionally removing.

- [ ] **Step 1.6: Validate Python syntax across the package**

```bash
cd /home/ds/DeepScientist-distill
python3 -m compileall -q src/deepscientist
```

Expected: no output (success).

- [ ] **Step 1.7: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/deepscientist/artifact/experience_distill.py tests/test_experience_distill_finalize_gate.py
git commit -m "fix: tighten distill finalize gate to drop write/finalize fallback route"
```

---

### Task 2: Add `neighbor_decisions` field to distill_review schema

**Files:**
- Modify: `src/deepscientist/artifact/schemas.py:36-37, 55-90`
- Test: `tests/test_artifact_schemas_distill_review.py`

- [ ] **Step 2.1: Write failing tests**

Add to `tests/test_artifact_schemas_distill_review.py`:

```python
def test_distill_review_neighbor_decisions_omitted_is_valid() -> None:
    payload = {
        "kind": "distill_review",
        "reviewed_run_ids": ["run-1"],
        "cards_written": [],
        "reason_if_empty": "smoke run",
    }
    assert validate_artifact_payload(payload) == []


def test_distill_review_neighbor_decisions_empty_list_is_valid() -> None:
    payload = {
        "kind": "distill_review",
        "reviewed_run_ids": ["run-1"],
        "cards_written": [],
        "reason_if_empty": "smoke run",
        "neighbor_decisions": [],
    }
    assert validate_artifact_payload(payload) == []


def test_distill_review_neighbor_decisions_well_formed_is_valid() -> None:
    payload = {
        "kind": "distill_review",
        "reviewed_run_ids": ["run-1"],
        "cards_written": [
            {
                "card_id": "knowledge-abc",
                "scope": "global",
                "action": "patch",
                "target_run_id": "run-1",
            }
        ],
        "neighbor_decisions": [
            {
                "candidate_card_id": "knowledge-xyz",
                "decision": "neighbor_but_separate",
                "reason": "different mechanism",
                "target_run_id": "run-1",
            }
        ],
    }
    assert validate_artifact_payload(payload) == []


def test_distill_review_neighbor_decisions_unknown_decision_rejected() -> None:
    payload = {
        "kind": "distill_review",
        "reviewed_run_ids": ["run-1"],
        "cards_written": [],
        "reason_if_empty": "skipped",
        "neighbor_decisions": [
            {
                "candidate_card_id": "knowledge-xyz",
                "decision": "merge",  # not in the allowed set
                "reason": "test",
                "target_run_id": "run-1",
            }
        ],
    }
    errors = validate_artifact_payload(payload)
    assert any("decision" in e.lower() for e in errors), errors


def test_distill_review_neighbor_decisions_target_run_id_must_be_in_reviewed() -> None:
    payload = {
        "kind": "distill_review",
        "reviewed_run_ids": ["run-1"],
        "cards_written": [],
        "reason_if_empty": "skipped",
        "neighbor_decisions": [
            {
                "candidate_card_id": "knowledge-xyz",
                "decision": "patch",
                "reason": "test",
                "target_run_id": "run-MISSING",
            }
        ],
    }
    errors = validate_artifact_payload(payload)
    assert any("target_run_id" in e for e in errors), errors


def test_distill_review_neighbor_decisions_missing_required_key_rejected() -> None:
    payload = {
        "kind": "distill_review",
        "reviewed_run_ids": ["run-1"],
        "cards_written": [],
        "reason_if_empty": "skipped",
        "neighbor_decisions": [
            {"candidate_card_id": "knowledge-xyz", "decision": "patch"}
        ],
    }
    errors = validate_artifact_payload(payload)
    assert any("neighbor_decisions" in e for e in errors), errors
```

(`from deepscientist.artifact.schemas import validate_artifact_payload` should already be at the top.)

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_artifact_schemas_distill_review.py -v -k neighbor_decisions
```

Expected: most pass (no validation = field ignored), but `unknown_decision_rejected`, `target_run_id_must_be_in_reviewed`, and `missing_required_key_rejected` FAIL because no validation exists yet.

- [ ] **Step 2.3: Implement the validation**

Edit `src/deepscientist/artifact/schemas.py`. After line 37 (`DISTILL_CARD_SCOPES = {"global", "quest"}`), add:

```python
DISTILL_NEIGHBOR_DECISIONS = {"patch", "new", "neighbor_but_separate"}
```

Inside the `if kind == "distill_review":` block, after the existing `cards_written` validation loop (after line 90, before the closing `return errors`), add:

```python
        neighbor_decisions = payload.get("neighbor_decisions")
        if neighbor_decisions is not None:
            if not isinstance(neighbor_decisions, list):
                errors.append("distill_review.neighbor_decisions must be a list when present.")
            else:
                for idx, entry in enumerate(neighbor_decisions):
                    if not isinstance(entry, dict):
                        errors.append(
                            f"distill_review.neighbor_decisions[{idx}] must be an object."
                        )
                        continue
                    for key in ("candidate_card_id", "decision", "reason", "target_run_id"):
                        if not str(entry.get(key) or "").strip():
                            errors.append(
                                f"distill_review.neighbor_decisions[{idx}] missing required key `{key}`."
                            )
                    decision = str(entry.get("decision") or "")
                    if decision and decision not in DISTILL_NEIGHBOR_DECISIONS:
                        errors.append(
                            f"distill_review.neighbor_decisions[{idx}].decision `{decision}` "
                            f"must be one of {sorted(DISTILL_NEIGHBOR_DECISIONS)}."
                        )
                    target = str(entry.get("target_run_id") or "")
                    if target and target not in reviewed_set:
                        errors.append(
                            f"distill_review.neighbor_decisions[{idx}].target_run_id `{target}` "
                            f"must be present in `reviewed_run_ids`."
                        )
```

- [ ] **Step 2.4: Run tests to confirm pass**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_artifact_schemas_distill_review.py -v
```

Expected: all pass.

- [ ] **Step 2.5: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/deepscientist/artifact/schemas.py tests/test_artifact_schemas_distill_review.py
git commit -m "feat: add optional neighbor_decisions audit field to distill_review schema"
```

---

### Task 3: Add `list_knowledge_summaries` method on `MemoryService`

**Files:**
- Modify: `src/deepscientist/memory/service.py`
- Test: `tests/test_memory_and_artifact.py`

- [ ] **Step 3.1: Write failing tests**

Add to `tests/test_memory_and_artifact.py`:

```python
def test_list_knowledge_summaries_global_returns_compact_rows(temp_home: Path) -> None:
    memory = MemoryService(temp_home)
    memory.write_card(
        scope="global",
        kind="knowledge",
        title="Reward shaping helps early",
        markdown=(
            "---\n"
            "subtype: experience\n"
            "claim: Shaping accelerates early DQN training.\n"
            "keywords:\n  - reward-shaping\n  - dqn\n  - manhattan\n"
            "tags:\n  - task:snake-10x10\n  - method:dqn\n"
            "---\n\nbody\n"
        ),
        quest_id="010",
    )
    rows = memory.list_knowledge_summaries(scope="global")
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Reward shaping helps early"
    assert row["claim"] == "Shaping accelerates early DQN training."
    assert row["keywords"] == ["reward-shaping", "dqn", "manhattan"]
    assert "task:snake-10x10" in row["tags"]
    assert row["scope"] == "global"
    assert row["subtype"] == "experience"
    assert row["card_id"]
    assert row["updated_at"]


def test_list_knowledge_summaries_handles_missing_optional_fields(temp_home: Path) -> None:
    memory = MemoryService(temp_home)
    memory.write_card(
        scope="global",
        kind="knowledge",
        title="Bare card",
        markdown="---\nclaim: ''\n---\n\n",
        quest_id="000",
    )
    rows = memory.list_knowledge_summaries(scope="global")
    assert len(rows) == 1
    row = rows[0]
    assert row["claim"] == ""
    assert row["keywords"] == []
    assert isinstance(row["tags"], list)


def test_list_knowledge_summaries_empty_when_no_cards(temp_home: Path) -> None:
    memory = MemoryService(temp_home)
    assert memory.list_knowledge_summaries(scope="global") == []


def test_list_knowledge_summaries_quest_scope(temp_home: Path) -> None:
    memory = MemoryService(temp_home)
    quest_root = temp_home / "quests" / "010"
    quest_root.mkdir(parents=True)
    memory.write_card(
        scope="quest",
        kind="knowledge",
        title="Quest-local card",
        markdown="---\nclaim: local claim\nkeywords:\n  - foo\n---\n\nbody\n",
        quest_root=quest_root,
        quest_id="010",
    )
    rows = memory.list_knowledge_summaries(scope="quest", quest_root=quest_root)
    assert len(rows) == 1
    assert rows[0]["title"] == "Quest-local card"
    assert rows[0]["scope"] == "quest"


def test_list_knowledge_summaries_sorted_recent_first(temp_home: Path) -> None:
    memory = MemoryService(temp_home)
    memory.write_card(
        scope="global", kind="knowledge", title="Older",
        markdown="---\nclaim: old\n---\n", quest_id="000",
    )
    memory.write_card(
        scope="global", kind="knowledge", title="Newer",
        markdown="---\nclaim: new\n---\n", quest_id="001",
    )
    rows = memory.list_knowledge_summaries(scope="global")
    assert [r["title"] for r in rows] == ["Newer", "Older"]
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_memory_and_artifact.py -v -k list_knowledge_summaries
```

Expected: all FAIL with `AttributeError: 'MemoryService' object has no attribute 'list_knowledge_summaries'`.

- [ ] **Step 3.3: Implement the method**

Add to `src/deepscientist/memory/service.py`, after the existing `list_recent` method (around line 311, before `search`):

```python
    def list_knowledge_summaries(
        self,
        *,
        scope: str = "global",
        quest_root: Path | None = None,
    ) -> list[dict[str, Any]]:
        """Return compact rows (id / title / claim / keywords / tags / subtype / updated_at)
        for every knowledge-kind card in scope.

        No ranking, no filtering, no pagination — the LLM is the judge.
        Sort: most-recently-updated first, ties broken by card id for stability.
        """
        if scope not in {"global", "quest", "visible"}:
            raise ValueError(f"unsupported scope: {scope}")

        sources: list[tuple[Path, str, str | None, bool]] = []
        if scope == "global":
            sources.append((self._root_for("global"), "global", None, False))
        elif scope == "quest":
            if quest_root is None:
                raise ValueError("quest scope requires quest_root")
            sources.append((self._root_for("quest", quest_root), "quest", None, False))
        else:  # visible: global + every initialized quest
            sources.append((self._root_for("global"), "global", None, False))
            for qid, qroot in self._iter_initialized_quest_roots() or []:
                sources.append((self._root_for("quest", qroot), "quest", qid, True))

        rows: list[dict[str, Any]] = []
        for root, source_scope, source_quest_id, shared in sources:
            for raw in self._list_cards_from_root(
                root=root,
                kind="knowledge",
                writable=not shared,
                scope=source_scope,
                source_quest_id=source_quest_id,
                shared=shared,
            ):
                metadata, _body = load_markdown_document(Path(raw["path"]))
                rows.append(self._summary_row(raw, metadata, source_scope))

        def _sort_key(row: dict[str, Any]) -> tuple[float, str]:
            ts = str(row.get("updated_at") or "")
            try:
                ts_float = -datetime.fromisoformat(ts).timestamp() if ts else 0.0
            except ValueError:
                ts_float = 0.0
            return (ts_float, str(row.get("card_id") or ""))

        rows.sort(key=_sort_key)
        return rows

    @staticmethod
    def _summary_row(raw: dict[str, Any], metadata: dict[str, Any], scope: str) -> dict[str, Any]:
        keywords = metadata.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        tags = metadata.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        return {
            "card_id": str(metadata.get("id") or raw.get("id") or "").strip(),
            "title": str(metadata.get("title") or raw.get("title") or "").strip(),
            "claim": str(metadata.get("claim") or "").strip(),
            "keywords": [str(k).strip() for k in keywords if str(k).strip()],
            "tags": [str(t).strip() for t in tags if str(t).strip()],
            "scope": scope,
            "quest_id": str(metadata.get("quest_id") or "").strip(),
            "subtype": (str(metadata.get("subtype")).strip() if metadata.get("subtype") else None),
            "updated_at": str(metadata.get("updated_at") or "").strip(),
        }
```

(Confirm `from datetime import datetime` and `load_markdown_document` are already imported in this module; they should be — `_card_timestamp` uses `datetime.fromisoformat` at line 188, and `_list_cards_from_root` uses `load_markdown_document` at line 162.)

- [ ] **Step 3.4: Run tests to confirm pass**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_memory_and_artifact.py -v -k list_knowledge_summaries
```

Expected: all 5 new tests pass. Run the full file to confirm no regression:

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_memory_and_artifact.py -v
```

Expected: all pass.

- [ ] **Step 3.5: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/deepscientist/memory/service.py tests/test_memory_and_artifact.py
git commit -m "feat: add MemoryService.list_knowledge_summaries for cross-quest recall"
```

---

### Task 4: Register `memory.list_knowledge_summaries` MCP tool

**Files:**
- Modify: `src/deepscientist/mcp/server.py` (memory namespace)
- Modify: `src/deepscientist/runners/codex.py:41-47`
- Test: `tests/test_mcp_servers.py`

- [ ] **Step 4.1: Write failing tests**

Add to `tests/test_mcp_servers.py`:

```python
def test_memory_list_knowledge_summaries_tool_registered(memory_mcp_context):
    """The memory MCP server exposes `list_knowledge_summaries`."""
    server, _context, _service = memory_mcp_context
    tools = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "list_knowledge_summaries" in tools


def test_memory_list_knowledge_summaries_tool_returns_summaries(memory_mcp_context, temp_home):
    server, context, service = memory_mcp_context
    service.write_card(
        scope="global", kind="knowledge", title="Card A",
        markdown=(
            "---\nclaim: Card A claim.\nkeywords:\n  - alpha\n  - beta\n"
            "tags:\n  - task:snake-10x10\n---\n\nbody\n"
        ),
        quest_id="010",
    )
    result = asyncio.run(server.call_tool("list_knowledge_summaries", {"scope": "global"}))
    payload = result[0].text if hasattr(result[0], "text") else result
    parsed = json.loads(payload) if isinstance(payload, str) else payload
    summaries = parsed["summaries"] if isinstance(parsed, dict) else parsed
    titles = [row["title"] for row in summaries]
    assert "Card A" in titles


def test_codex_runner_approves_list_knowledge_summaries():
    from deepscientist.runners.codex import _BUILTIN_MCP_TOOL_APPROVALS
    assert "list_knowledge_summaries" in _BUILTIN_MCP_TOOL_APPROVALS["memory"]
```

If `memory_mcp_context` fixture does not exist in this file, mirror the pattern of an existing fixture (e.g. one used by other memory MCP tests) — search for `mcp_context` or `build_memory_server` in the file. If a different pattern is used (e.g. directly invoking the registered function), adapt the assertions accordingly. The first and third tests do not require the fixture; they run independently.

- [ ] **Step 4.2: Run tests to confirm they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_mcp_servers.py -v -k list_knowledge_summaries
```

Expected: tool registration test FAILS (tool not present), codex approval test FAILS (allowlist missing entry).

- [ ] **Step 4.3: Register the MCP tool**

In `src/deepscientist/mcp/server.py`, find the memory namespace's `search` tool registration (around line 759) and add **after** it, before the next memory tool:

```python
    @server.tool(
        name="list_knowledge_summaries",
        description=(
            "List compact summaries (id / title / claim / keywords / tags) of every "
            "knowledge-kind card in scope. Use this before generating ideas or starting "
            "distill to find prior experience to recall or patch. Returns all cards "
            "unsorted-by-relevance — scan the rows yourself and `memory.read_card` "
            "anything worth reading in full."
        ),
        annotations=_read_only_tool_annotations(title="List knowledge summaries"),
    )
    def list_knowledge_summaries(
        scope: str = "global",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_scope = _resolve_search_scope(context, scope)
        quest_root = context.require_quest_root() if resolved_scope in {"quest", "visible"} else None
        return {
            "scope": resolved_scope,
            "summaries": service.list_knowledge_summaries(
                scope=resolved_scope,
                quest_root=quest_root,
            ),
        }
```

(`_resolve_search_scope` is already used by the `search` tool above; reuse it for symmetry.)

- [ ] **Step 4.4: Add to codex approval allowlist**

In `src/deepscientist/runners/codex.py`, edit lines 41-47:

```python
    "memory": (
        "write",
        "read",
        "search",
        "list_recent",
        "list_knowledge_summaries",
        "promote_to_global",
    ),
```

- [ ] **Step 4.5: Run tests to confirm pass**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_mcp_servers.py -v -k list_knowledge_summaries
```

Expected: all 3 new tests pass.

- [ ] **Step 4.6: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/deepscientist/mcp/server.py src/deepscientist/runners/codex.py tests/test_mcp_servers.py
git commit -m "feat: expose memory.list_knowledge_summaries MCP tool with codex approval"
```

---

### Task 5: Add `recall_priors` startup-contract plumbing

**Files:**
- Modify: `src/deepscientist/artifact/experience_distill.py` (add helpers)
- Modify: `src/deepscientist/mcp/server.py:222-249, 415-437`
- Test: `tests/test_experience_distill_config.py`

- [ ] **Step 5.1: Write failing tests**

Add to `tests/test_experience_distill_config.py`:

```python
from deepscientist.artifact.experience_distill import (
    coerce_recall_priors_mode,
    is_recall_priors_on,
    read_recall_priors_mode,
)


def test_coerce_recall_priors_mode_accepts_bool() -> None:
    assert coerce_recall_priors_mode(True) == {"mode": "on"}
    assert coerce_recall_priors_mode(False) == {"mode": "off"}


def test_coerce_recall_priors_mode_accepts_string() -> None:
    assert coerce_recall_priors_mode("on") == {"mode": "on"}
    assert coerce_recall_priors_mode("OFF") == {"mode": "off"}
    assert coerce_recall_priors_mode("garbage") == {"mode": "off"}


def test_coerce_recall_priors_mode_accepts_dict() -> None:
    assert coerce_recall_priors_mode({"mode": "on"}) == {"mode": "on"}
    assert coerce_recall_priors_mode({"mode": True}) == {"mode": "on"}
    assert coerce_recall_priors_mode({"mode": False}) == {"mode": "off"}


def test_coerce_recall_priors_mode_default_off() -> None:
    assert coerce_recall_priors_mode(None) == {"mode": "off"}
    assert coerce_recall_priors_mode(42) == {"mode": "off"}


def test_read_recall_priors_mode_reads_quest_yaml(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: on\n", encoding="utf-8"
    )
    assert read_recall_priors_mode(quest_root) == {"mode": "on"}
    assert is_recall_priors_on(quest_root) is True


def test_read_recall_priors_mode_defaults_off_when_missing(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text("startup_contract: {}\n", encoding="utf-8")
    assert read_recall_priors_mode(quest_root) == {"mode": "off"}
    assert is_recall_priors_on(quest_root) is False


def test_read_recall_priors_mode_defaults_off_when_no_yaml(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    assert is_recall_priors_on(quest_root) is False


def test_read_recall_priors_mode_independent_of_distill(tmp_path: Path) -> None:
    """recall_priors and experience_distill are separate fields."""
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: on\n  experience_distill: off\n",
        encoding="utf-8",
    )
    assert is_recall_priors_on(quest_root) is True
```

Also add a test that the start_setup form-field sanitizer accepts `recall_priors` as a bool (in `tests/test_mcp_servers.py` or wherever `_sanitize_start_setup_form_patch` is currently tested — search for `experience_distill` in test files to find the parallel test):

```python
def test_sanitize_start_setup_accepts_recall_priors_bool() -> None:
    from deepscientist.mcp.server import _sanitize_start_setup_form_patch
    patch = _sanitize_start_setup_form_patch({"recall_priors": True})
    assert patch == {"recall_priors": True}
    patch = _sanitize_start_setup_form_patch({"recall_priors": "on"})
    assert patch == {"recall_priors": True}
```

- [ ] **Step 5.2: Run tests to confirm they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_config.py -v -k recall_priors
```

Expected: all FAIL with `ImportError: cannot import name 'coerce_recall_priors_mode'`.

- [ ] **Step 5.3: Add the helper functions**

Edit `src/deepscientist/artifact/experience_distill.py`. After `is_distill_on` (line 151), add:

```python
def coerce_recall_priors_mode(value: Any, *, field_name: str = "recall_priors") -> dict[str, str]:
    """Normalize user-supplied value into {"mode": "on"|"off"} for recall_priors.

    Accepts: bool, "on"/"off" string, dict {"mode": ...}. Anything else collapses to off.
    """
    if value is True:
        return {"mode": "on"}
    if value is False or value is None:
        return {"mode": "off"}
    if isinstance(value, str):
        return {"mode": "on" if value.strip().lower() == "on" else "off"}
    if isinstance(value, dict):
        mode_val = value.get("mode")
        if mode_val is True:
            return {"mode": "on"}
        if mode_val is False:
            return {"mode": "off"}
        raw = str(mode_val or "").strip().lower()
        return {"mode": "on" if raw == "on" else "off"}
    return {"mode": "off"}


def read_recall_priors_mode(quest_root: Path | None) -> dict[str, str]:
    """Read `startup_contract.recall_priors` from quest.yaml; return normalized dict."""
    if quest_root is None:
        return {"mode": "off"}
    quest_yaml = quest_root / "quest.yaml"
    if not quest_yaml.exists():
        return {"mode": "off"}
    try:
        from ..shared import require_yaml
        require_yaml()
        import yaml  # type: ignore
        payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"mode": "off"}
    if not isinstance(payload, dict):
        return {"mode": "off"}
    contract = payload.get("startup_contract") or {}
    if not isinstance(contract, dict):
        return {"mode": "off"}
    return coerce_recall_priors_mode(contract.get("recall_priors"))


def is_recall_priors_on(quest_root: Path | None) -> bool:
    return read_recall_priors_mode(quest_root)["mode"] == "on"
```

- [ ] **Step 5.4: Wire into start_setup form**

Edit `src/deepscientist/mcp/server.py`:

1. Append `"recall_priors"` to `START_SETUP_FORM_FIELDS` at line 248-249 (after `"experience_distill",`).

2. In `_sanitize_start_setup_form_patch` (around line 428, after the `experience_distill` branch), add:

```python
        if key == "recall_priors":
            patch[key] = _coerce_prepare_bool(value, field_name=key)
            continue
```

- [ ] **Step 5.5: Run tests to confirm pass**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_config.py tests/test_mcp_servers.py -v -k recall_priors
```

Expected: all 9 tests pass.

- [ ] **Step 5.6: Validate Python syntax**

```bash
cd /home/ds/DeepScientist-distill
python3 -m compileall -q src/deepscientist
```

- [ ] **Step 5.7: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/deepscientist/artifact/experience_distill.py src/deepscientist/mcp/server.py tests/test_experience_distill_config.py tests/test_mcp_servers.py
git commit -m "feat: add startup_contract.recall_priors helpers and form-field plumbing"
```

---

### Task 6: Add `recall_priors` UI toggle

**Files:**
- Modify: `src/ui/src/lib/startResearch.ts`
- Modify: `src/ui/src/components/projects/CreateProjectDialog.tsx`

This task has no Python tests; verify by running `npm --prefix src/ui run build` to ensure TS compiles.

- [ ] **Step 6.1: Add `recall_priors` to form type and defaults in `startResearch.ts`**

Open `src/ui/src/lib/startResearch.ts`. Find the `experience_distill: boolean` in the form type (line 74) and add immediately below:

```typescript
  recall_priors: boolean;
```

For each location where `experience_distill: false` appears as a default (lines 198, 321, 375), add the parallel default:

```typescript
  recall_priors: false,
```

Locate the coercion at line 602 `experience_distill: input.experience_distill === true`, and add:

```typescript
  recall_priors: input.recall_priors === true,
```

Search the file for any other place `experience_distill` appears in JSON serialization or API submission and add the parallel `recall_priors` line.

- [ ] **Step 6.2: Add translation keys in `CreateProjectDialog.tsx`**

In the English translation block (lines 239-242), after the `distillDisabledBody` line, add:

```typescript
    recallPriorsEnabled: 'Recall priors on',
    recallPriorsEnabledBody: 'Stage skills (scout / idea / baseline) call memory.list_knowledge_summaries before generating, so prior task experience is surfaced.',
    recallPriorsDisabled: 'Recall priors off',
    recallPriorsDisabledBody: 'Stage skills do not look at global knowledge before generating. Suitable when this quest has no overlap with prior work.',
```

In the zh translation block (lines 635-638), add:

```typescript
    recallPriorsEnabled: '开启先验回忆',
    recallPriorsEnabledBody: '在 scout / idea / baseline 阶段开始前调用 memory.list_knowledge_summaries，把过往任务经验拉出来再做决定。',
    recallPriorsDisabled: '关闭先验回忆',
    recallPriorsDisabledBody: '阶段技能不查全局知识，直接生成。适合与已有积累完全无关的新任务。',
```

- [ ] **Step 6.3: Add `recall_priors: false` defaults in form initializers**

In `CreateProjectDialog.tsx`:
- Line 1442: alongside `experience_distill: false,`, add `recall_priors: false,`.
- Line 1484: same.
- Line 2488: alongside `experience_distill: next.experience_distill,`, add `recall_priors: next.recall_priors,`.
- Line 2575: alongside `experience_distill: saved.experience_distill,`, add `recall_priors: saved.recall_priors,`.

- [ ] **Step 6.4: Add the toggle UI block**

After the existing distill toggle block at lines 3066-3074, add a parallel block:

```tsx
                          {form.recall_priors ? t.recallPriorsEnabled : t.recallPriorsDisabled}
```

(Replicate the entire surrounding card/Switch structure from the distill toggle — copy lines 3060-3076 and substitute every `experience_distill` → `recall_priors`, `distillEnabled`/`distillEnabledBody`/`distillDisabled`/`distillDisabledBody` → the new `recallPriors*` keys.)

- [ ] **Step 6.5: Build the UI to verify TS compiles**

```bash
cd /home/ds/DeepScientist-distill
npm --prefix src/ui install --no-audit --no-fund 2>&1 | tail -5
npm --prefix src/ui run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors. If the build script is too slow on a fresh install, run only `npx tsc --noEmit -p src/ui` for type-check.

- [ ] **Step 6.6: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/ui/src/lib/startResearch.ts src/ui/src/components/projects/CreateProjectDialog.tsx
git commit -m "feat: add recall_priors toggle to project creation wizard"
```

---

### Task 7: Inject `recall_priors_rule` cue from prompt builder

**Files:**
- Modify: `src/deepscientist/prompts/builder.py:1031-1042` (per-turn cue block)
- Test: `tests/test_prompt_builder.py`

- [ ] **Step 7.1: Write failing tests**

Add to `tests/test_prompt_builder.py`:

```python
def test_prompt_builder_injects_recall_priors_when_on_for_stage_skill(tmp_path, prompt_builder_factory):
    """When recall_priors is on and the active skill is a stage skill, the cue line appears."""
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: on\n", encoding="utf-8"
    )
    builder = prompt_builder_factory(quest_root=quest_root)
    rendered = builder.build_prompt(skill_id="idea", quest_id="010", quest_root=quest_root)
    assert "recall_priors_rule:" in rendered
    assert "list_knowledge_summaries" in rendered


def test_prompt_builder_omits_recall_priors_when_off(tmp_path, prompt_builder_factory):
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: off\n", encoding="utf-8"
    )
    builder = prompt_builder_factory(quest_root=quest_root)
    rendered = builder.build_prompt(skill_id="idea", quest_id="010", quest_root=quest_root)
    assert "recall_priors_rule:" not in rendered


def test_prompt_builder_omits_recall_priors_for_companion_skill(tmp_path, prompt_builder_factory):
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: on\n", encoding="utf-8"
    )
    builder = prompt_builder_factory(quest_root=quest_root)
    rendered = builder.build_prompt(skill_id="distill", quest_id="010", quest_root=quest_root)
    assert "recall_priors_rule:" not in rendered
```

If `prompt_builder_factory` does not exist as a fixture, examine `tests/test_prompt_builder.py` for the existing pattern (search for `PromptBuilder` instantiation in the file) and adapt the test to call the public method that produces the per-turn cue block — the assertion is on substring presence, so any path that exercises the relevant code branch is valid.

If the existing tests instantiate `PromptBuilder` directly with a `home` argument, replace the fixture call with:

```python
from deepscientist.prompts.builder import PromptBuilder
builder = PromptBuilder(home=tmp_path)
rendered = builder._priority_memory_block(quest_root, skill_id="idea", active_anchor=None, user_message="")
# or whichever block injects the recall_priors_rule line
```

— and assert on that block's output.

- [ ] **Step 7.2: Run tests to confirm they fail**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_prompt_builder.py -v -k recall_priors
```

Expected: FAIL — no cue is injected yet.

- [ ] **Step 7.3: Implement the injection**

Edit `src/deepscientist/prompts/builder.py`. At the top, add the import (if not already present):

```python
from ..artifact.experience_distill import is_recall_priors_on
```

Find the existing block at lines 1031-1042 (the `recent_memory_cues:` block in whichever method this lives in — likely `_resume_spine_block` or similar). **Before** the `recent_memory = self.memory_service.list_recent(...)` call at line 1031, add:

```python
        if is_recall_priors_on(quest_root) and skill_id in stage_skill_ids(repo_root()):
            lines.append(
                "- recall_priors_rule: before generating new ideas, baselines, or experiment plans, "
                "call `memory.list_knowledge_summaries(scope='global')` once and scan the returned "
                "rows for any `task:` tag, claim, or keyword that overlaps your current quest. "
                "Read the full card via `memory.read_card` for any candidate that looks relevant. "
                "If nothing matches, say so explicitly in your reasoning and proceed."
            )
```

Verify the enclosing method receives `skill_id` and `quest_root` as parameters (they should — `_priority_memory_block` already takes both at line 330-335). If the cue block is in a different method without access to `skill_id`, thread the parameter through.

- [ ] **Step 7.4: Run tests to confirm pass**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_prompt_builder.py -v -k recall_priors
```

Expected: pass.

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_prompt_builder.py -v
```

Expected: full file passes (no regression).

- [ ] **Step 7.5: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/deepscientist/prompts/builder.py tests/test_prompt_builder.py
git commit -m "feat: inject recall_priors_rule cue into stage-skill prompts"
```

---

### Task 8: Rewrite distill SKILL.md (D + N1 + N3 + N4 docs)

**Files:**
- Modify: `src/skills/distill/SKILL.md`

This is a Markdown-only change. No tests. Verify by reading the file end-to-end after edit.

- [ ] **Step 8.1: Replace step 1 ("Search for neighbors") with summary-scan flow**

In `src/skills/distill/SKILL.md`, locate the section that begins "Search for neighbors:" (around line 36) and the JSON `memory.search` call. Replace from "Search for neighbors:" through the "Read the top 3 matches." sentence with:

```markdown
**Search for neighbors via the keyword summary index.**

```json
{"tool": "memory.list_knowledge_summaries", "arguments": {"scope": "global"}}
```

The tool returns one row per global knowledge card with
`card_id / title / claim / keywords / tags / subtype / updated_at`. Scan
the rows for any card whose `task:` tag, `claim`, or `keywords` overlap
the candidate run you are processing.

For each row that looks like a plausible neighbor, fetch the full card:

```json
{"tool": "memory.read_card", "arguments": {"card_id": "knowledge-..."}}
```

For each inspection, decide one of:

- **patch** — the existing card and the candidate run share a causal
  mechanism. Append a `lineage` entry, possibly downgrade `confidence`,
  narrow `conditions`, and append (do not delete) `keywords`. The
  `claim` text is immutable across quests.
- **new** — no existing card covers the candidate's mechanism; write a
  fresh card with `memory.write_card`.
- **neighbor_but_separate** — a related card exists but the candidate's
  mechanism is genuinely different. Note the relationship in `notes`
  and write a new card anyway.

Record one `neighbor_decisions` entry per inspected neighbor in the
final `distill_review` (see step 3) — including the negative cases
(`new`, `neighbor_but_separate`).
```

- [ ] **Step 8.2: Add `keywords` field to the new-card frontmatter template (B)**

Locate "B. Create a new global card" subsection. Update the frontmatter template to include both `keywords` and `tags`:

```yaml
subtype: experience
claim: <one sentence, mechanism-bearing, falsifiable>
mechanism: <causal chain — why this plausibly holds>
conditions:
  - <scoping tag 1>
  - <scoping tag 2>
keywords:
  - <kw 1>            # 3..8 short noun phrases or compound tokens; lowercased
  - <kw 2>
confidence: <0.0..1.0; 0.4 is a fine starting value>
tags:
  - task:<short-id>   # required
  - stage:<stage>     # optional
  - domain:<domain>   # optional
  - method:<method>   # optional
lineage:
  - quest: <quest_id>
    run: <candidate.run_id or candidate.artifact_id>
    direction: <direction or goal id>
    note: <one-phrase takeaway>
```

- [ ] **Step 8.3: Add `task:` tag and `keywords` to "Hard constraints"**

In the "Hard constraints on new/patched cards" section (currently § 2), append two bullets:

```markdown
- Every new or patched card must include a `task:<short-id>` tag in
  the top-level `tags:` list. The `<short-id>` is a stable
  low-cardinality slug for the task family the experience belongs to
  (e.g. `task:snake-10x10`, `task:cifar10-classification`,
  `task:gsm8k`). Reuse existing slugs when patching; coin a new slug
  only when no neighbor card uses one.
- Every new card must include a top-level `keywords` list of 3–8 short
  noun phrases (lowercased, hyphenated). Cross-quest patches may
  *append* keywords but must not delete existing ones; same-quest
  patches may freely edit.
```

- [ ] **Step 8.4: Update step 3 (distill_review recording) to mention neighbor_decisions**

In the section that shows the `distill_review` record example, after the `notes` line, add:

```json
    "neighbor_decisions": [
      {"candidate_card_id": "knowledge-...", "decision": "patch",  "reason": "same mechanism", "target_run_id": "run-..."},
      {"candidate_card_id": "knowledge-...", "decision": "neighbor_but_separate", "reason": "different conditions", "target_run_id": "run-..."}
    ]
```

And add a paragraph immediately after the JSON block:

> `neighbor_decisions` is optional but strongly recommended: record one
> entry per neighbor card you inspected, including the negative cases
> (where the decision was `new` or `neighbor_but_separate`). This makes
> the review log show what you considered, not just what you wrote.

- [ ] **Step 8.5: Read the file end-to-end to confirm it's coherent**

```bash
cd /home/ds/DeepScientist-distill
wc -l src/skills/distill/SKILL.md
```

Open the file and read top-to-bottom; confirm step 1 / template / hard constraints / step 3 all reference the same fields consistently.

- [ ] **Step 8.6: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add src/skills/distill/SKILL.md
git commit -m "docs(skill): rewrite distill neighbor flow to summary-scan + add task/keywords/neighbor_decisions conventions"
```

---

### Task 9: Backfill quest 010 cards

**Files:**
- Modify: `~/DeepScientist/memory/knowledge/potential-based-reward-shaping-gives-strong-early-advantage-but-converges-to-similar-asymptote-at-moderate-step-budgets.md`
- Modify: `~/DeepScientist/memory/knowledge/symbolic-features-enable-100-200x-sample-efficiency-vs-pixel-cnn-dqn-in-low-dimensional-grid-games.md`

These files live outside the repo, in the user's runtime memory dir.

- [ ] **Step 9.1: Add `task:snake-10x10` and `keywords` to card 1**

Edit `/home/ds/DeepScientist/memory/knowledge/potential-based-reward-shaping-gives-strong-early-advantage-but-converges-to-similar-asymptote-at-moderate-step-budgets.md`. In the top frontmatter block (lines 1-16), update:

```yaml
tags:
- stage:experiment
- domain:rl
- method:reward-shaping
- method:dqn
- task:snake-10x10
keywords:
- reward-shaping
- potential-based
- manhattan-distance
- dqn
- snake-grid
- early-training-advantage
- shaping-coefficient
```

(`keywords` is a new top-level field; insert it after the `tags:` block, before `created_at:`.)

- [ ] **Step 9.2: Add `task:snake-10x10` and `keywords` to card 2**

Edit `/home/ds/DeepScientist/memory/knowledge/symbolic-features-enable-100-200x-sample-efficiency-vs-pixel-cnn-dqn-in-low-dimensional-grid-games.md`:

```yaml
tags:
- stage:experiment
- domain:rl
- domain:game
- method:symbolic-features
- method:dqn
- task:snake-10x10
keywords:
- symbolic-features
- pixel-cnn-dqn
- sample-efficiency
- snake-grid
- low-dimensional-state
- mlp-dqn
- feature-engineering
```

- [ ] **Step 9.3: Verify the cards parse via `list_knowledge_summaries`**

```bash
cd /home/ds/DeepScientist-distill
python3 -c "
from pathlib import Path
from deepscientist.memory import MemoryService
m = MemoryService(Path.home() / 'DeepScientist')
rows = m.list_knowledge_summaries(scope='global')
for r in rows:
    print(r['title'], '->', r.get('keywords'), '|', [t for t in r.get('tags', []) if t.startswith('task:')])
"
```

Expected output: both cards listed, each with their `keywords` array populated and a `task:snake-10x10` entry in tags.

- [ ] **Step 9.4: No commit (these files are outside the repo)**

The runtime memory dir `~/DeepScientist/memory/` is the user's, not source-controlled here.

---

### Task 10: End-to-end integration test

**Files:**
- Modify: `tests/test_experience_distill_integration.py`

- [ ] **Step 10.1: Add the integration test**

Append to `tests/test_experience_distill_integration.py`:

```python
def test_e2e_finalize_gate_uses_imperative_routing_no_fallback(tmp_path: Path) -> None:
    """End-to-end: from quest with one completed run + recall_priors=on,
    a write decision routes to distill with the new imperative wording and
    no write fallback in alternative_routes."""
    quest_root = tmp_path / "quest-e2e"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n"
        "  experience_distill: on\n"
        "  recall_priors: on\n",
        encoding="utf-8",
    )
    artifacts_dir = quest_root / "artifacts"
    artifacts_dir.mkdir()
    run_path = artifacts_dir / "runs" / "run-main.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps({
            "kind": "run", "run_kind": "main_experiment",
            "status": "completed", "artifact_id": "run-main",
            "summary": "main experiment ok",
        }),
        encoding="utf-8",
    )
    (artifacts_dir / "_index.jsonl").write_text(
        json.dumps({"kind": "run", "path": str(run_path)}) + "\n", encoding="utf-8"
    )

    decision = {"kind": "decision", "action": "write", "artifact_id": "decision-write-1"}
    inbound = {"recommended_skill": "write", "recommended_action": "Draft paper."}
    fired = maybe_inject_distill_finalize_gate(quest_root, artifacts_dir, decision, inbound)

    assert fired is not None
    assert fired["recommended_skill"] == "distill"
    assert "Distill required" in fired["recommended_action"]
    assert fired["pending_distill_count"] == 1
    assert fired["pending_distill_ids"] == ["run-main"]
    routes = fired.get("alternative_routes") or []
    assert not any(
        isinstance(r, dict) and r.get("recommended_skill") == "write"
        for r in routes
    )

    # Now the agent records a distill_review with neighbor_decisions covering the run.
    review_path = artifacts_dir / "distill_reviews" / "distill-review-1.json"
    review_path.parent.mkdir(parents=True)
    review_payload = {
        "kind": "distill_review",
        "artifact_id": "distill-review-1",
        "created_at": "2026-04-25T10:00:00+00:00",
        "reviewed_run_ids": ["run-main"],
        "cards_written": [
            {
                "card_id": "knowledge-fresh",
                "scope": "global",
                "action": "new",
                "target_run_id": "run-main",
            }
        ],
        "neighbor_decisions": [
            {
                "candidate_card_id": "knowledge-existing",
                "decision": "neighbor_but_separate",
                "reason": "different mechanism",
                "target_run_id": "run-main",
            }
        ],
    }
    review_path.write_text(json.dumps(review_payload), encoding="utf-8")
    with (artifacts_dir / "_index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "distill_review", "path": str(review_path)}) + "\n")

    # Schema check passes.
    from deepscientist.artifact.schemas import validate_artifact_payload
    assert validate_artifact_payload(review_payload) == []

    # Re-evaluate the same write decision: gate clears, original route restored.
    cleared = maybe_inject_distill_finalize_gate(
        quest_root, artifacts_dir, decision, fired
    )
    assert cleared is not None
    assert cleared["recommended_skill"] == "write"
    assert cleared.get("gate") != "finalize"
```

- [ ] **Step 10.2: Run the new test**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_integration.py::test_e2e_finalize_gate_uses_imperative_routing_no_fallback -v
```

Expected: pass.

- [ ] **Step 10.3: Run the entire integration file + the full test suite**

```bash
cd /home/ds/DeepScientist-distill
pytest tests/test_experience_distill_integration.py -v
pytest 2>&1 | tail -30
```

Expected: integration file passes; full suite shows zero new failures attributable to this branch (pre-existing failures in unrelated modules are out of scope).

- [ ] **Step 10.4: Commit**

```bash
cd /home/ds/DeepScientist-distill
git add tests/test_experience_distill_integration.py
git commit -m "test: end-to-end check for distill phase 3 routing + neighbor_decisions"
```

---

## Final verification

After all 10 tasks land:

- [ ] **Run the full test suite**

```bash
cd /home/ds/DeepScientist-distill
pytest 2>&1 | tail -20
```

Expected: all tests pass (or only pre-existing unrelated failures remain).

- [ ] **Validate Python compiles**

```bash
cd /home/ds/DeepScientist-distill
python3 -m compileall -q src/deepscientist
```

Expected: no output.

- [ ] **Validate UI builds**

```bash
cd /home/ds/DeepScientist-distill
npm --prefix src/ui run build 2>&1 | tail -10
```

Expected: build succeeds.

- [ ] **Reinstall under ds user**

```bash
su - ds -c "cd /home/ds/DeepScientist-distill && bash install.sh"
```

Expected: install completes; `ds doctor` reports green.

- [ ] **Run quest 011 validation**

Create a fresh quest 011 with `experience_distill: on` and `recall_priors: on`, configured similarly to quest 010 (Snake DQN or comparable small-budget RL task). Walk it through baseline → idea → experiment → write decision. Verify:

1. The agent calls `memory.list_knowledge_summaries` at the start of the idea / experiment stages (recall_priors injection working).
2. The agent surfaces the quest 010 cards (backfill + summaries working).
3. When the agent records `decision(action='write')` before any `distill_review`, the guidance redirects to distill with the imperative wording and no write fallback (routing strength working).
4. After the agent records a `distill_review` with at least one `neighbor_decisions` entry, the gate clears and write resumes.

---

## Self-review checklist

**Spec coverage:**
- § A (routing strength) → Task 1 ✓
- § D (task tag) → Task 8.3 ✓ + Task 9 backfill ✓
- § P1.1 (recall_priors plumbing) → Task 5 ✓
- § P1.1 (UI) → Task 6 ✓
- § P1.2 (prompt builder injection) → Task 7 ✓
- § P2.N1 (keywords field) → Task 8.2, 8.3 ✓ + Task 9 backfill ✓
- § P2.N2 (list_knowledge_summaries service) → Task 3 ✓
- § P2.N2 (MCP tool + codex approval) → Task 4 ✓
- § P2.N3 (skill step 1 rewrite) → Task 8.1 ✓
- § P2.N4 (neighbor_decisions schema) → Task 2 ✓
- § P2.N4 (skill step 3 docs) → Task 8.4 ✓
- E2E test → Task 10 ✓
- Backfill → Task 9 ✓

**Placeholder scan:** clean. No "TBD" / "implement later". Test-paths-not-yet-confirmed (Task 7 fixture, Task 4 fixture) include explicit fallback instructions to adapt to the actual existing fixture pattern.

**Type consistency:**
- `list_knowledge_summaries` row shape: `card_id / title / claim / keywords / tags / scope / quest_id / subtype / updated_at` — used identically in Task 3 (service), Task 4 (MCP), Task 8.1 (skill markdown).
- `neighbor_decisions` entry shape: `candidate_card_id / decision / reason / target_run_id` — used identically in Task 2 (schema), Task 8.4 (skill markdown), Task 10 (integration test).
- `is_recall_priors_on(quest_root)` — defined Task 5, used Task 7.
- Frontmatter field names (`keywords`, `tags`, `task:<short-id>`) consistent across Task 8 / Task 9 / Task 10.
