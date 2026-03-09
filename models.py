import os
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

logger = logging.getLogger("AI-Waiter")

# Base class for declarative models
Base = declarative_base()

# =============================================================================
# App Settings Model — 持久化配置（代替 settings.json / delivery_areas.txt）
# =============================================================================
class AppSetting(Base):
    """
    通用键值配置表。
    存储所有原本保存在容器文件系统上的配置，确保跨部署持久化。

    常用 key：
        'settings_json'    → 完整的 settings.json JSON 字符串
        'delivery_areas'   → delivery_areas.txt 原始文本内容
    """
    __tablename__ = 'app_settings'

    key        = Column(String(100), primary_key=True)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Customer Data Model
# =============================================================================
class Customer(Base):
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    last_order_id = Column(String(50), nullable=True) # ID of the most recent order

    # Relationship to orders
    orders = relationship("Order", back_populates="customer")


# =============================================================================
# Order Data Models
# =============================================================================
class Order(Base):
    __tablename__ = 'orders'

    # Use the original string ID (e.g. "ORD-123456789-1234") as the primary key
    id = Column(String(50), primary_key=True)
    
    # Store the business date string (e.g. 'Sat Dec 27')
    business_date = Column(String(20), index=True, nullable=False)
    
    # Actual creation timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Customer reference
    customer_phone = Column(String(20), ForeignKey('customers.phone_number'), nullable=True)
    
    # Source: "AI" or "AI (Incomplete)"
    source = Column(String(50), nullable=False)
    
    # Order Details
    service_type = Column(String(20), nullable=False) # Delivery or Pickup
    delivery_area = Column(String(100), nullable=True)
    delivery_fee = Column(Float, default=0.0)
    payment_method = Column(String(20), nullable=False)
    total_value = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)
    
    # Use JSON column for the items for simplicity initially
    items = Column(JSON, nullable=False)
    
    # Store the conversation history for this order
    transcript = Column(JSON, nullable=True)
    
    # Raw receipt text
    receipt_text = Column(Text, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="orders")


# =============================================================================
# Menu Data Models
# =============================================================================
class MenuCategory(Base):
    __tablename__ = 'menu_categories'
    
    name = Column(String(100), primary_key=True) # e.g., "Spice Box", "Wok Box"
    display_order = Column(Integer, default=0)
    
    items = relationship("MenuItem", back_populates="category", cascade="all, delete-orphan")


class MenuItem(Base):
    __tablename__ = 'menu_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(100), ForeignKey('menu_categories.name'), nullable=False)
    name = Column(String(150), unique=True, index=True, nullable=False)
    price = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    allergens = Column(String(200), nullable=True)

    # Relationships
    category = relationship("MenuCategory", back_populates="items")
    options = relationship("MenuOption", back_populates="menu_item", cascade="all, delete-orphan")


class MenuOption(Base):
    __tablename__ = 'menu_options'

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey('menu_items.id'), nullable=False)
    name = Column(String(100), nullable=False)
    price_change = Column(Float, default=0.0)
    is_default = Column(Boolean, default=False)
    
    # Relationships
    menu_item = relationship("MenuItem", back_populates="options")


# =============================================================================
# Database Initialization — 环境感知（本地 SQLite / 生产 Cloud SQL）
# =============================================================================
def init_db():
    """
    初始化数据库引擎并创建所有表（如果不存在）。

    环境自动检测：
        - 本地开发（无 CLOUD_SQL_CONNECTION_NAME 环境变量）：使用 SQLite (app.db)
        - Cloud Run 生产环境（有 CLOUD_SQL_CONNECTION_NAME）：
          通过 Cloud SQL Python Connector 使用 Unix Socket 连接 PostgreSQL

    Returns:
        (engine, SessionLocal) 元组
    """
    cloud_sql_conn_name = os.environ.get("CLOUD_SQL_CONNECTION_NAME")

    if cloud_sql_conn_name:
        # === 生产环境：Cloud SQL for PostgreSQL (Unix Socket) ===
        db_name = os.environ.get("DB_NAME", "noodlebox")
        db_user = os.environ.get("DB_USER", "noodlebox")
        db_pass = os.environ.get("DB_PASSWORD", "")

        logger.info(f"🔌 连接 Cloud SQL: {cloud_sql_conn_name}/{db_name}")

        try:
            from google.cloud.sql.connector import Connector
            connector = Connector()

            def getconn():
                return connector.connect(
                    cloud_sql_conn_name,
                    "pg8000",
                    user=db_user,
                    password=db_pass,
                    db=db_name,
                )

            engine = create_engine(
                "postgresql+pg8000://",
                creator=getconn,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=2,
            )
        except Exception as e:
            logger.error(f"❌ Cloud SQL 连接失败: {e}")
            raise
    else:
        # === 本地开发环境：SQLite ===
        logger.info("💾 使用本地 SQLite 数据库 (app.db)")
        engine = create_engine(
            "sqlite:///app.db",
            connect_args={"check_same_thread": False}
        )

    # 创建所有表（幂等操作，已存在则跳过）
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal
