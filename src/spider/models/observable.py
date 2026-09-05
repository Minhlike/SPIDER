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
    elif obs_type in (ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS):
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
    elif obs_type in (ObservableType.USERNAME, ObservableType.ACCOUNT):
        return cleaned.lower()
    elif obs_type == ObservableType.PHONE:
        from spider.models.phone import phone_metadata
        return phone_metadata(cleaned)["e164"]
    return cleaned

class NormalizedObservable(SpiderBaseModel):
    type: ObservableType
    value: str
    namespace: str = ""
    canonical_value: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self.namespace = self.namespace.strip().casefold()
        if self.type == ObservableType.PHONE:
            from spider.models.phone import canonical_phone
            self.canonical_value = canonical_phone(self.value, self.canonical_value)
        elif not self.canonical_value:
            self.canonical_value = canonicalize_observable(self.type, self.value)

    @property
    def identity(self) -> tuple:
        """Identity within a case; an empty namespace means unscoped, not wildcard."""
        return self.type.value, self.namespace, self.canonical_value
