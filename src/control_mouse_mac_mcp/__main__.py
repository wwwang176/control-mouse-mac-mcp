"""Entry point.

AppKit must own the main thread (the overlays are NSWindows), so the MCP
stdio server runs on a background thread. When the client closes stdin the
server returns and the whole app terminates.
"""

import sys
import threading
import traceback

import AppKit
from PyObjCTools import AppHelper

from . import overlay, permissions
from .server import mcp


def _serve(app) -> None:
    try:
        mcp.run(transport="stdio")
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
    finally:
        AppHelper.callAfter(app.terminate_, None)


def main() -> None:
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)  # no Dock icon
    overlay.install()
    permissions.request_missing()
    threading.Thread(target=_serve, args=(app,), name="mcp-stdio", daemon=True).start()
    AppHelper.runEventLoop(installInterrupt=True)


if __name__ == "__main__":
    main()
