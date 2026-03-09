"""
database.py — 数据持久化层

功能说明：
    本模块负责所有本系统数据库的读写操作。
    已从纯 JSON 文件迁移到 SQLite 关系型数据库结构（生产环境使用 Cloud SQL for PostgreSQL）。
    
缓存策略：
    load_menu() 和 load_delivery_areas() 继续使用 @lru_cache(maxsize=1) 缓存结果，
    避免每次通话都重复读取数据库/磁盘。

连接策略：
    - 本地开发（无 CLOUD_SQL_CONNECTION_NAME 环境变量）：SQLite (app.db)
    - 云端生产（有 CLOUD_SQL_CONNECTION_NAME）：Cloud SQL for PostgreSQL (Unix Socket)
    - 使用懒初始化（Lazy Init）确保 Cloud SQL Proxy Sidecar 在首次连接前已就绪
"""

import os
import logging
from functools import lru_cache
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import init_db, Order, Customer, MenuCategory, MenuItem, MenuOption, AppSetting
from config import config

logger = logging.getLogger("AI-Waiter")

# =============================================================================
# Database Session Management — 懒初始化（Lazy Init）
# =============================================================================
# ⚠️ 关键架构决策：不在模块导入时连接数据库
# 原因：Cloud Run 的 Cloud SQL Auth Proxy 是 Sidecar 容器，启动比主容器慢。
#       如果在模块 import 时就建立连接，会因 Unix Socket 还未被 Sidecar 创建而崩溃。
# 解决方案：第一次实际需要数据库时才建立连接（懒初始化）。
_engine = None
_SessionLocal = None

def _get_session_factory():
    """获取 SessionFactory（首次调用时才真正连接数据库）"""
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine, _SessionLocal = init_db()
    return _SessionLocal

def get_db_session():
    """获取一个新的数据库 Session（Context Manager）"""
    return _get_session_factory()()


# =============================================================================
# App Settings 键值操作 — 持久化配置存 Cloud SQL 而不是本地文件
# =============================================================================

def get_app_setting(key: str) -> Optional[str]:
    """
    从 app_settings 表读取配置值。
    Cloud Run 生产环境才会调用（由 config.py 在 CLOUD_SQL_CONNECTION_NAME 存在时触发）。
    返回 None 表示 key 不存在。
    """
    try:
        with get_db_session() as db:
            row = db.query(AppSetting).filter_by(key=key).first()
            return row.value if row else None
    except Exception as e:
        logger.error(f"读取 app_setting[{key}] 失败: {e}")
        return None


def save_app_setting(key: str, value: str) -> bool:
    """
    将配置值写入 app_settings 表（upsert）。
    返回 True 表示成功。
    """
    try:
        with get_db_session() as db:
            row = db.query(AppSetting).filter_by(key=key).first()
            if row:
                row.value = value
            else:
                db.add(AppSetting(key=key, value=value))
            db.commit()
        return True
    except Exception as e:
        logger.error(f"写入 app_setting[{key}] 失败: {e}")
        return False


# =============================================================================
# 菜单相关操作 (Menu) - 现在从 SQLite 读取并转换成之前需要的嵌套字典格式
# =============================================================================

@lru_cache(maxsize=1)
def load_menu() -> Dict:
    """
    从 SQLite 加载菜单数据，并将结果转换成兼容之前 JSON 结构的字典并缓存。
    """
    menu_dict = {}
    try:
        with get_db_session() as db:
            categories = db.query(MenuCategory).order_by(MenuCategory.display_order).all()
            if not categories:
                logger.warning("No menu categories found in the database. Menu might empty if migration hasn't run.")
                return {}
            
            for category in categories:
                # 兼容原有原格式，需要按原有逻辑转换数据
                # "Category": [{"name": ..., "price": ..., "options": [...]}]
                cat_items = []
                for item in category.items:
                    item_data = {
                        "name": item.name,
                        "price": item.price,
                    }
                    if item.description:
                        item_data["description"] = item.description
                    if item.allergens:
                        item_data["allergens"] = item.allergens
                        
                    # 组装 options
                    if item.options:
                        # 对于兼容性，我们将所有 option 放进一个叫做 "CUSTOMIZE" 的逻辑大类里
                        # 过去的结构: {"name": "SIZE", "values": [{"name": "Large", "price_mod": 1.0}]}
                        # 现在的结构比较平，可以在此组装还原
                        options_grouped = {}
                        for opt in item.options:
                            # 假设名字包含了组别（比如 "MEAT: Chicken"）或者如果没有就塞进 Options
                            group_name = "OPTIONS"
                            opt_name = opt.name
                            if ":" in opt.name:
                                group_name, opt_name = opt.name.split(":", 1)
                                group_name = group_name.strip()
                                opt_name = opt_name.strip()
                                
                            if group_name not in options_grouped:
                                options_grouped[group_name] = []
                            
                            val_dict = {"name": opt_name, "price_mod": opt.price_change}
                            if opt.is_default:
                                val_dict["default"] = True
                            options_grouped[group_name].append(val_dict)
                        
                        # 重建成数组的形态
                        item_options = []
                        for g_name, vals in options_grouped.items():
                            item_options.append({
                                "name": g_name,
                                "values": vals
                            })
                        item_data["options"] = item_options
                        
                    # CRITICAL BUG FIX: This must be inside the loop
                    cat_items.append(item_data)
                
                menu_dict[category.name] = cat_items
                
        return menu_dict
    except Exception as e:
        logger.error(f"加载菜单时出错: {e}")
        return {}


def get_menu_text() -> str:
    """
    将菜单字典格式化为 AI 可读的多行文本字符串。
    逻辑基本保持不变。
    """
    menu = load_menu()
    text = "Menu:\n"

    for category, items in menu.items():
        text += f"  [{category}]:\n"
        if isinstance(items, list):
            for item in items:
                price = item.get('price', 0)
                desc = f" ({item['description']})" if 'description' in item else ""
                allergens = f" [Allergens: {item['allergens']}]" if 'allergens' in item else ""

                text += f"    - {item['name']}: €{price}{desc}{allergens}\n"

                if item.get('options'):
                    for opt in item['options']:
                        values_str = []
                        for v in opt['values']:
                            v_name = v['name']
                            if v.get('price_mod', 0) != 0:
                                sign = "+" if v['price_mod'] > 0 else "-"
                                v_name += f" ({sign}€{abs(v['price_mod'])})"
                            if v.get('default'):
                                v_name += "*"
                            values_str.append(v_name)

                        text += f"      * {opt['name']}: {', '.join(values_str)}\n"

    return text


# =============================================================================
# 客户档案相关操作 (Customer)
# =============================================================================

def get_customer(phone_number: str) -> Optional[Dict]:
    """
    从 SQLite 检索客户档案。
    """
    try:
        with get_db_session() as db:
            customer = db.query(Customer).filter_by(phone_number=phone_number).first()
            if customer:
                # 获取最新的 5 个订单作为 order_history
                recent_orders = db.query(Order).filter_by(customer_phone=phone_number).order_by(Order.created_at.desc()).limit(5).all()
                history = [f"{o.id}: €{o.total_value:.2f}" for o in reversed(recent_orders)]
                
                return {
                    "name": customer.name or "Unknown",
                    "address": customer.address or "Unknown",
                    "order_history": history
                }
    except Exception as e:
        logger.error(f"加载客户信息时出错: {e}")
    return None


def save_customer(phone_number: str, data: Dict) -> None:
    """
    保存或更新客户档案到 SQLite。
    注意：在新的流程中，更建议使用 update_customer_history 来直接更新。
    这里保留为了兼容性。
    """
    try:
        with get_db_session() as db:
            customer = db.query(Customer).filter_by(phone_number=phone_number).first()
            if not customer:
                customer = Customer(phone_number=phone_number)
                db.add(customer)
            
            if data.get("name") and data["name"] != "Unknown":
                customer.name = data["name"]
            if data.get("address") and data["address"] not in ("Unknown", "Pickup"):
                customer.address = data["address"]
                
            db.commit()
    except Exception as e:
        logger.error(f"保存客户信息时出错: {e}")


# =============================================================================
# 配送区域及餐厅静态信息操作 (保持读取 Txt，因非高频并发读写点)
# =============================================================================

DELIVERY_FILE = config.delivery_areas_file
RESTAURANT_INFO_FILE = config.restaurant_info_file

@lru_cache(maxsize=1)
def load_delivery_areas() -> Dict[str, float]:
    """
    加载配送区域及费率。
    生产环境（Cloud SQL）：优先从 app_settings 表读取。
    本地开发：从 delivery_areas.txt 文件读取（向下兼容）。
    """
    areas = {}
    raw_text = None

    # 生产环境：从 Cloud SQL 读取
    if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
        raw_text = get_app_setting("delivery_areas")

    # 本地开发（或 Cloud SQL 里还没有数据）：从文件读取
    if raw_text is None and os.path.exists(DELIVERY_FILE):
        try:
            with open(DELIVERY_FILE, 'r', encoding='utf-8') as f:
                raw_text = f.read()
        except Exception as e:
            logger.error(f"读取 delivery_areas.txt 失败: {e}")

    if not raw_text:
        return areas

    try:
        for line in raw_text.splitlines():
            if "€" in line and "..." in line:
                parts = line.split("€")
                price = float(parts[1].strip())
                name_part = parts[0].strip().rstrip(" .")
                areas[name_part.lower()] = price
    except Exception as e:
        logger.error(f"解析配送区域时出错: {e}")
    return areas

def get_restaurant_info() -> str:
    """保持从 Txt 读取。"""
    try:
        if os.path.exists(RESTAURANT_INFO_FILE):
            with open(RESTAURANT_INFO_FILE, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        pass
    return "Noodle Box Drogheda"

def get_delivery_fee(address: str) -> float:
    areas = load_delivery_areas()
    if not areas:
        return 0.0

    address_lower = address.lower()
    last_match = None
    last_match_index = -1

    for area, price in areas.items():
        idx = address_lower.rfind(area)
        if idx != -1:
            if idx > last_match_index:
                last_match_index = idx
                last_match = (area, price)

    if last_match:
        return last_match[1]

    return areas.get("drogheda", 3.0)


# =============================================================================
# 菜单项搜索
# =============================================================================

def find_item(query_name: str) -> dict:
    """基于缓存后的 menu.json 内存字典搜索，性能较高"""
    menu = load_menu()
    query_lower = query_name.lower().strip()

    # [BUG FIX] Gemini 会把 "KIDS MENU" 分类的菜品自动加上 "Kids " 前缀，
    # 导致 "Kids Chicken Nuggets & Chips" 匹配不到 "Chicken Nuggets & Chips"。
    # 若查询以 "kids " 开头，提取后面的部分作为真正的菜名，并标记我们在找儿童餐。
    is_kids_meal_request = False
    if query_lower.startswith("kids ") and "kids" not in query_lower[5:]:
        # 也有个别菜原本就叫 Kids xxx 的防止误伤，所以做个基础前缀剥离
        stripped_query = query_lower[5:].strip()
        is_kids_meal_request = True
    else:
        stripped_query = query_lower

    # --- 第零轮：特供 KIDS MENU 精确匹配防冲突 ---
    # 针对 "Chicken Goujons & Chips" 在欧洲菜单和儿童菜单重名的问题
    if is_kids_meal_request:
        kids_category = menu.get("KIDS MENU", [])
        if isinstance(kids_category, list):
            for item in kids_category:
                item_name_lower = item['name'].lower()
                if item_name_lower == stripped_query:
                    return item

    # --- 第一轮：普通精确匹配（优先）---
    for category, items in menu.items():
        # 如果是儿童餐请求且已经走到这里，说明上面没找到，但我们尽量跳过成年人同名菜防止误判导致价格错误
        if is_kids_meal_request and category == "EUROPEAN MENU":
            continue

        if isinstance(items, list):
            for item in items:
                item_name_lower = item['name'].lower()
                if item_name_lower == query_lower or item_name_lower == stripped_query:
                    return item

    # --- 第二轮：包含匹配（退而求其次）---
    for category, items in menu.items():
        if is_kids_meal_request and category == "EUROPEAN MENU":
            continue

        if isinstance(items, list):
            for item in items:
                item_name_lower = item['name'].lower()
                if query_lower in item_name_lower or (stripped_query and stripped_query in item_name_lower):
                    return item

    return None  # 完全未找到


# =============================================================================
# 订单持久化操作 (Order) -> 入库 SQLite
# =============================================================================

def save_order(order_data: dict):
    """
    将订单数据插入 SQLite orders 表。
    """
    try:
        with get_db_session() as db:
            # Check if order already exists
            order_id = order_data.get('order_id')
            if not order_id:
                logger.error("Order missing ID")
                return
                
            existing_order = db.query(Order).filter_by(id=order_id).first()
            if existing_order:
                logger.warning(f"Order {order_id} already exists, skipping insert.")
                return

            new_order = Order(
                id=order_id,
                business_date=order_data.get('business_date_str', 'Unknown Date'),
                customer_phone=order_data.get('customer_phone'),
                source=order_data.get('source', 'System'),
                service_type=order_data.get('service_type', 'Pickup'),
                delivery_area=order_data.get('delivery_area'),
                delivery_fee=float(order_data.get('delivery_fee', 0.0)),
                payment_method=order_data.get('payment_method', 'Cash'),
                total_value=float(order_data.get('total_value', 0.0)),
                notes=order_data.get('note'),
                items=order_data.get('items', []),
                transcript=order_data.get('transcript', [])
            )
            
            db.add(new_order)
            
            # Since an order just came in, ensure the customer exists or is updated
            # update_customer_history typically runs alongside this, but it handles the actual Customer row creation now if missing
            customer_phone = order_data.get('customer_phone')
            if customer_phone:
                customer = db.query(Customer).filter_by(phone_number=customer_phone).first()
                if customer:
                    customer.last_order_id = order_id
                else:
                    customer = Customer(phone_number=customer_phone, last_order_id=order_id)
                    db.add(customer)

            db.commit()
            logger.info(f"订单已保存至 SQLite 表: {order_id}")

    except Exception as e:
        logger.error(f"保存订单至数据库时出错: {e}")


def update_customer_history(
    phone: str,
    order_summary: str,
    name: str = None,
    address: str = None
):
    """
    更新 SQLite 中客户联系信息和建立/更新关联。
    """
    try:
        with get_db_session() as db:
            customer = db.query(Customer).filter_by(phone_number=phone).first()
            if not customer:
                customer = Customer(phone_number=phone)
                db.add(customer)
                
            if name and name != "Unknown":
                customer.name = name
            if address and address not in ("Pickup", "Unknown"):
                customer.address = address
                
            # 我们不再在这个表单独存 Array 的 History 了，而是通过查询 Order 外键连表动态计算了！
            db.commit()
    except Exception as e:
        logger.error(f"更新客户历史档案时出错: {e}")


def get_order_details(order_id: str) -> Optional[dict]:
    """
    根据 Order ID 从 SQLite 检索，组合成原来字典的结构返回。
    """
    try:
        with get_db_session() as db:
            # 优先精确匹配，如果是部分匹配，则通过 LIKE
            order = db.query(Order).filter(Order.id.like(f"%{order_id}%")).first()
            if order:
                # 转换 ORM Model 回 Dictionary 给 AI 读取
                return {
                    "order_id": order.id,
                    "customer_phone": order.customer_phone,
                    "service_type": order.service_type,
                    "delivery_area": order.delivery_area,
                    "delivery_fee": order.delivery_fee,
                    "payment_method": order.payment_method,
                    "total_value": order.total_value,
                    "note": order.notes,
                    "items": order.items
                }
    except Exception as e:
        logger.error(f"检索订单 {order_id} 失败: {e}")
    return None
