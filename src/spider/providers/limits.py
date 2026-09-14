"""Service-owned request limits with one active request per origin by default."""
import asyncio
import json
import os
import time
from email.utils import parsedate_to_datetime
from pathlib import Path


class Lease:
    def __init__(self, *semaphores):
        self.semaphores = semaphores

    def release(self):
        for semaphore in self.semaphores:
            semaphore.release()
        self.semaphores = ()


class OriginLimits:
    def __init__(self, total=4, per_origin=1, max_origins=128, clock=time.monotonic,
                 sleep=asyncio.sleep, persistence_path=None, wall_clock=time.time):
        self.total = asyncio.Semaphore(total)
        self.per_origin, self.max_origins = per_origin, max_origins
        self.origins = {}
        self.overflow = asyncio.Semaphore(per_origin)
        self.clock, self.sleep, self.cooldowns = clock, sleep, {}
        self.wall_clock = wall_clock
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.wall_cooldowns, self.strikes = {}, {}
        self._load()

    @staticmethod
    def _origin(origin):
        return str(origin or "unknown").strip().casefold()[:253]

    def _load(self):
        if not self.persistence_path:
            return
        try:
            payload = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            if payload.get("version") != 1 or not isinstance(payload.get("origins"), dict):
                return
            now = self.wall_clock()
            for origin, row in payload["origins"].items():
                until = float(row.get("until", 0))
                if until > now and isinstance(origin, str) and len(origin) <= 253:
                    self.wall_cooldowns[origin] = until
                    self.strikes[origin] = max(0, min(int(row.get("strikes", 0)), 12))
        except (OSError, ValueError, TypeError, AttributeError):
            # Cooldown state is an optimization. Corruption cannot stop SPIDER.
            return

    def _persist(self):
        if not self.persistence_path:
            return
        now = self.wall_clock()
        origins = {origin: {"until": until, "strikes": self.strikes.get(origin, 0)}
                   for origin, until in self.wall_cooldowns.items() if until > now}
        payload = json.dumps({"version": 1, "origins": origins}, separators=(",", ":"))
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.persistence_path.with_suffix(self.persistence_path.suffix + ".tmp")
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, self.persistence_path)
        except OSError:
            return

    def feedback(self, origin, status, retry_after=None):
        origin = self._origin(origin)
        if isinstance(status, int) and 200 <= status < 400:
            self.strikes.pop(origin, None)
            self.cooldowns.pop(origin, None)
            self.wall_cooldowns.pop(origin, None)
            self._persist()
            return
        if status not in (429, 503, "CHALLENGE", "NETWORK_ERROR"):
            return
        strike = min(12, self.strikes.get(origin, 0) + 1)
        self.strikes[origin] = strike
        delay = min(3600.0, 30.0 * (2 ** (strike - 1)))
        if isinstance(retry_after, str) and len(retry_after) <= 80:
            try:
                delay = (float(retry_after) if retry_after.isdigit()
                         else parsedate_to_datetime(retry_after).timestamp() - self.wall_clock())
            except (ValueError, TypeError, OverflowError):
                pass
        if status == "CHALLENGE" and retry_after is None:
            delay = max(delay, 900.0)
        delay = min(86400.0, max(0.0, delay))
        key = origin if origin in self.origins else None
        self.cooldowns[key] = max(self.cooldowns.get(key, 0), self.clock() + delay)
        self.wall_cooldowns[origin] = max(self.wall_cooldowns.get(origin, 0),
                                          self.wall_clock() + delay)
        self._persist()

    async def acquire(self, origin):
        origin = self._origin(origin)
        slot = self.origins.get(origin)
        if slot is None:
            slot = asyncio.Semaphore(self.per_origin) if len(self.origins) < self.max_origins else self.overflow
            if slot is not self.overflow:
                self.origins[origin] = slot
        await slot.acquire()
        try:
            key = origin if origin in self.origins else None
            while True:
                monotonic_wait = self.cooldowns.get(key, 0) - self.clock()
                wall_wait = (self.wall_cooldowns.get(origin, 0) - self.wall_clock()
                             if self.persistence_path else 0)
                delay = max(monotonic_wait, wall_wait)
                if delay <= 0:
                    break
                await self.sleep(delay)
            await self.total.acquire()
        except BaseException:
            slot.release()
            raise
        return Lease(self.total, slot)
