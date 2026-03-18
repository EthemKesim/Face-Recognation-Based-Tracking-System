import sqlite3

def init_db():
    conn = sqlite3.connect('face_records.db')
    cursor = conn.cursor()
    # Table name: users | Columns: id, name, face_vector
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       name TEXT, 
                       face_vector TEXT)''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()