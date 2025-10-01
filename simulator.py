#!/usr/bin/env python3
"""
IoT Device and Backend Simulator
Simulates an IoT device sending data and a backend receiving it
"""

import json
import hmac
import hashlib
import time
import uuid
import random
import threading
from datetime import datetime
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt
from colorama import Fore, Back, Style, init

# Initialize colorama
init(autoreset=True)

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 8883
MQTT_CA_CERT = "certs/ca.crt"

# Device configuration (will be overridden by command line)
DEVICE_ID = "sensor_001"
DEVICE_CERT = f"certs/{DEVICE_ID}.crt"
DEVICE_KEY = f"certs/{DEVICE_ID}.key"
SHARED_SECRET = "supersecretkey123"

MQTT_TOPIC_DATA = f"device/{DEVICE_ID}/data"
MQTT_TOPIC_RESPONSE = f"device/{DEVICE_ID}/response"

# Backend configuration
BACKEND_PORT = 5000

# Flask app for backend
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Backend statistics
backend_stats = {
    "messages_received": 0,
    "last_message": None
}


def log_header(message, color=Fore.BLUE):
    """Print a header log message"""
    print(f"\n{Back.BLUE}{Fore.WHITE}{'='*80}{Style.RESET_ALL}")
    print(f"{Back.BLUE}{Fore.WHITE} {message:^78} {Style.RESET_ALL}")
    print(f"{Back.BLUE}{Fore.WHITE}{'='*80}{Style.RESET_ALL}\n")


def log_info(component, message, component_color=Fore.GREEN):
    """Print an info log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{component_color}[{component}]{Style.RESET_ALL} {message}")


def log_success(component, message, component_color=Fore.GREEN):
    """Print a success log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{component_color}[{component}]{Style.RESET_ALL} "
          f"{Fore.GREEN}✓{Style.RESET_ALL} {message}")


def log_error(component, message, component_color=Fore.GREEN):
    """Print an error log message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} "
          f"{component_color}[{component}]{Style.RESET_ALL} "
          f"{Fore.RED}✗{Style.RESET_ALL} {message}")


def calculate_signature(device_id, timestamp, message_id, payload, secret):
    """Calculate HMAC-SHA256 signature for a message"""
    payload_str = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    message = f"{device_id}{timestamp}{message_id}{payload_str}"
    
    signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature


def create_device_message(device_id, payload, secret):
    """Create a signed message from device"""
    timestamp = int(time.time())
    message_id = str(uuid.uuid4())
    
    signature = calculate_signature(device_id, timestamp, message_id, payload, secret)
    
    message = {
        "device_id": device_id,
        "timestamp": timestamp,
        "message_id": message_id,
        "payload": payload,
        "signature": signature
    }
    
    return message


# ==================== BACKEND SIMULATION ====================

@app.route('/device/<device_id>/data', methods=['POST'])
def receive_device_data(device_id):
    """Backend endpoint to receive device data"""
    log_header(f"BACKEND RECEIVED DATA FROM {device_id}", Fore.MAGENTA)
    
    data = request.get_json()
    backend_stats["messages_received"] += 1
    backend_stats["last_message"] = data
    
    log_info("BACKEND", f"Device: {Fore.MAGENTA}{device_id}{Style.RESET_ALL}", Fore.MAGENTA)
    log_info("BACKEND", f"Payload: {Fore.YELLOW}{json.dumps(data, indent=2)}{Style.RESET_ALL}", Fore.MAGENTA)
    
    # Simulate processing
    response = {
        "status": "received",
        "message": "Data processed successfully",
        "timestamp": int(time.time())
    }
    
    # Check for alerts (example logic)
    if "temperature" in data:
        temp = data["temperature"]
        if temp > 30:
            response["alert"] = "HIGH_TEMPERATURE"
            log_info("BACKEND", f"🔥 Alert: High temperature detected ({temp}°C)", Fore.MAGENTA)
        elif temp < 10:
            response["alert"] = "LOW_TEMPERATURE"
            log_info("BACKEND", f"❄️  Alert: Low temperature detected ({temp}°C)", Fore.MAGENTA)
        else:
            response["alert"] = "NORMAL"
            log_success("BACKEND", f"Temperature normal ({temp}°C)", Fore.MAGENTA)
    
    log_success("BACKEND", f"Sending response to gateway", Fore.MAGENTA)
    print(f"  {Fore.YELLOW}{json.dumps(response, indent=2)}{Style.RESET_ALL}")
    
    print(f"\n{Fore.MAGENTA}{'─'*80}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}Backend Statistics:{Style.RESET_ALL}")
    print(f"  Total messages received: {Fore.GREEN}{backend_stats['messages_received']}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'─'*80}{Style.RESET_ALL}\n")
    
    return jsonify(response), 200


def run_backend():
    """Run the Flask backend server"""
    log_header("BACKEND SERVER STARTING", Fore.MAGENTA)
    log_info("BACKEND", f"Listening on port {BACKEND_PORT}", Fore.MAGENTA)
    log_info("BACKEND", f"Endpoint: {Fore.CYAN}http://localhost:{BACKEND_PORT}/device/<device_id>/data{Style.RESET_ALL}", Fore.MAGENTA)
    log_success("BACKEND", "Ready to receive data from gateway", Fore.MAGENTA)
    app.run(host='0.0.0.0', port=BACKEND_PORT, debug=False, use_reloader=False)


# ==================== DEVICE SIMULATION ====================

class IoTDevice:
    """Simulates an IoT device"""
    
    def __init__(self, device_id, cert, key, ca_cert, secret):
        self.device_id = device_id
        self.cert = cert
        self.key = key
        self.ca_cert = ca_cert
        self.secret = secret
        self.client = None
        self.connected = False
        self.message_count = 0
    
    def on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            log_success("DEVICE", f"Connected to broker", Fore.YELLOW)
            log_info("DEVICE", f"Device ID: {Fore.MAGENTA}{self.device_id}{Style.RESET_ALL}", Fore.YELLOW)
            
            # Subscribe to response topic
            client.subscribe(MQTT_TOPIC_RESPONSE)
            log_info("DEVICE", f"Subscribed to: {Fore.CYAN}{MQTT_TOPIC_RESPONSE}{Style.RESET_ALL}", Fore.YELLOW)
        else:
            log_error("DEVICE", f"Connection failed with code {rc}", Fore.YELLOW)
    
    def on_message(self, client, userdata, msg):
        """MQTT message received callback"""
        log_header(f"DEVICE RECEIVED RESPONSE", Fore.YELLOW)
        log_info("DEVICE", f"Topic: {Fore.CYAN}{msg.topic}{Style.RESET_ALL}", Fore.YELLOW)
        
        try:
            response = json.loads(msg.payload.decode('utf-8'))
            log_success("DEVICE", "Response parsed successfully", Fore.YELLOW)
            print(f"  {Fore.YELLOW}{json.dumps(response, indent=2)}{Style.RESET_ALL}")
            
            if "alert" in response:
                alert_color = Fore.RED if "HIGH" in response["alert"] or "LOW" in response["alert"] else Fore.GREEN
                log_info("DEVICE", f"Alert status: {alert_color}{response['alert']}{Style.RESET_ALL}", Fore.YELLOW)
        except json.JSONDecodeError:
            log_error("DEVICE", f"Invalid JSON in response", Fore.YELLOW)
    
    def connect(self):
        """Connect to MQTT broker"""
        log_header(f"DEVICE {self.device_id} CONNECTING", Fore.YELLOW)
        
        self.client = mqtt.Client(client_id=self.device_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Configure TLS
        log_info("DEVICE", "Configuring TLS with device certificate...", Fore.YELLOW)
        try:
            self.client.tls_set(
                ca_certs=self.ca_cert,
                certfile=self.cert,
                keyfile=self.key
            )
            log_success("DEVICE", "TLS configured", Fore.YELLOW)
        except Exception as e:
            log_error("DEVICE", f"TLS configuration failed: {e}", Fore.YELLOW)
            return False
        
        # Connect
        log_info("DEVICE", f"Connecting to {MQTT_BROKER}:{MQTT_PORT}...", Fore.YELLOW)
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            
            # Wait for connection
            timeout = 5
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self.connected:
                return True
            else:
                log_error("DEVICE", "Connection timeout", Fore.YELLOW)
                return False
                
        except Exception as e:
            log_error("DEVICE", f"Connection failed: {e}", Fore.YELLOW)
            return False
    
    def send_sensor_data(self, sensor_type="temperature"):
        """Send sensor data to gateway"""
        log_header(f"DEVICE SENDING DATA #{self.message_count + 1}", Fore.YELLOW)
        
        # Generate sensor data
        if sensor_type == "temperature":
            value = round(random.uniform(15.0, 35.0), 1)
            payload = {
                "temperature": value,
                "humidity": random.randint(40, 80),
                "sensor_type": "DHT22"
            }
        elif sensor_type == "motion":
            payload = {
                "motion_detected": random.choice([True, False]),
                "confidence": random.randint(70, 100)
            }
        else:
            payload = {"value": random.randint(0, 100)}
        
        log_info("DEVICE", f"Sensor reading: {Fore.CYAN}{json.dumps(payload)}{Style.RESET_ALL}", Fore.YELLOW)
        
        # Create signed message
        log_info("DEVICE", "Creating signed message...", Fore.YELLOW)
        message = create_device_message(self.device_id, payload, self.secret)
        
        # Log message details
        log_success("DEVICE", "Message created", Fore.YELLOW)
        print(f"  {Fore.YELLOW}Message ID:{Style.RESET_ALL} {message['message_id'][:16]}...")
        print(f"  {Fore.YELLOW}Timestamp:{Style.RESET_ALL} {message['timestamp']} ({datetime.fromtimestamp(message['timestamp']).strftime('%H:%M:%S')})")
        print(f"  {Fore.YELLOW}Signature:{Style.RESET_ALL} {message['signature'][:32]}...")
        
        # Publish message
        log_info("DEVICE", f"Publishing to topic: {Fore.CYAN}{MQTT_TOPIC_DATA}{Style.RESET_ALL}", Fore.YELLOW)
        
        message_json = json.dumps(message)
        result = self.client.publish(MQTT_TOPIC_DATA, message_json)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            log_success("DEVICE", "Message published successfully", Fore.YELLOW)
            self.message_count += 1
        else:
            log_error("DEVICE", f"Publish failed with code {result.rc}", Fore.YELLOW)
        
        print(f"\n{Fore.YELLOW}{'─'*80}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Device Statistics:{Style.RESET_ALL}")
        print(f"  Messages sent: {Fore.GREEN}{self.message_count}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'─'*80}{Style.RESET_ALL}\n")
        
        return result.rc == mqtt.MQTT_ERR_SUCCESS
    
    def disconnect(self):
        """Disconnect from broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            log_info("DEVICE", "Disconnected from broker", Fore.YELLOW)


def run_device_simulation():
    """Run the device simulation"""
    # Wait for backend to start
    time.sleep(2)
    
    # Create device
    device = IoTDevice(DEVICE_ID, DEVICE_CERT, DEVICE_KEY, MQTT_CA_CERT, SHARED_SECRET)
    
    # Connect
    if not device.connect():
        log_error("DEVICE", "Failed to connect to broker", Fore.YELLOW)
        return
    
    log_header("DEVICE READY - STARTING TO SEND DATA", Fore.YELLOW)
    
    try:
        # Send messages at intervals
        while True:
            time.sleep(3)  # Wait 3 seconds between messages
            device.send_sensor_data("temperature")
    except KeyboardInterrupt:
        log_info("DEVICE", "Stopping device...", Fore.YELLOW)
        device.disconnect()


def main():
    """Main function - runs both backend and device"""
    print(f"{Fore.CYAN}")
    print("""
    ╔═══════════════════════════════════════════════════════════════════════╗
    ║                                                                       ║
    ║              SecureIoTGateway - Device & Backend Simulator            ║
    ║                                                                       ║
    ╚═══════════════════════════════════════════════════════════════════════╝
    """)
    print(Style.RESET_ALL)
    
    log_info("SIMULATOR", "Starting backend server thread...")
    backend_thread = threading.Thread(target=run_backend, daemon=True)
    backend_thread.start()
    
    log_info("SIMULATOR", "Starting device simulation thread...")
    device_thread = threading.Thread(target=run_device_simulation, daemon=True)
    device_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_info("SIMULATOR", "\nShutting down simulator...")
        print(f"\n{Fore.GREEN}Simulator stopped.{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()