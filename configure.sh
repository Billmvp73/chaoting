#!/usr/bin/env bash
set -euo pipefail

# configure.sh — Generate and install the chaoting-dispatcher systemd service.
#
# Reads .env for configuration (OPENCLAW_CLI, OPENCLAW_STATE_DIR, etc.).
# The dispatcher and CLI also load .env at runtime, so the systemd service
# only needs CHAOTING_DIR and PATH — everything else comes from .env.
#
# Usage:
#   ./configure.sh              # generate service from .env (creates .env interactively if missing)
#   ./configure.sh --dry-run    # preview service file, no changes
#   ./configure.sh --env-only   # only create .env, don't touch systemd

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

DRY_RUN=0
ENV_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)   DRY_RUN=1 ;;
        --env-only)  ENV_ONLY=1 ;;
    esac
done

# ── Step 1: Ensure .env exists ──────────────────────────────────

create_env() {
    echo "No .env found. Let's create one."
    echo ""

    # Detect CLI
    local default_cli
    default_cli="$(command -v themachine 2>/dev/null || command -v openclaw 2>/dev/null || true)"
    read -rp "OPENCLAW_CLI [${default_cli:-<not found>}]: " user_cli
    local cli="${user_cli:-$default_cli}"
    if [ -z "$cli" ]; then
        echo "Error: no CLI binary found or provided."
        exit 1
    fi

    # Detect state dir
    local default_state=""
    if [ -d "$HOME/.themachine" ]; then
        default_state="$HOME/.themachine"
    elif [ -d "$HOME/.openclaw" ]; then
        default_state="$HOME/.openclaw"
    fi
    read -rp "OPENCLAW_STATE_DIR [${default_state:-<not found>}]: " user_state
    local state_dir="${user_state:-$default_state}"
    if [ -z "$state_dir" ]; then
        echo "Error: no state directory found or provided."
        exit 1
    fi

    # Discord channel (optional)
    read -rp "DISCORD_FALLBACK_CHANNEL_ID (optional, Enter to skip): " user_discord

    {
        echo "OPENCLAW_CLI=$cli"
        echo "OPENCLAW_STATE_DIR=$state_dir"
        [ -n "${user_discord:-}" ] && echo "DISCORD_FALLBACK_CHANNEL_ID=$user_discord"
    } > "$ENV_FILE"

    echo ""
    echo "Wrote $ENV_FILE"
}

if [ ! -f "$ENV_FILE" ]; then
    create_env
else
    echo "Using existing $ENV_FILE"
fi

if [ "$ENV_ONLY" = "1" ]; then
    echo "Done (--env-only). Edit $ENV_FILE as needed."
    exit 0
fi

# ── Step 2: Load .env ───────────────────────────────────────────

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

OPENCLAW_CLI="${OPENCLAW_CLI:-$(command -v themachine 2>/dev/null || command -v openclaw 2>/dev/null || true)}"
if [ -z "$OPENCLAW_CLI" ]; then
    echo "Error: OPENCLAW_CLI not set in .env and not found on PATH."
    exit 1
fi

CLI_DIR="$(dirname "$OPENCLAW_CLI")"
SVC_PATH="${CLI_DIR}:/usr/local/bin:/usr/bin:/bin"

# ── Step 3: Generate service file ──────────────────────────────
# The dispatcher loads .env itself at runtime, so the service only needs
# CHAOTING_DIR (to find .env) and PATH (to find the CLI binary).

SERVICE_CONTENT="[Unit]
Description=Chaoting Dispatcher
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/src/dispatcher.py
Restart=always
RestartSec=5
Environment=CHAOTING_DIR=${SCRIPT_DIR}
Environment=PATH=${SVC_PATH}
Environment=HOME=%h

[Install]
WantedBy=default.target"

# ── Step 4: Banner ─────────────────────────────────────────────

echo ""
echo "=== Chaoting Dispatcher Service ==="
echo "  CHAOTING_DIR:       $SCRIPT_DIR"
echo "  OPENCLAW_CLI:       $OPENCLAW_CLI"
echo "  OPENCLAW_STATE_DIR: ${OPENCLAW_STATE_DIR:-<not set>}"
echo "  DISCORD_CHANNEL:    ${DISCORD_FALLBACK_CHANNEL_ID:-<not set>}"
echo "  Service PATH:       $SVC_PATH"
echo ""

if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] Generated service file:"
    echo "---"
    echo "$SERVICE_CONTENT"
    echo "---"
    echo "[dry-run] No changes made."
    exit 0
fi

# ── Step 5: Install service ────────────────────────────────────

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/chaoting-dispatcher.service"
mkdir -p "$SERVICE_DIR"

if [ -f "$SERVICE_FILE" ]; then
    if diff -q <(echo "$SERVICE_CONTENT") "$SERVICE_FILE" >/dev/null 2>&1; then
        echo "Service file already up to date."
        exit 0
    fi
    BACKUP="${SERVICE_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$SERVICE_FILE" "$BACKUP"
    echo "Backed up existing service to: $BACKUP"
fi

echo "$SERVICE_CONTENT" > "$SERVICE_FILE"
echo "Wrote: $SERVICE_FILE"

systemctl --user daemon-reload
echo "Reloaded systemd daemon."

read -rp "Restart dispatcher now? [Y/n] " RESTART
RESTART="${RESTART:-Y}"
if [[ "$RESTART" =~ ^[Yy] ]]; then
    systemctl --user restart chaoting-dispatcher
    echo "Dispatcher restarted."
    sleep 1
    systemctl --user status chaoting-dispatcher --no-pager || true
else
    echo "Run when ready: systemctl --user restart chaoting-dispatcher"
fi
