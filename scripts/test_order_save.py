import database
import time

print("Testing save_order...")

test_order = {
    "order_id": f"TEST-{int(time.time())}",
    "timestamp": time.ctime(),
    "customer_phone": "+353871234567",
    "items": [{"name": "Spice Box", "quantity": 1}],
    "total_value": 15.00,
    "service_type": "Pickup"
}

database.save_order(test_order)

print("Order saved. Check orders.json manually.")
# 订单已保存。请手动检查 orders.json。
