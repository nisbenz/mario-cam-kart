import subprocess

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPostToPid,
    CGEventSourceCreate,
    kCGEventSourceStateHIDSystemState,
)

_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26,
    "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "Left": 123, "Right": 124, "Down": 125, "Up": 126,
    "Space": 49, "Return": 36,
}


def find_pids_by_name(process_name: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-x", process_name], capture_output=True, text=True
    )
    return [int(pid) for pid in result.stdout.split()]


class MacKeyboardBackend:
    def __init__(self, target_pid: int):
        self._target_pid = target_pid
        self._source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
        self._held: set[str] = set()

    def _post(self, key: str, key_down: bool) -> None:
        keycode = _KEYCODES[key]
        event = CGEventCreateKeyboardEvent(self._source, keycode, key_down)
        CGEventPostToPid(self._target_pid, event)

    def set_keys(self, keys_down: set[str]) -> None:
        for key in keys_down - self._held:
            self._post(key, True)
        for key in self._held - keys_down:
            self._post(key, False)
        self._held = set(keys_down)

    def release_all(self) -> None:
        self.set_keys(set())
