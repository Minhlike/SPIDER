"""Network work may overlap; entity admission and graph writes stay ordered."""
import asyncio
from contextlib import asynccontextmanager


class CommitOrder:
    def __init__(self):
        self.next_index = 0
        self.condition = asyncio.Condition()

    @asynccontextmanager
    async def slot(self, index):
        async with self.condition:
            await self.condition.wait_for(lambda: self.next_index == index)
            try:
                yield
            finally:
                self.next_index += 1
                self.condition.notify_all()
