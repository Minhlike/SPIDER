"""Aggregate a de-identified JSONL holdout without printing input rows."""
import argparse
import json
from pathlib import Path

from benchmarks.research_protocols import (score_email_benchmark,
    score_scheduler_holdout, score_username_manual_benchmark)


SCORERS = {
    "email": score_email_benchmark,
    "username-manual": score_username_manual_benchmark,
    "scheduler": score_scheduler_holdout,
}


def load_rows(path, max_rows=100_000):
    rows = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if number > max_rows:
                raise ValueError("Dataset row limit exceeded")
            if len(line) > 1_000_000:
                raise ValueError("Dataset row is too large")
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("Every dataset row must be an object")
                rows.append(value)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=sorted(SCORERS))
    parser.add_argument("dataset")
    args = parser.parse_args(argv)
    result = SCORERS[args.kind](load_rows(args.dataset))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
