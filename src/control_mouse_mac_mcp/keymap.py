"""Key names → macOS virtual keycodes and modifier flags.

Keycodes follow the ANSI keyboard layout (kVK_* in Carbon's Events.h).
Pure logic, no PyObjC imports, so it can be unit tested anywhere.
"""

from dataclasses import dataclass

# CGEventFlags (kCGEventFlagMask*)
FLAG_SHIFT = 0x00020000
FLAG_CTRL = 0x00040000
FLAG_ALT = 0x00080000
FLAG_CMD = 0x00100000
FLAG_FN = 0x00800000


class KeyNameError(ValueError):
    """Unknown or unsupported key name."""


@dataclass(frozen=True)
class Key:
    name: str
    code: int
    flag: int = 0  # non-zero for modifier keys

    @property
    def is_modifier(self) -> bool:
        return self.flag != 0


_MODIFIERS = {
    "cmd": (55, FLAG_CMD),
    "shift": (56, FLAG_SHIFT),
    "option": (58, FLAG_ALT),
    "ctrl": (59, FLAG_CTRL),
    "fn": (63, FLAG_FN),
}

_KEYS = {
    "enter": 36,
    "tab": 48,
    "space": 49,
    "backspace": 51,
    "escape": 53,
    "capslock": 57,
    "delete": 117,  # forward delete, same as Windows "Delete"
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
    "=": 24, "-": 27, "]": 30, "[": 33, "'": 39, ";": 41, "\\": 42, ",": 43, "/": 44,
    ".": 47, "`": 50,
}

_ALIASES = {
    "return": "enter",
    "esc": "escape",
    "command": "cmd",
    "win": "cmd",
    "windows": "cmd",
    "alt": "option",
    "opt": "option",
    "control": "ctrl",
}

_NOT_ON_MAC = {"insert", "printscreen", "numlock"}


def available_keys() -> list[str]:
    return sorted({*_MODIFIERS, *_KEYS, *_ALIASES})


def lookup(name: str) -> Key:
    raw = name.strip().lower()
    if not raw:
        raise KeyNameError("Empty key name")
    if raw in _NOT_ON_MAC:
        raise KeyNameError(f"Key '{raw}' is not available on macOS")
    canonical = _ALIASES.get(raw, raw)
    if canonical in _MODIFIERS:
        code, flag = _MODIFIERS[canonical]
        return Key(canonical, code, flag)
    if canonical in _KEYS:
        return Key(canonical, _KEYS[canonical])
    raise KeyNameError(f"Unknown key: {raw}. Available: {', '.join(available_keys())}")


def parse_combo(keys: str) -> list[Key]:
    """Parse 'cmd+shift+s' into keys, in press order."""
    return [lookup(part) for part in keys.split("+")]


def parse_modifiers(keys: str | None) -> list[Key]:
    """Parse modifiers held during a click/scroll, e.g. 'cmd+shift'."""
    if not keys:
        return []
    mods = parse_combo(keys)
    for k in mods:
        if not k.is_modifier:
            raise KeyNameError(f"'{k.name}' is not a modifier. Use cmd, ctrl, option, shift or fn")
    return mods


def combined_flags(keys: list[Key]) -> int:
    flags = 0
    for k in keys:
        flags |= k.flag
    return flags
