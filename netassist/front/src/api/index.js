// API配置
// 智能检测环境并配置API基础URL
const getAPIBaseURL = () => {
    if (window.location.port === '3000') {
        return '/api'
    }
    if (window.location.protocol === 'file:') {
        return 'http://localhost:20001/api'
    }
    return `${window.location.protocol}//${window.location.host}/api`
}

const getWSBaseURL = () => {
    if (window.location.port === '3000') {
        return '/ws'
    }
    if (window.location.protocol === 'file:') {
        return 'ws://localhost:20001/ws'
    }
    return `${window.location.protocol.replace('http', 'ws')}//${window.location.host}/ws`
}

const API_BASE_URL = getAPIBaseURL()
const WS_BASE_URL = getWSBaseURL()

// HTTP请求封装
async function apiRequest(url, options = {}) {
    const response = await fetch(`${API_BASE_URL}${url}`, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    })

    if (!response.ok) {
        let errorMessage = null
        try {
            const errorData = await response.json()
            if (errorData && errorData.detail) {
                errorMessage = errorData.detail
            }
        } catch (e) { /* ignore */ }

        if (errorMessage) {
            throw new Error(errorMessage)
        }
        throw new Error(`HTTP错误 ${response.status}`)
    }

    return await response.json()
}

// 网络相关API
export const netApi = {
    async connect(config) {
        return await apiRequest('/net/connect', {
            method: 'POST',
            body: JSON.stringify(config)
        })
    },

    async disconnect(connectionId) {
        return await apiRequest(`/net/disconnect/${connectionId}`, { method: 'POST' })
    },

    async sendData(connectionId, payload = {}) {
        if (!connectionId) throw new Error('连接ID不能为空')
        const requestData = {
            data: String(payload.data || ''),
            format: payload.format || 'text',
            encoding: payload.encoding || 'utf-8',
            end_chars: payload.end_chars || '',
            target: payload.target || null,
            append_check: payload.append_check || null
        }
        return await apiRequest(`/net/send/${connectionId}`, {
            method: 'POST',
            body: JSON.stringify(requestData)
        })
    },

    async getStatus(connectionId) {
        return await apiRequest(`/net/status/${connectionId}`)
    },

    async getClients(connectionId) {
        return await apiRequest(`/net/clients/${connectionId}`)
    },

    async disconnectClient(connectionId, clientId) {
        return await apiRequest(`/net/client/${connectionId}/disconnect/${clientId}`, { method: 'POST' })
    },

    createWebSocket(connectionId, encoding, onMessage, onClose, onError) {
        const wsUrl = `${WS_BASE_URL}/net/${connectionId}?encoding=${encoding || 'utf-8'}`
        const ws = new WebSocket(wsUrl)
        ws.onopen = () => console.log('WS已连接:', wsUrl)
        ws.onmessage = (event) => {
            try {
                onMessage && onMessage(JSON.parse(event.data))
            } catch (e) {
                console.error('WS消息解析错误:', e)
            }
        }
        ws.onclose = onClose
        ws.onerror = onError
        return ws
    }
}

// 串口相关API
export const serialApi = {
    async getPorts() {
        return await apiRequest('/serial/ports')
    },

    async connect(config) {
        return await apiRequest('/serial/connect', {
            method: 'POST',
            body: JSON.stringify(config)
        })
    },

    async disconnect(port) {
        return await apiRequest(`/serial/disconnect/${port}`, { method: 'POST' })
    },

    async sendData(port, payload = {}) {
        if (!port) throw new Error('串口不能为空')
        const requestData = {
            data: String(payload.data || ''),
            format: payload.format || 'text',
            encoding: payload.encoding || 'utf-8',
            end_chars: payload.end_chars || '',
            append_check: payload.append_check || null
        }
        return await apiRequest(`/serial/send/${port}`, {
            method: 'POST',
            body: JSON.stringify(requestData)
        })
    },

    async getStatus(port) {
        return await apiRequest(`/serial/status/${port}`)
    },

    createWebSocket(port, encoding, onMessage, onClose, onError) {
        const ws = new WebSocket(`${WS_BASE_URL}/serial/${port}?encoding=${encoding || 'utf-8'}`)
        ws.onmessage = (event) => {
            try {
                onMessage && onMessage(JSON.parse(event.data))
            } catch (e) {
                console.error('WS消息解析错误:', e)
            }
        }
        ws.onclose = onClose
        ws.onerror = onError
        return ws
    }
}

// MQTT 相关API
export const mqttApi = {
    async connect(config) {
        return await apiRequest('/mqtt/connect', {
            method: 'POST',
            body: JSON.stringify(config)
        })
    },

    async disconnect(connectionId) {
        return await apiRequest(`/mqtt/disconnect/${connectionId}`, { method: 'POST' })
    },

    // 发布：payload 携带 topic / data / format / encoding / qos / retain / end_chars / append_check
    async publish(connectionId, payload = {}) {
        if (!connectionId) throw new Error('连接ID不能为空')
        const requestData = {
            topic: payload.topic || '',
            payload: String(payload.data ?? payload.payload ?? ''),
            format: payload.format || 'hex',
            encoding: payload.encoding || 'utf-8',
            qos: payload.qos ?? 0,
            retain: !!payload.retain,
            end_chars: payload.end_chars || '',
            append_check: payload.append_check || null
        }
        return await apiRequest(`/mqtt/publish/${connectionId}`, {
            method: 'POST',
            body: JSON.stringify(requestData)
        })
    },

    async subscribe(connectionId, topic, qos = 0) {
        return await apiRequest(`/mqtt/subscribe/${connectionId}`, {
            method: 'POST',
            body: JSON.stringify({ topic, qos })
        })
    },

    async unsubscribe(connectionId, topic) {
        return await apiRequest(`/mqtt/unsubscribe/${connectionId}`, {
            method: 'POST',
            body: JSON.stringify({ topic })
        })
    },

    async getSubscriptions(connectionId) {
        return await apiRequest(`/mqtt/subscriptions/${connectionId}`)
    },

    async getStatus(connectionId) {
        return await apiRequest(`/mqtt/status/${connectionId}`)
    },

    createWebSocket(connectionId, encoding, onMessage, onClose, onError) {
        const wsUrl = `${WS_BASE_URL}/mqtt/${connectionId}?encoding=${encoding || 'utf-8'}`
        const ws = new WebSocket(wsUrl)
        ws.onopen = () => console.log('MQTT WS已连接:', wsUrl)
        ws.onmessage = (event) => {
            try {
                onMessage && onMessage(JSON.parse(event.data))
            } catch (e) {
                console.error('WS消息解析错误:', e)
            }
        }
        ws.onclose = onClose
        ws.onerror = onError
        return ws
    }
}

// 网络扫描相关API
export const scanApi = {
    // 本机可用网段
    async getSegments() {
        return await apiRequest('/scan/segments')
    },

    // 启动扫描，config 为后端 ScanConfig（snake_case）
    async start(config) {
        return await apiRequest('/scan/start', {
            method: 'POST',
            body: JSON.stringify(config)
        })
    },

    async stop(taskId) {
        return await apiRequest(`/scan/stop/${taskId}`, { method: 'POST' })
    },

    // 全量结果（用于刷新后恢复）
    async getResult(taskId) {
        return await apiRequest(`/scan/result/${taskId}`)
    },

    // 导出 CSV：{ items, task_id?, directory?, filename? }
    async exportCsv(payload) {
        return await apiRequest('/scan/export', {
            method: 'POST',
            body: JSON.stringify(payload || {})
        })
    },

    // 进度与结果推送 WebSocket
    createWebSocket(taskId, onMessage, onClose, onError) {
        const wsUrl = `${WS_BASE_URL}/scan/${taskId}`
        const ws = new WebSocket(wsUrl)
        ws.onopen = () => console.log('扫描 WS已连接:', wsUrl)
        ws.onmessage = (event) => {
            try {
                onMessage && onMessage(JSON.parse(event.data))
            } catch (e) {
                console.error('WS消息解析错误:', e)
            }
        }
        ws.onclose = onClose
        ws.onerror = onError
        return ws
    }
}

// 本机数据持久化API（快捷指令 / 批量 / 历史 / 自动应答 / 设置）
export const storeApi = {
    async getPath() { return await apiRequest('/store/path') },
    async get(key) { return await apiRequest(`/store/${key}`) },
    async set(key, value) {
        return await apiRequest(`/store/${key}`, {
            method: 'PUT',
            body: JSON.stringify({ value })
        })
    }
}

// 系统配置API
export const systemApi = {
    async getPortConfig() { return await apiRequest('/system/config/port') },
    async updatePortConfig(port) {
        return await apiRequest('/system/config/port', {
            method: 'POST',
            body: JSON.stringify({ port })
        })
    },
    async restartService() { return await apiRequest('/system/restart', { method: 'POST' }) },
    async getSystemInfo() { return await apiRequest('/system/info') },
    async getInterfaces() { return await apiRequest('/system/interfaces') }
}

// 工具箱API
export const toolboxApi = {
    async check(algorithm, data, format = 'hex') {
        return await apiRequest('/toolbox/check', {
            method: 'POST',
            body: JSON.stringify({ algorithm, data, format })
        })
    },
    async convert(data, fromFormat, toFormat, encoding = 'utf-8') {
        return await apiRequest('/toolbox/convert', {
            method: 'POST',
            body: JSON.stringify({ data, from_format: fromFormat, to_format: toFormat, encoding })
        })
    }
}

// Modbus API
export const modbusApi = {
    async build(payload) {
        return await apiRequest('/modbus/build', {
            method: 'POST',
            body: JSON.stringify(payload)
        })
    }
}

// 日志API
export const logApi = {
    async save(payload) {
        return await apiRequest('/log/save', {
            method: 'POST',
            body: JSON.stringify(payload)
        })
    }
}

// HTTP Server API（第五模式：本机启动 HTTP 服务端，接收任意 client 数据）
export const httpServerApi = {
    // 启动：config = { port, bind, response: {code, content_type, body, delay_ms, echo} }
    async start(config) {
        return await apiRequest('/http-server/start', {
            method: 'POST',
            body: JSON.stringify(config)
        })
    },
    // 停止
    async stop() {
        return await apiRequest('/http-server/stop', { method: 'POST' })
    },
    // 状态快照（含 addresses、total、count 等）
    async status() {
        return await apiRequest('/http-server/status')
    },
    // 全量请求记录
    async getRequests() {
        return await apiRequest('/http-server/requests')
    },
    // 清空请求记录
    async clear() {
        return await apiRequest('/http-server/clear', { method: 'POST' })
    },
    // 更新响应配置：{ echo?, code?, content_type?, body?, delay_ms? }
    async setResponse(payload) {
        return await apiRequest('/http-server/response', {
            method: 'POST',
            body: JSON.stringify(payload || {})
        })
    },
    // 导出请求日志：{ directory, filename }
    async exportLog(payload) {
        return await apiRequest('/http-server/export', {
            method: 'POST',
            body: JSON.stringify(payload || {})
        })
    },
    // 实时请求推送 WebSocket
    createWebSocket(sessionId, onMessage, onClose, onError) {
        const wsUrl = `${WS_BASE_URL}/http/${sessionId}`
        const ws = new WebSocket(wsUrl)
        ws.onopen = () => console.log('HTTP Server WS已连接:', wsUrl)
        ws.onmessage = (event) => {
            try {
                onMessage && onMessage(JSON.parse(event.data))
            } catch (e) {
                console.error('HTTP Server WS消息解析错误:', e)
            }
        }
        ws.onclose = onClose
        ws.onerror = onError
        return ws
    }
}
