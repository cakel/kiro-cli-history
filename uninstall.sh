#!/bin/bash
set -e

INSTALL_DIR="$HOME/.local/share/kiro-cli-history"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$INSTALL_DIR/venv"

echo "Uninstalling kiro-cli-history..."

# Kill any running kiro-cli-history processes
if pgrep -f "python.*kiro_history\.py" > /dev/null 2>&1; then
    echo "Stopping running kiro-cli-history processes..."
    pkill -f "python.*kiro_history\.py" 2>/dev/null || true
    sleep 0.3
fi

# Remove launcher script
if [ -f "$BIN_DIR/kiro-cli-history" ]; then
    rm -f "$BIN_DIR/kiro-cli-history"
    echo "Removed $BIN_DIR/kiro-cli-history"
fi

# Remove install directory (includes venv)
if [ -d "$INSTALL_DIR" ]; then
    DATA_DIR="$INSTALL_DIR/data"
    if [ -d "$DATA_DIR" ]; then
        echo ""
        echo "Found configuration and logs in: $DATA_DIR"
        printf "Delete config and logs? (y/N) "
        read -r response
        if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
            # Delete everything including data
            if [ -d "$VENV_DIR" ]; then
                echo "Removing virtual environment: $VENV_DIR"
            fi
            rm -rf "$INSTALL_DIR"
            echo "Removed $INSTALL_DIR (including config and logs)"
        else
            # Keep data, remove everything else
            TEMP_DATA=$(mktemp -d)
            mv "$DATA_DIR" "$TEMP_DATA/data"
            rm -rf "$INSTALL_DIR"
            mkdir -p "$INSTALL_DIR"
            mv "$TEMP_DATA/data" "$DATA_DIR"
            rm -rf "$TEMP_DATA"
            echo "Removed program files, kept config and logs"
        fi
    else
        # No data dir, just remove everything
        if [ -d "$VENV_DIR" ]; then
            echo "Removing virtual environment: $VENV_DIR"
        fi
        rm -rf "$INSTALL_DIR"
        echo "Removed $INSTALL_DIR"
    fi
fi

echo ""
echo "Done. kiro-cli-history has been removed."
