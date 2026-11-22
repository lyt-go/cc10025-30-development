<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">数据资产与生命周期治理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向数据资产编目、冷热分层、生命周期管理、血缘追踪与合规治理的统一数据治理平台。</span>
        <span class="head-user">当前值班：数据工程组</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
const navItems = [{ label: "运营概览", path: "/" }, { label: "资产编目", path: "/asset_catalog" }, { label: "分层策略", path: "/tier_policy" }, { label: "血缘图谱", path: "/lineage_graph" }, { label: "保留规则", path: "/retention_rule" }, { label: "合规检查", path: "/compliance_check" }, { label: "冷存储管理", path: "/cold_storage" }, { label: "预热回迁", path: "/hot_prefetch" }, { label: "版本快照", path: "/version_snapshot" }, { label: "标签体系", path: "/label_tag" }, { label: "外部标签样本", path: "/external_label_sample" }, { label: "审计日志", path: "/audit_log" }, { label: "访问网关", path: "/access_gate" }, { label: "成本追踪", path: "/cost_tracker" }, { label: "Schema注册", path: "/schema_registry" }, { label: "分区规划", path: "/partition_plan" }, { label: "补数任务", path: "/backfill_job" }, { label: "质量报告", path: "/quality_report" }, { label: "回收清理", path: "/reclaim_job" }, { label: "变更通知", path: "/change_notice" }]
</script>
