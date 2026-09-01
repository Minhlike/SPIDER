from pathlib import Path
from typing import Dict, Optional, Set
import yaml
from spider.models.enums import NetworkClass
from spider.models.policy import NetworkPolicyProfile, PolicyContext

class PolicyEngine:
    def __init__(self, config_path: Optional[str] = "config/policies.yaml"):
        self.profiles: Dict[str, NetworkPolicyProfile] = {}
        self.default_profile_name: str = "passive_standard"
        if config_path and Path(config_path).exists():
            self.load_from_yaml(config_path)

    def load_from_yaml(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.default_profile_name = data.get("default_profile", "passive_standard")
        for name, info in data.get("profiles", {}).items():
            allowed = {NetworkClass(c) for c in info.get("allowed_network_classes", []) if c in NetworkClass.__members__}
            self.profiles[name] = NetworkPolicyProfile(
                name=name,
                description=info.get("description", ""),
                allowed_network_classes=allowed,
                require_authorized_scope=info.get("require_authorized_scope", False)
            )

    def get_context(self, profile_name: Optional[str] = None, is_target_in_scope: bool = False, allow_privileged: bool = False) -> PolicyContext:
        name = profile_name or self.default_profile_name
        profile = self.profiles.get(name)
        if not profile:
            # Fallback default safe profile
            profile = NetworkPolicyProfile(
                name="fallback_passive",
                description="Default fallback passive profile",
                allowed_network_classes={NetworkClass.LOCAL_ONLY, NetworkClass.THIRD_PARTY_ONLY},
                require_authorized_scope=False
            )
        return PolicyContext(
            profile=profile,
            is_target_in_scope=is_target_in_scope,
            allow_privileged=allow_privileged
        )
