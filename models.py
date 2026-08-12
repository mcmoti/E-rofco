from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Branch(db.Model):
    __tablename__ = 'branches'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    location = db.Column(db.String(255))
    floating_balance = db.Column(db.Float, default=0.0)
    
    users = db.relationship('User', backref='branch', lazy=True)
    applications = db.relationship('Application', backref='branch', lazy=True)

class User(db.Model):
    __tablename__ = 'staff_users'
    username = db.Column(db.String(50), primary_key=True)
    pin = db.Column(db.String(10))
    password_hash = db.Column(db.String(255))
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)

class Application(db.Model):
    __tablename__ = 'applications'
    id = db.Column(db.String(50), primary_key=True)
    member_name = db.Column(db.String(100), nullable=False)
    member_id = db.Column(db.String(50), nullable=False)
    zone = db.Column(db.String(100))
    acreage = db.Column(db.Float, default=0.0)
    requested_amount = db.Column(db.Float, default=0.0)
    purpose = db.Column(db.Text)
    crop_health = db.Column(db.String(50), default='Pending Inspection')
    cane_stage = db.Column(db.String(50))
    estimated_tonnage = db.Column(db.Float, default=0.0)
    gross_valuation = db.Column(db.Float, default=0.0)
    net_valuation = db.Column(db.Float, default=0.0)
    max_cap = db.Column(db.Float, default=0.0)
    approved_amount = db.Column(db.Float, default=0.0)
    gps_coordinates = db.Column(db.String(100), default='Not Tagged')
    photo = db.Column(db.String(255))
    status = db.Column(db.String(50), default='Pending Assessment')
    committee_notes = db.Column(db.Text)
    guarantor_name = db.Column(db.String(100))
    guarantor_id = db.Column(db.String(50))
    loan_type = db.Column(db.String(50), default='Long-Term')
    
    # New Fields for Consolidated Loan Logic
    digital_signature_name = db.Column(db.String(100))
    digital_signature_id = db.Column(db.String(50))
    terms_accepted = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    
    expected_return_date = db.Column(db.DateTime, nullable=True)
    interest_applied = db.Column(db.Float, default=0.0)
    repaid_amount = db.Column(db.Float, default=0.0)

    # Relationships
    disbursements = db.relationship('HarvestingDisbursement', backref='application', lazy=True)
    loan_repayments = db.relationship('LoanRepayment', backref='application', lazy=True)

class HarvestingDisbursement(db.Model):
    __tablename__ = 'harvesting_disbursements'
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.String(50), db.ForeignKey('applications.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LoanRepayment(db.Model):
    __tablename__ = 'loan_repayments'
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.String(50), db.ForeignKey('applications.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_by = db.Column(db.String(100), nullable=False)
    receipt_number = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PasswordChangeRequest(db.Model):
    __tablename__ = 'password_change_requests'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    new_password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SystemFund(db.Model):
    __tablename__ = 'system_funds'
    id = db.Column(db.Integer, primary_key=True)
    available_balance = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FundRequest(db.Model):
    __tablename__ = 'fund_requests'
    id = db.Column(db.Integer, primary_key=True)
    requested_by = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CreditReceipt(db.Model):
    __tablename__ = 'credit_receipts'
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.String(50), nullable=False)
    member_name = db.Column(db.String(100))
    action = db.Column(db.String(50))
    approved_amount = db.Column(db.Float)
    committee_notes = db.Column(db.Text)
    processed_by = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ShareTransaction(db.Model):
    __tablename__ = 'share_transactions'
    id = db.Column(db.Integer, primary_key=True)
    farmer_name = db.Column(db.String(100), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False) # 'Purchase' or 'Sale'
    number_of_shares = db.Column(db.Integer, nullable=False)
    total_value = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending') # 'Pending', 'Approved', 'Rejected'
    initiated_by = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Farmer(db.Model):
    __tablename__ = 'farmers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    id_no = db.Column(db.String(50), nullable=False, unique=True)
    location = db.Column(db.String(255))
    size = db.Column(db.Float, default=0.0)
    crop = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TransportDispatch(db.Model):
    __tablename__ = 'transport_dispatches'
    id = db.Column(db.Integer, primary_key=True)
    farmer_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(255))
    service_type = db.Column(db.String(50))
    dispatch_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LedgerEntry(db.Model):
    __tablename__ = 'ledger_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    reference_id = db.Column(db.String(100)) # Can be loan ID, share ID, or generic
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
