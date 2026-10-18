#!/bin/bash
# One command, everything up: native melonDS (built-in hand-gesture +
# keyboard/mouse control) + the phone bridge server + the local web
# server serving the phone controller / QR scan pages. Ctrl+C here
# stops all of it together.

set -e
cd "$(dirname "$0")"

MELONDS_BIN="vendor/melonDS-src/build/melonDS.app/Contents/MacOS/melonDS"
ROM_PATH="$(pwd)/Mario Kart DS (USA) (En,Fr,De,Es,It).nds"
WEB_PORT=8080
WS_PORT=8765

if [ ! -x "$MELONDS_BIN" ]; then
    echo "[ERROR] Native melonDS build not found at $MELONDS_BIN"
    echo "        Build it first (see vendor/melonDS-src/BUILD.md)."
    exit 1
fi
if [ ! -f "$ROM_PATH" ]; then
    echo "[ERROR] ROM not found at: $ROM_PATH"
    exit 1
fi

kill_port() {
    local pids
    pids="$(lsof -ti ":$1" 2>/dev/null || true)"
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
}

echo "[INFO] Stopping any leftover melonDS / server processes..."
pkill -9 -x melonDS 2>/dev/null || true
kill_port "$WS_PORT"
kill_port "$WEB_PORT"
sleep 1

PHONE_PID=""
WEB_PID=""

cleanup() {
    echo ""
    echo "[INFO] Shutting down everything..."
    [ -n "$PHONE_PID" ] && kill "$PHONE_PID" 2>/dev/null || true
    [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null || true
    kill_port "$WS_PORT"
    kill_port "$WEB_PORT"
    pkill -9 -x melonDS 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

echo "[INFO] Launching melonDS..."
"$MELONDS_BIN" -b auto "$ROM_PATH" > /tmp/melonds_play.log 2>&1 &
MELON_PID=$!

for _ in $(seq 1 20); do
    pgrep -x melonDS > /dev/null && break
    sleep 0.5
done
if ! pgrep -x melonDS > /dev/null; then
    echo "[ERROR] melonDS did not start. Check /tmp/melonds_play.log"
    exit 1
fi
echo "[INFO] melonDS running, pid=$(pgrep -x melonDS)"

echo "[INFO] Sizing melonDS window..."
.venv/bin/python3 - <<'PYEOF'
import subprocess
import time
import Quartz

TARGET_W, TARGET_H = 700, 1050
TARGET_X, TARGET_Y = 100, 50


def get_bounds():
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID
    )
    for w in window_list:
        if w.get("kCGWindowOwnerName") == "melonDS" and w.get("kCGWindowName"):
            return w["kCGWindowBounds"]
    return None


def run_osascript(script):
    subprocess.run(["osascript", "-e", script], capture_output=True)


for _ in range(20):
    if get_bounds() is not None:
        break
    time.sleep(0.5)
else:
    raise SystemExit("[ERROR] melonDS window never appeared")

for attempt in range(6):
    run_osascript(
        f'tell application "System Events" to tell process "melonDS" '
        f'to set size of window 1 to {{{TARGET_W}, {TARGET_H}}}'
    )
    time.sleep(0.3)
    run_osascript(
        f'tell application "System Events" to tell process "melonDS" '
        f'to set position of window 1 to {{{TARGET_X}, {TARGET_Y}}}'
    )
    time.sleep(0.3)
    b = get_bounds()
    if (
        b
        and b["Width"] == TARGET_W
        and b["Height"] == TARGET_H
        and b["X"] == TARGET_X
        and b["Y"] == TARGET_Y
    ):
        print(f"[INFO] melonDS window set to {b}")
        break
    print(f"[WARN] attempt {attempt + 1}: bounds={b}, retrying...")
else:
    print(f"[WARN] could not perfectly set window bounds, using current: {get_bounds()}")
PYEOF

echo "[INFO] Starting phone bridge server (port $WS_PORT)..."
(cd server && ../.venv/bin/python app.py > /tmp/phone_server.log 2>&1) &
PHONE_PID=$!

echo "[INFO] Starting local web server (port $WEB_PORT)..."
(cd web && python3 -m http.server "$WEB_PORT" > /tmp/web_server.log 2>&1) &
WEB_PID=$!

sleep 1
if ! kill -0 "$PHONE_PID" 2>/dev/null; then
    echo "[ERROR] Phone bridge server failed to start. Check /tmp/phone_server.log"
    cat /tmp/phone_server.log
    cleanup
fi
if ! kill -0 "$WEB_PID" 2>/dev/null; then
    echo "[ERROR] Web server failed to start. Check /tmp/web_server.log"
    cat /tmp/web_server.log
    cleanup
fi

echo "[INFO] Generating QR code..."
.venv/bin/python tools/make_controller_qr.py "$WEB_PORT" "$WS_PORT"

LOCAL_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
SCAN_URL="http://$LOCAL_IP:$WEB_PORT/scan.html"

echo "[INFO] Opening scan page: $SCAN_URL"
open "$SCAN_URL"

echo ""
echo "======================================================="
echo " Everything is running:"
echo "   - melonDS (hand-gesture + keyboard/mouse control)"
echo "   - Phone bridge server  -> ws://$LOCAL_IP:$WS_PORT/player2"
echo "   - Scan page            -> $SCAN_URL"
echo "======================================================="
echo " Press Ctrl+C here to stop everything together."
echo "======================================================="

wait "$MELON_PID"
cleanup
