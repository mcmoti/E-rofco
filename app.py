import os
import json
import time
import secrets
import sqlite3
import urllib.parse
import csv
from io import StringIO
import pandas as pd
import requests
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

app = Flask(__name__)

# --- SECURITY & SECRET KEYS ---
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)

# --- DATABASE CONFIGURATION (PHASE 3) ---
DATABASE = os.path.join(app.root_path, 'sacco_portal.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database schema if tables do not exist."""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                member_name TEXT NOT NULL,
                member_id TEXT NOT NULL,
                zone TEXT,
                acreage REAL,
                requested_amount REAL,
                purpose TEXT,
                crop_health TEXT DEFAULT 'Pending Inspection',
                estimated_tonnage REAL DEFAULT 0.0,
                gross_valuation REAL DEFAULT 0.0,
                net_valuation REAL DEFAULT 0.0,
                max_cap REAL DEFAULT 0.0,
                approved_amount REAL DEFAULT 0.0,
                gps_coordinates TEXT DEFAULT 'Not Tagged',
                photo TEXT,
                status TEXT DEFAULT 'Pending Assessment',
                committee_notes TEXT,
                guarantor_name TEXT,
                guarantor_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS staff_users (
                username TEXT PRIMARY KEY,
                pin TEXT,
                password_hash TEXT,
                name TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS password_change_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                new_password_hash TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_funds (
                id INTEGER PRIMARY KEY,
                available_balance REAL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fund_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requested_by TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS credit_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                member_name TEXT,
                action TEXT,
                approved_amount REAL,
                committee_notes TEXT,
                processed_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM applications")
        if cursor.fetchone()[0] == 0:
            conn.execute('''
                INSERT INTO applications (
                    id, member_name, member_id, zone, acreage, requested_amount, 
                    purpose, crop_health, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                "APP-2026-001", "Ogutu Nyo", "28491032", "Kibos Sector", 
                4.5, 350000.0, "Mechanized Tractor Tillage & Fertilizer", 
                "Pending Inspection", "Pending Assessment"
            ))
            conn.commit()

        # Try to alter table if columns don't exist
        try:
            conn.execute("ALTER TABLE applications ADD COLUMN guarantor_name TEXT")
            conn.execute("ALTER TABLE applications ADD COLUMN guarantor_id TEXT")
        except sqlite3.OperationalError:
            pass
            
        try:
            conn.execute("ALTER TABLE applications ADD COLUMN loan_type TEXT DEFAULT 'Long-Term'")
        except sqlite3.OperationalError:
            pass
            
            
        try:
            conn.execute("ALTER TABLE staff_users ADD COLUMN password_hash TEXT")
            default_pw = generate_password_hash('Mrofco2026')
            conn.execute("UPDATE staff_users SET password_hash = ?", (default_pw,))
        except sqlite3.OperationalError:
            pass

        cursor.execute("SELECT COUNT(*) FROM staff_users")
        if cursor.fetchone()[0] == 0:
            default_pw = generate_password_hash('Mrofco2026')
            conn.executemany('''
                INSERT INTO staff_users (username, pin, password_hash, name, role) VALUES (?, ?, ?, ?, ?)
            ''', [
                ('intake1', '1000', default_pw, 'Alice (Intake)', 'Intake Agent'),
                ('assessor1', '2000', default_pw, 'Bob (Assessor)', 'Field Assessor'),
                ('committee1', '3000', default_pw, 'Charlie (Committee)', 'Committee Member'),
                ('admin1', '4000', default_pw, 'Dave (Admin)', 'System Admin')
            ])
            conn.commit()
            
        cursor.execute("SELECT COUNT(*) FROM system_funds")
        if cursor.fetchone()[0] == 0:
            conn.execute("INSERT INTO system_funds (id, available_balance) VALUES (1, 0.0)")
            conn.commit()

init_db()

# --- UPLOAD CONFIGURATION (PHASE 2) ---
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'inspections')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- URD CONFIGURATION & CONSTANTS ---
URD_CONFIG = {
    "sugarcane_price": 5500.0,
    "deduction_rate": 15.0,
    "ltv_cap": 50.0
}

SPREADSHEET_ID = "1EwSF4aOvOqMWK52u48mmgrDIENv1izIJ7EgZMBzf4sw"
SPREADSHEET_NAME = "M-ROFCO Production Yields"

DASHBOARD_CACHE = {
    "data": None,
    "last_updated": 0
}
CACHE_TIMEOUT = 300  # 5 minutes cache

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
        'reg_success': 'Farmer profile logged successfully!', 
        'back_dash': 'Back to Dashboard',
        'loan_title': 'Farm Credit Application', 
        'loan_sub': 'Log short-term advance requests for registered members.',
        'loan_amt_label': 'Requested Amount (KES)', 
        'loan_term_label': 'Repayment Period',
        'loan_btn': 'Submit Application', 
        'loan_success': 'Credit request recorded successfully.',
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
        'reg_success': 'Mkulima amesajiliwa!', 
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

# --- AUTOMATED LIVE CSV SHEET HELPER ---
def fetch_sheet_records(tab_name):
    encoded_tab = urllib.parse.quote(tab_name)
    csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_tab}"
    
    try:
        df = pd.read_csv(csv_url)
        df = df.fillna('')
        records = df.to_dict(orient="records")
        return records
    except Exception as e:
        print(f"DEBUG ERROR [{tab_name}]: Failed to fetch CSV records - {e}")
        return []

def fetch_registered_farmers():
    farmers = []
    records = fetch_sheet_records("Membership")
        
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

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('user_logged_in'):
                return redirect(url_for('login'))
            if session.get('user_role') not in roles and 'System Admin' not in roles:
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- APPLICATION ROUTES ---
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
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM staff_users WHERE username = ?", (username,))
            authenticated_user = cursor.fetchone()
                
        if authenticated_user and check_password_hash(authenticated_user['password_hash'], password):
            session['user_logged_in'] = True
            session['user_username'] = authenticated_user['username']
            session['user_name'] = authenticated_user['name']
            session['user_role'] = authenticated_user['role']
            return redirect(url_for('home'))
        else:
            error = "Invalid username or password. Please try again."
            
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
            metrics["yield_count"] = len(fetch_sheet_records("Membership"))
            metrics["shareholding_count"] = len(fetch_sheet_records("Shareholding Accounts"))
            metrics["loan_count"] = len(fetch_sheet_records("Short term Loans/Advances"))
            metrics["payment_count"] = len(fetch_sheet_records("Processed Payments"))
            metrics["transport_count"] = len(fetch_sheet_records("Transport Logistics"))
                
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
    error = None
    if request.method == 'POST':
        success = True

    return render_template('register_farm.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, error=error)

@app.route('/loan-services', methods=['GET', 'POST'])
def loan_services():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    error = None
    if request.method == 'POST':
        app_id = f"APP-2026-{int(time.time()) % 10000:04d}"
        farmer_name = request.form.get('farmer_name')
        contacts = request.form.get('contacts')
        location = request.form.get('location')
        amount = float(request.form.get('amount', 0.0))
        term = request.form.get('term')
        term_unit = request.form.get('term_unit', 'Months')
        
        with get_db() as conn:
            conn.execute('''
                INSERT INTO applications (
                    id, member_name, member_id, zone, acreage, requested_amount, purpose, 
                    estimated_tonnage, gross_valuation, net_valuation, max_cap, status, committee_notes, loan_type
                ) VALUES (?, ?, ?, ?, 0.0, ?, 'Input Micro-Loan', 0.0, 0.0, 0.0, ?, 'Pending Committee Review', ?, 'Short-Term')
            ''', (app_id, farmer_name, contacts, location, amount, amount, f"Term: {term} {term_unit}"))
            conn.commit()
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template('loan_services.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, error=error, farmers=farmers_list)

@app.route('/transport-logistics', methods=['GET', 'POST'])
def transport_logistics():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    error = None
    if request.method == 'POST':
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template('transport_logistics.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, error=error, farmers=farmers_list)

@app.route('/weighbridge-tickets/download-pdf')
def download_weighbridge_pdf():
    records = fetch_sheet_records("WeighbridgeTickets")
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="M-ROFCO - Weighbridge Tickets Report", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    for row in records:
        text = f"Ticket: {row.get('TicketNumber','')} | Date: {row.get('Date','')} | Farmer: {row.get('FarmerName','')} | Net Wt: {row.get('NetWeight','')} | Zone: {row.get('Zone','')}"
        pdf.cell(0, 8, txt=text, ln=True)
        
    pdf_path = os.path.join(app.root_path, 'static', 'weighbridge_report.pdf')
    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name="Weighbridge_Report.pdf")

@app.route('/shares-management', methods=['GET', 'POST'])
def shares_management():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success = False
    error = None
    if request.method == 'POST':
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template('shares_management.html', texts=TEXTS[session['lang']], current_lang=session['lang'], success=success, error=error, farmers=farmers_list)

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
    
    return render_template(
        'weighbridge_tickets.html',
        texts=TEXTS[session['lang']],
        current_lang=session['lang'],
        membership_tickets=membership_tickets,
        shareholding_tickets=shareholding_tickets,
        short_term_tickets=short_term_tickets,
        long_term_tickets=long_term_tickets,
        payment_tickets=payment_tickets,
        transport_tickets=transport_tickets,
        spreadsheet_id=SPREADSHEET_ID
    )

# --- URD WORKFLOW & ADMIN ROUTES WITH SQLITE PERSISTENCE ---
@app.route('/staff/loan-intake', methods=['GET', 'POST'])
@role_required('Intake Agent')
def staff_loan_intake():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    
    success_msg = None
    if request.method == 'POST':
        app_id = f"APP-2026-{int(time.time()) % 10000:04d}"
        member_name = request.form.get('member_name')
        member_id = request.form.get('member_id')
        zone = request.form.get('zone')
        acreage = float(request.form.get('acreage', 0.0))
        requested_amount = float(request.form.get('requested_amount', 0.0))
        purpose = request.form.get('purpose')
        term = request.form.get('term', '')
        term_unit = request.form.get('term_unit', 'Months')
        guarantor_name = request.form.get('guarantor_name')
        guarantor_id = request.form.get('guarantor_id')

        membership_records = fetch_sheet_records("Membership")
        total_tonnage = 0.0
        
        for r in membership_records:
            r_name = str(r.get("NAME") or r.get("Farmer Name") or r.get("Name") or "").strip().lower()
            r_id = str(r.get("ID") or r.get("National ID") or "").strip()
            
            if (member_id and r_id == str(member_id).strip()) or (member_name and r_name == str(member_name).strip().lower()):
                raw_yield = r.get("YIELD (TONS)") or r.get("Yield") or r.get("Tonnage") or 0.0
                try:
                    total_tonnage += float(raw_yield)
                except ValueError:
                    pass

        gross_val = total_tonnage * URD_CONFIG['sugarcane_price']

        with get_db() as conn:
            conn.execute('''
                INSERT INTO applications (
                    id, member_name, member_id, zone, acreage, requested_amount, purpose, 
                    estimated_tonnage, gross_valuation, status, guarantor_name, guarantor_id, loan_type, committee_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending Field Assessment', ?, ?, 'Long-Term', ?)
            ''', (app_id, member_name, member_id, zone, acreage, requested_amount, purpose, total_tonnage, gross_val, guarantor_name, guarantor_id, f"Requested Term: {term} {term_unit}"))
            conn.commit()

        success_msg = f"Loan application {app_id} created with auto-calculated yield ({total_tonnage} tons, KES {gross_val:,.2f}) and queued for field assessment!"

    return render_template(
        'staff_loan_intake.html', 
        active_role='intake', 
        name=session.get('user_name', 'Call Center Agent'), 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        config=URD_CONFIG,
        success_msg=success_msg
    )

@app.route('/staff/field-assessor', methods=['GET', 'POST'])
@role_required('Field Assessor')
def staff_field_assessor():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    
    success_msg = None
    if request.method == 'POST':
        app_id = request.form.get('app_id')
        tons_per_acre = float(request.form.get('tons_per_acre', 35.0))
        crop_health = request.form.get('crop_health', 'Grade A')
        latitude = request.form.get('latitude', '')
        longitude = request.form.get('longitude', '')
        
        photo_filename = None
        if 'inspection_photo' in request.files:
            file = request.files['inspection_photo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{app_id}_{int(time.time())}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_filename = filename

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT acreage FROM applications WHERE id = ?", (app_id,))
            row = cursor.fetchone()

            if row:
                acreage = row['acreage']
                tot_tonnage = acreage * tons_per_acre
                gross_val = tot_tonnage * URD_CONFIG['sugarcane_price']
                net_val = gross_val * (1 - (URD_CONFIG['deduction_rate'] / 100))
                max_cap = net_val * (URD_CONFIG['ltv_cap'] / 100)
                gps_coords = f"{latitude}, {longitude}" if latitude and longitude else "Not Tagged"

                if photo_filename:
                    conn.execute('''
                        UPDATE applications 
                        SET crop_health = ?, estimated_tonnage = ?, gross_valuation = ?, 
                            net_valuation = ?, max_cap = ?, gps_coordinates = ?, 
                            photo = ?, status = 'Pending Committee Review', updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (crop_health, tot_tonnage, gross_val, net_val, max_cap, gps_coords, photo_filename, app_id))
                else:
                    conn.execute('''
                        UPDATE applications 
                        SET crop_health = ?, estimated_tonnage = ?, gross_valuation = ?, 
                            net_valuation = ?, max_cap = ?, gps_coordinates = ?, 
                            status = 'Pending Committee Review', updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (crop_health, tot_tonnage, gross_val, net_val, max_cap, gps_coords, app_id))

                conn.commit()
                success_msg = f"Field assessment & GPS geotag saved for application {app_id}!"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM applications WHERE status IN ('Pending Assessment', 'Pending Field Assessment')")
        pending_apps = [dict(row) for row in cursor.fetchall()]

    return render_template(
        'staff_field_assessor.html', 
        active_role='assessor', 
        name=session.get('user_name', 'Field Agronomist'),
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        pending_apps=pending_apps,
        success_msg=success_msg
    )

@app.route('/staff/credit-committee')
@role_required('Committee Member')
def staff_credit_committee():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM applications WHERE status = 'Pending Committee Review'")
        pending_committee_apps = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT available_balance FROM system_funds WHERE id = 1")
        row = cursor.fetchone()
        available_balance = row['available_balance'] if row else 0.0

    error_msg = request.args.get('error')
    receipt_app_id = request.args.get('receipt_app_id')

    return render_template(
        'staff_credit_committee.html', 
        active_role='committee', 
        name=session.get('user_name', 'Committee Chair'), 
        applications=pending_committee_apps,
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        available_balance=available_balance,
        error_msg=error_msg,
        receipt_app_id=receipt_app_id
    )

@app.route('/staff/credit-committee/action', methods=['POST'])
@role_required('Committee Member')
def credit_committee_action():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    app_id = request.form.get('app_id')
    action = request.form.get('action')
    notes = request.form.get('notes', '')

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT requested_amount, max_cap, member_name FROM applications WHERE id = ?", (app_id,))
        app_row = cursor.fetchone()
        
        cursor.execute("SELECT available_balance FROM system_funds WHERE id = 1")
        row = cursor.fetchone()
        available_balance = row['available_balance'] if row else 0.0

        if app_row:
            req_amt = app_row['requested_amount']
            max_cap = app_row['max_cap']

            if action == 'approve':
                new_status = 'Approved'
                approved_val = max_cap
            elif action == 'override':
                new_status = 'Approved (Override)'
                approved_val = req_amt
            else:
                new_status = 'Rejected'
                approved_val = 0.0
                
            if action in ['approve', 'override']:
                if approved_val > available_balance:
                    return redirect(url_for('staff_credit_committee', error="Insufficient funds to approve this loan."))
                conn.execute("UPDATE system_funds SET available_balance = available_balance - ? WHERE id = 1", (approved_val,))

            conn.execute('''
                UPDATE applications 
                SET status = ?, approved_amount = ?, committee_notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, approved_val, notes, app_id))
            
            # Generate receipt record
            conn.execute('''
                INSERT INTO credit_receipts (app_id, member_name, action, approved_amount, committee_notes, processed_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (app_id, app_row['member_name'], action.upper(), approved_val, notes, session.get('user_username')))
            
            conn.commit()

        return redirect(url_for('staff_credit_committee', success_msg=f"Application {app_id} processed successfully.", receipt_app_id=app_id))

@app.route('/committee/download-receipt/<app_id>')
@role_required('Committee Member', 'System Admin')
def download_receipt(app_id):
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM credit_receipts WHERE app_id = ? ORDER BY id DESC LIMIT 1", (app_id,))
        receipt = cursor.fetchone()
        
    if not receipt:
        return "Receipt not found", 404
        
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="M-ROFCO Hub - Credit Committee Receipt", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Receipt ID: REC-{receipt['id']:04d}", ln=True)
    pdf.cell(200, 10, txt=f"Application ID: {receipt['app_id']}", ln=True)
    pdf.cell(200, 10, txt=f"Member Name: {receipt['member_name']}", ln=True)
    pdf.cell(200, 10, txt=f"Action Taken: {receipt['action']}", ln=True)
    pdf.cell(200, 10, txt=f"Approved Amount: KES {receipt['approved_amount']:,.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Processed By: {receipt['processed_by']}", ln=True)
    pdf.cell(200, 10, txt=f"Date: {receipt['created_at']}", ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Committee Notes/Justification:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=str(receipt['committee_notes']))
    
    pdf_path = os.path.join(app.root_path, 'static', f'receipt_{app_id}.pdf')
    pdf.output(pdf_path)
    
    return send_file(pdf_path, as_attachment=True)

@app.route('/staff/request-password-change', methods=['GET', 'POST'])
def request_password_change():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success_msg = None
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        new_password_hash = generate_password_hash(new_password)
        username = session.get('user_username')
        with get_db() as conn:
            conn.execute('''
                INSERT INTO password_change_requests (username, new_password_hash) VALUES (?, ?)
            ''', (username, new_password_hash))
            conn.commit()
        success_msg = "Password change request submitted for committee approval."

    return render_template(
        'request_password_change.html', 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        success_msg=success_msg
    )

@app.route('/committee/password-requests', methods=['GET', 'POST'])
@role_required('Committee Member', 'System Admin')
def password_requests():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        req_id = request.form.get('request_id')
        action = request.form.get('action')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM password_change_requests WHERE id = ?", (req_id,))
            req = cursor.fetchone()
            
            if req and action == 'approve':
                conn.execute("UPDATE staff_users SET password_hash = ? WHERE username = ?", (req['new_password_hash'], req['username']))
                conn.execute("UPDATE password_change_requests SET status = 'Approved' WHERE id = ?", (req_id,))
            elif req and action == 'reject':
                conn.execute("UPDATE password_change_requests SET status = 'Rejected' WHERE id = ?", (req_id,))
                
            conn.commit()
            
        return redirect(url_for('password_requests'))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM password_change_requests WHERE status = 'Pending'")
        requests = cursor.fetchall()
        
    return render_template(
        'password_requests.html', 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        requests=requests
    )

@app.route('/committee/create-staff', methods=['GET', 'POST'])
@role_required('Committee Member', 'System Admin')
def create_staff():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success_msg = None
    error_msg = None
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name')
        role = request.form.get('role')
        
        if role == 'System Admin' and session.get('user_role') != 'System Admin':
            error_msg = "Only System Admins can create new System Admin accounts."
        else:
            default_pw = generate_password_hash('Mrofco2026')
            try:
                with get_db() as conn:
                    conn.execute('''
                        INSERT INTO staff_users (username, password_hash, name, role) 
                        VALUES (?, ?, ?, ?)
                    ''', (username, default_pw, name, role))
                    conn.commit()
                success_msg = f"Staff account '{username}' created successfully with default password 'Mrofco2026'."
            except sqlite3.IntegrityError:
                error_msg = "Username already exists."

    return render_template(
        'create_staff.html', 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        success_msg=success_msg,
        error_msg=error_msg
    )

@app.route('/committee/fund-requests', methods=['GET', 'POST'])
@role_required('Committee Member', 'System Admin')
def fund_requests():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    success_msg = None
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0.0))
        username = session.get('user_username')
        with get_db() as conn:
            conn.execute("INSERT INTO fund_requests (requested_by, amount) VALUES (?, ?)", (username, amount))
            conn.commit()
        success_msg = f"Fund request for KES {amount:,.0f} submitted to admin."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fund_requests WHERE status = 'Pending'")
        pending_requests = cursor.fetchall()
        cursor.execute("SELECT available_balance FROM system_funds WHERE id = 1")
        row = cursor.fetchone()
        available_balance = row['available_balance'] if row else 0.0

    return render_template(
        'fund_requests.html', 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        success_msg=success_msg,
        requests=pending_requests,
        available_balance=available_balance
    )

@app.route('/admin/approve-funds', methods=['GET', 'POST'])
@role_required('System Admin')
def admin_approve_funds():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        req_id = request.form.get('request_id')
        action = request.form.get('action')
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM fund_requests WHERE id = ?", (req_id,))
            req = cursor.fetchone()
            
            if req and action == 'approve':
                conn.execute("UPDATE system_funds SET available_balance = available_balance + ? WHERE id = 1", (req['amount'],))
                conn.execute("UPDATE fund_requests SET status = 'Approved' WHERE id = ?", (req_id,))
            elif req and action == 'reject':
                conn.execute("UPDATE fund_requests SET status = 'Rejected' WHERE id = ?", (req_id,))
                
            conn.commit()
            
        return redirect(url_for('admin_approve_funds'))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fund_requests WHERE status = 'Pending'")
        requests = cursor.fetchall()
        
    return render_template(
        'admin_approve_funds.html', 
        texts=TEXTS[session['lang']], 
        current_lang=session['lang'],
        requests=requests
    )

# --- EXPORT ROUTE FOR EXCEL / CSV DOWNLOAD ---
@app.route('/admin/export-applications-csv')
@role_required('System Admin', 'Committee Member')
def export_applications_csv():
    if not session.get('user_logged_in'):
        return redirect(url_for('login'))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM applications ORDER BY created_at DESC")
        apps = cursor.fetchall()

    si = StringIO()
    writer = csv.writer(si)
    
    writer.writerow([
        'Application ID', 'Member Name', 'Member ID', 'Zone', 'Acreage', 
        'Requested Amount', 'Purpose', 'Crop Health', 'Estimated Tonnage', 
        'Gross Valuation', 'Net Valuation', 'Max Loan Cap', 'Approved Amount', 
        'GPS Coordinates', 'Status', 'Committee Notes', 'Created At', 'Updated At'
    ])
    
    for app in apps:
        writer.writerow([
            app['id'], app['member_name'], app['member_id'], app['zone'], app['acreage'],
            app['requested_amount'], app['purpose'], app['crop_health'], app['estimated_tonnage'],
            app['gross_valuation'], app['net_valuation'], app['max_cap'], app['approved_amount'],
            app['gps_coordinates'], app['status'], app['committee_notes'], app['created_at'], app['updated_at']
        ])

    output = si.getvalue()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=m_rofco_loan_applications.csv"}
    )

@app.route('/admin/config', methods=['GET', 'POST'])
@role_required('System Admin')
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

@app.route('/shares-management/download-pdf')
def download_shares_pdf():
    records = fetch_sheet_records("ShareCapital")
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="M-ROFCO - Shares Management Report", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    for row in records:
        text = f"Date: {row.get('Date','')} | Name: {row.get('MemberName','')} | Shares: {row.get('TotalShares','')} | Value: KES {row.get('ShareValue','')}"
        pdf.cell(0, 8, txt=text, ln=True)
        
    pdf_path = os.path.join(app.root_path, 'static', 'shares_report.pdf')
    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name="Shares_Report.pdf")

if __name__ == '__main__':
    app.run(debug=True, port=5000)