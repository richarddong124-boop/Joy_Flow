from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Callable

import numpy as np


PROMPT_HALLUCINATION_PHRASES = (
    "请输出简体中文",
    "请输入简体中文",
    "输出简体中文",
    "输入简体中文",
    "以下是普通话中文语音转写",
    "普通话中文语音转写",
    "不要翻译成英文",
)

VIDEO_OUTRO_HALLUCINATION_PHRASES = (
    "请点赞",
    "订阅",
    "转发",
    "打赏",
)


def _compact_text(text: str) -> str:
    return "".join(str(text or "").replace("，", ",").replace("。", ".").split())


def _should_block_transcript(text: str, *, peak: float, rms: float) -> tuple[bool, str]:
    """Return (True, reason) when Whisper produced obvious prompt/silence garbage."""
    compact = _compact_text(text)
    if not compact:
        return False, ""

    for phrase in PROMPT_HALLUCINATION_PHRASES:
        if _compact_text(phrase) in compact:
            return True, "blocked Chinese prompt hallucination"

    outro_hits = sum(1 for phrase in VIDEO_OUTRO_HALLUCINATION_PHRASES if phrase in text)
    if outro_hits >= 2:
        return True, "blocked common Chinese outro hallucination"

    # On very quiet audio, Whisper often invents text. Do not paste short confident-looking junk.
    if peak < 0.012 and rms < 0.0015:
        return True, "blocked ultra-quiet audio hallucination"

    return False, ""


def _contains_han(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def _contains_cjk(text: str) -> bool:
    for ch in str(text or ""):
        if (
            "\u3400" <= ch <= "\u4dbf"
            or "\u4e00" <= ch <= "\u9fff"
            or "\uf900" <= ch <= "\ufaff"
            or "\u3040" <= ch <= "\u30ff"
            or "\uac00" <= ch <= "\ud7af"
        ):
            return True
    return False


def _should_block_for_language(text: str, language: str | None) -> tuple[bool, str]:
    if language == "zh" and not _contains_han(text):
        return True, "blocked non-Chinese output in zh mode"
    if language == "en" and _contains_cjk(text):
        return True, "blocked CJK output in en mode"
    return False, ""


class WhisperDictation:
    """LT hold-to-talk recorder + Whisper transcriber.

    API expected by controller_mouse_app.py:
      start()
      stop_and_transcribe()
      cancel()
      state()
    """

    def __init__(
        self,
        notify: Callable[[str], None],
        *,
        model_name: str = "tiny",
        download_root: str | Path = "models",
        sample_rate: int = 16000,
        min_seconds: float = 0.25,
        release_tail_seconds: float = 0.25,
        language: str | None = None,
        initial_prompt: str | None = None,
    ):
        self.notify = notify
        self.model_name = str(model_name or "tiny")
        self.download_root = Path(download_root)
        self.sample_rate = int(sample_rate)
        self.min_seconds = float(min_seconds)
        self.release_tail_seconds = float(max(0.0, release_tail_seconds))
        self.language = language or None
        self.initial_prompt = initial_prompt or None

        self._lock = threading.RLock()
        self._frames: list[np.ndarray] = []
        self._stream = None
        self._recording = False
        self._transcribing = False
        self._start_time = 0.0
        self._model = None
        self._last_text = ""
        self._last_error = ""
        self._warmup_started = False
        self._model_loading = False
        self._model_condition = threading.Condition(self._lock)

    def state(self) -> dict:
        with self._lock:
            return {
                "recording": bool(self._recording),
                "transcribing": bool(self._transcribing),
                "loading": bool(self._warmup_started or self._model_loading),
                "ready": self._model is not None,
                "model": self.model_name,
                "language": self.language or "auto",
                "last_text": self._last_text,
                "last_error": self._last_error,
            }

    def start(self) -> None:
        with self._lock:
            if self._recording:
                self.notify("LT dictation already recording.")
                return
            if self._transcribing:
                self.notify("LT dictation busy: still transcribing previous audio.")
                return

            self._frames = []
            self._last_error = ""
            self._start_time = time.time()
            self._recording = True

        try:
            import sounddevice as sd

            def callback(indata, frames, time_info, status):  # noqa: ANN001
                if status:
                    self.notify(f"Microphone status: {status}")
                with self._lock:
                    if self._recording:
                        self._frames.append(np.array(indata[:, 0], dtype=np.float32).copy())

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=callback,
            )
            self._stream.start()
            self.notify("LT dictation: recording...")
        except Exception as exc:
            with self._lock:
                self._recording = False
            self._last_error = repr(exc)
            self.notify(f"Microphone start error: {exc!r}")
            self.notify(traceback.format_exc().rstrip())

    def stop_and_transcribe(self) -> None:
        # Capture and stop the stream quickly from the controller loop, then transcribe in background.
        with self._lock:
            if not self._recording:
                return

        if self.release_tail_seconds > 0:
            time.sleep(self.release_tail_seconds)

        with self._lock:
            self._recording = False
            duration = time.time() - self._start_time
            frames = list(self._frames)
            self._frames = []

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as exc:
            self.notify(f"Microphone stop warning: {exc!r}")
        finally:
            self._stream = None

        if duration < self.min_seconds:
            self.notify("LT dictation: too short, ignored.")
            return

        if not frames:
            self.notify("LT dictation: no microphone frames captured.")
            return

        audio = np.concatenate(frames).astype(np.float32, copy=False)
        if audio.size == 0:
            self.notify("LT dictation: empty audio buffer.")
            return

        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        actual_seconds = float(audio.size) / float(self.sample_rate)
        self.notify(f"Recorded audio: {actual_seconds:.2f}s | peak={peak:.4f} | rms={rms:.4f}")

        if peak < 0.003 and rms < 0.0008:
            self.notify("Microphone audio is extremely quiet. Check Windows input device/level.")

        threading.Thread(target=self._transcribe_and_paste, args=(audio,), daemon=True).start()

    def _load_model(self):
        with self._model_condition:
            if self._model is not None:
                return self._model
            if self._model_loading:
                while self._model_loading and self._model is None:
                    self._model_condition.wait(timeout=0.1)
                if self._model is not None:
                    return self._model
            self._model_loading = True

        try:
            import whisper

            self.download_root.mkdir(parents=True, exist_ok=True)
            self.notify(f"Loading Whisper model: {self.model_name}")
            self.notify(f"Whisper download_root: {self.download_root}")
            model = whisper.load_model(self.model_name, download_root=str(self.download_root))
            with self._model_condition:
                self._model = model
                self._model_loading = False
                self._model_condition.notify_all()
            self.notify("Whisper ready.")
            return model
        except Exception:
            with self._model_condition:
                self._model_loading = False
                self._model_condition.notify_all()
            raise

    def warmup_async(self) -> None:
        with self._lock:
            if self._model is not None or self._transcribing or self._warmup_started:
                return
            self._warmup_started = True

        def _worker() -> None:
            try:
                self.notify(f"Whisper warmup queued: {self.model_name}")
                self._load_model()
            except Exception as exc:
                self._last_error = repr(exc)
                self.notify(f"Whisper warmup error: {exc!r}")
                self.notify(traceback.format_exc().rstrip())
            finally:
                with self._lock:
                    self._warmup_started = False

        threading.Thread(target=_worker, daemon=True).start()

    def _transcribe_and_paste(self, audio: np.ndarray) -> None:
        with self._lock:
            if self._transcribing:
                self.notify("Whisper is already transcribing; skipped duplicate request.")
                return
            self._transcribing = True

        try:
            model = self._load_model()
            self.notify("Whisper transcribing...")

            kwargs = {
                "fp16": False,
                "task": "transcribe",
                "condition_on_previous_text": False,
                "no_speech_threshold": 0.55,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            }
            if self.language:
                kwargs["language"] = self.language
            if self.initial_prompt:
                kwargs["initial_prompt"] = self.initial_prompt

            result = model.transcribe(audio, **kwargs)
            text = str((result or {}).get("text") or "").strip()
            self._last_text = text

            if not text:
                self.notify("Whisper heard no text.")
                return

            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
            blocked, reason = _should_block_transcript(text, peak=peak, rms=rms)
            if blocked:
                self.notify(f"Ignored transcript: {reason}: {text}")
                return

            blocked, reason = _should_block_for_language(text, self.language)
            if blocked:
                self.notify(f"Ignored transcript: {reason}: {text}")
                return

            self.notify(f"Dictated: {text}")
            self._paste_text(text)

        except Exception as exc:
            self._last_error = repr(exc)
            self.notify(f"Whisper error: {exc!r}")
            self.notify(traceback.format_exc().rstrip())
        finally:
            with self._lock:
                self._transcribing = False

    def _paste_text(self, text: str) -> None:
        try:
            import pyperclip
            import pyautogui

            pyperclip.copy(text)
            time.sleep(0.03)
            pyautogui.hotkey("ctrl", "v", _pause=False)
        except Exception as exc:
            self._last_error = repr(exc)
            self.notify(f"Paste error: {exc!r}")
            self.notify(traceback.format_exc().rstrip())

    def cancel(self) -> None:
        with self._lock:
            was_recording = self._recording
            self._recording = False
            self._frames = []

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        finally:
            self._stream = None

        if was_recording:
            self.notify("LT dictation cancelled.")
