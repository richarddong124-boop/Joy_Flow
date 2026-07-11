from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "ControllerMouse"
CONFIG_FILE_NAME = "config.json"
DEBUG_LOG_FILE_NAME = "debug.log"


def _windows_dir(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name)
    if value:
        return Path(value).expanduser().resolve()
    return fallback.resolve()


def get_runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


RUNTIME_DIR = get_runtime_dir()
RESOURCE_DIR = get_resource_dir()
APPDATA_ROOT = _windows_dir("APPDATA", Path.home() / "AppData" / "Roaming")
LOCALAPPDATA_ROOT = _windows_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local")
APP_DATA_DIR = (APPDATA_ROOT / APP_NAME).resolve()
LOCAL_DATA_DIR = (LOCALAPPDATA_ROOT / APP_NAME).resolve()
LOG_DIR = (LOCAL_DATA_DIR / "logs").resolve()
CACHE_DIR = (LOCAL_DATA_DIR / "cache").resolve()
CONFIG_PATH = (APP_DATA_DIR / CONFIG_FILE_NAME).resolve()
DEBUG_LOG_PATH = (LOG_DIR / DEBUG_LOG_FILE_NAME).resolve()


def ensure_runtime_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def legacy_config_candidates() -> list[Path]:
    candidates = [
        RUNTIME_DIR / "controller_mouse_config.json",
        RUNTIME_DIR / CONFIG_FILE_NAME,
    ]
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def migrate_legacy_config() -> Path | None:
    ensure_runtime_dirs()
    for legacy_path in legacy_config_candidates():
        if not legacy_path.exists() or legacy_path == CONFIG_PATH:
            continue
        try:
            if not CONFIG_PATH.exists():
                shutil.copy2(legacy_path, CONFIG_PATH)
                return legacy_path
            if legacy_path.stat().st_mtime > CONFIG_PATH.stat().st_mtime:
                shutil.copy2(legacy_path, CONFIG_PATH)
                return legacy_path
        except Exception:
            continue
    return None
