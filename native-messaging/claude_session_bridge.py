#!/usr/bin/env python3
"""
Native Messaging Host for Claude Session Key Bridge.
Receives sessionKey from the Chrome extension and writes to ~/.claude-session-key.
Also clears Alfred workflow org/usage caches so stale data is not served.
"""
import json
import os
import struct
import sys

SESSION_KEY_FILE = os.path.expanduser("~/.claude-session-key")

CACHE_DIRS = [
    os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-usage-alfred"),
    os.path.expanduser(
        "~/Library/Caches/com.runningwithcrayons.Alfred"
        "/Workflow Data/com.claude.usage-monitor"
    ),
]


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    length = struct.unpack("=I", raw)[0]
    return json.loads(sys.stdin.buffer.read(length))


def send_message(msg):
    data = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def clear_caches():
    for d in CACHE_DIRS:
        for name in ("org_cache.json", "usage_cache.json"):
            try:
                os.remove(os.path.join(d, name))
            except Exception:
                pass


def main():
    msg = read_message()
    if not msg:
        send_message({"status": "error", "message": "no input"})
        return

    sk = msg.get("sessionKey", "")
    if not sk.startswith("sk-ant-sid"):
        send_message({"status": "error", "message": "invalid key format"})
        return

    # Skip write if unchanged
    try:
        with open(SESSION_KEY_FILE) as f:
            if f.read().strip() == sk:
                send_message({"status": "ok", "message": "unchanged"})
                return
    except Exception:
        pass

    try:
        with open(SESSION_KEY_FILE, "w") as f:
            f.write(sk)
        os.chmod(SESSION_KEY_FILE, 0o600)
        clear_caches()
        send_message({"status": "ok", "message": "updated"})
    except Exception as e:
        send_message({"status": "error", "message": str(e)})


if __name__ == "__main__":
    main()
