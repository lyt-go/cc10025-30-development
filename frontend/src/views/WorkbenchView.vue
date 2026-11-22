<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button
          v-if="isSampleModule"
          class="btn"
          data-testid="open-import"
          type="button"
          @click="openImport"
        >
          上传样本文件
        </button>
        <button
          v-if="isComplianceModule"
          class="btn"
          data-testid="open-scan-reports"
          type="button"
          @click="openReports"
        >
          扫描报告
        </button>
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button
              v-if="isComplianceModule"
              class="link"
              type="button"
              :data-testid="`scan-${row.id}`"
              @click="openScan(row)"
            >
              分层扫描
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="showImport" class="modal-backdrop" data-testid="import-modal">
      <form class="modal" @submit.prevent="submitImport">
        <h3>上传样本文件并导入</h3>
        <p class="page-desc">
          按分区键与标签来源逐行核对，生成分区匹配失败保留待核、可逐行复核的外部标签样本清单。
        </p>
        <label class="create-field">
          <span>来源文件</span>
          <input v-model="importFilename" data-testid="import-filename" placeholder="如 inspector_sample_2026-11-22.csv" required />
        </label>
        <label class="create-field">
          <span>文件内容（CSV 表头：分区键,文件分组,标签来源,优先级）</span>
          <textarea
            v-model="importContent"
            class="import-textarea"
            data-testid="import-content"
            rows="8"
            required
          ></textarea>
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showImport = false">取消</button>
          <button class="btn primary" data-testid="submit-import" type="submit" :disabled="importing">
            {{ importing ? '导入中…' : '确认导入' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="showScan" class="modal-backdrop" data-testid="scan-modal">
      <form class="modal" @submit.prevent="submitScan">
        <h3>提交分层扫描</h3>
        <p class="page-desc">
          按外部标签样本清单实际选择分区：已确认样本按标签来源的新归属组分层轮取，
          名额有限时优先覆盖不同归属组；待核行保留，不计入合规覆盖。
        </p>
        <label class="create-field">
          <span>本轮名额</span>
          <input v-model.number="scanQuota" data-testid="scan-quota" type="number" min="1" required />
        </label>
        <label class="create-field">
          <span>来源文件（留空按规则扫描范围）</span>
          <input v-model="scanSourceFile" data-testid="scan-source-file" placeholder="外部标签样本来源文件" />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showScan = false">取消</button>
          <button class="btn primary" data-testid="submit-scan" type="submit" :disabled="scanning">
            {{ scanning ? '扫描中…' : '提交扫描' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="showReports" class="modal-backdrop" data-testid="reports-modal">
      <div class="modal">
        <h3>合规分层扫描报告</h3>
        <template v-if="!activeReport">
          <table class="data-table">
            <thead>
              <tr>
                <th>报告编号</th>
                <th>规则</th>
                <th>来源文件</th>
                <th>名额</th>
                <th>覆盖分组</th>
                <th>抽中行号</th>
                <th>未核</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in reports" :key="item.report_id" :data-testid="`report-${item.report_id}`">
                <td>{{ item.report_id }}</td>
                <td>{{ item.rule_id }}</td>
                <td>{{ item.source_file || '全部样本' }}</td>
                <td>{{ item.quota }}</td>
                <td>{{ item.groups_used.join('、') }}</td>
                <td>{{ item.sampled_line_numbers.join('、') }}</td>
                <td>{{ item.unverified_count }}</td>
                <td class="row-actions">
                  <button class="link" type="button" :data-testid="`reopen-${item.report_id}`" @click="reopenReport(item.report_id)">
                    重新打开
                  </button>
                </td>
              </tr>
              <tr v-if="!reports.length">
                <td colspan="8" class="empty-state">暂无扫描报告，请先提交分层扫描</td>
              </tr>
            </tbody>
          </table>
          <div class="page-actions report-actions">
            <button class="btn" type="button" @click="showReports = false">关闭</button>
          </div>
        </template>
        <template v-else>
          <p class="page-desc">
            报告 {{ activeReport.report_id }} ｜ 规则 {{ activeReport.rule_id }} ｜
            {{ activeReport.sampling_mode }} ｜ 名额 {{ activeReport.quota }} ｜
            扫描时间 {{ activeReport.scanned_at }}
          </p>
          <p v-if="conflictText" class="conflict-note" data-testid="report-conflict">
            口径冲突：{{ conflictText }}，已按标签来源新归属组分层取样
          </p>
          <h4>抽中明细（取样分组 / 标签版本）</h4>
          <table class="data-table">
            <thead>
              <tr><th>文件行号</th><th>分区键</th><th>文件分组</th><th>取样分组</th><th>标签版本</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in activeReport.sampled" :key="item.样本编号">
                <td>{{ item.文件行号 }}</td>
                <td>{{ item.分区键 }}</td>
                <td>{{ item.文件分组 }}</td>
                <td>{{ item.取样分组 }}</td>
                <td>{{ item.标签版本 }}</td>
              </tr>
            </tbody>
          </table>
          <h4>实际读取的文件行（复核）</h4>
          <table class="data-table" data-testid="report-file-lines">
            <thead>
              <tr><th>来源文件</th><th>文件行号</th><th>原始行</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in activeReport.file_lines" :key="item.文件行号">
                <td>{{ item.来源文件 }}</td>
                <td>{{ item.文件行号 }}</td>
                <td><code>{{ item.原始行 }}</code></td>
              </tr>
            </tbody>
          </table>
          <h4>未抽中分区（跳过原因）</h4>
          <table class="data-table">
            <thead>
              <tr><th>文件行号</th><th>分区键</th><th>跳过原因</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in activeReport.skipped" :key="item.样本编号">
                <td>{{ item.文件行号 }}</td>
                <td>{{ item.分区键 }}</td>
                <td>{{ item.跳过原因 }}</td>
              </tr>
            </tbody>
          </table>
          <h4>未核行（保留待核，不计入合规覆盖）</h4>
          <table class="data-table">
            <thead>
              <tr><th>文件行号</th><th>分区键</th><th>核验说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in activeReport.unverified" :key="item.样本编号">
                <td>{{ item.文件行号 }}</td>
                <td>{{ item.分区键 }}</td>
                <td>{{ item.核验说明 }}</td>
              </tr>
              <tr v-if="!activeReport.unverified.length">
                <td colspan="3" class="empty-state">本轮无未核行</td>
              </tr>
            </tbody>
          </table>
          <div class="page-actions report-actions">
            <button class="btn" type="button" @click="activeReport = null">返回列表</button>
            <button class="btn" type="button" @click="showReports = false">关闭</button>
          </div>
        </template>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createEntry,
  downloadEntries,
  getScanReport,
  importSampleFile,
  listEntries,
  listScanReports,
  moduleMeta,
  runAction as applyAction,
  runStratifiedScan,
} from '@/api/backend-service'
import type { EntryRow, ScanReport, ScanReportSummary } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})

// 外部标签样本：上传样本文件并导入
const isSampleModule = props.moduleKey === 'external_label_sample'
const showImport = ref(false)
const importing = ref(false)
const importFilename = ref('')
const importContent = ref('')

// 合规检查：分层扫描与扫描报告复核
const isComplianceModule = props.moduleKey === 'compliance_check'
const showScan = ref(false)
const scanning = ref(false)
const scanRuleId = ref(0)
const scanQuota = ref(2)
const scanSourceFile = ref('')
const showReports = ref(false)
const reports = ref<ScanReportSummary[]>([])
const activeReport = ref<ScanReport | null>(null)
const conflictText = computed(() => {
  if (!activeReport.value) return ''
  return Object.entries(activeReport.value.conflict_groups)
    .map(([fileGroup, groups]) => `文件分组「${fileGroup}」已拆分为 ${groups.join('、')}`)
    .join('；')
})
const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

function openImport() {
  importFilename.value = ''
  importContent.value = ''
  errorMessage.value = ''
  noticeMessage.value = ''
  showImport.value = true
}

async function submitImport() {
  importing.value = true
  errorMessage.value = ''
  try {
    const result = await importSampleFile(importFilename.value, importContent.value)
    if (!result.ok) throw new Error(result.message)
    showImport.value = false
    await reload()
    noticeMessage.value = result.message
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '样本文件导入失败'
  } finally {
    importing.value = false
  }
}

function openScan(row: EntryRow) {
  scanRuleId.value = Number(row.id)
  scanQuota.value = 2
  scanSourceFile.value = String(row['扫描范围'] ?? '')
  errorMessage.value = ''
  noticeMessage.value = ''
  showScan.value = true
}

async function submitScan() {
  scanning.value = true
  errorMessage.value = ''
  try {
    const result = await runStratifiedScan(scanRuleId.value, scanQuota.value, scanSourceFile.value)
    if (!result.ok) throw new Error(result.message)
    showScan.value = false
    noticeMessage.value = result.message
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分层扫描失败'
  } finally {
    scanning.value = false
  }
}

async function openReports() {
  errorMessage.value = ''
  activeReport.value = null
  try {
    const payload = await listScanReports()
    reports.value = payload.items
    showReports.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '扫描报告读取失败'
  }
}

async function reopenReport(reportId: string) {
  errorMessage.value = ''
  try {
    activeReport.value = await getScanReport(reportId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '扫描报告读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(reload)
</script>
