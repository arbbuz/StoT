import queue
import ctypes
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import sounddevice as sd

from windows_spellcheck import SpellingIssue, add_word, check_text


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = app_dir()
APP_ICON = APP_DIR / "assets" / "app_icon.ico"
WHISPER_BACKENDS = {
    "avx2": APP_DIR / ".tools" / "whisper.cpp-build-avx2" / "bin" / "whisper-cli.exe",
    "compat": APP_DIR / ".tools" / "whisper.cpp-build-compat" / "bin" / "whisper-cli.exe",
}
DISABLED_WHISPER_BACKENDS: set[str] = set()
WHISPER_EXE = WHISPER_BACKENDS["compat"]
MODELS_DIR = APP_DIR / "models"
MODEL_LABELS = {
    "tiny-q5_1": "tiny-q5_1: быстрее, менее точно",
    "base-q5_1": "base-q5_1: рекомендовано",
    "small-q5_1": "small-q5_1: точнее, медленно",
}
MODEL_FILES = {
    "tiny-q5_1": MODELS_DIR / "ggml-tiny-q5_1.bin",
    "base-q5_1": MODELS_DIR / "ggml-base-q5_1.bin",
    "small-q5_1": MODELS_DIR / "ggml-small-q5_1.bin",
}
MODEL_OPTIONS = {MODEL_LABELS[key]: MODEL_FILES[key] for key in MODEL_LABELS}
MODEL_KEY_BY_LABEL = {label: key for key, label in MODEL_LABELS.items()}
DEFAULT_MODEL_LABEL = "base-q5_1: рекомендовано"
PROFILE_MODEL_KEYS = {
    "Авто": None,
    "Быстро": "tiny-q5_1",
    "Баланс": "base-q5_1",
    "Точно": "small-q5_1",
}
DEFAULT_PROFILE_LABEL = "Авто"
FALLBACK_AUTO_MODEL_KEY = "base-q5_1"
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
SILENCE_WINDOW_MS = 30
SILENCE_PADDING_MS = 250
SILENCE_PEAK_THRESHOLD = 350
MIN_AUDIO_MS = 600
VAD_FRAME_MS = 20
VAD_PADDING_MS = 180
VAD_MAX_INTERNAL_SILENCE_MS = 450
VAD_MIN_RMS = 80.0
VAD_MIN_PEAK = 350
VAD_NOISE_MULTIPLIER = 3.0
BENCHMARK_AUDIO_SECONDS = 2.0
FIREWALL_RULE_NAME = "VoiceHelper Block Outbound"


def performance_profile_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "VoiceHelper" / "performance_profile.json"
    return APP_DIR / "performance_profile.json"


PERFORMANCE_PROFILE_PATH = performance_profile_path()


def available_whisper_backends() -> list[tuple[str, Path]]:
    return [(name, path) for name, path in WHISPER_BACKENDS.items() if path.exists() and name not in DISABLED_WHISPER_BACKENDS]


def build_whisper_command(exe_path: Path, model_path: Path, wav_path: Path, out_base: Path) -> list[str]:
    return [
        str(exe_path),
        "-m",
        str(model_path),
        "-f",
        str(wav_path),
        "-l",
        "ru",
        "-t",
        "4",
        "-nt",
        "-np",
        "-nf",
        "-otxt",
        "-of",
        str(out_base),
    ]


def decode_process_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def run_whisper_with_fallback(model_path: Path, wav_path: Path, out_base: Path, timeout_seconds: int | None = None) -> tuple[str, subprocess.CompletedProcess[bytes]]:
    backends = available_whisper_backends()
    if not backends:
        expected = "\n".join(str(path) for path in WHISPER_BACKENDS.values())
        raise RuntimeError(f"missing-whisper-cli::{expected}")

    txt_path = out_base.with_suffix(".txt")
    errors: list[str] = []

    for backend_name, exe_path in backends:
        if txt_path.exists():
            txt_path.unlink()

        command = build_whisper_command(exe_path, model_path, wav_path, out_base)
        try:
            completed = subprocess.run(
                command,
                cwd=str(APP_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            errors.append(f"{backend_name}: timeout after {timeout_seconds} seconds")
            continue
        except Exception as exc:
            errors.append(f"{backend_name}: {exc}")
            continue

        if completed.returncode == 0 and txt_path.exists():
            return backend_name, completed

        stderr_text = decode_process_output(completed.stderr)
        stdout_text = decode_process_output(completed.stdout)
        detail = stderr_text or stdout_text or "stderr/stdout пустой"
        if completed.returncode == 0 and not txt_path.exists():
            detail = "TXT output was not created"
        if completed.returncode in (3221225501, -1073741795):
            DISABLED_WHISPER_BACKENDS.add(backend_name)
            detail = f"{detail}; backend disabled for this session after illegal instruction exit"
        errors.append(f"{backend_name}: exit {completed.returncode}; {detail}")

    technical = "\n".join(errors) if errors else "no backend attempts were made"
    raise RuntimeError(f"whisper-failed::1::{technical}")


def load_performance_profile() -> dict:
    try:
        if PERFORMANCE_PROFILE_PATH.exists():
            return json.loads(PERFORMANCE_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def save_performance_profile(data: dict) -> None:
    PERFORMANCE_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERFORMANCE_PROFILE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def choose_auto_model_key(results: dict | None = None) -> str:
    if results is None:
        results = load_performance_profile().get("results", {})

    def realtime_factor(model_key: str) -> float | None:
        item = results.get(model_key)
        if not isinstance(item, dict) or not item.get("ok"):
            return None
        try:
            return float(item["realtime_factor"])
        except Exception:
            return None

    small_rtf = realtime_factor("small-q5_1")
    base_rtf = realtime_factor("base-q5_1")
    tiny_rtf = realtime_factor("tiny-q5_1")

    if small_rtf is not None and small_rtf <= 1.5:
        return "small-q5_1"
    if base_rtf is not None and base_rtf <= 2.5:
        return "base-q5_1"
    if tiny_rtf is not None:
        return "tiny-q5_1"
    return FALLBACK_AUTO_MODEL_KEY


def write_benchmark_wav(wav_path: Path, seconds: float = BENCHMARK_AUDIO_SECONDS) -> None:
    total_frames = int(SAMPLE_RATE * seconds)
    frames = bytearray()
    for index in range(total_frames):
        t = index / SAMPLE_RATE
        envelope = 0.0 if t < 0.15 or t > seconds - 0.15 else 1.0
        sample = int(envelope * (2200 * math.sin(2 * math.pi * 220 * t) + 900 * math.sin(2 * math.pi * 440 * t)))
        frames.extend(sample.to_bytes(SAMPLE_WIDTH_BYTES, byteorder="little", signed=True))

    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))


def run_model_benchmark(allow_missing_models: bool = False, print_fn=None) -> dict:
    results: dict[str, dict] = {}

    with tempfile.TemporaryDirectory(prefix="voicehelper_benchmark_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        wav_path = tmp_path / "benchmark.wav"
        write_benchmark_wav(wav_path)

        for model_key, model_path in MODEL_FILES.items():
            if not model_path.exists():
                results[model_key] = {"ok": False, "error": f"missing model: {model_path}"}
                if print_fn:
                    print_fn(f"{model_key}: missing model")
                if not allow_missing_models:
                    continue
                continue

            out_base = tmp_path / f"benchmark_{model_key}"
            started_at = time.perf_counter()
            try:
                backend_name, _completed = run_whisper_with_fallback(
                    model_path,
                    wav_path,
                    out_base,
                    timeout_seconds=300,
                )
                elapsed = time.perf_counter() - started_at
                rtf = elapsed / BENCHMARK_AUDIO_SECONDS
                results[model_key] = {
                    "ok": True,
                    "backend": backend_name,
                    "elapsed_seconds": round(elapsed, 3),
                    "realtime_factor": round(rtf, 3),
                }
                if print_fn:
                    print_fn(f"{model_key}: {elapsed:.2f}s, realtime x{rtf:.2f}, backend={backend_name}")
            except Exception as exc:
                results[model_key] = {"ok": False, "error": str(exc)}
                if print_fn:
                    print_fn(f"{model_key}: failed: {exc}")

    selected_model = choose_auto_model_key(results)
    profile = {
        "version": 1,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "audio_seconds": BENCHMARK_AUDIO_SECONDS,
        "selected_model": selected_model,
        "results": results,
    }
    if any(item.get("ok") for item in results.values()):
        save_performance_profile(profile)
    return profile


class VoiceHelperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("VoiceHelper")
        self._apply_window_icon()
        self.root.geometry("900x560")
        self.root.minsize(720, 460)

        self.audio_chunks: list[bytes] = []
        self.stream: sd.RawInputStream | None = None
        self.worker: threading.Thread | None = None
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_recording = False
        self.is_recognizing = False
        self.is_testing_microphone = False
        self.is_benchmarking = False
        self.record_started_at: float | None = None
        self.record_sample_rate = SAMPLE_RATE
        self.mic_test_stream: sd.RawInputStream | None = None
        self.mic_test_peak = 0
        self.last_level_event_at = 0.0
        self.input_devices: dict[str, list[int]] = {}
        self.spellcheck_after_id: str | None = None
        self.spellcheck_generation = 0
        self.spelling_issues: dict[str, SpellingIssue] = {}

        self.status_var = tk.StringVar(value="Готово")
        self.record_time_var = tk.StringVar(value="Запись: 00:00")
        self.recognition_time_var = tk.StringVar(value="Распознавание: -")
        self.firewall_status_var = tk.StringVar(value="Сеть: проверка...")
        self.speed_status_var = tk.StringVar(value="Скорость: авто")
        self.profile_var = tk.StringVar(value=DEFAULT_PROFILE_LABEL)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL_LABEL)
        self.input_device_var = tk.StringVar(value="")
        self.input_level_var = tk.DoubleVar(value=0)
        self.input_level_text_var = tk.StringVar(value="Уровень: -")
        self.spellcheck_status_var = tk.StringVar(value="Орфография: авто")

        self._build_ui()
        self._apply_profile_selection()
        self.refresh_input_devices()
        self._check_local_files()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._process_ui_queue)
        self.root.after(250, self._update_record_timer)
        self.root.after(500, self.refresh_firewall_status)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(6, weight=1)

        self.record_button = ttk.Button(toolbar, text="Записать", command=self.start_recording)
        self.record_button.grid(row=0, column=0, padx=(0, 8))

        self.stop_button = ttk.Button(toolbar, text="Стоп", command=self.stop_recording, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=(0, 8))

        self.copy_button = ttk.Button(toolbar, text="Скопировать", command=self.copy_text)
        self.copy_button.grid(row=0, column=2, padx=(0, 8))

        self.clear_button = ttk.Button(toolbar, text="Очистить", command=self.clear_text)
        self.clear_button.grid(row=0, column=3, padx=(0, 16))

        self.firewall_button = ttk.Button(toolbar, text="Блокировать сеть", command=self.enable_firewall_block)
        self.firewall_button.grid(row=0, column=4, padx=(0, 0))

        self.firewall_unblock_button = ttk.Button(toolbar, text="Разблокировать", command=self.disable_firewall_block)
        self.firewall_unblock_button.grid(row=0, column=5, padx=(0, 16))

        ttk.Label(toolbar, text="Модель:").grid(row=0, column=6, sticky="e", padx=(0, 6))
        self.model_box = ttk.Combobox(
            toolbar,
            textvariable=self.model_var,
            values=list(MODEL_OPTIONS.keys()),
            state="readonly",
            width=28,
        )
        self.model_box.grid(row=0, column=7, sticky="e")
        self.model_box.bind("<<ComboboxSelected>>", self._on_model_changed)

        ttk.Label(toolbar, text="Профиль:").grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 6))
        self.profile_box = ttk.Combobox(
            toolbar,
            textvariable=self.profile_var,
            values=list(PROFILE_MODEL_KEYS.keys()),
            state="readonly",
            width=12,
        )
        self.profile_box.grid(row=1, column=1, sticky="w", pady=(8, 0), padx=(0, 8))
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_changed)
        self.benchmark_button = ttk.Button(toolbar, text="Бенчмарк", command=self.start_model_benchmark)
        self.benchmark_button.grid(row=1, column=2, sticky="w", pady=(8, 0), padx=(0, 12))
        ttk.Label(toolbar, textvariable=self.speed_status_var).grid(row=1, column=3, columnspan=5, sticky="w", pady=(8, 0))

        info = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        info.grid(row=1, column=0, sticky="ew")
        info.columnconfigure(3, weight=1)

        ttk.Label(info, text="Статус:").grid(row=0, column=0, padx=(0, 4))
        ttk.Label(info, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=(0, 18))
        ttk.Label(info, textvariable=self.record_time_var).grid(row=0, column=2, sticky="w", padx=(0, 18))
        ttk.Label(info, textvariable=self.recognition_time_var).grid(row=0, column=3, sticky="w", padx=(0, 18))
        ttk.Label(info, textvariable=self.firewall_status_var).grid(row=0, column=4, sticky="w")
        ttk.Label(info, textvariable=self.spellcheck_status_var).grid(row=0, column=5, sticky="w", padx=(18, 0))

        ttk.Label(info, text="Микрофон:").grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 4))
        self.input_device_box = ttk.Combobox(
            info,
            textvariable=self.input_device_var,
            state="readonly",
            width=44,
        )
        self.input_device_box.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(6, 0), padx=(0, 8))
        self.refresh_input_button = ttk.Button(info, text="Обновить", command=self.refresh_input_devices)
        self.refresh_input_button.grid(row=1, column=4, sticky="w", pady=(6, 0))
        self.test_input_button = ttk.Button(info, text="Проверить", command=self.start_microphone_test)
        self.test_input_button.grid(row=1, column=5, sticky="w", pady=(6, 0), padx=(8, 0))
        self.input_level_bar = ttk.Progressbar(
            info,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=90,
        )
        self.input_level_bar.grid(row=1, column=6, sticky="w", pady=(6, 0), padx=(8, 4))
        ttk.Label(info, textvariable=self.input_level_text_var).grid(row=1, column=7, sticky="w", pady=(6, 0))

        text_frame = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(text_frame, wrap="word", undo=True, font=("Segoe UI", 12))
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("spelling_error", underline=True)
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<Button-3>", self._show_spelling_menu)

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

    def _apply_window_icon(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VoiceHelper.LocalDictation")
        except Exception:
            pass

        if APP_ICON.exists():
            try:
                self.root.iconbitmap(default=str(APP_ICON))
            except Exception:
                pass

    def _check_local_files(self) -> None:
        missing = []
        if not available_whisper_backends():
            missing.extend(str(path) for path in WHISPER_BACKENDS.values())
        for model_path in MODEL_OPTIONS.values():
            if not model_path.exists():
                missing.append(str(model_path))

        if missing:
            self._set_status("Не найдены локальные файлы")
            messagebox.showerror(
                "VoiceHelper",
                self._format_problem_message(
                    "Не найдены обязательные локальные файлы VoiceHelper.",
                    [
                        "Запускайте приложение из полной папки VoiceHelper, не переносите один EXE отдельно.",
                        "Проверьте, что рядом с VoiceHelper.exe есть папки models и .tools.",
                        "Если это сборка из GitHub Actions, скачайте и распакуйте artifact целиком.",
                        "Для проверки запустите scripts\\diagnose_voicehelper.cmd.",
                    ],
                    technical="\n".join(missing),
                ),
            )
            self.record_button.configure(state=tk.DISABLED)

    def _on_profile_changed(self, event=None) -> None:
        self._apply_profile_selection()

    def _on_model_changed(self, event=None) -> None:
        self._update_speed_status()

    def _apply_profile_selection(self) -> None:
        profile = self.profile_var.get()
        model_key = PROFILE_MODEL_KEYS.get(profile)
        if model_key is None:
            model_key = choose_auto_model_key()
        self._select_model_key(model_key)
        self._update_speed_status()

    def _select_model_key(self, model_key: str) -> None:
        label = MODEL_LABELS.get(model_key, DEFAULT_MODEL_LABEL)
        self.model_var.set(label)

    def _selected_model_key(self) -> str:
        return MODEL_KEY_BY_LABEL.get(self.model_var.get(), MODEL_KEY_BY_LABEL[DEFAULT_MODEL_LABEL])

    def _update_speed_status(self, vad_stats: dict | None = None, backend_name: str | None = None) -> None:
        profile = self.profile_var.get()
        model_key = self._selected_model_key()
        backend = backend_name or self._preferred_backend_name()
        parts = [f"Скорость: {profile.lower()}, модель {model_key}", f"backend {backend}"]
        if vad_stats:
            reduction = vad_stats.get("reduction_percent", 0)
            parts.append(f"VAD -{reduction:.0f}%")
        self.speed_status_var.set("; ".join(parts))

    def _preferred_backend_name(self) -> str:
        backends = available_whisper_backends()
        return backends[0][0] if backends else "нет whisper-cli"

    def start_model_benchmark(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_benchmarking:
            return

        self.is_benchmarking = True
        self._set_status("Бенчмарк моделей...")
        self.record_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._benchmark_models_worker, daemon=True).start()

    def _benchmark_models_worker(self) -> None:
        try:
            profile = run_model_benchmark(allow_missing_models=True)
            if not any(item.get("ok") for item in profile.get("results", {}).values()):
                raise RuntimeError("No local models were available for benchmark.")
            self.ui_queue.put(("benchmark_result", profile))
        except Exception as exc:
            self.ui_queue.put(("benchmark_error", self._format_problem_message(
                "Не удалось выполнить бенчмарк моделей.",
                [
                    "Проверьте, что рядом с VoiceHelper.exe есть папки models и .tools.",
                    "Запустите scripts\\diagnose_voicehelper.cmd для проверки состава папки.",
                ],
                technical=self._shorten_technical_text(str(exc)),
            )))
        finally:
            self.ui_queue.put(("benchmark_ready", None))

    def refresh_input_devices(self) -> None:
        previous_value = self.input_device_var.get()
        self.input_devices = {}
        grouped_devices: dict[str, list[int]] = {}
        device_is_default: dict[str, bool] = {}

        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception as exc:
            self.input_device_var.set("")
            self.input_device_box.configure(values=[], state=tk.DISABLED)
            self.test_input_button.configure(state=tk.DISABLED)
            self._set_status("Не удалось прочитать микрофоны")
            return

        default_input = None
        try:
            candidate = sd.default.device[0]
            if isinstance(candidate, int) and candidate >= 0:
                default_input = candidate
        except Exception:
            default_input = None

        visible_candidates = []
        fallback_candidates = []
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) <= 0:
                continue
            hostapi_name = ""
            try:
                hostapi_name = hostapis[int(device["hostapi"])]["name"]
            except Exception:
                pass
            device_info = (index, str(device["name"]), hostapi_name)
            if self._is_low_level_input_backend(hostapi_name):
                fallback_candidates.append(device_info)
            elif self._is_system_input_alias(str(device["name"])):
                continue
            else:
                visible_candidates.append(device_info)

        candidates = visible_candidates or fallback_candidates
        for index, name, hostapi_name in candidates:
            if self._is_system_input_alias(name):
                continue
            display_name = self._clean_input_device_name(name)
            grouped_devices.setdefault(display_name, []).append(index)
            if index == default_input:
                device_is_default[display_name] = True

        ordered_names = sorted(
            grouped_devices,
            key=lambda name: (not device_is_default.get(name, False), name.lower()),
        )
        labels: list[str] = []
        for name in ordered_names:
            grouped_devices[name].sort(key=self._input_device_priority)
            marker = " (по умолчанию)" if device_is_default.get(name, False) else ""
            label = f"{name}{marker}"
            labels.append(label)
            self.input_devices[label] = grouped_devices[name]

        self.input_device_box.configure(values=labels)
        if not labels:
            self.input_device_var.set("")
            self.input_device_box.configure(state=tk.DISABLED)
            self.record_button.configure(state=tk.DISABLED)
            self.test_input_button.configure(state=tk.DISABLED)
            self._set_status("Микрофоны не найдены")
            return

        selected = None
        if previous_value in self.input_devices:
            selected = previous_value
        elif default_input is not None:
            selected = next((label for label, indexes in self.input_devices.items() if default_input in indexes), None)

        if selected is None:
            selected = labels[0]

        self.input_device_var.set(selected)
        self.input_device_box.configure(state="readonly")
        self.record_button.configure(state=tk.NORMAL)
        self.test_input_button.configure(state=tk.NORMAL)

    def _clean_input_device_name(self, name: str) -> str:
        return " ".join(name.replace("  ", " ").strip().split())

    def _is_system_input_alias(self, name: str) -> bool:
        normalized = name.lower()
        aliases = (
            "microsoft sound mapper",
            "primary sound capture",
            "первичный драйвер записи",
        )
        return any(alias in normalized for alias in aliases)

    def _is_low_level_input_backend(self, hostapi_name: str) -> bool:
        normalized = hostapi_name.lower()
        return "wdm-ks" in normalized

    def _input_device_priority(self, device_index: int) -> int:
        try:
            device = sd.query_devices(device_index, "input")
            hostapi = sd.query_hostapis(int(device["hostapi"]))
            hostapi_name = str(hostapi["name"]).lower()
        except Exception:
            return 99

        if "wasapi" in hostapi_name:
            return 0
        if "directsound" in hostapi_name:
            return 1
        if "mme" in hostapi_name:
            return 2
        if "wdm-ks" in hostapi_name:
            return 3
        return 10

    def _selected_input_device_indexes(self) -> list[int]:
        label = self.input_device_var.get()
        if label in self.input_devices:
            return self.input_devices[label]
        self.refresh_input_devices()
        label = self.input_device_var.get()
        if label in self.input_devices:
            return self.input_devices[label]
        raise RuntimeError("Не найден доступный микрофон в списке VoiceHelper.")

    def _input_device_default_sample_rate(self, device_index: int) -> int:
        try:
            device = sd.query_devices(device_index, "input")
            return int(float(device.get("default_samplerate", SAMPLE_RATE)))
        except Exception:
            return SAMPLE_RATE

    def start_microphone_test(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_benchmarking:
            return

        self.mic_test_peak = 0
        self._set_input_level(0)

        try:
            self.mic_test_stream = self._open_input_stream(
                self._selected_input_device_indexes(),
                callback=self._microphone_test_callback,
            )
            self.mic_test_stream.start()
        except Exception as exc:
            self.mic_test_stream = None
            self._set_status("Ошибка микрофона")
            messagebox.showerror(
                "VoiceHelper",
                self._format_microphone_error(
                    "Не удалось проверить микрофон.",
                    exc,
                    include_diagnostics=True,
                ),
            )
            return

        self.is_testing_microphone = True
        self._set_status("Проверка микрофона: говорите 3 секунды")
        self.record_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.root.after(3000, self.finish_microphone_test)

    def finish_microphone_test(self) -> None:
        if not self.is_testing_microphone:
            return

        self.is_testing_microphone = False
        try:
            if self.mic_test_stream is not None:
                self.mic_test_stream.stop()
                self.mic_test_stream.close()
        finally:
            self.mic_test_stream = None

        self.record_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state="readonly")
        self.profile_box.configure(state="readonly")
        self.benchmark_button.configure(state=tk.NORMAL)
        self.input_device_box.configure(state="readonly")
        self.refresh_input_button.configure(state=tk.NORMAL)
        self.test_input_button.configure(state=tk.NORMAL)

        if self.mic_test_peak >= 3:
            self._set_status(f"Микрофон работает, пик {self.mic_test_peak}%")
            self.input_level_text_var.set(f"Пик: {self.mic_test_peak}%")
        else:
            self._set_status("Микрофон открыт, но звук не обнаружен")
            self.input_level_text_var.set("Уровень: тишина")
            messagebox.showwarning(
                "VoiceHelper",
                self._format_problem_message(
                    "Микрофон удалось открыть, но заметного звука за 3 секунды не обнаружено.",
                    [
                        "Проверьте, что выбран именно рабочий микрофон, а не линейный вход или стерео микшер.",
                        "Проверьте уровень входа в настройках Windows.",
                        "Проверьте физическую кнопку mute на гарнитуре или микрофоне.",
                        "Нажмите Обновить и повторите Проверить.",
                    ],
                ),
            )

    def start_recording(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_benchmarking:
            return

        self.audio_chunks = []
        self.recognition_time_var.set("Распознавание: -")
        self._set_input_level(0)

        try:
            self.stream = self._open_input_stream(self._selected_input_device_indexes())
            self.stream.start()
        except Exception as exc:
            self.stream = None
            self._set_status("Ошибка микрофона")
            messagebox.showerror(
                "VoiceHelper",
                self._format_microphone_error(
                    "Не удалось начать запись.",
                    exc,
                    include_diagnostics=True,
                ),
            )
            return

        self.is_recording = True
        self.record_started_at = time.perf_counter()
        self._set_status("Запись")
        self.record_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)

    def _open_input_stream(self, device_indexes: list[int], callback=None) -> sd.RawInputStream:
        errors: list[str] = []
        stream_callback = callback or self._audio_callback
        for device_index in device_indexes:
            for sample_rate in (SAMPLE_RATE, self._input_device_default_sample_rate(device_index)):
                try:
                    self.record_sample_rate = sample_rate
                    return sd.RawInputStream(
                        device=device_index,
                        samplerate=sample_rate,
                        channels=CHANNELS,
                        dtype="int16",
                        callback=stream_callback,
                    )
                except Exception as exc:
                    errors.append(f"device {device_index}, {sample_rate} Hz: {exc}")
        raise RuntimeError("\n".join(errors[-6:]) or "Не удалось открыть выбранный микрофон.")

    def stop_recording(self) -> None:
        if not self.is_recording:
            return

        self.is_recording = False
        self.stop_button.configure(state=tk.DISABLED)

        try:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
        finally:
            self.stream = None

        if not self.audio_chunks:
            self.record_started_at = None
            self.record_time_var.set("Запись: 00:00")
            self._set_status("Готово")
            self.record_button.configure(state=tk.NORMAL)
            self.model_box.configure(state="readonly")
            self.profile_box.configure(state="readonly")
            self.benchmark_button.configure(state=tk.NORMAL)
            self.input_device_box.configure(state="readonly")
            self.refresh_input_button.configure(state=tk.NORMAL)
            self.test_input_button.configure(state=tk.NORMAL)
            messagebox.showwarning(
                "VoiceHelper",
                self._format_problem_message(
                    "Запись пустая: VoiceHelper не получил аудиоданные от микрофона.",
                    [
                        "Нажмите Проверить и скажите несколько слов.",
                        "Если индикатор уровня не двигается, выберите другой микрофон или нажмите Обновить.",
                        "Если проблема повторяется, запустите scripts\\diagnose_voicehelper.cmd.",
                    ],
                ),
            )
            return

        self.is_recognizing = True
        self._set_status("Распознавание")
        self.worker = threading.Thread(target=self._recognize_audio, daemon=True)
        self.worker.start()

    def copy_text(self) -> None:
        value = self.text.get("1.0", tk.END).strip()
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        self._set_status("Скопировано")

    def clear_text(self) -> None:
        self.text.delete("1.0", tk.END)
        self._clear_spelling_marks()
        self._set_status("Готово")

    def _on_text_modified(self, event=None) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._schedule_spellcheck()

    def _cancel_pending_spellcheck(self) -> None:
        if self.spellcheck_after_id is not None:
            try:
                self.root.after_cancel(self.spellcheck_after_id)
            except tk.TclError:
                pass
            self.spellcheck_after_id = None

    def _schedule_spellcheck(self, delay_ms: int = 700) -> None:
        self._cancel_pending_spellcheck()
        self.spellcheck_after_id = self.root.after(delay_ms, self._start_spellcheck)

    def _start_spellcheck(self) -> None:
        self.spellcheck_after_id = None
        text_value = self.text.get("1.0", tk.END).rstrip()
        if not text_value:
            self._clear_spelling_marks()
            self.spellcheck_status_var.set("Орфография: авто")
            return

        self.spellcheck_generation += 1
        generation = self.spellcheck_generation
        self.spellcheck_status_var.set("Орфография: проверка...")

        def worker() -> None:
            try:
                issues = check_text(text_value, language_tag="ru-RU")
                self.ui_queue.put(("spelling_result", (generation, issues, None)))
            except Exception as exc:
                self.ui_queue.put(("spelling_result", (generation, [], str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_spelling_marks(self) -> None:
        self.text.tag_remove("spelling_error", "1.0", tk.END)
        for tag_name in list(self.spelling_issues):
            try:
                self.text.tag_delete(tag_name)
            except tk.TclError:
                pass
        self.spelling_issues.clear()

    def _apply_spelling_issues(self, issues: list[SpellingIssue]) -> None:
        self._clear_spelling_marks()
        for index, issue in enumerate(issues):
            tag_name = f"spelling_issue_{index}"
            start = f"1.0 + {issue.start} chars"
            end = f"1.0 + {issue.start + issue.length} chars"
            self.text.tag_add("spelling_error", start, end)
            self.text.tag_add(tag_name, start, end)
            self.spelling_issues[tag_name] = issue

    def _show_spelling_menu(self, event) -> str | None:
        index = self.text.index(f"@{event.x},{event.y}")
        issue_tag = next((tag for tag in self.text.tag_names(index) if tag in self.spelling_issues), None)
        if issue_tag is None:
            return None

        issue = self.spelling_issues[issue_tag]
        menu = tk.Menu(self.root, tearoff=False)
        if issue.suggestions:
            for suggestion in issue.suggestions:
                menu.add_command(
                    label=suggestion,
                    command=lambda value=suggestion, tag=issue_tag: self._replace_spelling_issue(tag, value),
                )
        else:
            menu.add_command(label="Нет вариантов", state=tk.DISABLED)

        menu.add_separator()
        menu.add_command(label="Добавить в словарь", command=lambda tag=issue_tag: self._add_spelling_word(tag))
        menu.add_command(label="Пропустить", command=lambda tag=issue_tag: self._ignore_spelling_issue(tag))
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _replace_spelling_issue(self, tag_name: str, replacement: str) -> None:
        ranges = self.text.tag_ranges(tag_name)
        if len(ranges) < 2:
            return

        start, end = ranges[0], ranges[1]
        self.text.delete(start, end)
        self.text.insert(start, replacement)
        self._schedule_spellcheck(delay_ms=150)

    def _ignore_spelling_issue(self, tag_name: str) -> None:
        ranges = self.text.tag_ranges(tag_name)
        if len(ranges) >= 2:
            self.text.tag_remove("spelling_error", ranges[0], ranges[1])
        try:
            self.text.tag_delete(tag_name)
        except tk.TclError:
            pass
        self.spelling_issues.pop(tag_name, None)
        count = len(self.spelling_issues)
        self.spellcheck_status_var.set(f"Орфография: {count} ошибок" if count else "Орфография: ошибок нет")

    def _add_spelling_word(self, tag_name: str) -> None:
        issue = self.spelling_issues.get(tag_name)
        if issue is None:
            return

        word = issue.word
        self._ignore_spelling_issue(tag_name)
        self.spellcheck_status_var.set("Орфография: добавление...")

        def worker() -> None:
            try:
                add_word(word, language_tag="ru-RU")
                self.ui_queue.put(("spelling_word_added", word))
            except Exception as exc:
                self.ui_queue.put(("spelling_add_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_firewall_status(self) -> None:
        def worker() -> None:
            blocked = self._is_firewall_block_enabled()
            self.ui_queue.put(("firewall_status", blocked))

        threading.Thread(target=worker, daemon=True).start()

    def enable_firewall_block(self) -> None:
        target = self._firewall_target_path()
        if not target.exists():
            messagebox.showerror(
                "VoiceHelper",
                self._format_problem_message(
                    "Не найден файл, для которого нужно включить сетевую блокировку.",
                    [
                        "Запускайте приложение из полной папки VoiceHelper.",
                        "Если это исходники, сначала соберите EXE или откройте dist\\VoiceHelper\\VoiceHelper.exe.",
                    ],
                    technical=str(target),
                ),
            )
            return

        if not getattr(sys, "frozen", False):
            proceed = messagebox.askyesno(
                "VoiceHelper",
                "Сейчас приложение запущено через Python.\n\n"
                "Для чистого пилота лучше открыть dist\\VoiceHelper\\VoiceHelper.exe и нажать кнопку там.\n\n"
                f"Продолжить и заблокировать сеть для:\n{target}?",
            )
            if not proceed:
                return

        script_path = self._write_firewall_script(target)
        try:
            self._run_cmd_elevated(script_path)
        except Exception as exc:
            messagebox.showerror(
                "VoiceHelper",
                self._format_problem_message(
                    "Не удалось запустить настройку Windows Firewall.",
                    [
                        "Проверьте, что подтвердили UAC-запрос Windows.",
                        "Если UAC-запрос не появился, запустите scripts\\diagnose_voicehelper.cmd.",
                        "Посмотрите лог: %TEMP%\\voicehelper_firewall.log.",
                    ],
                    technical=str(exc),
                ),
            )
            return

        self.firewall_status_var.set("Сеть: ожидает подтверждения Windows")
        self.root.after(5000, self.refresh_firewall_status)

    def disable_firewall_block(self) -> None:
        target = self._firewall_target_path()
        if not target.exists():
            messagebox.showerror(
                "VoiceHelper",
                self._format_problem_message(
                    "Не найден файл, для которого нужно снять сетевую блокировку.",
                    [
                        "Проверьте, что приложение запущено из полной папки VoiceHelper.",
                        "Если папку перенесли, старое firewall-правило можно удалить вручную в Windows Firewall.",
                    ],
                    technical=str(target),
                ),
            )
            return

        proceed = messagebox.askyesno(
            "VoiceHelper",
            "Удалить firewall-правило VoiceHelper для этого приложения?\n\n"
            f"{target}",
        )
        if not proceed:
            return

        script_path = self._write_firewall_script(target, remove=True)
        try:
            self._run_cmd_elevated(script_path)
        except Exception as exc:
            messagebox.showerror(
                "VoiceHelper",
                self._format_problem_message(
                    "Не удалось запустить снятие firewall-правила.",
                    [
                        "Проверьте, что подтвердили UAC-запрос Windows.",
                        "Посмотрите лог: %TEMP%\\voicehelper_firewall.log.",
                        "Если правило не снимается из приложения, удалите его в Windows Firewall вручную.",
                    ],
                    technical=str(exc),
                ),
            )
            return

        self.firewall_status_var.set("Сеть: ожидает подтверждения Windows")
        self.root.after(5000, self.refresh_firewall_status)

    def on_close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.mic_test_stream is not None:
            try:
                self.mic_test_stream.stop()
                self.mic_test_stream.close()
            except Exception:
                pass
            self.mic_test_stream = None
        self.root.destroy()

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.ui_queue.put(("status", f"Запись: {status}"))
        data = bytes(indata)
        self.audio_chunks.append(data)
        self._queue_input_level(data)

    def _microphone_test_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.ui_queue.put(("status", f"Проверка микрофона: {status}"))
        data = bytes(indata)
        level = self._audio_peak_percent(data)
        self.mic_test_peak = max(self.mic_test_peak, level)
        self._queue_input_level(data, force=True)

    def _audio_peak_percent(self, audio: bytes) -> int:
        if len(audio) < SAMPLE_WIDTH_BYTES:
            return 0
        try:
            samples = memoryview(audio).cast("h")
            peak = max(abs(sample) for sample in samples)
        except Exception:
            return 0
        return min(100, int(round(peak * 100 / 32767)))

    def _queue_input_level(self, audio: bytes, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_level_event_at < 0.08:
            return
        self.last_level_event_at = now
        self.ui_queue.put(("input_level", self._audio_peak_percent(audio)))

    def _set_input_level(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.input_level_var.set(value)
        self.input_level_text_var.set(f"Уровень: {value}%")

    def _selected_model_path(self) -> Path:
        return MODEL_FILES.get(self._selected_model_key(), MODEL_OPTIONS[DEFAULT_MODEL_LABEL])

    def _recognize_audio(self) -> None:
        wav_path: Path | None = None
        out_base: Path | None = None
        txt_path: Path | None = None
        started_at = time.perf_counter()

        try:
            with tempfile.NamedTemporaryFile(prefix="voicehelper_", suffix=".wav", delete=False) as wav_file:
                wav_path = Path(wav_file.name)

            selected_model = self._selected_model_path()
            if not available_whisper_backends():
                expected = "\n".join(str(path) for path in WHISPER_BACKENDS.values())
                raise RuntimeError(f"missing-whisper-cli::{expected}")
            if not selected_model.exists():
                raise RuntimeError(f"missing-model::{selected_model}")

            sample_rate = self.record_sample_rate or SAMPLE_RATE
            audio_bytes, vad_stats = self._trim_silence(b"".join(self.audio_chunks), sample_rate)
            audio_ms = len(audio_bytes) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000
            if audio_ms < MIN_AUDIO_MS:
                raise RuntimeError("silent-or-short-recording")

            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav.setframerate(sample_rate)
                wav.writeframes(audio_bytes)

            out_base = Path(tempfile.gettempdir()) / f"{wav_path.stem}_out"
            txt_path = out_base.with_suffix(".txt")
            if txt_path.exists():
                txt_path.unlink()

            backend_name, completed = run_whisper_with_fallback(selected_model, wav_path, out_base)

            elapsed = time.perf_counter() - started_at

            if not txt_path.exists():
                raise RuntimeError("missing-recognition-output")

            recognized = txt_path.read_text(encoding="utf-8").strip()
            self.ui_queue.put(("recognized", (recognized, elapsed, backend_name, vad_stats)))
        except Exception as exc:
            self.ui_queue.put(("error", self._format_recognition_error(exc)))
        finally:
            self.audio_chunks = []
            for path in (wav_path, txt_path):
                if path and path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass
            self.ui_queue.put(("ready", None))

    def _process_ui_queue(self) -> None:
        while True:
            try:
                event, value = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if event == "status":
                self._set_status(str(value))
            elif event == "input_level":
                self._set_input_level(int(value))
            elif event == "recognized":
                recognized, elapsed, backend_name, vad_stats = value
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", str(recognized))
                self.recognition_time_var.set(f"Распознавание: {elapsed:.1f} с")
                self._update_speed_status(vad_stats=vad_stats, backend_name=backend_name)
                self._set_status("Готово")
                self._schedule_spellcheck(delay_ms=100)
            elif event == "error":
                self._set_status("Ошибка распознавания")
                messagebox.showerror("VoiceHelper", str(value))
            elif event == "ready":
                self.is_recognizing = False
                self.record_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.profile_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.input_device_box.configure(state="readonly")
                self.refresh_input_button.configure(state=tk.NORMAL)
                self.test_input_button.configure(state=tk.NORMAL)
            elif event == "benchmark_result":
                profile = value
                selected_model = profile.get("selected_model", FALLBACK_AUTO_MODEL_KEY)
                self.profile_var.set(DEFAULT_PROFILE_LABEL)
                self._select_model_key(selected_model)
                self._update_speed_status()
                self._set_status(f"Бенчмарк готов: выбрана модель {selected_model}")
            elif event == "benchmark_error":
                self._set_status("Ошибка бенчмарка")
                messagebox.showerror("VoiceHelper", str(value))
            elif event == "benchmark_ready":
                self.is_benchmarking = False
                self.record_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.profile_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.input_device_box.configure(state="readonly")
                self.refresh_input_button.configure(state=tk.NORMAL)
                self.test_input_button.configure(state=tk.NORMAL)
            elif event == "firewall_status":
                if value is True:
                    self.firewall_status_var.set("Сеть: заблокирована")
                    self.firewall_button.configure(state=tk.DISABLED)
                    self.firewall_unblock_button.configure(state=tk.NORMAL)
                elif value is False:
                    self.firewall_status_var.set("Сеть: не заблокирована")
                    self.firewall_button.configure(state=tk.NORMAL)
                    self.firewall_unblock_button.configure(state=tk.DISABLED)
                else:
                    self.firewall_status_var.set("Сеть: не удалось проверить")
                    self.firewall_button.configure(state=tk.NORMAL)
                    self.firewall_unblock_button.configure(state=tk.NORMAL)
            elif event == "spelling_result":
                generation, issues, error = value
                if generation != self.spellcheck_generation:
                    continue
                if error:
                    self._clear_spelling_marks()
                    self.spellcheck_status_var.set("Орфография: недоступна")
                else:
                    self._apply_spelling_issues(issues)
                    count = len(issues)
                    self.spellcheck_status_var.set(f"Орфография: {count} ошибок" if count else "Орфография: ошибок нет")
            elif event == "spelling_word_added":
                self.spellcheck_status_var.set(f"Орфография: слово добавлено")
                self._schedule_spellcheck(delay_ms=150)
            elif event == "spelling_add_error":
                self.spellcheck_status_var.set("Орфография: не удалось добавить")

        self.root.after(100, self._process_ui_queue)

    def _update_record_timer(self) -> None:
        if self.is_recording and self.record_started_at is not None:
            elapsed = int(time.perf_counter() - self.record_started_at)
            minutes, seconds = divmod(elapsed, 60)
            self.record_time_var.set(f"Запись: {minutes:02d}:{seconds:02d}")
        elif not self.is_recording and not self.is_recognizing:
            self.record_started_at = None
        self.root.after(250, self._update_record_timer)

    def _format_problem_message(
        self,
        summary: str,
        steps: list[str],
        details: str | None = None,
        technical: str | None = None,
    ) -> str:
        parts = [summary.strip()]
        if details:
            parts.extend(["", details.strip()])
        if steps:
            parts.append("")
            parts.append("Что сделать:")
            parts.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
        if technical:
            parts.append("")
            parts.append("Технические детали:")
            parts.append(str(technical).strip())
        return "\n".join(parts)

    def _format_microphone_error(self, summary: str, exc: Exception, include_diagnostics: bool = False) -> str:
        selected = self.input_device_var.get() or "не выбран"
        technical = str(exc).strip()
        steps = [
            "Проверьте, что микрофон подключен и выбран в строке Микрофон.",
            "Нажмите Обновить, затем Проверить.",
            "Закройте программы, которые могут занимать микрофон: браузер, Teams, Zoom, диктофон.",
            "Проверьте доступ к микрофону в настройках конфиденциальности Windows.",
        ]
        if include_diagnostics:
            steps.append("Если ошибка повторяется, запустите scripts\\diagnose_voicehelper.cmd и пришлите отчет из папки diagnostics.")

        return self._format_problem_message(
            summary,
            steps,
            details=f"Выбранный микрофон: {selected}",
            technical=self._shorten_technical_text(technical),
        )

    def _format_recognition_error(self, exc: Exception) -> str:
        raw = str(exc).strip()

        if raw == "silent-or-short-recording":
            return self._format_problem_message(
                "Запись слишком короткая или похожа на тишину.",
                [
                    "Говорите не меньше 1-2 секунд после нажатия Записать.",
                    "Перед записью нажмите Проверить и убедитесь, что индикатор уровня двигается.",
                    "Проверьте уровень входа микрофона в Windows и физическую кнопку mute.",
                ],
            )

        if raw.startswith("missing-whisper-cli::"):
            path = raw.split("::", 1)[1]
            return self._format_problem_message(
                "Не найден локальный движок распознавания whisper-cli.exe.",
                [
                    "Запускайте VoiceHelper из полной распакованной папки.",
                    "Проверьте, что рядом есть папка .tools.",
                    "Если это GitHub artifact, распакуйте ZIP целиком.",
                    "Запустите scripts\\diagnose_voicehelper.cmd для проверки состава папки.",
                ],
                technical=path,
            )

        if raw.startswith("missing-model::"):
            path = raw.split("::", 1)[1]
            return self._format_problem_message(
                "Не найдена выбранная локальная модель Whisper.",
                [
                    "Запускайте VoiceHelper из полной распакованной папки.",
                    "Проверьте, что рядом есть папка models.",
                    "Выберите другую модель в списке и повторите запись.",
                    "Запустите scripts\\diagnose_voicehelper.cmd для проверки состава папки.",
                ],
                technical=path,
            )

        if raw.startswith("whisper-failed::"):
            _, code, technical = raw.split("::", 2)
            return self._format_problem_message(
                "Локальный движок распознавания завершился с ошибкой.",
                [
                    "Повторите запись короткой фразой.",
                    "Проверьте, что модель выбрана и папка VoiceHelper распакована целиком.",
                    "Запустите scripts\\diagnose_voicehelper.cmd и пришлите отчет, если ошибка повторяется.",
                ],
                details=f"Код завершения whisper-cli: {code}",
                technical=self._shorten_technical_text(technical or "stderr/stdout пустой"),
            )

        if raw == "missing-recognition-output":
            return self._format_problem_message(
                "Распознавание завершилось, но файл с текстом не появился.",
                [
                    "Повторите запись.",
                    "Проверьте, что антивирус или EDR не блокирует временные файлы в TEMP.",
                    "Запустите scripts\\diagnose_voicehelper.cmd и пришлите отчет.",
                ],
            )

        return self._format_problem_message(
            "Не удалось распознать запись.",
            [
                "Повторите запись короткой фразой.",
                "Если ошибка повторяется, запустите scripts\\diagnose_voicehelper.cmd.",
            ],
            technical=self._shorten_technical_text(raw),
        )

    def _shorten_technical_text(self, value: str, limit: int = 1200) -> str:
        value = value.strip()
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + "\n... обрезано, полный вывод смотрите в диагностике."

    def _set_status(self, value: str) -> None:
        self.status_var.set(value)

    def _firewall_target_path(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve()

        packaged = APP_DIR / "dist" / "VoiceHelper" / "VoiceHelper.exe"
        if packaged.exists():
            return packaged.resolve()
        return Path(sys.executable).resolve()

    def _is_firewall_block_enabled(self) -> bool | None:
        target = str(self._firewall_target_path()).lower()
        try:
            completed = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE_NAME}", "verbose"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except Exception:
            return None

        if completed.returncode != 0:
            return False

        output = completed.stdout.decode("mbcs", errors="replace").lower()
        return target in output

    def _write_firewall_script(self, target: Path, remove: bool = False) -> Path:
        target_text = str(target)
        action = "remove" if remove else "enable"
        script_path = Path(tempfile.gettempdir()) / f"voicehelper_{action}_firewall.cmd"
        log_path = Path(tempfile.gettempdir()) / "voicehelper_firewall.log"

        if remove:
            content = f"""@echo off
setlocal
set "LOG={log_path}"
echo VoiceHelper firewall remove started > "%LOG%"
echo Program: {target_text} >> "%LOG%"
netsh advfirewall firewall delete rule name="{FIREWALL_RULE_NAME}" program="{target_text}" dir=out >> "%LOG%" 2>&1
echo ExitCode: %ERRORLEVEL% >> "%LOG%"
del "%~f0" >nul 2>nul
"""
        else:
            content = f"""@echo off
setlocal
set "LOG={log_path}"
echo VoiceHelper firewall enable started > "%LOG%"
echo Program: {target_text} >> "%LOG%"
netsh advfirewall firewall delete rule name="{FIREWALL_RULE_NAME}" program="{target_text}" dir=out >> "%LOG%" 2>&1
netsh advfirewall firewall add rule name="{FIREWALL_RULE_NAME}" dir=out action=block program="{target_text}" enable=yes profile=any description="VoiceHelper confidentiality control: block outbound network access." >> "%LOG%" 2>&1
echo ExitCode: %ERRORLEVEL% >> "%LOG%"
del "%~f0" >nul 2>nul
"""
        script_path.write_text(content, encoding="mbcs")
        return script_path

    def _run_cmd_elevated(self, script_path: Path) -> None:
        params = f'/c "{script_path}"'
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "cmd.exe",
            params,
            None,
            1,
        )
        if result <= 32:
            raise RuntimeError(f"Windows отказала в запуске с повышенными правами. Код ShellExecute: {result}")

    def _trim_silence(self, audio: bytes, sample_rate: int) -> tuple[bytes, dict]:
        stats = {
            "mode": "simple-vad",
            "original_ms": 0.0,
            "trimmed_ms": 0.0,
            "reduction_percent": 0.0,
            "segments": 0,
        }
        if not audio:
            return audio, stats

        original_ms = len(audio) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000
        stats["original_ms"] = original_ms

        frame_bytes = max(SAMPLE_WIDTH_BYTES, sample_rate * SAMPLE_WIDTH_BYTES * VAD_FRAME_MS // 1000)
        frame_bytes -= frame_bytes % SAMPLE_WIDTH_BYTES
        if frame_bytes <= 0:
            return audio, stats

        frames: list[tuple[int, int, float, int]] = []
        for start in range(0, len(audio), frame_bytes):
            end = min(start + frame_bytes, len(audio))
            window = audio[start:end]
            if len(window) < SAMPLE_WIDTH_BYTES:
                continue
            samples = memoryview(window).cast("h")
            if not samples:
                continue
            peak = max(abs(sample) for sample in samples)
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            frames.append((start, end, rms, peak))

        if not frames:
            return b"", stats

        sorted_rms = sorted(frame[2] for frame in frames)
        quiet_count = max(1, len(sorted_rms) // 5)
        noise_floor = sum(sorted_rms[:quiet_count]) / quiet_count
        threshold = max(VAD_MIN_RMS, noise_floor * VAD_NOISE_MULTIPLIER)
        raw_speech = [(rms >= threshold or peak >= VAD_MIN_PEAK) for _start, _end, rms, peak in frames]

        hangover_frames = max(1, VAD_PADDING_MS // VAD_FRAME_MS)
        speech = raw_speech[:]
        for index, is_speech in enumerate(raw_speech):
            if not is_speech:
                continue
            left = max(0, index - hangover_frames)
            right = min(len(speech), index + hangover_frames + 1)
            for padded_index in range(left, right):
                speech[padded_index] = True

        segments: list[tuple[int, int]] = []
        start_index: int | None = None
        for index, is_speech in enumerate(speech):
            if is_speech and start_index is None:
                start_index = index
            elif not is_speech and start_index is not None:
                segments.append((start_index, index - 1))
                start_index = None
        if start_index is not None:
            segments.append((start_index, len(speech) - 1))

        if not segments:
            legacy = self._trim_silence_by_peak(audio, sample_rate)
            stats["mode"] = "peak-fallback"
            stats["trimmed_ms"] = len(legacy) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000
            if original_ms > 0:
                stats["reduction_percent"] = max(0.0, (1 - stats["trimmed_ms"] / original_ms) * 100)
            stats["segments"] = 1 if legacy else 0
            return legacy, stats

        max_gap_frames = max(1, VAD_MAX_INTERNAL_SILENCE_MS // VAD_FRAME_MS)
        merged: list[tuple[int, int]] = []
        for segment_start, segment_end in segments:
            if not merged:
                merged.append((segment_start, segment_end))
                continue
            prev_start, prev_end = merged[-1]
            if segment_start - prev_end - 1 <= max_gap_frames:
                merged[-1] = (prev_start, segment_end)
            else:
                merged.append((segment_start, segment_end))

        parts: list[bytes] = []
        padding_frames = max(1, VAD_PADDING_MS // VAD_FRAME_MS)
        for segment_start, segment_end in merged:
            padded_start = max(0, segment_start - padding_frames)
            padded_end = min(len(frames) - 1, segment_end + padding_frames)
            byte_start = frames[padded_start][0]
            byte_end = frames[padded_end][1]
            byte_start -= byte_start % SAMPLE_WIDTH_BYTES
            byte_end -= byte_end % SAMPLE_WIDTH_BYTES
            parts.append(audio[byte_start:byte_end])

        trimmed = b"".join(parts)
        trimmed_ms = len(trimmed) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000
        stats["trimmed_ms"] = trimmed_ms
        stats["reduction_percent"] = max(0.0, (1 - trimmed_ms / original_ms) * 100) if original_ms > 0 else 0.0
        stats["segments"] = len(merged)
        stats["threshold"] = round(threshold, 1)
        return trimmed, stats

    def _trim_silence_by_peak(self, audio: bytes, sample_rate: int) -> bytes:
        bytes_per_ms = sample_rate * SAMPLE_WIDTH_BYTES // 1000
        window_size = max(SAMPLE_WIDTH_BYTES, bytes_per_ms * SILENCE_WINDOW_MS)
        window_size -= window_size % SAMPLE_WIDTH_BYTES
        padding = bytes_per_ms * SILENCE_PADDING_MS
        padding -= padding % SAMPLE_WIDTH_BYTES

        speech_start: int | None = None
        speech_end: int | None = None

        for start in range(0, len(audio), window_size):
            end = min(start + window_size, len(audio))
            window = audio[start:end]
            if len(window) < SAMPLE_WIDTH_BYTES:
                continue

            samples = memoryview(window).cast("h")
            peak = max(abs(sample) for sample in samples)
            if peak >= SILENCE_PEAK_THRESHOLD:
                if speech_start is None:
                    speech_start = start
                speech_end = end

        if speech_start is None or speech_end is None:
            return b""

        trim_start = max(0, speech_start - padding)
        trim_end = min(len(audio), speech_end + padding)
        trim_start -= trim_start % SAMPLE_WIDTH_BYTES
        trim_end -= trim_end % SAMPLE_WIDTH_BYTES
        return audio[trim_start:trim_end]


def main() -> None:
    if "--audio-devices" in sys.argv:
        print(f"default={sd.default.device}")
        print(sd.query_devices())
        raise SystemExit(0)

    if "--spell-test" in sys.argv:
        issues = check_text("тест превет", language_tag="ru-RU")
        print(f"issues={[(issue.word, issue.suggestions[:3]) for issue in issues]}")
        if not any(issue.word == "превет" for issue in issues):
            print("VoiceHelper spell-test note: test word is not flagged; it may already be in the user dictionary.")
        print("VoiceHelper spell-test passed.")
        raise SystemExit(0)

    if "--benchmark-models" in sys.argv:
        allow_missing_models = "--allow-missing-models" in sys.argv
        profile = run_model_benchmark(allow_missing_models=allow_missing_models, print_fn=print)
        print(f"selected_model={profile.get('selected_model', FALLBACK_AUTO_MODEL_KEY)}")
        print(f"profile={PERFORMANCE_PROFILE_PATH}")
        if not any(item.get("ok") for item in profile.get("results", {}).values()):
            raise SystemExit(1)
        raise SystemExit(0)

    if "--self-test" in sys.argv:
        allow_missing_models = "--allow-missing-models" in sys.argv
        required = [WHISPER_EXE] if allow_missing_models else [WHISPER_EXE, *MODEL_OPTIONS.values()]
        missing = [path for path in required if not path.exists()]
        if missing:
            print("VoiceHelper self-test failed. Missing files:")
            for path in missing:
                print(path)
            raise SystemExit(1)
        if allow_missing_models:
            missing_models = [path for path in MODEL_OPTIONS.values() if not path.exists()]
            if missing_models:
                print("VoiceHelper self-test warning: models are not included in this code-only package.")
                for path in missing_models:
                    print(path)
        print("VoiceHelper self-test passed.")
        print(f"APP_DIR={APP_DIR}")
        print(f"APP_ICON={APP_ICON}")
        print(f"WHISPER_BACKENDS={[(name, str(path), path.exists()) for name, path in WHISPER_BACKENDS.items()]}")
        print(f"PERFORMANCE_PROFILE={PERFORMANCE_PROFILE_PATH}")
        raise SystemExit(0)

    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    VoiceHelperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
