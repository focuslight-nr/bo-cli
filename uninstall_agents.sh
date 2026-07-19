#!/bin/sh
# Remove the LaunchAgents installed by install_agents.sh.
UID_NUM="$(id -u)"
for label in com.bo-cli.gui com.bo-cli.notify; do
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/$label.plist"
    echo "removed: $label"
done
