"""In-process handoff for browser challenges that require the local user.

Only operational metadata is exposed. Targets, URLs, page content and profile
data never enter this registry.
"""
import asyncio
import threading
import time
import uuid
from dataclasses import dataclass


@dataclass
class _PendingChallenge:
    challenge_id: str
    run_id: str
    source: str
    created_at: float
    expires_at: float
    event: asyncio.Event
    loop: asyncio.AbstractEventLoop

    def public(self):
        return {
            "challenge_id": self.challenge_id,
            "source": self.source,
            "state": "HUMAN_REQUIRED",
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class BrowserChallengeRegistry:
    """Bounded, restart-safe-by-design registry for open local browser tabs."""

    def __init__(self, max_pending=16, clock=time.time):
        self.max_pending = max(1, int(max_pending))
        self.clock = clock
        self._lock = threading.Lock()
        self._pending = {}

    def _prune_locked(self):
        now = self.clock()
        expired = [key for key, item in self._pending.items()
                   if item.expires_at <= now or item.event.is_set()]
        for key in expired:
            self._pending.pop(key, None)

    async def wait(self, run_id, source, timeout_seconds):
        timeout_seconds = max(0.01, min(float(timeout_seconds), 900.0))
        loop = asyncio.get_running_loop()
        item = _PendingChallenge(
            challenge_id=uuid.uuid4().hex,
            run_id=str(run_id)[:128],
            source=str(source)[:64],
            created_at=self.clock(),
            expires_at=self.clock() + timeout_seconds,
            event=asyncio.Event(),
            loop=loop,
        )
        key = (item.run_id, item.challenge_id)
        with self._lock:
            self._prune_locked()
            if len(self._pending) >= self.max_pending:
                return "FULL"
            self._pending[key] = item
        try:
            await asyncio.wait_for(item.event.wait(), timeout=timeout_seconds)
            return "CONTINUE"
        except asyncio.TimeoutError:
            return "TIMEOUT"
        finally:
            with self._lock:
                self._pending.pop(key, None)

    def list_for_run(self, run_id):
        with self._lock:
            self._prune_locked()
            items = [item.public() for item in self._pending.values()
                     if item.run_id == run_id]
        return sorted(items, key=lambda item: (item["created_at"], item["challenge_id"]))

    def continue_run(self, run_id):
        with self._lock:
            self._prune_locked()
            items = [item for item in self._pending.values() if item.run_id == run_id]
        for item in items:
            item.loop.call_soon_threadsafe(item.event.set)
        return len(items)


browser_challenges = BrowserChallengeRegistry()
