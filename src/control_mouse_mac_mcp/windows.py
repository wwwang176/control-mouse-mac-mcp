"""Window listing (CGWindowList) and control (Accessibility API)."""

import os
import re
from dataclasses import dataclass

import AppKit
import ApplicationServices as AS
import Quartz
from mcp.server.mcpserver.exceptions import ToolError

from .geometry import Rect, display_containing
from .screen import displays, visible_frames

AX_TIMEOUT = 1.0  # seconds; keeps an unresponsive app from hanging a tool call


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    pid: int
    app: str
    title: str
    bounds: Rect
    on_screen: bool

    def as_dict(self) -> dict:
        b = self.bounds
        return {
            "window_id": self.window_id,
            "app": self.app,
            "pid": self.pid,
            "title": self.title,
            "left": int(b.x),
            "top": int(b.y),
            "right": int(b.right),
            "bottom": int(b.bottom),
            "width": int(b.width),
            "height": int(b.height),
        }

    @property
    def label(self) -> str:
        return f"{self.app} - {self.title}"


def list_windows(include_offscreen: bool = False) -> list[WindowInfo]:
    """Normal (layer 0) windows that have a title, front to back. Excludes this server's own windows."""
    option = Quartz.kCGWindowListExcludeDesktopElements | (
        Quartz.kCGWindowListOptionAll if include_offscreen else Quartz.kCGWindowListOptionOnScreenOnly
    )
    me = os.getpid()
    result = []
    for w in Quartz.CGWindowListCopyWindowInfo(option, Quartz.kCGNullWindowID) or []:
        title = w.get("kCGWindowName")
        pid = int(w.get("kCGWindowOwnerPID", 0))
        if w.get("kCGWindowLayer", 0) != 0 or not title or pid == me:
            continue
        b = w.get("kCGWindowBounds", {})
        result.append(
            WindowInfo(
                window_id=int(w["kCGWindowNumber"]),
                pid=pid,
                app=str(w.get("kCGWindowOwnerName", "")),
                title=str(title),
                bounds=Rect(b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0)),
                on_screen=bool(w.get("kCGWindowIsOnscreen", False)),
            )
        )
    return result


def match_window(windows: list[WindowInfo], pattern: str) -> WindowInfo | None:
    """First window whose title matches the regex; otherwise the first whose app name matches."""
    rx = re.compile(pattern, re.IGNORECASE)
    for w in windows:
        if rx.search(w.title):
            return w
    for w in windows:
        if rx.search(w.app):
            return w
    return None


def find_window(pattern: str) -> WindowInfo:
    try:
        win = match_window(list_windows(), pattern) or match_window(list_windows(include_offscreen=True), pattern)
    except re.error as e:
        raise ToolError(f"Invalid regex '{pattern}': {e}") from e
    if win is None:
        raise ToolError(f"No window matching '{pattern}' found")
    return win


# ── Accessibility helpers ────────────────────────────────────────────────


def _ax_get(element, attr):
    err, value = AS.AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None


def _ax_set(element, attr, value, what: str) -> None:
    err = AS.AXUIElementSetAttributeValue(element, attr, value)
    if err != 0:
        raise ToolError(f"Could not {what} (AXError {err}). The app may not allow it.")


def _ax_point(value) -> tuple[float, float] | None:
    ok, pt = AS.AXValueGetValue(value, AS.kAXValueCGPointType, None) if value else (False, None)
    return (pt.x, pt.y) if ok else None


def _ax_size(value) -> tuple[float, float] | None:
    ok, sz = AS.AXValueGetValue(value, AS.kAXValueCGSizeType, None) if value else (False, None)
    return (sz.width, sz.height) if ok else None


def _ax_app(pid: int):
    app = AS.AXUIElementCreateApplication(pid)
    AS.AXUIElementSetMessagingTimeout(app, AX_TIMEOUT)
    return app


def _ax_window(win: WindowInfo):
    """The AX element of a CGWindowList window: same title, closest frame."""
    candidates = _ax_get(_ax_app(win.pid), AS.kAXWindowsAttribute) or []
    if not candidates:
        raise ToolError(f"Could not access windows of {win.app} via Accessibility")

    def score(el) -> tuple[int, float]:
        title = _ax_get(el, AS.kAXTitleAttribute)
        pos = _ax_point(_ax_get(el, AS.kAXPositionAttribute)) or (0, 0)
        size = _ax_size(_ax_get(el, AS.kAXSizeAttribute)) or (0, 0)
        b = win.bounds
        distance = abs(pos[0] - b.x) + abs(pos[1] - b.y) + abs(size[0] - b.width) + abs(size[1] - b.height)
        return (0 if title == win.title else 1, distance)

    return min(candidates, key=score)


def _activate_app(pid: int) -> None:
    """Bring the app to the front; try AX first, then NSRunningApplication."""
    ax_ok = AS.AXUIElementSetAttributeValue(_ax_app(pid), AS.kAXFrontmostAttribute, True) == 0
    app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    ns_ok = bool(app is not None and app.activateWithOptions_(AppKit.NSApplicationActivateAllWindows))
    if not (ax_ok or ns_ok):
        raise ToolError("Could not bring the app to the front")


def focus(win: WindowInfo) -> None:
    el = _ax_window(win)
    if _ax_get(el, AS.kAXMinimizedAttribute):
        _ax_set(el, AS.kAXMinimizedAttribute, False, "restore the window")
    # Best effort: some apps refuse one of these, raising the window is what matters.
    AS.AXUIElementPerformAction(el, AS.kAXRaiseAction)
    AS.AXUIElementSetAttributeValue(el, AS.kAXMainAttribute, True)
    _activate_app(win.pid)


def set_minimized(win: WindowInfo, minimized: bool) -> None:
    _ax_set(_ax_window(win), AS.kAXMinimizedAttribute, minimized, "minimize/restore the window")


def set_frame(win: WindowInfo, x: float | None, y: float | None, width: float | None, height: float | None) -> None:
    el = _ax_window(win)
    b = win.bounds
    pos = Quartz.CGPointMake(b.x if x is None else x, b.y if y is None else y)
    size = Quartz.CGSizeMake(b.width if width is None else width, b.height if height is None else height)
    pos_value = AS.AXValueCreate(AS.kAXValueCGPointType, pos)
    _ax_set(el, AS.kAXPositionAttribute, pos_value, "move the window")
    _ax_set(el, AS.kAXSizeAttribute, AS.AXValueCreate(AS.kAXValueCGSizeType, size), "resize the window")
    # Some apps clamp the position while the old size doesn't fit; set it again.
    _ax_set(el, AS.kAXPositionAttribute, pos_value, "move the window")


def maximize(win: WindowInfo) -> None:
    """Fill the usable area (menu bar and Dock excluded) of the display the window is on."""
    cx, cy = win.bounds.x + win.bounds.width / 2, win.bounds.y + win.bounds.height / 2
    ds = displays()
    target = display_containing(cx, cy, [d.bounds for d in ds])
    frame = visible_frames()[[d.bounds for d in ds].index(target)]
    set_frame(win, frame.x, frame.y, frame.width, frame.height)


def frontmost() -> dict:
    """Frontmost app and its focused window title (if Accessibility allows)."""
    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return {"app": "", "title": ""}
    pid = app.processIdentifier()
    title = ""
    focused = _ax_get(_ax_app(pid), AS.kAXFocusedWindowAttribute)
    if focused is not None:
        title = _ax_get(focused, AS.kAXTitleAttribute) or ""
    if not title:
        title = next((w.title for w in list_windows() if w.pid == pid), "")
    return {"app": str(app.localizedName() or ""), "title": str(title)}
