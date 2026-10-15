<template>
  <div class="debug-view" :class="{ dark: store.settings.theme === 'dark' }">
    <!-- 标题栏 -->
    <header class="title-bar">
      <div class="title-left">
        <span class="app-title">调试助手 <span class="app-ver">v{{ APP_VERSION }}</span></span>
        <el-radio-group v-model="mode" size="small" class="mode-switch">
          <el-radio-button label="network">网络调试</el-radio-button>
          <el-radio-button label="serial">串口调试</el-radio-button>
          <el-radio-button label="mqtt">MQTT调试</el-radio-button>
          <el-radio-button label="scan">网络扫描</el-radio-button>
          <el-radio-button label="httpd">HTTP Server</el-radio-button>
        </el-radio-group>
      </div>
      <div class="title-right">
        <el-tag v-if="mode === 'scan'" :type="scanTagType" size="small" effect="dark">
          {{ scanTagText }}
        </el-tag>
        <el-tag v-else-if="mode === 'httpd'" :type="httpdTagType" size="small" effect="dark">
          {{ httpdTagText }}
        </el-tag>
        <el-tag v-else :type="isConnected ? 'success' : 'info'" size="small" effect="dark">
          {{ isConnected ? '已连接' : '未连接' }}
        </el-tag>
        <el-button size="small" text class="panel-btn" @click="toggleLeft">
          {{ leftOpen ? '隐藏参数' : '参数设置' }}
        </el-button>
        <el-button v-if="mode !== 'scan' && mode !== 'httpd'" size="small" text class="panel-btn" @click="toggleRight">
          {{ rightOpen ? '隐藏模块' : '模块面板' }}
        </el-button>
      </div>
    </header>

    <div class="main-body" ref="bodyRef">
      <!-- 左栏：网络扫描 / HTTP Server 模式下替换为对应设置 -->
      <aside class="left-panel" v-show="leftOpen">
        <ScanSettings
          v-if="mode === 'scan'"
          :segments="scanSegments"
          :running="scanRunning"
          :status="scanStatus"
          :active-index="scanHistoryIndex"
          @start="startScan"
          @stop="stopScan"
          @select-history="selectScanHistory"
        />
        <HttpServerSettings
          v-else-if="mode === 'httpd'"
          :status="store.httpServerStatus"
          :running="httpdRunning"
          :loading="httpdStarting"
          @start="startHttpd"
          @stop="stopHttpd"
          @response-change="onHttpdResponseChange"
        />
        <template v-else>
        <div class="panel-head">
          <span class="panel-title">连接设置</span>
        </div>
        <div class="panel-scroll">
          <el-collapse v-model="openSections" class="side-collapse">
            <!-- 连接参数 -->
            <el-collapse-item title="连接参数" name="conn">
              <el-form label-width="70px" size="small" class="config-form">
                <!-- 网络设置 -->
                <template v-if="mode === 'network'">
                  <el-form-item label="协议">
                    <el-select v-model="netConfig.protocol" :disabled="isConnected" style="width:100%">
                      <el-option label="TCP Client" value="tcp" />
                      <el-option label="TCP Server" value="tcp_server" />
                      <el-option label="UDP" value="udp" />
                    </el-select>
                  </el-form-item>
                  <el-form-item :label="isServer ? '本地IP' : '远程主机'">
                    <el-select v-if="isServer" v-model="netConfig.host" :disabled="isConnected" style="width:100%" filterable allow-create>
                      <el-option v-for="ip in localIps" :key="ip" :label="ipLabel(ip)" :value="ip" />
                    </el-select>
                    <el-input v-else v-model="netConfig.host" :disabled="isConnected" />
                  </el-form-item>
                  <el-form-item :label="isServer ? '本地端口' : '远程端口'">
                    <el-input v-model.number="netConfig.port" type="number" :disabled="isConnected" />
                  </el-form-item>
                </template>

                <!-- 串口设置 -->
                <template v-else-if="mode === 'serial'">
                  <el-form-item label="串口号">
                    <div class="row-flex">
                      <el-select v-model="serialConfig.port" :disabled="isConnected" style="flex:1;min-width:0">
                        <el-option v-for="p in serialPorts" :key="p.device" :label="`${p.device} - ${p.description}`" :value="p.device" />
                      </el-select>
                      <el-button @click="refreshPorts" :disabled="isConnected">刷新</el-button>
                    </div>
                  </el-form-item>
                  <el-form-item label="波特率">
                    <el-select v-model="serialConfig.baud_rate" :disabled="isConnected" style="width:100%" filterable allow-create>
                      <el-option v-for="b in baudRates" :key="b" :label="b" :value="b" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="数据位">
                    <el-select v-model="serialConfig.data_bits" :disabled="isConnected" style="width:100%">
                      <el-option :value="8" label="8" />
                      <el-option :value="7" label="7" />
                      <el-option :value="6" label="6" />
                      <el-option :value="5" label="5" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="停止位">
                    <el-select v-model="serialConfig.stop_bits" :disabled="isConnected" style="width:100%">
                      <el-option :value="1" label="1" />
                      <el-option :value="1.5" label="1.5" />
                      <el-option :value="2" label="2" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="校验位">
                    <el-select v-model="serialConfig.parity" :disabled="isConnected" style="width:100%">
                      <el-option value="none" label="无" />
                      <el-option value="odd" label="奇校验" />
                      <el-option value="even" label="偶校验" />
                      <el-option value="mark" label="Mark" />
                      <el-option value="space" label="Space" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="流控">
                    <el-select v-model="serialConfig.flow_control" :disabled="isConnected" style="width:100%">
                      <el-option value="none" label="无" />
                      <el-option value="hardware" label="硬件" />
                      <el-option value="software" label="软件" />
                    </el-select>
                  </el-form-item>
                </template>

                <!-- MQTT 设置 -->
                <template v-else>
                  <el-form-item label="Broker">
                    <el-input v-model="store.mqttConfig.host" :disabled="isConnected" placeholder="broker.emqx.io" />
                  </el-form-item>
                  <el-form-item label="端口">
                    <el-input v-model.number="store.mqttConfig.port" type="number" :disabled="isConnected" />
                  </el-form-item>
                  <el-form-item label="ClientID">
                    <el-input v-model="store.mqttConfig.clientId" :disabled="isConnected" placeholder="留空自动生成" />
                  </el-form-item>
                  <el-form-item label="用户名">
                    <el-input v-model="store.mqttConfig.username" :disabled="isConnected" placeholder="可选" />
                  </el-form-item>
                  <el-form-item label="密码">
                    <el-input v-model="store.mqttConfig.password" type="password" :disabled="isConnected" placeholder="可选" show-password />
                  </el-form-item>
                  <el-form-item label="会话">
                    <div class="row-flex" style="gap:14px">
                      <el-checkbox v-model="store.mqttConfig.clean" :disabled="isConnected" size="small">Clean</el-checkbox>
                      <el-checkbox v-model="store.mqttConfig.reconnect" :disabled="isConnected" size="small">自动重连</el-checkbox>
                    </div>
                  </el-form-item>
                  <el-form-item label="心跳">
                    <el-input v-model.number="store.mqttConfig.keepalive" type="number" :disabled="isConnected" />
                  </el-form-item>
                  <div class="hint-row">
                    <span class="muted-text">默认 MQTT 3.1.1；TLS / 遗嘱 / 5.0 / WebSocket 二期支持</span>
                  </div>
                </template>
              </el-form>
            </el-collapse-item>

            <!-- 显示设置 -->
            <el-collapse-item title="显示设置" name="display">
              <div class="opt-list">
                <el-checkbox v-model="store.settings.showTimestamp" size="small">显示时间</el-checkbox>
                <el-checkbox v-model="hexDisplay" size="small">HEX 显示</el-checkbox>
                <el-checkbox v-model="store.settings.autoScroll" size="small">自动滚动</el-checkbox>
                <el-checkbox v-model="store.settings.lineWrap" size="small">自动换行</el-checkbox>
              </div>
              <div class="hint-row">
                <span v-if="store.settings.pauseDisplay" class="warn-text">
                  已暂停，待显示 {{ store.pendingLines.length }} 行（在发送区点「继续显示」恢复）
                </span>
                <span v-else class="muted-text">日志保留最近 2000 行</span>
              </div>
            </el-collapse-item>

            <!-- 发送设置 -->
            <el-collapse-item title="发送设置" name="sendset">
              <div class="opt-list">
                <el-checkbox v-model="loopSending" size="small" @change="toggleLoop">循环发送</el-checkbox>
                <div class="row-flex">
                  <span class="opt-label">周期</span>
                  <el-input-number v-model="loopInterval" :min="1" :max="3600000" :step="100" size="small" controls-position="right" style="flex:1;min-width:0" />
                  <span class="opt-label">ms</span>
                </div>
                <div class="row-flex">
                  <span class="opt-label">结束符</span>
                  <el-select v-model="endChars" size="small" style="flex:1;min-width:0" placeholder="无">
                    <el-option value="" label="无" />
                    <el-option value="\n" label="\\n" />
                    <el-option value="\r\n" label="\\r\\n" />
                  </el-select>
                </div>
              </div>
              <div class="hint-row">
                <span class="muted-text">循环内容取发送框当前内容</span>
              </div>
            </el-collapse-item>

            <!-- 数据保存 -->
            <el-collapse-item title="数据保存" name="save">
              <div class="opt-list">
                <el-checkbox v-model="autoSave.enabled" size="small" @change="toggleAutoSave">持续保存到文件</el-checkbox>
                <el-form label-width="52px" size="small" class="config-form">
                  <el-form-item label="文件名">
                    <el-input v-model="autoSave.filename" placeholder="debug_20260101.txt" />
                  </el-form-item>
                  <el-form-item label="目录">
                    <div class="row-flex">
                      <el-input v-model="autoSave.directory" placeholder="留空存到程序目录" />
                      <el-button @click="chooseAutoSaveDir" size="small">浏览</el-button>
                    </div>
                  </el-form-item>
                </el-form>
              </div>
              <div class="hint-row">
                <span v-if="autoSave.enabled" class="ok-text">已写入 {{ formatBytes(autoSave.bytes) }}</span>
                <span v-else class="muted-text">开启后实时追加写入</span>
              </div>
            </el-collapse-item>

          </el-collapse>
        </div>

        <!-- 收发统计：固定在左栏底部，无需滚动 -->
        <div class="stat-bar">
          <div class="stat-row">
            <span class="stat-label">接收</span>
            <span class="stat-value">{{ formatBytes(store.stats.rxBytes) }}</span>
            <span class="stat-count">{{ store.stats.rxCount }} 包</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">发送</span>
            <span class="stat-value">{{ formatBytes(store.stats.txBytes) }}</span>
            <span class="stat-count">{{ store.stats.txCount }} 包</span>
          </div>
          <el-button size="small" style="width:100%;margin-top:6px" @click="resetStats">计数清零</el-button>
        </div>

        <div class="panel-foot">
          <el-button :type="isConnected ? 'danger' : 'primary'" style="width:100%" @click="toggleConnect" :loading="connecting">
            {{ isConnected ? '断开连接' : '打开连接' }}
          </el-button>
        </div>
        </template>
      </aside>

      <!-- 中栏：网络扫描 / HTTP Server 模式下替换为对应面板 -->
      <main class="center-panel">
        <ScanResultTable
          v-if="mode === 'scan'"
          :results="store.scanResults"
          :progress="store.scanProgress"
          :changes="store.scanChanges"
          :change-list="store.scanChangeList"
          :running="scanRunning"
          @export="exportScan"
          @clear="clearScanResultsAndState"
          @use-ip="useScanIp"
        />
        <HttpServerCenter
          v-else-if="mode === 'httpd'"
          :requests="store.httpServerRequests"
          :status="store.httpServerStatus"
          :running="httpdRunning"
          :selected="store.httpServerSelected"
          @select="selectHttpRecord"
          @close-detail="closeHttpDetail"
          @export="exportHttpLog"
          @clear="clearHttpRecordsAndState"
        />
        <template v-else>
        <section class="log-panel">
          <div class="log-toolbar">
            <span class="panel-title">{{ mode === 'mqtt' ? '消息记录' : '数据日志' }}</span>
            <div class="toolbar-actions">
              <el-select v-model="recvFormat" size="small" class="sel-fmt">
                <el-option value="text" label="文本" />
                <el-option value="hex" label="HEX" />
              </el-select>
              <el-select v-model="store.settings.recvEncoding" size="small" class="sel-enc">
                <el-option value="utf-8" label="UTF-8" />
                <el-option value="gbk" label="GBK" />
              </el-select>
              <div class="btn-pair">
                <el-button size="small" @click="openSaveLog">保存</el-button>
                <el-button size="small" @click="clearLog">清空</el-button>
              </div>
            </div>
          </div>
          <!-- MQTT 连接信息条 -->
          <div v-if="mode === 'mqtt'" class="conn-bar">
            <div class="conn-info">
              <div class="conn-dot" :class="{ off: !isConnected }"></div>
              <span>Broker: <b>{{ mqttHostLabel }}</b></span>
              <span>ClientID: <b>{{ store.mqttConnInfo.clientId || '—' }}</b></span>
              <span>订阅: <b>{{ store.mqttSubscriptions.length }}</b> 个主题</span>
            </div>
            <el-button type="danger" size="small" @click="toggleConnect">断开连接</el-button>
          </div>

          <!-- 消息卡片列表（MQTT） -->
          <div v-if="mode === 'mqtt'" class="mqtt-msg-list" ref="mqttListRef">
            <MqttMessageCard v-for="(m, i) in store.mqttMessages" :key="i" :msg="m" />
            <div v-if="store.mqttMessages.length === 0" class="log-empty">暂无消息</div>
          </div>

          <!-- 日志列表（网络 / 串口） -->
          <div v-else class="log-list" ref="logListRef" :class="{ 'no-wrap': !store.settings.lineWrap }">
            <div v-for="(line, i) in store.logLines" :key="i" class="log-line" :class="'dir-' + line.dir.toLowerCase()">
              <span class="log-dir">{{ line.dir }}</span>
              <span v-if="store.settings.showTimestamp" class="log-time">{{ line.timeStr }}</span>
              <span v-if="line.client" class="log-client">{{ line.client }}</span>
              <span class="log-data">{{ line.display }}</span>
            </div>
            <div v-if="store.logLines.length === 0" class="log-empty">暂无数据</div>
          </div>
        </section>

        <section class="send-panel">
          <!-- 客户端管理（仅 TCP Server） -->
          <div v-if="isServer && mode === 'network'" class="client-bar">
            <span class="client-label">发送对象</span>
            <el-select v-model="sendTarget" size="small" class="client-select">
              <el-option value="all" :label="`广播全部 (${clients.length})`" />
              <el-option v-for="c in clients" :key="c.id" :value="c.id" :label="`指定: ${c.address}`" />
              <el-option v-if="selectedClients.length >= 2" :value="multiTargetValue" :label="`选中客户端 (${selectedClients.length} 台)`" />
            </el-select>
            <el-button size="small" @click="clientManageVisible = true">管理</el-button>
            <span class="client-count">{{ clients.length }} 在线</span>
          </div>

          <!-- 发布主题（仅 MQTT） -->
          <div v-if="mode === 'mqtt'" class="topic-row">
            <span class="opt-label">发布主题</span>
            <el-input v-model="store.mqttConfig.publishTopic" size="small" class="topic-input" placeholder="例如 berth/cmd/001" />
            <el-select v-model="store.mqttConfig.publishQos" size="small" class="pub-qos">
              <el-option :value="0" label="QoS 0" />
              <el-option :value="1" label="QoS 1" />
              <el-option :value="2" label="QoS 2" />
            </el-select>
            <el-checkbox v-model="store.mqttConfig.publishRetain" size="small">Retain</el-checkbox>
          </div>

          <div class="send-opts">
            <el-radio-group v-model="sendFormat" size="small">
              <el-radio-button label="text">文本</el-radio-button>
              <el-radio-button label="hex">HEX</el-radio-button>
            </el-radio-group>
            <div class="opt-group">
              <span class="opt-label">结束符</span>
              <el-select v-model="endChars" size="small" class="sel-end" placeholder="无">
                <el-option value="" label="无" />
                <el-option value="\n" label="\\n" />
                <el-option value="\r\n" label="\\r\\n" />
              </el-select>
            </div>
            <div class="opt-group">
              <span class="opt-label">校验</span>
              <el-select v-model="appendCheck" size="small" class="sel-chk" placeholder="无">
                <el-option value="" label="无" />
                <el-option value="sum" label="Sum" />
                <el-option value="xor" label="XOR" />
                <el-option value="lrc" label="LRC" />
                <el-option value="crc16" label="CRC16" />
                <el-option value="fcs" label="FCS" />
              </el-select>
            </div>
            <div class="send-actions">
              <el-button v-if="store.settings.pauseDisplay" type="warning" size="small" class="pause-btn" @click="togglePauseDisplay">
                继续显示{{ pendingCount ? ` (${pendingCount})` : '' }}
              </el-button>
              <el-button v-else size="small" class="pause-btn pause-idle" @click="togglePauseDisplay">
                暂停显示
              </el-button>
              <el-button type="primary" size="small" @click="doSend" :disabled="!isConnected">发送</el-button>
              <el-button size="small" @click="sendText = ''">清空</el-button>
            </div>
          </div>
          <el-input v-model="sendText" type="textarea" :rows="3" resize="none" placeholder="请输入要发送的数据" class="send-input" />
        </section>
        </template>
      </main>

      <!-- 右栏：功能模块（与中栏并排共存，宽度可拖动）；网络扫描 / HTTP Server 模式隐藏 -->
      <div v-if="mode !== 'scan' && mode !== 'httpd' && rightOpen" class="v-splitter" :class="{ dragging }" title="拖动调整宽度"
           @mousedown="onSplitterDown"></div>
      <aside v-if="mode !== 'scan' && mode !== 'httpd'" class="right-panel" :class="{ collapsed: !rightOpen }"
             :style="rightOpen ? { width: rightWidth + 'px' } : null">
        <div class="module-nav" :class="{ vertical: !rightOpen }">
          <div v-for="m in modules" :key="m.key" class="module-tab" :class="{ active: activeModule === m.key && rightOpen }"
               :title="m.label" @click="selectModule(m.key)">
            {{ rightOpen ? m.label : m.short }}
          </div>
          <div class="nav-toggle" :title="rightOpen ? '收起面板' : '展开面板'" @click="toggleRight">
            {{ rightOpen ? '»' : '«' }}
          </div>
        </div>
        <div class="module-content" v-show="rightOpen">
          <QuickCommands v-if="activeModule === 'quick'" />
          <BatchSend v-else-if="activeModule === 'batch'" />
          <HistorySend v-else-if="activeModule === 'history'" />
          <AutoReply v-else-if="activeModule === 'reply'" />
          <ModbusPanel v-else-if="activeModule === 'modbus'" />
          <ToolboxPanel v-else-if="activeModule === 'toolbox'" />
          <SettingsPanel v-else-if="activeModule === 'settings'" />
          <MqttSubscriptions v-else-if="activeModule === 'sub'" />
        </div>
      </aside>
    </div>

    <!-- 保存日志弹窗 -->
    <el-dialog v-model="saveLogDialogVisible" title="保存日志" width="520px">
      <el-form label-width="90px" size="small">
        <el-form-item label="文件名">
          <el-input v-model="logSave.filename" />
        </el-form-item>
        <el-form-item label="目录">
          <div class="row-flex">
            <el-input v-model="logSave.directory" placeholder="留空保存到程序目录" />
            <el-button @click="chooseDir">浏览</el-button>
          </div>
        </el-form-item>
        <el-form-item label="内容范围">
          <el-select v-model="logSave.scope" style="width:100%">
            <el-option value="all" label="全部" />
            <el-option value="rx" label="仅接收" />
            <el-option value="tx" label="仅发送" />
          </el-select>
        </el-form-item>
        <el-form-item label="行格式">
          <el-select v-model="logSave.lineFormat" style="width:100%">
            <el-option value="timestamp" label="含时间戳" />
            <el-option value="raw" label="纯数据" />
            <el-option value="hex" label="纯HEX" />
          </el-select>
        </el-form-item>
        <el-form-item label="编码">
          <el-select v-model="logSave.encoding" style="width:100%">
            <el-option value="utf-8" label="UTF-8" />
            <el-option value="utf-8-bom" label="UTF-8+BOM" />
            <el-option value="gbk" label="ANSI(GBK)" />
          </el-select>
        </el-form-item>
      </el-form>
      <div class="log-preview">预计导出 {{ previewCount }} 行</div>
      <template #footer>
        <el-button @click="saveLogDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="doSaveLog">保存</el-button>
      </template>
    </el-dialog>

    <!-- 客户端管理弹窗 -->
    <el-dialog v-model="clientManageVisible" title="客户端管理" width="460px">
      <el-table :data="clients" size="small" @selection-change="onClientSelect">
        <el-table-column type="selection" width="45" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="address" label="地址" />
        <el-table-column label="操作" width="80">
          <template #default="scope">
            <el-button size="small" type="danger" text @click="kickClient(scope.row)">断开</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="clients.length === 0" class="client-empty">暂无连接的客户端</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, provide, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { store, addHistory, addLogLine, clearLogLines, resetStats, flushPendingLines, initStore, addMqttMessage, flushPendingMessages, clearMqttMessages, upsertScanResult, clearScanResults, sortScanRows } from '../store'
import { netApi, serialApi, logApi, systemApi, mqttApi, scanApi, httpServerApi } from '../api'
import { formatTime, nowTs, textToHex, normalizeHex, matchTopic } from '../utils'
import QuickCommands from '../components/QuickCommands.vue'
import BatchSend from '../components/BatchSend.vue'
import HistorySend from '../components/HistorySend.vue'
import AutoReply from '../components/AutoReply.vue'
import ModbusPanel from '../components/ModbusPanel.vue'
import ToolboxPanel from '../components/ToolboxPanel.vue'
import SettingsPanel from '../components/SettingsPanel.vue'
import MqttSubscriptions from '../components/MqttSubscriptions.vue'
import MqttMessageCard from '../components/MqttMessageCard.vue'
import ScanSettings from '../components/ScanSettings.vue'
import ScanResultTable from '../components/ScanResultTable.vue'
import HttpServerSettings from '../components/HttpServerSettings.vue'
import HttpServerCenter from '../components/HttpServerCenter.vue'

// 右栏模块：基础 7 项 + MQTT 模式插入「订阅」Tab
const modules = computed(() => {
  const base = [
    { key: 'quick', label: '快捷指令', short: '快捷' },
    { key: 'batch', label: '批量发送', short: '批量' },
    { key: 'history', label: '历史发送', short: '历史' },
    { key: 'reply', label: '自动应答', short: '应答' }
  ]
  if (mode.value === 'mqtt') base.push({ key: 'sub', label: '订阅', short: '订阅' })
  base.push(
    { key: 'modbus', label: 'Modbus', short: 'MBus' },
    { key: 'toolbox', label: '工具箱', short: '工具' },
    { key: 'settings', label: '设置', short: '设置' }
  )
  return base
})

const mode = ref('network')
const APP_VERSION = '1.3.1'
const activeModule = ref('quick')
const isConnected = ref(false)
const connecting = ref(false)
const connectionId = ref('')
const ws = ref(null)

const baudRates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

const netConfig = reactive({ protocol: 'tcp', host: '127.0.0.1', port: 8000 })
const serialConfig = reactive({
  port: '', baud_rate: 9600, data_bits: 8, stop_bits: 1,
  parity: 'none', flow_control: 'none', dtr: false, rts: false
})
const serialPorts = ref([])
const localIps = ref(['0.0.0.0', '127.0.0.1'])
const ipLabels = ref({})

const sendText = ref('')
const sendFormat = ref('hex')
const endChars = ref('')
const appendCheck = ref('')
const recvFormat = ref('text')

const clients = ref([])
const selectedClients = ref([])
const sendTarget = ref('all')
const clientManageVisible = ref(false)

const saveLogDialogVisible = ref(false)

/* ==================================================================
 * 网络扫描（第四模式）
 * ================================================================== */
const scanSegments = ref([])
const scanRunning = ref(false)
const scanStatus = ref('idle') // idle | running | done | stopped
const scanTaskId = ref('')
const scanHistoryIndex = ref(-1)
let scanWs = null

/* ==================================================================
 * HTTP Server（第五模式）
 * ================================================================== */
const httpdRunning = ref(false)
const httpdStarting = ref(false)
const httpdSessionId = ref('')
let httpdWs = null
// status 周期刷新定时器（运行中每 1s 取一次）
let httpdStatusTimer = null
let httpdElapsedTimer = null

const httpdTagText = computed(() => httpdRunning.value ? '运行中' : '未启动')
const httpdTagType = computed(() => httpdRunning.value ? 'success' : 'info')

const scanTagText = computed(() => ({
  idle: '空闲',
  running: '扫描中',
  done: '完成',
  stopped: '已停止'
}[scanStatus.value] || '空闲'))
const scanTagType = computed(() => ({
  idle: 'info',
  running: '',
  done: 'success',
  stopped: 'warning'
}[scanStatus.value] || 'info'))

async function loadScanSegments() {
  try {
    const res = await scanApi.getSegments()
    scanSegments.value = res.data?.segments || []
  } catch (e) {
    console.error('获取本机网段失败:', e)
    scanSegments.value = []
  }
}

// 开始扫描：DebugView 负责编排（与 net/serial/mqtt 一致）
async function startScan(cfg) {
  clearScanResults()
  store.scanChangeList = { new: [], left: [], changed: [] }
  store.scanProgress = { scanned: 0, total: 0, online: 0, offline: 0, occupied: 0, utilization: 0, cidr: cfg.segment || '', elapsed: 0, status: 'running' }
  scanHistoryIndex.value = -1
  scanStatus.value = 'running'

  const payload = {
    start_ip: cfg.startIp,
    end_ip: cfg.endIp,
    method: cfg.method || 'arp_tcp',
    concurrency: cfg.concurrency,
    timeout_ms: cfg.timeoutMs,
    vendor_lookup: !!cfg.vendorLookup,
    resolve_hostname: !!cfg.resolveHostname,
    port_scan: !!cfg.portScan,
    ports: cfg.portScan ? (cfg.ports || []) : []
  }

  try {
    const res = await scanApi.start(payload)
    if (!res || res.success === false) {
      ElMessage.error(res?.message || '启动扫描失败')
      scanStatus.value = 'idle'
      return
    }
    scanTaskId.value = res.data?.task_id
    store.scanProgress.total = res.data?.total || 0
    if (scanWs) { try { scanWs.close() } catch (e) { /* ignore */ } }
    scanWs = scanApi.createWebSocket(scanTaskId.value, onScanMessage, () => { scanWs = null }, onScanWsError)
    scanRunning.value = true
    ElMessage.success(`开始扫描 ${res.data?.total || 0} 个地址`)
  } catch (e) {
    ElMessage.error('启动扫描失败: ' + e.message)
    scanStatus.value = 'idle'
  }
}

async function stopScan() {
  if (!scanTaskId.value) { scanRunning.value = false; scanStatus.value = 'stopped'; return }
  try {
    await scanApi.stop(scanTaskId.value)
    scanRunning.value = false
    scanStatus.value = 'stopped'
    ElMessage.info('已请求停止扫描')
  } catch (e) {
    ElMessage.error('停止失败: ' + e.message)
  }
}

function onScanWsError(e) {
  console.error('扫描 WS错误:', e)
}

function onScanMessage(frame) {
  if (!frame || !frame.type) return
  if (frame.type === 'progress') {
    store.scanProgress = {
      scanned: frame.scanned || 0,
      total: frame.total || store.scanProgress.total,
      online: frame.online || 0,
      offline: frame.offline || 0,
      occupied: frame.occupied || 0,
      utilization: frame.utilization || 0,
      cidr: frame.cidr || store.scanProgress.cidr || '',
      elapsed: frame.elapsed || 0,
      status: 'running'
    }
  } else if (frame.type === 'result') {
    upsertScanResult(frame.item)
  } else if (frame.type === 'done') {
    store.scanProgress = {
      scanned: frame.scanned ?? store.scanProgress.scanned,
      total: frame.total ?? store.scanProgress.total,
      online: frame.online ?? store.scanProgress.online,
      offline: frame.offline ?? store.scanProgress.offline,
      occupied: frame.occupied ?? store.scanProgress.occupied,
      utilization: frame.utilization ?? store.scanProgress.utilization,
      cidr: frame.cidr || store.scanProgress.cidr || '',
      elapsed: frame.elapsed ?? store.scanProgress.elapsed,
      status: frame.status || 'done'
    }
    // 写入服务端推过来的变化列表（new/left/changed）
    if (frame.changes) {
      store.scanChangeList = frame.changes
    }
    scanRunning.value = false
    scanStatus.value = frame.status === 'stopped' ? 'stopped' : 'done'
    finalizeScan()
  }
}

// 扫描结束：与上次结果比对，写入扫描历史（保留最近 10 次）
function finalizeScan() {
  const items = store.scanResults.slice()
  const prev = store.scanHistory[0]
  const hasPrev = !!(prev && Array.isArray(prev.devices) && prev.devices.length)
  const prevMap = {}
  if (hasPrev) {
    prev.devices.forEach(d => { if (d.mac) prevMap[d.ip] = d.mac })
  }

  // 仅在有上一次扫描结果时才有「新增 / 变化」的可比基线
  const changeMap = {}
  let newCount = 0
  let changedCount = 0
  if (hasPrev) {
    items.forEach(r => {
      if (!r.mac) return
      if (!(r.ip in prevMap)) {
        changeMap[r.ip] = { type: 'new', text: '与上次扫描相比新增的设备' }
        newCount += 1
      } else if (prevMap[r.ip] && prevMap[r.ip] !== r.mac) {
        changeMap[r.ip] = {
          type: 'changed',
          from: prevMap[r.ip],
          to: r.mac,
          text: `与上次扫描相比 MAC 由 ${prevMap[r.ip]} 变为 ${r.mac}，可能存在 IP 冲突`
        }
        changedCount += 1
      }
    })
  }
  store.scanChanges = changeMap

  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const time = `${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
  const cfg = store.scanConfig
  const entry = {
    time,
    seg: cfg.startIp && cfg.endIp ? `${cfg.startIp}-${cfg.endIp}` : '',
    total: store.scanProgress.total,
    online: items.filter(r => r.online).length,
    delta: newCount ? `新增 ${newCount}` : (changedCount ? `${changedCount} 项变化` : '—'),
    deltaCls: newCount ? 'new' : (changedCount ? 'warn' : ''),
    devices: items.map(r => ({
      ip: r.ip, mac: r.mac || '', vendor: r.vendor || '', hostname: r.hostname || '',
      delay_ms: r.delay_ms || 0, ports: r.ports || [], online: !!r.online
    }))
  }
  store.scanHistory.unshift(entry)
  if (store.scanHistory.length > 10) store.scanHistory.length = 10
}

// 点击历史条目：加载该次结果用于对照
function selectScanHistory(index) {
  const h = store.scanHistory[index]
  if (!h) return
  scanHistoryIndex.value = index
  store.scanChanges = {}
  store.scanChangeList = { new: [], left: [], changed: [] }
  store.scanResults = (h.devices || []).map(d => ({ ...d }))
  const online = store.scanResults.filter(d => d.online).length
  const occupied = store.scanResults.length
  const total = h.total || occupied
  store.scanProgress = {
    scanned: total, total,
    online, offline: Math.max(0, occupied - online),
    occupied, utilization: total ? Math.round(occupied * 100 / total * 100) / 100 : 0,
    cidr: '', elapsed: 0, status: 'done'
  }
  scanStatus.value = 'done'
  ElMessage.info(`已加载 ${h.time} 的扫描结果`)
}

// 清空结果（不清历史）
function clearScanResultsAndState() {
  clearScanResults()
  store.scanProgress = { scanned: 0, total: 0, online: 0, offline: 0, occupied: 0, utilization: 0, cidr: '', elapsed: 0, status: 'idle' }
  store.scanChangeList = { new: [], left: [], changed: [] }
  scanStatus.value = 'idle'
  scanHistoryIndex.value = -1
}

// 一键跳转网络调试：协议 tcp + 模式 client + host 填该 IP
function useScanIp(item) {
  if (!item || !item.ip) return
  netConfig.protocol = 'tcp'
  netConfig.host = item.ip
  mode.value = 'network'
  ElMessage.success(`已切换到网络调试，目标 ${item.ip}`)
}

// 导出 CSV（含备注；桌面端复用 pywebview 目录选择）
async function exportScan() {
  const items = sortScanRows(store.scanResults, store.scanFavorites).map(r => ({
    ip: r.ip,
    mac: r.mac || '',
    vendor: r.vendor || '',
    hostname: r.hostname || '',
    delay_ms: r.delay_ms || 0,
    ports: r.ports || [],
    online: !!r.online,
    note: store.scanNotes[r.ip] || ''
  }))
  if (!items.length) { ElMessage.warning('没有可导出的结果'); return }

  let directory = localStorage.getItem('na_scan_dir') || ''
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_dir) {
      const dir = await window.pywebview.api.choose_dir()
      if (dir) {
        directory = dir
        localStorage.setItem('na_scan_dir', dir)
      }
    } else {
      ElMessage.info('在线版将导出到程序目录')
    }
  } catch (e) { /* ignore */ }

  try {
    const res = await scanApi.exportCsv({ items, directory })
    ElMessage.success(`已导出 ${res.data?.count ?? items.length} 行：${res.data?.path || ''}`)
  } catch (e) {
    ElMessage.error('导出失败: ' + e.message)
  }
}

/* ---------- 左栏分区 ---------- */
// 默认只展开「连接参数」，其余分区保持闭合，避免左栏过挤
const openSections = ref(['conn'])

// 显示设置：HEX 显示与日志区格式下拉共用同一状态
const hexDisplay = computed({
    get: () => recvFormat.value === 'hex',
    set: (v) => { recvFormat.value = v ? 'hex' : 'text' }
})

/* ---------- 循环发送 ---------- */
const loopSending = ref(false)
const loopInterval = ref(1000)
let loopTimer = null

function stopLoop() {
    if (loopTimer) { clearInterval(loopTimer); loopTimer = null }
    loopSending.value = false
}

function toggleLoop(val) {
    if (val === false) { stopLoop(); return }
    if (!isConnected.value) {
        ElMessage.warning('请先建立连接')
        loopSending.value = false
        return
    }
    if (!sendText.value) {
        ElMessage.warning('发送框为空，无法循环发送')
        loopSending.value = false
        return
    }
    loopSending.value = true
    if (loopTimer) clearInterval(loopTimer)
    loopTimer = setInterval(() => { doSend() }, loopInterval.value)
}

// 周期变化后重启定时器，使新周期立即生效
watch(loopInterval, () => {
    if (loopSending.value && loopTimer) {
        clearInterval(loopTimer)
        loopTimer = setInterval(() => { doSend() }, loopInterval.value)
    }
})

// 断开连接时停止循环发送
watch(isConnected, (v) => { if (!v) stopLoop() })

/* ---------- 持续保存到文件 ---------- */
const autoSave = reactive({
    enabled: false,
    filename: '',
    directory: localStorage.getItem('na_log_dir') || '',
    bytes: 0
})
let saveBuffer = []
let saveTimer = null

function formatBytes(n) {
    if (n < 1024) return `${n} B`
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
    return `${(n / 1024 / 1024).toFixed(2)} MB`
}

async function flushAutoSave() {
    if (!saveBuffer.length) return
    const lines = saveBuffer
    saveBuffer = []
    const content = lines.map(l => `[${l.timeStr}] [${l.dir}]${l.client ? ' ' + l.client : ''} ${l.text}`).join('\n') + '\n'
    try {
        const res = await logApi.save({
            filename: autoSave.filename || defaultLogFilename(),
            directory: autoSave.directory || '.',
            scope: 'all',
            line_format: 'timestamp',
            encoding: 'utf-8',
            content
        })
        autoSave.bytes += res?.data?.size ? 0 : content.length
    } catch (e) {
        ElMessage.error('写入文件失败: ' + e.message)
    }
}

function toggleAutoSave(val) {
    if (val) {
        if (!autoSave.filename) autoSave.filename = defaultLogFilename()
        saveTimer = setInterval(flushAutoSave, 1000)
        ElMessage.success('已开启持续保存')
    } else {
        if (saveTimer) { clearInterval(saveTimer); saveTimer = null }
        flushAutoSave()
    }
}

async function chooseAutoSaveDir() {
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_dir) {
            const dir = await window.pywebview.api.choose_dir()
            if (dir) {
                autoSave.directory = dir
                localStorage.setItem('na_log_dir', dir)
            }
        } else {
            ElMessage.info('在线版无法读取本机目录，请手动输入完整路径')
        }
    } catch (e) {
        ElMessage.error('选择目录失败: ' + e.message)
    }
}

// 新日志行进入自动保存缓冲
watch(() => store.logLines.length, (n, old) => {
    if (autoSave.enabled && n > old) {
        saveBuffer.push(...store.logLines.slice(old))
    }
})


/* ---------- 布局自适应 ---------- */
const bodyRef = ref(null)
const bodyWidth = ref(1280)
let ro = null

// 紧凑阈值：低于此宽度时右栏自动折叠为竖条，避免中栏被挤压重叠；
// 左栏保持常驻，用户可手动在标题栏收起。
const compact = computed(() => bodyWidth.value < 980)

const leftOpen = ref(true)
const rightOpen = ref(true)
const rightWidth = ref(280)

// 拖动分隔条调整右栏宽度
const dragging = ref(false)
let dragStartX = 0
let dragStartW = 0

function onSplitterDown(e) {
    dragging.value = true
    dragStartX = e.clientX
    dragStartW = rightWidth.value
    document.addEventListener('mousemove', onSplitterMove)
    document.addEventListener('mouseup', onSplitterUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
}

// 右栏最大宽度：始终给中栏留至少 260px
const maxRightWidth = computed(() =>
    Math.max(220, bodyWidth.value - 252 - 260 - 48)
)

function onSplitterMove(e) {
    const next = dragStartW + (dragStartX - e.clientX)
    rightWidth.value = Math.min(maxRightWidth.value, Math.max(220, next))
}

function onSplitterUp() {
    dragging.value = false
    document.removeEventListener('mousemove', onSplitterMove)
    document.removeEventListener('mouseup', onSplitterUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
}

watch(compact, (v) => {
    rightOpen.value = !v
})

function toggleLeft() { leftOpen.value = !leftOpen.value }
function toggleRight() { rightOpen.value = !rightOpen.value }
function selectModule(key) {
  activeModule.value = key
  if (!rightOpen.value) rightOpen.value = true
}

function defaultLogFilename() {
  const d = new Date()
  const p = n => String(n).padStart(2, '0')
  return `debug_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.txt`
}

const logSave = reactive({
  filename: defaultLogFilename(),
  directory: localStorage.getItem('na_log_dir') || '',
  scope: 'all', lineFormat: 'timestamp', encoding: 'utf-8'
})
const logListRef = ref(null)
const mqttListRef = ref(null)

// MQTT 连接信息条展示用
const mqttHostLabel = computed(() => {
  const c = store.mqttConfig
  return c.host ? `${c.host}:${c.port}` : '—'
})
// 暂停显示待显示条数：MQTT 看消息数，其余看日志行数
const pendingCount = computed(() => mode.value === 'mqtt' ? store.pendingMessages.length : store.pendingLines.length)

const isServer = computed(() => mode.value === 'network' && netConfig.protocol === 'tcp_server')
const multiTargetValue = computed(() => selectedClients.value.map(c => c.id).join(','))

const previewCount = computed(() => {
  const lines = mode.value === 'mqtt' ? store.mqttMessages : store.logLines
  if (logSave.scope === 'all') return lines.length
  return lines.filter(l => String(l.dir).toLowerCase() === logSave.scope).length
})

// 提供给子组件
provide('debug', {
  mode, isConnected, connectionId, serialConfig, sendData: doSendFromModule
})

function currentTarget() {
  if (!isServer.value) return null
  if (sendTarget.value === 'all') return null
  return sendTarget.value
}

async function toggleConnect() {
  if (isConnected.value) {
    await disconnect()
  } else {
    await connect()
  }
}

async function connect() {
  connecting.value = true
  try {
    if (mode.value === 'network') {
      const cfg = {
        mode: netConfig.protocol === 'tcp_server' ? 'server' : 'client',
        protocol: netConfig.protocol === 'tcp_server' ? 'tcp' : netConfig.protocol,
        host: netConfig.host,
        port: netConfig.port
      }
      if (cfg.mode === 'server') cfg.host = cfg.host || '0.0.0.0'
      const res = await netApi.connect(cfg)
      connectionId.value = res.connection_id || res.data?.connection_id
      ws.value = netApi.createWebSocket(connectionId.value, store.settings.recvEncoding, onWsMessage, onWsClose, onWsError)
      isConnected.value = true
      ElMessage.success('连接成功')
    } else if (mode.value === 'serial') {
      if (!serialConfig.port) { ElMessage.warning('请选择串口'); return }
      await serialApi.connect(serialConfig)
      ws.value = serialApi.createWebSocket(serialConfig.port, store.settings.recvEncoding, onWsMessage, onWsClose, onWsError)
      isConnected.value = true
      ElMessage.success('串口已打开')
    } else {
      const cfg = {
        host: (store.mqttConfig.host || '').trim(),
        port: Number(store.mqttConfig.port) || 1883,
        client_id: (store.mqttConfig.clientId || '').trim(),
        username: store.mqttConfig.username || '',
        password: store.mqttConfig.password || '',
        keepalive: Number(store.mqttConfig.keepalive) || 60,
        clean: !!store.mqttConfig.clean,
        reconnect: !!store.mqttConfig.reconnect,
        reconnect_period: 4000,
        client_id_with_time: !!store.mqttConfig.clientIdWithTime
      }
      if (!cfg.host) { ElMessage.warning('请填写 Broker 地址'); return }
      const res = await mqttApi.connect(cfg)
      connectionId.value = res.data?.connection_id || res.connection_id
      store.mqttConnInfo = {
        connected: true,
        host: cfg.host,
        port: cfg.port,
        clientId: res.data?.client_id || '',
        status: 'connected'
      }
      ws.value = mqttApi.createWebSocket(connectionId.value, store.settings.recvEncoding, onWsMessage, onWsClose, onWsError)
      isConnected.value = true
      // 连接成功后重建持久化订阅（等价于后端重放的镜像）
      restoreSubscriptions()
      ElMessage.success('MQTT 连接成功')
    }
  } catch (e) {
    ElMessage.error('连接失败: ' + e.message)
  } finally {
    connecting.value = false
  }
}

async function disconnect() {
  try {
    if (ws.value) { ws.value.close(); ws.value = null }
    if (mode.value === 'network' && connectionId.value) {
      await netApi.disconnect(connectionId.value)
    } else if (mode.value === 'serial' && serialConfig.port) {
      await serialApi.disconnect(serialConfig.port)
    } else if (mode.value === 'mqtt' && connectionId.value) {
      await mqttApi.disconnect(connectionId.value)
    }
    isConnected.value = false
    connectionId.value = ''
    clients.value = []
    if (mode.value === 'mqtt') {
      store.mqttConnInfo = {
        connected: false,
        host: store.mqttConnInfo.host,
        port: store.mqttConnInfo.port,
        clientId: '',
        status: 'disconnected'
      }
    }
    ElMessage.info('已断开')
  } catch (e) {
    ElMessage.error('断开失败: ' + e.message)
  }
}

// 连接成功后重建持久化订阅表（订阅计数归零，交由运行时累加）
function restoreSubscriptions() {
  store.mqttSubscriptions.forEach(s => { s.count = 0 })
  store.mqttSubscriptions.forEach(s => {
    mqttApi.subscribe(connectionId.value, s.topic, s.qos)
      .catch(e => console.warn('恢复订阅失败:', s.topic, e))
  })
}

function onWsMessage(msg) {
  // MQTT 模式：data 帧为消息卡片，heartbeat 帧更新连接信息条
  if (mode.value === 'mqtt') {
    if (msg.type === 'data') {
      const item = {
        dir: 'RX',
        topic: msg.topic,
        qos: msg.qos ?? 0,
        retain: !!msg.retain,
        text: msg.data,
        hex: msg.hex_data,
        time: msg.timestamp,
        timeStr: formatTime(msg.timestamp, store.settings.showTimestamp),
        display: recvFormat.value === 'hex' ? msg.hex_data : msg.data
      }
      addMqttMessage(item, store.settings.pauseDisplay)
      // 命中订阅计数累加（前端即时反映）
      store.mqttSubscriptions.forEach(s => {
        if (matchTopic(msg.topic, s.topic)) s.count = (s.count || 0) + 1
      })
    } else if (msg.type === 'heartbeat' && msg.data) {
      store.mqttConnInfo = {
        connected: msg.data.status === 'connected',
        host: msg.data.host,
        port: msg.data.port,
        clientId: msg.data.clientId,
        status: msg.data.status
      }
    }
    return
  }

  if (msg.type === 'data') {
    const dir = 'RX'
    const line = {
      dir,
      text: msg.data,
      hex: msg.hex_data,
      time: msg.timestamp,
      timeStr: formatTime(msg.timestamp, store.settings.showTimestamp),
      client: msg.client_id ? `[${msg.client_id}]` : '',
      display: recvFormat.value === 'hex' ? msg.hex_data : msg.data
    }
    addLogLine(line, store.settings.pauseDisplay)
    checkAutoReply(msg.data)
  } else if (msg.type === 'heartbeat' && msg.data) {
    if (msg.data.clients) {
      clients.value = msg.data.clients
    }
  }
}

function onWsClose() {
  ws.value = null
}

function onWsError(e) {
  console.error('WS错误:', e)
}

// 自动应答引擎
function checkAutoReply(text) {
  const rules = store.autoReplyRules.filter(r => r.enabled)
  for (const rule of rules) {
    const matched = rule.matchType === 'regex'
      ? (new RegExp(rule.match)).test(text)
      : text.includes(rule.match)
    if (matched && rule.reply) {
      setTimeout(() => {
        doSendFromModule({ data: rule.reply, format: rule.replyFormat || 'text' })
      }, rule.delay || 0)
      addLogLine({ dir: 'AUTO', text: `命中规则「${rule.name}」→ ${rule.reply}`, hex: '', time: nowTs(), timeStr: formatTime(nowTs(), store.settings.showTimestamp), client: '', display: `命中规则「${rule.name}」→ ${rule.reply}` }, store.settings.pauseDisplay)
      break
    }
  }
}

async function doSend() {
  if (!sendText.value) { ElMessage.warning('请输入要发送的数据'); return }
  await doSendFromModule({ data: sendText.value, format: sendFormat.value })
}

// 统一的发送入口（供主界面与子模块调用）
async function doSendFromModule(payload = {}) {
  if (!isConnected.value) { ElMessage.warning('请先建立连接'); return false }

  // MQTT 分支：发布到「发布主题」
  if (mode.value === 'mqtt') {
    const topic = (store.mqttConfig.publishTopic || '').trim()
    if (!topic) { ElMessage.warning('请先填写发布主题'); return false }
    const data = payload.data ?? ''
    const format = payload.format || sendFormat.value
    const pub = {
      topic,
      data,
      format,
      encoding: store.settings.sendEncoding,
      qos: store.mqttConfig.publishQos ?? 0,
      retain: !!store.mqttConfig.publishRetain,
      end_chars: payload.endChars !== undefined ? payload.endChars : endChars.value,
      append_check: payload.appendCheck || appendCheck.value || null
    }
    try {
      await mqttApi.publish(connectionId.value, pub)
      addHistory({ data, format })
      const txHex = format === 'hex' ? normalizeHex(data) : textToHex(data)
      addMqttMessage({
        dir: 'TX', topic, qos: pub.qos, retain: pub.retain,
        text: data, hex: txHex, time: nowTs(),
        timeStr: formatTime(nowTs(), store.settings.showTimestamp),
        display: recvFormat.value === 'hex' ? (txHex || data) : data
      }, store.settings.pauseDisplay)
      return true
    } catch (e) {
      ElMessage.error('发送失败: ' + e.message)
      return false
    }
  }

  const full = {
    data: payload.data ?? '',
    format: payload.format || sendFormat.value,
    encoding: store.settings.sendEncoding,
    end_chars: payload.endChars !== undefined ? payload.endChars : endChars.value,
    append_check: payload.appendCheck || appendCheck.value || null,
    target: payload.target !== undefined ? payload.target : currentTarget()
  }
  try {
    if (mode.value === 'network') {
      await netApi.sendData(connectionId.value, full)
    } else {
      await serialApi.sendData(serialConfig.port, full)
    }
    if (full.format !== 'file') {
      addHistory({ data: full.data, format: full.format })
    }
    const targetLabel = full.target ? ` → [${full.target}]` : ''
    const isFile = full.format === 'file'
    const fileName = payload.fileName || ''
    const displayText = isFile ? `[文件] ${fileName || 'binary'}` : full.data
    const txHex = isFile ? '' : (full.format === 'hex' ? normalizeHex(full.data) : textToHex(full.data))
    addLogLine({
      dir: 'TX', text: displayText, hex: txHex, time: nowTs(),
      timeStr: formatTime(nowTs(), store.settings.showTimestamp),
      client: targetLabel,
      display: recvFormat.value === 'hex' ? (txHex || displayText) : displayText
    })
    return true
  } catch (e) {
    ElMessage.error('发送失败: ' + e.message)
    return false
  }
}

// 暂停/继续显示：按钮放在发送区，随时可点
function togglePauseDisplay() {
    store.settings.pauseDisplay = !store.settings.pauseDisplay
    if (!store.settings.pauseDisplay) {
        const n = flushPendingLines()
        const m = flushPendingMessages()
        if (mode.value === 'mqtt') {
            if (m) ElMessage.info(`已恢复显示 ${m} 条消息`)
        } else if (n) {
            ElMessage.info(`已恢复显示 ${n} 行`)
        }
    }
}

async function refreshPorts() {
  try {
    const res = await serialApi.getPorts()
    serialPorts.value = res.data?.ports || []
  } catch (e) {
    ElMessage.error('获取串口失败: ' + e.message)
  }
}

async function refreshInterfaces() {
  try {
    const res = await systemApi.getInterfaces()
    if (res.data?.ips) {
      localIps.value = res.data.ips
      ipLabels.value = res.data.labels || {}
      // 首次加载时把默认监听地址设为真实网卡 IP（优先有线），而不是 127.0.0.1
      if (netConfig.host === '127.0.0.1' && res.data.preferred) {
        netConfig.host = res.data.preferred
      }
    }
  } catch (e) {
    console.error('获取本机IP失败:', e)
  }
}

function ipLabel(ip) {
  if (ip === '0.0.0.0') return '0.0.0.0 · 全部网卡'
  const tag = ipLabels.value[ip]
  return tag ? `${ip} · ${tag}` : ip
}

function clearLog() {
  if (mode.value === 'mqtt') { clearMqttMessages(); return }
  clearLogLines()
}

function onClientSelect(rows) {
  selectedClients.value = rows
  if (rows.length === 0) {
    sendTarget.value = 'all'
  } else if (rows.length === 1) {
    sendTarget.value = rows[0].id
  } else {
    sendTarget.value = rows.map(r => r.id).join(',')
  }
}

async function kickClient(row) {
  try {
    await netApi.disconnectClient(connectionId.value, row.id)
    clients.value = clients.value.filter(c => c.id !== row.id)
    ElMessage.info(`已断开 ${row.address}`)
  } catch (e) {
    ElMessage.error('断开失败: ' + e.message)
  }
}

function openSaveLog() {
  logSave.filename = defaultLogFilename()
  logSave.directory = localStorage.getItem('na_log_dir') || ''
  saveLogDialogVisible.value = true
}

async function chooseDir() {
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.choose_dir) {
      const dir = await window.pywebview.api.choose_dir()
      if (dir) {
        logSave.directory = dir
        localStorage.setItem('na_log_dir', dir)
      }
    } else {
      ElMessage.info('在线版无法读取本机目录，请手动输入完整路径')
    }
  } catch (e) {
    ElMessage.error('选择目录失败: ' + e.message)
  }
}

// 单条 MQTT 消息 → 导出行（行格式：timestamp 含时间戳 / raw 纯数据 / hex 纯HEX）
function mqttLogLine(m) {
  const dir = String(m.dir || '').toUpperCase()
  const topic = m.topic || ''
  if (logSave.lineFormat === 'hex') return `[${dir}] [${topic}] ${m.hex || ''}`
  if (logSave.lineFormat === 'raw') return `[${dir}] [${topic}] ${m.text ?? ''}`
  return `[${m.timeStr}] [${dir}] [${topic}] ${m.text ?? ''}`
}

async function doSaveLog() {
  try {
    let content = ''
    if (mode.value === 'mqtt') {
      // MQTT 模式导出消息卡片；内容范围：全部 / 仅接收(RX) / 仅发送(TX)，AUTO 归入全部
      let msgs = store.mqttMessages
      if (logSave.scope !== 'all') {
        msgs = msgs.filter(m => String(m.dir).toLowerCase() === logSave.scope)
      }
      content = msgs.map(mqttLogLine).join('\n') + (msgs.length ? '\n' : '')
    } else {
      let lines = store.logLines
      if (logSave.scope !== 'all') {
        lines = lines.filter(l => l.dir.toLowerCase() === logSave.scope)
      }
      content = lines.map(l => {
        if (logSave.lineFormat === 'raw') return l.text
        if (logSave.lineFormat === 'hex') return l.hex || l.text
        return `[${l.timeStr}] [${l.dir}]${l.client ? ' ' + l.client : ''} ${l.text}`
      }).join('\n') + (lines.length ? '\n' : '')
    }

    const filename = logSave.filename || defaultLogFilename()
    const directory = logSave.directory || '.'
    await logApi.save({
      filename, directory, scope: logSave.scope,
      line_format: logSave.lineFormat, encoding: logSave.encoding, content
    })
    if (logSave.directory) localStorage.setItem('na_log_dir', logSave.directory)
    ElMessage.success('日志已保存')
    saveLogDialogVisible.value = false
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  }
}

// 切换模式时断开
watch(mode, () => {
  if (isConnected.value) disconnect()
  if (mode.value === 'mqtt') {
    // 进入 MQTT：右栏默认选中「订阅」
    activeModule.value = 'sub'
    if (!rightOpen.value) rightOpen.value = true
  } else if (activeModule.value === 'sub') {
    // 离开 MQTT：若停留在「订阅」则切回「快捷指令」
    activeModule.value = 'quick'
  }
  if (mode.value === 'network') refreshInterfaces()
  if (mode.value === 'scan') {
    // 进入扫描：左栏常驻，加载本机网段
    leftOpen.value = true
    if (!scanSegments.value.length) loadScanSegments()
  }
  if (mode.value === 'httpd') {
    // 进入 HTTP Server：拉一次状态（不自动停后端服务）
    leftOpen.value = true
    refreshHttpdStatus()
  }
})

// 切到 Server 模式时，本地 IP 默认监听所有接口
watch(() => netConfig.protocol, (v) => {
  if (v === 'tcp_server' && (!netConfig.host || netConfig.host === '127.0.0.1')) {
    netConfig.host = '0.0.0.0'
  }
})

// 切换编码时重连 WS（接收编码生效）
watch(() => store.settings.recvEncoding, () => {
  if (isConnected.value) {
    if (ws.value) { ws.value.close(); ws.value = null }
    if (mode.value === 'network' && connectionId.value) {
      ws.value = netApi.createWebSocket(connectionId.value, store.settings.recvEncoding, onWsMessage, onWsClose, onWsError)
    } else if (mode.value === 'serial' && serialConfig.port) {
      ws.value = serialApi.createWebSocket(serialConfig.port, store.settings.recvEncoding, onWsMessage, onWsClose, onWsError)
    } else if (mode.value === 'mqtt' && connectionId.value) {
      ws.value = mqttApi.createWebSocket(connectionId.value, store.settings.recvEncoding, onWsMessage, onWsClose, onWsError)
    }
  }
})

// 显示格式变化时刷新日志显示
watch(recvFormat, () => {
  store.logLines.forEach(l => {
    l.display = recvFormat.value === 'hex' ? (l.hex || textToHex(l.text)) : l.text
  })
  store.mqttMessages.forEach(m => {
    m.display = recvFormat.value === 'hex' ? (m.hex || m.text) : m.text
  })
})

// 自动滚动
watch(() => store.logLines.length, async () => {
  if (store.settings.autoScroll) {
    await nextTick()
    if (logListRef.value) {
      logListRef.value.scrollTop = logListRef.value.scrollHeight
    }
  }
})

// 自动滚动（MQTT 消息卡片）
watch(() => store.mqttMessages.length, async () => {
  if (store.settings.autoScroll) {
    await nextTick()
    if (mqttListRef.value) {
      mqttListRef.value.scrollTop = mqttListRef.value.scrollHeight
    }
  }
})

// 主题
watch(() => store.settings.theme, (v) => {
  document.documentElement.classList.toggle('dark', v === 'dark')
})

onMounted(async () => {
  // 先从本机数据文件恢复快捷指令等用户数据
  await initStore()
  refreshPorts()
  refreshInterfaces()
  document.documentElement.classList.toggle('dark', store.settings.theme === 'dark')
  if (bodyRef.value && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(entries => {
      const w = entries[0].contentRect.width
      if (w > 0) bodyWidth.value = w
    })
    ro.observe(bodyRef.value)
  }
  // 初始按实际宽度决定右栏折叠状态；左栏默认常驻展开
  if (bodyRef.value) {
    bodyWidth.value = bodyRef.value.clientWidth || 1280
    rightOpen.value = !compact.value
    leftOpen.value = true
    rightWidth.value = Math.min(280, maxRightWidth.value)
  }
})

onUnmounted(() => {
  if (ws.value) ws.value.close()
  if (scanWs) { try { scanWs.close() } catch (e) { /* ignore */ } }
  if (httpdWs) { try { httpdWs.close() } catch (e) { /* ignore */ } }
  if (ro) ro.disconnect()
  stopLoop()
  if (saveTimer) { clearInterval(saveTimer); saveTimer = null }
  if (httpdStatusTimer) { clearInterval(httpdStatusTimer); httpdStatusTimer = null }
  if (httpdElapsedTimer) { clearInterval(httpdElapsedTimer); httpdElapsedTimer = null }
})

/* ==================================================================
 * HTTP Server 编排（第五模式）
 * ================================================================== */
import { pushHttpRequest, clearHttpRequests } from '../store'

async function refreshHttpdStatus() {
  try {
    const res = await httpServerApi.status()
    if (res && res.success) {
      const prev = store.httpServerStatus
      store.httpServerStatus = { ...prev, ...(res.data || {}) }
      // 状态变化时同步本地的 running 标记
      httpdRunning.value = !!res.data.running
      httpdSessionId.value = res.data.session_id || ''
      if (httpdRunning.value) {
        ensureHttpdWs()
        ensureHttpdTimers()
        // 进入运行态时拉一次全量记录（避免热重启后丢上下文）
        if (store.httpServerRequests.length === 0) {
          try {
            const r = await httpServerApi.getRequests()
            if (r && r.success && Array.isArray(r.data.records)) {
              // 反转：最新在前
              store.httpServerRequests = [...r.data.records].reverse()
            }
          } catch (e) { /* ignore */ }
        }
      } else {
        stopHttpdTimers()
      }
    }
  } catch (e) {
    // 拉状态失败不弹错误（刚启动后端未就绪属正常）
  }
}

function ensureHttpdWs() {
  if (!httpdSessionId.value) return
  if (httpdWs) {
    try { httpdWs.close() } catch (e) { /* ignore */ }
    httpdWs = null
  }
  httpdWs = httpServerApi.createWebSocket(
    httpdSessionId.value,
    onHttpdWsMessage,
    () => {
      httpdWs = null
      // 断了就 1.5s 后重连
      setTimeout(() => { if (httpdRunning.value) ensureHttpdWs() }, 1500)
    },
    (e) => {
      console.warn('HTTP Server WS 错误:', e)
    }
  )
}

function onHttpdWsMessage(msg) {
  if (!msg || !msg.type) return
  if (msg.type === 'request') {
    pushHttpRequest(msg.data)
    // 当前查看的记录若被刷新（同一 id），保持选中
    const sel = store.httpServerSelected
    if (sel && msg.data && msg.data.id === sel.id) {
      store.httpServerSelected = msg.data
    }
  }
}

function ensureHttpdTimers() {
  if (!httpdStatusTimer) {
    httpdStatusTimer = setInterval(() => {
      // 周期刷新状态（total / addresses 等）
      httpServerApi.status().then((res) => {
        if (res && res.success) {
          store.httpServerStatus = { ...store.httpServerStatus, ...(res.data || {}) }
        }
      }).catch(() => {})
    }, 1000)
  }
  if (!httpdElapsedTimer) {
    httpdElapsedTimer = setInterval(() => {
      // 仅本地累加 elapsed，避免每秒都打后端
      const s = store.httpServerStatus
      if (s && s.started_at) s.elapsed = (Date.now() / 1000) - s.started_at
    }, 1000)
  }
}

function stopHttpdTimers() {
  if (httpdStatusTimer) { clearInterval(httpdStatusTimer); httpdStatusTimer = null }
  if (httpdElapsedTimer) { clearInterval(httpdElapsedTimer); httpdElapsedTimer = null }
}

async function startHttpd(cfg) {
  httpdStarting.value = true
  try {
    const res = await httpServerApi.start(cfg)
    if (res && res.success) {
      ElMessage.success(res.message || 'HTTP 服务已启动')
      httpdSessionId.value = res.data.session_id || ''
      clearHttpRequests()
      await refreshHttpdStatus()
    } else {
      ElMessage.error((res && res.detail) || (res && res.message) || '启动失败')
    }
  } catch (e) {
    ElMessage.error('启动失败: ' + (e?.message || e))
  } finally {
    httpdStarting.value = false
  }
}

async function stopHttpd() {
  try {
    if (httpdWs) { try { httpdWs.close() } catch (e) { /* ignore */ } httpdWs = null }
    const res = await httpServerApi.stop()
    if (res && res.success) {
      ElMessage.success(res.message || 'HTTP 服务已停止')
    }
  } catch (e) {
    ElMessage.error('停止失败: ' + (e?.message || e))
  } finally {
    await refreshHttpdStatus()
  }
}

// 响应配置变化（运行中实时同步）
let httpdRespTimer = null
function onHttpdResponseChange(resp) {
  // 防抖 300ms：连续改 body 不会逐次打后端
  if (httpdRespTimer) clearTimeout(httpdRespTimer)
  httpdRespTimer = setTimeout(async () => {
    try {
      const res = await httpServerApi.setResponse(resp)
      if (!(res && res.success)) {
        ElMessage.warning('响应配置更新失败: ' + ((res && res.message) || ''))
      }
    } catch (e) {
      // ignore
    }
  }, 300)
}

function selectHttpRecord(row) {
  store.httpServerSelected = row
}

function closeHttpDetail() {
  store.httpServerSelected = null
}

function clearHttpRecordsAndState() {
  // 乐观清空 + 调后端
  clearHttpRequests()
  httpServerApi.clear().catch(() => {})
}

async function exportHttpLog() {
  try {
    const res = await httpServerApi.exportLog({ directory: '', filename: '' })
    if (res && res.success) {
      ElMessage.success(`已导出 ${res.data.count} 条到 ${res.data.path}`)
    } else {
      ElMessage.error('导出失败: ' + ((res && res.message) || ''))
    }
  } catch (e) {
    ElMessage.error('导出失败: ' + (e?.message || e))
  }
}
</script>

<style scoped>
/* ============ 设计变量：单一主色 + 克制的中性色 ============ */
.debug-view {
  --primary: #2f6fed;
  --primary-hover: #4a82f5;
  --primary-soft: #eaf1fe;
  --danger: #e05c5c;
  --warning: #e8912d;
  --success: #2e9e6b;
  --purple: #8b5cf6;

  --bg: #f2f4f7;
  --panel: #ffffff;
  --border: #e3e8ef;
  --text: #1f2329;
  --sub: #5a6472;
  --muted: #8b95a3;
  --logbg: #fbfcfd;
  --soft: #f5f7fa;
  --bar-top: #2b3a55;
  --bar-bottom: #35485f;
  --shadow: 0 1px 3px rgba(16, 24, 40, .05), 0 1px 2px rgba(16, 24, 40, .03);

  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}
.debug-view.dark {
  --primary: #4a82f5;
  --primary-hover: #6b9bf7;
  --primary-soft: #1e2a40;
  --danger: #e4736f;
  --warning: #e8a04d;
  --success: #4bb98a;
  --bg: #101114;
  --panel: #191b1f;
  --border: #2a2d33;
  --text: #e5eaf3;
  --sub: #a8b0bd;
  --muted: #767d8a;
  --logbg: #141619;
  --soft: #212429;
  --bar-top: #171a20;
  --bar-bottom: #1f2329;
  --shadow: 0 1px 3px rgba(0, 0, 0, .35);
}

/* ============ 标题栏 ============ */
.title-bar {
  height: 46px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px;
  background: linear-gradient(90deg, var(--bar-top), var(--bar-bottom));
  color: #fff;
  box-shadow: 0 1px 0 rgba(0, 0, 0, .12);
}
.title-left { display: flex; align-items: center; gap: 14px; min-width: 0; }
.app-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: .5px;
  white-space: nowrap;
}
.app-ver {
  font-size: 11px;
  font-weight: 400;
  opacity: .55;
  margin-left: 2px;
  letter-spacing: 0;
}
.title-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.panel-btn { color: #c3cddb !important; }
.panel-btn:hover { color: #fff !important; }

/* ============ 主体 ============ */
.main-body {
  position: relative;
  flex: 1;
  display: flex;
  min-height: 0;
  padding: 10px;
  gap: 10px;
}

/* ============ 左栏 ============ */
.left-panel {
  width: 252px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--soft);
}
.panel-scroll { flex: 1; overflow-y: auto; padding: 4px 12px 8px; }

/* 左栏分区折叠 */
.side-collapse { border-top: none; }
.side-collapse :deep(.el-collapse-item__header) {
  height: 36px;
  line-height: 36px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  border-bottom: none;
}
.side-collapse :deep(.el-collapse-item__header.is-active) { color: var(--primary); }
.side-collapse :deep(.el-collapse-item__wrap) { border-bottom: 1px solid var(--border); }
.side-collapse :deep(.el-collapse-item__content) { padding-bottom: 8px; }
.config-form :deep(.el-form-item) { margin-bottom: 8px; }
.config-form :deep(.el-form-item__label) { color: var(--sub); }

.opt-list { display: flex; flex-direction: column; gap: 8px; }
.hint-row { margin-top: 6px; font-size: 12px; line-height: 1.5; }
.muted-text { color: var(--muted); }
.warn-text { color: var(--warning); }
.ok-text { color: var(--success); }

/* 统计栏 */
.stat-bar {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  background: var(--soft);
}
.stat-bar .stat-row { margin-bottom: 5px; }
.stat-bar .stat-row:last-of-type { margin-bottom: 0; }
.stat-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.stat-label {
  color: var(--sub);
  flex-shrink: 0;
  min-width: 28px;
}
.stat-value {
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.stat-count { color: var(--muted); margin-left: auto; }

.panel-foot {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  background: var(--panel);
}

.row-flex { display: flex; width: 100%; gap: 6px; }
.row-flex > * { min-width: 0; }

/* ============ 中栏 ============ */
.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  gap: 10px;
}

.log-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
  overflow: hidden;
}

.log-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--soft);
}
.toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px 10px;
  margin-left: auto;
}
.btn-pair { display: flex; gap: 6px; flex-shrink: 0; }
.sel-fmt { width: 78px; }
.sel-enc { width: 86px; }

.log-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 12px;
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 12.5px;
  line-height: 1.75;
  background: var(--logbg);
}
.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 4px;
  border-radius: 3px;
}
.log-line:hover { background: var(--primary-soft); }
.log-dir { font-weight: 700; margin-right: 6px; letter-spacing: .3px; }
.log-time { color: var(--muted); margin-right: 6px; }
.log-client { color: var(--muted); margin-right: 6px; }
.log-data { color: var(--text); }
/* 发送=主色蓝，接收=成功绿，自动应答=紫 */
.dir-tx .log-dir { color: var(--primary); }
.dir-rx .log-dir { color: var(--success); }
.dir-auto .log-dir { color: var(--purple); }
.log-empty { color: var(--muted); text-align: center; margin-top: 40px; font-size: 13px; }

.log-list.no-wrap { overflow-x: auto; }
.log-list.no-wrap .log-line { white-space: pre; word-break: normal; }

/* ============ MQTT 连接信息条 ============ */
.conn-bar {
  flex-shrink: 0;
  height: 40px;
  padding: 0 12px;
  background: #fcfdff;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.conn-info {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--sub);
  min-width: 0;
  overflow: hidden;
  flex-wrap: nowrap;
}
.conn-info > span { white-space: nowrap; }
.conn-info b { color: var(--text); font-weight: 600; }
.conn-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); flex: none; }
.conn-dot.off { background: #b6bdc9; }

/* ============ MQTT 消息卡片列表 ============ */
.mqtt-msg-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px 12px;
  background: #f7f9fc;
}

/* ============ 发送区 ============ */
.send-panel {
  flex-shrink: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
  padding: 10px 12px 12px;
}

.client-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 8px;
  margin-bottom: 8px;
  padding: 7px 10px;
  background: var(--primary-soft);
  border: 1px solid color-mix(in srgb, var(--primary) 22%, transparent);
  border-radius: 8px;
}
.client-label { font-size: 13px; color: var(--sub); flex-shrink: 0; font-weight: 600; }
.client-select { width: 170px; flex: 0 1 170px; min-width: 120px; }
.client-count {
  font-size: 12px;
  color: var(--primary);
  font-weight: 600;
  margin-left: auto;
}

.send-opts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 10px;
}

/* 发布主题行（仅 MQTT） */
.topic-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 10px;
  margin-bottom: 10px;
  padding: 7px 10px;
  background: var(--primary-soft);
  border: 1px solid color-mix(in srgb, var(--primary) 22%, transparent);
  border-radius: 8px;
}
.topic-row .opt-label { font-weight: 600; }
.topic-input { flex: 1; min-width: 140px; }
.pub-qos { width: 92px; flex: none; }
.opt-group { display: flex; align-items: center; gap: 6px; }
.opt-label { font-size: 13px; color: var(--sub); white-space: nowrap; }
.sel-end { width: 84px; }
.sel-chk { width: 94px; }
.send-actions { display: flex; gap: 8px; margin-left: auto; }

/* 暂停显示按钮：发送区常驻，橙色高亮，一眼可见 */
.pause-btn { font-weight: 600; }
.pause-idle {
  color: var(--warning) !important;
  border-color: color-mix(in srgb, var(--warning) 45%, transparent) !important;
  background: color-mix(in srgb, var(--warning) 8%, transparent) !important;
}
.pause-idle:hover {
  color: #fff !important;
  background: var(--warning) !important;
  border-color: var(--warning) !important;
}

.send-input :deep(textarea) {
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  line-height: 1.6;
}

/* ============ 可拖动分隔条 ============ */
.v-splitter {
  flex-shrink: 0;
  width: 4px;
  margin: 0 -2px;
  border-radius: 2px;
  cursor: col-resize;
  background: transparent;
  transition: background .15s;
}
.v-splitter:hover,
.v-splitter.dragging { background: var(--primary); }

/* ============ 右栏 ============ */
.right-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.right-panel.collapsed { width: 54px; }

.module-nav {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
  padding: 8px;
  border-bottom: 1px solid var(--border);
  background: var(--soft);
}
.module-nav.vertical {
  display: flex;
  flex-direction: column;
  border-bottom: none;
  gap: 5px;
  padding: 8px 6px;
}
.module-tab {
  padding: 6px 4px;
  font-size: 12px;
  text-align: center;
  cursor: pointer;
  border-radius: 6px;
  color: var(--sub);
  background: var(--panel);
  border: 1px solid var(--border);
  user-select: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: all .15s ease;
}
.module-tab:hover { color: var(--primary); border-color: var(--primary); }
.module-nav.vertical .module-tab { padding: 8px 2px; }
.module-tab.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  font-weight: 600;
}
.module-tab.active:hover { color: #fff; }

.nav-toggle {
  grid-column: 1 / -1;
  text-align: center;
  padding: 3px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  transition: color .15s;
}
.module-nav.vertical .nav-toggle { padding: 6px 2px; }
.nav-toggle:hover { color: var(--primary); }

.module-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px;
}

/* 面板标题：左侧主色竖条，层级清晰 */
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  padding-left: 8px;
  border-left: 3px solid var(--primary);
  line-height: 1.2;
}
.log-preview { margin-top: 8px; color: var(--muted); font-size: 13px; }
.client-empty { text-align: center; color: var(--muted); padding: 20px; }
</style>
