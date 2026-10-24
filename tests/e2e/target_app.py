"""A throwaway window for the end-to-end test to type into, move, and resize."""

import AppKit
from PyObjCTools import AppHelper

TITLE = "control-mouse-e2e-target"


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

    # Edit menu so cmd+a / cmd+c / cmd+v work in the text field
    menubar = AppKit.NSMenu.alloc().init()
    app_item, edit_item = AppKit.NSMenuItem.alloc().init(), AppKit.NSMenuItem.alloc().init()
    menubar.addItem_(app_item)
    menubar.addItem_(edit_item)
    app_menu = AppKit.NSMenu.alloc().init()
    app_menu.addItemWithTitle_action_keyEquivalent_("Quit", "terminate:", "q")
    app_item.setSubmenu_(app_menu)
    edit = AppKit.NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in (("Select All", "selectAll:", "a"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v")):
        edit.addItemWithTitle_action_keyEquivalent_(title, action, key)
    edit_item.setSubmenu_(edit)
    app.setMainMenu_(menubar)

    style = (
        AppKit.NSWindowStyleMaskTitled
        | AppKit.NSWindowStyleMaskClosable
        | AppKit.NSWindowStyleMaskMiniaturizable
        | AppKit.NSWindowStyleMaskResizable
    )
    win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(200, 300, 500, 200), style, AppKit.NSBackingStoreBuffered, False
    )
    win.setTitle_(TITLE)
    field = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(20, 140, 460, 28))
    field.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
    win.contentView().addSubview_(field)
    win.makeKeyAndOrderFront_(None)
    win.makeFirstResponder_(field)
    app.activateIgnoringOtherApps_(True)
    AppHelper.runEventLoop(installInterrupt=True)


if __name__ == "__main__":
    main()
