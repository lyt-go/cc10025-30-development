"""外部标签样本导入与合规分层扫描的专用接口。

与通用资源路由并存：通用路由负责清单的查询/登记/动作，
这里承载带文件内容与扫描参数的专用入口。注册顺序必须在通用
资源路由之前，否则 /api/compliance_check/scan_reports 会被
/{module}/{entry_id} 抢先匹配。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ActionResult, ImportPayload, ScanPayload
from app.services import service_for

router = APIRouter(prefix="/api", tags=["外部标签样本与分层扫描"])


@router.post("/external_label_sample/import", response_model=ActionResult)
def import_sample_file(payload: ImportPayload) -> ActionResult:
    """上传样本文件并按分区键与标签来源导入，生成可逐行核验的清单。"""
    service = service_for("external_label_sample")
    stats, message = service.import_file(payload.filename, payload.content)
    if stats is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=stats)


@router.get("/compliance_check/scan_reports", response_model=dict)
def list_scan_reports() -> dict:
    """扫描报告索引：本轮抽中情况与跳过原因可在此检索。"""
    service = service_for("compliance_check")
    items = service.list_scan_reports()
    return {"items": items, "total": len(items)}


@router.get("/compliance_check/scan_reports/{report_id}", response_model=dict)
def get_scan_report(report_id: str) -> dict:
    """重新打开扫描报告，复核实际读取的文件行。"""
    service = service_for("compliance_check")
    report = service.get_scan_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"扫描报告 {report_id} 不存在")
    return report


@router.post("/compliance_check/{entry_id}/stratified_scan", response_model=ActionResult)
def run_stratified_scan(entry_id: int, payload: ScanPayload) -> ActionResult:
    """按外部标签样本清单实际选择分区并提交本轮分层扫描。"""
    service = service_for("compliance_check")
    report, message = service.run_stratified_scan(
        entry_id, quota=payload.quota, source_file=payload.source_file)
    return ActionResult(ok=report is not None, message=message, entry=report)
