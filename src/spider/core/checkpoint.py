"""Versioned, credential-free checkpoints for deterministic investigation runs."""
from __future__ import annotations

from typing import Any, Iterable

from spider.models.budget import BudgetLedger
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable

CHECKPOINT_VERSION = 1


def encode_frontier(frontier: Iterable[tuple[NormalizedObservable, str, int]]) -> list[dict[str, Any]]:
    return [{
        "observable_type": observable.type.value,
        "namespace": observable.namespace,
        "value": observable.value,
        "canonical_value": observable.canonical_value,
        "seed_id": seed_id,
        "depth": depth,
    } for observable, seed_id, depth in frontier]


def decode_frontier(rows: Iterable[dict[str, Any]]) -> list[tuple[NormalizedObservable, str, int]]:
    frontier = []
    for row in rows:
        depth = int(row["depth"])
        if depth < 0:
            raise ValueError("Checkpoint depth must be non-negative")
        frontier.append((NormalizedObservable(
            type=ObservableType(row["observable_type"]),
            namespace=str(row.get("namespace") or ""),
            value=str(row["value"]),
            canonical_value=str(row["canonical_value"]),
        ), str(row["seed_id"]), depth))
    return frontier


def encode_checkpoint(frontier, executed_keys, ledger: BudgetLedger, state: str) -> dict[str, Any]:
    return {
        "version": CHECKPOINT_VERSION,
        "state": state,
        "frontier": encode_frontier(frontier),
        "executed_execution_keys": sorted(executed_keys),
        "admitted_entities": [list(identity) for identity in sorted(ledger.admitted_entity_keys())],
    }


def restore_ledger(payload: dict[str, Any] | None, checkpoint: dict[str, Any]) -> BudgetLedger:
    ledger = BudgetLedger.model_validate(payload or {})
    identities = checkpoint.get("admitted_entities", [])
    if any(not isinstance(identity, list) or len(identity) != 4
           or any(not isinstance(part, str) for part in identity) for identity in identities):
        raise ValueError("Checkpoint entity identity is invalid")
    ledger.restore_admitted_entity_keys(identities)
    return ledger
