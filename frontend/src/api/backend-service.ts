import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  EntryRow,
  OverviewResult,
  PageResult,
  ScanReport,
  ScanReportSummary,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

export async function importSampleFile(
  filename: string,
  content: string,
): Promise<ActionResult> {
  const response = await request('/api/external_label_sample/import', {
    method: 'POST',
    body: JSON.stringify({ filename, content }),
  })
  return await response.json()
}

export async function runStratifiedScan(
  id: number,
  quota: number,
  sourceFile: string,
): Promise<ActionResult> {
  const response = await request(`/api/compliance_check/${id}/stratified_scan`, {
    method: 'POST',
    body: JSON.stringify({ quota, source_file: sourceFile }),
  })
  return await response.json()
}

export async function listScanReports(): Promise<{ items: ScanReportSummary[]; total: number }> {
  const response = await request('/api/compliance_check/scan_reports')
  if (!response.ok) throw new Error('扫描报告读取失败')
  return await response.json()
}

export async function getScanReport(reportId: string): Promise<ScanReport> {
  const response = await request(`/api/compliance_check/scan_reports/${reportId}`)
  if (!response.ok) throw new Error('扫描报告不存在或已清理')
  return await response.json()
}
