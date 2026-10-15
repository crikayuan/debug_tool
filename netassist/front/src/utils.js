// 前端工具函数

export function formatTime(ts, full = false) {
    const d = new Date(ts * 1000)
    const p = (n) => String(n).padStart(2, '0')
    const hh = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
    if (!full) return hh
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${hh}.${String(d.getMilliseconds()).padStart(3, '0')}`
}

export function nowTs() {
    return Math.floor(Date.now() / 1000)
}

// 判断字符串是否为十六进制格式（每字节两位，空格分隔）
export function isHexString(s) {
    const cleaned = s.replace(/\s+/g, '')
    if (cleaned.length === 0 || cleaned.length % 2 !== 0) return false
    return /^[0-9a-fA-F]+$/.test(cleaned)
}

// 十六进制字符串转文本（前端显示用，简单转换）
export function hexToText(hex) {
    const cleaned = hex.replace(/\s+/g, '')
    if (cleaned.length % 2 !== 0) return hex
    let out = ''
    for (let i = 0; i < cleaned.length; i += 2) {
        const code = parseInt(cleaned.substr(i, 2), 16)
        if (code >= 32 && code < 127) {
            out += String.fromCharCode(code)
        } else {
            out += '.'
        }
    }
    return out
}

// 把任意输入规范化成与实际发送字节一致的 HEX 显示（奇数长度左补 0；非纯 HEX 原样返回）
export function normalizeHex(s) {
    const raw = s || ''
    const cleaned = raw.replace(/\s+/g, '')
    if (!cleaned) return ''
    if (!/^[0-9a-fA-F]+$/.test(cleaned)) return raw
    const v = cleaned.length % 2 !== 0 ? '0' + cleaned : cleaned
    return (v.match(/.{2}/g) || []).join(' ').toUpperCase()
}

export function textToHex(text) {
    let hex = ''
    for (let i = 0; i < text.length; i++) {
        hex += text.charCodeAt(i).toString(16).padStart(2, '0') + ' '
    }
    return hex.trim().toUpperCase()
}

/* =========================================================================
 * MQTT 辅助工具
 * ========================================================================= */

// Topic 着色池：8 色，与 UI 原型 V3 完全一致
export const TOPIC_COLOR_POOL = [
    '#2f6fed', '#18a058', '#f59e0b', '#8e5cd8',
    '#e54545', '#0ea5e9', '#f43f5e', '#10b981'
]

// HEX 颜色转 rgba（用于主题标签 10% 透明底色）
export function hexToRgba(hex, alpha = 1) {
    const h = String(hex || '').replace('#', '')
    if (h.length !== 6) return hex
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${alpha})`
}

// MQTT 主题通配符匹配：+ 匹配单层，# 匹配剩余所有层级（含 0 层）
export function matchTopic(actual, pattern) {
    const a = String(actual || '').split('/')
    const p = String(pattern || '').split('/')
    for (let i = 0; i < p.length; i++) {
        if (p[i] === '#') return true
        if (i >= a.length) return false
        if (p[i] === '+') continue
        if (p[i] !== a[i]) return false
    }
    return a.length === p.length
}

// 主题首次出现按池顺序分配颜色并登记进 colorMap，后续恒定不变
export function topicColor(topic, colorMap) {
    const map = colorMap || {}
    if (!map[topic]) {
        map[topic] = TOPIC_COLOR_POOL[Object.keys(map).length % TOPIC_COLOR_POOL.length]
    }
    return map[topic]
}
