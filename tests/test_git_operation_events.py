from __future__ import annotations

from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.gitops import current_branch, head_commit
from deepscientist.quest import QuestService
from deepscientist.shared import read_json
from deepscientist.shared import read_jsonl


def test_git_action_records_before_and_after_refs_for_state_changes(temp_home: Path) -> None:
    quest_service = QuestService(temp_home)
    artifact_service = ArtifactService(temp_home)
    quest = quest_service.create("git operation event metadata")
    quest_root = Path(str(quest["quest_root"]))
    quest_service.update_research_state(quest_root, workspace_mode="copilot")

    initial_branch = current_branch(quest_root)
    initial_head = head_commit(quest_root)

    commit_result = artifact_service.git_action(
        quest_root,
        action="commit",
        message="git op metadata",
        allow_empty=True,
    )
    commit_payload = dict(commit_result["result"])
    assert commit_payload["before_branch"] == initial_branch
    assert commit_payload["after_branch"] == initial_branch
    assert commit_payload["before_head"] == initial_head
    assert commit_payload["after_head"] == commit_payload["head"]
    assert commit_payload["target_ref"] == initial_branch

    branch_result = artifact_service.git_action(
        quest_root,
        action="branch",
        branch="feature/git-op",
    )
    branch_payload = dict(branch_result["result"])
    assert branch_payload["before_branch"] == initial_branch
    assert branch_payload["target_ref"] == "feature/git-op"
    assert branch_payload["create_from"] == initial_branch

    checkout_result = artifact_service.git_action(
        quest_root,
        action="checkout",
        branch="feature/git-op",
    )
    checkout_payload = dict(checkout_result["result"])
    assert checkout_payload["before_branch"] == initial_branch
    assert checkout_payload["after_branch"] == "feature/git-op"
    assert checkout_payload["target_ref"] == "feature/git-op"

    events = read_jsonl(quest_root / ".ds" / "events.jsonl")
    git_events = [event for event in events if event.get("type") == "artifact.git"]
    assert len(git_events) >= 3
    latest_three = git_events[-3:]
    assert [event.get("action") for event in latest_three] == ["commit", "branch", "checkout"]
    assert latest_three[0]["result"]["before_head"] == initial_head
    assert latest_three[1]["result"]["target_ref"] == "feature/git-op"
    assert latest_three[2]["result"]["after_branch"] == "feature/git-op"

    report_payloads = []
    for path in sorted((quest_root / "artifacts" / "reports").glob("*.json")):
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        if str(payload.get("report_type") or "") != "git_operation":
            continue
        report_payloads.append(payload)

    assert len(report_payloads) >= 3
    by_step = {str(payload.get("protocol_step") or ""): payload for payload in report_payloads}
    assert {"commit", "branch", "checkout"} <= set(by_step)
    assert by_step["commit"]["branch"] == initial_branch
    assert by_step["branch"]["branch"] == "feature/git-op"
    assert by_step["checkout"]["branch"] == "feature/git-op"


def test_git_operation_reports_do_not_collapse_repeated_commits(temp_home: Path) -> None:
    quest_service = QuestService(temp_home)
    artifact_service = ArtifactService(temp_home)
    quest = quest_service.create("git operation repeated commits")
    quest_root = Path(str(quest["quest_root"]))
    quest_service.update_research_state(quest_root, workspace_mode="copilot")

    artifact_service.git_action(
        quest_root,
        action="commit",
        message="repeat git op",
        allow_empty=True,
    )
    artifact_service.git_action(
        quest_root,
        action="commit",
        message="repeat git op",
        allow_empty=True,
    )

    commit_reports = []
    for path in sorted((quest_root / "artifacts" / "reports").glob("*.json")):
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        if str(payload.get("report_type") or "") != "git_operation":
            continue
        if str(payload.get("protocol_step") or "") != "commit":
            continue
        commit_reports.append(payload)

    assert len(commit_reports) == 2
    assert len({str(item.get("head_commit") or "").strip() for item in commit_reports}) == 2
