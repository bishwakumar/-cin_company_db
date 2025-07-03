import requests
import json
import time
import random
import string
import pika
import os
from db.models import create_search_table, get_connection
import subprocess

SEARCH_API_URL = "https://api.startupindia.gov.in/sih/api/noauth/search/profiles"
PROGRESS_FILE = "search_progress.json"

FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.startupindia.gov.in",
    "referer": "https://www.startupindia.gov.in/"
}

BASE_PAYLOAD = {
    "query": "A",
    "focusSector": False,
    "industries": [],
    "sectors": [],
    "states": [],
    "cities": [],
    "stages": [],
    "badges": [],
    "roles": ["Startup"],
    "sort": {
        "orders": [
            {
                "field": "name",
                "direction": "ASC"
            }
        ]
    },
    "dpiitRecogniseUser": True,
    "internationalUser": False,
    "page": 0
}

def load_progress():
    """Load the progress from file or initialize if not exists."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                progress = json.load(f)
                print(f"📝 Loaded progress: Last letter '{progress['current_letter']}', page {progress['current_page']}")
                return progress
        except Exception as e:
            print(f"⚠️ Error loading progress file: {e}")
    
    return {
        'current_letter': 'A',
        'current_page': 0,
        'processed_ids': [],
        'completed_letters': []
    }

def save_progress(letter, page, processed_ids, completed_letters):
    """Save the current progress to file."""
    progress = {
        'current_letter': letter,
        'current_page': page,
        'processed_ids': list(processed_ids),  # Convert set to list for JSON
        'completed_letters': list(completed_letters)
    }
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
        print(f"📝 Saved progress: Letter '{letter}', page {page}")
    except Exception as e:
        print(f"⚠️ Error saving progress: {e}")

def check_duplicate_id(cur, profile_id):
    """Check if profile_id already exists in database."""
    cur.execute("SELECT EXISTS(SELECT 1 FROM search WHERE profile_id = %s)", (profile_id,))
    return cur.fetchone()[0]

def make_search_api_request(payload, max_retries=5):
    attempt = 0
    backoff = 2
    while attempt < max_retries:
        headers = HEADERS.copy()
        headers["user-agent"] = FIXED_USER_AGENT
        try:
            response = requests.post(SEARCH_API_URL, headers=headers, json=payload)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", backoff))
                print(f"⏳ Rate limited. Sleeping for {retry_after} seconds...")
                time.sleep(retry_after)
                backoff = min(backoff * 2, 120)
                attempt += 1
                continue
            if response.status_code != 200:
                print(f"❌ Request failed with status {response.status_code}")
                time.sleep(backoff + random.uniform(0, 2))
                backoff = min(backoff * 2, 120)
                attempt += 1
                continue
            return response
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {str(e)}")
            time.sleep(backoff + random.uniform(0, 2))
            backoff = min(backoff * 2, 120)
            attempt += 1
    print(f"❌ Max retries reached for payload: {payload}")
    return None

def fetch_and_store_profiles(output_file="startup_profiles_filtered_xxx.json"):
    # Setup RabbitMQ connection
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='profile_id_queue', durable=True)

    # Load progress from file
    progress = load_progress()
    current_letter = progress['current_letter']
    current_page = progress['current_page']
    processed_ids = set(progress['processed_ids'])
    completed_letters = set(progress['completed_letters'])

    # Get database connection for duplicate checking
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Start from where we left off in the alphabet
        remaining_letters = [l for l in string.ascii_uppercase if l >= current_letter and l not in completed_letters]
        
        for letter in remaining_letters:
            print(f"🔠 Searching for startups starting with '{letter}'...")
            
            # If it's a new letter, start from page 0
            page = current_page if letter == current_letter else 0
            
            while True:
                print(f"  🔄 Fetching page {page} for query '{letter}'...")
                payload = BASE_PAYLOAD.copy()
                payload["query"] = letter
                payload["page"] = page

                try:
                    response = make_search_api_request(payload)
                    if response is None:
                        raise Exception("API request failed after retries")
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    print(f"  ❌ Error on page {page} for query '{letter}': {e}")
                    # Save progress before breaking
                    save_progress(letter, page, processed_ids, completed_letters)
                    break

                content = data.get("content", [])
                if not content:
                    print(f"  ✅ No more results found for query '{letter}'.")
                    completed_letters.add(letter)
                    save_progress(letter, page, processed_ids, completed_letters)
                    break

                # Process and store profiles
                batch = []
                for item in content:
                    profile_id = item.get("id")
                    
                    # Skip if we've already processed this ID
                    if not profile_id or profile_id in processed_ids or check_duplicate_id(cur, profile_id):
                        continue

                    # Prepare data for database
                    batch.append((
                        profile_id,
                        item.get("name"),
                        item.get("country"),
                        item.get("state"),
                        item.get("city")
                    ))
                    
                    # Send to RabbitMQ queue
                    channel.basic_publish(
                        exchange='',
                        routing_key='profile_id_queue',
                        body=profile_id,
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # Make message persistent
                        )
                    )
                    processed_ids.add(profile_id)

                # Batch insert into database
                if batch:
                    try:
                        args_str = ','.join(cur.mogrify('(%s,%s,%s,%s,%s)', x).decode('utf-8') for x in batch)
                        cur.execute(
                            f"""
                            INSERT INTO search (profile_id, name, country, state, city)
                            VALUES {args_str}
                            ON CONFLICT (profile_id) DO NOTHING
                            """
                        )
                        conn.commit()
                        print(f"  ✅ Inserted {len(batch)} new profiles")
                    except Exception as e:
                        print(f"  ❌ Postgres batch insert error: {e}")
                        conn.rollback()

                # Save progress after each page
                save_progress(letter, page, processed_ids, completed_letters)
                
                page += 1

            # Update current letter and page for next iteration
            current_letter = letter
            current_page = 0

    finally:
        cur.close()
        conn.close()
        connection.close()
        print(f"✅ Process completed. Processed {len(processed_ids)} unique profiles.")
        print(f"✅ Completed letters: {sorted(list(completed_letters))}")

def main():
    # Start the profile consumer in the background
    subprocess.Popen(['python3', 'api/profile.py'])
    create_search_table()
    fetch_and_store_profiles()

if __name__ == "__main__":
    main()
