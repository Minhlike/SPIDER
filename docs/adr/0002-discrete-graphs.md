# ADR 0002: Discrete Tri-Graph Architecture

## Context
OSINT engines frequently conflate execution state, capability routing, and discovered intelligence in a single graph, leading to messy schema couplings.

## Decision
Maintain three distinct graph representations:
1. **Control Graph (DAG)**: Models capabilities, prerequisites, routing rules, and workflow templates.
2. **Execution Graph**: Models runtime execution tasks, provider states, retries, timing, and errors.
3. **Knowledge Graph (Cyclic Multi-DiGraph)**: Models observables, entities, assertions, relationships, and evidence pointers.

## Consequences
- Clean separation of concerns.
- Clear data models and failure isolation.
