from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now

class SourceLineage(SpiderBaseModel):
    case_id: str
    run_id: str
    task_id: str
    provider_id: str
    provider_version: str
    adapter_version: str = "1.0.0"
    upstream_source: Optional[str] = None
    upstream_family: str = Field(default="UNKNOWN", description="Classification e.g. CERTIFICATE_TRANSPARENCY, WHOIS, DNS, SEARCH_ENGINE")
    parent_observable_value: Optional[str] = None
    configuration_hash: str = Field(default="default", description="Hash of provider execution parameters")
    raw_artifact_sha256: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
