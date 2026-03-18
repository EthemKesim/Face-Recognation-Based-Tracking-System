import sqlite3

def manage_records():
    conn = sqlite3.connect('face_records.db')
    cursor = conn.cursor()
    
    while True:
        cursor.execute("SELECT id, name FROM users")
        records = cursor.fetchall()
        
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
            
        cursor.execute("DELETE FROM users WHERE id = ?", (choice,))
        conn.commit()
        print(f"Record {choice} deleted.")

    conn.close()

if __name__ == "__main__":
    manage_records()