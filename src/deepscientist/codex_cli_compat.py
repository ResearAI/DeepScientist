from __future__ import annotations

import json
import re
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

_MIN_XHIGH_SUPPORTED_VERSION = (0, 63, 0)
_CODEX_VERSION_PATTERN = re.compile(r"codex-cli\s+(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)


def parse_codex_cli_version(text: str) -> tuple[int, int, int] | None:
    match = _CODEX_VERSION_PATTERN.search(str(text or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


@lru_cache(maxsize=32)
def codex_cli_version(binary: str) -> tuple[int, int, int] | None:
    normalized = str(binary or "").strip()
    if not normalized:
        return None
    try:
        result = subprocess.run(
            [normalized, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_codex_cli_version(f"{result.stdout}\n{result.stderr}")


def format_codex_cli_version(version: tuple[int, int, int] | None) -> str:
    if version is None:
        return ""
    return ".".join(str(part) for part in version)


def normalize_codex_reasoning_effort(
    reasoning_effort: str | None,
    *,
    resolved_binary: str | None,
) -> tuple[str | None, str | None]:
    normalized = str(reasoning_effort or "").strip()
    if not normalized:
        return None, None
    if normalized.lower() != "xhigh":
        return normalized, None

    version = codex_cli_version(str(resolved_binary or ""))
    if version is None or version >= _MIN_XHIGH_SUPPORTED_VERSION:
        return normalized, None

    version_text = format_codex_cli_version(version)
    return (
        "high",
        (
            f"Codex CLI {version_text} does not support `xhigh`; "
            "DeepScientist downgraded reasoning effort to `high` automatically."
        ),
    )


def adapt_profile_only_provider_config(
    config_text: str,
    *,
    profile: str,
) -> tuple[str, str | None]:
    normalized_profile = str(profile or "").strip()
    if not normalized_profile or not str(config_text or "").strip():
        return config_text, None
    try:
        parsed = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError:
        return config_text, None

    profiles = parsed.get("profiles")
    if not isinstance(profiles, dict):
        return config_text, None
    profile_payload = profiles.get(normalized_profile)
    if not isinstance(profile_payload, dict):
        return config_text, None

    prefix_lines: list[str] = []
    injected_fields: list[str] = []
    if "model_provider" not in parsed:
        model_provider = str(profile_payload.get("model_provider") or "").strip()
        if model_provider:
            prefix_lines.append(f"model_provider = {json.dumps(model_provider, ensure_ascii=False)}")
            injected_fields.append("model_provider")
    if "model" not in parsed:
        model = str(profile_payload.get("model") or "").strip()
        if model:
            prefix_lines.append(f"model = {json.dumps(model, ensure_ascii=False)}")
            injected_fields.append("model")

    if not prefix_lines:
        return config_text, None

    adapted = (
        "# BEGIN DEEPSCIENTIST PROFILE COMPAT\n"
        + "\n".join(prefix_lines)
        + "\n# END DEEPSCIENTIST PROFILE COMPAT\n\n"
        + config_text.lstrip()
    )
    return (
        adapted,
        (
            f"DeepScientist promoted `{normalized_profile}` profile "
            f"{', '.join(injected_fields)} to the top level for Codex compatibility."
        ),
    )


def provider_profile_metadata(
    config_text: str,
    *,
    profile: str,
) -> dict[str, str | bool | None]:
    normalized_profile = str(profile or "").strip()
    if not normalized_profile or not str(config_text or "").strip():
        return {
            "provider": None,
            "model": None,
            "env_key": None,
            "base_url": None,
            "wire_api": None,
            "requires_openai_auth": None,
        }
    try:
        parsed = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError:
        return {
            "provider": None,
            "model": None,
            "env_key": None,
            "base_url": None,
            "wire_api": None,
            "requires_openai_auth": None,
        }

    profiles = parsed.get("profiles")
    if not isinstance(profiles, dict):
        return {
            "provider": None,
            "model": None,
            "env_key": None,
            "base_url": None,
            "wire_api": None,
            "requires_openai_auth": None,
        }
    profile_payload = profiles.get(normalized_profile)
    if not isinstance(profile_payload, dict):
        return {
            "provider": None,
            "model": None,
            "env_key": None,
            "base_url": None,
            "wire_api": None,
            "requires_openai_auth": None,
        }

    model_provider = str(
        profile_payload.get("model_provider")
        or parsed.get("model_provider")
        or ""
    ).strip() or None
    model = str(
        profile_payload.get("model")
        or parsed.get("model")
        or ""
    ).strip() or None
    provider_payload = None
    model_providers = parsed.get("model_providers")
    if model_provider and isinstance(model_providers, dict):
        candidate = model_providers.get(model_provider)
        if isinstance(candidate, dict):
            provider_payload = candidate

    env_key = (
        str(provider_payload.get("env_key") or "").strip()
        if isinstance(provider_payload, dict)
        else None
    ) or None
    base_url = (
        str(provider_payload.get("base_url") or "").strip()
        if isinstance(provider_payload, dict)
        else None
    ) or None
    wire_api = (
        str(provider_payload.get("wire_api") or "").strip()
        if isinstance(provider_payload, dict)
        else None
    ) or None
    requires_openai_auth = (
        bool(provider_payload.get("requires_openai_auth"))
        if isinstance(provider_payload, dict) and "requires_openai_auth" in provider_payload
        else None
    )

    return {
        "provider": model_provider,
        "model": model,
        "env_key": env_key,
        "base_url": base_url,
        "wire_api": wire_api,
        "requires_openai_auth": requires_openai_auth,
    }


def provider_profile_metadata_from_home(
    config_home: str | Path,
    *,
    profile: str,
) -> dict[str, str | bool | None]:
    config_path = Path(config_home).expanduser() / "config.toml"
    if not config_path.exists():
        return {
            "provider": None,
            "model": None,
            "env_key": None,
            "base_url": None,
            "wire_api": None,
            "requires_openai_auth": None,
        }
    return provider_profile_metadata(config_path.read_text(encoding="utf-8"), profile=profile)
