# db/models.py
import psycopg2
from config import DB_CONFIG
import json

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def create_search_table():
    """Create the search table if it does not exist."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search (
            id SERIAL PRIMARY KEY,
            profile_id TEXT UNIQUE,
            name TEXT,
            country TEXT,
            state TEXT,
            city TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def create_profile_table():
    """Create the profile table if it does not exist."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id SERIAL PRIMARY KEY,
            profile_id TEXT UNIQUE,
            cin TEXT,
            pan TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def create_cin_table():
    """Create the cin_details table if it does not exist."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cin_details (
            id SERIAL PRIMARY KEY,
            profile_id TEXT,
            cin TEXT UNIQUE,
            email TEXT,
            incorp_date TEXT,
            registered_address TEXT,
            registered_contact TEXT,
            status TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def create_synced_data_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synced_data (
            id SERIAL PRIMARY KEY,
            profile_id TEXT,
            name TEXT,
            country TEXT,
            state TEXT,
            city TEXT,
            cin TEXT,
            pan TEXT,
            email TEXT,
            incorp_date TEXT,
            registered_address TEXT,
            registered_contact TEXT,
            cin_status TEXT,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def batch_insert_profiles(profiles):
    """Insert a batch of profile dicts into the profile table."""
    if not profiles:
        return
    conn = get_connection()
    cur = conn.cursor()
    try:
        args_list = [
            (p["profile_id"], p["cin"], p["pan"])
            for p in profiles
        ]
        args_str = ','.join(cur.mogrify('(%s,%s,%s)', x).decode('utf-8') for x in args_list)
        cur.execute(
            f"""
            INSERT INTO profile (profile_id, cin, pan)
            VALUES {args_str}
            ON CONFLICT (profile_id) DO NOTHING;
            """
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Postgres batch insert error: {e}")
    finally:
        cur.close()
        conn.close()

def insert_cin_details(cin_info):
    """Insert a single CIN details record into the cin_details table."""
    if not cin_info:
        return
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO cin_details 
            (cin, email, incorp_date, registered_address, registered_contact)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (cin) DO UPDATE SET
                email = EXCLUDED.email,
                incorp_date = EXCLUDED.incorp_date,
                registered_address = EXCLUDED.registered_address,
                registered_contact = EXCLUDED.registered_contact,
                created_at = CURRENT_TIMESTAMP;
            """,
            (
                cin_info["cin"],
                cin_info["email"],
                cin_info["incorpdate"],
                cin_info["registeredAddress"],
                cin_info["registeredContactNo"]
            )
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Postgres insert error for CIN {cin_info.get('cin')}: {e}")
    finally:
        cur.close()
        conn.close()

def batch_insert_cin_details(cin_details_list):
    """Insert a batch of CIN details into the cin_details table."""
    if not cin_details_list:
        return
    conn = get_connection()
    cur = conn.cursor()
    try:
        args_list = [
            (
                c["profile_id"],
                c["cin"],
                c["email"],
                c["incorpdate"],
                c["registeredAddress"],
                c["registeredContactNo"],
                c["status"]
            ) for c in cin_details_list
        ]
        args_str = ','.join(cur.mogrify('(%s,%s,%s,%s,%s,%s,%s)', x).decode('utf-8') for x in args_list)
        cur.execute(
            f"""
            INSERT INTO cin_details 
            (profile_id, cin, email, incorp_date, registered_address, registered_contact, status)
            VALUES {args_str}
            ON CONFLICT (cin) DO UPDATE SET
                profile_id = EXCLUDED.profile_id,
                email = EXCLUDED.email,
                incorp_date = EXCLUDED.incorp_date,
                registered_address = EXCLUDED.registered_address,
                registered_contact = EXCLUDED.registered_contact,
                status = EXCLUDED.status,
                created_at = CURRENT_TIMESTAMP;
            """
        )
        conn.commit()
    except Exception as e:
        print(f"❌ Postgres batch insert error for CIN details: {e}")
    finally:
        cur.close()
        conn.close()


