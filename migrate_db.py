from app import app, db
from models import Application, LoanRepayment
import sqlite3

def migrate():
    # Adding repaid_amount to applications
    conn = sqlite3.connect('sacco_portal.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE applications ADD COLUMN repaid_amount FLOAT DEFAULT 0.0")
        conn.commit()
        print("Added repaid_amount column successfully.")
    except sqlite3.OperationalError as e:
        print(f"OperationalError (might already exist): {e}")
    conn.close()

    # Creating loan_repayments table via SQLAlchemy create_all
    with app.app_context():
        db.create_all()
        print("Tables synced via SQLAlchemy.")

if __name__ == "__main__":
    migrate()
