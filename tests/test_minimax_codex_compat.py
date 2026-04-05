from __future__ import annotations

from pathlib import Path

from deepscientist.runners import CodexRunner, RunRequest
from deepscientist.runners.codex import provider_profile_metadata_from_home


def test_provider_profile_metadata_from_home_reads_minimax_profile(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(
        """[model_providers.minimax]
base_url = "https://api.minimaxi.com/v1"
env_key = "MINIMAX_API_KEY"
wire_api = "chat"
requires_openai_auth = false

[profiles.m27]
model = "codex-MiniMax-M2.7"
model_provider = "minimax"
""",
        encoding="utf-8",
    )

    metadata = provider_profile_metadata_from_home(codex_home, profile="m27")

    assert metadata["provider"] == "minimax"
    assert metadata["model"] == "codex-MiniMax-M2.7"
    assert metadata["env_key"] == "MINIMAX_API_KEY"
    assert metadata["requires_openai_auth"] is False


def test_codex_runner_build_command_forces_inherit_when_profile_is_set(temp_home) -> None:  # type: ignore[no-untyped-def]
    runner = CodexRunner(
        home=temp_home,
        repo_root=temp_home,
        binary="codex",
        logger=object(),  # type: ignore[arg-type]
        prompt_builder=object(),  # type: ignore[arg-type]
        artifact_service=object(),  # type: ignore[arg-type]
    )
    request = RunRequest(
        quest_id="q-001",
        quest_root=temp_home / "quest",
        worktree_root=temp_home / "quest",
        run_id="run-001",
        skill_id="baseline",
        message="hello",
        model="gpt-5.4",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    command = runner._build_command(request, "prompt", runner_config={"profile": "m27"})

    assert "--profile" in command
    assert "m27" in command
    assert "--model" not in command
