from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request

from ..codex_cli_compat import (
    active_provider_metadata_from_home,
    adapt_profile_only_provider_config,
    chat_wire_compatible_codex_version,
    codex_cli_version,
    format_codex_cli_version,
    materialize_codex_runtime_home,
    missing_provider_env_key,
    missing_provider_env_key_from_text,
    normalize_codex_reasoning_effort,
    provider_base_url_looks_local,
)
from ..kimi_cli_compat import materialize_kimi_runtime_home
from ..connector.connector_profiles import PROFILEABLE_CONNECTOR_NAMES, list_connector_profiles, normalize_connector_config
from ..connector_runtime import build_discovered_target, infer_connector_transport
from ..home import repo_root
from ..connector.lingzhu_support import (
    generate_lingzhu_auth_ak,
    lingzhu_auth_ak_needs_rotation,
    lingzhu_agent_id,
    lingzhu_generated_curl,
    lingzhu_generated_openclaw_config_text,
    lingzhu_gateway_port,
    lingzhu_health_url,
    lingzhu_is_passive_conversation_id,
    lingzhu_local_base_url,
    lingzhu_passive_conversation_id,
    lingzhu_probe_payload,
    lingzhu_public_base_url,
    lingzhu_sse_url,
    lingzhu_supported_commands,
    public_base_url_looks_public,
)
from ..connector.qq_profiles import (
    find_qq_profile,
    list_qq_profiles,
    normalize_qq_connector_config,
    qq_profile_label,
)
from ..connector.weixin_support import normalize_weixin_base_url, normalize_weixin_cdn_base_url
from ..network import urlopen_with_proxy as urlopen
from ..runners.metadata import get_runner_metadata, list_builtin_runner_names
from ..runners.runtime_overrides import apply_codex_runtime_overrides, apply_runners_runtime_overrides
from ..shared import ensure_utf8_subprocess_env, read_json, read_text, read_yaml, resolve_runner_binary, run_command, sha256_text, utc_now, utf8_text_subprocess_kwargs, which, write_text, write_yaml
from .models import (
    CONFIG_NAMES,
    OPTIONAL_CONFIG_NAMES,
    REQUIRED_CONFIG_NAMES,
    ConfigFileInfo,
    SYSTEM_CONNECTOR_NAMES,
    config_filename,
    default_system_enabled_connectors,
    default_payload,
)


class ConfigManager:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.config_root = home / "config"

    def path_for(self, name: str) -> Path:
        if name not in CONFIG_NAMES:
            raise KeyError(f"Unknown config name: {name}")
        return self.config_root / config_filename(name)

    def ensure_files(self) -> list[Path]:
        created: list[Path] = []
        for name in REQUIRED_CONFIG_NAMES:
            path = self.path_for(name)
            if not path.exists():
                write_yaml(path, default_payload(name, self.home))
                created.append(path)
        return created

    def ensure_optional_file(self, name: str) -> Path:
        if name not in OPTIONAL_CONFIG_NAMES:
            raise KeyError(f"{name} is not an optional config file")
        path = self.path_for(name)
        if not path.exists():
            write_yaml(path, default_payload(name, self.home))
        return path

    def list_files(self) -> list[ConfigFileInfo]:
        items: list[ConfigFileInfo] = []
        for name in CONFIG_NAMES:
            path = self.path_for(name)
            items.append(
                ConfigFileInfo(
                    name=name,
                    path=path,
                    required=name in REQUIRED_CONFIG_NAMES,
                    exists=path.exists(),
                )
            )
        return items

    def load_named(self, name: str, create_optional: bool = False) -> dict:
        path = self.path_for(name)
        if create_optional and name in OPTIONAL_CONFIG_NAMES and not path.exists():
            self.ensure_optional_file(name)
        return read_yaml(path, default_payload(name, self.home))

    def load_named_normalized(self, name: str, create_optional: bool = False) -> dict:
        return self._normalize_named_payload(name, self.load_named(name, create_optional=create_optional))

    def load_runners_config(self) -> dict:
        return apply_runners_runtime_overrides(self.load_named_normalized("runners"))

    def load_runtime_config(self) -> dict:
        return self.load_named_normalized("config")

    def system_connector_gates(self) -> dict[str, bool]:
        config = self.load_runtime_config()
        connectors = config.get("connectors") if isinstance(config.get("connectors"), dict) else {}
        system_enabled = connectors.get("system_enabled") if isinstance(connectors.get("system_enabled"), dict) else {}
        defaults = default_system_enabled_connectors()
        return {
            name: self._coerce_bool(system_enabled.get(name), default=defaults.get(name, False))
            for name in SYSTEM_CONNECTOR_NAMES
        }

    def system_enabled_connector_names(self) -> list[str]:
        gates = self.system_connector_gates()
        return [name for name in SYSTEM_CONNECTOR_NAMES if gates.get(name, False)]

    def is_connector_system_enabled(self, name: str) -> bool:
        normalized = str(name or "").strip().lower()
        if not normalized:
            return False
        if normalized == "local":
            return True
        if normalized == "lingzhu":
            return True
        gates = self.system_connector_gates()
        if normalized in gates:
            return gates[normalized]
        return True

    def load_named_text(self, name: str, create_optional: bool = False) -> str:
        path = self.path_for(name)
        if create_optional and name in OPTIONAL_CONFIG_NAMES and not path.exists():
            self.ensure_optional_file(name)
        if path.exists():
            return read_text(path)
        payload = default_payload(name, self.home)
        write_yaml(path, payload)
        return read_text(path)

    def save_named_text(self, name: str, content: str) -> dict:
        validation = self.validate_named_text(name, content)
        if not validation["ok"]:
            return validation
        path = self.path_for(name)
        write_text(path, content)
        return {
            "ok": True,
            "document_id": name,
            "path": str(path),
            "saved_at": utc_now(),
            "revision": f"sha256:{sha256_text(content)}",
            "conflict": False,
            "warnings": validation["warnings"],
            "errors": [],
        }

    def render_named_payload(self, name: str, payload: dict) -> str:
        from ..shared import require_yaml

        require_yaml()
        import yaml

        normalized = self._normalize_named_payload(name, payload)
        return yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False)

    def validate_named_payload(self, name: str, payload: dict) -> dict:
        return self.validate_named_text(name, self.render_named_payload(name, payload))

    def save_named_payload(self, name: str, payload: dict) -> dict:
        prepared = self._prepare_payload_for_save(name, payload)
        previous = self.load_named_normalized(name) if name in CONFIG_NAMES and self.path_for(name).exists() else default_payload(name, self.home)
        result = self.save_named_text(name, self.render_named_payload(name, prepared))
        if result.get("ok") and name == "runners":
            self._invalidate_codex_bootstrap_state_if_runner_changed(previous, self.load_named_normalized("runners"))
        return result

    def _prepare_payload_for_save(self, name: str, payload: dict) -> dict:
        prepared = deepcopy(payload) if isinstance(payload, dict) else {}
        if name != "connectors":
            return prepared
        lingzhu = prepared.get("lingzhu")
        if not isinstance(lingzhu, dict):
            return prepared
        enabled = self._coerce_bool(lingzhu.get("enabled"), default=False)
        raw_public_base_url = str(lingzhu.get("public_base_url") or "").strip()
        direct_auth_ak = str(lingzhu.get("auth_ak") or "").strip()
        if lingzhu_auth_ak_needs_rotation(direct_auth_ak):
            lingzhu["auth_ak"] = generate_lingzhu_auth_ak()
        elif (enabled or raw_public_base_url) and not self._has_secret(lingzhu, "auth_ak", "auth_ak_env"):
            lingzhu["auth_ak"] = generate_lingzhu_auth_ak()
        prepared["lingzhu"] = lingzhu
        return prepared

    def _invalidate_codex_bootstrap_state_if_runner_changed(self, previous: dict, current: dict) -> None:
        tracked_keys_by_runner = {
            "codex": (
                "binary",
                "config_dir",
                "profile",
                "model",
                "model_reasoning_effort",
                "approval_policy",
                "sandbox_mode",
                "env",
                "mcp_tool_timeout_sec",
            ),
            "claude": (
                "binary",
                "config_dir",
                "model",
                "permission_mode",
                "env",
            ),
            "kimi": (
                "binary",
                "config_dir",
                "model",
                "agent",
                "thinking",
                "yolo",
                "env",
            ),
            "opencode": (
                "binary",
                "config_dir",
                "model",
                "permission_mode",
                "default_agent",
                "variant",
                "env",
            ),
        }
        changed_runners: list[str] = []
        for runner_name, tracked_keys in tracked_keys_by_runner.items():
            previous_runner = previous.get(runner_name) if isinstance(previous.get(runner_name), dict) else {}
            current_runner = current.get(runner_name) if isinstance(current.get(runner_name), dict) else {}
            if all(previous_runner.get(key) == current_runner.get(key) for key in tracked_keys):
                continue
            changed_runners.append(runner_name)
        if not changed_runners:
            return
        config = self.load_named_normalized("config")
        bootstrap = config.get("bootstrap") if isinstance(config.get("bootstrap"), dict) else {}
        runner_readiness = bootstrap.get("runner_readiness") if isinstance(bootstrap.get("runner_readiness"), dict) else {}
        checked_at = utc_now()
        for runner_name in changed_runners:
            summary = f"{runner_name} runner configuration changed. A new startup probe is required."
            runner_readiness[runner_name] = {
                "ready": False,
                "last_checked_at": checked_at,
                "last_result": {
                    "ok": False,
                    "summary": summary,
                    "warnings": [],
                    "errors": [],
                    "guidance": [],
                },
            }
        bootstrap["runner_readiness"] = runner_readiness
        codex_state = runner_readiness.get("codex") if isinstance(runner_readiness.get("codex"), dict) else {}
        bootstrap["codex_ready"] = bool(codex_state.get("ready", False))
        bootstrap["codex_last_checked_at"] = codex_state.get("last_checked_at")
        bootstrap["codex_last_result"] = codex_state.get("last_result") if isinstance(codex_state.get("last_result"), dict) else {}
        config["bootstrap"] = bootstrap
        self.save_named_text("config", self.render_named_payload("config", config))

    def bind_qq_main_chat(self, *, profile_id: str | None = None, chat_id: str) -> dict:
        normalized_chat_id = str(chat_id or "").strip()
        if not normalized_chat_id:
            return {"ok": False, "saved": False, "message": "QQ main chat id is empty."}
        connectors = self.load_named_normalized("connectors")
        qq = connectors.get("qq") if isinstance(connectors.get("qq"), dict) else {}
        profiles = list_qq_profiles(qq)
        if not profiles:
            return {"ok": False, "saved": False, "message": "QQ profile is not configured yet."}
        resolved_profile = find_qq_profile(qq, profile_id=profile_id)
        if resolved_profile is None and len(profiles) == 1:
            resolved_profile = profiles[0]
        if resolved_profile is None:
            return {"ok": False, "saved": False, "message": "Unable to determine which QQ profile should save this OpenID."}
        configured = str((resolved_profile or {}).get("main_chat_id") or "").strip()
        if configured:
            return {
                "ok": True,
                "saved": False,
                "chat_id": configured,
                "already_configured": True,
                "profile_id": resolved_profile.get("profile_id"),
            }
        for item in profiles:
            if str(item.get("profile_id") or "").strip() == str(resolved_profile.get("profile_id") or "").strip():
                item["main_chat_id"] = normalized_chat_id
        qq["profiles"] = profiles
        qq = normalize_qq_connector_config(qq)
        connectors["qq"] = qq
        result = self.save_named_payload("connectors", connectors)
        return {
            "ok": bool(result.get("ok")),
            "saved": bool(result.get("ok")),
            "chat_id": normalized_chat_id,
            "profile_id": resolved_profile.get("profile_id"),
            "profile_label": qq_profile_label(resolved_profile),
            "saved_at": result.get("saved_at"),
            "errors": result.get("errors") or [],
            "warnings": result.get("warnings") or [],
        }

    def validate_named_text(self, name: str, content: str) -> dict:
        try:
            from ..shared import require_yaml

            require_yaml()
            import yaml

            parsed = yaml.safe_load(content) if content.strip() else {}
        except Exception as exc:
            return {
                "ok": False,
                "warnings": [],
                "errors": [str(exc)],
                "name": name,
            }
        warnings: list[str] = []
        errors: list[str] = []
        if parsed is None:
            parsed = {}
        if not isinstance(parsed, dict):
            return {
                "ok": False,
                "warnings": warnings,
                "errors": ["Top-level YAML value must be a mapping."],
                "name": name,
            }
        normalized = self._normalize_named_payload(name, parsed)
        if name == "connectors":
            connector_validation = self._validate_connectors_payload(normalized)
            warnings.extend(connector_validation["warnings"])
            errors.extend(connector_validation["errors"])
        elif name == "plugins":
            plugin_validation = self._validate_plugins_payload(normalized)
            warnings.extend(plugin_validation["warnings"])
            errors.extend(plugin_validation["errors"])
        elif name == "mcp_servers":
            mcp_validation = self._validate_mcp_servers_payload(normalized)
            warnings.extend(mcp_validation["warnings"])
            errors.extend(mcp_validation["errors"])
        return {
            "ok": len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "name": name,
            "parsed": normalized,
        }

    def validate_all(self) -> dict:
        results = []
        for info in self.list_files():
            if info.required and not info.exists:
                self.ensure_files()
            if not info.exists and not info.required:
                results.append(
                    {
                        "name": info.name,
                        "ok": True,
                        "warnings": ["Optional config file is missing and may be created lazily."],
                        "errors": [],
                    }
                )
                continue
            results.append(self.validate_named_text(info.name, self.load_named_text(info.name)))
        return {
            "ok": all(item["ok"] for item in results),
            "files": results,
        }

    def help_markdown(self, name: str) -> str:
        home_text = str(self.home)
        if name == "connectors":
            return f"""# Connector Settings Guide

This page edits `~/DeepScientist/config/connectors.yaml` directly.

## What this page is for

- connect Weixin, Telegram, Discord, Slack, Feishu, WhatsApp, or QQ
- choose one preferred connector for proactive artifact updates
- decide whether artifact updates fan out or stay focused
- use the built-in direct runtime for each connector
- keep all secrets in one visible place

## Recommended order

1. configure one connector first
2. fill the required token or secret fields
3. click **Validate**
4. click **Test**
5. save the file only after the test result looks healthy

## Preferred transports

- Weixin: `ilink_long_poll`
- Telegram: `polling`
- Slack: `socket_mode`
- Discord: `gateway`
- Feishu: `long_connection`
- WhatsApp: `local_session`
- QQ: `gateway_direct`

## Practical notes

### Telegram

- set `bot_token`
- prefer `transport: polling`
- readiness test uses `getMe`

### Slack

- set `bot_token`
- for no-callback mode also set `app_token`
- prefer `transport: socket_mode`
- readiness test uses `auth.test`

### Weixin

- scan the QR code first so DeepScientist can persist `bot_token` and `account_id`
- keep `transport: ilink_long_poll`
- every reply depends on the latest inbound `context_token`
- media send uses the built-in AES + CDN upload path for image, video, and file attachments

### Discord

- set `bot_token`
- prefer `transport: gateway`

### Feishu

- set `app_id`
- set `app_secret`
- prefer `transport: long_connection`
- test checks whether tenant token exchange succeeds

### WhatsApp

- prefer `transport: local_session`
- the local-session path is designed to avoid public callbacks
- keep one writable `session_dir` for the local auth state

### QQ

- QQ only uses the built-in gateway direct path with `app_id` + `app_secret`
- each QQ bot is stored as one item under `qq.profiles`
- save one QQ bot profile first, then ask the user to send one private QQ message to that specific bot
- the daemon auto-detects that user's `openid` and saves it into that profile's `main_chat_id`
- private QQ chats can then auto-follow the latest quest by default, unless disabled in settings
- readiness test exchanges `access_token` and probes `/gateway`
- active send targets use QQ user `openid` or group `group_openid`
- the settings page also surfaces recently discovered targets from runtime activity, grouped by QQ bot profile
- milestone delivery toggles default to enabled; adjust them only if you want less outbound push
- the recommended first-run path is: save credentials -> send one QQ private message -> confirm `Detected OpenID` -> run a probe

### Lingzhu

- Lingzhu is hosted directly by DeepScientist on `/metis/agent/api`
- keep `transport: openclaw_sse`
- use the same public DeepScientist origin and port that the browser is already serving on
- save once so DeepScientist can persist `auth_ak`; Rokid must use the same Bearer token
- `public_base_url` must be a public IP or public domain; loopback and private addresses are invalid for Rokid
- new Lingzhu tasks must start with `我现在的任务是`; other requests are treated as reconnect or progress polling

## Safety

- the file is saved in `{home_text}/config/connectors.yaml`
- no hidden connector database exists
- validation is local
- test is non-destructive and only uses lightweight identity or readiness endpoints
"""
        if name == "config":
            return f"""# Core Config Guide

This page edits the main runtime file at `{home_text}/config/config.yaml`.

## What to check

- `home`
- `ui.host`
- `ui.port`
- `logging.level`
- `git.auto_checkpoint`
- `cloud.enabled`
- `bootstrap.codex_ready`

## Test behavior

The **Test** button checks:

- whether `git` is installed
- whether `git user.name` exists
- whether `git user.email` exists
- whether the configured home path exists

This is a safe local smoke test.

## Codex startup gate

- `bootstrap.codex_ready` starts as `false`
- the launcher runs a real Codex hello probe before first daemon start
- once Codex answers correctly, DeepScientist flips this flag to `true`
- if the probe fails, DeepScientist writes the failure summary back into config and blocks startup

## Figure and chart style policy

- chart and paper-figure palettes are not configured in `config.yaml`
- DeepScientist keeps a fixed Morandi palette guide in the system prompt and relevant stage skills
- change visual defaults by editing the prompt / skill contract, not by adding per-install palette settings
"""
        if name == "runners":
            return f"""# Runner Config Guide

This page edits `{home_text}/config/runners.yaml`.

## Recommended v1 choice

- keep `codex.enabled: true`
- enable whichever runners you actually plan to use (`codex`, `claude`, `kimi`, `opencode`)
- keep the others disabled if their local CLI or credentials are not ready yet
- set `codex.profile` only when your Codex CLI uses a named provider profile such as `m27`
- when you launch DeepScientist ad hoc with a provider profile, you can also use `ds --codex-profile <name>`
- when you want a one-off Codex binary override, you can also use `ds --codex /absolute/path/to/codex`
- keep `codex.model_reasoning_effort: xhigh` unless you explicitly want a lighter default
- keep `codex.retry_on_failure: true` so transient Codex failures can resume automatically
- keep retry timing near `10s / 6x / 1800s max` so Codex backs off exponentially and the final retries sit at the 30-minute cap
- DeepScientist hard-limits one turn to at most `7` total attempts, even if the config says more

## Test behavior

The **Test** button checks:

- whether the configured runner binaries are on PATH
- whether disabled runners are intentionally skipped
- for Codex, it also runs a real hello probe so login problems, profile misconfiguration, and first-run setup issues surface before quest execution
- it does not simulate the full failure/retry loop, so use quest runtime logs when debugging recovery behavior
"""
        if name == "plugins":
            return f"""# Plugin Config Guide

This page edits `{home_text}/config/plugins.yaml`.

## What belongs here

- plugin discovery paths
- explicit enabled plugin ids
- explicit disabled plugin ids
- unsigned-plugin trust policy

## What does not belong here

- installed plugin metadata discovered from the filesystem
- plugin runtime state
- plugin-generated artifacts or logs

## Recommended approach

1. keep the default plugin directory in `load_paths`
2. add extra search roots only when you actually install external bundles
3. use `enabled` and `disabled` only for explicit overrides
4. leave `allow_unsigned` off unless you control the plugin source
"""
        if name == "mcp_servers":
            return f"""# External MCP Guide

This page edits `{home_text}/config/mcp_servers.yaml`.

## What belongs here

- external MCP server ids
- enable/disable state
- transport choice
- stdio command or remote URL
- optional working directory and env overrides

## What does not belong here

- built-in `memory` MCP
- built-in `artifact` MCP
- quest-local MCP state
- recent tool outputs

## Recommended approach

1. add one server card per external MCP namespace
2. use `stdio` for local MCP processes
3. use `streamable_http` for remote MCP services
4. keep secrets in the `env` block rather than hard-coding them into commands
"""
        return f"""# {name}.yaml

This page edits `{home_text}/config/{name}.yaml` directly.

Use **Validate** before saving.
Use **Test** when the file exposes runtime dependencies.
"""

    def test_named_text(self, name: str, content: str, *, live: bool = True, delivery_targets: dict | None = None) -> dict:
        validation = self.validate_named_text(name, content)
        if not validation["ok"]:
            return {
                "ok": False,
                "name": name,
                "summary": "Validation failed. Fix errors before testing.",
                "warnings": validation["warnings"],
                "errors": validation["errors"],
                "items": [],
            }
        parsed = validation.get("parsed") or {}
        if name == "connectors":
            return self._test_connectors_payload(parsed, live=live, delivery_targets=delivery_targets or {})
        if name == "config":
            return self._test_core_config_payload(parsed)
        if name == "runners":
            return self._test_runners_payload(parsed, live=live)
        return {
            "ok": True,
            "name": name,
            "summary": f"No runtime test is defined for `{name}`. Validation passed.",
            "warnings": validation["warnings"],
            "errors": [],
            "items": [],
        }

    def test_named_payload(self, name: str, payload: dict, *, live: bool = True, delivery_targets: dict | None = None) -> dict:
        rendered = self.render_named_payload(name, payload)
        return self.test_named_text(name, rendered, live=live, delivery_targets=delivery_targets)

    def test_deepxiv_payload(self, payload: dict | None = None) -> dict:
        normalized = self._normalize_named_payload("config", payload if isinstance(payload, dict) else self.load_named_normalized("config"))
        literature = normalized.get("literature") if isinstance(normalized.get("literature"), dict) else {}
        deepxiv = literature.get("deepxiv") if isinstance(literature.get("deepxiv"), dict) else {}
        base_url = str(deepxiv.get("base_url") or "https://data.rag.ac.cn").strip() or "https://data.rag.ac.cn"
        direct_token = str(deepxiv.get("token") or "").strip()
        token_env_name = str(deepxiv.get("token_env") or "").strip()
        env_token = str(os.environ.get(token_env_name) or "").strip() if token_env_name else ""
        resolved_token = direct_token or env_token
        query = "transformers"
        result_size = max(1, int(deepxiv.get("default_result_size") or 20))
        preview_characters = max(200, int(deepxiv.get("preview_characters") or 5000))
        request_timeout_seconds = max(3, int(deepxiv.get("request_timeout_seconds") or 90))
        details = {
            "base_url": base_url,
            "query": query,
            "result_size": result_size,
            "preview_characters": preview_characters,
            "request_timeout_seconds": request_timeout_seconds,
            "token_source": "direct_token" if direct_token else ("env" if env_token else "missing"),
            "token_env": token_env_name or None,
        }
        if not resolved_token:
            return {
                "ok": False,
                "summary": "DeepXiv test failed: token is missing.",
                "warnings": [],
                "errors": ["Provide a DeepXiv token before running the test."],
                "details": details,
                "results": [],
                "preview": "",
            }
        url = f"{base_url.rstrip('/')}/arxiv/?{urlencode({'type': 'retrieve', 'query': query, 'size': str(result_size)})}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {resolved_token}",
                "User-Agent": "DeepScientist/DeepXivTest",
            },
        )
        try:
            with urlopen(request, timeout=request_timeout_seconds) as response:  # noqa: S310
                response_text = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            details["request_url"] = url
            return {
                "ok": False,
                "summary": "DeepXiv test request failed.",
                "warnings": [],
                "errors": [str(exc)],
                "details": details,
                "results": [],
                "preview": "",
            }
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            preview = response_text[:preview_characters].rstrip()
            if len(response_text) > preview_characters:
                preview = f"{preview}\n...[truncated]"
            details["request_url"] = url
            return {
                "ok": False,
                "summary": "DeepXiv test returned invalid JSON.",
                "warnings": [],
                "errors": ["DeepXiv returned invalid JSON."],
                "details": details,
                "results": [],
                "preview": preview,
            }
        results = parsed.get("results") if isinstance(parsed.get("results"), list) else []
        preview_payload = {
            "total": parsed.get("total"),
            "took": parsed.get("took"),
            "results": results[: min(3, len(results))],
        }
        preview = json.dumps(preview_payload, ensure_ascii=False, indent=2)
        if len(preview) > preview_characters:
            preview = f"{preview[:preview_characters].rstrip()}\n...[truncated]"
        details.update(
            {
                "request_url": url,
                "total": parsed.get("total"),
                "result_count": len(results),
                "first_title": str((results[0] or {}).get("title") or "").strip() if results else None,
            }
        )
        ok = len(results) > 0
        return {
            "ok": ok,
            "summary": "DeepXiv returned search results for `transformers`." if ok else "DeepXiv returned no search results for `transformers`.",
            "warnings": [],
            "errors": [] if ok else ["No results were returned for `transformers`."],
            "details": details,
            "results": results[:5],
            "preview": preview,
        }

    def probe_runner_bootstrap(self, runner_name: str, *, persist: bool = False, payload: dict | None = None) -> dict:
        normalized_runner = str(runner_name or "codex").strip().lower() or "codex"
        runners_payload = payload if isinstance(payload, dict) else self.load_named_normalized("runners")
        runner_payload = runners_payload.get(normalized_runner) if isinstance(runners_payload.get(normalized_runner), dict) else {}
        if normalized_runner == "codex":
            result = self._probe_codex_runner(runner_payload)
        elif normalized_runner == "claude":
            result = self._probe_claude_runner(runner_payload)
        elif normalized_runner == "kimi":
            result = self._probe_kimi_runner(runner_payload)
        elif normalized_runner == "opencode":
            result = self._probe_opencode_runner(runner_payload)
        else:
            raise KeyError(f"Unknown runner `{normalized_runner}`.")
        if persist:
            self._persist_runner_bootstrap_result(normalized_runner, result)
        return result

    def runner_bootstrap_state(self, runner_name: str) -> dict:
        normalized_runner = str(runner_name or "codex").strip().lower() or "codex"
        config = self.load_named_normalized("config")
        bootstrap = config.get("bootstrap") if isinstance(config.get("bootstrap"), dict) else {}
        runner_readiness = bootstrap.get("runner_readiness") if isinstance(bootstrap.get("runner_readiness"), dict) else {}
        runner_state = runner_readiness.get(normalized_runner) if isinstance(runner_readiness.get(normalized_runner), dict) else {}
        if normalized_runner == "codex" and not runner_state:
            runner_state = {
                "ready": bool(bootstrap.get("codex_ready", False)),
                "last_checked_at": bootstrap.get("codex_last_checked_at"),
                "last_result": bootstrap.get("codex_last_result") if isinstance(bootstrap.get("codex_last_result"), dict) else {},
            }
        return {
            "runner": normalized_runner,
            "ready": bool(runner_state.get("ready", False)),
            "last_checked_at": runner_state.get("last_checked_at"),
            "last_result": runner_state.get("last_result") if isinstance(runner_state.get("last_result"), dict) else {},
        }

    def runner_readiness_map(self) -> dict[str, dict[str, Any]]:
        return {name: self.runner_bootstrap_state(name) for name in list_builtin_runner_names()}

    def probe_codex_bootstrap(self, *, persist: bool = False, payload: dict | None = None) -> dict:
        return self.probe_runner_bootstrap("codex", persist=persist, payload=payload)

    def codex_bootstrap_state(self) -> dict:
        state = self.runner_bootstrap_state("codex")
        return {
            "codex_ready": bool(state.get("ready")),
            "codex_last_checked_at": state.get("last_checked_at"),
            "codex_last_result": state.get("last_result") if isinstance(state.get("last_result"), dict) else {},
        }

    def git_readiness(self) -> dict:
        git_binary = which("git")
        if git_binary is None:
            return {
                "ok": False,
                "installed": False,
                "user_name": "",
                "user_email": "",
                "warnings": [],
                "errors": ["`git` is not installed or not on PATH."],
                "guidance": [
                    "Install Git first.",
                ],
            }

        def get_value(key: str) -> str:
            try:
                result = run_command(["git", "config", "--get", key], check=False)
            except Exception:
                return ""
            return result.stdout.strip()

        user_name = get_value("user.name")
        user_email = get_value("user.email")
        warnings: list[str] = []
        guidance: list[str] = []
        if not user_name:
            warnings.append("Git user.name is missing.")
            guidance.append('git config --global user.name "Your Name"')
        if not user_email:
            warnings.append("Git user.email is missing.")
            guidance.append('git config --global user.email "you@example.com"')
        return {
            "ok": True,
            "installed": True,
            "user_name": user_name,
            "user_email": user_email,
            "warnings": warnings,
            "errors": [],
            "guidance": guidance,
        }

    def _test_core_config_payload(self, payload: dict) -> dict:
        git = self.git_readiness()
        home_path = Path(str(payload.get("home") or self.home))
        items = [
            {
                "name": "home",
                "ok": home_path.exists(),
                "warnings": [],
                "errors": [] if home_path.exists() else [f"Configured home path does not exist: {home_path}"],
                "details": {"path": str(home_path)},
            },
            {
                "name": "git",
                "ok": git["installed"] and not git["errors"],
                "warnings": git["warnings"],
                "errors": git["errors"],
                "details": {
                    "user_name": git.get("user_name"),
                    "user_email": git.get("user_email"),
                    "guidance": git.get("guidance"),
                },
            },
        ]
        ok = all(item["ok"] and not item["errors"] for item in items)
        return {
            "ok": ok,
            "name": "config",
            "summary": "Core config smoke test completed.",
            "warnings": [],
            "errors": [],
            "items": items,
        }

    def _test_runners_payload(self, payload: dict, *, live: bool) -> dict:
        items = []
        for name, config in payload.items():
            if not isinstance(config, dict):
                continue
            enabled = bool(config.get("enabled", False))
            binary = str(config.get("binary") or name).strip()
            resolved_binary = resolve_runner_binary(binary, runner_name=name)
            exists = resolved_binary is not None
            warnings: list[str] = []
            if not enabled:
                warnings.append("Runner is disabled and was skipped.")
            item_ok = (not enabled) or exists
            item = {
                "name": name,
                "ok": item_ok,
                "warnings": warnings,
                "errors": [] if item_ok else [f"Runner binary `{binary}` is not available."],
                "details": {
                    "binary": binary,
                    "resolved_binary": resolved_binary,
                    "enabled": enabled,
                    "live_probe_executed": False,
                },
            }
            if enabled and name == "codex" and exists and live:
                probe = self._probe_codex_runner(config)
                item["ok"] = bool(probe.get("ok"))
                item["warnings"] = [*warnings, *list(probe.get("warnings") or [])]
                item["errors"] = list(probe.get("errors") or [])
                details = item["details"] if isinstance(item.get("details"), dict) else {}
                details.update(probe.get("details") or {})
                details["summary"] = probe.get("summary")
                details["live_probe_executed"] = True
                item["details"] = details
            items.append(item)
        return {
            "ok": all(item["ok"] for item in items),
            "name": "runners",
            "summary": "Runner readiness test completed.",
            "warnings": [],
            "errors": [],
            "items": items,
        }

    def _validate_connectors_payload(self, payload: dict) -> dict:
        warnings: list[str] = []
        errors: list[str] = []
        routing = payload.get("_routing") if isinstance(payload.get("_routing"), dict) else {}
        routing_policy = str(routing.get("artifact_delivery_policy") or "fanout_all").strip().lower()
        preferred_connector = str(routing.get("primary_connector") or "").strip().lower()
        enabled_connectors: list[str] = []

        if routing_policy not in {"fanout_all", "primary_only", "primary_plus_local"}:
            errors.append(
                "_routing: `artifact_delivery_policy` must be one of `fanout_all`, `primary_only`, or `primary_plus_local`."
            )

        for name, raw_config in payload.items():
            if str(name).startswith("_"):
                continue
            if not isinstance(raw_config, dict):
                errors.append(f"{name}: connector config must be a mapping.")
                continue
            config = raw_config
            enabled = bool(config.get("enabled", False))
            if not self._should_validate_connector(str(name), config):
                continue
            if enabled:
                enabled_connectors.append(str(name))

            if name == "qq":
                profiles = list_qq_profiles(config)
                if not profiles:
                    errors.append("qq: requires at least one configured profile under `qq.profiles`.")
                    continue
                legacy_missing_app_id = False
                legacy_missing_secret = False
                seen_profile_ids: set[str] = set()
                seen_app_ids: set[str] = set()
                for profile in profiles:
                    profile_id = str(profile.get("profile_id") or "").strip() or "unknown"
                    app_id = str(profile.get("app_id") or "").strip()
                    if not profile_id:
                        errors.append("qq: every profile requires a stable `profile_id`.")
                    elif profile_id in seen_profile_ids:
                        errors.append(f"qq: duplicate profile_id `{profile_id}`.")
                    else:
                        seen_profile_ids.add(profile_id)
                    if not app_id:
                        legacy_missing_app_id = True
                        errors.append(f"qq[{profile_id}]: requires `app_id`.")
                    elif app_id in seen_app_ids:
                        errors.append(f"qq: duplicate app_id `{app_id}` across profiles.")
                    else:
                        seen_app_ids.add(app_id)
                    if not self._has_secret(profile, "app_secret", "app_secret_env"):
                        legacy_missing_secret = True
                        errors.append(f"qq[{profile_id}]: requires `app_secret` or `app_secret_env`.")
                if len(profiles) == 1 and legacy_missing_app_id:
                    errors.append("qq: requires `app_id` for the built-in gateway direct connector.")
                if len(profiles) == 1 and legacy_missing_secret:
                    errors.append("qq: requires `app_secret` or `app_secret_env` for the built-in gateway direct connector.")
                continue
            transport = infer_connector_transport(name, config)

            policy_validation = self._validate_access_policies(name, config)
            warnings.extend(policy_validation["warnings"])
            errors.extend(policy_validation["errors"])

            if name == "telegram":
                has_token = self._has_secret(config, "bot_token", "bot_token_env")
                if transport != "polling":
                    errors.append("telegram: `transport` must stay `polling`.")
                if not has_token:
                    errors.append("telegram: `transport: polling` requires `bot_token` or `bot_token_env`.")
            elif name == "discord":
                has_token = self._has_secret(config, "bot_token", "bot_token_env")
                if transport != "gateway":
                    errors.append("discord: `transport` must stay `gateway`.")
                if not has_token:
                    errors.append("discord: `transport: gateway` requires `bot_token` or `bot_token_env`.")
                if not str(config.get("application_id") or "").strip():
                    warnings.append("discord: `application_id` is recommended for richer routing and future slash command support.")
            elif name == "slack":
                has_bot_token = self._has_secret(config, "bot_token", "bot_token_env")
                has_app_token = self._has_secret(config, "app_token", "app_token_env")
                if transport != "socket_mode":
                    errors.append("slack: `transport` must stay `socket_mode`.")
                if not has_bot_token:
                    errors.append("slack: `transport: socket_mode` requires `bot_token` or `bot_token_env`.")
                if not has_app_token:
                    errors.append("slack: `transport: socket_mode` requires `app_token` or `app_token_env`.")
            elif name == "weixin":
                if transport != "ilink_long_poll":
                    errors.append("weixin: `transport` must stay `ilink_long_poll`.")
                if not self._has_secret(config, "bot_token", "bot_token_env"):
                    errors.append("weixin: requires `bot_token` or `bot_token_env` after QR login.")
                if not str(config.get("account_id") or "").strip():
                    errors.append("weixin: requires `account_id` after QR login.")
                if not str(config.get("login_user_id") or "").strip():
                    warnings.append("weixin: `login_user_id` is empty. Save the scanner user id after QR login for easier diagnostics.")
            elif name == "feishu":
                has_app_id = bool(str(config.get("app_id") or "").strip())
                has_app_secret = self._has_secret(config, "app_secret", "app_secret_env")
                if transport != "long_connection":
                    errors.append("feishu: `transport` must stay `long_connection`.")
                if not has_app_id:
                    errors.append("feishu: `transport: long_connection` requires `app_id`.")
                if not has_app_secret:
                    errors.append("feishu: `transport: long_connection` requires `app_secret` or `app_secret_env`.")
            elif name == "whatsapp":
                if transport != "local_session":
                    errors.append("whatsapp: `transport` must stay `local_session`.")
                if not str(config.get("session_dir") or "").strip():
                    warnings.append("whatsapp: `transport: local_session` should set `session_dir` for local auth state.")
            elif name == "lingzhu":
                if transport != "openclaw_sse":
                    errors.append("lingzhu: `transport` must stay `openclaw_sse`.")
                if not str(config.get("local_host") or "").strip():
                    warnings.append("lingzhu: `local_host` is empty; DeepScientist will fall back to `127.0.0.1`.")
                if not self._has_secret(config, "auth_ak", "auth_ak_env"):
                    errors.append("lingzhu: requires `auth_ak` for Bearer authentication.")
                elif lingzhu_auth_ak_needs_rotation(self._secret(config, "auth_ak", "auth_ak_env")):
                    errors.append("lingzhu: `auth_ak` is still using the bundled example token; generate a new random AK before binding Rokid.")
                raw_gateway_port = str(config.get("gateway_port") or "").strip()
                normalized_port = lingzhu_gateway_port(config)
                if raw_gateway_port and str(normalized_port) != raw_gateway_port:
                    errors.append("lingzhu: `gateway_port` must be a valid TCP port between 1 and 65535.")
                raw_public_base_url = str(config.get("public_base_url") or "").strip()
                public_base_url = lingzhu_public_base_url(config)
                if raw_public_base_url and public_base_url is None:
                    errors.append("lingzhu: `public_base_url` must be a valid `http://` or `https://` URL when set.")
                elif raw_public_base_url and not public_base_url_looks_public(raw_public_base_url):
                    errors.append(
                        "lingzhu: `public_base_url` must be a public IP or public domain. `127.0.0.1`, `localhost`, and private network addresses cannot be registered on Rokid."
                    )
                raw_visible_progress_heartbeat_sec = str(
                    config.get("visible_progress_heartbeat_sec") or ""
                ).strip()
                if raw_visible_progress_heartbeat_sec:
                    try:
                        visible_progress_heartbeat_sec = int(raw_visible_progress_heartbeat_sec)
                    except ValueError:
                        errors.append(
                            "lingzhu: `visible_progress_heartbeat_sec` must be an integer between 5 and 120."
                        )
                    else:
                        if visible_progress_heartbeat_sec < 5 or visible_progress_heartbeat_sec > 120:
                            errors.append(
                                "lingzhu: `visible_progress_heartbeat_sec` must be an integer between 5 and 120."
                            )
                if not raw_public_base_url:
                    warnings.append(
                        "lingzhu: set `public_base_url` to a public IP or public domain before filling values into the Lingzhu platform."
                    )

        if preferred_connector and preferred_connector not in enabled_connectors:
            warnings.append(
                f"_routing: preferred connector `{preferred_connector}` is not currently enabled, so artifact delivery will ignore it until that connector is enabled."
            )
        if len(enabled_connectors) > 1 and routing_policy in {"primary_only", "primary_plus_local"} and not preferred_connector:
            warnings.append(
                "_routing: multiple connectors are enabled; set `primary_connector` to make artifact delivery deterministic."
            )

        return {
            "warnings": warnings,
            "errors": errors,
        }

    def _test_connectors_payload(self, payload: dict, *, live: bool, delivery_targets: dict[str, dict] | None = None) -> dict:
        items: list[dict] = []
        for name, raw_config in payload.items():
            if str(name).startswith("_"):
                continue
            if not isinstance(raw_config, dict):
                continue
            config = raw_config
            if not self._should_validate_connector(str(name), config):
                continue
            target = (delivery_targets or {}).get(name)
            items.append(self._test_single_connector(name, config, live=live, delivery_target=target if isinstance(target, dict) else None))
        return {
            "ok": all(item["ok"] for item in items) if items else True,
            "name": "connectors",
            "summary": "Connector test completed." if items else "No configured connectors to test.",
            "warnings": [],
            "errors": [],
            "items": items,
        }

    def _test_single_connector(self, name: str, config: dict, *, live: bool, delivery_target: dict[str, object] | None = None) -> dict:
        transport = infer_connector_transport(name, config)
        warnings: list[str] = []
        errors: list[str] = []
        details: dict[str, object] = {
            "mode": "gateway-direct" if name == "qq" else str(config.get("mode") or transport),
            "transport": transport,
        }

        try:
            if name == "telegram":
                token = self._secret(config, "bot_token", "bot_token_env")
                if transport == "polling" and live and token:
                    payload = self._http_json(f"https://api.telegram.org/bot{token}/getMe")
                    if not payload.get("ok", False):
                        errors.append("Telegram getMe did not return ok=true.")
                    else:
                        details["identity"] = (payload.get("result") or {}).get("username")
                elif transport == "polling" and not token:
                    errors.append("Telegram requires `bot_token` for polling.")
                else:
                    errors.append("Telegram transport must stay `polling`.")
            elif name == "slack":
                token = self._secret(config, "bot_token", "bot_token_env")
                app_token = self._secret(config, "app_token", "app_token_env")
                if transport == "socket_mode" and not app_token:
                    errors.append("Slack Socket Mode requires `app_token` or `app_token_env`.")
                if live and token:
                    payload = self._http_json("https://slack.com/api/auth.test", method="POST", headers={"Authorization": f"Bearer {token}"})
                    if not payload.get("ok", False):
                        errors.append(str(payload.get("error") or "Slack auth.test failed."))
                    else:
                        details["identity"] = payload.get("user")
                elif transport == "socket_mode" and not token:
                    errors.append("Slack requires `bot_token` for native runtime access.")
                elif transport != "socket_mode":
                    errors.append("Slack transport must stay `socket_mode`.")
            elif name == "discord":
                token = self._secret(config, "bot_token", "bot_token_env")
                if live and token:
                    payload = self._http_json("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bot {token}"})
                    if "id" not in payload:
                        errors.append(str(payload.get("message") or "Discord identity check failed."))
                    else:
                        details["identity"] = payload.get("username")
                elif transport == "gateway" and not token:
                    errors.append("Discord requires `bot_token` for gateway access.")
                elif transport != "gateway":
                    errors.append("Discord transport must stay `gateway`.")
            elif name == "feishu":
                app_id = str(config.get("app_id") or "").strip()
                app_secret = self._secret(config, "app_secret", "app_secret_env")
                if live and app_id and app_secret:
                    payload = self._http_json(
                        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                        method="POST",
                        headers={"Content-Type": "application/json; charset=utf-8"},
                        body={"app_id": app_id, "app_secret": app_secret},
                    )
                    if not payload.get("tenant_access_token"):
                        errors.append(str(payload.get("msg") or "Feishu tenant token exchange failed."))
                elif transport == "long_connection" and not (app_id and app_secret):
                    errors.append("Feishu requires `app_id` + `app_secret` for long-connection access.")
                elif transport != "long_connection":
                    errors.append("Feishu transport must stay `long_connection`.")
            elif name == "whatsapp":
                if transport == "local_session":
                    session_dir = str(config.get("session_dir") or "").strip()
                    details["session_dir"] = session_dir or None
                    if session_dir:
                        details["session_dir_exists"] = Path(session_dir).expanduser().exists()
                    if not session_dir:
                        warnings.append("WhatsApp local-session mode still needs a local `session_dir` for auth state.")
                else:
                    errors.append("WhatsApp transport must stay `local_session`.")
            elif name == "qq":
                details["transport"] = "gateway_direct"
                profile_results: list[dict[str, object]] = []
                profiles = list_qq_profiles(config)
                if not profiles:
                    errors.append("QQ requires at least one configured profile.")
                for profile in profiles:
                    profile_id = str(profile.get("profile_id") or "").strip() or "unknown"
                    app_id = str(profile.get("app_id") or "").strip()
                    app_secret = self._secret(profile, "app_secret", "app_secret_env")
                    profile_details: dict[str, object] = {
                        "profile_id": profile_id,
                        "label": qq_profile_label(profile),
                        "app_id": app_id or None,
                        "main_chat_id": str(profile.get("main_chat_id") or "").strip() or None,
                    }
                    if not app_id or not app_secret:
                        profile_details["ok"] = False
                        profile_details["error"] = "QQ requires `app_id` + `app_secret` for each configured profile."
                        errors.append(f"QQ profile `{profile_id}` is missing `app_id` or `app_secret`.")
                        profile_results.append(profile_details)
                        continue
                    if live:
                        token_payload = self._http_json(
                            "https://bots.qq.com/app/getAppAccessToken",
                            method="POST",
                            headers={"Content-Type": "application/json; charset=utf-8"},
                            body={"appId": app_id, "clientSecret": app_secret},
                        )
                        access_token = str(token_payload.get("access_token") or "").strip()
                        if not access_token:
                            message = str(token_payload.get("message") or "QQ access token exchange failed.")
                            errors.append(f"QQ profile `{profile_id}`: {message}")
                            profile_details["ok"] = False
                            profile_details["error"] = message
                            profile_results.append(profile_details)
                            continue
                        gateway_payload = self._http_json(
                            "https://api.sgroup.qq.com/gateway",
                            headers={"Authorization": f"QQBot {access_token}"},
                        )
                        gateway_url = str(gateway_payload.get("url") or "").strip()
                        if not gateway_url:
                            message = str(gateway_payload.get("message") or "QQ gateway probe failed.")
                            errors.append(f"QQ profile `{profile_id}`: {message}")
                            profile_details["ok"] = False
                            profile_details["error"] = message
                            profile_results.append(profile_details)
                            continue
                        profile_details["gateway_url"] = gateway_url
                        profile_details["token_expires_in"] = token_payload.get("expires_in")
                    profile_details["ok"] = True
                    profile_results.append(profile_details)
                details["profiles"] = profile_results
                if len(profile_results) == 1 and profile_results[0].get("ok"):
                    details["identity"] = profile_results[0].get("app_id")
                    details["gateway_url"] = profile_results[0].get("gateway_url")
                    details["token_expires_in"] = profile_results[0].get("token_expires_in")
            elif name == "weixin":
                details.update(
                    {
                        "base_url": normalize_weixin_base_url(config.get("base_url")),
                        "cdn_base_url": normalize_weixin_cdn_base_url(config.get("cdn_base_url")),
                        "account_id": str(config.get("account_id") or "").strip() or None,
                        "login_user_id": str(config.get("login_user_id") or "").strip() or None,
                    }
                )
                if transport != "ilink_long_poll":
                    errors.append("Weixin transport must stay `ilink_long_poll`.")
                if not self._has_secret(config, "bot_token", "bot_token_env"):
                    errors.append("Weixin requires `bot_token` after QR login.")
                if not str(config.get("account_id") or "").strip():
                    errors.append("Weixin requires `account_id` after QR login.")
                if live and not errors:
                    warnings.append(
                        "Weixin readiness is credential-based. Send one inbound Weixin message to populate `context_token` before testing outbound delivery."
                    )
            elif name == "lingzhu":
                details.update(self._lingzhu_snapshot_details(config))
                auth_ak = self._secret(config, "auth_ak", "auth_ak_env")
                if not auth_ak:
                    errors.append("Lingzhu requires `auth_ak` before it can accept Bearer-authenticated requests.")
                elif live:
                    health_probe = self._probe_lingzhu_health(config)
                    details["health_probe"] = health_probe
                    if not health_probe.get("ok", False):
                        errors.append(str(health_probe.get("message") or "Lingzhu health probe failed."))
                    else:
                        sse_probe = self._probe_lingzhu_sse(config)
                        details["sse_probe"] = sse_probe
                        if not sse_probe.get("ok", False):
                            errors.append(str(sse_probe.get("message") or "Lingzhu SSE probe failed."))
            else:
                warnings.append(f"No dedicated system test exists for connector `{name}`.")
        except Exception as exc:  # pragma: no cover - network-dependent
            errors.append(str(exc))

        if delivery_target and name != "lingzhu":
            delivery_message = str(delivery_target.get("text") or "").strip()
            chat_type = str(delivery_target.get("chat_type") or "direct").strip().lower()
            chat_id = str(delivery_target.get("chat_id") or "").strip()
            default_chat_id = ""
            if name == "qq":
                profiles = list_qq_profiles(config)
                if len(profiles) == 1:
                    default_chat_id = str(profiles[0].get("main_chat_id") or "").strip()
            if not default_chat_id:
                default_chat_id = self._connector_recent_chat_id(name, chat_type)
            if not chat_id and default_chat_id:
                chat_id = default_chat_id
            delivery_requested = bool(chat_id or delivery_message)
            details["delivery_target"] = {
                "chat_type": chat_type,
                "chat_id": chat_id or None,
            }
            if default_chat_id and chat_id == default_chat_id and not str(delivery_target.get("chat_id") or "").strip():
                details["delivery_target"]["used_default_target"] = True
            if not delivery_requested:
                details["delivery_target"]["configured"] = False
            elif chat_type not in {"direct", "group"}:
                warnings.append("Delivery test chat_type must be `direct` or `group`.")
            elif not chat_id:
                if name == "qq":
                    warnings.append(
                        "QQ readiness is healthy, but no OpenID has been learned yet. Save credentials, then send one private QQ message so DeepScientist can auto-detect and save the `openid`."
                    )
                else:
                    warnings.append("Delivery test is configured, but the target chat id is empty.")
            elif errors:
                warnings.append("Skipping live delivery because the connector readiness check still has errors.")
            else:
                from ..bridges import get_connector_bridge

                bridge = get_connector_bridge(name)
                if bridge is None:
                    warnings.append(f"No connector bridge is registered for `{name}`.")
                else:
                    outbound = {
                        "conversation_id": f"{name}:{chat_type}:{chat_id}",
                        "text": delivery_message or self._default_connector_probe_message(name),
                        "kind": "test_message",
                        "importance": "low",
                        "response_phase": "settings_probe",
                    }
                    delivery = bridge.deliver(outbound, config)
                    if delivery is None:
                        warnings.append(
                            "The current connector mode cannot actively send a test message yet. Finish the native direct setup first."
                        )
                    else:
                        details["delivery"] = delivery
                        if not delivery.get("ok", False):
                            errors.append("Live test message delivery failed.")

        return {
            "name": name,
            "ok": len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "details": details,
        }

    def _connector_recent_chat_id(self, connector_name: str, chat_type: str) -> str:
        state = read_json(self.home / "logs" / "connectors" / connector_name / "state.json", {})
        if not isinstance(state, dict):
            return ""
        conversation_id = str(state.get("last_conversation_id") or "").strip()
        parts = conversation_id.split(":", 2)
        if len(parts) != 3:
            return ""
        if parts[0] != connector_name or parts[1] != chat_type:
            return ""
        return parts[2]

    def _default_connector_probe_message(self, connector_name: str) -> str:
        config = self.load_named("config")
        locale = str(config.get("default_locale") or "").lower()
        if locale.startswith("zh"):
            return f"老师您好，这是一条来自 DeepScientist 设置页的 {connector_name} 连接测试消息。若您收到这条消息，说明当前绑定与发送链路已经打通。"
        return (
            f"Hello — this is a DeepScientist {connector_name} settings test message. "
            "If you received it, the connector binding and outbound delivery path are working."
        )

    @staticmethod
    def _codex_should_inherit_model(model: object) -> bool:
        normalized = str(model or "").strip().lower()
        return normalized in {"", "inherit", "default", "codex-default"}

    @staticmethod
    def _codex_requested_model(config: dict) -> str:
        raw_model = config.get("model")
        if raw_model is None:
            return "gpt-5.4"
        return str(raw_model).strip()

    @staticmethod
    def _codex_effective_model(config: dict) -> str:
        requested = ConfigManager._codex_requested_model(config)
        profile = ConfigManager._codex_profile_name(config)
        if profile and not ConfigManager._codex_should_inherit_model(requested):
            return "inherit"
        return requested

    @staticmethod
    def _codex_profile_name(config: dict) -> str:
        raw_profile = config.get("profile")
        if raw_profile is None:
            return ""
        return str(raw_profile).strip()

    @staticmethod
    def _codex_runner_env(config: dict) -> dict[str, str]:
        raw_env = config.get("env")
        if not isinstance(raw_env, dict):
            return ensure_utf8_subprocess_env({})
        resolved: dict[str, str] = {}
        for key, value in raw_env.items():
            env_key = str(key or "").strip()
            if not env_key or value is None:
                continue
            env_value = str(value)
            if env_value == "":
                continue
            resolved[env_key] = env_value
        return ensure_utf8_subprocess_env(resolved)

    def _prepare_codex_probe_home(
        self,
        *,
        config_dir: str,
        profile: str,
    ) -> tuple[str, str | None, tempfile.TemporaryDirectory[str] | None]:
        expanded = Path(config_dir).expanduser()
        config_path = expanded / "config.toml"
        if not config_path.exists():
            return str(expanded), None, None

        original_text = read_text(config_path)
        adapted_text, warning = adapt_profile_only_provider_config(original_text, profile=profile)
        if warning is None:
            return str(expanded), None, None

        temp_home = tempfile.TemporaryDirectory(prefix="ds-codex-probe-")
        temp_root = Path(temp_home.name)
        materialize_codex_runtime_home(
            source_home=expanded,
            target_home=temp_root,
            profile=profile,
        )
        write_text(temp_root / "config.toml", adapted_text)
        return str(temp_root), warning, temp_home

    def _codex_missing_binary_guidance(self, config: dict) -> list[str]:
        profile = self._codex_profile_name(config)
        guidance = [
            "Run `npm install -g @researai/deepscientist` again so the bundled Codex dependency is installed.",
            "If `codex` is still missing, install it explicitly with `npm install -g @openai/codex`.",
        ]
        if profile:
            guidance.extend(
                [
                    f"Then verify `codex --profile {profile}` works from a terminal before starting DeepScientist.",
                    "If that profile uses a custom provider, make sure its API key and Base URL are configured in Codex first.",
                ]
            )
        else:
            guidance.append("Run `codex login` (or just `codex`) once and finish authentication before starting DeepScientist.")
        guidance.append(
            "If you use a custom Codex path, either set `runners.codex.binary` or launch with `ds --codex /absolute/path/to/codex`."
        )
        return guidance

    @staticmethod
    def _provider_profile_probe_hints(metadata: dict[str, object]) -> list[str]:
        base_url = str(metadata.get("base_url") or "").strip().lower()
        model = str(metadata.get("model") or "").strip().lower()
        provider = str(metadata.get("provider") or "").strip().lower()
        if "dashscope.aliyuncs.com" not in base_url and "bailian" not in provider and "qwen" not in model:
            return []
        if "coding.dashscope.aliyuncs.com" not in base_url:
            return [
                "Alibaba Bailian's generic DashScope / Qwen platform API is not supported by the Codex-backed DeepScientist path.",
                "If you want to use Qwen here, switch the profile to the Bailian Coding Plan endpoint: `https://coding.dashscope.aliyuncs.com/v1`.",
            ]
        return [
            "For Qwen on Alibaba Bailian, only the Coding Plan endpoint is supported here; do not switch back to the generic Bailian / DashScope Qwen API.",
        ]

    @staticmethod
    def _local_provider_probe_hints(metadata: dict[str, object]) -> list[str]:
        base_url = str(metadata.get("base_url") or "").strip()
        wire_api = str(metadata.get("wire_api") or "").strip().lower()
        requires_openai_auth = metadata.get("requires_openai_auth")
        if not base_url:
            return []
        is_local_provider = provider_base_url_looks_local(base_url)
        if requires_openai_auth is not False and not is_local_provider:
            return []
        hints = [
            f"Verify the local provider directly: `curl {base_url}/models`.",
            f"Then verify the Responses API explicitly: `curl {base_url}/responses ...`.",
            "Latest Codex CLI requires `wire_api = \"responses\"`; chat-only provider configs are no longer accepted.",
            "If `/v1/chat/completions` works but `/v1/responses` fails, that backend is not currently compatible with the latest Codex runner.",
            "If the backend is chat-only and you still want to test it through Codex, try `@openai/codex@0.57.0` with top-level `model_provider` / `model` plus `wire_api = \"chat\"`.",
            "For local model backends, vLLM is the safest path. Ollama only works when its `/v1/responses` endpoint works; chat-only SGLang deployments will fail with the latest Codex.",
        ]
        if requires_openai_auth is not False:
            hints.insert(
                0,
                "For local or self-hosted providers, add `requires_openai_auth = false` so DeepScientist can remove conflicting `OPENAI_*` auth variables.",
            )
        if not wire_api:
            hints.insert(0, "Your current provider config does not declare `wire_api`; set `wire_api = \"responses\"` first.")
        elif wire_api != "responses":
            hints.insert(0, f"Your current provider config uses `wire_api = \"{wire_api}\"`; switch it to `wire_api = \"responses\"` first.")
        return hints

    @staticmethod
    def _missing_provider_env_guidance(
        *,
        profile: str,
        env_key: str,
        metadata: dict[str, object],
    ) -> list[str]:
        guidance = [
            f"Set `runners.codex.env.{env_key}` in `~/DeepScientist/config/runners.yaml`, or export `{env_key}` before launching `ds`.",
        ]
        if provider_base_url_looks_local(str(metadata.get("base_url") or "").strip()):
            guidance.append(
                f"If `{env_key}` is only a placeholder for a local OpenAI-compatible backend, any non-empty value such as `1234` is usually enough."
            )
            if metadata.get("requires_openai_auth") is not False:
                guidance.append(
                    "Also add `requires_openai_auth = false` to that local provider profile so DeepScientist can remove conflicting `OPENAI_*` auth variables."
                )
        guidance.append(
            f"Before retrying DeepScientist, run a real request such as `codex exec --profile {profile} --json --cd /tmp --skip-git-repo-check -` and verify it returns `HELLO`."
        )
        return guidance

    @staticmethod
    def _chat_wire_probe_version_block(
        metadata: dict[str, object],
        *,
        resolved_binary: str,
    ) -> tuple[tuple[int, int, int] | None, dict[str, object] | None]:
        wire_api = str(metadata.get("wire_api") or "").strip().lower()
        if wire_api != "chat":
            return None, None
        detected_version = codex_cli_version(str(resolved_binary or ""))
        required_version = chat_wire_compatible_codex_version()
        if detected_version == required_version:
            return detected_version, None
        required_text = format_codex_cli_version(required_version)
        detected_text = format_codex_cli_version(detected_version)
        errors = [
            "This provider uses `wire_api = \"chat\"`, but DeepScientist only probes chat-mode providers with `codex-cli 0.57.0`.",
        ]
        if detected_text:
            errors.append(f"Detected Codex CLI version: `{detected_text}`.")
        else:
            errors.append("DeepScientist could not determine the active Codex CLI version from the configured binary.")
        guidance = [
            "Install `npm install -g @openai/codex@0.57.0`, or point DeepScientist at a dedicated `0.57.0` binary with `ds --codex /absolute/path/to/codex`.",
            "If you want to stay on a newer Codex CLI, switch the provider/backend to `wire_api = \"responses\"` instead.",
            "For chat-mode fallback configs, keep the compatible top-level `model_provider` / `model` entries in `~/.codex/config.toml`.",
        ]
        return (
            detected_version,
            {
                "summary": f"Codex startup probe blocked by chat-mode provider compatibility. Required Codex CLI: `{required_text}`.",
                "errors": errors,
                "guidance": guidance,
            },
        )

    def _codex_probe_failure_guidance(self, config: dict) -> tuple[list[str], list[str]]:
        profile = self._codex_profile_name(config)
        config_dir = str(config.get("config_dir") or "~/.codex").strip()
        metadata = active_provider_metadata_from_home(config_dir, profile=profile or None) if config_dir else {}
        if profile:
            provider_hints = self._provider_profile_probe_hints(metadata)
            local_hints = self._local_provider_probe_hints(metadata)
            return (
                [
                    f"Codex profile `{profile}` did not complete the startup hello probe successfully.",
                ],
                [
                    f"Run `codex exec --profile {profile} --json --cd /tmp --skip-git-repo-check -` in a terminal and confirm that a real `HELLO` request succeeds.",
                    "If the profile uses a custom provider, make sure its API key, Base URL, and model configuration are available to Codex.",
                    "If the provider expects the model from the Codex profile itself, set `model: inherit` in `~/DeepScientist/config/runners.yaml`.",
                    *provider_hints,
                    *local_hints,
                    "Then run `ds doctor` and start DeepScientist again.",
                ],
            )
        return (
            [
                "Run `codex login` (or just `codex`) once and complete login before starting DeepScientist.",
            ],
            [
                "Run `codex login` (or just `codex`) in a terminal and complete login or first-run setup.",
                "If `codex` is missing, install it explicitly with `npm install -g @openai/codex`.",
                "If the configured model is not available to your Codex account, update `~/DeepScientist/config/runners.yaml` and try again.",
                "Then run `ds doctor` and start DeepScientist again.",
            ],
        )

    @staticmethod
    def _codex_model_unavailable(stdout_text: str, stderr_text: str) -> bool:
        haystack = f"{stdout_text}\n{stderr_text}".lower()
        markers = [
            "unknown model",
            "invalid model",
            "model not found",
            "unsupported model",
            "model is not available",
            "not authorized to use model",
            "you do not have access",
            "access to model",
            "model access",
            "unrecognized model",
        ]
        return any(marker in haystack for marker in markers)

    def _build_codex_probe_command(
        self,
        *,
        resolved_binary: str,
        profile: str,
        requested_model: str,
        approval_policy: str,
        reasoning_effort: str | None,
        sandbox_mode: str,
    ) -> list[str]:
        command = [
            resolved_binary,
            "--search",
        ]
        if profile:
            command.extend(["--profile", profile])
        command.extend(
            [
            "exec",
            "--json",
            "--cd",
            str(repo_root()),
            "--skip-git-repo-check",
            ]
        )
        if not self._codex_should_inherit_model(requested_model):
            command.extend(["--model", requested_model])
        if approval_policy:
            command.extend(["-c", f'approval_policy="{approval_policy}"'])
        if reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
        if sandbox_mode:
            command.extend(["--sandbox", sandbox_mode])
        command.append("-")
        return command

    def _persist_codex_model_inherit(self, requested_model: object) -> None:
        normalized_requested_model = str(requested_model or "").strip()
        if not normalized_requested_model:
            return
        runners = self.load_named("runners")
        codex = runners.get("codex") if isinstance(runners.get("codex"), dict) else None
        if not isinstance(codex, dict):
            return
        current_model = str(codex.get("model") or "").strip()
        if current_model != normalized_requested_model:
            return
        codex["model"] = "inherit"
        runners["codex"] = codex
        self.save_named_payload("runners", runners)

    def _probe_codex_runner(self, config: dict) -> dict:
        config = apply_codex_runtime_overrides(config)
        checked_at = utc_now()
        binary = str(config.get("binary") or "codex").strip() or "codex"
        resolved_binary = resolve_runner_binary(binary, runner_name="codex")
        profile = self._codex_profile_name(config)
        requested_model = self._codex_requested_model(config)
        effective_model = self._codex_effective_model(config)
        raw_reasoning_effort = config.get("model_reasoning_effort")
        requested_reasoning_effort = (
            str(raw_reasoning_effort).strip()
            if raw_reasoning_effort is not None and str(raw_reasoning_effort).strip()
            else ("xhigh" if raw_reasoning_effort is None else None)
        )
        reasoning_effort, reasoning_effort_warning = normalize_codex_reasoning_effort(
            requested_reasoning_effort,
            resolved_binary=resolved_binary,
        )
        details: dict[str, object] = {
            "binary": binary,
            "resolved_binary": resolved_binary,
            "config_dir": str(config.get("config_dir") or "~/.codex"),
            "profile": profile,
            "model": effective_model or "inherit",
            "requested_model": requested_model or "inherit",
            "effective_model": effective_model or "inherit",
            "approval_policy": str(config.get("approval_policy") or "on-request"),
            "sandbox_mode": str(config.get("sandbox_mode") or "workspace-write"),
            "reasoning_effort": reasoning_effort,
            "requested_reasoning_effort": requested_reasoning_effort,
            "model_fallback_attempted": False,
            "model_fallback_used": False,
            "checked_at": checked_at,
        }
        if not resolved_binary:
            return {
                "ok": False,
                "summary": "Codex probe failed before execution.",
                "warnings": [],
                "errors": [
                    "Codex binary is not installed or could not be resolved.",
                    "DeepScientist could not resolve the bundled or configured `codex` CLI.",
                ],
                "details": details,
                "guidance": self._codex_missing_binary_guidance(config),
            }

        approval_policy = str(config.get("approval_policy") or "on-request").strip()
        sandbox_mode = str(config.get("sandbox_mode") or "workspace-write").strip()

        env = ensure_utf8_subprocess_env(os.environ.copy())
        env.update(self._claude_auth_runner_env(self._codex_runner_env(config)))
        config_dir = str(config.get("config_dir") or "~/.codex").strip()
        probe_home_handle: tempfile.TemporaryDirectory[str] | None = None
        compatibility_warnings: list[str] = []
        if config_dir:
            prepared_home, profile_config_warning, probe_home_handle = self._prepare_codex_probe_home(
                config_dir=config_dir,
                profile=profile,
            )
            env["CODEX_HOME"] = prepared_home
            if profile_config_warning:
                compatibility_warnings.append(profile_config_warning)
        metadata = active_provider_metadata_from_home(env.get("CODEX_HOME") or config_dir, profile=profile or None)
        if metadata.get("requires_openai_auth") is False:
            env.pop("OPENAI_API_KEY", None)
            env.pop("OPENAI_BASE_URL", None)
        configured_provider_env_key = missing_provider_env_key(metadata, env)
        details["provider_env_key"] = str(metadata.get("env_key") or "").strip() or None
        details["provider_env_missing"] = bool(configured_provider_env_key)
        details["provider_wire_api"] = str(metadata.get("wire_api") or "").strip() or None
        detected_codex_version, chat_wire_block = self._chat_wire_probe_version_block(
            metadata,
            resolved_binary=resolved_binary,
        )
        if detected_codex_version is not None:
            details["codex_cli_version"] = format_codex_cli_version(detected_codex_version) or None
        prompt = "Reply with exactly HELLO."
        if reasoning_effort_warning:
            compatibility_warnings.append(reasoning_effort_warning)
        if profile and effective_model == "inherit" and not self._codex_should_inherit_model(requested_model):
            compatibility_warnings.append(
                f"Codex profile `{profile}` is provider-backed. DeepScientist is probing it with `model: inherit`."
            )
        base_warnings: list[str] = list(compatibility_warnings)
        if chat_wire_block is not None:
            return {
                "ok": False,
                "summary": str(chat_wire_block["summary"]),
                "warnings": base_warnings,
                "errors": list(chat_wire_block["errors"]),
                "details": details,
                "guidance": list(chat_wire_block["guidance"]),
            }

        def run_probe_once(model_for_command: str) -> tuple[list[str], subprocess.CompletedProcess[str] | None, subprocess.TimeoutExpired | None]:
            command = self._build_codex_probe_command(
                resolved_binary=resolved_binary,
                profile=profile,
                requested_model=model_for_command,
                approval_policy=approval_policy,
                reasoning_effort=reasoning_effort,
                sandbox_mode=sandbox_mode,
            )
            try:
                result = subprocess.run(
                    command,
                    input=prompt,
                    cwd=str(repo_root()),
                    env=env,
                    capture_output=True,
                    timeout=90,
                    check=False,
                    **utf8_text_subprocess_kwargs(),
                )
            except subprocess.TimeoutExpired as exc:
                return command, None, exc
            return command, result, None

        command, result, timeout_error = run_probe_once(effective_model)
        if timeout_error is not None:
            details.update(
                {
                    "exit_code": None,
                    "stdout_excerpt": self._compact_probe_text(timeout_error.stdout or ""),
                    "stderr_excerpt": self._compact_probe_text(timeout_error.stderr or ""),
                    "probe_command": command,
                }
            )
            return {
                "ok": False,
                "summary": "Codex startup probe timed out.",
                "warnings": base_warnings,
                "errors": [
                    "Codex did not answer the startup hello probe within 90 seconds.",
                    *self._codex_probe_failure_guidance(config)[0],
                ],
                "details": details,
                "guidance": [
                    *self._codex_probe_failure_guidance(config)[1],
                    "If `codex` is missing on PATH, install it explicitly with `npm install -g @openai/codex`.",
                    "Confirm the configured model is available to your Codex setup. DeepScientist currently probes Codex with the configured runner model first.",
                ],
            }

        assert result is not None
        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        hello_seen = "HELLO" in stdout_text.upper()
        ok = result.returncode == 0 and hello_seen
        fallback_warning: str | None = None
        if (
            not ok
            and not self._codex_should_inherit_model(requested_model)
            and self._codex_model_unavailable(stdout_text, stderr_text)
        ):
            details["model_fallback_attempted"] = True
            fallback_command, fallback_result, fallback_timeout = run_probe_once("inherit")
            details["initial_probe_command"] = command
            details["initial_exit_code"] = result.returncode
            details["initial_stdout_excerpt"] = self._compact_probe_text(stdout_text)
            details["initial_stderr_excerpt"] = self._compact_probe_text(stderr_text)
            details["fallback_probe_command"] = fallback_command
            if fallback_timeout is None and fallback_result is not None:
                fallback_stdout_text = (fallback_result.stdout or "").strip()
                fallback_stderr_text = (fallback_result.stderr or "").strip()
                fallback_hello_seen = "HELLO" in fallback_stdout_text.upper()
                fallback_ok = fallback_result.returncode == 0 and fallback_hello_seen
                details["fallback_exit_code"] = fallback_result.returncode
                details["fallback_stdout_excerpt"] = self._compact_probe_text(fallback_stdout_text)
                details["fallback_stderr_excerpt"] = self._compact_probe_text(fallback_stderr_text)
                if fallback_ok:
                    details.update(
                        {
                            "exit_code": fallback_result.returncode,
                            "stdout_excerpt": self._compact_probe_text(fallback_stdout_text),
                            "stderr_excerpt": self._compact_probe_text(fallback_stderr_text),
                            "probe_command": fallback_command,
                            "effective_model": "inherit",
                            "model_fallback_used": True,
                        }
                    )
                    fallback_warning = (
                        f"Configured Codex model `{requested_model}` is not available. "
                        "DeepScientist fell back to the current Codex default model."
                    )
                    return {
                        "ok": True,
                        "summary": "Codex startup probe completed with Codex default model fallback.",
                        "warnings": [*base_warnings, fallback_warning],
                        "errors": [],
                        "details": details,
                        "guidance": [
                            "DeepScientist switched the Codex runner model to `inherit` so future runs keep using the current Codex default model.",
                        ],
                    }
            else:
                details["fallback_exit_code"] = None
                details["fallback_stdout_excerpt"] = self._compact_probe_text((fallback_timeout.stdout if fallback_timeout else "") or "")
                details["fallback_stderr_excerpt"] = self._compact_probe_text((fallback_timeout.stderr if fallback_timeout else "") or "")

        details.update(
            {
                "exit_code": result.returncode,
                "stdout_excerpt": self._compact_probe_text(stdout_text),
                "stderr_excerpt": self._compact_probe_text(stderr_text),
                "probe_command": command,
            }
        )
        warnings: list[str] = list(base_warnings)
        errors: list[str] = []
        if not ok:
            errors.append("Codex did not complete the startup hello probe successfully.")
            if result.returncode == 0 and not hello_seen:
                errors.append("Codex responded, but the reply did not contain the expected `HELLO` marker.")
            if stderr_text:
                warnings.append("Codex returned stderr during the startup probe.")
            if details.get("model_fallback_attempted") and not details.get("model_fallback_used"):
                warnings.append("DeepScientist also tried the current Codex default model, but that fallback probe did not succeed.")
            errors.extend(self._codex_probe_failure_guidance(config)[0])
        missing_env_key = missing_provider_env_key_from_text(stdout_text, stderr_text) or configured_provider_env_key
        failure_guidance = self._codex_probe_failure_guidance(config)[1]
        if not ok and missing_env_key and profile:
            errors.append(
                f"Codex profile `{profile}` requires environment variable `{missing_env_key}`, but DeepScientist did not receive it."
            )
            failure_guidance = [
                *self._missing_provider_env_guidance(
                    profile=profile,
                    env_key=missing_env_key,
                    metadata=metadata,
                ),
                *failure_guidance,
            ]
        return {
            "ok": ok,
            "summary": "Codex startup probe completed." if ok else "Codex startup probe failed.",
            "warnings": warnings,
            "errors": errors,
            "details": details,
            "guidance": [] if ok else failure_guidance,
        }

    def _persist_runner_bootstrap_result(self, runner_name: str, result: dict) -> None:
        normalized_runner = str(runner_name or "codex").strip().lower() or "codex"
        config = self.load_named_normalized("config")
        bootstrap = config.get("bootstrap") if isinstance(config.get("bootstrap"), dict) else {}
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        runner_readiness = bootstrap.get("runner_readiness") if isinstance(bootstrap.get("runner_readiness"), dict) else {}
        runner_readiness[normalized_runner] = {
            "ready": bool(result.get("ok")),
            "last_checked_at": details.get("checked_at") or utc_now(),
            "last_result": {
                "ok": bool(result.get("ok")),
                "summary": result.get("summary"),
                "warnings": list(result.get("warnings") or []),
                "errors": list(result.get("errors") or []),
                "guidance": list(result.get("guidance") or []),
                "binary": details.get("binary"),
                "resolved_binary": details.get("resolved_binary"),
                "model": details.get("model"),
                "requested_model": details.get("requested_model"),
                "effective_model": details.get("effective_model"),
                "exit_code": details.get("exit_code"),
                "stdout_excerpt": details.get("stdout_excerpt"),
                "stderr_excerpt": details.get("stderr_excerpt"),
                "profile": details.get("profile"),
                "permission_mode": details.get("permission_mode"),
                "variant": details.get("variant"),
            },
        }
        bootstrap["runner_readiness"] = runner_readiness
        if normalized_runner == "codex":
            codex_state = runner_readiness["codex"]
            bootstrap["codex_ready"] = bool(codex_state.get("ready"))
            bootstrap["codex_last_checked_at"] = codex_state.get("last_checked_at")
            bootstrap["codex_last_result"] = codex_state.get("last_result")
        config["bootstrap"] = bootstrap
        self.save_named_payload("config", config)
        if normalized_runner == "codex" and bool(result.get("ok")) and bool(details.get("model_fallback_used")):
            self._persist_codex_model_inherit(details.get("requested_model"))

    def _persist_codex_bootstrap_result(self, result: dict) -> None:
        self._persist_runner_bootstrap_result("codex", result)

    @staticmethod
    def _copy_runner_file_if_exists(source: Path, target: Path) -> None:
        if not source.exists() or not source.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    @staticmethod
    def _claude_auth_runner_env(env: dict[str, str]) -> dict[str, str]:
        resolved = dict(env)
        auth_token = str(resolved.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
        api_key = str(resolved.get("ANTHROPIC_API_KEY") or "").strip()
        if auth_token and not api_key:
            resolved["ANTHROPIC_API_KEY"] = auth_token
        return resolved

    def _runner_missing_binary_guidance(self, runner_name: str, config: dict) -> list[str]:
        normalized_runner = str(runner_name or "").strip().lower()
        binary = str(config.get("binary") or normalized_runner).strip() or normalized_runner
        if normalized_runner == "codex":
            return self._codex_missing_binary_guidance(config)
        if normalized_runner == "claude":
            return [
                f"Install Claude Code and make sure `{binary} --version` works in the current shell.",
                "If Claude Code is already installed elsewhere, set `runners.claude.binary` to the absolute path.",
            ]
        if normalized_runner == "opencode":
            return [
                f"Install OpenCode and make sure `{binary} --version` works in the current shell.",
                "If OpenCode is already installed elsewhere, set `runners.opencode.binary` to the absolute path.",
            ]
        if normalized_runner == "kimi":
            return [
                f"Install Kimi Code and make sure `{binary} --version` works in the current shell.",
                "Run `kimi login` (or just `kimi`) once to complete the first-run login flow.",
                "If Kimi Code uses a custom home, point `runners.kimi.config_dir` at the correct `~/.kimi`-style directory that contains `config.toml` and `mcp.json`.",
            ]
        return [f"Install runner `{normalized_runner}` and ensure `{binary}` is on PATH."]

    def _probe_claude_runner(self, config: dict) -> dict:
        checked_at = utc_now()
        binary = str(config.get("binary") or "claude").strip() or "claude"
        resolved_binary = resolve_runner_binary(binary, runner_name="claude")
        requested_model = str(config.get("model") or "inherit").strip() or "inherit"
        permission_mode = str(config.get("permission_mode") or "bypassPermissions").strip() or "bypassPermissions"
        details: dict[str, object] = {
            "binary": binary,
            "resolved_binary": resolved_binary,
            "config_dir": str(config.get("config_dir") or "~/.claude"),
            "model": requested_model,
            "requested_model": requested_model,
            "effective_model": requested_model,
            "permission_mode": permission_mode,
            "checked_at": checked_at,
        }
        if not resolved_binary:
            return {
                "ok": False,
                "summary": "Claude Code startup probe failed before execution.",
                "warnings": [],
                "errors": [f"Claude Code binary `{binary}` is not available."],
                "details": details,
                "guidance": self._runner_missing_binary_guidance("claude", config),
            }
        env = ensure_utf8_subprocess_env(os.environ.copy())
        env.update(self._codex_runner_env(config))
        temp_home_handle = tempfile.TemporaryDirectory()
        try:
            temp_home = Path(temp_home_handle.name)
            source_home = Path(str(config.get("config_dir") or Path.home() / ".claude")).expanduser()
            for filename in (".credentials.json", "settings.json", "settings.local.json"):
                self._copy_runner_file_if_exists(source_home / filename, temp_home / filename)
            env["CLAUDE_CONFIG_DIR"] = str(temp_home)
            command = [
                resolved_binary,
                "-p",
                "--input-format",
                "text",
                "--output-format",
                "json",
                "--add-dir",
                str(repo_root()),
                "--no-session-persistence",
                "--permission-mode",
                permission_mode,
                "--tools",
                "",
            ]
            if requested_model.lower() not in {"", "inherit", "default", "claude-default"}:
                command.extend(["--model", requested_model])
            result = subprocess.run(
                command,
                input="Reply with exactly HELLO.",
                cwd=str(repo_root()),
                env=env,
                capture_output=True,
                timeout=90,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            details.update({
                "exit_code": None,
                "stdout_excerpt": self._compact_probe_text(exc.stdout or ""),
                "stderr_excerpt": self._compact_probe_text(exc.stderr or ""),
            })
            return {
                "ok": False,
                "summary": "Claude Code startup probe timed out.",
                "warnings": [],
                "errors": ["Claude Code did not answer the startup probe within 90 seconds."],
                "details": details,
                "guidance": [
                    "Run a small headless Claude Code request manually and confirm it can answer before starting DeepScientist.",
                ],
            }
        finally:
            temp_home_handle.cleanup()
        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        ok = result.returncode == 0 and "HELLO" in f"{stdout_text}\n{stderr_text}".upper()
        details.update({
            "exit_code": result.returncode,
            "stdout_excerpt": self._compact_probe_text(stdout_text),
            "stderr_excerpt": self._compact_probe_text(stderr_text),
            "probe_command": command,
        })
        return {
            "ok": ok,
            "summary": "Claude Code startup probe completed." if ok else "Claude Code startup probe failed.",
            "warnings": ["Claude Code returned stderr during the startup probe."] if stderr_text else [],
            "errors": [] if ok else ["Claude Code did not complete the startup hello probe successfully."],
            "details": details,
            "guidance": [] if ok else [
                "Run `claude -p --output-format json --tools ""` manually and confirm it returns `HELLO`.",
                "If Claude Code uses a custom account or credential path, point `runners.claude.config_dir` at the correct home.",
            ],
        }

    def _probe_opencode_runner(self, config: dict) -> dict:
        checked_at = utc_now()
        binary = str(config.get("binary") or "opencode").strip() or "opencode"
        resolved_binary = resolve_runner_binary(binary, runner_name="opencode")
        requested_model = str(config.get("model") or "inherit").strip() or "inherit"
        variant = str(config.get("variant") or "").strip() or None
        permission_mode = str(config.get("permission_mode") or "allow").strip().lower() or "allow"
        details: dict[str, object] = {
            "binary": binary,
            "resolved_binary": resolved_binary,
            "config_dir": str(config.get("config_dir") or "~/.config/opencode"),
            "model": requested_model,
            "requested_model": requested_model,
            "effective_model": requested_model,
            "variant": variant,
            "permission_mode": permission_mode,
            "checked_at": checked_at,
        }
        if not resolved_binary:
            return {
                "ok": False,
                "summary": "OpenCode startup probe failed before execution.",
                "warnings": [],
                "errors": [f"OpenCode binary `{binary}` is not available."],
                "details": details,
                "guidance": self._runner_missing_binary_guidance("opencode", config),
            }
        env = ensure_utf8_subprocess_env(os.environ.copy())
        env.update(self._codex_runner_env(config))
        temp_home_handle = tempfile.TemporaryDirectory()
        try:
            temp_home = Path(temp_home_handle.name)
            config_root = temp_home / ".config" / "opencode"
            config_root.mkdir(parents=True, exist_ok=True)
            source_root = Path(str(config.get("config_dir") or Path.home() / ".config" / "opencode")).expanduser()
            self._copy_runner_file_if_exists(source_root / "opencode.json", config_root / "opencode.json")
            env["HOME"] = str(temp_home)
            env["XDG_CONFIG_HOME"] = str(temp_home / ".config")
            command = [
                resolved_binary,
                "run",
                "--format",
                "json",
                "--pure",
                "--dir",
                str(repo_root()),
            ]
            if requested_model.lower() not in {"", "inherit", "default", "opencode-default"}:
                command.extend(["--model", requested_model])
            if variant:
                command.extend(["--variant", variant])
            command.append("Reply with exactly HELLO")
            result = subprocess.run(
                command,
                cwd=str(repo_root()),
                env=env,
                capture_output=True,
                timeout=90,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            details.update({
                "exit_code": None,
                "stdout_excerpt": self._compact_probe_text(exc.stdout or ""),
                "stderr_excerpt": self._compact_probe_text(exc.stderr or ""),
            })
            return {
                "ok": False,
                "summary": "OpenCode startup probe timed out.",
                "warnings": [],
                "errors": ["OpenCode did not answer the startup probe within 90 seconds."],
                "details": details,
                "guidance": [
                    "Run a small `opencode run --format json` request manually and confirm it can answer before starting DeepScientist.",
                ],
            }
        finally:
            temp_home_handle.cleanup()
        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        ok = result.returncode == 0 and "HELLO" in f"{stdout_text}\n{stderr_text}".upper()
        details.update({
            "exit_code": result.returncode,
            "stdout_excerpt": self._compact_probe_text(stdout_text),
            "stderr_excerpt": self._compact_probe_text(stderr_text),
            "probe_command": command,
        })
        return {
            "ok": ok,
            "summary": "OpenCode startup probe completed." if ok else "OpenCode startup probe failed.",
            "warnings": ["OpenCode returned stderr during the startup probe."] if stderr_text else [],
            "errors": [] if ok else ["OpenCode did not complete the startup hello probe successfully."],
            "details": details,
            "guidance": [] if ok else [
                "Run `opencode run --format json \"Reply with exactly HELLO\"` manually and confirm it succeeds.",
                "If OpenCode uses a custom config root, point `runners.opencode.config_dir` at the correct directory.",
            ],
        }

    def _probe_kimi_runner(self, config: dict) -> dict:
        checked_at = utc_now()
        binary = str(config.get("binary") or "kimi").strip() or "kimi"
        resolved_binary = resolve_runner_binary(binary, runner_name="kimi")
        requested_model = str(config.get("model") or "inherit").strip() or "inherit"
        agent_name = str(config.get("agent") or "").strip() or None
        yolo_enabled = bool(config.get("yolo", True))
        thinking_enabled = bool(config.get("thinking", False))
        details: dict[str, object] = {
            "binary": binary,
            "resolved_binary": resolved_binary,
            "config_dir": str(config.get("config_dir") or "~/.kimi"),
            "model": requested_model,
            "requested_model": requested_model,
            "effective_model": requested_model,
            "agent": agent_name,
            "thinking": thinking_enabled,
            "yolo": yolo_enabled,
            "checked_at": checked_at,
        }
        if not resolved_binary:
            return {
                "ok": False,
                "summary": "Kimi Code startup probe failed before execution.",
                "warnings": [],
                "errors": [f"Kimi Code binary `{binary}` is not available."],
                "details": details,
                "guidance": self._runner_missing_binary_guidance("kimi", config),
            }
        env = ensure_utf8_subprocess_env(os.environ.copy())
        env.update(self._codex_runner_env(config))
        temp_home_handle = tempfile.TemporaryDirectory()
        try:
            temp_home = Path(temp_home_handle.name)
            kimi_home = materialize_kimi_runtime_home(
                source_home=Path(str(config.get("config_dir") or Path.home() / ".kimi")).expanduser(),
                target_home=temp_home,
            )
            mcp_config_path = kimi_home / "mcp.json"
            write_json(mcp_config_path, {"mcpServers": {}})
            env["HOME"] = str(temp_home)
            env["USERPROFILE"] = str(temp_home)
            command = [
                resolved_binary,
                "--print",
                "--input-format",
                "text",
                "--output-format",
                "stream-json",
                "--work-dir",
                str(repo_root()),
                "--mcp-config-file",
                str(mcp_config_path),
            ]
            if yolo_enabled:
                command.append("--yolo")
            if requested_model.lower() not in {"", "inherit", "default", "kimi-default"}:
                command.extend(["--model", requested_model])
            if agent_name:
                command.extend(["--agent", agent_name])
            if thinking_enabled:
                command.append("--thinking")
            result = subprocess.run(
                command,
                input="Reply with exactly HELLO.",
                cwd=str(repo_root()),
                env=env,
                capture_output=True,
                timeout=90,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            details.update(
                {
                    "exit_code": None,
                    "stdout_excerpt": self._compact_probe_text(exc.stdout or ""),
                    "stderr_excerpt": self._compact_probe_text(exc.stderr or ""),
                }
            )
            return {
                "ok": False,
                "summary": "Kimi Code startup probe timed out.",
                "warnings": [],
                "errors": ["Kimi Code did not answer the startup probe within 90 seconds."],
                "details": details,
                "guidance": [
                    "Run a small `kimi --print --output-format stream-json` request manually and confirm it can answer before starting DeepScientist.",
                ],
            }
        finally:
            temp_home_handle.cleanup()
        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()
        ok = result.returncode == 0 and "HELLO" in f"{stdout_text}\n{stderr_text}".upper()
        details.update(
            {
                "exit_code": result.returncode,
                "stdout_excerpt": self._compact_probe_text(stdout_text),
                "stderr_excerpt": self._compact_probe_text(stderr_text),
                "probe_command": command,
            }
        )
        return {
            "ok": ok,
            "summary": "Kimi Code startup probe completed." if ok else "Kimi Code startup probe failed.",
            "warnings": ["Kimi Code returned stderr during the startup probe."] if stderr_text else [],
            "errors": [] if ok else ["Kimi Code did not complete the startup hello probe successfully."],
            "details": details,
            "guidance": [] if ok else [
                "Run `kimi --print --input-format text --output-format stream-json --yolo` manually and confirm it returns `HELLO`.",
                "Run `kimi login` first if this machine has not completed the Kimi Code login flow yet.",
                "If Kimi Code uses a custom home, point `runners.kimi.config_dir` at the correct `~/.kimi`-style directory.",
            ],
        }

    @staticmethod
    def _compact_probe_text(value: str, *, limit: int = 1200) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    def lingzhu_snapshot(self, config: dict | None = None) -> dict:
        resolved = dict(config or self.load_named_normalized("connectors").get("lingzhu") or {})
        state = self._lingzhu_runtime_state()
        raw_bindings = self._lingzhu_bindings()
        last_real_conversation_id = str(state.get("last_conversation_id") or "").strip() or None
        has_auth_ak = bool(self._secret(resolved, "auth_ak", "auth_ak_env"))
        passive_conversation_id = (
            lingzhu_passive_conversation_id(resolved)
            if bool(resolved.get("enabled", False)) and has_auth_ak
            else None
        )
        effective_binding = (
            self._lingzhu_effective_binding(raw_bindings, passive_conversation_id)
            if passive_conversation_id
            else None
        )
        bindings = [effective_binding] if isinstance(effective_binding, dict) and effective_binding.get("quest_id") else []
        default_target = (
            {
                **(
                    build_discovered_target(
                        passive_conversation_id,
                        source="passive_binding",
                        is_default=True,
                        label="Passive binding",
                        quest_id=str((effective_binding or {}).get("quest_id") or "").strip() or None,
                        updated_at=str((effective_binding or {}).get("updated_at") or "").strip() or None,
                    )
                    or {}
                ),
                "selectable": True,
                "is_passive": True,
            }
            if passive_conversation_id
            else None
        )
        discovered_targets = [default_target] if isinstance(default_target, dict) and default_target else []
        snapshot: dict[str, object] = {
            "name": "lingzhu",
            "display_mode": "companion_config",
            "mode": "openclaw_companion",
            "transport": "openclaw_sse",
            "enabled": bool(resolved.get("enabled", False)),
            "main_chat_id": None,
            "last_conversation_id": passive_conversation_id,
            "inbox_count": 0,
            "outbox_count": 0,
            "ignored_count": 0,
            "binding_count": len(bindings),
            "bindings": bindings,
            "target_count": len(discovered_targets),
            "recent_conversations": [],
            "recent_events": [],
            "known_targets": [],
            "discovered_targets": discovered_targets,
            "default_target": default_target,
            "details": self._lingzhu_snapshot_details(resolved),
        }
        snapshot["details"]["last_real_conversation_id"] = last_real_conversation_id
        snapshot["details"]["historical_target_count"] = len(self._lingzhu_recent_conversations(state))
        if not snapshot["enabled"]:
            snapshot["connection_state"] = "disabled"
            snapshot["auth_state"] = "disabled"
            return snapshot
        snapshot["auth_state"] = "ready" if has_auth_ak else "missing_auth_ak"
        health_probe = self._probe_lingzhu_health(resolved, timeout=1.5)
        snapshot["details"]["health_probe"] = health_probe
        if health_probe.get("ok", False):
            snapshot["connection_state"] = "reachable"
        else:
            snapshot["connection_state"] = "offline"
            if health_probe.get("message"):
                snapshot["last_error"] = health_probe.get("message")
        return snapshot

    def _lingzhu_runtime_state(self) -> dict[str, object]:
        payload = read_json(self.home / "logs" / "connectors" / "lingzhu" / "state.json", {})
        return payload if isinstance(payload, dict) else {}

    def _lingzhu_bindings(self) -> list[dict[str, object]]:
        payload = read_json(self.home / "logs" / "connectors" / "lingzhu" / "bindings.json", {"bindings": {}})
        raw_bindings = payload.get("bindings") if isinstance(payload, dict) else {}
        if not isinstance(raw_bindings, dict):
            return []
        items: list[dict[str, object]] = []
        for conversation_id, binding in sorted(raw_bindings.items()):
            if not isinstance(binding, dict):
                continue
            normalized_conversation_id = str(conversation_id or "").strip()
            if not normalized_conversation_id:
                continue
            items.append(
                {
                    "conversation_id": normalized_conversation_id,
                    "quest_id": str(binding.get("quest_id") or "").strip() or None,
                    "updated_at": str(binding.get("updated_at") or "").strip() or None,
                    "profile_id": None,
                    "profile_label": None,
                    "is_passive": lingzhu_is_passive_conversation_id(normalized_conversation_id),
                }
            )
        return items

    @staticmethod
    def _lingzhu_effective_binding(
        bindings: list[dict[str, object]],
        passive_conversation_id: str | None,
    ) -> dict[str, object] | None:
        normalized_passive_conversation_id = str(passive_conversation_id or "").strip()
        if not normalized_passive_conversation_id:
            return None
        candidate_bindings = [
            dict(item)
            for item in bindings
            if isinstance(item, dict) and str(item.get("quest_id") or "").strip()
        ]
        if not candidate_bindings:
            return None
        selected = max(
            candidate_bindings,
            key=lambda item: (
                str(item.get("updated_at") or ""),
                str(item.get("quest_id") or ""),
                str(item.get("conversation_id") or ""),
            ),
        )
        return {
            "conversation_id": normalized_passive_conversation_id,
            "quest_id": str(selected.get("quest_id") or "").strip() or None,
            "updated_at": str(selected.get("updated_at") or "").strip() or None,
            "profile_id": None,
            "profile_label": None,
            "is_passive": True,
        }

    @staticmethod
    def _lingzhu_recent_conversations(state: dict[str, object]) -> list[dict[str, object]]:
        items = state.get("recent_conversations")
        if not isinstance(items, list):
            return []
        return [dict(item) for item in items if isinstance(item, dict)]

    @staticmethod
    def _lingzhu_known_targets(state: dict[str, object]) -> list[dict[str, object]]:
        items = state.get("known_targets")
        if not isinstance(items, list):
            return []
        return [dict(item) for item in items if isinstance(item, dict)]

    def _lingzhu_snapshot_details(self, config: dict) -> dict:
        auth_ak = self._secret(config, "auth_ak", "auth_ak_env")
        return {
            "local_base_url": lingzhu_local_base_url(config),
            "health_url": lingzhu_health_url(config),
            "endpoint_url": lingzhu_sse_url(config),
            "public_base_url": lingzhu_public_base_url(config),
            "public_health_url": lingzhu_health_url(config, public=True),
            "public_endpoint_url": lingzhu_sse_url(config, public=True),
            "gateway_port": lingzhu_gateway_port(config),
            "agent_id": lingzhu_agent_id(config),
            "auth_ak_masked": self._mask_secret(auth_ak),
            "generated_curl": lingzhu_generated_curl({**config, "auth_ak": auth_ak}),
            "generated_openclaw_config": lingzhu_generated_openclaw_config_text({**config, "auth_ak": auth_ak}),
            "packaged_bridge_dir": "assets/connectors/lingzhu/openclaw-bridge",
            "packaged_template_path": "assets/connectors/lingzhu/openclaw.lingzhu.config.template.json",
            "supported_commands": lingzhu_supported_commands(
                experimental_enabled=bool(config.get("enable_experimental_native_actions", False))
            ),
            "public_ip_required": True,
        }

    def _probe_lingzhu_health(self, config: dict, *, timeout: float = 5.0) -> dict:
        url = lingzhu_health_url(config)
        if not url:
            return {"ok": False, "message": "Lingzhu health URL is empty."}
        try:
            request = Request(url, method="GET", headers={"Accept": "application/json"})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
                status_code = response.status
            return {
                "ok": True,
                "status_code": status_code,
                "status": payload.get("status"),
                "payload": payload,
            }
        except URLError as exc:
            return {"ok": False, "message": str(exc.reason or exc)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def _probe_lingzhu_sse(self, config: dict, *, timeout: float = 8.0) -> dict:
        url = lingzhu_sse_url(config)
        auth_ak = self._secret(config, "auth_ak", "auth_ak_env")
        if not url:
            return {"ok": False, "message": "Lingzhu SSE URL is empty."}
        if not auth_ak:
            return {"ok": False, "message": "Lingzhu auth_ak is empty."}
        request = Request(
            url,
            method="POST",
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {auth_ak}",
                "Content-Type": "application/json; charset=utf-8",
            },
            data=json.dumps(lingzhu_probe_payload(config), ensure_ascii=False).encode("utf-8"),
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                preview = response.read(512).decode("utf-8", errors="replace")
                content_type = str(response.headers.get("Content-Type") or "")
            ok = "text/event-stream" in content_type or "event:" in preview or "data:" in preview
            return {
                "ok": ok,
                "content_type": content_type,
                "preview": self._compact_probe_text(preview, limit=512),
                "message": None if ok else "Lingzhu SSE probe did not return an event-stream payload.",
            }
        except URLError as exc:
            return {"ok": False, "message": str(exc.reason or exc)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @staticmethod
    def _mask_secret(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= 8:
            return "*" * len(text)
        return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"

    def _normalize_named_payload(self, name: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return default_payload(name, self.home)
        prepared = deepcopy(payload)
        if name == "config":
            prepared.pop("reports", None)
            return self._normalize_config_payload(prepared)
        if name == "plugins":
            prepared = self._normalize_plugins_payload(prepared)
        elif name == "mcp_servers":
            prepared = self._normalize_mcp_payload(prepared)
        defaults = default_payload(name, self.home)
        if name == "runners":
            normalized = self._deep_merge(defaults, prepared)
            codex = normalized.get("codex")
            if isinstance(codex, dict):
                if self._looks_like_legacy_codex_retry_profile(codex):
                    codex["retry_initial_backoff_sec"] = 10.0
                    codex["retry_backoff_multiplier"] = 6.0
                    codex["retry_max_backoff_sec"] = 1800.0
                if self._looks_like_preupgrade_codex_retry_attempt_profile(codex):
                    codex["retry_max_attempts"] = 7
            claude = normalized.get("claude")
            if isinstance(claude, dict):
                legacy_approval_policy = str(claude.get("approval_policy") or "").strip().lower()
                if legacy_approval_policy and not str(claude.get("permission_mode") or "").strip():
                    if legacy_approval_policy == "never":
                        claude["permission_mode"] = "bypassPermissions"
                    elif legacy_approval_policy in {"on-request", "default"}:
                        claude["permission_mode"] = "default"
                if "approval_policy" in claude:
                    claude.pop("approval_policy", None)
                if "sandbox_mode" in claude:
                    claude.pop("sandbox_mode", None)
            return normalized
        if name == "connectors":
            normalized = deepcopy(defaults)
            for connector_name, connector_payload in prepared.items():
                if str(connector_name).startswith("_"):
                    if isinstance(connector_payload, dict):
                        base = deepcopy(defaults.get(connector_name, {})) if isinstance(defaults.get(connector_name), dict) else {}
                        base.update(connector_payload)
                        normalized[connector_name] = base
                    continue
                if not isinstance(connector_payload, dict):
                    normalized[connector_name] = connector_payload
                    continue
                base = deepcopy(defaults.get(connector_name, {})) if isinstance(defaults.get(connector_name), dict) else {}
                sanitized_payload = dict(connector_payload)
                if connector_name == "qq":
                    for legacy_key in ("mode", "relay_url", "relay_auth_token", "public_callback_url", "webhook_verify_signature"):
                        sanitized_payload.pop(legacy_key, None)
                    normalized["qq"] = normalize_qq_connector_config({**base, **sanitized_payload})
                    continue
                if connector_name in PROFILEABLE_CONNECTOR_NAMES:
                    normalized[connector_name] = normalize_connector_config(connector_name, {**base, **sanitized_payload})
                    continue
                elif connector_name == "weixin":
                    sanitized_payload["transport"] = "ilink_long_poll"
                    merged = {**base, **sanitized_payload}
                    merged["enabled"] = self._weixin_auto_enabled(merged)
                    normalized[connector_name] = merged
                    continue
                elif connector_name == "lingzhu":
                    sanitized_payload["transport"] = "openclaw_sse"
                    merged = {**base, **sanitized_payload}
                    merged["enabled"] = self._lingzhu_auto_enabled(merged)
                    normalized[connector_name] = merged
                    continue
                elif "transport" not in sanitized_payload:
                    inferred_transport = infer_connector_transport(connector_name, {**base, **sanitized_payload})
                    if inferred_transport:
                        sanitized_payload["transport"] = inferred_transport
                base.update(sanitized_payload)
                normalized[connector_name] = base
            return normalized
        return self._deep_merge(defaults, prepared)

    def _normalize_config_payload(self, payload: dict) -> dict:
        defaults = default_payload("config", self.home)
        normalized = self._deep_merge(defaults, payload)
        default_runner_override = str(
            os.environ.get("DEEPSCIENTIST_DEFAULT_RUNNER") or os.environ.get("DS_DEFAULT_RUNNER") or ""
        ).strip().lower()
        if default_runner_override:
            normalized["default_runner"] = default_runner_override
        bootstrap = normalized.get("bootstrap") if isinstance(normalized.get("bootstrap"), dict) else {}
        raw_bootstrap = payload.get("bootstrap") if isinstance(payload.get("bootstrap"), dict) else {}
        connectors = normalized.get("connectors") if isinstance(normalized.get("connectors"), dict) else {}
        raw_connectors = payload.get("connectors") if isinstance(payload.get("connectors"), dict) else {}
        default_locale = str(defaults.get("default_locale") or "").strip()
        current_locale = str(normalized.get("default_locale") or "").strip()
        locale_source = str(raw_bootstrap.get("locale_source") or "").strip().lower()
        locale_initialized_from_browser = bool(
            raw_bootstrap.get("locale_initialized_from_browser", bootstrap.get("locale_initialized_from_browser", False))
        )

        if locale_source not in {"default", "browser", "user"}:
            if current_locale and current_locale != default_locale:
                locale_source = "user"
            elif locale_initialized_from_browser:
                locale_source = "browser"
            else:
                locale_source = "default"

        if locale_source == "browser":
            locale_initialized_from_browser = True

        bootstrap["locale_source"] = locale_source
        bootstrap["locale_initialized_from_browser"] = locale_initialized_from_browser
        bootstrap["locale_initialized_at"] = bootstrap.get("locale_initialized_at")
        bootstrap["locale_initialized_browser_locale"] = bootstrap.get("locale_initialized_browser_locale")
        runner_readiness = bootstrap.get("runner_readiness") if isinstance(bootstrap.get("runner_readiness"), dict) else {}
        normalized_runner_readiness: dict[str, dict[str, Any]] = {}
        for runner_name in list_builtin_runner_names():
            state = runner_readiness.get(runner_name) if isinstance(runner_readiness.get(runner_name), dict) else {}
            if runner_name == "codex" and not state:
                state = {
                    "ready": bool(bootstrap.get("codex_ready", False)),
                    "last_checked_at": bootstrap.get("codex_last_checked_at"),
                    "last_result": bootstrap.get("codex_last_result") if isinstance(bootstrap.get("codex_last_result"), dict) else {},
                }
            normalized_runner_readiness[runner_name] = {
                "ready": bool(state.get("ready", False)),
                "last_checked_at": state.get("last_checked_at"),
                "last_result": state.get("last_result") if isinstance(state.get("last_result"), dict) else {},
            }
        bootstrap["runner_readiness"] = normalized_runner_readiness
        bootstrap["codex_ready"] = bool(normalized_runner_readiness.get("codex", {}).get("ready", False))
        bootstrap["codex_last_checked_at"] = normalized_runner_readiness.get("codex", {}).get("last_checked_at")
        bootstrap["codex_last_result"] = normalized_runner_readiness.get("codex", {}).get("last_result") if isinstance(normalized_runner_readiness.get("codex", {}).get("last_result"), dict) else {}
        normalized["bootstrap"] = bootstrap
        raw_system_enabled = raw_connectors.get("system_enabled") if isinstance(raw_connectors.get("system_enabled"), dict) else {}
        default_system_enabled = (
            defaults.get("connectors", {}).get("system_enabled")
            if isinstance(defaults.get("connectors"), dict)
            else {}
        )
        current_system_enabled = (
            connectors.get("system_enabled")
            if isinstance(connectors.get("system_enabled"), dict)
            else {}
        )
        connectors["system_enabled"] = {
            name: self._coerce_bool(
                raw_system_enabled.get(name, current_system_enabled.get(name)),
                default=bool(default_system_enabled.get(name, False)),
            )
            for name in SYSTEM_CONNECTOR_NAMES
        }
        normalized["connectors"] = connectors
        hardware = normalized.get("hardware") if isinstance(normalized.get("hardware"), dict) else {}
        raw_hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
        gpu_selection_mode = str(raw_hardware.get("gpu_selection_mode") or hardware.get("gpu_selection_mode") or "all").strip().lower()
        if gpu_selection_mode not in {"all", "selected"}:
            gpu_selection_mode = "all"
        raw_selected_gpu_ids = raw_hardware.get("selected_gpu_ids", hardware.get("selected_gpu_ids", []))
        selected_gpu_ids: list[str] = []
        if isinstance(raw_selected_gpu_ids, list):
            for item in raw_selected_gpu_ids:
                normalized_id = str(item or "").strip()
                if normalized_id and normalized_id not in selected_gpu_ids:
                    selected_gpu_ids.append(normalized_id)
        elif isinstance(raw_selected_gpu_ids, str):
            for item in raw_selected_gpu_ids.split(","):
                normalized_id = item.strip()
                if normalized_id and normalized_id not in selected_gpu_ids:
                    selected_gpu_ids.append(normalized_id)
        hardware["gpu_selection_mode"] = gpu_selection_mode
        hardware["selected_gpu_ids"] = selected_gpu_ids
        hardware["include_system_hardware_in_prompt"] = self._coerce_bool(
            raw_hardware.get(
                "include_system_hardware_in_prompt",
                hardware.get("include_system_hardware_in_prompt", True),
            ),
            default=True,
        )
        normalized["hardware"] = hardware
        literature = normalized.get("literature") if isinstance(normalized.get("literature"), dict) else {}
        raw_literature = payload.get("literature") if isinstance(payload.get("literature"), dict) else {}
        default_literature = defaults.get("literature") if isinstance(defaults.get("literature"), dict) else {}
        deepxiv_defaults = default_literature.get("deepxiv") if isinstance(default_literature.get("deepxiv"), dict) else {}
        deepxiv = literature.get("deepxiv") if isinstance(literature.get("deepxiv"), dict) else {}
        raw_deepxiv = raw_literature.get("deepxiv") if isinstance(raw_literature.get("deepxiv"), dict) else {}
        deepxiv["enabled"] = self._coerce_bool(
            raw_deepxiv.get("enabled", deepxiv.get("enabled", deepxiv_defaults.get("enabled", False))),
            default=bool(deepxiv_defaults.get("enabled", False)),
        )
        deepxiv["base_url"] = str(
            raw_deepxiv.get("base_url", deepxiv.get("base_url", deepxiv_defaults.get("base_url", "https://data.rag.ac.cn"))) or ""
        ).strip() or str(deepxiv_defaults.get("base_url") or "https://data.rag.ac.cn")
        deepxiv["token"] = str(raw_deepxiv.get("token", deepxiv.get("token", "")) or "").strip() or None
        deepxiv["token_env"] = str(
            raw_deepxiv.get("token_env", deepxiv.get("token_env", deepxiv_defaults.get("token_env", "DEEPXIV_TOKEN"))) or ""
        ).strip() or None
        try:
            deepxiv["default_result_size"] = max(1, int(raw_deepxiv.get("default_result_size", deepxiv.get("default_result_size", deepxiv_defaults.get("default_result_size", 20))) or 90))
        except (TypeError, ValueError):
            deepxiv["default_result_size"] = int(deepxiv_defaults.get("default_result_size", 20) or 10)
        try:
            deepxiv["preview_characters"] = max(200, int(raw_deepxiv.get("preview_characters", deepxiv.get("preview_characters", deepxiv_defaults.get("preview_characters", 5000))) or 5000))
        except (TypeError, ValueError):
            deepxiv["preview_characters"] = int(deepxiv_defaults.get("preview_characters", 5000) or 1200)
        try:
            deepxiv["request_timeout_seconds"] = max(3, int(raw_deepxiv.get("request_timeout_seconds", deepxiv.get("request_timeout_seconds", deepxiv_defaults.get("request_timeout_seconds", 90))) or 20))
        except (TypeError, ValueError):
            deepxiv["request_timeout_seconds"] = int(deepxiv_defaults.get("request_timeout_seconds", 90) or 20)
        literature["deepxiv"] = deepxiv
        normalized["literature"] = literature
        return normalized

    @staticmethod
    def _looks_like_legacy_codex_retry_profile(payload: dict) -> bool:
        try:
            initial = float(payload.get("retry_initial_backoff_sec"))
            multiplier = float(payload.get("retry_backoff_multiplier"))
            max_backoff = float(payload.get("retry_max_backoff_sec"))
        except (TypeError, ValueError):
            return False
        return abs(initial - 1.0) < 1e-9 and abs(multiplier - 2.0) < 1e-9 and abs(max_backoff - 8.0) < 1e-9

    @staticmethod
    def _looks_like_preupgrade_codex_retry_attempt_profile(payload: dict) -> bool:
        try:
            max_attempts = int(payload.get("retry_max_attempts"))
            initial = float(payload.get("retry_initial_backoff_sec"))
            multiplier = float(payload.get("retry_backoff_multiplier"))
            max_backoff = float(payload.get("retry_max_backoff_sec"))
        except (TypeError, ValueError):
            return False
        return (
            max_attempts == 5
            and abs(initial - 10.0) < 1e-9
            and abs(multiplier - 6.0) < 1e-9
            and abs(max_backoff - 1800.0) < 1e-9
        )

    @staticmethod
    def _coerce_bool(value: object, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "y"}:
                return True
            if normalized in {"0", "false", "no", "off", "n", ""}:
                return False
        return bool(value)

    @staticmethod
    def _connector_has_secret(payload: dict[str, object], direct_key: str, env_key: str) -> bool:
        return bool(str(payload.get(direct_key) or "").strip() or str(payload.get(env_key) or "").strip())

    def _weixin_auto_enabled(self, payload: dict[str, object]) -> bool:
        return self._connector_has_secret(payload, "bot_token", "bot_token_env") and bool(
            str(payload.get("account_id") or "").strip()
        )

    def _lingzhu_auto_enabled(self, payload: dict[str, object]) -> bool:
        auth_ready = self._connector_has_secret(payload, "auth_ak", "auth_ak_env")
        public_base_url = str(payload.get("public_base_url") or "").strip()
        if not auth_ready or not public_base_url:
            return False
        normalized_public_base_url = lingzhu_public_base_url(payload)
        if normalized_public_base_url is None:
            return False
        return public_base_url_looks_public(normalized_public_base_url)

    def _connector_has_user_config(self, name: str, config: dict[str, object]) -> bool:
        if name == "qq":
            return bool(list_qq_profiles(config))
        if name in PROFILEABLE_CONNECTOR_NAMES:
            return bool(list_connector_profiles(name, config))
        if name == "weixin":
            return any(
                str(config.get(key) or "").strip()
                for key in ("bot_token", "bot_token_env", "account_id", "login_user_id", "route_tag")
            )
        if name == "lingzhu":
            return any(
                str(config.get(key) or "").strip()
                for key in ("auth_ak", "auth_ak_env", "public_base_url")
            )
        return False

    def _should_validate_connector(self, name: str, config: dict[str, object]) -> bool:
        return bool(config.get("enabled", False)) or self._connector_has_user_config(name, config)

    def _normalize_plugins_payload(self, payload: dict) -> dict:
        normalized = deepcopy(payload)
        if "load_paths" not in normalized and isinstance(normalized.get("search_paths"), list):
            normalized["load_paths"] = normalized.pop("search_paths")
        return normalized

    def _normalize_mcp_payload(self, payload: dict) -> dict:
        normalized = deepcopy(payload)
        raw_servers = normalized.get("servers")
        if raw_servers is None:
            top_level_servers = {
                key: value
                for key, value in normalized.items()
                if key != "servers" and isinstance(value, dict)
            }
            if top_level_servers:
                normalized = {"servers": top_level_servers}
                raw_servers = normalized["servers"]

        if isinstance(raw_servers, list):
            server_map: dict[str, dict] = {}
            for item in raw_servers:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("id") or "").strip()
                if not name:
                    continue
                data = deepcopy(item)
                data.pop("name", None)
                data.pop("id", None)
                server_map[name] = data
            normalized["servers"] = server_map
        elif not isinstance(raw_servers, dict):
            normalized["servers"] = {}
        return normalized

    @staticmethod
    def _deep_merge(base: dict, patch: dict) -> dict:
        merged = deepcopy(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = ConfigManager._deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged

    def _validate_plugins_payload(self, payload: dict) -> dict:
        warnings: list[str] = []
        errors: list[str] = []
        for key in ("load_paths", "enabled", "disabled"):
            value = payload.get(key)
            if value is not None and not isinstance(value, list):
                errors.append(f"plugins: `{key}` must be a list.")
        enabled = set(self._list_values(payload.get("enabled")))
        disabled = set(self._list_values(payload.get("disabled")))
        overlap = sorted(enabled & disabled)
        if overlap:
            warnings.append(
                f"plugins: the following plugin ids appear in both `enabled` and `disabled`: {', '.join(overlap)}."
            )
        return {
            "warnings": warnings,
            "errors": errors,
        }

    def _validate_mcp_servers_payload(self, payload: dict) -> dict:
        warnings: list[str] = []
        errors: list[str] = []
        servers = payload.get("servers")
        if not isinstance(servers, dict):
            return {
                "warnings": warnings,
                "errors": ["mcp_servers: `servers` must be a mapping keyed by server id."],
            }

        for name, raw_server in servers.items():
            if not isinstance(raw_server, dict):
                errors.append(f"mcp_servers: `{name}` must be a mapping.")
                continue
            enabled = bool(raw_server.get("enabled", False))
            transport = str(raw_server.get("transport") or "stdio").strip().lower()
            if transport not in {"stdio", "streamable_http", "http", "sse"}:
                errors.append(
                    f"mcp_servers: `{name}` transport `{transport}` is unsupported. Use `stdio`, `streamable_http`, `http`, or `sse`."
                )
            command = raw_server.get("command")
            url = str(raw_server.get("url") or "").strip()
            env = raw_server.get("env")
            if enabled and transport == "stdio":
                command_list = command if isinstance(command, list) else [command] if isinstance(command, str) else []
                if not any(str(item or "").strip() for item in command_list):
                    errors.append(f"mcp_servers: `{name}` uses `stdio` but has no `command` configured.")
            if enabled and transport in {"streamable_http", "http", "sse"} and not url:
                errors.append(f"mcp_servers: `{name}` uses `{transport}` but has no `url` configured.")
            if env is not None and not isinstance(env, dict):
                errors.append(f"mcp_servers: `{name}` field `env` must be a mapping.")
        return {
            "warnings": warnings,
            "errors": errors,
        }

    def _validate_access_policies(self, name: str, config: dict) -> dict:
        warnings: list[str] = []
        errors: list[str] = []
        dm_policy = str(config.get("dm_policy") or "pairing").strip().lower()
        group_policy = str(config.get("group_policy") or "open").strip().lower()
        allow_from = self._list_values(config.get("allow_from"))
        group_allow_from = self._list_values(config.get("group_allow_from"))
        groups = config.get("groups")

        if dm_policy not in {"pairing", "allowlist", "open", "disabled"}:
            errors.append(f"{name}: unsupported `dm_policy` `{dm_policy}`.")
        if dm_policy == "allowlist" and not allow_from:
            errors.append(f"{name}: `dm_policy: allowlist` requires at least one `allow_from` entry.")
        if dm_policy == "open" and allow_from and "*" not in allow_from:
            errors.append(f"{name}: `dm_policy: open` requires `allow_from` to include `*` when `allow_from` is set.")

        if group_policy not in {"allowlist", "open", "disabled"}:
            errors.append(f"{name}: unsupported `group_policy` `{group_policy}`.")
        if group_policy == "allowlist" and not (group_allow_from or allow_from):
            errors.append(f"{name}: `group_policy: allowlist` requires `group_allow_from` or `allow_from`.")
        if isinstance(groups, list) and groups and "*" in groups and len(groups) > 1:
            warnings.append(f"{name}: `groups` contains `*`; the other explicit group ids are redundant.")
        if groups is not None and not isinstance(groups, list):
            errors.append(f"{name}: `groups` must be a list when provided.")

        return {
            "warnings": warnings,
            "errors": errors,
        }

    @staticmethod
    def _list_values(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            normalized = str(item or "").strip()
            if normalized:
                items.append(normalized)
        return items

    @staticmethod
    def _has_secret(config: dict, key: str, env_key: str) -> bool:
        if str(config.get(key) or "").strip():
            return True
        env_name = str(config.get(env_key) or "").strip()
        return bool(env_name and os.environ.get(env_name))

    @staticmethod
    def _secret(config: dict, key: str, env_key: str) -> str:
        value = str(config.get(key) or "").strip()
        if value:
            return value
        env_name = str(config.get(env_key) or "").strip()
        return str(os.environ.get(env_name) or "").strip() if env_name else ""

    @staticmethod
    def _http_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: dict | None = None) -> dict:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(url, data=raw, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        with urlopen(request, timeout=8) as response:  # noqa: S310
            text = response.read().decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"ok": False, "message": text[:500]}
