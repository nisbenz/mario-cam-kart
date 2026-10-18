import asyncio
import json
import sys
import threading
import time

import websockets

from config import PHONE_WS_HOST, PHONE_WS_PORT, PLAYERS, STEER_DEADZONE, PlayerConfig
from input_backend import MacKeyboardBackend, find_pids_by_name
from pose_tracker import Intent, PoseTracker

_lock = threading.Lock()
_latest_intents: dict[str, Intent] = {}


def _set_intent(player_name: str, intent: Intent) -> None:
    with _lock:
        _latest_intents[player_name] = intent


def _get_intent(player_name: str) -> Intent | None:
    with _lock:
        return _latest_intents.get(player_name)


def _camera_loop(player: PlayerConfig) -> None:
    tracker = PoseTracker(player.camera_index)
    try:
        while True:
            intent = tracker.read_intent()
            if intent is not None:
                _set_intent(player.name, intent)
            time.sleep(1 / 30)
    finally:
        tracker.close()


async def _phone_handler(websocket, player: PlayerConfig) -> None:
    async for message in websocket:
        data = json.loads(message)
        intent = Intent(
            steer=float(data.get("steer", 0.0)),
            accel=bool(data.get("accel", False)),
            brake=bool(data.get("brake", False)),
            drift=bool(data.get("drift", False)),
            item=bool(data.get("item", False)),
        )
        _set_intent(player.name, intent)


async def _run_phone_server(phone_players: list[PlayerConfig]) -> None:
    if not phone_players:
        return
    by_path = {f"/{player.name}": player for player in phone_players}

    async def handler(websocket):
        path = websocket.request.path
        player = by_path.get(path)
        if player is None:
            await websocket.close(code=4004, reason="unknown player path")
            return
        await _phone_handler(websocket, player)

    async with websockets.serve(handler, PHONE_WS_HOST, PHONE_WS_PORT):
        await asyncio.Future()


def _intent_to_keys(player: PlayerConfig, intent: Intent) -> set[str]:
    keymap = player.keymap
    keys: set[str] = set()
    if intent.steer <= -STEER_DEADZONE:
        keys.add(keymap.left)
    elif intent.steer >= STEER_DEADZONE:
        keys.add(keymap.right)
    if intent.accel:
        keys.add(keymap.accel)
    if intent.brake:
        keys.add(keymap.brake)
    if intent.drift:
        keys.add(keymap.drift)
    if intent.item:
        keys.add(keymap.item)
    return keys


def _resolve_backends() -> dict[str, MacKeyboardBackend]:
    pids_by_name: dict[str, list[int]] = {}
    backends: dict[str, MacKeyboardBackend] = {}
    for player in PLAYERS:
        pids = pids_by_name.setdefault(
            player.process_name, find_pids_by_name(player.process_name)
        )
        index = sum(1 for p in PLAYERS[: PLAYERS.index(player)] if p.process_name == player.process_name)
        if index >= len(pids):
            print(
                f"warning: no running '{player.process_name}' process found for {player.name}",
                file=sys.stderr,
            )
            continue
        backends[player.name] = MacKeyboardBackend(pids[index])
    return backends


async def _dispatch_loop(backends: dict[str, MacKeyboardBackend]) -> None:
    while True:
        for player in PLAYERS:
            backend = backends.get(player.name)
            if backend is None:
                continue
            intent = _get_intent(player.name) or Intent(0.0, False, False, False)
            backend.set_keys(_intent_to_keys(player, intent))
        await asyncio.sleep(1 / 60)


async def main() -> None:
    backends = _resolve_backends()

    camera_players = [p for p in PLAYERS if p.camera_index is not None]
    phone_players = [p for p in PLAYERS if p.camera_index is None]

    for player in camera_players:
        threading.Thread(target=_camera_loop, args=(player,), daemon=True).start()

    await asyncio.gather(
        _run_phone_server(phone_players),
        _dispatch_loop(backends),
    )


if __name__ == "__main__":
    asyncio.run(main())
