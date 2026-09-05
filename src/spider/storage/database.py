import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.engine import Engine
from spider.storage.schema import Base

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

class DatabaseManager:
    def __init__(self, db_path: str = "data/spider.db"):
        db_path = db_path or "data/spider.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Using aiosqlite for async sqlite
        url = f"sqlite+aiosqlite:///{self.db_path.as_posix()}"
        self.engine = create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False}
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def initialize(self) -> None:
        from spider.storage.migrations import migrate_typed_identity
        from spider.resolution.rebuilder import KnowledgeGraphRebuilder
        async with self.engine.begin() as conn:
            # Explicit BEGIN also covers SQLite DDL, including a rollback on rebuild failure.
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            legacy_cases = await conn.run_sync(migrate_typed_identity)
            await conn.run_sync(Base.metadata.create_all)
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                for case_id in legacy_cases:
                    await KnowledgeGraphRebuilder().rebuild_case(session, case_id)
                await session.flush()

    async def get_session(self) -> AsyncSession:
        return self.session_factory()

    async def close(self) -> None:
        await self.engine.dispose()
