# MQTT 收发功能 · 实施计划书

> 版本：v1.1（**已确认，实施中**）
> 日期：2026-10-14
> 状态：已确认，按阶段 1→4 实施

**已确认决策**：

| # | 决策项 | 确认结果 |
|---|---|---|
| 1 | UI 组织 | **方案 B** — 顶部模式切换新增「MQTT 调试」（置于右侧第三项），点击后左栏参数区 + 中栏收发区整体切换 |
| 2 | 订阅管理位置 | **右栏新增「订阅」Tab**（第 8 个模块） |
| 3 | 一期功能范围 | **仅核心收发**：TLS/SSL、遗嘱消息、MQTT 5.0、WebSocket 传输四项**一期不做**，列为二期 |
| 4 | 默认协议版本 | **3.1.1** |

---

## 一、结论摘要

新增 MQTT 收发在技术上没有阻塞项。公共 Broker 实测可达（`broker.emqx.io` 309ms、`broker.hivemq.com` 229ms、`test.mosquitto.org` 269ms），Python 侧成熟客户端 `paho-mqtt` 可直接接入现有 FastAPI 后端，且为纯 Python 包，PyInstaller 打包无 DLL 风险。

核心难点不在协议本身，而在**交互模型差异**：现有 TCP/UDP/串口是「字节流收发」，MQTT 是「发布/订阅」——发送必须带 Topic、QoS、Retain，接收必须知道来自哪个 Topic。因此 UI 需要新增三组参数，**推荐方案 B（顶部新增独立「MQTT 调试」模式）**，避免把 8+ 个 MQTT 专属字段挤进现有网络参数区。

预计改动：后端新增 3 个文件、修改 3 个文件；前端新增 2 个组件、修改 4 个文件。分 4 个阶段推进，每阶段有独立验收标准。

---

## 二、参考源码分析（GitHub）

### 2.1 主要参考：EMQX/MQTTX

| 项目 | 地址 | 技术栈 | 参考价值 |
|---|---|---|---|
| **MQTTX** | `github.com/emqx/MQTTX` | Electron + Vue3 + mqtt.js | 连接参数模型、订阅管理交互 |
| **paho.mqtt.python** | `github.com/eclipse-paho/paho.mqtt.python` | Python | 实际实施库及其 2.x 迁移指南 |

### 2.2 从 MQTTX `src/utils/mqttUtils.ts` 提炼的参数模型

MQTTX 的 `getDefaultRecord()` 定义了完整的连接记录结构，这是行业内验证过的参数集合：

```ts
// 来源：MQTTX src/utils/mqttUtils.ts getDefaultRecord()
clientId: getClientId(),        // 自动生成唯一 ID
host: 'broker.emqx.io', port: 1883, path: '/mqtt',
protocol: 'mqtt',               // mqtt / mqtts / ws / wss
username: '', password: '',
keepalive: 60,                  // 秒
connectTimeout: 10,             // 秒
clean: true,                    // Clean Session
reconnect: true, reconnectPeriod: 4000,   // ms
mqttVersion: '5.0',             // 3.1 / 3.1.1 / 5.0
ssl: false, certType: '', rejectUnauthorized: true,
ca: '', cert: '', key: '',
will: { lastWillTopic, lastWillPayload, lastWillQos, lastWillRetain },
subscriptions: [],              // { topic, qos, color, nl, rap, rh }
clientIdWithTime: false,        // clientId 追加重连时间戳
```

**关键设计点（已吸收到本方案）**：

1. **ClientID 必须唯一化** — MQTTX 用 `getClientId()` 随机生成，并提供 `clientIdWithTime` 选项在重连时追加时间戳。本项目支持**多开**，两个实例若用相同 ClientID 连同一 Broker 会互相踢下线，此点必须处理。
2. **重连与自动重订阅** — MQTTX 的 `options.resubscribe = autoResub`，重连成功后自动恢复订阅列表。本项目需自行维护订阅表并在 `on_connect` 中重放。
3. **订阅是一等公民** — 订阅列表独立于连接存在，带 QoS、颜色标记。不是「发一条 SUBSCRIBE 就完事」。
4. **协议与端口解耦** — `mqtt://` 1883、`mqtts://` 8883、`ws://` /`wss://` 走 path。协议切换时端口应自动带出默认值。
5. **发布参数四元组** — `topic + payload + qos + retain`，与连接参数分离。

### 2.3 paho-mqtt 2.x 必踩的坑（已确认）

`paho-mqtt >= 2.0.0` 强制要求显式声明回调 API 版本，否则直接抛 `ValueError: Unsupported callback API version`。回调签名也变了：

| 回调 | 1.x 签名 | 2.x VERSION2 签名 |
|---|---|---|
| `on_connect` | `(client, userdata, flags, rc)` | `(client, userdata, flags, reason_code, properties)` |
| `on_disconnect` | `(client, userdata, rc)` | `(client, userdata, flags, reason_code, properties)` |
| `on_message` | `(client, userdata, msg)` | **不变** |
| `on_publish` | `(client, userdata, mid)` | `(client, userdata, mid, reason_codes, properties)` |
| `on_subscribe` | `(client, userdata, mid, granted_qos)` | `(client, userdata, mid, reason_codes, properties)` |

**决策**：新项目直接用 `CallbackAPIVersion.VERSION2`（官方推荐），不用 VERSION1 兼容层。

---

## 三、现状接入点分析

### 3.1 现有架构（可直接复用）

```
┌─────────────┐   REST    ┌──────────────┐   socket   ┌────────┐
│  Vue3 前端   │ ────────► │  FastAPI 后端 │ ─────────► │ 对端设备 │
│             │ ◄──────── │              │ ◄───────── │        │
└─────────────┘  WebSocket └──────────────┘            └────────┘
                  (50ms 轮询队列)
```

| 层 | 现有实现 | MQTT 可复用度 |
|---|---|---|
| 连接管理 | `services/net_service.py` · `NetConnectionManager` | 结构可参照（dict 存 config/stats/queue），**代码不共用** |
| 数据推送 | `routes/websocket.py` · 50ms 轮询 + heartbeat | **完全复用模式**，新增一个 `/ws/mqtt/{id}` 端点 |
| 数据编码 | `utils/data_utils.py` · HEX/文本/校验 | **完全复用**（HEX 默认发送是既定需求） |
| 前端日志 | `store.js` · `addLogLine({dir,text,hex,...})` | **复用**，仅需扩展 `topic` 字段 |
| 持久化 | `store_service.py` · `%LOCALAPPDATA%\调试助手\store.json` | **复用**，新增 key 即可 |
| 文件选择 | `app.py` · pywebview `choose_file()` | **复用**（TLS 证书选择） |

### 3.2 必须新增的部分

| 缺口 | 原因 |
|---|---|
| `MqttConfig` 数据模型 | MQTT 参数与 TCP/UDP 完全不同构 |
| `services/mqtt_service.py` | paho 客户端生命周期、订阅表、消息队列 |
| `routes/mqtt.py` | connect / publish / subscribe / unsubscribe / status |
| 前端 MQTT 参数区 | 8+ 个专属字段 |
| 订阅管理 UI | 现有 7 个右侧模块中无对应项 |

---

## 四、方案对比

### 方案 A：并入「网络调试」（协议下拉加 MQTT）

| 维度 | 评价 |
|---|---|
| 改动量 | 小（约 60% 于方案 B） |
| 左栏 | ⚠️ 严重拥挤：ClientID / 用户名 / 密码 / KeepAlive / CleanSession / MQTT版本 / SSL 共 7 项要塞进现有 3 项空间 |
| 订阅管理 | ❌ 无位置，只能塞进右侧模块或弹窗 |
| 用户认知 | ⚠️ 协议下拉里混着「TCP Client / TCP Server / UDP / MQTT」，语义层级不一致 |
| 风险 | 低 |

### 方案 B：顶部新增「MQTT 调试」第三模式 ✅ **推荐**

```
[ 网络调试 ] [ 串口调试 ] [ MQTT调试 ]     ← 顶部模式切换新增一项
```

| 维度 | 评价 |
|---|---|
| 改动量 | 中（新增独立分支，但不动现有逻辑） |
| 左栏 | ✅ `mode==='mqtt'` 时渲染独立表单，字段完整不挤 |
| 订阅管理 | ✅ 有明确归属（见 4.1） |
| 日志/发送区 | ✅ 复用现有，仅发送区增加 Topic 行 |
| 回归风险 | ✅ 低——现有 network/serial 分支完全不动 |
| 一致性 | ✅ 与「串口调试」作为独立模式的既有设计一致 |

**推荐理由**：MQTT 的参数集与交互模型和 TCP/UDP 差异过大，强行合并会重演早期「界面杂乱」的问题（这是此前明确提过的负面反馈）。作为第三模式可保持各模式参数区干净，且完全不触碰现有已验证的逻辑。

### 4.1 订阅管理放哪里（方案 B 下的子决策）→ **已确认：B-1**

| 选项 | 说明 | 评价 |
|---|---|---|
| **B-1 右栏新增「订阅」Tab** ✅ **已选** | 作为第 8 个模块与快捷指令/批量发送并列 | 与现有右栏体系一致，右侧模块栏已有成熟的可拖动并排布局 |
| B-2 中栏日志区上方常驻订阅条 | 与「发送对象」条（TCP Server 客户端栏）同位置 | 订阅始终可见，但会占用中栏纵向空间 |
| B-3 左栏连接参数内嵌 | 折叠在「连接参数」里 | 空间不足，不推荐 |

---

## 五、技术设计

### 5.1 数据流

```
连接：  前端 POST /api/mqtt/connect ──► MqttManager.connect()
                                        ├─ paho.Client(VERSION2, client_id)
                                        ├─ username_pw_set / tls_set / will_set
                                        ├─ connect_async + loop_start()
                                        └─ on_connect → 重放订阅表

接收：  Broker ──► on_message(topic, payload, qos, retain)
                     ├─ 入 conn["queue"]（deque，上限 5000）
                     └─ stats.rxBytes/rxCount +=
        WS /ws/mqtt/{id} 50ms 轮询 ──► 前端 addLogLine({dir:'RX', topic})

发送：  前端 POST /api/mqtt/publish ──► client.publish(topic, payload, qos, retain)
                                        └─ stats.txBytes/txCount +=
```

### 5.2 后端改动

#### 5.2.1 新增依赖

```
paho-mqtt>=2.1.0
```

纯 Python 包，无编译产物，PyInstaller 可直接收集。需在 spec 的 `hiddenimports` 确认（首次打包后校验）。

#### 5.2.2 数据模型 — `models.py` 新增

> 一期范围已收敛为**核心收发**，TLS / 遗嘱 / MQTT5 / WebSocket 相关字段全部移除，避免 UI 出现不可用配置项。

```python
class MqttConfig(BaseModel):
    host: str = "broker.emqx.io"
    port: int = 1883
    client_id: str = ""            # 空则自动生成 debug-assistant-<8位随机>
    username: str = ""
    password: str = ""
    keepalive: int = 60
    clean: bool = True
    mqtt_version: str = "3.1.1"    # 一期固定 3.1.1（字段预留，UI 暂不暴露切换）
    reconnect: bool = True
    reconnect_period: int = 4000   # ms
    client_id_with_time: bool = False   # 重连时 ClientID 追加时间戳，规避多开冲突

class MqttSubscribeRequest(BaseModel):
    topic: str
    qos: int = 0

class MqttPublishRequest(BaseModel):
    topic: str
    payload: str
    format: str = "hex"            # 沿用 HEX 默认
    encoding: str = "utf-8"
    qos: int = 0
    retain: bool = False
```

#### 5.2.3 新增 `services/mqtt_service.py`

```
MqttConnectionManager
├─ connect(config)            → 建 paho client、设回调、connect_async + loop_start
├─ disconnect(id)             → disconnect + loop_stop + 清资源
├─ publish(id, topic, payload, qos, retain) → 返回 mid / 错误
├─ subscribe(id, topic, qos)  → 记入订阅表 + client.subscribe
├─ unsubscribe(id, topic)     → 出表 + client.unsubscribe
├─ get_subscriptions(id)      → [{topic, qos, state}]
├─ read_data(id)              → 从队列取 (topic, payload, qos, retain)  ← 供 WS 轮询
└─ get_status(id)             → {connected, stats, subscriptions}
```

**回调实现要点**（VERSION2）：

| 回调 | 职责 |
|---|---|
| `on_connect` | 记录连接状态；**重放订阅表**；`reason_code != 0` 时记录错误文本 |
| `on_message` | 入队 + 统计；payload 保留原始 bytes（HEX 显示在前端做） |
| `on_disconnect` | 更新 connected=False；区分「主动断开」与「异常掉线」 |
| `on_subscribe` | 更新订阅表状态（成功 / `reason_codes >= 128` 失败） |
| `on_publish` | QoS1/2 送达确认，更新统计 |

**多开 ClientID 冲突处理**：默认 `debug-assistant-<8位随机>`，用户可覆盖；提供「重连时追加时间戳」开关（对应 MQTTX `clientIdWithTime`）。

#### 5.2.4 新增 `routes/mqtt.py`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/mqtt/connect` | 建立连接（同步等待 CONNACK，超时 10s 报错） |
| POST | `/api/mqtt/disconnect/{id}` | 断开 |
| POST | `/api/mqtt/publish` | 发布消息 |
| POST | `/api/mqtt/subscribe` | 新增订阅 |
| POST | `/api/mqtt/unsubscribe` | 取消订阅 |
| GET | `/api/mqtt/subscriptions/{id}` | 订阅列表 |
| GET | `/api/mqtt/status/{id}` | 连接状态 + 统计 |

#### 5.2.5 修改 `routes/websocket.py`

新增 `/ws/mqtt/{connection_id}`，沿用现有 50ms 轮询 + heartbeat 结构，消息体扩展：

```json
{"type":"data","connection_id":"...","topic":"sensor/temp",
 "data":"...","hex_data":"01 03 ...","qos":0,"retain":false,"length":8,"timestamp":...}
```

#### 5.2.6 修改 `main.py`

注册 `mqtt_router`（**必须放在 `/{path:path}` catch-all 之前** —— 这是本项目踩过的坑）。

### 5.3 前端改动

| 文件 | 改动 |
|---|---|
| `api/index.js` | 新增 `mqttApi`（connect/disconnect/publish/subscribe/unsubscribe/status/createWebSocket） |
| `views/DebugView.vue` | ① 顶部模式组加 `mqtt`<br>② 左栏加 `mode==='mqtt'` 参数分支<br>③ 发送区在 MQTT 模式下增加 Topic 输入 + QoS 选择 + Retain 勾选<br>④ 日志行渲染 `topic` 标签<br>⑤ `toggleConnect` / `doSend` 增加 mqtt 分支 |
| `components/MqttSubscriptions.vue` | **新增** — 订阅列表（Topic / QoS / 状态 / 删除）+ 新增订阅输入行 |
| `store.js` | `PERSIST_KEYS` 增加 `mqttConfig`、`mqttSubscriptions`（走既有远程持久化） |

### 5.4 UI 布局（MQTT 模式）

```
┌────────────────────────────────────────────────────────────┐
│ 调试助手  [网络调试][串口调试][MQTT调试]        [已连接] [设置] │
├──────────┬─────────────────────────────────────────────────┤
│ 连接设置  │  ┌ 订阅栏 ────────────────────────────────────┐ │
│ ▼连接参数 │  │ [sensor/# ▾] [QoS 0 ▾] [+订阅]  3 个订阅   │ │
│  Broker  │  └───────────────────────────────────────────┘ │
│  端口     │  ┌ 数据日志 ──────────────────────────────────┐ │
│  ClientID│  │ RX [10:22:03] [sensor/temp] 01 03 00 00    │ │
│  用户名   │  │ TX [10:22:05] [cmd/reboot]  AA BB          │ │
│  密码     │  └───────────────────────────────────────────┘ │
│  KeepAlive│  ┌ 发送 ─────────────────────────────────────┐ │
│  Clean    │  │ Topic: [cmd/led      ] QoS:[0▾] ☐Retain  │ │
│  版本     │  │ [文本][HEX] 结束符[无▾] 校验[无▾]           │ │
│  ▸显示设置 │  │ ┌──────────────────────────────────────┐ │ │
│  ▸发送设置 │  │ │ 01 03 00 00 00 02                    │ │ │
│  ▸数据保存 │  │ └──────────────────────────────────────┘ │ │
│          │  │ [暂停显示] [发送] [清空]                    │ │
│ 接收/发送 │  └───────────────────────────────────────────┘ │
│ [断开连接]│                                                 │
└──────────┴─────────────────────────────────────────────────┘
```

---

## 六、分期实施计划

### 阶段 1 · 后端基础（可独立验证）

| 改动 | 文件 |
|---|---|
| 安装 `paho-mqtt` | venv + `requirements.txt` |
| 新增 `MqttConfig` / `MqttPublishRequest` / `MqttSubscribeRequest` | `models.py` |
| 新增 `MqttConnectionManager` | `services/mqtt_service.py`（新） |
| 新增 REST 路由 | `routes/mqtt.py`（新） |
| 注册路由 | `main.py` |

**验收**：curl 连接 `broker.emqx.io:1883` → 订阅 `test/debug` → 用独立 Python 脚本发布 → 通过 `/api/mqtt/status` 看到 rx 计数增加。

### 阶段 2 · 后端实时推送

| 改动 | 文件 |
|---|---|
| 新增 `/ws/mqtt/{connection_id}` | `routes/websocket.py` |

**验收**：建立 WebSocket，脚本发布消息后 WS 帧中可见 topic + hex_data。

### 阶段 3 · 前端接入

| 改动 | 文件 |
|---|---|
| 新增 `mqttApi` | `api/index.js` |
| 模式切换 + 左栏参数 + 发送区 Topic + 日志 topic 标签 | `views/DebugView.vue` |
| 订阅栏组件 | `components/MqttSubscriptions.vue`（新） |
| 持久化 key | `store.js` |

**验收**：UI 手动连通公共 Broker，订阅后能看到数据；发布后对端脚本能收到且字节一致（HEX 场景）。

### 阶段 4 · 打包与回归

| 步骤 | 说明 |
|---|---|
| `npm run build` | 前端构建到 `backend/static` |
| PyInstaller 重打包 | **不带 `--clean`**（既有坑） |
| 同步两处交付目录 | `C:\Users\yuanj\调试助手` + 工作区副本 |
| 回归测试 | 现有 `tests/e2e_test.py` 双实例 TCP 联调必须仍 5/5 通过 |
| 重新生成分发 zip | 更新 `调试助手_v1.1.0_Windows_x64.zip` |

---

## 七、风险与对策

| # | 风险 | 影响 | 对策 |
|---|---|---|---|
| 1 | **多开 ClientID 冲突**互相踢下线 | 中 | 默认随机 ClientID；提供「追加时间戳」开关；错误码 `Identifier rejected` 时前端友好提示 |
| 2 | `paho-mqtt` 2.x 回调签名变更 | 高 | 统一用 `CallbackAPIVersion.VERSION2`，按官方迁移表写回调 |
| 3 | PyInstaller 未收集 paho 子模块 | 高 | 打包后校验 `_internal/paho` 存在；必要时加 `hiddenimports` |
| 4 | 路由被 SPA catch-all 吞掉 | 中 | `mqtt_router` 注册在 `/{path:path}` 之前（既有教训） |
| 5 | 国内访问公共 Broker 不稳定 | 中 | 已测 3 个可用；默认填 `broker.emqx.io`，允许自由填写自建 Broker 地址 |
| 6 | QoS1/2 发布确认与统计时序 | 低 | `on_publish` 更新统计，不阻塞发送返回 |
| 7 | 订阅表与 Clean Session 不一致 | 低 | 本地维护订阅表，`on_connect` 无条件重放（对齐 MQTTX autoResub） |
| 8 | 打包体积增大 | 低 | paho-mqtt 约 250KB，可忽略 |

---

## 八、测试方案

| 层级 | 方法 |
|---|---|
| 单元 | paho 回调签名、ClientID 生成唯一性、订阅表重放 |
| 接口 | curl 连通 / 订阅 / 发布 / 状态查询 |
| 端到端 | 公共 Broker + 独立 Python 对端脚本，验证：HEX 发布字节一致、中文 payload、QoS1 送达、通配符 `sensor/#` 订阅、断线重连自动重订阅 |
| 回归 | `tests/e2e_test.py` 双实例 TCP 联调 5/5（确保不影响既有功能） |
| 打包 | 打包版 exe 实际连 Broker 收发一轮 |

**Broker 选型**：连接测试用 `broker.emqx.io:1883`（已实测 309ms 可达），备选 `broker.hivemq.com`、`test.mosquitto.org`。若为内网环境，需你提供自建 Broker 地址。

---

## 九、待你确认的决策点

| # | 决策 | 选项 | 我的建议 |
|---|---|---|---|
| 1 | UI 组织 | A 并入网络调试 / **B 独立 MQTT 模式** | **B** — 参数差异大，合并会挤爆左栏 |
| 2 | 订阅栏位置 | 右栏新 Tab / **中栏日志区上方常驻** | **中栏常驻** — 订阅是高频操作 |
| 3 | 一期功能范围 | □ TLS/SSL 证书<br>□ MQTT 5.0<br>□ 遗嘱消息<br>□ MQTT over WebSocket | 一期做 **TLS + 遗嘱**（成本低、现场会用）；MQTT5 与 WS 传输放二期 |
| 4 | MQTT 版本默认 | 3.1.1 / 5.0 | **3.1.1** — 现场设备与 Broker 兼容性最广 |

确认后按阶段 1→4 实施，每阶段完成即向你汇报实测结果。
