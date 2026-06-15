import asyncio
import logging

log = logging.getLogger("jobs")


class JobRegistry:
    def __init__(self):
        self._active: dict[str, asyncio.Task] = {}

    def is_active(self, job_id: str) -> bool:
        return job_id in self._active

    def start(self, job_id: str, coro) -> bool:
        if job_id in self._active:
            return False
        task = asyncio.create_task(self._wrap(job_id, coro))
        self._active[job_id] = task
        return True

    async def _wrap(self, job_id: str, coro):
        try:
            await coro
        except Exception as e:  # never crash the loop
            log.exception("job %s failed: %s", job_id, e)
        finally:
            self._active.pop(job_id, None)

    async def wait_all(self):
        while self._active:
            await asyncio.gather(*list(self._active.values()))
