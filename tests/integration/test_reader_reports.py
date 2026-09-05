import json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from spider.models.enums import ObservableType as T
from spider.service.reporting import reader_report, markdown_report, vocabulary
from spider.service.service import SpiderService
from spider.storage.schema import ProviderRunRecord, TaskRunRecord


def data(**changes):
    return {"target_type": "EMAIL", "status": "COMPLETED", "run_id": "run",
            "observations_count": 0, "assertions_count": 0, "scope": {},
            "coverage_report": {"decided": 0, "unknown": 1, "steps": [
                {"provider_id": "fixture", "state": "BLOCKED", "reason": "untrusted-error-token"}]}, **changes}


def test_blocked_and_absence_are_different_and_raw_errors_are_not_prose():
    blocked = reader_report(data())
    negative = reader_report(data(coverage_report={"decided": 1, "unknown": 0,
        "steps": [{"provider_id": "fixture", "state": "NOT_FOUND", "reason": None}]}))
    assert "Không thể kết luận" in blocked["conclusion"]
    assert blocked["sources"][0]["message"] != negative["sources"][0]["message"]
    assert "untrusted-error-token" not in json.dumps(blocked)
    assert "hạ tầng" in markdown_report(blocked)
    assert "not identity verification" in markdown_report(reader_report(data(), "en"))


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "PENDING"])
def test_running_is_not_a_final_conclusion(status):
    report = reader_report(data(status=status))
    assert "chưa phải kết luận cuối cùng" in report["conclusion"]
    assert "Theo dõi" in report["sections"][3]["items"][0]


def test_candidates_conflicts_and_unmeasured_scores_never_verify_a_person():
    report = reader_report(data(public_profiles=[{"profile_url": "https://fixture.invalid"}],
        evidence_analysis={"hypotheses": [{"CONTRADICTING_EVIDENCE": ["evidence"]}]}))
    assert "Chưa đủ cơ sở" in report["conclusion"]
    text = markdown_report(report)
    assert "bằng chứng chưa thống nhất" in text
    assert "không phải xác suất" in text
    assert set(vocabulary("vi")) == set(vocabulary("en"))


def test_markdown_cannot_turn_source_text_into_html_or_links():
    report = reader_report(data(target='<script>alert(1)</script>', reader_findings=[{
        "value": '[click](javascript:alert(1))', "evidence_ids": ['fixture']}]))
    text = markdown_report(report)
    assert '<script>' not in text and '[click](javascript:' not in text


def test_api_ui_exports_share_words_and_latest_run_is_target_scoped(tmp_path, monkeypatch):
    import spider.web.app as web_app
    service = SpiderService(str(tmp_path / "reports.db"), str(tmp_path / "runs"))
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    with TestClient(web_app.create_app()) as client:
        async def prepare():
            case = await service.create_case("Synthetic reader reports")
            a = await service.add_target(case["id"], "alpha", T.USERNAME)
            b = await service.add_target(case["id"], "beta", T.USERNAME)
            async def insert(session):
                for seed, run, status, time in ((a, "own", "PARTIAL", datetime.now(timezone.utc)),
                        (b, "foreign", "COMPLETED", datetime.now(timezone.utc) + timedelta(seconds=1))):
                    session.add(ProviderRunRecord(id=run, case_id=case["id"], status=status,
                        started_at=time, metadata_json={"expected_sources": {seed["id"]: ["fixture"]}}))
                session.add(TaskRunRecord(id="task", case_id=case["id"], run_id="own",
                    status="PARTIAL", provider_id="fixture", capability="USERNAME_DISCOVERY",
                    execution_key_hash="fixture", target_observable_value="alpha",
                    metadata_json={"seed_id": a["id"], "collection_state": "BLOCKED"}))
            await service.db_writer.submit(insert)
            return case["id"], a["id"], b["id"]
        case, a, b = client.portal.call(prepare)
        base = f"/api/cases/{case}"
        insights = client.get(base + "/insights", params={"target_id": a}).json()
        assert insights["run_id"] == "own" and insights["status"] == "PARTIAL"
        narrative = insights["reader_report"]
        exported = client.get(base + "/export", params={"target_id": a}).json()
        bundle = client.get(base + "/bundle", params={"target_id": a}).json()
        assert exported["reader_report"] == bundle["manifest"]["reader_report"] == narrative
        markdown = client.get(base + "/report", params={"target_id": a})
        assert markdown.status_code == 200 and 'spider-report.md' in markdown.headers['content-disposition']
        assert narrative["vi"]["conclusion"] in markdown.text
        assert "beta" not in markdown.text
        assert client.get(base + "/report").status_code == 422
        assert client.get(base + "/report", params={"target_id": "foreign-seed"}).status_code == 422
        assert client.get(base + "/report", params={"target_id": a, "language": "invalid"}).status_code == 422
