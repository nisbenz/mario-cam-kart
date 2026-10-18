#!/bin/bash
# Launch melonDS with Mario Kart DS ROM automatically

# Path to melonDS executable
MELONDS="/Applications/melonDS.app/Contents/MacOS/melonDS"

# Path to Mario Kart DS ROM
ROM_PATH="/Users/mac/Documents/project/free/mario-cam-kart/Mario Kart DS (USA) (En,Fr,De,Es,It).nds"

# Boot mode: auto (boot firmware if NDS rom given), always, or never
BOOT="auto"

# Start in fullscreen mode
FULLSCREEN=""

# Build command as an array so paths with spaces survive intact
CMD=("$MELONDS" -b "$BOOT")

# Add fullscreen flag if requested
if [ -n "$FULLSCREEN" ]; then
    CMD+=(-f)
fi

# Add ROM path as argument (last argument = Slot-1 ROM)
CMD+=("$ROM_PATH")

echo "Launching: ${CMD[@]}"
exec "${CMD[@]}"
