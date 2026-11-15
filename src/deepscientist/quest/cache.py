from __future__ import annotations

from collections import OrderedDict, deque
from itertools import chain
import sys
from typing import Any


def _retained_size(value: Any, limit: int) -> int:
    """Charge the reachable built-in containers once, stopping at the budget."""
    seen: set[int] = set()
    pending = [iter((value,))]
    total = 0
    while pending:
        try:
            item = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        identity = id(item)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(item)
        if total > limit:
            return total
        # Iterate lazily rather than copying a potentially oversized container.
        if isinstance(item, dict):
            pending.append(chain(item.keys(), item.values()))
        elif isinstance(item, (list, tuple, set, frozenset, deque)):
            pending.append(iter(item))
    return total


class BoundedCache:
    """LRU retention for JSON-like reader entries, not a process memory limit.

    Callers synchronize access and must not mutate values after insertion.
    The byte charge includes keys and reachable values; the entry limit also
    bounds bookkeeping. Oversized values are read normally but not retained.
    """

    def __init__(self, *, max_bytes: int = 64 * 1024 * 1024, max_entries: int = 2048) -> None:
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[dict[str, Any], int]] = OrderedDict()
        self._retained_bytes = 0

    @property
    def retained_bytes(self) -> int:
        return self._retained_bytes

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            return default
        self._entries.move_to_end(key)
        return entry[0]

    def pop(self, key: str, default: Any = None) -> Any:
        entry = self._entries.pop(key, None)
        if entry is None:
            return default
        self._retained_bytes -= entry[1]
        return entry[0]

    def put(self, key: str, value: dict[str, Any]) -> bool:
        self.pop(key)
        if self.max_bytes <= 0 or self.max_entries <= 0:
            return False
        size = _retained_size((key, value), self.max_bytes)
        if size > self.max_bytes:
            return False
        while self._entries and (
            self._retained_bytes + size > self.max_bytes
            or len(self._entries) >= self.max_entries
        ):
            _, (_, evicted_size) = self._entries.popitem(last=False)
            self._retained_bytes -= evicted_size
        self._entries[key] = (value, size)
        self._retained_bytes += size
        return True

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        self.put(key, value)
