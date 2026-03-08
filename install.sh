#!/usr/bin/env bash
set -euo pipefail

# install.sh — Install chaoting dispatcher as a systemd user service
#
# Usage:
#   ./install.sh                    # install (auto-detect openclaw CLI)
#   ./install.sh --dry-run          # preview generated service, don't install
#   OPENCLAW_CLI=/path/to/openclaw ./install.sh   # specify CLI path
#
# Prerequisites:
#   - Python 3.8+
#   - OpenClaw CLI installed and in PATH (or set OPENCLAW_CLI)
#   - systemd user session (loginctl enable-linger $USER)

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHAOTING_DIR="${CHAOTING_DIR:-$SCRIPT_DIR}"
OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"

# Preconditions
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found in PATH."
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    echo "Error: systemctl not found. This installer currently requires systemd user services."
    exit 1
fi

# Find OpenClaw CLI
if [ -z "${OPENCLAW_CLI:-}" ]; then
    OPENCLAW_CLI="$(command -v openclaw 2>/dev/null || true)"
    if [ -z "$OPENCLAW_CLI" ]; then
        echo "Error: openclaw CLI not found in PATH."
        echo "Install OpenClaw first, or set OPENCLAW_CLI=/path/to/openclaw"
        exit 1
    fi
fi

# Generate service content
SERVICE_CONTENT="[Unit]
Description=Chaoting Dispatcher
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${CHAOTING_DIR}/src/dispatcher.py
Restart=always
RestartSec=5
Environment=CHAOTING_DIR=${CHAOTING_DIR}
Environment=OPENCLAW_CLI=${OPENCLAW_CLI}
Environment=OPENCLAW_STATE_DIR=${OPENCLAW_STATE_DIR}
Environment=PATH=$(dirname "$OPENCLAW_CLI"):/usr/local/bin:/usr/bin:/bin
Environment=HOME=%h

[Install]
WantedBy=default.target"

echo "=== Chaoting Installer ==="
echo "  CHAOTING_DIR:  $CHAOTING_DIR"
echo "  OPENCLAW_CLI:  $OPENCLAW_CLI"
echo "  DB_PATH:       $CHAOTING_DIR/chaoting.db"
echo "  STATE_DIR:     $OPENCLAW_STATE_DIR"
echo ""

if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] Generated service file:"
    echo "---"
    echo "$SERVICE_CONTENT"
    echo "---"
    echo ""
    echo "[dry-run] Would initialize database at: $CHAOTING_DIR/chaoting.db"
    echo "[dry-run] Would install service to: ~/.config/systemd/user/chaoting-dispatcher.service"
    echo "[dry-run] No changes made."
    exit 0
fi

# Step 1: Initialize database
echo "[1/3] Initializing database..."
CHAOTING_DIR="$CHAOTING_DIR" python3 "$CHAOTING_DIR/src/init_db.py"

# Step 2: Install systemd service
echo "[2/3] Installing systemd user service..."
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
echo "$SERVICE_CONTENT" > "$SERVICE_DIR/chaoting-dispatcher.service"

# Step 3: Enable and start
systemctl --user daemon-reload
systemctl --user enable chaoting-dispatcher
systemctl --user restart chaoting-dispatcher

echo "[3/3] Service installed and started."
echo ""
systemctl --user status chaoting-dispatcher --no-pager | head -5
echo ""
echo "Done! Use 'systemctl --user status chaoting-dispatcher' to check."
echo ""
echo "To uninstall:"
echo "  systemctl --user disable --now chaoting-dispatcher"
echo "  rm ~/.config/systemd/user/chaoting-dispatcher.service"
