"""Accessibility and Screen Recording permission checks.

macOS grants these permissions to the "responsible" app that launched the
server (the terminal, Claude Desktop, ...), not to Python itself.
"""

import functools
import os
import subprocess
import sys

import ApplicationServices as AS
import Quartz
from AppKit import NSBundle
from mcp.server.mcpserver.exceptions import ToolError

_SETTINGS = "System Settings > Privacy & Security"


def has_accessibility() -> bool:
    return bool(AS.AXIsProcessTrusted())


def has_screen_recording() -> bool:
    return bool(Quartz.CGPreflightScreenCaptureAccess())


@functools.lru_cache(maxsize=1)
def host_app_name() -> str:
    """Name of the closest ancestor process that lives in an .app bundle."""
    pid = os.getpid()
    for _ in range(30):
        out = subprocess.run(
            ["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
        if not out:
            break
        ppid, path = out.split(None, 1)
        if ".app/" in path:
            bundle_path = path[: path.index(".app/") + len(".app")]
            bundle = NSBundle.bundleWithPath_(bundle_path)
            name = bundle.objectForInfoDictionaryKey_("CFBundleName") if bundle else None
            return str(name or os.path.basename(bundle_path)[: -len(".app")])
        pid = int(ppid)
        if pid <= 1:
            break
    return "the app that launches this server (your terminal or MCP client)"


def _missing_message(permission: str) -> str:
    app = host_app_name()
    return (
        f"{permission} permission is missing. Open {_SETTINGS} > {permission}, "
        f"enable \"{app}\", then quit and reopen \"{app}\" (the permission only applies after a restart)."
    )


def require_accessibility() -> None:
    if not has_accessibility():
        raise ToolError(_missing_message("Accessibility"))


def require_screen_recording() -> None:
    if not has_screen_recording():
        raise ToolError(_missing_message("Screen Recording"))


def status() -> dict:
    return {
        "accessibility": has_accessibility(),
        "screen_recording": has_screen_recording(),
        "host_app": host_app_name(),
    }


def request_missing() -> None:
    """Show the system prompts for missing permissions and log to stderr (stdout is the MCP channel)."""
    if not has_accessibility():
        AS.AXIsProcessTrustedWithOptions({AS.kAXTrustedCheckOptionPrompt: True})
        print(_missing_message("Accessibility"), file=sys.stderr)
    if not has_screen_recording():
        Quartz.CGRequestScreenCaptureAccess()
        print(_missing_message("Screen Recording"), file=sys.stderr)
