from app import app
client = app.test_client()

routes = [
    '/home',
    '/register-farm',
    '/loan-services',
    '/shares-management',
    '/transport-logistics',
    '/log-yield',
    '/weighbridge-tickets',
    '/staff/loan-intake'
]

with client.session_transaction() as sess:
    sess['user_logged_in'] = True
    sess['user_role'] = 'Intake Agent'
    sess['lang'] = 'en'

for route in routes:
    try:
        resp = client.get(route)
        print(f"{route}: {resp.status_code}")
        if resp.status_code != 200:
            print(resp.data[:200])
    except Exception as e:
        print(f"{route}: Exception -> {e}")
