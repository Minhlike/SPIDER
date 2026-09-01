from spider.models.enums import ObservableType

PROVIDER_COSTS = {
    "fake_a": 1.0,
    "fake_b": 1.0,
    "subfinder": 2.0,
    "metabigor": 2.0,
    "uncover": 3.0,
    "spiderfoot": 5.0,
    "maigret": 3.0
}

CAPABILITY_YIELD_ESTIMATES = {
    "SUBDOMAIN_DISCOVERY": 10.0,
    "INFRASTRUCTURE_DISCOVERY": 5.0,
    "USERNAME_DISCOVERY": 8.0,
    "INTERNET_INTELLIGENCE": 6.0,
    "BROAD_OSINT": 15.0
}

def calculate_task_priority(capability: str, provider_id: str, depth: int, is_seed: bool) -> float:
    """
    Deterministic heuristic score:
    Higher score = scheduled first.
    """
    base_yield = CAPABILITY_YIELD_ESTIMATES.get(capability, 5.0)
    cost = PROVIDER_COSTS.get(provider_id, 2.0)
    relevance = 10.0 if is_seed else max(1.0, 10.0 - (depth * 2.5))
    
    # Priority formula
    score = (base_yield * 1.5) + (relevance * 2.0) - (cost * 0.8)
    return round(score, 4)
