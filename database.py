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
    
    # Drop existing tables for clean slate (as per plan)
    c.execute("DROP TABLE IF EXISTS registrations")
    c.execute("DROP TABLE IF EXISTS events")
    c.execute("DROP TABLE IF EXISTS settings")

    # Events table
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        date TEXT,
        is_open BOOLEAN DEFAULT 0,
        seat_limit INTEGER DEFAULT 35
    )''')
    
    # Users table (global registry of all users who started the bot)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        last_seen TIMESTAMP
    )''')

    # Registrations table
    c.execute('''CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_id INTEGER,
        username TEXT,
        full_name TEXT,
        is_admin BOOLEAN DEFAULT 0,
        is_neuling BOOLEAN DEFAULT 0,
        partner_name TEXT,
        status TEXT DEFAULT 'PENDING',
        registration_time TIMESTAMP,
        FOREIGN KEY(event_id) REFERENCES events(id),
        UNIQUE(user_id, event_id)
    )''')
    
    conn.commit()
    conn.close()

# --- Event Operations ---

def create_event(name, seat_limit=35):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO events (name, seat_limit) VALUES (?, ?)", (name, seat_limit))
        event_id = c.lastrowid
        conn.commit()
        return event_id
    finally:
        conn.close()

def get_events():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM events")
    rows = c.fetchall()
    conn.close()
    return rows

def get_event(event_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = c.fetchone()
    conn.close()
    return row

def set_event_open(event_id, is_open):
    conn = get_connection()
    c = conn.cursor()
    val = 1 if is_open else 0
    c.execute("UPDATE events SET is_open = ? WHERE id = ?", (val, event_id))
    conn.commit()
    conn.close()

# --- Registration Operations ---

def add_registration(user_id, event_id, username, full_name, is_neuling, partner_name):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO registrations 
                     (user_id, event_id, username, full_name, is_neuling, partner_name, registration_time, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')''',
                  (user_id, event_id, username, full_name, is_neuling, partner_name, datetime.datetime.now()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_registration(user_id, event_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE user_id = ? AND event_id = ?", (user_id, event_id))
    row = c.fetchone()
    conn.close()
    return row

def get_user_registrations(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT r.*, e.name as event_name 
        FROM registrations r 
        JOIN events e ON r.event_id = e.id 
        WHERE r.user_id = ?
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_status(user_id, event_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE registrations SET status = ? WHERE user_id = ? AND event_id = ?", (status, user_id, event_id))
    conn.commit()
    conn.close()

def get_event_registrations(event_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE event_id = ?", (event_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_pending_registrations(event_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE event_id = ? AND status = 'PENDING'", (event_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_waiting_list(event_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM registrations WHERE event_id = ? AND status = 'WAITING' ORDER BY registration_time ASC", (event_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def set_admin(user_id, event_id, is_admin):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE registrations SET is_admin = ? WHERE user_id = ? AND event_id = ?", (is_admin, user_id, event_id))
    conn.commit()
    conn.close()

# --- User Operations ---

def upsert_user(user_id, username, full_name):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT OR REPLACE INTO users (user_id, username, full_name, last_seen)
                     VALUES (?, ?, ?, ?)''', 
                  (user_id, username, full_name, datetime.datetime.now()))
        conn.commit()
    finally:
        conn.close()

def get_user_by_username(username):
    if not username:
        return None
    # Remove @ if present
    if username.startswith('@'):
        username = username[1:]
        
    conn = get_connection()
    c = conn.cursor()
    # Case insensitive search
    c.execute("SELECT * FROM users WHERE LOWER(username) = ?", (username.lower(),))
    row = c.fetchone()
    conn.close()
    return row
