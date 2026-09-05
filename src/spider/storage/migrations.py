"""Small, transactional SQLite migrations. Never inspect raw artifacts or secrets."""
from sqlalchemy import inspect


def migrate_typed_identity(connection):
    tables = set(inspect(connection).get_table_names())
    if "entities" not in tables:
        return []
    old_identity = "namespace" not in {c["name"] for c in inspect(connection).get_columns("entities")}
    additions = {
        "provider_runs": {"metadata_json": "JSON"},
        "entities": {"namespace": "VARCHAR(255) NOT NULL DEFAULT ''"},
        "targets": {"namespace": "VARCHAR(255) NOT NULL DEFAULT ''"},
        "observations": {
            "seed_id": "VARCHAR(64)",
            "namespace": "VARCHAR(255) NOT NULL DEFAULT ''",
            "observable_metadata": "JSON",
            "parent_observable_type": "VARCHAR(32)",
            "parent_namespace": "VARCHAR(255) NOT NULL DEFAULT ''",
            "raw_artifact_sha256": "VARCHAR(64)",
        },
    }
    for table, columns in additions.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in inspect(connection).get_columns(table)}
        for name, declaration in columns.items():
            if name not in existing:
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    connection.exec_driver_sql("DROP INDEX IF EXISTS idx_entity_case_canonical")
    connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_typed_identity "
                               "ON entities (case_id, observable_type, namespace, canonical_name)")
    # A historical observation can be assigned without guessing only when its
    # case has exactly one seed. Multi-seed legacy cases remain explicitly
    # unscoped so projection cannot contaminate one target with another.
    if "observations" in tables and "targets" in tables:
        connection.exec_driver_sql(
            "UPDATE observations SET seed_id = ("
            "SELECT MIN(targets.id) FROM targets WHERE targets.case_id = observations.case_id) "
            "WHERE seed_id IS NULL AND 1 = ("
            "SELECT COUNT(*) FROM targets WHERE targets.case_id = observations.case_id)"
        )
    if not old_identity:
        return []
    # Restore evidence hashes using artifact metadata, without opening artifact files.
    connection.exec_driver_sql("UPDATE observations SET raw_artifact_sha256 = "
        "(SELECT sha256 FROM raw_artifacts WHERE raw_artifacts.id = observations.raw_artifact_id)")
    return list(connection.exec_driver_sql("SELECT DISTINCT case_id FROM observations").scalars())
