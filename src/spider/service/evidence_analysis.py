"""Conservative analysis of evidence already collected. No network or identity merge."""
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit


def public_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        # Query/fragment can contain tracking, access tokens or unrelated page state.
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", ""))
    except (ValueError, TypeError):
        return None


def link_proofs(observations):
    proofs = []
    for obs in observations:
        if obs.observable_type != "ACCOUNT":
            continue
        raw = obs.raw_data_json if isinstance(obs.raw_data_json, dict) else {}
        source = public_url(raw.get("profile_url"))
        if not source:
            continue
        links = list(raw.get("explicit_links", [])) if isinstance(raw.get("explicit_links"), list) else []
        if raw.get("website"):
            links.append({"url": raw["website"], "basis": "profile_website"})
        for link in links[:50]:
            if not isinstance(link, dict):
                continue
            target = public_url(link.get("url"))
            if not target or target == source or link.get("basis") not in {"rel_me", "jsonld_sameAs", "profile_website", "webfinger_self"}:
                continue
            proof_id = hashlib.sha256(f"{obs.id}|{source}|{target}|{link['basis']}".encode()).hexdigest()
            proofs.append({"id": proof_id, "source": source, "target": target,
                "kind": "SELF_ASSERTED_LINK", "basis": link["basis"], "observation_id": obs.id,
                "observed_at": obs.created_at.isoformat(), "identity_verified": False})
    pairs = {(p["source"], p["target"]) for p in proofs}
    for proof in proofs:
        if (proof["target"], proof["source"]) in pairs:
            proof["kind"] = "RECIPROCAL_LINK"
    return proofs


def assess_hypothesis(evidence):
    """Keep disagreement visible; unknown dependencies count as one cluster, not votes."""
    support, contradict, unknown, clusters = [], [], [], set()
    for item in evidence:
        role = item.get("role", "UNKNOWN")
        group = support if role == "SUPPORTING_EVIDENCE" else contradict if role == "CONTRADICTING_EVIDENCE" else unknown
        group.append(item["id"])
        if role == "SUPPORTING_EVIDENCE":
            dependency = item.get("dependency", "UNKNOWN_DEPENDENCY")
            clusters.add(item.get("origin_id") if dependency in {"INDEPENDENT_SOURCE", "DERIVED_SOURCE", "MIRRORED_SOURCE"}
                         and item.get("origin_id") else "UNKNOWN_DEPENDENCY")
    return {"SUPPORTING_EVIDENCE": support, "CONTRADICTING_EVIDENCE": contradict, "UNKNOWN": unknown,
            "dependency_clusters": len(clusters), "review_required": bool(contradict or unknown or not support),
            "identity_verified": False, "decision": "REVIEW_REQUIRED" if contradict or unknown else "LINK_EVIDENCE_ONLY"}


def ownership_hypotheses(observations, proofs=None):
    """Build one reviewable ownership hypothesis per typed account candidate.

    Accounts with the same username on different platforms remain separate.
    Public links support a relationship only and never verify a common owner.
    """
    proofs = proofs if proofs is not None else link_proofs(observations)
    proofs_by_observation = {}
    for proof in proofs:
        proofs_by_observation.setdefault(proof["observation_id"], []).append(proof)
    grouped = {}
    for obs in sorted(observations, key=lambda item: (item.created_at, item.id)):
        if obs.observable_type != "ACCOUNT":
            continue
        raw = obs.raw_data_json if isinstance(obs.raw_data_json, dict) else {}
        profile = public_url(raw.get("profile_url"))
        if not profile:
            continue
        namespace = str(getattr(obs, "namespace", "") or "")[:128]
        account = str(getattr(obs, "canonical_value", "") or "")[:512]
        key = (namespace, account)
        row = grouped.setdefault(key, {"namespace": namespace, "account": account,
            "profile_urls": set(), "evidence_ids": set(), "proof_ids": set(),
            "proof_kinds": set(), "evidence_basis": set()})
        row["profile_urls"].add(profile)
        row["evidence_ids"].add(obs.id)
        row["evidence_basis"].add(str(raw.get("match_basis") or "PROFILE_ROUTE_OBSERVED")[:128])
        for proof in proofs_by_observation.get(obs.id, []):
            row["proof_ids"].add(proof["id"])
            row["proof_kinds"].add(proof["kind"])
    output = []
    for (namespace, account), row in sorted(grouped.items()):
        hypothesis_id = hashlib.sha256(
            f"ACCOUNT_MAY_RELATE_TO_SEED|{namespace}|{account}".encode()).hexdigest()
        proof_kinds = sorted(row["proof_kinds"])
        output.append({"id": hypothesis_id, "claim_type": "ACCOUNT_MAY_RELATE_TO_SEED",
            "account": {"type": "ACCOUNT", "namespace": namespace,
                        "canonical_value": account},
            "profile_urls": sorted(row["profile_urls"])[:20],
            "evidence_ids": sorted(row["evidence_ids"])[:20],
            "link_proof_ids": sorted(row["proof_ids"])[:20],
            "evidence_basis": sorted(row["evidence_basis"]),
            "status": "RECIPROCAL_LINK_AVAILABLE" if "RECIPROCAL_LINK" in proof_kinds
                      else "SELF_ASSERTED_LINK_ONLY" if proof_kinds else "PROFILE_CANDIDATE",
            "identity_verified": False})
    total = len(output)
    for row in output:
        row["candidate_set_size"] = total
        row["alternatives_unresolved"] = total > 1
    return output


def evidence_next_action(hypotheses, proofs):
    """Return deterministic advice only; it never dispatches a request."""
    if not hypotheses:
        action, basis = "REVIEW_SOURCE_COVERAGE", "NO_ACCOUNT_CANDIDATE"
    elif any(not row["link_proof_ids"] for row in hypotheses):
        action, basis = "COLLECT_SELF_PUBLISHED_LINKS", "PROFILE_WITHOUT_LINK_PROOF"
    elif any(proof["kind"] == "SELF_ASSERTED_LINK" for proof in proofs):
        action, basis = "CHECK_RECIPROCAL_PUBLIC_LINK", "ONE_WAY_SELF_ASSERTED_LINK"
    else:
        action, basis = "COMPARE_INDEPENDENT_PROFILE_EVIDENCE", "RECIPROCAL_LINK_AVAILABLE"
    return {"action": action, "basis": basis, "dispatch": False,
            "identity_verified": False}


def temporal_events(observations):
    grouped, events = {}, []
    for obs in sorted(observations, key=lambda o: (o.created_at, o.id)):
        key = (obs.observable_type, obs.namespace, obs.canonical_value)
        raw = obs.raw_data_json if isinstance(obs.raw_data_json, dict) else {}
        archived_at = raw.get("archived_at")
        if raw.get("archive_capture_missing") is True:
            event = "NO_ARCHIVED_OBSERVATION"
        elif raw.get("absence_verified") is True and raw.get("specific_negative_signal"):
            event = "DISAPPEARED"
        else:
            prior = grouped.get(key)
            # Only compare bounded evidence fields, not incidental provider response data.
            fingerprint = json.dumps({k: raw.get(k) for k in ("display_name", "bio", "website", "explicit_links")}, sort_keys=True)
            event = "CHANGED" if prior and prior[0] != fingerprint else "OBSERVED"
            grouped[key] = (fingerprint, obs.id)
        events.append({"observation_id": obs.id, "event": event, "observed_at": obs.created_at.isoformat(),
                       "archived_at": archived_at, "view": "ARCHIVED" if archived_at else "CURRENT_OBSERVATION"})
    return events


def analyze(observations):
    links = link_proofs(observations)
    ownership = ownership_hypotheses(observations, links)
    evidence = []
    for link in links:
        evidence.append({"id": link["id"], "role": "SUPPORTING_EVIDENCE", "dependency": "UNKNOWN_DEPENDENCY"})
    return {"label": "EXPERIMENT RESULT", "link_proofs": links,
            "ownership_hypotheses": ownership,
            "next_best_action": evidence_next_action(ownership, links),
            "link_assessment": assess_hypothesis(evidence), "temporal_events": temporal_events(observations),
            "limitations": ["Public links do not establish common ownership", "Missing archive capture does not prove disappearance"]}
