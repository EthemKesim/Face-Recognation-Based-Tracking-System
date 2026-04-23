from database_utils import delete_employee_record, fetch_registered_users, init_db

def manage_records():
    init_db()
    
    while True:
        records = fetch_registered_users()
        
        print("\n" + "="*30)
        print("   REGISTERED USERS LIST")
        print("="*30)
        
        if not records:
            print("Database is currently empty.")
            break
            
        for user_id, name in records:
            print(f"ID: {user_id} | Name: {name}")
        
        choice = input("\nEnter the ID to delete (Press 'q' to quit): ")
        
        if choice.lower() == 'q':
            break

        if not choice.isdigit():
            print("Please enter a numeric ID.")
            continue

        result = delete_employee_record(int(choice))
        if result["deleted"]:
            print(f'Record {choice} deleted for {result["employee_name"]}.')
            if result.get("warning"):
                print(result["warning"])
        else:
            print(result["error"])

if __name__ == "__main__":
    manage_records()
