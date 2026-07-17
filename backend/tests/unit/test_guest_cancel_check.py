"""Regression: guest cancel_check must not treat async is_disconnected() as True."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from payroll_copilot.presentation.api.routes.extraction import _client_disconnect_cancel_check


@pytest.mark.asyncio
async def test_raw_is_disconnected_coroutine_is_truthy_bug() -> None:
    """Documents the false-cancellation bug: sync call returns a truthy coroutine."""

    class _Req:
        async def is_disconnected(self) -> bool:
            return False

    broken = lambda: _Req().is_disconnected()  # noqa: E731 — mirrors the old route bug
    value = broken()
    assert asyncio.iscoroutine(value)
    assert bool(value) is True  # would falsely cancel every extraction
    value.close()


@pytest.mark.asyncio
async def test_client_disconnect_cancel_check_false_while_connected() -> None:
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)
    cancel_check, watch = _client_disconnect_cancel_check(request)
    try:
        await asyncio.sleep(0.05)
        assert cancel_check() is False
    finally:
        watch.cancel()
        await asyncio.gather(watch, return_exceptions=True)


@pytest.mark.asyncio
async def test_client_disconnect_cancel_check_true_after_disconnect() -> None:
    request = AsyncMock()
    request.is_disconnected = AsyncMock(side_effect=[False, True])
    cancel_check, watch = _client_disconnect_cancel_check(request)
    try:
        for _ in range(20):
            if cancel_check():
                break
            await asyncio.sleep(0.05)
        assert cancel_check() is True
    finally:
        watch.cancel()
        await asyncio.gather(watch, return_exceptions=True)
