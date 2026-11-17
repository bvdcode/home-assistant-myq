import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.myq.exceptions import MyQRateLimitError
from custom_components.myq.tend_protocol import TendCameraTarget, TendStreamError
from custom_components.myq.tend_stream import TendLiveStream

TARGET = TendCameraTarget(destination="account:camera")


@pytest.fixture
def open_session() -> Generator[AsyncMock]:
    with patch(
        "custom_components.myq.tend_stream.TendSession.open", new_callable=AsyncMock
    ) as opened:
        opened.return_value = MagicMock(ended=False, close=AsyncMock())
        yield opened


async def test_reconnect_reuses_preparation_started_at_session_loss(
    open_session: AsyncMock,
) -> None:
    prepare = AsyncMock(return_value=TARGET)
    stream = TendLiveStream(prepare, AsyncMock(return_value="token"), prepare_on_disconnect=True)
    started, release = asyncio.Event(), asyncio.Event()

    async def wake() -> TendCameraTarget:
        started.set()
        await release.wait()
        return TARGET

    try:
        original = await stream._subscribe()
        prepare.side_effect = wake
        open_session.return_value.ended = True
        stream._on_frame(b"")
        stream._on_frame(b"")
        stream._unsubscribe(original)
        await asyncio.wait_for(started.wait(), 1)
        prepare.assert_awaited()
        assert prepare.await_count == 2

        reconnect = asyncio.create_task(stream._subscribe())
        await asyncio.sleep(0)
        assert not reconnect.done()
        assert prepare.await_count == 2
        release.set()
        await asyncio.wait_for(reconnect, 1)

        assert prepare.await_count == 2
        assert open_session.await_count == 2
        assert stream._target_task is None
    finally:
        await stream.close()


@pytest.mark.parametrize(("enabled", "with_viewer"), [(False, True), (True, False)])
async def test_session_loss_without_keypad_demand_stays_passive(
    open_session: AsyncMock, enabled: bool, with_viewer: bool
) -> None:
    prepare = AsyncMock(return_value=TARGET)
    stream = TendLiveStream(prepare, AsyncMock(return_value="token"), prepare_on_disconnect=enabled)
    try:
        viewer = await stream._subscribe()
        if not with_viewer:
            stream._unsubscribe(viewer)
        open_session.return_value.ended = True

        stream._on_frame(b"")
        await asyncio.sleep(0)

        prepare.assert_awaited_once()
        open_session.assert_awaited_once()
    finally:
        await stream.close()


async def test_removal_cancels_preparation_before_any_retry_subscribes(
    open_session: AsyncMock,
) -> None:
    started, stopped = asyncio.Event(), asyncio.Event()
    prepare = AsyncMock(return_value=TARGET)
    stream = TendLiveStream(prepare, AsyncMock(return_value="token"), prepare_on_disconnect=True)

    async def wake() -> TendCameraTarget:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return TARGET

    await stream._subscribe()
    prepare.side_effect = wake
    open_session.return_value.ended = True
    stream._on_frame(b"")
    await asyncio.wait_for(started.wait(), 1)

    await asyncio.wait_for(stream.close(), 1)

    assert stopped.is_set()
    assert stream._target_task is None
    open_session.assert_awaited_once()


async def test_idle_cleanup_discards_prepared_target_before_a_later_viewer(
    open_session: AsyncMock,
) -> None:
    prepare = AsyncMock(return_value=TARGET)
    stream = TendLiveStream(prepare, AsyncMock(return_value="token"), prepare_on_disconnect=True)
    try:
        viewer = await stream._subscribe()
        open_session.return_value.ended = True
        stream._on_frame(b"")
        await asyncio.sleep(0)
        assert prepare.await_count == 2
        stream._unsubscribe(viewer)

        await stream._close_if_idle()
        assert stream._target_task is None
        await stream._subscribe()

        assert prepare.await_count == 3
        assert open_session.await_count == 2
    finally:
        await stream.close()


async def test_preparation_failure_retains_cooldown_for_the_retry(
    open_session: AsyncMock,
) -> None:
    prepare = AsyncMock(return_value=TARGET)
    stream = TendLiveStream(prepare, AsyncMock(return_value="token"), prepare_on_disconnect=True)
    try:
        viewer = await stream._subscribe()
        prepare.side_effect = MyQRateLimitError(90)
        open_session.return_value.ended = True
        stream._on_frame(b"")
        stream._unsubscribe(viewer)
        await asyncio.sleep(0)

        with pytest.raises(TendStreamError, match=r"MyQRateLimitError.*retry after 90s"):
            await stream._subscribe()

        assert prepare.await_count == 2
        assert stream._target_task is None
        open_session.assert_awaited_once()
    finally:
        await stream.close()
