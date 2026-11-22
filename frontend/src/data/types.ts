/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
  entry?: Record<string, unknown> | null
}

export type ScanReportSummary = {
  report_id: string
  rule_id: string
  source_file: string
  quota: number
  sampling_mode: string
  groups_used: string[]
  sampled_count: number
  sampled_line_numbers: number[]
  unverified_count: number
  skipped_count: number
  scanned_at: string
}

export type ScanReport = ScanReportSummary & {
  conflict_groups: Record<string, string[]>
  sampled: {
    样本编号: string
    文件行号: number
    分区键: string
    文件分组: string
    取样分组: string
    标签版本: string
    原始行: string
  }[]
  unverified: {
    样本编号: string
    文件行号: number
    分区键: string
    核验说明: string
    原始行: string
  }[]
  skipped: {
    样本编号: string
    文件行号: number
    分区键: string
    跳过原因: string
  }[]
  file_lines: {
    来源文件: string
    文件行号: number
    原始行: string
  }[]
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}
