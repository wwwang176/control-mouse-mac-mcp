"""MCP tool definitions. Same tool names and parameters as the Windows version."""

import threading
import time

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import clipboard, input, overlay, permissions, screen, windows
from .geometry import Rect, union
from .keymap import KeyNameError, parse_combo, parse_modifiers

mcp = MCPServer(
    "computer-mac-control",
    instructions=(
        "You can control this Mac via screenshot, mouse, and keyboard tools. "
        "Typical workflow: take a screenshot to see the screen, then click/type to interact. "
        "Coordinates are macOS points with the origin at the top-left of the main display "
        "(on Retina displays one point is 2 pixels; the tools handle that). "
        "IMPORTANT: Screenshots are resized for efficiency and return scale_x and scale_y. "
        "To convert a position in the image to screen coordinates: "
        "x = left + image_x * scale_x, y = top + image_y * scale_y (left/top are given with each screenshot). "
        "All click/scroll/drag tools expect screen coordinates. "
        "Keyboard shortcuts on macOS mostly use cmd, e.g. cmd+c, cmd+v, cmd+tab. "
        "TIP: Use screenshot_after=true on action tools to get a screenshot around the action point "
        "in the same call."
    ),
)

# Tools run on worker threads; keep actions that drive the mouse/keyboard/windows from interleaving.
_action_lock = threading.Lock()


def _screenshot_result(img, region: Rect, max_width: int, max_height: int, label: str = "") -> list:
    shot = screen.make_thumbnail(img, region, max_width, max_height, label)
    return [shot.meta, Image(data=shot.png, format="png")]


def _capture_around(x: float, y: float) -> list:
    permissions.require_screen_recording()
    time.sleep(0.3)  # let the UI settle
    region = screen.region_around_point(x, y)
    return _screenshot_result(screen.capture(region), region, screen.SCREENSHOT_MAX_W, screen.SCREENSHOT_MAX_H)


def _modifiers(keys: str | None):
    try:
        return parse_modifiers(keys)
    except KeyNameError as e:
        raise ToolError(str(e)) from e


def _move_with_ring(x: float, y: float) -> None:
    input.smooth_move(x, y, on_step=overlay.cursor_highlight.move)


# ── Screen ───────────────────────────────────────────────────────────────


@mcp.tool()
def screenshot(
    left: int | None = None,
    top: int | None = None,
    right: int | None = None,
    bottom: int | None = None,
    monitor: int | None = None,
    all_screens: bool = False,
    max_width: int = 1280,
    max_height: int = 720,
) -> list:
    """Take a screenshot. Options (pick one):
    - No args: capture the main display
    - left/top/right/bottom: capture a specific region (in screen points)
    - monitor=N: capture monitor N (use list_monitors() to see indices)
    - all_screens=true: capture all monitors as one image
    Returns the image AND scale factors: x = left + image_x * scale_x, y = top + image_y * scale_y."""
    permissions.require_screen_recording()
    if all_screens:
        img, area = screen.capture_all()
        return _screenshot_result(img, area, max_width, max_height, "All screens")

    if None not in (left, top, right, bottom):
        if right <= left or bottom <= top:
            raise ToolError("right must be greater than left and bottom greater than top")
        try:
            region = screen.clamp_to_displays(Rect(left, top, right - left, bottom - top))
        except ValueError as e:
            raise ToolError(str(e)) from e
        label = "Region"
    elif monitor is not None:
        ds = screen.displays()
        match = next((d for d in ds if d.index == monitor), None)
        if match is None:
            raise ToolError(f"Monitor {monitor} not found. Available: {[d.index for d in ds]}")
        region, label = match.bounds, f"Monitor {monitor}"
    else:
        region, label = screen.main_display().bounds, "Main display"
    return _screenshot_result(screen.capture(region), region, max_width, max_height, label)


@mcp.tool()
def get_screen_info() -> dict:
    """Get main display size, virtual screen bounds, cursor position, active app/window, monitors and permission status."""
    ds = screen.displays()
    main = ds[0]
    area = union([d.bounds for d in ds])
    cx, cy = input.cursor_position()
    front = windows.frontmost()
    return {
        "primary_width": int(main.bounds.width),
        "primary_height": int(main.bounds.height),
        "primary_scale": round(main.scale, 2),
        "virtual_screen": {"left": int(area.x), "top": int(area.y), "width": int(area.width), "height": int(area.height)},
        "cursor_x": int(cx),
        "cursor_y": int(cy),
        "active_app": front["app"],
        "active_window": front["title"],
        "monitors": [d.as_dict() for d in ds],
        "permissions": permissions.status(),
    }


@mcp.tool()
def list_monitors() -> list[dict]:
    """List all connected monitors with their bounds (points), resolution (pixels), scale, and which is primary."""
    return [d.as_dict() for d in screen.displays()]


@mcp.tool()
def wait_for_change(
    left: int,
    top: int,
    right: int,
    bottom: int,
    timeout: float = 10.0,
    threshold: float = 0.01,
    interval: float = 0.5,
) -> list:
    """Wait for visual change in a screen region. Returns a screenshot when the region changes.
    threshold: fraction of pixels that must change (0.01 = 1%). interval: seconds between checks.
    If no change within timeout, returns the last screenshot with a timeout message."""
    permissions.require_screen_recording()
    try:
        region = screen.clamp_to_displays(Rect(left, top, right - left, bottom - top))
    except ValueError as e:
        raise ToolError(str(e)) from e

    base = screen.capture(region)
    current = base
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(interval)
        current = screen.capture(region)
        ratio = screen.change_ratio(base, current)
        if ratio >= threshold:
            elapsed = time.time() - start
            return [
                f"Change detected ({ratio:.1%} pixels changed) after {elapsed:.1f}s",
                *_screenshot_result(current, region, screen.SCREENSHOT_MAX_W, screen.SCREENSHOT_MAX_H),
            ]
    elapsed = time.time() - start
    return [
        f"No change after {elapsed:.1f}s (threshold={threshold:.1%})",
        *_screenshot_result(current, region, screen.SCREENSHOT_MAX_W, screen.SCREENSHOT_MAX_H),
    ]


# ── Mouse ────────────────────────────────────────────────────────────────


@mcp.tool()
def click(
    x: int,
    y: int,
    button: str = "left",
    double: bool = False,
    keys: str | None = None,
    screenshot_after: bool = False,
) -> list:
    """Click at screen coordinates (x, y). button: 'left', 'right', or 'middle'. Set double=true for double-click.
    keys: modifier keys to hold during click, e.g. 'cmd', 'shift', 'cmd+shift'.
    Set screenshot_after=true to get a screenshot of the area around the click point (saves a round trip)."""
    if button not in input.BUTTONS:
        raise ToolError(f"Unknown button: {button}. Use: {', '.join(input.BUTTONS)}")
    mods = _modifiers(keys)
    permissions.require_accessibility()
    with _action_lock:
        _move_with_ring(x, y)
        overlay.cursor_highlight.click_flash(x, y)
        input.click(x, y, button, double, mods)

    action = "Double-clicked" if double else "Clicked"
    mod_str = f"{keys}+" if keys else ""
    overlay.key_overlay.show(f"{'Double ' if double else ''}{mod_str}{button} ({x}, {y})")
    result = f"{action} {mod_str}{button} at ({x}, {y})"
    return [result, *_capture_around(x, y)] if screenshot_after else [result]


@mcp.tool()
def scroll(
    x: int, y: int, direction: str, clicks: int = 3, keys: str | None = None, screenshot_after: bool = False
) -> list:
    """Scroll at position (x, y). direction: 'up' or 'down'. clicks: number of scroll clicks (default 3).
    keys: modifier keys to hold during scroll, e.g. 'cmd'.
    Set screenshot_after=true to get a screenshot of the area around the scroll point."""
    if direction not in ("up", "down"):
        raise ToolError("direction must be 'up' or 'down'")
    mods = _modifiers(keys)
    permissions.require_accessibility()
    with _action_lock:
        _move_with_ring(x, y)
        input.scroll(x, y, direction, clicks, mods)

    mod_str = f"{keys}+" if keys else ""
    overlay.key_overlay.show(f"{mod_str}Scroll {direction} x{clicks}")
    result = f"{mod_str}Scrolled {direction} {clicks} clicks at ({x}, {y})"
    return [result, *_capture_around(x, y)] if screenshot_after else [result]


@mcp.tool()
def drag(x1: int, y1: int, x2: int, y2: int, screenshot_after: bool = False) -> list:
    """Drag from (x1, y1) to (x2, y2) with left mouse button.
    Set screenshot_after=true to get a screenshot of the area around the drop point."""
    permissions.require_accessibility()
    with _action_lock:
        input.drag(x1, y1, x2, y2, on_step=overlay.cursor_highlight.move)
    overlay.key_overlay.show(f"Drag ({x1},{y1}) -> ({x2},{y2})")
    result = f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"
    return [result, *_capture_around(x2, y2)] if screenshot_after else [result]


# ── Keyboard ─────────────────────────────────────────────────────────────


@mcp.tool()
def type_text(text: str, screenshot_after: bool = False) -> list:
    """Type text using Unicode input. Supports any language (Chinese, English, emoji, etc.).
    Newlines are sent as Return and tabs as Tab.
    Set screenshot_after=true to get a screenshot around the cursor position after typing."""
    permissions.require_accessibility()
    preview = text if len(text) <= 30 else text[:27] + "..."
    overlay.key_overlay.show(f"Type: {preview}")
    with _action_lock:
        input.type_text(text)
    result = f"Typed: {text}"
    return [result, *_capture_around(*input.cursor_position())] if screenshot_after else [result]


@mcp.tool()
def press_key(keys: str, screenshot_after: bool = False) -> list:
    """Press a key or key combination. Examples: 'enter', 'cmd+c', 'cmd+tab', 'cmd+shift+s', 'ctrl+c'.
    Modifiers: cmd (alias: command, win), ctrl (control), option (alt, opt), shift, fn.
    Keys: enter, tab, escape, backspace, delete (forward delete), space, up/down/left/right,
    home, end, pageup, pagedown, capslock, f1-f12, a-z, 0-9, and - = [ ] ; ' , . / \\ `.
    Set screenshot_after=true to get a screenshot around the cursor position after pressing."""
    try:
        combo = parse_combo(keys)
    except KeyNameError as e:
        raise ToolError(str(e)) from e
    permissions.require_accessibility()
    overlay.key_overlay.show(f"Key: {keys}")
    with _action_lock:
        input.press_combo(combo)
    result = f"Pressed: {keys}"
    return [result, *_capture_around(*input.cursor_position())] if screenshot_after else [result]


# ── Clipboard ────────────────────────────────────────────────────────────


@mcp.tool()
def clipboard_read() -> str:
    """Read text content from the clipboard."""
    return clipboard.read() or "(clipboard is empty)"


@mcp.tool()
def clipboard_write(text: str) -> str:
    """Write text to the clipboard. Supports any language."""
    clipboard.write(text)
    preview = text if len(text) <= 50 else text[:47] + "..."
    return f"Clipboard set: {preview}"


# ── Windows ──────────────────────────────────────────────────────────────


@mcp.tool()
def list_windows() -> list[dict]:
    """List all visible windows with their app, title, position and size (points)."""
    permissions.require_screen_recording()  # window titles are hidden without it
    return [w.as_dict() for w in windows.list_windows()]


@mcp.tool()
def focus_window(title: str) -> str:
    """Bring a window to the foreground. title is a regex pattern matched against window titles,
    then app names (case-insensitive). Examples: 'Chrome', '備忘錄', 'Visual Studio.*'"""
    permissions.require_screen_recording()
    permissions.require_accessibility()
    with _action_lock:
        win = windows.find_window(title)
        windows.focus(win)
    return f"Focused: {win.label}"


@mcp.tool()
def manage_window(
    title: str,
    action: str,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Manage a window. title is a regex pattern matched against window titles, then app names (case-insensitive).
    action: 'minimize', 'maximize', 'restore', 'move', 'resize'.
    For 'move': provide x, y. For 'resize': provide width, height. For 'move' + 'resize': provide all four.
    'maximize' fills the usable area of the window's display (menu bar and Dock excluded)."""
    actions = ("minimize", "maximize", "restore", "move", "resize")
    if action not in actions:
        raise ToolError(f"Unknown action: {action}. Use: {', '.join(actions)}")
    permissions.require_screen_recording()
    permissions.require_accessibility()
    with _action_lock:
        win = windows.find_window(title)
        if action == "minimize":
            windows.set_minimized(win, True)
        elif action == "restore":
            windows.set_minimized(win, False)
        elif action == "maximize":
            windows.maximize(win)
        else:
            windows.set_frame(win, x, y, width, height)
    return f"{action.capitalize()}d: {win.label}"
