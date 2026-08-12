import sqlite3

conn = sqlite3.connect('sacco_portal.db')
cursor = conn.cursor()
cursor.execute("SELECT username, role, password_hash FROM staff_users")
users = cursor.fetchall()

print("Users in database:")
for user in users:
    print(f"Username: {user[0]}, Role: {user[1]}, Password Hash: {user[2]}")

conn.close()
