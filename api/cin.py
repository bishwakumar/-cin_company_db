import requests
import time
import random
import json
import pika
import sys
import os

# Add the parent directory to sys.path to import from db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.models import create_cin_table, batch_insert_cin_details

BATCH_SIZE = 10
cin_batch = []

FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def create_empty_record(profile_id, cin, status, error_msg=None):
    """Create a record for cases where CIN details are not found."""
    return {
        "profile_id": profile_id,
        "cin": cin,
        "email": "",
        "incorpdate": "",
        "registeredAddress": "",
        "registeredContactNo": "",
        "status": f"{status}: {error_msg}" if error_msg else status
    }

def process_cin(profile_id, cin, max_retries=1):
    print(f"[*] Processing CIN: {cin} for profile: {profile_id}")
    base_headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://www.startupindia.gov.in",
        "referer": "https://www.startupindia.gov.in/"
    }
    url = f"https://api.startupindia.gov.in/sih/api/noauth/dpiit/services/cin/info?cin={cin}"
    attempt = 0
    backoff = 2
    while attempt < max_retries:
        headers = base_headers.copy()
        headers["user-agent"] = FIXED_USER_AGENT
        try:
            response = requests.get(url, headers=headers)
            print(f"[*] API Response status for {cin}: {response.status_code}")
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", backoff))
                print(f"⏳ Rate limited. Sleeping for {retry_after} seconds...")
                time.sleep(retry_after)
                backoff = min(backoff * 2, 120)  # Cap backoff at 2 minutes
                attempt += 1
                continue
            if response.status_code != 200:
                error_msg = f"Request failed with status {response.status_code}"
                print(f"❌ {error_msg}")
                time.sleep(backoff + random.uniform(0, 2))
                backoff = min(backoff * 2, 120)
                attempt += 1
                continue
            data = response.json()
            cin_data = data.get("data", {})
            if not cin_data:
                error_msg = "No data returned from API"
                print(f"⚠️ {error_msg}")
                return create_empty_record(profile_id, cin, "NO_DATA", error_msg)
            extracted = {
                "profile_id": profile_id,
                "cin": cin_data.get("cin", ""),
                "email": cin_data.get("email", ""),
                "incorpdate": cin_data.get("incorpdate", ""),
                "registeredAddress": cin_data.get("registeredAddress", ""),
                "registeredContactNo": cin_data.get("registeredContactNo", ""),
                "status": "SUCCESS"
            }
            if not extracted["cin"]:
                error_msg = "Missing CIN in API response"
                print(f"⚠️ {error_msg}")
                return create_empty_record(profile_id, cin, "INVALID_DATA", error_msg)
            print(f"✅ Successfully extracted data for {cin}: {json.dumps(extracted, indent=2)}")
            return extracted
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            print(f"❌ {error_msg}")
            time.sleep(backoff + random.uniform(0, 2))
            backoff = min(backoff * 2, 120)
            attempt += 1
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response: {str(e)}"
            print(f"❌ {error_msg}")
            return create_empty_record(profile_id, cin, "JSON_ERROR", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"❌ {error_msg}")
            time.sleep(backoff + random.uniform(0, 2))
            backoff = min(backoff * 2, 120)
            attempt += 1
    # If all retries failed
    return create_empty_record(profile_id, cin, "FAILED", f"Max retries reached after {max_retries} attempts")

def process_batch():
    global cin_batch
    if cin_batch:
        try:
            print(f"\n[*] Processing batch of {len(cin_batch)} records...")
            print(f"[*] Batch contents: {json.dumps(cin_batch, indent=2)}")
            batch_insert_cin_details(cin_batch)
            print(f"✅ Successfully inserted batch of {len(cin_batch)} records")
            cin_batch = []
        except Exception as e:
            print(f"❌ Failed to insert batch: {str(e)}")
            # Don't clear the batch on error, will retry on next batch
            raise

def callback(ch, method, properties, body):
    global cin_batch
    try:
        msg = json.loads(body.decode())
        print(f"\n[*] Received message: {json.dumps(msg, indent=2)}")
        
        profile_id = msg.get("profile_id")
        cin = msg.get("cin")
        
        if not cin or not profile_id:
            print(f"⚠️ Missing required fields in message: {msg}")
            if cin:  # If we at least have a CIN, store the error
                record = create_empty_record(profile_id or "UNKNOWN", cin, "INVALID_MESSAGE", "Missing profile_id")
                cin_batch.append(record)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        # Process CIN and always get a record (either with data or error status)
        record = process_cin(profile_id, cin)
        print(f"[*] Adding to batch (current size: {len(cin_batch)})")
        cin_batch.append(record)
            
        if len(cin_batch) >= BATCH_SIZE:
            process_batch()
                
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
        # --- Auto-close logic: check if cin_queue is empty ---
        method_frame = ch.queue_declare(queue='cin_queue', passive=True)
        if method_frame.method.message_count == 0:
            print("[!] cin_queue is empty. Flushing remaining batch and shutting down...")
            flush_remaining_batch()
            ch.connection.close()
            print("[x] Connection closed. Exiting.")
            sys.exit(0)
        # --- End auto-close logic ---
        
    except json.JSONDecodeError as e:
        print(f"❌ Failed to decode message: {str(e)}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"❌ Unexpected error in callback: {str(e)}")
        # Don't acknowledge on unexpected errors - message will be requeued
        raise

def flush_remaining_batch():
    print("\n[*] Flushing remaining batch...")
    process_batch()

print("[*] Creating CIN details table if it doesn't exist...")
create_cin_table()

print("[*] Connecting to RabbitMQ...")
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.queue_declare(queue='cin_queue', durable=True)
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='cin_queue', on_message_callback=callback)

print("[*] Waiting for CINs from cin_queue. To exit press CTRL+C")

try:
    channel.start_consuming()
except KeyboardInterrupt:
    print("\n[!] Caught keyboard interrupt. Shutting down...")
    flush_remaining_batch()
    connection.close()
    print("[x] Connection closed. Exiting.")
except Exception as e:
    print(f"\n❌ Unexpected error: {str(e)}")
    flush_remaining_batch()
    connection.close()
    raise
