<template>
  <div class="quick">
    <div class="head">
      <span class="t">快捷指令</span>
      <el-button size="small" @click="openAdd">新增</el-button>
    </div>
    <div class="list">
      <div v-for="(c, i) in store.quickCommands" :key="i" class="item">
        <div class="info">
          <div class="name">{{ c.name }} <span v-if="c.shortcut" class="sc">({{ c.shortcut }})</span></div>
          <div class="data">{{ c.data }}</div>
        </div>
        <div class="ops">
          <el-button size="small" type="primary" @click="send(c)">发送</el-button>
          <el-button size="small" @click="openEdit(i)">编辑</el-button>
          <el-button size="small" text type="danger" @click="store.quickCommands.splice(i, 1)">删</el-button>
        </div>
      </div>
      <div v-if="!store.quickCommands.length" class="empty">暂无指令</div>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing >= 0 ? '编辑指令' : '新增指令'" width="400px">
      <el-form label-width="60px" size="small">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="数据"><el-input v-model="form.data" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="格式">
          <el-radio-group v-model="form.format">
            <el-radio label="text">文本</el-radio>
            <el-radio label="hex">HEX</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="快捷键">
          <el-select v-model="form.shortcut" clearable style="width:100%">
            <el-option v-for="k in 12" :key="k" :label="'F' + k" :value="'F' + k" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, inject, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { store } from '../store'

const debug = inject('debug')
const dialogVisible = ref(false)
const editing = ref(-1)
const form = reactive({ name: '', data: '', format: 'text', shortcut: '' })

function openAdd() {
  editing.value = -1
  Object.assign(form, { name: '', data: '', format: 'text', shortcut: '' })
  dialogVisible.value = true
}

function openEdit(i) {
  editing.value = i
  Object.assign(form, store.quickCommands[i])
  dialogVisible.value = true
}

function save() {
  if (!form.name || !form.data) { ElMessage.warning('名称和数据不能为空'); return }
  if (editing.value >= 0) store.quickCommands[editing.value] = { ...form }
  else store.quickCommands.push({ ...form })
  dialogVisible.value = false
}

async function send(c) {
  await debug.sendData({ data: c.data, format: c.format })
}

function onKey(e) {
  if (e.key && e.key.startsWith('F')) {
    const c = store.quickCommands.find(x => x.shortcut === e.key)
    if (c) { e.preventDefault(); send(c) }
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.t { font-size: 14px; font-weight: 600; color: #303133; }
.list { display: flex; flex-direction: column; gap: 6px; }
.item { display: flex; align-items: center; gap: 8px; padding: 6px; background: #f5f7fa; border-radius: 6px; }
.info { flex: 1; min-width: 0; }
.name { font-size: 13px; font-weight: 600; }
.sc { color: #909399; font-weight: 400; }
.data { font-size: 12px; color: #606266; word-break: break-all; }
.ops { display: flex; gap: 2px; flex-shrink: 0; }
.empty { text-align: center; color: #999; padding: 20px; }
</style>
