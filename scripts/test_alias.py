import database
print("Loading menu...")
database.load_menu()

# 示例：测试查找 "Chicken Wings" 的别名 "Hot Chicken wings"
query = "Hot Chicken wings"
print(f"Testing find_item('{query}')...")
item = database.find_item(query)

if item:
    print(f"✅ Success! Found item: {item['name']}")
    print(f"Price: {item['price']}")
else:
    print("❌ Failed. Item not found.")
