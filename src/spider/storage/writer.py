import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

class SingleDBWriter:
    """
    Asynchronous single DB writer coroutine.
    Consumes transactions from an asyncio.Queue, guaranteeing sequential atomic write
    operations to SQLite with zero lock contention.
    """
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self.queue.join()
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def submit(self, write_func: Callable[[AsyncSession], Coroutine[Any, Any, Any]]) -> Any:
        fut = asyncio.get_running_loop().create_future()
        await self.queue.put((write_func, fut))
        return await fut

    async def _writer_loop(self) -> None:
        while self._running:
            try:
                item = await self.queue.get()
                if item is None:
                    self.queue.task_done()
                    break
                write_func, fut = item
                try:
                    async with self.db_manager.session_factory() as session:
                        async with session.begin():
                            result = await write_func(session)
                        if not fut.done():
                            fut.set_result(result)
                except Exception as ex:
                    logger.error("DB writer transaction failed (%s)", type(ex).__name__)
                    if not fut.done():
                        fut.set_exception(ex)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Unexpected DB writer failure (%s)", type(e).__name__)
