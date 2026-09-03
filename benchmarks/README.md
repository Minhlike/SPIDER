# Public footprint benchmark

This is an integration/failure-classification benchmark, not an Internet-wide
coverage ranking. All usernames, pages and profile text are synthetic. No real
email address belongs in this directory.

## Reproduce on Windows

Run from the repository root with the existing local SPIDER/Maigret runtime:

```powershell
.\runtime\venv\Scripts\python.exe -m venv runtime/benchmarks/sherlock
.\runtime\benchmarks\sherlock\Scripts\python.exe -m pip install sherlock-project==0.16.0
.\runtime\venv\Scripts\python.exe -m benchmarks.run_public_footprint
```

The benchmark writes ignored results to `test-results/public-footprint-benchmark`.
Sherlock is an isolated comparison runtime, not a production dependency/provider.
Maigret 0.6.5 and Sherlock 0.16.0 use their library entry points without changes to
their installed source files. Results record versions and engine-source hashes.
SPIDER adds structured progress, partial-result retention and public metadata
extraction around Maigret; its detection logic still depends on Maigret.

## Protocol

| Fixture | Ground truth | HTTP behavior |
|---|---|---|
| Present | Account exists | 200 and profile content |
| Absent | No account | 404 |
| SoftAbsent | No account | 200 and configured absence marker |
| Blocked | Insufficient evidence | 403 |
| RateLimited | Insufficient evidence | 429 |
| Slow | Insufficient evidence | Response delayed beyond timeout |
| Wildcard | No account | Generic 200 for every username, including a random control |

All engines get the same seven local endpoints, equivalent status/message rules,
four-second request timeout, at most twenty connections and no proxies,
recursion, extra enrichment requests or retry rounds. SPIDER additionally checks
an unpredictable control handle for positive status-only/absence-only detections;
this adds requests and abstains when the control also appears to exist. Upstream
baselines use their regular search entry points, without optional catalogue
self-checks. This difference and its cost are part of the measured configuration.
Three repetitions rotate
execution order. Timings include child-process startup. No other SPIDER test or
live investigation should run concurrently with the final benchmark measurement.

Precision, recall, F1 and decision coverage use only known positive/negative
cases. Unknown cases are scored separately, including false claims of absence.
Report all outcomes and request counts, not just a positive-profile list.

This small dataset cannot measure real-world recall, dynamic login walls,
CAPTCHAs, site catalogue freshness, cross-platform identity accuracy or legal
name verification. Wider claims require a representative, consented dataset and
the same site set/configuration for each tool. Do not compare arbitrary counts
of supported websites as proof of accuracy.

## Sources

- [Maigret usage](https://github.com/soxoj/maigret/blob/main/docs/source/usage-examples.rst)
- [Maigret MIT license](https://github.com/soxoj/maigret/blob/main/LICENSE)
- [Sherlock MIT license](https://github.com/sherlock-project/sherlock/blob/master/LICENSE)
- [Sherlock source](https://github.com/sherlock-project/sherlock)
