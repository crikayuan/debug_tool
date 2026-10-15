<template>
  <div>
    <div class="head"><span class="t">工具箱</span></div>
    <el-tabs v-model="tab" size="small">
      <!-- 校验计算 -->
      <el-tab-pane label="校验计算" name="check">
        <el-form label-width="70px" size="small">
          <el-form-item label="算法">
            <el-select v-model="check.algorithm" style="width:100%">
              <el-option value="sum" label="Sum 校验和" />
              <el-option value="xor" label="XOR 异或" />
              <el-option value="lrc" label="LRC" />
              <el-option value="crc16" label="CRC16 (Modbus)" />
              <el-option value="fcs" label="FCS (CCITT)" />
            </el-select>
          </el-form-item>
          <el-form-item label="格式">
            <el-radio-group v-model="check.format">
              <el-radio label="hex">HEX</el-radio>
              <el-radio label="text">文本</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="数据">
            <el-input v-model="check.data" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="doCheck">计算</el-button>
          </el-form-item>
        </el-form>
        <div v-if="checkResult" class="result">校验值：{{ checkResult }}</div>
      </el-tab-pane>

      <!-- 数据转换 -->
      <el-tab-pane label="数据转换" name="convert">
        <el-form label-width="70px" size="small">
          <el-form-item label="方向">
            <el-radio-group v-model="convert.direction">
              <el-radio label="hex2text">HEX→文本</el-radio>
              <el-radio label="text2hex">文本→HEX</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="编码">
            <el-select v-model="convert.encoding" style="width:100%">
              <el-option value="utf-8" label="UTF-8" />
              <el-option value="gbk" label="GBK" />
            </el-select>
          </el-form-item>
          <el-form-item label="内容">
            <el-input v-model="convert.data" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="doConvert">转换</el-button>
          </el-form-item>
        </el-form>
        <div v-if="convertResult" class="result">
          <div class="result-label">结果：</div>
          <div class="result-text">{{ convertResult }}</div>
        </div>
      </el-tab-pane>

      <!-- JSON 格式化 -->
      <el-tab-pane label="JSON" name="json">
        <el-input v-model="jsonInput" type="textarea" :rows="6" placeholder="粘贴 JSON 文本" />
        <div style="margin-top:8px;display:flex;gap:8px">
          <el-button size="small" type="primary" @click="formatJson">格式化</el-button>
          <el-button size="small" @click="minifyJson">压缩</el-button>
        </div>
        <div v-if="jsonOutput" class="result">
          <pre class="json-out">{{ jsonOutput }}</pre>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { toolboxApi } from '../api'

const tab = ref('check')

const check = reactive({ algorithm: 'crc16', format: 'hex', data: '' })
const checkResult = ref('')

const convert = reactive({ direction: 'hex2text', encoding: 'utf-8', data: '' })
const convertResult = ref('')

const jsonInput = ref('')
const jsonOutput = ref('')

async function doCheck() {
  if (!check.data) { ElMessage.warning('请输入数据'); return }
  try {
    const res = await toolboxApi.check(check.algorithm, check.data, check.format)
    checkResult.value = res.data.hex
  } catch (e) {
    ElMessage.error('计算失败: ' + e.message)
  }
}

async function doConvert() {
  if (!convert.data) { ElMessage.warning('请输入内容'); return }
  try {
    const from = convert.direction === 'hex2text' ? 'hex' : 'text'
    const to = convert.direction === 'hex2text' ? 'text' : 'hex'
    const res = await toolboxApi.convert(convert.data, from, to, convert.encoding)
    convertResult.value = res.data.result
  } catch (e) {
    ElMessage.error('转换失败: ' + e.message)
  }
}

function formatJson() {
  try {
    jsonOutput.value = JSON.stringify(JSON.parse(jsonInput.value), null, 2)
  } catch (e) {
    ElMessage.error('JSON 格式错误')
  }
}

function minifyJson() {
  try {
    jsonOutput.value = JSON.stringify(JSON.parse(jsonInput.value))
  } catch (e) {
    ElMessage.error('JSON 格式错误')
  }
}
</script>

<style scoped>
.head { margin-bottom: 8px; }
.t { font-size: 14px; font-weight: 600; color: #303133; }
.result { margin-top: 8px; padding: 8px; background: #f5f7fa; border-radius: 6px; font-size: 13px; }
.result-label { font-size: 12px; color: #606266; }
.result-text { word-break: break-all; font-family: Consolas, Monaco, monospace; }
.json-out { font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
</style>
