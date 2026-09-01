import hashlib
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now
from spider.models.enums import ExecutionStatus

class ExecutionKey(SpiderBaseModel):
    entity_id: str
    capability: str
    provider_id: str
    configuration_hash: str = "default"

    @property
    def key_string(self) -> str:
        raw = f"{self.entity_id}|{self.capability}|{self.provider_id}|{self.configuration_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TaskRun(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    run_id: str
    execution_key_hash: str
    provider_id: str
    capability: str
    target_observable_value: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    observations_count: int = 0
    raw_artifact_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProviderRun(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    tasks_count: int = 0
    observations_count: int = 0
    error_message: Optional[str] = None
