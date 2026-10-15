<template>
  <div class="mqtt-subs">
    <div class="mod-title">订阅管理</div>

    <!-- 新增订阅行 -->
    <div class="sub-add">
      <el-input
        v-model="newTopic"
        size="small"
        placeholder="主题，支持 + / # 通配符"
        @keyup.enter="addSubscription"
      />
      <el-select v-model="newQos" size="small" class="qos-sel">
        <el-option :value="0" label="QoS0" />
        <el-option :value="1" label="QoS1" />
        <el-option :value="2" label="QoS2" />
      </el-select>
      <el-button type="primary" size="small" :loading="subscribing" @click="addSubscription">订阅</el-button>
    </div>

    <!-- 订阅卡片列表 -->
    <div class="sub-list">
      <div
        v-for="(s, i) in store.mqttSubscriptions"
        :key="s.topic"
        class="sub-card"
        :class="{ active: s.topic === store.mqttConfig.publishTopic }"
        @click="fillPublishTopic(s.topic)"
      >
        <div class="sub-color" :style="{ background: colorOf(s) }"></div>
        <div class="sub-info">
          <div class="sub-topic">{{ s.topic }}</div>
          <div class="sub-meta">
            <span>QoS {{ s.qos }}</span>
            <span>{{ s.count || 0 }} 条消息</span>
          </div>
        </div>
        <div class="sub-actions">
          <el-button link type="primary" size="small" @click.stop="setDefault(s.topic)">设为默认</el-button>
          <el-button link type="danger" size="small" @click.stop="removeSubscription(s, i)">取消</el-button>
        </div>
      </div>
      <div v-if="!store.mqttSubscriptions.length" class="empty-tip">暂无订阅，请在上方输入主题后点「订阅」</div>
    </div>

    <div class="hint">点击订阅卡片可把主题填入发送区；断线重连后自动恢复订阅</div>
  </div>
</template>

<script setup>
import { ref, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { store, topicColor } from '../store'
import { mqttApi } from '../api'

const debug = inject('debug')
const connectionId = computed(() => debug.connectionId.value)
const isConnected = computed(() => debug.isConnected.value)

const newTopic = ref('')
const newQos = ref(0)
const subscribing = ref(false)

function colorOf(s) {
  return s.color || topicColor(s.topic)
}

// 点击卡片：把主题填入发送区
function fillPublishTopic(topic) {
  store.mqttConfig.publishTopic = topic
}

// 设为默认：填入并标记为当前主题
function setDefault(topic) {
  store.mqttConfig.publishTopic = topic
  ElMessage.success(`已设为默认主题：${topic}`)
}

async function addSubscription() {
  const topic = newTopic.value.trim()
  if (!topic) { ElMessage.warning('请输入订阅主题'); return }
  if (!isConnected.value) { ElMessage.warning('请先建立连接'); return }
  if (store.mqttSubscriptions.some(s => s.topic === topic)) {
    ElMessage.info('该主题已订阅')
    return
  }
  subscribing.value = true
  try {
    await mqttApi.subscribe(connectionId.value, topic, newQos.value)
    store.mqttSubscriptions.push({
      topic,
      qos: newQos.value,
      color: topicColor(topic),
      count: 0
    })
    // 首次订阅即默认填入发布主题，减少手工输入
    if (!store.mqttConfig.publishTopic) store.mqttConfig.publishTopic = topic
    newTopic.value = ''
    ElMessage.success(`已订阅：${topic}`)
  } catch (e) {
    ElMessage.error('订阅失败: ' + e.message)
  } finally {
    subscribing.value = false
  }
}

async function removeSubscription(s, index) {
  try {
    if (isConnected.value) await mqttApi.unsubscribe(connectionId.value, s.topic)
  } catch (e) {
    ElMessage.error('取消订阅失败: ' + e.message)
  }
  const idx = store.mqttSubscriptions.findIndex(x => x.topic === s.topic)
  if (idx >= 0) store.mqttSubscriptions.splice(idx, 1)
  else store.mqttSubscriptions.splice(index, 1)
}
</script>

<style scoped>
.mod-title { font-size: 14px; font-weight: 600; color: var(--text, #1f2329); margin-bottom: 10px; }

.sub-add { display: flex; gap: 5px; margin-bottom: 10px; align-items: center; }
.sub-add :deep(.el-input) { flex: 1; min-width: 0; }
.qos-sel { width: 78px; flex: none; }

.sub-list { display: flex; flex-direction: column; }
.sub-card {
  display: flex; align-items: center; gap: 8px; padding: 8px;
  border-radius: 8px; border: 1px solid var(--border, #e3e8ef); margin-bottom: 8px;
  background: #fff; cursor: pointer; transition: all .15s;
}
.sub-card:hover { border-color: var(--primary, #2f6fed); background: #fafbff; }
.sub-card.active { border-color: var(--primary, #2f6fed); background: var(--primary-soft, #eaf1fe); }
.sub-color { width: 4px; height: 36px; border-radius: 2px; flex: none; }
.sub-info { flex: 1; min-width: 0; }
.sub-topic { font-weight: 600; font-size: 12px; word-break: break-all; color: var(--text, #1f2329); }
.sub-meta { font-size: 11px; color: var(--muted, #8b95a3); margin-top: 2px; display: flex; gap: 8px; }
.sub-actions { display: flex; flex-direction: column; gap: 1px; flex: none; align-items: flex-start; }

.empty-tip { color: var(--muted, #8b95a3); font-size: 11.5px; text-align: center; padding: 20px 0; }
.hint { margin-top: 6px; font-size: 11px; color: var(--muted, #8b95a3); line-height: 1.6; }
</style>
