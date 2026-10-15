// 全局共享状态（跨组件共享的数据）
// 持久化策略：服务端本机数据文件（永久保存）为主 + localStorage（首屏/离线兜底）
import { reactive, watch } from 'vue'
import { storeApi } from './api'
import { topicColor as pickTopicColor } from './utils'

function load(key, def) {
    try {
        const v = localStorage.getItem(key)
        return v ? JSON.parse(v) : def
    } catch (e) {
        return def
    }
}

function save(key, val) {
    try {
        localStorage.setItem(key, JSON.stringify(val))
    } catch (e) { /* ignore */ }
}

export const store = reactive({
    // 日志行：{dir: 'TX'|'RX'|'AUTO', text, hex, time, client}
    logLines: [],
    // 历史发送：{data, format, time}
    history: load('na_history', []),
    // 快捷指令：{name, data, format, shortcut} —— 默认空，由用户添加后永久保存
    quickCommands: load('na_quick', []),
    // 批量发送：{data, format, delay, repeat}
    batchItems: load('na_batch', []),
    // 自动应答规则：{enabled, name, match, matchType, reply, replyFormat, delay}
    autoReplyRules: load('na_reply', []),
    // MQTT 连接配置（含发送区随带状态），跨重启保留
    mqttConfig: load('na_mqtt_config', {
        host: 'broker.emqx.io',
        port: 1883,
        clientId: '',            // 空则由后端生成唯一 ClientID
        username: '',
        password: '',
        clean: true,
        reconnect: true,
        keepalive: 60,
        clientIdWithTime: false,
        // 发送区随带状态
        publishTopic: '',
        publishQos: 0,
        publishRetain: false
    }),
    // MQTT 订阅列表（持久化 {topic,qos,color}；count 为运行时，不持久化）
    mqttSubscriptions: load('na_mqtt_subs', []),
    // 网络扫描配置（持久化，跨重启保留）
    scanConfig: load('na_scan_config', {
        method: 'arp_tcp',
        segment: '',                 // 选中的网段 CIDR 或 '__custom__'
        startIp: '',
        endIp: '',
        concurrency: 128,
        timeoutMs: 500,
        vendorLookup: true,
        resolveHostname: true,
        portScan: false,
        ports: [22, 80, 443, 445, 3389],
        portPreset: 'common'
    }),
    // 扫描备注：{ip: 备注文本}
    scanNotes: load('na_scan_notes', {}),
    // 扫描收藏：{ip: true}
    scanFavorites: load('na_scan_favorites', {}),
    // 扫描历史：最近 10 次 [{time, seg, total, online, delta, deltaCls, devices:[...]}]
    scanHistory: load('na_scan_history', []),
    // —— 网络扫描运行时态（不持久化）——
    scanResults: [],             // 本轮结果，上限 1024 行
    scanProgress: { scanned: 0, total: 0, online: 0, offline: 0, occupied: 0, utilization: 0, cidr: '', elapsed: 0, status: 'idle' },
    scanChanges: {},             // {ip: {type:'new'|'changed', from?, to?, text}}（行内徽标用）
    scanChangeList: { new: [], left: [], changed: [] }, // 服务端推送的本轮 vs 上一轮聚合列表（横幅用）
    // —— HTTP Server 配置（持久化端口 / 绑定地址 / 响应配置，跨重启保留）——
    httpServerConfig: load('na_http_server_config', {
        port: 8080,
        bind: '0.0.0.0',
        response: {
            code: 200,
            content_type: 'application/json',
            body: '{"ok":true}',
            delay_ms: 0,
            echo: true
        }
    }),
    // —— HTTP Server 运行时态（不持久化）——
    httpServerStatus: {
        running: false,
        session_id: '',
        port: 0,
        bind: '',
        total: 0,
        elapsed: 0,
        addresses: []   // [{ip, label, interface, rank, url}]
    },
    httpServerRequests: [],      // 已收到的请求记录（上限 2000）
    httpServerSelected: null,    // 当前在详情区查看的记录
    httpServerError: '',         // 启动/运行错误信息
    // —— MQTT 运行时态（不持久化）——
    mqttMessages: [],       // 消息卡片数据源，上限 2000
    pendingMessages: [],    // 暂停显示期间堆积的 MQTT 消息
    topicColorMap: {},      // {topic: color} 会话内主题→颜色登记表
    mqttConnInfo: { connected: false, host: '', port: 0, clientId: '', status: 'disconnected' },
    // 收发统计
    stats: { rxBytes: 0, txBytes: 0, rxCount: 0, txCount: 0 },
    // 暂停显示期间堆积的行（恢复显示时合并回 logLines）
    pendingLines: [],
    // 设置
    settings: load('na_settings', {
        theme: 'light',
        recvEncoding: 'utf-8',
        sendEncoding: 'utf-8',
        showTimestamp: true,
        autoScroll: true,
        lineWrap: true,
        pauseDisplay: false,
        showTxRx: true
    })
})

// 需要永久保存的字段
const PERSIST_KEYS = ['history', 'quickCommands', 'batchItems', 'autoReplyRules', 'settings', 'mqttConfig', 'mqttSubscriptions', 'scanConfig', 'scanNotes', 'scanFavorites', 'scanHistory', 'httpServerConfig']
const REMOTE_KEY = 'app_data'

let remoteReady = false
let saveTimer = null

// 订阅列表写盘/上云时剥离运行时字段 count，避免污染持久化数据
function stripSubCount(subs) {
    return (subs || []).map(({ topic, qos, color }) => ({ topic, qos, color }))
}

async function saveRemote() {
    const payload = {}
    for (const k of PERSIST_KEYS) {
        if (k === 'mqttSubscriptions') {
            payload[k] = stripSubCount(store[k])
        } else {
            payload[k] = JSON.parse(JSON.stringify(store[k]))
        }
    }
    try {
        await storeApi.set(REMOTE_KEY, payload)
    } catch (e) {
        console.error('保存到本机数据文件失败:', e)
    }
}

function scheduleRemoteSave() {
    if (!remoteReady) return
    clearTimeout(saveTimer)
    saveTimer = setTimeout(saveRemote, 500)
}

/**
 * 启动时从本机数据文件加载。
 * 只有服务端完全没有数据时才使用内置默认值，避免"删掉后又冒出来"。
 */
export async function initStore() {
    let loaded = false
    try {
        const res = await storeApi.get(REMOTE_KEY)
        const remote = res?.data?.value
        if (remote && typeof remote === 'object') {
            for (const k of PERSIST_KEYS) {
                if (remote[k] === undefined) continue
                if (k === 'settings' || k === 'mqttConfig' || k === 'scanConfig') {
                    store[k] = { ...store[k], ...remote[k] }
                } else {
                    store[k] = remote[k]
                }
            }
            loaded = true
        }
    } catch (e) {
        console.error('读取本机数据文件失败:', e)
    }

    remoteReady = true

    // 首次运行（服务端无数据）：写入当前值，建立本机数据库
    if (!loaded) {
        await saveRemote()
    }
    return loaded
}

export async function getStorePath() {
    try {
        const res = await storeApi.getPath()
        return res?.data?.path || ''
    } catch (e) {
        return ''
    }
}

// 持久化监听：本地缓存立即写，服务端防抖写
watch(() => store.history, (v) => { save('na_history', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.quickCommands, (v) => { save('na_quick', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.batchItems, (v) => { save('na_batch', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.autoReplyRules, (v) => { save('na_reply', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.settings, (v) => { save('na_settings', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.mqttConfig, (v) => { save('na_mqtt_config', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.mqttSubscriptions, () => {
    save('na_mqtt_subs', stripSubCount(store.mqttSubscriptions))
    scheduleRemoteSave()
}, { deep: true })

// 网络扫描持久化（配置 / 备注 / 收藏 / 历史）
watch(() => store.scanConfig, (v) => { save('na_scan_config', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.scanNotes, (v) => { save('na_scan_notes', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.scanFavorites, (v) => { save('na_scan_favorites', v); scheduleRemoteSave() }, { deep: true })
watch(() => store.scanHistory, (v) => { save('na_scan_history', v); scheduleRemoteSave() }, { deep: true })

// HTTP Server 配置持久化（端口 / 绑定地址 / 响应配置）
watch(() => store.httpServerConfig, (v) => { save('na_http_server_config', v); scheduleRemoteSave() }, { deep: true })

// 按 HEX 串估算字节数（HEX 为空时按 UTF-8 字节数兜底）
function byteSize(line) {
    if (line.hex) {
        const parts = line.hex.split(/\s+/).filter(Boolean)
        if (parts.length) return parts.length
    }
    if (line.text == null) return 0
    try {
        return new TextEncoder().encode(String(line.text)).length
    } catch (e) {
        return String(line.text).length
    }
}

export function addHistory(item) {
    store.history.unshift({ data: item.data, format: item.format, time: Date.now() })
    if (store.history.length > 500) {
        store.history.length = 500
    }
}

export function addLogLine(line, paused = false) {
    // 统计始终累加（暂停显示不影响计数）
    const dir = String(line.dir || '').toUpperCase()
    const size = byteSize(line)
    if (dir === 'RX') {
        store.stats.rxBytes += size
        store.stats.rxCount += 1
    } else if (dir === 'TX') {
        store.stats.txBytes += size
        store.stats.txCount += 1
    }

    if (paused) {
        store.pendingLines.push(line)
        if (store.pendingLines.length > 2000) {
            store.pendingLines.splice(0, store.pendingLines.length - 2000)
        }
        return
    }

    store.logLines.push(line)
    if (store.logLines.length > 2000) {
        store.logLines.splice(0, store.logLines.length - 2000)
    }
}

// 恢复显示：把暂停期间堆积的行合并回日志区
export function flushPendingLines() {
    if (!store.pendingLines.length) return 0
    const n = store.pendingLines.length
    store.logLines.push(...store.pendingLines)
    store.pendingLines = []
    if (store.logLines.length > 2000) {
        store.logLines.splice(0, store.logLines.length - 2000)
    }
    return n
}

export function resetStats() {
    store.stats.rxBytes = 0
    store.stats.txBytes = 0
    store.stats.rxCount = 0
    store.stats.txCount = 0
}

export function clearLogLines() {
    store.logLines = []
    store.pendingLines = []
}

/* =========================================================================
 * MQTT 消息与状态
 * ========================================================================= */

// 追加一条 MQTT 消息：始终累加统计；暂停时分流到 pendingMessages
export function addMqttMessage(msg, paused = false) {
    const dir = String(msg.dir || '').toUpperCase()
    const size = byteSize(msg)
    if (dir === 'RX') {
        store.stats.rxBytes += size
        store.stats.rxCount += 1
    } else if (dir === 'TX') {
        store.stats.txBytes += size
        store.stats.txCount += 1
    }

    if (paused) {
        store.pendingMessages.push(msg)
        if (store.pendingMessages.length > 2000) {
            store.pendingMessages.splice(0, store.pendingMessages.length - 2000)
        }
        return
    }

    store.mqttMessages.push(msg)
    if (store.mqttMessages.length > 2000) {
        store.mqttMessages.splice(0, store.mqttMessages.length - 2000)
    }
}

// 恢复显示：把暂停期间堆积的 MQTT 消息合并回消息列表
export function flushPendingMessages() {
    if (!store.pendingMessages.length) return 0
    const n = store.pendingMessages.length
    store.mqttMessages.push(...store.pendingMessages)
    store.pendingMessages = []
    if (store.mqttMessages.length > 2000) {
        store.mqttMessages.splice(0, store.mqttMessages.length - 2000)
    }
    return n
}

// 清空 MQTT 消息列表与暂存
export function clearMqttMessages() {
    store.mqttMessages = []
    store.pendingMessages = []
}

// 主题着色：首次出现按池顺序分配并登记，后续保持恒定
export function topicColor(topic) {
    return pickTopicColor(topic, store.topicColorMap)
}

/* =========================================================================
 * 网络扫描
 * ========================================================================= */

// 结果行上限（超出丢弃最早的行）
export const SCAN_MAX_ROWS = 1024

// 按 IP upsert（同一 IP 会收到多次 result 帧：TCP 阶段先推、enrich 补全后再推），
// 必须合并而非追加，否则表格会出现重复行。
export function upsertScanResult(item) {
    if (!item || !item.ip) return
    const list = store.scanResults
    const idx = list.findIndex(r => r.ip === item.ip)
    if (idx >= 0) {
        Object.assign(list[idx], item)
    } else {
        list.push({ ...item })
        if (list.length > SCAN_MAX_ROWS) list.splice(0, list.length - SCAN_MAX_ROWS)
    }
}

// 清空本轮结果与差异标记
export function clearScanResults() {
    store.scanResults = []
    store.scanChanges = {}
    store.scanChangeList = { new: [], left: [], changed: [] }
}

// IP 数值（用于自然排序：.1.2 在 .1.10 之前）
function ipNum(ip) {
    const p = String(ip || '').split('.')
    return ((((+p[0]) || 0) * 256 + ((+p[1]) || 0)) * 256 + ((+p[2]) || 0)) * 256 + ((+p[3]) || 0)
}

// 结果排序：收藏置顶，组内按 IP 自然序
export function sortScanRows(list, favorites) {
    const favs = favorites || store.scanFavorites
    return [...(list || [])].sort((a, b) => {
        const fa = favs[a.ip] ? 0 : 1
        const fb = favs[b.ip] ? 0 : 1
        if (fa !== fb) return fa - fb
        return ipNum(a.ip) - ipNum(b.ip)
    })
}

// —— HTTP Server 工具函数 ——

// HTTP 请求记录上限
export const HTTP_MAX_RECORDS = 2000

// 新增 / 头部插入请求记录（最新在上）
export function pushHttpRequest(record) {
    if (!record) return
    const list = store.httpServerRequests
    list.unshift(record)
    if (list.length > HTTP_MAX_RECORDS) list.length = HTTP_MAX_RECORDS
}

// 清空 HTTP Server 请求记录
export function clearHttpRequests() {
    store.httpServerRequests = []
    store.httpServerSelected = null
}

// HTTP 方法 → 显示色（按语义着色，与 UI 原型一致）
export function methodColor(method) {
    switch ((method || '').toUpperCase()) {
        case 'GET': return '#3b82f6'      // 蓝
        case 'POST': return '#10b981'     // 绿
        case 'PUT': return '#f59e0b'      // 橙
        case 'DELETE': return '#ef4444'   // 红
        case 'PATCH': return '#8b5cf6'    // 紫
        case 'HEAD': return '#64748b'     // 灰
        case 'OPTIONS': return '#06b6d4'  // 青
        default: return '#94a3b8'         // 默认
    }
}
