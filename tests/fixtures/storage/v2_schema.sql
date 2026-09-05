-- Immutable SPIDER b78ac03 schema, synthetic migration fixture only.

CREATE TABLE cases (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT, 
	tags JSON, 
	status VARCHAR(32), 
	created_at DATETIME, 
	updated_at DATETIME, 
	metadata_json JSON, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_cases_status ON cases (status);

CREATE TABLE entities (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	observable_type VARCHAR(32) NOT NULL, 
	canonical_name VARCHAR(512) NOT NULL, 
	first_seen DATETIME, 
	last_seen DATETIME, 
	observation_count INTEGER, 
	metadata_json JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_entities_case_id ON entities (case_id);
CREATE UNIQUE INDEX idx_entity_case_canonical ON entities (case_id, canonical_name);
CREATE INDEX ix_entities_canonical_name ON entities (canonical_name);
CREATE INDEX ix_entities_observable_type ON entities (observable_type);

CREATE TABLE execution_ledger (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	execution_key_hash VARCHAR(64) NOT NULL, 
	status VARCHAR(32), 
	executed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_execution_ledger_case_id ON execution_ledger (case_id);
CREATE UNIQUE INDEX idx_ledger_case_key ON execution_ledger (case_id, execution_key_hash);
CREATE INDEX ix_execution_ledger_execution_key_hash ON execution_ledger (execution_key_hash);

CREATE TABLE provider_runs (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	status VARCHAR(32), 
	started_at DATETIME, 
	completed_at DATETIME, 
	tasks_count INTEGER, 
	observations_count INTEGER, 
	error_message TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_provider_runs_status ON provider_runs (status);
CREATE INDEX ix_provider_runs_case_id ON provider_runs (case_id);

CREATE TABLE raw_artifacts (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(64) NOT NULL, 
	task_id VARCHAR(64) NOT NULL, 
	provider_id VARCHAR(64) NOT NULL, 
	storage_path TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	byte_size INTEGER NOT NULL, 
	mime_type VARCHAR(64), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_raw_artifacts_case_id ON raw_artifacts (case_id);
CREATE INDEX ix_raw_artifacts_sha256 ON raw_artifacts (sha256);
CREATE INDEX ix_raw_artifacts_task_id ON raw_artifacts (task_id);
CREATE INDEX ix_raw_artifacts_run_id ON raw_artifacts (run_id);

CREATE TABLE targets (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	observable_type VARCHAR(32) NOT NULL, 
	raw_input TEXT NOT NULL, 
	canonical_value VARCHAR(512) NOT NULL, 
	scope_authorized BOOLEAN, 
	created_at DATETIME, 
	metadata_json JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_targets_observable_type ON targets (observable_type);
CREATE INDEX ix_targets_canonical_value ON targets (canonical_value);
CREATE INDEX ix_targets_case_id ON targets (case_id);

CREATE TABLE task_runs (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(64) NOT NULL, 
	execution_key_hash VARCHAR(64) NOT NULL, 
	provider_id VARCHAR(64) NOT NULL, 
	capability VARCHAR(64) NOT NULL, 
	target_observable_value VARCHAR(512) NOT NULL, 
	status VARCHAR(32), 
	started_at DATETIME, 
	completed_at DATETIME, 
	error_message TEXT, 
	observations_count INTEGER, 
	raw_artifact_id VARCHAR(64), 
	metadata_json JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_task_runs_case_id ON task_runs (case_id);
CREATE INDEX ix_task_runs_provider_id ON task_runs (provider_id);
CREATE INDEX ix_task_runs_status ON task_runs (status);
CREATE INDEX ix_task_runs_run_id ON task_runs (run_id);

CREATE TABLE assertions (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	source_entity_id VARCHAR(64) NOT NULL, 
	target_entity_id VARCHAR(64) NOT NULL, 
	assertion_type VARCHAR(64) NOT NULL, 
	confidence FLOAT, 
	independent_source_count INTEGER, 
	source_families JSON, 
	resolver_version VARCHAR(32), 
	inference_rule VARCHAR(64), 
	first_observed DATETIME, 
	last_observed DATETIME, 
	metadata_json JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE, 
	FOREIGN KEY(source_entity_id) REFERENCES entities (id) ON DELETE CASCADE, 
	FOREIGN KEY(target_entity_id) REFERENCES entities (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_assertions_target_entity_id ON assertions (target_entity_id);
CREATE INDEX ix_assertions_source_entity_id ON assertions (source_entity_id);
CREATE UNIQUE INDEX idx_assertion_src_tgt_type ON assertions (case_id, source_entity_id, target_entity_id, assertion_type);
CREATE INDEX ix_assertions_case_id ON assertions (case_id);
CREATE INDEX ix_assertions_assertion_type ON assertions (assertion_type);

CREATE TABLE observations (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(64) NOT NULL, 
	task_id VARCHAR(64) NOT NULL, 
	observable_type VARCHAR(32) NOT NULL, 
	observable_value TEXT NOT NULL, 
	canonical_value VARCHAR(512) NOT NULL, 
	provider_id VARCHAR(64) NOT NULL, 
	provider_version VARCHAR(32) NOT NULL, 
	adapter_version VARCHAR(32), 
	upstream_source VARCHAR(128), 
	upstream_family VARCHAR(64) NOT NULL, 
	parent_observable_value VARCHAR(512), 
	configuration_hash VARCHAR(64), 
	confidence FLOAT, 
	raw_data_json JSON, 
	raw_artifact_id VARCHAR(64), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE, 
	FOREIGN KEY(raw_artifact_id) REFERENCES raw_artifacts (id)
)

;
CREATE INDEX idx_obs_case_canonical ON observations (case_id, canonical_value);
CREATE INDEX ix_observations_run_id ON observations (run_id);
CREATE INDEX ix_observations_case_id ON observations (case_id);
CREATE INDEX ix_observations_upstream_family ON observations (upstream_family);
CREATE INDEX ix_observations_canonical_value ON observations (canonical_value);
CREATE INDEX ix_observations_created_at ON observations (created_at);
CREATE INDEX ix_observations_task_id ON observations (task_id);
CREATE INDEX idx_obs_family ON observations (upstream_family);
CREATE INDEX ix_observations_provider_id ON observations (provider_id);
CREATE INDEX ix_observations_observable_type ON observations (observable_type);

CREATE TABLE evidence_refs (
	id VARCHAR(64) NOT NULL, 
	assertion_id VARCHAR(64) NOT NULL, 
	observation_id VARCHAR(64) NOT NULL, 
	provider_id VARCHAR(64) NOT NULL, 
	upstream_family VARCHAR(64) NOT NULL, 
	confidence_weight FLOAT, 
	excerpt TEXT, 
	raw_artifact_sha256 VARCHAR(64), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(assertion_id) REFERENCES assertions (id) ON DELETE CASCADE, 
	FOREIGN KEY(observation_id) REFERENCES observations (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_evidence_refs_observation_id ON evidence_refs (observation_id);
CREATE INDEX ix_evidence_refs_assertion_id ON evidence_refs (assertion_id);