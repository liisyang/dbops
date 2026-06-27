"""Inspection report DOCX export (plan §8).

Builds a single Word document in memory and serves it via FileResponse with a
BackgroundTasks cleanup hook. 500-instance cap, raw evidence gated to admin.

Layout (plan §8.3): cover -> basic info -> health summary -> level distribution
-> critical/warning listings -> instance summary table -> per-instance details
-> appendix.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor
from fastapi import BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.models.dbops_assets import (
    InspectionInstanceReport,
    InspectionReport,
    InspectionResult,
    InspectionTask,
    InspectionTaskItem,
    InspectionTaskTarget,
)
from app.services.inspection_evaluator_service import InspectionEvaluatorService


# plan §8.2 limits
MAX_INSTANCES_IN_DOCX = 500
RAW_ROWS_PREVIEW = 5
MESSAGE_PREVIEW = 240

HEALTH_LEVEL_LABEL = {
    "healthy": "健康",
    "warning": "告警",
    "critical": "严重",
    "unknown": "未知",
    "not_assessed": "未评估",
}

EVAL_STATUS_LABEL = {
    "normal": "正常",
    "warning": "告警",
    "critical": "严重",
    "unknown": "未知",
    "not_evaluated": "未评估",
}

REPORT_STATUS_LABEL = {
    "generating": "生成中",
    "ready": "已就绪",
    "partial": "部分",
    "failed": "失败",
}


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def build_report_docx(
    db: Session,
    *,
    report: InspectionReport,
    include_raw_evidence: bool,
    single_instance: tuple[str, int] | None = None,
) -> Document:
    """Build a python-docx Document for the given report.

    When ``single_instance`` is provided as ``(target_type, target_id)``,
    the document is scoped to just that one instance: only its results are
    pulled, only its instance_report is shown, and the section titles are
    relabeled accordingly. Used by the "export single instance" endpoint.
    """
    task = db.query(InspectionTask).filter(InspectionTask.id == int(report.task_id)).first()
    task_items = (
        db.query(InspectionTaskItem)
        .filter(InspectionTaskItem.task_id == int(report.task_id))
        .order_by(InspectionTaskItem.check_order, InspectionTaskItem.id)
        .all()
    )
    task_targets = (
        db.query(InspectionTaskTarget)
        .filter(InspectionTaskTarget.task_id == int(report.task_id))
        .order_by(InspectionTaskTarget.id)
        .all()
    )
    instance_reports_query = db.query(InspectionInstanceReport).filter(
        InspectionInstanceReport.report_id == int(report.id)
    )
    results_query = db.query(InspectionResult).filter(
        InspectionResult.task_id == int(report.task_id)
    )

    # Bug5 fix 2026-06-26: drop results whose task_item is not applicable to
    # the task_target's db_type. Without this guard, a task created with
    # "all DB types + all inspection items" lists every item under every
    # target, so an Oracle instance's report section shows MSSQL_* items and
    # vice versa. Mirrors InspectionService._is_task_item_applicable.
    target_db_types: dict[int, str | None] = {
        int(tt.id): (tt.db_type_code_snapshot or None) for tt in task_targets
    }
    item_db_types: dict[int, str | None] = {
        int(ti.id): (ti.db_type_code or None) for ti in task_items
    }

    def _is_applicable(task_item_id: int, task_target_id: int) -> bool:
        item_db = item_db_types.get(int(task_item_id))
        target_db = target_db_types.get(int(task_target_id))
        if item_db is None:
            # db-type-agnostic items (e.g. connectivity) apply to every target.
            return True
        if target_db is None:
            return False
        return item_db.lower() == target_db.lower()

    applicable_pairs: list[tuple[int, int]] = [
        (int(ti.id), int(tt.id))
        for ti in task_items
        for tt in task_targets
        if _is_applicable(int(ti.id), int(tt.id))
    ]

    if single_instance is not None:
        target_type, target_id = single_instance
        instance_reports_query = instance_reports_query.filter(
            InspectionInstanceReport.target_type == target_type,
            InspectionInstanceReport.target_id == int(target_id),
        )
        # Constrain results to the (task_item, task_target) pairs whose
        # task_item matches the target's db_type. applicable_pairs is keyed
        # by (task_item.id, task_target.id), so we compare against the
        # task_target's asset target_id, NOT the surrogate task_target.id.
        task_target_for_instance = next(
            (tt for tt in task_targets
             if tt.target_type == target_type
             and int(tt.target_id) == int(target_id)),
            None,
        )
        applicable_item_ids_for_target: set[int] = set()
        if task_target_for_instance is not None:
            applicable_item_ids_for_target = {
                item_id
                for item_id, tt_id in applicable_pairs
                if int(tt_id) == int(task_target_for_instance.id)
            }
        results_query = results_query.filter(
            InspectionResult.target_type == target_type,
            InspectionResult.target_id == int(target_id),
            InspectionResult.task_item_id.in_(applicable_item_ids_for_target),
        )
    else:
        # Full-report export: filter by (task_item, task_target) tuple so the
        # "严重/告警清单" and per-instance detail tables don't list MSSQL items
        # under an Oracle instance (and vice versa).
        if applicable_pairs:
            results_query = results_query.filter(
                tuple_(
                    InspectionResult.task_item_id,
                    InspectionResult.task_target_id,
                ).in_(applicable_pairs)
            )

    instance_reports = instance_reports_query.order_by(InspectionInstanceReport.id).all()
    results = results_query.all()

    document = Document()
    _apply_default_style(document)
    _write_cover(document, report, task, single_instance=single_instance)
    _write_basic_info(document, report, task, single_instance=single_instance)
    document.add_page_break()
    _write_health_summary(document, report, instance_reports)
    _write_level_distribution(document, instance_reports)
    _write_alerts(document, results)
    document.add_page_break()
    _write_instance_summary_table(document, instance_reports)
    _write_instance_details(
        document,
        instance_reports,
        results,
        task_items,
        task_targets,
        include_raw_evidence=include_raw_evidence,
    )
    document.add_page_break()
    _write_appendix(document, report, task, include_raw_evidence=include_raw_evidence)
    return document


def build_docx_response(
    *,
    report_code: str,
    document: Document,
    background_tasks: BackgroundTasks,
    single_instance: tuple[str, int] | None = None,
) -> FileResponse:
    """Save document to a temp file, register cleanup, return FileResponse.

    When ``single_instance`` is set, the filename includes the target id so
    operators can tell two single-instance downloads apart.
    """
    if single_instance is not None:
        _, target_id = single_instance
        prefix = f"inspection-report-{report_code}-instance-{target_id}-"
        download_name = f"inspection-report-{report_code}-instance-{target_id}.docx"
    else:
        prefix = f"inspection-report-{report_code}-"
        download_name = f"inspection-report-{report_code}.docx"
    with NamedTemporaryFile(prefix=prefix, suffix=".docx", delete=False) as f:
        temp_path = f.name
    document.save(temp_path)
    background_tasks.add_task(_remove_file, temp_path)
    return FileResponse(
        path=temp_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
        background=background_tasks,
    )


def _remove_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _apply_default_style(document: Document) -> None:
    style = document.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(10.5)


def _add_heading(document: Document, text: str, *, level: int = 1) -> None:
    h = document.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)


def _add_kv_table(
    document: Document,
    rows: list[tuple[str, Any]],
    *,
    col_widths: tuple[float, float] = (4.0, 12.0),
) -> None:
    table = document.add_table(rows=len(rows), cols=2)
    table.style = "Light Grid Accent 1"
    for i, (k, v) in enumerate(rows):
        cells = table.rows[i].cells
        cells[0].text = "" if k is None else str(k)
        cells[1].text = "" if v is None else str(v)
        cells[0].width = Cm(col_widths[0])
        cells[1].width = Cm(col_widths[1])
        for cell in cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(10)


def _write_cover(
    document: Document,
    report: InspectionReport,
    task: InspectionTask | None,
    *,
    single_instance: tuple[str, int] | None = None,
) -> None:
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cover_title = "数据库巡检报告（单实例）" if single_instance else "数据库巡检报告"
    run = title.add_run(cover_title)
    run.font.size = Pt(28)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    sub = document.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = sub.add_run(report.report_code or f"REPORT-{report.id}")
    sub_run.font.size = Pt(16)
    sub_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    document.add_paragraph()
    document.add_paragraph()
    meta = document.add_table(rows=4, cols=2)
    meta.style = "Light Shading Accent 1"
    meta_rows = [
        ("任务名称", getattr(task, "task_name", "") if task else ""),
        ("报告编号", report.report_code or ""),
        ("生成时间", (report.generated_at or report.created_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")),
        ("规则引擎版本", report.rule_engine_version or InspectionEvaluatorService.RULE_ENGINE_VERSION),
    ]
    for i, (k, v) in enumerate(meta_rows):
        cells = meta.rows[i].cells
        cells[0].text = k
        cells[1].text = v
    document.add_paragraph()
    note = document.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.add_run(
        f"健康等级：{HEALTH_LEVEL_LABEL.get(report.health_level, report.health_level or '未知')}    "
        f"健康分数：{report.health_score if report.health_score is not None else 'N/A'}"
    ).bold = True


def _write_basic_info(
    document: Document,
    report: InspectionReport,
    task: InspectionTask | None,
    *,
    single_instance: tuple[str, int] | None = None,
) -> None:
    _add_heading(document, "基本信息", level=1)
    rows = [
        ("报告编号", report.report_code or ""),
        ("关联任务", getattr(task, "task_name", "") if task else ""),
        ("任务编号", getattr(task, "task_code", "") if task else ""),
        ("报告状态", REPORT_STATUS_LABEL.get(report.report_status, report.report_status)),
        ("生成原因", report.generated_reason or ""),
        ("导出范围", f"单实例 {single_instance[0]}:{single_instance[1]}" if single_instance else "全报告"),
        ("生成人", report.generated_by or ""),
        ("生成时间", _fmt_dt(report.generated_at)),
        ("规则引擎版本", report.rule_engine_version or ""),
        (
            "源数据哈希",
            (report.source_data_hash or "")[:16]
            + ("..." if report.source_data_hash and len(report.source_data_hash) > 16 else ""),
        ),
        ("源结果数", str(report.source_result_count or 0)),
        ("目标实例数", str(report.total_target_count or 0)),
    ]
    _add_kv_table(document, rows)


def _write_health_summary(
    document: Document,
    report: InspectionReport,
    instance_reports: list[InspectionInstanceReport],
) -> None:
    _add_heading(document, "健康摘要", level=1)
    rows = [
        ("整体健康等级", HEALTH_LEVEL_LABEL.get(report.health_level or "", report.health_level or "")),
        ("整体健康分数", f"{report.health_score:.2f}" if report.health_score is not None else "N/A"),
        ("健康实例", str(report.healthy_count or 0)),
        ("告警实例", str(report.warning_count or 0)),
        ("严重实例", str(report.critical_count or 0)),
        ("未知实例", str(report.unknown_count or 0)),
        ("未评估实例", str(report.not_assessed_count or 0)),
        ("缺失结果数", str(report.missing_result_count or 0)),
        ("采集失败总数", str(report.collection_failed_count or 0)),
    ]
    _add_kv_table(document, rows)
    document.add_paragraph()
    p = document.add_paragraph()
    p.add_run(
        f"巡检项分布 — 正常 {report.normal_item_count or 0}，"
        f"告警 {report.warning_item_count or 0}，"
        f"严重 {report.critical_item_count or 0}，"
        f"未知 {report.unknown_item_count or 0}"
    )


def _write_level_distribution(
    document: Document,
    instance_reports: list[InspectionInstanceReport],
) -> None:
    _add_heading(document, "等级分布", level=1)
    if not instance_reports:
        document.add_paragraph("无实例结果。")
        return
    table = document.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for i, h in enumerate(("实例 ID", "目标类型", "健康等级", "健康分数")):
        hdr[i].text = h
    for ir in instance_reports[:MAX_INSTANCES_IN_DOCX]:
        row = table.add_row().cells
        row[0].text = str(ir.target_id)
        row[1].text = ir.target_type
        row[2].text = HEALTH_LEVEL_LABEL.get(ir.health_level or "", ir.health_level or "")
        row[3].text = f"{ir.health_score:.2f}" if ir.health_score is not None else "N/A"
    if len(instance_reports) > MAX_INSTANCES_IN_DOCX:
        document.add_paragraph(
            f"… 仅导出前 {MAX_INSTANCES_IN_DOCX} 个实例，剩余 {len(instance_reports) - MAX_INSTANCES_IN_DOCX} 个已截断。"
        )


def _write_alerts(document: Document, results: list[InspectionResult]) -> None:
    _add_heading(document, "严重 / 告警清单", level=1)
    critical = [r for r in results if r.evaluation_status == "critical"]
    warning = [r for r in results if r.evaluation_status == "warning"]
    if not critical and not warning:
        document.add_paragraph("本次巡检无严重 / 告警项。")
        return
    for title, bucket in (("严重", critical), ("告警", warning)):
        if not bucket:
            continue
        _add_heading(document, f"{title}（{len(bucket)} 项）", level=2)
        table = document.add_table(rows=1, cols=4)
        table.style = "Light Grid Accent 1"
        for i, h in enumerate(("目标 ID", "巡检项", "执行状态", "说明")):
            table.rows[0].cells[i].text = h
        for r in bucket[:MAX_INSTANCES_IN_DOCX]:
            row = table.add_row().cells
            row[0].text = str(r.target_id)
            row[1].text = r.result_code
            row[2].text = r.execution_status
            row[3].text = _truncate(r.message or "", MESSAGE_PREVIEW)


def _write_instance_summary_table(
    document: Document,
    instance_reports: list[InspectionInstanceReport],
) -> None:
    _add_heading(document, "实例汇总表", level=1)
    if not instance_reports:
        document.add_paragraph("无实例报告。")
        return
    table = document.add_table(rows=1, cols=8)
    table.style = "Light Grid Accent 1"
    headers = ("目标 ID", "目标类型", "健康等级", "分数", "正常", "告警", "严重", "未知")
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    for ir in instance_reports:
        row = table.add_row().cells
        row[0].text = str(ir.target_id)
        row[1].text = ir.target_type
        row[2].text = HEALTH_LEVEL_LABEL.get(ir.health_level or "", ir.health_level or "")
        row[3].text = f"{ir.health_score:.2f}" if ir.health_score is not None else "N/A"
        row[4].text = str(ir.normal_count)
        row[5].text = str(ir.warning_count)
        row[6].text = str(ir.critical_count)
        row[7].text = str(ir.unknown_count)


def _write_instance_details(
    document: Document,
    instance_reports: list[InspectionInstanceReport],
    results: list[InspectionResult],
    task_items: list[InspectionTaskItem],
    task_targets: list[InspectionTaskTarget],
    *,
    include_raw_evidence: bool,
) -> None:
    _add_heading(document, "实例详情", level=1)
    items_by_id = {int(ti.id): ti for ti in task_items}
    targets_by_id = {int(tt.id): tt for tt in task_targets}
    results_by_target: dict[int, list[InspectionResult]] = {}
    for r in results:
        results_by_target.setdefault(int(r.task_target_id), []).append(r)

    sliced = instance_reports[:MAX_INSTANCES_IN_DOCX]
    for ir in sliced:
        target = targets_by_id.get(int(ir.task_target_id))
        title = (
            f"实例 {ir.target_id}（{ir.target_type}）— "
            f"{HEALTH_LEVEL_LABEL.get(ir.health_level or '', ir.health_level or '')}"
        )
        _add_heading(document, title, level=2)
        meta_rows = [
            ("实例名", getattr(target, "target_name_snapshot", "") if target else ""),
            ("主机", getattr(target, "host_snapshot", "") if target else ""),
            ("端口", str(getattr(target, "port_snapshot", "") or "") if target else ""),
            ("数据库类型", getattr(target, "db_type_code_snapshot", "") if target else ""),
            ("业务系统", getattr(target, "business_system_snapshot", "") if target else ""),
            ("站点", getattr(target, "site_snapshot", "") if target else ""),
            ("健康分数", f"{ir.health_score:.2f}" if ir.health_score is not None else "N/A"),
            ("缺失结果数", str(ir.missing_result_count or 0)),
        ]
        _add_kv_table(document, meta_rows)
        document.add_paragraph()

        bucket = results_by_target.get(int(ir.task_target_id), [])
        if not bucket:
            document.add_paragraph("无巡检结果。")
            continue
        table = document.add_table(rows=1, cols=5)
        table.style = "Light Grid Accent 1"
        for i, h in enumerate(("巡检项", "执行状态", "评估状态", "说明", "原始数据")):
            table.rows[0].cells[i].text = h
        for r in bucket:
            row = table.add_row().cells
            row[0].text = r.result_code
            row[1].text = r.execution_status
            row[2].text = EVAL_STATUS_LABEL.get(r.evaluation_status or "", r.evaluation_status or "")
            row[3].text = _truncate(r.message or "", MESSAGE_PREVIEW)
            if include_raw_evidence:
                evidence = r.evidence or {}
                findings = evidence.get("findings") or []
                rows_data = evidence.get("rows") or []
                preview = json.dumps(
                    {"findings": findings[:RAW_ROWS_PREVIEW], "rows": rows_data[:RAW_ROWS_PREVIEW]},
                    ensure_ascii=False,
                )
                row[4].text = _truncate(preview, MESSAGE_PREVIEW)
            else:
                row[4].text = "(需 admin 角色)"


def _write_appendix(
    document: Document,
    report: InspectionReport,
    task: InspectionTask | None,
    *,
    include_raw_evidence: bool,
) -> None:
    _add_heading(document, "附录 — 审计元数据", level=1)
    rows = [
        ("报告 ID", str(report.id)),
        ("报告编号", report.report_code or ""),
        ("任务 ID", str(report.task_id)),
        ("报告状态", report.report_status or ""),
        ("生成原因", report.generated_reason or ""),
        ("生成人", report.generated_by or ""),
        ("生成时间", _fmt_dt(report.generated_at)),
        ("规则引擎版本", report.rule_engine_version or ""),
        ("源数据哈希", report.source_data_hash or ""),
        ("源结果数", str(report.source_result_count or 0)),
        ("原始 evidence 已包含", "是" if include_raw_evidence else "否（需 admin）"),
    ]
    _add_kv_table(document, rows)


# ---------------------------------------------------------------------------
# Helpers (reused by inspection_service for hash)
# ---------------------------------------------------------------------------


def _fmt_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def stable_hash(payload: Any) -> str:
    """Plan §5.6: sort_keys canonical JSON → SHA-256."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
