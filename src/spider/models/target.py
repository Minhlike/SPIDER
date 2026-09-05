import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import Field
from spider.models.base import SpiderBaseModel, utc_now
from spider.models.enums import ObservableType
from spider.models.observable import canonicalize_observable

class Target(SpiderBaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    observable_type: ObservableType
    namespace: str = ""
    raw_input: str
    canonical_value: str = ""
    scope_authorized: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self.namespace = self.namespace.strip().casefold()
        if not self.canonical_value:
            self.canonical_value = canonicalize_observable(self.observable_type, self.raw_input)
