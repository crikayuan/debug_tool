<template>
  <div class="scan-result">
    <!-- 顶部：进度 + 工具条 -->
    <div class="scan-toolbar">
      <div class="scan-status">
        <div class="progress-wrap">
          <span class="lbl">进度</span>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: percent + '%' }"></div>
          </div>
          <span class="progress-text">{{ progress.scanned || 0 }} / {{ progress.total || 0 }}</span>
        </div>
      </div>

      <!-- 统计 chip 行：总占用 / 在线 / 离线 / 可用率 / 段内空 IP -->
      <div class="stat-row">
        <div class="chip" :title="`扫描段 ${progress.cidr || '—'}`">
          <span class="chip-lbl">总占用</span>
          <span class="chip-val total">{{ stats.occupied }} <span class="chip-unit">/ {{ stats.total }}</span></span>
        </div>
        <div class="chip">
          <span class="chip-lbl">在线</span>
          <span class="chip-val online">{{ stats.online }}</span>
        </div>
        <div class="chip">
          <span class="chip-lbl">离线</span>
          <span class="chip-val offline">{{ stats.offline }}</span>
        </div>
        <div class="chip">
          <span class="chip-lbl">可用率</span>
          <span class="chip-val util" :class="utilClass">{{ stats.utilization }}%</span>
        </div>
        <div class="chip" :title="`段内未分配/不可达地址 = ${stats.total} - ${stats.occupied}`">
          <span class="chip-lbl">段内空</span>
          <span class="chip-val empty">{{ stats.empty }}</span>
        </div>
        <div class="chip" v-if="progress.cidr">
          <span class="chip-lbl">段</span>
          <span class="chip-val cidr">{{ progress.cidr }}</span>
        </div>
      </div>

      <div class="result-tools">
        <div class="seg">
          <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
          <button :class="{ active: filter === 'online' }" @click="filter = 'online'">仅在线</button>
          <button :class="{ active: filter === 'offline' }" @click="filter = 'offline'">仅离线</button>
        </div>
        <el-input v-model="keyword" size="small" class="kw" placeholder="按 IP / MAC / 厂商 / 主机名筛选" clearable />
        <span class="spacer"></span>
        <el-button size="small" @click="$emit('export')">导出 CSV</el-button>
        <el-button size="small" @click="$emit('clear')">清空结果</el-button>
      </div>
    </div>

    <!-- 变化告警横幅（新增 / 离开 / 改 IP-MAC） -->
    <div v-if="hasChanges" class="changes-banner">
      <span class="cb-label">变化</span>
      <span v-if="changeList.new && changeList.new.length" class="cb-item new">
        本次新增 <b>{{ changeList.new.length }}</b> 个
        <span class="cb-detail">
          <span v-for="(it, i) in changeList.new.slice(0, 3)" :key="'n'+i" class="cb-pill">
            {{ it.ip }}<span v-if="it.vendor"> · {{ it.vendor }}</span>
          </span>
          <span v-if="changeList.new.length > 3" class="cb-more">等 {{ changeList.new.length - 3 }} 个</span>
        </span>
      </span>
      <span v-if="changeList.left && changeList.left.length" class="cb-item left">
        离开 <b>{{ changeList.left.length }}</b> 个
        <span class="cb-detail">
          <span v-for="(it, i) in changeList.left.slice(0, 3)" :key="'l'+i" class="cb-pill">
            {{ it.ip }}<span v-if="it.mac"> · {{ it.mac }}</span>
          </span>
          <span v-if="changeList.left.length > 3" class="cb-more">等 {{ changeList.left.length - 3 }} 个</span>
        </span>
      </span>
      <span v-if="changeList.changed && changeList.changed.length" class="cb-item changed">
        IP-MAC 变化 <b>{{ changeList.changed.length }}</b> 个（疑似 IP 冲突）
        <span class="cb-detail">
          <span v-for="(it, i) in changeList.changed.slice(0, 2)" :key="'c'+i" class="cb-pill warn">
            {{ it.ip }}: {{ shortMac(it.from_mac) }} → {{ shortMac(it.to_mac) }}
          </span>
          <span v-if="changeList.changed.length > 2" class="cb-more">等 {{ changeList.changed.length - 2 }} 个</span>
        </span>
      </span>
    </div>

    <!-- 结果表格 -->
    <div class="table-wrap">
      <table class="result">
        <thead>
          <tr>
            <th style="width:34px" title="收藏（置顶）">★</th>
            <th style="width:74px">状态</th>
            <th style="width:118px">IP 地址</th>
            <th style="width:140px">MAC 地址</th>
            <th style="width:112px">厂商</th>
            <th style="width:122px">主机名</th>
            <th style="width:64px">延迟</th>
            <th>开放端口</th>
            <th style="width:110px">备注</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in rows"
            :key="r.ip"
            :class="rowClass(r)"
            @click="select(r)"
            @dblclick="select(r)"
          >
            <td class="star-cell">
              <span class="star" :class="{ on: isFav(r.ip) }" :title="isFav(r.ip) ? '取消收藏' : '收藏（置顶显示）'" @click.stop="toggleFav(r.ip)">★</span>
            </td>
            <td>
              <span class="dot" :class="r.online ? 'on' : 'off'"></span>{{ r.online ? '在线' : '离线' }}
              <span v-if="changeOf(r.ip) && changeOf(r.ip).type === 'changed'" class="warn-badge" :title="changeOf(r.ip).text">变化</span>
              <span v-else-if="changeOf(r.ip) && changeOf(r.ip).type === 'new'" class="new-badge">新增</span>
            </td>
            <td class="mono ip-cell">{{ r.ip }}</td>
            <td class="mono">{{ r.mac || '—' }}</td>
            <td class="vendor-cell">{{ r.vendor || '' }}</td>
            <td class="vendor-cell">{{ r.hostname || '' }}</td>
            <td class="mono">{{ r.online ? (r.delay_ms + ' ms') : '—' }}</td>
            <td class="ports-cell">
              <template v-if="r.ports && r.ports.length">
                <span v-for="p in r.ports" :key="p" class="tag-port">{{ p }}</span>
              </template>
              <span v-else class="muted">—</span>
            </td>
            <td class="note-cell">{{ store.scanNotes[r.ip] || '' }}</td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="9" class="empty-row">{{ emptyText }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 底部操作栏 -->
    <div class="result-footer">
      <span class="tip">
        {{ selected ? `已选中 ${selected.ip} · ${selected.mac || '—'}` : '未选中设备' }}
      </span>
      <span class="spacer"></span>
      <el-button size="small" :disabled="!selected" @click="copyIp">复制 IP</el-button>
      <el-button size="small" :disabled="!selected" @click="copyMac">复制 MAC</el-button>
      <el-button size="small" :disabled="!selected" @click="addNote">添加备注</el-button>
      <el-button size="small" :disabled="!selected" @click="toggleFav(selected.ip)">
        {{ selected && isFav(selected.ip) ? '取消收藏' : '收藏' }}
      </el-button>
      <el-button type="primary" size="small" :disabled="!selected" @click="$emit('use-ip', selected)">
        用该 IP 建立 TCP 连接
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { store, sortScanRows } from '../store'

const props = defineProps({
  results: { type: Array, default: () => [] },
  progress: { type: Object, default: () => ({ scanned: 0, total: 0, online: 0, elapsed: 0 }) },
  changes: { type: Object, default: () => ({}) },
  // 服务端推送的本轮 vs 上一轮 聚合列表 {new,left,changed}
  changeList: { type: Object, default: () => ({ new: [], left: [], changed: [] }) },
  running: { type: Boolean, default: false }
})
const emit = defineEmits(['export', 'clear', 'use-ip'])

const filter = ref('all')
const keyword = ref('')
const selectedIp = ref('')

const percent = computed(() => {
  const t = props.progress.total || 0
  if (!t) return 0
  return Math.min(100, Math.round((props.progress.scanned || 0) / t * 100))
})

const onlineCount = computed(() => props.results.filter(r => r.online).length)

// 聚合统计：total / online / offline / occupied / utilization / empty
const stats = computed(() => {
  const total = props.progress.total || 0
  // 优先用服务端推送的精确值；前端兜底（避免后端没下发时的空窗）
  const online = (props.progress.online != null) ? props.progress.online : onlineCount.value
  const offline = (props.progress.offline != null) ? props.progress.offline : (props.results.length - online)
  const occupied = (props.progress.occupied != null) ? props.progress.occupied : (online + offline)
  const utilization = (props.progress.utilization != null) ? props.progress.utilization : (total ? Math.round(occupied * 100 / total * 100) / 100 : 0)
  const empty = Math.max(0, total - occupied)
  return { total, online, offline, occupied, utilization, empty }
})

// 可用率色阶（>70% 红、30~70% 橙、<30% 绿）
const utilClass = computed(() => {
  const u = stats.value.utilization
  if (u >= 70) return 'util-high'
  if (u >= 30) return 'util-mid'
  return 'util-low'
})

// 变化告警：新增/离开/改 IP-MAC 任何一项非空即展示
const hasChanges = computed(() => {
  const c = props.changeList || {}
  return (c.new && c.new.length) || (c.left && c.left.length) || (c.changed && c.changed.length)
})

function shortMac(mac) {
  if (!mac) return '—'
  return mac.toUpperCase()
}

const rows = computed(() => {
  let list = props.results
  if (filter.value === 'online') list = list.filter(r => r.online)
  if (filter.value === 'offline') list = list.filter(r => !r.online)
  const kw = keyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(r =>
      String(r.ip || '').toLowerCase().includes(kw) ||
      String(r.mac || '').toLowerCase().includes(kw) ||
      String(r.vendor || '').toLowerCase().includes(kw) ||
      String(r.hostname || '').toLowerCase().includes(kw)
    )
  }
  return sortScanRows(list, store.scanFavorites)
})

const selected = computed(() => props.results.find(r => r.ip === selectedIp.value) || null)

const emptyText = computed(() => {
  if (props.running) return '正在扫描中…'
  if (props.results.length) return '没有符合筛选条件的结果'
  return '点击左侧「开始扫描」后，结果将实时显示在这里'
})

function isFav(ip) { return !!store.scanFavorites[ip] }

function toggleFav(ip) {
  if (!ip) return
  if (store.scanFavorites[ip]) delete store.scanFavorites[ip]
  else store.scanFavorites[ip] = true
}

function changeOf(ip) { return props.changes[ip] }

function rowClass(r) {
  const cls = []
  if (!r.online) cls.push('offline')
  if (r.ip === selectedIp.value) cls.push('selected')
  const chg = changeOf(r.ip)
  if (chg && chg.type === 'changed') cls.push('changed')
  if (chg && chg.type === 'new') cls.push('is-new')
  return cls
}

function select(r) {
  selectedIp.value = r.ip
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      el.remove()
    }
    ElMessage.success('已复制: ' + text)
  } catch (e) {
    ElMessage.error('复制失败')
  }
}

function copyIp() { if (selected.value) copyText(selected.value.ip) }
function copyMac() {
  if (!selected.value) return
  if (!selected.value.mac) { ElMessage.warning('该设备无 MAC 信息'); return }
  copyText(selected.value.mac)
}

async function addNote() {
  if (!selected.value) return
  const ip = selected.value.ip
  try {
    const { value } = await ElMessageBox.prompt(`为 ${ip} 添加备注`, '设备备注', {
      inputValue: store.scanNotes[ip] || '',
      inputPlaceholder: '例如：3号泊位PLC',
      confirmButtonText: '保存',
      cancelButtonText: '取消'
    })
    store.scanNotes[ip] = (value || '').trim()
    ElMessage.success('备注已保存')
  } catch (e) { /* 取消 */ }
}
</script>

<style scoped>
.scan-result {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel, #fff);
  border: 1px solid var(--border, #e3e8ef);
  border-radius: 10px;
  box-shadow: var(--shadow, 0 1px 3px rgba(16, 24, 40, .05));
  overflow: hidden;
}

/* 工具条 */
.scan-toolbar {
  flex: none;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border, #e3e8ef);
  background: var(--soft, #f5f7fa);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.scan-status { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--sub, #5a6472); }
.scan-status b { color: var(--text, #1f2329); }
.scan-status .stat { white-space: nowrap; }

/* 统计 chip 行：紧凑、彩色编码 */
.stat-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.chip {
  display: inline-flex; align-items: baseline; gap: 6px;
  padding: 3px 8px; border-radius: 14px;
  background: var(--soft, #f3f5f9); border: 1px solid var(--border, #e3e8ef);
  font-size: 11.5px; line-height: 1.2;
}
.chip-lbl { color: var(--sub, #5a6473); }
.chip-val { font-weight: 700; font-variant-numeric: tabular-nums; }
.chip-unit { font-weight: 400; color: var(--muted, #8b95a3); font-size: 10.5px; }
.chip-val.total { color: var(--primary, #2f6fed); }
.chip-val.online { color: #10b981; }
.chip-val.offline { color: #f59e0b; }
.chip-val.util-high { color: #ef4444; }
.chip-val.util-mid { color: #f59e0b; }
.chip-val.util-low { color: #10b981; }
.chip-val.empty { color: var(--sub, #5a6473); }
.chip-val.cidr { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 10.5px; color: var(--sub, #5a6473); }

/* 变化告警横幅 */
.changes-banner {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 6px 10px; margin: 6px 0 0;
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px;
  font-size: 12px;
}
.cb-label {
  font-size: 11px; font-weight: 700; color: #92400e;
  padding: 1px 6px; background: #fde68a; border-radius: 3px;
}
.cb-item { display: inline-flex; align-items: center; gap: 4px; }
.cb-item b { font-variant-numeric: tabular-nums; margin: 0 2px; }
.cb-item.new b { color: #10b981; }
.cb-item.left b { color: #ef4444; }
.cb-item.changed b { color: #f59e0b; }
.cb-detail { display: inline-flex; gap: 4px; flex-wrap: wrap; }
.cb-pill {
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 10.5px;
  padding: 1px 5px; border-radius: 3px;
  background: rgba(0,0,0,0.04);
  color: var(--sub, #5a6473);
}
.cb-pill.warn { background: #fee2e2; color: #991b1b; }
.cb-more { font-size: 10.5px; color: var(--muted, #8b95a3); }
.progress-wrap { flex: 1; display: flex; align-items: center; gap: 10px; min-width: 0; }
.progress-wrap .lbl { flex: none; }
.progress-track { flex: 1; height: 6px; border-radius: 3px; background: var(--border, #e3e8ef); overflow: hidden; }
.progress-fill { height: 100%; width: 0; background: var(--primary, #2f6fed); border-radius: 3px; transition: width .12s linear; }
.progress-text { font-size: 11.5px; color: var(--muted, #8b95a3); font-variant-numeric: tabular-nums; white-space: nowrap; }

.result-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.result-tools .spacer { flex: 1; }
.kw { width: 220px; }
.seg { display: inline-flex; border: 1px solid var(--border, #e3e8ef); border-radius: 6px; overflow: hidden; }
.seg button {
  height: 24px; padding: 0 11px; border: none; background: var(--panel, #fff);
  color: var(--sub, #5a6472); font-family: inherit; font-size: 11.5px; cursor: pointer;
  border-right: 1px solid var(--border, #e3e8ef);
}
.seg button:last-child { border-right: none; }
.seg button:hover { color: var(--primary, #2f6fed); }
.seg button.active { background: var(--primary, #2f6fed); color: #fff; font-weight: 600; }

/* 表格 */
.table-wrap { flex: 1; min-height: 0; overflow: auto; background: var(--panel, #fff); }
table.result { width: 100%; border-collapse: collapse; font-size: 12px; }
table.result thead th {
  position: sticky; top: 0; z-index: 2;
  background: var(--soft, #f5f7fa); color: var(--sub, #5a6472);
  font-weight: 600; font-size: 11.5px; text-align: left;
  padding: 7px 10px; border-bottom: 1px solid var(--border, #e3e8ef); white-space: nowrap;
}
table.result tbody td { padding: 6px 10px; border-bottom: 1px solid var(--border, #e3e8ef); white-space: nowrap; }
table.result tbody tr:hover td { background: var(--soft, #f5f7fa); }
table.result tbody tr.selected td { background: var(--primary-soft, #eaf1fe); }
table.result tbody tr.offline td { color: var(--muted, #8b95a3); }
table.result tbody tr.changed td:first-child { box-shadow: inset 3px 0 0 var(--warning, #e8912d); }
table.result tbody tr.is-new td:first-child { box-shadow: inset 3px 0 0 var(--success, #2e9e6b); }
.star-cell { text-align: center; }
.star { cursor: pointer; color: #d5dae2; font-size: 14px; user-select: none; line-height: 1; }
.star:hover { color: #f5c26b; }
.star.on { color: #f5a623; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.dot.on { background: var(--success, #2e9e6b); }
.dot.off { background: #cbd2dc; }
.mono { font-family: 'JetBrains Mono', Consolas, Monaco, monospace; }
.ip-cell { font-weight: 600; color: var(--text, #1f2329); }
.vendor-cell { color: var(--sub, #5a6472); }
.note-cell { color: var(--warning, #e8912d); }
.muted { color: var(--muted, #8b95a3); }
.tag-port {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  background: var(--primary-soft, #eaf1fe); color: var(--primary, #2f6fed);
  font-size: 11px; margin-right: 4px;
}
.warn-badge {
  display: inline-block; margin-left: 5px; font-size: 11px; cursor: help;
  color: #fff; background: var(--warning, #e8912d); border-radius: 3px; padding: 0 4px;
}
.new-badge {
  display: inline-block; margin-left: 5px; font-size: 11px;
  color: #fff; background: var(--success, #2e9e6b); border-radius: 3px; padding: 0 4px;
}
.empty-row { text-align: center; color: var(--muted, #8b95a3); padding: 46px 0 !important; font-size: 12.5px; }

/* 底部操作栏 */
.result-footer {
  flex: none; display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-top: 1px solid var(--border, #e3e8ef); background: var(--panel, #fff);
}
.result-footer .spacer { flex: 1; }
.result-footer .tip {
  font-size: 11.5px; color: var(--muted, #8b95a3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 40%;
}
</style>
