from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ConfigManager
from ..shared import append_jsonl, ensure_dir, generate_id, slugify, utc_now
from .frontmatter import dump_markdown_document, load_markdown_document, load_markdown_document_from_text

MEMORY_KINDS = ("papers", "ideas", "decisions", "episodes", "knowledge", "templates")
MEMORY_READ_VISIBILITY_MODES = ("independent", "shared_across_quests")
SHARED_MEMORY_DOCUMENT_PREFIX = "sharedmemory::"


class MemoryService:
    def __init__(self, home: Path) -> None:
        self.home = home

    @staticmethod
    def normalize_read_visibility_mode(value: Any) -> str:
        normalized = str(value or "independent").strip().lower() or "independent"
        return normalized if normalized in MEMORY_READ_VISIBILITY_MODES else "independent"

    @staticmethod
    def _normalize_tags(tags: list[str] | str | None) -> list[str]:
        if tags is None:
            return []
        raw_values: list[object]
        if isinstance(tags, str):
            stripped = tags.strip()
            if not stripped:
                return []
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    raw_values = list(parsed)
                else:
                    raw_values = [part.strip() for part in stripped.split(",")]
            else:
                raw_values = [part.strip() for part in stripped.split(",")]
        else:
            raw_values = list(tags)

        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_values:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _root_for(self, scope: str, quest_root: Path | None = None) -> Path:
        if scope == "global":
            return self.home / "memory"
        if scope == "quest":
            if quest_root is None:
                raise ValueError("quest_root is required for quest-scoped memory")
            return quest_root / "memory"
        raise ValueError(f"Unknown memory scope: {scope}")

    def _resolve_existing_card(
        self,
        *,
        card_id: str | None = None,
        path: str | None = None,
        scope: str,
        quest_root: Path | None = None,
    ) -> Path:
        if path:
            candidate = Path(path)
            if candidate.exists():
                return candidate
        root = self._root_for(scope, quest_root)
        if card_id:
            for candidate in root.glob("**/*.md"):
                metadata, _body = load_markdown_document(candidate)
                if metadata.get("id") == card_id:
                    return candidate
        raise FileNotFoundError("Memory card not found")

    def read_visibility_mode(self) -> str:
        config = ConfigManager(self.home).load_runtime_config()
        memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        return self.normalize_read_visibility_mode(memory.get("read_visibility_mode"))

    def shared_read_enabled(self) -> bool:
        return self.read_visibility_mode() == "shared_across_quests"

    def _iter_initialized_quest_roots(self):
        quests_root = self.home / "quests"
        if not quests_root.exists():
            return
        for quest_yaml in sorted(quests_root.glob("*/quest.yaml")):
            quest_root = quest_yaml.parent
            yield quest_root.name, quest_root

    @staticmethod
    def _shared_document_id(*, source_quest_id: str, relative_path: str) -> str:
        relative = str(relative_path or "").lstrip("/")
        return f"{SHARED_MEMORY_DOCUMENT_PREFIX}{source_quest_id}::{relative}"

    @staticmethod
    def parse_shared_document_id(document_id: str) -> tuple[str, str] | None:
        raw = str(document_id or "").strip()
        if not raw.startswith(SHARED_MEMORY_DOCUMENT_PREFIX):
            return None
        _prefix, quest_id, relative = (raw.split("::", 2) + ["", "", ""])[:3]
        quest_id = quest_id.strip()
        relative = relative.lstrip("/")
        if not quest_id or not relative:
            return None
        return quest_id, relative

    def _normalize_metadata(
        self,
        *,
        kind: str,
        title: str,
        scope: str,
        quest_id: str | None,
        tags: list[str] | str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        seed = dict(metadata or {})
        seed.setdefault("id", generate_id(kind[:-1] if kind.endswith("s") else kind))
        seed["type"] = kind
        seed.setdefault("kind", kind[:-1] if kind.endswith("s") else kind)
        seed.setdefault("title", title)
        seed.setdefault("quest_id", quest_id)
        seed.setdefault("tags", self._normalize_tags(tags))
        seed.setdefault("created_at", now)
        seed["updated_at"] = now
        seed["scope"] = scope
        return seed

    def _list_cards_from_root(
        self,
        *,
        root: Path,
        kind: str | None = None,
        writable: bool = True,
        scope: str | None = None,
        source_quest_id: str | None = None,
        shared: bool = False,
        include_metadata: bool = False,
        include_body: bool = False,
    ) -> list[dict]:
        cards: list[dict] = []
        if not root.exists():
            return cards
        pattern = f"{kind}/*.md" if kind else "*/*.md"
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            metadata, body = load_markdown_document(path)
            entry = {
                "id": metadata.get("id"),
                "title": metadata.get("title", path.stem),
                "type": metadata.get("type"),
                "path": str(path),
                "document_id": (
                    self._shared_document_id(source_quest_id=source_quest_id, relative_path=relative)
                    if shared and source_quest_id
                    else f"memory::{relative}"
                ),
                "excerpt": body.strip().splitlines()[0] if body.strip() else "",
                "updated_at": metadata.get("updated_at"),
                "writable": writable,
                "scope": scope,
                "shared": shared,
            }
            if include_metadata:
                entry["metadata"] = metadata
            if include_body:
                entry["body"] = body
            if source_quest_id:
                entry["source_quest_id"] = source_quest_id
            cards.append(entry)
        return cards

    @staticmethod
    def _card_timestamp(card: dict[str, Any]) -> float:
        updated_at = str(card.get("updated_at") or "").strip()
        try:
            return datetime.fromisoformat(updated_at).timestamp() if updated_at else float("-inf")
        except ValueError:
            return float("-inf")

    @classmethod
    def _visible_card_sort_key(cls, card: dict[str, Any], *, active_quest_id: str | None = None) -> tuple[int, float, str]:
        source_quest_id = str(card.get("source_quest_id") or "").strip()
        scope = str(card.get("scope") or "").strip()
        if active_quest_id and source_quest_id and source_quest_id == active_quest_id:
            rank = 0
        elif scope in {"quest", "shared_quest"}:
            rank = 1
        elif scope == "global":
            rank = 2
        else:
            rank = 3
        return (rank, -cls._card_timestamp(card), str(card.get("path") or ""))

    def _visible_quest_roots(
        self,
        *,
        active_quest_root: Path,
        active_quest_id: str,
        include_shared: bool,
    ) -> list[tuple[str, Path, bool]]:
        roots: list[tuple[str, Path, bool]] = [(active_quest_id, active_quest_root, False)]
        if not include_shared:
            return roots
        for quest_id, quest_root in self._iter_initialized_quest_roots() or []:
            if quest_id == active_quest_id:
                continue
            roots.append((quest_id, quest_root, True))
        return roots

    def write_card(
        self,
        *,
        scope: str,
        kind: str,
        title: str,
        body: str = "",
        markdown: str | None = None,
        quest_root: Path | None = None,
        quest_id: str | None = None,
        tags: list[str] | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        if kind not in MEMORY_KINDS:
            raise ValueError(f"Unknown memory kind: {kind}")
        root = self._root_for(scope, quest_root)
        folder = ensure_dir(root / kind)
        if markdown and markdown.lstrip().startswith("---"):
            parsed_metadata, parsed_body = load_markdown_document_from_text(markdown)
            title = str(parsed_metadata.get("title") or title or "Untitled")
            body = parsed_body
            metadata = {**parsed_metadata, **(metadata or {})}
        normalized = self._normalize_metadata(
            kind=kind,
            title=title,
            scope=scope,
            quest_id=quest_id,
            tags=tags,
            metadata=metadata,
        )
        filename = f"{slugify(title, kind)}.md"
        path = folder / filename
        path.write_text(dump_markdown_document(normalized, body), encoding="utf-8")
        self._append_index(folder / "_index.jsonl", path, normalized, body)
        return self.read_card(path=str(path), scope=scope, quest_root=quest_root)

    def read_card(
        self,
        *,
        card_id: str | None = None,
        path: str | None = None,
        scope: str = "global",
        quest_root: Path | None = None,
    ) -> dict:
        resolved = self._resolve_existing_card(card_id=card_id, path=path, scope=scope, quest_root=quest_root)
        metadata, body = load_markdown_document(resolved)
        return {
            "id": metadata.get("id"),
            "title": metadata.get("title", resolved.stem),
            "type": metadata.get("type"),
            "scope": metadata.get("scope", scope),
            "path": str(resolved),
            "metadata": metadata,
            "body": body,
            "updated_at": metadata.get("updated_at"),
            "excerpt": body.strip().splitlines()[0] if body.strip() else "",
        }

    def list_cards(
        self,
        *,
        scope: str = "global",
        quest_root: Path | None = None,
        limit: int = 30,
        kind: str | None = None,
    ) -> list[dict]:
        root = self._root_for(scope, quest_root)
        cards = self._list_cards_from_root(
            root=root,
            kind=kind,
            writable=True,
            scope=scope,
            source_quest_id=quest_root.name if scope == "quest" and quest_root is not None else None,
            shared=False,
        )
        return cards[-limit:]

    def list_recent(
        self,
        *,
        scope: str = "global",
        quest_root: Path | None = None,
        limit: int = 20,
        kind: str | None = None,
    ) -> list[dict]:
        cards = self.list_cards(scope=scope, quest_root=quest_root, limit=5000, kind=kind)
        cards.sort(key=self._card_sort_key, reverse=True)
        return cards[:limit]

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
                include_metadata=True,
                include_body=True,
            ):
                row = self._summary_row(raw, raw["metadata"], source_scope)
                # Defensive: legacy quest 010 cards stored experience metadata
                # (claim/mechanism/subtype) as a body-leading frontmatter block
                # rather than merging it into the top-level frontmatter. Fall
                # back to that block when top-level fields are missing.
                self._merge_body_frontmatter_fallback(row, raw.get("body") or "")
                # Pre-attach `path` for deterministic tie-break in `_card_sort_key`;
                # popped below before returning so consumers don't see it.
                row["path"] = raw["path"]
                rows.append(row)

        rows.sort(key=self._card_sort_key, reverse=True)
        for row in rows:
            row.pop("path", None)
        return rows

    @staticmethod
    def _merge_body_frontmatter_fallback(row: dict[str, Any], body: str) -> None:
        """If `body` starts with a YAML frontmatter block, parse it and use it
        to fill missing values in `row`. Top-level metadata always wins — this
        is a fallback for legacy "dual-frontmatter" knowledge cards where
        experience fields (claim/mechanism/subtype) live in a body-leading
        block instead of merged into the top-level frontmatter.
        """
        if not body or not body.lstrip().startswith("---"):
            return
        try:
            body_metadata, _rest = load_markdown_document_from_text(body)
        except Exception:
            # Malformed body frontmatter — silently skip (top-level still wins).
            return
        if not isinstance(body_metadata, dict) or not body_metadata:
            return

        for field in ("claim", "mechanism"):
            if not row.get(field):
                value = body_metadata.get(field)
                if value:
                    row[field] = str(value).strip()

        if not row.get("subtype"):
            subtype = body_metadata.get("subtype")
            if subtype:
                row["subtype"] = str(subtype).strip()

        if not row.get("keywords"):
            kws = body_metadata.get("keywords")
            if isinstance(kws, list):
                row["keywords"] = [str(k).strip() for k in kws if str(k).strip()]

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

    def search(
        self,
        query: str,
        *,
        scope: str = "global",
        quest_root: Path | None = None,
        limit: int = 20,
        kind: str | None = None,
    ) -> list[dict]:
        query_lower = query.lower()
        matches: list[dict] = []
        scopes = [scope]
        if scope == "both":
            scopes = ["quest", "global"]
        for resolved_scope in scopes:
            if resolved_scope == "quest" and quest_root is None:
                continue
            for card in self.list_cards(scope=resolved_scope, quest_root=quest_root, limit=500, kind=kind):
                content = Path(card["path"]).read_text(encoding="utf-8").lower()
                if query_lower in content:
                    match = dict(card)
                    match["scope"] = resolved_scope
                    matches.append(match)
        matches.sort(key=self._card_sort_key, reverse=True)
        return matches[:limit]

    def list_visible_quest_cards(
        self,
        *,
        active_quest_root: Path,
        active_quest_id: str | None = None,
        limit: int = 30,
        kind: str | None = None,
        include_shared: bool | None = None,
    ) -> list[dict]:
        resolved_active_quest_id = str(active_quest_id or active_quest_root.name).strip() or active_quest_root.name
        shared_enabled = self.shared_read_enabled() if include_shared is None else bool(include_shared)
        if not shared_enabled:
            return self.list_cards(scope="quest", quest_root=active_quest_root, limit=limit, kind=kind)

        cards: list[dict] = []
        for quest_id, quest_root, shared in self._visible_quest_roots(
            active_quest_root=active_quest_root,
            active_quest_id=resolved_active_quest_id,
            include_shared=shared_enabled,
        ):
            cards.extend(
                self._list_cards_from_root(
                    root=quest_root / "memory",
                    kind=kind,
                    writable=not shared,
                    scope="shared_quest" if shared else "quest",
                    source_quest_id=quest_id,
                    shared=shared,
                )
            )
        cards.sort(key=lambda item: self._visible_card_sort_key(item, active_quest_id=resolved_active_quest_id))
        return cards[:limit]

    def search_visible_quest_cards(
        self,
        query: str,
        *,
        active_quest_root: Path,
        active_quest_id: str | None = None,
        limit: int = 20,
        kind: str | None = None,
        include_shared: bool | None = None,
    ) -> list[dict]:
        resolved_active_quest_id = str(active_quest_id or active_quest_root.name).strip() or active_quest_root.name
        shared_enabled = self.shared_read_enabled() if include_shared is None else bool(include_shared)
        if not shared_enabled:
            return self.search(query, scope="quest", quest_root=active_quest_root, limit=limit, kind=kind)

        query_lower = query.lower()
        matches: list[dict] = []
        for quest_id, quest_root, shared in self._visible_quest_roots(
            active_quest_root=active_quest_root,
            active_quest_id=resolved_active_quest_id,
            include_shared=shared_enabled,
        ):
            cards = self._list_cards_from_root(
                root=quest_root / "memory",
                kind=kind,
                writable=not shared,
                scope="shared_quest" if shared else "quest",
                source_quest_id=quest_id,
                shared=shared,
            )
            for card in cards:
                content = Path(card["path"]).read_text(encoding="utf-8").lower()
                if query_lower in content:
                    matches.append(card)
        matches.sort(key=lambda item: self._visible_card_sort_key(item, active_quest_id=resolved_active_quest_id))
        return matches[:limit]

    def promote_to_global(
        self,
        *,
        card_id: str | None = None,
        path: str | None = None,
        quest_root: Path,
    ) -> dict:
        current = self.read_card(card_id=card_id, path=path, scope="quest", quest_root=quest_root)
        metadata = dict(current["metadata"])
        metadata["scope"] = "global"
        metadata["promoted_from"] = {
            "quest_root": str(quest_root),
            "path": current["path"],
        }
        return self.write_card(
            scope="global",
            kind=str(metadata.get("type") or "knowledge"),
            title=str(metadata.get("title") or "Promoted memory"),
            body=current["body"],
            metadata=metadata,
        )

    @staticmethod
    def _append_index(path: Path, card_path: Path, metadata: dict[str, Any], body: str) -> None:
        append_jsonl(
            path,
            {
                "id": metadata.get("id"),
                "title": metadata.get("title"),
                "type": metadata.get("type"),
                "path": str(card_path),
                "quest_id": metadata.get("quest_id"),
                "scope": metadata.get("scope"),
                "tags": metadata.get("tags", []),
                "updated_at": metadata.get("updated_at"),
                "excerpt": body.strip().splitlines()[0] if body.strip() else "",
            },
        )

    @staticmethod
    def _card_sort_key(card: dict[str, Any]) -> tuple[float, str]:
        updated_at = str(card.get("updated_at") or "").strip()
        try:
            parsed = datetime.fromisoformat(updated_at).timestamp() if updated_at else float("-inf")
        except ValueError:
            parsed = float("-inf")
        return parsed, str(card.get("path") or "")
