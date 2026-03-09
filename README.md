# 🍜 Gemini AI 智能电话点餐系统 (Noodle Box Drogheda)

本项目是一个基于 Google Gemini 2.5 Flash Native Audio 模型的全双工实时 AI 语音点餐服务器。它能够接听客户的 Twilio 电话，自动搜寻爱尔兰 Eircode 地址，计算含折扣和配送费的总价，并能根据并发量或客户诉求平滑转接给真正的人工店员。

---

## 📂 核心代码架构与设计模式

为了让后来的开发人员快速上手，本系统的代码做了极度结构化的拆分。所有的业务逻辑分离到了各自的 `tools_*.py` 工具包中，而主入口仅负责网络流的中转。

### 1. 核心后端 (Python)

*   **`server.py` (主网关 - 2900+行)**
    *   **职责**：FastAPI 主路由，处理 Twilio Webhook (`/incoming-call`)，以及 WebSocket 媒体流 (`/media-stream`)。
    *   **逻辑**：创建双向桥接任务。当 Twilio 发来 8kHz mu-law 音频时，它将其升频解码为 16kHz PCM 发给 Gemini；当 Gemini 生成 24kHz PCM 语音时，它将其降频压缩为 8kHz mu-law 发回给 Twilio。
    *   *注：此文件内含极度详尽的中文架构图和按行级别的逻辑块注释。*

*   **`boot.py` (Cloud Run 启动包装器)**
    *   **职责**：Cloud Run 正式部署时的启动入口（`CMD ["python", "boot.py"]`）。它在启动 uvicorn 服务前先 import server 并捕获任何致命错误，保证错误日志在容器退出前能完整传输到 Google Cloud Logging。本地开发可直接运行 `python server.py` 跳过此包装器。

*   **`audio_injector.py` (延迟掩盖引擎)**
    *   **职责**：负责解决 AI 思考时的“网络沉默期”带来的尴尬。它在内存中预加载 `键盘.wav` 文件，一旦检测到 AI 正在调用远程函数（如算钱、查地址），便立即通过非阻塞协程向底层 WebSocket 注入无缝的键盘打字音波。

*   **`config.py` (动态配置开关)**
    *   **职责**：全局参数集散地。采用 Pydantic+JSON 挂载模式，提供业务开关（折扣开关、AI 代接开关、最大并发数控制等），并支持内存级热重载，无需重启服务即可在前端面板中即时生效。

*   **`database.py` (SQLite 实体映射)**
    *   **职责**：ORM 数据库管控。它将顾客的地址历史（`Customer`）、历史订单记忆（`Order`）以及扁平化的多维树形菜单（`MenuItem`, `MenuOption`）进行封存和提取，给 AI 提供快速加载的 `lru_cache` 数据源。

*   **`prompts.py` (人格面具注射器)**
    *   **职责**：在每次接通电话的第一秒，负责合成数万字的 System Instruction 丢给 Gemini，其中包含了当天的日期、时间、是否是放假繁忙日、实时的折扣传销术语、以及完整菜单。

### 2. AI 智能工具箱 (`tools_*.py`)

AI 的“大脑”通过 Function Calling 协议主动调用这些本地 Python 脚本来进行物理世界的运算：

1.  **`tools_pricing.py`**：接收 AI 给出的购物车数组，比对 SQLite 验证单价，执行各种复杂的数学运算（尺寸加价、折扣百分比扣除、刷卡费附加、配送费叠加）。
2.  **`tools_address.py`**：连接爱尔兰国家地址库 `AutoAddress API`，接收客户报出的模糊地名或 Eircode，补全精准地址并校验是否在 Co. Louth / Meath 的配送范围内。
3.  **`tools_history.py`**：利用主叫号码（Caller ID），查询上一单的挂单数据，让 AI 能响应“老样子 (same as last time)”的模糊请求。
4.  **`tools_manage_call.py`**：包含 `end_call` (挂断并封存订单) 和 `transfer_call` (生成 `<Dial>` 拨号信令，将无理取闹的客户转接给人工)。

### 3. 可视化控制台 Frontend (React)

*   **`frontend/src/App.jsx` (单体巨无霸控制台)**
    *   **职责**：管理员使用的超大型 React Dashboard 仪表盘（1800+行代码）。
    *   **双层权限机制 (新)**：系统提供 Staff (防呆数据监控) 与 Admin (全量系统逻辑接管) 两种基于轻量级哈希 Token 的拦截模式，极大限度防止打工仔乱按造成系统宕机。
    *   **核心功能**：采用中英双语国际化切换，内嵌了：
        1. **Live Dashboard**：实时查看 WebSocket 建立状态、今日接单量饼图。
        2. **Orders View**：展示接单结果，分为“已解决”和“草稿/断线”栏目。
        3. **Config Editor**：通过 API 远程加密覆写后端的 `settings.json` 且支持在线热重载。
    *   *注：前端采用标准的 React Hooks + TailwindCSS 结构，组件以 Tabs 切换形式在内部定义。*

*   **`frontend/src/components/WebCallSimulator.jsx`**
    *   **职责**：让店长在不花 Twilio 话费的情况下，直接通过网页麦克风与本地测试版的 AI 进行语音交互。

---

## 🚀 启动指南 (如何跑起来？)

本地开发和测试本项目，需要开两个终端分别运行后端 Python 和前端 React，并且由于 Twilio 只向公网发送 Webhook，你还需要一个内网穿透工具。

### 步骤 1：环境配置文件 (.env)
在项目根目录下创建一个 `.env` 文件（或重命名现有的模板），并填入以下必须的安全通讯密钥：
```env
# 控制台登录密码（用于保护 React 的 Frontend）
ADMIN_PASSWORD=your_secure_password

# Twilio 通讯校验 Token (防止黑客假冒 Twilio 发起 Webhook)
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
```
> **防遗忘补丁**：如果在 UI 面板里修改了管理员密码后遗忘，请在服务器打开 `data/settings.json` 直接删除或修改 `"admin_password"` 节点，系统会实时热重载恢复您的最高管理权限。

### 步骤 2：启动内网穿透 (仅本地开发)
在物理机终端执行以下命令，将本地 `8080` 端口暴露给公网：
```bash
ngrok http 8080
```
> **重要操作**：拿到形如 `https://1234-abcd.ngrok-free.dev` 的链接后，需要去 Twilio 的控制台把自己购买的电话号码的 Webhook 指向 `https://你的ngrok网址/incoming-call`。

### 步骤 3：启动 Python 后端服务
打开第二个终端，进入项目根目录：
```bash
# （建议使用虚拟环境 source venv/bin/activate）
pip install -r requirements.txt

# 本地开发（直接运行，输出更简洁）
python server.py

# 或使用 Cloud Run 启动包装器（与生产环境等价，捕获启动致命错误）
python boot.py
```
> 服务将在 `localhost:8080` 端口运行（由 `PORT` 环境变量控制，默认 8080），看到 "Application startup complete" 即代表成功。

### 步骤 4：启动 React 管理面板
打开第三个终端，进入 `frontend` 目录：
```bash
cd frontend
npm install
npm run dev
```
> 在浏览器打开 `http://localhost:5173` (或命令行提示的地址)，即可进入强大的中控面板。

---

## ☁️ Google Cloud Run Serverless 云端部署指南

系统已经完美适配 Google Cloud Run 无服务器环境。

### 发布至云端的步骤
1. **编译前端**: 在 `frontend/` 目录下执行 `npm run build`，它会将 React 静态产物压入 `dist/` 文件夹供 Python 后端读取。
2. **构建镜像**: 在项目根目录下，执行 `gcloud builds submit --tag gcr.io/你的项目ID/gemini-live-api`。
   > **注意**：Dockerfile 使用 `python boot.py` 作为启动命令（`CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]`），它会在 uvicorn 启动前先验证所有模块可正常 import，保证 Cloud Logging 中能捕获启动崩溃日志。
3. **部署服务**: 执行以下命令推送镜像并关联环境变量。必须添加 `--max-instances 1` 以保证 WebSocket 的一致性和内存 SQLite 状态不丢失：
```bash
gcloud run deploy gemini-live-api \
  --image gcr.io/你的项目ID/gemini-live-api \
  --update-env-vars ADMIN_PASSWORD="your-password",TWILIO_AUTH_TOKEN="your-twilio-token" \
  --allow-unauthenticated \
  --max-instances 1 \
  --region europe-west1
```

### 🔐 极其重要：数据持久化与防丢失备份机制 (Data Backup)
因为 Cloud Run 的底层逻辑是每次修改重编镜像部署后都会**格式化销毁非 Volume 数据**。
所以我们在前端的 "**System Config**" 选项卡中增加了一个防丢档机制。

**在您每次打算对代码进行部署更新前，请严格执行以下闭环：**
1. 登录您现有的线上管理系统控制台。
2. 切到 `System Config` 选项卡，点击醒目的 **"Backup Database (app.db)"**。
3. 把下载好的历史数据库覆盖至您本地开发机的项目根绝路径下。
4. 现在可以执行部署了！新容器将打包读取这份最新数据，实现了数据的无缝继承。

---

## 🛡️ 后期维护者避坑指南 (Troubleshooting)

1.  **为啥 AI 通话中断线，且后台报 1008 错误？**
    *   这是谷歌 Gemini API (Preview) 版本上游的不稳定导致，尤其是当 AI 在脑内计算过多商品（或者尝试执行过长字符串拼接操作）时，模型崩盘了。解决在此代码范畴外，等谷歌发布正式版模型即可。
2.  **为啥 AI 算出来的钱和菜单对不上？**
    *   AI 只负责提取文字丢给 `calculate_total`。记账逻辑在 `tools_pricing.py`。修改价格逻辑、增删刷卡附加费等算法，请只修改 `tools_pricing.py`，绝对不要试图用 Prompt 教 AI 自己算钱（它数学极差）。
3.  **打字掩码音怎么不响？**
    *   打字音位于 `键盘.wav`，仅在发生明确系统函数调用（如算账阶段）时触发。如果是常规的 2-3 秒网络延迟（由于地理距离产生的物理延迟），系统无法预测这个空窗期多长，目前没有做环境噪音兜底。
4.  **前端页面无法保存配置？**
    *   检查后端的 `data/settings.json` 是否具有可写权限；检查 `.env` 文件是否存在并配置好了相关的 API_KEY。

祝您接手续写该系统顺利！有任何新需求可随时查阅每个具体的 `.py` 文件，里面拥有事无巨细的中文执行链路引导。 
