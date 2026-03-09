"""
config.py — 应用程序配置管理模块

功能说明：
    本模块负责集中管理系统的所有配置参数。
    设计目标是将配置分为两类，分别从不同来源读取：

    1. 静态机密配置（来自 .env 文件）：
       - API 密钥等敏感信息，不应提交到代码库
       - 使用 python-dotenv 从 .env 文件读取

    2. 动态业务配置（来自 settings.json）：
       - 可通过管理面板实时修改，无需重启服务
       - 支持热重载（reload_settings() 方法）
       - 包括：AI 开关状态、模型选择、折扣设置、电话路由等

配置优先级（从高到低）：
    settings.json → .env 环境变量 → 代码中的默认值

使用方式：
    在任何模块中：
        from config import config
        api_key = config.google_api_key
        config.reload_settings()  # 热重载动态配置

注意：
    模块末尾会创建一个全局单例 config 对象，
    所有模块共享同一个实例，确保配置状态一致。
"""

from dataclasses import dataclass, field
import os
import json
from typing import Optional, Dict, Any
from dotenv import load_dotenv  # 从 .env 文件加载环境变量
import logging

logger = logging.getLogger("AI-Waiter")

# 在模块加载时立即读取 .env 文件（如果存在）
# 将其中的 KEY=VALUE 设置到系统环境变量中，供 os.getenv() 读取
load_dotenv()


@dataclass
class AppConfig:
    """
    应用程序配置数据类。

    使用 Python dataclass 定义，每个字段都有默认值，
    确保即使某些配置缺失，系统也能以合理的默认值运行。

    字段分为三组：
        1. 静态机密配置：从 .env 读取，不支持热重载
        2. 动态业务配置：从 settings.json 读取，支持热重载
        3. 固定底层配置：代码中硬编码，通常不需要修改
    """

    # ==================== 静态机密配置（来自 .env 或 settings.json）====================

    # Google AI Studio / Vertex AI 的 API 密钥
    # 用于连接 Gemini Live API WebSocket
    # 获取方式：https://aistudio.google.com/apikey
    google_api_key: str = ""

    # AutoAddress.ie API 密钥
    # 用于爱尔兰地址搜索和验证服务
    # 获取方式：https://www.autoaddress.com/docs/api
    autoaddress_api_key: str = ""

    # Twilio 的安全鉴权 Token，用于验证 Webhook 来源的真实性以及发送 REST API 请求
    twilio_auth_token: str = ""

    # Twilio 账户 SID，用于发送 REST API 请求（例如手动转接排队用户）
    twilio_account_sid: str = ""

    # React 后台管理面板和 API 的管理员密码
    admin_password: str = "115673"


    # ==================== 动态业务配置（来自 settings.json，支持热重载）====================

    # --- 电话路由配置 ---

    # 转接人工时拨打的电话号码（爱尔兰格式，含国家码）
    # 在以下情况下使用：
    #   - AI 请求 transfer_call 工具
    #   - master_switch 设置为 "bypass"
    #   - 并发数超限且 overflow_action 为 "transfer"
    transfer_phone_number: str = "+353419816853"

    # --- AI 运行模式配置 ---

    # AI 点餐员总开关，控制来电的处理方式：
    #   "active"  — 正常运行，AI 接听并处理所有来电（默认）
    #   "bypass"  — 旁路模式，所有来电直接转接人工（播放 bypass_message 后转）
    #   "offline" — 离线模式，播放 offline_message 后挂断（或直接拒接）
    master_switch: str = "active"

    # 最大并发通话数（超出时触发溢出处理）
    # 建议根据实际业务量和 API选配设置，默认 10
    max_concurrent_calls: int = 10

    # Wait Queue (防死锁并发排队)的自定义配置
    wait_message: str = "All lines are currently busy, please hold on."
    wait_music_url: str = "" # 空则默认播放 Twilio 的 Classical 音乐

    # 并发超限时的处理策略：
    #   "transfer" — 将排队来电转接给人工（推荐）
    #   "reject"   — 播放繁忙提示后直接挂断
    call_overflow_action: str = "transfer"

    # Gemini 模型名称（通过 Google AI Studio 查看可用模型）
    # 目前使用支持实时语音的 native audio 模型
    model_name: str = "models/gemini-2.5-flash-native-audio-preview-12-2025"

    # AI 语音名称（Gemini 内置 TTS 语音）
    # 可选值参考 Google AI 文档：Aoede、Charon、Fenrir、Kore、Puck 等
    # "Aoede" 为爱尔兰口音友好的女声，适合餐厅场景
    voice_name: str = "Aoede"

    # AI 回复的随机性/创意性控制（0.0 = 最保守稳定，1.0 = 最随机）
    # 餐厅接单场景建议使用较低值（0.2~0.5），确保准确性优先
    temperature: float = 0.4

    # 离线模式下播放的语音消息（Twilio Polly TTS）
    # 留空时直接拒接来电（不播放任何内容）
    offline_message: str = "Sorry, Noodle Box Drogheda is closed today. Thank you for calling."

    # 旁路模式下转接前播放的提示语
    bypass_message: str = "Please hold on, transferring you to a staff member."

    # --- 业务计费配置 ---

    # 最低配送金额（欧元）：订单总额（含配送费前）低于此值时，AI 会提示客户加点
    minimum_delivery_order: float = 10.0

    # 刷卡附加费（欧元）：客户选择刷卡支付时叠加的手续费
    card_payment_surcharge: float = 0.50

    # 折扣开关：True = 启用折扣，AI 会主动宣传并在计算总价时应用
    discount_active: bool = False

    # 折扣描述（AI 宣传时使用的文本）
    # 示例："10% off all orders this weekend!"
    discount_description: str = ""

    # 折扣类型：
    #   "percentage" — 百分比折扣，discount_value 为小数（0.10 = 10%）
    #   "fixed"      — 固定金额折扣，discount_value 为欧元金额（5.0 = €5 off）
    discount_type: str = "percentage"

    # 折扣值：具体数值取决于 discount_type
    #   - percentage 类型：0.10 表示 10% 折扣
    #   - fixed 类型：5.0 表示 €5 折扣
    discount_value: float = 0.0


    # ==================== 固定底层配置（通常不需要修改）====================

    # Twilio 媒体流采样率：8kHz（Twilio 固定规格，不可更改）
    # 音频格式：mu-law 编码，8000 Hz
    twilio_sample_rate: int = 8000

    # Gemini 音频输入采样率：16kHz（Gemini 要求的最低质量）
    # 接收 Twilio 的 8kHz 音频后，需要上采样到 16kHz 再发送
    gemini_input_sample_rate: int = 16000

    # Gemini 音频输出采样率：24kHz（Gemini 生成的 TTS 音频规格）
    # 发送给 Twilio 前需要下采样到 8kHz
    gemini_output_sample_rate: int = 24000

    # FastAPI 服务监听地址（"0.0.0.0" 表示监听所有网络接口）
    host: str = "0.0.0.0"

    # FastAPI 服务监听端口（与 ngrok 转发端口保持一致）
    port: int = 5000

    # 告别语音频缓冲时间（秒）：
    # AI 说完 "Thank you, goodbye" 后，等待此时长再挂断，
    # 确保最后的音频包完全发送到客户端
    goodbye_audio_buffer_seconds: float = 1.5

    # 最小挂断延迟（秒）：
    # 即使没有剩余音频，也等待此时长再关闭连接，
    # 防止因网络延迟导致客户听不到最后几个字就挂断
    minimum_hangup_delay_seconds: float = 1.0

    # --- 数据文件路径配置 ---
    # 所有文件路径均相对于 server.py 所在目录

    menu_file: str = "menu.json"                                  # 菜单数据
    customers_file: str = "customers.json"                        # 客户档案
    orders_file: str = "orders.json"                              # 历史订单
    delivery_areas_file: str = "Delivery Area.txt"                # 配送区域费用表
    restaurant_info_file: str = "Restaurant Basic Information.txt"  # 餐厅基本信息
    settings_file: str = "settings.json"                          # 动态配置文件


    # ==================== 计算属性 ====================

    @property
    def gemini_ws_uri(self) -> str:
        """
        动态生成 Gemini Live API 的 WebSocket 连接 URI。

        URI 格式：
            wss://generativelanguage.googleapis.com/ws/
            google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent
            ?key=<GOOGLE_API_KEY>

        每次访问此属性时都会重新生成（因为 google_api_key 可能在热重载后变化）。

        Returns:
            str: 完整的 wss:// URI 字符串，可直接用于 websockets.connect()
        """
        host = "generativelanguage.googleapis.com"
        return (
            f"wss://{host}/ws/google.ai.generativelanguage.v1beta"
            f".GenerativeService.BidiGenerateContent?key={self.google_api_key}"
        )


    # ==================== 方法 ====================

    def reload_settings(self):
        """
        从 settings.json 热重载动态业务配置，并覆盖当前内存中的值。

        此方法在以下场景被调用：
            1. 每次电话呼入时（/incoming-call 路由）
            2. 前端保存设置后（POST /api/admin/settings 路由）
            3. tools_pricing.py 的 calculate_total() 中（确保折扣实时生效）
            4. prompts.py 的 get_system_instruction() 中（确保折扣感知最新）

        settings.json 文件结构（示例）：
            {
              "api_keys": {
                "google_api_key": "...",
                "autoaddress_api_key": "..."
              },
              "phone_routing": {
                "transfer_phone_number": "+353..."
              },
              "ai_settings": {
                "master_switch": "active",
                "max_concurrent_calls": 10,
                "model_name": "models/gemini-2.5-flash-...",
                "voice_name": "Aoede",
                "temperature": 0.4,
                "offline_message": "...",
                "bypass_message": "..."
              },
              "pricing_rules": {
                "minimum_delivery_order": 10.0,
                "card_payment_surcharge": 0.50,
                "discount_active": false,
                "discount_description": "",
                "discount_type": "percentage",
                "discount_value": 0.0
              }
            }

        注意：
            - settings.json 中的 API Key 会覆盖 .env 中的值（若非空）
            - 若 settings.json 不存在，保持现有配置不变（仅记录警告日志）
            - 任何解析错误都会被捕获，不会导致服务崩溃
        """
        try:
            data = {}
            if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
                # 生产环境：从 Cloud SQL 读取配置
                try:
                    from database import get_app_setting
                    raw = get_app_setting("settings_json")
                    if raw:
                        data = json.loads(raw)
                        logger.info("✅ 动态配置重载成功 (从 Cloud SQL 读取)")
                    else:
                        logger.warning("⚠️ Cloud SQL app_settings 中无 settings_json，将使用系统默认值")
                except Exception as db_err:
                    logger.error(f"❌ 从 Cloud SQL 读取配置失败: {db_err}，尝试回退到文件")
            
            if not data and os.path.exists(self.settings_file):
                # 本地开发（或 Cloud SQL 读取失败）：从文件读取
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info("✅ 动态配置重载成功 (从本地文件读取)")

            if data:
                    # --- 从 settings.json 更新安全与 API 密钥（若非空则覆盖 .env 的值）---
                    keys = data.get('api_keys', {})
                    if keys.get('google_api_key'):
                        self.google_api_key = keys['google_api_key']
                    if keys.get('autoaddress_api_key'):
                        self.autoaddress_api_key = keys['autoaddress_api_key']
                    
                    # 允许动态修改管理员密码，存储在 security_settings 中
                    security = data.get('security_settings', {})
                    if security.get('admin_password'):
                        self.admin_password = security['admin_password']

                    # --- 电话路由配置 ---
                    phone = data.get('phone_routing', {})
                    if phone.get('transfer_phone_number'):
                        self.transfer_phone_number = phone['transfer_phone_number']

                    # --- AI 运行设置 ---
                    ai = data.get('ai_settings', {})
                    self.master_switch = ai.get('master_switch', self.master_switch)
                    self.max_concurrent_calls = int(ai.get('max_concurrent_calls', self.max_concurrent_calls))
                    self.call_overflow_action = ai.get('call_overflow_action', self.call_overflow_action)
                    self.model_name = ai.get('model_name', self.model_name)
                    self.voice_name = ai.get('voice_name', self.voice_name)
                    self.temperature = ai.get('temperature', self.temperature)
                    self.offline_message = ai.get('offline_message', self.offline_message)
                    self.bypass_message = ai.get('bypass_message', self.bypass_message)

                    # --- 业务计费规则 ---
                    pricing = data.get('pricing_rules', {})
                    self.minimum_delivery_order = pricing.get('minimum_delivery_order', self.minimum_delivery_order)
                    self.card_payment_surcharge = pricing.get('card_payment_surcharge', self.card_payment_surcharge)
                    self.discount_active = pricing.get('discount_active', self.discount_active)
                    self.discount_description = pricing.get('discount_description', self.discount_description)
                    self.discount_type = pricing.get('discount_type', self.discount_type)
                    self.discount_value = pricing.get('discount_value', self.discount_value)
            else:
                logger.warning(f"⚠️ 无配置数据，将使用系统默认值")


        except Exception as e:
            logger.error(f"❌ 加载 settings.json 失败: {e}")

    @classmethod
    def initialize(cls) -> 'AppConfig':
        """
        工厂方法：创建并初始化 AppConfig 实例。

        初始化顺序（重要）：
            1. 创建带有默认值的 dataclass 实例
            2. 从 .env 环境变量读取机密配置（覆盖默认值）
            3. 从 settings.json 读取动态配置（可再次覆盖 .env 的值）

        Returns:
            AppConfig: 完整初始化的配置实例

        使用示例：
            config = AppConfig.initialize()
        """
        instance = cls()  # 创建实例（所有字段为默认值）

        # --- 步骤 1：从 .env 环境变量读取机密配置 ---
        env_google_key = os.getenv("GOOGLE_API_KEY")
        if env_google_key:
            instance.google_api_key = env_google_key

        env_autoaddress_key = os.getenv("AUTOADDRESS_API_KEY")
        if env_autoaddress_key:
            instance.autoaddress_api_key = env_autoaddress_key

        env_twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        if env_twilio_token:
            instance.twilio_auth_token = env_twilio_token

        env_admin_pwd = os.getenv("ADMIN_PASSWORD")
        if env_admin_pwd:
            instance.admin_password = env_admin_pwd

        env_transfer_phone = os.getenv("TRANSFER_PHONE_NUMBER")
        if env_transfer_phone:
            instance.transfer_phone_number = env_transfer_phone

        # --- 步骤 2：从 settings.json 读取动态配置（可覆盖上述值）---
        instance.reload_settings()
        return instance

    def validate(self) -> bool:
        """
        验证核心配置是否完整，缺少关键配置时返回 False。

        目前检查项：
            - google_api_key 不能为空（连接 Gemini API 的必要条件）

        Returns:
            bool: True = 配置有效，可以启动服务
                  False = 配置不完整，服务无法正常运行
        """
        if not self.google_api_key:
            logger.error("❌ GOOGLE_API_KEY 未设置 (请在 .env 或 settings.json 中配置)")
            return False
        return True


# =============================================================================
# 全局单例配置对象
#
# 所有模块通过 "from config import config" 使用同一个实例，
# 确保配置状态在整个应用中保持一致。
#
# 启动时若配置验证失败（如缺少 API Key），程序会抛出异常并终止，
# 防止以不完整的状态运行。
# =============================================================================
try:
    config = AppConfig.initialize()
    if not config.validate():
        raise ValueError("核心配置验证失败：请检查 GOOGLE_API_KEY 是否已设置")
except Exception as e:
    logger.error(f"❌ 配置初始化失败: {e}")
    raise  # 重新抛出，让调用者（uvicorn 启动脚本）感知到错误

# 声明此模块的公开导出接口
__all__ = ['config', 'AppConfig']
