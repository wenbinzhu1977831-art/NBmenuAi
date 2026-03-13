"""
server.py — AI 智能电话点餐系统主服务

系统架构概览：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  外部来电                                                             │
    │    │                                                                 │
    │  Twilio (电话网络)                                                    │
    │    │ POST /incoming-call (TwiML 路由判断)                             │
    │    │                                                                 │
    │    ├─ master_switch=offline → 播放离线消息/拒接                        │
    │    ├─ master_switch=bypass  → 直接转人工                              │
    │    ├─ 并发超限               → 溢出处理（转接或拒绝）                   │
    │    └─ 正常                  → 建立 WebSocket 媒体流                   │
    │                                    │                                 │
    │                             WS /media-stream                         │
    │                             ┌──────┴──────────────────────┐          │
    │                             │  双向音频桥接核心             │          │
    │                             │                             │          │
    │  Twilio(mu-law 8k) ──解码──▶│ receive_from_twilio()       │          │
    │                   ──上采样──▶│  → PCM 16k → Gemini        │          │
    │                             │                             │          │
    │  Gemini(PCM 24k) ──下采样──▶│ receive_from_gemini()       │          │
    │                   ──编码───▶│  → mu-law 8k → Twilio      │          │
    │                             │  → 工具调用分发              │          │
    │                             └─────────────────────────────┘          │
    │                                                                       │
    │  管理面板 (前端 Vue/React)                                             │
    │    WS /api/admin/ws          ← 实时推送（字幕、通话状态、订单）         │
    │    HTTP /api/admin/*         ← 配置读写、菜单管理、代码编辑             │
    │    WS /api/admin/web_call    ← Web 模拟电话测试                       │
    └─────────────────────────────────────────────────────────────────────┘

关键技术点：
    1. 音频转码：Twilio 使用 mu-law 8kHz，Gemini 使用 PCM 16kHz/24kHz
    2. 双向并发：两个独立异步任务分别处理 Twilio→Gemini 和 Gemini→Twilio
    3. 工具调用：Gemini 通过 Function Calling 触发地址验证、价格计算、挂断/转接
    4. 打断处理：检测用户打断信号，但过滤掉 ≤1 个单词的噪音误触发
    5. 热重载：所有业务配置支持通过管理面板实时修改，无需重启服务

运行方式：
    python server.py
    (需先运行 ngrok http 5000 获取公网地址并配置到 Twilio Webhook)
"""

import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import json
import base64
import asyncio
import audioop       # 音频编解码（mu-law ↔ PCM 转换）
import logging
import re               # ctrl-char filter for outputTranscription
import uuid          # 生成唯一订单 ID
import time
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, Request, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import secrets
from fastapi.staticfiles import StaticFiles
from websockets.client import connect as ws_connect      # 连接 Gemini WebSocket 服务端
from websockets.exceptions import ConnectionClosed       # WebSocket 连接关闭异常
from fastapi.websockets import WebSocketDisconnect       # FastAPI WebSocket 断开异常
from pydantic import BaseModel
from typing import Dict, Any

# 解决 Windows 终端中 ANSI 颜色转义码无法正确显示的问题
# 调用后，print("\033[93m黄色\033[0m") 等彩色输出才能在 PowerShell/CMD 中正常显示
import colorama
colorama.init()

# 业务逻辑模块
import database         # 数据持久化（菜单、客户、订单）
import tools_address    # AI 工具：爱尔兰地址搜索验证
import tools_pricing    # AI 工具：订单价格计算
import tools_manage_call  # AI 工具：通话控制（挂断/转接）
import tools_history    # AI 工具：历史订单查询
# 导入键盘打字音效注入工具
import audio_injector
import prompts          # AI 系统指令生成器

# 从配置管理模块导入全局唯一配置实例
from config import config

# =============================================================================
# 日志配置
# 格式：时间戳 - 日志级别 - 消息
# 示例：2025-12-27 16:34:45,123 - INFO - 来电号码: +353871234567
# =============================================================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AI-Waiter")


# =============================================================================
# 业务日期计算辅助函数
# =============================================================================

def get_business_date_str(timestamp_seconds=None):
    """
    计算"逻辑业务日期"的字符串表示（如 'Sat Dec 27'）。

    问题背景：
        餐厅通常营业到凌晨（如 23:00~01:00）。
        如果以自然日计算，凌晨 1:00 的订单属于第二天，
        但在业务上它应该算作前一天（同一个"营业日"）的订单。

    解决方案：
        将时间戳向前偏移 business_day_start_hour 小时（默认 5 小时）：
        - 凌晨 1:00 减去 5 小时 = 前一天 20:00 → 计入前一天
        - 早上 6:00 减去 5 小时 = 当天 1:00   → 计入当天

    Args:
        timestamp_seconds (float, optional): Unix 时间戳（秒）；
                                             为 None 时使用当前时间

    Returns:
        str: 格式化的业务日期字符串，如 "Sat Dec 27"
             用于与订单 timestamp 字段的日期部分进行比较

    注意：
        business_day_start_hour 从 config 中读取（使用 getattr 提供默认值 5），
        将来可通过在 AppConfig 中添加此字段使其可配置。
    """
    dt = datetime.fromtimestamp(timestamp_seconds) if timestamp_seconds else datetime.now()
    # 向前偏移 start_hour 小时，实现"业务日"的时间边界
    start_hour = int(getattr(config, 'business_day_start_hour', 7))
    logical_dt = dt - timedelta(hours=start_hour)
    return logical_dt.strftime("%a %b %d")


# =============================================================================
# FastAPI 应用实例
# =============================================================================
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务启动前执行：加载并预转码打字音效
    logger.info("系统启动：预加载音频资产...")
    import audio_injector
    audio_injector.load_typing_audio("键盘.wav")
    yield
    # 服务关闭时清理 (预留)
    logger.info("系统关闭。")

app = FastAPI(lifespan=lifespan)



def get_order_counts():
    """
    统计今日订单数 (SQLite)：返回 (completed_count, incomplete_count)
    """
    completed, incomplete = 0, 0
    try:
        from database import get_db_session
        from models import Order
        today_str = get_business_date_str()
        
        with get_db_session() as db:
            orders = db.query(Order).filter_by(business_date=today_str).all()
            for o in orders:
                if o.source and "Incomplete" in o.source:
                    incomplete += 1
                elif o.source and o.source.startswith("AI"):
                    completed += 1
    except Exception as e:
        logger.error(f"get_order_counts 失败: {e}")
    return completed, incomplete

# 跨域资源共享（CORS）配置
# 允许前端在开发阶段（不同端口）或其他域名访问此 API
# 生产环境建议将 allow_origins 限制为具体的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 允许所有来源（开发阶段）
    allow_credentials=True,
    allow_methods=["*"],       # 允许所有 HTTP 方法
    allow_headers=["*"],       # 允许所有请求头
)

# 前端静态文件服务（生产环境/Docker 部署）
# 如果 frontend/dist 目录存在（由 npm run build 生成），
# 则将其 assets 子目录作为静态文件服务挂载到 /assets 路径
# 同时 /index.html 由 serve_frontend() 路由处理
frontend_dist_path = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dist_path):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(frontend_dist_path, "assets")),
        name="assets"
    )


# =============================================================================
# 全局状态字典
# =============================================================================

# 通话意图状态字典：记录每个 CallSid 的挂断/转接意图
# 键：CallSid（Twilio 通话唯一标识）
# 值：{"intent": "hangup"/"transfer", "reason": "..."}
# 生命周期：从 AI 调用 end_call/transfer_call 工具时写入，
#           在 /stream-ended 路由读取并清除
CALL_STATES = {}

# 活跃通话字典：跟踪当前正在进行的通话
# 键：CallSid
# 值：{"start_time": float, "caller_number": str, "caller_name": str}
# 用途：
#   1. 并发控制（与 config.max_concurrent_calls 比较）
#   2. 管理面板实时展示当前通话数量和详情
ACTIVE_CALLS = {}

# =============================================================================
# 并发通话管理
# =============================================================================

# 呼入日志：记录每通电话的完整信息（最多保留 200 条）
call_log: list = []
CALL_LOG_MAX = 200

# 数据库写操作锁：防止并发写入 JSON 文件造成数据损坏
_db_write_lock = asyncio.Lock()


def call_log_add(call_sid: str, number: str, source: str) -> dict:
    """新增一条呼入记录，返回该记录。"""
    record = {
        "call_sid":        call_sid,
        "number":          number,
        "source":          source,
        "joined_at":       time.time(),
        "ended_at":        None,
        "status":          "active",
        "order_finalized": None,
        "transferred":     False,
    }
    call_log.append(record)
    if len(call_log) > CALL_LOG_MAX:
        call_log.pop(0)
    return record


def call_log_end(call_sid: str, order_finalized=None,
                 transferred: bool = False, missed: bool = False):
    """标记通话结束，更新 call_log 中的对应记录。"""
    for r in reversed(call_log):
        if r["call_sid"] == call_sid:
            r["ended_at"]        = time.time()
            r["status"]          = "missed" if missed else "completed"
            r["order_finalized"] = order_finalized
            r["transferred"]     = transferred
            break


def safe_call_log() -> list:
    """返回 call_log 的 JSON 安全副本。"""
    return [
        {
            "call_sid":        r["call_sid"],
            "number":          r["number"],
            "source":          r["source"],
            "joined_at":       r["joined_at"],
            "ended_at":        r["ended_at"],
            "status":          r["status"],
            "order_finalized": r["order_finalized"],
            "transferred":     r["transferred"],
        }
        for r in reversed(call_log)  # 最新通话排在最前面
    ]


# =============================================================================
# 管理面板 WebSocket 广播机制
# =============================================================================

# 所有已连接的管理面板 WebSocket 客户端集合
# 使用 set 存储，自动去重，方便批量广播
ADMIN_CLIENTS = set()


async def broadcast_admin(event: str, data: dict):
    """
    向所有已连接的管理面板前端推送实时事件消息。

    消息格式（JSON）：
        {"event": "<事件名>", "data": {...}}

    支持的事件类型：
        "sync"         — 初次连接时同步当前通话状态
        "call_start"   — 新通话开始（含来电号码、姓名、当前并发数）
        "call_end"     — 通话结束（含当前并发数）
        "transcript"   — 实时字幕流（用户/AI 的文字）
        "tool_call"    — AI 调用工具时（供调试）
        "tool_response"— 工具返回结果时（供调试）
        "new_order"    — 新订单归档后（含今日 AI 订单总数）
        "system_log"   — 系统日志消息（连接/断开等状态）

    容错机制：
        遍历过程中若某个客户端已断开，发送会抛出异常，
        将其加入 disconnected 集合，遍历结束后统一清除，
        避免在遍历过程中修改集合（会导致 RuntimeError）。

    Args:
        event (str): 事件名称字符串
        data (dict): 事件携带的数据字典
    """
    message = json.dumps({"event": event, "data": data})
    disconnected = set()  # 收集发送失败的断开客户端

    for ws in ADMIN_CLIENTS:
        try:
            await ws.send_text(message)
        except Exception:
            # 发送失败说明客户端已断开，标记待清除
            disconnected.add(ws)

    # 清除已断开的客户端
    for ws in disconnected:
        ADMIN_CLIENTS.remove(ws)


# =============================================================================

# 双层权限认证系统 (Admin vs Staff)
# =============================================================================

# 统一 Token 存储池 (内存字典)
# 结构: { "token_string": {"role": "admin"|"staff", "expires": timestamp} }
TOKEN_STORE = {}

class LoginRequest(BaseModel):
    password: str = None
    role: str = None

@app.post("/api/admin/login")
async def admin_login(req: LoginRequest):
    """
    处理登录请求并下发轻量级 Token。
    双通路设计：
        1. req.role == 'staff': 颁发普通店员凭证 (只能看看板，不能修改)
        2. req.password == CONFIG_PWD: 颁发最高管理员凭证
    """
    # 1. 员工无密码直接发 token
    if req.role == "staff":
        token = secrets.token_hex(16)
        TOKEN_STORE[token] = {"role": "staff", "expires": time.time() + 86400 * 7}
        return {"token": token, "role": "staff"}
    
    # 2. 管理员需密码校验
    if req.password == config.admin_password:
        token = secrets.token_hex(16)
        TOKEN_STORE[token] = {"role": "admin", "expires": time.time() + 86400 * 7}
        return {"token": token, "role": "admin"}
    
    raise HTTPException(status_code=401, detail="Invalid password")

class PasswordChangeRequest(BaseModel):
    new_password: str

async def verify_token(authorization: str = None):
    """基础凭证拦截器：提取 Authorization Header 中的 Bearer Token 并校验"""
    # 注意：为了让拦截器纯粹，这里手工从 header 或 Depends 抓取
    pass # 被 OAuth2 替代

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/admin/login", auto_error=False)

async def get_current_role(token: str = Depends(oauth2_scheme)):
    """验证 Token 是否有效并返回角色 (admin/staff)"""
    if not token or token not in TOKEN_STORE:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    
    info = TOKEN_STORE[token]
    if time.time() > info["expires"]:
        del TOKEN_STORE[token]
        raise HTTPException(status_code=401, detail="Token expired")
    
    return info["role"]

async def verify_admin(role: str = Depends(get_current_role)):
    """高级凭证拦截器：阻断 staff，仅允许 admin 放行"""
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required for this action")
    return role

@app.post("/api/admin/change-password")
async def change_password(req: PasswordChangeRequest, role: str = Depends(verify_admin)):
    """管理员在线重置系统密码。重置后销毁所有旧 Token 迫使所有人重新登录"""
    try:
        settings_data = {}
        if os.path.exists(config.settings_file):
            with open(config.settings_file, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
        
        if "security_settings" not in settings_data:
            settings_data["security_settings"] = {}
        settings_data["security_settings"]["admin_password"] = req.new_password
        
        with open(config.settings_file, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=2, ensure_ascii=False)
            
        # 让 Config 单例热重载新密码
        config.reload_settings()
        
        # 踢下线所有人
        TOKEN_STORE.clear()
        
        return {"status": "success", "message": "Password updated successfully."}
    except Exception as e:
        logger.error(f"Failed to change password: {e}")
        raise HTTPException(status_code=500, detail="Failed to write password setting")


# =============================================================================
# 管理面板 API 路由
# 均受 Token 保护。基础查看受 get_current_role 保护，写配置受 verify_admin 保护。
# =============================================================================

@app.post("/api/admin/reset-busy")
async def reset_busy(role: str = Depends(verify_admin)):
    """
    查询并重置 AI 并发状态。
    当通话意外断开导致 ACTIVE_CALLS 未能正确清除时，
    管理员可通过此端点广播当前真实状态，无需重启服务器。
    """
    await broadcast_admin("ai_status", {"busy": len(ACTIVE_CALLS) >= config.max_concurrent_calls})
    logger.warning("⚠️ 管理员查询并发状态，当前 ACTIVE_CALLS: %d", len(ACTIVE_CALLS))
    return {"status": "ok", "message": f"Active calls: {len(ACTIVE_CALLS)}, max: {config.max_concurrent_calls}"}

@app.websocket("/api/admin/ws")
async def admin_websocket(websocket: WebSocket, token: str = None):
    """
    管理面板实时通信 WebSocket 端点 (Token Query 鉴权)。
    """
    if not token or token not in TOKEN_STORE:
        await websocket.close(code=1008)
        return
    
    if time.time() > TOKEN_STORE[token]["expires"]:
        del TOKEN_STORE[token]
        await websocket.close(code=1008)
        return

    await websocket.accept()
    ADMIN_CLIENTS.add(websocket)

    # --- 发送初始同步数据：当前活跃通话状态 ---
    await websocket.send_text(json.dumps({
        "event": "sync",
        "data": {
            "active_calls_count": len(ACTIVE_CALLS),
            "active_calls": ACTIVE_CALLS  # 完整字典，含每个通话的详细信息
        }
    }))

    # --- 发送今日 AI 订单计数（初始同步，含草稿数）---
    completed, incomplete = get_order_counts()
    await websocket.send_json({
        "event": "new_order",
        "data": {
            "total_orders": completed,
            "incomplete_orders": incomplete,
            "order_id": None
        }
    })

    # --- 保持连接：等待前端发送任何消息（心跳）---
    try:
        while True:
            await websocket.receive_text()  # 阻塞等待，收到任何消息都忽略
    except WebSocketDisconnect:
        # 前端正常关闭页面或刷新时触发
        ADMIN_CLIENTS.discard(websocket)
    except Exception as e:
        logger.error(f"Admin WS 异常: {e}")
        ADMIN_CLIENTS.discard(websocket)


# --- 配置管理 API ---

@app.get("/api/admin/settings")
async def get_settings(role: str = Depends(get_current_role)):
    """
    获取当前配置。
    生产环境（Cloud SQL）：从 app_settings 表读取 settings_json key。
    本地开发：从 settings.json 文件读取（向下兼容）。
    """
    data = {}
    if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
        # 生产环境：从 Cloud SQL 读取
        raw = database.get_app_setting("settings_json")
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
    elif os.path.exists(config.settings_file):
        # 本地开发：从文件读取
        with open(config.settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    if role == "staff":
        data.pop("api_keys", None)
        data.pop("security_settings", None)
    return data


class SettingsUpdate(BaseModel):
    """POST /api/admin/settings 的请求体模型"""
    settings: Dict[str, Any]  # 完整的配置字典（嵌套结构，与 settings.json 格式一致）


@app.post("/api/admin/settings")
async def update_settings(update_data: SettingsUpdate, role: str = Depends(verify_admin)):
    """
    保存新的配置并立即热重载到内存。
    生产环境：写入 Cloud SQL app_settings 表。
    本地开发：写入 settings.json 文件。
    """
    try:
        json_str = json.dumps(update_data.settings, indent=2, ensure_ascii=False)
        if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
            # 生产环境：存入 Cloud SQL
            database.save_app_setting("settings_json", json_str)
        else:
            # 本地开发：写入文件
            with open(config.settings_file, "w", encoding="utf-8") as f:
                f.write(json_str)
        # 立即热重载，使新配置在下次 API 调用时生效
        config.reload_settings()
        return {"status": "success", "message": "Settings saved to Cloud SQL and reloaded"}
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- 数据备份 API ---

@app.get("/api/admin/backup/db")
async def download_database(token: str = None):
    """下载数据库备份。本地 SQLite 环境返回 app.db 文件；Cloud SQL 生产环境提示使用 GCP 控制台。"""
    if not token or token not in TOKEN_STORE or TOKEN_STORE[token]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin token required via query parameter")

    # Cloud SQL 生产环境：app.db 不存在，引导用户使用 GCP 控制台备份
    if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
        raise HTTPException(
            status_code=503,
            detail="生产环境使用 Cloud SQL，请在 GCP 控制台 → Cloud SQL → 导出 功能进行数据库备份。"
        )

    # 本地开发环境：直接下载 app.db
    db_path = "app.db"
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file not found.")
    return FileResponse(
        path=db_path,
        filename=f"app_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
        media_type="application/octet-stream"
    )

@app.get("/api/admin/backup/log")
async def download_server_log(token: str = None):
    """下载服务器运行日志 (server.log)，URL 参数鉴权"""
    if not token or token not in TOKEN_STORE or TOKEN_STORE[token]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin token required via query parameter")
        
    log_path = "server.log"
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Server log not found.")
    return FileResponse(
        path=log_path, 
        filename=f"server_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", 
        media_type="text/plain"
    )

# --- 菜单管理 API ---

@app.get("/api/admin/menu")
async def get_menu(role: str = Depends(verify_admin)):
    """
    读取菜单数据。
    丰山云生产环境和本地开发均从 Cloud SQL / SQLite 数据库读取。
    返回与原来 menu.json 格式完全异法 的 JSON 字符串。
    """
    menu_dict = database.load_menu()
    return {"content": json.dumps(menu_dict, indent=4, ensure_ascii=False)}


class MenuUpdate(BaseModel):
    """POST /api/admin/menu 的请求体模型"""
    content: str  # 菜单 JSON 字符串（前端编辑器的完整内容）


@app.post("/api/admin/menu")
async def save_menu(payload: MenuUpdate, role: str = Depends(verify_admin)):
    """
    将前端提交的菜单 JSON 写入 Cloud SQL（生产）或 SQLite（本地）。
    
    格式要求：{"Category": [{"name": ..., "price": ..., ...}]}
    """
    try:
        json_data = json.loads(payload.content)
        if not isinstance(json_data, dict):
            raise HTTPException(status_code=400, detail="Menu must be a JSON object (dict of categories)")

        with database.get_db_session() as db:
            from models import MenuCategory, MenuItem, MenuOption

            # 删除所有现有菜单数据（重建）
            db.query(MenuOption).delete()
            db.query(MenuItem).delete()
            db.query(MenuCategory).delete()

            for display_order, (category_name, items) in enumerate(json_data.items()):
                category = MenuCategory(
                    name=category_name,
                    display_order=display_order
                )
                db.add(category)

                if isinstance(items, list):
                    for item_data in items:
                        item = MenuItem(
                            category_name=category_name,
                            name=item_data.get('name', 'Unnamed Item'),
                            price=float(item_data.get('price', 0.0)),
                            description=item_data.get('description'),
                            allergens=item_data.get('allergens'),
                        )
                        db.add(item)
                        db.flush()  # 获取 item.id

                        # 处理 Options
                        for option_group in (item_data.get('options') or []):
                            group_name = option_group.get('name', 'OPTIONS')
                            for val in (option_group.get('values') or []):
                                opt = MenuOption(
                                    item_id=item.id,
                                    name=f"{group_name}: {val['name']}",
                                    price_change=float(val.get('price_mod', 0.0)),
                                    is_default=bool(val.get('default', False)),
                                )
                                db.add(opt)

            db.commit()

        # 清除菜单缓存，使新菜单立即生效
        database.load_menu.cache_clear()
        database.load_menu()

        return {"status": "success", "message": f"菜单已保存到数据库 ({len(json_data)} 个分类)"}

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    except Exception as e:
        logger.error(f"菜单保存失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/menu/factory-reset")
async def factory_reset_menu(role: str = Depends(verify_admin)):
    """
    从 Docker 镜像内置的 menu_factory.json（或 menu.json）恢复出厂默认菜单，
    并将其写入 Cloud SQL 数据库。
    """
    # 优先找 menu_factory.json，否则用 menu.json（镜像里的原版）
    factory_file = "menu_factory.json" if os.path.exists("menu_factory.json") else "menu.json"
    if not os.path.exists(factory_file):
        raise HTTPException(status_code=404, detail="Factory default menu file not found in image.")

    try:
        with open(factory_file, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        with database.get_db_session() as db:
            from models import MenuCategory, MenuItem, MenuOption
            db.query(MenuOption).delete()
            db.query(MenuItem).delete()
            db.query(MenuCategory).delete()

            for display_order, (category_name, items) in enumerate(json_data.items()):
                db.add(MenuCategory(name=category_name, display_order=display_order))
                if isinstance(items, list):
                    for item_data in items:
                        item = MenuItem(
                            category_name=category_name,
                            name=item_data.get('name', 'Unnamed Item'),
                            price=float(item_data.get('price', 0.0)),
                            description=item_data.get('description'),
                            allergens=item_data.get('allergens'),
                        )
                        db.add(item)
                        db.flush()
                        for option_group in (item_data.get('options') or []):
                            group_name = option_group.get('name', 'OPTIONS')
                            for val in (option_group.get('values') or []):
                                db.add(MenuOption(
                                    item_id=item.id,
                                    name=f"{group_name}: {val['name']}",
                                    price_change=float(val.get('price_mod', 0.0)),
                                    is_default=bool(val.get('default', False)),
                                ))
            db.commit()

        database.load_menu.cache_clear()
        database.load_menu()

        return {"status": "success", "content": json.dumps(json_data, indent=4, ensure_ascii=False)}

    except Exception as e:
        logger.error(f"Factory Reset 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# --- 配送区域管理 API ---

@app.get("/api/admin/delivery_areas")
async def get_delivery_areas():
    """
    读取配送区域文本内容。
    生产环境：从 Cloud SQL app_settings 表读取。
    本地开发：从 delivery_areas.txt 文件读取。
    """
    if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
        content = database.get_app_setting("delivery_areas") or ""
        return {"content": content}
    if os.path.exists(config.delivery_areas_file):
        with open(config.delivery_areas_file, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": ""}


@app.post("/api/admin/delivery_areas")
async def save_delivery_areas(payload: dict):
    """
    保存配送区域文本并清除内存缓存。
    生产环境：写入 Cloud SQL app_settings 表。
    本地开发：写入 delivery_areas.txt 文件。
    """
    try:
        content = payload.get("content", "")
        if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
            database.save_app_setting("delivery_areas", content)
        else:
            with open(config.delivery_areas_file, "w", encoding="utf-8") as f:
                f.write(content)
        # 清除配送区域缓存，确保新数据立即生效
        database.load_delivery_areas.cache_clear()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 代码文件管理 API ---
# 允许通过管理面板在线查看和编辑关键 Python 文件

# 白名单：只允许访问这些文件，防止任意文件读取安全漏洞
ALLOWED_CODE_FILES = [
    "prompts.py", "tools_address.py", "tools_history.py",
    "tools_manage_call.py", "tools_pricing.py", "server.py",
    "config.py", "database.py"
]


@app.get("/api/admin/code")
async def get_code(file: str):
    """
    读取指定 Python 文件的内容，供前端代码编辑器使用。

    安全控制：只允许访问 ALLOWED_CODE_FILES 白名单中的文件。

    Args:
        file (str): 文件名（Query 参数，如 ?file=prompts.py）

    Returns:
        dict: {"content": "<文件内容字符串>"}

    Raises:
        403: 文件不在白名单中
        404: 文件不存在
    """
    if file not in ALLOWED_CODE_FILES:
        raise HTTPException(status_code=403, detail="File access not allowed")

    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    raise HTTPException(status_code=404, detail="File not found")


class CodeUpdate(BaseModel):
    """POST /api/admin/code 的请求体模型"""
    content: str  # 修改后的文件内容
    file: str     # 目标文件名


@app.post("/api/admin/code")
async def save_code(payload: CodeUpdate, role: str = Depends(verify_admin)):
    """
    保存修改后的 Python 文件（含自动备份）。

    注意：
        保存代码文件后通常需要重启服务才能使更改生效（Python 不支持热重载模块）。
        唯一例外是 prompts.py，因为每次通话都会调用 get_system_instruction()，
        所以提示词修改立即生效。

    操作流程：
        1. 验证文件在白名单中
        2. 备份原文件到 backups/ 目录
        3. 写入新内容

    Returns:
        dict: {"status": "success", "message": "..."}

    Raises:
        403: 文件不在白名单中
        500: 文件操作失败
    """
    if payload.file not in ALLOWED_CODE_FILES:
        raise HTTPException(status_code=403, detail="File modification not allowed")

    try:
        backup_path = None
        # 备份原文件
        if os.path.exists(payload.file):
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"{payload.file}.{timestamp}.bak")
            import shutil
            shutil.copy2(payload.file, backup_path)

        # 写入新内容
        with open(payload.file, "w", encoding="utf-8") as f:
            f.write(payload.content)

        msg = f"Saved and backed up to {backup_path}" if backup_path else "Saved"
        return {"status": "success", "message": msg}

    except Exception as e:
        logger.error(f"保存代码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/backups")
async def list_backups(file: str, role: str = Depends(verify_admin)):
    """
    列出指定文件的所有历史备份（按时间倒序）。

    Args:
        file (str): 原始文件名（如 "prompts.py"）

    Returns:
        list: 备份信息列表，每项包含：
              {"filename": str, "timestamp": str, "path": str}
              若无备份则返回空列表
    """
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        return []

    backups = []
    for f in os.listdir(backup_dir):
        if f.startswith(f"{file}."):
            parts = f.split('.')
            if len(parts) >= 3:
                ts_str = parts[-2]  # 时间戳部分（格式：YYYYMMDD_HHMMSS）
                backups.append({
                    "filename": f,
                    "timestamp": ts_str,
                    "path": os.path.join(backup_dir, f)
                })

    # 按时间戳字符串倒序排列（最新的备份排在最前面）
    backups.sort(key=lambda x: x["timestamp"], reverse=True)
    return backups


class RestoreUpdate(BaseModel):
    """POST /api/admin/restore 的请求体模型"""
    backup_filename: str  # 备份文件名（如 "prompts.py.20251227_163445.bak"）
    target_file: str      # 恢复到的目标文件名（如 "prompts.py"）


@app.post("/api/admin/restore")
async def restore_backup(payload: RestoreUpdate, role: str = Depends(verify_admin)):
    """
    从指定备份文件恢复代码，覆盖当前版本。

    注意：
        恢复操作不会再次备份当前版本，请谨慎使用。
        建议恢复前先通过 GET /api/admin/code 保存当前内容。

    Returns:
        dict: {"status": "success"}

    Raises:
        404: 备份文件不存在
        500: 文件操作失败
    """
    backup_path = os.path.join("backups", payload.backup_filename)
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup not found")

    try:
        import shutil
        shutil.copy2(backup_path, payload.target_file)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/stats")
async def get_dashboard_stats(role: str = Depends(get_current_role)):
    """
    提供管理面板（Dashboard）统计图表所需的数据。
    包含：
        1. 营业额趋势 (最近7个营业日)
        2. 订单数量趋势 (最近7个营业日)
        3. 热销菜品 Top 5 (按销量)
        4. 总体统计 (总订单，总营业额，总客户)
    """
    try:
        from database import get_db_session
        from models import Order, Customer
        from sqlalchemy import func
        
        with get_db_session() as db:
            # 1. 总体统计
            total_orders = db.query(Order).filter(~Order.source.like('%Incomplete%')).count()
            total_revenue = db.query(func.sum(Order.total_value)).filter(~Order.source.like('%Incomplete%')).scalar() or 0.0
            total_customers = db.query(Customer).count()
            
            # --- 构建最近 7 个业务日期的标签列表 ---
            # 简化实现，这里通过取数据库中最后有的独特的 7 个日期来实现，或者根据当前时间往前推 7 天
            recent_dates = [get_business_date_str((datetime.now() - timedelta(days=i)).timestamp()) for i in range(6, -1, -1)]
            
            # 2. & 3. 营业额和订单趋势
            # 查询匹配这 7 天的记录
            orders_in_range = db.query(Order).filter(
                Order.business_date.in_(recent_dates),
                ~Order.source.like('%Incomplete%')
            ).all()

            revenue_by_date = {d: 0.0 for d in recent_dates}
            orders_by_date = {d: 0 for d in recent_dates}
            
            # 4. 热销菜品
            item_sales = {}
            
            for o in orders_in_range:
                d = o.business_date
                if d in revenue_by_date:
                    revenue_by_date[d] += float(o.total_value)
                    orders_by_date[d] += 1
                
                # 统计 item 销量
                if isinstance(o.items, list):
                    for item in o.items:
                        name = item.get("name")
                        if name:
                            item_sales[name] = item_sales.get(name, 0) + 1
            
            # Formatting arrays for recharts UI
            trend_data = []
            for date_str in recent_dates:
                 trend_data.append({
                     "date": date_str,
                     "revenue": round(revenue_by_date[date_str], 2),
                     "orders": orders_by_date[date_str]
                 })
            
            top_items = sorted([{"name": k, "value": v} for k, v in item_sales.items()], key=lambda x: x["value"], reverse=True)[:5]
            
            return {
                "summary": {
                    "total_orders": total_orders,
                    "total_revenue": round(total_revenue, 2),
                    "total_customers": total_customers
                },
                "trend": trend_data,
                "top_items": top_items
            }

    except Exception as e:
        logger.error(f"获取统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 执行启动后业务逻辑 =====
# 触发数据库懒初始化（首次访问时自动连接 SQLite 或 Cloud SQL）
try:
    database._get_session_factory()  # 触发初始化
    logger.info("✅ 数据库系统就绪")
except Exception as _db_init_err:
    logger.warning(f"⚠️ 数据库初始化失败，系统可能无法正常工作: {_db_init_err}")
    
try:
    # 在此处预加载打字音效掩盖延迟
    audio_injector.load_typing_audio("键盘.wav")
except Exception as e:
    logger.error(f"打字音效加载失败，延迟掩盖将不可用: {e}")


# =============================================================================
# 订单列表获取 API
# =============================================================================
@app.get("/api/admin/orders")
async def get_orders_list(all: str = "false", role: str = Depends(get_current_role)):
    """
    获取管理面板查看的历史与今日订单列表，包括草稿单和已完成订单。
    规则：把 Source 包含 'Incomplete' 字段的订单永远置顶，并且按倒序时间排列。
    若 `all=true`，则直接按倒序返回所有历史订单。
    """
    try:
        from database import get_db_session, load_menu
        from models import Order
        import json
        
        with get_db_session() as db:
            # Query all orders
            all_orders = db.query(Order).order_by(Order.created_at.desc()).all()
            
            menu_data = load_menu()
            price_map = {}
            option_price_map = {}
            for cat, c_items in menu_data.items():
                if isinstance(c_items, list):
                    for mi in c_items:
                        price_map[mi['name'].strip().lower()] = float(mi.get('price', 0.0))
                        if mi.get('options'):
                            for opt in mi['options']:
                                for val in opt.get('values', []):
                                    option_price_map[val['name'].strip().lower()] = float(val.get('price_mod', 0.0))
            
            # format the query into dictionaries
            formatted_orders = []
            for o in all_orders:
                items_list = o.items or []
                if isinstance(items_list, str):
                    try: items_list = json.loads(items_list)
                    except: items_list = []
                
                enriched_items = []
                for it in items_list:
                    if not isinstance(it, dict):
                        enriched_items.append(it)
                        continue
                    
                    item_name_lower = str(it.get('name', '')).strip().lower()
                    
                    # 1. 查找对应的菜品 db_item (优先完全相等，其次模糊)
                    db_item = None
                    for cat, c_items in menu_data.items():
                        if isinstance(c_items, list):
                            for mi in c_items:
                                if mi['name'].strip().lower() == item_name_lower:
                                    db_item = mi
                                    break
                            if db_item: break
                    
                    if not db_item:
                        for cat, c_items in menu_data.items():
                            if isinstance(c_items, list):
                                for mi in c_items:
                                    if item_name_lower in mi['name'].strip().lower() or mi['name'].strip().lower() in item_name_lower:
                                        db_item = mi
                                        break
                                if db_item: break

                    base_p = float(db_item.get('price', 0.0)) if db_item else 0.0
                    
                    # 2. 从 db_item['options'] 中精准查找用户的选项
                    opts = it.get('options', [])
                    modified_opts = []
                    
                    for opt_v in opts:
                        opt_name = opt_v if isinstance(opt_v, str) else str(opt_v.get('name', ''))
                        opt_name_lower = opt_name.strip().lower()
                        mod = 0.0
                        found_mod = False

                        if db_item and 'options' in db_item:
                            # 第一步：尝试精确匹配 (Exact Match)
                            for menu_opt_cat in db_item['options']:
                                for val in menu_opt_cat['values']:
                                    if opt_name_lower == val['name'].strip().lower():
                                        mod = float(val.get('price_mod', 0.0))
                                        found_mod = True
                                        break
                                if found_mod: break
                            
                            # 第二步：如果精确匹配失败，尝试模糊匹配 (Substring)
                            if not found_mod:
                                for menu_opt_cat in db_item['options']:
                                    for val in menu_opt_cat['values']:
                                        if opt_name_lower in val['name'].strip().lower():
                                            mod = float(val.get('price_mod', 0.0))
                                            found_mod = True
                                            break
                                    if found_mod: break
                        
                        base_p += mod
                        if isinstance(opt_v, dict):
                            if 'price_adjustment' not in opt_v:
                                opt_v['price_adjustment'] = mod
                            modified_opts.append(opt_v)
                        else:
                            modified_opts.append({"name": opt_name, "price_adjustment": mod})
                            
                    it['unit_price'] = base_p
                    it['options'] = modified_opts
                    enriched_items.append(it)

                order_dict = {
                    "id": o.id,
                    "business_date": o.business_date,
                    "created_at": o.created_at.isoformat(),
                    "customer_phone": o.customer_phone,
                    "customer_name": o.customer.name if o.customer else "Unknown",
                    "address": o.customer.address if o.customer else "Unknown",
                    "source": o.source,
                    "service_type": o.service_type,
                    "delivery_area": o.delivery_area,
                    "delivery_fee": float(o.delivery_fee) if o.delivery_fee else 0.0,
                    "payment_method": o.payment_method,
                    "total_value": float(o.total_value) if o.total_value else 0.0,
                    "notes": o.notes,
                    "items": enriched_items,
                    "transcript": o.transcript
                }
                formatted_orders.append(order_dict)

            if all.lower() == "true":
                return {"status": "success", "orders": formatted_orders}

            incomplete_orders = []
            completed_orders = []
            today_str = get_business_date_str()
            
            for o in formatted_orders:
                if "Incomplete" in o["source"]:
                    incomplete_orders.append(o)
                elif o["business_date"] == today_str:
                    completed_orders.append(o)
            
            # Combine them: Incomplete always go first.
            result = incomplete_orders + completed_orders
            
            return {"status": "success", "orders": result}

    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# 客户列表获取 API
# =============================================================================
@app.get("/api/admin/customers")
async def get_customers_list():
    """
    获取所有客户的信息列表
    """
    try:
        from database import get_db_session
        from models import Customer
        
        with get_db_session() as db:
            customers = db.query(Customer).order_by(Customer.id.desc()).all()
            
            result = []
            for c in customers:
                result.append({
                    "id": c.id,
                    "phone_number": c.phone_number,
                    "name": c.name or "Unknown",
                    "address": c.address or "Unknown",
                    "last_order_id": c.last_order_id or "None"
                })
            
            return {"status": "success", "customers": result}

    except Exception as e:
        logger.error(f"获取客户列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/orders/{order_id}")
async def delete_order(order_id: str):
    """
    删除指定的订单 (历史或草稿)
    """
    try:
        from database import get_db_session
        from models import Order
        
        with get_db_session() as db:
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            
            db.delete(order)
            db.commit()
            return {"status": "success", "message": f"Order {order_id} gracefully deleted."}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除订单失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/logs")
async def clear_logs():
    """
    清空后台日志文件.
    """
    try:
        # 打开 server.log 并清空内容
        with open("server.log", "w", encoding="utf-8") as f:
            f.truncate(0)
        return {"status": "success", "message": "Server logs have been cleared."}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# 管理端 API：电话排队区手动转接 (Emergency Transfer)
# =============================================================================


# =============================================================================
# 核心业务路由：Twilio 电话接入
# =============================================================================

@app.post("/incoming-call")
async def incoming_call(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio 电话呼入入口（Webhook）。

    当有新电话拨入 Twilio 号码时，Twilio 会向此端点发送 HTTP POST 请求，
    本函数返回 TwiML（Twilio Markup Language）XML 指令，告知 Twilio 如何处理通话。

    路由判断逻辑（按优先级）：
        1. master_switch = "offline"
           → 播放离线消息后挂断（或直接拒接，取决于 offline_message 是否为空）
        2. master_switch = "bypass"
           → 播放绕过消息后直接转接人工
        3. 并发数 >= max_concurrent_calls
           → 根据 call_overflow_action 转接人工或播放繁忙消息后挂断
        4. 正常情况（master_switch = "active"）
           → 建立 WebSocket 媒体流，开始 AI 接待

    每次来电都会重新加载配置（config.reload_settings()），
    确保通过管理面板修改的设置立即生效。

    Args:
        request (Request): FastAPI 请求对象，包含来电号码（Form 参数）

    Returns:
        Response: 内容为 TwiML XML 字符串，Content-Type 为 "application/xml"
    """
    # 每次来电重新加载配置，确保管理面板的修改立即生效
    config.reload_settings()

    # 获取服务器 Host（用于构建 WebSocket WSS 地址）
    host = request.headers.get("host")
    if not host:
        host = "localhost:5000"  # 本地调试时的后备值

    # 提取来电号码和账户 SID（Twilio 在 Form 数据中提供）
    form_data = await request.form()
    caller_number = form_data.get("From", "Unknown")
    call_sid = form_data.get("CallSid", "Unknown")
    account_sid = form_data.get("AccountSid", "Unknown")
    logger.info(f"来电号码: {caller_number}, AccountSid: {account_sid}")

    # --- 路由判断 1：离线模式 ---
    if config.master_switch == "offline":
        logger.info(f"状态 [Offline]: 处理来电 {caller_number}")
        if not config.offline_message or config.offline_message.strip() == "":
            # 离线消息为空：直接拒接，不播放任何声音
            twiml = "<Response><Reject /></Response>"
        else:
            # 使用 Amazon Polly TTS 播放离线消息后挂断
            twiml = f"""
            <Response>
                <Say voice="Polly.Amy">{config.offline_message}</Say>
                <Hangup/>
            </Response>
            """
        return Response(content=twiml, media_type="application/xml")

    # --- 路由判断 2：旁路模式（直接转人工）---
    elif config.master_switch == "bypass":
        logger.info(f"状态 [Bypass]: 转接人工 {caller_number}")
        twiml = f"""
        <Response>
            <Say voice="Polly.Amy">{config.bypass_message}</Say>
            <Dial>{config.transfer_phone_number}</Dial>
        </Response>
        """
        return Response(content=twiml, media_type="application/xml")

    # --- 路由判断 3：并发上限检查 ---
    active_count = len(ACTIVE_CALLS)
    if active_count >= config.max_concurrent_calls:
        logger.warning(
            f"[并发] 已达上限 ({active_count}/{config.max_concurrent_calls})，"
            f"拒绝来电 {caller_number}"
        )
        call_log_add(call_sid, caller_number, "twilio")
        call_log_end(call_sid, order_finalized=None, missed=True)
        background_tasks.add_task(broadcast_admin, "call_log_update", safe_call_log())
        if config.busy_message and config.busy_message.strip():
            twiml = f"""<Response>
                <Say voice="Polly.Amy">{config.busy_message}</Say>
                <Hangup/>
            </Response>"""
        else:
            twiml = """<Response><Reject reason="busy"/></Response>"""
        return Response(content=twiml, media_type="application/xml")

    # --- 路由判断 4：正常接待（active 模式，容量未满）---
    call_log_add(call_sid, caller_number, "twilio")
    background_tasks.add_task(broadcast_admin, "call_log_update", safe_call_log())
    background_tasks.add_task(broadcast_admin, "ai_status", {"busy": active_count + 1 >= config.max_concurrent_calls})

    twiml = f"""
    <Response>
        <Connect>
            <Stream url="wss://{host}/media-stream">
                <Parameter name="customer_number" value="{caller_number}" />
            </Stream>
        </Connect>
        <!-- WebSocket 关闭后，Twilio 重定向到此路由继续执行 TwiML -->
        <Redirect method="POST">https://{host}/stream-ended</Redirect>
    </Response>
    """
    return Response(content=twiml, media_type="application/xml")


    # <Connect><Stream> 是核心指令，指示 Twilio 建立 WebSocket 媒体流
    # url 必须是 wss:// 协议（Twilio 要求 TLS 加密），因此需要 ngrok 提供 HTTPS 隧道
    # <Parameter> 将来电号码作为自定义参数传递给流处理器
    # <Redirect> 在 WebSocket 关闭后执行，用于处理挂断/转接后续逻辑
    twiml = f"""
    <Response>
        <Connect>
            <Stream url="wss://{host}/media-stream">
                <Parameter name="customer_number" value="{caller_number}" />
            </Stream>
        </Connect>
        <!-- WebSocket 关闭后，Twilio 重定向到此路由继续执行 TwiML -->
        <Redirect method="POST">https://{host}/stream-ended</Redirect>
    </Response>
    """
    return Response(content=twiml, media_type="application/xml")


@app.post("/stream-ended")
async def stream_ended(request: Request):
    """
    WebSocket 媒体流结束后的通话后续处理。

    当 /media-stream WebSocket 关闭后，Twilio 会调用 incoming-call TwiML 中的
    <Redirect> 指令，跳转到此路由。

    此路由根据 CALL_STATES 字典中记录的意图决定最终动作：
        - intent = "hangup"   → 执行 <Hangup> 正常挂断
        - intent = "transfer" → 执行 <Dial> 转接到人工号码

    兼容性说明：
        state 可能是旧格式（字符串）或新格式（字典），
        代码同时支持两种格式以保证向后兼容。

    Args:
        request (Request): Twilio 的 POST 请求，包含 CallSid 等参数

    Returns:
        Response: TwiML XML（Hangup 或 Dial）
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    logger.info(f"通话流结束，CallSid: {call_sid}")

    # 强制重新加载配置，确保读取到最新的 transfer_phone_number 等设置
    config.reload_settings()

    # 获取状态，兼容旧版字符串格式和新版字典格式
    state = CALL_STATES.get(call_sid, {"intent": "hangup", "reason": "Unknown"})
    if isinstance(state, str):
        # 旧格式（已废弃）：状态直接是字符串
        intent = state
        reason = "Unknown"
    else:
        # 新格式：字典，包含 intent 和 reason
        intent = state.get("intent", "hangup")
        reason = state.get("reason", "Unknown")

    # 清除已处理的状态，防止内存泄漏
    if call_sid in CALL_STATES:
        del CALL_STATES[call_sid]

    if intent == "transfer":
        logger.info(f"执行转接，原因: {reason}")
        if reason == "system_fallback":
            message = "I'm having trouble connecting to my brain right now. Please hold on while I transfer you to a human."
        else:
            message = "Transferring you now. Please hold."
        twiml = f"""
        <Response>
            <Say voice="Polly.Amy">{message}</Say>
            <Dial>{config.transfer_phone_number}</Dial>
        </Response>
        """
    else:
        # 默认：正常挂断
        twiml = """
        <Response>
            <Hangup/>
        </Response>
        """

    return Response(content=twiml, media_type="application/xml")


@app.post("/call-status")
async def call_status(request: Request):
    """
    Twilio 通话状态回调（StatusCallback）处理器。
    Twilio 在通话状态变化时（ringing, in-progress, completed 等）POST 到此端点。
    只需返回 204 No Content 告知 Twilio 已收到即可。
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    status = form_data.get("CallStatus", "unknown")
    logger.info(f"Twilio 通话状态回调: SID={call_sid}, status={status}")
    return Response(status_code=204)



@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):

    """
    Twilio 媒体流 WebSocket 处理器，是整个系统的核心。

    功能：
        双向实时桥接 Twilio（电话端）和 Google Gemini Live API（AI 端），
        实现"AI 接电话"的核心功能。

    音频处理流程：
        ┌─────────────────────────────────────────────────┐
        │ 方向 1 (Twilio → Gemini)：                        │
        │   mu-law 8k → PCM 16-bit 8k → PCM 16-bit 16k    │
        │   （上采样：每个样本重复一次）                      │
        │                                                   │
        │ 方向 2 (Gemini → Twilio)：                        │
        │   PCM 16-bit 24k → PCM 16-bit 8k → mu-law 8k    │
        │   （下采样：每 3 个字节取第 1 个，即 24k→8k）       │
        └─────────────────────────────────────────────────┘

    并发架构：
        两个独立的异步任务并发运行：
            任务 A (receive_from_twilio)：Twilio → Gemini 方向
            任务 B (receive_from_gemini)：Gemini → Twilio 方向 + 工具调用

        使用 asyncio.wait(return_when=FIRST_COMPLETED) 等待，
        任何一个任务结束（正常或异常），另一个任务立即被取消。

    工具调用处理（在任务 B 中）：
        Gemini 可能在响应中包含 toolCall 字段，表示需要调用某个函数。
        支持的工具：
            - search_address：调用 AutoAddress API 验证地址
            - calculate_total：计算订单总价
            - end_call：挂断并归档订单
            - transfer_call：转接人工
            - get_past_order：查询历史订单

    注意：
        此函数为 WebSocket 端点，不直接被 HTTP 路由调用。
        Twilio 在建立媒体流时会自动连接此 WebSocket。
    """
    await websocket.accept()
    logger.info("Twilio WebSocket 连接已建立")

    # 建立与 Google Gemini Live API 的 WebSocket 连接
    # gemini_ws_uri 包含 API Key，在 config.gemini_ws_uri 属性中动态生成
    async with ws_connect(
        config.gemini_ws_uri,
        extra_headers={"Content-Type": "application/json"}
    ) as gemini_ws:


        # --- 共享状态变量（在两个子任务间共享）---
        stream_sid = None        # Twilio 媒体流 SID（发送音频时必须携带）
        stream_call_sid = None   # Twilio 通话 SID（用于 CALL_STATES 和 ACTIVE_CALLS）
        customer_number = "Unknown"   # 来电号码
        customer_info = None     # 客户档案字典（从数据库查询，可能为 None）
        call_transcript = []     # 记录该通电话的对话记录

        # 草稿订单缓存：在 calculate_total 调用后立即填充
        # 若通话在 end_call 前意外断开，此草稿会被自动保存为"未完成"订单
        draft_order = {}
        order_finalized = False  # 标记 end_call 是否已成功执行（避免重复保存）

        # -----------------------------------------------------------------------
        # 内部任务 A：Twilio → Gemini（接收用户语音，转发给 AI）
        # -----------------------------------------------------------------------
        async def receive_from_twilio():
            """
            持续接收 Twilio 发来的 WebSocket 消息，处理三种事件：
                1. media：音频数据包（mu-law 8k）
                   → 解码为 PCM 16bit 8k → 上采样到 16k → 发送给 Gemini
                2. start：通话开始事件
                   → 提取 stream_sid、call_sid、来电号码
                   → 查询客户档案
                   → 发送 Gemini 初始化 Setup 消息
                   → 发送触发器让 AI 先开口打招呼
                3. stop：通话停止事件
                   → 退出循环，结束任务
            """
            nonlocal stream_sid, stream_call_sid, customer_number, customer_info

            try:
                while True:
                    message = await websocket.receive_text()
                    data = json.loads(message)

                    # --- 事件 1：音频数据包 ---
                    if data['event'] == 'media':
                        media_payload = data['media']['payload']
                        # 步骤1：Base64 解码得到 mu-law 编码的原始字节
                        mulaw_data = base64.b64decode(media_payload)

                        # 步骤2：mu-law → PCM 16-bit（8kHz）
                        # audioop.ulaw2lin(data, width) 中 width=2 表示 16-bit 采样
                        pcm_8k = audioop.ulaw2lin(mulaw_data, 2)

                        # 步骤3：PCM 8kHz → PCM 16kHz（Gemini 要求最低 16kHz）
                        # 方法：简单重复（每个 2 字节样本写两次）
                        # 这是最低成本的上采样方法，会产生轻微的阶梯状失真，
                        # 但对语音识别来说已足够准确
                        pcm_16k_chunks = []
                        for i in range(0, len(pcm_8k), 2):
                            sample = pcm_8k[i:i+2]
                            pcm_16k_chunks.append(sample)
                            pcm_16k_chunks.append(sample)  # 重复一次实现 2× 上采样
                        pcm_16k = b"".join(pcm_16k_chunks)

                        # 步骤4：发送给 Gemini（Base64 编码的 PCM 音频）
                        await gemini_ws.send(json.dumps({
                            "realtimeInput": {
                                "audio": {
                                    "data": base64.b64encode(pcm_16k).decode('utf-8'),
                                    "mimeType": f"audio/pcm;rate={config.gemini_input_sample_rate}"
                                }
                            }
                        }))

                    # --- 事件 2：通话开始 ---
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        stream_call_sid = data['start']['callSid']
                        # 从 incoming-call 路由通过 TwiML <Parameter> 传递的来电号码
                        custom_params = data['start'].get('customParameters', {})
                        customer_number = custom_params.get('customer_number', 'Unknown')
                        logger.info(
                            f"通话开始，Stream SID: {stream_sid}, "
                            f"Customer Number: {customer_number}"
                        )

                        # 查询客户档案（返回 None 表示新客户）
                        customer_info = database.get_customer(customer_number)
                        caller_name = (
                            customer_info.get('name', 'Unknown Caller')
                            if customer_info else 'Unknown Caller'
                        )

                        # 记录到活跃通话字典，用于并发控制和管理面板展示
                        ACTIVE_CALLS[stream_call_sid] = {
                            "start_time": time.time(),
                            "caller_number": customer_number,
                            "caller_name": caller_name
                        }
                        # 广播给管理面板
                        await broadcast_admin("call_start", {
                            "call_sid": stream_call_sid,
                            "caller": customer_number,
                            "caller_name": caller_name,
                            "active_count": len(ACTIVE_CALLS),
                            "active_calls": ACTIVE_CALLS
                        })

                        # 加载菜单和餐厅信息（用于构建 AI System Prompt）
                        menu_text = database.get_menu_text()
                        restaurant_info = database.get_restaurant_info()

                        # 发送 Gemini Setup 消息（定义 AI 人设、工具列表、语音配置）
                        await send_setup_message(
                            gemini_ws, customer_info, menu_text,
                            restaurant_info, customer_number
                        )

                        # 发送初始触发器：强制 AI 先开口打招呼
                        # Gemini Live API 默认等待用户先说话，
                        # 通过发送一个文本消息触发 AI 主动开口
                        logger.info("发送初始触发器给 Gemini...")
                        await gemini_ws.send(json.dumps({
                            "clientContent": {
                                "turns": [{
                                    "role": "user",
                                    "parts": [{"text": "Call connected. Please greet the customer."}]
                                }],
                                "turnComplete": True
                            }
                        }))

                    # --- 事件 3：通话停止 ---
                    elif data['event'] == 'stop':
                        # Twilio 主动终止：可能是通话超时、来电方挂断、或 Twilio 服务端问题
                        logger.warning(
                            f"⚠️ Twilio 发送了停止信号 (call_sid={stream_call_sid})。"
                            f"这通常意味着 Twilio 端主动结束了通话，"
                            f"可能原因：客户挂断、Twilio 超时、或网络问题。"
                        )
                        await broadcast_admin("system_log", {
                            "message": "Twilio 发送停止信号 — 通话被 Twilio 端终止",
                            "type": "error"
                        })
                        return  # 退出循环，任务结束后另一个任务也会被取消

            except ConnectionClosed:
                logger.info("Twilio WebSocket 正常断开")
                return
            except Exception as e:
                logger.error(f"Twilio 接收循环异常: {e}")
                return

        # -----------------------------------------------------------------------
        # 内部任务 B：Gemini → Twilio（接收 AI 回复，转发音频给用户 + 处理工具调用）
        # -----------------------------------------------------------------------
        async def receive_from_gemini():
            """
            持续接收 Gemini 发来的 WebSocket 消息，处理四类内容：
                1. 音频数据（modelTurn.parts[].inlineData）
                   → 解码 PCM 24k → 下采样到 8k → 编码 mu-law → 发送给 Twilio
                2. 实时转录（inputTranscription）
                   → 用户的实时语音转文字，广播给管理面板字幕
                3. AI 输出转录（outputTranscription）
                   → AI 回复的文字版本，广播给管理面板字幕
                4. 打断信号（interrupted）
                   → 用户打断 AI 说话，清空 Twilio 音频缓冲队列
                5. 工具调用（toolCall）
                   → 分发到对应工具函数，返回结果给 Gemini
                6. 回合结束（turnComplete）
                   → 发送最终字幕标记，重置转录缓冲区
            """
            # 追踪音频播放预计完成时间（用于在挂断前等待告别语播放完毕）
            expected_finish_time = time.time()
            # 当前用户回合的实时转录文本（累积多个 chunk）
            current_user_transcript = ""
            # 声明外层共享变量（草稿订单缓存和完成标记）
            current_ai_transcript = ""
            nonlocal draft_order, order_finalized

            typing_event = None
            typing_task = None

            def start_typing_sound():
                nonlocal typing_event, typing_task
                if stream_sid and (typing_event is None or typing_event.is_set()):
                    import audio_injector
                    typing_event = asyncio.Event()
                    typing_task = asyncio.create_task(
                        audio_injector.stream_audio_to_websocket(
                            websocket, "twilio", typing_event, stream_sid
                        )
                    )

            def stop_typing_sound():
                nonlocal typing_event
                if typing_event and not typing_event.is_set():
                    typing_event.set()

            try:
                async for message in gemini_ws:
                    response = json.loads(message)

                    audio_data_parts = []  # 本次消息中的音频数据列表
                    
                    # 检测 Gemini 的 goAway 信号（会话即将到期的预警）
                    if 'goAway' in response:
                        time_left = response['goAway'].get('timeLeft', 'unknown')
                        logger.warning(
                            f"⚠️ Gemini 发出 goAway 信号！会话将在 {time_left} 后终止。"
                            f"通话将被强制结束，请注意草稿订单救援。"
                        )
                        await broadcast_admin("system_log", {
                            "message": f"⚠️ Gemini 会话即将超时 (剩余: {time_left})，通话可能即将断开",
                            "type": "error"
                        })

                    if 'serverContent' in response:
                        server_content = response['serverContent']

                        # --- 提取音频数据 ---
                        if 'modelTurn' in server_content:
                            parts = server_content['modelTurn'].get('parts', [])
                            for part in parts:
                                if 'inlineData' in part:
                                    # Base64 编码的 PCM 24kHz 音频
                                    audio_data_parts.append(part['inlineData']['data'])
                                    # 当 AI 开始回吐真实音频时，停止机械打字声
                                    stop_typing_sound()
                                if 'text' in part:
                                    text_content = part['text']
                                    # 当 AI 输出思维过程 (text) 时，启动机械打字声填补时间
                                    start_typing_sound()
                                    logger.info(f"Gemini 文本响应: {text_content}")
                                    call_transcript.append({
                                        "role": "thought", 
                                        "text": f"💭 思考过程: {text_content}", 
                                        "timestamp": time.time()
                                    })
                                    # 广播给管理面板
                                    await broadcast_admin("transcript", {
                                        "call_sid": stream_call_sid,
                                        "role": "thought",
                                        "text": f"💭 思考过程: {text_content}",
                                        "is_final": True
                                    })

                        # --- 实时用户语音转录（字幕流）---
                        if 'inputTranscription' in server_content:
                            transcription = server_content['inputTranscription']
                            if 'text' in transcription and transcription['text']:
                                text_chunk = transcription['text']
                                current_user_transcript += text_chunk  # 累积 chunk
                                # 人类说话时，绝对不能有打字声
                                stop_typing_sound()
                                # 黄色输出到服务器终端（实时流式输出，不换行）
                                print(f"\033[93m{text_chunk}\033[0m", end="", flush=True)
                                # 广播给管理面板（实时字幕）
                                await broadcast_admin("transcript", {
                                    "call_sid": stream_call_sid,
                                    "role": "user",
                                    "text": text_chunk,
                                    "is_final": False  # 是 chunk 而非完整句子
                                })

                        # --- AI 输出转录（AI 说了什么）---
                        if 'outputTranscription' in server_content:
                            text_chunk = server_content['outputTranscription'].get('text', '')
                            text_chunk = re.sub(r'<ctrl\d+>', '', text_chunk)  # filter Gemini internal tokens
                            if text_chunk:
                                current_ai_transcript += text_chunk
                                # 青色输出到服务器终端（实时流式输出，不换行）
                                print(f"\033[96m{text_chunk}\033[0m", end="", flush=True)
                                # 广播给管理面板（实时字幕，未完结阶段）
                                await broadcast_admin("transcript", {
                                    "call_sid": stream_call_sid,
                                    "role": "ai",
                                    "text": text_chunk,
                                    "is_final": False # 标记为 chunk
                                })

                        # --- 处理打断信号 ---
                        # Gemini 检测到用户在 AI 说话时开口，发送 interrupted=True
                        if server_content.get('interrupted'):
                            word_count = len(current_user_transcript.strip().split())
                            logger.info(
                                f"检测到打断信号。"
                                f"当前转录: '{current_user_transcript}' "
                                f"(单词数: {word_count})"
                            )

                            if word_count > 1:
                                # 有效打断（超过 1 个单词）：清空 Twilio 端的音频缓冲队列
                                # 这会立即停止正在播放的 AI 语音，响应用户打断
                                logger.info("⚠️ 有效打断 (单词 > 1) → 清空播放队列")
                                stop_typing_sound()
                                if stream_sid:
                                    await websocket.send_json({
                                        "event": "clear",
                                        "streamSid": stream_sid
                                    })
                                # 重置预计完成时间
                                expected_finish_time = time.time()
                                print("\n\033[91m[用户有效打断]\033[0m")

                                # 打断时，如果 AI 刚说到一半，把 AI 已经说的半截话归档
                                if current_ai_transcript.strip():
                                    call_transcript.append({"role": "ai", "text": current_ai_transcript, "timestamp": time.time()})
                                    await broadcast_admin("transcript", {
                                        "call_sid": stream_call_sid,
                                        "role": "ai",
                                        "text": current_ai_transcript,
                                        "is_final": True
                                    })
                                    current_ai_transcript = "" # 清空 AI 转录缓冲区

                                # (不需要向 Gemini 发送 turnComplete，Gemini 在发送 interrupted 时内部已自动中止回合)
                            else:
                                # 短打断（≤1 个单词）：忽略，视为背景噪音或短词
                                # 这避免了因咳嗽、喘气等噪音导致 AI 被打断的问题
                                logger.info("ℹ️ 忽略短打断 (噪音/短词)")

                            # 无论是否有效打断，都重置用户转录缓冲区
                            current_user_transcript = ""

                        # --- 回合结束信号 ---
                        if 'turnComplete' in server_content and server_content['turnComplete']:
                            print("")  # 换行，使下一行输出不与转录连在一起
                            # 发送该回合用户语音的最终完整文本给管理面板
                            if current_user_transcript:
                                call_transcript.append({"role": "user", "text": current_user_transcript, "timestamp": time.time()})
                                await broadcast_admin("transcript", {
                                    "call_sid": stream_call_sid,
                                    "role": "user",
                                    "text": current_user_transcript,
                                    "is_final": True  # 标记为完整句子
                                })
                            current_user_transcript = ""  # 重置用户转录缓冲区

                            # 发送该回合 AI 语音的最终完整文本给管理面板
                            if current_ai_transcript.strip():
                                call_transcript.append({"role": "ai", "text": current_ai_transcript, "timestamp": time.time()})
                                await broadcast_admin("transcript", {
                                    "call_sid": stream_call_sid,
                                    "role": "ai",
                                    "text": current_ai_transcript,
                                    "is_final": True
                                })
                            current_ai_transcript = "" # 清空 AI 转录缓冲区

                    # --- 发送音频给 Twilio ---
                    # 注：音频处理放在 serverContent 判断块之外，
                    # 确保即使有工具调用等其他响应，音频也能及时发出
                    if audio_data_parts:
                        for audio_data_b64 in audio_data_parts:
                            # 步骤1：Base64 解码 → PCM 16-bit 24kHz 字节
                            pcm_24k = base64.b64decode(audio_data_b64)

                            # 步骤2：PCM 24kHz → PCM 8kHz（下采样，比例 1:3）
                            # 方法：每 6 个字节（3个 16-bit 样本）取前 2 个字节（第 1 个样本）
                            # 即丢弃 2/3 的样本，从 24k 降到 8k
                            try:
                                pcm_8k_chunks = []
                                for i in range(0, len(pcm_24k), 6):
                                    pcm_8k_chunks.append(pcm_24k[i:i+2])
                                pcm_8k = b"".join(pcm_8k_chunks)
                            except Exception as e:
                                logger.error(f"重采样错误: {e}")
                                # 出错时使用简单的切片降采样作为后备方案
                                pcm_8k = pcm_24k[::3]

                            # 步骤3：PCM 16-bit → mu-law（Twilio 要求的格式）
                            mulaw_data = audioop.lin2ulaw(pcm_8k, 2)

                            # 步骤4：计算并更新预计音频播放完成时间
                            # 这用于在挂断前等待足够长的时间，确保告别语播完
                            chunk_duration = len(mulaw_data) / config.twilio_sample_rate
                            # 如果当前时间已超过预计完成时间（缓冲区已空），
                            # 从当前时刻重新开始计算；否则在现有队列末尾追加
                            expected_finish_time = (
                                max(time.time(), expected_finish_time) + chunk_duration
                            )

                            # 步骤5：发送给 Twilio 播放（streamSid 是必须的）
                            if stream_sid:
                                await websocket.send_json({
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": base64.b64encode(mulaw_data).decode('utf-8')
                                    }
                                })

                    # --- 处理工具调用 ---
                    if 'toolCall' in response:
                        tool_call = response['toolCall']
                        function_calls = tool_call.get('functionCalls', [])

                        logger.info(f"Gemini 请求工具调用: {function_calls}")
                        # 广播工具调用事件到管理面板（可视化调试）
                        await broadcast_admin("tool_call", {
                            "call_sid": stream_call_sid,
                            "calls": function_calls
                        })

                        # --- AUDIO INJECTOR (Twilio Ticking Sound) ---
                        # Prevent dead air over the phone while the API processes tools
                        start_typing_sound()

                        function_responses = []  # 收集所有工具的返回结果

                        for call in function_calls:
                            call_name = call['name']
                            call_args = call.get('args', {})
                            # ---- 工具 1：地址搜索 ----
                            if call_name == 'search_address':
                                query = call_args.get('address_query')
                                t0 = time.perf_counter()
                                result = await tools_address.search_address(query)
                                t1 = time.perf_counter()
                                logger.info(f"地址搜索耗时 {t1 - t0:.2f} 秒")

                                function_responses.append({
                                    "name": "search_address",
                                    "id": call['id'],
                                    "response": {
                                        "result": result,
                                        "scheduling": "INTERRUPT"  # NON_BLOCKING: 立即打断啄报结果
                                    }
                                })

                            # ---- 工具 2：价格计算 ----
                            elif call_name == 'calculate_total':
                                logger.info(f"🔢 [里程碑] 执行 calculate_total，参数: {call_args}")
                                
                                result = tools_pricing.calculate_total(
                                    call_args.get('items', []),
                                    call_args.get('delivery_fee', 0.0),
                                    call_args.get('payment_method', 'cash')
                                )
                                
                                function_responses.append({
                                    "name": "calculate_total",
                                    "id": call['id'],
                                    "response": result
                                })

                                # ★ 报价后立即缓存草稿订单
                                # 若通话在 end_call 前意外断开，草稿会被自动保存
                                draft_order = {
                                    "items": call_args.get('items', []),
                                    "delivery_fee": call_args.get('delivery_fee', 0.0),
                                    "payment_method": call_args.get('payment_method', 'unknown'),
                                    "calculate_total_result": result.get('result', ''),
                                    "total": result.get('total', 0.0)
                                }
                                logger.info("草稿订单已缓存（报价完成）")
                                
                                # ★ 实时广播到前端供 POS 小票展示
                                await broadcast_admin("live_order_update", {
                                    "call_sid": stream_call_sid,
                                    "items": call_args.get('items', []),
                                    "delivery_fee": result.get('delivery_fee', call_args.get('delivery_fee', 0.0)),
                                    "payment_method": call_args.get('payment_method', 'unknown'),
                                    "total": result.get('total', 0.0),
                                    "subtotal": result.get('subtotal', 0.0)
                                })

                            # ---- 工具 3：结束通话（含订单归档）----
                            elif call_name == 'end_call':
                                logger.info("📞 [里程碑] Gemini 请求挂断电话 (END CALL)")
                                reason = call_args.get('reason', 'Unknown')

                                # 如果有订单数据（Order 在 reason 中或传入了 items），保存订单
                                if "Order" in reason or call_args.get('items'):
                                    try:
                                        # 生成唯一订单 ID（时间戳 + UUID 前4位）
                                        order_id = f"ORD-{int(time.time())}-{str(uuid.uuid4())[:4]}"
                                        items = call_args.get('items', [])
                                        total = call_args.get('total_value', 0.0)
                                        s_type = call_args.get('service_type', 'Unknown')
                                        contact_phone = call_args.get('contact_phone')
                                        order_note = call_args.get('order_note', '')

                                        # 构建订单记录字典
                                        order_record = {
                                            "order_id": order_id,
                                            "business_date_str": get_business_date_str(),
                                            "timestamp": time.ctime(),     # 人类可读的时间戳
                                            "customer_phone": customer_number,  # Caller ID
                                            "contact_phone": contact_phone,     # 联系电话
                                            "customer_name": call_args.get(
                                                'customer_name',
                                                customer_info.get('name') if customer_info else "Unknown"
                                            ),
                                            "service_type": s_type,
                                            "address": call_args.get(
                                                'customer_address',
                                                customer_info.get('address') if customer_info else "Pickup"
                                            ),
                                            "delivery_area": call_args.get('delivery_area', 'Unknown'),
                                            "delivery_fee": call_args.get('delivery_fee', 0.0),
                                            "items": items,
                                            "total_value": total,
                                            "payment_method": call_args.get('payment_method', 'Unknown'),
                                            "note": order_note,
                                            "source": "AI",  # 标记为 AI 接单
                                            "transcript": call_transcript
                                        }

                                        # 持久化保存订单（锁防并发写入损坏）
                                        async with _db_write_lock:
                                            database.save_order(order_record)
                                            # 更新客户历史档案
                                            summary = f"{order_id}: {len(items)} items (€{total})"
                                            database.update_customer_history(
                                                customer_number, summary,
                                                name=call_args.get('customer_name'),
                                                address=call_args.get('customer_address')
                                            )

                                        logger.info(f"✅ 订单已归档: {order_id}")
                                        order_finalized = True  # 标记正式完成，草稿不再需要

                                        # 统计今日订单（含草稿）并广播给管理面板
                                        _completed, _incomplete = get_order_counts()
                                        await broadcast_admin("new_order", {
                                            "total_orders": _completed,
                                            "incomplete_orders": _incomplete,
                                            "order_id": order_id
                                        })

                                    except Exception as e:
                                        logger.error(f"归档订单失败: {e}")

                                # 记录挂断意图（/stream-ended 路由会读取此状态）
                                CALL_STATES[stream_call_sid] = {
                                    "intent": "hangup",
                                    "reason": reason
                                }

                                # 等待告别语播放完毕再挂断
                                remaining_time = expected_finish_time - time.time()
                                if remaining_time > 0:
                                    # 还有待播放的音频：等待剩余时间 + 安全缓冲
                                    wait_time = remaining_time + config.goodbye_audio_buffer_seconds
                                    logger.info(f"即将挂断，等待告别语播放 ({wait_time:.2f}s)...")
                                    await asyncio.sleep(wait_time)
                                else:
                                    # 没有待播放音频：最小延迟后挂断（防止客户听不到最后几个字）
                                    logger.info("无待播音频，执行最小缓冲挂断...")
                                    await asyncio.sleep(config.minimum_hangup_delay_seconds)

                                # 关闭两端 WebSocket 连接，触发 Twilio 执行 <Redirect>
                                await gemini_ws.close()
                                await websocket.close()
                                return  # 退出任务 B 的循环

                            # ---- 工具 4：转接人工 ----
                            elif call_name == 'transfer_call':
                                logger.info("Gemini 请求转接电话 (TRANSFER CALL)")
                                reason = call_args.get('reason', 'Generic Transfer')

                                # 记录转接意图（/stream-ended 路由会读取此状态并生成 <Dial> TwiML）
                                CALL_STATES[stream_call_sid] = {
                                    "intent": "transfer",
                                    "reason": reason
                                }

                                # 等待 AI 当前说的话播放完毕（如"正在为您转接，请稍候"）
                                remaining_time = expected_finish_time - time.time()
                                if remaining_time > 0:
                                    wait_time = remaining_time + 1.0  # 1 秒安全缓冲
                                    logger.info(f"等待 AI 说完后转接 ({wait_time:.2f}s)...")
                                    await asyncio.sleep(wait_time)

                                # 关闭连接，触发 Twilio 执行 <Redirect> → /stream-ended
                                await gemini_ws.close()
                                await websocket.close()
                                return  # 退出循环

                            # ---- 工具 5：查询历史订单 ----
                            elif call_name == 'get_past_order':
                                logger.info("Gemini 请求查询历史订单")
                                o_id = call_args.get('order_id')
                                result = tools_history.get_past_order(o_id)
                                logger.info(f"历史订单查询结果: {result}")

                                function_responses.append({
                                    "name": "get_past_order",
                                    "id": call['id'],
                                    "response": {
                                        **result,
                                        "scheduling": "INTERRUPT"  # NON_BLOCKING: 历史订单查到后立即打断啄报
                                    }
                                })

                        # 将所有工具的返回结果批量发回给 Gemini
                        if function_responses:
                            tool_response_msg = {
                                "toolResponse": {
                                    "functionResponses": function_responses
                                }
                            }
                            logger.info(f"发送 toolResponse: {tool_response_msg}")
                            await gemini_ws.send(json.dumps(tool_response_msg))

                            # 广播工具响应到管理面板（可视化调试）
                            await broadcast_admin("tool_response", {
                                "call_sid": stream_call_sid,
                                "responses": function_responses
                            })
                            
                        # --- 结束打字音效注入 ---
                        stop_typing_sound()

            except ConnectionClosed as e:
                close_code = e.rcvd.code if e.rcvd else "unknown"
                close_reason = e.rcvd.reason if e.rcvd else "no reason"

                if close_code == 1000:
                    logger.warning(
                        f"⚠️ Gemini 正常关闭 (code=1000)，可能是会话时长达到上限。原因: {close_reason}"
                    )
                    await broadcast_admin("system_log", {
                        "message": "Gemini 会话正常结束 (code=1000) — 可能已达会话时长上限",
                        "type": "error"
                    })
                elif close_code == 1008:
                    logger.error(
                        f"❌ Gemini 拒绝连接 (code=1008): {close_reason}\n"
                        f"   可能原因: ① 模型不支持某个 setup 参数（如 inputAudioTranscription）\n"
                        f"   ② 模型名称已失效，请在设置中更换模型\n"
                        f"   ③ API Key 配额耗尽或无权访问 Live API\n"
                        f"   当前模型: {config.model_name}"
                    )
                    await broadcast_admin("system_log", {
                        "message": (
                            f"⛔ Gemini 拒绝连接 (1008): {close_reason} | "
                            f"模型: {config.model_name} | "
                            f"请检查：① 模型名是否有效 ② API Key 是否有 Live API 权限"
                        ),
                        "type": "error"
                    })
                else:
                    logger.error(f"❌ Gemini WebSocket 异常关闭 (code={close_code}): {close_reason}")
                    await broadcast_admin("system_log", {
                        "message": f"Gemini 连接异常断开 code={close_code}: {close_reason}",
                        "type": "error"
                    })
                    if stream_call_sid:
                        CALL_STATES[stream_call_sid] = {"intent": "transfer", "reason": "system_fallback"}

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"Gemini 接收循环未知异常: {e}\n{tb}")
                await broadcast_admin("system_log", {
                    "message": f"Gemini 流连接异常: {type(e).__name__}: {e}",
                    "type": "error"
                })
                if stream_call_sid:
                    CALL_STATES[stream_call_sid] = {"intent": "transfer", "reason": "system_fallback"}

        # -----------------------------------------------------------------------
        # 启动双向并发任务并等待
        # -----------------------------------------------------------------------

        # 创建两个异步任务（非阻塞地并发运行）
        twilio_task = asyncio.create_task(receive_from_twilio())
        gemini_task = asyncio.create_task(receive_from_gemini())

        try:
            # 等待任意一个任务完成（正常结束或抛出异常）
            # FIRST_COMPLETED：只要有一个任务完成就返回，不等另一个
            done, pending = await asyncio.wait(
                [twilio_task, gemini_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # 取消所有仍在运行的任务（另一个方向的传输也必须停止）
            for task in pending:
                task.cancel()

            logger.info("媒体流双向通讯结束")

        except asyncio.CancelledError:
            # 整个 WebSocket 处理函数被外部取消（如服务关闭）
            logger.info("任务被取消（通常是因为 WebSocket 意外断开）")
            twilio_task.cancel()
            gemini_task.cancel()

        except Exception as e:
            logger.error(f"媒体流处理中发生意外错误: {e}")
            twilio_task.cancel()
            gemini_task.cancel()

        finally:
            # ★ 草稿订单救援：若通话在 end_call 前意外断开，自动保存未完成订单
            # 注意：stream_call_sid 可能为 None（如 Gemini 在 Twilio START 前就崩了）
            if not order_finalized:
                try:
                    # 如果 Gemini 在 START 之前就失败了，生成一个临时 SID
                    rescue_sid = stream_call_sid or f"ERROR-{int(time.time())}"
                    rescue_id = f"ORD-INCOMPLETE-{int(time.time())}-{str(uuid.uuid4())[:4]}"
                    rescue_record = {
                        "order_id": rescue_id,
                        "business_date_str": get_business_date_str(),
                        "timestamp": time.ctime(),
                        "customer_phone": customer_number,
                        "contact_phone": None,
                        "customer_name": customer_info.get('name', 'Unknown') if customer_info else 'Unknown',
                        "address": customer_info.get('address', 'Unknown') if customer_info else 'Unknown',
                        "delivery_area": "Unknown",
                        "items": draft_order.get('items', []) if draft_order else [],
                        "total_value": draft_order.get('total', 0.0) if draft_order else 0.0,
                        "payment_method": draft_order.get('payment_method', 'Unknown') if draft_order else 'Unknown',
                        "delivery_fee": draft_order.get('delivery_fee', 0.0) if draft_order else 0.0,
                        "note": f"⚠️ 通话意外断开。报价详情: {draft_order.get('calculate_total_result', '无报价') if draft_order else '无报价'}",
                        "service_type": "Dropped",
                        "source": "AI-Incomplete",
                        "transcript": call_transcript
                    }
                    database.save_order(rescue_record)
                    logger.warning(f"⚠️ 草稿订单已救援保存: {rescue_id}")
                    _completed, _incomplete = get_order_counts()
                    await broadcast_admin("new_order", {
                        "total_orders": _completed,
                        "incomplete_orders": _incomplete,
                        "order_id": rescue_id,
                        "warning": "通话意外断开，草稿订单已自动保存，请人工核实"
                    })
                except Exception as e:
                    logger.error(f"草稿订单救援失败: {e}")

            # 清理工作：无论通话如何结束，从活跃通话字典中移除并广播
            # finally 块确保即使发生异常也能正确清理资源
            if stream_call_sid and stream_call_sid in ACTIVE_CALLS:
                del ACTIVE_CALLS[stream_call_sid]
                await broadcast_admin("call_end", {
                    "call_sid": stream_call_sid,
                    "active_count": len(ACTIVE_CALLS),
                    "active_calls": ACTIVE_CALLS
                })
            
            # 更新呼入日志（Twilio 媒体流结束）
            transferred_flag = (CALL_STATES.get(stream_call_sid, {}).get("intent") == "transfer") if stream_call_sid else False
            call_log_end(
                stream_call_sid,
                order_finalized=order_finalized,
                transferred=transferred_flag
            )
            await broadcast_admin("call_log_update", safe_call_log())
            await broadcast_admin("ai_status", {"busy": len(ACTIVE_CALLS) >= config.max_concurrent_calls})


async def send_setup_message(
    ws,
    customer_info: dict,
    menu_text: str,
    restaurant_info: str,
    customer_number: str
):
    """
    向 Gemini 发送初始化 Setup 消息，定义 AI 的完整配置。

    此消息必须是与 Gemini 的 WebSocket 连接建立后发送的第一条消息，
    在任何音频或文本交换之前完成初始化。

    Setup 消息包含：
        1. model：使用的 Gemini 模型名称（如 gemini-2.5-flash-...）
        2. generationConfig：
           - responseModalities: ["AUDIO"] — 仅输出音频，减少文本处理延迟
           - speechConfig.voiceConfig：指定 TTS 语音（如 Aoede）
        3. inputAudioTranscription: {} — 启用用户语音实时转录功能
           4. outputAudioTranscription: {} — 启用 AI 语音输出转录（AI 说了什么的文字版本）
        4. systemInstruction：AI 的系统提示词（人设、规则、菜单、客户信息）
        5. tools：注册可供 AI 调用的工具函数列表

    Args:
        ws: Gemini WebSocket 连接对象
        customer_info (dict | None): 客户档案（老客户有历史数据，新客户为 None）
        menu_text (str): 格式化的菜单文本
        restaurant_info (str): 餐厅基本信息文本
        customer_number (str): 来电号码
    """
    # 通过 prompts 模块动态生成 System Prompt
    base_instruction = prompts.get_system_instruction(
        customer_info, menu_text, restaurant_info, customer_number
    )

    setup_payload = {
        "setup": {
            "model": config.model_name,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": config.voice_name
                        }
                    }
                }
            },
            # 启用上下文窗口压缩：原生音频每秒～25 tokens，不压缩 15 分钟就会超限
            # 启用滑动窗口将会话延长至无限
            "contextWindowCompression": {
                "slidingWindow": {},
                "triggerTokens": 25600  # ~17分钟音频后触发压缩
            },
            # 启用会话恢复：10分钟连接重置时能续接上下文
            "sessionResumption": {},
            # 启用用户语音实时转录（STT → inputTranscription 事件）
            "inputAudioTranscription": {},
            # 启用 AI 语音输出转录（AI 说了什么 → outputTranscription 事件）
            "outputAudioTranscription": {},
            "systemInstruction": {
                "parts": [{"text": base_instruction}]
            },
            "tools": [
                tools_address.tool_definition,
                tools_pricing.definition,
                tools_manage_call.tool_definition,
                tools_history.definition
            ]
        }
    }

    payload_json = json.dumps(setup_payload)
    payload_size = len(payload_json)
    instruction_size = len(base_instruction)
    logger.info(
        f"发送 Gemini setup | 模型: {config.model_name} | "
        f"Setup 总大小: {payload_size:,} 字节 | 系统指令大小: {instruction_size:,} 字节"
    )
    await ws.send(payload_json)


# =============================================================================
# Web 通话模拟器（管理面板内的测试功能）
# =============================================================================

@app.websocket("/api/admin/web_call")
async def handle_web_call_stream(websocket: WebSocket, token: str = None):
    """
    Web 通话模拟器 WebSocket 端点 (Token Query 鉴权)。

    功能：
        允许在管理面板中通过浏览器麦克风直接与 AI 对话，
        模拟真实的电话通话场景，无需真实的 Twilio 电话。
        主要用于：
            1. 测试新的 prompts.py 修改是否正确
            2. 测试菜单更改后 AI 的响应
            3. 展示系统功能（演示模式）

    与 /media-stream 的区别：
        - /media-stream：Twilio 发送 mu-law 8kHz，需要转码
        - /api/admin/web_call：浏览器直接发送 PCM 16kHz，无需转码
        - /media-stream：Gemini 输出转为 mu-law 发给 Twilio
        - /api/admin/web_call：Gemini 输出原始 PCM 24kHz 发给浏览器

    协议（前端须遵循）：
        连接后，前端首先发送 start 事件：
            {"event": "start", "customer_number": "08x..."}
        
        之后持续发送音频：
            {"event": "media", "payload": "<Base64 PCM 16kHz>"}
        
        服务端回复音频：
            {"event": "media", "payload": "<Base64 PCM 24kHz>", "sampleRate": 24000}
        
        打断信号：
            {"event": "clear"}
        
        通话结束（AI 主动）：
            {"event": "close"}
        
        用户主动挂断：
            {"event": "stop"}
    """
    if not token or token not in TOKEN_STORE:
        await websocket.close(code=1008)
        return
    
    if time.time() > TOKEN_STORE[token]["expires"]:
        del TOKEN_STORE[token]
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("Web Call Simulator WebSocket 连接已建立")

    stream_call_sid = None  # 在 finally 块中使用，需要在 try 块外初始化
    
    # 并发上限检查（WebRTC 和 Twilio 共享同一个计数器）
    config.reload_settings()
    if len(ACTIVE_CALLS) >= config.max_concurrent_calls:
        logger.info(f"[WebRTC] 连接被拒绝：已达并发上限 ({len(ACTIVE_CALLS)}/{config.max_concurrent_calls})")
        await websocket.close(code=1008, reason="All lines are busy")
        return

    await broadcast_admin("ai_status", {"busy": len(ACTIVE_CALLS) + 1 >= config.max_concurrent_calls})

    try:
        # --- 等待前端发送 start 事件 ---
        init_message = await websocket.receive_text()
        init_data = json.loads(init_message)

        if init_data.get('event') != 'start':
            # 首条消息不是 start，协议错误，关闭连接
            await websocket.close(code=1003, reason="Expected 'start' event")
            return

        # 提取模拟通话的"来电号码"（用于查询客户档案）
        customer_number = init_data.get('customer_number', '').strip()
        if not customer_number:
            customer_number = 'Unknown'

        # 生成唯一的模拟通话 SID（避免与真实 Twilio CallSid 冲突）
        stream_call_sid = f"web_{uuid.uuid4().hex[:8]}"

        # 新通话开始：清空实时订单小票
        await broadcast_admin("live_order_update", {
            "call_sid": stream_call_sid, "items": [], "subtotal": 0.0,
            "total": 0.0, "delivery_fee": 0.0, "payment_method": "", "calculate_total_result": ""
        })

        logger.info(f"Web 模拟通话开始，虚拟号码: {customer_number}")

        # 建立与 Gemini 的 WebSocket 连接
        async with ws_connect(
            config.gemini_ws_uri,
            extra_headers={"Content-Type": "application/json"}
        ) as gemini_ws:



            call_transcript = []  # 记录该通 Web 测试电话的对话记录
            draft_order = {}      # 草稿订单缓存（供 POS 使用）
            order_finalized = False # 标记记录是否已归档

            # 查询客户档案
            customer_info = database.get_customer(customer_number)
            caller_name = (
                customer_info.get('name', 'Web Tester')
                if customer_info else 'Web Tester'
            )

            # 记录活跃通话
            ACTIVE_CALLS[stream_call_sid] = {
                "start_time": time.time(),
                "caller_number": customer_number,
                "caller_name": caller_name
            }
            # 写入呼入日志（WebRTC 通话），立即广播给管理面板
            call_log_add(stream_call_sid, customer_number, "webrtc")
            await broadcast_admin("call_log_update", safe_call_log())
            await broadcast_admin("call_start", {
                "call_sid": stream_call_sid,
                "caller": customer_number,
                "caller_name": caller_name,
                "active_count": len(ACTIVE_CALLS),
                "active_calls": ACTIVE_CALLS
            })

            # 加载菜单和餐厅信息，发送 Setup 消息给 Gemini
            menu_text = database.get_menu_text()
            restaurant_info = database.get_restaurant_info()
            await send_setup_message(
                gemini_ws, customer_info, menu_text,
                restaurant_info, customer_number
            )

            # 发送触发器，使 AI 主动开口打招呼
            await gemini_ws.send(json.dumps({
                "clientContent": {
                    "turns": [{
                        "role": "user",
                        "parts": [{"text": "Call connected. Please greet the customer."}]
                    }],
                    "turnComplete": True
                }
            }))

            # -----------------------------------------------------------------------
            # 内部任务 A：浏览器 → Gemini（接收用户麦克风音频）
            # -----------------------------------------------------------------------
            async def receive_from_browser():
                """
                持续接收浏览器发来的音频数据，直接转发给 Gemini。

                浏览器直接发送 PCM 16kHz 的 Base64 编码数据，
                无需音频格式转换（这与 Twilio 端的 mu-law 转码不同）。

                支持两种事件：
                    - media：音频数据 → 转发给 Gemini
                    - stop：用户主动挂断 → 退出任务
                """
                try:
                    while True:
                        message = await websocket.receive_text()
                        data = json.loads(message)

                        if data.get('event') == 'media':
                            b64_pcm_16k = data.get('payload')
                            if b64_pcm_16k:
                                print(f"📞 [WebSim] Received audio chunk: {len(b64_pcm_16k)} bytes | Preview: {b64_pcm_16k[:30]}...")
                                # 浏览器已经提供了正确格式（PCM 16kHz），直接发给 Gemini
                                await gemini_ws.send(json.dumps({
                                    "realtimeInput": {
                                        "audio": {
                                            "data": b64_pcm_16k,
                                            "mimeType": f"audio/pcm;rate={config.gemini_input_sample_rate}"
                                        }
                                    }
                                }))

                        elif data.get('event') == 'stop':
                            logger.info("Web 浏览器主动挂断模拟电话")
                            return  # 退出任务

                except WebSocketDisconnect:
                    logger.info("Web 浏览器意外断开连接")
                    return
                except Exception as e:
                    logger.error(f"Web 浏览器接收循环异常: {e}")
                    return

            # -----------------------------------------------------------------------
            # 内部任务 B：Gemini → 浏览器（接收 AI 回复音频 + 处理工具调用）
            # -----------------------------------------------------------------------
            async def receive_from_gemini():
                """
                接收 Gemini 的响应，处理音频、转录、打断、工具调用。
                """
                nonlocal draft_order, order_finalized
                current_user_transcript_web = ""  # Web 端用户转录缓冲区
                current_ai_transcript_web = ""    # Web 端 AI 转录缓冲区

                typing_event = None
                typing_task = None
                
                def start_typing_sound():
                    nonlocal typing_event, typing_task
                    if typing_event is None or typing_event.is_set():
                        import audio_injector
                        typing_event = asyncio.Event()
                        typing_task = asyncio.create_task(
                            audio_injector.stream_audio_to_websocket(
                                websocket, "webrtc", typing_event
                            )
                        )

                def stop_typing_sound():
                    nonlocal typing_event
                    if typing_event and not typing_event.is_set():
                        typing_event.set()

                try:
                    async for message in gemini_ws:
                        response = json.loads(message)

                        audio_data_parts = []

                        # 检测 GoAway 信号（Gemini 会话即将超时的预警）
                        if 'goAway' in response:
                            time_left = response['goAway'].get('timeLeft', 'unknown')
                            logger.warning(
                                f"⚠️ [WebRTC] Gemini goAway: 会话将在 {time_left} 后终止"
                            )
                            await broadcast_admin("system_log", {
                                "message": f"⚠️ Gemini 会话即将超时 (剩余: {time_left})，通话可能即将断开",
                                "type": "error"
                            })


                        if 'serverContent' in response:
                            server_content = response['serverContent']

                            if 'modelTurn' in server_content:
                                parts = server_content['modelTurn'].get('parts', [])
                                for part in parts:
                                    if 'inlineData' in part:
                                        audio_data_parts.append(part['inlineData']['data'])
                                        stop_typing_sound()
                                    if 'text' in part:
                                        text_content = part['text']
                                        start_typing_sound()
                                        logger.info(f"Gemini (Web) 文本响应: {text_content}")
                                        await broadcast_admin("transcript", {
                                            "call_sid": stream_call_sid,
                                            "role": "thought",
                                            "text": f"💭 思考过程: {text_content}",
                                            "is_final": True
                                        })

                            # 用户语音实时转录
                            if 'inputTranscription' in server_content:
                                transcription = server_content['inputTranscription']
                                if 'text' in transcription and transcription['text']:
                                    text_chunk = transcription['text']
                                    current_user_transcript_web += text_chunk
                                    stop_typing_sound()
                                    print(f"\033[93m{text_chunk}\033[0m", end="", flush=True)
                                    await broadcast_admin("transcript", {
                                        "call_sid": stream_call_sid,
                                        "role": "user",
                                        "text": text_chunk,
                                        "is_final": False
                                    })

                            # AI 输出转录
                            if 'outputTranscription' in server_content:
                                text_chunk = server_content['outputTranscription'].get('text', '')
                                text_chunk = re.sub(r'<ctrl\d+>', '', text_chunk)  # filter Gemini internal tokens
                                if text_chunk:
                                    current_ai_transcript_web += text_chunk
                                    print(f"\033[96m{text_chunk}\033[0m", end="", flush=True)
                                    await broadcast_admin("transcript", {
                                        "call_sid": stream_call_sid,
                                        "role": "ai",
                                        "text": text_chunk,
                                        "is_final": False
                                    })

                            # 打断处理（Web 端：发送 clear 事件给浏览器）
                            if server_content.get('interrupted'):
                                word_count = len(current_user_transcript_web.strip().split())
                                stop_typing_sound()
                                if word_count > 1:
                                    logger.info("⚠️ 有效打断 (Web) → 发送清空指令给浏览器")
                                    await websocket.send_json({"event": "clear"})
                                current_user_transcript_web = ""

                            # 回合结束
                            if 'turnComplete' in server_content and server_content['turnComplete']:
                                print("")
                                if current_user_transcript_web:
                                    call_transcript.append({
                                        "role": "user", 
                                        "text": current_user_transcript_web, 
                                        "timestamp": time.time()
                                    })
                                    await broadcast_admin("transcript", {
                                        "call_sid": stream_call_sid,
                                        "role": "user",
                                        "text": current_user_transcript_web,
                                        "is_final": True
                                    })
                                    current_user_transcript_web = ""
                                
                                if current_ai_transcript_web:
                                    call_transcript.append({
                                        "role": "ai", 
                                        "text": current_ai_transcript_web, 
                                        "timestamp": time.time()
                                    })
                                    await broadcast_admin("transcript", {
                                        "call_sid": stream_call_sid,
                                        "role": "ai",
                                        "text": current_ai_transcript_web,
                                        "is_final": True
                                    })
                                    current_ai_transcript_web = ""

                        # ======= 发送音频给 Web=======
                        if audio_data_parts:
                            for audio_b64 in audio_data_parts:
                                await websocket.send_json({
                                    "event": "media",
                                    "payload": audio_b64,
                                    "sampleRate": 24000  # 告知浏览器采样率
                                })

                        # 工具调用处理
                        if 'toolCall' in response:
                            tool_call = response['toolCall']
                            function_calls = tool_call.get('functionCalls', [])
                            
                            start_typing_sound()
                            logger.info(f"Gemini (Web) 请求工具调用: {function_calls}")
                            await broadcast_admin("tool_call", {
                                "call_sid": stream_call_sid,
                                "calls": function_calls
                            })

                            function_responses = []

                            # === 方案C Part B: 工具调用期间保活心跳 ===
                            # 每3秒向浏览器发一次ping，防止静默期被判定为断线
                            _ws_keepalive_stop = asyncio.Event()
                            async def _ws_keepalive_fn():
                                while not _ws_keepalive_stop.is_set():
                                    try:
                                        await asyncio.wait_for(_ws_keepalive_stop.wait(), timeout=3.0)
                                    except asyncio.TimeoutError:
                                        try:
                                            await websocket.send_json({"event": "ping"})
                                        except Exception:
                                            _ws_keepalive_stop.set()
                                            break
                            _ws_keepalive_task = asyncio.create_task(_ws_keepalive_fn())


                            for call in function_calls:
                                call_id = call['id']
                                name = call['name']
                                args = call.get('args', {})

                                result = None
                                try:
                                    # Web 模拟器支持的工具集（与 Twilio 保持同步）
                                    if name == 'search_address':
                                        query = args.get('address_query')
                                        result = await tools_address.search_address(query)
                                    elif name == 'calculate_total':
                                        result = tools_pricing.calculate_total(
                                            args.get('items', []),
                                            args.get('delivery_fee', 0.0),
                                            args.get('payment_method', 'cash')
                                        )
                                        
                                        # 同步缓存并在管理面板更新直播单小票
                                        draft_order = {
                                            "call_sid": stream_call_sid,
                                            "items": args.get('items', []),
                                            "delivery_fee": result.get('delivery_fee', args.get('delivery_fee', 0.0)),
                                            "payment_method": args.get('payment_method', 'unknown'),
                                            "calculate_total_result": result.get('result', ''),
                                            "subtotal": result.get('subtotal', 0.0),
                                            "total": result.get('total', 0.0)
                                        }
                                        await broadcast_admin("live_order_update", draft_order)
                                        result = result.get('result', "Total calculated.") # WebSim expects result inner dict
                                    elif name == 'get_past_order':
                                        o_id = args.get('order_id')
                                        result_dict = tools_history.get_past_order(o_id)
                                        result = result_dict.get('result', "No history found.")
                                    elif name == 'get_business_hours':
                                        result = prompts.get_business_hours() if hasattr(prompts, 'get_business_hours') else {"error": "Not implemented"}
                                    elif name == 'get_restaurant_status':
                                        result = prompts.get_restaurant_status() if hasattr(prompts, 'get_restaurant_status') else {"error": "Not implemented"}
                                    elif name == 'check_delivery_availability':
                                        addr = args.get('address', '')
                                        result = {"delivery_fee": database.get_delivery_fee(addr)}
                                    elif name == 'end_call':
                                        # [防重复] guard: Gemini 有时会重复发 end_call，只处理第一次
                                        if order_finalized:
                                            result = {"status": "success", "note": "Order already saved. Say only Goodbye."}
                                            logger.warning("⚠️ 检测到重复 end_call，已忽略：避免重复归档")
                                            continue  # 跳过重复 end_call 处理
                                        else:
                                            order_finalized = True
                                        # 保存模拟订单（标记来源为 "AI (WebSim)"）
                                        # 保存模拟订单（标记来源为 "AI (WebSim)"）
                                        items = args.get('items', [])
                                        total = args.get('total_value', args.get('total_amount', 0))
                                        s_type = args.get('service_type', 'Pickup')
                                        order_note = args.get('note', args.get('special_instructions', ''))
                                        contact_phone = args.get('contact_phone', customer_number)

                                        try:
                                            order_id = f"AID{int(time.time() * 100)}"
                                            order_record = {
                                                "order_id": order_id,
                                                "business_date_str": get_business_date_str(),
                                                "timestamp": time.ctime(),
                                                "customer_phone": customer_number,
                                                "contact_phone": contact_phone,
                                                "customer_name": args.get(
                                                    'customer_name',
                                                    customer_info.get('name') if customer_info else "Unknown"
                                                ),
                                                "service_type": s_type,
                                                "address": args.get(
                                                    'customer_address',
                                                    customer_info.get('address') if customer_info else "Pickup"
                                                ),
                                                "delivery_area": args.get('delivery_area', 'Unknown'),
                                                "items": items,
                                                "total_value": total,
                                                "payment_method": args.get('payment_method', 'Unknown'),
                                                "note": order_note,
                                                "source": "AI (WebSim)",  # 标记为 Web 模拟器订单
                                                "transcript": json.dumps(call_transcript)
                                            }

                                            # 锁防并发写入损坏
                                            async with _db_write_lock:
                                                database.save_order(order_record)
                                                summary = f"{order_id}: {len(items)} items (€{total})"
                                                database.update_customer_history(
                                                    customer_number, summary,
                                                    name=args.get('customer_name'),
                                                    address=args.get('customer_address')
                                                )
                                            logger.info(f"✅ Web模拟订单归档: {order_id}")

                                            # 更新管理面板的今日订单计数
                                            _completed, _incomplete = get_order_counts()
                                            await broadcast_admin("new_order", {
                                                "total_orders": _completed,
                                                "incomplete_orders": _incomplete,
                                                "order_id": order_id
                                            })

                                            # [BUG FIX] save_order 成功后必须设置 result，
                                            # 否则会触发下方 "if result is None" 分支，
                                            # 错误地向 Gemini 返回 "Function not implemented"
                                            result = {"status": "success", "order_id": order_id, "note": "Order saved. Now say ONLY a brief Goodbye - do NOT repeat the total or delivery time."}

                                        except Exception as e:
                                            logger.error(f"Web模拟订单归档失败: {e}")
                                            result = {"status": "error", "message": str(e)}

                                    # 转接人工：立即通知浏览器关闭连接
                                    elif name == 'transfer_call':
                                        logger.info(f"AI 主动请求结束模拟通话: {name}")
                                        await websocket.send_json({"event": "close"})
                                        await gemini_ws.close()
                                        return  # 退出任务 B

                                    if result is None:
                                        result = {"error": "Function not implemented or failed"}

                                except Exception as e:
                                    logger.error(f"工具 {name} 执行失败: {e}")
                                    result = {"error": str(e)}

                                # 修复 Bug: 如果 result 已经是字典（如 {"result": "..."}, {"error": "..."}），直接解包使用
                                # 否则，对于旧设计的回退包裹为 {"result": result}
                                if isinstance(result, dict):
                                    _response_payload = {**result}
                                else:
                                    _response_payload = {"result": result}

                                # 对于 NON_BLOCKING 工具，加入 scheduling: INTERRUPT 让 AI 立即剥报结果
                                _scheduling = "INTERRUPT" if name in ("search_address", "get_past_order") else None
                                if _scheduling:
                                    _response_payload["scheduling"] = _scheduling
                                    
                                function_responses.append({
                                    "id": call_id,
                                    "name": name,
                                    "response": _response_payload
                                })

                            # 将工具结果发回给 Gemini
                            # 停止保活任务
                            _ws_keepalive_stop.set()
                            await asyncio.gather(_ws_keepalive_task, return_exceptions=True)

                            if function_responses:
                                stop_typing_sound()
                                start_typing_sound()
                                await gemini_ws.send(json.dumps({
                                    "toolResponse": {
                                        "functionResponses": function_responses
                                    }
                                }))

                                # 广播工具响应到管理面板（可视化调试）
                                await broadcast_admin("tool_response", {
                                    "call_sid": stream_call_sid,
                                    "responses": function_responses
                                })

                except ConnectionClosed:
                    logger.info("Gemini (Web) WebSocket 断开（Gemini 端关闭会话）")
                    try:
                        await websocket.send_json({
                            "event": "gemini_disconnect",
                            "message": "AI session disconnected unexpectedly. Please call again."
                        })
                    except Exception:
                        pass  # 浏览器也已断开，忽略
                except Exception as e:
                    import traceback
                    logger.error(f"Gemini (Web) 接收任务异常: {e}\n{traceback.format_exc()}")

            # 启动双向并发任务
            task_a = asyncio.create_task(receive_from_browser())
            task_b = asyncio.create_task(receive_from_gemini())

            # Fix B: Gemini WS 保活心跳 — 每10秒向 Gemini API 发 ping 防止超时

            # 等待任意一个任务完成，然后取消另一个
            done, pending = await asyncio.wait(
                [task_a, task_b],
                return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()

    except Exception as e:
        logger.error(f"Web 模拟通话全局异常: {e}")
    finally:
        # ★ WebRTC 草稿订单救援：若模拟通话中途丢失连接，同样挽救订单
        if not order_finalized and stream_call_sid:
            try:
                rescue_id = f"AID-INCOMPLETE-{int(time.time())}"
                rescue_record = {
                    "order_id": rescue_id,
                    "business_date_str": get_business_date_str(),
                    "timestamp": time.ctime(),
                    "customer_phone": customer_number,
                    "contact_phone": None,
                    "customer_name": customer_info.get('name', 'Web Tester') if customer_info else 'Web Tester',
                    "address": customer_info.get('address', 'Unknown') if customer_info else 'Unknown',
                    "delivery_area": "Unknown",
                    "items": draft_order.get('items', []) if draft_order else [],
                    "total_value": draft_order.get('total', 0.0) if draft_order else 0.0,
                    "payment_method": draft_order.get('payment_method', 'Unknown') if draft_order else 'Unknown',
                    "delivery_fee": draft_order.get('delivery_fee', 0.0) if draft_order else 0.0,
                    "note": f"⚠️ 模拟通话断开。报价详情: {draft_order.get('calculate_total_result', '无报价') if draft_order else '无报价'}",
                    "service_type": "Dropped",
                    "source": "AI-Incomplete",
                    "transcript": json.dumps(call_transcript)
                }
                async with _db_write_lock:
                    database.save_order(rescue_record)
                logger.warning(f"⚠️ WebSim草稿订单已救援保存: {rescue_id}")
                _completed, _incomplete = get_order_counts()
                await broadcast_admin("new_order", {
                    "total_orders": _completed,
                    "incomplete_orders": _incomplete,
                    "order_id": rescue_id,
                    "warning": "Web模拟通话意外断开，系统已挽救未完成订单。"
                })
            except Exception as e:
                logger.error(f"WebSim草稿订单救援失败: {e}")

        # 清理活跃通话记录并广播
        if stream_call_sid and stream_call_sid in ACTIVE_CALLS:
            del ACTIVE_CALLS[stream_call_sid]
            await broadcast_admin("call_end", {
                "call_sid": stream_call_sid,
                "active_count": len(ACTIVE_CALLS),
                "active_calls": ACTIVE_CALLS
            })
        logger.info(f"Web 模拟通话已清理，SID: {stream_call_sid}")

        # 更新呼入日志 + 广播
        call_log_end(
            stream_call_sid,
            order_finalized=order_finalized,
            transferred=(CALL_STATES.get(stream_call_sid, {}).get("intent") == "transfer") if stream_call_sid else False
        )
        await broadcast_admin("call_log_update", safe_call_log())
        await broadcast_admin("ai_status", {"busy": len(ACTIVE_CALLS) >= config.max_concurrent_calls})


# =============================================================================
# 前端 SPA 路由（生产环境 Catch-all）
# =============================================================================

@app.get("/{full_path:path}")
async def serve_frontend(request: Request, full_path: str):
    """
    前端单页应用（SPA）的 Catch-all 路由。

    工作原理：
        FastAPI 路由匹配遵循"先定义先匹配"原则。
        所有已定义的 /api/* 和 /assets/* 路由会优先匹配。
        只有在没有任何路由匹配时，才会到达此 Catch-all 路由。

    文件服务逻辑（两步）：
        1. 先检查请求路径是否对应 dist/ 目录下的真实文件
           （处理 logo.png、vite.svg、favicon 等根目录静态资源）
           如果是真实文件，直接返回该文件（FileResponse）
        2. 如果不是真实文件，返回 index.html
           让前端 JavaScript Router 处理 SPA 页面路由

    重要：
        如果没有步骤1，根目录的静态文件（logo.png 等）会被错误地
        返回 index.html（HTML 内容），导致图片/图标无法显示。

    Args:
        request (Request): FastAPI 请求对象（此处未使用）
        full_path (str): 匹配的路径字符串（所有非 API 路径）

    Returns:
        FileResponse: 真实文件 或 index.html（SPA fallback）
        JSONResponse (404): 若 dist/ 目录不存在，提示需要构建前端
    """
    if os.path.isdir(frontend_dist_path):
        # 步骤1：优先检查请求路径是否对应 dist/ 中的真实文件
        # 这处理了 logo.png、vite.svg、favicon.ico 等根目录静态资源
        requested_file = os.path.join(frontend_dist_path, full_path)
        if full_path and os.path.isfile(requested_file):
            return FileResponse(requested_file)

        # 步骤1.5：防止缓存投毒。如果是向 assets/ 请求旧的文件（JS/CSS），
        # 且文件已不存在，直接返回 404，不要 fallback 到 index.html。
        if full_path.startswith("assets/"):
            return JSONResponse(status_code=404, content={"message": "Asset not found."})

        # 步骤2：不是真实文件，返回 index.html（SPA 路由 fallback）
        index_path = os.path.join(frontend_dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)

    return JSONResponse(
        status_code=404,
        content={
            "message": (
                "Frontend not built or not found. "
                "Please run 'npm run build' inside the 'frontend' directory."
            )
        }
    )


# =============================================================================
# 服务启动入口
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    print("AI 智能点餐服务启动中...")
    print(f"   服务地址: http://{config.host}:{config.port}")
    print(f"   请务必运行 ngrok http {config.port} 获取公网地址并填入 Twilio 后台")
    print("   确保已创建 .env 文件并设置好所有必需的环境变量")

    try:
        # uvicorn 是 FastAPI 推荐的 ASGI 服务器
        # host="0.0.0.0" 允许从局域网访问，便于测试
        uvicorn.run(app, host=config.host, port=config.port)
    except KeyboardInterrupt:
        print("\n\n服务已停止（用户中断，Ctrl+C）")
    except Exception as e:
        print(f"\n服务异常退出: {e}")
