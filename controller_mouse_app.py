r"""
Joy Flow v4.4 LT Hold Fix Build

Fast v2.3 movement engine preserved.
Polished white UI added.
Minimal combo patch: LB+B sensitivity down. LB+X and X middle click removed.
Original movement logic preserved.
LT hold-to-talk Whisper dictation improved for Chinese with UI speech mode switching. RT sends Enter. Y sends Backspace.
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from tkinter import Tk, StringVar, DoubleVar, BOTH, X, LEFT, END, messagebox
from tkinter import ttk

import pygame
import pyautogui

from app_paths import (
    CACHE_DIR,
    CONFIG_PATH,
    DEBUG_LOG_PATH,
    RESOURCE_DIR,
    RUNTIME_DIR,
    ensure_runtime_dirs,
    migrate_legacy_config,
)

VOICE_DICTATION_IMPORT_ERROR = None
try:
    from voice_dictation import WhisperDictation
except Exception as exc:
    WhisperDictation = None
    VOICE_DICTATION_IMPORT_ERROR = repr(exc)

try:
    from snap_assist_windows import find_global_snap_target
except Exception as _snap_import_error:
    find_global_snap_target = None


def resolve_model_dir() -> Path:
    candidates = [
        RESOURCE_DIR / "models",
        RUNTIME_DIR / "models",
        Path.cwd().resolve() / "models",
        CACHE_DIR / "models",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate
    return (CACHE_DIR / "models").resolve()


APP_DIR = RUNTIME_DIR
LOG_PATH = DEBUG_LOG_PATH
MODEL_DIR = resolve_model_dir()

# ---------- FAST V2.3 CORE DEFAULTS ----------
DEFAULT_DEADZONE = 0.10
DEFAULT_SENSITIVITY_STAGES = [30, 45, 60, 80, 105]
DEFAULT_START_STAGE_INDEX = 2
DEFAULT_ACCEL_POWER = 1.35
DEFAULT_TICK_RATE = 240

DEFAULT_SCROLL_AMOUNT = 12
DEFAULT_SCROLL_REPEAT_DELAY = 0.025
DEFAULT_FINE_MOVE_PIXELS = 2
DEFAULT_FINE_MOVE_REPEAT_DELAY = 0.035

DEFAULT_CLICK_COOLDOWN = 0.12
DEFAULT_PAUSE_COOLDOWN = 0.35
DEFAULT_SENSITIVITY_CYCLE_COOLDOWN = 0.35
DEFAULT_ENTER_COOLDOWN = 0.20
DEFAULT_TRIGGER_THRESHOLD = 0.65
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_DICTATION_MIN_SECONDS = 0.45
DEFAULT_DICTATION_RELEASE_TAIL_SECONDS = 0.00
DEFAULT_WHISPER_LANGUAGE = "zh"
DEFAULT_WHISPER_INITIAL_PROMPT = None
# -------------------------------------------


def default_binding_labels() -> dict[str, str]:
    return {
        "move_cursor": "Left Stick",
        "fine_adjust": "D-pad",
        "dictation": "LT Hold",
        "enter": "RT",
        "sensitivity_up": "LB + A",
        "sensitivity_down": "LB + B",
        "backspace": "Y",
    }


BUTTON_BINDING_LABELS = {
    "a": "A",
    "b": "B",
    "x": "X",
    "y": "Y",
    "lb": "LB",
    "rb": "RB",
    "back": "Back/View",
    "lt": "LT Hold",
    "rt": "RT",
    "lb+a": "LB + A",
    "lb+b": "LB + B",
    "lb+x": "LB + X",
    "lb+y": "LB + Y",
    "left_stick": "Left Stick",
    "dpad": "D-pad",
}


def binding_choice_map() -> dict[str, list[dict[str, str]]]:
    return {
        "move_cursor": [{"value": "left_stick", "label": BUTTON_BINDING_LABELS["left_stick"]}],
        "fine_adjust": [{"value": "dpad", "label": BUTTON_BINDING_LABELS["dpad"]}],
        "dictation": [
            {"value": "lt", "label": BUTTON_BINDING_LABELS["lt"]},
            {"value": "rt", "label": "RT Hold"},
            {"value": "lb", "label": BUTTON_BINDING_LABELS["lb"]},
            {"value": "rb", "label": BUTTON_BINDING_LABELS["rb"]},
        ],
        "enter": [
            {"value": "rt", "label": BUTTON_BINDING_LABELS["rt"]},
            {"value": "a", "label": BUTTON_BINDING_LABELS["a"]},
            {"value": "b", "label": BUTTON_BINDING_LABELS["b"]},
            {"value": "x", "label": BUTTON_BINDING_LABELS["x"]},
            {"value": "y", "label": BUTTON_BINDING_LABELS["y"]},
        ],
        "sensitivity_up": [
            {"value": "lb+a", "label": BUTTON_BINDING_LABELS["lb+a"]},
            {"value": "lb+x", "label": BUTTON_BINDING_LABELS["lb+x"]},
            {"value": "lb+y", "label": BUTTON_BINDING_LABELS["lb+y"]},
        ],
        "sensitivity_down": [
            {"value": "lb+b", "label": BUTTON_BINDING_LABELS["lb+b"]},
            {"value": "lb+x", "label": BUTTON_BINDING_LABELS["lb+x"]},
            {"value": "lb+y", "label": BUTTON_BINDING_LABELS["lb+y"]},
        ],
        "backspace": [
            {"value": "y", "label": BUTTON_BINDING_LABELS["y"]},
            {"value": "x", "label": BUTTON_BINDING_LABELS["x"]},
            {"value": "b", "label": BUTTON_BINDING_LABELS["b"]},
            {"value": "a", "label": BUTTON_BINDING_LABELS["a"]},
        ],
    }


def normalize_binding_config(raw: dict[str, str] | None) -> dict[str, str]:
    defaults = {
        "move_cursor": "left_stick",
        "fine_adjust": "dpad",
        "dictation": "lt",
        "enter": "rt",
        "sensitivity_up": "lb+a",
        "sensitivity_down": "lb+b",
        "backspace": "y",
    }
    allowed = {key: {item["value"] for item in values} for key, values in binding_choice_map().items()}
    for key, value in (raw or {}).items():
        key = str(key or "").strip()
        value = str(value or "").strip().lower()
        if key in defaults and value in allowed.get(key, set()):
            defaults[key] = value
    return defaults

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0
try:
    pyautogui.MINIMUM_DURATION = 0
    pyautogui.MINIMUM_SLEEP = 0
except Exception:
    pass

BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LB = 4
BUTTON_RB = 5
BUTTON_BACK = 6


@dataclass
class AppConfig:
    deadzone: float = DEFAULT_DEADZONE
    sensitivity_stages: list[float] | None = None
    stage_index: int = DEFAULT_START_STAGE_INDEX
    accel_power: float = DEFAULT_ACCEL_POWER
    tick_rate: int = DEFAULT_TICK_RATE
    scroll_amount: int = DEFAULT_SCROLL_AMOUNT
    scroll_repeat_delay: float = DEFAULT_SCROLL_REPEAT_DELAY
    fine_move_pixels: int = DEFAULT_FINE_MOVE_PIXELS
    fine_move_repeat_delay: float = DEFAULT_FINE_MOVE_REPEAT_DELAY
    click_cooldown: float = DEFAULT_CLICK_COOLDOWN
    pause_cooldown: float = DEFAULT_PAUSE_COOLDOWN
    sensitivity_cycle_cooldown: float = DEFAULT_SENSITIVITY_CYCLE_COOLDOWN
    enter_cooldown: float = DEFAULT_ENTER_COOLDOWN
    trigger_threshold: float = DEFAULT_TRIGGER_THRESHOLD
    whisper_model: str = DEFAULT_WHISPER_MODEL
    whisper_language: str | None = DEFAULT_WHISPER_LANGUAGE
    whisper_initial_prompt: str | None = DEFAULT_WHISPER_INITIAL_PROMPT
    dictation_min_seconds: float = DEFAULT_DICTATION_MIN_SECONDS
    dictation_release_tail_seconds: float = DEFAULT_DICTATION_RELEASE_TAIL_SECONDS
    lt_axis_candidates: list[str] | None = None
    rt_axis_candidates: list[str] | None = None
    speech_profile: str = "zh-small"
    ui_language: str = "zh"
    ui_theme: str = "light"
    debug_logging: bool = False
    custom_bindings: dict[str, str] | None = None
    control_bindings: dict[str, str] | None = None

    def __post_init__(self):
        if self.sensitivity_stages is None:
            self.sensitivity_stages = list(DEFAULT_SENSITIVITY_STAGES)
        self.stage_index = int(max(0, min(len(self.sensitivity_stages) - 1, self.stage_index)))
        if self.lt_axis_candidates is None:
            # Most Xbox-style pads: LT=axis 4. Some older Windows mappings use shared axis 2.
            self.lt_axis_candidates = ["4:+"]
        if self.rt_axis_candidates is None:
            # Most Xbox-style pads: RT=axis 5. Some older Windows mappings use shared axis 2.
            self.rt_axis_candidates = ["5:+"]
        self.speech_profile = str(self.speech_profile or "zh-small")
        self.ui_language = "en" if str(self.ui_language or "").lower().startswith("en") else "zh"
        self.ui_theme = "dark" if str(self.ui_theme or "").lower() == "dark" else "light"
        merged_bindings = default_binding_labels()
        for key, value in (self.custom_bindings or {}).items():
            key = str(key or "").strip()
            if key in merged_bindings and str(value or "").strip():
                merged_bindings[key] = str(value).strip()
        self.custom_bindings = merged_bindings
        self.control_bindings = normalize_binding_config(self.control_bindings)

    @property
    def max_speed(self) -> float:
        idx = max(0, min(len(self.sensitivity_stages) - 1, int(self.stage_index)))
        return float(self.sensitivity_stages[idx])



def _dedupe_axis_candidates(candidates: list[str] | None) -> list[str]:
    seen = set()
    result = []
    for spec in candidates or []:
        spec = str(spec).strip()
        if not spec or spec in seen:
            continue
        seen.add(spec)
        result.append(spec)
    return result


def _sanitize_trigger_candidates(cfg: AppConfig, raw: dict | None = None) -> None:
    """
    v4.4 fix: do not treat both directions of the same trigger axis as LT.

    The user's log showed axis 4 firing as both 4:+ and 4:-. That makes the
    released/rest side of the analog trigger start a new dictation. For the
    current Xbox 360 mapping, LT is axis 4 positive and RT is axis 5 positive.
    """
    raw = raw or {}
    lt = _dedupe_axis_candidates(cfg.lt_axis_candidates)
    rt = _dedupe_axis_candidates(cfg.rt_axis_candidates)

    # If the old broad candidate list is present, narrow it to the stable Xbox mapping.
    if "4:+" in lt and "4:-" in lt:
        cfg.lt_axis_candidates = ["4:+"]
    elif lt:
        cfg.lt_axis_candidates = lt
    else:
        cfg.lt_axis_candidates = ["4:+"]

    if "5:+" in rt:
        cfg.rt_axis_candidates = ["5:+"]
    elif rt:
        cfg.rt_axis_candidates = rt
    else:
        cfg.rt_axis_candidates = ["5:+"]

    # Never persist the Chinese instruction prompt. It can be hallucinated and pasted.
    if cfg.whisper_initial_prompt and any(
        phrase in str(cfg.whisper_initial_prompt)
        for phrase in ("请输出简体中文", "请输入简体中文", "普通话中文语音转写", "不要翻译成英文")
    ):
        cfg.whisper_initial_prompt = None

    # Remove the old tail delay so recording stops immediately on release.
    if float(getattr(cfg, "dictation_release_tail_seconds", 0.0) or 0.0) > 0.0:
        cfg.dictation_release_tail_seconds = 0.0

    # Avoid 0.29s/0.34s accidental clips being transcribed after trigger bounce.
    cfg.dictation_min_seconds = max(0.45, float(getattr(cfg, "dictation_min_seconds", 0.45) or 0.45))

def load_config() -> AppConfig:
    ensure_runtime_dirs()
    migrate_legacy_config()
    if not CONFIG_PATH.exists():
        bundled_config_path = RESOURCE_DIR / "controller_mouse_config.json"
        if bundled_config_path.exists():
            try:
                raw = json.loads(bundled_config_path.read_text(encoding="utf-8"))
                allowed = set(AppConfig.__dataclass_fields__.keys())
                cleaned = {key: value for key, value in raw.items() if key in allowed}
                cfg = AppConfig(**cleaned)
                _sanitize_trigger_candidates(cfg, raw)
                if "speech_profile" in raw:
                    setattr(cfg, "speech_profile", raw["speech_profile"])
                save_config(cfg)
                return cfg
            except Exception:
                pass

        cfg = AppConfig()
        save_config(cfg)
        return cfg

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        allowed = set(AppConfig.__dataclass_fields__.keys())
        cleaned = {key: value for key, value in raw.items() if key in allowed}
        cfg = AppConfig(**cleaned)

        # Migrate older configs without losing the user's sensitivity settings.
        if "whisper_model" not in raw:
            cfg.whisper_model = DEFAULT_WHISPER_MODEL
        if "whisper_language" not in raw:
            cfg.whisper_language = DEFAULT_WHISPER_LANGUAGE
        if "whisper_initial_prompt" not in raw:
            cfg.whisper_initial_prompt = DEFAULT_WHISPER_INITIAL_PROMPT
        if "dictation_release_tail_seconds" not in raw:
            cfg.dictation_release_tail_seconds = DEFAULT_DICTATION_RELEASE_TAIL_SECONDS

        _sanitize_trigger_candidates(cfg, raw)
        save_config(cfg)
        return cfg

    except Exception:
        cfg = AppConfig()
        _sanitize_trigger_candidates(cfg, {})
        save_config(cfg)
        return cfg


def save_config(config: AppConfig) -> None:
    try:
        ensure_runtime_dirs()
        CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    except Exception:
        # Do not crash the movement engine if config saving is blocked.
        pass


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def apply_deadzone(value: float, deadzone: float) -> float:
    if abs(value) < deadzone:
        return 0.0
    sign = 1 if value > 0 else -1
    scaled = (abs(value) - deadzone) / (1 - deadzone)
    return sign * clamp(scaled, 0.0, 1.0)


def curved_speed(value: float, max_speed: float, accel_power: float) -> float:
    if value == 0:
        return 0.0
    return math.copysign(abs(value) ** accel_power, value) * max_speed


def get_button(controller, button_id: int) -> bool:
    return controller.get_numbuttons() > button_id and bool(controller.get_button(button_id))


def get_axis_safe(controller, axis_id: int) -> float:
    if controller.get_numaxes() <= axis_id:
        return 0.0
    return controller.get_axis(axis_id)


def get_hat_safe(controller, hat_id: int = 0) -> tuple[int, int]:
    if controller.get_numhats() <= hat_id:
        return (0, 0)
    return controller.get_hat(hat_id)


def parse_axis_candidate(spec: str) -> tuple[int, int] | None:
    """Parse strings like "4:+" or "2:-" into (axis_id, direction)."""
    try:
        axis_text, direction_text = str(spec).split(":", 1)
        axis_id = int(axis_text.strip())
        direction = -1 if direction_text.strip().startswith("-") else 1
        return axis_id, direction
    except Exception:
        return None


def trigger_pressed(controller, candidates: list[str], baselines: dict[int, float], threshold: float) -> bool:
    """
    Return True when a trigger candidate moves far enough away from its resting baseline.

    This supports both separate trigger axes, where rest may be -1 and press is +1,
    and shared trigger axes, where LT/RT may move the same axis in opposite directions.
    """
    for spec in candidates:
        parsed = parse_axis_candidate(spec)
        if parsed is None:
            continue

        axis_id, direction = parsed
        if controller.get_numaxes() <= axis_id:
            continue

        raw = get_axis_safe(controller, axis_id)
        baseline = baselines.get(axis_id, 0.0)
        moved = (raw - baseline) * direction

        if moved >= threshold:
            return True

    return False


def button_name_pressed(controller, name: str) -> bool:
    mapping = {
        "a": BUTTON_A,
        "b": BUTTON_B,
        "x": BUTTON_X,
        "y": BUTTON_Y,
        "lb": BUTTON_LB,
        "rb": BUTTON_RB,
        "back": BUTTON_BACK,
    }
    button_id = mapping.get(str(name or "").lower())
    if button_id is None:
        return False
    return get_button(controller, button_id)


class ControllerMouseEngine:
    def __init__(self, config: AppConfig, ui_callback=None):
        self.config = config
        self.ui_callback = ui_callback
        self.running = False
        self.paused = False
        self.thread = None
        self.controller = None
        self.controller_name = "None"
        self.snap_assist = False
        self.axis_baselines: dict[int, float] = {}
        self._waiting_for_controller = False
        self._last_connect_probe = 0.0
        self._connect_probe_interval = 2.5
        self._notify_throttle: dict[str, float] = {}
        self._log_initialized = False
        self._debug_logging_enabled = bool(
            str(os.environ.get("CONTROLLER_MOUSE_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}
            or getattr(self.config, "debug_logging", False)
        )
        self.dictation = (
            WhisperDictation(
                self._notify,
                model_name=self.config.whisper_model,
                download_root=MODEL_DIR,
                sample_rate=16000,
                min_seconds=self.config.dictation_min_seconds,
                release_tail_seconds=self.config.dictation_release_tail_seconds,
                language=self.config.whisper_language,
                initial_prompt=self.config.whisper_initial_prompt,
            )
            if WhisperDictation is not None
            else None
        )

    def start(self):
        if self.running:
            self._notify("Already running.")
            return
        self.running = True
        self.paused = False
        self.thread = threading.Thread(target=self._main_loop, daemon=True)
        self.thread.start()
        self._notify("Engine started.")
        self._notify(f"Runtime dir: {APP_DIR}")
        self._notify(f"Resource dir: {RESOURCE_DIR}")
        self._notify(f"Whisper model dir: {MODEL_DIR}")
        self._notify(f"Debug log path: {LOG_PATH}")
        self._notify(f"Config path: {CONFIG_PATH}")
        if WhisperDictation is None:
            reason = f" Import error: {VOICE_DICTATION_IMPORT_ERROR}" if VOICE_DICTATION_IMPORT_ERROR else ""
            self._notify("Whisper dictation unavailable." + reason)

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.paused = False
        self._notify("Engine stopping...")

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        self._notify("Paused." if self.paused else "Resumed.")

    def _notify(self, msg: str):
        text = str(msg)
        try:
            ensure_runtime_dirs()
            self._log_initialized = True
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with LOG_PATH.open("a", encoding="utf-8") as log_file:
                level = "DEBUG" if self._debug_logging_enabled else "INFO"
                log_file.write(f"[{stamp}] [{level}] {text}\n")
                log_file.flush()
                if os.environ.get("CONTROLLER_MOUSE_SYNC_LOG") == "1":
                    try:
                        os.fsync(log_file.fileno())
                    except Exception:
                        pass
        except Exception:
            pass

        if self.ui_callback:
            try:
                self.ui_callback(text)
            except Exception:
                pass

    def _notify_limited(self, key: str, msg: str, interval_seconds: float) -> bool:
        now = time.time()
        last = self._notify_throttle.get(key, 0.0)
        if now - last < interval_seconds:
            return False
        self._notify_throttle[key] = now
        self._notify(msg)
        return True

    def get_voice_state(self) -> dict:
        if self.dictation is None:
            return {"available": False, "recording": False, "transcribing": False}
        state = self.dictation.state()
        state["available"] = True
        state["config_model"] = self.config.whisper_model
        state["config_language"] = self.config.whisper_language or "auto"
        return state

    def _recreate_dictation(self) -> None:
        if self.dictation is not None:
            try:
                self.dictation.cancel()
            except Exception:
                pass

        self.dictation = (
            WhisperDictation(
                self._notify,
                model_name=self.config.whisper_model,
                download_root=MODEL_DIR,
                sample_rate=16000,
                min_seconds=self.config.dictation_min_seconds,
                release_tail_seconds=self.config.dictation_release_tail_seconds,
                language=self.config.whisper_language,
                initial_prompt=self.config.whisper_initial_prompt,
            )
            if WhisperDictation is not None
            else None
        )

    def set_speech_settings(
        self,
        *,
        model: str,
        language: str | None,
        initial_prompt: str | None,
        release_tail_seconds: float | None = None,
        profile: str | None = None,
    ) -> dict:
        self.config.whisper_model = str(model or "tiny")
        self.config.whisper_language = language or None
        self.config.whisper_initial_prompt = initial_prompt or None
        if profile:
            setattr(self.config, "speech_profile", str(profile))
        if release_tail_seconds is not None:
            self.config.dictation_release_tail_seconds = float(max(0.0, release_tail_seconds))
        save_config(self.config)
        self._recreate_dictation()
        if self.dictation is not None and hasattr(self.dictation, "warmup_async"):
            try:
                self.dictation.warmup_async()
            except Exception as exc:
                self._notify(f"Whisper warmup restart error: {exc!r}")

        state = self.get_voice_state()
        self._notify(
            f"Speech mode updated: model={self.config.whisper_model}, "
            f"language={self.config.whisper_language or 'auto'}"
        )
        return state

    def _apply_real_global_snap_assist(self, now: float, last_action: dict) -> None:
        """
        Real global snap assist.

        This does NOT use the HTML app's three snap targets.
        It scans Windows UI around the current cursor and snaps to real nearby
        buttons, links, checkboxes, text fields, and I-beam/hand cursor areas.
        """
        if find_global_snap_target is None:
            if now - last_action.get("global_snap_import_notice", 0) > 3.0:
                self._notify("Global Snap Assist not loaded. Run: pip install uiautomation comtypes")
                last_action["global_snap_import_notice"] = now
            return

        # UI Automation is heavier than normal movement. Keep it responsive but not constant.
        if now - last_action.get("global_snap_scan", 0) < 0.075:
            return
        last_action["global_snap_scan"] = now

        try:
            target = find_global_snap_target(radius=130)
        except Exception as exc:
            if now - last_action.get("global_snap_error_notice", 0) > 3.0:
                self._notify(f"Global Snap error: {exc}")
                last_action["global_snap_error_notice"] = now
            return

        if not target:
            return

        try:
            x = int(target["x"])
            y = int(target["y"])
            distance = float(target.get("distance", 999))
            label = str(target.get("label", "target"))
            kind = str(target.get("kind", "target"))
        except Exception:
            return

        # Do not move when already correctly placed.
        if distance > 4:
            pyautogui.moveTo(x, y, duration=0, _pause=False)

        if now - last_action.get("global_snap_notice", 0) > 0.8:
            self._notify(f"Global snap → {label} [{kind}]")
            last_action["global_snap_notice"] = now

    def _connect_controller_if_available(self) -> bool:
        """Try to connect joystick 0. Returns True when connected."""
        self._last_connect_probe = time.time()
        try:
            pygame.joystick.quit()
            pygame.joystick.init()

            if pygame.joystick.get_count() == 0:
                return False

            self.controller = pygame.joystick.Joystick(0)
            self.controller.init()
            self.controller_name = self.controller.get_name()
            self._waiting_for_controller = False
            self._connect_probe_interval = 1.0

            self._notify(f"Controller detected: {self.controller_name}")
            self.axis_baselines = {
                i: get_axis_safe(self.controller, i)
                for i in range(self.controller.get_numaxes())
            }

            self._notify(f"Buttons: {self.controller.get_numbuttons()} | Axes: {self.controller.get_numaxes()}")
            self._notify(f"Starting sensitivity stage: {self.config.stage_index + 1}/5, speed={self.config.max_speed:.0f}")
            self._notify(f"LT candidates: {self.config.lt_axis_candidates} | RT candidates: {self.config.rt_axis_candidates}")
            self._notify(f"Speech model={self.config.whisper_model} | language={self.config.whisper_language or 'auto'}")
            if self.config.whisper_model != "tiny":
                self._notify(f"Speech model {self.config.whisper_model} may take longer to load on first use.")
            self._notify("LT hold = Whisper dictation | RT = Enter")
            if self.dictation is not None and hasattr(self.dictation, "warmup_async"):
                try:
                    self.dictation.warmup_async()
                except Exception as exc:
                    self._notify(f"Whisper warmup start error: {exc!r}")
            return True

        except Exception as exc:
            self.controller = None
            self.controller_name = "None"
            self._connect_probe_interval = min(10.0, max(2.5, self._connect_probe_interval * 1.5))
            self._notify_limited("controller_connect_error", f"Controller connect error: {exc}", 20.0)
            return False

    def _handle_controller_removed(self, reason: str = "Controller disconnected or asleep.") -> None:
        """Clear the joystick object immediately so stale axis values cannot keep moving the mouse."""
        try:
            if self.controller:
                self.controller.quit()
        except Exception:
            pass

        self.controller = None
        self.controller_name = "None"
        self.axis_baselines = {}
        if self.dictation is not None:
            self.dictation.cancel()
        if not self._waiting_for_controller:
            self._notify(f"{reason} Waiting for reconnect...")
        self._waiting_for_controller = True
        self._connect_probe_interval = 1.0

    def _controller_is_attached(self) -> bool:
        """Return False when pygame/Windows says the controller is gone or sleeping."""
        if self.controller is None:
            return False

        try:
            if hasattr(self.controller, "get_attached") and not self.controller.get_attached():
                return False

            # Touch a cheap property so pygame.error is raised quickly on stale devices.
            self.controller.get_numaxes()
            return True

        except pygame.error:
            return False
        except Exception:
            return False

    def _process_joystick_hotplug_events(self) -> None:
        """Handle controller sleep/disconnect/reconnect events without preserving stale axis values."""
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEREMOVED:
                if self.controller is None:
                    continue

                try:
                    same_device = event.instance_id == self.controller.get_instance_id()
                except Exception:
                    same_device = True

                if same_device:
                    self._handle_controller_removed("Controller disconnected/asleep.")

            elif event.type == pygame.JOYDEVICEADDED:
                if self.controller is None:
                    self._connect_controller_if_available()

    def _main_loop(self):
        pygame.init()
        pygame.joystick.init()

        last_action = {}
        last_scroll_time = 0.0
        last_fine_move_time = 0.0
        last_controller_wait_notice = 0.0
        lt_was_pressed = False
        rt_was_pressed = False
        clock = pygame.time.Clock()

        while self.running:
            pygame.event.pump()
            self._process_joystick_hotplug_events()
            now = time.time()

            if self.controller is None:
                if not self._waiting_for_controller:
                    self._notify("Waiting for controller... plug it in or turn it on.")
                    self._waiting_for_controller = True
                    last_controller_wait_notice = now
                elif now - last_controller_wait_notice > 120.0:
                    self._notify("Still waiting for controller...")
                    last_controller_wait_notice = now

                if now - self._last_connect_probe >= self._connect_probe_interval:
                    self._connect_controller_if_available()
                clock.tick(5)
                continue

            if not self._controller_is_attached():
                self._handle_controller_removed("Controller disconnected/asleep.")
                clock.tick(5)
                continue

            try:
                bindings = normalize_binding_config(getattr(self.config, "control_bindings", None))
                lb_pressed = get_button(self.controller, BUTTON_LB)
                a_pressed = get_button(self.controller, BUTTON_A)
                b_pressed = get_button(self.controller, BUTTON_B)
                lt_pressed = trigger_pressed(
                    self.controller,
                    self.config.lt_axis_candidates or [],
                    self.axis_baselines,
                    float(self.config.trigger_threshold),
                )
                rt_pressed = trigger_pressed(
                    self.controller,
                    self.config.rt_axis_candidates or [],
                    self.axis_baselines,
                    float(self.config.trigger_threshold),
                )

                combo_states = {
                    "lb+a": lb_pressed and a_pressed,
                    "lb+b": lb_pressed and b_pressed,
                    "lb+x": lb_pressed and get_button(self.controller, BUTTON_X),
                    "lb+y": lb_pressed and get_button(self.controller, BUTTON_Y),
                }
                sensitivity_up_pressed = combo_states.get(bindings["sensitivity_up"], False)
                sensitivity_down_pressed = combo_states.get(bindings["sensitivity_down"], False)

                if get_button(self.controller, BUTTON_BACK):
                    self._notify("Back/View pressed. Stopping.")
                    break

                if sensitivity_up_pressed:
                    if now - last_action.get("cycle_sensitivity", 0) > self.config.sensitivity_cycle_cooldown:
                        self.config.stage_index = (self.config.stage_index + 1) % len(self.config.sensitivity_stages)
                        save_config(self.config)
                        self._notify(f"[LB+A] Sensitivity stage: {self.config.stage_index + 1}/5, speed={self.config.max_speed:.0f}")
                        last_action["cycle_sensitivity"] = now

                if sensitivity_down_pressed:
                    if now - last_action.get("cycle_sensitivity_down", 0) > self.config.sensitivity_cycle_cooldown:
                        self.config.stage_index = (self.config.stage_index - 1) % len(self.config.sensitivity_stages)
                        save_config(self.config)
                        self._notify(f"[LB+B] Sensitivity stage: {self.config.stage_index + 1}/5, speed={self.config.max_speed:.0f}")
                        last_action["cycle_sensitivity_down"] = now

                if not self.paused:
                    dictation_binding = bindings["dictation"]
                    dictation_pressed = (
                        lt_pressed if dictation_binding == "lt"
                        else rt_pressed if dictation_binding == "rt"
                        else button_name_pressed(self.controller, dictation_binding)
                    )
                    if dictation_pressed and not lt_was_pressed:
                        axis_snapshot = {
                            i: round(get_axis_safe(self.controller, i), 4)
                            for i in range(self.controller.get_numaxes())
                        }
                        self._notify(f"[LT] Pressed | axes={axis_snapshot} | baselines={self.axis_baselines}")
                        if self.dictation is None:
                            self._notify("Whisper dictation not loaded. Run: pip install -U openai-whisper sounddevice numpy pyperclip")
                        else:
                            self.dictation.start()
                    elif not dictation_pressed and lt_was_pressed:
                        axis_snapshot = {
                            i: round(get_axis_safe(self.controller, i), 4)
                            for i in range(self.controller.get_numaxes())
                        }
                        self._notify(f"[LT] Released | axes={axis_snapshot}")
                        if self.dictation is not None:
                            self.dictation.stop_and_transcribe()

                    enter_binding = bindings["enter"]
                    enter_pressed = (
                        rt_pressed if enter_binding == "rt"
                        else lt_pressed if enter_binding == "lt"
                        else button_name_pressed(self.controller, enter_binding)
                    )
                    if enter_pressed and not rt_was_pressed:
                        if now - last_action.get("enter", 0) > self.config.enter_cooldown:
                            pyautogui.press("enter", _pause=False)
                            self._notify("[RT] Enter")
                            last_action["enter"] = now

                    x_axis = apply_deadzone(get_axis_safe(self.controller, 0), self.config.deadzone)
                    y_axis = apply_deadzone(get_axis_safe(self.controller, 1), self.config.deadzone)

                    dx = curved_speed(x_axis, self.config.max_speed, self.config.accel_power)
                    dy = curved_speed(y_axis, self.config.max_speed, self.config.accel_power)

                    if dx or dy:
                        pyautogui.moveRel(dx, dy, duration=0, _pause=False)

                    def click_binding(binding_value: str, name: str, action):
                        if combo_states.get(binding_value, False):
                            return
                        if binding_value in ("lt", "rt", "lb+a", "lb+b", "lb+x", "lb+y"):
                            return
                        if button_name_pressed(self.controller, binding_value):
                            t = time.time()
                            if t - last_action.get(name, 0) > self.config.click_cooldown:
                                action()
                                last_action[name] = t

                    click_binding("a", "left", lambda: pyautogui.click(button="left", _pause=False))
                    click_binding("b", "right", lambda: pyautogui.click(button="right", _pause=False))
                    click_binding(bindings["backspace"], "delete", lambda: (pyautogui.press("backspace", _pause=False), self._notify("[Backspace]")))

                    if now - last_fine_move_time > self.config.fine_move_repeat_delay:
                        hat_x, hat_y = get_hat_safe(self.controller, 0)
                        if hat_x or hat_y:
                            fine = int(max(1, self.config.fine_move_pixels))
                            pyautogui.moveRel(hat_x * fine, -hat_y * fine, duration=0, _pause=False)
                            last_fine_move_time = now

                    if now - last_scroll_time > self.config.scroll_repeat_delay:
                        scroll_delta = 0
                        if lb_pressed and not (sensitivity_up_pressed or sensitivity_down_pressed):
                            scroll_delta -= int(self.config.scroll_amount)
                        if get_button(self.controller, BUTTON_RB):
                            scroll_delta += int(self.config.scroll_amount)
                        if scroll_delta:
                            pyautogui.scroll(scroll_delta, _pause=False)
                            last_scroll_time = now

                    if self.snap_assist:
                        self._apply_real_global_snap_assist(now, last_action)

                lt_was_pressed = dictation_pressed if 'dictation_pressed' in locals() else lt_pressed
                rt_was_pressed = enter_pressed if 'enter_pressed' in locals() else rt_pressed

            except pygame.error:
                self._handle_controller_removed("Controller disconnected/asleep.")
                continue

            except Exception as exc:
                self._notify(f"Error: {exc}")

            clock.tick(int(self.config.tick_rate))

        self.running = False
        self.paused = False
        self.controller = None
        self.axis_baselines = {}
        if self.dictation is not None:
            self.dictation.cancel()
        self._notify("Engine stopped.")
        try:
            pygame.quit()
        except Exception:
            pass


class ControllerMouseGUI:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Joy Flow v4.4 LT Hold Fix Build")
        self.root.geometry("820x720")
        self.root.configure(bg="#f5f6f8")

        self._setup_styles()

        self.config = load_config()
        self.engine = ControllerMouseEngine(self.config, self.on_engine_message)

        self.status = StringVar(value="Stopped")
        self.controller_status = StringVar(value="Controller: unknown")
        self.stage_text = StringVar(value=self._stage_label())

        self.deadzone_var = DoubleVar(value=self.config.deadzone)
        self.accel_var = DoubleVar(value=self.config.accel_power)
        self.tick_rate_var = DoubleVar(value=float(self.config.tick_rate))
        self.scroll_amount_var = DoubleVar(value=float(self.config.scroll_amount))
        self.fine_move_var = DoubleVar(value=float(self.config.fine_move_pixels))

        self.ui_buttons = []
        self.snap_to_buttons = True
        self.focus_index = 0

        self._build_ui()
        self._focus_button(0)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        self.colors = {
            "bg": "#f5f6f8",
            "card": "#ffffff",
            "text": "#111827",
            "muted": "#6b7280",
            "accent": "#22c55e",
            "accent_dark": "#16a34a",
        }

        style.configure(".", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Card.TFrame", background=self.colors["bg"])
        style.configure("Card.TLabelframe", background=self.colors["card"], borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 10, "bold"))
        style.configure("AppTitle.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 20, "bold"))
        style.configure("Muted.TLabel", background=self.colors["bg"], foreground=self.colors["muted"], font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 11))
        style.configure("Stage.TLabel", background=self.colors["card"], foreground=self.colors["accent_dark"], font=("Segoe UI", 12, "bold"))
        style.configure("Primary.TButton", background=self.colors["accent"], foreground="white", borderwidth=0)
        style.map("Primary.TButton",
                  background=[("active", self.colors["accent_dark"]), ("pressed", self.colors["accent_dark"])],
                  foreground=[("active", "white"), ("pressed", "white")])
        style.configure("Soft.TButton", background="#f8fafc", foreground=self.colors["text"], borderwidth=1, relief="solid")
        style.map("Soft.TButton",
                  background=[("active", "#eef2f7"), ("pressed", "#e5e7eb")])
        style.configure("Section.TLabel", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 11, "bold"))
        style.configure("SliderValue.TLabel", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 10))

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=18, style="Card.TFrame")
        main.pack(fill=BOTH, expand=True)

        header = ttk.Frame(main, style="Card.TFrame")
        header.pack(fill=X, pady=(0, 12))
        ttk.Label(header, text="Joy Flow", style="AppTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Polished white edition • fast v2.3 engine preserved • LT Whisper dictation • RT Enter",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        status_frame = ttk.LabelFrame(main, text="Status", style="Card.TLabelframe", padding=14)
        status_frame.pack(fill=X, pady=6)
        ttk.Label(status_frame, textvariable=self.status, style="Status.TLabel").pack(anchor="w", pady=2)
        ttk.Label(status_frame, textvariable=self.controller_status, style="Status.TLabel").pack(anchor="w", pady=2)
        ttk.Label(status_frame, textvariable=self.stage_text, style="Stage.TLabel").pack(anchor="w", pady=2)

        buttons = ttk.LabelFrame(main, text="Quick Actions", style="Card.TLabelframe", padding=14)
        buttons.pack(fill=X, pady=10)

        self._add_big_button(buttons, "Start", self.start_clicked, 0, 0, primary=True)
        self._add_big_button(buttons, "Stop", self.stop_clicked, 0, 1)
        self._add_big_button(buttons, "Pause / Resume", self.pause_clicked, 0, 2)

        self._add_big_button(buttons, "Sensitivity Cycle", self.sensitivity_cycle, 1, 0, primary=True)
        self._add_big_button(buttons, "Sensitivity -", self.sensitivity_down, 1, 1)
        self._add_big_button(buttons, "Sensitivity +", self.sensitivity_up, 1, 2)

        self._add_big_button(buttons, "Save", self.save_clicked, 2, 0)
        self._add_big_button(buttons, "Snap Mouse To Focus", self.snap_mouse_to_focus, 2, 1)
        self._add_big_button(buttons, "Toggle Snap", self.toggle_snap, 2, 2)

        for col in range(3):
            buttons.columnconfigure(col, weight=1)

        settings = ttk.LabelFrame(main, text="Fine Tuning", style="Card.TLabelframe", padding=14)
        settings.pack(fill=X, pady=10)
        self._slider(settings, "Deadzone", self.deadzone_var, 0.02, 0.35, self.on_slider_change)
        self._slider(settings, "Acceleration Power", self.accel_var, 1.00, 2.00, self.on_slider_change)
        self._slider(settings, "Tick Rate", self.tick_rate_var, 60, 360, self.on_slider_change)
        self._slider(settings, "Scroll Amount", self.scroll_amount_var, 1, 30, self.on_slider_change)
        self._slider(settings, "D-Pad Fine Move Pixels", self.fine_move_var, 1, 10, self.on_slider_change)

        hint = ttk.Frame(main, style="Card.TFrame")
        hint.pack(fill=X, pady=(2, 10))
        ttk.Label(
            hint,
            text="Recommended: Deadzone 0.08–0.10 • Acceleration 1.25–1.35 • Tick Rate 240 • Hold LT to dictate, release LT to paste, tap RT for Enter",
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w")

        log_frame = ttk.LabelFrame(main, text="Activity Log", style="Card.TLabelframe", padding=10)
        log_frame.pack(fill=BOTH, expand=True, pady=6)
        self.log = ttk.Treeview(log_frame, columns=("msg",), show="headings", height=10)
        self.log.heading("msg", text="Message")
        self.log.column("msg", width=740)
        self.log.pack(fill=BOTH, expand=True)

        self.root.bind("<Left>", lambda event: self._focus_button(self.focus_index - 1))
        self.root.bind("<Right>", lambda event: self._focus_button(self.focus_index + 1))
        self.root.bind("<Up>", lambda event: self._focus_button(self.focus_index - 3))
        self.root.bind("<Down>", lambda event: self._focus_button(self.focus_index + 3))
        self.root.bind("<Return>", lambda event: self._activate_focused_button())
        self.root.bind("<space>", lambda event: self._activate_focused_button())

        self._log("Ready.")

    def _add_big_button(self, parent, text, command, row, col, primary=False):
        style = "Primary.TButton" if primary else "Soft.TButton"
        button = ttk.Button(parent, text=text, command=command, style=style)
        button.grid(row=row, column=col, padx=8, pady=8, sticky="nsew", ipady=12)
        button.bind("<FocusIn>", lambda event, b=button: self._snap_to_widget(b))
        button.bind("<Enter>", lambda event, b=button: b.focus_set())
        self.ui_buttons.append(button)
        return button

    def _focus_button(self, index: int):
        if not self.ui_buttons:
            return
        self.focus_index = index % len(self.ui_buttons)
        button = self.ui_buttons[self.focus_index]
        button.focus_set()
        self._snap_to_widget(button)

    def _snap_to_widget(self, widget):
        if not self.snap_to_buttons:
            return
        try:
            self.root.update_idletasks()
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() // 2
            pyautogui.moveTo(x, y, duration=0, _pause=False)
        except Exception:
            pass

    def snap_mouse_to_focus(self):
        if self.ui_buttons:
            self._focus_button(self.focus_index)
            self._log("Mouse snapped to focused button.")

    def toggle_snap(self):
        self.snap_to_buttons = not self.snap_to_buttons
        self._log("Snap to buttons: ON" if self.snap_to_buttons else "Snap to buttons: OFF")

    def _slider(self, parent, label, variable, from_, to, command):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, padx=4, pady=8)

        label_var = StringVar(value=f"{label}: {variable.get():.2f}")
        ttk.Label(row, text=label, style="Section.TLabel", width=22).pack(side=LEFT)
        ttk.Scale(
            row,
            from_=from_,
            to=to,
            variable=variable,
            command=lambda _: command(label_var, label, variable),
        ).pack(side=LEFT, fill=X, expand=True, padx=12)
        ttk.Label(row, textvariable=label_var, style="SliderValue.TLabel", width=18).pack(side=LEFT)

    def _activate_focused_button(self):
        if self.ui_buttons:
            try:
                self.ui_buttons[self.focus_index].invoke()
            except Exception:
                pass

    def on_slider_change(self, label_var, label, variable):
        if label in {"Tick Rate", "Scroll Amount", "D-Pad Fine Move Pixels"}:
            label_var.set(f"{label}: {variable.get():.0f}")
        else:
            label_var.set(f"{label}: {variable.get():.2f}")
        self._apply_vars_to_config()

    def start_clicked(self):
        self._apply_vars_to_config()
        save_config(self.config)
        self.engine.start()
        self.status.set("Running")

    def stop_clicked(self):
        self.engine.stop()

    def pause_clicked(self):
        if not self.engine.running:
            messagebox.showinfo("Not running", "Start the app first.")
            return
        self.engine.toggle_pause()

    def sensitivity_cycle(self):
        self.config.stage_index = (self.config.stage_index + 1) % len(self.config.sensitivity_stages)
        self._stage_update_save()

    def sensitivity_down(self):
        self.config.stage_index = (self.config.stage_index - 1) % len(self.config.sensitivity_stages)
        self._stage_update_save()

    def sensitivity_up(self):
        self.config.stage_index = (self.config.stage_index + 1) % len(self.config.sensitivity_stages)
        self._stage_update_save()

    def _stage_update_save(self):
        save_config(self.config)
        self.stage_text.set(self._stage_label())
        self._log(f"Sensitivity stage: {self.config.stage_index + 1}/5, speed={self.config.max_speed:.0f}")

    def save_clicked(self):
        self._apply_vars_to_config()
        save_config(self.config)
        self.stage_text.set(self._stage_label())
        self._log("Settings saved.")

    def _apply_vars_to_config(self):
        self.config.deadzone = float(self.deadzone_var.get())
        self.config.accel_power = float(self.accel_var.get())
        self.config.tick_rate = int(self.tick_rate_var.get())
        self.config.scroll_amount = int(self.scroll_amount_var.get())
        self.config.fine_move_pixels = int(self.fine_move_var.get())

    def _stage_label(self) -> str:
        return f"Sensitivity stage: {self.config.stage_index + 1}/5, speed={self.config.max_speed:.0f}"

    def on_engine_message(self, msg: str):
        self.root.after(0, lambda: self._handle_engine_message(msg))

    def _handle_engine_message(self, msg: str):
        if "Controller detected" in msg:
            self.controller_status.set(msg)
        elif "No controller found" in msg:
            self.controller_status.set("Controller: not detected")
        elif "Controller disconnected" in msg:
            self.controller_status.set("Controller: disconnected")

        if msg == "Paused.":
            self.status.set("Paused")
        elif msg == "Resumed.":
            self.status.set("Running")
        elif msg == "Engine stopped.":
            self.status.set("Stopped")
        elif msg == "Engine started.":
            self.status.set("Running")

        if "Sensitivity stage" in msg:
            self.stage_text.set(self._stage_label())

        self._log(msg)

    def _log(self, msg: str):
        self.log.insert("", END, values=(msg,))
        items = self.log.get_children()
        if len(items) > 80:
            self.log.delete(items[0])
        latest = self.log.get_children()
        if latest:
            self.log.see(latest[-1])

    def on_close(self):
        self.engine.stop()
        save_config(self.config)
        self.root.destroy()


def main():
    root = Tk()
    app = ControllerMouseGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
