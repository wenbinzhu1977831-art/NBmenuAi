"""
upload_to_cloud_sql.py — 本地 SQLite 数据迁移到 Cloud SQL (PostgreSQL)

使用方式：
    python scripts/upload_to_cloud_sql.py

前置条件：
    1. 已安装依赖：pip install cloud-sql-python-connector[pg8000] SQLAlchemy pg8000
    2. 已完成 gcloud 认证：gcloud auth application-default login
    3. app.db 文件存在于项目根目录
    4. Cloud SQL 实例已创建 noodlebox 数据库和 noodlebox 用户

环境变量（脚本会自动使用，也可手动设置）：
    CLOUD_SQL_CONNECTION_NAME = gen-lang-client-0137495693:europe-west1:noodle-box-ai-project
    DB_NAME = noodlebox
    DB_USER = noodlebox
    DB_PASSWORD = your_db_password
"""

import os
import sys

# 确保从项目根目录运行
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SQLite→CloudSQL")

# ============================================================
# 硬编码连接信息（如果没有设置环境变量）
# ============================================================
CLOUD_SQL_CONNECTION_NAME = os.environ.get(
    "CLOUD_SQL_CONNECTION_NAME",
    "gen-lang-client-0137495693:europe-west1:noodle-box-ai-project"
)
DB_NAME = os.environ.get("DB_NAME", "noodlebox")
DB_USER = os.environ.get("DB_USER", "noodlebox")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

if not DB_PASSWORD:
    DB_PASSWORD = input("请输入 Cloud SQL noodlebox 用户密码: ").strip()

SQLITE_PATH = os.path.join(project_root, "app.db")

# ============================================================
# 连接本地 SQLite（数据源）
# ============================================================
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger.info(f"📂 打开本地 SQLite: {SQLITE_PATH}")
if not os.path.exists(SQLITE_PATH):
    logger.error("❌ app.db 不存在！请确认文件路径。")
    sys.exit(1)

sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})
SQLiteSession = sessionmaker(bind=sqlite_engine)
sqlite_db = SQLiteSession()

# ============================================================
# 连接 Cloud SQL PostgreSQL（目标）
# ============================================================
logger.info(f"🔌 连接 Cloud SQL: {CLOUD_SQL_CONNECTION_NAME}/{DB_NAME}")
try:
    from google.cloud.sql.connector import Connector
    connector = Connector()

    def getconn():
        return connector.connect(
            CLOUD_SQL_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )

    pg_engine = create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        pool_pre_ping=True,
    )
    # 测试连接
    with pg_engine.connect() as conn:
        conn.execute(pg_engine.dialect.statement_compiler(pg_engine.dialect, None).process(
            __import__("sqlalchemy").text("SELECT 1")
        ) if False else __import__("sqlalchemy").text("SELECT 1"))
    logger.info("✅ Cloud SQL 连接成功")
except Exception as e:
    logger.error(f"❌ 无法连接 Cloud SQL: {e}")
    logger.info("提示：请先运行 'gcloud auth application-default login'")
    sys.exit(1)

# 在 Cloud SQL 中创建表（如果不存在）
from models import Base
Base.metadata.create_all(pg_engine)
PGSession = sessionmaker(bind=pg_engine)
pg_db = PGSession()

# ============================================================
# 迁移各张表
# ============================================================
from models import Customer, Order, MenuCategory, MenuItem, MenuOption

def migrate_table(table_name, model_class, source_db, target_db):
    """通用表迁移函数"""
    records = source_db.query(model_class).all()
    logger.info(f"  📋 {table_name}: 本地共 {len(records)} 条记录")
    
    skipped = 0
    added = 0
    for record in records:
        # 获取主键判断是否已存在
        pk_cols = [c.key for c in __import__("sqlalchemy").inspect(model_class).primary_key]
        pk_vals = {col: getattr(record, col) for col in pk_cols}
        
        existing = target_db.query(model_class).filter_by(**pk_vals).first()
        if existing:
            skipped += 1
            continue
        
        # 创建新记录（分离 ORM 状态后复制）
        source_db.expunge(record)
        __import__("sqlalchemy").orm.make_transient(record)
        target_db.add(record)
        added += 1
    
    target_db.commit()
    logger.info(f"     ✅ 新增 {added} 条，跳过已存在 {skipped} 条")
    return added

try:
    logger.info("\n🚀 开始数据迁移...\n")
    
    # 按外键依赖顺序迁移
    migrate_table("menu_categories", MenuCategory, sqlite_db, pg_db)
    migrate_table("menu_items", MenuItem, sqlite_db, pg_db)
    migrate_table("menu_options", MenuOption, sqlite_db, pg_db)
    migrate_table("customers", Customer, sqlite_db, pg_db)
    migrate_table("orders", Order, sqlite_db, pg_db)

    logger.info("\n🎉 数据迁移完成！所有本地数据已上传至 Cloud SQL。")

except Exception as e:
    pg_db.rollback()
    logger.error(f"❌ 迁移失败，已回滚: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    sqlite_db.close()
    pg_db.close()
    connector.close()
