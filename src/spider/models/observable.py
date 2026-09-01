import re
import ipaddress
from typing import Dict, Any, Optional
from pydantic import Field, field_validator
from spider.models.base import SpiderBaseModel
from spider.models.enums import ObservableType

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
DOMAIN_REGEX = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")

def canonicalize_observable(obs_type: ObservableType, value: str) -> str:
    cleaned = value.strip()
    if obs_type in (ObservableType.DOMAIN, ObservableType.HOSTNAME):
        return cleaned.lower().rstrip(".")
    elif obs_type == ObservableType.EMAIL:
        return cleaned.lower()
    elif obs_type == ObservableType.IP_ADDRESS:
        try:
            return str(ipaddress.ip_address(cleaned))
        except ValueError:
            return cleaned.strip()
    elif obs_type == ObservableType.CIDR:
        try:
            return str(ipaddress.ip_network(cleaned, strict=False))
        except ValueError:
            return cleaned.strip()
    elif obs_type == ObservableType.ASN:
        norm = cleaned.upper()
        if not norm.startswith("AS") and norm.isdigit():
            norm = f"AS{norm}"
        return norm
    elif obs_type == ObservableType.USERNAME:
        return cleaned.lower()
    return cleaned

class NormalizedObservable(SpiderBaseModel):
    type: ObservableType
    value: str
    canonical_value: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.canonical_value:
            self.canonical_value = canonicalize_observable(self.type, self.value)
