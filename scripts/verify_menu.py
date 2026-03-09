import json
import database

def verify_menu_integrity():
    print("Loading original menu.json...")
    with open('menu.json', 'r', encoding='utf-8') as f:
        original_menu = json.load(f)
        
    print("Loading SQLite menu database via load_menu()...")
    db_menu = database.load_menu()
    
    missing_categories = []
    missing_items = []
    
    total_json_items = 0
    total_db_items = 0
    
    for cat_name, items in original_menu.items():
        if cat_name not in db_menu:
            missing_categories.append(cat_name)
            continue
            
        db_cat_items = db_menu[cat_name]
        db_item_names = [item['name'].strip() for item in db_cat_items]
        
        for item in items:
            total_json_items += 1
            item_name = item['name'].strip()
            if item_name not in db_item_names:
                missing_items.append((cat_name, item_name))
                
    for cat_name, items in db_menu.items():
        total_db_items += len(items)

    print(f"\n--- Verification Results ---")
    print(f"Total Items in menu.json: {total_json_items}")
    print(f"Total Items in Database : {total_db_items}")
    
    if missing_categories:
        print("\n[!] MISSING CATEGORIES IN DATABASE:")
        for cat in missing_categories:
            print(f"  - {cat}")
            
    if missing_items:
        print("\n[!] MISSING ITEMS IN DATABASE:")
        for cat, item in missing_items:
            print(f"  - [{cat}] {item}")
            
    if not missing_categories and not missing_items:
        print("\n✅ All categories and items from menu.json exist in the database!")

if __name__ == "__main__":
    verify_menu_integrity()
