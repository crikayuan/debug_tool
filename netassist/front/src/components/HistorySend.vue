<template>
  <div>
    <div class="head">
      <span class="t">历史发送</span>
      <el-button size="small" @click="store.history = []">清空</el-button>
    </div>
    <el-input v-model="keyword" size="small" placeholder="搜索已发送的指令" clearable style="margin-bottom:8px" />
    <div class="list">
      <div v-for="(h, i) in filtered" :key="i" class="item">
        <div class="info">
          <div class="data">{{ h.data }}</div>
          <div class="meta">{{ timeStr(h.time) }} · {{ h.format }}</div>
        </div>
        <el-button size="small" type="primary" @click="resend(h)">重发</el-button>
      </div>
      <div v-if="!filtered.length" class="empty">暂无历史记录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject } from 'vue'
import { store } from '../store'
import { formatTime } from '../utils'

const debug = inject('debug')
const keyword = ref('')

const filtered = computed(() => {
  if (!keyword.value) return store.history
  return store.history.filter(h => h.data.includes(keyword.value))
})

function timeStr(ts) {
  const d = new Date(ts)
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

async function resend(h) {
  await debug.sendData({ data: h.data, format: h.format })
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.t { font-size: 14px; font-weight: 600; color: #303133; }
.list { display: flex; flex-direction: column; gap: 6px; }
.item { display: flex; align-items: center; gap: 8px; padding: 6px; background: #f5f7fa; border-radius: 6px; }
.info { flex: 1; min-width: 0; }
.data { font-size: 13px; word-break: break-all; }
.meta { font-size: 12px; color: #909399; }
.empty { text-align: center; color: #999; padding: 16px; }
</style>
