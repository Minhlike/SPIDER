from typing import List, Dict, Set
from pydantic import BaseModel, Field
from spider.models.enums import ObservableType

class CapabilityDefinition(BaseModel):
    name: str
    description: str
    default_providers: List[str] = Field(default_factory=list)
    input_types: List[ObservableType] = Field(default_factory=list)
    output_types: List[ObservableType] = Field(default_factory=list)
