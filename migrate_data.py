import json
import logging
import os
import copy
from datetime import datetime

from models import init_db, MenuCategory, MenuItem, MenuOption, Customer, Order
from config import config

# Set up logging for the script
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Migration Script")

def migrate_data():
    logger.info("Starting data migration from JSON to database...")
    
    # Initialize the database and get session
    engine, SessionLocal = init_db()
    db = SessionLocal()

    try:
        # =====================================================================
        # 1. Migrate Menu (menu.json)
        # =====================================================================
        if os.path.exists(config.menu_file):
            logger.info(f"Migrating menu from {config.menu_file}...")
            with open(config.menu_file, "r", encoding="utf-8") as f:
                menu_data = json.load(f)

            display_order = 0
            for category_name, items in menu_data.items():
                logger.info(f"  -> Processing Category: {category_name}")
                
                # Check if category already exists
                category = db.query(MenuCategory).filter_by(name=category_name).first()
                if not category:
                    category = MenuCategory(name=category_name, display_order=display_order)
                    db.add(category)
                display_order += 10
                
                if isinstance(items, list):
                    for item in items:
                        # Check if item already exists
                        menu_item_query = db.query(MenuItem).filter_by(name=item["name"]).first()
                        if not menu_item_query:
                            logger.info(f"     * Adding Item: {item['name']}")
                            menu_item = MenuItem(
                                category_name=category_name,
                                name=item["name"],
                                price=float(item.get("price", 0.0)),
                                description=item.get("description"),
                                allergens=item.get("allergens")
                            )
                            db.add(menu_item)
                            db.flush() # Flush to get the ID
                            
                            # Process options if any
                            if "options" in item:
                                for opt_group in item["options"]:
                                    # opt_group eg: {"name": "SIZE", "values": [{"name": "Large", "price_mod": 1.0}]}
                                    group_name = opt_group["name"]
                                    for opt_val in opt_group["values"]:
                                        val_name = opt_val["name"]
                                        # To flatten it out, we prefix the name with the group name "MEAT: Chicken"
                                        full_opt_name = f"{group_name}: {val_name}"
                                        
                                        db.add(MenuOption(
                                            item_id=menu_item.id,
                                            name=full_opt_name,
                                            price_change=float(opt_val.get("price_mod", 0.0)),
                                            is_default=opt_val.get("default", False)
                                        ))
                                        
            logger.info("Menu migration complete.")
        else:
            logger.warning(f"Menu file {config.menu_file} not found. Skipping.")


        # =====================================================================
        # 2. Migrate Customers (customers.json)
        # =====================================================================
        if os.path.exists(config.customers_file):
            logger.info(f"Migrating customers from {config.customers_file}...")
            with open(config.customers_file, "r", encoding="utf-8") as f:
                customers_data = json.load(f)
                
            for phone, data in customers_data.items():
                existing_customer = db.query(Customer).filter_by(phone_number=phone).first()
                if not existing_customer:
                    logger.info(f"  -> Adding Customer: {phone}")
                    customer = Customer(
                        phone_number=phone,
                        name=data.get("name"),
                        address=data.get("address")
                    )
                    db.add(customer)
                else:
                    # Update fields if available
                    if data.get("name") and existing_customer.name in [None, 'Unknown']:
                        existing_customer.name = data.get("name")
                    if data.get("address") and existing_customer.address in [None, 'Unknown', 'Pickup']:
                        existing_customer.address = data.get("address")
                        
            logger.info("Customers migration complete.")
        else:
            logger.warning(f"Customers file {config.customers_file} not found. Skipping.")


        # =====================================================================
        # 3. Migrate Orders (orders.json)
        # =====================================================================
        if os.path.exists(config.orders_file):
            logger.info(f"Migrating orders from {config.orders_file}...")
            with open(config.orders_file, "r", encoding="utf-8") as f:
                try:
                    orders_data = json.load(f)
                except json.JSONDecodeError:
                    orders_data = []

            for index, order_data in enumerate(orders_data):
                order_id = order_data.get("order_id")
                if not order_id:
                    continue
                    
                existing_order = db.query(Order).filter_by(id=order_id).first()
                if not existing_order:
                    logger.info(f"  -> Adding Order: {order_id}")
                    
                    # Some early orders didn't have business_date_str correctly formatted, give a default
                    business_date_str = order_data.get("business_date_str", "Unknown")
                    if business_date_str == "Unknown":
                         # Fallback to try and extract it from timestamp
                         timestamp_str = order_data.get("timestamp", "")
                         if timestamp_str:
                             # Example: "Sat Dec 27 16:34:45 2025" -> "Sat Dec 27"
                             parts = timestamp_str.split(" ")
                             if len(parts) >= 3:
                                 business_date_str = f"{parts[0]} {parts[1]} {parts[2]}"
                    
                    new_order = Order(
                        id=order_id,
                        business_date=business_date_str,
                        customer_phone=order_data.get("customer_phone"),
                        source=order_data.get("source", "System"),
                        service_type=order_data.get("service_type", "Pickup"),
                        delivery_area=order_data.get("delivery_area"),
                        delivery_fee=float(order_data.get("delivery_fee", 0.0)),
                        payment_method=order_data.get("payment_method", "Cash"),
                        total_value=float(order_data.get("total_value", 0.0)),
                        notes=order_data.get("note"),
                        items=copy.deepcopy(order_data.get("items", []))
                    )
                    
                    db.add(new_order)
            
            logger.info("Orders migration complete.")
        else:
            logger.warning(f"Orders file {config.orders_file} not found. Skipping.")

        # Commit all transactions safely at the very end
        db.commit()
        logger.info("All data successfully migrated and committed!")

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed! Rolled back. Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_data()
