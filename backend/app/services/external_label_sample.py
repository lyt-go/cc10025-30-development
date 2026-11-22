"""external_label_sample 领域服务：外部标签样本清单。

外部检查员抽样文件缺少可按实际标签来源核对的入口，本模块提供
"上传样本文件 → 按分区键与标签来源导入 → 生成可逐行核验的样本清单"。

跨模块数据流：
    partition_plan → external_label_sample: 按分区键核对分区是否真实存在
    label_tag → external_label_sample: 按标签来源确认实际归属组与标签版本
    external_label_sample → compliance_check: 已确认样本支撑合规分层扫描

口径冲突：抽样文件按"文件分组"（旧组）归类，标签来源可能已把同一旧组
拆成多个新归属组；导入时逐行标注口径冲突，取样一律按新归属组分层。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


class ExternalLabelSampleService(BaseModuleService):
    MODULE = "external_label_sample"
    ENTITY = "标签样本"
    OPERATION_TERM = "核验"
    LIST_FIELDS = ["样本编号", "来源文件", "文件行号", "分区键", "文件分组", "标签来源", "归属组", "标签版本"]
    REQUIRED_FIELDS = ["样本编号", "分区键", "标签来源"]
    STATUS_ORDER = ["待核", "已确认", "已扫描", "已跳过"]
    ACTION_RULES = {"退回待核": "待核"}
    NEGATIVE_ACTIONS = ["退回待核"]

    # 样本文件（CSV）按表头识别的列；分区键与标签来源为导入核对的最小入口
    IMPORT_COLUMNS = ["分区键", "文件分组", "标签来源", "优先级"]

    # ------------------------------------------------------------------ 导入

    def import_file(self, filename: str, content: str) -> tuple[dict[str, Any] | None, str]:
        """上传样本文件并按分区键与标签来源逐行导入，生成可逐行核验的清单。

        返回 (导入统计, 提示消息)；任一行核对失败不会中断导入，
        失败行以"待核"状态保留，不计入合规覆盖。
        """
        filename = (filename or "").strip()
        if not filename:
            return None, "缺少来源文件名"
        content = (content or "").lstrip("\ufeff")
        if not content.strip():
            return None, f"样本文件 {filename} 为空"

        raw_lines = content.splitlines()
        reader = csv.reader(io.StringIO(content))
        header: list[str] | None = None
        pending_rows: list[tuple[int, list[str]]] = []
        for record in reader:
            if not any(cell.strip() for cell in record):
                continue  # 空行不计入样本，但物理行号已被 reader.line_num 消耗
            if header is None:
                header = [cell.strip() for cell in record]
                continue
            pending_rows.append((reader.line_num, record))

        if header is None:
            return None, f"样本文件 {filename} 缺少表头"
        missing = [col for col in ("分区键", "标签来源") if col not in header]
        if missing:
            return None, f"样本文件缺少必需列：{'、'.join(missing)}"
        if not pending_rows:
            return None, f"样本文件 {filename} 没有数据行"

        def cell(record: list[str], column: str) -> str:
            if column not in header:
                return ""
            index = header.index(column)
            return record[index].strip() if index < len(record) else ""

        rows = store.rows(self.MODULE)
        next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        seq = self._next_sample_seq()
        imported: list[dict[str, Any]] = []
        for line_no, record in pending_rows:
            raw_line = raw_lines[line_no - 1] if 0 < line_no <= len(raw_lines) else ""
            entry = {
                "id": next_id,
                "样本编号": f"EXLS-{seq:04d}",
                "来源文件": filename,
                "文件行号": line_no,
                "分区键": cell(record, "分区键"),
                "文件分组": cell(record, "文件分组"),
                "标签来源": cell(record, "标签来源"),
                "优先级": _to_int(cell(record, "优先级")),
                "原始行": raw_line,
                "归属组": "",
                "标签版本": "",
                "核验说明": "",
                "口径冲突": "否",
                "跳过原因": "",
                "扫描批次": "",
                "status": "待核",
                "pending": True,
                "abnormal": False,
            }
            self._verify_entry(entry)
            rows.append(entry)
            imported.append(entry)
            next_id += 1
            seq += 1

        conflicts = self._mark_conflicts(filename)
        confirmed = sum(1 for row in imported if row.get("status") == "已确认")
        pending = len(imported) - confirmed
        stats = {
            "来源文件": filename,
            "导入行数": len(imported),
            "已确认": confirmed,
            "待核": pending,
            "口径冲突文件分组": sorted(conflicts),
        }
        message = (
            f"已导入 {filename}：{len(imported)} 行，已确认 {confirmed} 行，待核 {pending} 行"
        )
        if conflicts:
            message += f"；文件分组 {'、'.join(sorted(conflicts))} 与标签来源口径冲突，取样按新归属组分层"
        return stats, message

    # ------------------------------------------------------------------ 核验

    def recheck_entry(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """重新核验单条样本：按当前分区规划与标签来源重算归属。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        self._verify_entry(entry)
        self._mark_conflicts(str(entry.get("来源文件", "")))
        if entry.get("status") == "已确认":
            return entry, f"{self.ENTITY} {entry.get('样本编号')} 已确认归属 {entry.get('归属组')}"
        return entry, f"{self.ENTITY} {entry.get('样本编号')} 仍待核：{entry.get('核验说明')}"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action == "重新核验":
            return self.recheck_entry(entry_id)
        return super().run_action(entry_id, action)

    def _verify_entry(self, entry: dict[str, Any]) -> None:
        """按分区键与标签来源核对单条样本，写入归属组与实际标签版本。"""
        partition_key = str(entry.get("分区键", "")).strip()
        source = str(entry.get("标签来源", "")).strip()
        entry["归属组"] = ""
        entry["标签版本"] = ""
        entry["扫描批次"] = ""
        entry["跳过原因"] = ""

        if not partition_key:
            self._mark_pending(entry, "分区匹配失败：分区键为空")
            return
        partition = self._match_partition(partition_key)
        if partition is None:
            self._mark_pending(entry, "分区匹配失败：分区规划中不存在该分区键")
            return
        label = self._match_label(partition_key, source)
        if label is None:
            self._mark_pending(entry, "标签来源未确认：无已生效标签可核对归属")
            return

        entry["status"] = "已确认"
        entry["pending"] = True  # 已确认但尚未被扫描覆盖，仍待检查员抽取
        entry["abnormal"] = False
        entry["归属组"] = str(label.get("标签名称", ""))
        entry["标签版本"] = str(label.get("标签版本", ""))
        entry["核验说明"] = (
            f"已按标签来源确认归属（分区方案 {partition.get('方案编号', '')}，"
            f"标签 {label.get('标签编号', '')}）"
        )

    def _mark_pending(self, entry: dict[str, Any], reason: str) -> None:
        entry["status"] = "待核"
        entry["pending"] = True
        entry["abnormal"] = True
        entry["核验说明"] = reason

    @staticmethod
    def _match_partition(partition_key: str) -> dict[str, Any] | None:
        for row in store.rows("partition_plan"):
            if str(row.get("分区键", "")) == partition_key and row.get("status") != "已停用":
                return row
        return None

    @staticmethod
    def _match_label(partition_key: str, source: str) -> dict[str, Any] | None:
        for row in store.rows("label_tag"):
            if (
                str(row.get("关联资产", "")) == partition_key
                and str(row.get("标签来源", "")) == source
                and row.get("status") == "已生效"
            ):
                return row
        return None

    def _mark_conflicts(self, filename: str) -> set[str]:
        """标注口径冲突：同一文件分组被标签来源拆成多个新归属组。"""
        rows = [
            row for row in store.rows(self.MODULE)
            if row.get("来源文件") == filename and row.get("status") in ("已确认", "已扫描", "已跳过")
        ]
        by_file_group: dict[str, set[str]] = {}
        for row in rows:
            by_file_group.setdefault(str(row.get("文件分组", "")), set()).add(str(row.get("归属组", "")))
        conflicts = {group for group, targets in by_file_group.items() if len(targets) > 1}
        for row in rows:
            in_conflict = str(row.get("文件分组", "")) in conflicts
            row["口径冲突"] = "是" if in_conflict else "否"
        return conflicts

    def _next_sample_seq(self) -> int:
        seq = 1
        for row in store.rows(self.MODULE):
            code = str(row.get("样本编号", ""))
            if code.startswith("EXLS-"):
                seq = max(seq, _to_int(code[5:]) + 1)
        return seq

    def domain_snapshot(self) -> dict[str, Any]:
        snapshot = super().domain_snapshot()
        rows = store.rows(self.MODULE)
        snapshot["conflict_rows"] = sum(1 for row in rows if row.get("口径冲突") == "是")
        snapshot["sources"] = sorted({str(row.get("来源文件", "")) for row in rows if row.get("来源文件")})
        return snapshot
