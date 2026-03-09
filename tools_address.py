"""
tools_address.py — 爱尔兰地址验证工具

功能说明：
    为 Gemini AI 提供爱尔兰地址搜索和验证工具。
    当 AI 收到客户提供的配送地址时，会调用 search_address() 函数，
    通过 AutoAddress API（爱尔兰国家级地址数据库服务）验证地址的合法性，
    并过滤出餐厅配送范围（仅限 Co. Louth 和 Co. Meath）内的有效地址，
    同时附带对应的配送费信息。

AutoAddress API 说明：
    - 服务地址：https://api.autoaddress.com/3.0/autocomplete
    - 需要 AUTOADDRESS_API_KEY（在 .env 或 settings.json 中配置）
    - 支持按地址字符串模糊搜索，也支持直接输入 Eircode（爱尔兰邮编）

搜索策略：
    1. 若客户输入含 "Louth" 或 "Meath" → 直接按原文搜索
    2. 若客户输入含 Eircode（如 "A91 X123"）→ 直接搜索
    3. 否则 → 并行搜索 "地址 + Co. Louth" 和 "地址 + Co. Meath"，
              合并结果，去重后过滤出配送范围内的条目
"""

import httpx       # 异步 HTTP 客户端，用于调用 AutoAddress API
import logging
import asyncio     # 用于并发执行两个县的地址搜索任务
import re          # 正则表达式，用于检测 Eircode 格式
import database    # 数据库模块，用于查询匹配地址的配送费

logger = logging.getLogger("AI-Waiter")

# 从配置管理模块读取 API Key
from config import config
AUTOADDRESS_API_KEY = config.autoaddress_api_key

# AutoAddress API 端点地址（固定值）
AUTOADDRESS_URL = "https://api.autoaddress.com/3.0/autocomplete"


# =============================================================================
# Gemini 工具定义 (JSON Schema)
#
# 此定义告知 Gemini AI：当客户提供配送地址时，
# 应调用 search_address 函数来验证地址合法性。
# =============================================================================
tool_definition = {
    "function_declarations": [
        {
            "name": "search_address",
            # 触发说明：
            #   - 客户提供了一个地址字符串
            #   - 客户提供了 Eircode（爱尔兰邮编，如 "A91 X123"）
            #   - 需要验证该地址是否在配送范围内
            "description": (
                "Search for a valid address in Ireland using the AutoAddress API. "
                "Use this when the user provides an address, an Eircode, "
                "or asks to check if an address is valid."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address_query": {
                        "type": "string",
                        # AI 应将客户口述的完整地址文本传入此参数
                        "description": (
                            "The address string or query provided by the user "
                            "(e.g., '123 Main St, Dublin' or 'A91 X123')."
                        )
                    }
                },
                "required": ["address_query"]
            }
        }
    ]
}


# =============================================================================
# 辅助函数：向 AutoAddress API 发送单次请求
# =============================================================================
async def _fetch_candidates(client: httpx.AsyncClient, query: str) -> list:
    """
    向 AutoAddress API 发送地址搜索请求，返回原始候选地址列表。

    此函数是内部辅助函数（以下划线开头命名约定），
    不直接暴露给外部调用，由主函数 search_address() 调用。

    Args:
        client (httpx.AsyncClient): 共享的异步 HTTP 客户端实例
                                    （在主函数中统一创建，减少连接开销）
        query (str): 要搜索的地址字符串（可能已附加了县名）

    Returns:
        list: AutoAddress 返回的地址候选项列表，每项为一个字典，
              包含 "value"（地址字符串）等字段；
              请求失败时返回空列表。
    """
    params = {
        "key": AUTOADDRESS_API_KEY,  # API 认证密钥
        "address": query,            # 要搜索的地址
        "language": "en",            # 返回英文地址
        "limit": 10,                 # 最多返回 10 条候选，后续会进一步过滤
        "country": "IE"              # 限定搜索国家为爱尔兰
    }
    # 设置 User-Agent 标识请求来源，防止被 API 服务端误判为爬虫
    headers = {"User-Agent": "Python AI Waiter Application"}

    try:
        # 设置 5 秒超时，防止网络故障导致通话卡顿
        response = await client.get(AUTOADDRESS_URL, params=params, headers=headers, timeout=5.0)
        if response.status_code == 200:
            # AutoAddress 返回的数据结构：{"options": [...], ...}
            return response.json().get("options", [])
    except Exception as e:
        logger.error(f"对查询 '{query}' 的 API 请求失败: {e}")

    return []  # 任何异常都静默处理，返回空列表，让上层决策


async def _fetch_full_eircode(client: httpx.AsyncClient, opt: dict) -> str:
    """
    如果选项中包含 lookup 链接，请求该链接以提取完整的 Eircode，
    并将其追加到地址字符串末尾。
    """
    address_str = opt.get("value", "")
    link = opt.get("link", {})
    if link.get("rel") == "lookup":
        href = link.get("href")
        if href:
            try:
                headers = {"User-Agent": "Python AI Waiter Application"}
                res = await client.get(href, headers=headers, timeout=5.0)
                if res.status_code == 200:
                    data = res.json()
                    postcode = data.get("address", {}).get("postcode", {}).get("value", "")
                    if postcode:
                        return f"{address_str} [Eircode: {postcode}]"
            except Exception as e:
                logger.error(f"Eircode 查询失败: {e}")
    return address_str

# =============================================================================
# 主工具函数：地址搜索与验证
# =============================================================================
async def search_address(address_query: str) -> dict:
    """
    搜索爱尔兰地址并验证其是否在餐厅的配送范围内。

    详细工作流程：
        步骤1. 分析查询文本，决定搜索策略：
               - 含 "louth"/"meath" → 直接搜索（已明确郡名）
               - 含 Eircode 格式   → 直接搜索（精确邮编）
               - 其他              → 并行搜索两个郡（提高召回率）

        步骤2. 汇总所有候选地址，去除重复项。

        步骤3. 过滤：只保留含 "louth" 或 "meath" 的地址
               （确保不配送到 Louth/Meath 之外的地区）。

        步骤4. 为每个有效地址查询对应的配送费。

        步骤5. 格式化并返回最多 5 个候选，供 AI 读给客户确认。

    Args:
        address_query (str): 客户口述的地址或 Eircode，
                             由 Gemini AI 从对话中提取并传入

    Returns:
        dict: 成功时 {"result": "Found N matches in delivery area: <地址列表>"}
              超出配送区域 {"result": "Address found but it is OUTSIDE our delivery area..."}
              无结果时 {"result": "No address matches found. Please ask..."}
              异常时 {"error": "<错误信息>"}

    注意：
        返回值最外层包含 "result" 键，符合 Gemini Tool Response 格式要求。
        AI 收到结果后会直接读给客户，因此结果字符串应具有可读性。
    """
    logger.info(f"工具执行: search_address(query='{address_query}')")

    # 配送区域限制：仅限 Co. Louth 和 Co. Meath
    valid_counties = ["louth", "meath"]
    query_lower = address_query.lower()

    # --- 步骤1：决定搜索策略 ---

    # 检查查询文本中是否已包含目标郡名
    # 例如："123 Main Street, Drogheda, Co. Louth" 已含 "louth"
    has_specified_county = any(c in query_lower for c in valid_counties)

    # 检测 Eircode 格式：3个字母数字 + 可选空格 + 4个字母数字
    # 例如：A91 X123、D01 F5P2、A91X123
    eircode_match = re.search(r'\b([A-Za-z0-9]{3})\s?([A-Za-z0-9]{4})\b', address_query)
    
    # 如果找到了 Eircode，则无视后面的各种杂乱文本，强制只搜 Eircode 确保高命中率
    clean_query = address_query
    if eircode_match:
        clean_query = f"{eircode_match.group(1)} {eircode_match.group(2)}"
        logger.info(f"✨ 成功拦截到 Eircode: {clean_query}，将忽略上下文杂音")

    all_options = []  # 汇总所有候选地址

    try:
        # 使用 async with 确保 HTTP 连接在使用后正确关闭
        async with httpx.AsyncClient() as client:

            if has_specified_county or eircode_match:
                # 策略 A：已知郡名或 Eircode → 直接精确搜索，减少 API 调用次数
                logger.info("检测到目标郡或 Eircode，正在直接搜索...")
                all_options = await _fetch_candidates(client, clean_query)
            else:
                # 策略 B：未指定郡 → 并发搜索两个目标郡，用 asyncio.gather 同时执行
                # 这比串行搜索快约 2 倍，减少客户等待时间
                logger.info("未指定郡/Eircode，正在同时搜索 Louth 和 Meath...")
                tasks = [
                    _fetch_candidates(client, f"{clean_query}, Co. Louth"),
                    _fetch_candidates(client, f"{clean_query}, Co. Meath")
                ]
                # gather() 并发运行所有任务，等待全部完成后返回结果列表
                results = await asyncio.gather(*tasks)
                for res in results:
                    all_options.extend(res)  # 将两次搜索结果合并到一个列表

        # --- 处理无结果的情况 ---
        if not all_options:
            return {
                "result": (
                    "No address matches found. "
                    "Please ask the user to clarify or provide an Eircode."
                )
            }

        # --- 步骤2-4：过滤、去重与 Eircode 补全 ---
        filtered_opts = []
        seen_addresses = set()  # 用集合去重，防止并行搜索返回重复地址

        for opt in all_options:
            address_str = opt["value"]  # AutoAddress 返回的标准化地址字符串

            # 去重判断：若此地址已处理过，跳过
            if address_str in seen_addresses:
                continue

            # 过滤判断：地址必须包含 "louth" 或 "meath"
            # 这确保我们只向配送范围内的客户报价
            if any(county in address_str.lower() for county in valid_counties):
                seen_addresses.add(address_str)
                filtered_opts.append(opt)

        # 截取前五个最佳选项，减轻后续并发查询 Eircode 的网络负担与 AI 阅读负担
        filtered_opts = filtered_opts[:5]

        # --- 处理过滤后无结果的情况（地址存在但超出配送范围）---
        if not filtered_opts:
            return {
                "result": (
                    "Address found but it is OUTSIDE our delivery area "
                    "(Co. Louth & Co. Meath only)."
                )
            }

        # 并发请求获取每个有效地址的完整 Eircode
        async with httpx.AsyncClient() as client:
            tasks = [_fetch_full_eircode(client, opt) for opt in filtered_opts]
            resolved_addresses = await asyncio.gather(*tasks)

        # 拼接配送费
        filtered_suggestions = []
        for address_str in resolved_addresses:
            fee = database.get_delivery_fee(address_str)
            formatted = f"{address_str} (Delivery Fee: €{fee:.2f})"
            filtered_suggestions.append(formatted)

        # 格式化最终返回值，AI 会以此内容向客户确认地址
        return {
            "result": (
                f"Found {len(filtered_suggestions)} matches in delivery area: "
                + "; ".join(filtered_suggestions)
            )
        }

    except Exception as e:
        # 捕获所有未预期的异常（如网络超时、API 格式变更等）
        logger.error(f"search_address 异常: {e}")
        return {"error": str(e)}
