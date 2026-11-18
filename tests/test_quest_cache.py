from __future__ import annotations

import gc
import weakref

from deepscientist.quest.cache import BoundedCache


def test_byte_budget_evicts_cold_entries_and_preserves_recent_reads() -> None:
    cache = BoundedCache(max_bytes=2048)
    cache["first"] = {"text": "a" * 400}
    cache["second"] = {"text": "b" * 400}
    assert cache.get("first") == {"text": "a" * 400}

    cache["third"] = {"text": "c" * 400}

    assert cache.get("second") is None
    assert cache.get("first") == {"text": "a" * 400}
    assert cache.get("third") == {"text": "c" * 400}


def test_entry_limit_bounds_small_payload_bookkeeping() -> None:
    cache = BoundedCache(max_bytes=1024 * 1024, max_entries=2)
    cache["first"] = {"text": "first"}
    cache["second"] = {"text": "second"}
    cache["third"] = {"text": "third"}

    assert cache.get("first") is None
    assert cache.get("second") == {"text": "second"}
    assert cache.get("third") == {"text": "third"}


def test_oversized_replacement_discards_stale_value_without_evicting_other_reads() -> None:
    cache = BoundedCache(max_bytes=2048)
    cache["changed"] = {"text": "old"}
    cache["hot"] = {"text": "keep"}

    retained = cache.put("changed", {"records": ["x" * 1024 + str(index) for index in range(8)]})

    assert retained is False
    assert cache.get("changed") is None
    assert cache.get("hot") == {"text": "keep"}


def test_eviction_and_explicit_removal_release_retained_objects() -> None:
    class Payload(dict):
        pass

    cache = BoundedCache(max_entries=1)
    first = Payload(text="first")
    first_reference = weakref.ref(first)
    cache["first"] = first
    del first
    cache["second"] = Payload(text="second")
    gc.collect()
    assert first_reference() is None

    second_reference = weakref.ref(cache.get("second"))
    cache.pop("second")
    gc.collect()
    assert second_reference() is None
    assert cache.retained_bytes == 0


def test_shared_nested_values_are_not_charged_repeatedly() -> None:
    cache = BoundedCache(max_bytes=4096)
    payload = {"records": ["x" * 1024] * 100}

    assert cache.put("shared", payload) is True
    assert cache.get("shared") == payload
    assert cache.retained_bytes <= 4096
