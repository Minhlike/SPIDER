import sqlite3
from pathlib import Path
import pytest
from sqlalchemy import select
from spider.storage.database import DatabaseManager
from spider.storage.schema import EntityRecord, ObservationRecord


def legacy_database(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(Path("tests/fixtures/storage/v2_schema.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO cases (id, name) VALUES ('case', 'Synthetic legacy case')")
        conn.execute("INSERT INTO targets (id, case_id, observable_type, raw_input, canonical_value) "
                     "VALUES ('seed', 'case', 'DOMAIN', 'example.test', 'example.test')")
        conn.execute("INSERT INTO entities (id, case_id, observable_type, canonical_name) "
                     "VALUES ('merged', 'case', 'DOMAIN', 'alice.dev')")
        for number, typ in enumerate(("DOMAIN", "USERNAME")):
            conn.execute("INSERT INTO observations (id, case_id, run_id, task_id, observable_type, "
                "observable_value, canonical_value, provider_id, provider_version, adapter_version, "
                "upstream_family, configuration_hash, confidence, created_at) "
                "VALUES (?, 'case', 'run', 'task', ?, 'alice.dev', 'alice.dev', 'fixture', '1', '1', 'FIXTURE', 'default', 1, '2026-01-01 00:00:00')",
                (str(number), typ))


@pytest.mark.asyncio
async def test_legacy_schema_rebuilds_without_merging_and_is_repeatable(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_database(path)
    db = DatabaseManager(str(path))
    try:
        for _ in range(2):
            await db.initialize()
            async with db.session_factory() as session:
                entities = (await session.execute(select(EntityRecord))).scalars().all()
                assert {(e.observable_type, e.namespace, e.canonical_name) for e in entities} == {
                    ("DOMAIN", "", "alice.dev"), ("USERNAME", "", "alice.dev")}
                observations = (await session.execute(select(ObservationRecord))).scalars().all()
                assert len(observations) == 2
                assert {observation.seed_id for observation in observations} == {"seed"}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_failed_migration_rolls_back_schema_and_materialized_graph(tmp_path, monkeypatch):
    from spider.resolution.rebuilder import KnowledgeGraphRebuilder
    path = tmp_path / "rollback.db"
    legacy_database(path)
    async def fail(*args):
        raise RuntimeError("Synthetic rebuild failure")
    monkeypatch.setattr(KnowledgeGraphRebuilder, "rebuild_case", fail)
    db = DatabaseManager(str(path))
    try:
        with pytest.raises(RuntimeError):
            await db.initialize()
    finally:
        await db.close()
    with sqlite3.connect(path) as conn:
        assert "namespace" not in {row[1] for row in conn.execute("PRAGMA table_info(entities)")}
        assert conn.execute("SELECT id FROM entities").fetchall() == [("merged",)]
