#!/usr/bin/env bash
set -euo pipefail

# install.sh — Install chaoting: dispatcher service + agent workspaces
#
# Usage:
#   ./install.sh                            # interactive install (legacy mode)
#   ./install.sh --workspace /path/to/ws    # workspace-isolated install
#   ./install.sh --dry-run                  # preview only, no changes
#   ./install.sh --auto-config              # non-interactive, auto-merge config
#   OPENCLAW_CLI=/path/to/cli ./install.sh
#
# Workspace mode:
#   --workspace /path/to/ws  Creates {ws}/.chaoting/ with isolated DB, logs,
#                            sentinels, and a dedicated systemd service named
#                            chaoting-dispatcher-{ws-name}.service
#
# Prerequisites:
#   - Python 3.8+
#   - OpenClaw CLI installed and in PATH (or set OPENCLAW_CLI)
#   - systemd user session

DRY_RUN=0
AUTO_CONFIG=0
WORKSPACE_PATH=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)     DRY_RUN=1; shift ;;
        --auto-config) AUTO_CONFIG=1; shift ;;
        --workspace)   WORKSPACE_PATH="$2"; shift 2 ;;
        --workspace=*) WORKSPACE_PATH="${1#*=}"; shift ;;
        *) shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHAOTING_DIR="${CHAOTING_DIR:-$SCRIPT_DIR}"
OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
SOULS_DIR="$CHAOTING_DIR/examples/souls"

# ── Workspace mode setup ──────────────────────────────────────────────────
if [ -n "$WORKSPACE_PATH" ]; then
    WORKSPACE_PATH="$(cd "$WORKSPACE_PATH" 2>/dev/null && pwd || echo "$WORKSPACE_PATH")"
    WORKSPACE_NAME="$(basename "$WORKSPACE_PATH" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
    CHAOTING_DATA_DIR="$WORKSPACE_PATH/.chaoting"
    SERVICE_NAME="chaoting-dispatcher-${WORKSPACE_NAME}"
    DB_PATH="$CHAOTING_DATA_DIR/chaoting.db"
    LOGS_DIR="$CHAOTING_DATA_DIR/logs"
    SENTINEL_DIR="$CHAOTING_DATA_DIR/sentinels"
    WORKSPACE_MODE=1
else
    WORKSPACE_NAME=""
    CHAOTING_DATA_DIR="$CHAOTING_DIR"
    SERVICE_NAME="chaoting-dispatcher"
    DB_PATH="$CHAOTING_DIR/chaoting.db"
    LOGS_DIR="$CHAOTING_DIR/logs"
    SENTINEL_DIR="$CHAOTING_DIR/sentinels"
    WORKSPACE_MODE=0
fi

# --- Agent registry ---
SUB_AGENTS=(zhongshu jishi_tech jishi_risk jishi_resource jishi_compliance bingbu gongbu hubu libu xingbu libu_hr)
AGENT_NAMES=(中书省 技术给事中 风险给事中 资源给事中 合规给事中 兵部 工部 户部 礼部 刑部 吏部)
AGENT_EMOJIS=(📜 🔬 ⚠️ 📦 🛡️ ⚔️ 🔨 📊 📚 ⚖️ 👔)

# --- Preconditions ---
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found in PATH."; exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
    echo "Error: systemctl not found. This installer requires systemd."; exit 1
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

# --- Generate service content ---
# Build ExecStart and environment for workspace vs legacy mode
if [ "$WORKSPACE_MODE" = "1" ]; then
    WORKSPACE_ENV_LINE="Environment=CHAOTING_WORKSPACE=${WORKSPACE_PATH}"
else
    WORKSPACE_ENV_LINE=""
fi

SERVICE_CONTENT="[Unit]
Description=Chaoting Dispatcher${WORKSPACE_NAME:+ (${WORKSPACE_NAME})}
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${CHAOTING_DIR}/src/dispatcher.py
Restart=always
RestartSec=5
Environment=CHAOTING_DIR=${CHAOTING_DIR}${WORKSPACE_ENV_LINE:+
${WORKSPACE_ENV_LINE}}
Environment=OPENCLAW_CLI=${OPENCLAW_CLI}
Environment=OPENCLAW_STATE_DIR=${OPENCLAW_STATE_DIR}
Environment=PATH=$(dirname "$OPENCLAW_CLI"):/usr/local/bin:/usr/bin:/bin
Environment=HOME=%h

[Install]
WantedBy=default.target"

# --- Banner ---
echo "=== Chaoting Installer ==="
echo "  CHAOTING_DIR:  $CHAOTING_DIR"
if [ "$WORKSPACE_MODE" = "1" ]; then
echo "  WORKSPACE:     $WORKSPACE_PATH"
echo "  DATA_DIR:      $CHAOTING_DATA_DIR"
echo "  SERVICE:       $SERVICE_NAME"
fi
echo "  OPENCLAW_CLI:  $OPENCLAW_CLI"
echo "  STATE_DIR:     $OPENCLAW_STATE_DIR"
echo "  DB_PATH:       $DB_PATH"
echo ""

# ============================================================
# Dry-run mode
# ============================================================
if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] Generated service file:"
    echo "---"
    echo "$SERVICE_CONTENT"
    echo "---"
    echo ""
    if [ "$WORKSPACE_MODE" = "1" ]; then
        echo "[dry-run] Would create workspace data dir: $CHAOTING_DATA_DIR"
        echo "[dry-run] Would initialize DB at: $DB_PATH"
    fi
    echo "[dry-run] Would create 11 agent workspaces under $OPENCLAW_STATE_DIR/"
    for i in "${!SUB_AGENTS[@]}"; do
        echo "  workspace-${SUB_AGENTS[$i]}/SOUL.md  (${AGENT_NAMES[$i]} ${AGENT_EMOJIS[$i]})"
    done
    echo ""
    echo "[dry-run] Would generate openclaw-agents-fragment.json"
    echo "[dry-run] No changes made."
    exit 0
fi

# ============================================================
# Step 1: Initialize database
# ============================================================
echo "[1/4] Initializing database..."
if [ "$WORKSPACE_MODE" = "1" ]; then
    # Create .chaoting directory structure
    mkdir -p "$CHAOTING_DATA_DIR/logs" "$CHAOTING_DATA_DIR/sentinels"
    echo "  Created workspace data dir: $CHAOTING_DATA_DIR"
    CHAOTING_DIR="$CHAOTING_DIR" CHAOTING_WORKSPACE="$WORKSPACE_PATH" python3 "$CHAOTING_DIR/src/init_db.py"
else
    CHAOTING_DIR="$CHAOTING_DIR" python3 "$CHAOTING_DIR/src/init_db.py"
fi

# ============================================================
# Step 2: Install systemd service
# ============================================================
echo "[2/4] Installing systemd user service..."
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
echo "$SERVICE_CONTENT" > "$SERVICE_DIR/${SERVICE_NAME}.service"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"
echo "  Dispatcher service started: $SERVICE_NAME"

# ============================================================
# Step 3: Agent setup
# ============================================================
echo "[3/4] Agent workspace setup..."

# Ask about agent setup
if [ "$AUTO_CONFIG" = "0" ]; then
    echo ""
    read -rp "Create agent workspaces and SOUL.md files? [Y/n] " SETUP_AGENTS
    SETUP_AGENTS="${SETUP_AGENTS:-Y}"
    if [[ ! "$SETUP_AGENTS" =~ ^[Yy] ]]; then
        echo "  Skipped. You can re-run with --auto-config later."
        echo ""
        echo "Done!"
        exit 0
    fi
fi

# Ask about model
DEFAULT_MODEL="anthropic/claude-sonnet-4-6"
if [ "$AUTO_CONFIG" = "0" ]; then
    echo ""
    read -rp "Model for agents (Enter for $DEFAULT_MODEL): " USER_MODEL
    AGENT_MODEL="${USER_MODEL:-$DEFAULT_MODEL}"
else
    AGENT_MODEL="${AGENT_MODEL:-$DEFAULT_MODEL}"
fi

# Create sub-agent workspaces
CREATED=0
SKIPPED=0
for i in "${!SUB_AGENTS[@]}"; do
    agent_id="${SUB_AGENTS[$i]}"
    ws_dir="$OPENCLAW_STATE_DIR/workspace-${agent_id}"
    soul_src="$SOULS_DIR/${agent_id}.md"
    soul_dst="$ws_dir/SOUL.md"

    if [ -f "$soul_dst" ]; then
        printf "  [skip]   %-20s — SOUL.md already exists\n" "$agent_id"
        SKIPPED=$((SKIPPED + 1))
    else
        mkdir -p "$ws_dir"
        if [ -f "$soul_src" ]; then
            # Replace $CHAOTING_CLI placeholder
            CHAOTING_CLI_PATH="$CHAOTING_DIR/src/chaoting"
            sed "s|\\\$CHAOTING_CLI|${CHAOTING_CLI_PATH}|g; s|\\\$CHAOTING_DIR|${CHAOTING_DIR}|g" "$soul_src" > "$soul_dst"
        else
            echo "  [warn]   $agent_id — template not found: $soul_src"
            continue
        fi
        printf "  [create] %-20s → %s\n" "$agent_id" "$soul_dst"
        CREATED=$((CREATED + 1))
    fi
done
echo "  Created $CREATED, skipped $SKIPPED."

# Ask about 司礼监
echo ""
if [ "$AUTO_CONFIG" = "0" ]; then
    echo "司礼监 (Capcom) — task creator & alert handler:"
    echo "  [1] Create standalone silijian agent"
    echo "  [2] Append to main agent's SOUL.md"
    echo "  [3] Skip"
    read -rp "Choice [1/2/3]: " CAPCOM_CHOICE
    CAPCOM_CHOICE="${CAPCOM_CHOICE:-3}"
else
    CAPCOM_CHOICE="1"
fi

case "$CAPCOM_CHOICE" in
    1)
        silijian_ws="$OPENCLAW_STATE_DIR/workspace-silijian"
        silijian_dst="$silijian_ws/SOUL.md"
        if [ -f "$silijian_dst" ]; then
            echo "  [skip] silijian — SOUL.md already exists"
        else
            mkdir -p "$silijian_ws"
            CHAOTING_CLI_PATH="$CHAOTING_DIR/src/chaoting"
            sed "s|\\\$CHAOTING_CLI|${CHAOTING_CLI_PATH}|g; s|\\\$CHAOTING_DIR|${CHAOTING_DIR}|g" "$SOULS_DIR/silijian.md" > "$silijian_dst"
            echo "  [create] silijian → $silijian_dst"
        fi
        # Add silijian to agent list for config fragment
        SUB_AGENTS+=(silijian)
        AGENT_NAMES+=("司礼监")
        AGENT_EMOJIS+=("🎭")
        ;;
    2)
        MAIN_SOUL="$OPENCLAW_STATE_DIR/workspace/SOUL.md"
        if [ -f "$MAIN_SOUL" ]; then
            echo "" >> "$MAIN_SOUL"
            echo "---" >> "$MAIN_SOUL"
            echo "" >> "$MAIN_SOUL"
            CHAOTING_CLI_PATH="$CHAOTING_DIR/src/chaoting"
            sed "s|\\\$CHAOTING_CLI|${CHAOTING_CLI_PATH}|g; s|\\\$CHAOTING_DIR|${CHAOTING_DIR}|g" "$SOULS_DIR/silijian.md" >> "$MAIN_SOUL"
            echo "  [append] silijian role appended to $MAIN_SOUL"
        else
            echo "  [warn] Main SOUL.md not found at $MAIN_SOUL — creating standalone instead"
            silijian_ws="$OPENCLAW_STATE_DIR/workspace-silijian"
            mkdir -p "$silijian_ws"
            CHAOTING_CLI_PATH="$CHAOTING_DIR/src/chaoting"
            sed "s|\\\$CHAOTING_CLI|${CHAOTING_CLI_PATH}|g; s|\\\$CHAOTING_DIR|${CHAOTING_DIR}|g" "$SOULS_DIR/silijian.md" > "$silijian_ws/SOUL.md"
            SUB_AGENTS+=(silijian)
            AGENT_NAMES+=("司礼监")
            AGENT_EMOJIS+=("🎭")
        fi
        ;;
    *)
        echo "  Skipped silijian setup."
        ;;
esac

# ============================================================
# Step 4: Generate config fragment
# ============================================================
echo ""
echo "[4/4] Generating OpenClaw agent config..."

FRAGMENT="$CHAOTING_DIR/openclaw-agents-fragment.json"
{
    echo "{"
    echo "  \"_comment\": \"Merge these into your openclaw.json under agents.list\","
    echo "  \"_generated_at\": \"$(date -Iseconds)\","
    echo "  \"agents\": ["
    last_idx=$(( ${#SUB_AGENTS[@]} - 1 ))
    for i in "${!SUB_AGENTS[@]}"; do
        agent_id="${SUB_AGENTS[$i]}"
        agent_name="${AGENT_NAMES[$i]}"
        agent_emoji="${AGENT_EMOJIS[$i]}"
        ws_path="$OPENCLAW_STATE_DIR/workspace-${agent_id}"
        comma=","
        [ "$i" -eq "$last_idx" ] && comma=""
        cat << AGENT
    {
      "id": "${agent_id}",
      "workspace": "${ws_path}",
      "model": "${AGENT_MODEL}",
      "identity": { "name": "${agent_name}", "emoji": "${agent_emoji}" }
    }${comma}
AGENT
    done
    echo "  ]"
    echo "}"
} > "$FRAGMENT"

echo "  Config fragment: $FRAGMENT"

# Auto-merge if requested and jq available
if [ "$AUTO_CONFIG" = "1" ]; then
    CONFIG_FILE="$OPENCLAW_STATE_DIR/openclaw.json"
    if [ -f "$CONFIG_FILE" ] && command -v jq >/dev/null 2>&1; then
        BACKUP="$CONFIG_FILE.bak.$(date +%Y%m%d-%H%M%S)"
        cp "$CONFIG_FILE" "$BACKUP"
        echo "  Backup: $BACKUP"

        jq --argjson new "$(jq .agents "$FRAGMENT")" \
            '.agents.list += $new | .agents.list |= unique_by(.id)' \
            "$CONFIG_FILE" > "${CONFIG_FILE}.tmp"

        if python3 -c "import json; json.load(open('${CONFIG_FILE}.tmp'))"; then
            mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
            echo "  ✅ Merged ${#SUB_AGENTS[@]} agents into $CONFIG_FILE"
        else
            rm -f "${CONFIG_FILE}.tmp"
            echo "  ❌ JSON validation failed, config not modified. Backup at: $BACKUP"
        fi
    else
        [ ! -f "${CONFIG_FILE:-}" ] && echo "  ⚠️  $CONFIG_FILE not found — merge manually."
        command -v jq >/dev/null 2>&1 || echo "  ⚠️  jq not installed — merge manually."
        echo "  Fragment: $FRAGMENT"
    fi
fi

echo ""
echo "Done! Next steps:"
echo "  1. Merge agent config:  cat $FRAGMENT"
echo "     Add to openclaw.json → agents.list, then restart OpenClaw"
echo "  2. Check dispatcher:    systemctl --user status ${SERVICE_NAME}"
echo ""
echo "To uninstall:"
echo "  systemctl --user disable --now ${SERVICE_NAME}"
echo "  rm ~/.config/systemd/user/${SERVICE_NAME}.service"
if [ "$WORKSPACE_MODE" = "1" ]; then
echo ""
echo "Workspace data dir: $CHAOTING_DATA_DIR"
echo "  To remove workspace data: rm -rf $CHAOTING_DATA_DIR"
fi
