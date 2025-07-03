import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.models import get_connection, create_synced_data_table

def sync():
    create_synced_data_table()
    conn = get_connection()
    cur = conn.cursor()
    # Clear the synced_data table before refreshing
    cur.execute("TRUNCATE synced_data;")
    # Join search, profile, cin_details
    cur.execute('''
        INSERT INTO synced_data (
            profile_id, name, country, state, city, cin, pan, email, incorp_date, registered_address, registered_contact, cin_status, synced_at
        )
        SELECT
            s.profile_id,
            s.name,
            s.country,
            s.state,
            s.city,
            p.cin,
            p.pan,
            c.email,
            c.incorp_date,
            c.registered_address,
            c.registered_contact,
            c.status as cin_status,
            CURRENT_TIMESTAMP
        FROM search s
        LEFT JOIN profile p ON s.profile_id = p.profile_id
        LEFT JOIN cin_details c ON p.cin = c.cin
        WHERE (c.email IS NOT NULL AND c.email <> '') OR (c.registered_contact IS NOT NULL AND c.registered_contact <> '')
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("[✓] synced_data table updated.")

if __name__ == "__main__":
    sync()
