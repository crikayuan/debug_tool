<template>
  <div>
    <div class="head"><span class="t">设置</span></div>
    <el-form label-width="90px" size="small">
      <el-form-item label="主题">
        <el-radio-group v-model="store.settings.theme">
          <el-radio label="light">浅色</el-radio>
          <el-radio label="dark">深色</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="接收编码">
        <el-select v-model="store.settings.recvEncoding" style="width:100%">
          <el-option value="utf-8" label="UTF-8" />
          <el-option value="gbk" label="ANSI(GBK)" />
        </el-select>
      </el-form-item>
      <el-form-item label="发送编码">
        <el-select v-model="store.settings.sendEncoding" style="width:100%">
          <el-option value="utf-8" label="UTF-8" />
          <el-option value="gbk" label="ANSI(GBK)" />
        </el-select>
      </el-form-item>
      <el-form-item label="显示时间戳">
        <el-switch v-model="store.settings.showTimestamp" />
      </el-form-item>
      <el-form-item label="自动滚动">
        <el-switch v-model="store.settings.autoScroll" />
      </el-form-item>
      <el-form-item label="自动换行">
        <el-switch v-model="store.settings.lineWrap" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { store } from '../store'
</script>

<style scoped>
.head { margin-bottom: 8px; }
.t { font-size: 14px; font-weight: 600; color: #303133; }
</style>
