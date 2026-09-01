import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now
from spider.models.enums import ObservableType

class Entity(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    type: ObservableType
    canonical_name: str
    first_seen: datetime = Field(default_factory=utc_now)
    last_seen: datetime = Field(default_factory=utc_now)
    observation_count: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)
