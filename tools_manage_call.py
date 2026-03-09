"""
tools_manage_call.py — 通话生命周期管理工具

功能说明：
    为 Gemini AI 定义两个核心的通话控制函数：
        1. end_call   — 完成订单后正常挂断，同时提交完整的订单数据
        2. transfer_call — 遇到复杂情况或客户要求时，将通话转接给人工

工作机制：
    AI 调用这两个工具时，server.py 中的 receive_from_gemini() 会捕获 toolCall 事件，
    解析工具名称和参数后：
        - end_call     → 触发订单归档逻辑，等待告别语播完后关闭 WebSocket
        - transfer_call → 在 CALL_STATES 中标记转接意图，关闭 WebSocket，
                          由 /stream-ended 路由读取状态并生成转接 TwiML

注册方式：
    在 server.py 的 send_setup_message() 中，
    将 tool_definition 字典传入 Gemini setup 的 tools 列表。
"""


# =============================================================================
# Gemini 工具定义 (JSON Schema)
#
# 每个 function_declaration 描述：
#   - 函数名称 (name)：server.py 中 call['name'] 判断的依据
#   - 调用说明 (description)：AI 理解何时应该触发此函数
#   - 参数规范 (parameters)：AI 填写时必须遵守的字段类型和约束
# =============================================================================
tool_definition = {
    "function_declarations": [

        # -----------------------------------------------------------------------
        # 工具 1：end_call —— 结束通话
        # 触发场景：
        #   a) 订单完成，客户说了再见
        #   b) 匿名来电者拒绝提供姓名或电话
        # 重要规则：
        #   - 对于已完成的订单，AI 必须传入完整的订单信息（items、total_value 等）
        #   - AI 应先说"Thank you, goodbye!"等告别语，等客户回应后再调用此工具
        #   - server.py 会等待告别语音频播放完毕，再实际挂断连接
        # -----------------------------------------------------------------------
        {
            "name": "end_call",
            "description": (
                "End the call. Use this when the order is complete OR anonymous caller refused. "
                "FOR COMPLETED ORDERS, YOU MUST PROVIDE ORDER DETAILS."
            ),
            "parameters": {
                "type": "object",
                "properties": {

                    # 挂断原因，用于日志记录和业务判断
                    # 示例值："Order Complete"、"Anonymous Caller"、"Customer Hung Up"
                    "reason": {
                        "type": "string",
                        "description": "Reason (e.g., 'Order Complete', 'Anonymous Caller')"
                    },

                    # 订购的菜品列表，每个元素包含：
                    #   - name (string)：菜品名称，必须与菜单严格匹配
                    #   - quantity (int)：数量
                    #   - options (list of string)：已选择的选项（如尺寸、辣度）
                    #   - note (string，可选)：该菜品的特殊备注
                    "items": {
                        "type": "array",
                        "description": (
                            "List of ordered items. Each object MUST contain "
                            "'name', 'quantity', 'options', and optionally 'note' "
                            "for special requests."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "options": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "note": {"type": "string"}
                            },
                            "required": ["name", "quantity"]
                        }
                    },

                    # 最终总价（欧元），由 calculate_total 工具计算后填入
                    "total_value": {
                        "type": "number",
                        "description": "Final total price in Euro."
                    },

                    # 配送费（欧元），若无配送费或为自取，则填 0
                    "delivery_fee": {
                        "type": "number",
                        "description": "Delivery fee in Euro (0 for Pickup or if no fee)."
                    },

                    # 服务类型：外卖配送 (Delivery) 或 到店自取 (Pickup)
                    "service_type": {
                        "type": "string",
                        "enum": ["Delivery", "Pickup"],
                        "description": "Type of service."
                    },

                    # 支付方式：现金 (Cash) 或 刷卡 (Card)
                    # 注意：刷卡会有 €0.50 附加费，由 calculate_total 自动计算
                    "payment_method": {
                        "type": "string",
                        "enum": ["Cash", "Card"],
                        "description": "Chosen payment method."
                    },

                    # 客户姓名：自取订单必填，用于出单时呼叫取餐
                    "customer_name": {
                        "type": "string",
                        "description": "Customer name (Required for Pickup)."
                    },

                    # 配送地址：外卖订单必填，需经过 search_address 验证后的完整地址
                    "customer_address": {
                        "type": "string",
                        "description": "Delivery address (Required for Delivery)."
                    },

                    # 配送区域名称：用于订单记录和统计
                    # 示例："Drogheda"、"Drogheda Rural"、"Shop Pickup"
                    "delivery_area": {
                        "type": "string",
                        "description": "Delivery Area name (e.g. 'Drogheda') or 'Shop Pickup'."
                    },

                    # 联系电话：若客户来电号码不方便联系，可提供另一个
                    # 格式要求：爱尔兰本地格式，以 "08x" 开头
                    "contact_phone": {
                        "type": "string",
                        "description": (
                            "Contact phone number if different from caller ID. "
                            "Format: 08x..."
                        )
                    },

                    # 订单级别的特殊备注：如"7点送达"、"不要葱"、"多放辣"
                    # 注意：此字段用于通用备注，不用于记录菜单选项
                    "order_note": {
                        "type": "string",
                        "description": (
                            "General notes for the order (e.g. 'Deliver at 7pm', "
                            "'No peppers', 'Extra onions'). NOT for standard menu options."
                        )
                    }
                },
                # reason 是唯一必填项，其余字段在订单完成场景下强烈建议填写
                "required": ["reason"]
            }
        },

        # -----------------------------------------------------------------------
        # 工具 2：transfer_call —— 转接人工
        # 触发场景：
        #   - 客户明确要求人工（"Can I speak to a manager?"）
        #   - 客户持续愤怒、投诉
        #   - 请求超出 AI 能力范围（如询问不相关问题）
        #   - 通话线路严重不清晰，AI 无法理解客户意图
        # 工作原理：
        #   server.py 收到此调用后，在 CALL_STATES 中记录 intent="transfer"，
        #   关闭 WebSocket 后，Twilio 会执行 /stream-ended 路由，
        #   该路由读取状态并生成 <Dial> TwiML 实现实际转接
        # -----------------------------------------------------------------------
        {
            "name": "transfer_call",
            "description": (
                "Transfer the call to a human manager. Use this if the user is confused, "
                "angry, asks for a human, or if the request is outside your capability."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    # 转接原因，用于日志记录，便于事后分析哪类情况最常触发转接
                    # 示例："Customer Request"、"Complaint"、"Bad Line/Unintelligible"
                    "reason": {
                        "type": "string",
                        "description": (
                            "Reason for transfer "
                            "(e.g., 'Customer Request', 'Complex Query')"
                        )
                    }
                },
                "required": ["reason"]
            }
        }
    ]
}
