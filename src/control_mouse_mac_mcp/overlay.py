"""Visual feedback: action text at the bottom of the screen and a ring around the cursor.

Both are borderless, click-through windows. They stay capturable so people
watching through screen sharing or remote desktop (which capture the screen)
can see them; the server's own screenshots hide them via hidden_for_capture().
Public methods are thread-safe: they only schedule work on the main thread.
"""

import time
from contextlib import contextmanager

import AppKit
import objc
import Quartz
from PyObjCTools import AppHelper

from .mainthread import call_on_main, run_on_main

CAPTURE_SETTLE = 0.05  # seconds for the window server to apply the hide before capturing


def _color(hex_rgb: str, alpha: float = 1.0):
    r, g, b = (int(hex_rgb[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def _main_height() -> float:
    return Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height


def _overlay_window(rect):
    win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False
    )
    win.setOpaque_(False)
    win.setBackgroundColor_(AppKit.NSColor.clearColor())
    win.setHasShadow_(False)
    win.setIgnoresMouseEvents_(True)
    win.setLevel_(AppKit.NSStatusWindowLevel)
    win.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle
    )
    win.setReleasedWhenClosed_(False)
    return win


class KeyOverlay:
    """Shows the current action at the bottom-center of the main display."""

    HIDE_AFTER = 1.5
    BOTTOM_MARGIN = 120
    PAD_X, PAD_Y = 20, 10

    def __init__(self):
        self._generation = 0
        self._win = _overlay_window(AppKit.NSMakeRect(0, 0, 100, 40))
        self.alpha = 1.0
        content = self._win.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(_color("#1a1a2e", 0.85).CGColor())
        content.layer().setCornerRadius_(10)
        self._label = AppKit.NSTextField.labelWithString_("")
        self._label.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(20, AppKit.NSFontWeightBold))
        self._label.setTextColor_(_color("#00FF88"))
        content.addSubview_(self._label)

    def show(self, text: str) -> None:
        call_on_main(self._show, text)

    def _show(self, text: str) -> None:
        self._label.setStringValue_(text)
        self._label.sizeToFit()
        lw, lh = self._label.frame().size.width, self._label.frame().size.height
        w, h = lw + self.PAD_X * 2, lh + self.PAD_Y * 2
        self._label.setFrameOrigin_((self.PAD_X, self.PAD_Y))

        main = AppKit.NSScreen.screens()[0].frame()
        x = main.origin.x + (main.size.width - w) / 2
        y = main.origin.y + self.BOTTOM_MARGIN
        self._win.setFrame_display_(AppKit.NSMakeRect(x, y, w, h), True)
        self._win.orderFrontRegardless()

        self._generation += 1
        gen = self._generation
        AppHelper.callLater(self.HIDE_AFTER, self._hide_if, gen)

    def _hide_if(self, gen: int) -> None:
        if gen == self._generation:
            self._win.orderOut_(None)

    def set_suppressed(self, suppressed: bool) -> None:
        self._win.setAlphaValue_(0.0 if suppressed else self.alpha)


class RingView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(RingView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.ring_color = CursorHighlight.COLOR_MOVE
        self.ring_width = CursorHighlight.WIDTH_MOVE
        return self

    def drawRect_(self, rect):
        inset = CursorHighlight.PAD + self.ring_width / 2
        oval = AppKit.NSInsetRect(self.bounds(), inset, inset)
        path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(oval)
        path.setLineWidth_(self.ring_width)
        self.ring_color.set()
        path.stroke()


class CursorHighlight:
    """Ring that follows the cursor during moves (gold) and flashes on click (red)."""

    RING_SIZE = 200
    PAD = 20
    COLOR_MOVE = _color("#FFD700")
    COLOR_CLICK = _color("#FF4444")
    WIDTH_MOVE = 30
    WIDTH_CLICK = 45
    HIDE_AFTER = 0.8
    RESET_AFTER = 0.4

    def __init__(self):
        self._generation = 0
        s = self.RING_SIZE
        self._win = _overlay_window(AppKit.NSMakeRect(0, 0, s, s))
        self.alpha = 0.6
        self._win.setAlphaValue_(self.alpha)
        self._view = RingView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, s, s))
        self._win.setContentView_(self._view)

    def move(self, x: float, y: float) -> None:
        call_on_main(self._show, x, y, False)

    def click_flash(self, x: float, y: float) -> None:
        call_on_main(self._show, x, y, True)

    def _style(self, clicked: bool) -> None:
        self._view.ring_color = self.COLOR_CLICK if clicked else self.COLOR_MOVE
        self._view.ring_width = self.WIDTH_CLICK if clicked else self.WIDTH_MOVE
        self._view.setNeedsDisplay_(True)

    def _show(self, x: float, y: float, clicked: bool) -> None:
        half = self.RING_SIZE / 2
        # CG (top-left origin) → Cocoa (bottom-left origin)
        self._win.setFrameOrigin_((x - half, _main_height() - y - half))
        self._style(clicked)
        self._win.orderFrontRegardless()

        self._generation += 1
        gen = self._generation
        if clicked:
            AppHelper.callLater(self.RESET_AFTER, self._reset_if, gen)
        AppHelper.callLater(self.HIDE_AFTER, self._hide_if, gen)

    def _reset_if(self, gen: int) -> None:
        if gen == self._generation:
            self._style(False)

    def _hide_if(self, gen: int) -> None:
        if gen == self._generation:
            self._win.orderOut_(None)

    def set_suppressed(self, suppressed: bool) -> None:
        self._win.setAlphaValue_(0.0 if suppressed else self.alpha)


class _NoOverlay:
    """Stand-in used before the overlays are created (e.g. when imported without an event loop)."""

    def show(self, *_):
        pass

    move = click_flash = show


key_overlay: KeyOverlay | _NoOverlay = _NoOverlay()
cursor_highlight: CursorHighlight | _NoOverlay = _NoOverlay()


def install() -> None:
    """Create the overlay windows. Must run on the main thread."""
    global key_overlay, cursor_highlight
    key_overlay = KeyOverlay()
    cursor_highlight = CursorHighlight()


_suppress_count = 0  # captures in progress; only touched on the main thread


def _suppress(delta: int) -> None:
    global _suppress_count
    _suppress_count += delta
    for o in (key_overlay, cursor_highlight):
        o.set_suppressed(_suppress_count > 0)


@contextmanager
def hidden_for_capture():
    """Make the overlays invisible while the server takes a screenshot."""
    if isinstance(key_overlay, _NoOverlay):
        yield
        return
    run_on_main(lambda: _suppress(1))
    time.sleep(CAPTURE_SETTLE)
    try:
        yield
    finally:
        call_on_main(_suppress, -1)
