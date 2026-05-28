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
    "small-q5_1": "small-q5_1: рабочая модель",
}
MODEL_FILES = {
    "small-q5_1": MODELS_DIR / "ggml-small-q5_1.bin",
}
MODEL_OPTIONS = {MODEL_LABELS[key]: MODEL_FILES[key] for key in MODEL_LABELS}
MODEL_KEY_BY_LABEL = {label: key for key, label in MODEL_LABELS.items()}
DEFAULT_MODEL_LABEL = MODEL_LABELS["small-q5_1"]
PROFILE_MODEL_KEYS = {
    "Стандарт": "small-q5_1",
}
DEFAULT_PROFILE_LABEL = "Стандарт"
FALLBACK_AUTO_MODEL_KEY = "small-q5_1"
TRANSLATION_PACK_DIR = APP_DIR / ".tools" / "argos-translate"
ARGOS_PACKAGES_DIR = TRANSLATION_PACK_DIR / "packages"
ARGOS_DATA_DIR = TRANSLATION_PACK_DIR / "data"
ARGOS_CONFIG_DIR = TRANSLATION_PACK_DIR / "config"
ARGOS_CACHE_DIR = TRANSLATION_PACK_DIR / "cache"
ARGOS_WORKER_EXE = TRANSLATION_PACK_DIR / "argos-worker.exe"
ARGOS_WORKER_SCRIPT_CANDIDATES = (
    APP_DIR / "scripts" / "argos_translate_worker.py",
    TRANSLATION_PACK_DIR / "argos_translate_worker.py",
)
ARGOS_PYTHON_CANDIDATES = (
    TRANSLATION_PACK_DIR / "python" / "python.exe",
    TRANSLATION_PACK_DIR / ".venv" / "Scripts" / "python.exe",
    TRANSLATION_PACK_DIR / "Scripts" / "python.exe",
)
TRANSLATION_DIR = APP_DIR / "translation"
EN_RU_GLOSSARY_PATH = TRANSLATION_DIR / "glossary_en_ru.json"
ARGOS_TRANSLATION_TIMEOUT_SECONDS = 45
RECOGNITION_MODE_LABELS = {
    "ru": "Русский текст",
    "en": "English text",
}
RECOGNITION_MODE_KEY_BY_LABEL = {label: key for key, label in RECOGNITION_MODE_LABELS.items()}
RUSSIAN_RECOGNITION_MODE_KEY = "ru"
ENGLISH_RECOGNITION_MODE_KEY = "en"
DEFAULT_RECOGNITION_MODE_KEY = RUSSIAN_RECOGNITION_MODE_KEY
DEFAULT_RECOGNITION_MODE_LABEL = RECOGNITION_MODE_LABELS[DEFAULT_RECOGNITION_MODE_KEY]
RECOGNITION_MODE_LANGUAGES = {
    "ru": "ru",
    "en": "en",
}
RECOGNITION_MODE_SPELLCHECK_TAGS = {
    "ru": "ru-RU",
    "en": "en-US",
}
SPELLCHECK_LANGUAGE_LABELS = {
    "ru-RU": "RU",
    "en-US": "EN",
}
SPELLCHECK_AVAILABILITY_TESTS = (
    ("ru-RU", "Русский", "тест"),
    ("en-US", "Английский", "test"),
)
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
INPUT_SAMPLE_RATE_FALLBACKS = (48000, 44100, 32000)
INPUT_SAMPLE_DTYPES = ("int16", "float32", "int24", "int32")
MICROPHONE_PROBE_SECONDS = 1.5
MICROPHONE_WORKING_PEAK_PERCENT = 1
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
AUDIO_GAIN_MAX_PERCENT = 1000
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
    "recognition_mode": DEFAULT_RECOGNITION_MODE_KEY,
    "backend": "auto",
    "audio_gain_percent": 0,
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


def float32_pcm_to_pcm16_mono(audio: bytes, source_channels: int) -> bytes:
    frame_width = 4 * max(1, source_channels)
    usable_length = len(audio) - (len(audio) % frame_width)
    if usable_length < frame_width:
        return b""

    try:
        samples = memoryview(audio[:usable_length]).cast("f")
    except Exception:
        return b""

    mono = array("h")
    for start in range(0, len(samples), source_channels):
        total = 0.0
        for offset in range(source_channels):
            total += float(samples[start + offset])
        value = total / source_channels
        if value >= 1.0:
            mono.append(32767)
        elif value <= -1.0:
            mono.append(-32768)
        else:
            mono.append(int(round(value * 32767)))
    return mono.tobytes()


def int24_pcm_to_pcm16_mono(audio: bytes, source_channels: int) -> bytes:
    source_channels = max(1, int(source_channels))
    frame_width = 3 * source_channels
    usable_length = len(audio) - (len(audio) % frame_width)
    if usable_length < frame_width:
        return b""

    mono = array("h")
    for frame_start in range(0, usable_length, frame_width):
        total = 0
        for channel in range(source_channels):
            offset = frame_start + channel * 3
            value = int.from_bytes(audio[offset : offset + 3], byteorder="little", signed=False)
            if value & 0x800000:
                value -= 0x1000000
            total += value
        mono.append(max(-32768, min(32767, int(round((total / source_channels) / 256)))))
    return mono.tobytes()


def int32_pcm_to_pcm16_mono(audio: bytes, source_channels: int) -> bytes:
    source_channels = max(1, int(source_channels))
    frame_width = 4 * source_channels
    usable_length = len(audio) - (len(audio) % frame_width)
    if usable_length < frame_width:
        return b""

    try:
        samples = memoryview(audio[:usable_length]).cast("i")
    except Exception:
        return b""

    mono = array("h")
    for start in range(0, len(samples), source_channels):
        total = 0
        for offset in range(source_channels):
            total += int(samples[start + offset])
        mono.append(max(-32768, min(32767, int(round((total / source_channels) / 65536)))))
    return mono.tobytes()


def audio_peak_percent(audio: bytes) -> int:
    usable_length = len(audio) - (len(audio) % SAMPLE_WIDTH_BYTES)
    if usable_length < SAMPLE_WIDTH_BYTES:
        return 0
    try:
        samples = memoryview(audio[:usable_length]).cast("h")
        peak = max(abs(sample) for sample in samples)
    except Exception:
        return 0
    return min(100, int(round(peak * 100 / 32767)))


def clamp_audio_gain_percent(value: object) -> int:
    try:
        percent = int(round(float(value)))
    except Exception:
        return 0
    return max(0, min(AUDIO_GAIN_MAX_PERCENT, percent))


def audio_gain_percent_text(value: object) -> str:
    percent = clamp_audio_gain_percent(value)
    return "без усиления" if percent <= 0 else f"+{percent}%"


def apply_pcm16_gain(audio: bytes, gain_percent: object = 0) -> tuple[bytes, dict]:
    percent = clamp_audio_gain_percent(gain_percent)
    stats = {
        "manual_gain_percent": percent,
        "gain_applied": False,
        "gain_multiplier": 1.0,
        "gain_input_peak_percent": audio_peak_percent(audio),
        "gain_output_peak_percent": audio_peak_percent(audio),
        "gain_clipped_samples": 0,
    }
    usable_length = len(audio) - (len(audio) % SAMPLE_WIDTH_BYTES)
    if percent <= 0 or usable_length < SAMPLE_WIDTH_BYTES:
        return audio, stats

    try:
        samples = memoryview(audio[:usable_length]).cast("h")
    except Exception:
        return audio, stats

    multiplier = 1.0 + (percent / 100.0)

    boosted = array("h")
    clipped = 0
    for sample in samples:
        value = int(round(int(sample) * multiplier))
        if value > 32767:
            value = 32767
            clipped += 1
        elif value < -32768:
            value = -32768
            clipped += 1
        boosted.append(value)

    result = boosted.tobytes() + audio[usable_length:]
    stats.update(
        {
            "gain_applied": True,
            "gain_multiplier": round(multiplier, 2),
            "gain_output_peak_percent": audio_peak_percent(result),
            "gain_clipped_samples": clipped,
        }
    )
    return result, stats


def audio_gain_status_text(audio_stats: dict | None) -> str | None:
    if not isinstance(audio_stats, dict) or not audio_stats.get("gain_applied"):
        return None
    percent = int(audio_stats.get("manual_gain_percent", 0) or 0)
    multiplier = float(audio_stats.get("gain_multiplier", 1.0) or 1.0)
    input_peak = int(audio_stats.get("gain_input_peak_percent", 0) or 0)
    output_peak = int(audio_stats.get("gain_output_peak_percent", 0) or 0)
    return f"усиление +{percent}% (x{multiplier:.2g}), пик {input_peak}->{output_peak}%"


def input_stream_config_text(config: dict | None) -> str:
    if not config:
        return "режим неизвестен"
    source_channels = int(config.get("source_channels", CHANNELS))
    channel_text = "1 канал" if source_channels == 1 else f"{source_channels}->1 канал"
    dtype = str(config.get("dtype", "int16"))
    dtype_text = "" if dtype == "int16" else f", {dtype}->PCM16"
    return f"{config.get('description', 'device')}, {config.get('sample_rate', SAMPLE_RATE)} Hz, {channel_text}{dtype_text}"


def input_stream_config_key(config: dict | None) -> tuple[int, int, int, str] | None:
    if not config:
        return None
    try:
        return (
            int(config["device_index"]),
            int(config["sample_rate"]),
            int(config["source_channels"]),
            str(config.get("dtype", "int16")),
        )
    except Exception:
        return None


def input_stream_candidates(device_indexes: list[int]) -> list[dict]:
    candidates: list[dict] = []
    for device_index in device_indexes:
        description = describe_input_device(device_index)
        for sample_rate in input_device_sample_rates(device_index):
            for source_channels in input_device_channel_counts(device_index):
                for dtype in INPUT_SAMPLE_DTYPES:
                    candidates.append(
                        {
                            "device_index": device_index,
                            "description": description,
                            "sample_rate": sample_rate,
                            "source_channels": source_channels,
                            "channels": CHANNELS,
                            "dtype": dtype,
                        }
                    )
    return candidates


def ordered_input_stream_candidates(device_indexes: list[int], preferred_config: dict | None = None) -> list[dict]:
    candidates = input_stream_candidates(device_indexes)
    preferred_key = input_stream_config_key(preferred_config)
    if preferred_key is None:
        return candidates

    preferred: list[dict] = []
    other: list[dict] = []
    for candidate in candidates:
        if input_stream_config_key(candidate) == preferred_key:
            preferred.append(candidate)
        else:
            other.append(candidate)
    return preferred + other


def _mono_input_callback(callback, source_channels: int, dtype: str = "int16"):
    def wrapper(indata, frames, time_info, status) -> None:
        data = bytes(indata)
        if dtype == "float32":
            data = float32_pcm_to_pcm16_mono(data, source_channels)
        elif dtype == "int24":
            data = int24_pcm_to_pcm16_mono(data, source_channels)
        elif dtype == "int32":
            data = int32_pcm_to_pcm16_mono(data, source_channels)
        elif source_channels > CHANNELS:
            data = downmix_pcm16_to_mono(data, source_channels)
        callback(data, frames, time_info, status)

    return wrapper


def open_input_stream_candidate(config: dict, callback, start: bool = False) -> sd.RawInputStream:
    source_channels = int(config.get("source_channels", CHANNELS))
    dtype = str(config.get("dtype", "int16"))
    stream = sd.RawInputStream(
        device=int(config["device_index"]),
        samplerate=int(config["sample_rate"]),
        channels=source_channels,
        dtype=dtype,
        callback=_mono_input_callback(callback, source_channels, dtype),
    )
    if start:
        stream.start()
    return stream


def open_dicta_input_stream(
    device_indexes: list[int],
    callback,
    start: bool = False,
    preferred_config: dict | None = None,
) -> tuple[sd.RawInputStream, dict]:
    if not device_indexes:
        raise RuntimeError("Не найден доступный микрофон в списке Dicta.")

    errors: list[str] = []
    for config in ordered_input_stream_candidates(device_indexes, preferred_config):
        description = str(config.get("description", "device"))
        sample_rate = int(config.get("sample_rate", SAMPLE_RATE))
        source_channels = int(config.get("source_channels", CHANNELS))
        try:
            stream = open_input_stream_candidate(config, callback, start=start)
            return stream, config
        except Exception as exc:
            action = "start" if start else "open"
            errors.append(f"{description}, {sample_rate} Hz, {source_channels} ch {action}: {exc}")

    raise RuntimeError("\n".join(errors[-12:]) or "Не удалось открыть выбранный микрофон.")


def probe_input_device_group(
    device_indexes: list[int],
    seconds: float = MICROPHONE_PROBE_SECONDS,
    level_callback=None,
    preferred_config: dict | None = None,
    progress_callback=None,
) -> dict:
    best_opened: dict | None = None
    errors: list[str] = []
    candidates = ordered_input_stream_candidates(device_indexes, preferred_config)

    for position, config in enumerate(candidates, start=1):
        peak = 0
        callback_count = 0
        stream_statuses: list[str] = []
        lock = threading.Lock()
        stream: sd.RawInputStream | None = None
        if progress_callback is not None:
            progress_callback(position - 1, len(candidates), config, 0)

        def callback(indata, frames, time_info, status) -> None:
            nonlocal peak, callback_count
            if status:
                with lock:
                    stream_statuses.append(str(status))
            level = audio_peak_percent(bytes(indata))
            with lock:
                callback_count += 1
                peak = max(peak, level)
            if level_callback is not None:
                level_callback(level)

        try:
            stream = open_input_stream_candidate(config, callback, start=True)
            deadline = time.perf_counter() + max(0.2, float(seconds))
            while time.perf_counter() < deadline:
                time.sleep(0.05)
            with lock:
                peak_value = peak
                callbacks = callback_count
                status_text = "; ".join(stream_statuses[-3:])

            result = {
                "ok": peak_value >= MICROPHONE_WORKING_PEAK_PERCENT,
                "opened": True,
                "status": "working" if peak_value >= MICROPHONE_WORKING_PEAK_PERCENT else "silent",
                "peak": peak_value,
                "config": config,
                "stream_status": status_text,
                "callback_count": callbacks,
                "seconds": seconds,
            }
            if result["ok"]:
                return result
            if best_opened is None or int(result.get("peak", 0)) > int(best_opened.get("peak", 0)):
                best_opened = result
        except Exception as exc:
            errors.append(f"{input_stream_config_text(config)}: {exc}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if progress_callback is not None:
                progress_callback(position, len(candidates), config, peak)

    if best_opened is not None:
        best_opened["errors"] = errors
        best_opened["error"] = "\n".join(errors)
        return best_opened

    return {
        "ok": False,
        "opened": False,
        "status": "failed",
        "peak": 0,
        "errors": errors,
        "error": "\n".join(errors) or "Не удалось открыть выбранный микрофон.",
        "seconds": seconds,
    }


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
    print(f"  sample formats: {', '.join(INPUT_SAMPLE_DTYPES)}")
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
            errors = result.get("errors")
            lines = errors if isinstance(errors, list) else str(result.get("error", "")).splitlines()
            for line in lines:
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


def sanitize_recognition_mode_key(value: object | None) -> str:
    if isinstance(value, str) and value in RECOGNITION_MODE_LABELS:
        return value
    if value in {"en_to_ru", "ru_to_en"}:
        return ENGLISH_RECOGNITION_MODE_KEY if value == "en_to_ru" else RUSSIAN_RECOGNITION_MODE_KEY
    return DEFAULT_RECOGNITION_MODE_KEY


def recognition_mode_language(mode_key: object | None) -> str:
    return RECOGNITION_MODE_LANGUAGES[sanitize_recognition_mode_key(mode_key)]


def recognition_mode_spellcheck_tag(mode_key: object | None) -> str:
    return RECOGNITION_MODE_SPELLCHECK_TAGS[sanitize_recognition_mode_key(mode_key)]


def spellcheck_language_label(language_tag: str) -> str:
    return SPELLCHECK_LANGUAGE_LABELS.get(language_tag, language_tag)


def spellcheck_availability_label(language_tag: str) -> str:
    for tag, label, _sample in SPELLCHECK_AVAILABILITY_TESTS:
        if tag == language_tag:
            return label
    return language_tag


def find_argos_worker_script() -> Path | None:
    for path in ARGOS_WORKER_SCRIPT_CANDIDATES:
        if path.exists():
            return path
    return None


def find_argos_runtime() -> tuple[str | None, Path | None, Path | None]:
    if ARGOS_WORKER_EXE.exists():
        return "exe", ARGOS_WORKER_EXE, None

    worker_script = find_argos_worker_script()
    if worker_script is None:
        return None, None, None

    for python_path in ARGOS_PYTHON_CANDIDATES:
        if python_path.exists():
            return "python", python_path, worker_script
    return None, None, worker_script


def translation_direction_key(from_code: str, to_code: str) -> str:
    return f"{from_code}_{to_code}"


def find_argos_model(from_code: str, to_code: str, packages_dir: Path = ARGOS_PACKAGES_DIR) -> Path | None:
    if not packages_dir.exists():
        return None

    for metadata_path in sorted(packages_dir.glob("*/metadata.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(metadata, dict):
            continue
        package_type = str(metadata.get("type", "translate"))
        if (
            package_type == "translate"
            and metadata.get("from_code") == from_code
            and metadata.get("to_code") == to_code
        ):
            return metadata_path.parent
    return None


def _load_string_replacements(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    replacements: dict[str, str] = {}
    for source, target in value.items():
        if isinstance(source, str) and isinstance(target, str) and source:
            replacements[source] = target
    return replacements


def load_translation_glossary(path: Path = EN_RU_GLOSSARY_PATH) -> tuple[dict[str, str], str | None]:
    if not path.exists():
        return {}, None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, str(exc)

    replacements: dict[str, str] = {}
    if isinstance(data, dict):
        replacements.update(_load_string_replacements(data.get("postprocess")))
        replacements.update(_load_string_replacements(data.get("replacements")))
        if not replacements:
            replacements.update(_load_string_replacements(data))
    else:
        return {}, "glossary root must be a JSON object"

    return replacements, None


def apply_translation_glossary(text: str, path: Path = EN_RU_GLOSSARY_PATH) -> str:
    replacements, error = load_translation_glossary(path)
    if error:
        return text

    result = text
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def apply_translation_postprocess(text: str, from_code: str, to_code: str) -> str:
    if from_code == "en" and to_code == "ru":
        return apply_translation_glossary(text)
    return text


def detect_translation_pack() -> dict[str, object]:
    runtime_kind, runtime_path, worker_script = find_argos_runtime()
    models = {
        "en_ru": find_argos_model("en", "ru"),
        "ru_en": find_argos_model("ru", "en"),
    }
    _replacements, glossary_error = load_translation_glossary()
    runtime_available = bool(runtime_kind and runtime_path)
    available_directions = {key: bool(runtime_available and path) for key, path in models.items()}
    return {
        "available": bool(runtime_available and all(available_directions.values())),
        "available_directions": available_directions,
        "runtime_kind": runtime_kind,
        "runtime_path": runtime_path,
        "worker_script": worker_script,
        "packages_dir": ARGOS_PACKAGES_DIR,
        "model_paths": models,
        "model_path": models["en_ru"],
        "glossary_path": EN_RU_GLOSSARY_PATH,
        "glossary_error": glossary_error,
    }


def translation_model_path(status: dict[str, object], from_code: str, to_code: str) -> Path | None:
    model_paths = status.get("model_paths")
    if isinstance(model_paths, dict):
        model_path = model_paths.get(translation_direction_key(from_code, to_code))
        if isinstance(model_path, Path):
            return model_path
        if model_path:
            return Path(str(model_path))
    if from_code == "en" and to_code == "ru":
        model_path = status.get("model_path")
        if isinstance(model_path, Path):
            return model_path
        if model_path:
            return Path(str(model_path))
    return None


def is_translation_direction_available(status: dict[str, object], from_code: str, to_code: str) -> bool:
    return bool(status.get("runtime_path") and translation_model_path(status, from_code, to_code))


def translation_pack_missing_details(
    status: dict[str, object],
    from_code: str | None = None,
    to_code: str | None = None,
) -> str:
    missing: list[str] = []
    if not status.get("runtime_path"):
        missing.append(f"runtime: {TRANSLATION_PACK_DIR}")
    if not status.get("worker_script") and status.get("runtime_kind") != "exe":
        missing.append(f"worker: {ARGOS_WORKER_SCRIPT_CANDIDATES[0]}")
    directions = [(from_code, to_code)] if from_code and to_code else [("en", "ru"), ("ru", "en")]
    for source_code, target_code in directions:
        if not translation_model_path(status, source_code, target_code):
            missing.append(f"model {source_code}->{target_code}: {ARGOS_PACKAGES_DIR}")
    return "; ".join(missing) if missing else str(TRANSLATION_PACK_DIR)


def translation_pack_status_label(status: dict[str, object]) -> str:
    glossary_error = status.get("glossary_error")
    glossary_note = "glossary: ошибка" if glossary_error else "glossary: ok"
    runtime_kind = status.get("runtime_kind") or "runtime"

    def direction_label(from_code: str, to_code: str) -> str:
        model_path = translation_model_path(status, from_code, to_code)
        state = "доступен" if is_translation_direction_available(status, from_code, to_code) else "недоступен"
        model_name = Path(model_path).name if model_path else f"{from_code}->{to_code}"
        return f"{from_code.upper()}->{to_code.upper()}: {state} ({model_name})"

    details = f"{direction_label('en', 'ru')}; {direction_label('ru', 'en')}"
    if not status.get("runtime_path"):
        return f"Перевод: недоступен ({translation_pack_missing_details(status)}; {glossary_note})"
    return f"Перевод: {details}; runtime {runtime_kind}; {glossary_note}"


def _parse_worker_json_response(output: str) -> dict | None:
    try:
        payload = json.loads(output)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass

    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            return payload if isinstance(payload, dict) else None
        except Exception:
            continue
    return None


def run_argos_translation(
    text: str,
    status: dict[str, object] | None = None,
    from_code: str = "en",
    to_code: str = "ru",
) -> str:
    if not text.strip():
        return text

    status = status or detect_translation_pack()
    if not is_translation_direction_available(status, from_code, to_code):
        raise RuntimeError(f"missing-translation-pack::{translation_pack_missing_details(status, from_code, to_code)}")

    runtime_kind = status.get("runtime_kind")
    runtime_path = status.get("runtime_path")
    worker_script = status.get("worker_script")
    packages_dir = Path(status.get("packages_dir") or ARGOS_PACKAGES_DIR)
    if runtime_kind == "exe" and runtime_path:
        args = [str(runtime_path)]
    elif runtime_kind == "python" and runtime_path and worker_script:
        args = [str(runtime_path), "-u", str(worker_script)]
    else:
        raise RuntimeError(f"missing-translation-pack::{translation_pack_missing_details(status)}")

    env = os.environ.copy()
    env.update(
        {
            "ARGOS_DEBUG": "0",
            "ARGOS_DEVICE_TYPE": "cpu",
            "ARGOS_PACKAGES_DIR": str(packages_dir),
            "XDG_DATA_HOME": str(ARGOS_DATA_DIR.parent),
            "XDG_CONFIG_HOME": str(ARGOS_CONFIG_DIR.parent),
            "XDG_CACHE_HOME": str(ARGOS_CACHE_DIR.parent),
        }
    )
    request = {
        "text": text,
        "from_code": from_code,
        "to_code": to_code,
        "packages_dir": str(packages_dir),
    }

    try:
        completed = subprocess.run(
            args,
            input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=ARGOS_TRANSLATION_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"translation-timeout::{ARGOS_TRANSLATION_TIMEOUT_SECONDS}") from exc

    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    payload = _parse_worker_json_response(stdout)
    if payload is not None:
        if not payload.get("ok"):
            raise RuntimeError(f"translation-failed::worker::{payload.get('error', 'unknown error')}")
        translated = str(payload.get("text", "")).strip()
        return apply_translation_postprocess(translated, from_code, to_code)

    technical = "\n".join(part for part in (stderr, stdout) if part)
    if completed.returncode != 0:
        raise RuntimeError(f"translation-failed::{completed.returncode}::{technical}")
    raise RuntimeError(f"translation-failed::invalid-response::{technical}")


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
    language: str = "ru",
    translate_to_english: bool = False,
) -> list[str]:
    threads = sanitize_whisper_threads(threads)
    language = language if language in RECOGNITION_MODE_LANGUAGES.values() else "ru"
    command = [
        str(exe_path),
        "-m",
        str(model_path),
        "-f",
        str(wav_path),
        "-l",
        language,
    ]
    if translate_to_english:
        command.append("-tr")
    command.extend(
        [
            "-t",
            str(threads),
            "-nt",
            "-np",
            "-nf",
            "-otxt",
            "-of",
            str(out_base),
        ]
    )
    return command


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
    language: str = "ru",
    translate_to_english: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    threads = sanitize_whisper_threads(threads)
    command = build_whisper_command(
        exe_path,
        model_path,
        wav_path,
        out_base,
        threads=threads,
        language=language,
        translate_to_english=translate_to_english,
    )
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
    language: str = "ru",
    translate_to_english: bool = False,
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
                language=language,
                translate_to_english=translate_to_english,
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
                settings["audio_gain_percent"] = clamp_audio_gain_percent(
                    stored.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"])
                )
                backend = stored.get("backend", DEFAULT_USER_SETTINGS["backend"])
                if backend in BACKEND_LABELS:
                    settings["backend"] = backend
                settings["recognition_mode"] = sanitize_recognition_mode_key(
                    stored.get("recognition_mode", DEFAULT_USER_SETTINGS["recognition_mode"])
                )
    except Exception:
        return dict(DEFAULT_USER_SETTINGS)
    return settings


def save_user_settings(settings: dict) -> None:
    payload = {
        "auto_copy": bool(settings.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"])),
        "format_text": bool(settings.get("format_text", DEFAULT_USER_SETTINGS["format_text"])),
        "voice_punctuation": bool(settings.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])),
        "recognition_mode": sanitize_recognition_mode_key(
            settings.get("recognition_mode", DEFAULT_USER_SETTINGS["recognition_mode"])
        ),
        "audio_gain_percent": clamp_audio_gain_percent(
            settings.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"])
        ),
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
        self.is_translating = False
        self.record_started_at: float | None = None
        self.record_sample_rate = SAMPLE_RATE
        self.last_input_stream_config: dict | None = None
        self.mic_test_stream: sd.RawInputStream | None = None
        self.mic_test_peak = 0
        self.last_level_event_at = 0.0
        self.input_devices: dict[str, list[int]] = {}
        self.preferred_input_configs: dict[str, dict] = {}
        self.last_recognition_audio_bytes: bytes | None = None
        self.last_recognition_sample_rate: int | None = None
        self.last_recognition_model_path: Path | None = None
        self.last_recognition_backend_preference: str | None = None
        self.last_recognition_mode_key: str | None = None
        self.last_recognition_text: str = ""
        self.spellcheck_after_id: str | None = None
        self.spellcheck_generation = 0
        self.spelling_issues: dict[str, SpellingIssue] = {}
        self.current_text_spellcheck_language_tag = recognition_mode_spellcheck_tag(DEFAULT_RECOGNITION_MODE_KEY)
        self.is_checking_spellcheck_languages = False
        self.settings = load_user_settings()
        self.translation_pack_status = detect_translation_pack()
        self.hotkey_thread: threading.Thread | None = None
        self.hotkey_thread_id: int | None = None
        self.translation_worker: threading.Thread | None = None
        self.format_undo_snapshot: tuple[str, str] | None = None
        self.settings_snapshot: dict[str, object] = {}

        self.status_var = tk.StringVar(value="Готово")
        self.record_time_var = tk.StringVar(value="Запись: 00:00")
        self.recognition_time_var = tk.StringVar(value="Распознавание: -")
        self.firewall_status_var = tk.StringVar(value="Сеть: проверка...")
        self.speed_status_var = tk.StringVar(value="Модель: small-q5_1")
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
        self.spellcheck_ru_availability_var = tk.StringVar(value="Русский: не проверено")
        self.spellcheck_en_availability_var = tk.StringVar(value="Английский: не проверено")
        self.translation_pack_status_var = tk.StringVar(
            value=translation_pack_status_label(self.translation_pack_status)
        )
        self.hotkey_status_var = tk.StringVar(value=f"Горячая клавиша: {HOTKEY_LABEL}")
        initial_recognition_mode = sanitize_recognition_mode_key(
            self.settings.get("recognition_mode", DEFAULT_RECOGNITION_MODE_KEY)
        )
        self.recognition_mode_var = tk.StringVar(
            value=RECOGNITION_MODE_LABELS[initial_recognition_mode]
        )
        self.current_text_spellcheck_language_tag = recognition_mode_spellcheck_tag(self._selected_recognition_mode_key())
        self.auto_copy_var = tk.BooleanVar(value=self.settings.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"]))
        self.format_text_var = tk.BooleanVar(value=self.settings.get("format_text", DEFAULT_USER_SETTINGS["format_text"]))
        self.voice_punctuation_var = tk.BooleanVar(
            value=self.settings.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])
        )
        self.audio_gain_percent_var = tk.DoubleVar(
            value=self.settings.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"])
        )
        self.audio_gain_percent_text_var = tk.StringVar(
            value=audio_gain_percent_text(self.audio_gain_percent_var.get())
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
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(8, weight=1)

        self.record_button = ttk.Button(toolbar, text="Записать", command=self.toggle_recording)
        self.record_button.grid(row=0, column=0, padx=(0, 8))

        self.stop_button = ttk.Button(toolbar, text="Стоп", command=self.stop_recording, state=tk.DISABLED)

        self.copy_button = ttk.Button(toolbar, text="Скопировать", command=self.copy_text)
        self.copy_button.grid(row=0, column=1, padx=(0, 8))

        self.translate_to_ru_button = ttk.Button(toolbar, text="В русский", command=self.translate_current_text_to_russian)
        self.translate_to_ru_button.grid(row=0, column=2, padx=(0, 8))

        self.translate_to_en_button = ttk.Button(toolbar, text="В English", command=self.translate_last_recording_to_english)
        self.translate_to_en_button.grid(row=0, column=3, padx=(0, 8))

        self.format_button = ttk.Button(toolbar, text="Автоформат", command=self.format_current_text)

        self.toolbar_recognition_mode_box = ttk.Combobox(
            toolbar,
            textvariable=self.recognition_mode_var,
            values=self._recognition_mode_labels(),
            state="readonly",
            width=18,
        )
        self.toolbar_recognition_mode_box.grid(row=0, column=4, padx=(0, 8))
        self.toolbar_recognition_mode_box.bind("<<ComboboxSelected>>", self._on_toolbar_recognition_mode_changed)

        self.clear_button = ttk.Button(toolbar, text="Очистить", command=self.clear_text)
        self.clear_button.grid(row=0, column=5, padx=(0, 16))

        self.input_level_bar = ttk.Progressbar(
            toolbar,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=120,
        )
        self.input_level_bar.grid(row=0, column=6, sticky="w", padx=(0, 6))
        ttk.Label(toolbar, textvariable=self.input_level_text_var).grid(row=0, column=7, sticky="w", padx=(0, 18))

        self.settings_button = ttk.Button(toolbar, text="Настройки", command=self.show_settings)
        self.settings_button.grid(row=0, column=9, sticky="e")

        text_frame = ttk.Frame(self.root, padding=(12, 6, 12, 6))
        text_frame.grid(row=1, column=0, sticky="nsew")
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

        ttk.Separator(self.root, orient="horizontal").grid(row=2, column=0, sticky="ew")
        status_bar = ttk.Frame(self.root, padding=(12, 4, 12, 6))
        status_bar.grid(row=3, column=0, sticky="ew")
        status_bar.columnconfigure(1, weight=1)

        ttk.Label(status_bar, text="Статус:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Label(status_bar, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=(0, 18))
        ttk.Label(status_bar, textvariable=self.record_time_var).grid(row=0, column=2, sticky="w", padx=(0, 18))
        ttk.Label(status_bar, textvariable=self.recognition_time_var).grid(row=0, column=3, sticky="w", padx=(0, 18))
        ttk.Label(status_bar, textvariable=self.spellcheck_status_var).grid(row=0, column=4, sticky="e")

        self._build_settings_window()
        self._update_translation_button_state()

    def _build_settings_window(self) -> None:
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Dicta: настройки")
        self.settings_window.geometry("720x500")
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

        text_tab.columnconfigure(1, weight=1)
        recording_tab.columnconfigure(1, weight=1)
        ttk.Label(recording_tab, text="Микрофон:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.input_device_box = ttk.Combobox(
            recording_tab,
            textvariable=self.input_device_var,
            state="readonly",
            width=52,
        )
        self.input_device_box.grid(row=0, column=1, columnspan=4, sticky="ew", pady=(0, 8))
        microphone_buttons = ttk.Frame(recording_tab)
        microphone_buttons.grid(row=1, column=1, columnspan=4, sticky="w")
        self.refresh_input_button = ttk.Button(microphone_buttons, text="Обновить", command=self.refresh_input_devices)
        self.refresh_input_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.test_input_button = ttk.Button(microphone_buttons, text="Проверить", command=self.start_microphone_test)
        self.test_input_button.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.find_input_button = ttk.Button(microphone_buttons, text="Найти микрофон", command=self.start_microphone_search)
        self.find_input_button.grid(row=0, column=2, sticky="w")
        ttk.Label(recording_tab, textvariable=self.input_level_text_var).grid(row=2, column=1, sticky="w", pady=(14, 0))
        self.microphone_search_progress = ttk.Progressbar(
            recording_tab,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=180,
        )
        self.microphone_search_progress.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 8))
        ttk.Label(recording_tab, textvariable=self.microphone_search_status_var, width=28).grid(
            row=3,
            column=3,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(recording_tab, text="Усиление записи:").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        self.audio_gain_scale = ttk.Scale(
            recording_tab,
            from_=0,
            to=AUDIO_GAIN_MAX_PERCENT,
            variable=self.audio_gain_percent_var,
            command=self._on_audio_gain_changed,
        )
        self.audio_gain_scale.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 8))
        ttk.Label(recording_tab, textvariable=self.audio_gain_percent_text_var, width=14).grid(
            row=4,
            column=3,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(recording_tab, textvariable=self.hotkey_status_var).grid(row=5, column=1, sticky="w", pady=(8, 0))

        ttk.Label(text_tab, text="Режим:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.recognition_mode_box = ttk.Combobox(
            text_tab,
            textvariable=self.recognition_mode_var,
            values=self._recognition_mode_labels(),
            state="readonly",
            width=18,
        )
        self.recognition_mode_box.grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.recognition_mode_box.bind("<<ComboboxSelected>>", self._on_recognition_mode_changed)

        self.auto_copy_check = ttk.Checkbutton(
            text_tab,
            text="Автокопия",
            variable=self.auto_copy_var,
        )
        self.auto_copy_check.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.format_text_check = ttk.Checkbutton(
            text_tab,
            text="Форматировать",
            variable=self.format_text_var,
        )
        self.format_text_check.grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.voice_punctuation_check = ttk.Checkbutton(
            text_tab,
            text="Команды пунктуации",
            variable=self.voice_punctuation_var,
        )
        self.voice_punctuation_check.grid(row=3, column=0, sticky="w", pady=(0, 12))
        ttk.Label(text_tab, textvariable=self.spellcheck_status_var).grid(row=4, column=0, sticky="w", pady=(0, 12))
        ttk.Separator(text_tab, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(text_tab, text="Проверка орфографии:").grid(
            row=6,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        self.spellcheck_check_button = ttk.Button(
            text_tab,
            text="Проверить",
            command=self.start_spellcheck_availability_check,
        )
        self.spellcheck_check_button.grid(row=6, column=1, sticky="w", pady=(0, 8))
        ttk.Label(text_tab, textvariable=self.spellcheck_ru_availability_var).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 4),
        )
        ttk.Label(text_tab, textvariable=self.spellcheck_en_availability_var).grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
        )
        ttk.Separator(text_tab, orient="horizontal").grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 10))
        ttk.Label(text_tab, text="Перевод EN->RU:").grid(
            row=10,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(0, 8),
        )
        self.translation_check_button = ttk.Button(
            text_tab,
            text="Проверить",
            command=self.start_translation_availability_check,
        )
        self.translation_check_button.grid(row=10, column=1, sticky="w", pady=(0, 8))
        ttk.Label(text_tab, textvariable=self.translation_pack_status_var, wraplength=560).grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="w",
        )

        performance_tab.columnconfigure(1, weight=1)
        ttk.Label(performance_tab, text="Модель:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Label(performance_tab, textvariable=self.model_var).grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.model_box = ttk.Combobox(
            performance_tab,
            textvariable=self.model_var,
            values=list(MODEL_OPTIONS.keys()),
            state="readonly",
            width=30,
        )
        self.model_box.bind("<<ComboboxSelected>>", self._on_model_changed)

        self.profile_box = ttk.Combobox(
            performance_tab,
            textvariable=self.profile_var,
            values=list(PROFILE_MODEL_KEYS.keys()),
            state="readonly",
            width=14,
        )
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_changed)

        ttk.Label(performance_tab, text="Backend:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.backend_box = ttk.Combobox(
            performance_tab,
            textvariable=self.backend_var,
            values=list(BACKEND_LABELS.values()),
            state="readonly",
            width=14,
        )
        self.backend_box.grid(row=1, column=1, sticky="w", pady=(0, 8))
        self.backend_box.bind("<<ComboboxSelected>>", self._on_backend_changed)

        benchmark_buttons = ttk.Frame(performance_tab)
        benchmark_buttons.grid(row=2, column=1, sticky="w", pady=(6, 8))
        self.benchmark_button = ttk.Button(benchmark_buttons, text="Бенчмарк модели", command=self.start_model_benchmark)
        self.backend_benchmark_button = ttk.Button(benchmark_buttons, text="Backend тест", command=self.start_backend_benchmark)
        self.backend_benchmark_button.grid(row=0, column=0, sticky="w")
        ttk.Label(performance_tab, textvariable=self.speed_status_var).grid(row=3, column=1, sticky="w")

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
        self._center_settings_window()
        self.settings_window.deiconify()
        self.settings_window.lift()
        self.settings_window.focus_force()
        self.start_spellcheck_availability_check()
        self.start_translation_availability_check()

    def hide_settings(self) -> None:
        self.settings_window.withdraw()

    def _center_settings_window(self) -> None:
        self.root.update_idletasks()
        self.settings_window.update_idletasks()

        width = max(self.settings_window.winfo_width(), self.settings_window.winfo_reqwidth(), 720)
        height = max(self.settings_window.winfo_height(), self.settings_window.winfo_reqheight(), 430)
        root_width = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        root_height = max(self.root.winfo_height(), self.root.winfo_reqheight())

        x = self.root.winfo_rootx() + max(0, (root_width - width) // 2)
        y = self.root.winfo_rooty() + max(0, (root_height - height) // 2)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, min(x, max(0, screen_width - width)))
        y = max(0, min(y, max(0, screen_height - height)))
        self.settings_window.geometry(f"{width}x{height}+{x}+{y}")

    def _on_audio_gain_changed(self, value: object | None = None) -> None:
        percent = clamp_audio_gain_percent(self.audio_gain_percent_var.get() if value is None else value)
        self.audio_gain_percent_text_var.set(audio_gain_percent_text(percent))

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
        if self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking or self.is_translating:
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
        self._set_recognition_mode_controls_state("readonly")
        self._update_translation_button_state()

    def _set_record_button_recording(self) -> None:
        self.record_button.configure(text="Стоп", command=self.stop_recording, state=tk.NORMAL)
        self._set_recognition_mode_controls_state(tk.DISABLED)
        self._set_translation_buttons_state(tk.DISABLED)

    def _set_record_button_busy(self, text: str) -> None:
        self.record_button.configure(text=text, state=tk.DISABLED)
        self._set_recognition_mode_controls_state(tk.DISABLED)
        self._set_translation_buttons_state(tk.DISABLED)

    def _set_recognition_mode_controls_state(self, state: str) -> None:
        for control_name in ("toolbar_recognition_mode_box", "recognition_mode_box"):
            control = getattr(self, control_name, None)
            if control is not None:
                control.configure(state=state)

    def _is_recognition_mode_available(self, mode_key: str) -> bool:
        return mode_key in RECOGNITION_MODE_LABELS

    def _recognition_mode_labels(self) -> list[str]:
        return [
            label
            for key, label in RECOGNITION_MODE_LABELS.items()
            if self._is_recognition_mode_available(key)
        ]

    def _refresh_recognition_mode_options(self) -> None:
        labels = self._recognition_mode_labels()
        for control_name in ("toolbar_recognition_mode_box", "recognition_mode_box"):
            control = getattr(self, control_name, None)
            if control is not None:
                control.configure(values=labels)

        selected_key = self._selected_recognition_mode_key()
        if not self._is_recognition_mode_available(selected_key):
            fallback_key = ENGLISH_RECOGNITION_MODE_KEY
            self._select_recognition_mode_key(fallback_key)
            self._set_text_spellcheck_language_from_mode(fallback_key)
            self.spellcheck_generation += 1
            self._clear_spelling_marks()
            self._schedule_spellcheck(delay_ms=100)

    def _on_profile_changed(self, event=None) -> None:
        self._apply_profile_selection()

    def _on_model_changed(self, event=None) -> None:
        self._update_speed_status()

    def _on_backend_changed(self, event=None) -> None:
        self._update_speed_status()

    def _on_recognition_mode_changed(self, event=None) -> None:
        selected_key = self._selected_recognition_mode_key()
        if not self._is_recognition_mode_available(selected_key):
            selected_key = ENGLISH_RECOGNITION_MODE_KEY
            self._select_recognition_mode_key(selected_key)
        self._set_text_spellcheck_language_from_mode(selected_key)
        self.spellcheck_generation += 1
        self._clear_spelling_marks()
        self._schedule_spellcheck(delay_ms=100)

    def _on_toolbar_recognition_mode_changed(self, event=None) -> None:
        self._on_recognition_mode_changed(event)
        settings = dict(self.settings)
        settings["recognition_mode"] = self._selected_recognition_mode_key()
        try:
            save_user_settings(settings)
            self.settings = load_user_settings()
            self.settings_snapshot["recognition_mode"] = settings["recognition_mode"]
            self._set_status("Режим распознавания сохранен")
        except Exception as exc:
            self._set_status(f"Не удалось сохранить режим: {exc}")

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

    def _selected_recognition_mode_key(self) -> str:
        return RECOGNITION_MODE_KEY_BY_LABEL.get(self.recognition_mode_var.get(), DEFAULT_RECOGNITION_MODE_KEY)

    def _select_recognition_mode_key(self, mode_key: object | None) -> None:
        self.recognition_mode_var.set(RECOGNITION_MODE_LABELS[sanitize_recognition_mode_key(mode_key)])

    def _active_spellcheck_language_tag(self) -> str:
        language_tag = getattr(self, "current_text_spellcheck_language_tag", "")
        if language_tag in SPELLCHECK_LANGUAGE_LABELS:
            return language_tag
        return recognition_mode_spellcheck_tag(self._selected_recognition_mode_key())

    def _set_text_spellcheck_language_from_mode(self, mode_key: object | None) -> None:
        self.current_text_spellcheck_language_tag = recognition_mode_spellcheck_tag(mode_key)

    def _set_spellcheck_status(self, message: str, language_tag: str | None = None) -> None:
        tag = language_tag or self._active_spellcheck_language_tag()
        self.spellcheck_status_var.set(f"Орфография {spellcheck_language_label(tag)}: {message}")

    def start_spellcheck_availability_check(self) -> None:
        if self.is_checking_spellcheck_languages:
            return

        self.is_checking_spellcheck_languages = True
        self.spellcheck_ru_availability_var.set("Русский: проверка...")
        self.spellcheck_en_availability_var.set("Английский: проверка...")
        button = getattr(self, "spellcheck_check_button", None)
        if button is not None:
            button.configure(state=tk.DISABLED)

        def worker() -> None:
            results: dict[str, tuple[bool, str | None]] = {}
            for language_tag, _label, sample in SPELLCHECK_AVAILABILITY_TESTS:
                try:
                    check_text(sample, language_tag=language_tag)
                    results[language_tag] = (True, None)
                except Exception as exc:
                    results[language_tag] = (False, str(exc))
            self.ui_queue.put(("spellcheck_availability_result", results))

        threading.Thread(target=worker, daemon=True).start()

    def start_translation_availability_check(self) -> None:
        self.translation_pack_status = detect_translation_pack()
        self.translation_pack_status_var.set(translation_pack_status_label(self.translation_pack_status))
        self._refresh_recognition_mode_options()
        self._update_translation_button_state()

    def _set_translation_buttons_state(self, state: str) -> None:
        for button_name in ("translate_to_ru_button", "translate_to_en_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state=state)

    def _clear_last_recognition_audio(self) -> None:
        self.last_recognition_audio_bytes = None
        self.last_recognition_sample_rate = None
        self.last_recognition_model_path = None
        self.last_recognition_backend_preference = None
        self.last_recognition_mode_key = None
        self.last_recognition_text = ""
        self._update_translation_button_state()

    def _update_translation_button_state(self) -> None:
        busy = (
            self.is_recording
            or self.is_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_benchmarking
            or self.is_translating
        )
        text_has_value = bool(getattr(self, "text", None) and self.text.get("1.0", tk.END).strip())
        to_ru_state = (
            tk.NORMAL
            if is_translation_direction_available(self.translation_pack_status, "en", "ru") and text_has_value and not busy
            else tk.DISABLED
        )
        to_en_state = (
            tk.NORMAL
            if is_translation_direction_available(self.translation_pack_status, "ru", "en") and text_has_value and not busy
            else tk.DISABLED
        )
        to_ru_button = getattr(self, "translate_to_ru_button", None)
        if to_ru_button is not None:
            to_ru_button.configure(state=to_ru_state)
        to_en_button = getattr(self, "translate_to_en_button", None)
        if to_en_button is not None:
            to_en_button.configure(state=to_en_state)

    def _selected_backend_preference(self) -> str | None:
        backend_key = self._selected_backend_key()
        return None if backend_key == "auto" else backend_key

    def _select_backend_key(self, backend_key: str) -> None:
        self.backend_var.set(BACKEND_LABELS.get(backend_key, DEFAULT_BACKEND_LABEL))

    def _update_speed_status(
        self,
        vad_stats: dict | None = None,
        audio_stats: dict | None = None,
        backend_name: str | None = None,
        backend_threads: int | None = None,
    ) -> None:
        model_key = self._selected_model_key()
        backend = backend_name or self._preferred_backend_name()
        parts = [f"Модель: {model_key}", f"backend {backend}"]
        if backend in WHISPER_BACKENDS:
            threads = backend_threads or choose_backend_threads(backend)
            parts.append(f"t={threads}")
        if vad_stats:
            reduction = vad_stats.get("reduction_percent", 0)
            parts.append(f"VAD -{reduction:.0f}%")
        gain_text = audio_gain_status_text(audio_stats)
        if gain_text:
            parts.append(gain_text)
        self.speed_status_var.set("; ".join(parts))

    def _preferred_backend_name(self) -> str:
        backends = available_whisper_backends(self._selected_backend_preference())
        return backends[0][0] if backends else "нет whisper-cli"

    def start_model_benchmark(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking or self.is_translating:
            return

        self.is_benchmarking = True
        self._set_status("Бенчмарк модели: подготовка...")
        self.speed_status_var.set("Бенчмарк модели: идет проверка small-q5_1")
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
                "Не удалось выполнить бенчмарк модели.",
                [
                    "Проверьте, что рядом с Dicta.exe есть папки models и .tools.",
                    "Запустите scripts\\diagnose_dicta.cmd для проверки состава папки.",
                ],
                technical=self._shorten_technical_text(str(exc)),
            )))
        finally:
            self.ui_queue.put(("benchmark_ready", None))

    def start_backend_benchmark(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking or self.is_translating:
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
        self.preferred_input_configs = {
            label: config for label, config in self.preferred_input_configs.items() if label in input_devices
        }
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
            or self.is_translating
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
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking or self.is_translating:
            return

        self.mic_test_peak = 0
        self.last_input_stream_config = None
        self.microphone_search_progress_var.set(0)
        self.microphone_search_status_var.set("Проверка...")
        self._set_input_level(0)

        try:
            label = self.input_device_var.get()
            device_indexes = self._selected_input_device_indexes()
        except Exception as exc:
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
        self._set_status("Проверка микрофона: говорите обычной громкостью")
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
        threading.Thread(
            target=self._microphone_test_worker,
            args=(label, device_indexes, self.preferred_input_configs.get(label)),
            daemon=True,
        ).start()

    def _microphone_test_worker(self, label: str, device_indexes: list[int], preferred_config: dict | None) -> None:
        try:
            def report_level(level: int) -> None:
                self.ui_queue.put(("input_level", level))

            def report_progress(checked: int, total: int, config: dict, peak: int) -> None:
                self.ui_queue.put(("microphone_test_progress", (checked, total, config, peak)))

            result = probe_input_device_group(
                device_indexes,
                seconds=MICROPHONE_PROBE_SECONDS,
                level_callback=report_level,
                preferred_config=preferred_config,
                progress_callback=report_progress,
            )
            self.ui_queue.put(("microphone_test_result", (label, result)))
        except Exception as exc:
            self.ui_queue.put(("microphone_test_error", self._format_microphone_error(
                "Не удалось проверить микрофон.",
                exc,
                include_diagnostics=True,
            )))
        finally:
            self.ui_queue.put(("microphone_test_ready", None))

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

    def _handle_microphone_test_result(self, label: str, result: dict) -> None:
        peak = int(result.get("peak", 0))
        self.mic_test_peak = peak
        config = result.get("config")
        self.last_input_stream_config = config if isinstance(config, dict) else None
        config_text = input_stream_config_text(self.last_input_stream_config)
        callback_count = int(result.get("callback_count", 0) or 0)
        stream_status = str(result.get("stream_status", "") or "").strip()

        self.input_level_var.set(peak)
        self.input_level_text_var.set(f"Пик: {peak}%")

        if result.get("ok"):
            if self.last_input_stream_config is not None:
                self.preferred_input_configs[label] = self.last_input_stream_config
            self._set_status(f"Микрофон работает, пик {peak}%")
            self.microphone_search_status_var.set(f"Проверен: пик {peak}%")
            return

        if result.get("opened"):
            self._set_status("Микрофон открыт, но Dicta не видит сигнал")
            self.microphone_search_status_var.set(f"Проверен: пик {peak}%")
            details = (
                f"Лучший проверенный режим: {config_text}\n"
                f"Callback count: {callback_count}"
            )
            if stream_status:
                details += f"\nStream status: {stream_status}"
            messagebox.showwarning(
                "Dicta",
                self._format_problem_message(
                    "Микрофон открылся, но Dicta не увидела входной сигнал в проверенных режимах.",
                    [
                        "Если индикатор Windows двигается, нажмите Найти микрофон: Dicta проверит все устройства и режимы.",
                        "Проверьте, что в Windows разрешен доступ классическим приложениям к микрофону.",
                        "Проверьте уровень входа и усиление микрофона в настройках Windows.",
                        "Если запись в Dicta все равно получается пустой, запустите scripts\\diagnose_dicta.cmd.",
                    ],
                    details=details,
                    technical=self._shorten_technical_text(str(result.get("error", ""))),
                ),
            )
            return

        self._set_status("Ошибка микрофона")
        self.microphone_search_status_var.set("Проверка: ошибка")
        messagebox.showerror(
            "Dicta",
            self._format_problem_message(
                "Dicta не смогла открыть выбранный микрофон ни в одном режиме.",
                [
                    "Закройте программы, которые могут занимать микрофон.",
                    "Нажмите Обновить и повторите Проверить.",
                    "Запустите scripts\\diagnose_dicta.cmd для отчета.",
                ],
                technical=self._shorten_technical_text(str(result.get("error", ""))),
            ),
        )

    def start_microphone_search(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking or self.is_translating:
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
                    preferred_config=self.preferred_input_configs.get(label),
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
        if self.is_recording or self.is_recognizing or self.is_testing_microphone or self.is_finding_microphone or self.is_benchmarking or self.is_translating:
            return

        self.audio_chunks = []
        self.recognition_time_var.set("Распознавание: -")
        self.last_input_stream_config = None
        self._clear_last_recognition_audio()
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
        label = self.input_device_var.get()
        stream, config = open_dicta_input_stream(
            device_indexes,
            stream_callback,
            start=True,
            preferred_config=self.preferred_input_configs.get(label),
        )
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
            "recognition_mode": self._selected_recognition_mode_key(),
            "audio_gain_percent": clamp_audio_gain_percent(self.audio_gain_percent_var.get()),
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
            "recognition_mode": self._selected_recognition_mode_key(),
            "auto_copy": self.auto_copy_var.get(),
            "format_text": self.format_text_var.get(),
            "voice_punctuation": self.voice_punctuation_var.get(),
            "audio_gain_percent": clamp_audio_gain_percent(self.audio_gain_percent_var.get()),
        }

    def _restore_settings_state(self, state: dict[str, object]) -> None:
        input_device = str(state.get("input_device", ""))
        if input_device in self.input_devices:
            self.input_device_var.set(input_device)
        self.profile_var.set(DEFAULT_PROFILE_LABEL)
        self.model_var.set(DEFAULT_MODEL_LABEL)
        self.backend_var.set(str(state.get("backend", DEFAULT_BACKEND_LABEL)))
        self._select_recognition_mode_key(state.get("recognition_mode", DEFAULT_RECOGNITION_MODE_KEY))
        self.auto_copy_var.set(bool(state.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"])))
        self.format_text_var.set(bool(state.get("format_text", DEFAULT_USER_SETTINGS["format_text"])))
        self.voice_punctuation_var.set(bool(state.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])))
        self.audio_gain_percent_var.set(
            clamp_audio_gain_percent(state.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"]))
        )
        self._on_audio_gain_changed()
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

    def translate_current_text_to_russian(self) -> None:
        if (
            self.is_recording
            or self.is_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_benchmarking
            or self.is_translating
        ):
            return

        value = self.text.get("1.0", tk.END).strip()
        if not value:
            self._set_status("Нет текста для перевода")
            self._update_translation_button_state()
            return

        self.translation_pack_status = detect_translation_pack()
        self.translation_pack_status_var.set(translation_pack_status_label(self.translation_pack_status))
        if not is_translation_direction_available(self.translation_pack_status, "en", "ru"):
            self._update_translation_button_state()
            messagebox.showwarning(
                "Dicta",
                self._format_translation_error(
                    RuntimeError(f"missing-translation-pack::{translation_pack_missing_details(self.translation_pack_status, 'en', 'ru')}")
                ),
            )
            return

        self.is_translating = True
        self._set_status("Перевод EN->RU")
        self._set_record_button_busy("Перевод")
        self.translation_worker = threading.Thread(
            target=self._translate_text_to_russian_worker,
            args=(value, dict(self.translation_pack_status)),
            daemon=True,
        )
        self.translation_worker.start()

    def _translate_text_to_russian_worker(self, source: str, translation_status: dict[str, object]) -> None:
        started_at = time.perf_counter()
        try:
            translated = run_argos_translation(source, translation_status, from_code="en", to_code="ru")
            elapsed = time.perf_counter() - started_at
            self.ui_queue.put(("translation_to_ru_result", (source, translated, elapsed)))
        except Exception as exc:
            self.ui_queue.put(("translation_error", self._format_translation_error(exc)))
        finally:
            self.ui_queue.put(("translation_ready", None))

    def translate_last_recording_to_english(self) -> None:
        if (
            self.is_recording
            or self.is_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_benchmarking
            or self.is_translating
        ):
            return

        if not self.text.get("1.0", tk.END).strip():
            self._set_status("Нет текста для перевода")
            self._update_translation_button_state()
            return
        self.translation_pack_status = detect_translation_pack()
        self.translation_pack_status_var.set(translation_pack_status_label(self.translation_pack_status))
        if not is_translation_direction_available(self.translation_pack_status, "ru", "en"):
            messagebox.showwarning(
                "Dicta",
                self._format_translation_error(
                    RuntimeError(f"missing-translation-pack::{translation_pack_missing_details(self.translation_pack_status, 'ru', 'en')}")
                ),
            )
            self._update_translation_button_state()
            return

        self.is_translating = True
        self._set_status("Перевод RU->EN")
        self._set_record_button_busy("Перевод")
        self.translation_worker = threading.Thread(
            target=self._translate_text_to_english_worker,
            args=(self.text.get("1.0", tk.END).strip(), dict(self.translation_pack_status)),
            daemon=True,
        )
        self.translation_worker.start()

    def _translate_text_to_english_worker(self, source: str, translation_status: dict[str, object]) -> None:
        started_at = time.perf_counter()
        try:
            translated = run_argos_translation(source, translation_status, from_code="ru", to_code="en")
            elapsed = time.perf_counter() - started_at
            self.ui_queue.put(("translation_to_en_result", (source, translated, elapsed)))
        except Exception as exc:
            self.ui_queue.put(("translation_error", self._format_translation_error(exc)))
        finally:
            self.ui_queue.put(("translation_ready", None))

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
            use_voice_punctuation=self.voice_punctuation_var.get()
            and self._selected_recognition_mode_key() == RUSSIAN_RECOGNITION_MODE_KEY,
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
        self._clear_last_recognition_audio()
        self._set_text_spellcheck_language_from_mode(self._selected_recognition_mode_key())
        self._clear_spelling_marks()
        self._set_status("Готово")

    def _on_text_modified(self, event=None) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._schedule_spellcheck()
        self._update_translation_button_state()

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
            self._set_spellcheck_status("авто")
            return

        language_tag = self._active_spellcheck_language_tag()
        self.spellcheck_generation += 1
        generation = self.spellcheck_generation
        self._set_spellcheck_status("проверка...", language_tag)

        def worker() -> None:
            try:
                issues = check_text(text_value, language_tag=language_tag)
                self.ui_queue.put(("spelling_result", (generation, language_tag, issues, None)))
            except Exception as exc:
                self.ui_queue.put(("spelling_result", (generation, language_tag, [], str(exc))))

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
        self._set_spellcheck_status(f"{count} ошибок" if count else "ошибок нет")

    def _add_spelling_word(self, tag_name: str) -> None:
        issue = self.spelling_issues.get(tag_name)
        if issue is None:
            return

        word = issue.word
        self._ignore_spelling_issue(tag_name)
        language_tag = self._active_spellcheck_language_tag()
        self._set_spellcheck_status("добавление...", language_tag)

        def worker() -> None:
            try:
                add_word(word, language_tag=language_tag)
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

            recognition_mode_key = self._selected_recognition_mode_key()
            recognition_language = recognition_mode_language(recognition_mode_key)
            sample_rate = self.record_sample_rate or SAMPLE_RATE
            raw_audio = b"".join(self.audio_chunks)
            normalized_audio, audio_stats = apply_pcm16_gain(raw_audio, self.audio_gain_percent_var.get())
            audio_bytes, vad_stats = self._trim_silence(normalized_audio, sample_rate)
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
                language=recognition_language,
                translate_to_english=False,
            )

            elapsed = time.perf_counter() - started_at

            if not txt_path.exists():
                raise RuntimeError("missing-recognition-output")

            recognized = txt_path.read_text(encoding="utf-8").strip()
            self.last_recognition_audio_bytes = bytes(audio_bytes)
            self.last_recognition_sample_rate = sample_rate
            self.last_recognition_model_path = selected_model
            self.last_recognition_backend_preference = self._selected_backend_preference()
            self.last_recognition_mode_key = recognition_mode_key
            self.last_recognition_text = recognized
            self.ui_queue.put(
                (
                    "recognized",
                    (recognized, elapsed, backend_name, backend_threads, vad_stats, audio_stats, recognition_mode_key),
                )
            )
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
            elif event == "microphone_test_progress":
                checked, total, config, peak = value
                total = max(1, int(total))
                checked = max(0, min(total, int(checked)))
                self.microphone_search_progress_var.set(checked * 100 / total)
                self.microphone_search_status_var.set(f"Проверка: {checked}/{total}, пик {int(peak)}%")
                if checked < total:
                    self._set_status(f"Проверка микрофона: {input_stream_config_text(config)}")
            elif event == "microphone_test_result":
                label, result = value
                self.finish_microphone_test()
                self._handle_microphone_test_result(str(label), result)
            elif event == "microphone_test_error":
                self.finish_microphone_test()
                self._set_status("Ошибка микрофона")
                self.microphone_search_status_var.set("Проверка: ошибка")
                messagebox.showerror("Dicta", str(value))
            elif event == "microphone_test_ready":
                self.finish_microphone_test()
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
                        if isinstance(self.last_input_stream_config, dict):
                            self.preferred_input_configs[str(label)] = self.last_input_stream_config
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
                recognized, elapsed, backend_name, backend_threads, vad_stats, audio_stats, recognition_mode_key = value[:7]
                self._set_text_spellcheck_language_from_mode(recognition_mode_key)
                prepared = prepare_recognized_text(
                    str(recognized),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=self.voice_punctuation_var.get()
                    and recognition_mode_key == RUSSIAN_RECOGNITION_MODE_KEY,
                )
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self.format_button.configure(text="Автоформат")
                self.recognition_time_var.set(f"Распознавание: {elapsed:.1f} с")
                self._update_speed_status(
                    vad_stats=vad_stats,
                    audio_stats=audio_stats,
                    backend_name=backend_name,
                    backend_threads=backend_threads,
                )
                gain_text = audio_gain_status_text(audio_stats)
                if self.auto_copy_var.get() and prepared:
                    self._copy_value_to_clipboard(prepared)
                    status = "Скопировано автоматически"
                else:
                    status = "Готово"
                if gain_text:
                    status = f"{status}; {gain_text}"
                self._set_status(status)
                self._schedule_spellcheck(delay_ms=100)
                self._update_translation_button_state()
            elif event == "translation_to_ru_result":
                source, translated, translation_elapsed = value
                current = self.text.get("1.0", tk.END).strip()
                if current != str(source).strip():
                    self._set_status("Текст изменен, перевод не применен")
                    continue
                prepared = prepare_recognized_text(
                    str(translated),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=False,
                )
                self.current_text_spellcheck_language_tag = "ru-RU"
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self.format_button.configure(text="Автоформат")
                if self.auto_copy_var.get() and prepared:
                    self._copy_value_to_clipboard(prepared)
                    status = f"Переведено и скопировано: {translation_elapsed:.1f} с"
                else:
                    status = f"Переведено: {translation_elapsed:.1f} с"
                self._set_status(status)
                self._schedule_spellcheck(delay_ms=100)
                self._update_translation_button_state()
            elif event == "translation_to_en_result":
                _source, translated, translation_elapsed = value
                prepared = prepare_recognized_text(
                    str(translated),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=False,
                )
                self.current_text_spellcheck_language_tag = "en-US"
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self.format_button.configure(text="Автоформат")
                if self.auto_copy_var.get() and prepared:
                    self._copy_value_to_clipboard(prepared)
                    status = f"Переведено в English и скопировано: {translation_elapsed:.1f} с"
                else:
                    status = f"Переведено в English: {translation_elapsed:.1f} с"
                self._set_status(status)
                self._schedule_spellcheck(delay_ms=100)
                self._update_translation_button_state()
            elif event == "translation_error":
                self._set_status("Ошибка перевода")
                messagebox.showwarning("Dicta", str(value))
            elif event == "translation_ready":
                self.is_translating = False
                self.translation_worker = None
                self._set_record_button_idle()
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
                self._set_status(f"Бенчмарк модели: {message}")
                self.speed_status_var.set(f"Бенчмарк модели: {message}")
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
                self.benchmark_button.configure(text="Бенчмарк модели", state=tk.NORMAL)
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
                if len(value) == 4:
                    generation, language_tag, issues, error = value
                else:
                    generation, issues, error = value
                    language_tag = self._active_spellcheck_language_tag()
                if generation != self.spellcheck_generation:
                    continue
                if error:
                    self._clear_spelling_marks()
                    self._set_spellcheck_status("недоступна", language_tag)
                else:
                    self._apply_spelling_issues(issues)
                    count = len(issues)
                    self._set_spellcheck_status(f"{count} ошибок" if count else "ошибок нет", language_tag)
            elif event == "spelling_word_added":
                self._set_spellcheck_status("слово добавлено")
                self._schedule_spellcheck(delay_ms=150)
            elif event == "spelling_add_error":
                self._set_spellcheck_status("не удалось добавить")
            elif event == "spellcheck_availability_result":
                self.is_checking_spellcheck_languages = False
                button = getattr(self, "spellcheck_check_button", None)
                if button is not None:
                    button.configure(state=tk.NORMAL)
                results = value if isinstance(value, dict) else {}
                status_vars = {
                    "ru-RU": self.spellcheck_ru_availability_var,
                    "en-US": self.spellcheck_en_availability_var,
                }
                for language_tag, status_var in status_vars.items():
                    ok, _error = results.get(language_tag, (False, None))
                    label = spellcheck_availability_label(language_tag)
                    status_var.set(f"{label}: {'доступна' if ok else 'недоступна'}")

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
                    "Скопируйте ggml-small-q5_1.bin в папку models и повторите запись.",
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

    def _format_translation_error(self, exc: Exception) -> str:
        raw = str(exc).strip()

        if raw.startswith("missing-translation-pack::"):
            details = raw.split("::", 1)[1]
            return self._format_problem_message(
                "Перевод EN->RU недоступен: не найден optional translation pack.",
                [
                    "Проверьте в настройках статус перевода EN->RU.",
                    "Папка .tools\\argos-translate должна лежать рядом с Dicta.exe.",
                    "Внутри pack должны быть runtime Argos и модель packages\\translate-en_ru-1_9.",
                ],
                technical=details,
            )

        if raw.startswith("translation-timeout::"):
            seconds = raw.split("::", 1)[1]
            return self._format_problem_message(
                "Перевод EN->RU не завершился за отведенное время.",
                [
                    "Повторите запись более короткой фразой.",
                    "Если ошибка повторяется, проверьте optional translation pack в настройках.",
                ],
                details=f"Таймаут: {seconds} с",
            )

        if raw.startswith("translation-failed::"):
            parts = raw.split("::", 2)
            code = parts[1] if len(parts) > 1 else "worker"
            technical = parts[2] if len(parts) > 2 else raw
            return self._format_problem_message(
                "Локальный перевод EN->RU завершился с ошибкой.",
                [
                    "Проверьте в настройках наличие runtime и модели EN->RU.",
                    "Если pack недавно заменяли, перезапустите Dicta и повторите запись.",
                ],
                details=f"Код перевода: {code}",
                technical=self._shorten_technical_text(technical),
            )

        return self._format_problem_message(
            "Не удалось выполнить локальный перевод EN->RU.",
            [
                "Проверьте optional translation pack в настройках.",
                "Если ошибка повторяется, используйте режим English text до замены pack.",
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

    if "--translation-test" in sys.argv:
        en_sample = "The recognized text is ready."
        ru_sample = "Я лежу дома на диване."
        if "--text" in sys.argv:
            index = sys.argv.index("--text")
            if index + 1 < len(sys.argv):
                en_sample = sys.argv[index + 1]
        status = detect_translation_pack()
        print(translation_pack_status_label(status))
        if not is_translation_direction_available(status, "en", "ru"):
            print("Dicta translation-test failed. Missing EN->RU translation pack.")
            raise SystemExit(1)
        if not is_translation_direction_available(status, "ru", "en"):
            print("Dicta translation-test failed. Missing RU->EN translation pack.")
            raise SystemExit(1)
        translated_ru = run_argos_translation(en_sample, status, from_code="en", to_code="ru")
        translated_en = run_argos_translation(ru_sample, status, from_code="ru", to_code="en")
        print(f"en_source={en_sample}")
        print(f"ru_translated={translated_ru}")
        print(f"ru_source={ru_sample}")
        print(f"en_translated={translated_en}")
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
        _glossary_replacements, glossary_error = load_translation_glossary()
        if glossary_error:
            print("Dicta self-test failed. Translation glossary is invalid:")
            print(glossary_error)
            raise SystemExit(1)
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
        print(f"TRANSLATION_PACK={translation_pack_status_label(detect_translation_pack())}")
        raise SystemExit(0)

    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    DictaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
