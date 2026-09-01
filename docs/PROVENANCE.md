# SPIDER Provenance & Source Families

## Upstream Family Classification
SPIDER groups data sources into distinct upstream families:
- `CERTIFICATE_TRANSPARENCY` (e.g., crt.sh, certspotter)
- `DNS` (e.g., DNS brute-force, authoritative zone lookup, dnsdumpster)
- `ROUTING_REGISTRY` (e.g., BGPView, RADB, ARIN, RIPE, APNIC)
- `SECURITY_INTELLIGENCE` (e.g., VirusTotal, AlienVault, SecurityTrails)
- `INTERNET_SCANNER` (e.g., Shodan, Censys, FOFA, ZoomEye)
- `SOCIAL_MEDIA` (e.g., GitHub, Reddit, Twitter/X profile registries)
- `EMAIL_INTELLIGENCE` (e.g., Hunter.io, breach registries)
- `PHONE_REGISTRY` (e.g., Numverify, telco registries)

## Confidence Calculation
Confidence is weighted by **independent source families**, not raw tool count:
```
confidence = min(0.99, base_confidence + (len(distinct_families) - 1) * 0.05)
```
