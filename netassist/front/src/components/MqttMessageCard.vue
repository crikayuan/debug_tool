<template>
  <div class="msg-card" :class="dirClass">
    <div class="msg-header">
      <span class="msg-time">{{ msg.timeStr }}</span>
      <span class="topic-tag" :style="{ background: tagBg, color: color }">
        <span class="topic-dot" :style="{ background: color }"></span>{{ msg.topic }}
      </span>
      <span class="msg-qos">QoS{{ msg.qos }}</span>
      <span v-if="msg.retain" class="msg-retain">Retain</span>
      <span class="msg-dir" :class="dirClass">{{ dirLabel }}</span>
    </div>
    <div class="msg-payload">{{ msg.display }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { topicColor } from '../store'
import { hexToRgba } from '../utils'

const props = defineProps({
  msg: { type: Object, required: true }
})

const dirClass = computed(() => String(props.msg.dir || 'rx').toLowerCase())
const dirLabel = computed(() => {
  switch (dirClass.value) {
    case 'tx': return '→ 发送'
    case 'auto': return '自动'
    default: return '← 接收'
  }
})
const color = computed(() => topicColor(props.msg.topic))
const tagBg = computed(() => hexToRgba(color.value, 0.1))
</script>

<style scoped>
.msg-card {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--border, #e3e8ef);
  box-shadow: 0 1px 3px rgba(16, 24, 40, .05), 0 1px 2px rgba(16, 24, 40, .03);
}
.msg-card.tx { border-left: 3px solid var(--primary, #2f6fed); }
.msg-card.rx { border-left: 3px solid var(--success, #18a058); }
.msg-card.auto { border-left: 3px solid var(--purple, #8e5cd8); }

.msg-header { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; flex-wrap: wrap; }
.msg-time { font-size: 11px; color: var(--muted, #8b95a3); font-family: 'JetBrains Mono', Consolas, monospace; }
.topic-tag {
  display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px;
  border-radius: 12px; font-size: 11.5px; font-weight: 600; word-break: break-all;
}
.topic-dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.msg-dir { margin-left: auto; font-size: 11px; font-weight: 700; }
.msg-dir.rx { color: var(--success, #18a058); }
.msg-dir.tx { color: var(--primary, #2f6fed); }
.msg-dir.auto { color: var(--purple, #8e5cd8); }
.msg-qos { font-size: 10px; color: var(--muted, #8b95a3); background: #f2f4f8; padding: 1px 5px; border-radius: 4px; }
.msg-retain { font-size: 10px; color: #b26a00; border: 1px solid #f6d99a; padding: 0 4px; border-radius: 4px; }
.msg-payload {
  font-family: 'JetBrains Mono', Consolas, 'Courier New', monospace; font-size: 13px; line-height: 1.65;
  background: #fafbfc; padding: 8px 10px; border-radius: 6px; word-break: break-all; color: var(--text, #1f2329);
  white-space: pre-wrap;
}
</style>
