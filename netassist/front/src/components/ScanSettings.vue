<template>
  <div class="scan-settings">
    <div class="panel-head">
      <span class="panel-title">扫描设置</span>
    </div>

    <div class="panel-scroll">
      <el-collapse v-model="openSections" class="side-collapse">
        <!-- 扫描范围 -->
        <el-collapse-item title="扫描范围" name="range">
          <el-form label-width="58px" size="small" class="config-form">
            <el-form-item label="网段">
              <el-select v-model="cfg.segment" style="width:100%" placeholder="选择本机网段" @change="onSegmentChange">
                <el-option
                  v-for="s in segments"
                  :key="s.cidr"
                  :label="`${s.cidr} · ${s.type}`"
                  :value="s.cidr"
                />
                <el-option label="自定义范围" value="__custom__" />
              </el-select>
            </el-form-item>
            <el-form-item label="起始 IP">
              <el-input v-model="cfg.startIp" placeholder="192.168.1.1" />
            </el-form-item>
            <el-form-item label="结束 IP">
              <el-input v-model="cfg.endIp" placeholder="192.168.1.254" />
            </el-form-item>
          </el-form>
          <div class="hint-row">
            共 <b>{{ hostCount }}</b> 个地址待扫描。支持 <code>192.168.1.1-254</code> 或 CIDR 写法
          </div>
          <div class="btn-row">
            <el-button size="small" @click="fillLocalSeg">用本机网段</el-button>
            <el-button size="small" @click="fillCClass">整个 C 类</el-button>
          </div>
        </el-collapse-item>

        <!-- 探测方式 -->
        <el-collapse-item title="探测方式" name="probe">
          <el-form label-width="58px" size="small" class="config-form">
            <el-form-item label="方式">
              <el-select v-model="cfg.method" style="width:100%">
                <el-option value="arp_tcp" label="ARP + TCP（推荐）" />
              </el-select>
            </el-form-item>
            <el-form-item label="并发">
              <el-input-number
                v-model="cfg.concurrency"
                :min="8"
                :max="512"
                size="small"
                controls-position="right"
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="超时">
              <div class="row-flex">
                <el-input-number
                  v-model="cfg.timeoutMs"
                  :min="50"
                  :max="10000"
                  :step="50"
                  size="small"
                  controls-position="right"
                  style="flex:1;min-width:0"
                />
                <span class="unit">ms</span>
              </div>
            </el-form-item>
          </el-form>
          <div class="hint-row muted">ARP + TCP 无需管理员权限，速度最快；ICMP 需要管理员权限（二期）</div>
        </el-collapse-item>

        <!-- 信息获取 -->
        <el-collapse-item title="信息获取" name="info">
          <div class="opt-list">
            <el-checkbox :model-value="true" disabled size="small">MAC 地址（ARP 表）</el-checkbox>
            <el-checkbox v-model="cfg.vendorLookup" size="small">厂商（MAC 前缀库）</el-checkbox>
            <el-checkbox v-model="cfg.resolveHostname" size="small">主机名（反向解析）</el-checkbox>
            <el-checkbox v-model="cfg.portScan" size="small">开放端口探测</el-checkbox>
          </div>
          <template v-if="cfg.portScan">
            <div class="port-row">
              <span class="opt-label">端口</span>
              <el-select v-model="cfg.portPreset" size="small" style="flex:1;min-width:0" @change="applyPreset">
                <el-option v-for="p in PRESETS" :key="p.key" :label="p.label" :value="p.key" />
              </el-select>
            </div>
            <el-input v-model="portsText" size="small" placeholder="逗号分隔端口，如 80,443,502" class="ports-input" />
          </template>
          <div class="hint-row muted">端口探测会显著增加扫描耗时</div>
        </el-collapse-item>

        <!-- 扫描历史 -->
        <el-collapse-item title="扫描历史" name="history">
          <div class="hist-list">
            <div
              v-for="(h, i) in store.scanHistory"
              :key="i"
              class="hist-item"
              :class="{ active: i === activeIndex }"
              @click="$emit('select-history', i)"
            >
              <div class="hist-main">
                <div class="hist-time">{{ h.time }}</div>
                <div class="hist-meta">{{ h.seg || '—' }} · 在线 {{ h.online }}</div>
              </div>
              <span class="hist-delta" :class="h.deltaCls">{{ h.delta }}</span>
            </div>
            <div v-if="!store.scanHistory.length" class="empty-tip">暂无扫描记录</div>
          </div>
          <div class="hint-row muted">保留最近 10 次；对比上次可发现新增设备与 IP-MAC 变化（疑似 IP 冲突）</div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div class="panel-foot">
      <el-button type="primary" style="flex:1" :disabled="running" @click="onStart">开始扫描</el-button>
      <el-button type="danger" style="flex:1" :disabled="!running" @click="$emit('stop')">停止</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { store } from '../store'

const props = defineProps({
  segments: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
  status: { type: String, default: 'idle' },
  activeIndex: { type: Number, default: -1 }
})
const emit = defineEmits(['start', 'stop', 'select-history'])

// 直接绑定到持久化配置（变更经 store 的 watch 自动落盘）
const cfg = reactive(store.scanConfig)

// 端口预设方案（含工控）
const PRESETS = [
  { key: 'common', label: '常用（22,80,443,445,3389）', ports: [22, 80, 443, 445, 3389] },
  { key: 'web', label: 'Web（80,443,8080,8000）', ports: [80, 443, 8080, 8000] },
  { key: 'remote', label: '远程（22,3389,5900）', ports: [22, 3389, 5900] },
  { key: 'db', label: '数据库（3306,5432,1433,6379）', ports: [3306, 5432, 1433, 6379] },
  { key: 'plc', label: '工控（502,102,44818,47808）', ports: [502, 102, 44818, 47808] },
  { key: 'custom', label: '自定义', ports: [] }
]

const openSections = ref(['range', 'probe', 'info', 'history'])

// 端口输入框：与 cfg.ports 双向同步，手工编辑即切到「自定义」
const portsText = computed({
  get: () => (cfg.ports || []).join(','),
  set: (v) => {
    cfg.ports = String(v)
      .split(',')
      .map(s => parseInt(s.trim(), 10))
      .filter(n => !Number.isNaN(n) && n >= 1 && n <= 65535)
    cfg.portPreset = 'custom'
  }
})

function applyPreset(key) {
  if (key === 'custom') return
  const preset = PRESETS.find(p => p.key === key)
  if (preset) cfg.ports = [...preset.ports]
}

/* ---------- IP 范围辅助（仅用于提示与快捷填充） ---------- */
function ipToInt(ip) {
  const p = String(ip || '').split('.')
  if (p.length !== 4) return NaN
  const n = p.map(x => parseInt(x, 10))
  if (n.some(x => Number.isNaN(x) || x < 0 || x > 255)) return NaN
  return ((n[0] * 256 + n[1]) * 256 + n[2]) * 256 + n[3]
}
function intToIp(n) {
  return [24, 16, 8, 0].map(s => (n >>> s) & 255).join('.')
}

const hostCount = computed(() => {
  const s = ipToInt(cfg.startIp)
  const e = ipToInt(cfg.endIp)
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return 0
  return e - s + 1
})

// 从 CIDR 计算可用主机范围（如 /24 → .1 ~ .254）
function segRange(cidr) {
  const parts = String(cidr).split('/')
  if (parts.length !== 2) return null
  const base = ipToInt(parts[0])
  const prefix = parseInt(parts[1], 10)
  if (Number.isNaN(base) || Number.isNaN(prefix)) return null
  const size = Math.pow(2, 32 - prefix)
  if (size <= 2) return [intToIp(base), intToIp(base + size - 1)]
  return [intToIp(base + 1), intToIp(base + size - 2)]
}

function onSegmentChange(val) {
  if (!val || val === '__custom__') { cfg.segment = '__custom__'; return }
  const range = segRange(val)
  if (range) {
    cfg.startIp = range[0]
    cfg.endIp = range[1]
  }
}

function fillLocalSeg() {
  if (!props.segments.length) { ElMessage.warning('未获取到本机网段'); return }
  const seg = props.segments[0]
  cfg.segment = seg.cidr
  const range = segRange(seg.cidr)
  if (range) {
    cfg.startIp = range[0]
    cfg.endIp = range[1]
  }
}

function fillCClass() {
  const base = ipToInt(cfg.startIp)
  if (Number.isNaN(base)) { ElMessage.warning('请先填写起始 IP'); return }
  const prefix = intToIp(base).split('.').slice(0, 3).join('.')
  cfg.segment = '__custom__'
  cfg.startIp = `${prefix}.1`
  cfg.endIp = `${prefix}.254`
}

function onStart() {
  const start = (cfg.startIp || '').trim()
  const end = (cfg.endIp || '').trim()
  if (Number.isNaN(ipToInt(start)) || Number.isNaN(ipToInt(end))) {
    ElMessage.warning('请填写合法的起始/结束 IP')
    return
  }
  if (ipToInt(start) > ipToInt(end)) {
    ElMessage.warning('起始 IP 不能大于结束 IP')
    return
  }
  emit('start', {
    startIp: start,
    endIp: end,
    method: cfg.method,
    concurrency: cfg.concurrency,
    timeoutMs: cfg.timeoutMs,
    vendorLookup: cfg.vendorLookup,
    resolveHostname: cfg.resolveHostname,
    portScan: cfg.portScan,
    ports: cfg.portScan ? [...(cfg.ports || [])] : []
  })
}
</script>

<style scoped>
.scan-settings {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border, #e3e8ef);
  background: var(--soft, #f5f7fa);
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #1f2329);
  padding-left: 8px;
  border-left: 3px solid var(--primary, #2f6fed);
  line-height: 1.2;
}
.panel-scroll { flex: 1; overflow-y: auto; padding: 4px 12px 8px; }

.side-collapse { border-top: none; }
.side-collapse :deep(.el-collapse-item__header) {
  height: 34px;
  line-height: 34px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #1f2329);
  border-bottom: none;
}
.side-collapse :deep(.el-collapse-item__header.is-active) { color: var(--primary, #2f6fed); }
.side-collapse :deep(.el-collapse-item__wrap) { border-bottom: 1px solid var(--border, #e3e8ef); }
.side-collapse :deep(.el-collapse-item__content) { padding-bottom: 8px; }
.config-form :deep(.el-form-item) { margin-bottom: 8px; }
.config-form :deep(.el-form-item__label) { color: var(--sub, #5a6472); }

.hint-row { margin-top: 6px; font-size: 11.5px; line-height: 1.5; color: var(--sub, #5a6472); }
.hint-row b { color: var(--primary, #2f6fed); }
.hint-row code {
  background: var(--soft, #f5f7fa);
  padding: 0 3px;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
}
.hint-row.muted { color: var(--muted, #8b95a3); }
.btn-row { display: flex; gap: 6px; margin-top: 8px; }
.btn-row .el-button { flex: 1; }

.opt-list { display: flex; flex-direction: column; gap: 7px; }
.port-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.opt-label { font-size: 12px; color: var(--sub, #5a6472); white-space: nowrap; }
.ports-input { margin-top: 6px; }
.unit { font-size: 12px; color: var(--muted, #8b95a3); }

/* 扫描历史 */
.hist-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 6px; }
.hist-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid var(--border, #e3e8ef);
  border-radius: 6px;
  cursor: pointer;
  transition: all .15s;
}
.hist-item:hover { border-color: var(--primary, #2f6fed); background: #fafbff; }
.hist-item.active { border-color: var(--primary, #2f6fed); background: var(--primary-soft, #eaf1fe); }
.hist-main { flex: 1; min-width: 0; }
.hist-time { font-size: 11.5px; font-weight: 600; color: var(--text, #1f2329); }
.hist-meta {
  font-size: 10.5px;
  color: var(--muted, #8b95a3);
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hist-delta { margin-left: auto; font-size: 10.5px; font-weight: 600; color: var(--muted, #8b95a3); flex: none; }
.hist-delta.new { color: var(--success, #2e9e6b); }
.hist-delta.warn { color: var(--warning, #e8912d); }
.empty-tip { color: var(--muted, #8b95a3); font-size: 11.5px; text-align: center; padding: 16px 0; }

.panel-foot {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid var(--border, #e3e8ef);
  background: var(--panel, #fff);
}
.row-flex { display: flex; width: 100%; gap: 6px; align-items: center; }
.row-flex > * { min-width: 0; }
</style>
