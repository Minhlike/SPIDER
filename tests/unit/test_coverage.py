from types import SimpleNamespace

from spider.service.coverage import collection_state, coverage_report


def test_list_provider_outcomes_cannot_crash_case_coverage():
    task = SimpleNamespace(id="task", provider_id="fixture", status="PARTIAL",
                           error_message=None, metadata_json={"budget_reason": ["timeout"]})
    assert collection_state(task, 0) == "ATTEMPTED"
    report = coverage_report([task], [], ["fixture"])
    assert report["steps"][0]["state"] == "ATTEMPTED"
