"""
tools_history.py — 历史订单查询工具

功能说明：
    为 Gemini AI 提供查询历史订单的函数定义（Tool Definition）和实际执行逻辑。
    
使用场景：
    当客户说"老样子"、"上次一样"或指定某个订单编号时，
    AI 会自动调用 get_past_order() 工具，取回历史订单详情，
    再读给客户确认，避免重复询问每个菜品。

注册方式：
    在 server.py 的 send_setup_message() 函数中，
    将 definition 字典传入 Gemini setup 的 tools 列表，
    使 AI 知晓此工具的存在和调用方式。
"""

import database  # 数据库操作模块，负责从 orders.json 中检索订单
import logging

# 使用统一的 Logger，日志前缀为 "AI-Waiter"，与其他模块保持一致
logger = logging.getLogger("AI-Waiter")


# =============================================================================
# Gemini 工具定义 (JSON Schema)
#
# 这是一个符合 Gemini Function Calling 规范的字典。
# Gemini 通过解读此 Schema，了解：
#   - 函数名称 (name)
#   - 何时调用 (description)
#   - 需要传入什么参数 (parameters)
#
# 重要：函数声明必须在通话开始时，通过 setup 消息注册给 Gemini，
#       否则 AI 不知道此工具存在，无法调用。
# =============================================================================
definition = {
    "function_declarations": [
        {
            "name": "get_past_order",
            "behavior": "NON_BLOCKING",
            "description": (
                "Retrieve details of a past order using its Order ID. "
                "**Invocation Condition:** Call this ONLY when the customer says "
                "'same as last time', 'repeat my last order', or references a specific order ID. "
                "Extract the order_id from the Order History section in your context. "
                "Say 'Give me a moment to pull that up...' before calling."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": (
                            "The unique ID of the order (e.g., 'ORD-1766856461-2866'). "
                            "Extract this from the Order History in context or from the customer."
                        )
                    }
                },
                "required": ["order_id"]
            }
        }
    ]
}


def get_past_order(order_id: str) -> dict:
    """
    根据订单 ID 检索历史订单的完整详情。

    工作流程：
        1. 接收 Gemini AI 传入的 order_id 字符串
        2. 调用 database.get_order_details() 在 orders.json 中查找匹配记录
        3. 找到则返回完整订单字典；未找到则返回包含错误说明的字典

    Args:
        order_id (str): 订单唯一 ID，格式通常为 "ORD-<时间戳>-<随机码>"
                        例如："ORD-1766856461-2866"

    Returns:
        dict: 成功时返回 {"result": <订单详情字典>}
              失败时返回 {"result": "Order <id> not found."}

    注意：
        返回值最外层必须包含 "result" 键，这是 Gemini Tool Response 协议要求的格式。
        Gemini 会将此 result 的内容作为工具执行结果，注入到 AI 的下一轮对话上下文中。
    """
    logger.info(f"正在检索历史订单，订单 ID: {order_id}")

    try:
        # 委托给 database 层执行实际的文件读取和查找操作
        order_details = database.get_order_details(order_id)

        if order_details:
            # 找到订单，返回完整的订单数据字典
            # AI 收到后会逐项读给客户确认（例如："一份辣鸡外卖，共 €18.50"）
            return {"result": order_details}
        else:
            # 未找到时返回描述性错误文本，AI 会据此告知客户找不到该订单
            return {"result": f"Order {order_id} not found."}
    except Exception as e:
        logger.error(f"Error retrieving past order: {e}")
        return {"result": f"Error looking up order {order_id}. Please ask the customer for details directly."}
