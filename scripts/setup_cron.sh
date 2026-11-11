#!/usr/bin/env bash
# ==============================================================================
# stock_market_expert_bd — Linux/macOS Cron & Scheduled Jobs Installer
#
# Usage:
#   bash scripts/setup_cron.sh install    # Automatically configure and install crontab
#   bash scripts/setup_cron.sh show       # Preview generated crontab entries
#   bash scripts/setup_cron.sh uninstall  # Remove scheduled jobs from crontab
#   bash scripts/setup_cron.sh systemd    # Generate systemd unit files with absolute paths
# ==============================================================================
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
LOGS_DIR="$REPO_DIR/logs/cron"

mkdir -p "$LOGS_DIR"

# Detect Python interpreter
if [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
elif [ -f "$REPO_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_DIR/.venv/bin/python"
elif [ -f "$REPO_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$REPO_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    PYTHON_BIN="$(command -v python)"
fi

CRON_MARKER_START="# >>> DSE QUANTITATIVE ENGINE CRON JOBS >>>"
CRON_MARKER_END="# <<< DSE QUANTITATIVE ENGINE CRON JOBS <<<"

generate_crontab_block() {
    cat <<EOF
$CRON_MARKER_START
# Timezone: Asia/Dhaka (BST: UTC+6) | Trading Days: Sunday-Thursday
CRON_TZ=Asia/Dhaka
SHELL=/bin/bash

# 1. Post-Market Daily Alpha & Learning Cycle (Sun-Thu at 15:30 BST / 09:30 UTC)
30 15 * * 0-4 cd "$REPO_DIR" && "$PYTHON_BIN" scripts/auto_daily_alpha_routine.py >> "$LOGS_DIR/daily_alpha.log" 2>&1

# 2. Master Daily Pipeline & Position Plan (Sun-Thu at 16:15 BST / 10:15 UTC)
15 16 * * 0-4 cd "$REPO_DIR" && "$PYTHON_BIN" scripts/run_daily_pipeline.py --skip-scrape >> "$LOGS_DIR/daily_pipeline.log" 2>&1

# 3. Weekly Deep Knowledge Refresh (Every Thursday at 18:00 BST / 12:00 UTC)
00 18 * * 4 cd "$REPO_DIR" && "$PYTHON_BIN" scripts/analyzer.py category_a weekly >> "$LOGS_DIR/weekly_refresh.log" 2>&1

# 4. Weekly Baseline Database Compression & Git Push (Every Thursday at 19:00 BST / 13:00 UTC)
00 19 * * 4 cd "$REPO_DIR" && "$PYTHON_BIN" scripts/push_db_update.py >> "$LOGS_DIR/push_db.log" 2>&1

# 5. Midday Market Pulse Check (Sun-Thu at 11:30 and 13:30 BST during active trading)
30 11,13 * * 0-4 cd "$REPO_DIR" && "$PYTHON_BIN" scripts/check_daily_sync.py >> "$LOGS_DIR/midday_sync.log" 2>&1
$CRON_MARKER_END
EOF
}

ACTION="${1:-show}"

case "$ACTION" in
    show)
        echo "================================================================================"
        echo "📋 Generated Crontab Configuration for stock_market_expert_bd"
        echo "   Repository Directory : $REPO_DIR"
        echo "   Python Interpreter   : $PYTHON_BIN"
        echo "   Log Directory        : $LOGS_DIR"
        echo "================================================================================"
        generate_crontab_block
        echo "================================================================================"
        echo "To install these jobs into your user crontab, run:"
        echo "  bash scripts/setup_cron.sh install"
        ;;

    install)
        echo "🔧 Installing DSE scheduled jobs into user crontab..."
        TMP_CRON="$(mktemp)"
        
        # Read existing crontab, ignoring error if none exists
        crontab -l 2>/dev/null > "$TMP_CRON" || true

        # Strip old DSE block if present
        sed -i "/$CRON_MARKER_START/,/$CRON_MARKER_END/d" "$TMP_CRON" 2>/dev/null || sed -i "" "/$CRON_MARKER_START/,/$CRON_MARKER_END/d" "$TMP_CRON" 2>/dev/null || true

        # Append new block
        generate_crontab_block >> "$TMP_CRON"

        # Install new crontab
        crontab "$TMP_CRON"
        rm -f "$TMP_CRON"

        echo "✅ SUCCESS: DSE Cron jobs successfully installed into crontab!"
        echo "   Logs will be written to: $LOGS_DIR"
        echo "   View active crontab with: crontab -l"
        ;;

    uninstall)
        echo "🗑️ Removing DSE scheduled jobs from user crontab..."
        TMP_CRON="$(mktemp)"
        crontab -l 2>/dev/null > "$TMP_CRON" || true
        sed -i "/$CRON_MARKER_START/,/$CRON_MARKER_END/d" "$TMP_CRON" 2>/dev/null || sed -i "" "/$CRON_MARKER_START/,/$CRON_MARKER_END/d" "$TMP_CRON" 2>/dev/null || true
        crontab "$TMP_CRON"
        rm -f "$TMP_CRON"
        echo "✅ DSE Cron jobs removed."
        ;;

    systemd)
        echo "⚙️ Generating systemd configuration with resolved paths..."
        SYSTEMD_DIR="$REPO_DIR/cron/systemd/generated"
        mkdir -p "$SYSTEMD_DIR"

        CURRENT_USER="$(whoami 2>/dev/null || echo 'ubuntu')"

        cat <<EOF > "$SYSTEMD_DIR/dse-daily-alpha.service"
[Unit]
Description=DSE Quantitative Engine — Daily Statistical Alpha & Pipeline Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$CURRENT_USER
WorkingDirectory=$REPO_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="TZ=Asia/Dhaka"
ExecStart=$PYTHON_BIN $REPO_DIR/scripts/auto_daily_alpha_routine.py
StandardOutput=journal
StandardError=journal
Restart=no

[Install]
WantedBy=multi-user.target
EOF

        cp "$REPO_DIR/cron/systemd/dse-daily-alpha.timer" "$SYSTEMD_DIR/dse-daily-alpha.timer"
        cp "$REPO_DIR/cron/systemd/dse-weekly-refresh.timer" "$SYSTEMD_DIR/dse-weekly-refresh.timer"

        cat <<EOF > "$SYSTEMD_DIR/dse-weekly-refresh.service"
[Unit]
Description=DSE Quantitative Engine — Weekly Knowledge Base Refresh Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$CURRENT_USER
WorkingDirectory=$REPO_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="TZ=Asia/Dhaka"
ExecStart=$PYTHON_BIN $REPO_DIR/scripts/analyzer.py category_a weekly
StandardOutput=journal
StandardError=journal
Restart=no

[Install]
WantedBy=multi-user.target
EOF

        echo "✅ Systemd unit files generated in: $SYSTEMD_DIR"
        echo "To install on systemd Linux servers:"
        echo "  sudo cp $SYSTEMD_DIR/* /etc/systemd/system/"
        echo "  sudo systemctl daemon-reload"
        echo "  sudo systemctl enable --now dse-daily-alpha.timer"
        echo "  sudo systemctl enable --now dse-weekly-refresh.timer"
        ;;

    *)
        echo "Usage: bash scripts/setup_cron.sh [install|show|uninstall|systemd]"
        exit 1
        ;;
esac
