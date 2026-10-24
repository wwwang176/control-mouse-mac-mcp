from PIL import Image

from control_mouse_mac_mcp.geometry import Rect
from control_mouse_mac_mcp.screen import change_ratio, make_thumbnail


def test_change_ratio_identical():
    a = Image.new("RGB", (10, 10), "white")
    assert change_ratio(a, a.copy()) == 0.0


def test_change_ratio_counts_changed_pixels():
    a = Image.new("RGB", (10, 10), "white")
    b = a.copy()
    b.paste((0, 0, 0), (0, 0, 5, 10))  # 左半邊變黑
    assert change_ratio(a, b) == 0.5


def test_change_ratio_ignores_small_noise():
    a = Image.new("RGB", (10, 10), (100, 100, 100))
    b = Image.new("RGB", (10, 10), (105, 105, 105))
    assert change_ratio(a, b) == 0.0


def test_change_ratio_handles_size_mismatch():
    a = Image.new("RGB", (10, 10), "white")
    b = Image.new("RGB", (20, 20), "white")
    assert change_ratio(a, b) == 0.0


def test_make_thumbnail_retina():
    # 1440x900 point 的 Retina 螢幕，截圖 2880x1800 pixel
    img = Image.new("RGB", (2880, 1800), "white")
    shot = make_thumbnail(img, Rect(0, 0, 1440, 900), 1280, 720)
    assert shot.size == (1152, 720)
    assert (shot.scale_x, shot.scale_y) == (1.25, 1.25)
    assert shot.png.startswith(b"\x89PNG")


def test_make_thumbnail_keeps_small_images():
    img = Image.new("RGB", (400, 300), "white")
    shot = make_thumbnail(img, Rect(100, 200, 400, 300), 1280, 720)
    assert shot.size == (400, 300)
    assert (shot.scale_x, shot.scale_y) == (1.0, 1.0)
    assert "x=int(100 + ix*1.00)" in shot.meta
