import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from spider.storage.schema import TargetRecord, EntityRecord, AssertionRecord, ObservationRecord, TaskRunRecord, ProviderRunRecord
from spider.models.enums import ObservableType
from spider.service.projection import project
from spider.service.coverage import coverage_report
from spider.service.evidence_analysis import analyze, public_url
from spider.service.phone_candidates import public_phone_candidates
from spider.service.review import hypotheses

logger = logging.getLogger(__name__)

COUNTRY_CODES = {
    "+84": "Việt Nam (VN)",
    "+1": "Hoa Kỳ / Canada (US/CA)",
    "+44": "Vương quốc Anh (UK)",
    "+33": "Pháp (FR)",
    "+49": "Đức (DE)",
    "+81": "Nhật Bản (JP)",
    "+82": "Hàn Quốc (KR)",
    "+65": "Singapore (SG)",
    "+86": "Trung Quốc (CN)",
    "+61": "Úc (AU)",
    "+7": "Nga (RU)",
    "+91": "Ấn Độ (IN)"
}

def infer_phone_country(phone: str) -> str:
    cleaned = phone.strip()
    for prefix, name in COUNTRY_CODES.items():
        if cleaned.startswith(prefix):
            return name
    return "Quốc tế / Chưa xác định"


def _append_unique(values: list, value) -> None:
    if value not in values:
        values.append(value)


def domain_evidence_profile(observations) -> Dict[str, Any]:
    """Summarize observed domain facts without turning scanner hints into claims."""
    profile = {
        "dns_records": {kind: [] for kind in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA")},
        "dns_security": {"spf": [], "dmarc": [], "caa": []},
        "certificates": [],
        "public_services": [],
        "technology_signals": [],
        "web_metadata": [],
        "network_profiles": [],
    }
    for observation in observations:
        raw = getattr(observation, "raw_data_json", None) or {}
        if not isinstance(raw, dict):
            continue
        provider_id = getattr(observation, "provider_id", "")
        if provider_id == "native_dns":
            record_type, value = raw.get("type"), raw.get("value")
            if not isinstance(value, str):
                continue
            if record_type in profile["dns_records"]:
                _append_unique(profile["dns_records"][record_type], value)
            lowered = value.lower()
            if record_type == "TXT" and "v=spf1" in lowered:
                _append_unique(profile["dns_security"]["spf"], value)
            if record_type == "DMARC" or "v=dmarc1" in lowered:
                _append_unique(profile["dns_security"]["dmarc"], value)
            if record_type == "CAA":
                _append_unique(profile["dns_security"]["caa"], value)
        elif provider_id == "native_ct":
            certificate = {key: raw.get(key) for key in (
                "issuer_name", "not_before", "not_after", "serial_number", "id")
                if isinstance(raw.get(key), (str, int, float))}
            if certificate:
                _append_unique(profile["certificates"], certificate)
        elif provider_id == "uncover":
            service = {key: raw.get(key) for key in ("engine", "ip", "host", "url", "port", "protocol")
                       if isinstance(raw.get(key), (str, int, float))}
            if service:
                _append_unique(profile["public_services"], service)
            for key in ("technology", "product", "server", "software"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    _append_unique(profile["technology_signals"], value.strip())
            technologies = raw.get("technologies")
            if isinstance(technologies, list):
                for value in technologies:
                    if isinstance(value, str) and value.strip():
                        _append_unique(profile["technology_signals"], value.strip())
        elif provider_id == "native_web" and raw.get("record_kind") == "authorized_web_metadata":
            metadata = {key: raw.get(key) for key in (
                "url", "http_status", "redirect_location", "title", "content_type", "has_hsts", "has_csp")
                if isinstance(raw.get(key), (str, int, bool))}
            if metadata:
                _append_unique(profile["web_metadata"], metadata)
            for key in ("server", "x_powered_by", "generator"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    _append_unique(profile["technology_signals"], value.strip())
        elif raw.get("record_kind") in {"rdap_network", "bgp_prefix", "whatismyip_ip_intelligence"}:
            network = {key: raw.get(key) for key in (
                "asn", "cidr", "prefix", "organization", "isp", "network_name", "rir",
                "country", "region", "city", "start_address", "end_address")
                if isinstance(raw.get(key), (str, int, float)) and raw.get(key) not in ("", None)}
            observed_ip = getattr(observation, "parent_observable_value", None)
            if isinstance(observed_ip, str) and observed_ip:
                network["ip"] = observed_ip
            if network:
                _append_unique(profile["network_profiles"], network)
    return profile

class CaseInsightsBuilder:
    @staticmethod
    async def build_insights(session, case_id: str, case_rec, target_id=None, question="all") -> Dict[str, Any]:
        # 1. Fetch Targets
        t_stmt = select(TargetRecord).where(TargetRecord.case_id == case_id)
        targets = (await session.execute(t_stmt)).scalars().all()
        projection = await project(session, case_id, target_id, question)
        seed_target = projection.seed
        target_val = seed_target.canonical_value if seed_target else ""
        target_type = seed_target.observable_type if seed_target else "UNKNOWN"

        # 2. Fetch Entities
        e_stmt = select(EntityRecord).where(EntityRecord.case_id == case_id)
        entities = projection.finding_entities
        entity_map = {e.id: e for e in entities}
        entity_type_counts: Dict[str, int] = {}
        for e in entities:
            entity_type_counts[e.observable_type] = entity_type_counts.get(e.observable_type, 0) + 1

        # 3. Fetch Assertions
        a_stmt = select(AssertionRecord).where(AssertionRecord.case_id == case_id)
        assertions = projection.assertions

        # Counts and profile evidence must include the whole case, not the first 300 rows.
        o_stmt = select(ObservationRecord).where(ObservationRecord.case_id == case_id).order_by(ObservationRecord.created_at.asc())
        observations = projection.evidence_observations

        # 5. Fetch Task Runs
        tr_stmt = select(TaskRunRecord).where(TaskRunRecord.case_id == case_id)
        task_runs = (await session.execute(tr_stmt)).scalars().all()

        # 6. Fetch Provider Runs
        pr_stmt = select(ProviderRunRecord).where(ProviderRunRecord.case_id == case_id).order_by(ProviderRunRecord.started_at.desc())
        provider_runs = (await session.execute(pr_stmt)).scalars().all()
        # A later run for a different seed must not become this target's report.
        scoped_run_ids = {t.run_id for t in task_runs if seed_target and
                          (t.metadata_json or {}).get("seed_id") == seed_target.id}
        scoped_run_ids.update(o.run_id for o in observations)
        provider_runs = [r for r in provider_runs if seed_target and
            (r.id in scoped_run_ids or seed_target.id in (r.metadata_json or {}).get("target_ids", []) or seed_target.id in
             (r.metadata_json or {}).get("expected_sources", {}))]
        latest_run = provider_runs[0] if provider_runs else None
        if latest_run:
            task_runs = [task for task in task_runs if task.run_id == latest_run.id]
        task_runs = [task for task in task_runs if seed_target and (task.metadata_json or {}).get("seed_id") == seed_target.id]
        run_metadata = (latest_run.metadata_json or {}) if latest_run else {}
        expected_sources = set(run_metadata.get("expected_sources", {}).get(seed_target.id, [])) if seed_target else set()

        profiles = {}
        for observation in observations:
            raw = observation.raw_data_json or {}
            if observation.observable_type not in ("ACCOUNT", "URL") or not isinstance(raw, dict):
                continue
            if raw.get("match_basis") not in ("exact_public_email", "email_hash_public_profile",
                                               "verified_account_from_email_profile", "username_only",
                                               "signed_in_browser_candidate", "coccoc_search_candidate"):
                continue
            url = raw.get("profile_url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                continue
            existing = profiles.get(url)
            if existing and existing["match_basis"] == "exact_public_email":
                continue
            explicit_links = []
            for link in (raw.get("explicit_links") if isinstance(raw.get("explicit_links"), list) else [])[:50]:
                safe = public_url(link.get("url")) if isinstance(link, dict) else None
                if safe and safe != url and link.get("basis") in ("rel_me", "jsonld_sameAs"):
                    explicit_links.append({"url": safe, "basis": link["basis"]})
            profiles[url] = {"profile_url": url, "platform": raw.get("platform", "Web"),
                "display_name": raw.get("display_name", ""), "bio": raw.get("bio", ""),
                "website": raw.get("website", ""), "location": raw.get("location", ""),
                "job_title": raw.get("job_title", ""), "company": raw.get("company", ""),
                "match_basis": raw["match_basis"],
                "verification_state": raw.get("verification_state", "PUBLIC_SELF_PUBLISHED"),
                "explicit_links": explicit_links,
                "provider_id": observation.provider_id, "observation_id": observation.id,
                "observed_at": observation.created_at.isoformat(), "identity_verified": False}
        public_profiles = list(profiles.values())

        # --- A. Build Type-Specific Insights ---
        # Email Insights
        email_insights = {
            "email": target_val if target_type == "EMAIL" else None,
            "extracted_domain": None,
            "mail_servers": [],
            "spf_record": None,
            "dmarc_record": None,
            "nameservers": [],
            "ip_addresses": [],
            "accounts": []
        }

        # Domain Insights
        domain_insights = {
            "domain": target_val if target_type in ("DOMAIN", "HOSTNAME") else (target_val.split("@")[1] if "@" in target_val else None),
            "subdomains": [],
            "ip_addresses": [],
            "nameservers": [],
            "mail_servers": [],
            "certificates": [],
            "emails": [],
            "dns_records": {},
            "dns_security": {},
            "public_services": [],
            "technology_signals": [],
            "web_metadata": [],
            "network_profiles": [],
        }

        # IP Insights
        ip_insights = {
            "ip": target_val if target_type in ("IP_ADDRESS", "IPV6_ADDRESS") else None,
            "reverse_dns": [],
            "asn": None,
            "cidr": None,
            "organization": None,
            "associated_hostnames": [],
            "country": None,
            "region": None,
            "city": None,
            "postal_code": None,
            "latitude": None,
            "longitude": None,
            "time_zone": None,
            "isp": None,
            "rir": None,
            "network_name": None,
            "start_address": None,
            "end_address": None,
            "registry_status": [],
            "registry_events": [],
            "contacts": [],
            "is_proxy": None,
            "is_vpn": None,
            "is_datacenter": None,
            "is_residential": None,
            "proxy_type": None,
            "proxy_type_description": None,
            "proxy_level": None,
            "proxy_range": None,
            "proxy_provider": None,
            "source_observations": []
        }

        # Username Insights
        username_insights = {
            "username": target_val if target_type == "USERNAME" else None,
            "accounts": [],
            "profile_urls": []
        }

        # Phone Insights
        phone_insights = {
            "phone": target_val if target_type == "PHONE" else None,
            "country": infer_phone_country(target_val) if target_type == "PHONE" else None,
            "carrier": None,
            "public_candidate_digest": public_phone_candidates(observations, target_val) if target_type == "PHONE" else None,
        }

        # Extract info from entities & assertions
        for e in entities:
            val = e.canonical_name
            etype = e.observable_type
            if etype == "HOSTNAME":
                if "ns." in val or "ns1" in val or "ns2" in val or "ns3" in val:
                    if val not in domain_insights["nameservers"]:
                        domain_insights["nameservers"].append(val)
                elif "mail" in val or "mx" in val or "smtp" in val:
                    if val not in domain_insights["mail_servers"]:
                        domain_insights["mail_servers"].append(val)
                    if val not in email_insights["mail_servers"]:
                        email_insights["mail_servers"].append(val)
                else:
                    if val not in domain_insights["subdomains"]:
                        domain_insights["subdomains"].append(val)
            elif etype in ("IP_ADDRESS", "IPV6_ADDRESS"):
                if val not in domain_insights["ip_addresses"]:
                    domain_insights["ip_addresses"].append(val)
                if val not in email_insights["ip_addresses"]:
                    email_insights["ip_addresses"].append(val)
            elif etype == "EMAIL":
                if val not in domain_insights["emails"]:
                    domain_insights["emails"].append(val)
            elif etype == "ASN":
                ip_insights["asn"] = val
            elif etype == "CIDR":
                ip_insights["cidr"] = val
            elif etype == "ORGANIZATION":
                ip_insights["organization"] = val
            elif etype == "ACCOUNT":
                acc_entry = {"account": val, "platform": val.split("@")[1] if "@" in val else "Web"}
                username_insights["accounts"].append(acc_entry)
                email_insights["accounts"].append(acc_entry)
            elif etype == "URL":
                username_insights["profile_urls"].append(val)

        # Extract TXT / SPF / DMARC from Observations
        for o in observations:
            raw = o.raw_data_json or {}
            if isinstance(raw, dict):
                rtype = raw.get("type", "")
                rval = str(raw.get("value", ""))
                if "v=spf1" in rval:
                    email_insights["spf_record"] = rval
                elif "v=DMARC1" in rval:
                    email_insights["dmarc_record"] = rval
                record_kind = raw.get("record_kind")
                if target_type in ("IP_ADDRESS", "IPV6_ADDRESS") and record_kind in {
                    "whatismyip_ip_intelligence", "rdap_network", "bgp_prefix"
                }:
                    ip_insights["source_observations"].append({
                        "provider_id": o.provider_id,
                        "upstream_source": o.upstream_source,
                        "observed_at": o.created_at.isoformat() if o.created_at else None,
                        "confidence": o.confidence,
                        "record_kind": record_kind,
                    })
                if record_kind == "whatismyip_ip_intelligence":
                    for field in ("country", "region", "city", "postal_code", "latitude",
                                  "longitude", "time_zone", "isp", "is_proxy", "is_vpn",
                                  "is_datacenter", "is_residential", "proxy_type",
                                  "proxy_type_description", "proxy_level", "proxy_range",
                                  "proxy_provider"):
                        if raw.get(field) is not None:
                            ip_insights[field] = raw[field]
                    if raw.get("asn"):
                        ip_insights["asn"] = raw["asn"]
                    if raw.get("isp"):
                        ip_insights["organization"] = raw["isp"]
                elif record_kind == "rdap_network":
                    for field in ("rir", "network_name", "start_address", "end_address"):
                        if raw.get(field) is not None:
                            ip_insights[field] = raw[field]
                    ip_insights["registry_status"] = raw.get("status", [])
                    ip_insights["registry_events"] = raw.get("events", [])
                    ip_insights["contacts"] = raw.get("contacts", [])
                    if raw.get("cidrs"):
                        ip_insights["cidr"] = raw["cidrs"][0]
                elif record_kind == "bgp_prefix":
                    if raw.get("asn"):
                        ip_insights["asn"] = raw["asn"]
                    if raw.get("prefix"):
                        ip_insights["cidr"] = raw["prefix"]
                    if raw.get("organization"):
                        ip_insights["organization"] = raw["organization"]
                if (target_type in ("IP_ADDRESS", "IPV6_ADDRESS")
                        and o.observable_type == "HOSTNAME"
                        and o.canonical_value not in ip_insights["reverse_dns"]):
                    ip_insights["reverse_dns"].append(o.canonical_value)
                    ip_insights["associated_hostnames"].append(o.canonical_value)

        if target_type == "EMAIL" and "@" in target_val:
            email_insights["extracted_domain"] = target_val.split("@")[1]

        domain_profile = domain_evidence_profile(observations)
        domain_insights.update(domain_profile)
        domain_insights["certificates"] = domain_profile["certificates"]

        unique_ip_sources = {}
        for source in ip_insights["source_observations"]:
            key = (source["provider_id"], source["upstream_source"], source["record_kind"])
            unique_ip_sources[key] = source
        ip_insights["source_observations"] = list(unique_ip_sources.values())

        # --- B. Provider Contributions ---
        provider_stats: Dict[str, Dict[str, Any]] = {}
        for tr in task_runs:
            pid = tr.provider_id
            if pid not in provider_stats:
                provider_stats[pid] = {
                    "provider_id": pid,
                    "tasks_count": 0,
                    "status": "SUCCESS",
                    "duration_ms": 0.0,
                    "error_message": None,
                    "coverage": None,
                    "budget_reason": None,
                    "engine_states": None,
                    "request_count": 0,
                    "collection_reason": None,
                    "scope": None,
                }
            provider_stats[pid]["tasks_count"] += 1
            metadata = tr.metadata_json or {}
            provider_stats[pid]["duration_ms"] += metadata.get("duration_ms", 0)
            provider_stats[pid]["request_count"] += metadata.get("request_count", 0)
            if metadata.get("collection_reason"):
                provider_stats[pid]["collection_reason"] = metadata["collection_reason"]
            if metadata.get("scope"):
                provider_stats[pid]["scope"] = metadata["scope"]
            if metadata.get("coverage"):
                previous = provider_stats[pid]["coverage"] or {}
                current = metadata["coverage"]
                combined = {key: previous.get(key, 0) + current.get(key, 0)
                    for key in ("selected", "checked", "found", "not_found", "unknown", "invalid", "unprocessed", "non_unique_detections", "controls_pending", "controls_unknown")}
                combined["priority_sites"] = {
                    **previous.get("priority_sites", {}),
                    **current.get("priority_sites", {}),
                }
                if current.get("source_scope"):
                    combined["source_scope"] = current["source_scope"]
                provider_stats[pid]["coverage"] = combined
            if metadata.get("budget_reason"):
                provider_stats[pid]["budget_reason"] = metadata["budget_reason"]
            if metadata.get("engines"):
                provider_stats[pid]["engine_states"] = {
                    name: value.get("state", "UNKNOWN") for name, value in metadata["engines"].items()
                    if isinstance(value, dict)
                }
            priority = {"RUNNING": 6, "PARTIAL": 5, "FAILED": 4, "CANCELLED": 3, "COMPLETED": 1, "SUCCESS": 0}
            if priority.get(tr.status, 2) > priority.get(provider_stats[pid]["status"], 0):
                provider_stats[pid]["status"] = tr.status
                if tr.error_message:
                    provider_stats[pid]["error_message"] = tr.error_message

        # Count observations per provider
        provider_obs_count: Dict[str, int] = {}
        for o in observations:
            pid = o.provider_id or "unknown"
            provider_obs_count[pid] = provider_obs_count.get(pid, 0) + 1

        all_known_providers = ["native_dns", "native_rdap", "native_ct", "native_web", "subfinder", "metabigor", "spiderfoot", "maigret", "github_public", "gravatar_public", "uncover", "coccoc_browser"]
        provider_ids = list(dict.fromkeys(all_known_providers + sorted(
            expected_sources | set(provider_stats) | set(provider_obs_count))))
        contributions = []
        for pid in provider_ids:
            st = provider_stats.get(pid)
            obs_cnt = provider_obs_count.get(pid, 0)
            applicable = pid in expected_sources
            request_count = st.get("request_count", 0) if st else 0
            if st:
                status_str = "SUCCESS" if obs_cnt > 0 else "NO_FINDINGS"
                if st.get("budget_reason") == "UNMETERED_PROVIDER":
                    status_str = "BLOCKED"
                elif st["status"] in ("FAILED", "ERROR"):
                    status_str = "ERROR"
                elif st["status"] in ("PARTIAL", "RUNNING", "CANCELLED"):
                    status_str = st["status"]
                execution_state = ("BLOCKED_UNMETERED" if st.get("budget_reason") == "UNMETERED_PROVIDER"
                    else "CALLED" if request_count
                    else "RUNNING" if st["status"] in ("RUNNING", "PENDING")
                    else "EXECUTED_NO_NETWORK")
                credential_state = "NOT_REQUIRED"
                if pid == "uncover":
                    states = set((st.get("engine_states") or {}).values())
                    credential_state = ("MISSING_CREDENTIAL" if states == {"MISSING_CREDENTIAL"}
                        else "CONFIGURED" if states
                        else "NOT_CHECKED")
                contributions.append({
                    "provider_id": pid,
                    "applicability": "APPLICABLE" if applicable else "NOT_APPLICABLE",
                    "execution_state": execution_state,
                    "request_count": request_count,
                    "contributed": obs_cnt > 0,
                    "status": status_str,
                    "observations_count": obs_cnt,
                    "tasks_count": st["tasks_count"],
                    "duration_ms": round(st.get("duration_ms", 0), 1),
                    "error_message": st.get("error_message"),
                    "coverage": st.get("coverage"),
                    "credential_state": credential_state,
                    "engine_states": st.get("engine_states"),
                    "collection_reason": st.get("collection_reason"),
                    "scope": st.get("scope"),
                })
            else:
                execution_state = "NOT_SCHEDULED" if applicable else "NOT_APPLICABLE"
                contributions.append({
                    "provider_id": pid,
                    "applicability": "APPLICABLE" if applicable else "NOT_APPLICABLE",
                    "execution_state": execution_state,
                    "request_count": request_count,
                    "contributed": False,
                    "status": "SKIPPED",
                    "observations_count": 0,
                    "tasks_count": 0,
                    "duration_ms": 0.0,
                    "error_message": "Chưa được lập lịch" if applicable else "Không áp dụng cho loại đối tượng này",
                    "credential_state": "NOT_CHECKED" if pid == "uncover" and applicable else "NOT_APPLICABLE" if pid == "uncover" else "NOT_REQUIRED",
                    "engine_states": None,
                    "collection_reason": None,
                    "scope": None,
                })

        # --- C. Empty Result Explanation ---
        # A seed is retained as evidence for reproducibility, but it is not a
        # discovery.  Empty-result guidance must therefore consider only
        # entities beyond the selected input(s).
        seed_identities = {(str(target.observable_type), target.namespace, target.canonical_value)
                           for target in targets}
        total_enrichments = sum(
            (str(entity.observable_type), entity.namespace, entity.canonical_name) not in seed_identities
            for entity in entities)
        is_empty = (total_enrichments == 0 and len(assertions) == 0)

        checked_count = sum(1 for c in contributions if c["tasks_count"] > 0)
        no_findings_count = sum(1 for c in contributions if c["status"] == "NO_FINDINGS")
        error_count = sum(1 for c in contributions if c["status"] == "ERROR")
        missing_cred_count = sum(1 for c in contributions if c["credential_state"] == "MISSING_CREDENTIAL")

        empty_reason = {
            "is_empty": is_empty,
            "message_vi": "Không tìm thấy dữ liệu bổ sung từ các nguồn OSINT mở." if is_empty else "Đã phát hiện thông tin tình báo.",
            "message_en": "No additional intelligence found from public OSINT sources." if is_empty else "Intelligence findings discovered.",
            "breakdown": {
                "checked_sources": checked_count,
                "no_findings_sources": no_findings_count,
                "missing_credentials": missing_cred_count,
                "error_sources": error_count
            }
        }

        result = {
            "case_id": case_id,
            "evidence_analysis": {**analyze(observations), "hypotheses": await hypotheses(session, case_id, projection)},
            "scope": {"target_id": seed_target.id if seed_target else None, "question": question,
                "selection_required": len(targets) > 1 and seed_target is None,
                "unscoped_observations_excluded": projection.excluded_unscoped,
                "evidence_ids": [o.id for o in observations],
                "targets": [{"id": t.id, "value": t.canonical_value, "type": t.observable_type, "namespace": t.namespace} for t in targets]},
            "target": target_val,
            "coverage_report": coverage_report(task_runs, observations,
                sorted(expected_sources)),
            "target_type": target_type,
            "status": latest_run.status if latest_run else "NOT_STARTED",
            "run_id": latest_run.id if latest_run else None,
            "investigation_mode": (latest_run.metadata_json or {}).get("investigation_mode") if latest_run else None,
            "browser_assisted": bool((latest_run.metadata_json or {}).get("browser_assisted")) if latest_run else False,
            "budget_ledger": (latest_run.metadata_json or {}).get("budget_ledger") if latest_run else None,
            "entities_count": len(entities),
            "assertions_count": len(assertions),
            "observations_count": len(observations),
            "entity_type_counts": entity_type_counts,
            "email_insights": email_insights,
            "domain_insights": domain_insights,
            "ip_insights": ip_insights,
            "username_insights": username_insights,
            "public_profiles": public_profiles,
            "profile_evidence": {"profiles_count": len(public_profiles),
                "checked_sources": sorted({t.provider_id for t in task_runs if t.provider_id in ("maigret", "github_public", "gravatar_public", "coccoc_browser")}),
                "exact_email_matches": sum(p["match_basis"] in ("exact_public_email", "email_hash_public_profile") for p in public_profiles),
                "identity_verified": False,
                "message_vi": ("Chưa có hồ sơ công khai được đối chiếu với mục tiêu. Dữ liệu máy chủ thư không xác định chủ email."
                    if not public_profiles else "Hồ sơ công khai và căn cứ liên hệ; chưa xác minh danh tính người sở hữu."),
                "message_en": ("No public profile linked to this target yet. Mail infrastructure does not identify the email owner."
                    if not public_profiles else "Public profiles and linkage evidence; owner identity has not been verified.")},
            "phone_insights": phone_insights,
            "provider_contributions": contributions,
            "empty_reason": empty_reason
        }

        from spider.service.reporting import reader_report
        result["reader_findings"] = [{"id": entity.id, "type": entity.observable_type,
            "value": entity.canonical_name, "evidence_ids": [o.id for o in observations
                if (o.observable_type, o.namespace, o.canonical_value) ==
                   (entity.observable_type, entity.namespace, entity.canonical_name)][:5]}
            for entity in entities[:50]]
        result["reader_findings_truncated"] = len(entities) > 50
        result["reader_report"] = {language: reader_report(result, language) for language in ("vi", "en")}
        result["empty_reason"].update(message_vi=result["reader_report"]["vi"]["conclusion"],
                                      message_en=result["reader_report"]["en"]["conclusion"])
        return result
