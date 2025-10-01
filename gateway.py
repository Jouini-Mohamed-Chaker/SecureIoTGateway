#!/usr/bin/env python3
"""
SecureIoTGateway - Security proxy for IoT devices
Validates messages from MQTT devices and forwards to backend
"""

import json
import hmac
import hashlib
import time
import sqlite3
import uuid
from collections import defaultdict, deque
from datetime import datetime
import paho.mqtt.client as mqtt
import requests
from colorama import Fore, Back, Style, init

# Initialize colorama
init(autoreset=True)

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 8883
MQTT_TOPIC_SUBSCRIBE = "device/+/data"
MQTT_TOPIC_RESPONSE = "device/{}/response"
MQTT_CA_CERT = "certs/ca.crt"
MQTT_CLIENT_CERT = "certs/gateway.crt"
MQTT_CLIENT_KEY = "certs/gateway.key"

BACKEND_URL = "http://localhost:5000/device/{}/data"
DATABASE_PATH = "devices.db"

TIMESTAMP_TOLERANCE = 300  # 5 minutes in seconds
REPLAY_CACHE_SIZE = 1000  # Per device

# In-memory replay cache
replay_cache = defaultdict(lambda: deque(maxlen=REPLAY_CACHE_SIZE))

# Statistics
stats = {
    "messages_received": 0,
    "messages_validated": 0,
    "messages_rejected": 0,
    "messages_forwarded": 0
}


def log_header(message):
    """Print a header log message"""
    print(f"\n{Back.BLUE}{Fore.WHITE}{'='*80}{Style.RESET_ALL}")
    print(f"{Back.BLUE}{Fore.WHITE} {message:^78} {Style.RESET_ALL}")
    print(f"{Back.BLUE}{Fore.WHITE}{'='*80}{Style.RESET_ALL}\n")


def log_info(component, message):
    """Print an info log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{Fore.GREEN}[{component}]{Style.RESET_ALL} {message}")


def log_success(component, message):
    """Print a success log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{Fore.GREEN}[{component}]{Style.RESET_ALL} "
          f"{Fore.GREEN}✓{Style.RESET_ALL} {message}")


def log_warning(component, message):
    """Print a warning log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{Fore.YELLOW}[{component}]{Style.RESET_ALL} "
          f"{Fore.YELLOW}⚠{Style.RESET_ALL} {message}")


def log_error(component, message):
    """Print an error log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{Fore.RED}[{component}]{Style.RESET_ALL} "
          f"{Fore.RED}✗{Style.RESET_ALL} {message}")


def log_validation(step, status, message):
    """Print a validation step"""
    icon = "✓" if status else "✗"
    color = Fore.GREEN if status else Fore.RED
    print(f"  {color}[{step}]{Style.RESET_ALL} {color}{icon}{Style.RESET_ALL} {message}")


def init_database():
    """Initialize the SQLite database"""
    log_info("DATABASE", "Initializing database...")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            shared_secret TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    log_success("DATABASE", "Database initialized")


def get_device_secret(device_id):
    """Get the shared secret for a device"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT shared_secret FROM devices WHERE device_id = ?", (device_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        log_info("DATABASE", f"Retrieved secret for device: {Fore.MAGENTA}{device_id}{Style.RESET_ALL}")
        return result[0]
    else:
        log_error("DATABASE", f"Device not found: {Fore.MAGENTA}{device_id}{Style.RESET_ALL}")
        return None


def calculate_signature(device_id, timestamp, message_id, payload, secret):
    """Calculate HMAC-SHA256 signature for a message"""
    # Concatenate message components
    payload_str = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    message = f"{device_id}{timestamp}{message_id}{payload_str}"
    
    # Calculate HMAC
    signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature


def validate_message(message_data, topic):
    """Validate a message from a device"""
    log_header("MESSAGE VALIDATION")
    stats["messages_received"] += 1
    
    # Extract device_id from topic
    topic_parts = topic.split('/')
    if len(topic_parts) != 3:
        log_error("VALIDATION", "Invalid topic format")
        stats["messages_rejected"] += 1
        return False, None
    
    tls_device_id = topic_parts[1]
    log_info("VALIDATION", f"TLS Identity: {Fore.MAGENTA}{tls_device_id}{Style.RESET_ALL}")
    
    # Parse message
    try:
        message = json.loads(message_data)
        log_success("VALIDATION", "Message parsed successfully")
        print(f"  {Fore.CYAN}Raw message:{Style.RESET_ALL}")
        print(f"  {json.dumps(message, indent=4)}")
    except json.JSONDecodeError as e:
        log_error("VALIDATION", f"Invalid JSON: {e}")
        stats["messages_rejected"] += 1
        return False, None
    
    # Extract fields
    device_id = message.get('device_id')
    timestamp = message.get('timestamp')
    message_id = message.get('message_id')
    payload = message.get('payload')
    signature = message.get('signature')
    
    print(f"\n{Fore.YELLOW}Starting validation checks...{Style.RESET_ALL}\n")
    
    # Validation 1: Required fields
    if not all([device_id, timestamp, message_id, payload, signature]):
        log_validation("1. Required Fields", False, "Missing required fields")
        stats["messages_rejected"] += 1
        return False, None
    log_validation("1. Required Fields", True, "All required fields present")
    
    # Validation 2: Identity consistency
    if device_id != tls_device_id:
        log_validation("2. Identity Check", False, 
                      f"device_id '{device_id}' != TLS identity '{tls_device_id}'")
        stats["messages_rejected"] += 1
        return False, None
    log_validation("2. Identity Check", True, f"device_id matches TLS identity")
    
    # Validation 3: Timestamp freshness
    current_time = int(time.time())
    time_diff = abs(current_time - timestamp)
    
    if time_diff > TIMESTAMP_TOLERANCE:
        log_validation("3. Timestamp Check", False,
                      f"Time difference {time_diff}s exceeds tolerance {TIMESTAMP_TOLERANCE}s")
        log_error("VALIDATION", f"Message time: {datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')}")
        log_error("VALIDATION", f"Current time: {datetime.fromtimestamp(current_time).strftime('%H:%M:%S')}")
        stats["messages_rejected"] += 1
        return False, None
    log_validation("3. Timestamp Check", True,
                  f"Time difference {time_diff}s within tolerance ({TIMESTAMP_TOLERANCE}s)")
    
    # Validation 4: Replay detection
    if message_id in replay_cache[device_id]:
        log_validation("4. Replay Detection", False, f"Message ID already seen: {message_id}")
        stats["messages_rejected"] += 1
        return False, None
    log_validation("4. Replay Detection", True, f"Message ID is unique: {message_id[:8]}...")
    
    # Validation 5: Signature verification
    secret = get_device_secret(device_id)
    if not secret:
        log_validation("5. Signature Check", False, "Device not found in database")
        stats["messages_rejected"] += 1
        return False, None
    
    expected_signature = calculate_signature(device_id, timestamp, message_id, payload, secret)
    
    if signature != expected_signature:
        log_validation("5. Signature Check", False, "Signature mismatch")
        log_error("VALIDATION", f"Expected: {expected_signature[:32]}...")
        log_error("VALIDATION", f"Received: {signature[:32]}...")
        stats["messages_rejected"] += 1
        return False, None
    log_validation("5. Signature Check", True, "HMAC signature verified")
    
    # All checks passed
    replay_cache[device_id].append(message_id)
    stats["messages_validated"] += 1
    
    print(f"\n{Fore.GREEN}{Back.GREEN}{Fore.BLACK} ALL CHECKS PASSED {Style.RESET_ALL}")
    log_success("VALIDATION", f"Message validated successfully for {Fore.MAGENTA}{device_id}{Style.RESET_ALL}")
    
    return True, payload


def forward_to_backend(device_id, payload):
    """Forward validated payload to backend"""
    log_header("BACKEND FORWARDING")
    
    url = BACKEND_URL.format(device_id)
    log_info("BACKEND", f"Forwarding to: {Fore.CYAN}{url}{Style.RESET_ALL}")
    log_info("BACKEND", f"Payload: {json.dumps(payload)}")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        log_success("BACKEND", f"Response: {Fore.GREEN}{response.status_code}{Style.RESET_ALL}")
        log_info("BACKEND", f"Body: {response.text}")
        
        stats["messages_forwarded"] += 1
        return response
        
    except requests.exceptions.RequestException as e:
        log_error("BACKEND", f"Request failed: {e}")
        return None


def on_connect(client, userdata, flags, rc):
    """Callback for MQTT connection"""
    if rc == 0:
        log_success("MQTT", f"Connected to broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_SUBSCRIBE)
        log_info("MQTT", f"Subscribed to topic: {Fore.CYAN}{MQTT_TOPIC_SUBSCRIBE}{Style.RESET_ALL}")
    else:
        log_error("MQTT", f"Connection failed with code {rc}")


def on_message(client, userdata, msg):
    """Callback for MQTT message received"""
    log_info("MQTT", f"Message received on topic: {Fore.CYAN}{msg.topic}{Style.RESET_ALL}")
    
    # Validate message
    is_valid, payload = validate_message(msg.payload.decode('utf-8'), msg.topic)
    
    if is_valid:
        # Extract device_id from topic
        device_id = msg.topic.split('/')[1]
        
        # Forward to backend
        response = forward_to_backend(device_id, payload)
        
        if response and response.status_code == 200:
            # Send response back to device
            response_topic = MQTT_TOPIC_RESPONSE.format(device_id)
            client.publish(response_topic, response.text)
            log_success("MQTT", f"Response sent to device on topic: {Fore.CYAN}{response_topic}{Style.RESET_ALL}")
    
    # Print statistics
    print(f"\n{Fore.YELLOW}{'─'*80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Statistics:{Style.RESET_ALL}")
    print(f"  Received: {stats['messages_received']} | "
          f"Validated: {Fore.GREEN}{stats['messages_validated']}{Style.RESET_ALL} | "
          f"Rejected: {Fore.RED}{stats['messages_rejected']}{Style.RESET_ALL} | "
          f"Forwarded: {Fore.GREEN}{stats['messages_forwarded']}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'─'*80}{Style.RESET_ALL}\n")


def main():
    """Main function"""
    log_header("SECURE IOT GATEWAY STARTING")
    
    # Initialize database
    init_database()
    
    # Create MQTT client
    log_info("MQTT", "Initializing MQTT client...")
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Configure TLS
    log_info("MQTT", "Configuring TLS...")
    try:
        client.tls_set(
            ca_certs=MQTT_CA_CERT,
            certfile=MQTT_CLIENT_CERT,
            keyfile=MQTT_CLIENT_KEY
        )
        log_success("MQTT", "TLS configured with mutual authentication")
    except Exception as e:
        log_error("MQTT", f"TLS configuration failed: {e}")
        return
    
    # Connect to broker
    log_info("MQTT", f"Connecting to broker at {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        log_success("MQTT", "Connection initiated")
    except Exception as e:
        log_error("MQTT", f"Connection failed: {e}")
        return
    
    log_header("GATEWAY READY - WAITING FOR MESSAGES")
    
    # Start loop
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log_warning("GATEWAY", "Shutting down...")
        client.disconnect()
        log_info("GATEWAY", "Gateway stopped")


if __name__ == "__main__":
    main()