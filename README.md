# SecureIoTGateway - Complete Setup & Usage Guide

A security gateway that sits between IoT devices and a backend server, validating all messages with TLS and HMAC signatures before forwarding them.

---

## Check out my Blog post for more easy to understand explanation of all the concepts and protocols used in this project

[https://jouini.dev/posts/secure-iot-gateway/](https://jouini.dev/posts/secure-iot-gateway/)

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

* Ubuntu/Debian Linux (20.04 or later)
* **sudo access** (Important: do **not** run the installer as root — the setup script will request `sudo` when needed)
* Internet connection

### Installation (One Command)

```bash
chmod +x setup.sh
./setup.sh
```

This will automatically:

* ✅ Install Mosquitto MQTT broker and clients
* ✅ Install OpenSSL, Python3 and SQLite
* ✅ Create a Python virtual environment and install Python packages
* ✅ Generate SSL/TLS certificates (keeps `ca.key` in project `certs/`)
* ✅ Install broker certs into `/etc/mosquitto/certs`
* ✅ Configure Mosquitto for mutual TLS on port **8883**
* ✅ Create device database with 3 sample devices
* ✅ Create helper scripts (`start_gateway.sh`, `start_simulator.sh`, `add_device.sh`)

After setup completes, follow the [Running the System](#running-the-system) section.

---

## 🔧 Manual Setup (Detailed)

The automated script performs the steps below. If you need to do any step manually, follow these instructions.

### Step 1: Install System Packages

```bash
# Update package list
sudo apt-get update

# Install Mosquitto MQTT broker and clients
sudo apt-get install -y mosquitto mosquitto-clients

# Install OpenSSL
sudo apt-get install -y openssl

# Install Python3, pip and venv
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
# Create virtual environment (project root)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies (script uses these)
pip install paho-mqtt requests colorama flask

# Deactivate when done
deactivate
```

**Required Python packages (installed by the script):**

* `paho-mqtt` - MQTT client library
* `requests` - HTTP client for backend forwarding
* `colorama` - Colored terminal output
* `flask` - Backend server for simulation

---

### Step 3: Generate SSL/TLS Certificates (script behavior)

The script generates certificates inside the project `certs/` folder and **keeps the CA private key (`ca.key`) locally** with permissions `600`.

Important details matching the script:

* The gateway certificate is created with SANs for `localhost`, `gateway` and `127.0.0.1` so TLS will be valid for those names.
* The script copies only the files required by Mosquitto into `/etc/mosquitto/certs`:

  * `ca.crt`, `gateway.crt`, `gateway.key` are copied to `/etc/mosquitto/certs`
  * **`ca.key` remains in the project `certs/` directory** (do not move it to the broker folder)
* File permissions set by the script:

  * `ca.key` in project: `chmod 600`
  * `/etc/mosquitto/certs` directory: owned by `mosquitto:mosquitto`, `chmod 755`
  * Certificates (`*.crt`) in `/etc/mosquitto/certs`: `chmod 644`
  * Gateway key in `/etc/mosquitto/certs/gateway.key`: `chmod 640`

If you need to reproduce the steps manually, see the script for exact `openssl` commands — the gateway certificate is signed with an `-extfile` containing the SANs.

**Certificate files location (created by script):**

```
certs/
├── ca.crt
├── ca.key        # keep secret; the script leaves this in certs/ (mode 600)
├── gateway.crt
├── gateway.key
├── sensor_001.crt
├── sensor_001.key
├── sensor_002.crt
├── sensor_002.key
├── sensor_003.crt
└── sensor_003.key
```

---

### Step 4: Configure Mosquitto MQTT Broker (script behavior)

The script writes the Mosquitto configuration to `/etc/mosquitto/conf.d/iot-gateway.conf` and reloads/restarts the service. The script uses the installed certs path:

```conf
listener 8883
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/gateway.crt
keyfile /etc/mosquitto/certs/gateway.key

require_certificate true
use_identity_as_username true

log_dest stdout
log_type all
connection_messages true
log_timestamp true

allow_anonymous false

max_connections 1000
max_queued_messages 1000
```

**Note:** Because the script copies broker certs to `/etc/mosquitto/certs` and writes this conf, you don't need to edit paths manually after running the installer. If doing a manual install, use the above absolute paths.

Restart Mosquitto (script does this automatically):

```bash
sudo systemctl daemon-reload
sudo systemctl restart mosquitto
sudo systemctl enable mosquitto
sudo systemctl status mosquitto
```

If Mosquitto fails to start, check logs: `sudo journalctl -u mosquitto -n 200 --no-pager`

---

### Step 5: Initialize Device Database (script behavior)

The installer creates `devices.db` (SQLite) and inserts three sample devices with the current timestamp (the script uses `$(date +%s)` for `created_at`).

To inspect the database:

```bash
sqlite3 devices.db "SELECT device_id, shared_secret FROM devices;"
```

Expected output (example):

```
sensor_001|supersecretkey123
sensor_002|anothersecretkey456
sensor_003|yetanothersecret789
```

---

## 🎯 Running the System

Run components in separate terminals.

### Terminal 1: Gateway

```bash
# Activate virtual environment
source venv/bin/activate

# Run gateway (script uses `gateway.py`)
./start_gateway.sh
```

### Terminal 2: Simulator (Device + Backend)

```bash
# Activate virtual environment
source venv/bin/activate

# Run simulator
./start_simulator.sh
```

The helper scripts are created by the installer and call `python3 gateway.py` and `python3 simulator.py` inside the virtualenv.

---

## ➕ Adding New Devices

Use the helper script created by the installer:

```bash
./add_device.sh sensor_004 mynewsecret123
```

This will:

* Insert the new device into `devices.db` using the current timestamp
* Generate a private key and certificate for the device inside `certs/` (signed by the local CA)

Manual steps are also possible; the `add_device.sh` in the project shows the exact `openssl` and `sqlite3` commands used.

---

## 🔍 Troubleshooting (aligns with script actions)

### Mosquitto Won't Start

```bash
sudo journalctl -u mosquitto -n 50 --no-pager
```

Common issues:

* Certificate file paths wrong in config (script uses `/etc/mosquitto/certs`)
* Permissions on certificate files are wrong

Fix permissions (script already sets these, but if you changed things manually):

```bash
sudo chmod 644 /etc/mosquitto/certs/*.crt
sudo chmod 640 /etc/mosquitto/certs/gateway.key
sudo chown -R mosquitto:mosquitto /etc/mosquitto/certs
```

### Gateway Can't Connect to Mosquitto

```bash
# Check Mosquitto status
sudo systemctl status mosquitto

# Test with mosquitto_sub using one of the device certs
mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/certs/ca.crt \
    --cert certs/sensor_001.crt --key certs/sensor_001.key -t 'device/#' -v
```

### Device Can't Connect

TLS handshake issues:

```bash
# Check certificate validity
openssl x509 -in certs/sensor_001.crt -noout -dates

# Verify chain
openssl verify -CAfile certs/ca.crt certs/sensor_001.crt
```

### Message Validation Fails

Common causes: clock skew, wrong shared secret, replayed message id. See the `Troubleshooting` section in the project for commands to sync time and check DB.

---

## 🛡️ Security Notes (script decisions)

* The script **keeps `ca.key` inside the project `certs/`** with mode `600` so you can add devices locally — **but you should move `ca.key` offline after provisioning production devices**.
* The script only installs the files Mosquitto needs into `/etc/mosquitto/certs` and sets ownership to `mosquitto:mosquitto`.

