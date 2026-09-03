# Public footprint improvement plan

Authorized follow-up to v2.0.0; preserve the completed release. Scope: public
profiles for self-audits or authorized investigations. No private databases,
password-reset probes, access-control bypass, or automatic person identification.

## Delivery and acceptance

1. Repair Maigret integration using a structured report from an isolated worker.
   Preserve per-site negative/unknown outcomes, reject URL-only positives, retain
   partial results and reap cancelled workers. Offer 50, 500 or all enabled
   supported sites within an explicit time limit. Exclude entries requiring token
   activation, non-HTTP protocols or similar-username searches.
   For positive status-only/absence-only detections, check a random control handle
   and abstain when the website claims both accounts exist. Count unfinished or
   unavailable controls; a partial run must not imply all candidates were checked.
2. Persist running task progress, timestamps and completed/partial/failed outcomes.
   A blocked lookup must not be reported as absence of an account.
3. Search GitHub's official public user API by email, then fetch each candidate
   profile and require an exact public email match. Show public name, bio and
   profile link with provenance. Do not infer identity from an email's spelling.
4. Separate profile evidence from mail infrastructure in the Vietnamese/light UI.
   Show public HTML title/description already fetched by Maigret with no additional
   network requests. A page title is not an independently verified personal name.
   Explain missing profile evidence even when DNS results exist. Shared usernames
   are candidates, never proof of one person's ownership.
5. Verify contracts, cancellation, browser flow and existing regression suite.
   Run a bounded live self-audit; keep its email and results outside Git/fixtures.
6. Benchmark pinned MIT Maigret and Sherlock on identical synthetic local sites.
   Publish truth labels, versions, precision, recall, coverage and elapsed time.
   This measures integration and failure handling, not the whole public Internet.

## Claim gate

No superiority claim from wrapping competitors or counting graph nodes. Report
ties, misses, unknowns and regressions. No promise to search every website.
The v2.0.0 tag remains unchanged; new work stays local pending release approval.

## Primary references

- [Maigret MIT license](https://github.com/soxoj/maigret/blob/main/LICENSE)
- [Maigret coverage](https://github.com/soxoj/maigret/blob/main/docs/source/usage-examples.rst)
- [Sherlock MIT license](https://github.com/sherlock-project/sherlock/blob/master/LICENSE)
- [GitHub user search](https://docs.github.com/en/search-github/searching-on-github/searching-users)
- [GitHub public profiles](https://docs.github.com/en/rest/users/users)
