import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import time
import random
import json
import pika
from db.models import create_profile_table, batch_insert_profiles
import concurrent.futures
import signal
import queue
import threading
import multiprocessing

headers = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.startupindia.gov.in",
    "referer": "https://www.startupindia.gov.in/",
    "user-agent": "Mozilla/5.0"
}

batch_profiles = []
BATCH_SIZE = 10

# Setup RabbitMQ connection for publishing profile_id and cin
producer_connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
producer_channel = producer_connection.channel()
producer_channel.queue_declare(queue='cin_queue', durable=True)

# ThreadPoolExecutor for concurrent processing
executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

# Track if shutdown is requested
graceful_shutdown = False

publish_queue = queue.Queue()
PUBLISH_SENTINEL = object()

def shutdown(signum=None, frame=None):
    global graceful_shutdown
    graceful_shutdown = True
    print("\n[!] Shutdown requested. Cleaning up...")

def save_batch_if_needed(force=False):
    """Save the current batch if it reaches BATCH_SIZE or if force=True."""
    global batch_profiles
    if batch_profiles and (len(batch_profiles) >= BATCH_SIZE or force):
        print(f"💾 Saving batch of {len(batch_profiles)} profiles to Postgres...")
        batch_insert_profiles(batch_profiles)
        batch_profiles.clear()

def publisher_thread_func():
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='cin_queue', durable=True)
    while True:
        item = publish_queue.get()
        if item is PUBLISH_SENTINEL:
            break
        msg = item
        try:
            channel.basic_publish(
                exchange='',
                routing_key='cin_queue',
                body=msg,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"[→] Sent to cin_queue: {msg}")
        except Exception as e:
            print(f"[!] Failed to publish message: {e}")
        finally:
            publish_queue.task_done()
    connection.close()

publisher_thread = threading.Thread(target=publisher_thread_func, daemon=True)
publisher_thread.start()

def process_profile(profile_id):
    url = f"https://api.startupindia.gov.in/sih/api/common/replica/user/profile/{profile_id}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Request failed for profile ID {profile_id} with status {response.status_code}")
        return
    try:
        data = response.json()
        user_data = data.get("user", {})
        startup_data = user_data.get("startup", {})
        extracted = {
            "profile_id": profile_id,
            "cin": startup_data.get("cin"),
            "pan": startup_data.get("pan"),
            "members": startup_data.get("members", [])
        }
        batch_profiles.append(extracted)
        # Put message onto the publish queue instead of publishing directly
        msg = json.dumps({"profile_id": profile_id, "cin": extracted["cin"] or ""})
        publish_queue.put(msg)
        save_batch_if_needed()
        print(f"✅ Added data for {profile_id}")
    except Exception as e:
        print(f"⚠️ Failed to process {profile_id}: {e}")
    # Remove or reduce sleep for faster processing
    # time.sleep(random.uniform(1, 2))

def consumer_process(profile_id_queue):
    import pika
    def callback(ch, method, properties, body):
        profile_id = body.decode()
        if profile_id == 'STOP':
            print("[x] Received STOP signal. Exiting consumer.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            ch.stop_consuming()
            return
        profile_id_queue.put(profile_id)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    print("[x] Consumer process: Waiting for profile IDs from RabbitMQ. To exit press CTRL+C")
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='profile_id_queue', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='profile_id_queue', on_message_callback=callback)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[!] Consumer process: Stopped consuming.")
    finally:
        connection.close()
        print("[x] Consumer process: Connection closed. Exiting.")

if __name__ == "__main__":
    # Register signal handler for graceful shutdown (main process only)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    # Setup multiprocessing queue
    mp_profile_id_queue = multiprocessing.Queue()
    # Start consumer process
    consumer_proc = multiprocessing.Process(target=consumer_process, args=(mp_profile_id_queue,))
    consumer_proc.start()

    create_profile_table()
    print("[x] Main process: Waiting for profile IDs from consumer process...")
    try:
        while not graceful_shutdown:
            try:
                profile_id = mp_profile_id_queue.get(timeout=1)
                if profile_id == 'STOP':
                    print("[x] Main process: Received STOP signal. Initiating shutdown.")
                    break
                executor.submit(process_profile, profile_id)
            except queue.Empty:
                # If the consumer process is no longer alive and queue is empty, break
                if not consumer_proc.is_alive():
                    print("[x] Consumer process ended and queue is empty. Shutting down main process.")
                    break
                continue
    except KeyboardInterrupt:
        print("[!] Main process: KeyboardInterrupt received.")
    finally:
        print("[!] Cleaning up: waiting for threads to finish and closing connections...")
        executor.shutdown(wait=True)
        save_batch_if_needed(force=True)
        publish_queue.put(PUBLISH_SENTINEL)
        publisher_thread.join()
        consumer_proc.terminate()
        consumer_proc.join()
        print("[x] All connections closed. Exiting.")
