import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now

class EvidenceRef(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    observation_id: str
    assertion_id: Optional[str] = None
    provider_id: str
    upstream_family: str
    confidence_weight: float = 0.8
    excerpt: Optional[str] = None
    raw_artifact_sha256: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
