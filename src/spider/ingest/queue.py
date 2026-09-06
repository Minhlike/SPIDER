import asyncio
from typing import List, Tuple
from spider.models.observation import Observation
from spider.models.raw_artifact import RawArtifactRef
from spider.storage.writer import SingleDBWriter
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.repositories.artifact_repo import ArtifactRepository

class IngestQueue:
    def __init__(self, db_writer: SingleDBWriter):
        self.db_writer = db_writer

    async def ingest_batch(self, observations: List[Observation], raw_artifact: RawArtifactRef, *, resolve_batch=None) -> None:
        async def _write_txn(session):
            await ArtifactRepository.save_artifact_record(session, raw_artifact)
            await session.flush()
            if observations:
                await ObservationRepository.append_observations_batch(session, observations)
                if resolve_batch is not None:
                    await session.flush()
                    await resolve_batch(session, observations)
        
        await self.db_writer.submit(_write_txn)
