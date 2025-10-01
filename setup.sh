#!/bin/bash

# SecureIoTGateway Setup Script (updated)
# Generates certificates locally, then installs broker files into /etc/mosquitto/certs
# and gives ownership to the mosquitto user. Keeps CA private key in project folder.

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored messages
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}→ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if running as root for apt operations
check_sudo() {
    if [ "$EUID" -eq 0 ]; then 
        print_warning "Please don't run this script as root. We'll ask for sudo when needed."
        exit 1
    fi
}

# Install required packages
install_packages() {
    print_header "Installing Required Packages"
    
    print_info "Updating package list..."
    sudo apt-get update -qq
    
    print_info "Installing Mosquitto MQTT Broker..."
    sudo apt-get install -y mosquitto mosquitto-clients
    print_success "Mosquitto installed"
    
    print_info "Installing OpenSSL for certificate generation..."
    sudo apt-get install -y openssl
    print_success "OpenSSL installed"
    
    print_info "Installing Python3 and pip..."
    sudo apt-get install -y python3 python3-pip python3-venv
    print_success "Python3 installed"
    
    print_info "Installing SQLite..."
    sudo apt-get install -y sqlite3
    print_success "SQLite installed"
}

# Create Python virtual environment and install dependencies
setup_python_env() {
    print_header "Setting Up Python Environment"
    
    if [ -d "venv" ]; then
        print_warning "Virtual environment already exists, skipping creation"
    else
        print_info "Creating virtual environment..."
        python3 -m venv venv
        print_success "Virtual environment created"
    fi
    
    print_info "Activating virtual environment..."
    source venv/bin/activate
    
    print_info "Installing Python dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet paho-mqtt requests colorama flask
    print_success "Python dependencies installed"
    
    deactivate
}

# Generate certificates (locally inside project certs/) then install broker files into /etc/mosquitto/certs
generate_certificates() {
    print_header "Generating SSL/TLS Certificates"
    
    if [ -d "certs" ]; then
        print_warning "Certificates directory exists. Delete it to regenerate certificates."
        read -p "Delete and regenerate? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf certs
        else
            print_info "Skipping certificate generation"
            return
        fi
    fi
    
    mkdir -p certs
    cd certs
    
    # Generate CA (Certificate Authority)
    print_info "Generating CA private key..."
    openssl genrsa -out ca.key 2048 2>/dev/null
    chmod 600 ca.key
    
    print_info "Generating CA certificate..."
    openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
        -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=IoT-CA" 2>/dev/null
    print_success "CA certificate created (valid for 10 years)"
    
    # Generate Gateway certificate (with SANs for localhost and 127.0.0.1)
    print_info "Generating Gateway private key..."
    openssl genrsa -out gateway.key 2048 2>/dev/null
    chmod 600 gateway.key

    print_info "Generating Gateway certificate signing request..."
    openssl req -new -key gateway.key -out gateway.csr \
        -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=gateway" 2>/dev/null

    # Create a SAN file so certificate is valid for localhost, gateway and 127.0.0.1
    cat > san.cnf <<EOF
subjectAltName = DNS:localhost, DNS:gateway, IP:127.0.0.1
EOF

    print_info "Signing Gateway certificate with CA (including SANs)..."
    openssl x509 -req -in gateway.csr -CA ca.crt -CAkey ca.key \
        -CAcreateserial -out gateway.crt -days 3650 -sha256 -extfile san.cnf 2>/dev/null

    # cleanup
    rm -f gateway.csr san.cnf
    print_success "Gateway certificate created (with SANs for localhost and 127.0.0.1)"

    
    # Generate Device certificates
    for device_id in sensor_001 sensor_002 sensor_003; do
        print_info "Generating certificate for device: $device_id..."
        
        openssl genrsa -out ${device_id}.key 2048 2>/dev/null
        chmod 600 ${device_id}.key
        openssl req -new -key ${device_id}.key -out ${device_id}.csr \
            -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=${device_id}" 2>/dev/null
        openssl x509 -req -in ${device_id}.csr -CA ca.crt -CAkey ca.key \
            -CAcreateserial -out ${device_id}.crt -days 3650 2>/dev/null
        
        print_success "Certificate created for $device_id"
    done
    
    # Clean up CSR files
    rm -f *.csr
    
    cd ..

    print_success "All certificates generated successfully (local certs/)"
    echo -e "\n${CYAN}Certificate files location:${NC} $(pwd)/certs/"

    # Install broker-needed certs into /etc/mosquitto/certs with proper ownership
    print_header "Installing broker certs into /etc/mosquitto/certs"
    sudo mkdir -p /etc/mosquitto/certs

    # Copy only the files mosquitto needs (keep CA private key in project folder)
    print_info "Copying ca.crt, gateway.crt and gateway.key to /etc/mosquitto/certs"
    sudo cp certs/ca.crt /etc/mosquitto/certs/
    sudo cp certs/gateway.crt /etc/mosquitto/certs/
    sudo cp certs/gateway.key /etc/mosquitto/certs/

    # Set ownership and permissions for the broker files
    sudo chown -R mosquitto:mosquitto /etc/mosquitto/certs
    sudo chmod 755 /etc/mosquitto/certs
    sudo chmod 644 /etc/mosquitto/certs/*.crt
    sudo chmod 640 /etc/mosquitto/certs/gateway.key

    print_success "Broker certs installed to /etc/mosquitto/certs and ownership set to mosquitto:mosquitto"
    print_info "Note: ca.key (the CA private key) remains in the project at certs/ca.key with mode 600"
}

# Configure Mosquitto
configure_mosquitto() {
    print_header "Configuring Mosquitto MQTT Broker"
    
    MOSQUITTO_CONF="/etc/mosquitto/conf.d/iot-gateway.conf"
    
    print_info "Creating Mosquitto configuration..."
    
    sudo tee "$MOSQUITTO_CONF" > /dev/null <<EOF
# SecureIoTGateway Mosquitto Configuration

# TLS/SSL Configuration
listener 8883
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/gateway.crt
keyfile /etc/mosquitto/certs/gateway.key

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
EOF
    
    print_success "Mosquitto configuration created at $MOSQUITTO_CONF"
    
    # Restart mosquitto service
    print_info "Restarting Mosquitto service..."
    sudo systemctl daemon-reload
    sudo systemctl restart mosquitto
    sudo systemctl enable mosquitto

    print_info "Checking Mosquitto status..."
    if sudo systemctl is-active --quiet mosquitto; then
        print_success "Mosquitto is running"
    else
        print_error "Mosquitto failed to start"
        print_info "Check logs with: sudo journalctl -u mosquitto -n 200 --no-pager"
        exit 1
    fi
}

# Initialize database
initialize_database() {
    print_header "Initializing Device Database"
    
    if [ -f "devices.db" ]; then
        print_warning "Database already exists"
        read -p "Delete and recreate? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm devices.db
        else
            print_info "Skipping database initialization"
            return
        fi
    fi
    
    print_info "Creating SQLite database..."
    sqlite3 devices.db <<EOF
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    shared_secret TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- Add sample devices
INSERT INTO devices (device_id, shared_secret, created_at) VALUES
    ('sensor_001', 'supersecretkey123', $(date +%s)),
    ('sensor_002', 'anothersecretkey456', $(date +%s)),
    ('sensor_003', 'yetanothersecret789', $(date +%s));
EOF
    
    print_success "Database created with 3 sample devices"
    
    print_info "Database contents:"
    sqlite3 devices.db "SELECT device_id, shared_secret FROM devices;" | while read line; do
        echo -e "  ${CYAN}$line${NC}"
    done
}

# Create helper scripts
create_helper_scripts() {
    print_header "Creating Helper Scripts"
    
    # Start gateway script
    cat > start_gateway.sh <<'EOF'
#!/bin/bash
source venv/bin/activate
python3 gateway.py
EOF
    chmod +x start_gateway.sh
    print_success "Created start_gateway.sh"
    
    # Start simulator script
    cat > start_simulator.sh <<'EOF'
#!/bin/bash
source venv/bin/activate
python3 simulator.py
EOF
    chmod +x start_simulator.sh
    print_success "Created start_simulator.sh"
    
    # Add device script
    cat > add_device.sh <<'EOF'
#!/bin/bash

if [ $# -ne 2 ]; then
    echo "Usage: $0 <device_id> <shared_secret>"
    echo "Example: $0 sensor_004 mysecretkey"
    exit 1
fi

DEVICE_ID=$1
SECRET=$2

# Add to database
sqlite3 devices.db "INSERT INTO devices (device_id, shared_secret, created_at) VALUES ('$DEVICE_ID', '$SECRET', $(date +%s));"

# Generate certificate
cd certs
openssl genrsa -out ${DEVICE_ID}.key 2048 2>/dev/null
openssl req -new -key ${DEVICE_ID}.key -out ${DEVICE_ID}.csr \
    -subj "/C=US/ST=State/L=City/O=IoTGateway/CN=${DEVICE_ID}" 2>/dev/null
openssl x509 -req -in ${DEVICE_ID}.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out ${DEVICE_ID}.crt -days 3650 2>/dev/null
rm ${DEVICE_ID}.csr
cd ..

echo "Device $DEVICE_ID added successfully!"
EOF
    chmod +x add_device.sh
    print_success "Created add_device.sh"
}

# Print final instructions
print_final_instructions() {
    print_header "Setup Complete!"
    
    echo -e "${GREEN}✓ All components installed and configured${NC}\n"
    
    echo -e "${CYAN}Project Structure:${NC}"
    echo -e "  📁 $(pwd)"
    echo -e "  ├── 📄 gateway.py          (Security gateway script)"
    echo -e "  ├── 📄 simulator.py        (Device & backend simulator)"
    echo -e "  ├── 📄 devices.db          (Device credentials database)"
    echo -e "  ├── 📁 certs/              (Local SSL/TLS certificates - keeps CA private key here)"
    echo -e "  ├── 📁 venv/               (Python virtual environment)"
    echo -e "  ├── 🚀 start_gateway.sh    (Start gateway)"
    echo -e "  ├── 🚀 start_simulator.sh  (Start simulator)"
    echo -e "  └── 🛠️  add_device.sh       (Add new device)\n"
    
    echo -e "${YELLOW}Quick Start:${NC}\n"
    echo -e "  ${CYAN}1.${NC} Start the gateway (in terminal 1):"
    echo -e "     ${GREEN}./start_gateway.sh${NC}\n"
    echo -e "  ${CYAN}2.${NC} Start the simulator (in terminal 2):"
    echo -e "     ${GREEN}./start_simulator.sh${NC}\n"
    
    echo -e "${YELLOW}Available Devices:${NC}"
    sqlite3 devices.db "SELECT device_id, shared_secret FROM devices;" | while read line; do
        echo -e "  ${MAGENTA}→${NC} $line"
    done
    echo ""
    
    echo -e "${YELLOW}To add a new device:${NC}"
    echo -e "  ${GREEN}./add_device.sh sensor_004 yoursecretkey${NC}\n"
    
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo -e "  ${CYAN}→${NC} Check Mosquitto logs: ${GREEN}sudo journalctl -u mosquitto -f${NC}"
    echo -e "  ${CYAN}→${NC} Test MQTT connection: ${GREEN}mosquitto_sub -h localhost -p 8883 --cafile /etc/mosquitto/certs/ca.crt --cert certs/sensor_001.crt --key certs/sensor_001.key -t 'device/#'${NC}"
    echo -e "  ${CYAN}→${NC} View database: ${GREEN}sqlite3 devices.db 'SELECT * FROM devices;'${NC}\n"
    
    echo -e "${GREEN}Happy testing! 🚀${NC}\n"
}

# Main execution
main() {
    echo -e "${MAGENTA}"
    cat <<'EOF'
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║          SecureIoTGateway - Automated Setup Script            ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}\n"
    
    check_sudo
    install_packages
    setup_python_env
    generate_certificates
    configure_mosquitto
    initialize_database
    create_helper_scripts
    print_final_instructions
}

main
