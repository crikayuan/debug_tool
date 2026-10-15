<template>
  <div class="http-server-settings">
    <div class="panel-head">
      <span class="panel-title">HTTP 服务设置</span>
    </div>
    <div class="panel-scroll">
      <el-collapse v-model="openSections" class="side-collapse">
        <!-- 1. 服务配置 -->
        <el-collapse-item title="服务配置" name="server">
          <el-form label-width="70px" size="small" class="config-form">
            <el-form-item label="端口">
              <el-input-number
                v-model.number="config.port"
                :min="1"
                :max="65535"
                :step="1"
                :disabled="running"
                controls-position="right"
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="绑定地址">
              <el-select v-model="config.bind" :disabled="running" style="width:100%" size="small">
                <el-option label="0.0.0.0 (所有网卡)" value="0.0.0.0" />
                <el-option label="127.0.0.1 (仅本机)" value="127.0.0.1" />
              </el-select>
            </el-form-item>
            <el-form-item label=" ">
              <div class="hint">所有方法（GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS）均接收，任意路径都接。</div>
            </el-form-item>
          </el-form>
        </el-collapse-item>

        <!-- 2. 响应配置（决定 client 收到什么） -->
        <el-collapse-item title="响应配置" name="response">
          <el-form label-width="84px" size="small" class="config-form">
            <el-form-item label="模式">
              <el-radio-group v-model="responseMode" size="small" :disabled="false">
                <el-radio-button label="echo">回显</el-radio-button>
                <el-radio-button label="custom">自定义</el-radio-button>
              </el-radio-group>
              <div class="hint" style="margin-top:4px">
                回显 = 把 client 发来的 body 原样返回（推荐，便于联调）；自定义 = 按下面配置返回
              </div>
            </el-form-item>

            <template v-if="responseMode === 'custom'">
              <el-form-item label="状态码">
                <el-input-number
                  v-model.number="config.response.code"
                  :min="100"
                  :max="599"
                  :step="1"
                  controls-position="right"
                  style="width:100%"
                />
              </el-form-item>
              <el-form-item label="Content-Type">
                <el-select
                  v-model="config.response.content_type"
                  size="small"
                  filterable
                  allow-create
                  default-first-option
                  style="width:100%"
                  placeholder="可输入自定义或选预设"
                >
                  <el-option label="application/json" value="application/json" />
                  <el-option label="application/xml" value="application/xml" />
                  <el-option label="text/plain; charset=utf-8" value="text/plain; charset=utf-8" />
                  <el-option label="text/html; charset=utf-8" value="text/html; charset=utf-8" />
                  <el-option label="application/octet-stream" value="application/octet-stream" />
                </el-select>
              </el-form-item>
              <el-form-item label="Body">
                <el-input
                  v-model="config.response.body"
                  type="textarea"
                  :rows="5"
                  placeholder="自定义响应体（UTF-8）"
                />
              </el-form-item>
            </template>

            <el-form-item label="响应延迟">
              <el-input-number
                v-model.number="config.response.delay_ms"
                :min="0"
                :max="60000"
                :step="100"
                controls-position="right"
                style="width:100%"
              />
              <div class="hint" style="margin-top:4px">毫秒（0~60000），用于模拟慢响应</div>
            </el-form-item>
          </el-form>
        </el-collapse-item>

        <!-- 3. 统计 -->
        <el-collapse-item title="运行统计" name="stats">
          <div class="stat-row"><span class="k">总请求数</span><span class="v">{{ status.total || 0 }}</span></div>
          <div class="stat-row"><span class="k">内存中记录</span><span class="v">{{ status.count || 0 }}</span></div>
          <div class="stat-row"><span class="k">已运行</span><span class="v">{{ formatElapsed(status.elapsed) }}</span></div>
          <div class="stat-row" v-if="status.last_error"><span class="k">最近错误</span><span class="v err">{{ status.last_error }}</span></div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div class="panel-foot">
      <el-button :type="running ? 'danger' : 'primary'" style="width:100%" @click="onToggle" :loading="loading">
        {{ running ? '停止服务' : '启动服务' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { store } from '../store'

const props = defineProps({
  status: { type: Object, required: true },
  running: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['start', 'stop', 'response-change'])

const openSections = ref(['server', 'response', 'stats'])

// 深拷贝以避免修改 store 里的对象引起 watcher 误触发
const config = ref(JSON.parse(JSON.stringify(store.httpServerConfig || {})))

// 回显 / 自定义模式
const responseMode = ref(config.value.response?.echo !== false ? 'echo' : 'custom')

watch(responseMode, (v) => {
  config.value.response.echo = v === 'echo'
  emit('response-change', config.value.response)
})
watch(
  () => config.value.response,
  (v) => emit('response-change', v),
  { deep: true }
)

function onToggle() {
  // 同步回显标志位
  config.value.response.echo = responseMode.value === 'echo'
  if (props.running) {
    emit('stop')
  } else {
    // 启动前把当前 config 写回 store
    store.httpServerConfig = JSON.parse(JSON.stringify(config.value))
    emit('start', config.value)
  }
}

function formatElapsed(sec) {
  sec = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}时${m}分${s}秒`
  if (m > 0) return `${m}分${s}秒`
  return `${s}秒`
}
</script>

<style scoped>
.http-server-settings { display: flex; flex-direction: column; height: 100%; }
.panel-head {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--soft);
  display: flex;
  align-items: center;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  padding-left: 8px;
  border-left: 3px solid var(--primary);
}
.panel-scroll { flex: 1; overflow-y: auto; padding: 6px 8px; }
.panel-foot { padding: 8px 12px; border-top: 1px solid var(--border); background: var(--soft); }
.config-form .el-form-item { margin-bottom: 10px; }
.hint { font-size: 11px; color: var(--muted); line-height: 1.5; }
.stat-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0; border-bottom: 1px dashed var(--border);
  font-size: 12px;
}
.stat-row:last-child { border-bottom: none; }
.stat-row .k { color: var(--sub); }
.stat-row .v { font-weight: 600; color: var(--text); }
.stat-row .v.err { color: #ef4444; font-weight: 500; }
</style>
