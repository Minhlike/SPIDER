# SPIDER Policy & Safety Engine

## Network Classes
- `LOCAL_ONLY`: Fully offline processing.
- `THIRD_PARTY_ONLY`: Queries 3rd-party registries and passive data sources (Default enabled).
- `TARGET_DIRECT`: Direct inspection of target infrastructure (Requires profile authorization).
- `TARGET_ACTIVE`: Active scanning/probing (Requires explicit target scope authorization).
- `PRIVILEGED_LOCAL`: Administrative elevation operations.

## Safety Guarantees
- No automated credential attacks, brute forcing, exploitation, or authentication bypass.
- Subprocess arguments are passed as structured arrays (argv), preventing shell injection.
