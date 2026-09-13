import json

import pytest

from benchmarks.score_research_dataset import load_rows, main


def test_dataset_loader_accepts_jsonl_objects_without_echoing_rows(tmp_path):
    path = tmp_path / "holdout.jsonl"
    path.write_text(json.dumps({"fixture_id": "deidentified-hash"}) + "\n\n",
                    encoding="utf-8")
    assert load_rows(path) == [{"fixture_id": "deidentified-hash"}]


def test_dataset_loader_rejects_non_object_and_oversized_rows(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rows(path)
    path.write_text(json.dumps({"value": "x" * 1_000_000}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rows(path)


def test_cli_prints_aggregate_without_fixture_identifier(tmp_path, capsys):
    fixture_id = "a" * 64
    row = {"fixture_id": fixture_id, "service": "fixture", "cohort": "OVERLAP",
           "truth": "EXISTS", "engine": "holehe",
           "outcome": "CONFIRMED_EXISTS", "requests": 1}
    path = tmp_path / "email.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    main(["email", str(path)])
    output = capsys.readouterr().out
    assert fixture_id not in output
    assert json.loads(output)["adoption_gate"] == "NOT_YET_VERIFIED"


def test_cli_rejects_raw_identifier_fields(tmp_path):
    row = {"fixture_id": "b" * 64, "service": "fixture", "cohort": "OVERLAP",
           "truth": "EXISTS", "engine": "holehe",
           "outcome": "CONFIRMED_EXISTS", "requests": 1,
           "email": "must-not-be-accepted@example.invalid"}
    path = tmp_path / "unsafe.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        main(["email", str(path)])
