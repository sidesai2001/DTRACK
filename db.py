import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "dtrack.db")

# TEMPORARY: Delete old database to apply schema changes
# Remove this block after first deployment


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_columns(table: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in c.fetchall()]
    conn.close()
    return cols

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            approved INTEGER DEFAULT 0,
            valid_till TEXT,
            password_expiry TEXT,
            parent_user TEXT,
            created_on TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Main HDD records - only admin can add, user assigns to subuser
    c.execute("""
        CREATE TABLE IF NOT EXISTS hdd_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_no TEXT UNIQUE NOT NULL,
            unit_space TEXT,
            team_code TEXT,
            assigned_subuser TEXT,
            premise_name TEXT,
            date_search TEXT,
            date_seized TEXT,
            data_details TEXT,
            status TEXT DEFAULT 'available',
            created_by TEXT,
            created_on TEXT,
            barcode_value TEXT,
            FOREIGN KEY (team_code) REFERENCES users(username),
            FOREIGN KEY (assigned_subuser) REFERENCES users(username)
        )
    """)
    
    # Extraction records - admin disburses to vendor when received from user
    c.execute("""
        CREATE TABLE IF NOT EXISTS extraction_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_hdd_sn TEXT NOT NULL,
            unit_space TEXT,
            team_code TEXT,
            data_details TEXT,
            date_extraction_start TEXT,
            extracted_hdd_sn TEXT,
            extracted_by TEXT,
            working_copy_sns TEXT,
            date_receiving TEXT,
            assigned_user TEXT,
            created_by TEXT,
            created_on TEXT,
            FOREIGN KEY (original_hdd_sn) REFERENCES hdd_records(serial_no)
        )
    """)
    
    # Analysis records - admin disburses to analyst when received from vendor
    c.execute("""
        CREATE TABLE IF NOT EXISTS analysis_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracted_hdd_sn TEXT NOT NULL,
            analyst_name TEXT,
            date_disburse TEXT,
            analysis_notes TEXT,
            status TEXT DEFAULT 'in_progress',
            created_by TEXT,
            created_on TEXT,
            FOREIGN KEY (extracted_hdd_sn) REFERENCES extraction_records(extracted_hdd_sn)
        )
    """)
    
    # Activity logs
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Options table for Units and Vendors
    c.execute("""
        CREATE TABLE IF NOT EXISTS options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(type, name)
        )
    """)
    
    # Insert default units if table is empty
    c.execute("SELECT COUNT(*) FROM options WHERE type='unit'")
    if c.fetchone()[0] == 0:
        default_units = [
            "4(1) Delhi", "4(2) Mumbai", "4(3) Kolkata", "4(4) Chennai",
            "4(5) Hyderabad", "4(6) Bangalore", "4(7) Lucknow", "4(8) Chandigarh"
        ]
        for u in default_units:
            c.execute("INSERT OR IGNORE INTO options (type, name) VALUES ('unit', ?)", (u,))
    
    # Insert default vendors if table is empty
    c.execute("SELECT COUNT(*) FROM options WHERE type='vendor'")
    if c.fetchone()[0] == 0:
        default_vendors = ["Cyint", "TechForensics", "DataRecovery Pro"]
        for v in default_vendors:
            c.execute("INSERT OR IGNORE INTO options (type, name) VALUES ('vendor', ?)", (v,))
    
    # Indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_hdd_team ON hdd_records(team_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_hdd_subuser ON hdd_records(assigned_subuser)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_hdd_serial ON hdd_records(serial_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_hdd_status ON hdd_records(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_parent ON users(parent_user)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_options_type ON options(type)")
    
    conn.commit()
    conn.close()

init_db()