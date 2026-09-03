"""Run unmodified upstream library entry points against a local site catalogue."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path


class Quiet:
    def start(self, *args, **kwargs): pass
    def finish(self, *args, **kwargs): pass
    def update(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def success(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def enrich(self, *args, **kwargs): pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=["maigret", "sherlock"])
    parser.add_argument("database")
    parser.add_argument("output")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    if args.engine == "maigret":
        import maigret
        import maigret.checking
        db = maigret.MaigretDatabase().load_from_file(args.database)
        results = asyncio.run(maigret.search("fixture-user", db.ranked_sites_dict(disabled=False),
            logging.getLogger("benchmark"), query_notify=Quiet(), timeout=4, max_connections=20,
            no_progressbar=True, retries=0, is_parsing_enabled=False, is_enrich_enabled=False,
            check_domains=False, dns_resolver="threaded"))
        source = Path(maigret.checking.__file__)
        version = importlib.metadata.version("maigret")
    else:
        from sherlock_project.sherlock import sherlock
        import sherlock_project.sherlock as module
        results = sherlock("fixture-user", json.loads(Path(args.database).read_text()), Quiet(), timeout=4)
        source = Path(module.__file__)
        version = importlib.metadata.version("sherlock-project")
    states = {name: row["status"].status.value for name, row in results.items()}
    Path(args.output).write_text(json.dumps({"states": states, "version": version,
        "engine_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
