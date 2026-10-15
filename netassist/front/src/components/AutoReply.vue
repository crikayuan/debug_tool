<template>
  <div>
    <div class="head">
      <span class="t">自动应答</span>
      <el-button size="small" @click="openAdd">新增</el-button>
    </div>
    <div class="list">
      <div v-for="(r, i) in store.autoReplyRules" :key="i" class="item">
        <el-switch v-model="r.enabled" size="small" />
        <div class="info">
          <div class="name">{{ r.name }}</div>
          <div class="m">{{ r.match }} → {{ r.reply }}</div>
        </div>
        <el-button size="small" text type="danger" @click="store.autoReplyRules.splice(i, 1)">删</el-button>
      </div>
      <div v-if="!store.autoReplyRules.length" class="empty">暂无规则</div>
    </div>

    <el-dialog v-model="dialogVisible" title="新增自动应答规则" width="440px">
      <el-form label-width="80px" size="small">
        <el-form-item label="规则名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="匹配类型">
          <el-radio-group v-model="form.matchType">
            <el-radio label="contains">包含匹配</el-radio>
            <el-radio label="regex">正则匹配</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="匹配内容"><el-input v-model="form.match" /></el-form-item>
        <el-form-item label="回复内容"><el-input v-model="form.reply" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="回复格式">
          <el-radio-group v-model="form.replyFormat">
            <el-radio label="text">文本</el-radio>
            <el-radio label="hex">HEX</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="延时(ms)"><el-input-number v-model="form.delay" :min="0" :max="60000" :step="100" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { store } from '../store'

const dialogVisible = ref(false)
const form = reactive({ name: '', matchType: 'contains', match: '', reply: '', replyFormat: 'text', delay: 0 })

function openAdd() {
  Object.assign(form, { name: '', matchType: 'contains', match: '', reply: '', replyFormat: 'text', delay: 0 })
  dialogVisible.value = true
}

function save() {
  if (!form.name || !form.match) { ElMessage.warning('规则名和匹配内容不能为空'); return }
  store.autoReplyRules.push({ enabled: true, ...form })
  dialogVisible.value = false
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.t { font-size: 14px; font-weight: 600; color: #303133; }
.list { display: flex; flex-direction: column; gap: 6px; }
.item { display: flex; align-items: center; gap: 8px; padding: 6px; background: #f5f7fa; border-radius: 6px; }
.info { flex: 1; min-width: 0; }
.name { font-size: 13px; font-weight: 600; }
.m { font-size: 12px; color: #606266; word-break: break-all; }
.empty { text-align: center; color: #999; padding: 16px; }
</style>
