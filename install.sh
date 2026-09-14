#!/bin/bash
set -e

# Get absolute path of script directory (works from any CWD)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

INSTALL_DIR="$HOME/.local/share/kiro-cli-history"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$INSTALL_DIR/venv"

# Cleanup function for rollback on failure
cleanup_on_error() {
    echo ""
    echo "ERROR: Installation failed. Cleaning up..."
    rm -rf "$INSTALL_DIR" 2>/dev/null || true
    rm -f "$BIN_DIR/kiro-cli-history" 2>/dev/null || true
    exit 1
}

# Set trap for cleanup on error
trap cleanup_on_error ERR

echo "kiro-cli-history installer"
echo "======================"
echo ""

# Check dependencies
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found."
    echo "Install it via your package manager (apt, brew, etc.)"
    exit 1
fi

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Create virtual environment and install dependencies
# Remove existing venv first to avoid stale state on reinstall
if [ -d "$VENV_DIR" ]; then
    echo "Removing existing virtual environment..."
    # Kill any running kiro-cli-history processes holding the venv
    pkill -f "kiro-cli-history.*python" 2>/dev/null || true
    sleep 0.3
    rm -rf "$VENV_DIR"
fi

# Prefer uv if available, fallback to standard venv
if command -v uv &>/dev/null; then
    echo "Using uv (fast mode)..."
    uv venv "$VENV_DIR" || { echo "ERROR: uv venv creation failed"; exit 1; }
    uv pip install textual --python "$VENV_DIR/bin/python" || { echo "ERROR: uv pip install failed"; exit 1; }
else
    echo "Using standard venv..."
    python3 -m venv "$VENV_DIR" || { echo "ERROR: python3 venv creation failed"; exit 1; }
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet || { echo "ERROR: pip upgrade failed"; exit 1; }
    "$VENV_DIR/bin/pip" install textual --quiet || { echo "ERROR: textual install failed"; exit 1; }
fi

# Copy files
echo "Installing to $INSTALL_DIR..."
cp "$SCRIPT_DIR/kiro_history.py" "$INSTALL_DIR/kiro_history.py" || { echo "ERROR: Failed to copy kiro_history.py"; exit 1; }

# Create wrapper script that uses venv python
cat > "$BIN_DIR/kiro-cli-history" << EOF
#!/bin/bash
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/kiro_history.py" "\$@"
EOF
chmod +x "$BIN_DIR/kiro-cli-history"

# Disable trap after successful installation
trap - ERR

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "NOTE: $BIN_DIR is not in your PATH."
    echo "Add this to your ~/.zshrc or ~/.bashrc:"
    echo ""
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo ""
echo "Installed! Run: kiro-cli-history"
echo ""
echo "To uninstall: bash $SCRIPT_DIR/uninstall.sh"
