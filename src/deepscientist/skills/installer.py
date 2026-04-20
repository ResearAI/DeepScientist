from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from uuid import uuid4

from ..memory.frontmatter import load_markdown_document
from ..shared import ensure_dir, read_json, utc_now, write_json
from .registry import discover_skill_bundles

_PROMPT_SYNC_STATE_FILENAME = ".deepscientist-prompt-sync.json"
_PROMPT_VERSIONS_DIRNAME = "prompt_versions"
_PROMPT_VERSIONS_INDEX_FILENAME = "index.json"


class SkillInstaller:
    def __init__(self, repo_root: Path, home: Path) -> None:
        self.repo_root = repo_root
        self.home = home

    def discover(self):
        return discover_skill_bundles(self.repo_root)

    def sync_global(self) -> dict:
        codex_root = ensure_dir(Path.home() / ".codex" / "skills")
        claude_root = ensure_dir(Path.home() / ".claude" / "agents")
        kimi_root = ensure_dir(Path.home() / ".kimi" / "skills")
        opencode_root = ensure_dir(Path.home() / ".config" / "opencode" / "skills")
        copied_codex: list[str] = []
        copied_claude: list[str] = []
        copied_kimi: list[str] = []
        copied_opencode: list[str] = []
        expected_codex: set[str] = set()
        expected_claude: set[str] = set()
        expected_kimi: set[str] = set()
        expected_opencode: set[str] = set()
        for bundle in self.discover():
            target = codex_root / f"deepscientist-{bundle.skill_id}"
            expected_codex.add(target.name)
            self._sync_bundle_tree(bundle.root, target)
            copied_codex.append(str(target))
            claude_target = self._sync_claude_projection(bundle, claude_root)
            expected_claude.add(claude_target.name)
            copied_claude.append(str(claude_target))
            kimi_target = kimi_root / f"deepscientist-{bundle.skill_id}"
            expected_kimi.add(kimi_target.name)
            self._sync_bundle_tree(bundle.root, kimi_target)
            copied_kimi.append(str(kimi_target))
            opencode_target = opencode_root / f"deepscientist-{bundle.skill_id}"
            expected_opencode.add(opencode_target.name)
            self._sync_bundle_tree(bundle.root, opencode_target)
            copied_opencode.append(str(opencode_target))
        self._prune_bundle_targets(codex_root, expected_codex)
        self._prune_bundle_targets(claude_root, expected_claude)
        self._prune_bundle_targets(kimi_root, expected_kimi)
        self._prune_bundle_targets(opencode_root, expected_opencode)
        return {
            "codex": copied_codex,
            "claude": copied_claude,
            "kimi": copied_kimi,
            "opencode": copied_opencode,
            "notes": [],
        }

    def sync_quest(self, quest_root: Path, *, installed_version: str | None = None) -> dict:
        prompt_sync = self.sync_quest_prompts(quest_root, installed_version=installed_version)
        prompts_root = ensure_dir(quest_root / ".codex" / "prompts")
        codex_root = ensure_dir(quest_root / ".codex" / "skills")
        claude_root = ensure_dir(quest_root / ".claude" / "agents")
        kimi_root = ensure_dir(quest_root / ".kimi" / "skills")
        opencode_root = ensure_dir(quest_root / ".opencode" / "skills")
        copied_codex: list[str] = []
        copied_claude: list[str] = []
        copied_kimi: list[str] = []
        copied_opencode: list[str] = []
        expected_codex: set[str] = set()
        expected_claude: set[str] = set()
        expected_kimi: set[str] = set()
        expected_opencode: set[str] = set()
        for bundle in self.discover():
            target = codex_root / f"deepscientist-{bundle.skill_id}"
            expected_codex.add(target.name)
            self._sync_bundle_tree(bundle.root, target)
            copied_codex.append(str(target))
            claude_target = self._sync_claude_projection(bundle, claude_root)
            expected_claude.add(claude_target.name)
            copied_claude.append(str(claude_target))
            kimi_target = kimi_root / f"deepscientist-{bundle.skill_id}"
            expected_kimi.add(kimi_target.name)
            self._sync_bundle_tree(bundle.root, kimi_target)
            copied_kimi.append(str(kimi_target))
            opencode_target = opencode_root / f"deepscientist-{bundle.skill_id}"
            expected_opencode.add(opencode_target.name)
            self._sync_bundle_tree(bundle.root, opencode_target)
            copied_opencode.append(str(opencode_target))
        self._prune_bundle_targets(codex_root, expected_codex)
        self._prune_bundle_targets(claude_root, expected_claude)
        self._prune_bundle_targets(kimi_root, expected_kimi)
        self._prune_bundle_targets(opencode_root, expected_opencode)
        return {
            "prompts": [str(path) for path in sorted(prompts_root.rglob("*")) if path.is_file()],
            "prompt_sync": prompt_sync,
            "codex": copied_codex,
            "claude": copied_claude,
            "kimi": copied_kimi,
            "opencode": copied_opencode,
            "notes": [],
        }

    def sync_existing_quests(self, *, installed_version: str | None = None) -> dict:
        quests_root = self.home / "quests"
        synced: list[dict[str, object]] = []
        if not quests_root.exists():
            return {
                "count": 0,
                "quests": [],
            }
        for quest_root in sorted(quests_root.iterdir()):
            if not quest_root.is_dir():
                continue
            if not (quest_root / "quest.yaml").exists():
                continue
            result = self.sync_quest(quest_root, installed_version=installed_version)
            synced.append(
                {
                    "quest_id": quest_root.name,
                    "quest_root": str(quest_root),
                    "codex_count": len(result.get("codex") or []),
                    "claude_count": len(result.get("claude") or []),
                    "kimi_count": len(result.get("kimi") or []),
                    "prompt_backup_id": (result.get("prompt_sync") or {}).get("backup_id"),
                    "prompt_fingerprint": (result.get("prompt_sync") or {}).get("prompt_fingerprint"),
                }
            )
        return {
            "count": len(synced),
            "quests": synced,
        }

    def ensure_release_sync(
        self,
        *,
        installed_version: str,
        sync_global_enabled: bool = True,
        sync_existing_quests_enabled: bool = True,
        force: bool = False,
    ) -> dict:
        normalized_version = str(installed_version or "").strip() or "unknown"
        state = self._read_release_sync_state()
        previous_version = str(state.get("installed_version") or "").strip()
        if not force and previous_version == normalized_version:
            return {
                "updated": False,
                "installed_version": normalized_version,
                "previous_version": previous_version or None,
                "global_synced": False,
                "existing_quests_synced": False,
                "state_path": str(self._release_sync_state_path()),
            }

        summary: dict[str, object] = {
            "updated": True,
            "installed_version": normalized_version,
            "previous_version": previous_version or None,
            "global_synced": False,
            "existing_quests_synced": False,
            "state_path": str(self._release_sync_state_path()),
            "synced_at": utc_now(),
        }
        if sync_global_enabled:
            summary["global"] = self.sync_global()
            summary["global_synced"] = True
        if sync_existing_quests_enabled:
            summary["existing_quests"] = self.sync_existing_quests(installed_version=normalized_version)
            summary["existing_quests_synced"] = True
        self._write_release_sync_state(summary)
        return summary

    def sync_quest_prompts(
        self,
        quest_root: Path,
        *,
        installed_version: str | None = None,
    ) -> dict[str, object]:
        prompts_root = ensure_dir(quest_root / ".codex" / "prompts")
        source_root = self.repo_root / "src" / "prompts"
        normalized_version = self._normalized_installed_version(installed_version)
        previous_state = self._read_prompt_sync_state(prompts_root)
        current_fingerprint = self._prompt_tree_fingerprint(prompts_root, exclude_state_file=True)
        source_fingerprint = self._prompt_tree_fingerprint(source_root, exclude_state_file=False)
        backup_id: str | None = None
        updated = False

        if current_fingerprint != source_fingerprint:
            if current_fingerprint:
                backup_id = self._backup_prompt_tree(
                    quest_root,
                    prompts_root=prompts_root,
                    installed_version=str(previous_state.get("installed_version") or normalized_version),
                    prompt_fingerprint=current_fingerprint,
                )
            self._sync_prompt_tree(prompts_root)
            updated = True

        prompt_state = {
            "installed_version": normalized_version,
            "prompt_fingerprint": self._prompt_tree_fingerprint(prompts_root, exclude_state_file=True),
            "synced_at": utc_now(),
            "backup_id": backup_id,
            "source_root": str(source_root),
        }
        write_json(self._prompt_sync_state_path(prompts_root), prompt_state)
        return {
            "updated": updated,
            "backup_id": backup_id,
            "prompt_fingerprint": prompt_state["prompt_fingerprint"],
            "installed_version": normalized_version,
            "source_root": str(source_root),
            "active_root": str(prompts_root),
            "versions_root": str(self._prompt_versions_root(quest_root)),
        }

    def list_prompt_versions(self, quest_root: Path) -> list[dict[str, object]]:
        payload = read_json(self._prompt_versions_index_path(quest_root), {})
        versions = payload.get("versions") if isinstance(payload.get("versions"), list) else []
        return [dict(item) for item in versions if isinstance(item, dict)]

    def resolve_prompt_version_root(self, quest_root: Path, selection: str) -> Path | None:
        normalized = str(selection or "").strip()
        if not normalized:
            return None
        exact_root = self._prompt_versions_root(quest_root) / normalized
        if exact_root.exists():
            return exact_root
        candidates = [
            dict(item)
            for item in self.list_prompt_versions(quest_root)
            if str(item.get("installed_version") or "").strip() == normalized
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: str(item.get("created_at") or ""))
        selected_path = Path(str(candidates[-1].get("path") or "")).expanduser()
        return selected_path if selected_path.exists() else None

    @staticmethod
    def _normalized_installed_version(installed_version: str | None) -> str:
        normalized = str(installed_version or "").strip()
        if normalized:
            return normalized
        from .. import __version__

        return str(__version__ or "").strip() or "unknown"

    def _backup_prompt_tree(
        self,
        quest_root: Path,
        *,
        prompts_root: Path,
        installed_version: str,
        prompt_fingerprint: str,
    ) -> str:
        versions_root = ensure_dir(self._prompt_versions_root(quest_root))
        backup_id = ""
        target_root: Path | None = None
        for _attempt in range(8):
            backup_id = self._unique_prompt_backup_id(
                versions_root,
                installed_version=installed_version,
                prompt_fingerprint=prompt_fingerprint,
            )
            target_root = versions_root / backup_id
            try:
                shutil.copytree(prompts_root, target_root)
                break
            except FileExistsError:
                # Another sync run may have created the same backup directory between
                # name selection and copy. Regenerate a fresh id and retry.
                continue
        else:
            raise FileExistsError(
                f"Failed to allocate a unique prompt backup directory under `{versions_root}` after multiple attempts."
            )
        assert target_root is not None
        entry = {
            "backup_id": backup_id,
            "installed_version": str(installed_version or "").strip() or "unknown",
            "prompt_fingerprint": prompt_fingerprint,
            "created_at": utc_now(),
            "path": str(target_root),
        }
        versions = self.list_prompt_versions(quest_root)
        versions = [item for item in versions if str(item.get("backup_id") or "").strip() != backup_id]
        versions.append(entry)
        versions.sort(key=lambda item: str(item.get("created_at") or ""))
        write_json(self._prompt_versions_index_path(quest_root), {"versions": versions})
        return backup_id

    @staticmethod
    def _prompt_versions_root(quest_root: Path) -> Path:
        return ensure_dir(quest_root / ".codex" / _PROMPT_VERSIONS_DIRNAME)

    @staticmethod
    def _prompt_versions_index_path(quest_root: Path) -> Path:
        return SkillInstaller._prompt_versions_root(quest_root) / _PROMPT_VERSIONS_INDEX_FILENAME

    @staticmethod
    def _prompt_sync_state_path(prompts_root: Path) -> Path:
        return prompts_root / _PROMPT_SYNC_STATE_FILENAME

    def _read_prompt_sync_state(self, prompts_root: Path) -> dict[str, object]:
        payload = read_json(self._prompt_sync_state_path(prompts_root), {})
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _sanitize_prompt_label(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
        return normalized or "unknown"

    def _unique_prompt_backup_id(
        self,
        versions_root: Path,
        *,
        installed_version: str,
        prompt_fingerprint: str,
    ) -> str:
        version_label = self._sanitize_prompt_label(installed_version)
        timestamp_label = self._sanitize_prompt_label(
            utc_now().replace(":", "").replace("+00:00", "Z")
        )
        fingerprint_label = (str(prompt_fingerprint or "").strip() or "unknown")[:12]
        base = f"{version_label}__prompts-{fingerprint_label}__{timestamp_label}"
        candidate = base
        counter = 2
        while (versions_root / candidate).exists():
            candidate = f"{base}__{counter}"
            counter += 1
        return candidate

    @staticmethod
    def _prompt_tree_fingerprint(root: Path, *, exclude_state_file: bool) -> str:
        if not root.exists():
            return ""
        files = [
            path
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and not (exclude_state_file and path.name == _PROMPT_SYNC_STATE_FILENAME)
        ]
        if not files:
            return ""
        hasher = hashlib.sha256()
        for path in files:
            relative = path.relative_to(root).as_posix()
            hasher.update(relative.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
            hasher.update(b"\0")
        return hasher.hexdigest()

    def _sync_claude_projection(self, bundle, target_root: Path) -> Path:
        target = target_root / f"deepscientist-{bundle.skill_id}.md"
        if bundle.claude_md and bundle.claude_md.exists():
            self._write_bytes_atomic(target, bundle.claude_md.read_bytes())
            return target
        self._write_bytes_atomic(target, self._render_claude_projection(bundle).encode("utf-8"))
        return target

    @staticmethod
    def _render_claude_projection(bundle) -> str:
        metadata, body = load_markdown_document(bundle.skill_md)
        title = str(metadata.get("name") or bundle.name or bundle.skill_id)
        description = str(metadata.get("description") or "").strip()
        parts = [f"# {title}", ""]
        if description:
            parts.extend([description, ""])
        parts.append(body.strip())
        return "\n".join(parts).rstrip() + "\n"

    def _sync_bundle_tree(self, source_root: Path, target_root: Path) -> None:
        ensure_dir(target_root)
        expected_paths: set[Path] = set()

        for source_path in sorted(source_root.rglob("*")):
            relative = source_path.relative_to(source_root)
            expected_paths.add(relative)
            target_path = target_root / relative
            if source_path.is_dir():
                ensure_dir(target_path)
                continue
            self._sync_file(source_path, target_path)

        for target_path in sorted(target_root.rglob("*"), reverse=True):
            relative = target_path.relative_to(target_root)
            if relative in expected_paths:
                continue
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink(missing_ok=True)

    def _sync_file(self, source_path: Path, target_path: Path) -> None:
        payload = source_path.read_bytes()
        if target_path.exists():
            try:
                if target_path.read_bytes() == payload:
                    return
            except OSError:
                pass
        self._write_bytes_atomic(target_path, payload)

    @staticmethod
    def _write_bytes_atomic(path: Path, payload: bytes) -> None:
        ensure_dir(path.parent)
        temp_path = path.parent / f".{path.name}.tmp-{uuid4().hex}"
        temp_path.write_bytes(payload)
        temp_path.replace(path)

    def _sync_prompt_tree(self, target_root: Path) -> None:
        source_root = self.repo_root / "src" / "prompts"
        self._sync_bundle_tree(source_root, target_root)

    @staticmethod
    def _prune_bundle_targets(root: Path, expected_names: set[str]) -> None:
        for target in sorted(root.glob("deepscientist-*"), reverse=True):
            if target.name in expected_names:
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

    def _release_sync_state_path(self) -> Path:
        return self.home / "runtime" / "skill-sync-state.json"

    def _read_release_sync_state(self) -> dict:
        payload = read_json(self._release_sync_state_path(), {})
        return payload if isinstance(payload, dict) else {}

    def _write_release_sync_state(self, payload: dict[str, object]) -> None:
        write_json(self._release_sync_state_path(), payload)
