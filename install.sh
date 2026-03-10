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
# Workspace mode (--workspace):
#   Creates {ws}/.chaoting/ with isolated DB, logs, sentinels, and a
#   dedicated systemd service named chaoting-dispatcher-{ws-name}.service
#   Set CHAOTING_WORKSPACE={ws} in agent env to use the isolated data dir.
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

# ── Workspace mode setup ──────────────────────────────────────────────────
# CHAOTING_SRC_DIR always points to the original repo (source of truth for files).
# In workspace mode CHAOTING_DIR is redirected to {ws}/.chaoting so the deploy
# is self-contained; in legacy mode they are the same.
CHAOTING_SRC_DIR="$CHAOTING_DIR"
SOULS_DIR="$CHAOTING_SRC_DIR/examples/souls"

if [ -n "$WORKSPACE_PATH" ]; then
    WORKSPACE_PATH="$(cd "$WORKSPACE_PATH" 2>/dev/null && pwd || echo "$WORKSPACE_PATH")"
    WORKSPACE_NAME="$(basename "$WORKSPACE_PATH" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
    CHAOTING_DATA_DIR="$WORKSPACE_PATH/.chaoting"
    CHAOTING_DIR="$CHAOTING_DATA_DIR"  # self-contained: code lives in workspace
    SERVICE_NAME="chaoting-dispatcher-${WORKSPACE_NAME}"
    DB_PATH="$CHAOTING_DATA_DIR/chaoting.db"
    LOGS_DIR="$CHAOTING_DATA_DIR/logs"
    SENTINEL_DIR="$CHAOTING_DATA_DIR/sentinels"
    WORKSPACE_MODE=1
    echo "🏗️  Workspace mode: $WORKSPACE_PATH"
    echo "   Data dir:  $CHAOTING_DATA_DIR"
    echo "   Service:   $SERVICE_NAME"
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
# workspace 模式：注入 CHAOTING_WORKSPACE 环境变量，使 dispatcher 使用独立 data dir
_ENV_WORKSPACE=""
if [ "$WORKSPACE_MODE" -eq 1 ]; then
    _ENV_WORKSPACE="Environment=CHAOTING_WORKSPACE=${WORKSPACE_PATH}"
fi

SERVICE_CONTENT="[Unit]
Description=Chaoting Dispatcher${WORKSPACE_NAME:+ ($WORKSPACE_NAME)}
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
${_ENV_WORKSPACE}

[Install]
WantedBy=default.target"

# --- Banner ---
echo "=== Chaoting Installer ==="
if [ "$WORKSPACE_MODE" -eq 1 ]; then
    echo "  SOURCE_DIR:    $CHAOTING_SRC_DIR"
    echo "  DEPLOY_DIR:    $CHAOTING_DIR"
    echo "  WORKSPACE:     $WORKSPACE_PATH"
    echo "  SERVICE:       $SERVICE_NAME"
else
    echo "  CHAOTING_DIR:  $CHAOTING_DIR"
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
    echo "[dry-run] Would create 11 agent workspaces under $OPENCLAW_STATE_DIR/"
    for i in "${!SUB_AGENTS[@]}"; do
        echo "  workspace-${SUB_AGENTS[$i]}/SOUL.md  (${AGENT_NAMES[$i]} ${AGENT_EMOJIS[$i]})"
    done
    echo ""
    CONFIG_FILE=""
    for candidate in "$OPENCLAW_STATE_DIR/themachine.json" "$OPENCLAW_STATE_DIR/openclaw.json"; do
        [ -f "$candidate" ] && CONFIG_FILE="$candidate" && break
    done
    echo "[dry-run] Would merge ${#SUB_AGENTS[@]} agents into ${CONFIG_FILE:-<not found>}"
    if [ "$WORKSPACE_MODE" -eq 1 ]; then
        echo "[dry-run] Would copy src/, docs/, examples/souls/ to $CHAOTING_DATA_DIR"
    fi
    echo "[dry-run] No changes made."
    exit 0
fi

# ============================================================
# Step 0 (workspace only): Copy source, docs, souls into workspace
# ============================================================
if [ "$WORKSPACE_MODE" -eq 1 ]; then
    echo "[0/4] Deploying code to workspace ($CHAOTING_DATA_DIR)..."
    mkdir -p "$CHAOTING_DATA_DIR/src" "$CHAOTING_DATA_DIR/docs" "$CHAOTING_DATA_DIR/examples/souls"

    # src/ — executable scripts + modules
    for f in chaoting chaoting_log.py config.py dispatcher.py init_db.py sentinel.py; do
        cp "$CHAOTING_SRC_DIR/src/$f" "$CHAOTING_DATA_DIR/src/$f"
    done
    chmod +x "$CHAOTING_DATA_DIR/src/chaoting"
    echo "  Copied src/ ($(ls "$CHAOTING_DATA_DIR/src/" | wc -l) files)"

    # docs/
    cp -r "$CHAOTING_SRC_DIR/docs/"* "$CHAOTING_DATA_DIR/docs/" 2>/dev/null || true
    echo "  Copied docs/"

    # examples/souls/ (templates for reference)
    cp "$CHAOTING_SRC_DIR/examples/souls/"*.md "$CHAOTING_DATA_DIR/examples/souls/" 2>/dev/null || true
    echo "  Copied examples/souls/"
fi

# ============================================================
# Step 1: Initialize database
# ============================================================
echo "[1/4] Initializing database..."
CHAOTING_DIR="$CHAOTING_DIR" python3 "$CHAOTING_DIR/src/init_db.py"

# ============================================================
# Step 2: Install systemd service
# ============================================================
echo "[2/4] Installing systemd user service ($SERVICE_NAME)..."
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

# workspace 模式：确保 data dir 存在
if [ "$WORKSPACE_MODE" -eq 1 ]; then
    mkdir -p "$CHAOTING_DATA_DIR/logs" "$CHAOTING_DATA_DIR/sentinels"
    echo "  Created data dir: $CHAOTING_DATA_DIR"
fi

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
DEFAULT_MODEL="amazon-bedrock/us.anthropic.claude-sonnet-4-6"
if [ "$AUTO_CONFIG" = "0" ]; then
    echo ""
    read -rp "Model for agents (Enter for $DEFAULT_MODEL): " USER_MODEL
    AGENT_MODEL="${USER_MODEL:-$DEFAULT_MODEL}"
else
    AGENT_MODEL="${AGENT_MODEL:-$DEFAULT_MODEL}"
fi

# Helper: inject/update CHAOTING_WORKSPACE env block in a SOUL.md
_inject_workspace_env() {
    local soul_file="$1" ws_path="$2" chaoting_dir="$3" agent_id="$4"
    local marker="## Chaoting 环境变量"
    local block
    local cli_path="${chaoting_dir}/src/chaoting"
    block=$(cat <<ENVBLOCK

${marker}

**每次执行 chaoting 命令前，必须先 export 以下变量，否则命令会失败：**

\`\`\`bash
export CHAOTING_WORKSPACE=${ws_path} CHAOTING_DIR=${chaoting_dir} OPENCLAW_AGENT_ID=${agent_id}
${cli_path} <command>
\`\`\`
ENVBLOCK
)
    if grep -qF "$marker" "$soul_file" 2>/dev/null; then
        # Replace existing block (from marker to next ## or EOF)
        python3 -c "
import re, sys
with open('$soul_file') as f:
    content = f.read()
pattern = r'\n*## Chaoting 环境变量.*?(?=\n## |\Z)'
content = re.sub(pattern, '', content, flags=re.DOTALL)
with open('$soul_file', 'w') as f:
    f.write(content.rstrip() + '\n')
"
        echo "$block" >> "$soul_file"
        printf "  [update] %-20s — workspace env updated\n" "$(basename "$(dirname "$soul_file")")"
    else
        echo "$block" >> "$soul_file"
        printf "  [inject] %-20s — workspace env added\n" "$(basename "$(dirname "$soul_file")")"
    fi
}

# Create/update sub-agent workspaces
# Always regenerate SOUL.md from template to pick up latest changes and paths.
CREATED=0
UPDATED=0
for i in "${!SUB_AGENTS[@]}"; do
    agent_id="${SUB_AGENTS[$i]}"
    ws_dir="$OPENCLAW_STATE_DIR/workspace-${agent_id}"
    soul_src="$SOULS_DIR/${agent_id}.md"
    soul_dst="$ws_dir/SOUL.md"

    mkdir -p "$ws_dir"
    if [ ! -f "$soul_src" ]; then
        echo "  [warn]   $agent_id — template not found: $soul_src"
        continue
    fi

    CHAOTING_CLI_PATH="$CHAOTING_DIR/src/chaoting"
    label="create"
    [ -f "$soul_dst" ] && label="update"
    sed "s|\\\$CHAOTING_CLI|${CHAOTING_CLI_PATH}|g; s|\\\$CHAOTING_DIR|${CHAOTING_DIR}|g" "$soul_src" > "$soul_dst"
    printf "  [%s] %-20s → %s\n" "$label" "$agent_id" "$soul_dst"
    [ "$label" = "create" ] && CREATED=$((CREATED + 1)) || UPDATED=$((UPDATED + 1))

    # Inject/update CHAOTING_WORKSPACE env block in SOUL.md
    if [ "$WORKSPACE_MODE" -eq 1 ]; then
        _inject_workspace_env "$soul_dst" "$WORKSPACE_PATH" "$CHAOTING_DIR" "$agent_id"
    fi
done
echo "  Created $CREATED, updated $UPDATED."

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
        mkdir -p "$silijian_ws"
        label="create"
        [ -f "$silijian_dst" ] && label="update"
        CHAOTING_CLI_PATH="$CHAOTING_DIR/src/chaoting"
        sed "s|\\\$CHAOTING_CLI|${CHAOTING_CLI_PATH}|g; s|\\\$CHAOTING_DIR|${CHAOTING_DIR}|g" "$SOULS_DIR/silijian.md" > "$silijian_dst"
        echo "  [$label] silijian → $silijian_dst"
        if [ "$WORKSPACE_MODE" -eq 1 ]; then
            _inject_workspace_env "$silijian_dst" "$WORKSPACE_PATH" "$CHAOTING_DIR" "silijian"
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
# Step 4: Merge agent config into gateway config
# ============================================================
echo ""
echo "[4/4] Registering agents in gateway config..."

# Detect config file: themachine.json or openclaw.json
CONFIG_FILE=""
for candidate in "$OPENCLAW_STATE_DIR/themachine.json" "$OPENCLAW_STATE_DIR/openclaw.json"; do
    if [ -f "$candidate" ]; then
        CONFIG_FILE="$candidate"
        break
    fi
done

if [ -z "$CONFIG_FILE" ]; then
    echo "  ⚠️  No gateway config found in $OPENCLAW_STATE_DIR/ (themachine.json or openclaw.json)"
    echo "  Skipping agent registration. Add agents manually after creating the config."
else
    # Build agent list as JSON and merge via python3 (no jq dependency)
    _AGENT_JSON="["
    last_idx=$(( ${#SUB_AGENTS[@]} - 1 ))
    for i in "${!SUB_AGENTS[@]}"; do
        agent_id="${SUB_AGENTS[$i]}"
        agent_name="${AGENT_NAMES[$i]}"
        agent_emoji="${AGENT_EMOJIS[$i]}"
        ws_path="$OPENCLAW_STATE_DIR/workspace-${agent_id}"
        _AGENT_JSON+=$(printf '{"id":"%s","workspace":"%s","model":{"primary":"%s"},"identity":{"name":"%s","emoji":"%s"}}' \
            "$agent_id" "$ws_path" "$AGENT_MODEL" "$agent_name" "$agent_emoji")
        [ "$i" -lt "$last_idx" ] && _AGENT_JSON+=","
    done
    _AGENT_JSON+="]"

    BACKUP="$CONFIG_FILE.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$CONFIG_FILE" "$BACKUP"

    python3 -c "
import json, sys

config_file = '$CONFIG_FILE'
new_agents = json.loads('$_AGENT_JSON')

with open(config_file) as f:
    cfg = json.load(f)

existing = cfg.setdefault('agents', {}).setdefault('list', [])
existing_ids = {a['id'] for a in existing}

added = 0
updated = 0
for agent in new_agents:
    if agent['id'] in existing_ids:
        # Update workspace/model/identity for existing agents
        for i, e in enumerate(existing):
            if e['id'] == agent['id']:
                existing[i].update(agent)
                break
        updated += 1
    else:
        existing.append(agent)
        added += 1

with open(config_file, 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f'  Merged into {config_file}: {added} added, {updated} updated')
"
    echo "  Backup: $BACKUP"
fi

echo ""
echo "Done!"
echo "  Dispatcher: systemctl --user status ${SERVICE_NAME}"
if [ "$WORKSPACE_MODE" -eq 1 ]; then
    echo "  Data dir:   $CHAOTING_DATA_DIR"
fi
echo ""
echo "To uninstall:"
echo "  systemctl --user disable --now ${SERVICE_NAME}"
echo "  rm ~/.config/systemd/user/${SERVICE_NAME}.service"
