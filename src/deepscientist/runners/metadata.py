from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunnerMetadata:
    name: str
    label: str
    default_binary: str
    default_config_dir: str
    quest_dotdir: str
    status_note: str = ""
    supports_reasoning_effort: bool = False


_RUNNER_METADATA: dict[str, RunnerMetadata] = {
    "codex": RunnerMetadata(
        name="codex",
        label="Codex",
        default_binary="codex",
        default_config_dir="~/.codex",
        quest_dotdir=".codex",
        supports_reasoning_effort=True,
    ),
    "claude": RunnerMetadata(
        name="claude",
        label="Claude",
        default_binary="claude",
        default_config_dir="~/.claude",
        quest_dotdir=".claude",
    ),
    "opencode": RunnerMetadata(
        name="opencode",
        label="OpenCode",
        default_binary="opencode",
        default_config_dir="~/.config/opencode",
        quest_dotdir=".opencode",
    ),
    "kimi": RunnerMetadata(
        name="kimi",
        label="Kimi Code",
        default_binary="kimi",
        default_config_dir="~/.kimi",
        quest_dotdir=".kimi",
    ),
}


def get_runner_metadata(name: str) -> RunnerMetadata:
    normalized = str(name or "").strip().lower()
    try:
        return _RUNNER_METADATA[normalized]
    except KeyError as exc:
        available = ", ".join(sorted(_RUNNER_METADATA)) or "none"
        raise KeyError(f"Unknown runner `{normalized}`. Available runners: {available}.") from exc


def list_builtin_runner_names() -> tuple[str, ...]:
    return tuple(sorted(_RUNNER_METADATA))


def runner_binary_override_env_names(name: str) -> tuple[str, str]:
    normalized = str(name or "").strip().upper().replace("-", "_")
    return (
        f"DEEPSCIENTIST_{normalized}_BINARY",
        f"DS_{normalized}_BINARY",
    )
