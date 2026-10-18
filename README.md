# mario-cam-kart

Control Mario Kart DS with webcam hand-tracking, on melonDS. Phase 2 adds a
second camera/phone-controlled player for local co-op across two melonDS
instances.

## Phase 1 (today): single player, webcam steering

Uses [`vendor/steering_wheel.py`](vendor/steering_wheel.py), pulled in from
[zaibutman/Virtual-Steering-Wheel](https://github.com/zaibutman/Virtual-Steering-Wheel).
It tracks both hands with MediaPipe, treats them like a wheel grip (tilt the
imaginary wheel left/right to steer), fist = accelerate, open palm = brake,
and sends plain arrow-key presses via `pynput` to whatever window has OS
focus — so it only drives one game window at a time.

### Setup

```bash
cd /Users/mac/Documents/project/free/mario-cam-kart
.venv/bin/pip install -r requirements.txt   # venv already created
```

melonDS is installed at `/Applications/melonDS.app`. It's ad-hoc signed (not
notarized), so the first launch needs **right-click → Open → "Open Anyway"**
instead of a normal double-click, or Gatekeeper will refuse to run it.

1. Open melonDS, load your own legally-dumped Mario Kart DS ROM.
2. In melonDS: Config → Input, bind: Up/Down/Left/Right to arrow keys (should
   already be default).
3. Click into the melonDS window so it has focus, then run:
   ```bash
   .venv/bin/python vendor/steering_wheel.py
   ```
4. Hold both hands up in front of the webcam like gripping a wheel. Tilt to
   steer, make fists to accelerate, open both palms to brake. Press `q` in
   the controller's own preview window to stop (releases all keys).

Tune constants at the top of `vendor/steering_wheel.py` (`CAMERA_INDEX`,
`DEAD_ZONE_DEG`, etc.) to taste.

## Phase 2 (not yet wired to melonDS): 2-player co-op

The 2-player pieces already exist in `server/` but were built against Azahar
and need their process target switched to melonDS + validated against a real
melonDS local-multiplayer session (melonDS has a real `LocalMP` networking
layer for this, same mechanism as in-game Download Play):

- `server/pose_tracker.py` — MediaPipe Pose-based lean/hands-up intent
  (alternative to the hand-wheel-grip approach, tracks the whole body).
- `web/controller.html` — phone page: tilt phone to steer, tap buttons for
  accel/brake/drift, sent over WebSocket.
- `server/input_backend.py` — targets a specific process by PID via
  `CGEventPostToPid` (macOS `Quartz`), which is what makes two simultaneous
  emulator instances possible — unlike `pynput`, it doesn't depend on OS
  window focus.
- `server/app.py` — merges whichever intent source (camera or phone) is live
  per player and dispatches to that player's backend.

To bring this online once Phase 1 feels good:

1. Launch two melonDS instances, start a local multiplayer session between
   them (melonDS's own Multiplayer menu) so both are in the same Mario Kart
   DS race.
2. In `server/config.py`, set `PLAYERS[i].process_name = "melonDS"` for both
   (already defaulted), `camera_index=0` for a camera player,
   `camera_index=None` for a phone player.
3. Grant Accessibility permission (System Settings → Privacy & Security →
   Accessibility) to whatever runs `server/app.py` — required for
   `CGEventPostToPid`.
4. Run `cd server && ../.venv/bin/python app.py`.
5. For the phone player: `cd web && python3 -m http.server 8080`, then on the
   phone (same Wi-Fi) open `http://<mac-ip>:8080/controller.html`, connect to
   `ws://<mac-ip>:8765/player2` (path must match that player's `name`).

## Known limitations

- Phase 1 is single-player only by construction (global keyboard focus).
- Steering is digital, not analog — macOS has no unprivileged virtual-gamepad
  API (Apple gates a real one behind a manually-approved entitlement).
- Phase 2's process-to-PID matching is by launch order, not explicit PID —
  fine for two local instances, fragile if either restarts.
- Phase 2 hasn't been run end-to-end against melonDS yet.
