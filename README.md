# 🍜 Gemini AI 智能电话点餐系统

> **Noodle Box Drogheda — AI 语音服务台**  
> 基于 Google Gemini 2.5 Flash Native Audio 的全双工实时语音点餐平台。  
> 支持 Twilio 真实来电 + WebRTC 网页模拟通话，可多路并发，内置中英文管理控制台。

---

## 📂 项目结构与核心模块

```
Gemini 3 Live API/
├── server.py               # 主网关（FastAPI + WebSocket 桥接）
├── boot.py                 # Cloud Run 启动包装器
├── config.py               # 动态配置（热重载，无需重启）
├── database.py             # SQLite ORM（客户 / 订单 / 菜单）
├── models.py               # SQLAlchemy 数据模型定义
├── prompts.py              # 系统指令动态生成器
├── audio_injector.py       # 工具调用期间的键盘打字音注入
├── tools_pricing.py        # AI 工具：订单总价计算
├── tools_address.py        # AI 工具：爱尔兰地址查询（AutoAddress API）
├── tools_history.py        # AI 工具：历史订单查询
├── tools_manage_call.py    # AI 工具：挂断 / 转接人工
├── menu.json               # 主菜单数据（SQLite 来源）
├── menu_factory.json       # 容器内备用菜单（兜底）
├── menu_compressed.md      # AI 用菜单文本（已压缩）
├── app.db                  # 本地 SQLite 数据库
├── 键盘.wav                 # 工具等待音效
├── Dockerfile              # 容器镜像定义
├── docker-compose.yml      # 本地 Docker 开发
├── cloud_run_env.yaml      # Cloud Run 环境变量模板
├── requirements.txt        # Python 依赖
├── .env / .env.example     # 环境变量（本地）
├── frontend/               # React 管理控制台
│   ├── src/App.jsx         # 主控制台（2200+ 行）
│   └── src/components/
│       ├── WebCallSimulator.jsx   # 网页麦克风通话模拟器
│       └── MenuGUI.jsx            # 菜单可视化编辑器
└── scripts/                # 运维工具脚本
    ├── migrate_orders_only.py     # 订单数据迁移
    ├── upload_to_cloud_sql.py     # 上传数据到 Cloud SQL
    ├── verify_admin_login.py      # 验证管理员登录
    ├── verify_menu.py             # 菜单完整性检查
    └── test_*.py                  # 单元测试脚本
```

---

## 🏗️ 核心架构说明

### 1. 电话接入层（双通道）

| 通道 | 入口 | 说明 |
|---|---|---|
| **Twilio 真实来电** | `/incoming-call` → `/media-stream` | 处理真实电话，8kHz μ-law ↔ 16kHz PCM 双向转换 |
| **WebRTC 网页测试** | `/api/rtc/connect` | 本地网页麦克风直连 Gemini，无需 Twilio 费用 |

两条通道共享同一套 **并发上限控制**（`config.max_concurrent_calls`），均写入统一的呼入日志（`call_log`）。

### 2. 并发通话隔离

每路通话使用独立的 `call_sid`（Twilio 真实 SID 或 `web_xxxxxxxx` 虚拟 SID），完全独立的：
- Gemini WebSocket 会话（独立 AI 大脑）
- 对话记录 (`call_transcript`)
- 草稿订单 (`draft_order`)
- 状态感知 (`CALL_STATES`, `ACTIVE_CALLS`)

### 3. AI 实时转录

Gemini 配置了双向转录：
- `inputAudioTranscription`：客户语音 → 文字（流式）
- `outputAudioTranscription`：AI 语音 → 文字（流式）

转录通过 WebSocket 推送到管理面板，以打字机效果（TypewriterText 组件）逐字显示。

### 4. 工具调用链

```
AI 决策 → Function Call
         ├── calculate_total()     → tools_pricing.py
         ├── search_address()      → tools_address.py  
         ├── get_past_order()      → tools_history.py
         ├── end_call()            → tools_manage_call.py → database.save_order()
         └── transfer_call()       → tools_manage_call.py → Twilio <Dial>
```

工具等待期间，`audio_injector.py` 向音频流注入键盘音防止"沉默挂断"。

---

## 🚀 本地开发启动指南

### 步骤 1：配置环境变量

复制 `.env.example` 为 `.env` 并填写：

```env
GEMINI_API_KEY=your_gemini_api_key
ADMIN_PASSWORD=your_secure_password
TWILIO_AUTH_TOKEN=your_twilio_auth_token
# 以下仅生产环境需要
# CLOUD_SQL_CONNECTION_NAME=project:region:instance
```

### 步骤 2：启动 Python 后端

```bash
pip install -r requirements.txt
python server.py          # 本地开发
# 或
python boot.py            # 等价生产启动（捕获启动崩溃日志）
```

服务运行在 `http://localhost:8080`（`PORT` 环境变量可调）。

### 步骤 3：启动 React 管理面板

```bash
cd frontend
npm install
npm run dev               # 开发服务器，热重载
# 或
npm run build             # 构建生产前端（部署前执行）
```

访问 `http://localhost:5173` 进入控制台。

### 步骤 4：接入 Twilio（真实来电测试）

需要内网穿透工具将本地 8080 暴露到公网：

```bash
ngrok http 8080
```

在 [Twilio Console](https://console.twilio.com) 将购买的号码 Webhook 指向：
```
https://你的ngrok地址/incoming-call
```

> **WebRTC 网页测试无需 Twilio**：登录管理面板 → Dashboard → 点击 "Start Web Call"，直接用电脑麦克风模拟来电。

---

## ☁️ Google Cloud Run 部署指南

### 部署流程

```bash
# 1. 构建前端（必须在部署前执行）
cd frontend && npm run build && cd ..

# 2. 构建并推送容器镜像
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/gemini-live-api

# 3. 部署到 Cloud Run
gcloud run deploy gemini-live-api \
  --image gcr.io/YOUR_PROJECT_ID/gemini-live-api \
  --region europe-west1 \
  --max-instances 1 \
  --set-env-vars GEMINI_API_KEY="...",ADMIN_PASSWORD="...",TWILIO_AUTH_TOKEN="..."
```

> **为何 `--max-instances 1`？** `call_log`、`TOKEN_STORE`（登录 Token）等关键状态存于内存，多实例会造成请求路由不一致。单实例保证所有 WebSocket 连接在同一进程内共享状态。

### 数据持久化（⚠️ 重要）

Cloud Run 每次部署都会**重置容器文件系统**，`app.db` 会丢失。

**每次部署前必做**：
1. 管理面板 → `System Config` → **Backup Database (app.db)**
2. 下载的 `app.db` 覆盖本地项目根目录
3. 再执行 `gcloud builds submit`

> 新容器启动时会打包进这份最新数据库，实现无缝数据继承。

### 重新登录说明

`TOKEN_STORE` 是内存字典，每次云端部署后会清空。浏览器 `localStorage` 中保存的旧 Token 会导致 403 错误。**每次部署后需重新登录控制台。**

---

## 🖥️ 管理控制台功能

| 选项卡 | 功能 |
|---|---|
| **Dashboard** | 呼入日志（10条，最新在顶）、并发线路状态、WebRTC 测试入口 |
| **Live Transcript** | 实时打字机效果对话记录，多路通话独立隔离显示 |
| **Live Receipt** | 实时订单小票（含草稿状态） |
| **Orders View** | 今日已处理订单列表，可查看完整订单详情 |
| **AI Brain** | 查看 Gemini 系统指令（只读） |
| **Menu GUI** | 可视化菜单编辑器 |
| **System Config** | 业务开关（AI 开/关/旁路）、折扣配置、数据库备份、日志下载 |

---

## 🛡️ 常见问题排查

**Q: AI 通话突然中断，日志显示 1008 错误？**  
A: Gemini Live API Preview 版本上游不稳定，尤其处理大量商品时会崩盘。等待 Google 发布正式版模型。

**Q: AI 算的钱对不上菜单？**  
A: 计价逻辑在 `tools_pricing.py`，与 Prompt 无关。修改价格/折扣/刷卡附加费请只改此文件。

**Q: 客户说了菜单上的菜名被当成外语转接？**  
A: STT 对带口音的单词（如 "Tagliatelle"）可能误转录为外语字符。系统已在 `prompts.py` 加入菜单上下文匹配例外规则，AI 会根据对话上下文推断最近的菜单选项而非直接拒绝。

**Q: 打字掩盖音不响？**  
A: `键盘.wav` 仅在 AI 发起 Function Call 时触发。普通网络延迟（无法预判时长）无法触发，属设计限制。

**Q: 控制台无法保存配置，报 403？**  
A: 检查 `.env` 中 `ADMIN_PASSWORD` 是否设置；Cloud Run 部署后需重新登录获取新 Token。

---

*后端全面使用中文注释，每个 `.py` 文件均包含详尽的执行链路说明，可直接阅读源码了解实现细节。*
