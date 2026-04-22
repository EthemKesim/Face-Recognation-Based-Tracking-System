from database_utils import deactivate_or_delete_user, fetch_registered_users, init_db

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

        if deactivate_or_delete_user(int(choice)):
            print(f"Record {choice} deleted.")
        else:
            print(f"Record {choice} was not found.")

if __name__ == "__main__":
    manage_records()
