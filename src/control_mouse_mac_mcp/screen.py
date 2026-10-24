"""Screenshots, display info, and change detection.

Screenshots use the built-in `screencapture` tool, which respects
NSWindow.sharingType, so the overlays never show up in captures.
Regions are in points; captured images are in pixels (2x on Retina).
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO

import AppKit
import Quartz
from PIL import Image, ImageChops

from .geometry import Rect, display_containing, flip_y, region_around, scale_factors, union
from .mainthread import run_on_main

SCREENSHOT_MAX_W = 1280
SCREENSHOT_MAX_H = 720
AUTO_SCREENSHOT_RADIUS = 400  # points around the action point


@dataclass(frozen=True)
class Display:
    index: int  # 1-based, main display first
    display_id: int
    bounds: Rect  # points
    pixel_width: int
    pixel_height: int
    is_main: bool

    @property
    def scale(self) -> float:
        return self.pixel_width / self.bounds.width

    def as_dict(self) -> dict:
        b = self.bounds
        return {
            "index": self.index,
            "display_id": self.display_id,
            "left": int(b.x),
            "top": int(b.y),
            "right": int(b.right),
            "bottom": int(b.bottom),
            "width": int(b.width),
            "height": int(b.height),
            "pixel_width": self.pixel_width,
            "pixel_height": self.pixel_height,
            "scale": round(self.scale, 2),
            "is_primary": self.is_main,
        }


def displays() -> list[Display]:
    _, ids, count = Quartz.CGGetActiveDisplayList(32, None, None)
    main_id = Quartz.CGMainDisplayID()
    ordered = sorted(ids[:count], key=lambda d: d != main_id)
    result = []
    for i, did in enumerate(ordered, start=1):
        b = Quartz.CGDisplayBounds(did)
        mode = Quartz.CGDisplayCopyDisplayMode(did)
        result.append(
            Display(
                index=i,
                display_id=int(did),
                bounds=Rect(b.origin.x, b.origin.y, b.size.width, b.size.height),
                pixel_width=int(Quartz.CGDisplayModeGetPixelWidth(mode)),
                pixel_height=int(Quartz.CGDisplayModeGetPixelHeight(mode)),
                is_main=did == main_id,
            )
        )
    return result


def main_display() -> Display:
    return displays()[0]


def visible_frames() -> list[Rect]:
    """Usable area of each display (excluding menu bar and Dock), in CG coordinates, same order as displays()."""

    def collect():
        screens = AppKit.NSScreen.screens()
        main_h = screens[0].frame().size.height
        frames = {}
        for s in screens:
            did = int(s.deviceDescription()["NSScreenNumber"])
            vf = s.visibleFrame()
            frames[did] = flip_y(Rect(vf.origin.x, vf.origin.y, vf.size.width, vf.size.height), main_h)
        return frames

    frames = run_on_main(collect)
    return [frames.get(d.display_id, d.bounds) for d in displays()]


def capture(region: Rect) -> Image.Image:
    """Capture a region (points). Returns a pixel image."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        rect = f"{int(region.x)},{int(region.y)},{int(region.width)},{int(region.height)}"
        r = subprocess.run(["screencapture", "-x", "-t", "png", "-R", rect, path], capture_output=True)
        if r.returncode != 0 or os.path.getsize(path) == 0:
            raise RuntimeError(f"screencapture failed: {r.stderr.decode().strip() or r.returncode}")
        img = Image.open(path)
        img.load()
        return img.convert("RGB")
    finally:
        os.unlink(path)


def capture_all() -> tuple[Image.Image, Rect]:
    """Capture every display and stitch them into one image covering their union."""
    ds = displays()
    area = union([d.bounds for d in ds])
    scale = max(d.scale for d in ds)
    canvas = Image.new("RGB", (round(area.width * scale), round(area.height * scale)), "black")
    for d in ds:
        b = d.bounds
        img = capture(b).resize((round(b.width * scale), round(b.height * scale)))
        canvas.paste(img, (round((b.x - area.x) * scale), round((b.y - area.y) * scale)))
    return canvas, area


def clamp_to_displays(region: Rect) -> Rect:
    """Clip a region to the union of all displays so the capture matches the requested origin."""
    area = union([d.bounds for d in displays()])
    left, top = max(region.x, area.x), max(region.y, area.y)
    right, bottom = min(region.right, area.right), min(region.bottom, area.bottom)
    if right <= left or bottom <= top:
        raise ValueError(f"Region ({region.x},{region.y})-({region.right},{region.bottom}) is outside all displays")
    return Rect(left, top, right - left, bottom - top)


def region_around_point(x: float, y: float) -> Rect:
    bounds = display_containing(x, y, [d.bounds for d in displays()])
    return region_around(x, y, AUTO_SCREENSHOT_RADIUS, bounds)


@dataclass(frozen=True)
class Screenshot:
    png: bytes
    size: tuple[int, int]
    scale_x: float
    scale_y: float
    meta: str


def make_thumbnail(img: Image.Image, region: Rect, max_width: int, max_height: int, label: str = "") -> Screenshot:
    captured = img.size
    img = img.copy()
    img.thumbnail((max_width, max_height))
    sx, sy = scale_factors(region, img.size)
    buf = BytesIO()
    img.save(buf, format="PNG")
    left, top = int(region.x), int(region.y)
    meta = (
        f"{label or 'Region'} ({left},{top})-({int(region.right)},{int(region.bottom)}) points, "
        f"captured {captured[0]}x{captured[1]}px -> {img.size[0]}x{img.size[1]}. "
        f"scale_x={sx:.2f}, scale_y={sy:.2f}. "
        f"To click (ix,iy) in this image: x=int({left} + ix*{sx:.2f}), y=int({top} + iy*{sy:.2f})"
    )
    return Screenshot(buf.getvalue(), img.size, sx, sy, meta)


def change_ratio(a: Image.Image, b: Image.Image, tolerance: int = 10) -> float:
    """Fraction of pixels whose difference exceeds the tolerance."""
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    changed = sum(diff.point(lambda p: 255 if p > tolerance else 0).histogram()[255:])
    total = a.size[0] * a.size[1]
    return changed / total if total else 0.0
