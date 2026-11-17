"""The app window: the engine and the UI together, started with one command.

The window is a WebView2 view (the browser engine that ships with Windows),
so nothing the size of a whole browser is bundled with the app.
"""

import threading
from pathlib import Path

from . import APP_NAME, config, server

ICON = Path(__file__).resolve().parent / "assets" / "icon.ico"   # drawn by design/make_icon.py
# Tells Windows which taskbar button and pinned shortcut this window belongs to.
# The Start menu and desktop shortcuts carry the same ID (see shortcuts.py), so the
# running window and a pinned shortcut share one taskbar button with the mushroom icon.
APP_ID = "xburrito64.THEDownloader"

_WIDTH, _HEIGHT = 1120, 760
_MIN_WIDTH, _MIN_HEIGHT = 900, 620
_BACKGROUND = "#063420"  # shown for the moment before the UI has loaded; matches the screen colour


def _work_area(x: int, y: int) -> tuple[int, int, int, int] | None:
    """Left, top, width and height of the screen under a point, without the taskbar."""
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT), ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # 2 = the nearest screen
    info = MonitorInfo()
    info.size = ctypes.sizeof(MonitorInfo)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    work = info.work
    return work.left, work.top, work.right - work.left, work.bottom - work.top


class WindowApi:
    """The few things the UI cannot do itself, because they belong to Windows.

    The UI draws its own title bar, so the window buttons call back into here.
    Names without an underscore are callable from the UI; everything else is hidden from it.
    """

    def __init__(self) -> None:
        self._window = None
        self._maximized = False
        self._before = (0, 0, _WIDTH, _HEIGHT)

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> bool:
        """Fill the screen, or go back to the size before.

        Windows' own "maximise" makes a window without a frame cover the taskbar too,
        so the window is moved and sized to the free area of its screen instead.
        """
        window = self._window
        if self._maximized:
            x, y, width, height = self._before
            window.resize(width, height)
            window.move(x, y)
            self._maximized = False
            return False
        area = _work_area(window.x + window.width // 2, window.y + window.height // 2)
        if area is None:
            return False
        self._before = (window.x, window.y, window.width, window.height)
        window.move(area[0], area[1])
        window.resize(area[2], area[3])
        self._maximized = True
        return True

    def close(self) -> None:
        self._window.destroy()

    def resize(self, width, height) -> None:
        """Called while the corner grip is dragged. A window without a frame has no edges to drag."""
        if self._maximized or not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            return
        self._window.resize(max(_MIN_WIDTH, int(width)), max(_MIN_HEIGHT, int(height)))

    def choose_folder(self) -> str:
        """Windows' own folder picker. Returns "" when cancelled."""
        import webview

        picked = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return str(picked[0]) if picked else ""

    def choose_cookies_file(self) -> str:
        """Windows' own file picker, for a cookies.txt exported from a browser. Returns "" when cancelled."""
        import webview

        picked = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Cookies file (*.txt)", "All files (*.*)"))
        return str(picked[0]) if picked else ""


def run(debug: bool = False) -> None:
    import webview

    state = server.build_state()
    if state.ui_dir is None or not (state.ui_dir / "index.html").is_file():
        state.store.close()
        raise config.ConfigError(
            "The UI has not been built yet. Run these two commands in the ui folder: npm install, then npm run build.")

    sock = server.open_socket()
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    api_server = server.make_server(state)
    thread = threading.Thread(target=api_server.run, kwargs={"sockets": [sock]}, name="api", daemon=True)
    thread.start()

    api = WindowApi()
    # The token travels after the # sign, which the window never sends over the network or writes to a log.
    api._window = webview.create_window(
        APP_NAME, f"{address}/#token={state.token}", js_api=api,
        width=_WIDTH, height=_HEIGHT, min_size=(_MIN_WIDTH, _MIN_HEIGHT),
        frameless=True, easy_drag=False, background_color=_BACKGROUND, text_select=False,
    )
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass  # only the taskbar grouping is lost; the app works the same
    try:
        webview.start(debug=debug, icon=str(ICON) if ICON.is_file() else None)  # returns when the window is closed
    finally:
        server.stop(api_server, state)
        thread.join(8)
        state.store.close()


def main() -> None:
    """Entry point without a terminal window (see pyproject.toml)."""
    try:
        run()
    except Exception as exc:  # there is no terminal to print to, so show a message box instead
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(exc), APP_NAME, 0x10)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # what the Start menu and desktop shortcuts run: pythonw -m thedownloader.window
    main()
