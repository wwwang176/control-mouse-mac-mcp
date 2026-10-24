import re

import pytest

from control_mouse_mac_mcp.geometry import Rect
from control_mouse_mac_mcp.windows import WindowInfo, match_window

WINS = [
    WindowInfo(1, 100, "Google Chrome", "GitHub - Pull requests", Rect(0, 0, 800, 600), True),
    WindowInfo(2, 200, "Notes", "購物清單", Rect(10, 10, 400, 300), True),
    WindowInfo(3, 300, "Terminal", "zsh — 80×24", Rect(20, 20, 600, 400), True),
]


def test_match_by_title_regex_case_insensitive():
    assert match_window(WINS, "github").window_id == 1
    assert match_window(WINS, "購物").window_id == 2


def test_title_match_wins_over_app_match():
    wins = [
        WindowInfo(1, 100, "Notes", "Untitled", Rect(0, 0, 1, 1), True),
        WindowInfo(2, 200, "TextEdit", "Notes draft", Rect(0, 0, 1, 1), True),
    ]
    assert match_window(wins, "notes").window_id == 2


def test_falls_back_to_app_name():
    assert match_window(WINS, "chrome").window_id == 1
    assert match_window(WINS, "^terminal$").window_id == 3


def test_no_match_returns_none():
    assert match_window(WINS, "safari") is None


def test_invalid_regex_raises():
    with pytest.raises(re.error):
        match_window(WINS, "(")
