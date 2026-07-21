import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = 'erofco_secret_key_for_development'

# --- GLOBAL CACHE CONFIGURATION ---
DASHBOARD_CACHE = {
    "data": None,
    "last_updated": 0
}
CACHE_TIMEOUT = 300  # 5 minutes

REGISTERED_USERS = {
    "emp1": {"pin": "1234", "name": "John Doe", "role": "Staff Officer", "class": "Shareholding"},
    "emp2": {"pin": "4321", "name": "John Doe", "role": "Staff Officer", "class": "General"}
}

TEXTS = {
    'en': {
        'welcome': 'Welcome to E-ROFCO Staff Portal', 
        'subtext': 'Internal Registry & Operations System.',
        'proceed': 'Proceed to Security Check', 
        'switch_btn': 'Badili kwenda Kiswahili',
        'policy_title': 'E-ROFCO Regulatory & Data Compliance', 
        'policy_text': 'By ticking the box below, you explicitly agree to handle member farm data securely under the regional framework.',
        'agree_check': 'I explicitly agree to the corporate data protection terms.', 
        'continue_btn': 'Continue to Identification Portal', 
        'error_msg': 'You must accept the terms to proceed.',
        'login_title': 'Staff Identity Verification', 
        'login_subtext': 'Please enter your employee 4-digit security PIN.',
        'pin_label': 'Security PIN', 
        'login_btn': 'Verify Staff Identity', 
        'invalid_pin': 'Access Denied: Invalid credentials.',
        'dash_title': 'Cooperative Operations Hub', 
        'dash_sub': 'Logged in as Employee: ', 
        'logout': 'Secure Log Out',
        'm1': 'Farmer Registry', 
        'm1_sub': 'Register new farmers and complete profile metrics',
        'm2': 'Transport Logistics', 
        'm2_sub': 'Search registered farmers & schedule tractor dispatches',
        'm3': 'Production Yield Dataset', 
        'm3_sub': 'Access live spreadsheet metrics & membership ledger',
        'm5': 'LOAN Services', 
        'm5_sub': 'Search registered farmers & issue credit applications',
        'm6': 'Shares Management', 
        'm6_sub': 'Search registered farmers & manage share accounts',
        'reg_title': 'Farmer Registry', 
        'reg_sub': 'Register comprehensive farmer profile details directly into Google Sheets.',
        'label_farmer_name': 'Farmer Full Name', 
        'label_phone': 'Phone Number', 
        'label_id': 'National ID / Registration No.',
        'label_loc': 'Farm Location / Region', 
        'label_size': 'Farm Size (Acres)', 
        'label_crop': 'Primary Target Crop',
        'reg_btn': 'Save & Register Farmer', 
        'reg_success': 'Farmer profile successfully saved to Google Sheets Membership ledger!', 
        'back_dash': 'Back to Dashboard',
        'loan_title': 'Credit & Capital Ledger', 
        'loan_sub': 'Register micro-finance credit applications for existing farmers.',
        'loan_amt_label': 'Requested Loan Amount (KES)', 
        'loan_term_label': 'Repayment Term (Months)',
        'loan_btn': 'Submit Credit Application', 
        'loan_success': 'Loan application logged to Google Sheets!',
        'interest_notice': 'All applications include a flat 10% interest markup.',
        'trans_title': 'Transport & Machinery Logistics',
        'trans_sub': 'Schedule tractor dispatch services for registered farmers.',
        'label_service_type': 'Required Service Type', 
        'label_dispatch_date': 'Target Dispatch Date',
        'opt_plow': 'Land Ploughing / Preparation', 
        'opt_haul': 'Crop Hauling & Transport', 
        'opt_harv': 'Mechanical Harvesting',
        'trans_btn': 'Request Tractor Dispatch', 
        'trans_success': 'Tractor request logged in Google Sheets!',
        'shares_title': 'Shares & Capital Registry',
        'shares_sub': 'Record farmer shareholding allocations and benefits.',
        'label_num_shares': 'Number of Shares', 
        'label_share_val': 'Share Value Rate (KES)',
        'label_benefits': 'Expected Annual Benefits (KES)', 
        'shares_btn': 'Record Share Details',
        'shares_success': 'Share records saved to Google Sheets!',
        'about_title': 'About E-ROFCO', 
        'about_sub': 'Cooperative Society',
        'about_text': 'E-ROFCO is dedicated to empowering local smallholder farmers by offering modernized, digital co-operative frameworks.',
        'about_leadership': 'Executive Leadership', 
        'role_chairman': 'Chairman', 
        'role_treasurer': 'Treasurer', 
        'role_secretary': 'Secretary',
        'about_partners': 'Key Partners', 
        'about_contact_title': 'Get in Touch', 
        'about_phone_label': 'Call Us',
        'about_email_label': 'Email Us', 
        'about_social_label': 'Follow Us'
    },
    'sw': {
        'welcome': 'Karibu kwenye Tovuti ya Wafanyakazi ya E-ROFCO', 
        'subtext': 'Mfumo wa Ndani wa Usajili na Shughuli.',
        'proceed': 'Endelea kwa Uhakiki wa Usalama', 
        'switch_btn': 'Switch to English',
        'policy_title': 'Uzingatiaji wa Sheria na Data wa E-ROFCO', 
        'policy_text': 'Kwa kuweka alama kwenye sanduku, unakubali kushughulikia data za wakulima kwa usalama.',
        'agree_check': 'Ninakubali masharti ya ulinzi wa data.', 
        'continue_btn': 'Endelea hadi Tovuti ya Utambulisho', 
        'error_msg': 'Ni lazima ukubali masharti ili kuendelea.',
        'login_title': 'Uhakiki wa Mfanyakazi', 
        'login_subtext': 'Tafadhali weka PIN yako ya mfanyakazi yenye tarakimu 4.',
        'pin_label': 'Nambari ya Siri (PIN)', 
        'login_btn': 'Hakiki Utambulisho wa Mfanyakazi', 
        'invalid_pin': 'Ufikiaji Umekataliwa: Sifa si sahihi.',
        'dash_title': 'Kituo cha Shughuli za Ushirika', 
        'dash_sub': 'Umeingia kama Mfanyakazi: ', 
        'logout': 'Ondoka kwa Usalama',
        'm1': 'Usajili wa Wakulima', 
        'm1_sub': 'Sajili wakulima wapya au usasishe wasifu wao',
        'm2': 'Usafirishaji na Logistiki', 
        'm2_sub': 'Tafuta wakulima na upange trekta',
        'm3': 'Seti ya Data ya Mavuno', 
        'm3_sub': 'Kagua lahajakazi ya vipimo',
        'm5': 'Huduma za MIKOPO', 
        'm5_sub': 'Tafuta wakulima na ujaze maombi ya mkopo',
        'm6': 'Usimamizi wa Hisa', 
        'm6_sub': 'Tafuta wakulima na usimamie akaunti za hisa',
        'reg_title': 'Usajili wa Wakulima', 
        'reg_sub': 'Jaza taarifa kamili za mkulima moja kwa moja kwenye Google Sheets.',
        'label_farmer_name': 'Jina Kamili la Mkulima', 
        'label_phone': 'Nambari ya Simu', 
        'label_id': 'Kitambulisho cha Taifa',
        'label_loc': 'Eneo la Shamba / Mkoa', 
        'label_size': 'Ukubwa wa Shamba (Acres)', 
        'label_crop': 'Zao Kuu Lengwa',
        'reg_btn': 'Hifadhi na Umsajili Mkulima', 
        'reg_success': 'Taarifa za mkulima zimehifadhiwa kwenye Google Sheets!', 
        'back_dash': 'Rudi kwenye Kituo Kuu',
        'loan_title': 'Ledger ya Mikopo na Mtaji', 
        'loan_sub': 'Sajili maombi ya mikopo kwa wakulima waliandikishwa.',
        'loan_amt_label': 'Kiasi cha Mkopo Unachoomba (KES)', 
        'loan_term_label': 'Muda wa Kulipa (Miezi)',
        'loan_btn': 'Wasilisha Ombi la Mkopo', 
        'loan_success': 'Ombi la mkopo limeandikishwa kwenye Google Sheets!',
        'interest_notice': 'Maombi yote yanajumuisha riba ya kudumu ya 10%.',
        'trans_title': 'Usafirishaji na Shughuli za Mitambo', 
        'trans_sub': 'Ratibu huduma za trekta kwa wakulima waliosajiliwa.',
        'label_service_type': 'Aina ya Huduma Inayohitajika', 
        'label_dispatch_date': 'Tarehe Lengwa ya Upelekaji',
        'opt_plow': 'Kutayarisha / Kulima Shamba', 
        'opt_haul': 'Kusafirisha na Kubeba Mazao', 
        'opt_harv': 'Uvunaji wa Mitambo',
        'trans_btn': 'Omba Upelekaji wa Trekta', 
        'trans_success': 'Ombi la trekta limehifadhiwa kwenye Google Sheets!',
        'shares_title': 'Sajili ya Hisa na Mtaji', 
        'shares_sub': 'Rekodi mgawo na taarifa za hisa za mkulima.',
        'label_num_shares': 'Idadi ya Hisa', 
        'label_share_val': 'Thamani ya Hisa (KES)', 
        'label_benefits': 'Manufaa Inayotarajiwa ya Mwaka (KES)',
        'shares_btn': 'Hifadhi Taarifa za Hisa', 
        'shares_success': 'Hisa zimehifadhiwa kwenye Google Sheets!',
        'about_title': 'Kuhusu E-ROFCO', 
        'about_sub': 'Chama cha Ushirika',
        'about_text': 'E-ROFCO imejitolea kuwawezesha wakulima wadogo wa kiasili kwa kutoa mifumo ya kisasa ya ushirika ya kidijitali.',
        'about_leadership': 'Uongozi Mkuu', 
        'role_chairman': 'Mwenyekiti', 
        'role_treasurer': 'Treasurer', 
        'role_secretary': 'Katibu',
        'about_partners': 'Washirika Wakuu', 
        'about_contact_title': 'Wasiliana Nasi', 
        'about_phone_label': 'Tupigie Simu',
        'about_email_label': 'Email Us', 
        'about_social_label': 'Tufuate'
    }
}

# --- GLOBAL SESSION HANDLER ---
@app.before_request
def ensure_language():
    """Ensures 'lang' is always set in session to prevent KeyError."""
    if 'lang' not in session:
        session['lang'] = 'en'

def append_to_sheet(tab_name, row_data):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_keys.json", scope)
        client = gspread.authorize(creds)
        workbook = client.open("M-ROFCO Production Yields")
        
        try:
            worksheet = workbook.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = workbook.add_worksheet(title=tab_name, rows="100", cols="10")
            
        worksheet.append_row(row_data)
        DASHBOARD_CACHE["data"] = None
        return True
    except Exception as e:
        print(f"Error appending row to Google Sheets [{tab_name}]: {e}")
        return False

def fetch_sheet_records(tab_name):
    """Helper function to read records directly from a specific Google Sheet tab."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_keys.json", scope)
        client = gspread.authorize(creds)
        workbook = client.open("M-ROFCO Production Yields")
        worksheet = workbook.worksheet(tab_name)
        return worksheet.get_all_records()
    except Exception as e:
        print(f"Error reading records from tab [{tab_name}]: {e}")
        return []

def fetch_registered_farmers():
    farmers = []
    records = fetch_sheet_records("Membership")
    if not records:
        records = fetch_sheet_records("Farm Profiles")
        
    for r in records:
        farmers.append({
            "name": r.get("NAME") or r.get("Farmer Name") or r.get("Name") or "",
            "phone": r.get("PHONE CONTACT") or r.get("Phone Number") or r.get("Contacts") or "",
            "id_no": r.get("ID") or r.get("National ID") or "",
            "location": r.get("LOCATION") or r.get("Location") or r.get("Region") or "",
            "farm_size": r.get("FARM SIZE") or r.get("SIZE") or r.get("Farm Size") or "N/A"
        })
    return farmers

@app.route('/')
def index():
    return render_template('welcome.html', texts=TEXTS[session['lang']], current_lang=session['lang'])

@app.route('/policy', methods=['GET', 'POST'])
def policy():
    error = None
    if request.method == 'POST':
        if request.form.get('accept_policy'):
            session['policy_accepted'] = True
            return redirect(url_for('login'))
        else:
            error = TEXTS[session['lang']]['error_msg']
    return render_template('policy.html', texts=TEXTS[session['lang']], current_lang=session['lang'], error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not session.get('policy_accepted'):
        return redirect(url_for('policy'))
        
    error = None
    if request.method == 'POST':
        user_pin = request.form.get('pin', '')
        authenticated_user = None
        for username, data in REGISTERED_USERS.items():
            if data['pin'] == user_pin:
                authenticated_user = data
                break
                
        if authenticated_user:
            session['user_logged_in'] = True
            session['user_username'] = username
            session['user_name'] = authenticated_user['name']
            session['user_role'] = authenticated_user.get('role', 'Staff')
            session['user_class'] = authenticated_user.get('class', 'General')
            return redirect(url_for('home'))
        else:
            error = TEXTS[session['lang']]['invalid_pin']
            
    return render_template('login.html', texts=TEXTS[session['lang']], current_lang=session['lang'], error=error)

@app.route('/home')
def home():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    current_time = time.time()
    
    if DASHBOARD_CACHE["data"] and (current_time - DASHBOARD_CACHE["last_updated"] < CACHE_TIMEOUT):
        metrics = DASHBOARD_CACHE["data"]
    else:
        metrics = {"yield_count": 0, "shareholding_count": 0, "loan_count": 0, "payment_count": 0}
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name("google_keys.json", scope)
            client = gspread.authorize(creds)
            workbook = client.open("M-ROFCO Production Yields")
            
            try: metrics["yield_count"] = len(workbook.worksheet("Membership").get_all_records())
            except: pass
            try: metrics["shareholding_count"] = len(workbook.worksheet("Shareholding Accounts").get_all_records())
            except: pass
            try: metrics["loan_count"] = len(workbook.worksheet("Short term Loans/Advances").get_all_records())
            except: pass
            try: metrics["payment_count"] = len(workbook.worksheet("Processed Payments").get_all_records())
            except: pass
                
            DASHBOARD_CACHE["data"] = metrics
            DASHBOARD_CACHE["last_updated"] = current_time
        except Exception as e:
            print(f"Metrics collection issue: {e}")

    return render_template('home.html', texts=TEXTS[session['lang']], current_lang=session['lang'], name=session.get('user_name', 'John Doe'), metrics=metrics)

@app.route('/register-farm', methods=['GET', 'POST'])
def register_farm():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    if request.method == 'POST':
        farmer_name = request.form.get('farmer_name', '')
        phone = request.form.get('phone', '')
        id_no = request.form.get('id_no', '')
        location = request.form.get('location', '')
        size = request.form.get('size', '')
        crop = request.form.get('crop', 'Sugarcane')
        
        # 1. Commit to Farm Profiles tab
        append_to_sheet("Farm Profiles", [farmer_name, phone, id_no, location, size, crop])
        
        # 2. Automatically sync directly to Membership tab under Production Yield Dataset (Including Farm Size in Column F)
        farm_size_formatted = f"{size} Acres" if size and "acre" not in size.lower() else size
        append_to_sheet("Membership", [farmer_name, phone, id_no, location, crop, farm_size_formatted])
        
        success = True

    return render_template('register_farm.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success)

@app.route('/loan-services', methods=['GET', 'POST'])
def loan_services():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    if request.method == 'POST':
        farmer_name = request.form.get('farmer_name', '')
        contacts = request.form.get('contacts', '')
        location = request.form.get('location', '')
        amount = request.form.get('amount', '')
        term = request.form.get('term', '')
        interest = f"{float(amount) * 0.10:.2f}" if amount else "0"
        date_today = time.strftime("%Y-%m-%d")
        
        row_data = [farmer_name, contacts, location, amount, interest, date_today, f"{term} Months"]
        append_to_sheet("Short term Loans/Advances", row_data)
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template('loan_services.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, farmers=farmers_list)

@app.route('/transport-logistics', methods=['GET', 'POST'])
def transport_logistics():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    if request.method == 'POST':
        farmer_name = request.form.get('farmer_name', '')
        location = request.form.get('location', '')
        service_type = request.form.get('service_type', '')
        dispatch_date = request.form.get('dispatch_date', '')
        logged_by = session.get('user_name', 'John Doe')
        
        row_data = [farmer_name, location, service_type, dispatch_date, logged_by]
        append_to_sheet("Transport Logistics", row_data)
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template('transport_logistics.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, farmers=farmers_list)

@app.route('/shares-management', methods=['GET', 'POST'])
def shares_management():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    if request.method == 'POST':
        farmer_name = request.form.get('farmer_name', '')
        num_shares = request.form.get('number_of_shares', '')
        share_value = request.form.get('shares_value', '')
        annual_benefits = request.form.get('annual_benefits', '')
        
        row_data = [farmer_name, num_shares, share_value, annual_benefits]
        append_to_sheet("Shareholding Accounts", row_data)
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template('shares_management.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, farmers=farmers_list)

@app.route('/weighbridge-tickets')
def weighbridge_tickets():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    # Read live records across all 5 dataset tabs from Google Sheets
    membership_tickets = fetch_sheet_records("Membership")
    shareholding_tickets = fetch_sheet_records("Shareholding Accounts")
    short_term_tickets = fetch_sheet_records("Short term Loans/Advances")
    long_term_tickets = fetch_sheet_records("Long term Loans/Advances")
    payment_tickets = fetch_sheet_records("Processed Payments")
    
    base_sheet_url = "https://docs.google.com/spreadsheets/d/1EwSF4aOvOqMWK52u48mmgrDIENv1izIJ7EgZMBzf4sw/htmlembed"
    sheet_urls = {
        "membership": f"{base_sheet_url}?gid=0&widget=false&headers=false",
        "shareholding": f"{base_sheet_url}?gid=1943609077&widget=false&headers=false", 
        "short_term": f"{base_sheet_url}?gid=1049826867&widget=false&headers=false",  
        "long_term": f"{base_sheet_url}?gid=1767668779&widget=false&headers=false",   
        "payment": f"{base_sheet_url}?gid=94456819&widget=false&headers=false"       
    }
    
    return render_template(
        'weighbridge_tickets.html',
        texts=TEXTS[session['lang']],
        current_lang=session['lang'],
        urls=sheet_urls,
        membership_tickets=membership_tickets,
        shareholding_tickets=shareholding_tickets,
        short_term_tickets=short_term_tickets,
        long_term_tickets=long_term_tickets,
        payment_tickets=payment_tickets,
        members=membership_tickets
    )

@app.route('/add-record', methods=['POST'])
def add_record():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    target_tab = request.form.get('target_tab')
    
    if target_tab == 'Shareholding Accounts':
        farmer_name = request.form.get('farmer_name', '')
        shares_count = request.form.get('shares_count', '')
        shares_value = request.form.get('shares_value', '')
        annual_benefits = request.form.get('annual_benefits', '')
        
        row_data = [farmer_name, shares_count, shares_value, annual_benefits]
        append_to_sheet("Shareholding Accounts", row_data)

    elif target_tab == 'Short term Loans/Advances':
        farmer_name = request.form.get('farmer_name', '')
        contacts = request.form.get('contacts', '')
        location = request.form.get('location', '')
        loan_amount = request.form.get('loan_amount', '')
        interest = request.form.get('interest', '')
        taken_date = request.form.get('taken_date', '')
        return_date = request.form.get('return_date', '')
        
        row_data = [farmer_name, contacts, location, loan_amount, interest, taken_date, return_date]
        append_to_sheet("Short term Loans/Advances", row_data)

    elif target_tab == 'Long term Loans/Advances':
        date = request.form.get('date', '')
        farmer_name = request.form.get('farmer_name', '')
        farmer_id = request.form.get('id', '')
        loan_taken = request.form.get('loan_taken', '')
        interest = request.form.get('interest', '')
        purpose = request.form.get('purpose', '')
        return_date = request.form.get('return_date', '')
        
        row_data = [date, farmer_name, farmer_id, loan_taken, interest, purpose, return_date]
        append_to_sheet("Long term Loans/Advances", row_data)

    return redirect(url_for('weighbridge_tickets'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/toggle-language')
def toggle_language():
    session['lang'] = 'sw' if session.get('lang') == 'en' else 'en'
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)