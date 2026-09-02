from database.db import init_db
from config import DATABASE_FILE

print("Database:")
print(DATABASE_FILE)
print("")
print("Checking / migrating schema...")

init_db()

print("")
print("SQLite migration: OK")
print("You can now run:")
print("python main.py")
