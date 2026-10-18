from dataclasses import dataclass


@dataclass
class KeyMap:
    left: str
    right: str
    accel: str
    brake: str
    drift: str
    item: str


DEFAULT_KEYMAP = KeyMap(
    left="Left",
    right="Right",
    accel="Up",
    brake="Down",
    drift="z",
    item="x",
)

STEER_DEADZONE = 0.25

LEAN_MAX_DEGREES = 30.0

PHONE_WS_HOST = "0.0.0.0"
PHONE_WS_PORT = 8765


@dataclass
class PlayerConfig:
    name: str
    process_name: str
    camera_index: int | None = None
    keymap: KeyMap | None = None

    def __post_init__(self):
        if self.keymap is None:
            self.keymap = DEFAULT_KEYMAP


PLAYERS = [
    PlayerConfig(name="player1", process_name="melonDS", camera_index=0),
    PlayerConfig(name="player2", process_name="melonDS", camera_index=None),
]
