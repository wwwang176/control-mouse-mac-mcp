from control_mouse_mac_mcp.geometry import (
    Rect,
    display_containing,
    flip_y,
    region_around,
    scale_factors,
    union,
)

MAIN = Rect(0, 0, 1920, 1080)
LEFT = Rect(-1440, 100, 1440, 900)  # 主螢幕左邊的副螢幕


def test_rect_edges():
    r = Rect(10, 20, 100, 50)
    assert (r.right, r.bottom) == (110, 70)
    assert r.contains(10, 20)
    assert not r.contains(110, 70)


def test_flip_y_is_symmetric():
    # CG 左上原點 ↔ Cocoa 左下原點，主螢幕高 1080
    cocoa = flip_y(Rect(100, 50, 200, 80), main_height=1080)
    assert cocoa == Rect(100, 950, 200, 80)
    assert flip_y(cocoa, main_height=1080) == Rect(100, 50, 200, 80)


def test_scale_factors_non_retina():
    # 1920x1080 point 縮到 1280x720
    assert scale_factors(Rect(0, 0, 1920, 1080), (1280, 720)) == (1.5, 1.5)


def test_scale_factors_retina_uses_points_not_pixels():
    # Retina 截圖是 2880x1800 pixel，但區域是 1440x900 point；縮圖 1152x720
    sx, sy = scale_factors(Rect(0, 0, 1440, 900), (1152, 720))
    assert (sx, sy) == (1.25, 1.25)


def test_display_containing():
    assert display_containing(-10, 500, [MAIN, LEFT]) == LEFT
    assert display_containing(5, 5, [MAIN, LEFT]) == MAIN


def test_display_containing_falls_back_to_first():
    assert display_containing(99999, 99999, [MAIN, LEFT]) == MAIN


def test_union_with_negative_origin():
    assert union([MAIN, LEFT]) == Rect(-1440, 0, 3360, 1080)


def test_region_around_clamps_to_display():
    assert region_around(100, 100, 400, MAIN) == Rect(0, 0, 500, 500)
    assert region_around(1900, 1000, 400, MAIN) == Rect(1500, 600, 420, 480)
    assert region_around(960, 540, 400, MAIN) == Rect(560, 140, 800, 800)


def test_region_around_on_negative_display():
    assert region_around(-100, 500, 400, LEFT) == Rect(-500, 100, 500, 800)
