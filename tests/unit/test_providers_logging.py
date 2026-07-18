"""Tests for aiforge.providers.logging."""

from __future__ import annotations

import logging

import pytest

from aiforge.providers.logging import log_request_error, log_request_start, log_response
from aiforge.providers.types import ChatRequest, ChatResponse, Message, Role, Usage


def _request() -> ChatRequest:
    return ChatRequest(messages=(Message(role=Role.USER, content="hi"),), model="m")


def test_log_request_start_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="aiforge.providers.logging"):
        log_request_start("fake", _request())


def test_log_response_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    response = ChatResponse(
        text="hi", model="m", provider="fake", usage=Usage(input_tokens=1, output_tokens=1)
    )
    with caplog.at_level(logging.DEBUG, logger="aiforge.providers.logging"):
        log_response("fake", response, elapsed_s=0.01)


def test_log_request_error_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="aiforge.providers.logging"):
        log_request_error("fake", ValueError("boom"), elapsed_s=0.01)
