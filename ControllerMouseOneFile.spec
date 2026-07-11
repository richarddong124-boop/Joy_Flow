# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path.cwd()
APP_NAME = "Joy Flow"
BUILD_MODE = "onefile"

UI_FILES = [
    "controlleruisubzhCN.html",
    "controlleruisubdarkzhCN.html",
    "controlleruisub.html",
    "controlleruisubdark.html",
    "controller_ui.html",
    "controller_overlay.js",
]

datas = []
for name in UI_FILES + ["controller_mouse_config.json", "controller_mouse_logo.ico"]:
    file_path = ROOT / name
    if file_path.exists():
        datas.append((str(file_path), "."))

models_dir = ROOT / "models"
if models_dir.exists():
    datas.append((str(models_dir), "models"))

binaries = []
hiddenimports = [
    "voice_dictation",
    "whisper",
    "sounddevice",
    "numpy",
    "pyperclip",
    "pyautogui",
    "pygame",
    "pystray._win32",
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.mshtml",
    "uiautomation",
    "comtypes",
    "pythoncom",
    "pywintypes",
    "win32api",
    "win32clipboard",
    "win32com",
    "win32con",
    "win32gui",
    "win32process",
    "win32timezone",
    "tiktoken",
    "tiktoken_ext",
]

for package_name in ("webview", "whisper"):
    try:
        package_datas, package_bins, package_hidden = collect_all(package_name)
        datas += package_datas
        binaries += package_bins
        hiddenimports += package_hidden
    except Exception:
        pass

for package_name in ("tiktoken", "tiktoken_ext", "whisper"):
    try:
        hiddenimports += collect_submodules(package_name)
    except Exception:
        pass


a = Analysis(
    [str(ROOT / "controller_desktop_tray.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pygame.tests",
        "matplotlib",
        "IPython",
        "jedi",
        "pytest",
        "pydoc",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if BUILD_MODE == "onefile":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "controller_mouse_logo.ico") if (ROOT / "controller_mouse_logo.ico").exists() else None,
        version=str(ROOT / "joy_flow_version_info.txt"),
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "controller_mouse_logo.ico") if (ROOT / "controller_mouse_logo.ico").exists() else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME,
    )
