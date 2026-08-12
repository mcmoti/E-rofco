import os
from app import app, db
from models import User

def test_system():
    with app.app_context():
        print("=======================================")
        print("      E-ROFCO SYSTEM TEST SCRIPT")
        print("=======================================\n")
        
        print("[*] Connecting to database...")
        users = User.query.all()
        
        # The default password seeded in app.py during init_db()
        default_password = 'Mrofco2026'
        
        print(f"[*] Found {len(users)} users in the system.\n")
        
        print("--- USER ROLES & DEFAULT CREDENTIALS ---")
        if not users:
            print("No users found in the database. Has the app been initialized?")
        else:
            print(f"{'ROLE':<20} | {'USERNAME':<15} | {'DEFAULT PASSWORD'}")
            print("-" * 60)
            for user in users:
                print(f"{user.role:<20} | {user.username:<15} | {default_password}")
                
        print("\n--- TESTING CORE FUNCTIONALITY ---")
        client = app.test_client()
        
        print("[*] 1. Testing Policy Acceptance Route...")
        # First accept the policy
        policy_resp = client.post('/policy', data={'accept_policy': 'true'})
        if policy_resp.status_code in [200, 302]:
            print("    [+] Policy accepted successfully.")
        else:
            print(f"    [-] Policy acceptance failed with status {policy_resp.status_code}.")

        if users:
            test_user = users[0]
            print(f"[*] 2. Testing Login for Role: {test_user.role} (User: {test_user.username})...")
            
            login_resp = client.post('/login', data={
                'role': test_user.role,
                'username': test_user.username,
                'password': default_password
            }, follow_redirects=True)
            
            # Check if login was successful by looking for typical dashboard elements
            if b'Sign Out' in login_resp.data or b'Toka Mfomoni' in login_resp.data:
                print(f"    [+] Login successful! Redirected to {test_user.role} dashboard.")
            elif b'Invalid username or password' in login_resp.data:
                print(f"    [-] Login failed: Invalid username or password.")
                print(f"        (Note: The password in the database for {test_user.username} might have been changed from the default '{default_password}')")
            elif b'Invalid role selected' in login_resp.data:
                print("    [-] Login failed: Invalid role selected.")
            else:
                print("    [?] Login completed, but could not explicitly verify dashboard content.")
                
        print("\n=======================================")
        print("         SYSTEM TEST COMPLETE")
        print("=======================================")

if __name__ == '__main__':
    test_system()
