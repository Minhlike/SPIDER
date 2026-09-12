"""Role-scoped infrastructure claims from evidence already stored by providers."""

AUDITED_FACILITY_PROVIDERS = frozenset()


def _timestamp(observation):
    value = getattr(observation, "created_at", None)
    return value.isoformat() if value is not None else None


def _scalar_fields(raw, names):
    return {name: raw[name] for name in names
            if isinstance(raw.get(name), (str, int, float, bool))
            and raw.get(name) not in ("", None)}


def infrastructure_claims(observations, resolved_ips=()):
    """Separate registry, routing, location and physical-facility semantics.

    A network registration country, IP geolocation or datacenter classification
    never becomes a physical server/facility claim. Every returned row points to
    the source observation that supports it.
    """
    roles, locations, facilities = [], [], []
    for observation in observations:
        raw = getattr(observation, "raw_data_json", None) or {}
        if not isinstance(raw, dict):
            continue
        kind = raw.get("record_kind")
        provider = str(getattr(observation, "provider_id", "") or "")[:128]
        observation_id = str(getattr(observation, "id", "") or "")[:128]
        observed_at = _timestamp(observation)
        resource = raw.get("ip") or getattr(observation, "parent_observable_value", None)
        common = {"provider_id": provider, "observation_id": observation_id,
                  "observed_at": observed_at,
                  "resource": str(resource)[:128] if isinstance(resource, str) else None,
                  "physical_facility_verified": False}
        if kind == "rdap_network":
            claim = _scalar_fields(raw, (
                "network_name", "rir", "country", "start_address", "end_address"))
            cidrs = [str(value)[:128] for value in raw.get("cidrs", [])[:20]
                     if isinstance(value, str)] if isinstance(raw.get("cidrs"), list) else []
            organizations = [str(value)[:256] for value in raw.get("organizations", [])[:20]
                             if isinstance(value, str)] if isinstance(raw.get("organizations"), list) else []
            if claim or cidrs or organizations:
                roles.append({**common, "role": "NETWORK_REGISTRANT",
                              "claim": {**claim, "cidrs": cidrs,
                                        "organizations": organizations}})
        elif kind == "bgp_prefix":
            claim = _scalar_fields(raw, ("asn", "prefix", "organization", "country"))
            if claim:
                roles.append({**common, "role": "ROUTING_ORIGIN", "claim": claim})
        elif kind == "whatismyip_ip_intelligence":
            claim = _scalar_fields(raw, (
                "asn", "isp", "is_proxy", "is_vpn", "is_datacenter",
                "is_residential", "proxy_type", "proxy_provider"))
            if claim:
                roles.append({**common, "role": "IP_INTELLIGENCE_ESTIMATE", "claim": claim})
            location = _scalar_fields(raw, (
                "country", "region", "city", "postal_code", "latitude",
                "longitude", "time_zone"))
            if location:
                locations.append({**common, "claim_type": "IP_GEOLOCATION_ESTIMATE",
                                  "claim": location})
        elif kind == "sourced_physical_facility" and provider in AUDITED_FACILITY_PROVIDERS:
            # No bundled provider emits this contract today. This branch is a
            # fail-closed extension point for a future audited source.
            claim = _scalar_fields(raw, ("facility_name", "facility_region", "facility_country"))
            if claim and raw.get("facility_scope") == "PHYSICAL_FACILITY":
                facilities.append({**common, "claim_type": "SOURCED_FACILITY_CLAIM",
                                   "claim": claim, "physical_facility_verified": True})

    if facilities:
        status = "SOURCED_FACILITY_CLAIM"
    elif any(row["claim"].get("is_datacenter") is True for row in roles
             if row["role"] == "IP_INTELLIGENCE_ESTIMATE"):
        status = "DATACENTER_NETWORK_CLASSIFICATION_ONLY"
    elif roles or locations:
        status = "NETWORK_OPERATOR_OR_EDGE_ONLY"
    else:
        status = "UNKNOWN"
    evidence_ids = sorted({row["observation_id"] for row in roles + locations + facilities
                           if row["observation_id"]})
    return {"network_roles": roles, "location_claims": locations,
            "facility_claims": facilities,
            "hosting_assessment": {
                "status": status,
                "resolved_ips": sorted({str(value) for value in resolved_ips if value}),
                "physical_data_center": facilities[0]["claim"] if len(facilities) == 1 else None,
                "origin_server_verified": False,
                "evidence_observation_ids": evidence_ids,
            }}
