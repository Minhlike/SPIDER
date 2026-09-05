from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now
from spider.models.enums import ObservableType
from spider.models.observable import canonicalize_observable

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
    parent_observable_type: Optional[ObservableType] = None
    parent_namespace: str = ""
    seed_id: Optional[str] = None
    configuration_hash: str = Field(default="default", description="Hash of provider execution parameters")
    raw_artifact_sha256: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)

    def model_copy(self, *, update=None, deep=False):
        changes = dict(update or {})
        if ("parent_observable_value" in changes
                and changes["parent_observable_value"] != self.parent_observable_value
                and "parent_observable_type" not in changes):
            # Older adapters replacing a parent string cannot inherit its old type.
            changes.update(parent_observable_type=None, parent_namespace="")
        return super().model_copy(update=changes, deep=deep)

    def with_parent(self, value: str, obs_type: ObservableType, namespace: str = ""):
        return self.model_copy(update={
            "parent_observable_value": canonicalize_observable(obs_type, value),
            "parent_observable_type": obs_type,
            "parent_namespace": namespace.strip().casefold(),
        })
