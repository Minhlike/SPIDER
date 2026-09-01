import abc
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

class ProviderHealth(BaseModel):
    state: ProviderState = ProviderState.READY
    message: str = "OK"
    details: Dict[str, Any] = Field(default_factory=dict)

class ProviderExecutionResult(BaseModel):
    raw_content: bytes
    observations: List[Observation] = Field(default_factory=list)
    exit_code: int = 0
    error_message: Optional[str] = None
    mime_type: str = "text/plain"

class BaseProviderAdapter(abc.ABC):
    @abc.abstractmethod
    def provider_id(self) -> str:
        pass

    @abc.abstractmethod
    def version(self) -> str:
        pass

    @abc.abstractmethod
    def adapter_version(self) -> str:
        return "1.0.0"

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
