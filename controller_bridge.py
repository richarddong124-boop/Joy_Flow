from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file, redirect
from flask_cors import CORS

try:
    from controller_mouse_app import (
        ControllerMouseEngine,
        load_config,
        save_config,
        _sanitize_trigger_candidates,
        default_binding_labels,
        binding_choice_map,
        normalize_binding_config,
    )
except ImportError:
    from controller_mouse_app import ControllerMouseEngine, load_config
    def save_config(_config):
        return None
    def _sanitize_trigger_candidates(_config, _raw=None):
        return None
    def default_binding_labels():
        return {
            "move_cursor": "Left Stick",
            "fine_adjust": "D-pad",
            "dictation": "LT Hold",
            "enter": "RT",
            "sensitivity_up": "LB + A",
            "sensitivity_down": "LB + B",
            "backspace": "Y",
        }
    def binding_choice_map():
        return {}
    def normalize_binding_config(raw=None):
        return raw or {}


def candidate_resource_dirs() -> list[Path]:
    dirs: list[Path] = []

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        dirs.append(Path(sys._MEIPASS))

    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)

    dirs.append(Path(__file__).resolve().parent)
    dirs.append(Path(os.getcwd()).resolve())

    # Preserve order, remove duplicates.
    seen: set[Path] = set()
    unique: list[Path] = []
    for folder in dirs:
        folder = folder.resolve()
        if folder not in seen:
            seen.add(folder)
            unique.append(folder)
    return unique


UI_FILES = {
    "zh": "controlleruisubzhCN.html",          # default Chinese page
    "zh-light": "controlleruisubzhCN.html",
    "zh-dark": "controlleruisubdarkzhCN.html",
    "en": "controlleruisub.html",
    "en-light": "controlleruisub.html",
    "en-dark": "controlleruisubdark.html",
    "legacy": "controller_ui.html",
}


def find_named_ui_file(filename: str) -> Path | None:
    for folder in candidate_resource_dirs():
        ui_file = folder / filename
        if ui_file.exists():
            return ui_file
    return None


def find_named_resource_file(filename: str) -> Path | None:
    if "/" in filename or "\\" in filename:
        return None
    for folder in candidate_resource_dirs():
        candidate = folder / filename
        if candidate.exists():
            return candidate
    return None


def find_ui_file(name: str = "zh") -> Path | None:
    filename = UI_FILES.get(name, UI_FILES["zh"])
    found = find_named_ui_file(filename)
    if found:
        return found
    # Fallback for older builds that only packaged controller_ui.html.
    return find_named_ui_file("controller_ui.html")


app = Flask(__name__)
CORS(app)

config = load_config()
engine = ControllerMouseEngine(config, print)
SPEECH_LOADING_STATE: dict[str, Any] = {
    "active": False,
    "target": None,
    "phase": None,
}
SPEECH_LOADING_LOCK = threading.RLock()


SPEECH_PROFILES: dict[str, dict[str, Any]] = {
    "zh-small": {
        "id": "zh-small",
        "label": "Stable Chinese Input",
        "label_zh": "中文输入 (稳)",
        "model": "small",
        "language": "zh",
        "initial_prompt": None,
    },
    "en-small": {
        "id": "en-small",
        "label": "Stable English Input",
        "label_zh": "英文输入 (稳)",
        "model": "small",
        "language": "en",
        "initial_prompt": None,
    },
    "zh-tiny": {
        "id": "zh-tiny",
        "label": "Lightning CN Input",
        "label_zh": "中文输入 (快)",
        "model": "tiny",
        "language": "zh",
        "initial_prompt": None,
    },
    "auto-tiny": {
        "id": "auto-tiny",
        "label": "Auto Lightning Input",
        "label_zh": "自动识别 (快)",
        "model": "tiny",
        "language": None,
        "initial_prompt": None,
    },
}


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def config_json_path() -> Path:
    # Works with your newer Whisper build and old fallback builds.
    try:
        import controller_mouse_app as cma
        path = getattr(cma, "CONFIG_PATH", None)
        if path:
            return Path(path)
    except Exception:
        pass
    return app_dir() / "controller_mouse_config.json"


def update_config_json(profile: dict[str, Any]) -> None:
    path = config_json_path()
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["speech_profile"] = profile["id"]
    data["whisper_model"] = profile["model"]
    data["whisper_language"] = profile["language"]
    data["whisper_initial_prompt"] = profile.get("initial_prompt")

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def current_speech_profile_id() -> str:
    raw = getattr(config, "speech_profile", None)
    if raw in SPEECH_PROFILES:
        return raw

    model = getattr(config, "whisper_model", None)
    language = getattr(config, "whisper_language", None)
    for profile_id, profile in SPEECH_PROFILES.items():
        if profile["model"] == model and profile["language"] == language:
            return profile_id

    # JSON fallback in case config dataclass did not expose dynamic attrs.
    path = config_json_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("speech_profile") in SPEECH_PROFILES:
                return data["speech_profile"]
        except Exception:
            pass

    return "auto-tiny"


def current_ui_language() -> str:
    value = str(getattr(config, "ui_language", "zh") or "zh").lower()
    return "en" if value.startswith("en") else "zh"


def current_ui_theme() -> str:
    value = str(getattr(config, "ui_theme", "light") or "light").lower()
    return "dark" if value == "dark" else "light"


def current_ui_route() -> str:
    language = current_ui_language()
    theme = current_ui_theme()
    if language == "en":
        return "/ui/en-dark" if theme == "dark" else "/ui/en"
    return "/ui/zh-dark" if theme == "dark" else "/ui/zh"


def update_speech_loading_state() -> dict[str, Any]:
    voice_state: dict[str, Any] = {}
    if hasattr(engine, "get_voice_state"):
        try:
            voice_state = engine.get_voice_state() or {}
        except Exception:
            voice_state = {}

    with SPEECH_LOADING_LOCK:
        state = dict(SPEECH_LOADING_STATE)
        if state.get("active"):
            target = state.get("target")
            loading = bool(voice_state.get("loading"))
            ready = bool(voice_state.get("ready"))
            current_model = voice_state.get("model")
            if not loading and ready and target in SPEECH_PROFILES:
                expected_model = SPEECH_PROFILES[target]["model"]
                if current_model == expected_model:
                    SPEECH_LOADING_STATE["active"] = False
                    SPEECH_LOADING_STATE["phase"] = "ready"
        return dict(SPEECH_LOADING_STATE)


def get_voice_state() -> dict[str, Any]:
    if hasattr(engine, "get_voice_state"):
        try:
            return engine.get_voice_state() or {}
        except Exception:
            return {}
    return {}


def profile_matches_voice_state(profile: dict[str, Any], voice_state: dict[str, Any]) -> bool:
    voice_model = voice_state.get("model")
    voice_language = voice_state.get("language")
    profile_language = profile["language"] or "auto"
    if voice_language in (None, ""):
        voice_language = "auto"
    return voice_model == profile["model"] and voice_language == profile_language


def apply_speech_profile(profile_id: str) -> dict[str, Any]:
    if profile_id not in SPEECH_PROFILES:
        raise ValueError(f"Unknown speech profile: {profile_id}")

    profile = SPEECH_PROFILES[profile_id]

    # Update the shared config object used by the engine.
    setattr(config, "speech_profile", profile_id)
    setattr(config, "whisper_model", profile["model"])
    setattr(config, "whisper_language", profile["language"])
    setattr(config, "whisper_initial_prompt", profile.get("initial_prompt"))

    # Recreate the live dictation object when the engine exposes the newer API.
    set_speech_settings = getattr(engine, "set_speech_settings", None)
    if callable(set_speech_settings):
        try:
            set_speech_settings(
                model=profile["model"],
                language=profile["language"],
                initial_prompt=profile.get("initial_prompt"),
                release_tail_seconds=getattr(config, "dictation_release_tail_seconds", 0.0),
                profile=profile_id,
            )
        except Exception:
            pass
    else:
        for method_name in ("set_speech_mode", "set_speech_profile", "configure_speech", "set_voice_config"):
            method = getattr(engine, method_name, None)
            if callable(method):
                try:
                    method(
                        model=profile["model"],
                        language=profile["language"],
                        initial_prompt=profile.get("initial_prompt"),
                        profile=profile_id,
                    )
                    break
                except TypeError:
                    try:
                        method(profile_id)
                        break
                    except Exception:
                        pass
                except Exception:
                    pass

    # Update dictation object directly for builds where the engine exposes it.
    dictation = getattr(engine, "dictation", None)
    if dictation is not None:
        previous_model_name = getattr(dictation, "model_name", None) or getattr(dictation, "model", None)
        for attr, value in (
            ("model_name", profile["model"]),
            ("model", profile["model"]),
            ("language", profile["language"]),
            ("initial_prompt", profile.get("initial_prompt")),
        ):
            try:
                setattr(dictation, attr, value)
            except Exception:
                pass
        if previous_model_name != profile["model"]:
            try:
                dictation._model = None
            except Exception:
                pass

    try:
        save_config(config)
    except Exception:
        pass
    update_config_json(profile)

    return profile


def speech_config_payload() -> dict[str, Any]:
    current = current_speech_profile_id()
    voice_state = get_voice_state()
    if not voice_state and hasattr(engine, "get_voice_state"):
        try:
            engine.get_voice_state()
        except Exception as exc:
            voice_state = {"error": str(exc)}

    loading_state = update_speech_loading_state()

    return {
        "ok": True,
        "current": current,
        "profiles": list(SPEECH_PROFILES.values()),
        "model": getattr(config, "whisper_model", None),
        "language": getattr(config, "whisper_language", None),
        "loading": loading_state,
        "voice": voice_state,
    }


def bindings_payload() -> dict[str, Any]:
    sensitivity_stages = list(getattr(config, "sensitivity_stages", []) or [])
    stage_index = int(getattr(config, "stage_index", 0) or 0)
    stage_count = len(sensitivity_stages)
    current_speed = None
    if 0 <= stage_index < stage_count:
        current_speed = sensitivity_stages[stage_index]

    configured = normalize_binding_config(getattr(config, "control_bindings", None))
    choices = binding_choice_map()
    bindings = {}
    for key, options in choices.items():
        current_value = configured.get(key)
        label = current_value
        for option in options:
            if option["value"] == current_value:
                label = option["label"]
                break
        bindings[key] = label

    return {
        "ok": True,
        "controller": getattr(engine, "controller_name", None),
        "bindings": bindings,
        "binding_values": configured,
        "binding_options": choices,
        "config": {
            "deadzone": float(getattr(config, "deadzone", 0.1) or 0.1),
            "trigger_threshold": float(getattr(config, "trigger_threshold", 0.65) or 0.65),
            "fine_move_pixels": int(getattr(config, "fine_move_pixels", 2) or 2),
            "scroll_amount": int(getattr(config, "scroll_amount", 12) or 12),
            "accel_power": float(getattr(config, "accel_power", 1.35) or 1.35),
            "tick_rate": int(getattr(config, "tick_rate", 240) or 240),
            "scroll_repeat_delay": float(getattr(config, "scroll_repeat_delay", 0.025) or 0.025),
            "fine_move_repeat_delay": float(getattr(config, "fine_move_repeat_delay", 0.035) or 0.035),
            "click_cooldown": float(getattr(config, "click_cooldown", 0.12) or 0.12),
            "pause_cooldown": float(getattr(config, "pause_cooldown", 0.35) or 0.35),
            "sensitivity_cycle_cooldown": float(getattr(config, "sensitivity_cycle_cooldown", 0.35) or 0.35),
            "enter_cooldown": float(getattr(config, "enter_cooldown", 0.2) or 0.2),
            "dictation_min_seconds": float(getattr(config, "dictation_min_seconds", 0.45) or 0.45),
            "stage_index": stage_index,
            "stage_count": stage_count,
            "current_speed": current_speed,
            "sensitivity_stages": sensitivity_stages,
            "lt_axis_candidates": list(getattr(config, "lt_axis_candidates", []) or []),
            "rt_axis_candidates": list(getattr(config, "rt_axis_candidates", []) or []),
            "speech_profile": current_speech_profile_id(),
            "ui_language": current_ui_language(),
            "ui_theme": current_ui_theme(),
            "control_bindings": configured,
        },
        "speech_profiles": list(SPEECH_PROFILES.values()),
    }


def _parse_axis_candidates(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _parse_sensitivity_stages(raw: Any, fallback: list[float]) -> list[float]:
    if isinstance(raw, list):
        values = raw
    else:
        text = str(raw or "").strip()
        values = text.replace(";", ",").split(",") if text else []
    parsed: list[float] = []
    for item in values:
        try:
            value = float(item)
        except Exception:
            continue
        if value <= 0:
            continue
        parsed.append(value)
    return parsed or list(fallback)


@app.route("/")
def home():
    return redirect(current_ui_route(), code=302)


@app.route("/ui/<name>")
def ui_page(name: str):
    ui_file = find_ui_file(name)
    if ui_file is None:
        return jsonify({"ok": False, "error": f"Unknown or missing UI page: {name}"}), 404
    return send_file(ui_file)


@app.route("/assets/<filename>")
def asset_file(filename: str):
    asset = find_named_resource_file(filename)
    if asset is None:
        return jsonify({"ok": False, "error": f"Missing asset: {filename}"}), 404
    return send_file(asset)


@app.route("/health")
def health():
    ui_file = find_ui_file("zh")
    return jsonify({
        "ok": True,
        "running": bool(engine.running),
        "paused": bool(engine.paused),
        "controller": engine.controller_name,
        "ui_file": str(ui_file) if ui_file else None,
        "snap": engine.get_snap_state() if hasattr(engine, "get_snap_state") else None,
        "speech_profile": current_speech_profile_id(),
        "voice": engine.get_voice_state() if hasattr(engine, "get_voice_state") else None,
    })


@app.route("/speech-mode")
def speech_mode():
    return jsonify(speech_config_payload())


@app.route("/bindings")
def bindings():
    return jsonify(bindings_payload())


@app.route("/bindings", methods=["POST"])
def update_bindings():
    data = request.get_json(silent=True) or {}

    if "deadzone" in data:
        config.deadzone = max(0.0, min(0.5, float(data["deadzone"])))
    if "trigger_threshold" in data:
        config.trigger_threshold = max(0.1, min(0.99, float(data["trigger_threshold"])))
    if "fine_move_pixels" in data:
        config.fine_move_pixels = max(1, min(20, int(data["fine_move_pixels"])))
    if "scroll_amount" in data:
        config.scroll_amount = max(1, min(120, int(data["scroll_amount"])))
    if "accel_power" in data:
        config.accel_power = max(0.5, min(3.0, float(data["accel_power"])))
    if "tick_rate" in data:
        config.tick_rate = max(30, min(1000, int(data["tick_rate"])))
    if "scroll_repeat_delay" in data:
        config.scroll_repeat_delay = max(0.005, min(1.0, float(data["scroll_repeat_delay"])))
    if "fine_move_repeat_delay" in data:
        config.fine_move_repeat_delay = max(0.005, min(1.0, float(data["fine_move_repeat_delay"])))
    if "click_cooldown" in data:
        config.click_cooldown = max(0.01, min(2.0, float(data["click_cooldown"])))
    if "pause_cooldown" in data:
        config.pause_cooldown = max(0.01, min(2.0, float(data["pause_cooldown"])))
    if "sensitivity_cycle_cooldown" in data:
        config.sensitivity_cycle_cooldown = max(0.01, min(2.0, float(data["sensitivity_cycle_cooldown"])))
    if "enter_cooldown" in data:
        config.enter_cooldown = max(0.01, min(2.0, float(data["enter_cooldown"])))
    if "dictation_min_seconds" in data:
        config.dictation_min_seconds = max(0.1, min(10.0, float(data["dictation_min_seconds"])))
    if "sensitivity_stages" in data:
        current_stages = list(getattr(config, "sensitivity_stages", []) or [30, 45, 60, 80, 105])
        config.sensitivity_stages = _parse_sensitivity_stages(data["sensitivity_stages"], current_stages)
    if "stage_index" in data:
        stage_count = len(getattr(config, "sensitivity_stages", []) or [])
        if stage_count > 0:
            config.stage_index = max(0, min(stage_count - 1, int(data["stage_index"])))
    if "lt_axis_candidates" in data:
        config.lt_axis_candidates = _parse_axis_candidates(data["lt_axis_candidates"])
    if "rt_axis_candidates" in data:
        config.rt_axis_candidates = _parse_axis_candidates(data["rt_axis_candidates"])
    if "ui_language" in data:
        config.ui_language = "en" if str(data["ui_language"]).lower().startswith("en") else "zh"
    if "ui_theme" in data:
        config.ui_theme = "dark" if str(data["ui_theme"]).lower() == "dark" else "light"
    if "control_bindings" in data and isinstance(data["control_bindings"], dict):
        config.control_bindings = normalize_binding_config(data["control_bindings"])

    _sanitize_trigger_candidates(config, data)

    speech_profile = data.get("speech_profile")
    if speech_profile in SPEECH_PROFILES:
        apply_speech_profile(str(speech_profile))

    try:
        save_config(config)
    except Exception:
        pass

    return jsonify(bindings_payload())


@app.route("/set-speech-mode", methods=["POST"])
def set_speech_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode") or data.get("profile")
    if mode not in SPEECH_PROFILES:
        return jsonify({"ok": False, "error": "unknown speech mode", "mode": mode, "allowed": list(SPEECH_PROFILES)}), 400
    profile = SPEECH_PROFILES[mode]
    current = current_speech_profile_id()
    voice_state = get_voice_state()
    loading_state = update_speech_loading_state()

    same_mode = mode == current
    already_loading_same_mode = (
        bool(loading_state.get("active"))
        and loading_state.get("target") == mode
    )
    already_ready_same_mode = (
        same_mode
        and profile_matches_voice_state(profile, voice_state)
        and not bool(voice_state.get("loading"))
    )

    if already_loading_same_mode or already_ready_same_mode:
        with SPEECH_LOADING_LOCK:
            if profile["model"] == "small":
                SPEECH_LOADING_STATE["active"] = bool(voice_state.get("loading")) or already_loading_same_mode
                SPEECH_LOADING_STATE["target"] = mode
                SPEECH_LOADING_STATE["phase"] = "loading" if SPEECH_LOADING_STATE["active"] else "ready"
            else:
                SPEECH_LOADING_STATE["active"] = False
                SPEECH_LOADING_STATE["target"] = mode
                SPEECH_LOADING_STATE["phase"] = "ready"
        print(f"[WEB] speech mode unchanged -> {mode} | model={profile['model']} | language={profile['language'] or 'auto'}")
        return jsonify(speech_config_payload())

    profile = apply_speech_profile(mode)
    with SPEECH_LOADING_LOCK:
        if profile["model"] == "small":
            SPEECH_LOADING_STATE["active"] = True
            SPEECH_LOADING_STATE["target"] = mode
            SPEECH_LOADING_STATE["phase"] = "loading"
        else:
            SPEECH_LOADING_STATE["active"] = False
            SPEECH_LOADING_STATE["target"] = mode
            SPEECH_LOADING_STATE["phase"] = "ready"
    print(f"[WEB] speech mode -> {mode} | model={profile['model']} language={profile['language'] or 'auto'}")
    return jsonify(speech_config_payload())


@app.route("/snap-targets", methods=["POST"])
def snap_targets():
    data = request.get_json(silent=True) or {}
    targets = data.get("targets", [])

    if hasattr(engine, "set_snap_targets"):
        engine.set_snap_targets(targets)

    return jsonify({
        "ok": True,
        "count": len(targets),
    })


@app.route("/snap-state")
def snap_state():
    if hasattr(engine, "get_snap_state"):
        return jsonify(engine.get_snap_state())

    return jsonify({
        "enabled": False,
        "index": 0,
        "count": 0,
        "label": None,
    })


@app.route("/start", methods=["POST"])
def start():
    print("[WEB] start")
    engine.start()
    return "started"


@app.route("/pause", methods=["POST"])
def pause():
    print("[WEB] pause")
    if hasattr(engine, "toggle_pause"):
        engine.toggle_pause()
    return "paused"


@app.route("/stop", methods=["POST"])
def stop():
    print("[WEB] stop")
    engine.stop()
    return "stopped"


if __name__ == "__main__":
    print("Running at http://127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)
