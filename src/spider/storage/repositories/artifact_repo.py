import hashlib
from pathlib import Path
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.schema import RawArtifactRecord
from spider.models.raw_artifact import RawArtifactRef

class ArtifactRepository:
    def __init__(self, artifacts_dir: str = "data/runs"):
        artifacts_dir = artifacts_dir or "data/runs"
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def store_raw_bytes(self, case_id: str, run_id: str, task_id: str, provider_id: str, content: bytes, mime_type: str = "text/plain") -> RawArtifactRef:
        sha256_hash = hashlib.sha256(content).hexdigest()
        run_dir = self.artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_id = f"{task_id}_{provider_id}_{sha256_hash[:8]}"
        file_path = run_dir / f"{artifact_id}.raw"
        file_path.write_bytes(content)

        return RawArtifactRef(
            id=artifact_id,
            case_id=case_id,
            run_id=run_id,
            task_id=task_id,
            provider_id=provider_id,
            storage_path=str(file_path.as_posix()),
            sha256=sha256_hash,
            byte_size=len(content),
            mime_type=mime_type
        )

    @staticmethod
    async def save_artifact_record(session: AsyncSession, artifact: RawArtifactRef) -> RawArtifactRecord:
        rec = RawArtifactRecord(
            id=artifact.id,
            case_id=artifact.case_id,
            run_id=artifact.run_id,
            task_id=artifact.task_id,
            provider_id=artifact.provider_id,
            storage_path=artifact.storage_path,
            sha256=artifact.sha256,
            byte_size=artifact.byte_size,
            mime_type=artifact.mime_type,
            created_at=artifact.created_at
        )
        session.add(rec)
        return rec

    @staticmethod
    async def get_artifact(session: AsyncSession, artifact_id: str) -> Optional[RawArtifactRecord]:
        result = await session.execute(select(RawArtifactRecord).where(RawArtifactRecord.id == artifact_id))
        return result.scalar_one_or_none()
