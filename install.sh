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
    # Preserve existing data/ (config and logs) if present
    DATA_BACKUP=""
    if [ -d "$INSTALL_DIR/data" ]; then
        DATA_BACKUP=$(mktemp -d)
        mv "$INSTALL_DIR/data" "$DATA_BACKUP/data" 2>/dev/null || DATA_BACKUP=""
    fi
    rm -rf "$INSTALL_DIR" 2>/dev/null || true
    rm -f "$BIN_DIR/kiro-cli-history" 2>/dev/null || true
    # Restore data/ if we backed it up
    if [ -n "$DATA_BACKUP" ] && [ -d "$DATA_BACKUP/data" ]; then
        mkdir -p "$INSTALL_DIR"
        mv "$DATA_BACKUP/data" "$INSTALL_DIR/data" 2>/dev/null || true
        rm -rf "$DATA_BACKUP"
        echo "Config and logs preserved in $INSTALL_DIR/data"
    fi
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

# Create virtual environment with uv (auto-installed via pip if missing)
# Remove existing venv first to avoid stale state on reinstall
if [ -d "$VENV_DIR" ]; then
    echo "Removing existing virtual environment..."
    # Kill any running kiro-cli-history processes holding the venv
    # Use precise pattern matching to avoid killing unrelated processes
    pkill -f "python.*kiro_history\.py" 2>/dev/null || true
    sleep 0.3
    rm -rf "$VENV_DIR"
fi

# Ensure uv is available — install it if missing
if ! command -v uv &>/dev/null; then
    echo "uv not found — installing uv via pip..."
    python3 -m pip install --quiet uv || { echo "ERROR: Failed to install uv. Install manually: pip install uv"; exit 1; }
    # Reload PATH so the newly installed uv is found
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "ERROR: uv installed but not found in PATH. Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
        exit 1
    fi
    echo "uv installed successfully."
fi

echo "Using uv..."
uv venv "$VENV_DIR" || { echo "ERROR: uv venv creation failed"; exit 1; }
uv pip install --python "$VENV_DIR/bin/python" textual || { echo "ERROR: textual install failed"; exit 1; }

# Copy files
echo "Installing to $INSTALL_DIR..."
cp "$SCRIPT_DIR/kiro_history.py" "$INSTALL_DIR/kiro_history.py" || { echo "ERROR: Failed to copy kiro_history.py"; exit 1; }
cp "$SCRIPT_DIR/session_store.py" "$INSTALL_DIR/session_store.py" || { echo "ERROR: Failed to copy session_store.py"; exit 1; }

# Copy config.py and app_log.py (required for settings and logging)
[ -f "$SCRIPT_DIR/config.py" ] || { echo "ERROR: config.py not found in $SCRIPT_DIR"; exit 1; }
[ -f "$SCRIPT_DIR/app_log.py" ] || { echo "ERROR: app_log.py not found in $SCRIPT_DIR"; exit 1; }
[ -f "$SCRIPT_DIR/_version.py" ] || { echo "ERROR: _version.py not found in $SCRIPT_DIR"; exit 1; }
[ -f "$SCRIPT_DIR/widgets.py" ] || { echo "ERROR: widgets.py not found in $SCRIPT_DIR"; exit 1; }
cp "$SCRIPT_DIR/config.py" "$INSTALL_DIR/config.py" || { echo "ERROR: Failed to copy config.py"; exit 1; }
cp "$SCRIPT_DIR/app_log.py" "$INSTALL_DIR/app_log.py" || { echo "ERROR: Failed to copy app_log.py"; exit 1; }
cp "$SCRIPT_DIR/_version.py" "$INSTALL_DIR/_version.py" || { echo "ERROR: Failed to copy _version.py"; exit 1; }
cp "$SCRIPT_DIR/widgets.py" "$INSTALL_DIR/widgets.py" || { echo "ERROR: Failed to copy widgets.py"; exit 1; }
echo "Copied config.py, app_log.py, _version.py and widgets.py"

# Inject current git version and hash into installed _version.py
GIT_HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || true)
GIT_TAG=$(git -C "$SCRIPT_DIR" describe --tags --abbrev=0 2>/dev/null || true)
if [ -n "$GIT_HASH" ]; then
    sed -i.bak "s/_BUILT_HASH = \"\"/_BUILT_HASH = \"$GIT_HASH\"/" "$INSTALL_DIR/_version.py" && rm -f "$INSTALL_DIR/_version.py.bak"
    echo "Injected git hash: $GIT_HASH"
fi
if [ -n "$GIT_TAG" ]; then
    sed -i.bak "s/_BUILT_VERSION = \"\"/_BUILT_VERSION = \"$GIT_TAG\"/" "$INSTALL_DIR/_version.py" && rm -f "$INSTALL_DIR/_version.py.bak"
    echo "Injected git version: $GIT_TAG"
fi

# Install portable ripgrep from bundled bin/
RG_BIN_DIR="$INSTALL_DIR/bin"
mkdir -p "$RG_BIN_DIR"
RG_PATH="$RG_BIN_DIR/rg"

if [ ! -f "$RG_PATH" ]; then
    ARCH=$(uname -m)
    OS=$(uname -s)
    BUNDLED_RG=""
    case "$OS" in
        Darwin)
            case "$ARCH" in
                arm64)  BUNDLED_RG="$SCRIPT_DIR/bin/macos-arm64/rg" ;;
                *)      BUNDLED_RG="$SCRIPT_DIR/bin/macos-x64/rg" ;;
            esac ;;
        Linux)
            case "$ARCH" in
                aarch64|arm64) BUNDLED_RG="$SCRIPT_DIR/bin/linux-arm64/rg" ;;
                *)             BUNDLED_RG="$SCRIPT_DIR/bin/linux-x64/rg" ;;
            esac ;;
    esac

    if [ -n "$BUNDLED_RG" ] && [ -f "$BUNDLED_RG" ]; then
        cp "$BUNDLED_RG" "$RG_PATH"
        chmod +x "$RG_PATH"
        echo "ripgrep installed: $RG_PATH"
    else
        echo "WARNING: bundled rg not found for $OS/$ARCH — search will use Python fallback."
    fi
else
    echo "ripgrep already present: $RG_PATH"
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
