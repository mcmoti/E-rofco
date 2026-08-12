import sqlite3

def update_db():
    conn = sqlite3.connect('sacco_portal.db')
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ledger_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        category VARCHAR(100) NOT NULL,
        amount FLOAT NOT NULL,
        description TEXT,
        reference_id VARCHAR(100),
        created_at DATETIME
    )
    """)
    
    conn.commit()
    conn.close()
    print("Ledger table created successfully.")

if __name__ == '__main__':
    update_db()
