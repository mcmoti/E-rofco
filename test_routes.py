from app import app
client = app.test_client()
with client.session_transaction() as sess:
    sess['user_logged_in'] = True
    sess['user_role'] = 'Intake Agent'
    sess['lang'] = 'en'
    
resp = client.get('/register-farm')
print(f"Status Code: {resp.status_code}")
print(f"Is Farm Registry in data: {b'Farm Registry' in resp.data}")
print("Response top 500 chars:")
print(resp.data[:500].decode('utf-8'))
