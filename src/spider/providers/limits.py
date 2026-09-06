"""Service-owned request limits. Unknown excess origins share a bounded fallback."""
import asyncio
import time
from email.utils import parsedate_to_datetime


class Lease:
    def __init__(self, *semaphores):
        self.semaphores = semaphores

    def release(self):
        for semaphore in self.semaphores:
            semaphore.release()
        self.semaphores = ()


class OriginLimits:
    def __init__(self, total=8, per_origin=2, max_origins=128, clock=time.monotonic, sleep=asyncio.sleep):
        self.total = asyncio.Semaphore(total)
        self.per_origin, self.max_origins = per_origin, max_origins
        self.origins = {}
        self.overflow = asyncio.Semaphore(per_origin)
        self.clock, self.sleep, self.cooldowns = clock, sleep, {}

    def feedback(self, origin, status, retry_after=None):
        if status != 429:
            return
        delay = 1.0
        if isinstance(retry_after, str) and len(retry_after) <= 80:
            try:
                delay = float(retry_after) if retry_after.isdigit() else parsedate_to_datetime(retry_after).timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                pass
        delay = min(30, max(0, delay))
        key = origin if origin in self.origins else None
        self.cooldowns[key] = max(self.cooldowns.get(key, 0), self.clock() + delay)

    async def acquire(self, origin):
        slot = self.origins.get(origin)
        if slot is None:
            slot = asyncio.Semaphore(self.per_origin) if len(self.origins) < self.max_origins else self.overflow
            if slot is not self.overflow:
                self.origins[origin] = slot
        await slot.acquire()
        try:
            key = origin if origin in self.origins else None
            while self.cooldowns.get(key, 0) > self.clock():
                await self.sleep(self.cooldowns[key] - self.clock())
            await self.total.acquire()
        except BaseException:
            slot.release()
            raise
        return Lease(self.total, slot)
