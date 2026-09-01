from pathlib import Path
from typing import Dict, List, Optional
import yaml
from spider.models.enums import ObservableType
from spider.capability.definitions import CapabilityDefinition

class CapabilityRegistry:
    def __init__(self, config_path: Optional[str] = "config/capabilities.yaml"):
        self.capabilities: Dict[str, CapabilityDefinition] = {}
        if config_path and Path(config_path).exists():
            self.load_from_yaml(config_path)

    def load_from_yaml(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        for name, info in data.get("capabilities", {}).items():
            input_types = [ObservableType(t) for t in info.get("input_types", []) if t in ObservableType.__members__]
            output_types = [ObservableType(t) for t in info.get("output_types", []) if t in ObservableType.__members__]
            self.capabilities[name] = CapabilityDefinition(
                name=name,
                description=info.get("description", ""),
                default_providers=info.get("default_providers", []),
                input_types=input_types,
                output_types=output_types
            )

    def register_capability(self, cap: CapabilityDefinition) -> None:
        self.capabilities[cap.name] = cap

    def get_capabilities_for_input(self, obs_type: ObservableType) -> List[CapabilityDefinition]:
        return [cap for cap in self.capabilities.values() if obs_type in cap.input_types]

    def get_capability(self, name: str) -> Optional[CapabilityDefinition]:
        return self.capabilities.get(name)
