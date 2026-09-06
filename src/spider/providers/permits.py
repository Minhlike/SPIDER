"""Anonymous-pipe request permits, granted by the parent before worker I/O."""
import re
from spider.models.budget import RequestBudgetExceeded


class RequestPermits:
    def __init__(self, provider_id, ledger=None, budget=None, recorder=None, *, destination=None,
                 credentialed=False, origin_limits=None):
        self.provider_id, self.ledger, self.budget, self.recorder = provider_id, ledger, budget, recorder
        self.destination, self.credentialed = destination, credentialed
        self.sequence = 0
        self.granted = 0
        self.denied = False
        self.events = {}
        self.finished = set()
        self.origin_limits, self.leases = origin_limits, {}
        self.destinations = {}

    async def grant(self, frame):
        if (not isinstance(frame, dict) or frame.get("kind") != "request_permit"
                or type(frame.get("sequence")) is not int or frame["sequence"] != self.sequence + 1
                or frame.get("purpose") not in {"lookup", "negative_control", "account_validation", "internet_asset_search"}
                or not isinstance(frame.get("destination"), str)
                or not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}|<identifier-host>", frame["destination"])
                or (self.destination and frame["destination"] != self.destination)):
            raise ValueError("Invalid request permit frame")
        fingerprint = frame.get("identifier_fingerprint")
        if fingerprint is not None and (not isinstance(fingerprint, str)
                                       or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)):
            raise ValueError("Invalid request fingerprint")
        self.sequence += 1
        lease = await self.origin_limits.acquire(frame["destination"]) if self.origin_limits else None
        try:
            if self.ledger is not None:
                self.ledger.request(self.budget, self.provider_id, "HTTP", frame["purpose"])
        except RequestBudgetExceeded:
            if lease:
                lease.release()
            self.denied = True
            return False
        except BaseException:
            if lease:
                lease.release()
            raise
        if lease:
            self.leases[frame["sequence"]] = lease
            self.destinations[frame["sequence"]] = frame["destination"]
        self.granted += 1
        if self.recorder:
            self.events[frame["sequence"]] = await self.recorder.begin(frame["destination"],
                frame["purpose"], credentialed=self.credentialed, fingerprint=fingerprint)
        return True

    async def finish(self, sequence, outcome):
        if not isinstance(outcome, str) or not re.fullmatch(
                r"HTTP_[1-5][0-9]{2}|CONNECTION_FAILED|UNKNOWN_AFTER_DISPATCH", outcome):
            raise ValueError("Invalid request outcome")
        destination = self.destinations.pop(sequence, None)
        if destination and self.origin_limits and outcome == "HTTP_429":
            self.origin_limits.feedback(destination, 429)
        lease = self.leases.pop(sequence, None)
        if lease:
            lease.release()
        if sequence in self.events and sequence not in self.finished:
            await self.recorder.finish(self.events[sequence], outcome)
            self.finished.add(sequence)

    async def close(self):
        # A grant is an attempted dispatch, not evidence of a completed response.
        for sequence in set(self.leases) | (self.events.keys() - self.finished):
            await self.finish(sequence, "UNKNOWN_AFTER_DISPATCH")
