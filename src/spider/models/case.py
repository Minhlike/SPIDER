import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now

class Case(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: str = "ACTIVE"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
