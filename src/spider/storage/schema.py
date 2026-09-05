import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CaseRecord(Base):
    __tablename__ = "cases"
    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    status = Column(String(32), default="ACTIVE", index=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    metadata_json = Column(JSON, default=dict)

class TargetRecord(Base):
    __tablename__ = "targets"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    observable_type = Column(String(32), nullable=False, index=True)
    namespace = Column(String(255), nullable=False, default="", server_default="")
    raw_input = Column(Text, nullable=False)
    canonical_value = Column(String(512), nullable=False, index=True)
    scope_authorized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
    metadata_json = Column(JSON, default=dict)

class RawArtifactRecord(Base):
    __tablename__ = "raw_artifacts"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=False, index=True)
    provider_id = Column(String(64), nullable=False)
    storage_path = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    byte_size = Column(Integer, nullable=False)
    mime_type = Column(String(64), default="text/plain")
    created_at = Column(DateTime, default=utc_now)

class ObservationRecord(Base):
    __tablename__ = "observations"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=False, index=True)
    seed_id = Column(String(64), nullable=True, index=True)
    observable_type = Column(String(32), nullable=False, index=True)
    namespace = Column(String(255), nullable=False, default="", server_default="")
    observable_metadata = Column(JSON, default=dict)
    observable_value = Column(Text, nullable=False)
    canonical_value = Column(String(512), nullable=False, index=True)
    provider_id = Column(String(64), nullable=False, index=True)
    provider_version = Column(String(32), nullable=False)
    adapter_version = Column(String(32), default="1.0.0")
    upstream_source = Column(String(128), nullable=True)
    upstream_family = Column(String(64), nullable=False, index=True)
    parent_observable_value = Column(String(512), nullable=True)
    parent_observable_type = Column(String(32), nullable=True)
    parent_namespace = Column(String(255), nullable=False, default="", server_default="")
    raw_artifact_sha256 = Column(String(64), nullable=True)
    configuration_hash = Column(String(64), default="default")
    confidence = Column(Float, default=0.8)
    raw_data_json = Column(JSON, default=dict)
    raw_artifact_id = Column(String(64), ForeignKey("raw_artifacts.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        Index("idx_obs_case_canonical", "case_id", "canonical_value"),
        Index("idx_obs_family", "upstream_family"),
    )

class EntityRecord(Base):
    __tablename__ = "entities"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    observable_type = Column(String(32), nullable=False, index=True)
    namespace = Column(String(255), nullable=False, default="", server_default="")
    canonical_name = Column(String(512), nullable=False, index=True)
    first_seen = Column(DateTime, default=utc_now)
    last_seen = Column(DateTime, default=utc_now)
    observation_count = Column(Integer, default=1)
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_entity_typed_identity", "case_id", "observable_type", "namespace", "canonical_name", unique=True),
    )

class AssertionRecord(Base):
    __tablename__ = "assertions"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    source_entity_id = Column(String(64), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_id = Column(String(64), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    assertion_type = Column(String(64), nullable=False, index=True)
    confidence = Column(Float, default=0.8)
    independent_source_count = Column(Integer, default=1)
    source_families = Column(JSON, default=list)
    resolver_version = Column(String(32), default="1.0.0")
    inference_rule = Column(String(64), default="DIRECT_OBSERVATION")
    first_observed = Column(DateTime, default=utc_now)
    last_observed = Column(DateTime, default=utc_now)
    metadata_json = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_assertion_src_tgt_type", "case_id", "source_entity_id", "target_entity_id", "assertion_type", unique=True),
    )

class EvidenceRefRecord(Base):
    __tablename__ = "evidence_refs"
    id = Column(String(64), primary_key=True)
    assertion_id = Column(String(64), ForeignKey("assertions.id", ondelete="CASCADE"), nullable=False, index=True)
    observation_id = Column(String(64), ForeignKey("observations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(String(64), nullable=False)
    upstream_family = Column(String(64), nullable=False)
    confidence_weight = Column(Float, default=0.8)
    excerpt = Column(Text, nullable=True)
    raw_artifact_sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now)

class ExecutionLedgerRecord(Base):
    __tablename__ = "execution_ledger"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_key_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default="COMPLETED")
    executed_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        Index("idx_ledger_case_key", "case_id", "execution_key_hash", unique=True),
    )

class TaskRunRecord(Base):
    __tablename__ = "task_runs"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    execution_key_hash = Column(String(64), nullable=False)
    provider_id = Column(String(64), nullable=False, index=True)
    capability = Column(String(64), nullable=False)
    target_observable_value = Column(String(512), nullable=False)
    status = Column(String(32), default="PENDING", index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    observations_count = Column(Integer, default=0)
    raw_artifact_id = Column(String(64), nullable=True)
    metadata_json = Column(JSON, default=dict)

class ProviderRunRecord(Base):
    __tablename__ = "provider_runs"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="PENDING", index=True)
    started_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)
    tasks_count = Column(Integer, default=0)
    observations_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)


class EgressRecord(Base):
    __tablename__ = "egress_events"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=False)
    seed_id = Column(String(64), nullable=True)
    provider_id = Column(String(64), nullable=False)
    identifier_type = Column(String(32), nullable=False)
    identifier_fingerprint = Column(String(64), nullable=False)
    destination = Column(String(255), nullable=False)
    purpose = Column(String(64), nullable=False)
    derivation = Column(String(16), nullable=False)
    authentication = Column(String(16), nullable=False)
    outcome = Column(String(32), nullable=False)
    policy_decision = Column(String(32), nullable=False, default="ALLOWED")
    budget_decision = Column(String(32), nullable=False, default="RESERVED")
    observed_at = Column(DateTime, default=utc_now)


class ProviderAuditRecord(Base):
    __tablename__ = "provider_audits"
    provider_id = Column(String(64), primary_key=True)
    provider_version = Column(String(64), nullable=False)
    adapter_version = Column(String(64), nullable=False)
    state = Column(String(32), nullable=False)
    failure_streak = Column(Integer, default=0)
    success_streak = Column(Integer, default=0)
    report_sha256 = Column(String(64), nullable=False)
    checked_at = Column(DateTime, default=utc_now)


class EvidenceReviewRecord(Base):
    __tablename__ = "evidence_reviews"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    seed_id = Column(String(64), nullable=False)
    claim_id = Column(String(64), nullable=False)
    observation_id = Column(String(64), nullable=False)
    role = Column(String(32), nullable=False)
    dependency = Column(String(32), nullable=False)
    origin_id = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime, default=utc_now)


class HypothesisRecord(Base):
    __tablename__ = "investigation_hypotheses"
    id = Column(String(64), primary_key=True)
    case_id = Column(String(64), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    seed_id = Column(String(64), ForeignKey("targets.id", ondelete="CASCADE"), nullable=False, index=True)
    statement = Column(String(1000), nullable=False)
    evidence_json = Column(JSON, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now)
