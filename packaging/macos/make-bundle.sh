#!/bin/bash
# Assembles the standalone macOS DS64 app bundle:
#
#   melonDS.app/
#     Contents/MacOS/melonDS        (embedded ROM, static Qt)
#     Contents/Frameworks/Python.framework   (runtime used by embedded Python)
#     Contents/Resources/ds64/
#       site-packages/              (target-arch wheels from requirements.txt)
#       tools/{gesture,phone}
#       make_controller_qr.py, lan_ip.py
#       web/
#
# melonDS finds this layout at runtime (see ds64ConfigureBundledRuntime() in
# src/frontend/qt_sdl/main.cpp), so launching the .app directly generates the
# QR codes, serves the controller page, and boots the embedded ROM exactly
# like the Linux AppImage does.
#
# Usage: make-bundle.sh <melonDS.app> <repo-root> <python3> <site-packages-dir>

set -euo pipefail

APP="$1"
REPO_ROOT="$2"
PYTHON="$3"
SITE_PACKAGES="$4"

EXE="$APP/Contents/MacOS/melonDS"
DEST_FRAMEWORK="$APP/Contents/Frameworks/Python.framework"

if [ ! -x "$EXE" ]; then
    echo "error: $EXE not found" >&2
    exit 1
fi

PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_PREFIX="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
SOURCE_FRAMEWORK="$(cd "$PY_PREFIX/../.." && pwd)"
if [ "$(basename "$SOURCE_FRAMEWORK")" != "Python.framework" ]; then
    echo "error: $PYTHON is not a framework Python build (base_prefix=$PY_PREFIX)" >&2
    exit 1
fi

echo "==> Bundling Python.framework ($PY_VERSION)"
rm -rf "$DEST_FRAMEWORK"
mkdir -p "$APP/Contents/Frameworks"
cp -a "$SOURCE_FRAMEWORK" "$DEST_FRAMEWORK"

FW_BIN="$DEST_FRAMEWORK/Versions/$PY_VERSION/Python"
NEW_ID="@rpath/Python.framework/Versions/$PY_VERSION/Python"
if [ ! -f "$FW_BIN" ]; then
    echo "error: framework binary not found at $FW_BIN" >&2
    exit 1
fi
install_name_tool -id "$NEW_ID" "$FW_BIN"

# Point the executable at the copy inside the app, and let @rpath resolve to
# Contents/Frameworks.
OLD_DEP="$(otool -L "$EXE" | awk '/Python\.framework/ {print $1; exit}')"
if [ -n "$OLD_DEP" ]; then
    install_name_tool -change "$OLD_DEP" "$NEW_ID" "$EXE"
else
    echo "error: $EXE does not link Python.framework" >&2
    exit 1
fi
if ! otool -l "$EXE" | grep -A2 'LC_RPATH' | grep -q '@executable_path/../Frameworks'; then
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$EXE"
fi

echo "==> Adding DS64 scripts, Python packages, and controller page"
BUNDLE="$APP/Contents/Resources/ds64"
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/tools"
cp -a "$REPO_ROOT/vendor/melonDS-src/tools/gesture" "$BUNDLE/tools/"
cp -a "$REPO_ROOT/vendor/melonDS-src/tools/phone" "$BUNDLE/tools/"
cp -a "$REPO_ROOT/tools/make_controller_qr.py" "$BUNDLE/"
cp -a "$REPO_ROOT/tools/lan_ip.py" "$BUNDLE/"
cp -a "$REPO_ROOT/web" "$BUNDLE/web"
if [ -d "$SITE_PACKAGES" ]; then
    cp -a "$SITE_PACKAGES" "$BUNDLE/site-packages"
fi

find "$BUNDLE" -name __pycache__ -prune -exec rm -rf {} +

# install_name_tool invalidated the old ad-hoc signature; re-sign the complete
# bundle after adding Resources.
codesign --force --deep --sign - "$APP" >/dev/null

echo "==> Bundle ready: $APP"
