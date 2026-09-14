#!/bin/bash
set -e

INSTALL_DIR="$HOME/.local/share/kiro-cli-history"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$INSTALL_DIR/venv"

echo "Uninstalling kiro-cli-history..."

# Remove launcher script
if [ -f "$BIN_DIR/kiro-cli-history" ]; then
    rm -f "$BIN_DIR/kiro-cli-history"
    echo "Removed $BIN_DIR/kiro-cli-history"
fi

# Remove install directory (includes venv)
if [ -d "$INSTALL_DIR" ]; then
    if [ -d "$VENV_DIR" ]; then
        echo "Removing virtual environment: $VENV_DIR"
    fi
    rm -rf "$INSTALL_DIR"
    echo "Removed $INSTALL_DIR"
fi

echo ""
echo "Done. kiro-cli-history has been removed."
