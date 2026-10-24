"""Mouse and keyboard input via CGEvent. Requires the Accessibility permission."""

import time
from typing import Callable

import CoreFoundation as CF
import Quartz

from .keymap import Key, combined_flags, lookup

OnStep = Callable[[float, float], None] | None

_BUTTONS = {
    "left": (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
    "right": (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
    "middle": (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp, Quartz.kCGMouseButtonCenter),
}
BUTTONS = tuple(_BUTTONS)

LINES_PER_SCROLL_CLICK = 3  # Windows sends 120 per wheel click, which scrolls about 3 lines
MAX_UNICODE_CHUNK = 20  # CGEventKeyboardSetUnicodeString handles at most ~20 UTF-16 units


def _post(event) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def cursor_position() -> tuple[float, float]:
    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return loc.x, loc.y


def _post_mouse(event_type, x: float, y: float, button, flags: int = 0, click_state: int = 0) -> None:
    ev = Quartz.CGEventCreateMouseEvent(None, event_type, (x, y), button)
    Quartz.CGEventSetFlags(ev, flags)
    if click_state:
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, click_state)
    _post(ev)


def smooth_move(
    x: float, y: float, duration: float = 0.3, steps: int = 20, dragging: bool = False, on_step: OnStep = None
) -> None:
    """Move the cursor to (x, y) along an ease-out path."""
    event_type = Quartz.kCGEventLeftMouseDragged if dragging else Quartz.kCGEventMouseMoved
    sx, sy = cursor_position()
    dx, dy = x - sx, y - sy

    if abs(dx) <= 1 and abs(dy) <= 1:
        steps = 1
    interval = duration / steps if steps > 1 else 0
    for i in range(1, steps + 1):
        t = i / steps
        t = 1 - (1 - t) ** 2  # ease-out quadratic
        cx, cy = sx + dx * t, sy + dy * t
        _post_mouse(event_type, cx, cy, Quartz.kCGMouseButtonLeft)
        if on_step:
            on_step(cx, cy)
        if interval:
            time.sleep(interval)


def _press_modifiers(mods: list[Key]) -> None:
    held: list[Key] = []
    for k in mods:
        held.append(k)
        _post_key(k.code, True, combined_flags(held))


def _release_modifiers(mods: list[Key]) -> None:
    held = list(mods)
    for k in reversed(mods):
        held.remove(k)
        _post_key(k.code, False, combined_flags(held))


def click(x: float, y: float, button: str = "left", double: bool = False, modifiers: list[Key] | None = None) -> None:
    down, up, btn = _BUTTONS[button]
    mods = modifiers or []
    flags = combined_flags(mods)
    _press_modifiers(mods)
    try:
        for click_state in (1, 2) if double else (1,):
            _post_mouse(down, x, y, btn, flags, click_state)
            _post_mouse(up, x, y, btn, flags, click_state)
            if double and click_state == 1:
                time.sleep(0.05)
    finally:
        _release_modifiers(mods)


def natural_scrolling() -> bool:
    """System "natural scrolling" setting; macOS defaults to on when it was never changed."""
    value = CF.CFPreferencesCopyAppValue("com.apple.swipescrolldirection", CF.kCFPreferencesAnyApplication)
    return True if value is None else bool(value)


def scroll(x: float, y: float, direction: str, clicks: int = 3, modifiers: list[Key] | None = None) -> None:
    # macOS applies natural scrolling to synthetic wheel events too; compensate so "up" always shows content above.
    sign = 1 if direction == "up" else -1
    if natural_scrolling():
        sign = -sign
    mods = modifiers or []
    flags = combined_flags(mods)
    _press_modifiers(mods)
    try:
        for _ in range(clicks):
            ev = Quartz.CGEventCreateScrollWheelEvent(
                None, Quartz.kCGScrollEventUnitLine, 1, sign * LINES_PER_SCROLL_CLICK
            )
            Quartz.CGEventSetLocation(ev, (x, y))
            Quartz.CGEventSetFlags(ev, flags)
            _post(ev)
            time.sleep(0.02)
    finally:
        _release_modifiers(mods)


def drag(x1: float, y1: float, x2: float, y2: float, on_step: OnStep = None) -> None:
    smooth_move(x1, y1, on_step=on_step)
    _post_mouse(Quartz.kCGEventLeftMouseDown, x1, y1, Quartz.kCGMouseButtonLeft, click_state=1)
    time.sleep(0.05)
    try:
        smooth_move(x2, y2, duration=0.4, dragging=True, on_step=on_step)
        time.sleep(0.05)
    finally:
        _post_mouse(Quartz.kCGEventLeftMouseUp, x2, y2, Quartz.kCGMouseButtonLeft, click_state=1)


def _post_key(code: int, down: bool, flags: int) -> None:
    ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
    Quartz.CGEventSetFlags(ev, flags)
    _post(ev)
    time.sleep(0.005)


def press_combo(keys: list[Key]) -> None:
    """Press all keys in order, then release them in reverse order."""
    mods = [k for k in keys if k.is_modifier]
    flags = combined_flags(mods)
    _press_modifiers(mods)
    try:
        for k in keys:
            if not k.is_modifier:
                _post_key(k.code, True, flags)
        for k in reversed(keys):
            if not k.is_modifier:
                _post_key(k.code, False, flags)
    finally:
        _release_modifiers(mods)


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _post_unicode(chunk: str) -> None:
    n = _utf16_len(chunk)
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
        Quartz.CGEventSetFlags(ev, 0)  # don't inherit modifiers that are physically held
        Quartz.CGEventKeyboardSetUnicodeString(ev, n, chunk)
        _post(ev)
    time.sleep(0.01)


def type_text(text: str) -> None:
    """Type any Unicode text. Newlines and tabs are sent as Return and Tab key presses."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    special = {"\n": lookup("enter"), "\t": lookup("tab")}
    chunk = ""
    for ch in text:
        if ch in special or _utf16_len(chunk + ch) > MAX_UNICODE_CHUNK:
            if chunk:
                _post_unicode(chunk)
                chunk = ""
        if ch in special:
            press_combo([special[ch]])
        else:
            chunk += ch
    if chunk:
        _post_unicode(chunk)
