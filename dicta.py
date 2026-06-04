import queue
import atexit
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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from comtypes.client import CreateObject
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
    "sse42": APP_DIR / ".tools" / "whisper.cpp-build-sse42" / "bin" / "whisper-cli.exe",
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
    "sse42": "SSE4.2",
    "compat": "Compat",
}
BACKEND_KEY_BY_LABEL = {label: key for key, label in BACKEND_LABELS.items()}
DEFAULT_BACKEND_LABEL = BACKEND_LABELS["auto"]
FALLBACK_AUTO_BACKEND_KEY = "compat"
MODELS_DIR = APP_DIR / "models"
MODEL_LABELS = {
    "small-q5_1": "small-q5_1: стандарт",
    "small": "small: качество выше",
    "medium-q5_0": "medium-q5_0: качество, опция",
    "medium": "medium: качество, опция",
    "large-v3-turbo-q5_0": "large-v3-turbo-q5_0: максимум, опция",
    "large-v3-turbo": "large-v3-turbo: максимум, опция",
}
MODEL_FILES = {
    "small-q5_1": MODELS_DIR / "ggml-small-q5_1.bin",
    "small": MODELS_DIR / "ggml-small.bin",
    "medium-q5_0": MODELS_DIR / "ggml-medium-q5_0.bin",
    "medium": MODELS_DIR / "ggml-medium.bin",
    "large-v3-turbo-q5_0": MODELS_DIR / "ggml-large-v3-turbo-q5_0.bin",
    "large-v3-turbo": MODELS_DIR / "ggml-large-v3-turbo.bin",
}
MODEL_OPTIONS = {MODEL_LABELS[key]: MODEL_FILES[key] for key in MODEL_LABELS}
MODEL_KEY_BY_LABEL = {label: key for key, label in MODEL_LABELS.items()}
DEFAULT_MODEL_LABEL = MODEL_LABELS["small-q5_1"]
REQUIRED_MODEL_KEYS = ("small-q5_1",)
PACKAGE_MODEL_KEYS = (
    "small-q5_1",
    "small",
    "medium-q5_0",
    "medium",
    "large-v3-turbo-q5_0",
    "large-v3-turbo",
)
QUALITY_MODEL_PREFERENCE = (
    "large-v3-turbo",
    "large-v3-turbo-q5_0",
    "medium",
    "medium-q5_0",
    "small",
    "small-q5_1",
)
BACKEND_BENCHMARK_MODEL_PREFERENCE = (
    "small-q5_1",
    "small",
    "medium-q5_0",
    "medium",
    "large-v3-turbo-q5_0",
    "large-v3-turbo",
)
FALLBACK_AUTO_MODEL_KEY = "small-q5_1"
TRANSLATION_PACK_DIR = APP_DIR / ".tools" / "argos-translate"
ARGOS_PACKAGES_DIR = TRANSLATION_PACK_DIR / "packages"
ARGOS_DATA_DIR = TRANSLATION_PACK_DIR / "data"
ARGOS_CONFIG_DIR = TRANSLATION_PACK_DIR / "config"
ARGOS_CACHE_DIR = TRANSLATION_PACK_DIR / "cache"
ARGOS_WORKER_EXE_CANDIDATES = (
    TRANSLATION_PACK_DIR / "argos-worker.exe",
    TRANSLATION_PACK_DIR / "argos-worker" / "argos-worker.exe",
)
ARGOS_WORKER_EXE = ARGOS_WORKER_EXE_CANDIDATES[0]
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
RU_RECOGNITION_DICTIONARY_PATH = APP_DIR / "dicta_dictionary_ru.json"
ARGOS_TRANSLATION_TIMEOUT_SECONDS = 45
ARGOS_WORKER_FIRST_TRANSLATION_TIMEOUT_SECONDS = 120
ARGOS_WORKER_STOP_TIMEOUT_SECONDS = 3
ARGOS_WORKER_IDLE_STOP_SECONDS = 30
ARGOS_WORKER_WARMUP_TEXT_BY_DIRECTION = {
    ("en", "ru"): "test",
    ("ru", "en"): "тест",
}
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
AUDIO_SOURCE_LABELS = {
    "microphone": "Микрофон",
    "system": "Системный звук встречи",
    "combined": "Системный звук + микрофон",
}
AUDIO_SOURCE_KEY_BY_LABEL = {label: key for key, label in AUDIO_SOURCE_LABELS.items()}
DEFAULT_AUDIO_SOURCE_KEY = "microphone"
DEFAULT_SYSTEM_OUTPUT_DEVICE_ID = "default"
DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL = "По умолчанию Windows"
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
INPUT_SAMPLE_RATE_FALLBACKS = (48000, 44100, 32000)
INPUT_SAMPLE_DTYPES = ("int16", "float32", "int24", "int32")
MICROPHONE_PROBE_SECONDS = 1.5
SYSTEM_AUDIO_TEST_SECONDS = 1.5
PROTOCOL_CHUNK_SECONDS = 60.0
PROTOCOL_FINAL_CHUNK_MIN_SECONDS = 1.0
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
RU_POSTPROCESS_MIN_WORD_LENGTH = 5
RU_POSTPROCESS_MAX_EDIT_DISTANCE = 2
RU_POSTPROCESS_LOG_LIMIT = 200
WHISPER_PROGRESS_PATTERN = re.compile(r"progress\s*=\s*(\d{1,3})%", re.IGNORECASE)
RECOGNITION_FALLBACK_PROGRESS_MAX = 90
BENCHMARK_AUDIO_SECONDS = 2.0
BENCHMARK_TOTAL_TIMEOUT_SECONDS = 180
BENCHMARK_ATTEMPT_TIMEOUT_SECONDS = 180
BENCHMARK_QUICK_BACKEND_LIMIT = 0
DEFAULT_WHISPER_THREADS = 4
GPU_BACKEND_KEYS = {"vulkan", "cuda", "openvino"}
GPU_BACKEND_PRIORITY = ("cuda", "vulkan", "openvino")
CPU_BACKEND_PRIORITY = ("avx2", "sse42")
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
    "audio_source": DEFAULT_AUDIO_SOURCE_KEY,
    "system_output_device_id": DEFAULT_SYSTEM_OUTPUT_DEVICE_ID,
    "recognition_mode": DEFAULT_RECOGNITION_MODE_KEY,
    "backend": "auto",
    "model_key": FALLBACK_AUTO_MODEL_KEY,
    "audio_gain_percent": 0,
}


WASAPI_E_RENDER = 0
WASAPI_E_CONSOLE = 0
WASAPI_CLSCTX_ALL = 23
WASAPI_DEVICE_STATE_ACTIVE = 1
WASAPI_SHAREMODE_SHARED = 0
WASAPI_STREAMFLAGS_LOOPBACK = 0x00020000
WASAPI_BUFFERFLAGS_SILENT = 0x00000002
WASAPI_STGM_READ = 0
WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
VT_LPWSTR = 31
KSDATAFORMAT_SUBTYPE_PCM = "{00000001-0000-0010-8000-00aa00389b71}"
KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = "{00000003-0000-0010-8000-00aa00389b71}"
PKEY_DEVICE_FRIENDLY_NAME_FMTID = "{A45C254E-DF1C-4EFD-8020-67D146A850E0}"
PKEY_DEVICE_FRIENDLY_NAME_PID = 14


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint),
        ("nAvgBytesPerSec", ctypes.c_uint),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class WAVEFORMATEXTENSIBLE(ctypes.Structure):
    _fields_ = [
        ("Format", WAVEFORMATEX),
        ("wValidBitsPerSample", ctypes.c_ushort),
        ("dwChannelMask", ctypes.c_ulong),
        ("SubFormat", GUID),
    ]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [
        ("fmtid", GUID),
        ("pid", ctypes.c_ulong),
    ]


class PROPVARIANT_UNION(ctypes.Union):
    _fields_ = [
        ("pwszVal", ctypes.c_wchar_p),
        ("pszVal", ctypes.c_char_p),
        ("ulVal", ctypes.c_ulong),
        ("uhVal", ctypes.c_ushort),
        ("boolVal", ctypes.c_short),
        ("llVal", ctypes.c_longlong),
        ("ullVal", ctypes.c_ulonglong),
    ]


class PROPVARIANT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("value", PROPVARIANT_UNION),
    ]


PKEY_DEVICE_FRIENDLY_NAME = PROPERTYKEY(
    GUID(PKEY_DEVICE_FRIENDLY_NAME_FMTID),
    PKEY_DEVICE_FRIENDLY_NAME_PID,
)


class IPropertyStore(IUnknown):
    _iid_ = GUID("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], ctypes.POINTER(ctypes.c_ulong), "cProps")),
        COMMETHOD([], HRESULT, "GetAt"),
        COMMETHOD(
            [],
            HRESULT,
            "GetValue",
            (["in"], ctypes.POINTER(PROPERTYKEY), "key"),
            (["out"], ctypes.POINTER(PROPVARIANT), "pv"),
        ),
        COMMETHOD([], HRESULT, "SetValue"),
        COMMETHOD([], HRESULT, "Commit"),
    ]


class IMMDevice(IUnknown):
    _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "Activate",
            (["in"], ctypes.POINTER(GUID), "iid"),
            (["in"], ctypes.c_ulong, "dwClsCtx"),
            (["in"], ctypes.c_void_p, "pActivationParams"),
            (["out"], ctypes.POINTER(ctypes.c_void_p), "ppInterface"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "OpenPropertyStore",
            (["in"], ctypes.c_ulong, "stgmAccess"),
            (["out"], ctypes.POINTER(ctypes.POINTER(IPropertyStore)), "ppProperties"),
        ),
        COMMETHOD([], HRESULT, "GetId", (["out"], ctypes.POINTER(ctypes.c_wchar_p), "ppstrId")),
        COMMETHOD([], HRESULT, "GetState", (["out"], ctypes.POINTER(ctypes.c_ulong), "pdwState")),
    ]


class IMMDeviceCollection(IUnknown):
    _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-C0F65C15A6D5}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCount", (["out"], ctypes.POINTER(ctypes.c_uint), "pcDevices")),
        COMMETHOD(
            [],
            HRESULT,
            "Item",
            (["in"], ctypes.c_uint, "nDevice"),
            (["out"], ctypes.POINTER(ctypes.POINTER(IMMDevice)), "ppDevice"),
        ),
    ]


class IMMDeviceEnumerator(IUnknown):
    _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "EnumAudioEndpoints",
            (["in"], ctypes.c_int, "dataFlow"),
            (["in"], ctypes.c_ulong, "dwStateMask"),
            (["out"], ctypes.POINTER(ctypes.POINTER(IMMDeviceCollection)), "ppDevices"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetDefaultAudioEndpoint",
            (["in"], ctypes.c_int, "dataFlow"),
            (["in"], ctypes.c_int, "role"),
            (["out"], ctypes.POINTER(ctypes.POINTER(IMMDevice)), "ppEndpoint"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetDevice",
            (["in"], ctypes.c_wchar_p, "pwstrId"),
            (["out"], ctypes.POINTER(ctypes.POINTER(IMMDevice)), "ppDevice"),
        ),
        COMMETHOD([], HRESULT, "RegisterEndpointNotificationCallback"),
        COMMETHOD([], HRESULT, "UnregisterEndpointNotificationCallback"),
    ]


class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "Initialize",
            (["in"], ctypes.c_int, "ShareMode"),
            (["in"], ctypes.c_ulong, "StreamFlags"),
            (["in"], ctypes.c_longlong, "hnsBufferDuration"),
            (["in"], ctypes.c_longlong, "hnsPeriodicity"),
            (["in"], ctypes.POINTER(WAVEFORMATEX), "pFormat"),
            (["in"], ctypes.POINTER(GUID), "AudioSessionGuid"),
        ),
        COMMETHOD([], HRESULT, "GetBufferSize", (["out"], ctypes.POINTER(ctypes.c_uint), "pNumBufferFrames")),
        COMMETHOD([], HRESULT, "GetStreamLatency"),
        COMMETHOD([], HRESULT, "GetCurrentPadding"),
        COMMETHOD([], HRESULT, "IsFormatSupported"),
        COMMETHOD([], HRESULT, "GetMixFormat", (["out"], ctypes.POINTER(ctypes.POINTER(WAVEFORMATEX)), "ppDeviceFormat")),
        COMMETHOD([], HRESULT, "GetDevicePeriod"),
        COMMETHOD([], HRESULT, "Start"),
        COMMETHOD([], HRESULT, "Stop"),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "SetEventHandle"),
        COMMETHOD(
            [],
            HRESULT,
            "GetService",
            (["in"], ctypes.POINTER(GUID), "riid"),
            (["out"], ctypes.POINTER(ctypes.c_void_p), "ppv"),
        ),
    ]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "GetBuffer",
            (["out"], ctypes.POINTER(ctypes.POINTER(ctypes.c_byte)), "ppData"),
            (["out"], ctypes.POINTER(ctypes.c_uint), "pNumFramesToRead"),
            (["out"], ctypes.POINTER(ctypes.c_ulong), "pdwFlags"),
            (["out"], ctypes.POINTER(ctypes.c_ulonglong), "pu64DevicePosition"),
            (["out"], ctypes.POINTER(ctypes.c_ulonglong), "pu64QPCPosition"),
        ),
        COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], ctypes.c_uint, "NumFramesRead")),
        COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], ctypes.POINTER(ctypes.c_uint), "pNumFramesInNextPacket")),
    ]


@dataclass(frozen=True)
class WasapiOutputDeviceInfo:
    device_id: str
    name: str
    is_default: bool = False


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


def pcm16_mono_to_array(audio: bytes) -> array:
    usable_length = len(audio) - (len(audio) % SAMPLE_WIDTH_BYTES)
    samples = array("h")
    if usable_length <= 0:
        return samples
    samples.frombytes(audio[:usable_length])
    return samples


def resample_pcm16_mono(audio: bytes, source_rate: int, target_rate: int = SAMPLE_RATE) -> bytes:
    source_rate = max(1, int(source_rate or target_rate))
    target_rate = max(1, int(target_rate or source_rate))
    samples = pcm16_mono_to_array(audio)
    if not samples or source_rate == target_rate:
        return samples.tobytes()

    target_count = max(1, int(round(len(samples) * target_rate / source_rate)))
    if target_count == 1:
        return array("h", [int(samples[0])]).tobytes()

    result = array("h")
    scale = (len(samples) - 1) / (target_count - 1)
    for index in range(target_count):
        position = index * scale
        left = int(position)
        right = min(left + 1, len(samples) - 1)
        fraction = position - left
        value = int(round(int(samples[left]) * (1.0 - fraction) + int(samples[right]) * fraction))
        result.append(max(-32768, min(32767, value)))
    return result.tobytes()


def mix_pcm16_mono(a: bytes, b: bytes) -> bytes:
    first = pcm16_mono_to_array(a)
    second = pcm16_mono_to_array(b)
    sample_count = max(len(first), len(second))
    if sample_count <= 0:
        return b""

    mixed = array("h")
    for index in range(sample_count):
        left = int(first[index]) if index < len(first) else 0
        right = int(second[index]) if index < len(second) else 0
        mixed.append(max(-32768, min(32767, left + right)))
    return mixed.tobytes()


def mix_recording_sources(
    system_audio: bytes,
    system_rate: int,
    microphone_audio: bytes,
    microphone_rate: int,
    target_rate: int = SAMPLE_RATE,
) -> bytes:
    system_resampled = resample_pcm16_mono(system_audio, system_rate, target_rate)
    microphone_resampled = resample_pcm16_mono(microphone_audio, microphone_rate, target_rate)
    return mix_pcm16_mono(system_resampled, microphone_resampled)


def wasapi_create_device_enumerator() -> IMMDeviceEnumerator:
    return CreateObject(
        GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"),
        interface=IMMDeviceEnumerator,
    )


def wasapi_device_id(device: IMMDevice) -> str:
    return str(device.GetId())


def wasapi_output_device_name(device: IMMDevice) -> str:
    prop_variant: PROPVARIANT | None = None
    try:
        store = device.OpenPropertyStore(WASAPI_STGM_READ)
        prop_variant = store.GetValue(ctypes.byref(PKEY_DEVICE_FRIENDLY_NAME))
        if int(prop_variant.vt) == VT_LPWSTR and prop_variant.pwszVal:
            return clean_input_device_name(str(prop_variant.pwszVal))
    except Exception:
        pass
    finally:
        if prop_variant is not None:
            try:
                ctypes.windll.ole32.PropVariantClear(ctypes.byref(prop_variant))
            except Exception:
                pass
    device_id = wasapi_device_id(device)
    return device_id[-48:] if len(device_id) > 48 else device_id


def wasapi_default_output_device(enumerator: IMMDeviceEnumerator | None = None) -> IMMDevice:
    enumerator = enumerator or wasapi_create_device_enumerator()
    return enumerator.GetDefaultAudioEndpoint(WASAPI_E_RENDER, WASAPI_E_CONSOLE)


def wasapi_output_device_by_id(device_id: str | None) -> IMMDevice:
    enumerator = wasapi_create_device_enumerator()
    if not device_id or device_id == DEFAULT_SYSTEM_OUTPUT_DEVICE_ID:
        return wasapi_default_output_device(enumerator)
    return enumerator.GetDevice(str(device_id))


def collect_wasapi_output_devices() -> list[WasapiOutputDeviceInfo]:
    if os.name != "nt":
        return []

    comtypes.CoInitialize()
    try:
        enumerator = wasapi_create_device_enumerator()
        default_id = ""
        try:
            default_id = wasapi_device_id(wasapi_default_output_device(enumerator))
        except Exception:
            default_id = ""

        collection = enumerator.EnumAudioEndpoints(WASAPI_E_RENDER, WASAPI_DEVICE_STATE_ACTIVE)
        count = int(collection.GetCount())
        devices: list[WasapiOutputDeviceInfo] = []
        seen_ids: set[str] = set()
        for index in range(count):
            device = collection.Item(index)
            try:
                device_id = wasapi_device_id(device)
                if not device_id or device_id in seen_ids:
                    continue
                seen_ids.add(device_id)
                devices.append(
                    WasapiOutputDeviceInfo(
                        device_id=device_id,
                        name=wasapi_output_device_name(device),
                        is_default=bool(default_id and device_id == default_id),
                    )
                )
            except Exception:
                continue
        devices.sort(key=lambda item: (not item.is_default, item.name.lower()))
        return devices
    finally:
        comtypes.CoUninitialize()


def build_system_output_device_choices(
    devices: list[WasapiOutputDeviceInfo],
) -> tuple[list[str], dict[str, str], dict[str, WasapiOutputDeviceInfo]]:
    default_device = next((device for device in devices if device.is_default), None)
    default_label = DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL
    if default_device is not None and default_device.name:
        default_label = f"{DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL}: {default_device.name}"
    labels = [default_label]
    label_to_id = {default_label: DEFAULT_SYSTEM_OUTPUT_DEVICE_ID}
    id_to_device = {device.device_id: device for device in devices}
    used_labels = set(labels)
    name_counts: dict[str, int] = {}
    for device in devices:
        device_name = device.name or "Устройство вывода Windows"
        base_label = f"Только это устройство: {device_name}"
        duplicate_count = name_counts.get(base_label, 0) + 1
        name_counts[base_label] = duplicate_count
        label = base_label if duplicate_count == 1 else f"{base_label} #{duplicate_count}"
        while label in used_labels:
            duplicate_count += 1
            label = f"{base_label} #{duplicate_count}"
        used_labels.add(label)
        labels.append(label)
        label_to_id[label] = device.device_id
    return labels, label_to_id, id_to_device


def system_output_device_label_for_id(label_to_id: dict[str, str], device_id: object | None) -> str:
    sanitized = sanitize_system_output_device_id(device_id)
    fallback_label = next(
        (
            label
            for label, candidate in label_to_id.items()
            if candidate == DEFAULT_SYSTEM_OUTPUT_DEVICE_ID
        ),
        DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL,
    )
    for label, candidate in label_to_id.items():
        if candidate == sanitized:
            return label
    return fallback_label


def wasapi_mix_format_info(
    format_pointer,
    *,
    description: str = "Системный звук Windows",
    output_device_id: str | None = None,
    output_device_name: str | None = None,
) -> dict:
    fmt = format_pointer.contents
    sample_format = "float32" if fmt.wBitsPerSample == 32 else f"pcm{fmt.wBitsPerSample}"
    subformat = ""
    if fmt.wFormatTag == WAVE_FORMAT_IEEE_FLOAT:
        sample_format = "float32"
    elif fmt.wFormatTag == WAVE_FORMAT_PCM:
        sample_format = f"pcm{fmt.wBitsPerSample}"
    elif fmt.wFormatTag == WAVE_FORMAT_EXTENSIBLE and fmt.cbSize >= 22:
        try:
            extensible = ctypes.cast(format_pointer, ctypes.POINTER(WAVEFORMATEXTENSIBLE)).contents
            subformat = str(extensible.SubFormat).lower()
            if subformat == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT:
                sample_format = "float32"
            elif subformat == KSDATAFORMAT_SUBTYPE_PCM:
                sample_format = f"pcm{fmt.wBitsPerSample}"
        except Exception:
            pass
    return {
        "source_type": "system_loopback",
        "description": description,
        "output_device_id": output_device_id or DEFAULT_SYSTEM_OUTPUT_DEVICE_ID,
        "output_device_name": output_device_name or "",
        "sample_rate": int(fmt.nSamplesPerSec),
        "source_channels": int(fmt.nChannels),
        "channels": CHANNELS,
        "bits_per_sample": int(fmt.wBitsPerSample),
        "block_align": int(fmt.nBlockAlign),
        "format_tag": int(fmt.wFormatTag),
        "sample_format": sample_format,
        "subformat": subformat,
    }


def wasapi_mix_to_pcm16_mono(audio: bytes, config: dict) -> bytes:
    sample_format = str(config.get("sample_format", "float32"))
    source_channels = max(1, int(config.get("source_channels", CHANNELS)))
    if sample_format == "float32":
        return float32_pcm_to_pcm16_mono(audio, source_channels)
    if sample_format == "pcm16":
        return downmix_pcm16_to_mono(audio, source_channels)
    if sample_format == "pcm24":
        return int24_pcm_to_pcm16_mono(audio, source_channels)
    if sample_format == "pcm32":
        return int32_pcm_to_pcm16_mono(audio, source_channels)
    return b""


class WasapiLoopbackStream:
    def __init__(self, callback, device_id: str | None = None) -> None:
        self.callback = callback
        self.device_id = sanitize_system_output_device_id(device_id)
        self.config: dict | None = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_error: Exception | None = None

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Системный звук доступен только на Windows.")
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        if not self._ready_event.wait(timeout=5):
            self.stop()
            raise RuntimeError("Не удалось запустить запись системного звука.")
        if self._start_error is not None:
            raise RuntimeError(f"Не удалось открыть системный звук: {self._start_error}")

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    def close(self) -> None:
        self.stop()

    def _capture_loop(self) -> None:
        client = None
        capture_client = None
        started = False
        mix_format = None
        comtypes.CoInitialize()
        try:
            device = wasapi_output_device_by_id(self.device_id)
            if int(device.GetState()) != WASAPI_DEVICE_STATE_ACTIVE:
                raise RuntimeError("устройство вывода Windows не активно")
            actual_device_id = wasapi_device_id(device)
            output_device_name = wasapi_output_device_name(device)

            client_pointer = device.Activate(ctypes.byref(IAudioClient._iid_), WASAPI_CLSCTX_ALL, None)
            client = ctypes.cast(client_pointer, ctypes.POINTER(IAudioClient))
            mix_format = client.GetMixFormat()
            self.config = wasapi_mix_format_info(
                mix_format,
                description=f"Системный звук: {output_device_name}",
                output_device_id=actual_device_id,
                output_device_name=output_device_name,
            )
            try:
                client.Initialize(
                    WASAPI_SHAREMODE_SHARED,
                    WASAPI_STREAMFLAGS_LOOPBACK,
                    10_000_000,
                    0,
                    mix_format,
                    None,
                )
            finally:
                try:
                    ctypes.windll.ole32.CoTaskMemFree(mix_format)
                except Exception:
                    pass
                mix_format = None
            capture_pointer = client.GetService(ctypes.byref(IAudioCaptureClient._iid_))
            capture_client = ctypes.cast(capture_pointer, ctypes.POINTER(IAudioCaptureClient))
            client.Start()
            started = True
            self._ready_event.set()

            while not self._stop_event.is_set():
                packet_size = int(capture_client.GetNextPacketSize())
                if packet_size <= 0:
                    time.sleep(0.02)
                    continue
                while packet_size > 0 and not self._stop_event.is_set():
                    data, frames, flags, _position, _qpc = capture_client.GetBuffer()
                    try:
                        byte_count = int(frames) * int(self.config.get("block_align", 0))
                        if flags & WASAPI_BUFFERFLAGS_SILENT or not data:
                            raw_audio = b"\x00" * byte_count
                        else:
                            raw_audio = ctypes.string_at(data, byte_count)
                        pcm16 = wasapi_mix_to_pcm16_mono(raw_audio, self.config)
                        if pcm16:
                            self.callback(pcm16, int(frames), None, None)
                    finally:
                        capture_client.ReleaseBuffer(int(frames))
                    packet_size = int(capture_client.GetNextPacketSize())
        except Exception as exc:
            self._start_error = exc
            self._ready_event.set()
        finally:
            if started and client is not None:
                try:
                    client.Stop()
                except Exception:
                    pass
            if mix_format is not None:
                try:
                    ctypes.windll.ole32.CoTaskMemFree(mix_format)
                except Exception:
                    pass
            comtypes.CoUninitialize()


class CombinedRecordingStream:
    def __init__(self, *streams) -> None:
        self.streams = [stream for stream in streams if stream is not None]

    def stop(self) -> None:
        for stream in reversed(self.streams):
            try:
                stream.stop()
            except Exception:
                pass

    def close(self) -> None:
        for stream in reversed(self.streams):
            try:
                stream.close()
            except Exception:
                pass


def open_wasapi_loopback_stream(
    callback,
    start: bool = False,
    device_id: str | None = None,
) -> tuple[WasapiLoopbackStream, dict]:
    stream = WasapiLoopbackStream(callback, device_id=device_id)
    if start:
        stream.start()
    config = stream.config or {
        "source_type": "system_loopback",
        "description": "Системный звук Windows",
        "output_device_id": sanitize_system_output_device_id(device_id),
        "output_device_name": "",
        "sample_rate": SAMPLE_RATE,
        "source_channels": CHANNELS,
        "channels": CHANNELS,
        "sample_format": "unknown",
    }
    return stream, config


def measure_wasapi_loopback_level(device_id: str | None, seconds: float = SYSTEM_AUDIO_TEST_SECONDS) -> dict:
    peak = 0
    byte_count = 0
    callback_count = 0

    def callback(data, frames, time_info, status) -> None:
        nonlocal peak, byte_count, callback_count
        audio = bytes(data)
        callback_count += 1
        byte_count += len(audio)
        peak = max(peak, audio_peak_percent(audio))

    stream = None
    config: dict | None = None
    try:
        stream, config = open_wasapi_loopback_stream(callback, start=True, device_id=device_id)
        deadline = time.perf_counter() + max(0.1, float(seconds))
        while time.perf_counter() < deadline:
            time.sleep(0.05)
        return {
            "opened": True,
            "ok": peak >= MICROPHONE_WORKING_PEAK_PERCENT,
            "peak": peak,
            "bytes": byte_count,
            "callback_count": callback_count,
            "config": config,
        }
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


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
    if config.get("source_type") == "combined":
        return (
            "Системный звук + микрофон, "
            f"{config.get('sample_rate', SAMPLE_RATE)} Hz, PCM16"
        )
    if config.get("source_type") == "system_loopback":
        source_channels = int(config.get("source_channels", CHANNELS))
        channel_text = "1 канал" if source_channels == 1 else f"{source_channels}->1 канал"
        sample_format = str(config.get("sample_format", "system"))
        return (
            f"{config.get('description', 'Системный звук Windows')}, "
            f"{config.get('sample_rate', SAMPLE_RATE)} Hz, {channel_text}, {sample_format}->PCM16"
        )
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


def ru_postprocess_log_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Dicta" / "postprocess_corrections.log"
    return APP_DIR / "postprocess_corrections.log"


RU_POSTPROCESS_LOG_PATH = ru_postprocess_log_path()


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


def sanitize_audio_source_key(value: object | None) -> str:
    if isinstance(value, str) and value in AUDIO_SOURCE_LABELS:
        return value
    if isinstance(value, str) and value in AUDIO_SOURCE_KEY_BY_LABEL:
        return AUDIO_SOURCE_KEY_BY_LABEL[value]
    return DEFAULT_AUDIO_SOURCE_KEY


def sanitize_system_output_device_id(value: object | None) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_SYSTEM_OUTPUT_DEVICE_ID


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
    for worker_exe in ARGOS_WORKER_EXE_CANDIDATES:
        if worker_exe.exists():
            return "exe", worker_exe, None

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


def _build_argos_worker_env(packages_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ARGOS_DEBUG": "0",
            "ARGOS_DEVICE_TYPE": "cpu",
            "ARGOS_BEAM_SIZE": "1",
            "ARGOS_COMPUTE_TYPE": "int8",
            "ARGOS_PACKAGES_DIR": str(packages_dir),
            "XDG_DATA_HOME": str(ARGOS_DATA_DIR.parent),
            "XDG_CONFIG_HOME": str(ARGOS_CONFIG_DIR.parent),
            "XDG_CACHE_HOME": str(ARGOS_CACHE_DIR.parent),
        }
    )
    return env


def _build_argos_worker_command(status: dict[str, object]) -> tuple[list[str], Path, tuple[str, str, str]]:
    runtime_kind = status.get("runtime_kind")
    runtime_path = status.get("runtime_path")
    worker_script = status.get("worker_script")
    packages_dir = Path(status.get("packages_dir") or ARGOS_PACKAGES_DIR)

    if runtime_kind == "exe" and runtime_path:
        runtime_path = Path(runtime_path)
        args = [str(runtime_path), "--persistent"]
        signature = ("exe", str(runtime_path), str(packages_dir))
        return args, packages_dir, signature

    if runtime_kind == "python" and runtime_path and worker_script:
        runtime_path = Path(runtime_path)
        worker_script = Path(worker_script)
        args = [str(runtime_path), "-u", str(worker_script), "--persistent"]
        signature = ("python", f"{runtime_path}|{worker_script}", str(packages_dir))
        return args, packages_dir, signature

    raise RuntimeError(f"missing-translation-pack::{translation_pack_missing_details(status)}")


def _argos_worker_warmup_text(from_code: str, to_code: str) -> str:
    return ARGOS_WORKER_WARMUP_TEXT_BY_DIRECTION.get((from_code, to_code), "test")


class ArgosTranslationClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._signature: tuple[str, str, str] | None = None
        self._stderr_tail: list[str] = []
        self._idle_timer: threading.Timer | None = None
        self._idle_timer_token: object | None = None

    def translate(
        self,
        text: str,
        status: dict[str, object],
        from_code: str,
        to_code: str,
    ) -> str:
        request = {
            "text": text,
            "from_code": from_code,
            "to_code": to_code,
            "packages_dir": str(Path(status.get("packages_dir") or ARGOS_PACKAGES_DIR)),
        }
        with self._lock:
            self._cancel_idle_stop_locked()
            try:
                translated = self._translate_locked(request, status)
            except Exception:
                raise
            self._schedule_idle_stop_locked()
            return translated

    def warm_up(self, status: dict[str, object], from_code: str, to_code: str) -> None:
        request = {
            "text": _argos_worker_warmup_text(from_code, to_code),
            "from_code": from_code,
            "to_code": to_code,
            "packages_dir": str(Path(status.get("packages_dir") or ARGOS_PACKAGES_DIR)),
        }
        with self._lock:
            self._cancel_idle_stop_locked()
            self._translate_locked(request, status)
            self._schedule_idle_stop_locked()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _translate_locked(self, request: dict[str, str], status: dict[str, object]) -> str:
        started = self._ensure_started_locked(status)
        timeout = (
            ARGOS_WORKER_FIRST_TRANSLATION_TIMEOUT_SECONDS
            if started
            else ARGOS_TRANSLATION_TIMEOUT_SECONDS
        )
        try:
            return self._send_request_locked(request, timeout)
        except Exception:
            self._stop_locked()
            raise

    def _cancel_idle_stop_locked(self) -> None:
        timer = self._idle_timer
        self._idle_timer = None
        self._idle_timer_token = None
        if timer is not None:
            timer.cancel()

    def _schedule_idle_stop_locked(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        if ARGOS_WORKER_IDLE_STOP_SECONDS <= 0:
            self._stop_locked(cancel_idle_timer=False)
            return

        token = object()
        timer = threading.Timer(ARGOS_WORKER_IDLE_STOP_SECONDS, self._stop_after_idle, args=(token,))
        timer.daemon = True
        self._idle_timer = timer
        self._idle_timer_token = token
        timer.start()

    def _stop_after_idle(self, token: object) -> None:
        with self._lock:
            if token is not self._idle_timer_token:
                return
            self._idle_timer = None
            self._idle_timer_token = None
            self._stop_locked(cancel_idle_timer=False)

    def _ensure_started_locked(self, status: dict[str, object]) -> bool:
        args, packages_dir, signature = _build_argos_worker_command(status)
        if self._process is not None and self._signature == signature and self._process.poll() is None:
            return False

        self._stop_locked()
        self._stdout_queue = queue.Queue()
        self._stderr_tail = []
        self._process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=_build_argos_worker_env(packages_dir),
        )
        self._signature = signature
        self._start_reader_threads(self._process)
        return True

    def _start_reader_threads(self, process: subprocess.Popen) -> None:
        stdout_queue = self._stdout_queue

        def stdout_reader() -> None:
            try:
                if process.stdout is None:
                    return
                for line in process.stdout:
                    stdout_queue.put(line)
            finally:
                stdout_queue.put(None)

        def stderr_reader() -> None:
            if process.stderr is None:
                return
            for line in process.stderr:
                line = line.strip()
                if not line:
                    continue
                self._stderr_tail.append(line)
                del self._stderr_tail[:-20]

        threading.Thread(target=stdout_reader, daemon=True).start()
        threading.Thread(target=stderr_reader, daemon=True).start()

    def _send_request_locked(self, request: dict[str, str], timeout: int) -> str:
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("translation-failed::worker-not-started")
        if process.poll() is not None:
            raise RuntimeError(f"translation-failed::worker-exited::{process.returncode}::{self._stderr_text()}")

        line = json.dumps(request, ensure_ascii=False)
        try:
            process.stdin.write(line + "\n")
            process.stdin.flush()
        except Exception as exc:
            raise RuntimeError(f"translation-failed::worker-stdin::{exc}") from exc

        payload = self._read_payload(timeout)
        if not payload.get("ok"):
            raise RuntimeError(f"translation-failed::worker::{payload.get('error', 'unknown error')}")
        return str(payload.get("text", "")).strip()

    def _read_payload(self, timeout: int) -> dict:
        deadline = time.perf_counter() + timeout
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise RuntimeError(f"translation-timeout::{timeout}")
            try:
                line = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise RuntimeError(f"translation-timeout::{timeout}") from exc
            if line is None:
                process = self._process
                returncode = process.returncode if process is not None else "unknown"
                raise RuntimeError(f"translation-failed::worker-exited::{returncode}::{self._stderr_text()}")
            payload = _parse_worker_json_response(line.strip())
            if payload is not None:
                return payload

    def _stderr_text(self) -> str:
        return "\n".join(self._stderr_tail[-10:])

    def _stop_locked(self, cancel_idle_timer: bool = True) -> None:
        if cancel_idle_timer:
            self._cancel_idle_stop_locked()
        process = self._process
        self._process = None
        self._signature = None
        if process is None:
            return

        if process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                    process.stdin.flush()
                process.wait(timeout=ARGOS_WORKER_STOP_TIMEOUT_SECONDS)
            except Exception:
                try:
                    process.terminate()
                    process.wait(timeout=ARGOS_WORKER_STOP_TIMEOUT_SECONDS)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass


_ARGOS_TRANSLATION_CLIENT = ArgosTranslationClient()


def stop_argos_translation_worker() -> None:
    _ARGOS_TRANSLATION_CLIENT.stop()


atexit.register(stop_argos_translation_worker)


def warm_up_argos_translation(
    status: dict[str, object] | None = None,
    from_code: str = "ru",
    to_code: str = "en",
) -> None:
    status = status or detect_translation_pack()
    if not is_translation_direction_available(status, from_code, to_code):
        raise RuntimeError(f"missing-translation-pack::{translation_pack_missing_details(status, from_code, to_code)}")

    _ARGOS_TRANSLATION_CLIENT.warm_up(status, from_code, to_code)


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

    translated = _ARGOS_TRANSLATION_CLIENT.translate(text, status, from_code, to_code)
    return apply_translation_postprocess(translated, from_code, to_code)


def backend_thread_candidates(backend_name: str) -> list[int]:
    cpu_count = max(1, os.cpu_count() or DEFAULT_WHISPER_THREADS)
    profile = "gpu" if backend_name in GPU_BACKEND_KEYS else "cpu"
    configured = BACKEND_BENCHMARK_THREAD_COUNTS[profile]
    candidates = [threads for threads in configured if threads <= cpu_count]
    if not candidates:
        candidates = [1]
    return sorted(set(candidates))


def quick_backend_benchmark_names(preferred_backend_key: str | None = None) -> list[str]:
    available = {
        name
        for name, path in WHISPER_BACKENDS.items()
        if path.exists()
    }
    if not available:
        return []

    priority: list[str] = []
    if preferred_backend_key and preferred_backend_key not in {"auto", FALLBACK_AUTO_BACKEND_KEY}:
        priority.append(preferred_backend_key)

    priority.extend(name for name in GPU_BACKEND_PRIORITY if name in available)
    priority.extend(name for name in CPU_BACKEND_PRIORITY if name in available)
    priority.extend(
        name
        for name in WHISPER_BACKENDS
        if name in available and name != FALLBACK_AUTO_BACKEND_KEY
    )

    result: list[str] = []
    seen: set[str] = set()
    for backend_name in priority:
        if backend_name in seen or backend_name not in available:
            continue
        result.append(backend_name)
        seen.add(backend_name)
        if BENCHMARK_QUICK_BACKEND_LIMIT and len(result) >= BENCHMARK_QUICK_BACKEND_LIMIT:
            break
    return result


def backend_result_error_text(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ""

    parts: list[str] = []
    error = item.get("error")
    if error:
        parts.append(str(error))

    thread_results = item.get("thread_results")
    if isinstance(thread_results, dict):
        for thread_item in thread_results.values():
            if isinstance(thread_item, dict) and thread_item.get("error"):
                parts.append(str(thread_item["error"]))

    return "\n".join(parts)


def backend_result_is_timeout(item: dict | None) -> bool:
    text = backend_result_error_text(item).lower()
    return "timeout" in text or "overall timeout" in text or "лимит времени" in text


def should_auto_select_compat_after_quick_benchmark(results: dict) -> bool:
    for backend_name in CPU_BACKEND_PRIORITY:
        backend_path = WHISPER_BACKENDS.get(backend_name)
        if not backend_path or not backend_path.exists():
            continue

        item = results.get(backend_name)
        if not isinstance(item, dict) or item.get("ok") or item.get("skipped"):
            return False
        if backend_result_is_timeout(item):
            return False

    return True


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
    saved_selected: str | None = None
    if results is None:
        profile = load_backend_profile()
        selected = profile.get("selected_backend")
        if isinstance(selected, str):
            saved_selected = selected
        results = profile.get("results", {})

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
    if saved_selected and is_whisper_backend_available(saved_selected):
        return saved_selected
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
    print_progress: bool = False,
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
            "-nf",
            "-otxt",
            "-of",
            str(out_base),
        ]
    )
    if not print_progress:
        command.append("-np")
    return command


def decode_process_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


class RecognitionCancelled(RuntimeError):
    pass


def _terminate_process(process: subprocess.Popen, timeout_seconds: float = 2.0) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=timeout_seconds)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=timeout_seconds)
        except Exception:
            pass


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
    cancel_event: threading.Event | None = None,
    process_callback: Callable[[subprocess.Popen | None], None] | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if cancel_event is not None and cancel_event.is_set():
        raise RecognitionCancelled()

    threads = sanitize_whisper_threads(threads)
    command = build_whisper_command(
        exe_path,
        model_path,
        wav_path,
        out_base,
        threads=threads,
        language=language,
        translate_to_english=translate_to_english,
        print_progress=progress_callback is not None,
    )
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(APP_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if process_callback is not None:
            process_callback(process)

        deadline = time.perf_counter() + timeout_seconds if timeout_seconds is not None else None
        if progress_callback is None:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    _terminate_process(process)
                    raise RecognitionCancelled()
                if deadline is not None and time.perf_counter() >= deadline:
                    _terminate_process(process)
                    raise RuntimeError(f"{backend_name} t={threads}: timeout after {timeout_seconds} seconds")
                try:
                    wait_timeout = 0.1
                    if deadline is not None:
                        wait_timeout = max(0.01, min(wait_timeout, deadline - time.perf_counter()))
                    stdout_data, stderr_data = process.communicate(timeout=wait_timeout)
                    break
                except subprocess.TimeoutExpired:
                    continue
        else:
            stdout_buffer = bytearray()
            stderr_buffer = bytearray()
            last_progress = -1

            def emit_progress_from_text(text: str) -> None:
                nonlocal last_progress
                for match in WHISPER_PROGRESS_PATTERN.finditer(text):
                    value = max(0, min(100, int(match.group(1))))
                    if value > last_progress:
                        last_progress = value
                        progress_callback(value)

            def stdout_reader() -> None:
                if process is None or process.stdout is None:
                    return
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    stdout_buffer.extend(chunk)

            def stderr_reader() -> None:
                if process is None or process.stderr is None:
                    return
                line_buffer = bytearray()
                while True:
                    chunk = process.stderr.read(1)
                    if not chunk:
                        break
                    stderr_buffer.extend(chunk)
                    if chunk in (b"\r", b"\n"):
                        if line_buffer:
                            emit_progress_from_text(line_buffer.decode("utf-8", errors="replace"))
                            line_buffer.clear()
                    else:
                        line_buffer.extend(chunk)
                if line_buffer:
                    emit_progress_from_text(line_buffer.decode("utf-8", errors="replace"))

            stdout_thread = threading.Thread(target=stdout_reader, daemon=True)
            stderr_thread = threading.Thread(target=stderr_reader, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            while True:
                if cancel_event is not None and cancel_event.is_set():
                    _terminate_process(process)
                    raise RecognitionCancelled()
                if deadline is not None and time.perf_counter() >= deadline:
                    _terminate_process(process)
                    raise RuntimeError(f"{backend_name} t={threads}: timeout after {timeout_seconds} seconds")
                returncode = process.poll()
                if returncode is not None:
                    break
                time.sleep(0.1)

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            stdout_data = bytes(stdout_buffer)
            stderr_data = bytes(stderr_buffer)

        if cancel_event is not None and cancel_event.is_set():
            raise RecognitionCancelled()
        completed = subprocess.CompletedProcess(command, process.returncode, stdout_data, stderr_data)
    except RecognitionCancelled:
        raise
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"{backend_name} t={threads}: {exc}")
    finally:
        if process_callback is not None:
            process_callback(None)

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
    cancel_event: threading.Event | None = None,
    process_callback: Callable[[subprocess.Popen | None], None] | None = None,
    progress_callback: Callable[[int], None] | None = None,
    deadline: float | None = None,
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
        if deadline is not None and time.perf_counter() >= deadline:
            raise RuntimeError("overall timeout")
        if txt_path.exists():
            txt_path.unlink()

        if cancel_event is not None and cancel_event.is_set():
            raise RecognitionCancelled()

        threads = choose_backend_threads(backend_name, backend_profile)
        attempt_timeout = timeout_seconds
        if deadline is not None:
            remaining = max(0.01, deadline - time.perf_counter())
            attempt_timeout = remaining if attempt_timeout is None else min(attempt_timeout, remaining)
        try:
            completed = run_whisper_backend(
                backend_name,
                exe_path,
                model_path,
                wav_path,
                out_base,
                attempt_timeout,
                threads=threads,
                language=language,
                translate_to_english=translate_to_english,
                cancel_event=cancel_event,
                process_callback=process_callback,
                progress_callback=progress_callback,
            )
            return backend_name, threads, completed
        except RecognitionCancelled:
            raise
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
                settings["audio_source"] = sanitize_audio_source_key(
                    stored.get("audio_source", DEFAULT_USER_SETTINGS["audio_source"])
                )
                settings["system_output_device_id"] = sanitize_system_output_device_id(
                    stored.get("system_output_device_id", DEFAULT_USER_SETTINGS["system_output_device_id"])
                )
                settings["audio_gain_percent"] = clamp_audio_gain_percent(
                    stored.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"])
                )
                backend = stored.get("backend", DEFAULT_USER_SETTINGS["backend"])
                if backend in BACKEND_LABELS:
                    settings["backend"] = backend
                settings["recognition_mode"] = sanitize_recognition_mode_key(
                    stored.get("recognition_mode", DEFAULT_USER_SETTINGS["recognition_mode"])
                )
                settings["model_key"] = sanitize_model_key(
                    stored.get("model_key", DEFAULT_USER_SETTINGS["model_key"])
                )
    except Exception:
        return dict(DEFAULT_USER_SETTINGS)
    return settings


def save_user_settings(settings: dict) -> None:
    payload = {
        "auto_copy": bool(settings.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"])),
        "format_text": bool(settings.get("format_text", DEFAULT_USER_SETTINGS["format_text"])),
        "voice_punctuation": bool(settings.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])),
        "audio_source": sanitize_audio_source_key(settings.get("audio_source", DEFAULT_USER_SETTINGS["audio_source"])),
        "system_output_device_id": sanitize_system_output_device_id(
            settings.get("system_output_device_id", DEFAULT_USER_SETTINGS["system_output_device_id"])
        ),
        "recognition_mode": sanitize_recognition_mode_key(
            settings.get("recognition_mode", DEFAULT_USER_SETTINGS["recognition_mode"])
        ),
        "audio_gain_percent": clamp_audio_gain_percent(
            settings.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"])
        ),
        "backend": str(settings.get("backend", DEFAULT_USER_SETTINGS["backend"])),
        "model_key": sanitize_model_key(settings.get("model_key", DEFAULT_USER_SETTINGS["model_key"])),
    }
    if payload["backend"] not in BACKEND_LABELS:
        payload["backend"] = DEFAULT_USER_SETTINGS["backend"]
    USER_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_voice_punctuation_commands(text: str) -> str:
    replacements = [
        (r"(?iu)(?<!\w)новый\s+абзац[.,!?;:]*(?!\w)", "\n\n"),
        (r"(?iu)(?<!\w)новая\s+строка[.,!?;:]*(?!\w)", "\n"),
        (
            r"(?iu)(?<!\w)(?:точка[.,!?;:]*\s+(?:с\s+)?(?:запятой|запитой|запетой|запятая|запитая|запетая)|точку[.,!?;:]*\s+(?:с\s+)?(?:запятой|запитой|запетой))[.,!?;:]*(?!\w)",
            ";",
        ),
        (
            r"(?iu)(?<!\w)(?:двоеточие|двоеточия|двоиточие|двоиточия|дваиточие|дво[её]\s+точие|двои\s+точие|двой\s+точие|твои\s+точ[яие]|твой\s+точ[яие]|две\s+точки|два\s+точки)[.,!?;:]*(?!\w)",
            ":",
        ),
        (r"(?iu)(?<!\w)(?:многоточие|многоточия)[.,!?;:]*(?!\w)", "..."),
        (r"(?iu)(?<!\w)(?:вопросительный\s+знак|знак\s+вопроса)[.,!?;:]*(?!\w)", "?"),
        (r"(?iu)(?<!\w)(?:восклицательный\s+знак|знак\s+восклицания)[.,!?;:]*(?!\w)", "!"),
        (
            r"(?iu)(?<!\w)(?:кавычки\s+открываются|открывающиеся\s+кавычки|открывающая\s+кавычка|открыть\s+кавычки|открыть\s+кавычку)[.,!?;:]*(?!\w)",
            '"',
        ),
        (
            r"(?iu)(?<!\w)(?:кавычки\s+закрываются|закрывающиеся\s+кавычки|закрывающая\s+кавычка|закрыть\s+кавычки|закрыть\s+кавычку)[.,!?;:]*(?!\w)",
            '"',
        ),
        (r"(?iu)(?<!\w)(?:кавычки|кавычка)[.,!?;:]*(?!\w)", '"'),
        (
            r"(?iu)(?<!\w)(?:скобка\s+открывается|скобки\s+открываются|открывающая\s+скобка|открыть\s+скобку)[.,!?;:]*(?!\w)",
            "(",
        ),
        (
            r"(?iu)(?<!\w)(?:скобка\s+закрывается|скобки\s+закрываются|закрывающая\s+скобка|закрыть\s+скобку)[.,!?;:]*(?!\w)",
            ")",
        ),
        (r"(?iu)(?<!\w)тире[.,!?;:]*(?!\w)", " - "),
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
    result = re.sub(r"\.(?:\s*\.){2,}", "...", result)
    result = re.sub(r"([,;:!?])(?:\s*\1)+", r"\1", result)
    result = re.sub(r",\s*([.!?])", r"\1", result)
    result = re.sub(r"([.!?])\s*,", r"\1", result)
    result = re.sub(r"([,.;:!?])(?=[^\s\n,.;:!?])", r"\1 ", result)
    result = re.sub(r'"\s*([^"\n]*?)\s*"', lambda match: f'"{match.group(1).strip()}"', result)
    result = re.sub(r'([0-9A-Za-zА-Яа-яЁё])\s*[,;]\s*(")(?=\s*(?:$|[.!?…]))', r'\1\2', result)
    result = re.sub(r'(^|[\s(\[{])"\s+', r'\1"', result)
    result = re.sub(r'\s+"(?=$|[\s,.;:!?()\]}])', '"', result)
    result = re.sub(r"\(\s+", "(", result)
    result = re.sub(r"\s+\)", ")", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result.strip()


def capitalize_text(text: str) -> str:
    return re.sub(
        r'(?iu)(^|[.!?]\s+|\n+)(["«„“]?)([a-zа-яё])',
        lambda match: match.group(1) + match.group(2) + match.group(3).upper(),
        text,
    )


def _is_standalone_quoted_text(text: str) -> bool:
    return bool(re.fullmatch(r'"[^"\n]+"', text.strip()))


def ensure_final_period(text: str) -> str:
    result = text.rstrip()
    if not result:
        return result
    if result[-1] in ".!?…":
        return result
    if _is_standalone_quoted_text(result):
        return result
    if result[-1] == '"':
        inner = result[:-1].rstrip()
        if inner and inner[-1] in ".!?…":
            return result
        if inner and inner[-1] in ",;:":
            result = inner[:-1].rstrip() + '"'
        return result + "."
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


@dataclass(frozen=True)
class RecognitionCorrection:
    start: int
    end: int
    source: str
    replacement: str


@dataclass(frozen=True)
class RecognitionPostprocessResult:
    text: str
    corrections: tuple[RecognitionCorrection, ...]


@dataclass(frozen=True)
class RuRecognitionDictionary:
    replacements: dict[str, str]
    protected_words: frozenset[str]
    known_words: frozenset[str]
    blocked_pairs: dict[str, frozenset[str]]
    phrase_replacements: dict[str, str]


def _load_dictionary_words(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(str(item).strip().casefold() for item in value if str(item).strip())


def _load_dictionary_replacements(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    replacements: dict[str, str] = {}
    for source, replacement in value.items():
        source_text = str(source).strip()
        replacement_text = str(replacement).strip()
        if source_text and replacement_text:
            replacements[source_text.casefold()] = replacement_text
    return replacements


def _load_dictionary_blocked_pairs(value: object) -> dict[str, frozenset[str]]:
    if not isinstance(value, dict):
        return {}
    blocked_pairs: dict[str, frozenset[str]] = {}
    for source, replacements in value.items():
        source_text = str(source).strip()
        if not source_text:
            continue
        if isinstance(replacements, list):
            blocked = frozenset(str(item).strip().casefold() for item in replacements if str(item).strip())
        else:
            blocked = frozenset({str(replacements).strip().casefold()}) if str(replacements).strip() else frozenset()
        if blocked:
            blocked_pairs[source_text.casefold()] = blocked
    return blocked_pairs


def _load_dictionary_phrase_replacements(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    phrase_replacements: dict[str, str] = {}
    for source, replacement in value.items():
        source_text = str(source).strip()
        replacement_text = str(replacement).strip()
        if source_text and replacement_text:
            phrase_replacements[source_text] = replacement_text
    return phrase_replacements


def load_ru_recognition_dictionary_payload() -> dict[str, object]:
    try:
        data = json.loads(RU_RECOGNITION_DICTIONARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    return {
        "version": 2,
        "replacements": data.get("replacements") if isinstance(data.get("replacements"), dict) else {},
        "protected_words": data.get("protected_words") if isinstance(data.get("protected_words"), list) else [],
        "known_words": data.get("known_words") if isinstance(data.get("known_words"), list) else [],
        "blocked_pairs": data.get("blocked_pairs") if isinstance(data.get("blocked_pairs"), dict) else {},
        "phrase_replacements": data.get("phrase_replacements")
        if isinstance(data.get("phrase_replacements"), dict)
        else {},
    }


def save_ru_recognition_dictionary_payload(payload: dict[str, object]) -> None:
    RU_RECOGNITION_DICTIONARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RU_RECOGNITION_DICTIONARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_ru_recognition_dictionary() -> RuRecognitionDictionary:
    data = load_ru_recognition_dictionary_payload()
    return RuRecognitionDictionary(
        replacements=_load_dictionary_replacements(data.get("replacements")),
        protected_words=_load_dictionary_words(data.get("protected_words")),
        known_words=_load_dictionary_words(data.get("known_words")),
        blocked_pairs=_load_dictionary_blocked_pairs(data.get("blocked_pairs")),
        phrase_replacements=_load_dictionary_phrase_replacements(data.get("phrase_replacements")),
    )


def remove_casefolded_list_item(items: list[object], value: str) -> bool:
    value_key = value.casefold()
    kept = [item for item in items if str(item).strip().casefold() != value_key]
    if len(kept) == len(items):
        return False
    items[:] = kept
    return True


def remove_casefolded_mapping_key(mapping: dict[str, object], key: str) -> bool:
    key_folded = key.casefold()
    existing_key = next((item for item in mapping if str(item).casefold() == key_folded), None)
    if existing_key is None:
        return False
    mapping.pop(existing_key, None)
    return True


def add_ru_dictionary_known_word(word: str) -> bool:
    clean_word = word.strip()
    if not clean_word or re.search(r"\s", clean_word):
        return False

    payload = load_ru_recognition_dictionary_payload()
    known_words = payload["known_words"]
    if not isinstance(known_words, list):
        known_words = []
        payload["known_words"] = known_words

    if any(str(item).strip().casefold() == clean_word.casefold() for item in known_words):
        return False
    known_words.append(clean_word)
    save_ru_recognition_dictionary_payload(payload)
    return True


def add_ru_dictionary_known_words(words: list[str]) -> int:
    added = 0
    for word in words:
        if add_ru_dictionary_known_word(word):
            added += 1
    return added


def add_ru_dictionary_replacement(source: str, replacement: str) -> bool:
    source_text = source.strip()
    replacement_text = replacement.strip()
    if not source_text or not replacement_text or source_text.casefold() == replacement_text.casefold():
        return False

    payload = load_ru_recognition_dictionary_payload()
    replacements = payload["replacements"]
    if not isinstance(replacements, dict):
        replacements = {}
        payload["replacements"] = replacements
    replacements[source_text] = replacement_text

    for list_key in ("known_words", "protected_words"):
        values = payload[list_key]
        if isinstance(values, list):
            remove_casefolded_list_item(values, source_text)

    blocked_pairs = payload["blocked_pairs"]
    if isinstance(blocked_pairs, dict):
        blocked = blocked_pairs.get(source_text)
        if isinstance(blocked, list):
            remove_casefolded_list_item(blocked, replacement_text)
            if not blocked:
                blocked_pairs.pop(source_text, None)

    save_ru_recognition_dictionary_payload(payload)
    return True


def remember_rejected_ru_corrections(corrections: tuple[RecognitionCorrection, ...]) -> bool:
    if not corrections:
        return False

    payload = load_ru_recognition_dictionary_payload()
    replacements = payload["replacements"]
    blocked_pairs = payload["blocked_pairs"]
    phrase_replacements = payload["phrase_replacements"]
    if not isinstance(replacements, dict) or not isinstance(blocked_pairs, dict) or not isinstance(phrase_replacements, dict):
        return False

    changed = False
    for correction in corrections:
        source = correction.source.strip()
        replacement = correction.replacement.strip()
        if not source or not replacement:
            continue

        direct_key = next((key for key, value in replacements.items() if str(key).casefold() == source.casefold() and str(value).casefold() == replacement.casefold()), None)
        if direct_key is not None:
            replacements.pop(direct_key, None)
            changed = True

        phrase_key = next((key for key, value in phrase_replacements.items() if str(key).casefold() == source.casefold() and str(value).casefold() == replacement.casefold()), None)
        if phrase_key is not None:
            phrase_replacements.pop(phrase_key, None)
            changed = True

        if re.fullmatch(r"[А-Яа-яЁё]+", source) and re.fullmatch(r"[А-Яа-яЁё]+", replacement):
            existing_key = next((key for key in blocked_pairs if str(key).casefold() == source.casefold()), source)
            blocked = blocked_pairs.get(existing_key)
            if not isinstance(blocked, list):
                blocked = []
                blocked_pairs[existing_key] = blocked
            if not any(str(item).casefold() == replacement.casefold() for item in blocked):
                blocked.append(replacement)
                changed = True

    if changed:
        save_ru_recognition_dictionary_payload(payload)
    return changed


def russian_letter_count(value: str) -> int:
    return sum(1 for char in value if "а" <= char.lower() <= "я" or char.lower() == "ё")


def is_russian_word(value: str) -> bool:
    return bool(re.fullmatch(r"[А-Яа-яЁё]+", value))


def is_uppercase_abbreviation(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    return len(letters) >= 2 and all(char.upper() == char for char in letters)


def is_protected_spellcheck_word(value: str) -> bool:
    if not value or len(value) < RU_POSTPROCESS_MIN_WORD_LENGTH:
        return True
    if any(char.isdigit() for char in value):
        return True
    if re.search(r"[A-Za-z@_:/\\]", value):
        return True
    if "-" in value:
        return True
    if russian_letter_count(value) < RU_POSTPROCESS_MIN_WORD_LENGTH:
        return True
    if is_uppercase_abbreviation(value):
        return True
    return not is_russian_word(value)


def is_protected_spellcheck_context(text: str, start: int, end: int) -> bool:
    left = start
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    right = end
    while right < len(text) and not text[right].isspace():
        right += 1
    token = text[left:right]
    token_lower = token.lower()
    return bool(
        "@"
        in token
        or "://"
        in token
        or token_lower.startswith("www.")
        or "/" in token
        or "\\" in token
    )


def edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def match_word_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source.islower():
        return replacement.lower()
    if source[:1].isupper() and source[1:].islower():
        return replacement[:1].upper() + replacement[1:].lower()
    return replacement


def match_phrase_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def dictionary_phrase_pattern(source: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in source.split())
    return re.compile(rf"(?iu)(?<!\w){body}(?!\w)")


def apply_ru_dictionary_phrase_replacements(
    text: str,
    dictionary: RuRecognitionDictionary,
) -> RecognitionPostprocessResult:
    if not dictionary.phrase_replacements:
        return RecognitionPostprocessResult(text, ())

    result = text
    corrections: list[RecognitionCorrection] = []
    replacements = sorted(dictionary.phrase_replacements.items(), key=lambda item: len(item[0]), reverse=True)
    for source, replacement in replacements:
        matches = list(dictionary_phrase_pattern(source).finditer(result))
        if not matches:
            continue
        for match in reversed(matches):
            replace_start = match.start()
            replace_end = match.end()
            replacement_text = match_phrase_case(match.group(0), replacement)
            if replacement_text.startswith((".", ",", ";", ":", "!", "?")) and replace_start > 0 and result[replace_start - 1].isspace():
                replace_start -= 1
            source_text = result[replace_start:replace_end]
            if source_text.casefold() == replacement_text.casefold():
                continue
            result = result[:replace_start] + replacement_text + result[replace_end:]
            corrections.append(
                RecognitionCorrection(
                    start=replace_start,
                    end=replace_end,
                    source=source_text,
                    replacement=replacement_text,
                )
            )

    if not corrections:
        return RecognitionPostprocessResult(text, ())
    corrections.sort(key=lambda item: item.start)
    return RecognitionPostprocessResult(result, tuple(corrections))


def choose_conservative_suggestion(
    issue: SpellingIssue,
    text: str,
    dictionary: RuRecognitionDictionary,
) -> str | None:
    source = issue.word
    start = issue.start
    end = issue.start + issue.length
    source_key = source.casefold()
    if source_key in dictionary.known_words:
        return None
    if source_key in dictionary.protected_words:
        return None
    if is_protected_spellcheck_word(source) or is_protected_spellcheck_context(text, start, end):
        return None

    dictionary_replacement = dictionary.replacements.get(source_key)
    if dictionary_replacement:
        candidate = dictionary_replacement.strip()
        if not is_protected_spellcheck_word(candidate) and source.casefold() != candidate.casefold():
            return match_word_case(source, candidate)

    if not issue.suggestions:
        return None
    if len(issue.suggestions) != 1:
        return None

    candidate = str(issue.suggestions[0]).strip()
    if is_protected_spellcheck_word(candidate):
        return None
    if source.casefold() == candidate.casefold():
        return None
    if candidate.casefold() in dictionary.blocked_pairs.get(source_key, frozenset()):
        return None

    distance = edit_distance(source.casefold(), candidate.casefold())
    if distance <= 0 or distance > RU_POSTPROCESS_MAX_EDIT_DISTANCE:
        return None
    if distance == RU_POSTPROCESS_MAX_EDIT_DISTANCE and russian_letter_count(source) < 8:
        return None
    if source[:1].casefold() != candidate[:1].casefold():
        return None

    return match_word_case(source, candidate)


def apply_ru_recognition_postprocess(text: str) -> RecognitionPostprocessResult:
    if not text.strip():
        return RecognitionPostprocessResult(text, ())

    dictionary = load_ru_recognition_dictionary()
    phrase_result = apply_ru_dictionary_phrase_replacements(text, dictionary)
    working_text = phrase_result.text
    issues = check_text(working_text, language_tag="ru-RU")
    word_corrections: list[RecognitionCorrection] = []
    for issue in issues:
        replacement = choose_conservative_suggestion(issue, working_text, dictionary)
        if not replacement:
            continue
        word_corrections.append(
            RecognitionCorrection(
                start=issue.start,
                end=issue.start + issue.length,
                source=issue.word,
                replacement=replacement,
            )
        )

    if not phrase_result.corrections and not word_corrections:
        return RecognitionPostprocessResult(text, ())

    result = working_text
    for correction in sorted(word_corrections, key=lambda item: item.start, reverse=True):
        result = result[: correction.start] + correction.replacement + result[correction.end :]
    return RecognitionPostprocessResult(result, phrase_result.corrections + tuple(word_corrections))


def log_ru_recognition_corrections(corrections: tuple[RecognitionCorrection, ...]) -> None:
    if not corrections:
        return
    try:
        RU_POSTPROCESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
        visible = corrections[:RU_POSTPROCESS_LOG_LIMIT]
        pairs = "; ".join(f"{item.source} -> {item.replacement}" for item in visible)
        suffix = f"; ... +{len(corrections) - len(visible)}" if len(corrections) > len(visible) else ""
        with RU_POSTPROCESS_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{timestamp}\t{pairs}{suffix}\n")
    except Exception:
        pass


def ru_recognition_corrections_status(corrections: tuple[RecognitionCorrection, ...]) -> str:
    return f"Исправлено: {len(corrections)}"


def run_ru_dictionary_self_test() -> None:
    original_text = ""
    if RU_RECOGNITION_DICTIONARY_PATH.exists():
        original_text = RU_RECOGNITION_DICTIONARY_PATH.read_text(encoding="utf-8")

    try:
        if not add_ru_dictionary_replacement("тестошибка", "тест"):
            raise AssertionError("dictionary replacement was not added")
        payload = load_ru_recognition_dictionary_payload()
        replacements = payload.get("replacements", {})
        if not isinstance(replacements, dict) or replacements.get("тестошибка") != "тест":
            raise AssertionError("dictionary replacement was not saved")

        if not add_ru_dictionary_known_word("Тесттермин"):
            raise AssertionError("known word was not added")
        payload = load_ru_recognition_dictionary_payload()
        known_words = payload.get("known_words", [])
        if not isinstance(known_words, list) or not any(str(item) == "Тесттермин" for item in known_words):
            raise AssertionError("known word was not saved")

        rejected = (
            RecognitionCorrection(
                start=0,
                end=10,
                source="тестошибка",
                replacement="тест",
            ),
        )
        if not remember_rejected_ru_corrections(rejected):
            raise AssertionError("rejected correction was not remembered")
        payload = load_ru_recognition_dictionary_payload()
        replacements = payload.get("replacements", {})
        blocked_pairs = payload.get("blocked_pairs", {})
        if isinstance(replacements, dict) and "тестошибка" in replacements:
            raise AssertionError("rejected replacement was not removed")
        if not isinstance(blocked_pairs, dict) or "тестошибка" not in blocked_pairs:
            raise AssertionError("blocked pair was not saved")
    finally:
        if original_text:
            RU_RECOGNITION_DICTIONARY_PATH.write_text(original_text, encoding="utf-8")
        elif RU_RECOGNITION_DICTIONARY_PATH.exists():
            try:
                RU_RECOGNITION_DICTIONARY_PATH.unlink()
            except OSError:
                pass


def run_text_cleanup_self_test() -> None:
    cases = [
        (
            "привет точка новый абзац как дела запятая нормально",
            "Привет.\n\nКак дела, нормально.",
        ),
        (
            "список двоеточие первое точка с запятой второе точка",
            "Список: первое; второе.",
        ),
        (
            "применение твои точя носить на сумке точка запятой дарить точка",
            "Применение: носить на сумке; дарить.",
        ),
        (
            "оберег точка, запятой применение двоиточие носить точка",
            "Оберег; применение: носить.",
        ),
        (
            "я думаю многоточие возможно вопросительный знак точно восклицательный знак",
            "Я думаю... Возможно? Точно!",
        ),
        (
            "первая строка новая строка вторая строка тире продолжение",
            "Первая строка\nВторая строка - продолжение.",
        ),
        (
            "он сказал кавычки открываются привет кавычки закрываются точка",
            'Он сказал "привет".',
        ),
        (
            "кавычки привет кавычки",
            '"Привет"',
        ),
        (
            "кавычки привет, кавычки",
            '"Привет"',
        ),
        (
            "он сказал кавычки привет, кавычки",
            'Он сказал "привет".',
        ),
        (
            "термин кавычки договор кавычки скобка открывается важно скобка закрывается точка",
            'Термин "договор" (важно).',
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


def available_model_keys() -> list[str]:
    return [model_key for model_key in MODEL_LABELS if MODEL_FILES[model_key].exists()]


def available_model_options() -> dict[str, Path]:
    keys = available_model_keys()
    if not keys:
        keys = list(REQUIRED_MODEL_KEYS)
    return {MODEL_LABELS[key]: MODEL_FILES[key] for key in keys}


def required_model_paths() -> list[Path]:
    return [MODEL_FILES[key] for key in REQUIRED_MODEL_KEYS]


def sanitize_model_key(model_key: object | None, require_available: bool = False) -> str:
    key = str(model_key or FALLBACK_AUTO_MODEL_KEY)
    if key not in MODEL_FILES:
        return FALLBACK_AUTO_MODEL_KEY
    if require_available and not MODEL_FILES[key].exists():
        return choose_best_quality_model_key()
    return key


def choose_best_quality_model_key(results: dict | None = None) -> str:
    for model_key in QUALITY_MODEL_PREFERENCE:
        if model_key not in MODEL_FILES:
            continue
        if results is not None:
            item = results.get(model_key, {})
            if isinstance(item, dict) and item.get("ok"):
                return model_key
            continue
        if MODEL_FILES[model_key].exists():
            return model_key
    return FALLBACK_AUTO_MODEL_KEY


def choose_auto_model_key(results: dict | None = None) -> str:
    if results:
        return choose_best_quality_model_key(results)
    return FALLBACK_AUTO_MODEL_KEY


def choose_backend_benchmark_model_key() -> str:
    for model_key in BACKEND_BENCHMARK_MODEL_PREFERENCE:
        model_path = MODEL_FILES.get(model_key)
        if model_path and model_path.exists():
            return model_key
    for model_key, model_path in MODEL_FILES.items():
        if model_path.exists():
            return model_key
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


def run_model_benchmark(
    allow_missing_models: bool = False,
    print_fn=None,
    preferred_backend_key: str | None = None,
    cancel_event: threading.Event | None = None,
    total_timeout_seconds: float = BENCHMARK_TOTAL_TIMEOUT_SECONDS,
    attempt_timeout_seconds: float = BENCHMARK_ATTEMPT_TIMEOUT_SECONDS,
) -> dict:
    results: dict[str, dict] = {}
    deadline = time.perf_counter() + max(1.0, float(total_timeout_seconds))

    with tempfile.TemporaryDirectory(prefix="dicta_benchmark_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        wav_path = tmp_path / "benchmark.wav"
        write_benchmark_wav(wav_path)

        for model_key, model_path in MODEL_FILES.items():
            if cancel_event is not None and cancel_event.is_set():
                raise RecognitionCancelled()
            if time.perf_counter() >= deadline:
                if print_fn:
                    print_fn("общий лимит времени исчерпан")
                break
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
                remaining = max(0.01, deadline - time.perf_counter())
                backend_name, backend_threads, _completed = run_whisper_with_fallback(
                    model_path,
                    wav_path,
                    out_base,
                    timeout_seconds=min(attempt_timeout_seconds, remaining),
                    preferred_backend_key=preferred_backend_key,
                    cancel_event=cancel_event,
                    deadline=deadline,
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
    preferred_backend_key: str | None = None,
    cancel_event: threading.Event | None = None,
    quick: bool = True,
    total_timeout_seconds: float = BENCHMARK_TOTAL_TIMEOUT_SECONDS,
    attempt_timeout_seconds: float = BENCHMARK_ATTEMPT_TIMEOUT_SECONDS,
) -> dict:
    model_key = model_key or choose_backend_benchmark_model_key()
    model_path = MODEL_FILES.get(model_key, MODEL_FILES[FALLBACK_AUTO_MODEL_KEY])
    results: dict[str, dict] = {}
    deadline = time.perf_counter() + max(1.0, float(total_timeout_seconds))

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
            if quick:
                backend_names = quick_backend_benchmark_names(preferred_backend_key)
            else:
                backend_names = list(WHISPER_BACKENDS.keys())
            for backend_name in WHISPER_BACKENDS:
                if backend_name not in backend_names:
                    path = WHISPER_BACKENDS[backend_name]
                    results[backend_name] = {
                        "ok": False,
                        "available": path.exists(),
                        "skipped": True,
                        "error": "skipped by quick backend selection" if quick else "not selected",
                    }

            for backend_name in backend_names:
                if cancel_event is not None and cancel_event.is_set():
                    raise RecognitionCancelled()
                if time.perf_counter() >= deadline:
                    if print_fn:
                        print_fn("общий лимит времени исчерпан")
                    break
                exe_path = WHISPER_BACKENDS[backend_name]
                if not exe_path.exists():
                    results[backend_name] = {
                        "ok": False,
                        "available": False,
                        "error": f"missing backend: {exe_path}",
                    }
                    if print_fn:
                        print_fn(f"{backend_name}: missing backend")
                    continue
                if backend_name in DISABLED_WHISPER_BACKENDS:
                    results[backend_name] = {
                        "ok": False,
                        "available": True,
                        "error": "backend disabled for this session",
                    }
                    if print_fn:
                        print_fn(f"{backend_name}: пропущен после ошибки запуска")
                    continue

                thread_results: dict[str, dict] = {}
                if quick:
                    thread_candidates = [choose_backend_threads(backend_name)]
                else:
                    thread_candidates = backend_thread_candidates(backend_name)
                for threads in thread_candidates:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RecognitionCancelled()
                    if time.perf_counter() >= deadline:
                        if print_fn:
                            print_fn("общий лимит времени исчерпан")
                        break
                    out_base = tmp_path / f"backend_{backend_name}_t{threads}"
                    txt_path = out_base.with_suffix(".txt")
                    if txt_path.exists():
                        txt_path.unlink()

                    if print_fn:
                        print_fn(f"{backend_name} t={threads}: проверка...")
                    started_at = time.perf_counter()
                    try:
                        remaining = max(0.01, deadline - time.perf_counter())
                        run_whisper_backend(
                            backend_name,
                            exe_path,
                            model_path,
                            wav_path,
                            out_base,
                            timeout_seconds=min(attempt_timeout_seconds, remaining),
                            threads=threads,
                            cancel_event=cancel_event,
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

    has_success = any(results.get(backend_name, {}).get("ok") for backend_name in WHISPER_BACKENDS)
    compat_available = is_whisper_backend_available(FALLBACK_AUTO_BACKEND_KEY)
    compat_auto_selected = bool(
        quick
        and not has_success
        and compat_available
        and should_auto_select_compat_after_quick_benchmark(results)
    )
    if has_success:
        selected_backend = choose_auto_backend_key(results)
        selected_threads = choose_backend_threads_from_results(selected_backend, results)
    elif compat_auto_selected:
        selected_backend = FALLBACK_AUTO_BACKEND_KEY
        selected_threads = DEFAULT_WHISPER_THREADS
    else:
        selected_backend = choose_auto_backend_key(results)
        selected_threads = choose_backend_threads_from_results(selected_backend, results)
    profile = {
        "version": 2,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "audio_seconds": BENCHMARK_AUDIO_SECONDS,
        "model": model_key,
        "selected_backend": selected_backend,
        "selected_threads": selected_threads,
        "quick": bool(quick),
        "compat_auto_selected": compat_auto_selected,
        "compat_suggested": bool(quick and not has_success and compat_available and not compat_auto_selected),
        "results": results,
    }
    if has_success or compat_auto_selected:
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
        self.system_audio_chunks: list[bytes] = []
        self.microphone_audio_chunks: list[bytes] = []
        self.system_audio_sample_rate = SAMPLE_RATE
        self.microphone_audio_sample_rate = SAMPLE_RATE
        self.stream = None
        self.worker: threading.Thread | None = None
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_recording = False
        self.is_recognizing = False
        self.is_testing_microphone = False
        self.is_finding_microphone = False
        self.is_testing_system_audio = False
        self.is_benchmarking = False
        self.is_translating = False
        self.is_protocol_recognizing = False
        self.record_started_at: float | None = None
        self.record_sample_rate = SAMPLE_RATE
        self.recognition_progress_started_at = 0.0
        self.recognition_progress_estimate_seconds = 90.0
        self.recognition_progress_has_real_update = False
        self.last_input_stream_config: dict | None = None
        self.mic_test_stream: sd.RawInputStream | None = None
        self.mic_test_peak = 0
        self.last_level_event_at = 0.0
        self.system_recording_peak = 0
        self.microphone_recording_peak = 0
        self.recording_lock = threading.Lock()
        self.system_recording_wav = None
        self.microphone_recording_wav = None
        self.recording_temp_paths: list[Path] = []
        self.protocol_prepare_queue: queue.Queue | None = None
        self.protocol_recognition_queue: queue.Queue | None = None
        self.protocol_prepare_thread: threading.Thread | None = None
        self.protocol_recognition_thread: threading.Thread | None = None
        self.protocol_system_chunk_parts: list[bytes] = []
        self.protocol_microphone_chunk_parts: list[bytes] = []
        self.protocol_system_chunk_bytes = 0
        self.protocol_microphone_chunk_bytes = 0
        self.protocol_chunk_index = 0
        self.protocol_chunks_queued = 0
        self.protocol_chunks_recognized = 0
        self.protocol_text_started = False
        self.input_devices: dict[str, list[int]] = {}
        self.preferred_input_configs: dict[str, dict] = {}
        self.system_output_devices: dict[str, str] = {
            DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL: DEFAULT_SYSTEM_OUTPUT_DEVICE_ID
        }
        self.system_output_device_info_by_id: dict[str, WasapiOutputDeviceInfo] = {}
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
        self.translation_warmup_worker: threading.Thread | None = None
        self.recognition_cancel_event = threading.Event()
        self.benchmark_cancel_event = threading.Event()
        self.recognition_process_lock = threading.Lock()
        self.recognition_process: subprocess.Popen | None = None
        self.last_recording_source_key = DEFAULT_AUDIO_SOURCE_KEY
        self.format_undo_snapshot: tuple[str, str] | None = None
        self.postprocess_undo_snapshot: tuple[str, str, tuple[RecognitionCorrection, ...]] | None = None
        self.translation_undo_snapshot: tuple[str, str, str, str] | None = None
        self.settings_snapshot: dict[str, object] = {}

        self.status_var = tk.StringVar(value="Готово")
        self.record_time_var = tk.StringVar(value="Запись: 00:00")
        self.recognition_time_var = tk.StringVar(value="-")
        self.recognition_progress_var = tk.DoubleVar(value=0)
        self.recognition_progress_text_var = tk.StringVar(value="0%")
        self.firewall_status_var = tk.StringVar(value="Сеть: проверка...")
        initial_model_key = sanitize_model_key(
            self.settings.get("model_key", FALLBACK_AUTO_MODEL_KEY),
            require_available=True,
        )
        self.speed_status_var = tk.StringVar(value=f"Модель: {initial_model_key}")
        self.model_var = tk.StringVar(value=MODEL_LABELS.get(initial_model_key, DEFAULT_MODEL_LABEL))
        self.backend_var = tk.StringVar(
            value=BACKEND_LABELS.get(str(self.settings.get("backend", "auto")), DEFAULT_BACKEND_LABEL)
        )
        self.input_device_var = tk.StringVar(value="")
        initial_audio_source = sanitize_audio_source_key(
            self.settings.get("audio_source", DEFAULT_AUDIO_SOURCE_KEY)
        )
        self.audio_source_var = tk.StringVar(value=AUDIO_SOURCE_LABELS[initial_audio_source])
        self.system_output_device_var = tk.StringVar(value=DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL)
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
        self._update_speed_status()
        self.refresh_system_output_devices(show_status=False)
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
        toolbar.columnconfigure(5, weight=1)

        self.record_button = ttk.Button(toolbar, text="Записать", command=self.toggle_recording)
        self.record_button.grid(row=0, column=0, padx=(0, 8))

        self.stop_button = ttk.Button(toolbar, text="Стоп", command=self.stop_recording, state=tk.DISABLED)

        self.copy_button = ttk.Button(toolbar, text="Скопировать", command=self.copy_text)
        self.copy_button.grid(row=0, column=1, padx=(0, 8))

        self.more_menu = tk.Menu(toolbar, tearoff=False)
        self.translate_menu = self.more_menu
        self.translate_to_ru_menu_index = 0
        self.translate_to_en_menu_index = 1
        self.undo_translation_menu_index = 2
        self.format_menu_index = 4
        self.undo_postprocess_menu_index = 5
        self.more_menu.add_command(label="Перевести в русский", command=self.translate_current_text_to_russian)
        self.more_menu.add_command(label="Перевести в English", command=self.translate_last_recording_to_english)
        self.more_menu.add_command(label="Вернуть перевод", command=self.undo_last_translation, state=tk.DISABLED)
        self.more_menu.add_separator()
        self.more_menu.add_command(label="Автоформат", command=self.format_current_text)
        self.more_menu.add_command(label="Откатить автоисправления", command=self.undo_last_postprocess, state=tk.DISABLED)
        self.more_menu.add_separator()
        self.more_menu.add_command(label="Очистить", command=self.clear_text)
        self.more_button = ttk.Menubutton(toolbar, text="Еще", menu=self.more_menu)

        self.toolbar_recognition_mode_box = ttk.Combobox(
            toolbar,
            textvariable=self.recognition_mode_var,
            values=self._recognition_mode_labels(),
            state="readonly",
            width=16,
        )
        self.toolbar_recognition_mode_box.grid(row=0, column=2, padx=(0, 8))
        self.toolbar_recognition_mode_box.bind("<<ComboboxSelected>>", self._on_toolbar_recognition_mode_changed)

        self.toolbar_audio_source_box = ttk.Combobox(
            toolbar,
            textvariable=self.audio_source_var,
            values=list(AUDIO_SOURCE_LABELS.values()),
            state="readonly",
            width=27,
        )
        self.toolbar_audio_source_box.grid(row=0, column=3, padx=(0, 8))
        self.toolbar_audio_source_box.bind("<<ComboboxSelected>>", self._on_audio_source_changed)

        self.more_button.grid(row=0, column=4, padx=(0, 8))

        self.settings_button = ttk.Button(toolbar, text="Настройки", command=self.show_settings)
        self.settings_button.grid(row=0, column=6, sticky="e")

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
        status_bar.columnconfigure(9, weight=1)

        ttk.Label(status_bar, text="Статус:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Label(status_bar, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.recognition_progress_bar = ttk.Progressbar(
            status_bar,
            variable=self.recognition_progress_var,
            maximum=100,
            mode="determinate",
            length=110,
        )
        self.recognition_progress_bar.grid(row=0, column=2, sticky="w", padx=(0, 4))
        ttk.Label(status_bar, textvariable=self.recognition_progress_text_var, width=5).grid(
            row=0,
            column=3,
            sticky="w",
            padx=(0, 18),
        )
        self.input_level_bar = ttk.Progressbar(
            status_bar,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=90,
        )
        ttk.Label(status_bar, textvariable=self.input_level_text_var).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.input_level_bar.grid(row=0, column=5, sticky="w", padx=(0, 18))
        ttk.Label(status_bar, textvariable=self.record_time_var).grid(row=0, column=6, sticky="w", padx=(0, 18))
        ttk.Label(status_bar, textvariable=self.recognition_time_var).grid(row=0, column=7, sticky="w", padx=(0, 18))
        ttk.Label(status_bar, textvariable=self.spellcheck_status_var).grid(row=0, column=8, sticky="w")

        self._build_settings_window()
        self._update_translation_button_state()

    def _build_settings_window(self) -> None:
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Dicta: настройки")
        self.settings_window.geometry("820x540")
        self.settings_window.minsize(720, 420)
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
        ttk.Label(recording_tab, text="Источник:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.audio_source_box = ttk.Combobox(
            recording_tab,
            textvariable=self.audio_source_var,
            values=list(AUDIO_SOURCE_LABELS.values()),
            state="readonly",
            width=28,
        )
        self.audio_source_box.grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.audio_source_box.bind("<<ComboboxSelected>>", self._on_audio_source_changed)

        ttk.Label(recording_tab, text="Устройство вывода:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8)
        )
        self.system_output_device_box = ttk.Combobox(
            recording_tab,
            textvariable=self.system_output_device_var,
            values=[DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL],
            state="readonly",
            width=64,
        )
        self.system_output_device_box.grid(row=1, column=1, columnspan=4, sticky="ew", pady=(0, 8))
        self.system_output_device_box.bind("<<ComboboxSelected>>", self._on_system_output_device_changed)
        system_output_buttons = ttk.Frame(recording_tab)
        system_output_buttons.grid(row=2, column=1, columnspan=4, sticky="w", pady=(0, 8))
        self.refresh_system_output_button = ttk.Button(
            system_output_buttons,
            text="Обновить",
            command=self.refresh_system_output_devices,
        )
        self.refresh_system_output_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.test_system_audio_button = ttk.Button(
            system_output_buttons,
            text="Проверить звук",
            command=self.start_system_audio_test,
        )
        self.test_system_audio_button.grid(row=0, column=1, sticky="w")

        ttk.Label(recording_tab, text="Микрофон:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.input_device_box = ttk.Combobox(
            recording_tab,
            textvariable=self.input_device_var,
            state="readonly",
            width=52,
        )
        self.input_device_box.grid(row=3, column=1, columnspan=4, sticky="ew", pady=(0, 8))
        microphone_buttons = ttk.Frame(recording_tab)
        microphone_buttons.grid(row=4, column=1, columnspan=4, sticky="w")
        self.refresh_input_button = ttk.Button(microphone_buttons, text="Обновить", command=self.refresh_input_devices)
        self.refresh_input_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.test_input_button = ttk.Button(microphone_buttons, text="Проверить", command=self.start_microphone_test)
        self.test_input_button.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.find_input_button = ttk.Button(microphone_buttons, text="Найти микрофон", command=self.start_microphone_search)
        self.find_input_button.grid(row=0, column=2, sticky="w")
        ttk.Label(recording_tab, textvariable=self.input_level_text_var).grid(row=5, column=1, sticky="w", pady=(14, 0))
        self.microphone_search_progress = ttk.Progressbar(
            recording_tab,
            variable=self.input_level_var,
            maximum=100,
            mode="determinate",
            length=180,
        )
        self.microphone_search_progress.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 8))
        ttk.Label(recording_tab, textvariable=self.microphone_search_status_var, width=28).grid(
            row=6,
            column=3,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(recording_tab, text="Усиление записи:").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        self.audio_gain_scale = ttk.Scale(
            recording_tab,
            from_=0,
            to=AUDIO_GAIN_MAX_PERCENT,
            variable=self.audio_gain_percent_var,
            command=self._on_audio_gain_changed,
        )
        self.audio_gain_scale.grid(row=7, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 8))
        ttk.Label(recording_tab, textvariable=self.audio_gain_percent_text_var, width=14).grid(
            row=7,
            column=3,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Label(recording_tab, textvariable=self.hotkey_status_var).grid(row=8, column=1, sticky="w", pady=(8, 0))

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
        self.model_box = ttk.Combobox(
            performance_tab,
            textvariable=self.model_var,
            values=list(available_model_options().keys()),
            state="readonly",
            width=30,
        )
        self.model_box.grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.model_box.bind("<<ComboboxSelected>>", self._on_model_changed)

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
        self.backend_benchmark_button = ttk.Button(benchmark_buttons, text="Подобрать движок", command=self.start_backend_benchmark)
        self.benchmark_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.backend_benchmark_button.grid(row=0, column=1, sticky="w")
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
        self._refresh_model_options()
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
        for model_path in required_model_paths():
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
        if self._is_audio_source_busy():
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
        self._update_audio_source_controls_state()

    def _set_record_button_recording(self) -> None:
        self.record_button.configure(text="Стоп", command=self.stop_recording, state=tk.NORMAL)
        self._set_recognition_mode_controls_state(tk.DISABLED)
        self._set_translation_buttons_state(tk.DISABLED)
        self._update_audio_source_controls_state()

    def _set_record_button_recognizing(self) -> None:
        self.record_button.configure(text="Прервать", command=self.cancel_recognition, state=tk.NORMAL)
        self._set_recognition_mode_controls_state(tk.DISABLED)
        self._set_translation_buttons_state(tk.DISABLED)
        self._update_audio_source_controls_state()

    def _set_record_button_busy(self, text: str) -> None:
        self.record_button.configure(text=text, state=tk.DISABLED)
        self._set_recognition_mode_controls_state(tk.DISABLED)
        self._set_translation_buttons_state(tk.DISABLED)
        self._update_audio_source_controls_state()

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

    def _refresh_model_options(self) -> None:
        options = list(available_model_options().keys())
        model_box = getattr(self, "model_box", None)
        if model_box is not None:
            model_box.configure(values=options)
        if self.model_var.get() not in options:
            self._select_model_key(choose_best_quality_model_key())

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

    def _select_model_key(self, model_key: str) -> None:
        model_key = sanitize_model_key(model_key, require_available=True)
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

    def _selected_audio_source_key(self) -> str:
        return AUDIO_SOURCE_KEY_BY_LABEL.get(self.audio_source_var.get(), DEFAULT_AUDIO_SOURCE_KEY)

    def _select_audio_source_key(self, source_key: object | None) -> None:
        self.audio_source_var.set(AUDIO_SOURCE_LABELS[sanitize_audio_source_key(source_key)])

    def _is_system_audio_source_selected(self) -> bool:
        return self._selected_audio_source_key() == "system"

    def _is_combined_audio_source_selected(self) -> bool:
        return self._selected_audio_source_key() == "combined"

    def _selected_source_uses_system_audio(self) -> bool:
        return self._selected_audio_source_key() in {"system", "combined"}

    def _selected_source_uses_microphone(self) -> bool:
        return self._selected_audio_source_key() in {"microphone", "combined"}

    def _is_audio_source_busy(self) -> bool:
        return (
            self.is_recording
            or self.is_recognizing
            or self.is_protocol_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_testing_system_audio
            or self.is_benchmarking
            or self.is_translating
        )

    def _on_audio_source_changed(self, event=None) -> None:
        if self._selected_source_uses_system_audio() and not self._is_audio_source_busy():
            self.refresh_system_output_devices(show_status=False)
        self._update_audio_source_controls_state()
        if self._is_combined_audio_source_selected():
            self._set_status("Источник записи: системный звук и микрофон")
        elif self._is_system_audio_source_selected():
            self._set_status("Источник записи: системный звук встречи")
        else:
            self._set_status("Источник записи: микрофон")

    def _selected_system_output_device_id(self) -> str:
        return self.system_output_devices.get(
            self.system_output_device_var.get(),
            DEFAULT_SYSTEM_OUTPUT_DEVICE_ID,
        )

    def _select_system_output_device_id(self, device_id: object | None) -> None:
        if not self.system_output_devices:
            self.system_output_devices = {
                DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL: DEFAULT_SYSTEM_OUTPUT_DEVICE_ID
            }
        label = system_output_device_label_for_id(self.system_output_devices, device_id)
        self.system_output_device_var.set(label)

    def _on_system_output_device_changed(self, event=None) -> None:
        self._set_status("Устройство вывода выбрано")

    def _update_audio_source_controls_state(self) -> None:
        busy = self._is_audio_source_busy()
        for source_box_name in ("audio_source_box", "toolbar_audio_source_box"):
            source_box = getattr(self, source_box_name, None)
            if source_box is not None:
                source_box.configure(state=tk.DISABLED if busy else "readonly")

        system_controls_available = self._selected_source_uses_system_audio()
        system_box_state = "readonly" if system_controls_available and not busy and self.system_output_devices else tk.DISABLED
        system_refresh_state = tk.NORMAL if system_controls_available and not busy else tk.DISABLED
        system_test_state = tk.NORMAL if system_controls_available and not busy and self.system_output_devices else tk.DISABLED
        for control_name, state in (
            ("system_output_device_box", system_box_state),
            ("refresh_system_output_button", system_refresh_state),
            ("test_system_audio_button", system_test_state),
        ):
            control = getattr(self, control_name, None)
            if control is not None:
                control.configure(state=state)

        microphone_controls_available = bool(self.input_devices) and self._selected_source_uses_microphone()
        microphone_state = "readonly" if microphone_controls_available and not busy else tk.DISABLED
        microphone_button_state = tk.NORMAL if microphone_controls_available and not busy else tk.DISABLED
        for control_name, state in (
            ("input_device_box", microphone_state),
            ("refresh_input_button", microphone_button_state),
            ("test_input_button", microphone_button_state),
            ("find_input_button", microphone_button_state),
        ):
            control = getattr(self, control_name, None)
            if control is not None:
                control.configure(state=state)

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
        translate_button = getattr(self, "translate_button", None)
        if translate_button is not None:
            translate_button.configure(state=state)
        translate_menu = getattr(self, "translate_menu", None)
        if translate_menu is not None:
            translate_menu.entryconfigure(self.translate_to_ru_menu_index, state=state)
            translate_menu.entryconfigure(self.translate_to_en_menu_index, state=state)
        if state == tk.DISABLED:
            self._set_translation_undo_state(tk.DISABLED)

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
            or self.is_protocol_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_testing_system_audio
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
        translate_menu = getattr(self, "translate_menu", None)
        if translate_menu is not None:
            translate_menu.entryconfigure(self.translate_to_ru_menu_index, state=to_ru_state)
            translate_menu.entryconfigure(self.translate_to_en_menu_index, state=to_en_state)

        translate_button = getattr(self, "translate_button", None)
        if translate_button is not None:
            translate_button.configure(state=tk.NORMAL if to_ru_state == tk.NORMAL or to_en_state == tk.NORMAL else tk.DISABLED)
        undo_translation_state = tk.NORMAL if self._is_translation_undo_available() and not busy else tk.DISABLED
        self._set_translation_undo_state(undo_translation_state)

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
        if self._is_audio_source_busy():
            return

        self.benchmark_cancel_event.clear()
        self.is_benchmarking = True
        self._set_status("Бенчмарк модели: подготовка...")
        self.speed_status_var.set("Бенчмарк модели: идет проверка доступных моделей")
        self._set_record_button_busy("Бенчмарк")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(text="Прервать тест", command=self.cancel_benchmark, state=tk.NORMAL)
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
                cancel_event=self.benchmark_cancel_event,
                print_fn=report_progress,
            )
            if not any(item.get("ok") for item in profile.get("results", {}).values()):
                raise RuntimeError("No local models were available for benchmark.")
            self.ui_queue.put(("benchmark_result", profile))
        except RecognitionCancelled:
            self.ui_queue.put(("benchmark_cancelled", None))
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
        if self._is_audio_source_busy():
            return

        self.benchmark_cancel_event.clear()
        self.is_benchmarking = True
        self._set_status("Подбор движка: подготовка...")
        self.speed_status_var.set("Подбор движка: быстрый тест легкой модели")
        self._set_record_button_busy("Бенчмарк")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(text="Прервать тест", command=self.cancel_benchmark, state=tk.NORMAL)
        self.input_device_box.configure(state=tk.DISABLED)
        self.refresh_input_button.configure(state=tk.DISABLED)
        self.test_input_button.configure(state=tk.DISABLED)
        self.find_input_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._benchmark_backends_worker, daemon=True).start()

    def _benchmark_backends_worker(self) -> None:
        try:
            def report_progress(message: str) -> None:
                self.ui_queue.put(("backend_benchmark_progress", message))

            benchmark_model_key = choose_backend_benchmark_model_key()
            report_progress(f"модель для теста: {benchmark_model_key}")
            profile = run_backend_benchmark(
                model_key=benchmark_model_key,
                allow_missing_models=True,
                preferred_backend_key=self._selected_backend_preference(),
                cancel_event=self.benchmark_cancel_event,
                quick=True,
                print_fn=report_progress,
            )
            if profile.get("compat_suggested"):
                self.ui_queue.put(("backend_benchmark_compat_suggested", profile))
                return
            if (
                not profile.get("compat_auto_selected")
                and not any(profile.get("results", {}).get(backend_name, {}).get("ok") for backend_name in WHISPER_BACKENDS)
            ):
                raise RuntimeError("No local whisper.cpp backends completed the benchmark.")
            self.ui_queue.put(("backend_benchmark_result", profile))
        except RecognitionCancelled:
            self.ui_queue.put(("benchmark_cancelled", None))
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

    def cancel_benchmark(self) -> None:
        if not self.is_benchmarking:
            return
        self.benchmark_cancel_event.set()
        self._set_status("Прерывание теста")
        self.speed_status_var.set("Тест прерывается...")
        self.benchmark_button.configure(text="Прерывание...", state=tk.DISABLED)
        self.backend_benchmark_button.configure(text="Прерывание...", state=tk.DISABLED)

    def refresh_system_output_devices(self, show_status: bool = True) -> None:
        previous_device_id = self._selected_system_output_device_id()
        saved_device_id = sanitize_system_output_device_id(
            self.settings.get("system_output_device_id", DEFAULT_SYSTEM_OUTPUT_DEVICE_ID)
        )
        if not show_status and previous_device_id == DEFAULT_SYSTEM_OUTPUT_DEVICE_ID:
            previous_device_id = saved_device_id

        try:
            devices = collect_wasapi_output_devices()
        except Exception as exc:
            self.system_output_devices = {
                DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL: DEFAULT_SYSTEM_OUTPUT_DEVICE_ID
            }
            self.system_output_device_info_by_id = {}
            self.system_output_device_box.configure(values=[DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL])
            self.system_output_device_var.set(DEFAULT_SYSTEM_OUTPUT_DEVICE_LABEL)
            self._update_audio_source_controls_state()
            if show_status:
                self._set_status(f"Не удалось прочитать устройства вывода: {exc}")
            return

        labels, label_to_id, id_to_device = build_system_output_device_choices(devices)
        self.system_output_devices = label_to_id
        self.system_output_device_info_by_id = id_to_device
        self.system_output_device_box.configure(values=labels)
        self._select_system_output_device_id(previous_device_id)
        self._update_audio_source_controls_state()
        if show_status:
            if devices:
                self._set_status(f"Устройства вывода обновлены: {len(devices)}")
            else:
                self._set_status("Активные устройства вывода не найдены")

    def refresh_input_devices(self) -> None:
        previous_value = self.input_device_var.get()

        try:
            labels, input_devices, default_input = collect_input_device_groups()
        except Exception as exc:
            self.input_devices = {}
            self.input_device_var.set("")
            self.input_device_box.configure(values=[])
            self._update_audio_source_controls_state()
            if self._is_system_audio_source_selected():
                self._set_record_button_idle()
                self._set_status("Микрофоны не прочитаны; системный звук доступен")
            else:
                self._set_record_button_busy("Нет микрофона")
                self._set_status("Не удалось прочитать микрофоны")
            return

        self.input_devices = input_devices
        self.preferred_input_configs = {
            label: config for label, config in self.preferred_input_configs.items() if label in input_devices
        }
        self.input_device_box.configure(values=labels)
        if not labels:
            self.input_device_var.set("")
            self._update_audio_source_controls_state()
            if self._is_system_audio_source_selected():
                if not self._is_audio_source_busy():
                    self._set_record_button_idle()
                self._set_status("Микрофоны не найдены; системный звук доступен")
            else:
                self._set_record_button_busy("Нет микрофона")
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
        if not self._is_audio_source_busy():
            self._set_record_button_idle()
        self._update_audio_source_controls_state()

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

    def start_system_audio_test(self) -> None:
        if self._is_audio_source_busy():
            return
        if not self._selected_source_uses_system_audio():
            self._set_status("Выберите источник с системным звуком")
            return

        self.is_testing_system_audio = True
        self.last_input_stream_config = None
        self.microphone_search_progress_var.set(0)
        self.microphone_search_status_var.set("Системный звук: проверка...")
        self._set_input_level(0)
        self._set_status("Проверка системного звука: включите звук встречи")
        self._set_record_button_busy("Проверка")
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(state=tk.DISABLED)
        self._update_audio_source_controls_state()
        device_id = self._selected_system_output_device_id()
        threading.Thread(target=self._system_audio_test_worker, args=(device_id,), daemon=True).start()

    def _system_audio_test_worker(self, device_id: str) -> None:
        try:
            result = measure_wasapi_loopback_level(device_id, seconds=SYSTEM_AUDIO_TEST_SECONDS)
            self.ui_queue.put(("system_audio_test_result", result))
        except Exception as exc:
            self.ui_queue.put(("system_audio_test_error", self._format_system_audio_error(
                "Не удалось проверить системный звук.",
                exc,
            )))
        finally:
            self.ui_queue.put(("system_audio_test_ready", None))

    def finish_system_audio_test(self) -> None:
        if not self.is_testing_system_audio:
            return

        self.is_testing_system_audio = False
        self._set_record_button_idle()
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state="readonly")
        self.benchmark_button.configure(state=tk.NORMAL)
        self.backend_box.configure(state="readonly")
        self.backend_benchmark_button.configure(state=tk.NORMAL)
        self._update_audio_source_controls_state()
        self.microphone_search_progress_var.set(0)

    def _handle_system_audio_test_result(self, result: dict) -> None:
        peak = int(result.get("peak", 0))
        self.last_input_stream_config = result.get("config") if isinstance(result.get("config"), dict) else None
        self.input_level_var.set(peak)
        self.input_level_text_var.set(f"Пик: {peak}%")
        config_text = input_stream_config_text(self.last_input_stream_config)
        callback_count = int(result.get("callback_count", 0) or 0)
        byte_count = int(result.get("bytes", 0) or 0)

        if result.get("ok"):
            self._set_status(f"Системный звук работает, пик {peak}%")
            self.microphone_search_status_var.set(f"Системный звук: пик {peak}%")
            return

        self._set_status("Системный звук открыт, но сигнал не найден")
        self.microphone_search_status_var.set("Системный звук: тишина")
        messagebox.showwarning(
            "Dicta",
            self._format_problem_message(
                "Dicta открыла выбранное устройство вывода, но не увидела заметного звука.",
                [
                    "Включите воспроизведение встречи, видео или другого источника звука.",
                    "Проверьте, что звук слышен именно в выбранных колонках или наушниках.",
                    "Если звук идет в другое устройство, выберите его в строке Устройство вывода.",
                    "Проверьте громкость Teams, Zoom, браузера или другой программы встречи.",
                ],
                details=(
                    f"Открытый режим: {config_text}\n"
                    f"Callback count: {callback_count}\n"
                    f"Bytes: {byte_count}"
                ),
            ),
        )

    def start_microphone_test(self) -> None:
        if self._is_audio_source_busy():
            return
        if self._is_system_audio_source_selected():
            self._set_status("Выбран системный звук; проверка микрофона не нужна")
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
        self.benchmark_button.configure(state=tk.NORMAL)
        self.backend_box.configure(state="readonly")
        self.backend_benchmark_button.configure(state=tk.NORMAL)
        self._update_audio_source_controls_state()
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
        if self._is_audio_source_busy():
            return
        if self._is_system_audio_source_selected():
            self._set_status("Выбран системный звук; поиск микрофона не нужен")
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
        if self._is_audio_source_busy():
            return

        self.audio_chunks = []
        self.system_audio_chunks = []
        self.microphone_audio_chunks = []
        self.system_audio_sample_rate = SAMPLE_RATE
        self.microphone_audio_sample_rate = SAMPLE_RATE
        self.system_recording_peak = 0
        self.microphone_recording_peak = 0
        self.recognition_time_var.set("-")
        self._reset_recognition_progress()
        self.last_input_stream_config = None
        self.last_recording_source_key = self._selected_audio_source_key()
        self._clear_last_recognition_audio()
        self.recognition_cancel_event.clear()
        self._set_input_level(0)

        try:
            self.stream = self._open_recording_stream()
        except Exception as exc:
            self.stream = None
            source_key = self.last_recording_source_key
            source_uses_system = source_key in {"system", "combined"}
            source_uses_microphone = source_key in {"microphone", "combined"}
            if source_key == "combined":
                self._set_status("Ошибка записи встречи")
            elif source_uses_system:
                self._set_status("Ошибка системного звука")
            else:
                self._set_status("Ошибка микрофона")
            messagebox.showerror(
                "Dicta",
                self._format_system_audio_error("Не удалось начать запись системного звука.", exc)
                if source_uses_system and not source_uses_microphone
                else self._format_combined_recording_error("Не удалось начать запись системного звука и микрофона.", exc)
                if source_uses_system and source_uses_microphone
                else self._format_microphone_error(
                    "Не удалось начать запись.",
                    exc,
                    include_diagnostics=True,
                ),
            )
            return

        self.is_recording = True
        self.record_started_at = time.perf_counter()
        if self.last_recording_source_key == "combined":
            self._set_status("Запись системного звука и микрофона")
        elif self.last_recording_source_key == "system":
            self._set_status("Запись системного звука")
        else:
            self._set_status("Запись")
        self._set_record_button_recording()
        self.stop_button.configure(state=tk.NORMAL)
        self.model_box.configure(state=tk.DISABLED)
        self.benchmark_button.configure(state=tk.DISABLED)
        self.backend_box.configure(state=tk.DISABLED)
        self.backend_benchmark_button.configure(state=tk.DISABLED)
        self._update_audio_source_controls_state()

    def _open_recording_stream(self):
        if self._is_combined_audio_source_selected():
            return self._open_combined_recording_stream()
        if self._is_system_audio_source_selected():
            stream, config = open_wasapi_loopback_stream(
                self._audio_callback,
                start=True,
                device_id=self._selected_system_output_device_id(),
            )
            self.record_sample_rate = int(config.get("sample_rate", SAMPLE_RATE))
            self.last_input_stream_config = config
            return stream
        return self._open_input_stream(self._selected_input_device_indexes())

    def _open_combined_recording_stream(self) -> CombinedRecordingStream:
        system_stream = None
        microphone_stream = None
        try:
            self._start_protocol_streaming()
            system_stream, system_config = open_wasapi_loopback_stream(
                self._system_audio_callback,
                start=True,
                device_id=self._selected_system_output_device_id(),
            )
            self.system_audio_sample_rate = int(system_config.get("sample_rate", SAMPLE_RATE))
            self._open_system_recording_file(self.system_audio_sample_rate)
            self.last_input_stream_config = {
                "source_type": "combined",
                "sample_rate": SAMPLE_RATE,
                "system": system_config,
                "microphone": {},
            }
            microphone_stream = self._open_input_stream(
                self._selected_input_device_indexes(),
                callback=self._microphone_recording_callback,
            )
            microphone_config = self.last_input_stream_config or {}
            self.microphone_audio_sample_rate = int(microphone_config.get("sample_rate", SAMPLE_RATE))
            self._open_microphone_recording_file(self.microphone_audio_sample_rate)
            self.record_sample_rate = SAMPLE_RATE
            self.last_input_stream_config = {
                "source_type": "combined",
                "sample_rate": SAMPLE_RATE,
                "system": system_config,
                "microphone": microphone_config,
            }
            return CombinedRecordingStream(system_stream, microphone_stream)
        except Exception:
            for stream in (microphone_stream, system_stream):
                if stream is not None:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
            self._cancel_protocol_streaming()
            raise

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

    def _open_recording_file(self, prefix: str, sample_rate: int):
        fd, path_text = tempfile.mkstemp(prefix=prefix, suffix=".wav")
        os.close(fd)
        path = Path(path_text)
        wav = wave.open(str(path), "wb")
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav.setframerate(max(1, int(sample_rate or SAMPLE_RATE)))
        self.recording_temp_paths.append(path)
        return wav

    def _open_system_recording_file(self, sample_rate: int) -> None:
        self.system_recording_wav = self._open_recording_file("dicta_system_", sample_rate)

    def _open_microphone_recording_file(self, sample_rate: int) -> None:
        self.microphone_recording_wav = self._open_recording_file("dicta_microphone_", sample_rate)

    def _close_recording_files(self) -> None:
        for attr_name in ("system_recording_wav", "microphone_recording_wav"):
            wav = getattr(self, attr_name, None)
            if wav is not None:
                try:
                    wav.close()
                except Exception:
                    pass
                setattr(self, attr_name, None)

    def _cleanup_recording_temp_files(self) -> None:
        for path in self.recording_temp_paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        self.recording_temp_paths = []

    def _start_protocol_streaming(self) -> None:
        self._cancel_protocol_streaming(mark_cancelled=False)
        self.protocol_prepare_queue = queue.Queue()
        self.protocol_recognition_queue = queue.Queue()
        self.protocol_system_chunk_parts = []
        self.protocol_microphone_chunk_parts = []
        self.protocol_system_chunk_bytes = 0
        self.protocol_microphone_chunk_bytes = 0
        self.protocol_chunk_index = 0
        self.protocol_chunks_queued = 0
        self.protocol_chunks_recognized = 0
        self.protocol_text_started = False
        self.recording_temp_paths = []
        self.is_protocol_recognizing = True
        self.protocol_prepare_thread = threading.Thread(target=self._protocol_prepare_worker, daemon=True)
        self.protocol_recognition_thread = threading.Thread(target=self._protocol_recognition_worker, daemon=True)
        self.protocol_prepare_thread.start()
        self.protocol_recognition_thread.start()

    def _cancel_protocol_streaming(self, mark_cancelled: bool = True) -> None:
        if mark_cancelled:
            self.recognition_cancel_event.set()
        if self.protocol_prepare_queue is not None:
            try:
                self.protocol_prepare_queue.put(None)
            except Exception:
                pass
        self._close_recording_files()
        self._cleanup_recording_temp_files()
        self.protocol_system_chunk_parts = []
        self.protocol_microphone_chunk_parts = []
        self.protocol_system_chunk_bytes = 0
        self.protocol_microphone_chunk_bytes = 0
        self.is_protocol_recognizing = False

    def _protocol_chunk_seconds_locked(self) -> float:
        system_seconds = self.protocol_system_chunk_bytes / (
            max(1, int(self.system_audio_sample_rate or SAMPLE_RATE)) * SAMPLE_WIDTH_BYTES
        )
        microphone_seconds = self.protocol_microphone_chunk_bytes / (
            max(1, int(self.microphone_audio_sample_rate or SAMPLE_RATE)) * SAMPLE_WIDTH_BYTES
        )
        return max(system_seconds, microphone_seconds)

    def _take_protocol_chunk_locked(self, final: bool = False) -> dict | None:
        duration = self._protocol_chunk_seconds_locked()
        if duration <= 0:
            return None
        if final and duration < PROTOCOL_FINAL_CHUNK_MIN_SECONDS and self.protocol_chunks_queued > 0:
            self.protocol_system_chunk_parts = []
            self.protocol_microphone_chunk_parts = []
            self.protocol_system_chunk_bytes = 0
            self.protocol_microphone_chunk_bytes = 0
            return None
        if not final and duration < PROTOCOL_CHUNK_SECONDS:
            return None

        self.protocol_chunk_index += 1
        chunk = {
            "index": self.protocol_chunk_index,
            "system_audio": b"".join(self.protocol_system_chunk_parts),
            "system_rate": self.system_audio_sample_rate,
            "microphone_audio": b"".join(self.protocol_microphone_chunk_parts),
            "microphone_rate": self.microphone_audio_sample_rate,
            "recognition_mode_key": self._selected_recognition_mode_key(),
        }
        self.protocol_system_chunk_parts = []
        self.protocol_microphone_chunk_parts = []
        self.protocol_system_chunk_bytes = 0
        self.protocol_microphone_chunk_bytes = 0
        self.protocol_chunks_queued += 1
        return chunk

    def _queue_protocol_chunk(self, chunk: dict | None) -> None:
        if chunk is None or self.protocol_prepare_queue is None:
            return
        self.protocol_prepare_queue.put(chunk)

    def _finish_combined_recording_streaming(self) -> bool:
        final_chunk: dict | None = None
        with self.recording_lock:
            final_chunk = self._take_protocol_chunk_locked(final=True)
        self._queue_protocol_chunk(final_chunk)
        self._close_recording_files()
        if self.protocol_prepare_queue is not None:
            self.protocol_prepare_queue.put(None)
        self.record_sample_rate = SAMPLE_RATE
        return self.protocol_chunks_queued > 0

    def _protocol_prepare_worker(self) -> None:
        prepare_queue = self.protocol_prepare_queue
        recognition_queue = self.protocol_recognition_queue
        if prepare_queue is None or recognition_queue is None:
            return

        try:
            while True:
                item = prepare_queue.get()
                if item is None:
                    recognition_queue.put(None)
                    return

                try:
                    mixed_audio = mix_recording_sources(
                        bytes(item.get("system_audio", b"")),
                        int(item.get("system_rate", SAMPLE_RATE)),
                        bytes(item.get("microphone_audio", b"")),
                        int(item.get("microphone_rate", SAMPLE_RATE)),
                        SAMPLE_RATE,
                    )
                    if mixed_audio:
                        recognition_queue.put(
                            {
                                "index": int(item.get("index", 0)),
                                "audio": mixed_audio,
                                "sample_rate": SAMPLE_RATE,
                                "recognition_mode_key": item.get(
                                    "recognition_mode_key",
                                    self._selected_recognition_mode_key(),
                                ),
                            }
                        )
                except Exception as exc:
                    self.ui_queue.put(("protocol_recognition_error", exc))
        finally:
            if recognition_queue is not None:
                recognition_queue.put(None)

    def _protocol_recognition_worker(self) -> None:
        recognition_queue = self.protocol_recognition_queue
        if recognition_queue is None:
            return

        cancelled = False
        try:
            while True:
                item = recognition_queue.get()
                if item is None:
                    break
                if self.recognition_cancel_event.is_set():
                    cancelled = True
                    break

                try:
                    result = self._recognize_pcm16_audio(
                        bytes(item.get("audio", b"")),
                        int(item.get("sample_rate", SAMPLE_RATE)),
                        str(item.get("recognition_mode_key", self._selected_recognition_mode_key())),
                    )
                    if str(result.get("recognized", "")).strip():
                        self.ui_queue.put(("protocol_chunk_recognized", (int(item.get("index", 0)), result)))
                except RecognitionCancelled:
                    cancelled = True
                    break
                except Exception as exc:
                    if str(exc).strip() == "silent-or-short-recording":
                        continue
                    self.ui_queue.put(("protocol_recognition_error", exc))
                    cancelled = True
                    break
        finally:
            self.ui_queue.put(("protocol_recognition_done", {"cancelled": cancelled}))

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

        if self.last_recording_source_key == "combined":
            has_protocol_chunks = self._finish_combined_recording_streaming()
            if not has_protocol_chunks:
                self.record_started_at = None
                self.record_time_var.set("Запись: 00:00")
                self.is_protocol_recognizing = False
                self._set_status("Готово")
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(state=tk.NORMAL)
                self._update_audio_source_controls_state()
                messagebox.showwarning(
                    "Dicta",
                    self._format_problem_message(
                        "Запись пустая: Dicta не получила системный звук и микрофон.",
                        [
                            "Проверьте, что звук встречи слышен в колонках или наушниках.",
                            "Проверьте, что выбранный микрофон работает.",
                            "Нажмите Проверить звук и Проверить микрофон в настройках записи.",
                        ],
                        details=f"Открытый режим: {input_stream_config_text(self.last_input_stream_config)}",
                    ),
                )
                return

            self.is_recognizing = True
            self._start_recognition_progress()
            self._set_status("Распознавание протокола")
            self._set_record_button_recognizing()
            return

        if not self.audio_chunks:
            self.record_started_at = None
            self.record_time_var.set("Запись: 00:00")
            self._set_status("Готово")
            self._set_record_button_idle()
            self.model_box.configure(state="readonly")
            self.benchmark_button.configure(state=tk.NORMAL)
            self.backend_box.configure(state="readonly")
            self.backend_benchmark_button.configure(state=tk.NORMAL)
            self._update_audio_source_controls_state()
            if self.last_recording_source_key == "combined":
                summary = "Запись пустая: Dicta не получила системный звук и микрофон."
                steps = [
                    "Проверьте, что звук встречи слышен в колонках или наушниках.",
                    "Проверьте, что выбранный микрофон работает.",
                    "Нажмите Проверить звук и Проверить микрофон в настройках записи.",
                ]
            elif self.last_recording_source_key == "system":
                summary = "Запись пустая: Dicta не получила системный звук."
                steps = [
                    "Проверьте, что звук встречи слышен в колонках или наушниках.",
                    "Проверьте, что нужные колонки или наушники выбраны в Windows как устройство вывода по умолчанию.",
                    "Проверьте громкость Teams, Zoom, браузера или другой программы встречи.",
                ]
            else:
                summary = "Запись пустая: Dicta не получил аудиоданные от микрофона."
                steps = [
                    "Нажмите Проверить и скажите несколько слов.",
                    "Если индикатор уровня не двигается, нажмите Найти микрофон или выберите другой микрофон.",
                    "Если проблема повторяется, запустите scripts\\diagnose_dicta.cmd.",
                ]
            messagebox.showwarning(
                "Dicta",
                self._format_problem_message(
                    summary,
                    steps,
                    details=f"Открытый режим: {input_stream_config_text(self.last_input_stream_config)}",
                ),
            )
            return

        self.is_recognizing = True
        self.recognition_cancel_event.clear()
        self._start_recognition_progress()
        self._set_status("Распознавание")
        self._set_record_button_recognizing()
        self.worker = threading.Thread(target=self._recognize_audio, daemon=True)
        self.worker.start()

    def cancel_recognition(self) -> None:
        if not self.is_recognizing and not self.is_protocol_recognizing:
            return

        self.recognition_cancel_event.set()
        self._set_status("Прерывание распознавания")
        self._set_record_button_busy("Прерывание")
        with self.recognition_process_lock:
            process = self.recognition_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def _set_recognition_process(self, process: subprocess.Popen | None) -> None:
        with self.recognition_process_lock:
            self.recognition_process = process
            should_stop = process is not None and self.recognition_cancel_event.is_set()
        if should_stop and process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def _start_translation_warmup_after_recognition(self, recognition_mode_key: str) -> None:
        worker = self.translation_warmup_worker
        if worker is not None and worker.is_alive():
            return

        if recognition_mode_key == RUSSIAN_RECOGNITION_MODE_KEY:
            direction = ("ru", "en")
        else:
            direction = ("en", "ru")

        self.translation_warmup_worker = threading.Thread(
            target=self._warm_up_translation_worker,
            args=direction,
            daemon=True,
        )
        self.translation_warmup_worker.start()

    def _warm_up_translation_worker(self, from_code: str, to_code: str) -> None:
        try:
            status = detect_translation_pack()
            if is_translation_direction_available(status, from_code, to_code):
                warm_up_argos_translation(status, from_code=from_code, to_code=to_code)
        except Exception:
            pass

    def _save_current_settings(self) -> bool:
        settings = {
            "auto_copy": self.auto_copy_var.get(),
            "format_text": self.format_text_var.get(),
            "voice_punctuation": self.voice_punctuation_var.get(),
            "audio_source": self._selected_audio_source_key(),
            "system_output_device_id": self._selected_system_output_device_id(),
            "recognition_mode": self._selected_recognition_mode_key(),
            "audio_gain_percent": clamp_audio_gain_percent(self.audio_gain_percent_var.get()),
            "backend": self._selected_backend_key(),
            "model_key": self._selected_model_key(),
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
            "audio_source": self._selected_audio_source_key(),
            "system_output_device_id": self._selected_system_output_device_id(),
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
        self._select_audio_source_key(state.get("audio_source", DEFAULT_USER_SETTINGS["audio_source"]))
        self._select_system_output_device_id(
            state.get("system_output_device_id", DEFAULT_USER_SETTINGS["system_output_device_id"])
        )
        model_key = MODEL_KEY_BY_LABEL.get(str(state.get("model", DEFAULT_MODEL_LABEL)), FALLBACK_AUTO_MODEL_KEY)
        self._select_model_key(model_key)
        self.backend_var.set(str(state.get("backend", DEFAULT_BACKEND_LABEL)))
        self._select_recognition_mode_key(state.get("recognition_mode", DEFAULT_RECOGNITION_MODE_KEY))
        self.auto_copy_var.set(bool(state.get("auto_copy", DEFAULT_USER_SETTINGS["auto_copy"])))
        self.format_text_var.set(bool(state.get("format_text", DEFAULT_USER_SETTINGS["format_text"])))
        self.voice_punctuation_var.set(bool(state.get("voice_punctuation", DEFAULT_USER_SETTINGS["voice_punctuation"])))
        self.audio_gain_percent_var.set(
            clamp_audio_gain_percent(state.get("audio_gain_percent", DEFAULT_USER_SETTINGS["audio_gain_percent"]))
        )
        self._on_audio_gain_changed()
        self._update_audio_source_controls_state()
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

    def _set_translation_undo_state(self, state: str) -> None:
        undo_button = getattr(self, "undo_translation_button", None)
        if undo_button is not None:
            undo_button.configure(state=state)
        translate_menu = getattr(self, "translate_menu", None)
        undo_index = getattr(self, "undo_translation_menu_index", None)
        if translate_menu is not None and undo_index is not None:
            translate_menu.entryconfigure(undo_index, state=state)

    def _is_translation_undo_available(self) -> bool:
        if self.translation_undo_snapshot is None or getattr(self, "text", None) is None:
            return False
        _source, translated, _source_language_tag, _translated_language_tag = self.translation_undo_snapshot
        return self.text.get("1.0", "end-1c") == translated

    def _set_translation_undo(
        self,
        source: str,
        translated: str,
        source_language_tag: str,
        translated_language_tag: str,
    ) -> None:
        self.translation_undo_snapshot = (source, translated, source_language_tag, translated_language_tag)
        self._update_translation_button_state()

    def _reset_translation_undo(self) -> None:
        self.translation_undo_snapshot = None
        self._set_translation_undo_state(tk.DISABLED)

    def undo_last_translation(self) -> None:
        if self.translation_undo_snapshot is None:
            self._set_status("Нет перевода для возврата")
            return

        source, translated, source_language_tag, _translated_language_tag = self.translation_undo_snapshot
        current = self.text.get("1.0", "end-1c")
        if current != translated:
            self._reset_translation_undo()
            self._set_status("Текст изменен, возврат перевода недоступен")
            self._update_translation_button_state()
            return

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", source)
        self.current_text_spellcheck_language_tag = source_language_tag
        self.format_undo_snapshot = None
        self._set_format_action_label("Автоформат")
        self._reset_postprocess_undo()
        self._reset_translation_undo()
        self._set_status("Перевод возвращен")
        self._schedule_spellcheck(delay_ms=100)
        self._update_translation_button_state()

    def translate_current_text_to_russian(self) -> None:
        if (
            self.is_recording
            or self.is_recognizing
            or self.is_protocol_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_testing_system_audio
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
            or self.is_protocol_recognizing
            or self.is_testing_microphone
            or self.is_finding_microphone
            or self.is_testing_system_audio
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
        self._set_format_action_label("Автоформат")

    def _set_format_action_label(self, label: str) -> None:
        more_menu = getattr(self, "more_menu", None)
        if more_menu is not None:
            more_menu.entryconfigure(self.format_menu_index, label=label)

    def _reset_postprocess_undo(self) -> None:
        self.postprocess_undo_snapshot = None
        self._set_postprocess_undo_state(tk.DISABLED)

    def _set_postprocess_undo_state(self, state: str) -> None:
        more_menu = getattr(self, "more_menu", None)
        if more_menu is not None:
            more_menu.entryconfigure(self.undo_postprocess_menu_index, state=state)

    def _set_postprocess_undo(
        self,
        original: str,
        corrected: str,
        corrections: tuple[RecognitionCorrection, ...],
    ) -> None:
        self.postprocess_undo_snapshot = (original, corrected, corrections)
        self._set_postprocess_undo_state(tk.NORMAL)

    def undo_last_postprocess(self) -> None:
        if self.postprocess_undo_snapshot is None:
            self._set_status("Нет автоисправлений для отката")
            return

        original, corrected, corrections = self.postprocess_undo_snapshot
        current = self.text.get("1.0", "end-1c")
        if current != corrected:
            self._reset_postprocess_undo()
            self._set_status("Текст изменен, откат автоисправлений недоступен")
            return

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", original)
        remembered = remember_rejected_ru_corrections(corrections)
        self._reset_postprocess_undo()
        self._reset_translation_undo()
        if remembered:
            self._set_status("Автоисправления отменены и запомнены")
        else:
            self._set_status("Автоисправления отменены")
        self._schedule_spellcheck(delay_ms=100)
        self._update_translation_button_state()

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
        self._reset_postprocess_undo()
        self._reset_translation_undo()
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
        self._reset_postprocess_undo()
        self._reset_translation_undo()
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
            self._set_format_action_label("Автоформат")
            self._set_status("Нет текста для форматирования")
            return
        if self.format_undo_snapshot is not None:
            original, formatted_snapshot = self.format_undo_snapshot
            if value == formatted_snapshot:
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", original)
                self.format_undo_snapshot = None
                self._set_format_action_label("Автоформат")
                self._reset_postprocess_undo()
                self._reset_translation_undo()
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
            self._set_format_action_label("Автоформат")
            self._set_status("Текст уже отформатирован")
            return
        self.format_undo_snapshot = (value, formatted)
        self._reset_postprocess_undo()
        self._reset_translation_undo()
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", formatted)
        self._set_format_action_label("Вернуть форматирование")
        self._set_status("Текст отформатирован")
        self._schedule_spellcheck(delay_ms=100)

    def clear_text(self) -> None:
        self.text.delete("1.0", tk.END)
        self.format_undo_snapshot = None
        self._set_format_action_label("Автоформат")
        self._reset_postprocess_undo()
        self._reset_translation_undo()
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
                remember_menu = tk.Menu(menu, tearoff=False)
                for suggestion in issue.suggestions:
                    menu.add_command(
                        label=suggestion,
                        command=lambda value=suggestion, tag=issue_tag: self._replace_spelling_issue(tag, value),
                    )
                    remember_menu.add_command(
                        label=suggestion,
                        command=lambda value=suggestion, tag=issue_tag: self._replace_spelling_issue(
                            tag,
                            value,
                            remember=True,
                        ),
                    )
                menu.add_cascade(label="Исправить и запомнить", menu=remember_menu)
            else:
                menu.add_command(label="Нет вариантов", state=tk.DISABLED)

            menu.add_separator()
            menu.add_command(label="Считать словом Dicta", command=lambda tag=issue_tag: self._add_dicta_known_word(tag))
            menu.add_command(label="Добавить в словарь Windows", command=lambda tag=issue_tag: self._add_spelling_word(tag))
            menu.add_command(label="Пропустить", command=lambda tag=issue_tag: self._ignore_spelling_issue(tag))
            menu.add_separator()

        has_selection = self._has_text_selection()
        has_text = bool(self.text.get("1.0", tk.END).strip())
        can_paste = self._clipboard_has_text()
        selection_state = tk.NORMAL if has_selection else tk.DISABLED

        menu.add_command(
            label="Откатить автоисправления",
            command=self.undo_last_postprocess,
            state=tk.NORMAL if self.postprocess_undo_snapshot is not None else tk.DISABLED,
        )
        menu.add_separator()
        menu.add_command(label="Вырезать", command=self._cut_selection, state=selection_state)
        menu.add_command(label="Копировать", command=self._copy_selection, state=selection_state)
        menu.add_command(label="Вставить", command=self._paste_clipboard, state=tk.NORMAL if can_paste else tk.DISABLED)
        menu.add_command(
            label="Добавить выделенное в словарь Dicta",
            command=self._add_selected_dicta_known_words,
            state=selection_state,
        )
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=self._select_all_text, state=tk.NORMAL if has_text else tk.DISABLED)

        x_root, y_root = self._context_menu_position(event, index)
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        return "break"

    def _replace_spelling_issue(self, tag_name: str, replacement: str, remember: bool = False) -> None:
        issue = self.spelling_issues.get(tag_name)
        ranges = self.text.tag_ranges(tag_name)
        if len(ranges) < 2:
            return

        start, end = ranges[0], ranges[1]
        source = issue.word if issue is not None else self.text.get(start, end)
        self.text.delete(start, end)
        self.text.insert(start, replacement)
        self._reset_postprocess_undo()
        if remember and add_ru_dictionary_replacement(source, replacement):
            self._set_status(f"Запомнено: {source} -> {replacement}")
        self._schedule_spellcheck(delay_ms=150)

    def _add_dicta_known_word(self, tag_name: str) -> None:
        issue = self.spelling_issues.get(tag_name)
        if issue is None:
            return

        if add_ru_dictionary_known_word(issue.word):
            self._ignore_spelling_issue(tag_name)
            self._set_status(f"Добавлено в словарь Dicta: {issue.word}")
        else:
            self._set_status("Слово уже есть в словаре Dicta")

    def _add_selected_dicta_known_words(self) -> None:
        if not self._has_text_selection():
            return
        selected = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        words = re.findall(r"[A-Za-zА-Яа-яЁё]+", selected)
        added = add_ru_dictionary_known_words(words)
        if added:
            self._set_status(f"Добавлено в словарь Dicta: {added}")
            self._schedule_spellcheck(delay_ms=150)
        else:
            self._set_status("Нечего добавить в словарь Dicta")

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
        stop_argos_translation_worker()
        self.recognition_cancel_event.set()
        if self.protocol_prepare_queue is not None:
            try:
                self.protocol_prepare_queue.put(None)
            except Exception:
                pass
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
        self._close_recording_files()
        self._cleanup_recording_temp_files()
        self.root.destroy()

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.ui_queue.put(("status", f"Запись: {status}"))
        data = bytes(indata)
        self.audio_chunks.append(data)
        self._queue_input_level(data)

    def _system_audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.ui_queue.put(("status", f"Системный звук: {status}"))
        data = bytes(indata)
        chunk = None
        with self.recording_lock:
            if self.system_recording_wav is not None:
                try:
                    self.system_recording_wav.writeframes(data)
                except Exception:
                    pass
            self.protocol_system_chunk_parts.append(data)
            self.protocol_system_chunk_bytes += len(data)
            chunk = self._take_protocol_chunk_locked(final=False)
        self._queue_protocol_chunk(chunk)
        self.system_recording_peak = self._audio_peak_percent(data)
        self._queue_combined_input_level()

    def _microphone_recording_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.ui_queue.put(("status", f"Микрофон: {status}"))
        data = bytes(indata)
        chunk = None
        with self.recording_lock:
            if self.microphone_recording_wav is not None:
                try:
                    self.microphone_recording_wav.writeframes(data)
                except Exception:
                    pass
            self.protocol_microphone_chunk_parts.append(data)
            self.protocol_microphone_chunk_bytes += len(data)
            chunk = self._take_protocol_chunk_locked(final=False)
        self._queue_protocol_chunk(chunk)
        self.microphone_recording_peak = self._audio_peak_percent(data)
        self._queue_combined_input_level()

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

    def _queue_combined_input_level(self) -> None:
        now = time.perf_counter()
        if now - self.last_level_event_at < 0.08:
            return
        self.last_level_event_at = now
        self.ui_queue.put(("combined_input_level", (self.system_recording_peak, self.microphone_recording_peak)))

    def _set_input_level(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.input_level_var.set(value)
        self.input_level_text_var.set(f"Уровень: {value}%")

    def _set_combined_input_level(self, system_value: int, microphone_value: int) -> None:
        system_value = max(0, min(100, int(system_value)))
        microphone_value = max(0, min(100, int(microphone_value)))
        self.input_level_var.set(max(system_value, microphone_value))
        self.input_level_text_var.set(f"Уровень: система {system_value}%, микрофон {microphone_value}%")

    def _set_recognition_progress(self, value: object) -> None:
        try:
            percent = int(round(float(value)))
        except Exception:
            percent = 0
        percent = max(0, min(100, percent))
        self.recognition_progress_var.set(percent)
        self.recognition_progress_text_var.set(f"{percent}%")

    def _reset_recognition_progress(self) -> None:
        self.recognition_progress_has_real_update = False
        self._set_recognition_progress(0)

    def _recognition_progress_estimate(self) -> float:
        try:
            audio_seconds = sum(len(chunk) for chunk in self.audio_chunks) / (
                max(1, int(self.record_sample_rate or SAMPLE_RATE)) * SAMPLE_WIDTH_BYTES
            )
        except Exception:
            audio_seconds = 10.0

        model_factor = {
            "small-q5_1": 0.8,
            "small": 1.0,
            "medium-q5_0": 1.8,
            "medium": 2.4,
            "large-v3-turbo-q5_0": 2.8,
            "large-v3-turbo": 3.4,
        }.get(self._selected_model_key(), 1.0)
        backend_key = self._selected_backend_preference()
        if backend_key == "auto":
            backend_key = self._preferred_backend_name()
        backend_factor = {
            "vulkan": 0.7,
            "cuda": 0.7,
            "openvino": 0.9,
            "avx2": 1.0,
            "sse42": 1.7,
            "compat": 3.0,
        }.get(backend_key, 1.5)
        return max(60.0, min(300.0, 15.0 + audio_seconds * model_factor * backend_factor * 3.0))

    def _start_recognition_progress(self) -> None:
        self.recognition_progress_started_at = time.perf_counter()
        self.recognition_progress_estimate_seconds = self._recognition_progress_estimate()
        self.recognition_progress_has_real_update = False
        self._set_recognition_progress(0)
        self.root.after(300, self._tick_recognition_progress)

    def _tick_recognition_progress(self) -> None:
        if not self.is_recognizing:
            return
        if self.recognition_progress_has_real_update:
            self.root.after(500, self._tick_recognition_progress)
            return
        elapsed = max(0.0, time.perf_counter() - self.recognition_progress_started_at)
        estimate = max(1.0, self.recognition_progress_estimate_seconds)
        estimated_percent = int(
            round(RECOGNITION_FALLBACK_PROGRESS_MAX * (1.0 - math.exp(-elapsed / estimate)))
        )
        estimated_percent = min(RECOGNITION_FALLBACK_PROGRESS_MAX, estimated_percent)
        if estimated_percent > int(self.recognition_progress_var.get()):
            self._set_recognition_progress(estimated_percent)
        self.root.after(500, self._tick_recognition_progress)

    def _selected_model_path(self) -> Path:
        return MODEL_FILES.get(self._selected_model_key(), MODEL_OPTIONS[DEFAULT_MODEL_LABEL])

    def _recognize_pcm16_audio(
        self,
        raw_audio: bytes,
        sample_rate: int,
        recognition_mode_key: str,
        progress_callback: Callable[[int], None] | None = None,
    ) -> dict:
        wav_path: Path | None = None
        out_base: Path | None = None
        txt_path: Path | None = None
        started_at = time.perf_counter()

        try:
            if self.recognition_cancel_event.is_set():
                raise RecognitionCancelled()

            with tempfile.NamedTemporaryFile(prefix="dicta_", suffix=".wav", delete=False) as wav_file:
                wav_path = Path(wav_file.name)

            selected_model = self._selected_model_path()
            if not available_whisper_backends():
                expected = "\n".join(str(path) for path in WHISPER_BACKENDS.values())
                raise RuntimeError(f"missing-whisper-cli::{expected}")
            if not selected_model.exists():
                raise RuntimeError(f"missing-model::{selected_model}")

            recognition_language = recognition_mode_language(recognition_mode_key)
            sample_rate = int(sample_rate or SAMPLE_RATE)
            normalized_audio, audio_stats = apply_pcm16_gain(raw_audio, self.audio_gain_percent_var.get())
            audio_bytes, vad_stats = self._trim_silence(normalized_audio, sample_rate)
            audio_ms = len(audio_bytes) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000
            if audio_ms < MIN_AUDIO_MS:
                raise RuntimeError("silent-or-short-recording")
            if self.recognition_cancel_event.is_set():
                raise RecognitionCancelled()

            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav.setframerate(sample_rate)
                wav.writeframes(audio_bytes)
            if self.recognition_cancel_event.is_set():
                raise RecognitionCancelled()

            out_base = Path(tempfile.gettempdir()) / f"{wav_path.stem}_out"
            txt_path = out_base.with_suffix(".txt")
            if txt_path.exists():
                txt_path.unlink()

            backend_name, backend_threads, _completed = run_whisper_with_fallback(
                selected_model,
                wav_path,
                out_base,
                preferred_backend_key=self._selected_backend_preference(),
                language=recognition_language,
                translate_to_english=False,
                cancel_event=self.recognition_cancel_event,
                process_callback=self._set_recognition_process,
                progress_callback=progress_callback,
            )
            if self.recognition_cancel_event.is_set():
                raise RecognitionCancelled()

            elapsed = time.perf_counter() - started_at

            if not txt_path.exists():
                raise RuntimeError("missing-recognition-output")

            recognized = txt_path.read_text(encoding="utf-8").strip()
            return {
                "recognized": recognized,
                "elapsed": elapsed,
                "backend_name": backend_name,
                "backend_threads": backend_threads,
                "vad_stats": vad_stats,
                "audio_stats": audio_stats,
                "audio_bytes": audio_bytes,
                "sample_rate": sample_rate,
                "selected_model": selected_model,
                "recognition_mode_key": recognition_mode_key,
            }
        finally:
            self._set_recognition_process(None)
            for path in (wav_path, txt_path):
                if path and path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def _recognize_audio(self) -> None:
        started_at = time.perf_counter()

        try:
            if self.recognition_cancel_event.is_set():
                raise RecognitionCancelled()

            recognition_mode_key = self._selected_recognition_mode_key()
            sample_rate = self.record_sample_rate or SAMPLE_RATE
            raw_audio = b"".join(self.audio_chunks)

            def report_recognition_progress(percent: int) -> None:
                self.ui_queue.put(("recognition_progress", ("real", percent)))

            result = self._recognize_pcm16_audio(
                raw_audio,
                sample_rate,
                recognition_mode_key,
                progress_callback=report_recognition_progress,
            )
            recognized = result["recognized"]
            elapsed = float(result["elapsed"])
            backend_name = str(result["backend_name"])
            backend_threads = int(result["backend_threads"])
            vad_stats = result["vad_stats"]
            audio_stats = result["audio_stats"]
            audio_bytes = result["audio_bytes"]
            selected_model = result["selected_model"]
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
        except RecognitionCancelled:
            self.ui_queue.put(("recognition_cancelled", None))
        except Exception as exc:
            self.ui_queue.put(("error", self._format_recognition_error(exc)))
        finally:
            self._set_recognition_process(None)
            self.audio_chunks = []
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
            elif event == "combined_input_level":
                system_value, microphone_value = value
                self._set_combined_input_level(int(system_value), int(microphone_value))
            elif event == "recognition_progress":
                is_real_progress = False
                progress_value = value
                if isinstance(value, tuple) and len(value) >= 2:
                    is_real_progress = value[0] == "real"
                    progress_value = value[1]
                try:
                    progress_int = int(progress_value)
                except Exception:
                    progress_int = 0
                if is_real_progress:
                    self.recognition_progress_has_real_update = True
                self._set_recognition_progress(max(progress_int, int(self.recognition_progress_var.get())))
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
            elif event == "system_audio_test_result":
                self.finish_system_audio_test()
                self._handle_system_audio_test_result(value if isinstance(value, dict) else {})
            elif event == "system_audio_test_error":
                self.finish_system_audio_test()
                self._set_status("Ошибка системного звука")
                self.microphone_search_status_var.set("Системный звук: ошибка")
                messagebox.showerror("Dicta", str(value))
            elif event == "system_audio_test_ready":
                self.finish_system_audio_test()
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
                self.benchmark_button.configure(state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(state=tk.NORMAL)
                self._update_audio_source_controls_state()
            elif event == "hotkey":
                self._handle_record_hotkey()
            elif event == "hotkey_status":
                self.hotkey_status_var.set(str(value))
            elif event == "recognized":
                recognized, elapsed, backend_name, backend_threads, vad_stats, audio_stats, recognition_mode_key = value[:7]
                self._set_recognition_progress(100)
                self._set_text_spellcheck_language_from_mode(recognition_mode_key)
                prepared = prepare_recognized_text(
                    str(recognized),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=self.voice_punctuation_var.get()
                    and recognition_mode_key == RUSSIAN_RECOGNITION_MODE_KEY,
                )
                prepared_before_postprocess = prepared
                postprocess_corrections: tuple[RecognitionCorrection, ...] = ()
                if recognition_mode_key == RUSSIAN_RECOGNITION_MODE_KEY:
                    try:
                        postprocess_result = apply_ru_recognition_postprocess(prepared)
                        prepared = postprocess_result.text
                        postprocess_corrections = postprocess_result.corrections
                        log_ru_recognition_corrections(postprocess_corrections)
                    except Exception:
                        postprocess_corrections = ()
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self._set_format_action_label("Автоформат")
                self._reset_translation_undo()
                if postprocess_corrections:
                    self._set_postprocess_undo(prepared_before_postprocess, prepared, postprocess_corrections)
                else:
                    self._reset_postprocess_undo()
                self.recognition_time_var.set(f"{elapsed:.1f} с")
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
                if postprocess_corrections:
                    status = f"{status}; {ru_recognition_corrections_status(postprocess_corrections)}"
                self._set_status(status)
                self._start_translation_warmup_after_recognition(str(recognition_mode_key))
                self._schedule_spellcheck(delay_ms=100)
                self._update_translation_button_state()
            elif event == "protocol_chunk_recognized":
                chunk_index, result = value
                recognition_mode_key = str(result.get("recognition_mode_key", self._selected_recognition_mode_key()))
                self._set_text_spellcheck_language_from_mode(recognition_mode_key)
                prepared = prepare_recognized_text(
                    str(result.get("recognized", "")),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=self.voice_punctuation_var.get()
                    and recognition_mode_key == RUSSIAN_RECOGNITION_MODE_KEY,
                )
                if recognition_mode_key == RUSSIAN_RECOGNITION_MODE_KEY:
                    try:
                        prepared = apply_ru_recognition_postprocess(prepared).text
                    except Exception:
                        pass
                if prepared:
                    if not self.protocol_text_started:
                        self.text.delete("1.0", tk.END)
                        self.protocol_text_started = True
                        self.format_undo_snapshot = None
                        self._set_format_action_label("Автоформат")
                        self._reset_translation_undo()
                        self._reset_postprocess_undo()
                    current = self.text.get("1.0", "end-1c").strip()
                    insert_text = prepared if not current else "\n\n" + prepared
                    self.text.insert(tk.END, insert_text)
                    self.last_recognition_text = self.text.get("1.0", "end-1c").strip()
                    self.protocol_chunks_recognized += 1
                    self.recognition_time_var.set(f"{float(result.get('elapsed', 0.0)):.1f} с")
                    self._update_speed_status(
                        vad_stats=result.get("vad_stats"),
                        audio_stats=result.get("audio_stats"),
                        backend_name=str(result.get("backend_name", "")),
                        backend_threads=parse_positive_int(result.get("backend_threads")),
                    )
                    self._set_status(f"Протокол: фрагмент {int(chunk_index)} готов")
                    self._schedule_spellcheck(delay_ms=250)
                    self._update_translation_button_state()
            elif event == "protocol_recognition_error":
                self.recognition_cancel_event.set()
                self._set_status("Ошибка распознавания протокола")
                messagebox.showerror("Dicta", self._format_recognition_error(value))
            elif event == "protocol_recognition_done":
                if not self.is_protocol_recognizing and not self.is_recognizing:
                    continue
                cancelled = bool(value.get("cancelled")) if isinstance(value, dict) else False
                self.is_recognizing = False
                self.is_protocol_recognizing = False
                self._set_recognition_process(None)
                self._set_recognition_progress(0 if cancelled else 100)
                self.record_started_at = None
                self.record_time_var.set("Запись: 00:00")
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(state=tk.NORMAL)
                self._update_audio_source_controls_state()
                self._cleanup_recording_temp_files()
                if cancelled:
                    self._set_status("Распознавание протокола прервано")
                    self.recognition_time_var.set("-")
                else:
                    text_value = self.text.get("1.0", "end-1c").strip()
                    if self.auto_copy_var.get() and text_value:
                        self._copy_value_to_clipboard(text_value)
                        self._set_status("Протокол готов и скопирован")
                    else:
                        self._set_status("Протокол готов")
                    self._start_translation_warmup_after_recognition(self._selected_recognition_mode_key())
                    self._update_translation_button_state()
            elif event == "translation_to_ru_result":
                source, translated, translation_elapsed = value
                current = self.text.get("1.0", tk.END).strip()
                if current != str(source).strip():
                    self._set_status("Текст изменен, перевод не применен")
                    continue
                source_language_tag = self.current_text_spellcheck_language_tag
                prepared = prepare_recognized_text(
                    str(translated),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=False,
                )
                self.current_text_spellcheck_language_tag = "ru-RU"
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self._set_format_action_label("Автоформат")
                self._reset_postprocess_undo()
                self._set_translation_undo(current, prepared, source_language_tag, "ru-RU")
                if self.auto_copy_var.get() and prepared:
                    self._copy_value_to_clipboard(prepared)
                    status = f"Переведено и скопировано: {translation_elapsed:.1f} с"
                else:
                    status = f"Переведено: {translation_elapsed:.1f} с"
                self._set_status(status)
                self._schedule_spellcheck(delay_ms=100)
                self._update_translation_button_state()
            elif event == "translation_to_en_result":
                source, translated, translation_elapsed = value
                current = self.text.get("1.0", tk.END).strip()
                if current != str(source).strip():
                    self._set_status("Текст изменен, перевод не применен")
                    continue
                source_language_tag = self.current_text_spellcheck_language_tag
                prepared = prepare_recognized_text(
                    str(translated),
                    use_formatting=self.format_text_var.get(),
                    use_voice_punctuation=False,
                )
                self.current_text_spellcheck_language_tag = "en-US"
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", prepared)
                self.format_undo_snapshot = None
                self._set_format_action_label("Автоформат")
                self._reset_postprocess_undo()
                self._set_translation_undo(current, prepared, source_language_tag, "en-US")
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
                self._reset_recognition_progress()
                self._set_status("Ошибка распознавания")
                messagebox.showerror("Dicta", str(value))
            elif event == "recognition_cancelled":
                self._reset_recognition_progress()
                self._set_status("Распознавание прервано")
                self.recognition_time_var.set("-")
            elif event == "ready":
                self.is_recognizing = False
                self.worker = None
                self._set_recognition_process(None)
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.benchmark_button.configure(state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(state=tk.NORMAL)
                self._update_audio_source_controls_state()
            elif event == "benchmark_result":
                profile = value
                selected_model = profile.get("selected_model", FALLBACK_AUTO_MODEL_KEY)
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
                self._select_backend_key(selected_backend if selected_backend in BACKEND_LABELS else "auto")
                self._save_current_settings()
                self._update_speed_status()
                if profile.get("compat_auto_selected"):
                    self._set_status(f"AVX2/SSE4.2 не работают; выбран Compat, t={selected_threads}")
                else:
                    benchmark_model = profile.get("model", choose_backend_benchmark_model_key())
                    self._set_status(f"Движок выбран: {selected_backend}, t={selected_threads}; тест {benchmark_model}")
            elif event == "backend_benchmark_progress":
                message = str(value)
                self._set_status(f"Подбор движка: {message}")
                self.speed_status_var.set(f"Подбор движка: {message}")
            elif event == "backend_benchmark_compat_suggested":
                self._set_status("Подбор не завершился; Backend не изменен, Compat доступен вручную")
                self._update_speed_status()
            elif event == "benchmark_cancelled":
                self._set_status("Тест прерван")
                self.speed_status_var.set("Тест прерван")
            elif event == "benchmark_error":
                self._set_status("Ошибка бенчмарка")
                messagebox.showerror("Dicta", str(value))
            elif event == "benchmark_ready":
                self.is_benchmarking = False
                self.benchmark_cancel_event.clear()
                self._set_record_button_idle()
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
                self.benchmark_button.configure(text="Бенчмарк модели", command=self.start_model_benchmark, state=tk.NORMAL)
                self.backend_box.configure(state="readonly")
                self.backend_benchmark_button.configure(
                    text="Подобрать движок",
                    command=self.start_backend_benchmark,
                    state=tk.NORMAL,
                )
                self._update_audio_source_controls_state()
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

    def _format_system_audio_error(self, summary: str, exc: Exception) -> str:
        technical = str(exc).strip()
        return self._format_problem_message(
            summary,
            [
                "Проверьте, что звук встречи слышен в колонках или наушниках.",
                "Проверьте, что нужные колонки или наушники выбраны в Windows как устройство вывода по умолчанию.",
                "Проверьте громкость Teams, Zoom, браузера или другой программы встречи.",
                "Если звук идет в другое устройство, выберите его устройством вывода Windows по умолчанию и повторите запись.",
            ],
            details=f"Последний открытый режим: {input_stream_config_text(self.last_input_stream_config)}",
            technical=self._shorten_technical_text(technical),
        )

    def _format_combined_recording_error(self, summary: str, exc: Exception) -> str:
        technical = str(exc).strip()
        return self._format_problem_message(
            summary,
            [
                "Проверьте, что звук встречи слышен в колонках или наушниках.",
                "Проверьте, что выбранный микрофон работает.",
                "Если звук встречи идет в другое устройство, выберите его в строке Устройство вывода.",
                "Если микрофон занят другой программой, закройте эту программу или выберите другой микрофон.",
            ],
            details=f"Последний открытый режим: {input_stream_config_text(self.last_input_stream_config)}",
            technical=self._shorten_technical_text(technical),
        )

    def _format_recognition_error(self, exc: Exception) -> str:
        raw = str(exc).strip()

        if raw == "silent-or-short-recording":
            if self.last_recording_source_key == "combined":
                return self._format_problem_message(
                    "Запись слишком короткая или похожа на тишину системного звука и микрофона.",
                    [
                        "Начните воспроизведение встречи или видео до остановки записи.",
                        "Скажите несколько слов в выбранный микрофон.",
                        "Проверьте уровни: система и микрофон должны двигаться во время записи.",
                    ],
                )
            if self.last_recording_source_key == "system":
                return self._format_problem_message(
                    "Запись слишком короткая или похожа на тишину системного звука.",
                    [
                        "Начните воспроизведение встречи или видео до остановки записи.",
                        "Проверьте, что звук слышен в колонках или наушниках.",
                        "Проверьте, что нужное устройство вывода выбрано в Windows по умолчанию.",
                    ],
                )
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
                    "Скопируйте выбранную модель в папку models или выберите профиль Стандарт.",
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

    if "--dictionary-test" in sys.argv:
        run_ru_dictionary_self_test()
        print("Dicta dictionary-test passed.")
        raise SystemExit(0)

    if "--postprocess-test" in sys.argv:
        sample = "Я еду в Екатеринбурх."
        result = apply_ru_recognition_postprocess(sample)
        pelmeni = apply_ru_recognition_postprocess("Племень готов.")
        phrase = apply_ru_recognition_postprocess("Это общество с ограниченной ответственностью.")
        domain = apply_ru_recognition_postprocess("Сайт example точка ру работает.")
        known_dictionary = RuRecognitionDictionary(
            replacements={},
            protected_words=frozenset(),
            known_words=frozenset({"абвгд"}),
            blocked_pairs={},
            phrase_replacements={},
        )
        known_issue = SpellingIssue(start=0, length=5, word="абвгд", suggestions=("абвгде",))
        print(f"text={result.text}")
        print(f"corrections={[(item.source, item.replacement) for item in result.corrections]}")
        if "Екатеринбург" not in result.text:
            print("Dicta postprocess-test failed. Expected Екатеринбург.")
            raise SystemExit(1)
        if "Пельмень готов." not in pelmeni.text or "пламень" in pelmeni.text.casefold():
            print("Dicta postprocess-test failed. Expected племень -> пельмень.")
            raise SystemExit(1)
        if "Это ООО." not in phrase.text:
            print("Dicta postprocess-test failed. Expected phrase replacement.")
            raise SystemExit(1)
        if "example.ru" not in domain.text:
            print("Dicta postprocess-test failed. Expected phrase replacement for domain.")
            raise SystemExit(1)
        if choose_conservative_suggestion(known_issue, known_issue.word, known_dictionary) is not None:
            print("Dicta postprocess-test failed. known_words must block corrections.")
            raise SystemExit(1)
        print("Dicta postprocess-test passed.")
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
        required = [WHISPER_EXE] if allow_missing_models else [WHISPER_EXE, *required_model_paths()]
        missing = [path for path in required if not path.exists()]
        if missing:
            print("Dicta self-test failed. Missing files:")
            for path in missing:
                print(path)
            raise SystemExit(1)
        if allow_missing_models:
            missing_models = [path for path in required_model_paths() if not path.exists()]
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
