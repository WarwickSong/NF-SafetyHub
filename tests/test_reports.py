from datetime import datetime
from pathlib import Path

from config import settings
from reports.generator import generate_report_files, resolve_report_path
from storage.models import RuntimeSample
from storage.reports import LOCAL_TZ, ReportBuildData, _build_trend, period_from_values


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
        trend=[{"label": "00:00", "security_events": 1, "blocked": 1, "cpu_avg": 12.5, "cpu_min": 8.0, "cpu_peak": 22.5, "queue_avg": 2.0, "queue_min": 1, "queue_peak": 3, "archive_avg": 4.0, "archive_min": 2, "archive_peak": 5}],
        rules=[{"rule_id": "keyword_secret", "rule_level": "block", "scanner_type": "keyword", "action_taken": "blocked", "count": 1}],
        api_keys=[{"user_id": "user-a", "security_events": 3}],
        runtime={"sample_count": 1, "cpu_avg": 12.5, "cpu_min": 8.0, "cpu_peak": 22.5, "memory_avg": 30.0, "memory_min": 20.0, "memory_peak": 40.0, "queue_avg": 2.0, "queue_min": 1, "queue_peak": 3, "archive_queue_avg": 4.0, "archive_queue_min": 2, "archive_queue_peak": 5, "data_disk_min_free": 1024, "system_disk_min_free": 2048},
        high_risk=[{"id": 1, "created_at": datetime.now(LOCAL_TZ).isoformat(), "user_id": "user-a", "rule_id": "keyword_secret", "rule_level": "block", "action_taken": "blocked"}],
        include_sensitive=False,
    )

    paths, hashes = generate_report_files(data, 1)

    for key in ("pdf", "xlsx", "csv"):
        output = Path(settings.reports_dir) / paths[key]
        assert output.exists()
        assert hashes[key]
    assert (Path(settings.reports_dir) / paths["pdf"]).read_bytes().startswith(b"%PDF")


def test_runtime_trend_uses_fine_grained_buckets_and_stats():
    daily = period_from_values("daily", "2026-06-29")
    weekly = period_from_values("weekly", "2026-W27")
    monthly = period_from_values("monthly", "2026-06")

    daily_rows = _build_trend(daily, [], [
        RuntimeSample(sampled_at=datetime(2026, 6, 29, 0, 4, tzinfo=LOCAL_TZ), cpu_percent=10, v1_queued=1, archive_queue_size=3),
        RuntimeSample(sampled_at=datetime(2026, 6, 29, 0, 9, tzinfo=LOCAL_TZ), cpu_percent=20, v1_queued=5, archive_queue_size=7),
        RuntimeSample(sampled_at=datetime(2026, 6, 29, 0, 11, tzinfo=LOCAL_TZ), cpu_percent=30, v1_queued=2, archive_queue_size=4),
    ])
    weekly_rows = _build_trend(weekly, [], [RuntimeSample(sampled_at=datetime(2026, 6, 29, 3, 20, tzinfo=LOCAL_TZ), cpu_percent=11, v1_queued=0, archive_queue_size=0)])
    monthly_rows = _build_trend(monthly, [], [RuntimeSample(sampled_at=datetime(2026, 6, 15, 13, 0, tzinfo=LOCAL_TZ), cpu_percent=12, v1_queued=0, archive_queue_size=0)])

    assert [row["label"] for row in daily_rows] == ["00:00", "00:10"]
    assert daily_rows[0]["cpu_avg"] == 15
    assert daily_rows[0]["cpu_min"] == 10
    assert daily_rows[0]["cpu_peak"] == 20
    assert weekly_rows[0]["label"] == "2026-06-29 02:00"
    assert monthly_rows[0]["label"] == "2026-06-15"


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
