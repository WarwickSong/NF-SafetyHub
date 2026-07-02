from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings
from storage.reports import LOCAL_TZ, ReportBuildData

FONT = "STSong-Light"


class MetricCard(Flowable):
    def __init__(self, title: str, value: str, note: str, accent: str = "#2563eb", width: float = 41 * mm, height: float = 25 * mm):
        super().__init__()
        self.title = title
        self.value = value
        self.note = note
        self.accent = colors.HexColor(accent)
        self.width = width
        self.height = height

    def draw(self):
        self.canv.setFillColor(colors.white)
        self.canv.setStrokeColor(colors.HexColor("#d9e2ec"))
        self.canv.roundRect(0, 0, self.width, self.height, 6, stroke=1, fill=1)
        self.canv.setFillColor(self.accent)
        self.canv.roundRect(0, self.height - 3 * mm, self.width, 3 * mm, 5, stroke=0, fill=1)
        self.canv.setFillColor(colors.HexColor("#64748b"))
        self.canv.setFont(FONT, 7.5)
        self.canv.drawString(4 * mm, 15.5 * mm, self.title)
        self.canv.setFillColor(colors.HexColor("#0f172a"))
        self.canv.setFont(FONT, 15)
        self.canv.drawString(4 * mm, 8 * mm, self.value)
        self.canv.setFillColor(colors.HexColor("#64748b"))
        self.canv.setFont(FONT, 6.8)
        self.canv.drawString(4 * mm, 3.5 * mm, self.note)


class SectionBar(Flowable):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.width = 178 * mm
        self.height = 13 * mm

    def draw(self):
        self.canv.setFillColor(colors.HexColor("#eef4ff"))
        self.canv.roundRect(0, 0, self.width, self.height, 5, stroke=0, fill=1)
        self.canv.setFillColor(colors.HexColor("#2563eb"))
        self.canv.roundRect(0, 0, 3 * mm, self.height, 2, stroke=0, fill=1)
        self.canv.setFillColor(colors.HexColor("#102033"))
        self.canv.setFont(FONT, 12)
        self.canv.drawString(7 * mm, 7.5 * mm, self.title)
        if self.subtitle:
            self.canv.setFillColor(colors.HexColor("#64748b"))
            self.canv.setFont(FONT, 7.5)
            self.canv.drawRightString(self.width - 5 * mm, 7.8 * mm, self.subtitle)


class LineChart(Flowable):
    def __init__(self, title: str, labels: list[str], series: list[tuple[str, list[float], str]], visible_labels: list[str] | None = None, width: float = 178 * mm, height: float = 54 * mm):
        super().__init__()
        self.title = title
        self.labels = labels
        self.visible_labels = visible_labels or labels
        self.series = series
        self.width = width
        self.height = height

    def draw(self):
        left = 12 * mm
        right = 7 * mm
        top = 10 * mm
        bottom = 10 * mm
        plot_width = self.width - left - right
        plot_height = self.height - top - bottom
        values = [value for _, row, _ in self.series for value in row]
        max_value = max(max(values) * 1.15, 1) if values else 1
        self.canv.setFillColor(colors.white)
        self.canv.setStrokeColor(colors.HexColor("#dbe4ef"))
        self.canv.roundRect(0, 0, self.width, self.height, 6, stroke=1, fill=1)
        self.canv.setFillColor(colors.HexColor("#102033"))
        self.canv.setFont(FONT, 9.5)
        self.canv.drawString(5 * mm, self.height - 6 * mm, self.title)
        for index in range(4):
            y = bottom + plot_height * index / 3
            self.canv.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.canv.setLineWidth(0.3)
            self.canv.line(left, y, left + plot_width, y)
        for index, label in enumerate(self.visible_labels):
            if not label:
                continue
            x = left + plot_width * index / max(1, len(self.labels) - 1)
            self.canv.setFillColor(colors.HexColor("#64748b"))
            self.canv.setFont(FONT, 6.5)
            self.canv.drawCentredString(x, 4 * mm, label[:8])
        for offset, (name, row, color) in enumerate(self.series):
            points = []
            for index, value in enumerate(row):
                x = left + plot_width * index / max(1, len(row) - 1)
                y = bottom + plot_height * value / max_value
                points.append((x, y))
            self.canv.setStrokeColor(colors.HexColor(color))
            self.canv.setLineWidth(1.2)
            for start, end in zip(points, points[1:]):
                self.canv.line(start[0], start[1], end[0], end[1])
            self.canv.setFillColor(colors.HexColor(color))
            for x, y in points:
                self.canv.circle(x, y, 1.2, stroke=0, fill=1)
            legend_y = self.height - 6 * mm - offset * 4 * mm
            self.canv.circle(self.width - 58 * mm, legend_y + 1, 1.4, stroke=0, fill=1)
            self.canv.setFillColor(colors.HexColor("#475569"))
            self.canv.setFont(FONT, 6.8)
            self.canv.drawString(self.width - 55 * mm, legend_y - 1, name)


def generate_report_files(data: ReportBuildData, report_id: int) -> tuple[dict[str, str], dict[str, str]]:
    base_dir = _report_dir(data)
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = f"safetyhub_{data.period.report_type}_{data.period.label}_{report_id}"
    files = {
        "pdf": base_dir / f"{stem}.pdf",
        "xlsx": base_dir / f"{stem}.xlsx",
        "csv": base_dir / f"{stem}.csv",
    }
    _write_pdf(data, files["pdf"])
    _write_xlsx(data, files["xlsx"])
    _write_csv(data, files["csv"])
    rel_paths = {key: str(path.relative_to(settings.reports_dir)) for key, path in files.items()}
    hashes = {key: _sha256(path) for key, path in files.items()}
    return rel_paths, hashes


def resolve_report_path(relative_path: str) -> Path:
    root = settings.reports_dir.resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents and path != root:
        raise ValueError("invalid report path")
    return path


def _report_dir(data: ReportBuildData) -> Path:
    return settings.reports_dir / data.period.report_type / data.period.label.replace("-", "/")


def _write_pdf(data: ReportBuildData, path: Path) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story = []
    story.extend(_pdf_cover(data))
    story.append(_metrics_row(data))
    story.append(SectionBar("一、管理结论", "关键指标与处置建议"))
    story.append(Spacer(1, 6))
    story.append(_table(_conclusion_rows(data), widths=[55 * mm, 55 * mm, 68 * mm]))
    story.append(SectionBar("二、趋势与风险", "按周期聚合"))
    story.append(Spacer(1, 6))
    story.append(_runtime_chart(data))
    story.append(Spacer(1, 8))
    story.append(_table(_trend_rows(data), widths=[36 * mm, 30 * mm, 30 * mm, 30 * mm, 30 * mm]))
    story.append(SectionBar("三、规则命中排行", "默认不展示完整上下文"))
    story.append(Spacer(1, 6))
    story.append(_table(_rule_rows(data), widths=[55 * mm, 28 * mm, 32 * mm, 30 * mm, 33 * mm]))
    story.append(PageBreak())
    story.append(SectionBar("四、运行状态采样摘要", "曲线优先，数字辅助"))
    story.append(Spacer(1, 6))
    story.append(_runtime_table(data))
    story.append(Spacer(1, 8))
    story.append(Paragraph("说明：本报表中的系统运行状态来自周期采样聚合，不使用生成时刻快照替代周期状态。", _styles()["small"]))
    doc.build(story, onFirstPage=_page, onLaterPages=_page)


def _write_xlsx(data: ReportBuildData, path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "概览"
    for row in [["报表类型", data.period.report_type], ["统计周期", data.period.label], ["是否包含敏感字段", data.include_sensitive], *data.summary.items()]:
        ws.append(list(row))
    _sheet(wb, "趋势", data.trend)
    _sheet(wb, "规则排行", data.rules)
    _sheet(wb, "APIKey统计", data.api_keys)
    _sheet(wb, "高风险明细", data.high_risk)
    runtime = data.runtime.copy()
    _sheet(wb, "系统状态", [{"key": key, "value": json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value} for key, value in runtime.items()])
    wb.save(path)


def _write_csv(data: ReportBuildData, path: Path) -> None:
    rows = data.high_risk or []
    fields = sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sheet(wb: Workbook, title: str, rows: list[dict]) -> None:
    ws = wb.create_sheet(title=title)
    if not rows:
        ws.append(["empty"])
        return
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(header, "") for header in headers])


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "cover_title": ParagraphStyle("cover_title", fontName=FONT, fontSize=25, leading=34, textColor=colors.white, alignment=TA_LEFT),
        "cover_subtitle": ParagraphStyle("cover_subtitle", fontName=FONT, fontSize=10.5, leading=17, textColor=colors.HexColor("#dbeafe"), alignment=TA_LEFT),
        "body": ParagraphStyle("body", fontName=FONT, fontSize=9, leading=15, textColor=colors.HexColor("#334155")),
        "center": ParagraphStyle("center", fontName=FONT, fontSize=8.5, leading=12, textColor=colors.HexColor("#334155"), alignment=TA_CENTER),
        "small": ParagraphStyle("small", fontName=FONT, fontSize=7.5, leading=11, textColor=colors.HexColor("#64748b")),
    }


def _page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#f8fafc"))
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.setFont(FONT, 7)
    canvas.drawString(16 * mm, 9 * mm, "LLM-SafetyHub 自动生成报表 · 敏感明细默认不包含")
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"第 {doc.page} 页")
    canvas.restoreState()


def _pdf_cover(data: ReportBuildData) -> list:
    title = {"daily": "SafetyHub 安全日报", "weekly": "SafetyHub 安全周报", "monthly": "SafetyHub 安全月报"}.get(data.period.report_type, "SafetyHub 安全报表")
    subtitle = f"统计周期：{data.period.label}｜时区：Asia/Shanghai｜敏感明细：{'包含' if data.include_sensitive else '未包含'}"
    box = Table([[[Paragraph(title, _styles()["cover_title"]), Spacer(1, 5), Paragraph(subtitle, _styles()["cover_subtitle"])]]], colWidths=[178 * mm], rowHeights=[42 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f2a43")), ("LEFTPADDING", (0, 0), (-1, -1), 12 * mm), ("TOPPADDING", (0, 0), (-1, -1), 9 * mm)]))
    return [box, Spacer(1, 10)]


def _metrics_row(data: ReportBuildData):
    summary = data.summary
    cards = [
        ("总请求次数", str(summary.get("total_requests", 0)), f"事件率 {summary.get('event_rate', 0)}%", "#2563eb"),
        ("安全事件", str(summary.get("security_events", 0)), "审计事件总数", "#f59e0b"),
        ("拦截请求", str(summary.get("blocked", 0)), "高风险优先处理", "#dc2626"),
        ("系统采样", str(data.runtime.get("sample_count", 0)), "周期采样点", "#16a34a"),
    ]
    return Table([[MetricCard(*card) for card in cards]], colWidths=[43 * mm] * 4, hAlign="LEFT", spaceAfter=8)


def _table(rows, widths=None):
    body = [[Paragraph(str(cell), _styles()["center"] if index else _styles()["body"]) for index, cell in enumerate(row)] for row in rows]
    result = Table(body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2ff")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f2a43")), ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe4ef")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 5)]))
    return result


def _conclusion_rows(data: ReportBuildData) -> list[list[str]]:
    return [["结论", "影响", "建议动作"], [f"周期内安全事件率 {data.summary.get('event_rate', 0)}%。", "中继与审计运行压力可控。", "持续观察高峰时段和高风险规则。"], [f"拦截请求 {data.summary.get('blocked', 0)} 次。", "存在敏感项外发尝试。", "复核规则排行和高风险明细。"], [f"运行采样 {data.runtime.get('sample_count', 0)} 个点。", "可用于判断周期稳定性。", "关注曲线峰值和异常采样。"]]


def _trend_rows(data: ReportBuildData) -> list[list[str]]:
    rows = [["周期", "安全事件", "拦截", "CPU均/低/高", "排队均/低/高"]]
    rows.extend([
        [
            item.get("label", ""),
            item.get("security_events", 0),
            item.get("blocked", 0),
            _stat_text(item, "cpu"),
            _stat_text(item, "queue"),
        ]
        for item in _table_trend_rows(data.trend)
    ])
    return rows


def _rule_rows(data: ReportBuildData) -> list[list[str]]:
    rows = [["规则", "级别", "扫描器", "动作", "次数"]]
    rows.extend([[item.get("rule_id", ""), item.get("rule_level", ""), item.get("scanner_type", ""), item.get("action_taken", ""), item.get("count", 0)] for item in data.rules[:10]])
    return rows


def _runtime_table(data: ReportBuildData):
    runtime = data.runtime
    return _table([
        ["采样项", "平均值", "最小值", "最大/最低", "说明"],
        ["CPU 使用率", runtime.get("cpu_avg", 0), runtime.get("cpu_min", 0), runtime.get("cpu_peak", 0), "周期采样聚合"],
        ["内存使用率", runtime.get("memory_avg", 0), runtime.get("memory_min", 0), runtime.get("memory_peak", 0), "周期采样聚合"],
        ["/v1 排队", runtime.get("queue_avg", 0), runtime.get("queue_min", 0), runtime.get("queue_peak", 0), "周期采样聚合"],
        ["归档队列", runtime.get("archive_queue_avg", 0), runtime.get("archive_queue_min", 0), runtime.get("archive_queue_peak", 0), "周期采样聚合"],
        ["数据盘剩余", "-", "-", _format_bytes(runtime.get("data_disk_min_free", 0)), "周期内最低空闲"],
        ["系统盘剩余", "-", "-", _format_bytes(runtime.get("system_disk_min_free", 0)), "周期内最低空闲"],
    ], widths=[32 * mm, 28 * mm, 28 * mm, 32 * mm, 58 * mm])


def _runtime_chart(data: ReportBuildData):
    rows = data.trend or [{"label": "无数据", "cpu_avg": 0, "queue_avg": 0, "archive_avg": 0}]
    labels = [item.get("label", "") for item in rows]
    cpu = [_metric_value(item, "cpu") for item in rows]
    queue = [_metric_value(item, "queue") for item in rows]
    archive = [_metric_value(item, "archive") for item in rows]
    return LineChart("运行状态曲线｜均值趋势（横轴标签抽稀）", labels, [("CPU均值%", cpu, "#2563eb"), ("排队均值", queue, "#f59e0b"), ("归档队列均值", archive, "#16a34a")], _axis_labels(data.period.report_type, labels))


def _metric_value(item: dict, prefix: str) -> float:
    return float(item.get(prefix + "_avg", item.get(prefix + "_peak", 0)) or 0)


def _axis_labels(report_type: str, labels: list[str]) -> list[str]:
    if not labels:
        return []
    visible = [""] * len(labels)
    if report_type == "daily":
        for index, label in enumerate(labels):
            if label.endswith(":00"):
                visible[index] = label[:2]
        return visible
    if report_type == "monthly":
        for index, label in enumerate(labels):
            visible[index] = label[-2:]
        return visible
    for index, label in enumerate(labels):
        if index == 0 or index == len(labels) - 1 or label.endswith("00:00"):
            visible[index] = label[5:10]
    return visible


def _table_trend_rows(rows: list[dict]) -> list[dict]:
    if len(rows) <= 14:
        return rows
    step = max(1, len(rows) // 14)
    selected = rows[::step]
    if selected[-1] is not rows[-1]:
        selected.append(rows[-1])
    return selected[:16]


def _stat_text(item: dict, prefix: str) -> str:
    return f"{item.get(prefix + '_avg', 0)}/{item.get(prefix + '_min', 0)}/{item.get(prefix + '_peak', 0)}"


def _format_bytes(value: int) -> str:
    if not value:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.1f}{units[index]}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
