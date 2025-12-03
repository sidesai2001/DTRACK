import os, hashlib
from db import get_conn
from datetime import datetime, timedelta

def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return salt.hex() + ":" + dk.hex()

def check_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        new_dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000).hex()
        return new_dk == dk_hex
    except Exception:
        return False

def create_user(username: str, password: str, role: str = 'user', approved: int = 0, valid_till: str = None, password_expiry: str = None):
    conn = get_conn(); c = conn.cursor()
    pw_hash = hash_password(password)
    c.execute('INSERT INTO users(username, password_hash, role, approved, valid_till, password_expiry) VALUES (?,?,?,?,?,?)',
              (username, pw_hash, role, approved, valid_till, password_expiry))
    conn.commit(); conn.close()

def get_user(username: str):
    conn = get_conn(); c = conn.cursor()
    row = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    return row

def log_action(username: str, action: str):
    conn = get_conn(); c = conn.cursor()
    c.execute('INSERT INTO logs(username, action, ts) VALUES (?,?,?)', (username, action, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()

def ensure_default_admin():
    conn = get_conn(); c = conn.cursor()
    row = c.execute('SELECT * FROM users WHERE username=?', ('admin',)).fetchone()
    if not row:
        pw_hash = hash_password('admin123')
        c.execute('INSERT INTO users(username, password_hash, role, approved) VALUES (?,?,?,1)', ('admin', pw_hash, 'admin'))
        conn.commit()
    conn.close()

def fix_selectbox_color():
    st.markdown("""
        <style>

        /* Fix selected text inside the selectbox */
        div[data-baseweb="select"] > div {
            color: black !important;
        }

        /* Fix dropdown menu text */
        div[data-baseweb="menu"] div {
            color: black !important;
        }

        /* Fix placeholder text */
        div[data-baseweb="select"] span {
            color: black !important;
        }

        /* Fix selected item highlight */
        div[data-baseweb="select"] [aria-selected="true"] {
            background-color: #dce6ff !important;
            color: black !important;
        }

        /* Control itself (the box) */
        div[data-baseweb="select"] {
            background-color: white !important;
            color: black !important;
        }

        /* Fix arrow icon visibility */
        div[data-baseweb="select"] svg {
            fill: black !important;
        }

        </style>
    """, unsafe_allow_html=True)