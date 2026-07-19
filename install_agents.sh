#!/bin/sh
# Install LaunchAgents so the GUI server (with night-mode scheduler) and the
# TTS notify server start at login and restart if they crash.
# Re-running is safe: existing agents are replaced.
set -e

REPO="$(cd "$(dirname "$0")" && pwd)"
PY="$REPO/.venv/bin/python"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"

if [ ! -x "$PY" ]; then
    echo "venv not found. Run first:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

mkdir -p "$AGENTS" "$HOME/Library/Logs"

install_agent() {
    label="$1"
    script="$2"
    plist="$AGENTS/$label.plist"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$REPO/$script</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/$label.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/$label.log</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    # bootoutは非同期なので、直後のbootstrapが競合したら少し待って再試行
    for attempt in 1 2 3; do
        if launchctl bootstrap "gui/$UID_NUM" "$plist" 2>/dev/null; then
            echo "installed: $label ($script)"
            return 0
        fi
        sleep 1
    done
    echo "failed to bootstrap $label — try: launchctl bootstrap gui/$UID_NUM $plist" >&2
    return 1
}

install_agent com.bo-cli.gui gui_server.py
install_agent com.bo-cli.notify notify_server.py

echo
echo "GUI:    http://localhost:8342/"
echo "Notify: http://localhost:8340/"
echo "Logs:   ~/Library/Logs/com.bo-cli.*.log"
echo "Remove: ./uninstall_agents.sh"
