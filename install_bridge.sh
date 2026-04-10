#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Install Native Messaging Host for Claude Session Key Bridge
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST_NAME="com.claude.session.bridge"
HOST_SCRIPT="$SCRIPT_DIR/native-messaging/claude_session_bridge.py"

# ── Usage ────────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
  cat <<EOF
Usage: $0 <extension_id> [browser]

  extension_id  The Chrome extension ID (from chrome://extensions)
  browser       One of: chrome (default), edge, arc, brave, chromium

Steps:
  1. Open Chrome → chrome://extensions → Enable Developer Mode
  2. Click "Load unpacked" → select the extension/ folder
  3. Copy the extension ID shown below the extension name
  4. Run:  $0 <that_id>
EOF
  exit 1
fi

EXT_ID="$1"
BROWSER="${2:-chrome}"

# ── Determine NativeMessagingHosts directory ─────────────────
case "$BROWSER" in
  chrome)    NM_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts" ;;
  edge)      NM_DIR="$HOME/Library/Application Support/Microsoft Edge/NativeMessagingHosts" ;;
  arc)       NM_DIR="$HOME/Library/Application Support/Arc/User Data/NativeMessagingHosts" ;;
  brave)     NM_DIR="$HOME/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts" ;;
  chromium)  NM_DIR="$HOME/Library/Application Support/Chromium/NativeMessagingHosts" ;;
  *)         echo "Unknown browser: $BROWSER"; exit 1 ;;
esac

mkdir -p "$NM_DIR"

# ── Make host script executable ──────────────────────────────
chmod +x "$HOST_SCRIPT"

# ── Write native messaging host manifest ─────────────────────
MANIFEST="$NM_DIR/$HOST_NAME.json"

cat > "$MANIFEST" <<EOF
{
  "name": "$HOST_NAME",
  "description": "Sync Claude session key to ~/.claude-session-key",
  "path": "$HOST_SCRIPT",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
EOF

echo "✅ Installed native messaging host:"
echo "   Manifest: $MANIFEST"
echo "   Host:     $HOST_SCRIPT"
echo "   Browser:  $BROWSER"
echo ""
echo "Done! The extension will now auto-sync your Claude session key."
