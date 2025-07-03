import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from db.models import get_connection

def export_synced_data(limit=150000):
    conn = get_connection()
    query = f"""
        SELECT profile_id, name, country, state, city, cin, pan, email, incorp_date, registered_address, registered_contact, cin_status, synced_at
        FROM synced_data
        ORDER BY id
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    # Remove timezone info from datetime columns for Excel compatibility
    if 'synced_at' in df.columns:
        df['synced_at'] = pd.to_datetime(df['synced_at'], errors='coerce').dt.tz_localize(None)
    # Export to Excel
    df.to_excel('synced_data_export_final.xlsx', index=False)
    # Export to CSV
    df.to_csv('synced_data_export_final.csv', index=False)
    print(f"Exported {len(df)} rows to 'synced_data_export.xlsx' and 'synced_data_export.csv'.")

if __name__ == "__main__":
    export_synced_data()
