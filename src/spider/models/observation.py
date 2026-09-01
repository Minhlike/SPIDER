import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

class Observation(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    observable: NormalizedObservable
    lineage: SourceLineage
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    raw_artifact_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
