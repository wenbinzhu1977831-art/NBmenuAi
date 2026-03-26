# NoodleBox AI 电话点餐系统 — 项目架构全解

> **项目路径：** `c:\Users\wenbi\OneDrive\桌面\Gemini 3 Live API (Node)`  
> **技术栈：** Node.js + TypeScript + Fastify + Google Gemini Live API + React/Vite + PostgreSQL/SQLite

---

## 一、这个项目是做什么的？

这是一套 **AI 自动接电话的餐厅点餐系统**。当客人打电话给 Noodle Box Drogheda（爱尔兰德罗赫达的一家中式外卖餐厅）时，不是人工接听，而是由 Google Gemini AI 通过语音对话，完成点菜 → 确认地址 → 算账 → 确认下单的全部流程。

系统支持两种入口：
1. **Twilio 电话线路**：真实客户从座机/手机打来的电话
2. **网页 WebRTC 模拟器**：店老板在浏览器内测试 AI 响应的工具

---

## 二、整体架构图

```
+─────────────────────────────────────────────────────+
│             客人拨打电话 (PSTN)                        │
│                     │                               │
│              [Twilio 云平台]                          │
│             /media-stream (WebSocket)                │
│                     │                               │
│    ┌────────────────▼─────────────────────────────┐  │
│    │         Fastify HTTP+WS 服务器                 │  │
│    │              server.ts                        │  │
│    │                                               │  │
│    │    bridge/twilioGemini.ts ←→ Gemini Live API  │  │
│    │    bridge/webrtcGemini.ts ← 网页浏览器 (老板)  │  │
│    │                                               │  │
│    │    tools/   ← AI 工具调用处理层               │  │
│    │    routes/  ← HTTP API + Admin WebSocket      │  │
│    │    database.ts ← PostgreSQL / SQLite           │  │
│    └───────────────────────────────────────────────┘  │
│                     │                               │
│              [React 管理后台]                         │
│         (由 Fastify 直接伺服 frontend/dist)           │
+─────────────────────────────────────────────────────+
```

---

## 三、目录结构总览

```
Gemini 3 Live API (Node)/
├── src/                      ← Node.js 后端 TypeScript 代码
│   ├── server.ts             ← 🏠 主入口：Fastify 服务启动
│   ├── config.ts             ← ⚙️ 配置管理单例（支持热重载）
│   ├── database.ts           ← 🗄️ 数据库抽象层（双环境适配）
│   ├── prompts.ts            ← 🧠 AI 系统指令生成器
│   ├── audioUtils.ts         ← 🔊 音频格式转换工具函数
│   ├── bridge/
│   │   ├── twilioGemini.ts   ← 📞 Twilio电话 ↔ Gemini 核心桥接
│   │   └── webrtcGemini.ts   ← 💻 网页模拟 ↔ Gemini 桥接
│   ├── routes/
│   │   ├── admin.ts          ← 🖥️ 管理后台 REST+WebSocket 接口
│   │   └── twilio.ts         ← 📱 Twilio Webhook 接口（接/挂电话）
│   └── tools/
│       ├── address.ts        ← 🗺️ AI工具：爱尔兰地址查询
│       ├── pricing.ts        ← 💰 AI工具：订单总价计算
│       ├── history.ts        ← 📋 AI工具：历史订单查询
│       └── manageCall.ts     ← 📲 AI工具：挂断/转人工定义
├── frontend/                 ← React/Vite 前端管理面板
│   └── src/
│       └── App.jsx           ← 整个管理面板 (约 113KB 的单文件)
├── menu.json                 ← 菜单母版 JSON（341KB）
├── menu_compressed.md        ← 压缩后的菜单（给 AI 喂的那份）
├── Delivery Area.txt         ← 配送区域与运费配置文本
├── package.json              ← Node.js 依赖声明
├── Dockerfile                ← 容器化部署配置
└── .env.example              ← 环境变量说明模板
```

---

## 四、核心模块详解

### 1. [server.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/server.ts) — 系统主入口 (Fastify 核心)

启动顺序：
1. 注册 CORS、WebSocket 插件
2. 初始化数据库 + 建表 + 载入菜单
3. 从数据库读取最新配置（热重载）
4. 注册 WebSocket 路由：`/media-stream`（Twilio）和 `/api/admin/web_call`（WebRTC）
5. 注册 HTTP 路由（Twilio Webhook、管理后台 API）
6. 托管 React 前端静态文件（SPA 兜底）
7. 监听 `0.0.0.0:8080`

---

### 2. [config.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/config.ts) — 配置管理（单例模式）

**优先级从高到低：**
```
数据库 settings_json > 环境变量 .env > 代码默认值
```

核心配置项：
| 配置项 | 说明 |
|---|---|
| `googleApiKey` | Gemini API 密钥 |
| `masterSwitch` | `active`/`offline`/`bypass` 三种运营模式 |
| `modelName` | 当前使用的 Gemini 模型（默认 `gemini-2.5-flash-native-audio-preview-12-2025`）|
| `voiceName` | AI 声音，默认 `Aoede` |
| `maxConcurrentCalls` | 最多同时接几路电话（默认 3）|
| `discountActive` | 是否开启促销折扣 |

**热更新机制**：每通新电话接入前会调用 `configManager.reload()` 从数据库拉取最新设置，无需重启服务。

---

### 3. [bridge/twilioGemini.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/bridge/twilioGemini.ts) — 电话核心桥接

这是整个系统**逻辑最复杂**的文件。每通电话接入时，它会：

**同时维护 2 条 WebSocket**：
- **左边**：Twilio（客人的电话）
- **右边**：Google Gemini（AI 大脑）

**音频流处理管线（Twilio → Gemini）：**
```
Twilio μ-law 8kHz → 解码 PCM16 → 升频 16kHz → Base64 → Gemini
```

**AI 回声管线（Gemini → Twilio）：**
```
Gemini PCM16 24kHz → 降频 8kHz → 编码 μ-law → Base64 → Twilio
```

**关键机制：**
- **打断检测**：Gemini 发来 `interrupted` 信号时，向 Twilio 发 `clear` 清空已缓冲但未播出的音频
- **续单草稿救援**：如果电话中途断线但已经 [calculate_total](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/tools/pricing.ts#52-225) 过，会自动将草稿单保存为 `ORD-INCOMPLETE-...`

---

### 4. [bridge/webrtcGemini.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/bridge/webrtcGemini.ts) — 网页模拟器桥接

与 [twilioGemini.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/bridge/twilioGemini.ts) 几乎相同，但关键区别：
- **无需音频转码**：浏览器直接发 PCM16 16kHz，Gemini 原生支持
- **打断处理**：发 JSON `{type: 'interrupted'}` 给前端，由浏览器内 JS 负责停止 AudioContext 播放
- 会话 ID 以 `WEB-` 开头标识是测试会话

---

### 5. [prompts.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/prompts.ts) — AI 人设生成器

每通电话接入时动态生成系统提示词，包含：
- 当前爱尔兰时间 + 星期几
- 智能判断营业繁忙度（周五/六/日/公假 = 忙碌 → 外卖时间延长至 40-50 分钟）
- 老客人名字/地址（如果有档案）
- 当前促销活动
- 完整压缩菜单文本
- 9 步标准接单流程（严格约束 AI 行为）

---

### 6. `tools/` — AI 工具（Function Calling）

AI 在对话中会**主动调用**以下 4 个工具：

| 工具名 | 触发时机 | 执行内容 |
|---|---|---|
| [search_address](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/tools/address.ts#86-162) | 客人报配送地址时 | 调用 AutoAddress API，验证并查询爱尔兰门牌，限制仅送 Louth/Meath 两个郡 |
| [calculate_total](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/tools/pricing.ts#52-225) | 点完所有菜、确认服务类型和支付方式后 | 后端精准计算小计、折扣、运费、刷卡费，生成文字小票返还给 AI |
| `get_past_order` | 客人说"跟上次一样" | 按订单ID查历史单据明细 |
| `end_call` | AI 说出再见后 | 正式下单入库、广播给后台、延时挂断(等待告别语播完) |
| `transfer_call` | 客人要求转人工 | 设置转接意图、断开连接，Twilio 侧会自动路由到人工 |

---

### 7. [database.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/database.ts) — 双环境数据库层

**环境识别**：
- 有 `CLOUD_SQL_CONNECTION_NAME` 环境变量 → 连 **PostgreSQL**（Google Cloud SQL）
- 无此环境变量 → 连本地 **SQLite** (`app.db`)

**数据表结构：**

| 表名 | 作用 |
|---|---|
| `customers` | 客户档案（电话、姓名、地址、最后一单ID）|
| `orders` | 订单记录（含 items JSON、transcript JSON）|
| `app_settings` | Key-Value 动态配置（菜单、settings_json 等）|
| `menu_categories` | 菜单分类 |
| `menu_items` | 菜品详情（名、价格、过敏原）|
| `menu_options` | 菜品加料选项 |

**菜单自动播种**：首次启动时若 `menu_items` 表为空，自动从 [menu.json](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/menu.json) 导入全套菜单。

---

### 8. [routes/admin.ts](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/src/routes/admin.ts) — 管理后台 API

| 接口 | 说明 |
|---|---|
| `GET /api/admin/ws` | WebSocket，给店老板网页推实时战况（通话、字幕、工具调用、新订单）|
| `GET /api/admin/orders` | 获取历史订单（支持按日期过滤）|
| `GET /api/admin/settings` | 读取所有系统配置 |
| `POST /api/admin/settings` | 保存配置（含热重载）|
| `GET /api/admin/stats` | 今日统计数字 |
| `GET /api/admin/menu` | 获取完整菜单数据 |
| `POST /api/admin/apply-config` | 应用配置（新版接口）|
| `GET /api/admin/auth-check` | Bearer Token 密码验证 |

---

## 五、完整呼叫数据流（以外卖订单为例）

```
1. 客人打电话进来
        ↓
2. Twilio 接听，向 /media-stream 发起 WebSocket 连接
        ↓
3. twilioGemini.ts 收到 start 事件，建立 Gemini WebSocket 连接
        ↓
4. 向 Gemini 发送 setup（含模型、系统提示词、工具列表）
        ↓
5. 发 "Call connected" 触发 AI 开口说 "Hello!"
        ↓
6. Twilio 持续推送客人声音 → 升频 → 转发给 Gemini
        ↓
7. Gemini 生成回答音频 → 降频 → 发回 Twilio → 客人听到声音
        ↓
8. 客人说地址 → AI 调用 search_address → 查 AutoAddress API → 告知运费
        ↓
9. 客人点完菜 → AI 调用 calculate_total → 后端算账 → 吐出小票文字
        ↓
10. AI 确认信息，调用 end_call（含完整订单参数）
        ↓
11. 后端 saveOrder() 写入数据库，broadcastAdmin 通知管理后台
        ↓
12. 等告别语音播完 → 关闭两条 WebSocket → 本通电话结束
```

---

## 六、部署方式

```dockerfile
# Dockerfile 流程：
FROM node:20-slim
→ 安装 better-sqlite3 编译依赖
→ npm ci 安装 Node.js 依赖
→ npm run build 编译 TypeScript
→ 构建 React 前端 (frontend/npm run build)
→ EXPOSE 8080
→ CMD ["node", "dist/server.js"]
```

**本地开发：** `npm run dev`（使用 `ts-node` 直接跑 TypeScript，连 SQLite）  
**生产运行：** 部署为 Docker 容器到 **Google Cloud Run**，通过 Unix Socket 连 Cloud SQL（PostgreSQL）

---

## 七、关键环境变量（[.env.example](file:///c:/Users/wenbi/OneDrive/%E6%A1%8C%E9%9D%A2/Gemini%203%20Live%20API%20%28Node%29/.env.example)）

| 变量名 | 说明 |
|---|---|
| `GOOGLE_API_KEY` | Gemini API 密钥 |
| `AUTOADDRESS_API_KEY` | 爱尔兰地址查询 API 密钥 |
| `ADMIN_PASSWORD` | 管理后台登录密码 |
| `TRANSFER_PHONE_NUMBER` | 转人工时的目标电话号 |
| `CLOUD_SQL_CONNECTION_NAME` | GCP 的 Cloud SQL 连接名（有=用 PostgreSQL，无=用 SQLite）|
| `DB_NAME / DB_USER / DB_PASSWORD` | Cloud SQL 数据库凭据 |
