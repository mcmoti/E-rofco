import sqlite3

def migrate():
    conn = sqlite3.connect('sacco_portal.db')
    cursor = conn.cursor()
    
    # Add column
    try:
        cursor.execute("ALTER TABLE applications ADD COLUMN repaid_amount FLOAT DEFAULT 0.0")
        print("Added repaid_amount column successfully.")
    except sqlite3.OperationalError as e:
        print(f"Column might exist: {e}")
        
    # Create table loan_repayments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS loan_repayments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id VARCHAR(50) NOT NULL,
        amount FLOAT NOT NULL,
        paid_by VARCHAR(100) NOT NULL,
        receipt_number VARCHAR(100),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(application_id) REFERENCES applications(id)
    )
    """)
    print("Created loan_repayments table successfully.")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
