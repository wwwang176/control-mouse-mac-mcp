"""End-to-end test: start the server over stdio and drive a throwaway target window.

This really moves the mouse and types. It needs the Accessibility and Screen
Recording permissions for the terminal running it. Opt in with:

    E2E=1 .venv/bin/python -m pytest tests/e2e -v
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import base64
import tempfile
from io import BytesIO

import anyio
import pytest
from mcp import ClientSession
from PIL import Image
from mcp.client.stdio import StdioServerParameters, stdio_client

pytestmark = pytest.mark.skipif(not os.environ.get("E2E"), reason="set E2E=1 to run (moves the mouse and types)")

HERE = Path(__file__).parent
TARGET = "control-mouse-e2e-target"
EXPECTED_TOOLS = {
    "screenshot", "get_screen_info", "click", "scroll", "drag", "type_text", "press_key",
    "clipboard_read", "clipboard_write", "list_windows", "focus_window", "manage_window",
    "wait_for_change", "list_monitors",
}


@pytest.fixture(scope="module")
def target():
    proc = subprocess.Popen([sys.executable, str(HERE / "target_app.py")])
    time.sleep(1.5)
    yield
    proc.terminate()
    proc.wait(5)


def texts(result) -> list[str]:
    return [c.text for c in result.content if c.type == "text"]


def images(result) -> list:
    return [c for c in result.content if c.type == "image"]


def data(result):
    """Tool return value: structured content if present, else JSON from the text blocks."""
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    parsed = [json.loads(t) for t in texts(result)]
    return parsed[0] if len(parsed) == 1 else parsed


def overlay_green_ratio(img: Image.Image) -> float:
    """Fraction of pixels in the overlay text color (#00FF88)."""
    raw = img.convert("RGB").tobytes()
    px = zip(raw[0::3], raw[1::3], raw[2::3])
    return sum(1 for r, g, b in px if r < 90 and g > 200 and 100 < b < 190) / (len(raw) // 3)


def capture_like_remote_desktop(left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Capture from outside the server, the way screen sharing / remote desktop apps see the screen."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    subprocess.run(["screencapture", "-x", "-R", f"{left},{top},{right - left},{bottom - top}", path], check=True)
    img = Image.open(path)
    img.load()
    os.unlink(path)
    return img


def find_target(windows: list[dict]) -> dict | None:
    return next((w for w in windows if w["title"] == TARGET), None)


async def scenario():
    params = StdioServerParameters(command=sys.executable, args=["-m", "control_mouse_mac_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()

        async def call(name, **args):
            r = await s.call_tool(name, args)
            assert not r.is_error, f"{name} failed: {texts(r)}"
            return r

        tools = {t.name for t in (await s.list_tools()).tools}
        assert tools == EXPECTED_TOOLS

        info = data(await call("get_screen_info"))
        assert info["permissions"]["accessibility"] and info["permissions"]["screen_recording"], info
        assert data(await call("list_monitors"))

        shot = await call("screenshot")
        assert len(images(shot)) == 1 and "scale_x=" in texts(shot)[0]

        # overlay: visible to other capturers (remote desktop), but not in the server's own screenshots
        w, h = info["primary_width"], info["primary_height"]
        bottom_center = dict(left=w // 2 - 250, top=h - 190, right=w // 2 + 250, bottom=h - 100)
        await call("press_key", keys="shift")
        await anyio.sleep(0.3)
        assert overlay_green_ratio(capture_like_remote_desktop(**bottom_center)) > 0.01, "overlay not visible on screen"
        own = await call("screenshot", **bottom_center)
        own_img = Image.open(BytesIO(base64.b64decode(images(own)[0].data)))
        assert overlay_green_ratio(own_img) == 0, "overlay leaked into the server's screenshot"

        # window management
        await call("manage_window", title=TARGET, action="move", x=300, y=200, width=600, height=250)
        await anyio.sleep(0.3)
        win = find_target(data(await call("list_windows")))
        assert win is not None
        assert (abs(win["left"] - 300), abs(win["top"] - 200), abs(win["width"] - 600), abs(win["height"] - 250)) <= (2, 2, 2, 2), win

        assert "Focused" in texts(await call("focus_window", title=TARGET))[0]
        await anyio.sleep(0.5)

        # click into the text field (32pt below the content top, title bar about 28pt)
        r = await call("click", x=win["left"] + 100, y=win["top"] + 28 + 32 + 14, screenshot_after=True)
        assert len(images(r)) == 1

        # typing + shortcuts + clipboard
        text = "Hello 你好 🙂"
        await call("type_text", text=text)
        await call("press_key", keys="cmd+a")
        await call("press_key", keys="cmd+c")
        await anyio.sleep(0.2)
        assert texts(await call("clipboard_read"))[0] == text

        await call("clipboard_write", text="剪貼簿 test")
        assert texts(await call("clipboard_read"))[0] == "剪貼簿 test"

        bad = await s.call_tool("press_key", {"keys": "printscreen"})
        assert bad.is_error and "not available on macOS" in texts(bad)[0]

        # wait_for_change runs while another tool types into the watched region
        region = dict(left=win["left"], top=win["top"] + 28, right=win["right"], bottom=win["top"] + 28 + 80)
        results = {}

        async def watch():
            results["wait"] = await call("wait_for_change", timeout=5, threshold=0.001, **region)

        async with anyio.create_task_group() as tg:
            tg.start_soon(watch)
            await anyio.sleep(1.2)
            await call("type_text", text=" changed")
        assert texts(results["wait"])[0].startswith("Change detected"), texts(results["wait"])

        await call("scroll", x=win["left"] + 100, y=win["top"] + 150, direction="down", clicks=2)
        await call("drag", x1=win["left"] + 30, y1=win["top"] + 74, x2=win["left"] + 200, y2=win["top"] + 74)

        # minimize / restore / maximize
        await call("manage_window", title=TARGET, action="minimize")
        await anyio.sleep(1.0)
        assert find_target(data(await call("list_windows"))) is None
        await call("manage_window", title=TARGET, action="restore")
        await anyio.sleep(1.0)
        assert find_target(data(await call("list_windows"))) is not None

        await call("manage_window", title=TARGET, action="maximize")
        await anyio.sleep(0.5)
        win = find_target(data(await call("list_windows")))
        assert win["width"] >= info["primary_width"] - 10, win


def test_end_to_end(target):
    anyio.run(scenario)
