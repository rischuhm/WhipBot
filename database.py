import sqlite3
import datetime

DB_NAME = "eventbot.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Registrations table
    c.execute('''CREATE TABLE IF NOT EXISTS registrations (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        is_admin BOOLEAN DEFAULT 0,
        is_neuling BOOLEAN DEFAULT 0,
        partner_name TEXT,
        status TEXT DEFAULT 'PENDING',
        registration_time TIMESTAMP
    )''')
    
    # Settings table
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Initialize registration status if not exists
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_open', '1')")
    
    conn.commit()
    conn.close()

def add_registration(user_id, username, full_name, is_neuling, partner_name):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO registrations 
                     (user_id, username, full_name, is_neuling, partner_name, registration_time, status)
                     VALUES (?, ?, ?, ?, ?, ?, 'PENDING')''',
                  (user_id, username, full_name, is_neuling, partner_name, datetime.datetime.now()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_registration(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_status(user_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE registrations SET status = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def get_all_registrations():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations")
    rows = c.fetchall()
    conn.close()
    return rows

def get_pending_registrations():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE status = 'PENDING'")
    rows = c.fetchall()
    conn.close()
    return rows

def get_accepted_count():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM registrations WHERE status = 'ACCEPTED'")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_waiting_list():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE status = 'WAITING' ORDER BY registration_time ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def is_registration_open():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'registration_open'")
    row = c.fetchone()
    conn.close()
    return row and row['value'] == '1'

def set_registration_open(is_open):
    conn = get_connection()
    c = conn.cursor()
    val = '1' if is_open else '0'
    c.execute("UPDATE settings SET value = ? WHERE key = 'registration_open'", (val,))
    conn.commit()
    conn.close()

def set_admin(user_id, is_admin):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE registrations SET is_admin = ? WHERE user_id = ?", (is_admin, user_id))
    conn.commit()
    conn.close()
