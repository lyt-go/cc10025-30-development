"""外部标签样本清单 + 合规分层扫描场景测试。

场景还原：
    外部检查员的抽样文件把同一旧组的四个有证分区归为一组（旧组G），
    标签来源已把它们拆成 归属组A / 归属组B 两个新归属组，按旧组和
    按新组取样存在口径冲突。检查员本轮最多查两个分区（名额=2），
    并沿用相同的文件行号复核覆盖。

步骤：
    1. 登记分区规划与标签来源（四个有证分区，两个新归属组）。
    2. 上传样本文件并导入：四条已确认（两条最高优先级属 A，另两条属 B），
       外加一条无法核对的分区（分区匹配失败，保留待核）。
    3. 按两个名额提交实际扫描，核对是延续旧组抽样还是覆盖两个确认的新组。
    4. 重新打开报告，复核实际读取的文件行。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.store import store
from app.services import service_for

DATA_ROOT = os.path.join(os.path.dirname(__file__), "app", "data")
RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

passed = 0
failed = 0

SOURCE_FILE = "inspector_sample_2026-11-22.csv"
LABEL_SOURCE = "外部审计标签源"
LABEL_VERSION = "v2026.11"
OLD_GROUP = "旧组G"

# 四个有证分区：01/02 被标签来源拆入归属组A，03/04 拆入归属组B
PARTITIONS = ["dt=2026-11-01", "dt=2026-11-02", "dt=2026-11-03", "dt=2026-11-04"]
NEW_GROUP_OF = {
    "dt=2026-11-01": "归属组A",
    "dt=2026-11-02": "归属组A",
    "dt=2026-11-03": "归属组B",
    "dt=2026-11-04": "归属组B",
}

# 抽样文件：两条最高优先级（100/90）都在归属组A，另两条在归属组B，
# 第 6 行的分区在分区规划中不存在，无法核对
SAMPLE_CSV = "\n".join([
    "分区键,文件分组,标签来源,优先级",
    f"dt=2026-11-01,{OLD_GROUP},{LABEL_SOURCE},100",
    f"dt=2026-11-02,{OLD_GROUP},{LABEL_SOURCE},90",
    f"dt=2026-11-03,{OLD_GROUP},{LABEL_SOURCE},80",
    f"dt=2026-11-04,{OLD_GROUP},{LABEL_SOURCE},70",
    f"dt=2026-11-99,{OLD_GROUP},{LABEL_SOURCE},60",
])


def check(desc, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  {GREEN}PASS{RESET} {desc}")
        passed += 1
    else:
        print(f"  {RED}FAIL{RESET} {desc} {detail}")
        failed += 1
        return False
    return True


def setup_registry():
    """登记四个有证分区与对应的已生效标签（两个新归属组）。"""
    print("\n=== 准备：分区规划 + 标签来源（旧组拆分为 A/B 两个新归属组） ===")
    plan_svc = service_for("partition_plan")
    label_svc = service_for("label_tag")

    for index, partition_key in enumerate(PARTITIONS, start=1):
        plan, missing = plan_svc.create_entry({
            "方案编号": f"PART-9{index:03d}",
            "关联资产": "外部审计资产",
            "分区键": partition_key,
            "分区粒度": "按日",
            "预计分区数": "1",
            "维护窗口": "夜间",
            "合并策略": "不合并",
            "方案版本": "v1",
        })
        check(f"分区方案登记成功 {partition_key}", plan is not None, str(missing))
        plan_svc.run_action(plan["id"], "提交校验")
        plan, msg = plan_svc.run_action(plan["id"], "标记生效")
        check(f"分区已生效（有证）{partition_key}", plan is not None and plan["status"] == "已生效", msg)

        label, missing = label_svc.create_entry({
            "标签编号": f"LABE-9{index:03d}",
            "标签名称": NEW_GROUP_OF[partition_key],
            "标签类型": "归属分组",
            "关联资产": partition_key,
            "置信度": "0.99",
            "标签来源": LABEL_SOURCE,
            "生效时间": "2026-11-22",
            "标签版本": LABEL_VERSION,
        })
        check(f"标签登记成功 {partition_key} → {NEW_GROUP_OF[partition_key]}",
              label is not None, str(missing))
        label, msg = label_svc.run_action(label["id"], "确认生效")
        check(f"标签已生效 {partition_key}", label is not None and label["status"] == "已生效", msg)


def test_import_sample_file():
    """上传样本文件并导入，生成可逐行核验的外部标签样本清单。"""
    print("\n=== 步骤1：上传样本文件并按分区键与标签来源导入 ===")
    svc = service_for("external_label_sample")

    stats, msg = svc.import_file(SOURCE_FILE, SAMPLE_CSV)
    check("样本文件导入成功", stats is not None, msg)
    check("导入行数=5", stats and stats["导入行数"] == 5, str(stats))
    check("已确认=4", stats and stats["已确认"] == 4, str(stats))
    check("待核=1", stats and stats["待核"] == 1, str(stats))
    check("口径冲突文件分组=旧组G",
          stats and stats["口径冲突文件分组"] == [OLD_GROUP], str(stats))

    rows = [row for row in store.rows("external_label_sample")
            if row.get("来源文件") == SOURCE_FILE]
    check("清单可逐行核验（5 行全部在册）", len(rows) == 5, f"实际 {len(rows)} 行")

    confirmed = [row for row in rows if row.get("status") == "已确认"]
    check("四条已确认样本", len(confirmed) == 4)

    # 已确认样本关联文件原行与实际使用的标签版本
    for row in confirmed:
        check(f"行{row['文件行号']} 关联标签版本 {LABEL_VERSION}",
              row.get("标签版本") == LABEL_VERSION, str(row.get("标签版本")))
    by_partition = {row["分区键"]: row for row in confirmed}
    for partition_key, group in NEW_GROUP_OF.items():
        row = by_partition.get(partition_key)
        check(f"{partition_key} 归属 {group}",
              row is not None and row.get("归属组") == group,
              str(row and row.get("归属组")))
    check("已确认样本标注口径冲突",
          all(row.get("口径冲突") == "是" for row in confirmed))

    # 分区匹配失败的行保留待核，不计入合规覆盖
    pending = [row for row in rows if row.get("status") == "待核"]
    check("一条待核行", len(pending) == 1)
    if pending:
        row = pending[0]
        check("待核行是第 6 行（无法核对的分区）", row.get("文件行号") == 6,
              f"实际行号 {row.get('文件行号')}")
        check("待核行分区键 dt=2026-11-99", row.get("分区键") == "dt=2026-11-99")
        check("待核行注明分区匹配失败", "分区匹配失败" in str(row.get("核验说明", "")),
              str(row.get("核验说明")))
        check("待核行无归属组与标签版本",
              not row.get("归属组") and not row.get("标签版本"))


def test_stratified_scan():
    """按两个名额提交实际扫描，核对分层口径与落库内容。"""
    print("\n=== 步骤2：按两个名额提交分层扫描 ===")
    svc = service_for("compliance_check")

    rule, missing = svc.create_entry({
        "规则编号": "COMP-9001",
        "检查维度": "外部标签样本",
        "合规标准": "分层覆盖",
        "扫描范围": SOURCE_FILE,
        "阻断阈值": "0",
        "修复建议": "补核",
        "检查频率": "本轮",
        "规则版本": "v1",
    })
    check("合规规则登记成功", rule is not None, str(missing))

    report, msg = svc.run_stratified_scan(rule["id"], quota=2)
    check("分层扫描执行成功", report is not None, msg)
    if report is None:
        return

    check("本轮名额=2", report["quota"] == 2)
    check("抽中 2 个分区", len(report["sampled"]) == 2, str(report["sampled"]))

    # 核对口径：覆盖两个确认的新组，而不是延续旧组抽最高优先级的两条（都在A）
    check("覆盖两个确认的新组 A+B",
          report["groups_used"] == ["归属组A", "归属组B"], str(report["groups_used"]))
    check("不是旧组口径的旧组G 整组", report["groups_used"] != [OLD_GROUP])
    sampled_lines = sorted(report["sampled_line_numbers"])
    check("抽中行号为 2 和 4（A 组最高优先级 + B 组最高优先级）",
          sampled_lines == [2, 4], str(sampled_lines))
    check("若延续旧组抽样会抽中 2 和 3，实际未发生", sampled_lines != [2, 3])
    check("报告记录口径冲突", report["conflict_groups"].get(OLD_GROUP) == ["归属组A", "归属组B"],
          str(report["conflict_groups"]))

    # 抽中的样本关联文件原行与实际标签版本
    for item in report["sampled"]:
        check(f"抽中行{item['文件行号']} 标签版本 {LABEL_VERSION}",
              item["标签版本"] == LABEL_VERSION)
        check(f"抽中行{item['文件行号']} 保留文件分组 {OLD_GROUP}",
              item["文件分组"] == OLD_GROUP)

    # 未抽中的分区：两条因名额跳过，一条因归属未确认保留待核
    skipped = report["skipped"]
    quota_skipped = [row for row in skipped if row["跳过原因"] == "名额不足"]
    unconfirmed_skipped = [row for row in skipped if row["跳过原因"] == "归属未确认"]
    check("两条已确认分区因名额不足跳过", len(quota_skipped) == 2, str(skipped))
    check("一条分区因归属未确认跳过", len(unconfirmed_skipped) == 1, str(skipped))
    check("未核行落库（行号 6）",
          [row["文件行号"] for row in report["unverified"]] == [6],
          str(report["unverified"]))

    # 样本清单状态同步：已扫描 / 已跳过 / 待核
    rows = [row for row in store.rows("external_label_sample")
            if row.get("来源文件") == SOURCE_FILE]
    scanned = [row for row in rows if row.get("status") == "已扫描"]
    skipped_rows = [row for row in rows if row.get("status") == "已跳过"]
    pending_rows = [row for row in rows if row.get("status") == "待核"]
    check("清单中 2 行已扫描", len(scanned) == 2)
    check("已扫描行挂扫描批次", all(row.get("扫描批次") == report["report_id"] for row in scanned))
    check("清单中 2 行已跳过（名额不足）",
          len(skipped_rows) == 2 and all(row.get("跳过原因") == "名额不足" for row in skipped_rows))
    check("待核行不计入合规覆盖（仍待核）",
          len(pending_rows) == 1 and pending_rows[0].get("跳过原因") == "归属未确认")

    # 落库：报告文件与审计日志
    report_file = os.path.join(DATA_ROOT, "quality", f"scan_report_{report['report_id']}.json")
    check("扫描报告已落库", os.path.exists(report_file), report_file)
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as handle:
            persisted = json.load(handle)
        check("落库报告含抽中行号", persisted.get("sampled_line_numbers") == report["sampled_line_numbers"])
        check("落库报告含取样分组", persisted.get("groups_used") == report["groups_used"])
        check("落库报告含未核行", len(persisted.get("unverified", [])) == 1)
    audit_rows = [row for row in store.rows("audit_log") if row.get("操作类型") == "分层扫描"]
    check("分层扫描已写审计日志", len(audit_rows) >= 1)

    return report


def test_reopen_report(report):
    """重新打开报告，复核实际读取的文件行。"""
    print("\n=== 步骤3：重新打开报告复核文件行 ===")
    if report is None:
        check("存在可重新打开的报告", False, "上一步未生成报告")
        return
    svc = service_for("compliance_check")

    summaries = svc.list_scan_reports()
    check("报告索引可查询", any(item["report_id"] == report["report_id"] for item in summaries))

    reopened = svc.get_scan_report(report["report_id"])
    check("报告重新打开成功", reopened is not None)
    if reopened is None:
        return

    csv_lines = SAMPLE_CSV.splitlines()
    file_lines = reopened["file_lines"]
    check("实际读取的文件行数=2", len(file_lines) == 2, str(file_lines))
    for item in file_lines:
        line_no = item["文件行号"]
        check(f"复核行 {line_no}：与抽样文件原行一致",
              item["原始行"] == csv_lines[line_no - 1],
              f"报告={item['原始行']!r} 文件={csv_lines[line_no - 1]!r}")
        check(f"复核行 {line_no} 来源文件正确", item["来源文件"] == SOURCE_FILE)
    check("沿用相同文件行号复核覆盖（2、4）",
          sorted(item["文件行号"] for item in file_lines) == [2, 4])


def test_unscoped_rule_rejected():
    """扫描范围对不上样本来源时，不能误扫其他文件。"""
    print("\n=== 兜底：扫描范围不匹配时不抽样 ===")
    svc = service_for("compliance_check")
    rule, _ = svc.create_entry({
        "规则编号": "COMP-9002",
        "检查维度": "外部标签样本",
        "合规标准": "分层覆盖",
        "扫描范围": "不存在的文件.csv",
        "阻断阈值": "0",
        "修复建议": "补核",
        "检查频率": "本轮",
        "规则版本": "v1",
    })
    report, msg = svc.run_stratified_scan(rule["id"], quota=2)
    check("无匹配样本时拒绝扫描", report is None, msg)


if __name__ == "__main__":
    print("=" * 60)
    print("外部标签样本清单 + 合规分层扫描 场景测试")
    print("=" * 60)

    setup_registry()
    test_import_sample_file()
    report = test_stratified_scan()
    test_reopen_report(report)
    test_unscoped_rule_rejected()

    print(f"\n{'=' * 60}")
    print(f"结果: {GREEN}{passed} 通过{RESET} / {RED}{failed} 失败{RESET} / "
          f"{passed + failed} 总计")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
