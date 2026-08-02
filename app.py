import os
import json
import time
import secrets
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)

# --- SECURITY & SECRET KEYS ---
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)

# --- URD CONFIGURATION & CONSTANTS ---
URD_CONFIG = {
    "sugarcane_price": 5500.0,
    "deduction_rate": 15.0,
    "ltv_cap": 50.0
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SPREADSHEET_ID = "1EwSF4aOvOqMWK52u48mmgrDIENv1izIJ7EgZMBzf4sw"
SPREADSHEET_NAME = "M-ROFCO Production Yields"

DASHBOARD_CACHE = {
    "data": None,
    "last_updated": 0
}
CACHE_TIMEOUT = 300  # 5 minutes

REGISTERED_USERS = {
    "emp1": {"pin": "1234", "name": "John Doe", "role": "Staff Officer", "class": "Shareholding"},
    "emp2": {"pin": "4321", "name": "John Doe", "role": "Staff Officer", "class": "General"}
}

# --- GROUNDED & HUMANIZED TEXT DICTIONARY ---
TEXTS = {
    'en': {
        'welcome': 'M-ROFCO Cooperative Portal', 
        'subtext': 'Staff ledger, weighbridge records, and field logistics.',
        'proceed': 'Verify Identity', 
        'switch_btn': 'Swahili',
        'policy_title': 'Staff Data Safeguards', 
        'policy_text': 'Please confirm you are logged in from an official co-op device and handling farmer records in compliance with M-ROFCO guidelines.',
        'agree_check': 'I confirm I am authorized to access member ledgers.', 
        'continue_btn': 'Proceed to Security Verification', 
        'error_msg': 'Please check the box to confirm authorization.',
        'login_title': 'Staff Login', 
        'login_subtext': 'Enter your 4-digit staff PIN to access management records.',
        'pin_label': 'Staff PIN', 
        'login_btn': 'Enter Portal', 
        'invalid_pin': 'Incorrect PIN. Please try again.',
        'dash_title': 'Field & Branch Hub', 
        'dash_sub': 'Active Staff Session: ', 
        'logout': 'Sign Out',
        'twende_pamoja': 'TWENDE PAMOJA • WELCOME TO M-ROFCO',
        'services_we_offer': 'Services We Offer',
        'field_operations': 'Field Operations and Highlights',
        'm1': 'Member Directory', 
        'm1_sub': 'Register new farmers or update profile details',
        'm2': 'Tractor & Machinery', 
        'm2_sub': 'Schedule field plowing and crop transport dispatches',
        'm3': 'Weighbridge & Yields', 
        'm3_sub': 'View harvest weights, delivery logs, and ledger totals',
        'm5': 'Member Advances & Loans', 
        'm5_sub': 'Process short-term inputs and credit applications',
        'm6': 'Shareholder Accounts', 
        'm6_sub': 'Manage member share capital and dividend balances',
        'reg_title': 'New Farmer Registration', 
        'reg_sub': 'Add a farmer to the official M-ROFCO registry.',
        'label_farmer_name': 'Full Name', 
        'label_phone': 'Phone Number (M-PESA)', 
        'label_id': 'National ID Number',
        'label_loc': 'Sub-County / Field Zone', 
        'label_size': 'Acreage', 
        'label_crop': 'Main Crop',
        'reg_btn': 'Save Farmer Profile', 
        'reg_success': 'Farmer registered successfully in Google Sheets!', 
        'back_dash': 'Back to Dashboard',
        'loan_title': 'Farm Credit Application', 
        'loan_sub': 'Log short-term advance requests for registered members.',
        'loan_amt_label': 'Requested Amount (KES)', 
        'loan_term_label': 'Repayment Period',
        'loan_btn': 'Submit Application', 
        'loan_success': 'Credit request recorded.',
        'interest_notice': 'Standard 10% interest rate applied automatically.',
        'trans_title': 'Tractor Dispatch Request',
        'trans_sub': 'Book machinery support for field preparation or transport.',
        'label_service_type': 'Machinery Service', 
        'label_dispatch_date': 'Requested Date',
        'opt_plow': 'Plowing / Tilling', 
        'opt_haul': 'Crop Hauling', 
        'opt_harv': 'Harvesting Support',
        'trans_btn': 'Dispatch Booking', 
        'trans_success': 'Dispatch request submitted!',
        'shares_title': 'Share Capital Account',
        'shares_sub': 'Record member share purchases and dividend eligibility.',
        'label_num_shares': 'Number of Shares', 
        'label_share_val': 'Value per Share (KES)',
        'label_benefits': 'Estimated Dividend (KES)', 
        'shares_btn': 'Update Share Account',
        'shares_success': 'Share records updated!',
        'about_title': 'About M-ROFCO Cooperative', 
        'about_sub': 'Empowering Local Smallholder Farmers',
        'about_text': 'M-ROFCO Cooperative Society Ltd is dedicated to transforming regional agriculture through mechanized farming dispatches, fair weighbridge auditing, low-interest farm advances, and transparent digital share ledger tracking.',
        'about_leadership': 'Management Team', 
        'role_chairman': 'Chairman', 
        'role_treasurer': 'Treasurer', 
        'role_secretary': 'Secretary',
        'about_partners': 'Community Partners', 
        'about_contact_title': 'Branch Contact', 
        'about_phone_label': 'Phone',
        'about_email_label': 'Email', 
        'about_social_label': 'Updates',
        'transport_logistics': 'Machinery Services',
        'membership_records': 'Registered Farmers',
        'shareholding_accounts': 'Share Accounts',
        'short_term_advances': 'Short Advances',
        'long_term_loans': 'Development Loans',
        'processed_payments': 'Payment History',
        'view_membership': 'View Members',
        'view_shareholding': 'View Shares',
        'view_short_term': 'View Loans',
        'view_long_term': 'View Capital',
        'view_payments': 'View Payments',
        'view_transport': 'View Logistics',
        'no_transport_entries': 'No tractor dispatches booked yet.',
        'master_membership_dir': 'Member Directory & Ledger',
        'direct_live_sync': 'Live view of Google Sheets records.',
        'filter_membership_records': 'Search Records',
        'search_membership_ph': 'Search by name, phone, ID, or zone...',
        'farmer_full_name': 'Member Name',
        'phone_contact': 'Phone Number',
        'national_id': 'ID Number',
        'location_region': 'Zone / Region',
        'membership_type': 'Member Type',
        'edit_live_sheet': 'Open Google Sheet',
        'edit_live_sheet_title': 'Open in Google Sheets',
        'close_panel': 'Close'
    },
    'sw': {
        'welcome': 'Tovuti ya M-ROFCO', 
        'subtext': 'Kumbukumbu za wanachama, uzani wa mazao, na mitambo.',
        'proceed': 'Thibitisha Mfanyakazi', 
        'switch_btn': 'English',
        'policy_title': 'Usalama wa Taarifa', 
        'policy_text': 'Tafadhali thibitisha unatumia kifaa rasmi cha chama kushughulikia taarifa za wakulima.',
        'agree_check': 'Ninthibitisha nina idhini ya kutazama daftari la wanachama.', 
        'continue_btn': 'Endelea kwa Uhakiki', 
        'error_msg': 'Weka alama ili kuthibitisha idhini.',
        'login_title': 'Ingia Kama Mfanyakazi', 
        'login_subtext': 'Weka PIN yako ya tarakimu 4 kuingia kwenye mfumo.',
        'pin_label': 'Nambari ya Siri (PIN)', 
        'login_btn': 'Ingia Mfomoni', 
        'invalid_pin': 'PIN si sahihi. Jaribu tena.',
        'dash_title': 'Kituo cha Shughuli za Nyanjani', 
        'dash_sub': 'Mfanyakazi Aliyeingia: ', 
        'logout': 'Toka Mfomoni',
        'twende_pamoja': 'TWENDE PAMOJA • KARIBU M-ROFCO',
        'services_we_offer': 'Huduma Tunazotoa',
        'field_operations': 'Shughuli za Nyanjani na Picha',
        'm1': 'Orodha ya Wanachama', 
        'm1_sub': 'Sajili wakulima wapya au usasishe taarifa zao',
        'm2': 'Huduma za Trekta', 
        'm2_sub': 'Panga huduma za kulima na kusafirisha mazao',
        'm3': 'Uzani na Mavuno', 
        'm3_sub': 'Tazama vipimo vya mizani na mahesabu ya mazao',
        'm5': 'Mikopo na Pembejeo', 
        'm5_sub': 'Shughulikia maombi ya mikopo ya muda mfupi',
        'm6': 'Akaunti za Hisa', 
        'm6_sub': 'Usimamizi wa hisa na gawio la wanachama',
        'reg_title': 'Usajili wa Mkulima Mpya', 
        'reg_sub': 'Ongeza mkulima kwenye daftari rasmi la M-ROFCO.',
        'label_farmer_name': 'Jina Kamili', 
        'label_phone': 'Nambari ya Simu (M-PESA)', 
        'label_id': 'Nambari ya Kitambulisho',
        'label_loc': 'Eneo / Eneo la Shamba', 
        'label_size': 'Ukubwa wa Shamba (Hekari)', 
        'label_crop': 'Zao Kuu',
        'reg_btn': 'Hifadhi Taarifa za Mkulima', 
        'reg_success': 'Mkulima amesajiliwa kwenye Google Sheets!', 
        'back_dash': 'Rudi Kituoni',
        'loan_title': 'Ombi la Mkopo wa Shamba', 
        'loan_sub': 'Andikisha maombi ya mikopo ya pembejeo kwa wanachama.',
        'loan_amt_label': 'Kiasi Kinachoombwa (KES)', 
        'loan_term_label': 'Muda wa Kulipa',
        'loan_btn': 'Wasilisha Ombi', 
        'loan_success': 'Ombi la mkopo limehifadhiwa.',
        'interest_notice': 'Riba ya kawaida ni 10%.',
        'trans_title': 'Hifadhi Huduma ya Trekta', 
        'trans_sub': 'Weka nafasi ya trekta kwa ajili ya kulima au kubeba mazao.',
        'label_service_type': 'Huduma Inayohitajika', 
        'label_dispatch_date': 'Tarehe Inayotakiwa',
        'opt_plow': 'Kutayarisha / Kulima', 
        'opt_haul': 'Kusafirisha Mazao', 
        'opt_harv': 'Kuvuna kwa Mitambo',
        'trans_btn': 'Weka Nauli/Nafasi', 
        'trans_success': 'Ombi la trekta limehifadhiwa!',
        'shares_title': 'Akaunti ya Hisa', 
        'shares_sub': 'Rekodi ununuzi wa hisa na gawio la mwanachama.',
        'label_num_shares': 'Idadi ya Hisa', 
        'label_share_val': 'Thamani ya Kila Hisa (KES)', 
        'label_benefits': 'Gawio Linalotarajiwa (KES)',
        'shares_btn': 'Hifadhi Taarifa za Hisa', 
        'shares_success': 'Taarifa za hisa zimesasishwa!',
        'about_title': 'Kuhusu Ushirika wa M-ROFCO', 
        'about_sub': 'Kuwezesha Wakulima Wadogo wa Eneo Hili',
        'about_text': 'Chama cha Ushirika cha M-ROFCO Ltd kimejitolea kubadilisha kilimo cha eneo hili kupitia huduma za mitambo, uhakiki wa uzito wa mazao, mikopo ya usaidizi, na usimamizi wa kisasa wa mtaji wa hisa.',
        'about_leadership': 'Uongozi Mkuu', 
        'role_chairman': 'Mwenyekiti', 
        'role_treasurer': 'Mwekahazina', 
        'role_secretary': 'Katibu',
        'about_partners': 'Washirika Wakuu', 
        'about_contact_title': 'Wasiliana na Tawi', 
        'about_phone_label': 'Simu',
        'about_email_label': 'Barua pepe', 
        'about_social_label': 'Taarifa',
        'transport_logistics': 'Huduma za Mitambo',
        'membership_records': 'Wanachama Waliosajiliwa',
        'shareholding_accounts': 'Akaunti za Hisa',
        'short_term_advances': 'Mikopo ya Muda Mfupi',
        'long_term_loans': 'Mikopo ya Maendeleo',
        'processed_payments': 'Kumbukumbu za Malipo',
        'view_membership': 'Tazama Wanachama',
        'view_shareholding': 'Tazama Hisa',
        'view_short_term': 'Tazama Mikopo',
        'view_long_term': 'Tazama Mtaji',
        'view_payments': 'Tazama Malipo',
        'view_transport': 'Tazama Usafirishaji',
        'no_transport_entries': 'Bado hakuna huduma za trekta zilizowekwa.',
        'master_membership_dir': 'Daftari la Wanachama',
        'direct_live_sync': 'Muonekano wa moja kwa moja wa Google Sheets.',
        'filter_membership_records': 'Tafuta Taarifa',
        'search_membership_ph': 'Tafuta kwa jina, simu, ID, au eneo...',
        'farmer_full_name': 'Jina la Mwanachama',
        'phone_contact': 'Nambari ya Simu',
        'national_id': 'Kitambulisho',
        'location_region': 'Eneo / Mkoa',
        'membership_type': 'Aina ya Mwanachama',
        'edit_live_sheet': 'Fungua Google Sheet',
        'edit_live_sheet_title': 'Fungua katika Google Sheets',
        'close_panel': 'Funga'
    }
}

# --- GOOGLE AUTHENTICATION & SHEETS HELPER ---
def get_gspread_client():
    creds = None
    if os.path.exists("google_keys.json"):
        try:
            creds = Credentials.from_service_account_file("google_keys.json", scopes=SCOPES)
        except Exception as e:
            print(f"Error loading google_keys.json: {e}")

    if not creds and os.environ.get("GOOGLE_KEYS_JSON"):
        try:
            info = json.loads(os.environ.get("GOOGLE_KEYS_JSON"))
            if "private_key" in info:
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            print(f"Error loading credentials from Environment Variable: {e}")

    if not creds:
        raise RuntimeError("No valid Google credentials found!")

    return gspread.authorize(creds)

def append_to_sheet(tab_name, row_data):
    try:
        client = get_gspread_client()
        workbook = client.open_by_key(SPREADSHEET_ID)
        
        try:
            worksheet = workbook.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = workbook.add_worksheet(title=tab_name, rows="100", cols="10")
            
        worksheet.append_row(row_data)
        DASHBOARD_CACHE["data"] = None  # Invalidate cache for instant update
        return True
    except Exception as e:
        print(f"Error appending row to Google Sheets [{tab_name}]: {e}")
        return False

def fetch_sheet_records(tab_name):
    try:
        client = get_gspread_client()
        workbook = client.open_by_key(SPREADSHEET_ID)
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

def get_gallery_photos():
    images_dir = os.path.join(app.static_folder, 'images')
    if not os.path.exists(images_dir):
        return []
        
    valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    photos = [
        f for f in os.listdir(images_dir) 
        if f.lower().endswith(valid_extensions) and not f.lower().startswith('.')
    ]
    photos.sort()
    return photos

@app.before_request
def ensure_language():
    if 'lang' not in session:
        session['lang'] = 'en'

# --- EXISTING APPLICATION ROUTES ---
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
        metrics = {"yield_count": 0, "shareholding_count": 0, "loan_count": 0, "payment_count": 0, "transport_count": 0}
        try:
            client = get_gspread_client()
            workbook = client.open_by_key(SPREADSHEET_ID)
            
            try: metrics["yield_count"] = len(workbook.worksheet("Membership").get_all_records())
            except: pass
            try: metrics["shareholding_count"] = len(workbook.worksheet("Shareholding Accounts").get_all_records())
            except: pass
            try: metrics["loan_count"] = len(workbook.worksheet("Short term Loans/Advances").get_all_records())
            except: pass
            try: metrics["payment_count"] = len(workbook.worksheet("Processed Payments").get_all_records())
            except: pass
            try: metrics["transport_count"] = len(workbook.worksheet("Transport Logistics").get_all_records())
            except: pass
                
            DASHBOARD_CACHE["data"] = metrics
            DASHBOARD_CACHE["last_updated"] = current_time
        except Exception as e:
            print(f"Metrics collection issue: {e}")

    photos = get_gallery_photos()

    return render_template(
        'home.html', 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'], 
        name=session.get('user_name', 'John Doe'), 
        metrics=metrics,
        photos=photos[:4]
    )

@app.route('/gallery')
def gallery():
    photos = get_gallery_photos()
    return render_template('gallery.html', texts=TEXTS[session['lang']], current_lang=session['lang'], photos=photos)

@app.route('/about')
def about():
    return render_template('about_us.html', texts=TEXTS[session['lang']], current_lang=session['lang'])

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
        
        append_to_sheet("Farm Profiles", [farmer_name, phone, id_no, location, size, crop])
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
@app.route('/production-yields')
def weighbridge_tickets():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    membership_tickets = fetch_sheet_records("Membership")
    shareholding_tickets = fetch_sheet_records("Shareholding Accounts")
    short_term_tickets = fetch_sheet_records("Short term Loans/Advances")
    long_term_tickets = fetch_sheet_records("Long term Loans/Advances")
    payment_tickets = fetch_sheet_records("Processed Payments")
    transport_tickets = fetch_sheet_records("Transport Logistics")
    
    base_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
    sheet_urls = {
        "membership": f"{base_url}#gid=0",
        "shareholding": f"{base_url}#gid=1943609077", 
        "short_term": f"{base_url}#gid=1049826867",  
        "long_term": f"{base_url}#gid=1767668779",   
        "payment": f"{base_url}#gid=94456819",
        "transport": f"{base_url}#gid=284019284"
    }
    
    return render_template(
        'weighbridge_tickets.html',
        texts=TEXTS[session['lang']],
        current_lang=session['lang'],
        sheet_urls=sheet_urls,
        membership_tickets=membership_tickets,
        shareholding_tickets=shareholding_tickets,
        short_term_tickets=short_term_tickets,
        long_term_tickets=long_term_tickets,
        payment_tickets=payment_tickets,
        transport_tickets=transport_tickets,
        members=membership_tickets,
        spreadsheet_id=SPREADSHEET_ID
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

    elif target_tab == 'Transport Logistics':
        farmer_name = request.form.get('farmer_name', '')
        location = request.form.get('location', '')
        service_type = request.form.get('service_type', '')
        dispatch_date = request.form.get('dispatch_date', '')
        logged_by = session.get('user_name', 'John Doe')
        row_data = [farmer_name, location, service_type, dispatch_date, logged_by]
        append_to_sheet("Transport Logistics", row_data)

    return redirect(url_for('weighbridge_tickets'))

# --- URD WORKFLOW & ADMIN ROUTES ---
@app.route('/staff/loan-intake')
def staff_loan_intake():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    return render_template(
        'staff_loan_intake.html', 
        active_role='intake', 
        name=session.get('user_name', 'Call Center Agent'), 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        config=URD_CONFIG
    )

@app.route('/staff/field-assessor')
def staff_field_assessor():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    return render_template(
        'staff_field_assessor.html', 
        active_role='assessor', 
        name=session.get('user_name', 'Field Agronomist'),
        texts=TEXTS[session['lang']], 
        current_lang=session['lang']
    )

@app.route('/staff/credit-committee')
def staff_credit_committee():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    
    pending_applications = [
        {
            "id": "APP-2026-001",
            "member_name": "Ogutu Nyo",
            "member_id": "28491032",
            "zone": "Kibos Sector",
            "acreage": 4.5,
            "crop_health": "Grade A (>35 Tons/Acre)",
            "gross_valuation": 866250,
            "net_valuation": 736312,
            "max_cap": 368156,
            "requested_amount": 420000,
            "purpose": "Mechanized Tractor Tillage & Fertilizer",
            "status": "Pending Committee Review"
        }
    ]
    return render_template(
        'staff_credit_committee.html', 
        active_role='committee', 
        name=session.get('user_name', 'Committee Chair'), 
        applications=pending_applications,
        texts=TEXTS[session['lang']], 
        current_lang=session['lang']
    )

@app.route('/staff/credit-committee/action', methods=['POST'])
def credit_committee_action():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    app_id = request.form.get('app_id', '')
    member_name = request.form.get('member_name', '')
    action = request.form.get('action', '')
    approved_amount_raw = request.form.get('approved_amount', '0')
    notes = request.form.get('notes', '')
    reviewer = session.get('user_name', 'Committee Officer')
    date_today = time.strftime("%Y-%m-%d %H:%M")

    try:
        approved_amount = float(approved_amount_raw)
    except ValueError:
        approved_amount = 0.0

    status_map = {
        'approve': 'Approved (Standard Cap)',
        'override': 'Approved (Management Override)',
        'reject': 'Rejected by Committee'
    }
    final_status = status_map.get(action, 'Pending')

    # Log action to audit sheet
    audit_row = [date_today, app_id, member_name, final_status, approved_amount, reviewer, notes]
    append_to_sheet("Loan Committee Audit Log", audit_row)

    # If approved, post to Short term Loans/Advances ledger
    if action in ['approve', 'override']:
        interest = f"{approved_amount * 0.10:.2f}"
        loan_row = [member_name, "N/A", "N/A", str(approved_amount), interest, date_today[:10], "12 Months", final_status]
        append_to_sheet("Short term Loans/Advances", loan_row)

    return redirect(url_for('staff_credit_committee'))

@app.route('/admin/config', methods=['GET', 'POST'])
def admin_config():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        URD_CONFIG["sugarcane_price"] = float(request.form.get('sugarcane_price', 5500))
        URD_CONFIG["deduction_rate"] = float(request.form.get('deduction_rate', 15))
        URD_CONFIG["ltv_cap"] = float(request.form.get('ltv_cap', 50))
        return redirect(url_for('admin_config'))
        
    return render_template(
        'admin_config.html', 
        active_role='admin', 
        name=session.get('user_name', 'Admin'), 
        config=URD_CONFIG,
        texts=TEXTS[session['lang']], 
        current_lang=session['lang']
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/toggle-language')
def toggle_language():
    session['lang'] = 'sw' if session.get('lang') == 'en' else 'en'
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)