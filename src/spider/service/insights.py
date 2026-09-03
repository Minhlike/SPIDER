import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from spider.storage.schema import TargetRecord, EntityRecord, AssertionRecord, ObservationRecord, TaskRunRecord, ProviderRunRecord
from spider.models.enums import ObservableType

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

class CaseInsightsBuilder:
    @staticmethod
    async def build_insights(session, case_id: str, case_rec) -> Dict[str, Any]:
        # 1. Fetch Targets
        t_stmt = select(TargetRecord).where(TargetRecord.case_id == case_id)
        targets = (await session.execute(t_stmt)).scalars().all()
        seed_target = targets[0] if targets else None
        target_val = seed_target.canonical_value if seed_target else ""
        target_type = seed_target.observable_type if seed_target else "UNKNOWN"

        # 2. Fetch Entities
        e_stmt = select(EntityRecord).where(EntityRecord.case_id == case_id)
        entities = (await session.execute(e_stmt)).scalars().all()
        entity_map = {e.id: e for e in entities}
        entity_type_counts: Dict[str, int] = {}
        for e in entities:
            entity_type_counts[e.observable_type] = entity_type_counts.get(e.observable_type, 0) + 1

        # 3. Fetch Assertions
        a_stmt = select(AssertionRecord).where(AssertionRecord.case_id == case_id)
        assertions = (await session.execute(a_stmt)).scalars().all()

        # 4. Fetch Observations (limit to last 200)
        o_stmt = select(ObservationRecord).where(ObservationRecord.case_id == case_id).order_by(ObservationRecord.created_at.asc()).limit(300)
        observations = (await session.execute(o_stmt)).scalars().all()

        # 5. Fetch Task Runs
        tr_stmt = select(TaskRunRecord).where(TaskRunRecord.case_id == case_id)
        task_runs = (await session.execute(tr_stmt)).scalars().all()

        # 6. Fetch Provider Runs
        pr_stmt = select(ProviderRunRecord).where(ProviderRunRecord.case_id == case_id).order_by(ProviderRunRecord.started_at.desc())
        provider_runs = (await session.execute(pr_stmt)).scalars().all()
        latest_run = provider_runs[0] if provider_runs else None

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
            "emails": []
        }

        # IP Insights
        ip_insights = {
            "ip": target_val if target_type in ("IP_ADDRESS", "IPV6_ADDRESS") else None,
            "reverse_dns": [],
            "asn": None,
            "cidr": None,
            "organization": None,
            "associated_hostnames": []
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
            "carrier": None
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

        if target_type == "EMAIL" and "@" in target_val:
            email_insights["extracted_domain"] = target_val.split("@")[1]

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
                    "error_message": None
                }
            provider_stats[pid]["tasks_count"] += 1
            if tr.status != "SUCCESS":
                provider_stats[pid]["status"] = tr.status
                if tr.error_message:
                    provider_stats[pid]["error_message"] = tr.error_message

        # Count observations per provider
        provider_obs_count: Dict[str, int] = {}
        for o in observations:
            pid = o.provider_id or "unknown"
            provider_obs_count[pid] = provider_obs_count.get(pid, 0) + 1

        all_known_providers = ["native_dns", "native_rdap", "native_ct", "subfinder", "metabigor", "spiderfoot", "maigret", "uncover"]
        contributions = []
        for pid in all_known_providers:
            st = provider_stats.get(pid)
            obs_cnt = provider_obs_count.get(pid, 0)
            if st:
                status_str = "SUCCESS" if obs_cnt > 0 else "NO_FINDINGS"
                if st["status"] in ("FAILED", "ERROR"):
                    status_str = "ERROR"
                contributions.append({
                    "provider_id": pid,
                    "status": status_str,
                    "observations_count": obs_cnt,
                    "tasks_count": st["tasks_count"],
                    "duration_ms": round(st.get("duration_ms", 0), 1),
                    "error_message": st.get("error_message"),
                    "credential_state": "OK" if pid != "uncover" else "MISSING_CREDENTIAL"
                })
            else:
                contributions.append({
                    "provider_id": pid,
                    "status": "SKIPPED" if pid != "uncover" else "MISSING_CREDENTIAL",
                    "observations_count": 0,
                    "tasks_count": 0,
                    "duration_ms": 0.0,
                    "error_message": "Không kích hoạt cho loại đối tượng này" if pid != "uncover" else "Chưa cấu hình API Key tìm kiếm",
                    "credential_state": "OK" if pid != "uncover" else "MISSING_CREDENTIAL"
                })

        # --- C. Empty Result Explanation ---
        total_enrichments = max(0, len(entities) - (1 if seed_target else 0))
        is_empty = (total_enrichments == 0 and len(assertions) == 0)

        checked_count = sum(1 for c in contributions if c["tasks_count"] > 0)
        no_findings_count = sum(1 for c in contributions if c["status"] == "NO_FINDINGS")
        error_count = sum(1 for c in contributions if c["status"] == "ERROR")
        missing_cred_count = sum(1 for c in contributions if c["status"] == "MISSING_CREDENTIAL")

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

        return {
            "case_id": case_id,
            "target": target_val,
            "target_type": target_type,
            "status": latest_run.status if latest_run else "COMPLETED",
            "run_id": latest_run.id if latest_run else None,
            "entities_count": len(entities),
            "assertions_count": len(assertions),
            "observations_count": len(observations),
            "entity_type_counts": entity_type_counts,
            "email_insights": email_insights,
            "domain_insights": domain_insights,
            "ip_insights": ip_insights,
            "username_insights": username_insights,
            "phone_insights": phone_insights,
            "provider_contributions": contributions,
            "empty_reason": empty_reason
        }
