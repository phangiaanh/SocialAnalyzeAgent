import asyncio
import pytest
from app.jobs import JobRegistry


@pytest.mark.anyio
async def test_dedup_and_completion():
    reg = JobRegistry()
    ran = []

    async def work():
        await asyncio.sleep(0.01)
        ran.append(1)

    assert reg.start("j1", work()) is True
    # duplicate while active -> rejected (close the coroutine we won't run)
    dup = work()
    assert reg.start("j1", dup) is False
    dup.close()
    await reg.wait_all()
    assert ran == [1]
    assert reg.is_active("j1") is False
