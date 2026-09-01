from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now

class RawArtifactRef(SpiderBaseModel):
    id: str
    case_id: str
    run_id: str
    task_id: str
    provider_id: str
    storage_path: str
    sha256: str
    byte_size: int
    mime_type: str = "text/plain"
    created_at: datetime = Field(default_factory=utc_now)
