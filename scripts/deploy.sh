#!/usr/bin/env bash
# Deployment script for tri-arb
# Builds, copies files, and sets up systemd service

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/tri-arb"
SERVICE_NAME="tri-arb"
SERVICE_FILE="scripts/systemd/tri-arb.service"
BUILD_SCRIPT="scripts/build.sh"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}tri-arb Deployment Script${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    echo "Run with: sudo $0"
    exit 1
fi

# Check if running from project root
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from project root directory${NC}"
    exit 1
fi

# Step 1: Build the application
echo -e "${YELLOW}Step 1: Building application...${NC}"
if [ ! -f "$BUILD_SCRIPT" ]; then
    echo -e "${RED}Error: Build script not found: $BUILD_SCRIPT${NC}"
    exit 1
fi

bash "$BUILD_SCRIPT"

# Check if build was successful
if [ ! -f "dist/tri-arb" ]; then
    echo -e "${RED}Error: Build failed - executable not found${NC}"
    exit 1
fi

# Step 2: Create installation directory
echo -e "${YELLOW}Step 2: Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"/{bin,config,data,logs}

# Step 3: Copy files
echo -e "${YELLOW}Step 3: Copying files...${NC}"

# Copy executable
cp dist/tri-arb "$INSTALL_DIR/bin/"
chmod +x "$INSTALL_DIR/bin/tri-arb"
echo -e "${GREEN}✓ Executable copied${NC}"

# Copy configuration files
if [ -f "config/config.example.yaml" ]; then
    cp config/config.example.yaml "$INSTALL_DIR/config/config.yaml"
    echo -e "${GREEN}✓ Configuration copied${NC}"
else
    echo -e "${YELLOW}⚠ No config.example.yaml found, skipping${NC}"
fi

if [ -f ".env.example" ]; then
    cp .env.example "$INSTALL_DIR/.env.example"
    echo -e "${GREEN}✓ Environment template copied${NC}"
else
    echo -e "${YELLOW}⚠ No .env.example found, skipping${NC}"
fi

# Step 4: Create user and group
echo -e "${YELLOW}Step 4: Creating service user...${NC}"
if ! id -u tri-arb &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false tri-arb
    echo -e "${GREEN}✓ User 'tri-arb' created${NC}"
else
    echo -e "${YELLOW}⚠ User 'tri-arb' already exists${NC}"
fi

# Step 5: Set permissions
echo -e "${YELLOW}Step 5: Setting permissions...${NC}"
chown -R tri-arb:tri-arb "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR"/config/*
echo -e "${GREEN}✓ Permissions set${NC}"

# Step 6: Install systemd service
echo -e "${YELLOW}Step 6: Installing systemd service...${NC}"
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: Service file not found: $SERVICE_FILE${NC}"
    exit 1
fi

cp "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
echo -e "${GREEN}✓ Service installed${NC}"

# Step 7: Create symbolic link
echo -e "${YELLOW}Step 7: Creating symbolic link...${NC}"
ln -sf "$INSTALL_DIR/bin/tri-arb" /usr/local/bin/tri-arb
echo -e "${GREEN}✓ Symbolic link created${NC}"

# Step 8: Display next steps
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Edit configuration:"
echo -e "   ${GREEN}nano $INSTALL_DIR/config/config.yaml${NC}"
echo ""
echo -e "2. Set environment variables (optional):"
echo -e "   ${GREEN}nano $INSTALL_DIR/.env${NC}"
echo ""
echo -e "3. Enable service to start on boot:"
echo -e "   ${GREEN}systemctl enable $SERVICE_NAME${NC}"
echo ""
echo -e "4. Start the service:"
echo -e "   ${GREEN}systemctl start $SERVICE_NAME${NC}"
echo ""
echo -e "5. Check service status:"
echo -e "   ${GREEN}systemctl status $SERVICE_NAME${NC}"
echo ""
echo -e "6. View logs:"
echo -e "   ${GREEN}journalctl -u $SERVICE_NAME -f${NC}"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo -e "  Start service:   ${GREEN}systemctl start $SERVICE_NAME${NC}"
echo -e "  Stop service:    ${GREEN}systemctl stop $SERVICE_NAME${NC}"
echo -e "  Restart service: ${GREEN}systemctl restart $SERVICE_NAME${NC}"
echo -e "  View status:     ${GREEN}systemctl status $SERVICE_NAME${NC}"
echo -e "  View logs:       ${GREEN}journalctl -u $SERVICE_NAME -f${NC}"
echo ""
echo -e "${GREEN}Installation directory: $INSTALL_DIR${NC}"
echo -e "${GREEN}Executable: /usr/local/bin/tri-arb${NC}"
echo -e "${GREEN}========================================${NC}"
