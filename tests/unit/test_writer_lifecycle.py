import asyncio
import pytest
from sqlalchemy import select
from spider.storage.database import DatabaseManager
from spider.storage.writer import SingleDBWriter
from spider.storage.schema import CaseRecord


@pytest.mark.asyncio
async def test_stop_drains_accepted_transactions_under_backpressure(tmp_path):
    db = DatabaseManager(str(tmp_path / "writer.db"))
    await db.initialize()
    writer = SingleDBWriter(db)
    writer.queue = asyncio.Queue(maxsize=1)
    await writer.start()
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(session):
        started.set()
        await release.wait()
        session.add(CaseRecord(id="one", name="one"))

    async def fast(session):
        session.add(CaseRecord(id="two", name="two"))

    first = asyncio.create_task(writer.submit(slow))
    await started.wait()
    second = asyncio.create_task(writer.submit(fast))
    await asyncio.sleep(0)
    stopped = asyncio.create_task(writer.stop())
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError):
        await writer.submit(fast)
    assert not stopped.done()
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second, stopped), timeout=5)
    async with db.session_factory() as session:
        assert set((await session.scalars(select(CaseRecord.id))).all()) == {"one", "two"}
    assert writer.metrics["completed"] == 2 and writer.metrics["failed"] == 0
    assert writer.metrics["peak_queue"] <= 1
    await db.close()
