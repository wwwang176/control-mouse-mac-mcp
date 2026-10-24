"""Coordinate helpers. Pure logic.

All rects are in points, in CG global coordinates (origin at the top-left of
the main display, y grows downward), unless a function says otherwise.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom


def flip_y(rect: Rect, main_height: float) -> Rect:
    """Convert between CG (top-left origin) and Cocoa (bottom-left origin). Symmetric."""
    return Rect(rect.x, main_height - rect.y - rect.height, rect.width, rect.height)


def scale_factors(region: Rect, thumb_size: tuple[int, int]) -> tuple[float, float]:
    """Points per thumbnail pixel, so that point = region origin + image coord * scale."""
    tw, th = thumb_size
    return region.width / tw, region.height / th


def display_containing(px: float, py: float, displays: list[Rect]) -> Rect:
    """Display that contains the point; the first (main) display if none does."""
    for d in displays:
        if d.contains(px, py):
            return d
    return displays[0]


def union(rects: list[Rect]) -> Rect:
    left = min(r.x for r in rects)
    top = min(r.y for r in rects)
    right = max(r.right for r in rects)
    bottom = max(r.bottom for r in rects)
    return Rect(left, top, right - left, bottom - top)


def region_around(cx: float, cy: float, radius: float, display: Rect) -> Rect:
    """Square of the given radius around a point, clipped to the display."""
    left = max(display.x, cx - radius)
    top = max(display.y, cy - radius)
    right = min(display.right, cx + radius)
    bottom = min(display.bottom, cy + radius)
    return Rect(left, top, right - left, bottom - top)
