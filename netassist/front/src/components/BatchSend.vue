<template>
  <div class="batch-send">
    <div class="batch-table-wrap">
      <el-table
        :data="store.batchItems"
        size="small"
        height="100%"
        row-key="id"
        highlight-current-row
        @selection-change="onSelectionChange"
        @row-dblclick="editRow"
      >
        <el-table-column type="selection" width="38" />
        <el-table-column label="编号" width="52" align="center">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="延迟" width="70" align="right">
          <template #default="scope">{{ scope.row.delay }} ms</template>
        </el-table-column>
        <el-table-column label="重复" width="56" align="center">
          <template #default="scope">{{ scope.row.repeat }}</template>
        </el-table-column>
        <el-table-column label="数据" min-width="120" show-overflow-tooltip>
          <template #default="scope">
            <div class="data-cell">
              <el-tag size="small" :type="tagType(scope.row.format)" effect="plain" class="fmt-tag">
                {{ fmtLabel(scope.row.format) }}
              </el-tag>
              <span class="data-text" :title="dataTitle(scope.row)">{{ dataText(scope.row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="90" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="76" align="center">
          <template #default="scope">
            <el-button size="small" text type="primary" @click="editRow(scope.row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="removeOne(scope.$index)">删</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">点击下方 + 添加要批量发送的数据</div>
        </template>
      </el-table>
    </div>

    <div class="batch-toolbar">
      <div class="tool-left">
        <el-button size="small" circle title="添加" @click="openAdd">
          <el-icon><Plus /></el-icon>
        </el-button>
        <el-button size="small" circle title="删除选中" :disabled="!selected.length" @click="removeSelected">
          <el-icon><Close /></el-icon>
        </el-button>
        <el-button size="small" circle title="上移" :disabled="!canUp" @click="moveUp">
          <el-icon><ArrowUp /></el-icon>
        </el-button>
        <el-button size="small" circle title="下移" :disabled="!canDown" @click="moveDown">
          <el-icon><ArrowDown /></el-icon>
        </el-button>
      </div>
      <div class="tool-right">
        <el-select v-model="loopMode" size="small" style="width:110px">
          <el-option label="循环1次" value="once" />
          <el-option label="无限循环" value="infinite" />
          <el-option label="指定循环..." value="custom" />
        </el-select>
        <el-input-number v-if="loopMode === 'custom'" v-model="customLoop" size="small" :min="1" :max="999999" :step="1" style="width:80px" />
        <el-button size="small" type="primary" @click="start" :disabled="running || !store.batchItems.length">启动批量发送</el-button>
        <el-button size="small" @click="stop" :disabled="!running">停止</el-button>
      </div>
    </div>
    <div class="batch-status">{{ statusText }}</div>

    <!-- 添加/编辑数据项 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑数据项' : '添加数据项'" width="480px">
      <el-form label-width="90px" size="small">
        <el-form-item label="数据类型">
          <el-radio-group v-model="form.format">
            <el-radio-button label="text">ASCII</el-radio-button>
            <el-radio-button label="hex">HEX</el-radio-button>
            <el-radio-button label="file">FILE</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.format === 'file'" label="文件">
          <div class="row-flex">
            <el-input v-model="form.fileName" placeholder="请选择文件" readonly style="flex:1" />
            <el-button @click="chooseFile">浏览</el-button>
            <input ref="fileInput" type="file" style="display:none" @change="onBrowserFile" />
          </div>
        </el-form-item>
        <el-form-item v-else label="数据">
          <el-input v-model="form.data" type="textarea" :rows="4" placeholder="请输入要发送的数据" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="可空" />
        </el-form-item>
        <el-form-item label="发送延时">
          <div class="row-flex">
            <el-input-number v-model="form.delay" :min="0" :max="3600000" :step="100" style="flex:1" />
            <span class="unit">ms</span>
          </div>
        </el-form-item>
        <el-form-item label="重复次数">
          <el-input-number v-model="form.repeat" :min="1" :max="999999" :step="1" style="flex:1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button size="small" type="primary" @click="saveItem">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, inject, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Close, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import { store } from '../store'

const debug = inject('debug')
const isConnected = computed(() => debug.isConnected.value)

const selected = ref([])
const running = ref(false)
const done = ref(0)
const total = ref(0)
const loopMode = ref('once')
const customLoop = ref(1)
const dialogVisible = ref(false)
const editingId = ref(null)
const fileInput = ref(null)
let stopFlag = false

const form = reactive({
  data: '',
  format: 'hex',
  fileName: '',
  delay: 1000,
  repeat: 1,
  remark: ''
})

const statusText = computed(() => {
  if (running.value) return `发送中 ${done.value}/${total.value}`
  return `共 ${store.batchItems.length} 项，选中 ${selected.value.length} 项`
})

const canUp = computed(() => selected.value.length === 1 && store.batchItems.indexOf(selected.value[0]) > 0)
const canDown = computed(() => selected.value.length === 1 && store.batchItems.indexOf(selected.value[0]) < store.batchItems.length - 1)

function fmtLabel(fmt) {
  if (fmt === 'hex') return 'HEX'
  if (fmt === 'file') return '文件'
  return '文本'
}
function tagType(fmt) {
  if (fmt === 'hex') return 'warning'
  if (fmt === 'file') return 'success'
  return ''
}
function dataText(item) {
  if (item.format === 'file') return item.fileName || '[文件]'
  return item.data || ''
}
function dataTitle(item) {
  if (item.format === 'file') return item.fileName || ''
  return item.data || ''
}

function onSelectionChange(rows) {
  selected.value = rows
}

function resetForm() {
  form.data = ''
  form.format = 'hex'
  form.fileName = ''
  form.delay = 1000
  form.repeat = 1
  form.remark = ''
  editingId.value = null
}

function openAdd() {
  resetForm()
  dialogVisible.value = true
}

function editRow(row) {
  editingId.value = row.id
  form.data = row.format === 'file' ? '' : row.data
  form.format = row.format
  form.fileName = row.fileName || ''
  form.delay = row.delay ?? 1000
  form.repeat = row.repeat ?? 1
  form.remark = row.remark || ''
  dialogVisible.value = true
}

function removeOne(idx) {
  store.batchItems.splice(idx, 1)
}

function removeSelected() {
  const ids = new Set(selected.value.map(r => r.id))
  store.batchItems = store.batchItems.filter(b => !ids.has(b.id))
  selected.value = []
}

function moveUp() {
  const row = selected.value[0]
  const idx = store.batchItems.indexOf(row)
  if (idx > 0) {
    store.batchItems.splice(idx, 1)
    store.batchItems.splice(idx - 1, 0, row)
  }
}

function moveDown() {
  const row = selected.value[0]
  const idx = store.batchItems.indexOf(row)
  if (idx >= 0 && idx < store.batchItems.length - 1) {
    store.batchItems.splice(idx, 1)
    store.batchItems.splice(idx + 1, 0, row)
  }
}

function generateId() {
  return 'b' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

function saveItem() {
  if (form.format !== 'file' && !form.data) {
    ElMessage.warning('请输入数据')
    return
  }
  if (form.format === 'file' && !form.data) {
    ElMessage.warning('请选择文件')
    return
  }
  const item = {
    id: editingId.value || generateId(),
    data: form.data,
    format: form.format,
    fileName: form.format === 'file' ? form.fileName : '',
    delay: form.delay,
    repeat: form.repeat,
    remark: form.remark
  }
  if (editingId.value) {
    const idx = store.batchItems.findIndex(b => b.id === editingId.value)
    if (idx >= 0) store.batchItems.splice(idx, 1, item)
  } else {
    store.batchItems.push(item)
  }
  dialogVisible.value = false
}

function chooseFile() {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_file) {
    window.pywebview.api.choose_file().then(res => {
      if (res && res.data) {
        form.format = 'file'
        form.data = res.data
        form.fileName = res.name || ''
      }
    }).catch(e => ElMessage.error('选择文件失败: ' + e))
  } else {
    fileInput.value && fileInput.value.click()
  }
}

function onBrowserFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const base64 = reader.result.split(',')[1]
    form.format = 'file'
    form.data = base64
    form.fileName = file.name
  }
  reader.readAsDataURL(file)
  e.target.value = ''
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function start() {
  const items = store.batchItems.filter(b => b.data)
  if (!items.length) { ElMessage.warning('请先添加要批量发送的数据'); return }
  if (!isConnected.value) { ElMessage.warning('请先建立连接'); return }

  const loops = loopMode.value === 'infinite' ? Infinity : loopMode.value === 'custom' ? Math.max(1, customLoop.value || 1) : 1
  const totalPerLoop = items.reduce((s, b) => s + (b.repeat || 1), 0)
  running.value = true
  stopFlag = false
  done.value = 0
  total.value = loops === Infinity ? '∞' : totalPerLoop * loops

  let loopIdx = 0
  while (loops === Infinity || loopIdx < loops) {
    if (stopFlag) break
    loopIdx++
    for (const b of items) {
      if (stopFlag) break
      const repeat = b.repeat || 1
      for (let i = 0; i < repeat; i++) {
        if (stopFlag) break
        const ok = await debug.sendData({
          data: b.data,
          format: b.format,
          fileName: b.fileName,
          endChars: '',
          appendCheck: null
        })
        if (!ok) {
          stopFlag = true
          break
        }
        done.value++
        const needDelay = (i < repeat - 1) || b !== items[items.length - 1]
        if (b.delay > 0 && needDelay && !stopFlag) await sleep(b.delay)
      }
      if (stopFlag) break
    }
  }

  running.value = false
  if (!stopFlag) ElMessage.success('批量发送完成')
}

function stop() {
  stopFlag = true
  running.value = false
}
</script>

<style scoped>
.batch-send { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.batch-table-wrap { flex: 1; min-height: 0; }
.batch-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0 6px;
  border-top: 1px solid var(--el-border-color-light);
  margin-top: 6px;
}
.tool-left { display: flex; gap: 6px; }
.tool-right { display: flex; align-items: center; gap: 8px; }
.batch-status { font-size: 12px; color: var(--el-text-color-secondary); padding-top: 2px; }
.data-cell { display: flex; align-items: center; gap: 6px; }
.fmt-tag { flex-shrink: 0; }
.data-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { text-align: center; color: var(--el-text-color-secondary); padding: 30px 0; }
.row-flex { display: flex; width: 100%; gap: 8px; align-items: center; }
.unit { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
