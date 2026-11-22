"""compliance_check 领域服务：合规检查管理，检查数据资产合规性并生成审计日志和质量报告。

跨模块数据流：
    asset_catalog → compliance_check: 资产变更触发合规扫描
    external_label_sample → compliance_check: 已确认样本支撑分层扫描
    compliance_check → audit_log: 检查结果写入审计日志
    compliance_check → quality_report: 合规结果纳入质量报告
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "quality")
SCAN_REPORT_PREFIX = "scan_report_"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


class ComplianceCheckService(BaseModuleService):
    MODULE = "compliance_check"
    ENTITY = "合规规则"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["规则编号", "检查维度", "合规标准", "扫描范围", "阻断阈值", "修复建议", "检查频率", "规则版本"]
    REQUIRED_FIELDS = ["规则编号", "检查维度", "合规标准"]
    STATUS_ORDER = ["草稿", "待校验", "已生效", "已停用"]
    ACTION_RULES = {"提交校验": "待校验", "标记生效": "已生效", "停用规则": "已停用"}
    NEGATIVE_ACTIONS = ["停用规则"]

    def __init__(self):
        super().__init__()
        os.makedirs(DATA_DIR, exist_ok=True)
        self._scan_reports: dict[str, dict[str, Any]] = {}
        self._load_scan_reports()

    def run_check(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """执行合规检查：扫描关联资产并生成检查结果。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在"

        dimension = str(entry.get("检查维度", ""))
        standard = str(entry.get("合规标准", ""))
        scope = str(entry.get("扫描范围", ""))

        # 模拟合规扫描：统计关联的资产模块中的pending和abnormal状态
        checked_count = 0
        violations = 0
        for module_name in store.module_names():
            for row in store.rows(module_name):
                if scope and str(row.get("所属域", "") + str(row.get("关联资产", ""))).find(scope[:3]) >= 0:
                    checked_count += 1
                    if row.get("abnormal"):
                        violations += 1
                checked_count += 1
                if row.get("abnormal"):
                    violations += 1

        passed = violations == 0

        # 写入合规检查结果
        result = {
            "rule_id": str(entry.get("规则编号", "")),
            "dimension": dimension,
            "standard": standard,
            "scope": scope,
            "checked_count": checked_count,
            "violations": violations,
            "passed": passed,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_check_result(str(entry.get("规则编号", "")), result)

        # 写入审计日志
        self._write_audit_entry(
            entity="合规检查",
            action="执行扫描",
            target_id=str(entry.get("规则编号", "")),
            detail=f"合规检查 {dimension}: {violations} / {checked_count} 违规",
        )

        # 更新质量报告
        self._update_quality_report(dimension, checked_count, violations)

        message = f"合规检查完成：{checked_count}项，{violations}违规{'，通过' if passed else '，不通过'}"
        return entry, message

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action == "标记生效":
            return self.run_check(entry_id)
        if action == "分层扫描":
            report, message = self.run_stratified_scan(entry_id)
            return (store.find(self.MODULE, entry_id) if report is not None else None), message
        return super().run_action(entry_id, action)

    # ---------------------------------------------------------- 分层扫描

    def run_stratified_scan(
        self,
        entry_id: int,
        quota: int = 2,
        source_file: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """按外部标签样本清单实际选择分区并执行分层扫描。

        取样口径：一律按标签来源确认的新归属组分层轮取，不延续文件旧组；
        名额有限时优先覆盖不同归属组。抽中的原始行号、取样分组与未核行
        一并落库为扫描报告，未抽中的分区保留跳过原因（名额/归属未确认）。
        """
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在"
        quota = _to_int(quota, default=0)
        if quota < 1:
            return None, "本轮名额必须为正整数"

        scope = (source_file or "").strip() or str(entry.get("扫描范围", "")).strip()
        samples = list(store.rows("external_label_sample"))
        if scope:
            samples = [row for row in samples if str(row.get("来源文件", "")) == scope]
        if not samples:
            target = f"来源文件「{scope}」" if scope else "外部标签样本清单"
            return None, f"{target}没有可扫描的样本，请先上传样本文件并导入"

        confirmed = [row for row in samples if row.get("status") in ("已确认", "已跳过")]
        unverified = [row for row in samples if row.get("status") == "待核"]
        if not confirmed:
            return None, "样本全部待核，归属未确认，无法执行分层扫描"

        # 按新归属组分层：组内按优先级从高到低，组间轮取直到名额用完
        strata: dict[str, list[dict[str, Any]]] = {}
        for row in confirmed:
            strata.setdefault(str(row.get("归属组") or "未分组"), []).append(row)
        for rows in strata.values():
            rows.sort(key=lambda row: (-_to_int(row.get("优先级")), _to_int(row.get("文件行号"))))
        ordered_strata = sorted(
            strata.items(),
            key=lambda item: (-_to_int(item[1][0].get("优先级")), item[0]),
        )
        selected: list[dict[str, Any]] = []
        depth = 0
        while len(selected) < quota:
            progressed = False
            for _group, rows in ordered_strata:
                if len(selected) >= quota:
                    break
                if depth < len(rows):
                    selected.append(rows[depth])
                    progressed = True
            if not progressed:
                break
            depth += 1

        report_id = self._next_scan_report_id()
        scanned_at = datetime.now(timezone.utc).isoformat()
        selected_codes = {str(row.get("样本编号")) for row in selected}

        skipped: list[dict[str, Any]] = []
        for row in selected:
            row["status"] = "已扫描"
            row["pending"] = False
            row["扫描批次"] = report_id
            row["跳过原因"] = ""
        for row in confirmed:
            if str(row.get("样本编号")) not in selected_codes:
                row["status"] = "已跳过"
                row["pending"] = True
                row["跳过原因"] = "名额不足"
                skipped.append(self._skipped_row(row, "名额不足"))
        for row in unverified:
            row["跳过原因"] = "归属未确认"
            skipped.append(self._skipped_row(row, "归属未确认"))

        # 口径冲突：同一文件旧组被标签来源拆成多个新归属组
        file_groups: dict[str, set[str]] = {}
        for row in confirmed:
            file_groups.setdefault(str(row.get("文件分组", "")), set()).add(str(row.get("归属组", "")))
        conflict_groups = {
            group: sorted(targets) for group, targets in file_groups.items() if len(targets) > 1
        }

        report = {
            "report_id": report_id,
            "rule_id": str(entry.get("规则编号", "")),
            "source_file": scope,
            "quota": quota,
            "sampling_mode": "按标签来源新归属组分层取样",
            "conflict_groups": conflict_groups,
            "groups_used": sorted({str(row.get("归属组", "")) for row in selected}),
            "sampled": [
                {
                    "样本编号": str(row.get("样本编号", "")),
                    "文件行号": _to_int(row.get("文件行号")),
                    "分区键": str(row.get("分区键", "")),
                    "文件分组": str(row.get("文件分组", "")),
                    "取样分组": str(row.get("归属组", "")),
                    "标签版本": str(row.get("标签版本", "")),
                    "原始行": str(row.get("原始行", "")),
                }
                for row in selected
            ],
            "sampled_line_numbers": [_to_int(row.get("文件行号")) for row in selected],
            "unverified": [
                {
                    "样本编号": str(row.get("样本编号", "")),
                    "文件行号": _to_int(row.get("文件行号")),
                    "分区键": str(row.get("分区键", "")),
                    "核验说明": str(row.get("核验说明", "")),
                    "原始行": str(row.get("原始行", "")),
                }
                for row in unverified
            ],
            "skipped": skipped,
            "file_lines": [
                {
                    "来源文件": str(row.get("来源文件", "")),
                    "文件行号": _to_int(row.get("文件行号")),
                    "原始行": str(row.get("原始行", "")),
                }
                for row in selected
            ],
            "scanned_at": scanned_at,
        }
        self._scan_reports[report_id] = report
        self._write_scan_report(report)

        self._write_audit_entry(
            entity="合规检查",
            action="分层扫描",
            target_id=str(entry.get("规则编号", "")),
            detail=(
                f"分层扫描 {scope or '全部样本'}：名额 {quota}，抽中 {len(selected)} 行"
                f"（行号 {'、'.join(str(n) for n in report['sampled_line_numbers'])}），"
                f"覆盖分组 {'、'.join(report['groups_used'])}，未核 {len(unverified)} 行"
            ),
        )
        self._update_quality_report(
            "外部标签样本分层扫描", len(confirmed) + len(unverified), len(unverified))

        message = (
            f"分层扫描完成：名额 {quota}，抽中 {len(selected)} 个分区，"
            f"覆盖 {len(report['groups_used'])} 个归属组（{'、'.join(report['groups_used'])}），"
            f"未核 {len(unverified)} 行已保留待核"
        )
        return report, message

    def list_scan_reports(self) -> list[dict[str, Any]]:
        """扫描报告索引：供检查员选择要重新打开的报告。"""
        summaries = []
        for report in sorted(self._scan_reports.values(), key=lambda item: item["report_id"]):
            summaries.append({
                "report_id": report["report_id"],
                "rule_id": report["rule_id"],
                "source_file": report["source_file"],
                "quota": report["quota"],
                "sampling_mode": report["sampling_mode"],
                "groups_used": report["groups_used"],
                "sampled_count": len(report["sampled"]),
                "sampled_line_numbers": report["sampled_line_numbers"],
                "unverified_count": len(report["unverified"]),
                "skipped_count": len(report["skipped"]),
                "scanned_at": report["scanned_at"],
            })
        return summaries

    def get_scan_report(self, report_id: str) -> dict[str, Any] | None:
        """重新打开扫描报告：复核实际读取的文件行。"""
        return self._scan_reports.get(report_id)

    @staticmethod
    def _skipped_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "样本编号": str(row.get("样本编号", "")),
            "文件行号": _to_int(row.get("文件行号")),
            "分区键": str(row.get("分区键", "")),
            "跳过原因": reason,
        }

    def _next_scan_report_id(self) -> str:
        seq = len(self._scan_reports) + 1
        while f"SCAN-{seq:04d}" in self._scan_reports:
            seq += 1
        return f"SCAN-{seq:04d}"

    def _write_scan_report(self, report: dict[str, Any]) -> None:
        path = os.path.join(DATA_DIR, f"{SCAN_REPORT_PREFIX}{report['report_id']}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, default=str)

    def _load_scan_reports(self) -> None:
        if not os.path.isdir(DATA_DIR):
            return
        for name in sorted(os.listdir(DATA_DIR)):
            if not (name.startswith(SCAN_REPORT_PREFIX) and name.endswith(".json")):
                continue
            path = os.path.join(DATA_DIR, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    report = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            report_id = str(report.get("report_id", ""))
            if report_id:
                self._scan_reports[report_id] = report

    def _write_check_result(self, rule_id: str, result: dict[str, Any]) -> None:
        filename = f"compliance_check_{rule_id}.json"
        path = os.path.join(DATA_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    def _write_audit_entry(self, entity: str, action: str, target_id: str,
                           detail: str) -> None:
        audit_rows = store.rows("audit_log")
        next_id = max((int(r.get("id", 0)) for r in audit_rows), default=0) + 1
        entry = {
            "id": next_id,
            "status": "已记录",
            "pending": False,
            "abnormal": False,
            "记录编号": f"AUDI-{next_id:04d}",
            "操作主体": entity,
            "操作类型": action,
            "操作对象": target_id,
            "操作时间": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "影响范围": detail,
            "审计摘要": detail,
            "归档状态": "已记录",
        }
        audit_rows.append(entry)

    def _update_quality_report(self, dimension: str, total: int, violations: int) -> None:
        quality_rows = store.rows("quality_report")
        next_id = max((int(r.get("id", 0)) for r in quality_rows), default=0) + 1
        completeness = "高" if total > 0 and violations / total < 0.1 else "中" if violations > 0 else "高"
        report = {
            "id": next_id,
            "status": "已生成",
            "pending": False,
            "abnormal": violations > 0,
            "报告编号": f"QUAL-{next_id:04d}",
            "关联资产": "全量资产",
            "检核时间": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "完整性": completeness,
            "准确性": f"合规率:{1 - violations/max(total,1):.1%}",
            "及时性": "实时",
            "异常数": str(violations),
            "趋势方向": "恶化" if violations > 0 else "稳定",
        }
        quality_rows.append(report)