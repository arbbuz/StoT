import queue
import ctypes
import ctypes.wintypes
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from array import array
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
    "vulkan": APP_DIR / ".tools" / "whisper.cpp-build-vulkan" / "bin" / "whisper-cli.exe",
    "cuda": APP_DIR / ".tools" / "whisper.cpp-build-cuda" / "bin" / "whisper-cli.exe",
    "openvino": APP_DIR / ".tools" / "whisper.cpp-build-openvino" / "bin" / "whisper-cli.exe",
    "avx2": APP_DIR / ".tools" / "whisper.cpp-build-avx2" / "bin" / "whisper-cli.exe",
    "compat": APP_DIR / ".tools" / "whisper.cpp-build-compat" / "bin" / "whisper-cli.exe",
}
DISABLED_WHISPER_BACKENDS: set[str] = set()
WHISPER_EXE = WHISPER_BACKENDS["compat"]
BACKEND_LABELS = {
    "auto": "Авто",
    "vulkan": "Vulkan",
    "cuda": "CUDA",
    "openvino": "OpenVINO",
    "avx2": "AVX2",
    "compat": "Compat",
}
BACKEND_KEY_BY_LABEL = {label: key for key, label in BACKEND_LABELS.items()}
DEFAULT_BACKEND_LABEL = BACKEND_LABELS["auto"]
FALLBACK_AUTO_BACKEND_KEY = "compat"
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
INPUT_SAMPLE_RATE_FALLBACKS = (48000, 44100, 32000)
MICROPHONE_PROBE_SECONDS = 1.5
MICROPHONE_WORKING_PEAK_PERCENT = 3
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
DEFAULT_WHISPER_THREADS = 4
GPU_BACKEND_KEYS = {"vulkan", "cuda", "openvino"}
BACKEND_BENCHMARK_THREAD_COUNTS = {
    "gpu": (1, 2, 4, 6, 8),
    "cpu": (2, 4, 6, 8, 12),
}
FIREWALL_RULE_NAME = "Dicta Block Outbound"
HOTKEY_LABEL = "Ctrl+Shift+Space"
HOTKEY_ID = 1
HOTKEY_MODIFIERS = 0x0002 | 0x0004
HOTKEY_MOD_NOREPEAT = 0x4000
HOTKEY_VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
DEFAULT_USER_SETTINGS = {
    "auto_copy": False,
    "format_text": True,
    "voice_punctuation": True,
    "backend": "auto",
}


def clean_input_device_name(name: str) -> str:
    return " ".join(name.replace("  ", " ").strip().split())


def is_system_input_alias(name: str) -> bool:
    normalized = name.lower()
    aliases = (
        "microsoft sound mapper",
        "primary sound capture",
        "первичный драйвер записи",
    )
    return any(alias in normalized for alias in aliases)


def is_low_level_input_backend(hostapi_name: str) -> bool:
    return "wdm-ks" in hostapi_name.lower()


def input_device_hostapi_name(device: dict, hostapis: object | None = None) -> str:
    try:
        if hostapis is None:
            hostapis = sd.query_hostapis()
        return str(hostapis[int(device["hostapi"])]["name"])
    except Exception:
        return ""


def input_device_default_sample_rate(device_index: int) -> int:
    try:
        device = sd.query_devices(device_index, "input")
        sample_rate = int(float(device.get("default_samplerate", SAMPLE_RATE)))
        return sample_rate if sample_rate > 0 else SAMPLE_RATE
    except Exception:
        return SAMPLE_RATE


def input_device_sample_rates(device_index: int) -> list[int]:
    candidates = [
        SAMPLE_RATE,
        input_device_default_sample_rate(device_index),
        *INPUT_SAMPLE_RATE_FALLBACKS,
    ]
    sample_rates: list[int] = []
    for sample_rate in candidates:
        try:
            sample_rate = int(sample_rate)
        except Exception:
            continue
        if sample_rate > 0 and sample_rate not in sample_rates:
            sample_rates.append(sample_rate)
    return sample_rates or [SAMPLE_RATE]


def input_device_channel_counts(device_index: int) -> list[int]:
    try:
        device = sd.query_devices(device_index, "input")
        max_channels = int(device.get("max_input_channels", 0))
    except Exception:
        max_channels = 0

    channel_counts = [CHANNELS]
    if max_channels >= 2 and 2 not in channel_counts:
        channel_counts.append(2)
    return channel_counts


def input_device_priority(device_index: int) -> int:
    try:
        device = sd.query_devices(device_index, "input")
        hostapi_name = input_device_hostapi_name(device).lower()
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


def describe_input_device(device_index: int) -> str:
    try:
        device = sd.query_devices(device_index, "input")
        name = clean_input_device_name(str(device.get("name", f"device {device_index}")))
        hostapi_name = input_device_hostapi_name(device)
    except Exception:
        return f"device {device_index}"
    return f"#{device_index} {name}" + (f" [{hostapi_name}]" if hostapi_name else "")


def collect_input_device_groups() -> tuple[list[str], dict[str, list[int]], int | None]:
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    default_input = None
    try:
        candidate = sd.default.device[0]
        if isinstance(candidate, int) and candidate >= 0:
            default_input = candidate
    except Exception:
        default_input = None

    visible_grouped: dict[str, list[int]] = {}
    fallback_grouped: dict[str, list[int]] = {}
    device_is_default: dict[str, bool] = {}

    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        name = str(device.get("name", ""))
        if is_system_input_alias(name):
            continue
        hostapi_name = input_device_hostapi_name(device, hostapis)
        display_name = clean_input_device_name(name)
        if not display_name:
            display_name = f"device {index}"

        if is_low_level_input_backend(hostapi_name):
            fallback_grouped.setdefault(display_name, []).append(index)
        else:
            visible_grouped.setdefault(display_name, []).append(index)

        if index == default_input:
            device_is_default[display_name] = True

    input_devices: dict[str, list[int]] = {}
    labels: list[str] = []

    def sort_names(names: list[str]) -> list[str]:
        return sorted(names, key=lambda name: (not device_is_default.get(name, False), name.lower()))

    def add_group(name: str, indexes: list[int], fallback_only: bool = False) -> None:
        unique_indexes: list[int] = []
        for index in indexes:
            if index not in unique_indexes:
                unique_indexes.append(index)
        unique_indexes.sort(key=input_device_priority)
        marker = " (по умолчанию)" if device_is_default.get(name, False) else ""
        fallback_marker = " (тех. fallback)" if fallback_only else ""
        label = f"{name}{marker}{fallback_marker}"
        labels.append(label)
        input_devices[label] = unique_indexes

    if visible_grouped:
        for name in sort_names(list(visible_grouped)):
            visible_indexes = sorted(visible_grouped[name], key=input_device_priority)
            fallback_indexes = sorted(fallback_grouped.get(name, []), key=input_device_priority)
            add_group(name, visible_indexes + fallback_indexes)

        fallback_only_names = [name for name in fallback_grouped if name not in visible_grouped]
        for name in sort_names(fallback_only_names):
            add_group(name, fallback_grouped[name], fallback_only=True)
    else:
        for name in sort_names(list(fallback_grouped)):
            add_group(name, fallback_grouped[name])

    return labels, input_devices, default_input


def downmix_pcm16_to_mono(audio: bytes, source_channels: int) -> bytes:
    if source_channels <= CHANNELS:
        return bytes(audio)

    frame_width = SAMPLE_WIDTH_BYTES * source_channels
    usable_length = len(audio) - (len(audio) % frame_width)
    if usable_length < frame_width:
        return b""

    samples = memoryview(audio[:usable_length]).cast("h")
    mono = array("h")
    for start in range(0, len(samples), source_channels):
        total = 0
        for offset in range(source_channels):
            total += int(samples[start + offset])
        mono.append(int(total / source_channels))
    return mono.tobytes()


def audio_peak_percent(audio: bytes) -> int:
    if len(audio) < SAMPLE_WIDTH_BYTES:
        return 0
    try:
        samples = memoryview(audio).cast("h")
        peak = max(abs(sample) for sample in samples)
    except Exception:
        return 0
    return min(100, int(round(peak * 100 / 32767)))


def input_stream_config_text(config: dict | None) -> str:
    if not config:
        return "режим неизвестен"
    source_channels = int(config.get("source_channels", CHANNELS))
    channel_text = "1 канал" if source_channels == 1 else f"{source_channels}->1 канал"
    return f"{config.get('description', 'device')}, {config.get('sample_rate', SAMPLE_RATE)} Hz, {channel_text}"


def _mono_input_callback(callback, source_channels: int):
    def wrapper(indata, frames, time_info, status) -> None:
        data = bytes(indata)
        if source_channels > CHANNELS:
            data = downmix_pcm16_to_mono(data, source_channels)
        callback(data, frames, time_info, status)

    return wrapper


def open_dicta_input_stream(device_indexes: list[int], callback, start: bool = False) -> tuple[sd.RawInputStream, dict]:
    if not device_indexes:
        raise RuntimeError("Не найден доступный микрофон в списке Dicta.")

    errors: list[str] = []
    for device_index in device_indexes:
        description = describe_input_device(device_index)
        for sample_rate in input_device_sample_rates(device_index):
            for source_channels in input_device_channel_counts(device_index):
                try:
                    stream = sd.RawInputStream(
                        device=device_index,
                        samplerate=sample_rate,
                        channels=source_channels,
                        dtype="int16",
                        callback=_mono_input_callback(callback, source_channels),
                    )
                    config = {
                        "device_index": device_index,
                        "description": description,
                        "sample_rate": sample_rate,
                        "source_channels": source_channels,
                        "channels": CHANNELS,
                    }
                    if start:
                        try:
                            stream.start()
                        except Exception as exc:
                            errors.append(f"{description}, {sample_rate} Hz, {source_channels} ch start: {exc}")
                            try:
                                stream.close()
                            except Exception:
                                pass
                            continue
                    return stream, config
                except Exception as exc:
                    errors.append(f"{description}, {sample_rate} Hz, {source_channels} ch open: {exc}")

    raise RuntimeError("\n".join(errors[-12:]) or "Не удалось открыть выбранный микрофон.")


def probe_input_device_group(
    device_indexes: list[int],
    seconds: float = MICROPHONE_PROBE_SECONDS,
    level_callback=None,
) -> dict:
    peak = 0
    stream_statuses: list[str] = []
    lock = threading.Lock()
    stream: sd.RawInputStream | None = None
    config: dict | None = None

    def callback(indata, frames, time_info, status) -> None:
        nonlocal peak
        if status:
            with lock:
                stream_statuses.append(str(status))
        level = audio_peak_percent(bytes(indata))
        with lock:
            peak = max(peak, level)
        if level_callback is not None:
            level_callback(level)

    try:
        stream, config = open_dicta_input_stream(device_indexes, callback, start=True)
        deadline = time.perf_counter() + max(0.2, float(seconds))
        while time.perf_counter() < deadline:
            time.sleep(0.05)
        with lock:
            peak_value = peak
            status_text = "; ".join(stream_statuses[-3:])
        return {
            "ok": peak_value >= MICROPHONE_WORKING_PEAK_PERCENT,
            "opened": True,
            "status": "working" if peak_value >= MICROPHONE_WORKING_PEAK_PERCENT else "silent",
            "peak": peak_value,
            "config": config,
            "stream_status": status_text,
            "seconds": seconds,
        }
    except Exception as exc:
        return {
            "ok": False,
            "opened": False,
            "status": "failed",
            "peak": 0,
            "error": str(exc),
            "seconds": seconds,
        }
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


def print_audio_devices() -> None:
    print(f"default={sd.default.device}")
    labels, input_devices, _default_input = collect_input_device_groups()
    print("")
    print("Dicta grouped input devices:")
    if not labels:
        print("  no input devices")
    for label in labels:
        indexes = ", ".join(describe_input_device(index) for index in input_devices[label])
        print(f"  {label}: {indexes}")
    print("")
    print("Open modes tried for each device:")
    print(f"  sample rates: {SAMPLE_RATE}, default, {', '.join(str(rate) for rate in INPUT_SAMPLE_RATE_FALLBACKS)}")
    print("  channels: 1, then 2 with downmix to mono when available")
    print("")
    print("Raw PortAudio devices:")
    print(sd.query_devices())


def run_microphone_diagnostics(seconds: float = MICROPHONE_PROBE_SECONDS, print_fn=print) -> list[dict]:
    labels, input_devices, _default_input = collect_input_device_groups()
    print_fn(f"Microphone diagnostics: {seconds:.1f}s per grouped device")
    print_fn(f"Working threshold: peak >= {MICROPHONE_WORKING_PEAK_PERCENT}%")
    print_fn("")

    if not labels:
        print_fn("No input devices found.")
        return []

    results: list[dict] = []
    selected: dict | None = None
    selected_label: str | None = None
    best_opened: dict | None = None
    best_opened_label: str | None = None

    for position, label in enumerate(labels, start=1):
        print_fn(f"[{position}/{len(labels)}] {label}")
        print_fn(f"  devices: {', '.join(describe_input_device(index) for index in input_devices[label])}")
        result = probe_input_device_group(input_devices[label], seconds=seconds)
        result["label"] = label
        results.append(result)

        if result.get("opened"):
            print_fn(f"  opened: {input_stream_config_text(result.get('config'))}")
            print_fn(f"  peak:   {result.get('peak', 0)}% ({result.get('status')})")
            if result.get("stream_status"):
                print_fn(f"  status: {result.get('stream_status')}")
            if best_opened is None or int(result.get("peak", 0)) > int(best_opened.get("peak", 0)):
                best_opened = result
                best_opened_label = label
        else:
            print_fn("  failed:")
            for line in str(result.get("error", "")).splitlines()[-12:]:
                print_fn(f"    {line}")

        if result.get("ok") and selected is None:
            selected = result
            selected_label = label
        print_fn("")

    if selected is not None:
        print_fn(f"Selected working microphone: {selected_label}")
        print_fn(f"  {input_stream_config_text(selected.get('config'))}")
        print_fn(f"  peak: {selected.get('peak', 0)}%")
    elif best_opened is not None:
        print_fn(f"No microphone reached the working threshold. Best opened device: {best_opened_label}")
        print_fn(f"  {input_stream_config_text(best_opened.get('config'))}")
        print_fn(f"  peak: {best_opened.get('peak', 0)}%")
    else:
        print_fn("No microphone could be opened.")

    return results


def performance_profile_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Dicta" / "performance_profile.json"
    return APP_DIR / "performance_profile.json"


PERFORMANCE_PROFILE_PATH = performance_profile_path()


def backend_profile_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Dicta" / "backend_profile.json"
    return APP_DIR / "backend_profile.json"


BACKEND_PROFILE_PATH = backend_profile_path()


def user_settings_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Dicta" / "settings.json"
    return APP_DIR / "settings.json"


USER_SETTINGS_PATH = user_settings_path()


def is_whisper_backend_available(backend_name: str) -> bool:
    path = WHISPER_BACKENDS.get(backend_name)
    return bool(path and path.exists() and backend_name not in DISABLED_WHISPER_BACKENDS)


def load_backend_profile() -> dict:
    try:
        if BACKEND_PROFILE_PATH.exists():
            return json.loads(BACKEND_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def save_backend_profile(data: dict) -> None:
    BACKEND_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKEND_PROFILE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_positive_int(value: object) -> int | None:
    try:
        number = int(value)
    except Exception:
        return None
    if number < 1:
        return None
    return min(number, 64)


def sanitize_whisper_threads(value: object | None, default: int = DEFAULT_WHISPER_THREADS) -> int:
    return parse_positive_int(value) or default


def backend_thread_candidates(backend_name: str) -> list[int]:
    cpu_count = max(1, os.cpu_count() or DEFAULT_WHISPER_THREADS)
    profile = "gpu" if backend_name in GPU_BACKEND_KEYS else "cpu"
    configured = BACKEND_BENCHMARK_THREAD_COUNTS[profile]
    candidates = [threads for threads in configured if threads <= cpu_count]
    if not candidates:
        candidates = [1]
    return sorted(set(candidates))


def choose_backend_threads_from_results(backend_name: str, results: dict | None = None) -> int:
    item = results.get(backend_name) if isinstance(results, dict) else None
    if not isinstance(item, dict):
        return DEFAULT_WHISPER_THREADS

    selected_threads = parse_positive_int(item.get("selected_threads"))
    if selected_threads:
        return selected_threads

    legacy_threads = parse_positive_int(item.get("threads"))
    if legacy_threads:
        return legacy_threads

    thread_results = item.get("thread_results")
    if not isinstance(thread_results, dict):
        return DEFAULT_WHISPER_THREADS

    best_threads: int | None = None
    best_elapsed: float | None = None
    for thread_key, thread_item in thread_results.items():
        if not isinstance(thread_item, dict) or not thread_item.get("ok"):
            continue
        try:
            elapsed = float(thread_item["elapsed_seconds"])
        except Exception:
            continue
        threads = parse_positive_int(thread_item.get("threads")) or parse_positive_int(thread_key)
        if threads is None:
            continue
        if best_elapsed is None or elapsed < best_elapsed:
            best_threads = threads
            best_elapsed = elapsed

    return best_threads or DEFAULT_WHISPER_THREADS


def choose_backend_threads(backend_name: str, profile: dict | None = None) -> int:
    if profile is None:
        profile = load_backend_profile()

    if isinstance(profile, dict) and profile.get("selected_backend") == backend_name:
        selected_threads = parse_positive_int(profile.get("selected_threads"))
        if selected_threads:
            return selected_threads

    results = profile.get("results", {}) if isinstance(profile, dict) else {}
    return choose_backend_threads_from_results(backend_name, results)


def choose_auto_backend_key(results: dict | None = None) -> str:
    if results is None:
        selected = load_backend_profile().get("selected_backend")
        if isinstance(selected, str) and is_whisper_backend_available(selected):
            return selected
        results = load_backend_profile().get("results", {})

    best_backend: str | None = None
    best_elapsed: float | None = None
    for backend_name in WHISPER_BACKENDS:
        item = results.get(backend_name) if isinstance(results, dict) else None
        if not isinstance(item, dict) or not item.get("ok"):
            continue
        try:
            elapsed = float(item["elapsed_seconds"])
        except Exception:
            continue
        if best_elapsed is None or elapsed < best_elapsed:
            best_backend = backend_name
            best_elapsed = elapsed

    if best_backend and is_whisper_backend_available(best_backend):
        return best_backend
    for backend_name in WHISPER_BACKENDS:
        if is_whisper_backend_available(backend_name):
            return backend_name
    return FALLBACK_AUTO_BACKEND_KEY


def available_whisper_backends(preferred_backend_key: str | None = None) -> list[tuple[str, Path]]:
    available = [(name, path) for name, path in WHISPER_BACKENDS.items() if is_whisper_backend_available(name)]
    if not available:
        return []

    priority: list[str] = []
    if preferred_backend_key and preferred_backend_key != "auto":
        priority.append(preferred_backend_key)
    else:
        priority.append(choose_auto_backend_key())
    priority.extend(WHISPER_BACKENDS.keys())

    ordered: list[tuple[str, Path]] = []
    seen: set[str] = set()
    available_by_name = dict(available)
    for backend_name in priority:
        if backend_name in seen or backend_name not in available_by_name:
            continue
        ordered.append((backend_name, available_by_name[backend_name]))
        seen.add(backend_name)
    return ordered


def build_whisper_command(
    exe_path: Path,
    model_path: Path,
    wav_path: Path,
    out_base: Path,
    threads: int = DEFAULT_WHISPER_THREADS,
) -> list[str]:
    threads = sanitize_whisper_threads(threads)
    return [
        str(exe_path),
        "-m",
        str(model_path),
        "-f",
        str(wav_path),
        "-l",
        "ru",
        "-t",
        str(threads),
        "-nt",
        "-np",
        "-nf",
        "-otxt",
        "-of",
        str(out_base),
    ]


def decode_process_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def run_whisper_backend(
    backend_name: str,
    exe_path: Path,
    model_path: Path,
    wav_path: Path,
    out_base: Path,
    timeout_seconds: int | None = None,
    threads: int = DEFAULT_WHISPER_THREADS,
) -> subprocess.CompletedProcess[bytes]:
    threads = sanitize_whisper_threads(threads)
    command = build_whisper_command(exe_path, model_path, wav_path, out_base, threads=threads)
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
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{backend_name} t={threads}: timeout after {timeout_seconds} seconds")
    except Exception as exc:
        raise RuntimeError(f"{backend_name} t={threads}: {exc}")

    txt_path = out_base.with_suffix(".txt")
    if completed.returncode == 0 and txt_path.exists():
        return completed

    stderr_text = decode_process_output(completed.stderr)
    stdout_text = decode_process_output(completed.stdout)
    detail = stderr_text or stdout_text or "stderr/stdout пустой"
    if completed.returncode == 0 and not txt_path.exists():
        detail = "TXT output was not created"
    if completed.returncode in (3221225501, -1073741795):
        DISABLED_WHISPER_BACKENDS.add(backend_name)
        detail = f"{detail}; backend disabled for this session after illegal instruction exit"
    raise RuntimeError(f"{backend_name} t={threads}: exit {completed.returncode}; {detail}")


def run_whisper_with_fallback(
    model_path: Path,
    wav_path: Path,
    out_base: Path,
    timeout_seconds: int | None = None,
    preferred_backend_key: str | None = None,
) -> tuple[str, int, subprocess.CompletedProcess[bytes]]:
    backends = available_whisper_backends(preferred_backend_key)
    if not backends:
        expected = "\n".join(str(path) for path in WHISPER_BACKENDS.values())
        raise RuntimeError(f"missing-whisper-cli::{expected}")

    backend_profile = load_backend_profile()
    txt_path = out_base.with_suffix(".txt")
    errors: list[str] = []
    if preferred_backend_key and preferred_backend_key != "auto" and not is_whisper_backend_available(preferred_backend_key):
        preferred_path = WHISPER_BACKENDS.get(preferred_backend_key)
        errors.append(f"{preferred_backend_key}: missing backend: {preferred_path}")

    for backend_name, exe_path in backends:
        if txt_path.exists():
            txt_path.unlink()

        threads = choose_backend_threads(backend_name, backend_profile)
        try:
            completed = run_whisper_backend(
                backend_name,
                exe_path,
                model_path,
                wav_path,
                out_base,
                timeout_seconds,
                threads=threads,
            )
            return backend_name, threads, completed
        except RuntimeError as exc:
            errors.append(str(exc))
            continue

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


def load_user_settings() -> dict:
    settings = dict(DEFAULT_USER_SETTINGS)
    try:
        if USER_SETTINGS_PATH.exists():
            stored = json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for key in ("auto_copy", "format_text", "voice_punctuation"):
                    settings[key] = bool(stored.get(key, DEFAULT_USER_SETTINGS[key]))
                backend = stored.get("backend", DEFAULT_USER_SETTINGS["backend"])
                if backend in BACKEND_LABELS:
                    settings["backend"] = backend
    except Exception:
        return dict(DEFAULT_USER_SETTINGS)
    return settings


def save_user_settings(settings: dict) -> None:
    payload = {
        "auto_copy": bool(settings.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"])),
        "format_text": bool(settings.get("format_text", DEFAULT_USER_SETTINGS["format_text"])),
        "voice_punctuation": bool(settings.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])),
        "backend": str(settings.get("backend", DEFAULT_USER_SETTINGS["backend"])),
    }
    if payload["backend"] not in BACKEND_LABELS:
        payload["backend"] = DEFAULT_USER_SETTINGS["backend"]
    USER_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_voice_punctuation_commands(text: str) -> str:
    replacements = [
        (r"(?iu)(?<!\w)новый\s+абзац[.,!?;:]*(?!\w)", "\n\n"),
        (r"(?iu)(?<!\w)(?:запятая|запитая|запетая|запятую|запитую|запятой|запитой)[.,!?;:]*(?!\w)", ","),
        (r"(?iu)(?<!\w)(?:точка|точку)[.,!?;:]*(?!\w)", "."),
    ]
    result = text
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)
    return normalize_punctuation_spacing(result)


def normalize_punctuation_spacing(text: str) -> str:
    result = text.replace("\r\n", "\n").replace("\r", "\n")
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"([,.;:!?])(?:\s*\1)+", r"\1", result)
    result = re.sub(r",\s*([.!?])", r"\1", result)
    result = re.sub(r"([.!?])\s*,", r"\1", result)
    result = re.sub(r"([,.;:!?])(?=[^\s\n,.;:!?])", r"\1 ", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result.strip()


def capitalize_text(text: str) -> str:
    return re.sub(
        r"(?iu)(^|[.!?]\s+|\n+)([a-zа-яё])",
        lambda match: match.group(1) + match.group(2).upper(),
        text,
    )


def ensure_final_period(text: str) -> str:
    result = text.rstrip()
    if not result:
        return result
    if result[-1] in ".!?…":
        return result
    if result[-1] in ",;:":
        return result[:-1].rstrip() + "."
    return result + "."


def format_recognized_text(text: str) -> str:
    result = normalize_punctuation_spacing(text)
    if not result:
        return result
    result = capitalize_text(result)
    result = ensure_final_period(result)
    return result


def prepare_recognized_text(text: str, use_formatting: bool = True, use_voice_punctuation: bool = True) -> str:
    result = text.strip()
    if use_voice_punctuation:
        result = apply_voice_punctuation_commands(result)
    if use_formatting:
        result = format_recognized_text(result)
    return result


def run_text_cleanup_self_test() -> None:
    cases = [
        (
            "привет точка новый абзац как дела запятая нормально",
            "Привет.\n\nКак дела, нормально.",
        ),
        (
            "Провегаем команды пунктуаций, запитая, 1, 2, 3, 4, 5, запитая, 6, 7, 8, 9,.",
            "Провегаем команды пунктуаций, 1, 2, 3, 4, 5, 6, 7, 8, 9.",
        ),
        (
            "  привет   мир  ",
            "Привет мир.",
        ),
        (
            "первая строка\n\n\nвторая строка",
            "Первая строка\n\nВторая строка.",
        ),
    ]
    for source, expected in cases:
        actual = prepare_recognized_text(source)
        if actual != expected:
            raise AssertionError(f"text cleanup failed: {source!r} -> {actual!r}, expected {expected!r}")


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


def faster_whisper_model_path(model_key: str) -> Path:
    configured = os.environ.get("DICTA_FASTER_WHISPER_MODEL")
    if configured:
        return Path(configured)
    return APP_DIR / ".tools" / "faster-whisper-models" / model_key


def run_faster_whisper_benchmark(wav_path: Path, model_key: str) -> dict:
    model_path = faster_whisper_model_path(model_key)
    if not model_path.exists():
        return {
            "ok": False,
            "available": False,
            "error": f"missing faster-whisper model directory: {model_path}",
        }

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "error": f"faster-whisper is not installed: {exc}",
        }

    device = os.environ.get("DICTA_FASTER_WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("DICTA_FASTER_WHISPER_COMPUTE_TYPE", "int8")

    try:
        started_at = time.perf_counter()
        model = WhisperModel(str(model_path), device=device, compute_type=compute_type)
        segments, _info = model.transcribe(str(wav_path), language="ru", beam_size=1)
        segment_count = len(list(segments))
        elapsed = time.perf_counter() - started_at
        return {
            "ok": True,
            "available": True,
            "model": str(model_path),
            "device": device,
            "compute_type": compute_type,
            "segments": segment_count,
            "elapsed_seconds": round(elapsed, 3),
            "realtime_factor": round(elapsed / BENCHMARK_AUDIO_SECONDS, 3),
        }
    except Exception as exc:
        return {
            "ok": False,
            "available": True,
            "model": str(model_path),
            "device": device,
            "compute_type": compute_type,
            "error": str(exc),
        }


def run_model_benchmark(allow_missing_models: bool = False, print_fn=None, preferred_backend_key: str | None = None) -> dict:
    results: dict[str, dict] = {}

    with tempfile.TemporaryDirectory(prefix="dicta_benchmark_") as tmp_dir:
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
            if print_fn:
                print_fn(f"{model_key}: проверка...")
            started_at = time.perf_counter()
            try:
                backend_name, backend_threads, _completed = run_whisper_with_fallback(
                    model_path,
                    wav_path,
                    out_base,
                    timeout_seconds=300,
                    preferred_backend_key=preferred_backend_key,
                )
                elapsed = time.perf_counter() - started_at
                rtf = elapsed / BENCHMARK_AUDIO_SECONDS
                results[model_key] = {
                    "ok": True,
                    "backend": backend_name,
                    "threads": backend_threads,
                    "elapsed_seconds": round(elapsed, 3),
                    "realtime_factor": round(rtf, 3),
                }
                if print_fn:
                    print_fn(
                        f"{model_key}: {elapsed:.2f}s, realtime x{rtf:.2f}, "
                        f"backend={backend_name}, t={backend_threads}"
                    )
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


def run_backend_benchmark(
    model_key: str | None = None,
    allow_missing_models: bool = False,
    include_faster_whisper: bool = False,
    print_fn=None,
) -> dict:
    model_key = model_key or choose_auto_model_key()
    model_path = MODEL_FILES.get(model_key, MODEL_FILES[FALLBACK_AUTO_MODEL_KEY])
    results: dict[str, dict] = {}

    with tempfile.TemporaryDirectory(prefix="dicta_backend_benchmark_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        wav_path = tmp_path / "benchmark.wav"
        write_benchmark_wav(wav_path)

        if not model_path.exists():
            error = f"missing model: {model_path}"
            for backend_name in WHISPER_BACKENDS:
                results[backend_name] = {"ok": False, "available": False, "error": error}
            if print_fn:
                print_fn(error)
            if not allow_missing_models:
                selected_backend = choose_auto_backend_key(results)
                selected_threads = choose_backend_threads_from_results(selected_backend, results)
                profile = {
                    "version": 2,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
                    "audio_seconds": BENCHMARK_AUDIO_SECONDS,
                    "model": model_key,
                    "selected_backend": selected_backend,
                    "selected_threads": selected_threads,
                    "results": results,
                }
                return profile
        else:
            for backend_name, exe_path in WHISPER_BACKENDS.items():
                if not exe_path.exists():
                    results[backend_name] = {
                        "ok": False,
                        "available": False,
                        "error": f"missing backend: {exe_path}",
                    }
                    if print_fn:
                        print_fn(f"{backend_name}: missing backend")
                    continue

                thread_results: dict[str, dict] = {}
                for threads in backend_thread_candidates(backend_name):
                    out_base = tmp_path / f"backend_{backend_name}_t{threads}"
                    txt_path = out_base.with_suffix(".txt")
                    if txt_path.exists():
                        txt_path.unlink()

                    if print_fn:
                        print_fn(f"{backend_name} t={threads}: проверка...")
                    started_at = time.perf_counter()
                    try:
                        run_whisper_backend(
                            backend_name,
                            exe_path,
                            model_path,
                            wav_path,
                            out_base,
                            timeout_seconds=300,
                            threads=threads,
                        )
                        elapsed = time.perf_counter() - started_at
                        rtf = elapsed / BENCHMARK_AUDIO_SECONDS
                        thread_results[str(threads)] = {
                            "ok": True,
                            "threads": threads,
                            "elapsed_seconds": round(elapsed, 3),
                            "realtime_factor": round(rtf, 3),
                        }
                        if print_fn:
                            print_fn(f"{backend_name} t={threads}: {elapsed:.2f}s, realtime x{rtf:.2f}")
                    except Exception as exc:
                        thread_results[str(threads)] = {
                            "ok": False,
                            "threads": threads,
                            "error": str(exc),
                        }
                        if print_fn:
                            print_fn(f"{backend_name} t={threads}: failed: {exc}")
                        if backend_name in DISABLED_WHISPER_BACKENDS:
                            break

                best_threads = choose_backend_threads_from_results(
                    backend_name,
                    {backend_name: {"thread_results": thread_results}},
                )
                best_result = thread_results.get(str(best_threads), {})
                if best_result.get("ok"):
                    results[backend_name] = {
                        "ok": True,
                        "available": True,
                        "selected_threads": best_threads,
                        "elapsed_seconds": best_result.get("elapsed_seconds"),
                        "realtime_factor": best_result.get("realtime_factor"),
                        "thread_results": thread_results,
                    }
                    if print_fn:
                        print_fn(
                            f"{backend_name}: selected t={best_threads}, "
                            f"{best_result.get('elapsed_seconds'):.2f}s"
                        )
                else:
                    errors = [
                        str(item.get("error"))
                        for item in thread_results.values()
                        if isinstance(item, dict) and item.get("error")
                    ]
                    results[backend_name] = {
                        "ok": False,
                        "available": True,
                        "error": "; ".join(errors) if errors else "no thread candidates completed",
                        "thread_results": thread_results,
                    }

        if include_faster_whisper:
            result = run_faster_whisper_benchmark(wav_path, model_key)
            results["faster-whisper"] = result
            if print_fn:
                if result.get("ok"):
                    print_fn(
                        "faster-whisper: "
                        f"{result['elapsed_seconds']:.2f}s, realtime x{result['realtime_factor']:.2f}, "
                        f"device={result.get('device')}, compute={result.get('compute_type')}"
                    )
                else:
                    print_fn(f"faster-whisper: skipped: {result.get('error')}")

    selected_backend = choose_auto_backend_key(results)
    selected_threads = choose_backend_threads_from_results(selected_backend, results)
    profile = {
        "version": 2,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "audio_seconds": BENCHMARK_AUDIO_SECONDS,
        "model": model_key,
        "selected_backend": selected_backend,
        "selected_threads": selected_threads,
        "results": results,
    }
    if any(results.get(backend_name, {}).get("ok") for backend_name in WHISPER_BACKENDS):
        save_backend_profile(profile)
    return profile


class DictaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Dicta")
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
        self.is_finding_microphone = False
        self.is_benchmarking = False
        self.record_started_at: float | None = None
        self.record_sample_rate = SAMPLE_RATE
        self.last_input_stream_config: dict | None = None
        self.mic_test_stream: sd.RawInputStream | None = None
        self.mic_test_peak = 0
        self.last_level_event_at = 0.0
        self.input_devices: dict[str, list[int]] = {}
        self.spellcheck_after_id: str | None = None
        self.spellcheck_generation = 0
        self.spelling_issues: dict[str, SpellingIssue] = {}
        self.settings = load_user_settings()
        self.hotkey_thread: threading.Thread | None = None
        self.hotkey_thread_id: int | None = None
        self.format_undo_snapshot: tuple[str, str] | None = None
        self.settings_snapshot: dict[str, object] = {}

        self.status_var = tk.StringVar(value="Готово")
        self.record_time_var = tk.StringVar(value="Запись: 00:00")
        self.recognition_time_var = tk.StringVar(value="Распознавание: -")
        self.firewall_status_var = tk.StringVar(value="Сеть: проверка...")
        self.speed_status_var = tk.StringVar(value="Скорость: авто")
        self.profile_var = tk.StringVar(value=DEFAULT_PROFILE_LABEL)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL_LABEL)
        self.backend_var = tk.StringVar(
            value=BACKEND_LABELS.get(str(self.settings.get("backend", "auto")), DEFAULT_BACKEND_LABEL)
        )
        self.input_device_var = tk.StringVar(value="")
        self.input_level_var = tk.DoubleVar(value=0)
        self.input_level_text_var = tk.StringVar(value="Уровень: -")
        self.microphone_search_progress_var = tk.DoubleVar(value=0)
        self.microphone_search_status_var = tk.StringVar(value="Поиск: -")
        self.spellcheck_status_var = tk.StringVar(value="Орфография: авто")
        self.hotkey_status_var = tk.StringVar(value=f"Горячая клавиша: {HOTKEY_LABEL}")
        self.auto_copy_var = tk.BooleanVar(value=self.settings.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"]))
        self.format_text_var = tk.BooleanVar(value=self.settings.get("format_text", DEFAULT_USER_SETTINGS["format_text"]))
        self.voice_punctuation_var = tk.BooleanVar(
            value=self.settings.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])
        )

        self._build_ui()
        self._apply_profile_selection()
        self.refresh_input_devices()
        self.settings_snapshot = self._capture_settings_state()
        self._check_local_files()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._process_ui_queue)
        self.root.after(250, self._update_record_timer)
        self.root.after(500, self.refresh_firewall_status)
        self._start_hotkey_listener()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(6, weight=1)

        self.record_button = ttk.Button(toolbar, text="Записать", command=self.toggle_recording)
        self.record_button.grid(row=0, column=0, padx=(0, 8))

        self.stop_button = ttk.Button(toolbar, text="Стоп", command=self.stop_recording, state=tk.DISABLED)

        self.copy_button = ttk.Button(toolbar, text="Скопировать", command=self.copy_text)
        self.copy_button.grid(row=0, column=1, padx=(0, 8))

        self.format_button = ttk.Button(toolbar, text="Автоформат", command=self.format_current_text)
        self.format_button.grid(row=0, column=2, padx=(0, 8))

        self.clear_button = ttk.Button(toolbar, text="Очистить", command=self.clear_text)
        self.clear_button.grid(row=0, column=3, padx=(0, 16))

        self.input_level_bar = ttk.Progressbar(
            toolbar,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=120,
        )
        self.input_level_bar.grid(row=0, column=4, sticky="w", padx=(0, 6))
        ttk.Label(toolbar, textvariable=self.input_level_text_var).grid(row=0, column=5, sticky="w", padx=(0, 18))

        self.settings_button = ttk.Button(toolbar, text="Настройки", command=self.show_settings)
        self.settings_button.grid(row=0, column=7, sticky="e")

        info = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        info.grid(row=1, column=0, sticky="ew")
        info.columnconfigure(3, weight=1)

        ttk.Label(info, text="Статус:").grid(row=0, column=0, padx=(0, 4))
        ttk.Label(info, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=(0, 18))
        ttk.Label(info, textvariable=self.record_time_var).grid(row=0, column=2, sticky="w", padx=(0, 18))
        ttk.Label(info, textvariable=self.recognition_time_var).grid(row=0, column=3, sticky="w", padx=(0, 18))
        ttk.Label(info, textvariable=self.spellcheck_status_var).grid(row=0, column=4, sticky="w", padx=(18, 0))

        text_frame = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(text_frame, wrap="word", undo=True, font=("Segoe UI", 12))
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("spelling_error", underline=True)
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<Button-3>", self._show_text_context_menu)
        self.text.bind("<Menu>", self._show_text_context_menu)
        self.text.bind("<Shift-F10>", self._show_text_context_menu)

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self._build_settings_window()

    def _build_settings_window(self) -> None:
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Dicta: настройки")
        self.settings_window.geometry("720x430")
        self.settings_window.minsize(620, 360)
        self.settings_window.transient(self.root)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.hide_settings)
        self.settings_window.withdraw()

        notebook = ttk.Notebook(self.settings_window)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        recording_tab = ttk.Frame(notebook, padding=12)
        text_tab = ttk.Frame(notebook, padding=12)
        performance_tab = ttk.Frame(notebook, padding=12)
        security_tab = ttk.Frame(notebook, padding=12)
        notebook.add(recording_tab, text="Запись")
        notebook.add(text_tab, text="Текст")
        notebook.add(performance_tab, text="Производительность")
        notebook.add(security_tab, text="Безопасность")

        recording_tab.columnconfigure(1, weight=1)
        ttk.Label(recording_tab, text="Микрофон:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.input_device_box = ttk.Combobox(
            recording_tab,
            textvariable=self.input_device_var,
            state="readonly",
            width=52,
        )
        self.input_device_box.grid(row=0, column=1, columnspan=4, sticky="ew", pady=(0, 8))
        self.refresh_input_button = ttk.Button(recording_tab, text="Обновить", command=self.refresh_input_devices)
        self.refresh_input_button.grid(row=1, column=1, sticky="w", padx=(0, 8))
        self.test_input_button = ttk.Button(recording_tab, text="Проверить", command=self.start_microphone_test)
        self.test_input_button.grid(row=1, column=2, sticky="w", padx=(0, 8))
        self.find_input_button = ttk.Button(recording_tab, text="Найти микрофон", command=self.start_microphone_search)
        self.find_input_button.grid(row=1, column=3, sticky="w")
        ttk.Label(recording_tab, textvariable=self.input_level_text_var).grid(row=2, column=1, sticky="w", pady=(14, 0))
        self.microphone_search_progress = ttk.Progressbar(
            recording_tab,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=180,
        )
        self.microphone_search_progress.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 8))
        ttk.Label(recording_tab, textvariable=self.microphone_search_status_var).grid(
            row=3,
            column=3,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(recording_tab, textvariable=self.hotkey_status_var).grid(row=4, column=1, sticky="w", pady=(8, 0))

        self.auto_copy_check = ttk.Checkbutton(
            text_tab,
            text="Автокопия",
            variable=self.auto_copy_var,
        )
        self.auto_copy_check.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.format_text_check = ttk.Checkbutton(
            text_tab,
            text="Форматировать",
            variable=self.format_text_var,
        )
        self.format_text_check.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.voice_punctuation_check = ttk.Checkbutton(
            text_tab,
            text="Команды пунктуации",
            variable=self.voice_punctuation_var,
        )
        self.voice_punctuation_check.grid(row=2, column=0, sticky="w", pady=(0, 12))
        ttk.Label(text_tab, textvariable=self.spellcheck_status_var).grid(row=3, column=0, sticky="w")

        performance_tab.columnconfigure(1, weight=1)
        ttk.Label(performance_tab, text="Модель:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.model_box = ttk.Combobox(
            performance_tab,
            textvariable=self.model_var,
            values=list(MODEL_OPTIONS.keys()),
            state="readonly",
            width=30,
        )
        self.model_box.grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.model_box.bind("<<ComboboxSelected>>", self._on_model_changed)

        ttk.Label(performance_tab, text="Профиль:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.profile_box = ttk.Combobox(
            performance_tab,
            textvariable=self.profile_var,
            values=list(PROFILE_MODEL_KEYS.keys()),
            state="readonly",
            width=14,
        )
        self.profile_box.grid(row=1, column=1, sticky="w", pady=(0, 8))
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_changed)

        ttk.Label(performance_tab, text="Backend:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.backend_box = ttk.Combobox(
            performance_tab,
            textvariable=self.backend_var,
            values=list(BACKEND_LABELS.values()),
            state="readonly",
            width=14,
        )
        self.backend_box.grid(row=2, column=1, sticky="w", pady=(0, 8))
        self.backend_box.bind("<<ComboboxSelected>>", self._on_backend_changed)

        benchmark_buttons = ttk.Frame(performance_tab)
        benchmark_buttons.grid(row=3, column=1, sticky="w", pady=(6, 8))
        self.benchmark_button = ttk.Button(benchmark_buttons, text="Бенчмарк моделей", command=self.start_model_benchmark)
        self.benchmark_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.backend_benchmark_button = ttk.Button(benchmark_buttons, text="Backend тест", command=self.start_backend_benchmark)
        self.backend_benchmark_button.grid(row=0, column=1, sticky="w")
        ttk.Label(performance_tab, textvariable=self.speed_status_var).grid(row=4, column=1, sticky="w")

        self.firewall_button = ttk.Button(security_tab, text="Блокировать сеть", command=self.enable_firewall_block)
        self.firewall_button.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 10))
        self.firewall_unblock_button = ttk.Button(security_tab, text="Разблокировать", command=self.disable_firewall_block)
        self.firewall_unblock_button.grid(row=0, column=1, sticky="w", pady=(0, 10))
        ttk.Label(security_tab, textvariable=self.firewall_status_var).grid(row=1, column=0, columnspan=2, sticky="w")

        settings_buttons = ttk.Frame(self.settings_window)
        settings_buttons.pack(fill="x", padx=12, pady=(0, 12))
        settings_buttons.columnconfigure(0, weight=1)
        self.cancel_settings_button = ttk.Button(settings_buttons, text="Отмена", command=self.cancel_settings_changes)
        self.cancel_settings_button.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.save_settings_button = ttk.Button(settings_buttons, text="Сохранить", command=self.save_settings_changes)
        self.save_settings_button.grid(row=0, column=2, sticky="e")

    def show_settings(self) -> None:
        self.settings_window.deiconify()
        self.settings_window.lift()
        self.settings_window.focus_force()

    def hide_settings(self) -> None:
        self.settings_window.withdraw()

    def _apply_window_icon(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Dicta.LocalDictation")
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
            expected = "\n".join(f"{name}: {path}" for name, path in WHISPER_BACKENDS.items())
            missing.append(f"Не найден ни один локальный whisper.cpp backend:\n{expected}")
        for model_path in MODEL_OPTIONS.values():
            if not model_path.exists():
                missing.append(str(model_path))

        if missing:
            self._set_status("Не найдены локальные файлы")
            messagebox.showerror(
                "Dicta",
                self._format_problem_message(
                    "Не найдены обязательные локальные файлы Dicta.",
                    [
                        "Запускайте приложение из полной папки Dicta, не переносите один EXE отдельно.",
                        "Проверьте, что рядом с Dicta.exe есть папки models и .tools.",
                        "Если это сборка из GitHub Actions, скачайте и распакуйте artifact целиком.",
                        "Для проверки запустите scripts\\diagnose_dicta.cmd.",
                    ],
                    technical="\n".join(missing),
                ),
            )
            self._set_record_button_busy("Нет файлов")

    def _start_hotkey_listener(self) -> None:
        if os.name != "nt":
            self.hotkey_status_var.set("Горячая клавиша: только Windows")
            return

        self.hotkey_thread = threading.Thread(target=self._hotkey_worker, daemon=True)
        self.hotkey_thread.start()

    def _hotkey_worker(self) -> None:
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.hotkey_thread_id = int(kernel32.GetCurrentThreadId())

            modifiers = HOTKEY_MODIFIERS | HOTKEY_MOD_NOREPEAT
            registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, modifiers, HOTKEY_VK_SPACE))
            if not registered:
                registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, HOTKEY_MODIFIERS, HOTKEY_VK_SPACE))
            if not registered:
                self.ui_queue.put(("hotkey_status", f"Горячая клавиша: недоступна ({HOTKEY_LABEL})"))
                return

            self.ui_queue.put(("hotkey_status", f"Горячая клавиша: {HOTKEY_LABEL}"))
            msg = ctypes.wintypes.MSG()
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0 or result == -1:
                    break
                if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
                    self.ui_queue.put(("hotkey", None))
        except Exception:
            self.ui_queue.put(("hotkey_status", f"Горячая клавиша: недоступна ({HOTKEY_LABEL})"))
        finally:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            except Exception:
                pass

    def _stop_hotkey_listener(self) -> None:
        if os.name != "nt" or self.hotkey_thread_id is None:
            return
        try:
            ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, WM_QUIT, 0, 0)
        except Exception:
            pass

    def _handle_record_hotkey(self) -> None:
        if self.is_recording:
            self.stop_recording()
            return
        if self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking:
            return
        if self.record_button.instate(["!disabled"]):
            self.start_recording()

    def toggle_recording(self) -> None:
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def _set_record_button_idle(self) -> None:
        self.record_button.configure(text="Записать", command=self.toggle_recording, state=tk.NORMAL)

    def _set_record_button_recording(self) -> None:
        self.record_button.configure(text="Стоп", command=self.stop_recording, state=tk.NORMAL)

    def _set_record_button_busy(self, text: str) -> None:
        self.record_button.configure(text=text, state=tk.DISABLED)

    def _on_profile_changed(self, event=None) -> None:
        self._apply_profile_selection()

    def _on_model_changed(self, event=None) -> None:
        self._update_speed_status()

    def _on_backend_changed(self, event=None) -> None:
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

    def _selected_backend_key(self) -> str:
        return BACKEND_KEY_BY_LABEL.get(self.backend_var.get(), "auto")

    def _selected_backend_preference(self) -> str | None:
        backend_key = self._selected_backend_key()
        return None if backend_key == "auto" else backend_key

    def _select_backend_key(self, backend_key: str) -> None:
        self.backend_var.set(BACKEND_LABELS.get(backend_key, DEFAULT_BACKEND_LABEL))

    def _update_speed_status(
        self,
        vad_stats: dict | None = None,
        backend_name: str | None = None,
        backend_threads: int | None = None,
    ) -> None:
        profile = self.profile_var.get()
        model_key = self._selected_model_key()
        backend = backend_name or self._preferred_backend_name()
        parts = [f"Скорость: {profile.lower()}, модель {model_key}", f"backend {backend}"]
        if backend in WHISPER_BACKENDS:
            threads = backend_threads or choose_backend_threads(backend)
            parts.append(f"t={threads}")
        if vad_stats:
            reduction = vad_stats.get("reduction_percent", 0)
            parts.append(f"VAD -{reduction:.0f}%")
        self.speed_status_var.set("; ".join(parts))

    def _preferred_backend_name(self) -> str:
        backends = available_whisper_backends(self._selected_backend_preference())
        return backends[0][0] if backends else "нет whisper-cli"

    def start_model_benchmark(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking:
            return

        self.is_benchmarking = True
        self._set_status("Бенчмарк моделей: подготовка...")
        self.speed_status_var.set("Бенчмарк моделей: идет проверка моделей")
        self._set_record_button_busy("Бенчмарк")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(text="Идет тест...", state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.find_input_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._benchmark_models_worker, daemon=True).start()

    def _benchmark_models_worker(self) -> None:
        try:
            def report_progress(message: str) -> None:
                self.ui_queue.put(("model_benchmark_progress", message))

            profile = run_model_benchmark(
                allow_missing_models=True,
                preferred_backend_key=self._selected_backend_preference(),
                print_fn=report_progress,
            )
            if not any(item.get("ok") for item in profile.get("results", {}).values()):
                raise RuntimeError("No local models were available for benchmark.")
            self.ui_queue.put(("benchmark_result", profile))
        except Exception as exc:
            self.ui_queue.put(("benchmark_error", self._format_problem_message(
                "Не удалось выполнить бенчмарк моделей.",
                [
                    "Проверьте, что рядом с Dicta.exe есть папки models и .tools.",
                    "Запустите scripts\\diagnose_dicta.cmd для проверки состава папки.",
                ],
                technical=self._shorten_technical_text(str(exc)),
            )))
        finally:
            self.ui_queue.put(("benchmark_ready", None))

    def start_backend_benchmark(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking:
            return

        self.is_benchmarking = True
        self._set_status("Backend тест: подготовка...")
        self.speed_status_var.set("Backend тест: идет проверка backend и потоков")
        self._set_record_button_busy("Бенчмарк")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(text="Идет тест...", state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.find_input_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._benchmark_backends_worker, daemon=True).start()

    def _benchmark_backends_worker(self) -> None:
        try:
            def report_progress(message: str) -> None:
                self.ui_queue.put(("backend_benchmark_progress", message))

            profile = run_backend_benchmark(
                model_key=self._selected_model_key(),
                allow_missing_models=True,
                print_fn=report_progress,
            )
            if not any(profile.get("results", {}).get(backend_name, {}).get("ok") for backend_name in WHISPER_BACKENDS):
                raise RuntimeError("No local whisper.cpp backends completed the benchmark.")
            self.ui_queue.put(("backend_benchmark_result", profile))
        except Exception as exc:
            self.ui_queue.put(("benchmark_error", self._format_problem_message(
                "Не удалось выполнить бенчмарк backend.",
                [
                    "Проверьте, что рядом с Dicta.exe есть папки models и .tools.",
                    "GPU backend считаются optional: если их нет, должен сработать AVX2 или Compat.",
                    "Запустите scripts\\diagnose_dicta.cmd для проверки состава папки.",
                ],
                technical=self._shorten_technical_text(str(exc)),
            )))
        finally:
            self.ui_queue.put(("benchmark_ready", None))

    def refresh_input_devices(self) -> None:
        previous_value = self.input_device_var.get()

        try:
            labels, input_devices, default_input = collect_input_device_groups()
        except Exception as exc:
            self.input_devices = {}
            self.input_device_var.set("")
            self.input_device_box.configure(values=[], state=tk.DISABLED)
            self.test_input_button.configure(state=tk.DISABLED)
            self.find_input_button.configure(state=tk.DISABLED)
            self._set_status("Не удалось прочитать микрофоны")
            return

        self.input_devices = input_devices
        self.input_device_box.configure(values=labels)
        if not labels:
            self.input_device_var.set("")
            self.input_device_box.configure(state=tk.DISABLED)
            self._set_record_button_busy("Нет микрофона")
            self.test_input_button.configure(state=tk.DISABLED)
            self.find_input_button.configure(state=tk.DISABLED)
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
        if not (
            self.is_recording
            or self.is_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_benchmarking
        ):
            self._set_record_button_idle()
        self.test_input_button.configure(state=tk.NORMAL)
        self.find_input_button.configure(state=tk.NORMAL)

    def _clean_input_device_name(self, name: str) -> str:
        return clean_input_device_name(name)

    def _is_system_input_alias(self, name: str) -> bool:
        return is_system_input_alias(name)

    def _is_low_level_input_backend(self, hostapi_name: str) -> bool:
        return is_low_level_input_backend(hostapi_name)

    def _input_device_priority(self, device_index: int) -> int:
        return input_device_priority(device_index)

    def _selected_input_device_indexes(self) -> list[int]:
        label = self.input_device_var.get()
        if label in self.input_devices:
            return self.input_devices[label]
        self.refresh_input_devices()
        label = self.input_device_var.get()
        if label in self.input_devices:
            return self.input_devices[label]
        raise RuntimeError("Не найден доступный микрофон в списке Dicta.")

    def _input_device_default_sample_rate(self, device_index: int) -> int:
        return input_device_default_sample_rate(device_index)

    def start_microphone_test(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking:
            return

        self.mic_test_peak = 0
        self.last_input_stream_config = None
        self.microphone_search_progress_var.set(0)
        self.microphone_search_status_var.set("Проверка...")
        self._set_input_level(0)

        try:
            self.mic_test_stream = self._open_input_stream(
                self._selected_input_device_indexes(),
                callback=self._microphone_test_callback,
            )
        except Exception as exc:
            self.mic_test_stream = None
            self.microphone_search_progress_var.set(0)
            self.microphone_search_status_var.set("Проверка: ошибка")
            self._set_status("Ошибка микрофона")
            messagebox.showerror(
                "Dicta",
                self._format_microphone_error(
                    "Не удалось проверить микрофон.",
                    exc,
                    include_diagnostics=True,
                ),
            )
            return

        self.is_testing_microphone = True
        self._set_status("Проверка микрофона: говорите 3 секунды")
        self._set_record_button_busy("Проверка")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.find_input_button.configure(state=tk.DISABLED)
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

        self._set_record_button_idle()
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state="readonly")
        self.profile_box.configure(state="readonly")
        self.benchmark_button.configure(state=tk.NORMAL)
        self.backend_box.configure(state="readonly")
        self.backend_benchmark_button.configure(state=tk.NORMAL)
        self.input_device_box.configure(state="readonly")
        self.refresh_input_button.configure(state=tk.NORMAL)
        self.test_input_button.configure(state=tk.NORMAL)
        self.find_input_button.configure(state=tk.NORMAL)
        self.microphone_search_progress_var.set(0)

        config_text = input_stream_config_text(self.last_input_stream_config)
        if self.mic_test_peak >= MICROPHONE_WORKING_PEAK_PERCENT:
            self._set_status(f"Микрофон работает, пик {self.mic_test_peak}%")
            self.input_level_var.set(self.mic_test_peak)
            self.input_level_text_var.set(f"Пик: {self.mic_test_peak}%")
            self.microphone_search_status_var.set(f"Проверен: пик {self.mic_test_peak}%")
        else:
            self._set_status("Микрофон открыт, но звук не обнаружен")
            self.input_level_var.set(0)
            self.input_level_text_var.set("Уровень: тишина")
            messagebox.showwarning(
                "Dicta",
                self._format_problem_message(
                    "Микрофон удалось открыть, но заметного звука за 3 секунды не обнаружено.",
                    [
                        "Проверьте, что выбран именно рабочий микрофон, а не линейный вход или стерео микшер.",
                        "Проверьте уровень входа в настройках Windows.",
                        "Проверьте физическую кнопку mute на гарнитуре или микрофоне.",
                        "Нажмите Найти микрофон или Обновить и повторите Проверить.",
                    ],
                    details=f"Открытый режим: {config_text}",
                ),
            )

    def start_microphone_search(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking:
            return

        self.refresh_input_devices()
        groups = list(self.input_devices.items())
        if not groups:
            self._set_status("Микрофоны не найдены")
            self.microphone_search_status_var.set("Поиск: нет устройств")
            return

        self.is_finding_microphone = True
        self.mic_test_peak = 0
        self.microphone_search_progress_var.set(0)
        self.microphone_search_status_var.set(f"Поиск: 0/{len(groups)}")
        self._set_input_level(0)
        self._set_status("Поиск микрофона: говорите обычной громкостью")
        self._set_record_button_busy("Поиск")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.find_input_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._find_microphone_worker, args=(groups,), daemon=True).start()

    def _find_microphone_worker(self, groups: list[tuple[str, list[int]]]) -> None:
        results: list[dict] = []

        try:
            total = len(groups)
            for position, (label, indexes) in enumerate(groups, start=1):
                self.ui_queue.put(("microphone_search_progress", (position - 1, total, label, 0)))

                def report_level(level: int) -> None:
                    self.ui_queue.put(("input_level", level))

                result = probe_input_device_group(
                    indexes,
                    seconds=MICROPHONE_PROBE_SECONDS,
                    level_callback=report_level,
                )
                result["label"] = label
                results.append(result)
                self.ui_queue.put(("microphone_search_progress", (position, total, label, result.get("peak", 0))))

                if result.get("ok"):
                    self.ui_queue.put(("microphone_search_result", (label, result, results)))
                    return

            self.ui_queue.put(("microphone_search_result", (None, None, results)))
        finally:
            self.ui_queue.put(("microphone_search_ready", None))

    def _format_microphone_search_results(self, results: list[dict]) -> str:
        lines: list[str] = []
        for result in results[:10]:
            label = str(result.get("label", "Микрофон"))
            if result.get("opened"):
                lines.append(
                    f"{label}: пик {result.get('peak', 0)}%, {input_stream_config_text(result.get('config'))}"
                )
            else:
                error = str(result.get("error", "")).splitlines()
                tail = error[-1] if error else "не открылся"
                lines.append(f"{label}: не открылся ({tail})")
        if len(results) > 10:
            lines.append(f"... еще {len(results) - 10} устройств")
        return "\n".join(lines)

    def start_recording(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking:
            return

        self.audio_chunks = []
        self.recognition_time_var.set("Распознавание: -")
        self.last_input_stream_config = None
        self._set_input_level(0)

        try:
            self.stream = self._open_input_stream(self._selected_input_device_indexes())
        except Exception as exc:
            self.stream = None
            self._set_status("Ошибка микрофона")
            messagebox.showerror(
                "Dicta",
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
        self._set_record_button_recording()
        self.stop_button.configure(state=tk.NORMAL)
        self.model_box.configure(state=tk.DISABLED)
        self.profile_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(state=tk.DISABLED)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.find_input_button.configure(state=tk.DISABLED)

    def _open_input_stream(self, device_indexes: list[int], callback=None) -> sd.RawInputStream:
        stream_callback = callback or self._audio_callback
        stream, config = open_dicta_input_stream(device_indexes, stream_callback, start=True)
        self.record_sample_rate = int(config.get("sample_rate", SAMPLE_RATE))
        self.last_input_stream_config = config
        return stream

    def stop_recording(self) -> None:
        if not self.is_recording:
            return

        self.is_recording = False
        self._set_record_button_busy("Распознавание")
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
            self._set_record_button_idle()
            self.model_box.configure(state="readonly")
            self.profile_box.configure(state="readonly")
            self.benchmark_button.configure(state=tk.NORMAL)
            self.backend_box.configure(state="readonly")
            self.backend_benchmark_button.configure(state=tk.NORMAL)
            self.input_device_box.configure(state="readonly")
            self.refresh_input_button.configure(state=tk.NORMAL)
            self.test_input_button.configure(state=tk.NORMAL)
            self.find_input_button.configure(state=tk.NORMAL)
            messagebox.showwarning(
                "Dicta",
                self._format_problem_message(
                    "Запись пустая: Dicta не получил аудиоданные от микрофона.",
                    [
                        "Нажмите Проверить и скажите несколько слов.",
                        "Если индикатор уровня не двигается, нажмите Найти микрофон или выберите другой микрофон.",
                        "Если проблема повторяется, запустите scripts\\diagnose_dicta.cmd.",
                    ],
                    details=f"Открытый режим: {input_stream_config_text(self.last_input_stream_config)}",
                ),
            )
            return

        self.is_recognizing = True
        self._set_status("Распознавание")
        self.worker = threading.Thread(target=self._recognize_audio, daemon=True)
        self.worker.start()

    def _save_current_settings(self) -> bool:
        settings = {
            "auto_copy": self.auto_copy_var.get(),
            "format_text": self.format_text_var.get(),
            "voice_punctuation": self.voice_punctuation_var.get(),
            "backend": self._selected_backend_key(),
        }
        try:
            save_user_settings(settings)
            self.settings = load_user_settings()
            self.settings_snapshot = self._capture_settings_state()
            self._set_status("Настройки сохранены")
            return True
        except Exception as exc:
            self._set_status(f"Не удалось сохранить настройки: {exc}")
            return False

    def _capture_settings_state(self) -> dict[str, object]:
        return {
            "input_device": self.input_device_var.get(),
            "profile": self.profile_var.get(),
            "model": self.model_var.get(),
            "backend": self.backend_var.get(),
            "auto_copy": self.auto_copy_var.get(),
            "format_text": self.format_text_var.get(),
            "voice_punctuation": self.voice_punctuation_var.get(),
        }

    def _restore_settings_state(self, state: dict[str, object]) -> None:
        input_device = str(state.get("input_device", ""))
        if input_device in self.input_devices:
            self.input_device_var.set(input_device)
        self.profile_var.set(str(state.get("profile", DEFAULT_PROFILE_LABEL)))
        self.model_var.set(str(state.get("model", DEFAULT_MODEL_LABEL)))
        self.backend_var.set(str(state.get("backend", DEFAULT_BACKEND_LABEL)))
        self.auto_copy_var.set(bool(state.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"])))
        self.format_text_var.set(bool(state.get("format_text", DEFAULT_USER_SETTINGS["format_text"])))
        self.voice_punctuation_var.set(bool(state.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])))
        self._update_speed_status()

    def save_settings_changes(self) -> None:
        if self._save_current_settings():
            self.hide_settings()

    def cancel_settings_changes(self) -> None:
        self._restore_settings_state(self.settings_snapshot)
        self._set_status("Изменения настроек отменены")
        self.hide_settings()

    def _copy_value_to_clipboard(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()

    def copy_text(self) -> None:
        value = self.text.get("1.0", tk.END).strip()
        if not value:
            return
        self._copy_value_to_clipboard(value)
        self._set_status("Скопировано")

    def _has_text_selection(self) -> bool:
        try:
            self.text.index(tk.SEL_FIRST)
            self.text.index(tk.SEL_LAST)
            return True
        except tk.TclError:
            return False

    def _is_index_in_selection(self, index: str) -> bool:
        if not self._has_text_selection():
            return False
        return bool(
            self.text.compare(index, ">=", tk.SEL_FIRST)
            and self.text.compare(index, "<", tk.SEL_LAST)
        )

    def _clipboard_has_text(self) -> bool:
        try:
            return bool(self.root.clipboard_get())
        except tk.TclError:
            return False

    def _reset_format_undo(self) -> None:
        self.format_undo_snapshot = None
        self.format_button.configure(text="Автоформат")

    def _copy_selection(self) -> None:
        if not self._has_text_selection():
            return
        value = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        self._copy_value_to_clipboard(value)
        self._set_status("Скопировано")

    def _cut_selection(self) -> None:
        if not self._has_text_selection():
            return
        value = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        self._copy_value_to_clipboard(value)
        self.text.delete(tk.SEL_FIRST, tk.SEL_LAST)
        self._reset_format_undo()
        self._set_status("Вырезано")
        self._schedule_spellcheck(delay_ms=150)

    def _paste_clipboard(self) -> None:
        try:
            value = self.root.clipboard_get()
        except tk.TclError:
            return
        if not value:
            return
        if self._has_text_selection():
            insert_index = self.text.index(tk.SEL_FIRST)
            self.text.delete(tk.SEL_FIRST, tk.SEL_LAST)
            self.text.mark_set(tk.INSERT, insert_index)
        self.text.insert(tk.INSERT, value)
        self._reset_format_undo()
        self._set_status("Вставлено")
        self._schedule_spellcheck(delay_ms=150)

    def _select_all_text(self) -> None:
        if not self.text.get("1.0", tk.END).strip():
            return
        self.text.tag_add(tk.SEL, "1.0", "end-1c")
        self.text.mark_set(tk.INSERT, "end-1c")
        self.text.see(tk.INSERT)
        self.text.focus_set()
        self._set_status("Текст выделен")

    def format_current_text(self) -> None:
        value = self.text.get("1.0", tk.END).strip()
        if not value:
            self.format_undo_snapshot = None
            self.format_button.configure(text="Автоформат")
            self._set_status("Нет текста для форматирования")
            return
        if self.format_undo_snapshot is not None:
            original, formatted_snapshot = self.format_undo_snapshot
            if value == formatted_snapshot:
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", original)
                self.format_undo_snapshot = None
                self.format_button.configure(text="Автоформат")
                self._set_status("Форматирование отменено")
                self._schedule_spellcheck(delay_ms=100)
                return

        formatted = prepare_recognized_text(
            value,
            use_formatting=True,
            use_voice_punctuation=self.voice_punctuation_var.get(),
        )
        if formatted == value:
            self.format_undo_snapshot = None
            self.format_button.configure(text="Автоформат")
            self._set_status("Текст уже отформатирован")
            return
        self.format_undo_snapshot = (value, formatted)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", formatted)
        self.format_button.configure(text="Вернуть")
        self._set_status("Текст отформатирован")
        self._schedule_spellcheck(delay_ms=100)

    def clear_text(self) -> None:
        self.text.delete("1.0", tk.END)
        self.format_undo_snapshot = None
        self.format_button.configure(text="Автоформат")
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

    def _context_menu_position(self, event, index: str) -> tuple[int, int]:
        x_root = getattr(event, "x_root", 0)
        y_root = getattr(event, "y_root", 0)
        if x_root and y_root:
            return int(x_root), int(y_root)

        bbox = self.text.bbox(index)
        if bbox is None:
            return self.text.winfo_rootx() + 12, self.text.winfo_rooty() + 12
        x, y, _width, height = bbox
        return self.text.winfo_rootx() + x, self.text.winfo_rooty() + y + height

    def _show_text_context_menu(self, event) -> str:
        is_mouse_event = bool(getattr(event, "x_root", 0) and getattr(event, "y_root", 0))
        if is_mouse_event:
            index = self.text.index(f"@{event.x},{event.y}")
        else:
            index = self.text.index(tk.INSERT)

        if not self._is_index_in_selection(index):
            self.text.tag_remove(tk.SEL, "1.0", tk.END)
            self.text.mark_set(tk.INSERT, index)
        self.text.focus_set()

        issue_tag = next((tag for tag in self.text.tag_names(index) if tag in self.spelling_issues), None)
        menu = tk.Menu(self.root, tearoff=False)

        if issue_tag is not None:
            issue = self.spelling_issues[issue_tag]
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
            menu.add_separator()

        has_selection = self._has_text_selection()
        has_text = bool(self.text.get("1.0", tk.END).strip())
        can_paste = self._clipboard_has_text()
        selection_state = tk.NORMAL if has_selection else tk.DISABLED

        menu.add_command(label="Вырезать", command=self._cut_selection, state=selection_state)
        menu.add_command(label="Копировать", command=self._copy_selection, state=selection_state)
        menu.add_command(label="Вставить", command=self._paste_clipboard, state=tk.NORMAL if can_paste else tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=self._select_all_text, state=tk.NORMAL if has_text else tk.DISABLED)

        x_root, y_root = self._context_menu_position(event, index)
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
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
                "Dicta",
                self._format_problem_message(
                    "Не найден файл, для которого нужно включить сетевую блокировку.",
                    [
                        "Запускайте приложение из полной папки Dicta.",
                        "Если это исходники, сначала соберите EXE или откройте dist\\Dicta\\Dicta.exe.",
                    ],
                    technical=str(target),
                ),
            )
            return

        if not getattr(sys, "frozen", False):
            proceed = messagebox.askyesno(
                "Dicta",
                "Сейчас приложение запущено через Python.\n\n"
                "Для чистого пилота лучше открыть dist\\Dicta\\Dicta.exe и нажать кнопку там.\n\n"
                f"Продолжить и заблокировать сеть для:\n{target}?",
            )
            if not proceed:
                return

        script_path = self._write_firewall_script(target)
        try:
            self._run_cmd_elevated(script_path)
        except Exception as exc:
            messagebox.showerror(
                "Dicta",
                self._format_problem_message(
                    "Не удалось запустить настройку Windows Firewall.",
                    [
                        "Проверьте, что подтвердили UAC-запрос Windows.",
                        "Если UAC-запрос не появился, запустите scripts\\diagnose_dicta.cmd.",
                        "Посмотрите лог: %TEMP%\\dicta_firewall.log.",
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
                "Dicta",
                self._format_problem_message(
                    "Не найден файл, для которого нужно снять сетевую блокировку.",
                    [
                        "Проверьте, что приложение запущено из полной папки Dicta.",
                        "Если папку перенесли, старое firewall-правило можно удалить вручную в Windows Firewall.",
                    ],
                    technical=str(target),
                ),
            )
            return

        proceed = messagebox.askyesno(
            "Dicta",
            "Удалить firewall-правило Dicta для этого приложения?\n\n"
            f"{target}",
        )
        if not proceed:
            return

        script_path = self._write_firewall_script(target, remove=True)
        try:
            self._run_cmd_elevated(script_path)
        except Exception as exc:
            messagebox.showerror(
                "Dicta",
                self._format_problem_message(
                    "Не удалось запустить снятие firewall-правила.",
                    [
                        "Проверьте, что подтвердили UAC-запрос Windows.",
                        "Посмотрите лог: %TEMP%\\dicta_firewall.log.",
                        "Если правило не снимается из приложения, удалите его в Windows Firewall вручную.",
                    ],
                    technical=str(exc),
                ),
            )
            return

        self.firewall_status_var.set("Сеть: ожидает подтверждения Windows")
        self.root.after(5000, self.refresh_firewall_status)

    def on_close(self) -> None:
        self._stop_hotkey_listener()
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
        return audio_peak_percent(audio)

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
            with tempfile.NamedTemporaryFile(prefix="dicta_", suffix=".wav", delete=False) as wav_file:
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

            backend_name, backend_threads, completed = run_whisper_with_fallback(
                selected_model,
                wav_path,
                out_base,
                preferred_backend_key=self._selected_backend_preference(),
            )

            elapsed = time.perf_counter() - started_at

            if not txt_path.exists():
                raise RuntimeError("missing-recognition-output")

            recognized = txt_path.read_text(encoding="utf-8").strip()
            self.ui_queue.put(("recognized", (recognized, elapsed, backend_name, backend_threads, vad_stats)))
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
            elif event == "microphone_search_progress":
                checked, total, label, peak = value
                total = max(1, int(total))
                checked = max(0, min(total, int(checked)))
                progress = checked * 100 / total
                self.microphone_search_progress_var.set(progress)
                if checked >= total:
                    self.microphone_search_status_var.set(f"Поиск: {checked}/{total}, пик {peak}%")
                else:
                    self.microphone_search_status_var.set(f"Поиск: {checked}/{total}")
                    self._set_status(f"Поиск микрофона: {label}")
            elif event == "microphone_search_result":
                label, result, results = value
                if label and result:
                    self.input_device_var.set(str(label))
                    self.last_input_stream_config = result.get("config")
                    self.mic_test_peak = int(result.get("peak", 0))
                    self.input_level_var.set(self.mic_test_peak)
                    self.input_level_text_var.set(f"Пик: {self.mic_test_peak}%")
                    if result.get("ok"):
                        self._set_status(f"Найден микрофон: {label}, пик {self.mic_test_peak}%")
                        self.microphone_search_status_var.set(f"Найден: пик {self.mic_test_peak}%")
                    else:
                        self._set_status("Микрофон открылся, но звук не обнаружен")
                        self.microphone_search_status_var.set("Открыт, но тишина")
                        messagebox.showwarning(
                            "Dicta",
                            self._format_problem_message(
                                "Dicta нашла микрофон, который открывается, но заметного звука не услышала.",
                                [
                                    "Говорите во время поиска или нажмите Проверить после выбора.",
                                    "Проверьте уровень входа Windows и физическую кнопку mute на USB-гарнитуре.",
                                    "Если индикатор не двигается, запустите scripts\\diagnose_dicta.cmd.",
                                ],
                                details=f"Выбран: {label}",
                                technical=self._shorten_technical_text(self._format_microphone_search_results(results)),
                            ),
                        )
                else:
                    self._set_status("Рабочий микрофон не найден")
                    self.input_level_var.set(0)
                    self.microphone_search_status_var.set("Поиск: микрофон не найден")
                    messagebox.showwarning(
                        "Dicta",
                        self._format_problem_message(
                            "Dicta не смогла найти микрофон с заметным уровнем звука.",
                            [
                                "Проверьте, что USB-гарнитура подключена и не выключена кнопкой mute.",
                                "Закройте программы, которые могут занимать микрофон: браузер, Teams, Zoom, диктофон.",
                                "Запустите scripts\\diagnose_dicta.cmd и пришлите отчет из папки diagnostics.",
                            ],
                            details=f"Выбор не изменен: {self.input_device_var.get() or 'не выбран'}",
                            technical=self._shorten_technical_text(self._format_microphone_search_results(results)),
                        ),
                    )
            elif event == "microphone_search_ready":
                self.is_finding_microphone = False
                self.microphone_search_progress_var.set(0)
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.profile_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(state=tk.NORMAL)
                self.input_device_box.configure(state="readonly" if self.input_devices else tk.DISABLED)
                self.refresh_input_button.configure(state=tk.NORMAL)
                self.test_input_button.configure(state=tk.NORMAL if self.input_devices else tk.DISABLED)
                self.find_input_button.configure(state=tk.NORMAL if self.input_devices else tk.DISABLED)
            elif event == "hotkey":
                self._handle_record_hotkey()
            elif event == "hotkey_status":
                self.hotkey_status_var.set(str(value))
            elif event == "recognized":
                recognized, elapsed, backend_name, backend_threads, vad_stats = value
                prepared = prepare_recognized_text(
                    str(recognized),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=self.voice_punctuation_var.get(),
                )
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self.format_button.configure(text="Автоформат")
                self.recognition_time_var.set(f"Распознавание: {elapsed:.1f} с")
                self._update_speed_status(
                    vad_stats=vad_stats,
                    backend_name=backend_name,
                    backend_threads=backend_threads,
                )
                if self.auto_copy_var.get() and prepared:
                    self._copy_value_to_clipboard(prepared)
                    self._set_status("Скопировано автоматически")
                else:
                    self._set_status("Готово")
                self._schedule_spellcheck(delay_ms=100)
            elif event == "error":
                self._set_status("Ошибка распознавания")
                messagebox.showerror("Dicta", str(value))
            elif event == "ready":
                self.is_recognizing = False
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.profile_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(state=tk.NORMAL)
                self.input_device_box.configure(state="readonly")
                self.refresh_input_button.configure(state=tk.NORMAL)
                self.test_input_button.configure(state=tk.NORMAL)
                self.find_input_button.configure(state=tk.NORMAL)
            elif event == "benchmark_result":
                profile = value
                selected_model = profile.get("selected_model", FALLBACK_AUTO_MODEL_KEY)
                self.profile_var.set(DEFAULT_PROFILE_LABEL)
                self._select_model_key(selected_model)
                self._update_speed_status()
                self._set_status(f"Бенчмарк готов: выбрана модель {selected_model}")
            elif event == "model_benchmark_progress":
                message = str(value)
                self._set_status(f"Бенчмарк моделей: {message}")
                self.speed_status_var.set(f"Бенчмарк моделей: {message}")
            elif event == "backend_benchmark_result":
                profile = value
                selected_backend = profile.get("selected_backend", FALLBACK_AUTO_BACKEND_KEY)
                selected_threads = parse_positive_int(profile.get("selected_threads")) or choose_backend_threads(selected_backend)
                self._select_backend_key("auto")
                self._save_current_settings()
                self._update_speed_status()
                self._set_status(f"Backend бенчмарк готов: выбран {selected_backend}, t={selected_threads}")
            elif event == "backend_benchmark_progress":
                message = str(value)
                self._set_status(f"Backend тест: {message}")
                self.speed_status_var.set(f"Backend тест: {message}")
            elif event == "benchmark_error":
                self._set_status("Ошибка бенчмарка")
                messagebox.showerror("Dicta", str(value))
            elif event == "benchmark_ready":
                self.is_benchmarking = False
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.profile_box.configure(state="readonly")
                self.benchmark_button.configure(text="Бенчмарк моделей", state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(text="Backend тест", state=tk.NORMAL)
                self.input_device_box.configure(state="readonly")
                self.refresh_input_button.configure(state=tk.NORMAL)
                self.test_input_button.configure(state=tk.NORMAL)
                self.find_input_button.configure(state=tk.NORMAL)
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
            "Нажмите Найти микрофон, затем Проверить.",
            "Закройте программы, которые могут занимать микрофон: браузер, Teams, Zoom, диктофон.",
            "Проверьте доступ к микрофону в настройках конфиденциальности Windows.",
        ]
        if include_diagnostics:
            steps.append("Если ошибка повторяется, запустите scripts\\diagnose_dicta.cmd и пришлите отчет из папки diagnostics.")

        return self._format_problem_message(
            summary,
            steps,
            details=f"Выбранный микрофон: {selected}\nПоследний открытый режим: {input_stream_config_text(self.last_input_stream_config)}",
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
                    "Запускайте Dicta из полной распакованной папки.",
                    "Проверьте, что рядом есть папка .tools.",
                    "Если это GitHub artifact, распакуйте ZIP целиком.",
                    "Запустите scripts\\diagnose_dicta.cmd для проверки состава папки.",
                ],
                technical=path,
            )

        if raw.startswith("missing-model::"):
            path = raw.split("::", 1)[1]
            return self._format_problem_message(
                "Не найдена выбранная локальная модель Whisper.",
                [
                    "Запускайте Dicta из полной распакованной папки.",
                    "Проверьте, что рядом есть папка models.",
                    "Выберите другую модель в списке и повторите запись.",
                    "Запустите scripts\\diagnose_dicta.cmd для проверки состава папки.",
                ],
                technical=path,
            )

        if raw.startswith("whisper-failed::"):
            _, code, technical = raw.split("::", 2)
            return self._format_problem_message(
                "Локальный движок распознавания завершился с ошибкой.",
                [
                    "Повторите запись короткой фразой.",
                    "Проверьте, что модель выбрана и папка Dicta распакована целиком.",
                    "Запустите scripts\\diagnose_dicta.cmd и пришлите отчет, если ошибка повторяется.",
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
                    "Запустите scripts\\diagnose_dicta.cmd и пришлите отчет.",
                ],
            )

        return self._format_problem_message(
            "Не удалось распознать запись.",
            [
                "Повторите запись короткой фразой.",
                "Если ошибка повторяется, запустите scripts\\diagnose_dicta.cmd.",
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

        packaged = APP_DIR / "dist" / "Dicta" / "Dicta.exe"
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
        script_path = Path(tempfile.gettempdir()) / f"dicta_{action}_firewall.cmd"
        log_path = Path(tempfile.gettempdir()) / "dicta_firewall.log"

        if remove:
            content = f"""@echo off
setlocal
set "LOG={log_path}"
echo Dicta firewall remove started > "%LOG%"
echo Program: {target_text} >> "%LOG%"
netsh advfirewall firewall delete rule name="{FIREWALL_RULE_NAME}" program="{target_text}" dir=out >> "%LOG%" 2>&1
echo ExitCode: %ERRORLEVEL% >> "%LOG%"
del "%~f0" >nul 2>nul
"""
        else:
            content = f"""@echo off
setlocal
set "LOG={log_path}"
echo Dicta firewall enable started > "%LOG%"
echo Program: {target_text} >> "%LOG%"
netsh advfirewall firewall delete rule name="{FIREWALL_RULE_NAME}" program="{target_text}" dir=out >> "%LOG%" 2>&1
netsh advfirewall firewall add rule name="{FIREWALL_RULE_NAME}" dir=out action=block program="{target_text}" enable=yes profile=any description="Dicta confidentiality control: block outbound network access." >> "%LOG%" 2>&1
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
        print_audio_devices()
        raise SystemExit(0)

    if "--microphone-diagnostics" in sys.argv:
        seconds = MICROPHONE_PROBE_SECONDS
        if "--seconds" in sys.argv:
            index = sys.argv.index("--seconds")
            if index + 1 < len(sys.argv):
                try:
                    seconds = max(0.2, min(5.0, float(sys.argv[index + 1].replace(",", "."))))
                except Exception:
                    seconds = MICROPHONE_PROBE_SECONDS
        run_microphone_diagnostics(seconds=seconds, print_fn=print)
        raise SystemExit(0)

    if "--spell-test" in sys.argv:
        issues = check_text("тест превет", language_tag="ru-RU")
        print(f"issues={[(issue.word, issue.suggestions[:3]) for issue in issues]}")
        if not any(issue.word == "превет" for issue in issues):
            print("Dicta spell-test note: test word is not flagged; it may already be in the user dictionary.")
        print("Dicta spell-test passed.")
        raise SystemExit(0)

    if "--format-test" in sys.argv:
        run_text_cleanup_self_test()
        print("Dicta format-test passed.")
        raise SystemExit(0)

    if "--benchmark-models" in sys.argv:
        allow_missing_models = "--allow-missing-models" in sys.argv
        profile = run_model_benchmark(allow_missing_models=allow_missing_models, print_fn=print)
        print(f"selected_model={profile.get('selected_model', FALLBACK_AUTO_MODEL_KEY)}")
        print(f"profile={PERFORMANCE_PROFILE_PATH}")
        if not any(item.get("ok") for item in profile.get("results", {}).values()):
            raise SystemExit(1)
        raise SystemExit(0)

    if "--benchmark-backends" in sys.argv:
        allow_missing_models = "--allow-missing-models" in sys.argv
        include_faster_whisper = "--include-faster-whisper" in sys.argv
        model_key = None
        if "--model-key" in sys.argv:
            index = sys.argv.index("--model-key")
            if index + 1 < len(sys.argv):
                model_key = sys.argv[index + 1]
        profile = run_backend_benchmark(
            model_key=model_key,
            allow_missing_models=allow_missing_models,
            include_faster_whisper=include_faster_whisper,
            print_fn=print,
        )
        selected_backend = profile.get("selected_backend", FALLBACK_AUTO_BACKEND_KEY)
        selected_threads = parse_positive_int(profile.get("selected_threads")) or choose_backend_threads(selected_backend)
        print(f"selected_backend={selected_backend}")
        print(f"selected_threads={selected_threads}")
        print(f"profile={BACKEND_PROFILE_PATH}")
        results = profile.get("results", {})
        if not any(results.get(backend_name, {}).get("ok") for backend_name in WHISPER_BACKENDS):
            raise SystemExit(1)
        raise SystemExit(0)

    if "--self-test" in sys.argv:
        allow_missing_models = "--allow-missing-models" in sys.argv
        run_text_cleanup_self_test()
        required = [WHISPER_EXE] if allow_missing_models else [WHISPER_EXE, *MODEL_OPTIONS.values()]
        missing = [path for path in required if not path.exists()]
        if missing:
            print("Dicta self-test failed. Missing files:")
            for path in missing:
                print(path)
            raise SystemExit(1)
        if allow_missing_models:
            missing_models = [path for path in MODEL_OPTIONS.values() if not path.exists()]
            if missing_models:
                print("Dicta self-test warning: models are not included in this code-only package.")
                for path in missing_models:
                    print(path)
        print("Dicta self-test passed.")
        print(f"APP_DIR={APP_DIR}")
        print(f"APP_ICON={APP_ICON}")
        print(f"WHISPER_BACKENDS={[(name, str(path), path.exists()) for name, path in WHISPER_BACKENDS.items()]}")
        print(f"DEFAULT_WHISPER_THREADS={DEFAULT_WHISPER_THREADS}")
        print(f"PERFORMANCE_PROFILE={PERFORMANCE_PROFILE_PATH}")
        print(f"BACKEND_PROFILE={BACKEND_PROFILE_PATH}")
        print(f"USER_SETTINGS={USER_SETTINGS_PATH}")
        raise SystemExit(0)

    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    DictaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
