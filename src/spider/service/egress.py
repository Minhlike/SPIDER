"""Persist disclosure attempts without identifiers, query strings, headers or credentials."""
import hashlib
import hmac
import json
import uuid
from urllib.parse import urlsplit, unquote
from spider.storage.schema import EgressRecord


def safe_destination(value, identifier):
    parsed = urlsplit(value if "://" in value else "//" + value)
    hostname = (parsed.hostname or "unknown").lower()
    if identifier and unquote(identifier).lower() in unquote(hostname).lower():
        return "<identifier-host>"
    return hostname[:255]


class EgressRecorder:
    def __init__(self, writer, task, target, lineage, derivation, salt):
        self.writer, self.task, self.target = writer, task, target
        self.seed_id, self.derivation = lineage.seed_id, derivation
        self.salt = salt
        # Salt is per run, in memory only. Fingerprints cannot be correlated across runs.
        self.fingerprint = hmac.new(salt, json.dumps(target.identity).encode(), hashlib.sha256).hexdigest()

    async def begin(self, destination, purpose="lookup", credentialed=False, identifier=None, fingerprint=None):
        identifier = identifier or self.target
        digest = fingerprint or hmac.new(self.salt, json.dumps(identifier.identity).encode(), hashlib.sha256).hexdigest()
        event_id = str(uuid.uuid4())
        async def write(session):
            session.add(EgressRecord(id=event_id, case_id=self.task.case_id, run_id=self.task.run_id,
                task_id=self.task.id, seed_id=self.seed_id, provider_id=self.task.provider_id,
                identifier_type=identifier.type.value, identifier_fingerprint=digest,
                destination=safe_destination(destination, identifier.canonical_value), purpose=purpose,
                # Negative controls disclose a synthetic value even though their
                # plaintext is deliberately absent from the parent process.
                derivation=("DERIVED" if purpose == "negative_control" or
                            identifier.identity != self.target.identity else self.derivation),
                authentication="CREDENTIALED" if credentialed else "ANONYMOUS",
                outcome="DISPATCH_ATTEMPTED"))
        await self.writer.submit(write)
        return event_id

    async def finish(self, event_id, outcome):
        async def write(session):
            event = await session.get(EgressRecord, event_id)
            event.outcome = outcome
        await self.writer.submit(write)
