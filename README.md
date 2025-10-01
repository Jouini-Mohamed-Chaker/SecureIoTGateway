# SecureIoTGateway - Complete Setup & Usage Guide

A security gateway that sits between IoT devices and a backend server, validating all messages with TLS and HMAC signatures before forwarding them.

---

## 📋 Table of Contents

1. [Quick Start (Automated)](#quick-start-automated)
2. [Manual Setup (Detailed)](#manual-setup-detailed)
3. [Running the System](#running-the-system)
4. [Adding New Devices](#adding-new-devices)
5. [Architecture Overview](#architecture-overview)
6. [Troubleshooting](#troubleshooting)
7. [Security Features](#security-features)

---

## 🚀 Quick Start (Automated)

### Prerequisites
- Ubuntu/Debian Linux (20.04 or later)
- Root/sudo access
- Internet connection

### Installation (One Command)

```bash
chmod +x setup.sh
./setup.sh
```

This will automatically:
- ✅ Install Mosquitto MQTT broker
- ✅ Install Python dependencies
- ✅ Generate all SSL/TLS certificates
- ✅ Configure Mosquitto for mutual TLS
- ✅ Create device database with 3 sample devices
- ✅ Create helper scripts

After setup completes, follow the [Running the System](#running-the-system) section.

---

## 🔧 Manual Setup (Detailed)

If you prefer to understand each step or the automated script fails, follow this guide.

### Step 1: Install System Packages

```bash
# Update package list
sudo apt-get update

# Install Mosquitto MQTT broker
sudo apt-get install -y mosquitto mosquitto-clients

# Install OpenSSL
sudo apt-get install -y openssl

# Install Python and pip
sudo apt-get install -y python3 python3-pip python3-venv

# Install SQLite
sudo apt-get install -y sqlite3
```

**Verify installations:**
```bash
mosquitto -h        # Should show version
openssl version     # Should show OpenSSL version
python3 --version   # Should show Python 3.x
sqlite3 --version   # Should show SQLite version
```

---

### Step 2: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
pip install paho-mqtt requests colorama flask

# Deactivate when done (for now)
deactivate
```

**Required Python packages:**
- `paho-mqtt` - MQTT client library
- `requests` - HTTP client for backend forwarding
- `colorama` - Colored terminal output
- `flask` - Backend server for simulation

---

### Step 3: Generate SSL/TLS Certificates

SSL certificates are used for mutual TLS authentication between devices and the gateway.

```bash
# Create certificates directory
mkdir -p certs
cd certs
```

#### 3.1: Generate Certificate Authority (CA)

The CA is used to sign all device and gateway certificates.

```bash
# Generate CA private key (2048-bit RSA)
openssl genrsa -out ca.key 2048

# Generate CA certificate (valid for 10 years)
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=IoT-CA"
```

**What this creates:**
- `ca.key` - CA private key (keep secret!)
- `ca.crt` - CA certificate (shared with all devices)

#### 3.2: Generate Gateway Certificate

```bash
# Generate gateway private key
openssl genrsa -out gateway.key 2048

# Generate certificate signing request
openssl req -new -key gateway.key -out gateway.csr \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=gateway"

# Sign gateway certificate with CA
openssl x509 -req -in gateway.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out gateway.crt -days 3650

# Remove CSR (no longer needed)
rm gateway.csr
```

**What this creates:**
- `gateway.key` - Gateway private key
- `gateway.crt` - Gateway certificate (signed by CA)

#### 3.3: Generate Device Certificates

Create a certificate for each device. Example for `sensor_001`:

```bash
# Generate device private key
openssl genrsa -out sensor_001.key 2048

# Generate certificate signing request
openssl req -new -key sensor_001.key -out sensor_001.csr \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=sensor_001"

# Sign device certificate with CA
openssl x509 -req -in sensor_001.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out sensor_001.crt -days 3650

# Remove CSR
rm sensor_001.csr
```

**Repeat for additional devices:**
```bash
# sensor_002
openssl genrsa -out sensor_002.key 2048
openssl req -new -key sensor_002.key -out sensor_002.csr \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=sensor_002"
openssl x509 -req -in sensor_002.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out sensor_002.crt -days 3650
rm sensor_002.csr

# sensor_003
openssl genrsa -out sensor_003.key 2048
openssl req -new -key sensor_003.key -out sensor_003.csr \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=sensor_003"
openssl x509 -req -in sensor_003.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out sensor_003.crt -days 3650
rm sensor_003.csr
```

Return to project root:
```bash
cd ..
```

**Certificate directory structure:**
```
certs/
├── ca.crt              # CA certificate (public)
├── ca.key              # CA private key (secret!)
├── gateway.crt         # Gateway certificate
├── gateway.key         # Gateway private key
├── sensor_001.crt      # Device certificate
├── sensor_001.key      # Device private key
├── sensor_002.crt
├── sensor_002.key
├── sensor_003.crt
└── sensor_003.key
```

---

### Step 4: Configure Mosquitto MQTT Broker

Mosquitto needs to be configured for mutual TLS authentication.

```bash
# Create configuration file
sudo nano /etc/mosquitto/conf.d/iot-gateway.conf
```

**Add the following configuration:**
```conf
# SecureIoTGateway Mosquitto Configuration

# TLS/SSL Configuration
listener 8883
cafile /path/to/your/project/certs/ca.crt
certfile /path/to/your/project/certs/gateway.crt
keyfile /path/to/your/project/certs/gateway.key

# Require certificate from clients
require_certificate true
use_identity_as_username true

# Logging
log_dest stdout
log_type all
connection_messages true
log_timestamp true

# Security
allow_anonymous false

# Performance
max_connections 1000
max_queued_messages 1000
```

**Important:** Replace `/path/to/your/project` with the actual absolute path to your project directory.

**Save and exit** (Ctrl+X, Y, Enter in nano)

#### Restart Mosquitto

```bash
# Restart Mosquitto to apply configuration
sudo systemctl restart mosquitto

# Enable Mosquitto to start on boot
sudo systemctl enable mosquitto

# Check status
sudo systemctl status mosquitto
```

**Expected output:**
```
● mosquitto.service - Mosquitto MQTT Broker
     Loaded: loaded (/lib/systemd/system/mosquitto.service; enabled)
     Active: active (running) since ...
```

**If Mosquitto fails to start:**
```bash
# Check logs
sudo journalctl -u mosquitto -n 50
```

Common issues:
- Certificate file paths are incorrect
- Permissions on certificate files are wrong (`sudo chmod 644 certs/*.crt && sudo chmod 600 certs/*.key`)

---

### Step 5: Initialize Device Database

The gateway stores device credentials (device ID and shared secret) in an SQLite database.

```bash
# Create database
sqlite3 devices.db
```

**In the SQLite prompt, run:**
```sql
-- Create devices table
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    shared_secret TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- Add sample devices
INSERT INTO devices (device_id, shared_secret, created_at) VALUES
    ('sensor_001', 'supersecretkey123', 1704067200),
    ('sensor_002', 'anothersecretkey456', 1704067200),
    ('sensor_003', 'yetanothersecret789', 1704067200);

-- Verify
SELECT * FROM devices;

-- Exit
.quit
```

**Verify database creation:**
```bash
sqlite3 devices.db "SELECT device_id, shared_secret FROM devices;"
```

**Expected output:**
```
sensor_001|supersecretkey123
sensor_002|anothersecretkey456
sensor_003|yetanothersecret789
```

---

## 🎯 Running the System

The system consists of three components that run in separate terminals:

### Terminal 1: Gateway

```bash
# Activate virtual environment
source venv/bin/activate

# Run gateway
python3 gateway.py
```

**Expected output:**
```
════════════════════════════════════════════════════════════════════════════════
                        SECURE IOT GATEWAY STARTING                        
════════════════════════════════════════════════════════════════════════════════

[10:30:15.123] [DATABASE] Initializing database...
[10:30:15.125] [DATABASE] ✓ Database initialized
[10:30:15.126] [MQTT] Initializing MQTT client...
[10:30:15.127] [MQTT] Configuring TLS...
[10:30:15.128] [MQTT] ✓ TLS configured with mutual authentication
[10:30:15.129] [MQTT] Connecting to broker at localhost:8883...
[10:30:15.145] [MQTT] ✓ Connected to broker at localhost:8883
[10:30:15.146] [MQTT] Subscribed to topic: device/+/data

════════════════════════════════════════════════════════════════════════════════
                   GATEWAY READY - WAITING FOR MESSAGES                   
════════════════════════════════════════════════════════════════════════════════
```

### Terminal 2: Simulator (Device + Backend)

```bash
# Activate virtual environment
source venv/bin/activate

# Run simulator
python3 simulator.py
```

**Expected output:**
```
════════════════════════════════════════════════════════════════════════════════
                   BACKEND SERVER STARTING                   
════════════════════════════════════════════════════════════════════════════════

[10:30:20.001] [BACKEND] Listening on port 5000
[10:30:20.002] [BACKEND] Ready to receive data from gateway

════════════════════════════════════════════════════════════════════════════════
                   DEVICE sensor_001 CONNECTING                   
════════════════════════════════════════════════════════════════════════════════

[10:30:22.010] [DEVICE] Configuring TLS with device certificate...
[10:30:22.011] [DEVICE] ✓ TLS configured
[10:30:22.012] [DEVICE] Connecting to localhost:8883...
[10:30:22.050] [DEVICE] ✓ Connected to broker
```

### What Happens

1. **Backend** starts listening on port 5000
2. **Device** connects to Mosquitto broker with TLS certificate
3. **Device** sends sensor data every 3 seconds
4. **Gateway** validates each message (5 security checks)
5. **Gateway** forwards valid messages to backend
6. **Backend** processes data and responds
7. **Gateway** routes response back to device

---

## 📊 Understanding the Logs

### Device Sending Data

```
════════════════════════════════════════════════════════════════════════════════
                        DEVICE SENDING DATA #1                        
════════════════════════════════════════════════════════════════════════════════

[10:30:25.100] [DEVICE] Sensor reading: {"temperature": 22.5, "humidity": 65}
[10:30:25.101] [DEVICE] Creating signed message...
[10:30:25.102] [DEVICE] ✓ Message created
  Message ID: 550e8400-e29b-41d4...
  Timestamp: 1704067825 (10:30:25)
  Signature: a3f5b8c9d2e1f4a6b7c8d9e0f1a2b3c4...
[10:30:25.103] [DEVICE] Publishing to topic: device/sensor_001/data
[10:30:25.104] [DEVICE] ✓ Message published successfully
```

### Gateway Validation

```
════════════════════════════════════════════════════════════════════════════════
                        MESSAGE VALIDATION                        
════════════════════════════════════════════════════════════════════════════════

[10:30:25.105] [VALIDATION] TLS Identity: sensor_001
[10:30:25.106] [VALIDATION] ✓ Message parsed successfully

Starting validation checks...

  [1. Required Fields] ✓ All required fields present
  [2. Identity Check] ✓ device_id matches TLS identity
  [3. Timestamp Check] ✓ Time difference 0s within tolerance (300s)
  [4. Replay Detection] ✓ Message ID is unique: 550e8400...
  [5. Signature Check] ✓ HMAC signature verified

 ALL CHECKS PASSED 
[10:30:25.110] [VALIDATION] ✓ Message validated successfully for sensor_001
```

### Backend Receiving

```
════════════════════════════════════════════════════════════════════════════════
                   BACKEND RECEIVED DATA FROM sensor_001                   
════════════════════════════════════════════════════════════════════════════════

[10:30:25.115] [BACKEND] Device: sensor_001
[10:30:25.116] [BACKEND] Payload: {
  "temperature": 22.5,
  "humidity": 65
}
[10:30:25.117] [BACKEND] ✓ Temperature normal (22.5°C)
[10:30:25.118] [BACKEND] ✓ Sending response to gateway
```

---

## ➕ Adding New Devices

### Option 1: Using Helper Script (Automated Setup Only)

```bash
./add_device.sh sensor_004 mynewsecret123
```

This automatically:
- Adds device to database
- Generates certificate and private key

### Option 2: Manual Method

#### Step 1: Add to Database

```bash
sqlite3 devices.db
```

```sql
INSERT INTO devices (device_id, shared_secret, created_at) 
VALUES ('sensor_004', 'mynewsecret123', strftime('%s', 'now'));

-- Verify
SELECT * FROM devices WHERE device_id = 'sensor_004';

.quit
```

#### Step 2: Generate Certificate

```bash
cd certs

# Generate private key
openssl genrsa -out sensor_004.key 2048

# Generate CSR
openssl req -new -key sensor_004.key -out sensor_004.csr \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=sensor_004"

# Sign with CA
openssl x509 -req -in sensor_004.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out sensor_004.crt -days 3650

# Clean up
rm sensor_004.csr

cd ..
```

#### Step 3: Update Simulator

Edit `simulator.py` and change the device configuration:

```python
# Around line 20, change:
DEVICE_ID = "sensor_004"
SHARED_SECRET = "mynewsecret123"
```

Then restart the simulator.

---

## 🏗️ Architecture Overview

### Message Flow

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│             │  MQTT   │              │  HTTP   │             │
│  IoT Device │────────▶│   Gateway    │────────▶│   Backend   │
│             │  +TLS   │              │  +TLS   │   Server    │
│             │◀────────│              │◀────────│             │
└─────────────┘         └──────────────┘         └─────────────┘
```

### Security Layers

#### Layer 1: Transport Security (TLS)
- Mutual TLS authentication
- Device must present valid certificate signed by CA
- All traffic encrypted

#### Layer 2: Message Security (HMAC)
- Each message includes HMAC-SHA256 signature
- Signature proves message authenticity and integrity
- Prevents tampering and replay attacks

### Message Format

```json
{
  "device_id": "sensor_001",
  "timestamp": 1704067200,
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": {
    "temperature": 22.5,
    "humidity": 60
  },
  "signature": "a3f5b8c9d2e1f4a6b7c8d9e0f1a2b3c4..."
}
```

### Validation Steps

The gateway performs 5 security checks on every message:

1. **Required Fields** - All fields present
2. **Identity Consistency** - device_id matches TLS certificate
3. **Timestamp Freshness** - Message within 5 minutes
4. **Replay Detection** - Message ID not seen before
5. **Signature Verification** - HMAC signature valid

---

## 🔍 Troubleshooting

### Mosquitto Won't Start

```bash
# Check logs
sudo journalctl -u mosquitto -n 50 --no-pager

# Common issues:
# 1. Certificate paths wrong in config
# 2. Permission issues on certificate files
sudo chmod 644 certs/*.crt
sudo chmod 600 certs/*.key

# 3. Port 8883 already in use
sudo netstat -tlnp | grep 8883
```

### Gateway Can't Connect to Mosquitto

**Symptom:** `Connection failed: Connection refused`

```bash
# Check if Mosquitto is running
sudo systemctl status mosquitto

# Check if listening on 8883
sudo netstat -tlnp | grep 8883

# Test with mosquitto_sub
mosquitto_sub -h localhost -p 8883 \
    --cafile certs/ca.crt \
    --cert certs/sensor_001.crt \
    --key certs/sensor_001.key \
    -t 'device/#' -v
```

### Device Can't Connect

**Symptom:** TLS handshake failure

```bash
# Check certificate validity
openssl x509 -in certs/sensor_001.crt -noout -dates

# Verify certificate chain
openssl verify -CAfile certs/ca.crt certs/sensor_001.crt

# Check Mosquitto logs for TLS errors
sudo journalctl -u mosquitto -f
```

### Message Validation Fails

#### Timestamp Check Fails

**Symptom:** `Time difference 350s exceeds tolerance 300s`

**Solution:** System clocks out of sync

```bash
# Check system time
date

# Sync time (if needed)
sudo ntpdate pool.ntp.org
# OR
sudo timedatectl set-ntp true
```

#### Signature Check Fails

**Symptom:** `Signature mismatch`

**Possible causes:**
1. Wrong shared secret in database
2. Device using wrong secret
3. Message modified in transit (shouldn't happen with TLS)

```bash
# Verify database secret
sqlite3 devices.db "SELECT * FROM devices WHERE device_id='sensor_001';"

# Make sure simulator uses same secret
grep "SHARED_SECRET" simulator.py
```

#### Replay Detection Fails

**Symptom:** `Message ID already seen`

**Solution:** This is expected if you restart the device without restarting the gateway. The gateway keeps message IDs in memory. Either:
- Restart the gateway to clear cache
- Wait for the device to generate a new message ID

### Backend Not Receiving Messages

```bash
# Check if backend is running
curl http://localhost:5000/

# Check gateway logs for forwarding errors

# Test backend directly
curl -X POST http://localhost:5000/device/sensor_001/data \
    -H "Content-Type: application/json" \
    -d '{"temperature": 25.0}'
```

### Permission Denied Errors

```bash
# Fix certificate permissions
chmod 644 certs/*.crt
chmod 600 certs/*.key
chmod 644 devices.db

# If running as different user
sudo chown $USER:$USER certs/* devices.db
```

---

## 🛡️ Security Features

### What This System Protects Against

✅ **Eavesdropping** - TLS encryption prevents reading messages in transit

✅ **Unauthorized Devices** - Only devices with valid certificates can connect

✅ **Message Tampering** - HMAC signatures detect any modifications

✅ **Replay Attacks** - Message IDs and timestamps prevent reuse of old messages

✅ **Impersonation** - TLS + HMAC combination prevents spoofing

✅ **Man-in-the-Middle** - Mutual TLS verifies both parties

### What This System Does NOT Protect Against

❌ **Compromised Device** - If a device is hacked, it can send valid malicious messages

❌ **Physical Attacks** - If someone steals a device, they have its certificate and key

❌ **Backend Vulnerabilities** - Gateway doesn't protect backend from SQL injection, etc.

❌ **Denial of Service** - No rate limiting implemented

❌ **Certificate Theft** - If private keys are extracted, attacker can impersonate device

### Security Best Practices

1. **Keep CA Private Key Secure** - `ca.key` should be stored offline after generating certificates
2. **Rotate Secrets Regularly** - Change shared secrets periodically
3. **Monitor Failed Attempts** - Watch gateway logs for validation failures
4. **Use Strong Secrets** - Minimum 16 characters, random
5. **Separate Networks** - IoT devices on isolated network
6. **Regular Updates** - Keep Mosquitto and Python packages updated

---

## 📝 Configuration Reference

### Gateway Configuration

Edit `gateway.py` to change:

```python
MQTT_BROKER = "localhost"          # Mosquitto broker address
MQTT_PORT = 8883                   # Mosquitto TLS port
BACKEND_URL = "http://localhost:5000/device/{}/data"  # Backend endpoint
TIMESTAMP_TOLERANCE = 300          # 5 minutes in seconds
REPLAY_CACHE_SIZE = 1000          # Messages to remember per device
```

### Mosquitto Configuration

`/etc/mosquitto/conf.d/iot-gateway.conf`:

```conf
listener 8883                      # Port to listen on
cafile /path/to/ca.crt            # CA certificate
certfile /path/to/gateway.crt     # Gateway certificate
keyfile /path/to/gateway.key      # Gateway private key
require_certificate true           # Force client certificates
use_identity_as_username true     # Use CN as username
allow_anonymous false             # No anonymous connections
max_connections 1000              # Connection limit
```

### Database Schema

```sql
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,      -- Unique device identifier
    shared_secret TEXT NOT NULL,     -- HMAC secret key
    created_at INTEGER NOT NULL      -- Unix timestamp
);
```

---

## 🧪 Testing & Validation

### Test Valid Message Flow

1. Start gateway
2. Start simulator
3. Watch for successful validation in gateway logs
4. Verify backend receives data

### Test Invalid Messages

#### Test 1: Tampered Message

Modify `simulator.py` to change payload after signing:

```python
# After creating message
message["payload"]["temperature"] = 99.9  # Tamper with data
```

Expected: Gateway rejects with "Invalid signature"

#### Test 2: Replay Attack

Send same message twice:

```python
# In simulator.py, comment out UUID generation
# message_id = str(uuid.uuid4())
message_id = "fixed-id-12345"  # Use fixed ID
```

Expected: Second message rejected with "Message ID already seen"

#### Test 3: Old Message

Set timestamp to 10 minutes ago:

```python
timestamp = int(time.time()) - 600  # 10 minutes old
```

Expected: Gateway rejects with "Timestamp out of range"

#### Test 4: Wrong Device Identity

In simulator.py, change:

```python
message["device_id"] = "sensor_999"  # Different from certificate
```

Expected: Gateway rejects with "device_id mismatch with TLS identity"

### Manual MQTT Testing

Subscribe to all device topics:

```bash
mosquitto_sub -h localhost -p 8883 \
    --cafile certs/ca.crt \
    --cert certs/gateway.crt \
    --key certs/gateway.key \
    -t 'device/#' -v
```

Publish test message:

```bash
# Create a test message (you'll need to calculate signature manually)
mosquitto_pub -h localhost -p 8883 \
    --cafile certs/ca.crt \
    --cert certs/sensor_001.crt \
    --key certs/sensor_001.key \
    -t 'device/sensor_001/data' \
    -m '{"device_id":"sensor_001",...}'
```

---

## 🎓 Educational Use

This project is designed for learning IoT security concepts:

- **Transport Layer Security (TLS)** with mutual authentication
- **Message authentication** with HMAC signatures
- **Replay attack prevention** with message IDs and timestamps
- **MQTT protocol** for IoT communication
- **Security validation** patterns

### Extending the Project

Ideas for enhancements:

1. **Rate Limiting** - Limit messages per device per minute
2. **Certificate Revocation** - Block compromised devices
3. **Command & Control** - Send commands from backend to devices
4. **Device Groups** - Apply policies to device groups
5. **Logging Database** - Store all messages for audit
6. **Web Dashboard** - Visualize device status and messages
7. **Alert System** - Email/SMS on security violations
8. **Load Balancing** - Multiple gateway instances
9. **Device Provisioning** - Automated device registration
10. **Metrics & Monitoring** - Prometheus/Grafana integration


---

## 🐛 Found a Bug?

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs: `sudo journalctl -u mosquitto -n 100`
3. Verify all steps were followed correctly
4. Check file permissions on certificates

---

## ✨ Success Indicators

You know everything is working when you see:

1. ✅ Gateway shows "GATEWAY READY - WAITING FOR MESSAGES"
2. ✅ Device shows "✓ Connected to broker"
3. ✅ Gateway validation logs show "ALL CHECKS PASSED"
4. ✅ Backend receives data and shows temperature alerts
5. ✅ Device receives responses from backend
6. ✅ Statistics counters increment correctly
