from datetime import datetime
from pathlib import Path

from config import settings
from reports.generator import generate_report_files, resolve_report_path
from storage.reports import LOCAL_TZ, ReportBuildData, period_from_values


def test_report_periods_use_shanghai_natural_boundaries():
    daily = period_from_values("daily", "2026-06-29")
    weekly = period_from_values("weekly", "2026-W27")
    monthly = period_from_values("monthly", "2026-06")

    assert daily.start.astimezone(LOCAL_TZ).isoformat().startswith("2026-06-29T00:00:00")
    assert daily.end.astimezone(LOCAL_TZ).isoformat().startswith("2026-06-30T00:00:00")
    assert weekly.start.astimezone(LOCAL_TZ).weekday() == 0
    assert (weekly.end - weekly.start).days == 7
    assert monthly.start.astimezone(LOCAL_TZ).day == 1
    assert monthly.end.astimezone(LOCAL_TZ).month == 7


def test_generate_report_files_outputs_pdf_xlsx_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reports_dir", tmp_path)
    period = period_from_values("daily", "2026-06-29")
    data = ReportBuildData(
        period=period,
        summary={"total_requests": 100, "security_events": 3, "blocked": 1, "event_rate": 3.0},
        trend=[{"label": "00:00", "security_events": 1, "blocked": 1, "cpu_peak": 22.5, "queue_peak": 3, "archive_peak": 5}],
        rules=[{"rule_id": "keyword_secret", "rule_level": "block", "scanner_type": "keyword", "action_taken": "blocked", "count": 1}],
        api_keys=[{"user_id": "user-a", "security_events": 3}],
        runtime={"sample_count": 1, "cpu_avg": 12.5, "cpu_peak": 22.5, "memory_avg": 30.0, "memory_peak": 40.0, "queue_peak": 3, "archive_queue_peak": 5, "data_disk_min_free": 1024},
        high_risk=[{"id": 1, "created_at": datetime.now(LOCAL_TZ).isoformat(), "user_id": "user-a", "rule_id": "keyword_secret", "rule_level": "block", "action_taken": "blocked"}],
        include_sensitive=False,
    )

    paths, hashes = generate_report_files(data, 1)

    for key in ("pdf", "xlsx", "csv"):
        output = Path(settings.reports_dir) / paths[key]
        assert output.exists()
        assert hashes[key]
    assert (Path(settings.reports_dir) / paths["pdf"]).read_bytes().startswith(b"%PDF")


def test_resolve_report_path_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reports_dir", tmp_path)

    safe = resolve_report_path("daily/2026/06/report.pdf")

    assert safe == tmp_path / "daily/2026/06/report.pdf"
    for value in ("../secret.txt", "/etc/passwd"):
        try:
            resolve_report_path(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe path accepted: {value}")
