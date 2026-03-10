"""
migrate_orders_only.py — 只迁移 orders 和 customers 到 Cloud SQL
（menu 已经成功迁移，跳过）
"""
import os, sys, json
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OrderMigrate")

import sqlite3
from google.cloud.sql.connector import Connector
import sqlalchemy
from sqlalchemy.orm import sessionmaker

CLOUD_SQL_CONNECTION_NAME = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "gen-lang-client-0137495693:europe-west1:noodle-box-ai-project")
DB_NAME = os.environ.get("DB_NAME", "noodlebox")
DB_USER = os.environ.get("DB_USER", "noodlebox")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD:
    DB_PASSWORD = input("Cloud SQL 密码: ").strip()

# ── Cloud SQL 连接 ──
connector = Connector()
def getconn():
    return connector.connect(CLOUD_SQL_CONNECTION_NAME, "pg8000", user=DB_USER, password=DB_PASSWORD, db=DB_NAME)

pg_engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn, pool_pre_ping=True)

from models import Base, Customer, Order
Base.metadata.create_all(pg_engine)
PGSession = sessionmaker(bind=pg_engine)
pg_db = PGSession()

# ── 读取 SQLite ──
sqlite_conn = sqlite3.connect("app.db")
sqlite_conn.row_factory = sqlite3.Row

def safe_str(val):
    """确保值是字符串或 None，不是 list/dict"""
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    return str(val) if val != '' else None

def safe_float(val):
    try:
        return float(val) if val is not None else 0.0
    except:
        return 0.0

def safe_json(val):
    """确保值是可序列化的 list/dict"""
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except:
        return []

try:
    # ── 迁移 customers ──
    cur = sqlite_conn.execute("SELECT * FROM customers")
    customers = cur.fetchall()
    logger.info(f"📋 customers: {len(customers)} 条")
    added = skipped = 0
    for row in customers:
        existing = pg_db.query(Customer).filter_by(phone_number=row['phone_number']).first()
        if existing:
            skipped += 1
            continue
        pg_db.add(Customer(
            phone_number=row['phone_number'],
            name=safe_str(row['name']),
            address=safe_str(row['address']),
            last_order_id=safe_str(row['last_order_id'])
        ))
        added += 1
    pg_db.commit()
    logger.info(f"   ✅ 新增 {added}，跳过 {skipped}")

    # ── 迁移 orders ──
    cur = sqlite_conn.execute("SELECT * FROM orders")
    orders = cur.fetchall()
    logger.info(f"📋 orders: {len(orders)} 条")
    added = skipped = 0
    for row in orders:
        existing = pg_db.query(Order).filter_by(id=row['id']).first()
        if existing:
            skipped += 1
            continue
        try:
            pg_db.add(Order(
                id=row['id'],
                business_date=str(row['business_date'] or 'Unknown'),
                created_at=row['created_at'],
                customer_phone=safe_str(row['customer_phone']),
                source=str(row['source'] or 'System'),
                service_type=str(row['service_type'] or 'Pickup'),
                delivery_area=safe_str(row['delivery_area']),
                delivery_fee=safe_float(row['delivery_fee']),
                payment_method=str(row['payment_method'] or 'Cash'),
                total_value=safe_float(row['total_value']),
                notes=safe_str(row['notes']),
                items=safe_json(row['items']),
                transcript=safe_json(row['transcript']),
                receipt_text=safe_str(row['receipt_text'])
            ))
            pg_db.flush()
            added += 1
        except Exception as e:
            pg_db.rollback()
            logger.warning(f"   ⚠️ 跳过订单 {row['id']}: {e}")
            skipped += 1
    pg_db.commit()
    logger.info(f"   ✅ 新增 {added}，跳过 {skipped}")

    logger.info("\n🎉 orders + customers 迁移完成！")

except Exception as e:
    pg_db.rollback()
    logger.error(f"❌ 失败: {e}")
    import traceback; traceback.print_exc()
finally:
    sqlite_conn.close()
    pg_db.close()
    connector.close()
