# SecureIoTGateway Architecture

## What's this project

A security gateway that sits between IoT devices and a backend server. Devices send data through the gateway, which checks that messages are legitimate before forwarding them to the backend.

---

## Background: What is MQTT?

**MQTT** (Message Queuing Telemetry Transport) is a lightweight messaging protocol designed for IoT devices. Think of it like a post office system:

- **Publisher**: Sends messages (like mailing a letter)
- **Subscriber**: Receives messages (like having a mailbox)
- **Broker**: The middleman that receives and delivers messages (like the post office)
- **Topic**: The "address" for messages (e.g., `device/sensor1/temperature`)

**Why MQTT for IoT?**
- Very lightweight (works on tiny devices)
- Maintains persistent connections (devices don't reconnect constantly)
- Devices can sleep and wake up to send data efficiently

**In our system:**
- Devices are publishers (sending sensor data)
- The gateway runs an MQTT broker (receives messages from devices)
- The gateway is also a subscriber (listens to device messages)

---

## System Architecture Overview

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│             │  MQTT   │              │  HTTP   │             │
│  IoT Device │────────▶│   Gateway    │────────▶│   Backend   │
│             │  +TLS   │              │  +TLS   │   Server    │
│             │◀────────│              │◀────────│             │
└─────────────┘         └──────────────┘         └─────────────┘
   (sensor)              (security proxy)          (your app)
```

**Three components total:**
1. **IoT Device**: Temperature sensor, camera, smart lock, etc.
2. **Gateway**: The security checkpoint (what we're building)
3. **Backend**: Your application server (already exists)

---

## Component Details

### 1. IoT Device (Client)

**What it has:**
- MQTT client library
- Unique certificate (proves identity)
- Shared secret key (for signing messages)
- Sensor hardware

**What it does:**
- Collects sensor data (temperature, motion, etc.)
- Creates signed messages
- Sends messages via MQTT to gateway
- Receives commands from gateway

### 2. Gateway (Security Proxy)

**What it has:**
- **Mosquitto MQTT Broker**: Handles MQTT connections from devices
- **Python Security Script**: Does all security checks
- **SQLite Database**: Stores device credentials
- **Certificate Authority (CA) Certificate**: Verifies device certificates

**What it does:**
- Accepts MQTT connections from devices (with TLS)
- Validates every message for security
- Converts MQTT messages to HTTP requests
- Forwards valid messages to backend
- Routes backend responses back to devices

**Internal parts:**
- **Mosquitto** (existing software): Handles TLS handshake and MQTT protocol
- **Python script** : 
  - Security validation
  - Message forwarding
  - Protocol conversion (MQTT ↔ HTTP)

### 3. Backend Server

**What it has:**
- HTTP API endpoint
- Your business logic

**What it does:**
- Receives clean, validated data from gateway
- Processes data (stores in database, triggers alerts, etc.)
- Sends commands back to gateway (which routes to devices)

**Important:** Backend has ZERO security code. It trusts the gateway completely.

---

## Security Layers

### Layer 1: Transport Security (TLS)

**What happens:**
When a device connects, there's a TLS handshake:

1. Device: "I want to connect" (sends its certificate)
2. Mosquitto: "Prove you own that certificate" (cryptographic challenge)
3. Device: "Here's proof" (signs challenge with private key)
4. Mosquitto: "Certificate is valid, connection accepted"

**What this protects against:**
- ✅ Eavesdropping (all traffic encrypted)
- ✅ Man-in-the-middle attacks (certificates verified)
- ✅ Unauthorized devices (only devices with valid certificates can connect)

**What this does NOT protect against:**
- ❌ A compromised device with valid certificate sending fake data
- ❌ Replay attacks (someone re-sending old valid messages)
- ❌ Message tampering after TLS decryption inside gateway

### Layer 2: Message-Level Security (HMAC Signatures)

**What happens:**
Each message has a signature that proves:
- The message came from the device it claims to be from
- The message hasn't been modified
- The message is fresh (timestamp)
- The message hasn't been seen before (unique ID)

**What this protects against:**
- ✅ Message tampering (signature becomes invalid if modified)
- ✅ Replay attacks (message IDs tracked)
- ✅ Spoofing (only device with secret key can create valid signature)
- ✅ Old messages (timestamp validation)

**What this does NOT protect against:**
- ❌ Compromised device sending malicious but properly signed messages
- ❌ Backend being hacked (gateway only protects device→backend direction)

---

## Message Format

Every message from device to gateway looks like this:

```json
{
  "device_id": "sensor_001",
  "timestamp": 1727712000,
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": {
    "temperature": 22.5,
    "humidity": 60
  },
  "signature": "a3f5b8c9d2e1f4a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
}
```

**Field explanations:**
- `device_id`: Who is sending this? (e.g., "sensor_001")
- `timestamp`: When was this created? (Unix timestamp, seconds since 1970)
- `message_id`: Unique identifier (UUID v4) to prevent replay attacks
- `payload`: The actual sensor data (any JSON structure)
- `signature`: HMAC-SHA256 hash proving authenticity

**How signature is calculated:**
```
signature = HMAC-SHA256(
    key: device's_shared_secret,
    message: "sensor_001" + "1727712000" + "550e8400..." + '{"temperature":22.5,"humidity":60}'
)
```

The signature is a one-way hash. Even if someone intercepts the message, they can't create a new valid signature without knowing the shared secret.

---

## Detailed Message Flow: Device → Backend

Let's trace a temperature reading from a sensor to your backend.

### Step 1: Device Preparation
```
Sensor reads: 22.5°C
Device creates message:
  - device_id = "sensor_001"
  - timestamp = 1727712000 (current time)
  - message_id = "550e8400-e29b-41d4-a716-446655440000" (random UUID)
  - payload = {"temperature": 22.5}
  
Device calculates signature:
  - Concatenates: "sensor_0011727712000550e8400-e29b-41d4-a716-446655440000{"temperature":22.5}"
  - Applies HMAC-SHA256 with shared secret "supersecretkey123"
  - Gets: "a3f5b8c9d2e1f4a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
```

### Step 2: Device Sends Message
```
Device publishes to MQTT topic: "device/sensor_001/data"
Message body: {entire JSON above}

MQTT connection already established (persistent connection with TLS)
Message encrypted by TLS before transmission
```

### Step 3: Gateway (Mosquitto) Receives
```
Mosquitto broker receives encrypted MQTT message
Decrypts using TLS
Delivers to Python script (subscribed to "device/+/data")
```

### Step 4: Python Script - Security Validation

**Check 1: TLS Identity**
```
Mosquitto already verified device certificate during connection
Device authenticated as "sensor_001"
Python script knows message came over authenticated connection
```

**Check 2: Timestamp Validation**
```
Current gateway time: 1727712050 (50 seconds after message created)
Message timestamp: 1727712000
Difference: 50 seconds
Tolerance: ±300 seconds (5 minutes)
✓ PASS - timestamp is fresh
```

**Check 3: Replay Detection**
```
Python checks in-memory cache for message_id "550e8400-e29b-41d4-a716-446655440000"
Cache is a list of last 1000 message IDs per device
Message ID not found in cache
✓ PASS - not a replay
Add message_id to cache
```

**Check 4: Identity Consistency**
```
device_id in message: "sensor_001"
TLS certificate identity: "sensor_001"
✓ PASS - matches
```

**Check 5: Signature Verification**
```
Python looks up shared secret for "sensor_001" in database
Finds: "supersecretkey123"

Recalculates signature:
  - Concatenates: "sensor_0011727712000550e8400-e29b-41d4-a716-446655440000{"temperature":22.5}"
  - HMAC-SHA256 with "supersecretkey123"
  - Gets: "a3f5b8c9d2e1f4a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
  
Compares with signature in message:
Message signature: "a3f5b8c9d2e1f4a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
✓ PASS - signatures match
```

### Step 5: Forward to Backend
```
All checks passed!

Python script extracts payload: {"temperature": 22.5}
Makes HTTP POST request:
  URL: http://backend.local:5000/device/sensor_001/data
  Body: {"temperature": 22.5}
  Headers: Content-Type: application/json
  
(Using TLS if backend URL is https://)
```

### Step 6: Backend Response
```
Backend receives: {"temperature": 22.5}
Backend processes (stores in database, etc.)
Backend responds: HTTP 200 OK
Body: {"status": "received", "alert": "temperature normal"}
```

### Step 7: Gateway Routes Response Back
```
Python script receives backend response
Publishes to MQTT topic: "device/sensor_001/response"
Message: {"status": "received", "alert": "temperature normal"}

Mosquitto delivers to device over existing TLS connection
Device receives response
```

---

## Message Flow: Backend → Device (Command)

Let's say the backend wants to tell the device to reboot.

### Step 1: Backend Sends Command
```
Backend makes HTTP POST:
  URL: https://gateway:8443/command/sensor_001
  Headers: 
    Authorization: Bearer your-backend-api-key
  Body: {"action": "reboot"}
```

### Step 2: Gateway API Receives
```
Python script runs a small HTTP server on port 8443
Receives POST request
Validates API key in Authorization header
✓ API key matches configured value
```

### Step 3: Gateway Creates Signed Message
```
Gateway creates message for device:
  - timestamp = current time
  - message_id = new UUID
  - payload = {"action": "reboot"}
  - signature = HMAC with device's shared secret

Full message:
{
  "timestamp": 1727712100,
  "message_id": "660f9500-f39c-42e5-b827-557766551111",
  "payload": {"action": "reboot"},
  "signature": "b4g6c9e3f2g5h7j8k9l0m1n2o3p4q5r6s7t8u9v0w1x2y3z4a5b6c7d8e9f0g1"
}
```

### Step 4: Gateway Publishes to Device
```
Publishes to MQTT topic: "device/sensor_001/command"
Mosquitto delivers over TLS to device
```

### Step 5: Device Receives and Validates
```
Device receives message
Device verifies signature using its shared secret
✓ Signature valid
Device checks timestamp (within 5 minutes)
✓ Fresh message
Device processes command: initiates reboot
```

---

## What If Something Goes Wrong?

### Scenario 1: Attacker Replays Old Message
```
Attacker captured message from 10 minutes ago
Attacker resends exact same message

Gateway receives message
Check 2 (Timestamp): 
  Current time: 1727712600
  Message time: 1727712000
  Difference: 600 seconds (10 minutes)
  Tolerance: 300 seconds (5 minutes)
  ✗ FAIL - timestamp too old

Gateway logs: "Rejected message from sensor_001: Timestamp out of range"
Gateway does NOT forward to backend
Attacker blocked ✓
```

### Scenario 2: Attacker Modifies Message
```
Attacker intercepts message (despite TLS... maybe compromised gateway?)
Original payload: {"temperature": 22.5}
Attacker changes to: {"temperature": 99.9}

Gateway receives modified message
Check 5 (Signature):
  Recalculates signature with original concatenation
  Original: "sensor_001" + timestamp + message_id + '{"temperature":22.5}'
  But payload now says: {"temperature": 99.9}
  Signatures don't match
  ✗ FAIL - invalid signature

Gateway logs: "Rejected message from sensor_001: Invalid signature"
Gateway does NOT forward to backend
Attacker blocked ✓
```

### Scenario 3: Attacker Tries to Impersonate Device
```
Attacker creates fake message:
{
  "device_id": "sensor_001",
  "timestamp": 1727712700,
  "message_id": "770g0611-g40d-43f6-c938-668877662222",
  "payload": {"temperature": 50.0},
  "signature": "random_garbage_signature"
}

Attacker tries to send via MQTT

Check 1 (TLS Connection):
  Attacker doesn't have sensor_001's certificate and private key
  TLS handshake fails
  Mosquitto rejects connection
  
Attacker can't even connect ✓

Alternative: Attacker has compromised another device (sensor_002)
Attacker connects as sensor_002 (has valid cert)
Sends message claiming to be sensor_001

Check 4 (Identity):
  TLS identity: sensor_002
  Message device_id: sensor_001
  ✗ FAIL - mismatch

Gateway logs: "Rejected message: device_id mismatch with TLS identity"
Gateway does NOT forward to backend
Attacker blocked ✓
```

---

## Security Summary

### ✅ What This Protects Against:

1. **Eavesdropping**: TLS encryption prevents reading messages in transit
2. **Unauthorized devices**: Mutual TLS blocks devices without valid certificates
3. **Message tampering**: HMAC signatures detect any modifications
4. **Replay attacks**: Message ID cache and timestamp prevent reusing old messages
5. **Impersonation**: Combination of TLS identity + HMAC signature prevents spoofing
6. **Man-in-the-middle**: Mutual TLS verifies both device and gateway identities

### ❌ What This Does NOT Protect Against:

1. **Compromised device sending malicious data**: If a device is hacked, it can create valid signed messages with false data (e.g., fake temperature readings)
2. **Backend vulnerabilities**: Gateway doesn't protect the backend from SQL injection, XSS, etc.
3. **Physical attacks on devices**: If someone steals a device, they have its certificate and secret
4. **Certificate theft**: If device's private key is extracted, attacker can impersonate device
5. **Denial of Service**: Attacker could flood gateway with connection attempts (rate limiting would help but not implemented here)
6. **Side-channel attacks**: Timing attacks, power analysis on devices (out of scope for this project)
7. **Backend → Device message tampering**: Backend commands are signed by gateway, but if gateway is compromised, fake commands could be sent

---

## Database Schema

The gateway needs to store device credentials:

```sql
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,           -- "sensor_001"
    shared_secret TEXT NOT NULL,          -- "supersecretkey123"
    created_at INTEGER                    -- Unix timestamp when device was registered
);
```

That's it. Simple table with device IDs and their secrets.

---

## Configuration

### Gateway needs:
- Mosquitto config file (enables TLS, points to certificates)
- Python script config (backend URL, database path, tolerance values)
- Device database (SQLite file)
- Certificates (CA cert, gateway cert, gateway private key)

### Each device needs:
- Device certificate file
- Device private key file
- CA certificate file (to verify gateway)
- Shared secret (hardcoded in device firmware or config)
- Device ID (hardcoded or in config)

### Backend needs:
- HTTP endpoint: `/device/{device_id}/data`
- Nothing else! Gateway handles all security.

---

## Why This Architecture is Simple

1. **Mosquitto does the heavy lifting**: You don't write TLS code, MQTT code, or certificate validation
2. **Python is glue code**: Just validates messages and forwards HTTP requests
3. **Single backend URL**: All devices forward to same server (no routing logic)
4. **In-memory cache**: No need for Redis or complex replay protection database
5. **Standard protocols**: MQTT and HTTP are well-understood, plenty of libraries available

---

## Performance Characteristics

- **Latency**: ~10-50ms added by gateway (security checks + HTTP forward)
- **Throughput**: Can handle ~1000 messages/second on modest hardware (depends on Python performance)
- **Scalability**: Bottleneck is Python script (single-threaded), but fine for regular use
- **Memory**: ~1MB per 1000 devices (replay cache dominates memory usage)