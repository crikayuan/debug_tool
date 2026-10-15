<template>
  <div>
    <div class="head"><span class="t">Modbus 指令生成</span></div>
    <el-form label-width="80px" size="small">
      <el-form-item label="协议">
        <el-select v-model="form.protocol" style="width:100%">
          <el-option value="rtu" label="RTU" />
          <el-option value="tcp" label="TCP" />
          <el-option value="ascii" label="ASCII" />
        </el-select>
      </el-form-item>
      <el-form-item label="从站地址">
        <el-input-number v-model="form.slave_id" :min="0" :max="247" style="width:100%" />
      </el-form-item>
      <el-form-item label="功能码">
        <el-select v-model="form.function" style="width:100%">
          <el-option :value="1" label="01 读线圈" />
          <el-option :value="2" label="02 读离散输入" />
          <el-option :value="3" label="03 读保持寄存器" />
          <el-option :value="4" label="04 读输入寄存器" />
          <el-option :value="5" label="05 写单个线圈" />
          <el-option :value="6" label="06 写单个寄存器" />
          <el-option :value="15" label="0F 写多个线圈" />
          <el-option :value="16" label="10 写多个寄存器" />
        </el-select>
      </el-form-item>
      <el-form-item label="起始地址">
        <el-input-number v-model="form.address" :min="0" :max="65535" style="width:100%" />
      </el-form-item>
      <el-form-item label="数量">
        <el-input-number v-model="form.quantity" :min="1" :max="125" style="width:100%" />
      </el-form-item>
      <el-form-item v-if="needValues" label="写入值">
        <el-input v-model="valuesStr" placeholder="逗号分隔，如 1,2,3" />
      </el-form-item>
      <el-form-item label="字节序">
        <el-select v-model="form.byte_order" style="width:100%">
          <el-option value="big" label="大端" />
          <el-option value="little" label="小端" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="build">生成帧</el-button>
        <el-button @click="send" :disabled="!frameHex">发送</el-button>
      </el-form-item>
    </el-form>

    <div v-if="frameHex" class="frame">
      <div class="frame-label">生成的帧：</div>
      <div class="frame-hex">{{ frameHex }}</div>
      <div class="frame-meta">长度 {{ frameLen }} 字节</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { modbusApi } from '../api'

const debug = inject('debug')
const form = reactive({
  protocol: 'rtu', slave_id: 1, function: 3,
  address: 0, quantity: 1, byte_order: 'big'
})
const valuesStr = ref('')
const frameHex = ref('')
const frameLen = ref(0)

const needValues = computed(() => [5, 6, 15, 16].includes(form.function))

function parseValues() {
  if (!valuesStr.value.trim()) return []
  return valuesStr.value.split(/[,，\s]+/).map(s => parseInt(s, 10)).filter(v => !isNaN(v))
}

async function build() {
  try {
    const payload = { ...form, values: parseValues() }
    const res = await modbusApi.build(payload)
    frameHex.value = res.data.frame_hex
    frameLen.value = res.data.length
  } catch (e) {
    ElMessage.error('生成失败: ' + e.message)
  }
}

async function send() {
  await debug.sendData({ data: frameHex.value, format: 'hex' })
}
</script>

<style scoped>
.head { margin-bottom: 8px; }
.t { font-size: 14px; font-weight: 600; color: #303133; }
.frame { margin-top: 8px; padding: 8px; background: #f5f7fa; border-radius: 6px; }
.frame-label { font-size: 12px; color: #606266; }
.frame-hex { font-family: Consolas, Monaco, monospace; font-size: 12px; word-break: break-all; margin: 4px 0; }
.frame-meta { font-size: 12px; color: #909399; }
</style>
