"""Run code on the AppKit main thread from MCP worker threads."""

import threading

from PyObjCTools import AppHelper


def call_on_main(fn, *args) -> None:
    """Schedule fn(*args) on the main thread without waiting."""
    AppHelper.callAfter(fn, *args)


def run_on_main(fn, timeout: float = 5.0):
    """Run fn() on the main thread and return its result."""
    if threading.current_thread() is threading.main_thread():
        return fn()

    box: dict = {}
    done = threading.Event()

    def wrapper():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = e
        finally:
            done.set()

    AppHelper.callAfter(wrapper)
    if not done.wait(timeout):
        raise TimeoutError("Main thread did not respond")
    if "error" in box:
        raise box["error"]
    return box.get("value")
