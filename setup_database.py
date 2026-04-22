from database_utils import init_db


def setup_database():
    init_db()
    print("Database initialized successfully.")

if __name__ == "__main__":
    setup_database()
