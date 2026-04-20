from __future__ import annotations

from pathlib import Path
from typing import Any

from ..shared import ensure_dir, generate_id, read_json, utc_now, write_json, write_text


_ADMIN_OPS_LEAD_MESSAGE = {
    "zh": (
        "我是 DeepScientist AdminOps，可以帮助你诊断运行时问题、检查日志、分析 quest 状态、验证配置，"
        "并在允许范围内执行安全修复。"
    ),
    "en": (
        "I am DeepScientist AdminOps. I can help diagnose runtime problems, inspect logs, analyze quest state, "
        "validate configuration, and apply safe repairs when allowed."
    ),
}

_ADMIN_OPS_KNOWLEDGE_REFS = [
    "README.md",
    "docs/en/README.md",
    "docs/zh/README.md",
    "docs/en/00_QUICK_START.md",
    "docs/zh/00_QUICK_START.md",
    "docs/en/01_SETTINGS_REFERENCE.md",
    "docs/zh/01_SETTINGS_REFERENCE.md",
    "docs/en/09_DOCTOR.md",
    "docs/zh/09_DOCTOR.md",
    "docs/en/13_CORE_ARCHITECTURE_GUIDE.md",
    "docs/zh/13_CORE_ARCHITECTURE_GUIDE.md",
    "docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md",
    "docs/zh/14_PROMPT_SKILLS_AND_MCP_GUIDE.md",
    "src/deepscientist/daemon/app.py",
    "src/deepscientist/daemon/api/router.py",
    "src/deepscientist/daemon/api/handlers.py",
    "src/deepscientist/prompts/builder.py",
    "src/deepscientist/runtime_tools/",
    "src/ui/src/components/settings/SettingsPage.tsx",
    "src/ui/src/components/settings/SettingsOpsRail.tsx",
    "src/ui/src/components/settings/SettingsRepairsSection.tsx",
]


class AdminRepairService:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.home = Path(app.home)

    @property
    def repairs_root(self) -> Path:
        return ensure_dir(self.home / "runtime" / "admin" / "repairs")

    def record_path(self, repair_id: str) -> Path:
        return self.repairs_root / f"{repair_id}.json"

    def _quest_report_dir(self, ops_quest_id: str) -> Path:
        quest_root = self.app.quest_service._quest_root(ops_quest_id)
        return ensure_dir(quest_root / "artifacts" / "reports" / "admin")

    def _write_repair_report(self, payload: dict[str, Any]) -> None:
        ops_quest_id = str(payload.get("ops_quest_id") or "").strip()
        if not ops_quest_id:
            return
        report_dir = self._quest_report_dir(ops_quest_id)
        repair_id = str(payload.get("repair_id") or "").strip() or "repair"
        markdown_path = report_dir / f"{repair_id}.md"
        json_path = report_dir / f"{repair_id}.json"
        lines = [
            f"# Admin Repair {repair_id}",
            "",
            f"- status: `{payload.get('status')}`",
            f"- scope: `{payload.get('scope')}`",
            f"- repair_policy: `{payload.get('repair_policy')}`",
            f"- source_page: `{payload.get('source_page')}`",
            f"- ops_quest_id: `{ops_quest_id}`",
            f"- created_at: `{payload.get('created_at')}`",
            f"- updated_at: `{payload.get('updated_at')}`",
            f"- closed_at: `{payload.get('closed_at')}`",
            "",
            "## User Request",
            "",
            str(payload.get("user_request") or "").strip() or "_No request text recorded._",
            "",
            "## Targets",
            "",
            "```json",
            __import__("json").dumps(payload.get("targets") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Selected Paths",
            "",
        ]
        selected_paths = [str(item).strip() for item in (payload.get("selected_paths") or []) if str(item).strip()]
        if selected_paths:
            lines.extend([f"- `{item}`" for item in selected_paths])
        else:
            lines.append("- None")
        write_text(markdown_path, "\n".join(lines).rstrip() + "\n")
        write_json(json_path, payload)

    def _admin_ops_lead_message(self) -> str:
        config = self.app.config_manager.load_runtime_config()
        locale = str(config.get("default_locale") or "en-US").strip().lower()
        return _ADMIN_OPS_LEAD_MESSAGE["zh" if locale.startswith("zh") else "en"]

    def list_repairs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.repairs_root.glob("*.json"), reverse=True):
            payload = read_json(path, default=None)
            if isinstance(payload, dict):
                items.append(payload)
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return items[: max(1, limit)]

    def get_repair(self, repair_id: str) -> dict[str, Any]:
        payload = read_json(self.record_path(repair_id), default=None)
        if not isinstance(payload, dict):
            raise FileNotFoundError(f"Unknown repair `{repair_id}`.")
        return payload

    def create_repair(
        self,
        *,
        request_text: str,
        source_page: str | None = None,
        scope: str = "system",
        targets: dict[str, Any] | None = None,
        repair_policy: str = "diagnose_only",
        selected_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_request = str(request_text or "").strip()
        if not normalized_request:
            raise ValueError("Repair request text is required.")
        repair_id = generate_id("repair")
        normalized_scope = str(scope or "system").strip().lower() or "system"
        normalized_targets = dict(targets or {})
        normalized_paths = [str(item).strip() for item in (selected_paths or []) if str(item).strip()]
        startup_contract = {
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "admin_ops",
            "custom_brief": normalized_request,
            "entry_state_summary": f"Admin repair session `{repair_id}` from `{source_page or '/admin'}`.",
            "review_materials": normalized_paths,
            "admin_session": {
                "repair_id": repair_id,
                "scope": normalized_scope,
                "targets": normalized_targets,
                "repair_policy": repair_policy,
                "source_page": source_page or "/admin",
                "selected_paths": normalized_paths,
                "knowledge_refs": list(_ADMIN_OPS_KNOWLEDGE_REFS),
            },
        }
        quest_title = f"Admin Repair {repair_id}"
        next_numeric = self.app.quest_service.preview_next_numeric_quest_id()
        snapshot = self.app.create_quest(
            goal=normalized_request,
            title=quest_title,
            quest_id=f"S-{next_numeric}",
            source="admin",
            announce_connector_binding=False,
            auto_bind_latest_connectors=False,
            startup_contract=startup_contract,
        )
        ops_quest_id = str(snapshot.get("quest_id") or "").strip()
        quest_root = self.app.quest_service._quest_root(ops_quest_id)
        self.app.quest_service.update_research_state(quest_root, workspace_mode="copilot")
        self.app.quest_service.append_message(
            ops_quest_id,
            "assistant",
            self._admin_ops_lead_message(),
            source="deepscientist",
        )
        self.app.quest_service.update_runtime_state(
            quest_root=quest_root,
            status="idle",
            display_status="idle",
        )
        self.app.quest_service.set_continuation_state(
            quest_root,
            policy="wait_for_user_or_resume",
            anchor="decision",
            reason="copilot_mode",
        )
        self.app.submit_user_message(
            ops_quest_id,
            text=normalized_request,
            source="admin",
        )
        payload = {
            "repair_id": repair_id,
            "status": "open",
            "scope": normalized_scope,
            "source_page": source_page or "/admin",
            "targets": normalized_targets,
            "repair_policy": str(repair_policy or "diagnose_only").strip() or "diagnose_only",
            "selected_paths": normalized_paths,
            "user_request": normalized_request,
            "ops_quest_id": ops_quest_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "closed_at": None,
        }
        write_json(self.record_path(repair_id), payload)
        self._write_repair_report(payload)
        return payload

    def close_repair(self, repair_id: str) -> dict[str, Any]:
        payload = self.get_repair(repair_id)
        payload["status"] = "closed"
        payload["closed_at"] = utc_now()
        payload["updated_at"] = payload["closed_at"]
        write_json(self.record_path(repair_id), payload)
        self._write_repair_report(payload)
        return payload
