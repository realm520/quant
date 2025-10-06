#!/usr/bin/env bash
# PyInstaller build script for tri-arb
# Creates standalone executable with all dependencies bundled

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}tri-arb PyInstaller Build Script${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if running from project root
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from project root directory${NC}"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if PyInstaller is installed
echo -e "${YELLOW}Checking PyInstaller installation...${NC}"
if ! uv pip list | grep -q pyinstaller; then
    echo -e "${YELLOW}Installing PyInstaller...${NC}"
    uv pip install pyinstaller
fi

# Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
rm -rf build/ dist/ *.spec

# Build configuration
APP_NAME="tri-arb"
ENTRY_POINT="src/tri_arb/__main__.py"
DIST_DIR="dist"
BUILD_DIR="build"

# Hidden imports (modules that PyInstaller might miss)
HIDDEN_IMPORTS=(
    "uvloop"
    "httpx"
    "pydantic"
    "typer"
    "structlog"
    "prometheus_client"
    "aiosqlite"
    "cachetools"
)

# Build hidden imports arguments
HIDDEN_IMPORT_ARGS=""
for import in "${HIDDEN_IMPORTS[@]}"; do
    HIDDEN_IMPORT_ARGS="$HIDDEN_IMPORT_ARGS --hidden-import $import"
done

# Build with PyInstaller
echo -e "${YELLOW}Building executable with PyInstaller...${NC}"
pyinstaller \
    --name "$APP_NAME" \
    --onefile \
    --console \
    --clean \
    --noconfirm \
    $HIDDEN_IMPORT_ARGS \
    --add-data "config:config" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --specpath "." \
    "$ENTRY_POINT"

# Check if build was successful
if [ -f "$DIST_DIR/$APP_NAME" ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Build successful!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "Executable: ${GREEN}$DIST_DIR/$APP_NAME${NC}"
    echo -e "Size: $(du -h "$DIST_DIR/$APP_NAME" | cut -f1)"
    echo ""
    echo -e "${YELLOW}Test the executable:${NC}"
    echo -e "  ./$DIST_DIR/$APP_NAME --version"
    echo -e "  ./$DIST_DIR/$APP_NAME --help"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Build failed!${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi

# Optional: Create tarball for distribution
echo ""
echo -e "${YELLOW}Creating distribution tarball...${NC}"
tar -czf "$DIST_DIR/$APP_NAME.tar.gz" -C "$DIST_DIR" "$APP_NAME"
echo -e "${GREEN}Tarball created: $DIST_DIR/$APP_NAME.tar.gz${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build complete!${NC}"
echo -e "${GREEN}========================================${NC}"
