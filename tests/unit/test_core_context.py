"""Tests for aiforge.core.context."""

from __future__ import annotations

from aiforge.core.context import TaskContext, TaskRequest


def test_task_request_defaults() -> None:
    request = TaskRequest(prompt="hello")
    assert request.system is None
    assert request.provider is None
    assert request.model is None
    assert request.skills == ()
    assert request.file_hints == ()
    assert request.max_tokens is None
    assert request.stream is False
    assert request.metadata == {}


def test_task_request_accepts_overrides() -> None:
    request = TaskRequest(
        prompt="hi",
        system="be terse",
        provider="anthropic",
        model="claude-opus-4-8",
        skills=("python",),
        file_hints=("main.py",),
        max_tokens=100,
        stream=True,
        metadata={"trace_id": "abc"},
    )
    assert request.skills == ("python",)
    assert request.metadata["trace_id"] == "abc"


def test_task_request_metadata_defaults_are_independent() -> None:
    a = TaskRequest(prompt="a")
    b = TaskRequest(prompt="b")
    a.metadata["x"] = 1
    assert b.metadata == {}


def test_task_context_wraps_request_and_resolution() -> None:
    request = TaskRequest(prompt="hello")
    context = TaskContext(
        request=request,
        provider_name="anthropic",
        model="claude-opus-4-8",
        resolved_skills=("python",),
        composed_system="You are a Python expert.",
    )
    assert context.request is request
    assert context.provider_name == "anthropic"
    assert context.resolved_skills == ("python",)
