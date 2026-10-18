#!/bin/bash
# Same entrypoint on macOS and Linux: finds (or installs) a system
# Python 3, then hands off to play.py, which does everything else
# (venv + dependency install, build-toolchain check/install, building
# melonDS if needed, launching, QR codes, the web server). Windows uses
# play.bat instead, but both just delegate to play.py — see that file
# for the actual logic.
set -e
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" > /dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] No Python 3 found."
    if [ "$(uname)" = "Darwin" ]; then
        if command -v brew > /dev/null 2>&1; then
            echo "[INFO] Installing Python 3 via Homebrew..."
            brew install python3
            PYTHON=python3
        else
            echo "        Install Homebrew (https://brew.sh) then run: brew install python3"
            exit 1
        fi
    else
        echo "        Install Python 3 with your distro's package manager, e.g.:"
        echo "          sudo apt install python3 python3-venv   (Debian/Ubuntu)"
        echo "          sudo dnf install python3                (Fedora)"
        echo "          sudo pacman -S python                   (Arch)"
        exit 1
    fi
fi

exec "$PYTHON" play.py "$@"
