import os
import time
from datetime import datetime, timedelta
import secrets
import sqlite3
import urllib.parse
import csv
from io import StringIO
import pandas as pd
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    Response,
    send_file,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- SECURITY & SECRET KEYS ---
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

# --- DATABASE CONFIGURATION (PHASE 1) ---
from config import Config
from models import (
    db,
    Branch,
    User,
    Application,
    PasswordChangeRequest,
    SystemFund,
    FundRequest,
    CreditReceipt,
    ShareTransaction,
    Farmer,
    TransportDispatch,
    LedgerEntry,
    HarvestingDisbursement,
)

app.config.from_object(Config)
db.init_app(app)


# --- DYNAMIC INTEREST CRON JOB ---
def calculate_overdue_interest():
    """Background task to apply flat-fee interest on overdue short-term advances."""
    with app.app_context():
        overdue_apps = Application.query.filter(
            Application.status == "Approved",
            Application.loan_type == "Short-Term",
            Application.expected_return_date < datetime.utcnow(),
        ).all()

        for app_record in overdue_apps:
            # For simplicity, if interest_applied is 0, we apply the flat fee ONCE when it becomes overdue.
            if app_record.interest_applied == 0:
                fee = 500.0  # flat fee penalty
                app_record.interest_applied = fee
                app_record.approved_amount += fee  # Adjust the required payback amount

                print(
                    f"Applied KES {fee} flat fee penalty to Overdue Application {app_record.id}"
                )

        db.session.commit()


scheduler = BackgroundScheduler()
scheduler.add_job(
    func=calculate_overdue_interest, trigger="interval", minutes=60
)  # Runs every hour
scheduler.start()

# Stop scheduler when exiting
import atexit

atexit.register(lambda: scheduler.shutdown())


def get_db():
    # Temporary shim for gradual migration
    conn = sqlite3.connect(
        app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    )
    conn.row_factory = sqlite3.Row
    return conn


@app.context_processor
def inject_layout():
    role = session.get("user_role")
    if role == "Intake Agent":
        return {"layout_template": "base_intake.html"}
    elif role == "Committee Member":
        return {"layout_template": "base_committee.html"}
    elif role == "Field Assessor":
        return {"layout_template": "base_assessor.html"}
    elif role == "System Admin":
        return {"layout_template": "base_admin.html"}
    return {"layout_template": "base_intake.html"}  # Fallback


def init_db():
    """Initializes the database schema using SQLAlchemy."""
    with app.app_context():
        db.create_all()

        # Seed default fund
        if not SystemFund.query.first():
            db.session.add(SystemFund(id=1, available_balance=0.0))
            db.session.commit()

        # Seed default users
        if not User.query.first():
            default_pw = generate_password_hash("Mrofco2026")
            users = [
                User(
                    username="intake1",
                    pin="1000",
                    password_hash=default_pw,
                    name="Alice (Intake)",
                    role="Intake Agent",
                ),
                User(
                    username="assessor1",
                    pin="2000",
                    password_hash=default_pw,
                    name="Bob (Assessor)",
                    role="Field Assessor",
                ),
                User(
                    username="committee1",
                    pin="3000",
                    password_hash=default_pw,
                    name="Charlie (Committee)",
                    role="Committee Member",
                ),
                User(
                    username="admin1",
                    pin="4000",
                    password_hash=default_pw,
                    name="System Admin",
                    role="System Admin",
                ),
            ]
            db.session.add_all(users)
            db.session.commit()

        # Seed default application
        if not Application.query.first():
            app1 = Application(
                id="APP-2026-001",
                member_name="Ogutu Nyo",
                member_id="28491032",
                zone="Kibos Sector",
                acreage=4.5,
                requested_amount=350000.0,
                purpose="Mechanized Tractor Tillage & Fertilizer",
                crop_health="Pending Inspection",
                status="Pending Assessment",
            )
            db.session.add(app1)
            db.session.commit()


init_db()

# --- UPLOAD CONFIGURATION (PHASE 2) ---
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "inspections")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --- URD CONFIGURATION & CONSTANTS ---
URD_CONFIG = {"sugarcane_price": 5500.0, "deduction_rate": 15.0, "ltv_cap": 50.0}

SPREADSHEET_ID = "1EwSF4aOvOqMWK52u48mmgrDIENv1izIJ7EgZMBzf4sw"
SPREADSHEET_NAME = "M-ROFCO Production Yields"

DASHBOARD_CACHE = {"data": None, "last_updated": 0}
CACHE_TIMEOUT = 300  # 5 minutes cache

# --- GROUNDED & HUMANIZED TEXT DICTIONARY ---
TEXTS = {
    "en": {
        "welcome": "M-ROFCO Cooperative Portal",
        "subtext": "Staff ledger, weighbridge records, and field logistics.",
        "proceed": "Verify Identity",
        "switch_btn": "Swahili",
        "policy_title": "Staff Data Safeguards",
        "policy_text": "Please confirm you are logged in from an official co-op device and handling farmer records in compliance with M-ROFCO guidelines.",
        "agree_check": "I confirm I am authorized to access member ledgers.",
        "continue_btn": "Proceed to Security Verification",
        "error_msg": "Please check the box to confirm authorization.",
        "login_title": "Staff Login",
        "login_subtext": "Enter your 4-digit staff PIN to access management records.",
        "pin_label": "Staff PIN",
        "login_btn": "Enter Portal",
        "invalid_pin": "Incorrect PIN. Please try again.",
        "dash_title": "Field & Branch Hub",
        "dash_sub": "Active Staff Session: ",
        "logout": "Sign Out",
        "twende_pamoja": "TWENDE PAMOJA • WELCOME TO M-ROFCO",
        "services_we_offer": "Services We Offer",
        "field_operations": "Field Operations and Highlights",
        "m1": "Member Directory",
        "m1_sub": "Register new farmers or update profile details",
        "m2": "Tractor & Machinery",
        "m2_sub": "Schedule field plowing and crop transport dispatches",
        "m3": "Weighbridge & Yields",
        "m3_sub": "View harvest weights, delivery logs, and ledger totals",
        "m5": "Short Term Loan Application",
        "m5_sub": "Process short-term inputs and credit applications",
        "m6": "Shareholder Accounts",
        "m6_sub": "Manage member share capital and dividend balances",
        "reg_title": "New Farmer Registration",
        "reg_sub": "Add a farmer to the official M-ROFCO registry.",
        "label_farmer_name": "Full Name",
        "label_phone": "Phone Number (M-PESA)",
        "label_id": "National ID Number",
        "label_loc": "Sub-County / Field Zone",
        "label_size": "Acreage",
        "label_crop": "Main Crop",
        "reg_btn": "Save Farmer Profile",
        "reg_success": "Farmer profile logged successfully!",
        "back_dash": "Back to Dashboard",
        "loan_title": "Short Term Loan Application",
        "loan_sub": "Log short-term advance requests for registered members.",
        "loan_amt_label": "Requested Amount (KES)",
        "loan_term_label": "Repayment Period",
        "loan_btn": "Submit Application",
        "loan_success": "Credit request recorded successfully.",
        "interest_notice": "Standard 10% interest rate applied automatically.",
        "trans_title": "Tractor Dispatch Request",
        "trans_sub": "Book machinery support for field preparation or transport.",
        "label_service_type": "Machinery Service",
        "label_dispatch_date": "Requested Date",
        "opt_plow": "Plowing / Tilling",
        "opt_haul": "Crop Hauling",
        "opt_harv": "Harvesting Support",
        "trans_btn": "Dispatch Booking",
        "trans_success": "Dispatch request submitted!",
        "shares_title": "Share Capital Account",
        "shares_sub": "Record member share purchases and dividend eligibility.",
        "label_num_shares": "Number of Shares",
        "label_share_val": "Value per Share (KES)",
        "label_benefits": "Estimated Dividend (KES)",
        "shares_btn": "Update Share Account",
        "shares_success": "Share records updated!",
        "about_title": "About M-ROFCO Cooperative",
        "about_sub": "Empowering Local Smallholder Farmers",
        "about_text": "M-ROFCO Cooperative Society Ltd is dedicated to transforming regional agriculture through mechanized farming dispatches, fair weighbridge auditing, low-interest farm advances, and transparent digital share ledger tracking.",
        "about_leadership": "Management Team",
        "role_chairman": "Chairman",
        "role_treasurer": "Treasurer",
        "role_secretary": "Secretary",
        "about_partners": "Community Partners",
        "about_contact_title": "Branch Contact",
        "about_phone_label": "Phone",
        "about_email_label": "Email",
        "about_social_label": "Updates",
        "transport_logistics": "Machinery Services",
        "membership_records": "Registered Farmers",
        "shareholding_accounts": "Share Accounts",
        "short_term_advances": "Short Advances",
        "long_term_loans": "Development Loans",
        "processed_payments": "Payment History",
        "view_membership": "View Members",
        "view_shareholding": "View Shares",
        "view_short_term": "View Loans",
        "view_long_term": "View Capital",
        "view_payments": "View Payments",
        "view_transport": "View Logistics",
        "no_transport_entries": "No tractor dispatches booked yet.",
        "master_membership_dir": "Member Directory & Ledger",
        "direct_live_sync": "Live view of Google Sheets records.",
        "filter_membership_records": "Search Records",
        "search_membership_ph": "Search by name, phone, ID, or zone...",
        "farmer_full_name": "Member Name",
        "phone_contact": "Phone Number",
        "national_id": "ID Number",
        "location_region": "Zone / Region",
        "membership_type": "Member Type",
        "edit_live_sheet": "Open Google Sheet",
        "edit_live_sheet_title": "Open in Google Sheets",
        "close_panel": "Close",
    },
    "sw": {
        "welcome": "Tovuti ya M-ROFCO",
        "subtext": "Kumbukumbu za wanachama, uzani wa mazao, na mitambo.",
        "proceed": "Thibitisha Mfanyakazi",
        "switch_btn": "English",
        "policy_title": "Usalama wa Taarifa",
        "policy_text": "Tafadhali thibitisha unatumia kifaa rasmi cha chama kushughulikia taarifa za wakulima.",
        "agree_check": "Ninthibitisha nina idhini ya kutazama daftari la wanachama.",
        "continue_btn": "Endelea kwa Uhakiki",
        "error_msg": "Weka alama ili kuthibitisha idhini.",
        "login_title": "Ingia Kama Mfanyakazi",
        "login_subtext": "Weka PIN yako ya tarakimu 4 kuingia kwenye mfumo.",
        "pin_label": "Nambari ya Siri (PIN)",
        "login_btn": "Ingia Mfomoni",
        "invalid_pin": "PIN si sahihi. Jaribu tena.",
        "dash_title": "Kituo cha Shughuli za Nyanjani",
        "dash_sub": "Mfanyakazi Aliyeingia: ",
        "logout": "Toka Mfomoni",
        "twende_pamoja": "TWENDE PAMOJA • KARIBU M-ROFCO",
        "services_we_offer": "Huduma Tunazotoa",
        "field_operations": "Shughuli za Nyanjani na Picha",
        "m1": "Orodha ya Wanachama",
        "m1_sub": "Sajili wakulima wapya au usasishe taarifa zao",
        "m2": "Huduma za Trekta",
        "m2_sub": "Panga huduma za kulima na kusafirisha mazao",
        "m3": "Uzani na Mavuno",
        "m3_sub": "Tazama vipimo vya mizani na mahesabu ya mazao",
        "m5": "Ombi la Mkopo wa Muda Mfupi",
        "m5_sub": "Shughulikia maombi ya mikopo ya muda mfupi",
        "m6": "Akaunti za Hisa",
        "m6_sub": "Usimamizi wa hisa na gawio la wanachama",
        "reg_title": "Usajili wa Mkulima Mpya",
        "reg_sub": "Ongeza mkulima kwenye daftari rasmi la M-ROFCO.",
        "label_farmer_name": "Jina Kamili",
        "label_phone": "Nambari ya Simu (M-PESA)",
        "label_id": "Nambari ya Kitambulisho",
        "label_loc": "Eneo / Eneo la Shamba",
        "label_size": "Ukubwa wa Shamba (Hekari)",
        "label_crop": "Zao Kuu",
        "reg_btn": "Hifadhi Taarifa za Mkulima",
        "reg_success": "Mkulima amesajiliwa!",
        "back_dash": "Rudi Kituoni",
        "loan_title": "Ombi la Mkopo wa Muda Mfupi",
        "loan_sub": "Andikisha maombi ya mikopo ya pembejeo kwa wanachama.",
        "loan_amt_label": "Kiasi Kinachoombwa (KES)",
        "loan_term_label": "Muda wa Kulipa",
        "loan_btn": "Wasilisha Ombi",
        "loan_success": "Ombi la mkopo limehifadhiwa.",
        "interest_notice": "Riba ya kawaida ni 10%.",
        "trans_title": "Hifadhi Huduma ya Trekta",
        "trans_sub": "Weka nafasi ya trekta kwa ajili ya kulima au kubeba mazao.",
        "label_service_type": "Huduma Inayohitajika",
        "label_dispatch_date": "Tarehe Inayotakiwa",
        "opt_plow": "Kutayarisha / Kulima",
        "opt_haul": "Kusafirisha Mazao",
        "opt_harv": "Kuvuna kwa Mitambo",
        "trans_btn": "Weka Nauli/Nafasi",
        "trans_success": "Ombi la trekta limehifadhiwa!",
        "shares_title": "Akaunti ya Hisa",
        "shares_sub": "Rekodi ununuzi wa hisa na gawio la mwanachama.",
        "label_num_shares": "Idadi ya Hisa",
        "label_share_val": "Thamani ya Kila Hisa (KES)",
        "label_benefits": "Gawio Linalotarajiwa (KES)",
        "shares_btn": "Hifadhi Taarifa za Hisa",
        "shares_success": "Taarifa za hisa zimesasishwa!",
        "about_title": "Kuhusu Ushirika wa M-ROFCO",
        "about_sub": "Kuwezesha Wakulima Wadogo wa Eneo Hili",
        "about_text": "Chama cha Ushirika cha M-ROFCO Ltd kimejitolea kubadilisha kilimo cha eneo hili kupitia huduma za mitambo, uhakiki wa uzito wa mazao, mikopo ya usaidizi, na usimamizi wa kisasa wa mtaji wa hisa.",
        "about_leadership": "Uongozi Mkuu",
        "role_chairman": "Mwenyekiti",
        "role_treasurer": "Mwekahazina",
        "role_secretary": "Katibu",
        "about_partners": "Washirika Wakuu",
        "about_contact_title": "Wasiliana na Tawi",
        "about_phone_label": "Simu",
        "about_email_label": "Barua pepe",
        "about_social_label": "Taarifa",
        "transport_logistics": "Huduma za Mitambo",
        "membership_records": "Wanachama Waliosajiliwa",
        "shareholding_accounts": "Akaunti za Hisa",
        "short_term_advances": "Mikopo ya Muda Mfupi",
        "long_term_loans": "Mikopo ya Maendeleo",
        "processed_payments": "Kumbukumbu za Malipo",
        "view_membership": "Tazama Wanachama",
        "view_shareholding": "Tazama Hisa",
        "view_short_term": "Tazama Mikopo",
        "view_long_term": "Tazama Mtaji",
        "view_payments": "Tazama Malipo",
        "view_transport": "Tazama Usafirishaji",
        "no_transport_entries": "Bado hakuna huduma za trekta zilizowekwa.",
        "master_membership_dir": "Daftari la Wanachama",
        "direct_live_sync": "Muonekano wa moja kwa moja wa Google Sheets.",
        "filter_membership_records": "Tafuta Taarifa",
        "search_membership_ph": "Tafuta kwa jina, simu, ID, au eneo...",
        "farmer_full_name": "Jina la Mwanachama",
        "phone_contact": "Nambari ya Simu",
        "national_id": "Kitambulisho",
        "location_region": "Eneo / Mkoa",
        "membership_type": "Aina ya Mwanachama",
        "edit_live_sheet": "Fungua Google Sheet",
        "edit_live_sheet_title": "Fungua katika Google Sheets",
        "close_panel": "Funga",
    },
}


# --- AUTOMATED LIVE CSV SHEET HELPER ---
def fetch_sheet_records(tab_name):
    encoded_tab = urllib.parse.quote(tab_name)
    csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_tab}"

    try:
        df = pd.read_csv(csv_url)
        df = df.fillna("")
        records = df.to_dict(orient="records")
        return records
    except Exception as e:
        print(f"DEBUG ERROR [{tab_name}]: Failed to fetch CSV records - {e}")
        return []


def fetch_registered_farmers():
    farmers = []
    records = fetch_sheet_records("Membership")

    for r in records:
        farmers.append(
            {
                "name": r.get("NAME") or r.get("Farmer Name") or r.get("Name") or "",
                "phone": r.get("PHONE CONTACT")
                or r.get("Phone Number")
                or r.get("Contacts")
                or "",
                "id_no": r.get("ID") or r.get("National ID") or "",
                "location": r.get("LOCATION")
                or r.get("Location")
                or r.get("Region")
                or "",
                "farm_size": r.get("FARM SIZE")
                or r.get("SIZE")
                or r.get("Farm Size")
                or "N/A",
            }
        )

    try:
        with app.app_context():
            local_farmers = Farmer.query.all()
            for lf in local_farmers:
                farmers.append(
                    {
                        "name": lf.name,
                        "phone": lf.phone,
                        "id_no": lf.id_no,
                        "location": lf.location,
                        "farm_size": lf.size,
                    }
                )
    except Exception:
        pass

    return farmers


def get_gallery_photos():
    images_dir = os.path.join(app.static_folder, "images")
    if not os.path.exists(images_dir):
        return []

    valid_extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp")
    photos = [
        f
        for f in os.listdir(images_dir)
        if f.lower().endswith(valid_extensions) and not f.lower().startswith(".")
    ]
    photos.sort()
    return photos


@app.before_request
def ensure_language():
    if "lang" not in session:
        session["lang"] = "en"


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_logged_in"):
                return redirect(url_for("login"))
            if session.get("user_role") not in roles:
                return redirect(url_for("home"))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# --- APPLICATION ROUTES ---
@app.route("/")
def index():
    return render_template(
        "welcome.html", texts=TEXTS[session["lang"]], current_lang=session["lang"]
    )


@app.route("/policy", methods=["GET", "POST"])
def policy():
    error = None
    if request.method == "POST":
        if request.form.get("accept_policy"):
            session["policy_accepted"] = True
            return redirect(url_for("login"))
        else:
            error = TEXTS[session["lang"]]["error_msg"]
    return render_template(
        "policy.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        error=error,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if not session.get("policy_accepted"):
        return redirect(url_for("policy"))

    error = None
    if request.method == "POST":
        role_selected = request.form.get("role", "")
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        user = User.query.get(username)

        if user and check_password_hash(user.password_hash, password):
            if user.role != role_selected:
                error = (
                    f"Invalid role selected for this username. You are a {user.role}."
                )
            else:
                session["user_logged_in"] = True
                session["user_username"] = user.username
                session["user_name"] = user.name
                session["user_role"] = user.role
                session["branch_id"] = user.branch_id
                role = user.role

                if role == "Intake Agent":
                    return redirect(url_for("home"))
                elif role == "Field Assessor":
                    return redirect(url_for("staff_field_assessor"))
                elif role == "Office Staff":
                    return redirect(url_for("home"))
                elif role == "Committee Member":
                    return redirect(url_for("staff_credit_committee"))
                elif role == "System Admin":
                    return redirect(url_for("admin_branches"))
                else:
                    return redirect(url_for("login"))
        else:
            error = "Invalid username or password. Please try again."

    return render_template(
        "login.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        error=error,
    )


@app.route("/home")
def home():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    current_time = time.time()

    if DASHBOARD_CACHE["data"] and (
        current_time - DASHBOARD_CACHE["last_updated"] < CACHE_TIMEOUT
    ):
        metrics = DASHBOARD_CACHE["data"]
    else:
        try:
            from models import (
                Farmer,
                Application,
                ShareTransaction,
                LoanRepayment,
                TransportDispatch,
            )

            metrics = {
                "yield_count": 0,  # Placeholder if no yield DB exists
                "shareholding_count": ShareTransaction.query.count(),
                "loan_count": Application.query.filter_by(
                    loan_type="Short-Term"
                ).count(),
                "long_term_loan_count": Application.query.filter_by(
                    loan_type="Long-Term"
                ).count(),
                "payment_count": LoanRepayment.query.count(),
                "transport_count": TransportDispatch.query.count(),
            }

            DASHBOARD_CACHE["data"] = metrics
            DASHBOARD_CACHE["last_updated"] = current_time
        except Exception as e:
            metrics = {
                "yield_count": 0,
                "shareholding_count": 0,
                "loan_count": 0,
                "payment_count": 0,
                "transport_count": 0,
                "long_term_loan_count": 0,
            }
            print(f"Metrics collection issue: {e}")

    try:
        from models import Farmer, Application

        local_farmers = Farmer.query.count()
        local_loans_pending = Application.query.filter(
            ~Application.status.like("Approved%"), Application.status != "Rejected"
        ).count()
        local_loans_complete = Application.query.filter(
            Application.status.like("Approved%")
        ).count()
        metrics["local_farmers"] = local_farmers
        metrics["local_loans_pending"] = local_loans_pending
        metrics["local_loans_complete"] = local_loans_complete
    except Exception as e:
        metrics["local_farmers"] = 0
        metrics["local_loans_pending"] = 0
        metrics["local_loans_complete"] = 0

    photos = get_gallery_photos()

    return render_template(
        "home.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        name=session.get("user_name", "John Doe"),
        metrics=metrics,
        photos=photos[:4],
    )


@app.route("/gallery")
def gallery():
    photos = get_gallery_photos()
    return render_template(
        "gallery.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        photos=photos,
    )


@app.route("/about")
def about():
    return render_template(
        "about_us.html", texts=TEXTS[session["lang"]], current_lang=session["lang"]
    )


@app.route("/register-farm", methods=["GET", "POST"])
@role_required("Intake Agent", "System Admin")
def register_farm():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None
    if request.method == "POST":
        farmer_name = request.form.get("farmer_name")
        phone = request.form.get("phone")
        id_no = request.form.get("id_no")
        location = request.form.get("location")
        size_str = request.form.get("size", "0.0")
        crop = request.form.get("crop")

        try:
            size = float(size_str)
        except ValueError:
            size = 0.0

        try:
            new_farmer = Farmer(
                name=farmer_name,
                phone=phone,
                id_no=id_no,
                location=location,
                size=size,
                crop=crop,
            )
            db.session.add(new_farmer)
            db.session.commit()
            success = True
        except Exception as e:
            db.session.rollback()
            error = f"Error registering farmer. They might already exist. Details: {e}"

    return render_template(
        "register_farm.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
    )


@app.route("/loan-services", methods=["GET", "POST"])
@role_required("Intake Agent", "System Admin")
def loan_services():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None

    if request.method == "POST":
        action_type = request.form.get("action_type", "new_loan")

        if action_type == "new_loan":
            app_id = f"APP-2026-{int(time.time()) % 10000:04d}"
            farmer_name = request.form.get("farmer_name")
            contacts = request.form.get("contacts")
            location = request.form.get("location")
            amount = float(request.form.get("amount", 0.0))
            term = request.form.get("term")
            term_unit = request.form.get("term_unit", "Months")
            loan_type = request.form.get("loan_type")

            digital_signature_name = request.form.get("digital_signature_name")
            digital_signature_id = request.form.get("digital_signature_id")
            terms_accepted = request.form.get("terms_accepted") == "on"

            expected_return_date = request.form.get("expected_return_date")
            if expected_return_date:
                try:
                    expected_return_date = datetime.strptime(
                        expected_return_date, "%Y-%m-%d"
                    )
                except ValueError:
                    expected_return_date = None

            if not expected_return_date:
                try:
                    term_int = int(term)
                    if term_unit == "Months":
                        expected_return_date = datetime.utcnow() + timedelta(
                            days=term_int * 30
                        )
                    elif term_unit == "Days":
                        expected_return_date = datetime.utcnow() + timedelta(
                            days=term_int
                        )
                    elif term_unit == "Weeks":
                        expected_return_date = datetime.utcnow() + timedelta(
                            days=term_int * 7
                        )
                    elif term_unit == "Years":
                        expected_return_date = datetime.utcnow() + timedelta(
                            days=term_int * 365
                        )
                except (ValueError, TypeError):
                    pass

            branch_id = session.get("branch_id")

            interest_applied = 0.0
            if loan_type == "Short-Term" or loan_type == "Harvesting Loan":
                interest_applied = amount * 0.10
            elif loan_type == "Long-Term":
                interest_applied = amount * 0.15

            new_app = Application(
                id=app_id,
                member_name=farmer_name,
                member_id=contacts,
                zone=location,
                requested_amount=amount,
                purpose=(
                    "Sugarcane Advance"
                    if loan_type == "Long-Term"
                    else "Input Micro-Loan"
                ),
                max_cap=amount,
                status=(
                    "Pending Committee Review"
                    if loan_type == "Harvesting Loan"
                    else "Pending Assessment"
                ),
                committee_notes=f"Term: {term} {term_unit}",
                loan_type=loan_type,
                expected_return_date=expected_return_date,
                interest_applied=interest_applied,
                branch_id=branch_id,
                digital_signature_name=digital_signature_name,
                digital_signature_id=digital_signature_id,
                terms_accepted=terms_accepted,
            )
            db.session.add(new_app)

            if loan_type == "Harvesting Loan":
                # Log the initial payout
                disb = HarvestingDisbursement(
                    application_id=app_id,
                    date=datetime.utcnow().date(),
                    amount=amount,
                    notes="Initial Harvesting Payout",
                )
                db.session.add(disb)

            db.session.commit()
            success = True

        elif action_type == "add_payout":
            app_id = request.form.get("harvest_app_id")
            payout_amount = float(request.form.get("payout_amount", 0.0))

            if app_id and payout_amount > 0:
                app_record = Application.query.get(app_id)
                if app_record:
                    disb = HarvestingDisbursement(
                        application_id=app_id,
                        date=datetime.utcnow().date(),
                        amount=payout_amount,
                        notes="Daily Payout",
                    )
                    db.session.add(disb)
                    # Also update the principal and interest of the loan!
                    app_record.requested_amount += payout_amount
                    app_record.max_cap += payout_amount
                    app_record.interest_applied = app_record.requested_amount * 0.10
                    db.session.commit()
                    success = True
                else:
                    error = "Application not found."

    farmers_list = fetch_registered_farmers()
    harvesting_loans = Application.query.filter_by(loan_type="Harvesting Loan").all()

    return render_template(
        "loan_services.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
        farmers=farmers_list,
        harvesting_loans=harvesting_loans,
    )


@app.route("/staff/ledger", methods=["GET", "POST"])
@role_required("Intake Agent", "System Admin")
def staff_ledger():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None
    if request.method == "POST":
        category = request.form.get("category")
        amount = float(request.form.get("amount", 0.0))
        description = request.form.get("description")

        try:
            new_entry = LedgerEntry(
                category=category,
                amount=amount,
                description=description,
                reference_id="MANUAL",
            )
            db.session.add(new_entry)
            db.session.commit()
            success = True
        except Exception as e:
            error = f"Error adding ledger entry: {e}"

    recent_entries = (
        LedgerEntry.query.order_by(LedgerEntry.created_at.desc()).limit(20).all()
    )
    return render_template(
        "ledger_entry.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
        entries=recent_entries,
    )


@app.route("/loan-repayment", methods=["GET", "POST"])
@role_required("Intake Agent", "System Admin")
def loan_repayment():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None
    from models import Application, LoanRepayment

    if request.method == "POST":
        app_id = request.form.get("application_id")
        amount = float(request.form.get("amount", 0.0))
        receipt_number = request.form.get("receipt_number")

        try:
            loan = Application.query.get(app_id)
            if loan:
                new_repayment = LoanRepayment(
                    application_id=app_id,
                    amount=amount,
                    paid_by=loan.member_name,
                    receipt_number=receipt_number,
                )
                loan.repaid_amount += amount
                db.session.add(new_repayment)
                db.session.commit()
                success = True
            else:
                error = "Application not found."
        except Exception as e:
            db.session.rollback()
            error = f"Error recording payment: {e}"

    # Get approved loans that might be active
    active_loans = Application.query.filter(Application.status.like("Approved%")).all()
    return render_template(
        "loan_repayment.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
        active_loans=active_loans,
    )


@app.route("/log-yield", methods=["GET", "POST"])
@role_required("Intake Agent", "System Admin")
def log_yield():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None
    farmers = fetch_registered_farmers()

    if request.method == "POST":
        request.form.get("farmer_name")
        request.form.get("contacts")
        request.form.get("location")
        request.form.get("tonnage")
        request.form.get("factory")

        try:
            # We can log this to Google Sheets or SQLite. For now, pretend it succeeds.
            success = True
        except Exception as e:
            error = f"Failed to log yield: {e}"

    return render_template(
        "yield_ticket_form.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
        farmers=farmers,
    )


@app.route("/transport-logistics", methods=["GET", "POST"])
@role_required("Intake Agent", "Committee Member", "System Admin")
def transport_logistics():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None
    if request.method == "POST":
        farmer_name = request.form.get("farmer_name")
        location = request.form.get("location")
        service_type = request.form.get("service_type")
        dispatch_date_str = request.form.get("dispatch_date")

        try:
            dispatch_date = (
                datetime.strptime(dispatch_date_str, "%Y-%m-%d").date()
                if dispatch_date_str
                else None
            )
            new_dispatch = TransportDispatch(
                farmer_name=farmer_name,
                location=location,
                service_type=service_type,
                dispatch_date=dispatch_date,
                status="Pending",
            )
            db.session.add(new_dispatch)
            db.session.commit()
            success = True
        except Exception as e:
            db.session.rollback()
            error = f"Error requesting transport. Details: {e}"

    farmers_list = fetch_registered_farmers()
    return render_template(
        "transport_logistics.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
        farmers=farmers_list,
    )


@app.route("/weighbridge-tickets/download-pdf")
def download_weighbridge_pdf():
    records = fetch_sheet_records("WeighbridgeTickets")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt="M-ROFCO - Weighbridge Tickets Report", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", size=10)
    for row in records:
        text = f"Ticket: {row.get('TicketNumber','')} | Date: {row.get('Date','')} | Farmer: {row.get('FarmerName','')} | Net Wt: {row.get('NetWeight','')} | Zone: {row.get('Zone','')}"
        pdf.cell(0, 8, txt=text, ln=True)

    pdf_path = os.path.join(app.root_path, "static", "weighbridge_report.pdf")
    pdf.output(pdf_path)
    return send_file(
        pdf_path, as_attachment=True, download_name="Weighbridge_Report.pdf"
    )


@app.route("/shares-management", methods=["GET", "POST"])
@role_required("Intake Agent", "System Admin")
def shares_management():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success = False
    error = None
    if request.method == "POST":
        farmer_name = request.form.get("farmer_name")
        number_of_shares = int(request.form.get("number_of_shares", 0))
        shares_value = float(request.form.get("shares_value", 0))

        transaction = ShareTransaction(
            farmer_name=farmer_name,
            transaction_type="Purchase",
            number_of_shares=number_of_shares,
            total_value=shares_value,
            status="Pending",
            initiated_by=session.get("user_username"),
        )
        db.session.add(transaction)
        db.session.commit()
        success = True

    farmers_list = fetch_registered_farmers()
    return render_template(
        "shares_management.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success=success,
        error=error,
        farmers=farmers_list,
    )


@app.route("/committee/shares", methods=["GET", "POST"])
@role_required("Committee Member", "System Admin")
def committee_shares():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        txn_id = request.form.get("txn_id")
        action = request.form.get("action")

        txn = ShareTransaction.query.get(txn_id)
        if txn:
            if action == "approve":
                txn.status = "Approved"
            elif action == "reject":
                txn.status = "Rejected"
            db.session.commit()
        return redirect(url_for("committee_shares"))

    pending_shares = ShareTransaction.query.filter_by(status="Pending").all()
    rejected_shares = ShareTransaction.query.filter_by(status="Rejected").all()
    return render_template(
        "committee_shares.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        shares=pending_shares,
        rejected_shares=rejected_shares,
    )


@app.route("/committee/reporting")
@role_required("Committee Member", "System Admin")
def committee_reporting():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    report_type = request.args.get("type", "society")

    # Calculate start and end of current week (Monday to Sunday)
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    ledger_entries = LedgerEntry.query.filter(
        LedgerEntry.date >= start_of_week, LedgerEntry.date <= end_of_week
    ).all()

    # Aggregate data for Society Status
    society_data = {
        "farmers_payment": 0.0,
        "contractors_payment": 0.0,
        "travellings": 0.0,
        "wages": 0.0,
        "advances": 0.0,
        "refund": 0.0,
        "bank_charge": 0.0,
        "commission": 0.0,
        "adv_recoveries": 0.0,
    }

    # Calculate from Ledger
    for entry in ledger_entries:
        cat = entry.category
        amt = entry.amount
        if cat == "Farmers Payment":
            society_data["farmers_payment"] += amt
        elif cat == "Contractors Payment":
            society_data["contractors_payment"] += amt
        elif cat == "Travellings":
            society_data["travellings"] += amt
        elif cat == "Wages":
            society_data["wages"] += amt
        elif cat == "Farmers Advances":
            society_data["advances"] += amt
        elif cat == "Refund":
            society_data["refund"] += amt
        elif cat == "Bank Charge":
            society_data["bank_charge"] += amt
        elif cat == "Commission":
            society_data["commission"] += amt
        elif cat == "Advance Recovery":
            society_data["adv_recoveries"] += amt

    society_data["grand_total_expenses"] = (
        society_data["farmers_payment"]
        + society_data["contractors_payment"]
        + society_data["travellings"]
        + society_data["wages"]
        + society_data["advances"]
        + society_data["refund"]
        + society_data["bank_charge"]
    )

    society_data["grand_total_income"] = (
        society_data["commission"] + society_data["adv_recoveries"]
    )

    # Account Status (Consolidated Bank Account)
    system_fund = SystemFund.query.get(1)
    available_balance = system_fund.available_balance if system_fund else 0.0

    return render_template(
        "committee_reporting.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        report_type=report_type,
        start_date=start_of_week,
        end_date=end_of_week,
        society_data=society_data,
        available_balance=available_balance,
        entries=ledger_entries,
    )


@app.route("/committee/farmers")
@role_required("Committee Member", "System Admin")
def committee_farmers():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    farmers = Farmer.query.order_by(Farmer.created_at.desc()).all()
    total_farms = len(farmers)
    total_acreage = sum(f.size for f in farmers)
    return render_template(
        "committee_farmers.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        farmers=farmers,
        total_farms=total_farms,
        total_acreage=total_acreage,
    )


@app.route("/committee/equity")
@role_required("Committee Member", "System Admin")
def committee_equity():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    approved_shares = ShareTransaction.query.filter_by(status="Approved").all()
    equity_map = {}
    for txn in approved_shares:
        if txn.farmer_name not in equity_map:
            equity_map[txn.farmer_name] = {"total_shares": 0, "total_value": 0.0}
        equity_map[txn.farmer_name]["total_shares"] += txn.number_of_shares
        equity_map[txn.farmer_name]["total_value"] += txn.total_value

    return render_template(
        "committee_equity.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        equity_map=equity_map,
    )


@app.route("/committee/logistics")
@role_required("Committee Member", "System Admin")
def committee_logistics():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    dispatches = TransportDispatch.query.order_by(
        TransportDispatch.created_at.desc()
    ).all()
    return render_template(
        "committee_logistics.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        dispatches=dispatches,
    )


@app.route("/weighbridge-tickets")
@app.route("/production-yields")
def weighbridge_tickets():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    membership_tickets = fetch_sheet_records("Membership")
    shareholding_tickets = fetch_sheet_records("Shareholding Accounts")
    short_term_tickets = fetch_sheet_records("Short term Loans/Advances")
    long_term_tickets = fetch_sheet_records("Long term Loans/Advances")
    payment_tickets = fetch_sheet_records("Processed Payments")
    transport_tickets = fetch_sheet_records("Transport Logistics")

    return render_template(
        "weighbridge_tickets.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        membership_tickets=membership_tickets,
        shareholding_tickets=shareholding_tickets,
        short_term_tickets=short_term_tickets,
        long_term_tickets=long_term_tickets,
        payment_tickets=payment_tickets,
        transport_tickets=transport_tickets,
        spreadsheet_id=SPREADSHEET_ID,
    )


# --- URD WORKFLOW & ADMIN ROUTES WITH SQLITE PERSISTENCE ---
@app.route("/staff/loan-intake", methods=["GET", "POST"])
@role_required("Intake Agent")
def staff_loan_intake():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success_msg = None
    if request.method == "POST":
        app_id = f"APP-2026-{int(time.time()) % 10000:04d}"
        member_name = request.form.get("member_name")
        member_id = request.form.get("member_id")
        zone = request.form.get("zone")
        acreage = float(request.form.get("acreage", 0.0))
        requested_amount = float(request.form.get("requested_amount", 0.0))
        purpose = request.form.get("purpose")
        term = request.form.get("term", "")
        term_unit = request.form.get("term_unit", "Months")
        guarantor_name = request.form.get("guarantor_name")
        guarantor_id = request.form.get("guarantor_id")

        membership_records = fetch_sheet_records("Membership")
        total_tonnage = 0.0

        for r in membership_records:
            r_name = (
                str(r.get("NAME") or r.get("Farmer Name") or r.get("Name") or "")
                .strip()
                .lower()
            )
            r_id = str(r.get("ID") or r.get("National ID") or "").strip()

            if (member_id and r_id == str(member_id).strip()) or (
                member_name and r_name == str(member_name).strip().lower()
            ):
                raw_yield = (
                    r.get("YIELD (TONS)") or r.get("Yield") or r.get("Tonnage") or 0.0
                )
                try:
                    total_tonnage += float(raw_yield)
                except ValueError:
                    pass

        gross_val = total_tonnage * URD_CONFIG["sugarcane_price"]

        branch_id = session.get("branch_id")
        new_app = Application(
            id=app_id,
            member_name=member_name,
            member_id=member_id,
            zone=zone,
            acreage=acreage,
            requested_amount=requested_amount,
            purpose=purpose,
            estimated_tonnage=total_tonnage,
            gross_valuation=gross_val,
            status="Pending Field Assessment",
            guarantor_name=guarantor_name,
            guarantor_id=guarantor_id,
            loan_type="Long-Term",
            committee_notes=f"Requested Term: {term} {term_unit}",
            branch_id=branch_id,
        )
        db.session.add(new_app)
        db.session.commit()

        success_msg = f"Loan application {app_id} created with auto-calculated yield ({total_tonnage} tons, KES {gross_val:,.2f}) and queued for field assessment!"

    return render_template(
        "staff_loan_intake.html",
        active_role="intake",
        name=session.get("user_name", "Call Center Agent"),
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        config=URD_CONFIG,
        success_msg=success_msg,
    )


@app.route("/staff/field-assessor", methods=["GET", "POST"])
@role_required("Field Assessor")
def staff_field_assessor():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success_msg = None
    if request.method == "POST":
        app_id = request.form.get("app_id")
        tons_per_acre = float(request.form.get("tons_per_acre", 35.0))
        crop_health = request.form.get("crop_health", "Grade A")
        latitude = request.form.get("latitude", "")
        longitude = request.form.get("longitude", "")

        photo_filename = None
        if "inspection_photo" in request.files:
            file = request.files["inspection_photo"]
            if file and file.filename != "" and allowed_file(file.filename):
                filename = secure_filename(
                    f"{app_id}_{int(time.time())}_{file.filename}"
                )
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                photo_filename = filename

        app_record = Application.query.get(app_id)
        if app_record:
            # Enforce silo: only update if it matches assessor's branch or assessor has no branch
            assessor_branch = session.get("branch_id")
            if not assessor_branch or app_record.branch_id == assessor_branch:
                tot_tonnage = app_record.acreage * tons_per_acre
                gross_val = tot_tonnage * URD_CONFIG["sugarcane_price"]
                net_val = gross_val * (1 - (URD_CONFIG["deduction_rate"] / 100))
                max_cap = net_val * (URD_CONFIG["ltv_cap"] / 100)
                location_notes = request.form.get("location_notes", "")
                assessor_notes = request.form.get("notes", "")
                gps_coords = (
                    f"{latitude}, {longitude}"
                    if latitude and longitude
                    else "Not Tagged"
                )
                cane_stage = request.form.get("cane_stage", "Standing Cane")

                app_record.crop_health = crop_health
                app_record.cane_stage = cane_stage
                app_record.estimated_tonnage = tot_tonnage
                app_record.gross_valuation = gross_val
                app_record.net_valuation = net_val
                app_record.max_cap = max_cap
                app_record.gps_coordinates = gps_coords
                app_record.status = "Pending Committee Review"

                # Append assessor notes
                if location_notes or assessor_notes:
                    current_notes = app_record.committee_notes or ""
                    app_record.committee_notes = f"{current_notes}\n[Assessor Location]: {location_notes}\n[Assessor Notes]: {assessor_notes}"

                if photo_filename:
                    app_record.photo = photo_filename

                db.session.commit()
                success_msg = (
                    f"Field assessment & GPS geotag saved for application {app_id}!"
                )
            else:
                success_msg = "Error: Application does not belong to your branch."

    assessor_branch = session.get("branch_id")
    query = Application.query.filter(
        Application.status.in_(["Pending Assessment", "Pending Field Assessment"])
    )
    if assessor_branch:
        query = query.filter_by(branch_id=assessor_branch)

    pending_apps = query.all()

    return render_template(
        "staff_field_assessor.html",
        active_role="assessor",
        name=session.get("user_name", "Field Agronomist"),
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        pending_apps=pending_apps,
        success_msg=success_msg,
    )


@app.route("/staff/credit-committee")
@role_required("Committee Member")
def staff_credit_committee():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    pending_committee_apps = Application.query.filter_by(
        status="Pending Committee Review"
    ).all()

    system_fund = SystemFund.query.get(1)
    available_balance = system_fund.available_balance if system_fund else 0.0

    error_msg = request.args.get("error")
    receipt_app_id = request.args.get("receipt_app_id")

    from models import LoanRepayment

    recent_repayments = (
        LoanRepayment.query.order_by(LoanRepayment.created_at.desc()).limit(10).all()
    )

    return render_template(
        "staff_credit_committee.html",
        active_role="committee",
        name=session.get("user_name", "Committee Chair"),
        applications=pending_committee_apps,
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        available_balance=available_balance,
        error_msg=error_msg,
        receipt_app_id=receipt_app_id,
        recent_repayments=recent_repayments,
    )


@app.route("/staff/credit-committee/action", methods=["POST"])
@role_required("Committee Member")
def credit_committee_action():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    app_id = request.form.get("app_id")
    action = request.form.get("action")
    notes = request.form.get("notes", "")

    if action == "override" and not notes.strip():
        return redirect(
            url_for(
                "staff_credit_committee",
                error="Override requires a justification comment in the notes field.",
            )
        )

    app_record = Application.query.get(app_id)
    system_fund = SystemFund.query.get(1)
    available_balance = system_fund.available_balance if system_fund else 0.0

    if app_record:
        req_amt = app_record.requested_amount
        max_cap = app_record.max_cap

        if action == "approve":
            new_status = "Approved"
            approved_val = max_cap
        elif action == "override":
            new_status = "Approved (Override)"
            approved_val = req_amt
        else:
            new_status = "Rejected"
            approved_val = 0.0

        if action in ["approve", "override"]:
            if approved_val > available_balance:
                return redirect(
                    url_for(
                        "staff_credit_committee",
                        error="Insufficient floating cash to approve this loan.",
                    )
                )
            system_fund.available_balance -= approved_val

            # Automatically log to Ledger
            ledger_entry = LedgerEntry(
                category="Farmers Advances",
                amount=approved_val,
                description=f"Loan Disbursement for {app_record.member_name}",
                reference_id=app_id,
            )
            db.session.add(ledger_entry)

        app_record.status = new_status
        app_record.approved_amount = approved_val
        app_record.committee_notes = notes

        # Generate receipt record
        receipt = CreditReceipt(
            app_id=app_id,
            member_name=app_record.member_name,
            action=action.upper(),
            approved_amount=approved_val,
            committee_notes=notes,
            processed_by=session.get("user_username"),
        )
        db.session.add(receipt)
        db.session.commit()

    return redirect(
        url_for(
            "staff_credit_committee",
            success_msg=f"Application {app_id} processed successfully.",
            receipt_app_id=app_id,
        )
    )


@app.route("/committee/download-receipt/<app_id>")
@role_required("Committee Member", "System Admin")
def download_receipt(app_id):
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    receipt = (
        CreditReceipt.query.filter_by(app_id=app_id)
        .order_by(CreditReceipt.id.desc())
        .first()
    )

    if not receipt:
        return "Receipt not found", 404

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt="M-ROFCO Hub - Credit Committee Receipt", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Receipt ID: REC-{receipt.id:04d}", ln=True)
    pdf.cell(200, 10, txt=f"Application ID: {receipt.app_id}", ln=True)
    pdf.cell(200, 10, txt=f"Member Name: {receipt.member_name}", ln=True)
    pdf.cell(200, 10, txt=f"Action Taken: {receipt.action}", ln=True)
    pdf.cell(
        200, 10, txt=f"Approved Amount: KES {receipt.approved_amount:,.2f}", ln=True
    )
    pdf.cell(200, 10, txt=f"Processed By: {receipt.processed_by}", ln=True)
    pdf.cell(200, 10, txt=f"Date: {receipt.created_at}", ln=True)
    pdf.ln(10)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(200, 10, txt="Committee Notes/Justification:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=str(receipt.committee_notes))

    pdf_path = os.path.join(app.root_path, "static", f"receipt_{app_id}.pdf")
    pdf.output(pdf_path)

    return send_file(pdf_path, as_attachment=True)


@app.route("/staff/request-password-change", methods=["GET", "POST"])
def request_password_change():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success_msg = None
    error_msg = None
    if request.method == "POST":
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        username = session.get("user_username")
        
        # Verify old password
        from models import User
        user = User.query.get(username)
        if not user or not check_password_hash(user.password_hash, old_password):
            error_msg = "Incorrect old password."
        elif new_password != confirm_password:
            error_msg = "New passwords do not match."
        else:
            new_password_hash = generate_password_hash(new_password)
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO password_change_requests (username, new_password_hash) VALUES (?, ?)
                """,
                    (username, new_password_hash),
                )
                conn.commit()
            success_msg = "Awaiting approval from the committee"

    return render_template(
        "request_password_change.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success_msg=success_msg,
        error_msg=error_msg,
    )


@app.route("/committee/password-requests", methods=["GET", "POST"])
@role_required("Committee Member", "System Admin")
def password_requests():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        req_id = request.form.get("request_id")
        action = request.form.get("action")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM password_change_requests WHERE id = ?", (req_id,)
            )
            req = cursor.fetchone()

            if req and action == "approve":
                conn.execute(
                    "UPDATE staff_users SET password_hash = ? WHERE username = ?",
                    (req["new_password_hash"], req["username"]),
                )
                conn.execute(
                    "UPDATE password_change_requests SET status = 'Approved' WHERE id = ?",
                    (req_id,),
                )
            elif req and action == "reject":
                conn.execute(
                    "UPDATE password_change_requests SET status = 'Rejected' WHERE id = ?",
                    (req_id,),
                )

            conn.commit()

        return redirect(url_for("password_requests"))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM password_change_requests WHERE status = 'Pending'"
        )
        requests = cursor.fetchall()

    return render_template(
        "password_requests.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        requests=requests,
    )


@app.route("/committee/create-staff", methods=["GET", "POST"])
@role_required("Committee Member", "System Admin")
def create_staff():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success_msg = None
    error_msg = None
    if request.method == "POST":
        username = request.form.get("username")
        name = request.form.get("name")
        role = request.form.get("role")
        branch_id = request.form.get("branch_id")

        if branch_id == "":
            branch_id = None
        elif branch_id:
            branch_id = int(branch_id)

        if role == "System Admin" and session.get("user_role") != "System Admin":
            error_msg = "Only System Admins can create new System Admin accounts."
        else:
            default_pw = generate_password_hash("Mrofco2026")
            existing_user = User.query.get(username)
            if existing_user:
                error_msg = "Username already exists."
            else:
                new_user = User(
                    username=username,
                    password_hash=default_pw,
                    name=name,
                    role=role,
                    branch_id=branch_id,
                )
                db.session.add(new_user)
                db.session.commit()
                success_msg = f"Staff account '{username}' created successfully with default password 'Mrofco2026'."

    branches = Branch.query.all()
    return render_template(
        "create_staff.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success_msg=success_msg,
        error_msg=error_msg,
        branches=branches,
    )


@app.route("/admin/branches", methods=["GET", "POST"])
@role_required("System Admin")
def admin_branches():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success_msg = None
    error_msg = None
    if request.method == "POST":
        name = request.form.get("name")
        location = request.form.get("location")

        if Branch.query.filter_by(name=name).first():
            error_msg = "Branch name already exists."
        else:
            new_branch = Branch(name=name, location=location)
            db.session.add(new_branch)
            db.session.commit()
            success_msg = f"Branch '{name}' created successfully."

    branches = Branch.query.all()
    return render_template(
        "admin_branches.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success_msg=success_msg,
        error_msg=error_msg,
        branches=branches,
    )


@app.route("/committee/fund-requests", methods=["GET", "POST"])
@role_required("Committee Member", "System Admin")
def fund_requests():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    success_msg = None
    if request.method == "POST":
        amount = float(request.form.get("amount", 0.0))
        username = session.get("user_username")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO fund_requests (requested_by, amount) VALUES (?, ?)",
                (username, amount),
            )
            conn.commit()
        success_msg = f"Fund request for KES {amount:,.0f} submitted to admin."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fund_requests WHERE status = 'Pending'")
        pending_requests = cursor.fetchall()
        cursor.execute("SELECT available_balance FROM system_funds WHERE id = 1")
        row = cursor.fetchone()
        available_balance = row["available_balance"] if row else 0.0

    return render_template(
        "fund_requests.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        success_msg=success_msg,
        requests=pending_requests,
        available_balance=available_balance,
    )


@app.route("/admin/approve-funds", methods=["GET", "POST"])
@role_required("System Admin")
def admin_approve_funds():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        req_id = request.form.get("request_id")
        action = request.form.get("action")

        req = FundRequest.query.get(req_id)
        if req:
            if action == "approve":
                system_fund = SystemFund.query.get(1)
                if system_fund:
                    system_fund.available_balance += req.amount
                req.status = "Approved"
            elif action == "reject":
                req.status = "Rejected"

            db.session.commit()

        return redirect(url_for("admin_approve_funds"))

    requests = FundRequest.query.filter_by(status="Pending").all()

    return render_template(
        "admin_approve_funds.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        requests=requests,
    )


# --- EXPORT ROUTE FOR EXCEL / CSV DOWNLOAD ---
@app.route("/admin/ledger")
@role_required("System Admin")
def admin_ledger():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    system_fund = SystemFund.query.get(1)
    available_balance = system_fund.available_balance if system_fund else 0.0

    # Get all approved applications for the ledger
    approved_loans = (
        Application.query.filter(Application.status.like("Approved%"))
        .order_by(Application.updated_at.desc())
        .all()
    )

    # Calculate total dispersed
    total_dispersed = sum(app.approved_amount for app in approved_loans)

    return render_template(
        "admin_ledger.html",
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
        available_balance=available_balance,
        total_dispersed=total_dispersed,
        loans=approved_loans,
    )


@app.route("/admin/export-applications-csv")
@role_required("System Admin", "Committee Member")
def export_applications_csv():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    apps = Application.query.order_by(Application.created_at.desc()).all()

    si = StringIO()
    writer = csv.writer(si)

    writer.writerow(
        [
            "Application ID",
            "Member Name",
            "Member ID",
            "Zone",
            "Acreage",
            "Requested Amount",
            "Purpose",
            "Crop Health",
            "Estimated Tonnage",
            "Gross Valuation",
            "Net Valuation",
            "Max Loan Cap",
            "Approved Amount",
            "GPS Coordinates",
            "Status",
            "Committee Notes",
            "Created At",
            "Updated At",
        ]
    )

    for app_record in apps:
        writer.writerow(
            [
                app_record.id,
                app_record.member_name,
                app_record.member_id,
                app_record.zone,
                app_record.acreage,
                app_record.requested_amount,
                app_record.purpose,
                app_record.crop_health,
                app_record.estimated_tonnage,
                app_record.gross_valuation,
                app_record.net_valuation,
                app_record.max_cap,
                app_record.approved_amount,
                app_record.gps_coordinates,
                app_record.status,
                app_record.committee_notes,
                app_record.created_at,
                app_record.updated_at,
            ]
        )

    output = si.getvalue()

    return Response(
        output,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment;filename=m_rofco_loan_applications.csv"
        },
    )


@app.route("/admin/config", methods=["GET", "POST"])
@role_required("System Admin")
def admin_config():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        URD_CONFIG["sugarcane_price"] = float(request.form.get("sugarcane_price", 5500))
        URD_CONFIG["deduction_rate"] = float(request.form.get("deduction_rate", 15))
        URD_CONFIG["ltv_cap"] = float(request.form.get("ltv_cap", 50))
        return redirect(url_for("admin_config"))

    return render_template(
        "admin_config.html",
        active_role="admin",
        name=session.get("user_name", "Admin"),
        config=URD_CONFIG,
        texts=TEXTS[session["lang"]],
        current_lang=session["lang"],
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/toggle-language")
def toggle_language():
    session["lang"] = "sw" if session.get("lang") == "en" else "en"
    return redirect(request.referrer or url_for("index"))


@app.route("/shares-management/download-pdf")
def download_shares_pdf():
    records = fetch_sheet_records("ShareCapital")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, txt="M-ROFCO - Shares Management Report", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", size=10)
    for row in records:
        text = f"Date: {row.get('Date','')} | Name: {row.get('MemberName','')} | Shares: {row.get('TotalShares','')} | Value: KES {row.get('ShareValue','')}"
        pdf.cell(0, 8, txt=text, ln=True)

    pdf_path = os.path.join(app.root_path, "static", "shares_report.pdf")
    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name="Shares_Report.pdf")


@app.route("/committee/password-requests", methods=["GET", "POST"])
@role_required("Committee Member", "System Admin")
def committee_password_requests():
    if not session.get("user_logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        request_id = request.form.get("request_id")
        action = request.form.get("action")

        req = PasswordChangeRequest.query.get(request_id)
        if req and req.status == "Pending":
            if action == "approve":
                req.status = "Approved"
                user = User.query.filter_by(username=req.username).first()
                if user:
                    user.password_hash = req.new_password_hash
            elif action == "reject":
                req.status = "Rejected"
            db.session.commit()
        return redirect(url_for("committee_password_requests"))

    requests = PasswordChangeRequest.query.filter_by(status="Pending").all()
    return render_template(
        "password_requests.html",
        texts=TEXTS.get(session.get("lang", "en")),
        current_lang=session.get("lang", "en"),
        requests=requests,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
