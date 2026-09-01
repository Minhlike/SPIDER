from typing import List, Set
from pydantic import Field
from spider.models.base import SpiderBaseModel
from spider.models.enums import NetworkClass

class NetworkPolicyProfile(SpiderBaseModel):
    name: str
    description: str
    allowed_network_classes: Set[NetworkClass] = Field(
        default_factory=lambda: {NetworkClass.LOCAL_ONLY, NetworkClass.THIRD_PARTY_ONLY}
    )
    require_authorized_scope: bool = False

class PolicyContext(SpiderBaseModel):
    profile: NetworkPolicyProfile
    is_target_in_scope: bool = False
    allow_privileged: bool = False

    def is_action_allowed(self, required_class: NetworkClass) -> bool:
        if required_class not in self.profile.allowed_network_classes:
            return False
        if required_class in (NetworkClass.TARGET_DIRECT, NetworkClass.TARGET_ACTIVE) and not self.is_target_in_scope:
            return False
        if required_class == NetworkClass.PRIVILEGED_LOCAL and not self.allow_privileged:
            return False
        return True
