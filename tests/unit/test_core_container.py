"""Tests for aiforge.core.container."""

from __future__ import annotations

import pytest

from aiforge.core.container import Container, Key


def test_singleton_returns_same_instance() -> None:
    container = Container()
    key: Key[list[int]] = Key("numbers")
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [1, 2, 3]

    container.register(key, factory)
    first = container.resolve(key)
    second = container.resolve(key)
    assert first is second
    assert calls == [1]


def test_non_singleton_builds_fresh_instance_each_time() -> None:
    container = Container()
    key: Key[object] = Key("fresh")
    container.register(key, lambda: object(), singleton=False)
    first = container.resolve(key)
    second = container.resolve(key)
    assert first is not second


def test_register_instance_is_returned_directly() -> None:
    container = Container()
    key: Key[str] = Key("greeting")
    container.register_instance(key, "hello")
    assert container.resolve(key) == "hello"


def test_singleton_resolve_is_thread_safe() -> None:
    # Regression: resolve() used an unlocked check-then-build-then-cache,
    # so concurrent first resolves each invoked the factory.
    import threading
    import time

    container = Container()
    key: Key[object] = Key("slow")
    calls: list[int] = []

    def factory() -> object:
        calls.append(1)
        time.sleep(0.05)
        return object()

    container.register(key, factory)
    barrier = threading.Barrier(8)
    results: list[object] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        instance = container.resolve(key)
        with results_lock:
            results.append(instance)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1
    assert all(r is results[0] for r in results)


def test_resolve_missing_key_raises_key_error() -> None:
    container = Container()
    key: Key[object] = Key("missing")
    with pytest.raises(KeyError):
        container.resolve(key)


def test_has_reflects_registration_state() -> None:
    container = Container()
    key: Key[object] = Key("thing")
    assert container.has(key) is False
    container.register(key, lambda: object())
    assert container.has(key) is True


def test_reset_forces_rebuild() -> None:
    container = Container()
    key: Key[list[int]] = Key("numbers")
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [len(calls)]

    container.register(key, factory)
    first = container.resolve(key)
    container.reset(key)
    second = container.resolve(key)
    assert first is not second
    assert calls == [1, 1]


def test_reset_all_clears_every_cached_instance() -> None:
    container = Container()
    key_a: Key[object] = Key("a")
    key_b: Key[object] = Key("b")
    container.register(key_a, lambda: object())
    container.register(key_b, lambda: object())
    a1, b1 = container.resolve(key_a), container.resolve(key_b)
    container.reset()
    a2, b2 = container.resolve(key_a), container.resolve(key_b)
    assert a1 is not a2
    assert b1 is not b2


def test_distinct_keys_with_same_label_are_independent() -> None:
    container = Container()
    key1: Key[str] = Key("dup")
    key2: Key[str] = Key("dup")
    container.register_instance(key1, "one")
    container.register_instance(key2, "two")
    assert container.resolve(key1) == "one"
    assert container.resolve(key2) == "two"


def test_re_registering_replaces_and_clears_cached_instance() -> None:
    container = Container()
    key: Key[str] = Key("value")
    container.register_instance(key, "old")
    assert container.resolve(key) == "old"
    container.register(key, lambda: "new")
    assert container.resolve(key) == "new"
