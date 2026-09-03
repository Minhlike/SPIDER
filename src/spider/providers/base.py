import abc
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

class ProviderHealth(BaseModel):
    state: ProviderState
    provider_version: Optional[str] = None
    adapter_version: Optional[str] = "1.0.0"
    runtime_path: Optional[str] = None
    runtime_exists: bool = True
    runtime_version_verified: bool = True
    credential_state: Optional[str] = "OK"
    contract_verified: bool = True
    live_verified: bool = True
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_yield: int = 0
    latency_ms: Optional[float] = None
    message: str = "OK"
    details: Dict[str, Any] = Field(default_factory=dict)

class ProviderExecutionResult(BaseModel):
    raw_content: bytes
    observations: List[Observation]
    exit_code: int = 0
    error_message: Optional[str] = None
    mime_type: str = "application/json"
    duration_ms: float = 0.0
    raw_items_count: int = 0
    accepted_count: int = 0
    dropped_count: int = 0
    outcome: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BaseProviderAdapter(abc.ABC):
    @abc.abstractmethod
    def provider_id(self) -> str:
        pass

    @abc.abstractmethod
    def version(self) -> str:
        pass

    @abc.abstractmethod
    def adapter_version(self) -> str:
        pass

    @abc.abstractmethod
    def capabilities(self) -> List[str]:
        pass

    @abc.abstractmethod
    def network_class(self) -> NetworkClass:
        pass

    @abc.abstractmethod
    def accepts(self) -> List[ObservableType]:
        pass

    @abc.abstractmethod
    def produces(self) -> List[ObservableType]:
        pass

    @abc.abstractmethod
    async def health(self) -> ProviderHealth:
        pass

    @abc.abstractmethod
    def build_command(self, target: NormalizedObservable) -> List[str]:
        pass

    @abc.abstractmethod
    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        pass

    @abc.abstractmethod
    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        pass

    @abc.abstractmethod
    def normalize(self, raw_item: Any) -> NormalizedObservable:
        pass
