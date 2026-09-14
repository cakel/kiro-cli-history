#!/bin/bash
set -e

# Get absolute path of script directory (works from any CWD)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

INSTALL_DIR="$HOME/.local/share/kiro-cli-history"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$INSTALL_DIR/venv"

# Cleanup function for rollback on failure
cleanup_on_error() {
    # Disable trap inside handler to prevent recursion
    trap - ERR
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
    # Use precise pattern matching to avoid killing unrelated processes
    pkill -f "python.*kiro_history\.py" 2>/dev/null || true
    sleep 0.3
    rm -rf "$VENV_DIR"
fi

# Prefer uv if available, fallback to standard venv
if command -v uv &>/dev/null; then
    echo "Using uv (fast mode)..."
    uv venv "$VENV_DIR" || { echo "ERROR: uv venv creation failed"; exit 1; }
    # Use venv python directly - avoids --python flag version compatibility issues
    "$VENV_DIR/bin/python" -m pip install textual --quiet || {
        # Fall back to uv pip if pip not available in venv
        uv pip install --python "$VENV_DIR" textual || { echo "ERROR: textual install failed"; exit 1; }
    }
else
    echo "Using standard venv..."
    python3 -m venv "$VENV_DIR" || { echo "ERROR: python3 venv creation failed"; exit 1; }
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet || { echo "ERROR: pip upgrade failed"; exit 1; }
    "$VENV_DIR/bin/pip" install textual --quiet || { echo "ERROR: textual install failed"; exit 1; }
fi

# Copy files
echo "Installing to $INSTALL_DIR..."
cp "$SCRIPT_DIR/kiro_history.py" "$INSTALL_DIR/kiro_history.py" || { echo "ERROR: Failed to copy kiro_history.py"; exit 1; }
cp "$SCRIPT_DIR/session_store.py" "$INSTALL_DIR/session_store.py" || { echo "ERROR: Failed to copy session_store.py"; exit 1; }

# Inject current git hash into installed script
GIT_HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || true)
if [ -n "$GIT_HASH" ]; then
    sed -i.bak "s/_BUILT_HASH = \"\"/_BUILT_HASH = \"$GIT_HASH\"/" "$INSTALL_DIR/kiro_history.py" && rm -f "$INSTALL_DIR/kiro_history.py.bak"
    echo "Injected git hash: $GIT_HASH"
fi

# Create wrapper script atomically (tmp + mv to avoid partial writes)
WRAPPER_TMP="$(mktemp "$BIN_DIR/.kiro-cli-history.XXXXXX")"
cat > "$WRAPPER_TMP" << 'WRAPPER_EOF'
#!/bin/bash
VENV_PYTHON="VENV_PYTHON_PLACEHOLDER"
MAIN_SCRIPT="MAIN_SCRIPT_PLACEHOLDER"
exec "$VENV_PYTHON" "$MAIN_SCRIPT" "$@"
WRAPPER_EOF
# Substitute actual paths after heredoc (avoids quote escaping in heredoc)
# Use portable sed -i syntax: macOS (BSD) requires backup extension, Linux (GNU) works with ""
sed -i.bak "s|VENV_PYTHON_PLACEHOLDER|${VENV_DIR}/bin/python|g" "$WRAPPER_TMP" && rm -f "${WRAPPER_TMP}.bak"
sed -i.bak "s|MAIN_SCRIPT_PLACEHOLDER|${INSTALL_DIR}/kiro_history.py|g" "$WRAPPER_TMP" && rm -f "${WRAPPER_TMP}.bak"
chmod +x "$WRAPPER_TMP"
mv "$WRAPPER_TMP" "$BIN_DIR/kiro-cli-history"

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
