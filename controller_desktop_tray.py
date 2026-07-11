from __future__ import annotations

import ctypes
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from app_paths import CACHE_DIR, ensure_runtime_dirs

ERROR_ALREADY_EXISTS = 183
_SINGLE_INSTANCE_MUTEX = None

WINDOW = None
TRAY_ICON = None
APP_EXITING = False
APP = None
ENGINE = None
_BRIDGE_LOCK = threading.Lock()
_LAST_TRAY_STATUS = None

DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 960
WINDOW_EDGE_MARGIN = 24
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
SERVER_STARTUP_TIMEOUT = 0.35
SERVER_STARTUP_POLL_INTERVAL = 0.01
TRAY_STATUS_POLL_INTERVAL = 0.4
DESKTOP_SHORTCUT_NAME = "Joy Flow.lnk"


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def ensure_single_instance() -> bool:
    """Prevent multiple Joy Flow backend/window copies from stacking."""
    global _SINGLE_INSTANCE_MUTEX
    _SINGLE_INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(
        None,
        False,
        "Global\\ControllerMouseApp_SingleInstance",
    )
    return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def get_initial_window_bounds() -> tuple[int, int, int, int]:
    """Fit the launcher window inside the visible desktop work area."""
    rect = RECT()
    spi_get_work_area = 0x0030
    ok = ctypes.windll.user32.SystemParametersInfoW(spi_get_work_area, 0, ctypes.byref(rect), 0)
    if not ok:
        return 80, 80, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT

    work_width = max(640, rect.right - rect.left)
    work_height = max(480, rect.bottom - rect.top)

    max_width = max(640, work_width - (WINDOW_EDGE_MARGIN * 2))
    max_height = max(480, work_height - (WINDOW_EDGE_MARGIN * 2))

    width = min(DEFAULT_WINDOW_WIDTH, max_width)
    height = min(DEFAULT_WINDOW_HEIGHT, max_height)

    x = rect.left + max(WINDOW_EDGE_MARGIN, (work_width - width) // 2)
    y = rect.top + max(WINDOW_EDGE_MARGIN, (work_height - height) // 2)
    return x, y, width, height


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS))
    return get_base_dir()


def get_desktop_dir() -> Path | None:
    desktop = os.environ.get("USERPROFILE")
    if not desktop:
        return None
    return Path(desktop) / "Desktop"


def ensure_desktop_shortcut() -> None:
    """Create a desktop shortcut for onedir distributions so users do not separate the EXE from _internal."""
    if not getattr(sys, "frozen", False):
        return

    exe_path = Path(sys.executable)
    base_dir = exe_path.parent
    internal_dir = base_dir / "_internal"
    if not internal_dir.exists():
        return

    desktop_dir = get_desktop_dir()
    if not desktop_dir:
        return

    shortcut_path = desktop_dir / DESKTOP_SHORTCUT_NAME
    if shortcut_path.exists():
        return

    icon_path = base_dir / "controller_mouse_logo.ico"
    icon_location = str(icon_path if icon_path.exists() else exe_path)
    shortcut_path_ps = str(shortcut_path).replace("'", "''")
    exe_path_ps = str(exe_path).replace("'", "''")
    base_dir_ps = str(base_dir).replace("'", "''")
    icon_location_ps = icon_location.replace("'", "''")

    script = (
        "$WScriptShell = New-Object -ComObject WScript.Shell\n"
        f"$Shortcut = $WScriptShell.CreateShortcut('{shortcut_path_ps}')\n"
        f"$Shortcut.TargetPath = '{exe_path_ps}'\n"
        f"$Shortcut.WorkingDirectory = '{base_dir_ps}'\n"
        f"$Shortcut.IconLocation = '{icon_location_ps}'\n"
        "$Shortcut.Save()\n"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


BASE_DIR = get_base_dir()
RESOURCE_DIR = get_resource_dir()
os.chdir(BASE_DIR)


# BUNDLED_WHISPER_CACHE_PATCH
ensure_runtime_dirs()
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_DIR))
os.environ.setdefault("TORCH_HOME", str(CACHE_DIR / "torch"))

logging.getLogger("werkzeug").disabled = True


def ensure_bridge_loaded():
    global APP, ENGINE
    if APP is not None and ENGINE is not None:
        return APP, ENGINE

    with _BRIDGE_LOCK:
        if APP is None or ENGINE is None:
            from controller_bridge import app as bridge_app, engine as bridge_engine

            APP = bridge_app
            ENGINE = bridge_engine

    return APP, ENGINE


class WindowApi:
    """Bridge used by the custom HTML titlebar buttons."""

    def minimize(self):
        if WINDOW:
            WINDOW.minimize()

    def close(self):
        hide_window()

    def quit(self):
        quit_app()


def create_tray_image():
    from PIL import Image, ImageDraw, ImageOps

    status = current_tray_status()
    palette = {
        "running": (34, 197, 94, 255),
        "paused": (245, 158, 11, 255),
        "stopped": (239, 68, 68, 255),
    }
    accent_color = palette.get(status, palette["stopped"])

    logo_path = os.path.join(RESOURCE_DIR, "controller_mouse_logo.ico")
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo = ImageOps.contain(logo, (64, 64), method=Image.Resampling.LANCZOS)
            alpha = logo.getchannel("A")

            # Use the real app logo silhouette, tinted by runtime status.
            colored_logo = Image.new("RGBA", logo.size, accent_color)
            colored_logo.putalpha(alpha)

            canvas = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
            offset = ((64 - colored_logo.width) // 2, (64 - colored_logo.height) // 2)
            canvas.paste(colored_logo, offset, colored_logo)
            return canvas
        except Exception:
            pass

    image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=14, fill=accent_color)
    draw.ellipse((20, 20, 44, 44), fill=(255, 255, 255, 255))
    return image


def current_tray_status() -> str:
    try:
        _app, engine = ensure_bridge_loaded()
    except Exception:
        return "stopped"
    if not getattr(engine, "running", False):
        return "stopped"
    if getattr(engine, "paused", False):
        return "paused"
    return "running"


def refresh_tray_icon(force: bool = False) -> None:
    global _LAST_TRAY_STATUS
    if TRAY_ICON is None:
        return
    status = current_tray_status()
    if not force and status == _LAST_TRAY_STATUS:
        return
    _LAST_TRAY_STATUS = status
    try:
        TRAY_ICON.icon = create_tray_image()
        TRAY_ICON.title = f"Joy Flow ({status})"
        if hasattr(TRAY_ICON, "update_menu"):
            TRAY_ICON.update_menu()
        if hasattr(TRAY_ICON, "update_icon"):
            TRAY_ICON.update_icon()
    except Exception:
        pass


def tray_status_loop() -> None:
    while not APP_EXITING:
        refresh_tray_icon()
        time.sleep(TRAY_STATUS_POLL_INTERVAL)


def run_server():
    app, _engine = ensure_bridge_loaded()
    app.run(
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=False,
        use_reloader=False,
    )


def autostart_engine() -> None:
    try:
        _app, engine = ensure_bridge_loaded()
        engine.start()
    except Exception as exc:
        print(f"Auto-start failed: {exc!r}")


def show_window(icon=None, item=None):
    if WINDOW:
        WINDOW.show()


def hide_window(icon=None, item=None):
    if WINDOW:
        WINDOW.hide()


def quit_app(icon=None, item=None):
    global APP_EXITING
    APP_EXITING = True

    if TRAY_ICON:
        TRAY_ICON.stop()

    if WINDOW:
        WINDOW.destroy()


def setup_tray():
    global TRAY_ICON
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem("Show Joy Flow", show_window, default=True),
        pystray.MenuItem("Hide to Tray", hide_window),
        pystray.MenuItem("Quit", quit_app),
    )

    TRAY_ICON = pystray.Icon(
        "ControllerMouse",
        create_tray_image(),
        "Joy Flow",
        menu,
    )
    threading.Thread(target=tray_status_loop, daemon=True).start()
    TRAY_ICON.run()


def on_window_closing():
    if not APP_EXITING:
        hide_window()
        return False
    return True


def wait_for_local_server(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.time() + max(0.0, timeout_seconds)
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.05):
                return True
        except OSError:
            time.sleep(SERVER_STARTUP_POLL_INTERVAL)
    return False


def main():
    global WINDOW

    if not ensure_single_instance():
        print("Joy Flow is already running. Exiting duplicate instance.")
        return

    ensure_desktop_shortcut()

    threading.Thread(target=autostart_engine, daemon=True).start()
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=setup_tray, daemon=True).start()
    wait_for_local_server(SERVER_HOST, SERVER_PORT, SERVER_STARTUP_TIMEOUT)

    api = WindowApi()
    window_x, window_y, window_width, window_height = get_initial_window_bounds()
    import webview

    WINDOW = webview.create_window(
        title="Joy Flow",
        url=f"http://{SERVER_HOST}:{SERVER_PORT}",
        x=window_x,
        y=window_y,
        width=window_width,
        height=window_height,
        resizable=True,
        frameless=True,
        easy_drag=False,
        js_api=api,
    )

    WINDOW.events.closing += on_window_closing
    webview.start()


if __name__ == "__main__":
    main()
