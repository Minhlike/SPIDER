from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class SpiderBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True
    )
    schema_version: str = Field(default="1.0", description="Schema version of the data model")
