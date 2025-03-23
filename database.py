import sqlite3
import datetime
import os

DB_PATH = "crisis_alerts.db"

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create alerts table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'potential'
    )
    ''')
    
    # Create subscriptions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL UNIQUE,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        radius REAL NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

def insert_alert(text, lat, lon):
    """Insert a new potential alert into the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (text, lat, lon, time) VALUES (?, ?, ?, ?)",
        (text, lat, lon, datetime.datetime.now())
    )
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return alert_id

def update_alert_status(alert_id, status):
    """Update an alert status (confirmed or dismissed)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE alerts SET status = ? WHERE id = ?",
        (status, alert_id)
    )
    conn.commit()
    conn.close()

def register_user(phone, lat, lon, radius):
    """Register a new user for notifications"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO subscriptions (phone, lat, lon, radius) VALUES (?, ?, ?, ?)",
            (phone, lat, lon, radius)
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # Phone number already exists
        success = False
    finally:
        conn.close()
    return success

def get_potential_alerts():
    """Get all potential alerts for review"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alerts WHERE status in ('pending','potential') ORDER BY time DESC")
    alerts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return alerts

def get_all_users():
    """Get all registered users"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

def get_alert_by_id(alert_id):
    """Get alert details by ID"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    alert = cursor.fetchone()
    conn.close()
    return dict(alert) if alert else None
