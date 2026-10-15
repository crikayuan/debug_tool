<template>
  <div class="http-server-center">
    <!-- 顶部连接信息条：服务运行后展示所有可用访问地址 -->
    <div class="conn-bar">
      <template v-if="running">
        <span class="badge on">服务运行中</span>
        <span class="addr" v-for="a in addresses" :key="a.ip">
          <span class="addr-label">{{ a.label }}:</span>
          <code class="addr-url">{{ a.url }}</code>
          <el-button link size="small" type="primary" @click="copyText(a.url)">复制</el-button>
        </span>
      </template>
      <template v-else>
        <span class="badge off">未启动</span>
        <span class="muted">点击左下「启动服务」后此处会显示所有可访问的 URL（含本机/局域网）</span>
      </template>
    </div>

    <!-- 工具栏 -->
    <div class="log-toolbar">
      <span class="panel-title">请求记录 <span class="count">{{ totalText }}</span></span>
      <div class="toolbar-actions">
        <el-input
          v-model="filterText"
          size="small"
          class="filter-input"
          placeholder="筛选：方法/路径/IP/Body 关键字"
          clearable
        />
        <el-select v-model="methodFilter" size="small" class="method-filter" clearable placeholder="方法">
          <el-option v-for="m in methods" :key="m" :label="m" :value="m" />
        </el-select>
        <div class="btn-pair">
          <el-button size="small" @click="onExport" :disabled="!requests.length">导出</el-button>
          <el-button size="small" @click="onClear" :disabled="!requests.length">清空</el-button>
        </div>
      </div>
    </div>

    <!-- 主体：表格 + 详情 -->
    <div class="main-split">
      <!-- 请求列表 -->
      <div class="table-wrap" :class="{ expanded: !selected }">
        <el-table
          :data="filtered"
          height="100%"
          size="small"
          :row-class-name="rowClass"
          highlight-current-row
          @row-click="onRowClick"
          empty-text="暂无请求记录"
        >
          <el-table-column type="index" label="#" width="50" />
          <el-table-column label="时间" width="92">
            <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
          </el-table-column>
          <el-table-column label="方法" width="80">
            <template #default="{ row }">
              <span class="method-pill" :style="{ background: methodColor(row.method) }">
                {{ row.method }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="路径" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.raw_path }}</template>
          </el-table-column>
          <el-table-column label="来源" width="170">
            <template #default="{ row }">
              <span class="ip-click" :title="`复制 IP：${row.client_ip}`" @click.stop="copyText(row.client_ip)">
                {{ row.client_ip }}
              </span>
              <span class="muted">:</span>
              <span class="ip-click" :title="`复制端口：${row.client_port}`" @click.stop="copyText(String(row.client_port))">
                {{ row.client_port }}
              </span>
              <el-button link size="small" type="primary" class="copy-link" @click.stop="copyText(`${row.client_ip}:${row.client_port}`)">复制</el-button>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="80" align="right">
            <template #default="{ row }">{{ row.body_size }}B</template>
          </el-table-column>
          <el-table-column label="操作" width="64" align="center" fixed="right">
            <template #default="{ row }">
              <el-tooltip content="复制整条" placement="top">
                <el-button link size="small" type="primary" @click.stop="copyRow(row)">⧉</el-button>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 详情区 -->
      <div class="detail-wrap" v-if="selected">
        <div class="detail-head">
          <div class="detail-title">
            <span class="method-pill" :style="{ background: methodColor(selected.method) }">{{ selected.method }}</span>
            <code class="detail-path">{{ selected.raw_path }}</code>
          </div>
          <el-dropdown trigger="click" @command="onCopyCommand">
            <el-button size="small" type="primary" plain>
              <span style="margin-right:4px">⧉</span>复制
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="whole">整条（JSON）</el-dropdown-item>
                <el-dropdown-item command="curl">cURL 命令</el-dropdown-item>
                <el-dropdown-item command="url">URL（含 query）</el-dropdown-item>
                <el-dropdown-item command="body-text" :disabled="!selected.body">Body（文本）</el-dropdown-item>
                <el-dropdown-item command="body-hex" :disabled="!selected.body_hex">Body（HEX）</el-dropdown-item>
                <el-dropdown-item command="headers">Headers（键值对）</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" text @click="$emit('close-detail')">关闭</el-button>
        </div>
        <el-tabs v-model="detailTab" class="detail-tabs">
          <!-- 概览 -->
          <el-tab-pane label="概览" name="overview">
            <div class="kv">
              <div class="kv-row"><span class="k">方法</span><span class="v">{{ selected.method }}</span></div>
              <div class="kv-row"><span class="k">路径</span><span class="v">{{ selected.path }}</span></div>
              <div class="kv-row"><span class="k">完整 URL</span><span class="v">{{ selected.raw_path }}</span></div>
              <div class="kv-row" v-if="selected.query"><span class="k">查询参数</span><span class="v">{{ selected.query }}</span></div>
              <div class="kv-row"><span class="k">HTTP 版本</span><span class="v">{{ selected.http_version }}</span></div>
              <div class="kv-row"><span class="k">来源</span><span class="v">{{ selected.client_ip }}:{{ selected.client_port }}</span></div>
              <div class="kv-row"><span class="k">时间</span><span class="v">{{ formatFull(selected.timestamp) }}</span></div>
              <div class="kv-row"><span class="k">Body 大小</span><span class="v">{{ selected.body_size }} 字节</span></div>
              <div class="kv-row"><span class="k">Content-Type</span><span class="v">{{ selected.content_type || '—' }}</span></div>
              <div class="kv-row"><span class="k">是否二进制</span><span class="v">{{ selected.is_binary ? '是' : '否' }}</span></div>
            </div>
          </el-tab-pane>

          <!-- Headers -->
          <el-tab-pane :label="`Headers (${headerCount})`" name="headers">
            <div class="headers">
              <div class="kv-row" v-for="(v, k) in selected.headers" :key="k">
                <span class="k">{{ k }}</span>
                <span class="v">{{ formatHeader(v) }}</span>
              </div>
              <div v-if="!headerCount" class="muted">无请求头</div>
            </div>
          </el-tab-pane>

          <!-- Body（文本） -->
          <el-tab-pane label="Body（文本）" name="body-text" v-if="!selected.is_binary && selected.body">
            <pre class="body-text">{{ selected.body }}</pre>
          </el-tab-pane>

          <!-- Body（HEX） -->
          <el-tab-pane label="Body（HEX）" name="body-hex" v-if="selected.is_binary || selected.body_hex">
            <pre class="body-hex">{{ selected.body_hex || '' }}</pre>
          </el-tab-pane>

          <!-- 原始（整条 JSON） -->
          <el-tab-pane label="原始" name="raw">
            <pre class="body-json">{{ JSON.stringify(selected, null, 2) }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { methodColor } from '../store'
import { formatTime } from '../utils'

const props = defineProps({
  requests: { type: Array, default: () => [] },
  status: { type: Object, required: true },
  running: { type: Boolean, default: false },
  selected: { type: Object, default: null }
})
const emit = defineEmits(['select', 'close-detail', 'export', 'clear'])

const methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
const filterText = ref('')
const methodFilter = ref('')
const detailTab = ref('overview')

const addresses = computed(() => props.status?.addresses || [])

const filtered = computed(() => {
  const text = (filterText.value || '').trim().toLowerCase()
  const m = (methodFilter.value || '').toUpperCase()
  return (props.requests || []).filter((r) => {
    if (m && r.method !== m) return false
    if (!text) return true
    return (
      (r.raw_path || '').toLowerCase().includes(text) ||
      (r.method || '').toLowerCase().includes(text) ||
      (r.client_ip || '').toLowerCase().includes(text) ||
      (r.body || '').toLowerCase().includes(text) ||
      (r.body_hex || '').toLowerCase().includes(text)
    )
  })
})

const totalText = computed(() => {
  const t = props.status?.total || 0
  const c = props.requests.length
  return t === c ? `(${t})` : `(${c}/${t})`
})

const headerCount = computed(() => Object.keys(props.selected?.headers || {}).length)

function onRowClick(row) {
  emit('select', row)
}

function rowClass({ row }) {
  if (props.selected && props.selected.id === row.id) return 'is-selected'
  return ''
}

function onExport() {
  emit('export')
}

function onClear() {
  emit('clear')
}

// 整行格式化为单行可读文本（适合贴聊天/工单）
function formatRowOneline(row) {
  const ts = formatFull(row.timestamp)
  return `${ts}  ${row.method} ${row.raw_path}  ${row.client_ip}:${row.client_port}  ${row.body_size}B`
}

function copyRow(row) {
  copyText(formatRowOneline(row))
}

// 详情区复制下拉
function onCopyCommand(cmd) {
  const row = props.selected
  if (!row) return
  let text = ''
  let label = ''
  switch (cmd) {
    case 'whole':
      text = JSON.stringify(row, null, 2)
      label = '整条 JSON'
      break
    case 'curl': {
      // 构造可复跑的 curl 命令（默认 echo=true 会被回显，对联调足够）
      const host = window.location.hostname || '127.0.0.1'
      const port = (props.status && props.status.port) || '<port>'
      const url = `http://${host}:${port}${row.raw_path}`
      const headers = []
      if (row.headers) {
        for (const [k, v] of Object.entries(row.headers)) {
          if (k.toLowerCase() === 'host' || k.toLowerCase() === 'content-length') continue
          const val = Array.isArray(v) ? v[0] : v
          headers.push(`  -H '${k}: ${val}'`)
        }
      }
      const bodyPart = row.is_binary
        ? `  --data-binary $'\\x${(row.body_hex || '').replace(/ /g, '\\x')}'`
        : row.body
        ? `  --data '${row.body.replace(/'/g, "'\\''")}'`
        : ''
      text = `curl -i -X ${row.method} '${url}' \\\n${headers.join(' \\\n')}${bodyPart ? ' \\\n' + bodyPart : ''}`
      label = 'cURL 命令'
      break
    }
    case 'url': {
      const host = window.location.hostname || '127.0.0.1'
      const port = (props.status && props.status.port) || '<port>'
      text = `http://${host}:${port}${row.raw_path}`
      label = 'URL'
      break
    }
    case 'body-text':
      text = row.body || ''
      label = 'Body 文本'
      break
    case 'body-hex':
      text = row.body_hex || ''
      label = 'Body HEX'
      break
    case 'headers': {
      const lines = []
      if (row.headers) {
        for (const [k, v] of Object.entries(row.headers)) {
          if (Array.isArray(v)) {
            for (const one of v) lines.push(`${k}: ${one}`)
          } else {
            lines.push(`${k}: ${v}`)
          }
        }
      }
      text = lines.join('\n')
      label = 'Headers'
      break
    }
  }
  if (text) copyText(text, label)
}

function formatHeader(v) {
  return Array.isArray(v) ? v.join('\n') : String(v)
}

function formatFull(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}

async function copyText(text, label) {
  if (!text && text !== 0) return
  const tag = label ? `（${label}）` : ''
  try {
    await navigator.clipboard.writeText(text)
    // 文本太长只显示前 60 字符
    const preview = text.length > 60 ? text.slice(0, 60) + '…' : text
    ElMessage.success(`已复制${tag}：${preview}`)
  } catch (e) {
    // 兜底：选中文本
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy'); ElMessage.success(`已复制${tag}`) } catch (e2) { ElMessage.error('复制失败') }
    document.body.removeChild(ta)
  }
}
</script>

<style scoped>
.http-server-center { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.conn-bar {
  padding: 8px 12px;
  background: var(--soft);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  min-height: 38px;
}
.badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.badge.on { background: #10b981; color: #fff; }
.badge.off { background: #94a3b8; color: #fff; }
.muted { color: var(--muted); }

.addr {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.addr-label { color: var(--sub); font-size: 11px; }
.addr-url { color: var(--text); font-size: 12px; font-family: ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace; }

.log-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--panel);
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  padding-left: 8px;
  border-left: 3px solid var(--primary);
}
.panel-title .count { color: var(--muted); font-weight: 400; font-size: 12px; margin-left: 6px; }

.toolbar-actions { display: flex; align-items: center; gap: 8px; }
.filter-input { width: 240px; }
.method-filter { width: 100px; }
.btn-pair { display: inline-flex; gap: 6px; }

.main-split {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 1px;
  background: var(--border);
}
.table-wrap { background: var(--panel); overflow: hidden; flex: 1 1 auto; min-width: 0; }
.table-wrap.expanded { flex: 1 1 100%; }
.detail-wrap { background: var(--panel); width: 45%; min-width: 320px; display: flex; flex-direction: column; overflow: hidden; }

.detail-head {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--soft);
}
.detail-title { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; overflow: hidden; }
.detail-path { color: var(--text); font-size: 12px; font-family: ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ip-click {
  cursor: pointer;
  color: var(--text);
  font-family: ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  padding: 0 2px;
  border-radius: 3px;
  transition: background .12s;
}
.ip-click:hover { background: var(--soft); color: var(--primary); }
.copy-link { margin-left: 4px; padding: 0 4px; }

.method-pill {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  font-family: ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace;
  letter-spacing: 0.3px;
}

.detail-tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.detail-tabs :deep(.el-tabs__content) { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 12px; }

.kv { display: flex; flex-direction: column; gap: 2px; }
.kv-row {
  display: flex;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border);
  font-size: 12px;
  align-items: flex-start;
  gap: 12px;
}
.kv-row:last-child { border-bottom: none; }
.kv-row .k { flex: 0 0 90px; color: var(--sub); }
.kv-row .v { flex: 1; word-break: break-all; color: var(--text); }

.headers { font-size: 12px; }

.body-text, .body-hex, .body-json {
  margin: 0;
  font-family: ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text);
  background: var(--soft);
  padding: 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  max-height: 100%;
  overflow: auto;
}

:deep(.el-table .is-selected) td { background: rgba(64, 158, 255, 0.12) !important; }
</style>
