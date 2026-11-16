"""The app window: the engine and the UI together, started with one command.

The window is a WebView2 view (the browser engine that ships with Windows),
so nothing the size of a whole browser is bundled with the app.
"""

import threading

from . import APP_NAME, config, server

_WIDTH, _HEIGHT = 1120, 760
_MIN_WIDTH, _MIN_HEIGHT = 900, 620
_BACKGROUND = "#063420"  # shown for the moment before the UI has loaded; matches the screen colour


class WindowApi:
    """The few things the UI cannot do itself, because they belong to Windows.

    The UI draws its own title bar, so the window buttons call back into here.
    Names without an underscore are callable from the UI; everything else is hidden from it.
    """

    def __init__(self) -> None:
        self._window = None
        self._maximized = False

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> bool:
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized
        return self._maximized

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
        webview.start(debug=debug)  # returns when the window is closed
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
