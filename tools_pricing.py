"""
tools_pricing.py — 订单价格计算工具

功能说明：
    为 Gemini AI 提供精确的订单总价计算功能。
    AI 在向客户确认订单之前，必须调用此工具计算出最终总价，
    并将结果读给客户（包括明细、配送费、折扣、刷卡附加费等）。

计算逻辑（按顺序叠加）：
    1. 逐项计算菜品基础价格 + 选项价格修正
    2. 应用动态折扣（如果后台启用）：百分比折扣或固定金额折扣
    3. 叠加配送费（自取为 0）
    4. 叠加刷卡附加费（如果支付方式为 Card）
    5. 检查最低配送金额限制

动态配置：
    折扣、刷卡附加费、最低配送金额均从 config 中读取，
    支持通过管理面板实时热更新，无需重启服务。
"""

import database  # 用于查找菜单项和计算配送费
import logging
from config import config  # 用于读取动态业务规则（折扣、附加费等）

logger = logging.getLogger("AI-Waiter")


# =============================================================================
# Gemini 工具定义 (JSON Schema)
#
# 描述 calculate_total 函数的参数规范，
# 使 Gemini AI 知道应该传入哪些数据来计算订单总价。
# =============================================================================
definition = {
    "function_declarations": [
        {
            "name": "calculate_total",
            # 触发时机：AI 整理完所有菜品和选项、确认服务类型和支付方式后调用
            # 规则：必须在读单确认（readback）之前调用，以获得准确的总价
            "description": (
                "Calculate the final order total including delivery fees, "
                "option costs, and payment surcharges. "
                "**Invocation Condition:** Call this EXACTLY ONCE, only after "
                "the customer has finished ordering ALL items AND stated their "
                "service type (Delivery/Pickup) AND payment method. "
                "Never call mid-order or more than once."
            ),
            "parameters": {
                "type": "object",
                "properties": {

                    # 订购菜品列表
                    # 修改为简单的字符串列表，防止原生语音大模型在生成深层嵌套 JSON 时触发 Google 后端 1011 崩溃
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": (
                            "List of items ordered with options and quantities. "
                            "Format each string as: '[Quantity]x [Item Name] (with [Options])'. "
                            "Example: '2x Large Munchie Box (with Fried Rice, Extra Hot)', '1x Can of Coke'"
                        )
                    },

                    # 配送费（欧元）
                    # 自取订单传入 0，配送订单传入 search_address 返回的配送费金额
                    "delivery_fee": {
                        "type": "number",
                        "description": "Delivery fee amount in Euro (e.g. 3.0, 5.0). Use 0 for pickup."
                    },

                    # 支付方式：影响是否叠加刷卡附加费
                    "payment_method": {
                        "type": "string",
                        "description": "Payment method: 'cash' or 'card'.",
                        "enum": ["cash", "card"]
                    }
                },
                # 这三个参数都是必填的，AI 必须全部传入
                "required": ["items", "delivery_fee", "payment_method"]
            }
        }
    ]
}


def _calculate_total_impl(items: list, delivery_fee: float, payment_method: str) -> dict:
    """
    计算订单的完整价格明细，返回格式化的收据文本。

    计算步骤：
        1. 遍历 items，每个菜品：
           a. 在菜单数据库中查找基础价格
           b. 遍历客户已选的 options，查找对应的价格修正值（price_mod）
           c. 计算该菜品的行总计 = (基础价 + 选项修正) × 数量
        2. 汇总所有菜品的行总计得到 subtotal（小计）
        3. 若折扣激活且折扣值 > 0，计算折扣金额并扣除
        4. 若 delivery_fee > 0，加入配送费
        5. 若支付方式为 "card"，加入刷卡附加费
        6. 检查最低配送金额限制，在收据中显示警告或确认

    Args:
        items (list): 菜品列表，来自 Gemini AI 的工具调用参数
        delivery_fee (float): 配送费金额（欧元），自取为 0.0
        payment_method (str): 支付方式，"cash" 或 "card"（不区分大小写）

    Returns:
        dict: {"result": "<格式化的收据文本字符串>"}
              收据文本包含每行明细、小计、折扣、配送费、
              刷卡附加费、最终总价（或最低金额警告）

    注意：
        - 此函数每次调用都会执行 config.reload_settings()，
          确保折扣、附加费等动态配置始终是最新值
        - 折扣百分比配置格式：0.10 = 10%（十进制小数，不是百分制整数）
        - 如果菜品名称在菜单中找不到，会在收据中显示警告行，但不终止计算
    """
    # 每次调用前重新加载配置，以应用管理面板最新的热更新
    # 这确保折扣开关、刷卡附加费等变更立即生效，无需重启
    config.reload_settings()

    logger.info(f"正在计算 {len(items)} 个项目的总价，支付方式: {payment_method}")

    total_price = 0.0  # 累计总价（欧元）
    receipt_lines = ["--- ORDER SUMMARY ---"]  # 收据文本行列表

    # -----------------------------------------------------------------------
    # 步骤 1：逐一计算每个菜品的价格
    # -----------------------------------------------------------------------
    import re
    
    for item_raw in items:
        # 如果 AI 还是传了原本的字典结构，说明它没有听从新 Schema，回退兼容
        if isinstance(item_raw, dict):
            name = item_raw.get('name', 'Unknown')
            qty = item_raw.get('quantity', 1)
            opts = item_raw.get('options', [])
        else:
            item_str = str(item_raw)
            # 匹配数量 (可选的 Nx 或 N x 前缀)
            qty_match = re.search(r'^(\d+)\s*x\s+', item_str, re.IGNORECASE)
            qty = int(qty_match.group(1)) if qty_match else 1
            
            # 移除数量前缀
            name_with_opts = item_str[qty_match.end():] if qty_match else item_str
            
            # 匹配选项 (括号内的内容，支持 with 或 without)
            opts = []
            opt_match = re.search(r'\((?:with\s+)?(.*?)\)', name_with_opts, re.IGNORECASE)
            if opt_match:
                # 提取括号里的内容，按逗号分割
                opts_str = opt_match.group(1)
                opts = [o.strip() for o in opts_str.split(',') if o.strip()]
                # 从名字中移除括号及其内容
                name = name_with_opts[:opt_match.start()].strip()
            else:
                name = name_with_opts.strip()

        # 在菜单数据库中查找此菜品（支持模糊匹配）
        db_item = database.find_item(name)
        if not db_item:
            # 菜品未找到：在收据中记录警告，假设价格为 €0.00，继续处理其他菜品
            receipt_lines.append(f"⚠️ Unknown Item: {name} (Assumed €0.00)")
            continue

        base_price = db_item.get('price', 0.0)  # 菜品基础价格（欧元）
        item_total = base_price                  # 当前菜品单价（会加上选项修正）

        # --- 计算选项价格修正 ---
        option_details = []  # 记录有价格修正的选项，用于收据展示
        enriched_options = [] # 记录包含单价修正的选项详细字典给前后端使用
        if opts and 'options' in db_item:
            available_opts = []
            for menu_opt_cat in db_item['options']:
                for val in menu_opt_cat['values']:
                    available_opts.append(val['name'])
            logger.info(f"  [{name}] 可用选项: {available_opts}")
            
            for user_opt in opts:  # 遍历客户选择的每个选项名称
                found_mod = False
                user_opt_lower = user_opt.lower()
                logger.info(f"  [{name}] 尝试匹配选项: '{user_opt}'")

                # 第一步：尝试精确匹配 (Exact Match)
                for menu_opt_cat in db_item['options']:
                    for val in menu_opt_cat['values']:
                        if user_opt_lower == val['name'].lower():
                            mod = val.get('price_mod', 0.0)
                            logger.info(f"  [{name}] 精确匹配成功: '{val['name']}' price_mod={mod}")
                            if mod != 0:
                                item_total += mod
                                sign = '+' if mod > 0 else ''
                                option_details.append(f"{user_opt} ({sign}€{mod:.2f})")
                            enriched_options.append({'name': val['name'], 'price_adjustment': mod})
                            found_mod = True
                            break
                    if found_mod: break

                # 第二步：如果精确匹配失败，尝试模糊匹配 (Substring Match)
                if not found_mod:
                    for menu_opt_cat in db_item['options']:
                        for val in menu_opt_cat['values']:
                            if user_opt_lower in val['name'].lower():
                                mod = val.get('price_mod', 0.0)
                                logger.info(f"  [{name}] 模糊匹配成功: '{val['name']}' price_mod={mod}")
                                if mod != 0:
                                    item_total += mod
                                    sign = '+' if mod > 0 else ''
                                    option_details.append(f"{user_opt} ({sign}€{mod:.2f})")
                                enriched_options.append({'name': val['name'], 'price_adjustment': mod})
                                found_mod = True
                                break
                        if found_mod: break

                # 若找不到选项，也当做 0 欧元存下来，让小票能显示
                if not found_mod:
                    logger.warning(f"  [{name}] ⚠️ 选项未找到: '{user_opt}' (不会影响总价但选项名称会显示在小票上)")
                    enriched_options.append({'name': user_opt, 'price_adjustment': 0.0})

        # 计算该菜品的行总计
        order_item['unit_price'] = item_total
        order_item['options'] = enriched_options
        line_total = item_total * qty
        total_price += line_total

        # 格式化收据行：例如 "2x 辣鸡翅 @ €8.50 +Extra Hot (+€1.00) = €19.00"
        opts_str = f" +{', '.join(option_details)}" if option_details else ""
        receipt_lines.append(
            f"{qty}x {db_item['name']} @ €{item_total:.2f}{opts_str} = €{line_total:.2f}"
        )

    receipt_lines.append("---------------------")
    receipt_lines.append(f"Subtotal: €{total_price:.2f}")
    subtotal = total_price

    # -----------------------------------------------------------------------
    # 步骤 2：应用动态折扣（如果后台已启用）
    # -----------------------------------------------------------------------
    if config.discount_active and config.discount_value > 0 and total_price > 0:
        discount_amount = 0.0

        if config.discount_type == 'percentage':
            # 百分比折扣：discount_value 为小数格式，0.10 表示 10% 折扣
            # 注意：如果管理员配置的是 10（而非 0.10），需要在设置界面说明
            discount_amount = total_price * float(config.discount_value)
            receipt_lines.append(
                f"Discount ({float(config.discount_value) * 100}% off): -€{discount_amount:.2f}"
            )
        elif config.discount_type == 'fixed':
            # 固定金额折扣：discount_value 为直接的欧元金额，如 5.0 表示减 €5
            # 使用 min() 防止折扣超过实际小计（不允许负值订单）
            discount_amount = min(total_price, float(config.discount_value))
            receipt_lines.append(
                f"Discount (-€{float(config.discount_value):.2f}): -€{discount_amount:.2f}"
            )

        total_price -= discount_amount
        receipt_lines.append(f"Subtotal after Discount: €{total_price:.2f}")

    # -----------------------------------------------------------------------
    # 步骤 3：叠加配送费
    # -----------------------------------------------------------------------
    if delivery_fee > 0:
        receipt_lines.append(f"Delivery Charge: €{delivery_fee:.2f}")
        total_price += delivery_fee

    # -----------------------------------------------------------------------
    # 步骤 4：叠加刷卡附加费（从动态配置读取，默认 €0.50）
    # -----------------------------------------------------------------------
    if payment_method.lower() == "card" and config.card_payment_surcharge > 0:
        surcharge = float(config.card_payment_surcharge)
        total_price += surcharge
        receipt_lines.append(f"Card Fee: €{surcharge:.2f}")

    receipt_lines.append("---------------------")

    # -----------------------------------------------------------------------
    # 步骤 5：检查最低配送金额（仅适用于配送订单，自取无限制）
    # -----------------------------------------------------------------------
    min_order = float(config.minimum_delivery_order)
    if total_price < min_order and delivery_fee > 0:
        # 未达到最低配送金额：显示警告，AI 会据此告知客户需要加点菜
        receipt_lines.append(f"⚠️ TOTAL: €{total_price:.2f}")
        receipt_lines.append(f"❌ WARNING: Minimum delivery order is €{min_order:.2f}")
    else:
        # 金额合规：显示最终总价确认
        receipt_lines.append(f"✅ FINAL TOTAL: €{total_price:.2f}")
        
    receipt_lines.append(f"Payment Method: {payment_method.capitalize()}")
    if payment_method.lower() == 'card':
        receipt_lines.append("Note: Card surcharge €0.50 (included in total)")

    # 将所有行合并为单个字符串返回
    # AI 会将此字符串中的关键数字（总价）读给客户
    logger.info(f"价格计算完成: subtotal={subtotal:.2f}, delivery_fee={delivery_fee:.2f}, total={total_price:.2f}")
    return {
        "result": "\n".join(receipt_lines),
        "total": total_price,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee
    }

def calculate_total(items: list, delivery_fee: float, payment_method: str) -> dict:
    try:
        return _calculate_total_impl(items, delivery_fee, payment_method)
    except Exception as e:
        logger.error(f"Error calculating total: {e}")
        return {"result": f"Error calculating total. Please inform the customer there is a system error calculating the price."}
