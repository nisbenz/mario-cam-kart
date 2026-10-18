#!/bin/bash
# Launch melonDS + the webcam cockpit together as one step.
#
# 1. Kills any leftover melonDS / cockpit processes from a previous run.
# 2. Launches melonDS with the ROM.
# 3. Waits for its window, then resizes/repositions it to a size melonDS
#    renders cleanly at (it visually corrupts at extreme window sizes).
# 4. Launches vendor/cockpit.py, which captures that window + your webcam
#    into one combined view and drives the game via hand gestures.

set -e
cd "$(dirname "$0")"

echo "[INFO] Stopping any existing melonDS / cockpit processes..."
pkill -x melonDS 2>/dev/null || true
pkill -f "vendor/cockpit.py" 2>/dev/null || true
sleep 1

echo "[INFO] Launching melonDS..."
./launch_mkds.sh > /tmp/melon_launch.log 2>&1 &

MELON_PID=""
for _ in $(seq 1 20); do
    MELON_PID=$(pgrep -x melonDS || true)
    if [ -n "$MELON_PID" ]; then
        break
    fi
    sleep 0.5
done

if [ -z "$MELON_PID" ]; then
    echo "[ERROR] melonDS did not start. Check /tmp/melon_launch.log"
    exit 1
fi
echo "[INFO] melonDS running, pid=$MELON_PID"

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

echo "[INFO] Launching cockpit..."
exec .venv/bin/python -u vendor/cockpit.py
