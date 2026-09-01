import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now
from spider.models.enums import AssertionType
from spider.models.evidence import EvidenceRef

class Assertion(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    source_entity_id: str
    target_entity_id: str
    assertion_type: AssertionType
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    independent_source_count: int = 1
    source_families: List[str] = Field(default_factory=list)
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    resolver_version: str = "1.0.0"
    inference_rule: str = "DIRECT_OBSERVATION"
    first_observed: datetime = Field(default_factory=utc_now)
    last_observed: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
