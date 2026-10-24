"""Plain-text clipboard via NSPasteboard."""

from AppKit import NSPasteboard, NSPasteboardTypeString


def read() -> str:
    return str(NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString) or "")


def write(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    if not pb.setString_forType_(text, NSPasteboardTypeString):
        raise RuntimeError("Could not write to the clipboard")
