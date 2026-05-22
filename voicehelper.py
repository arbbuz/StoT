import queue
import ctypes
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
WHISPER_EXE = APP_DIR / ".tools" / "whisper.cpp-build-compat" / "bin" / "whisper-cli.exe"
MODELS_DIR = APP_DIR / "models"
MODEL_OPTIONS = {
    "tiny-q5_1: быстрее, менее точно": MODELS_DIR / "ggml-tiny-q5_1.bin",
    "base-q5_1: рекомендовано": MODELS_DIR / "ggml-base-q5_1.bin",
    "small-q5_1: точнее, медленно": MODELS_DIR / "ggml-small-q5_1.bin",
}
DEFAULT_MODEL_LABEL = "base-q5_1: рекомендовано"
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
SILENCE_WINDOW_MS = 30
SILENCE_PADDING_MS = 250
SILENCE_PEAK_THRESHOLD = 350
MIN_AUDIO_MS = 600
FIREWALL_RULE_NAME = "VoiceHelper Block Outbound"


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
        self.model_var = tk.StringVar(value=DEFAULT_MODEL_LABEL)
        self.input_device_var = tk.StringVar(value="")
        self.input_level_var = tk.DoubleVar(value=0)
        self.input_level_text_var = tk.StringVar(value="Уровень: -")
        self.spellcheck_status_var = tk.StringVar(value="Орфография: авто")

        self._build_ui()
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
        if not WHISPER_EXE.exists():
            missing.append(str(WHISPER_EXE))
        for model_path in MODEL_OPTIONS.values():
            if not model_path.exists():
                missing.append(str(model_path))

        if missing:
            self._set_status("Не найдены локальные файлы")
            messagebox.showerror(
                "VoiceHelper",
                "Не найдены обязательные локальные файлы:\n\n" + "\n".join(missing),
            )
            self.record_button.configure(state=tk.DISABLED)

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
            self._set_status(f"Ошибка микрофона: {exc}")
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
        raise RuntimeError("Не найден доступный микрофон. Проверьте подключение микрофона и нажмите \"Обновить\".")

    def _input_device_default_sample_rate(self, device_index: int) -> int:
        try:
            device = sd.query_devices(device_index, "input")
            return int(float(device.get("default_samplerate", SAMPLE_RATE)))
        except Exception:
            return SAMPLE_RATE

    def start_microphone_test(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone:
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
                "Не удалось проверить микрофон.\n\n"
                f"Выбранный микрофон:\n{self.input_device_var.get() or 'не выбран'}\n\n"
                f"Ошибка:\n{exc}\n\n"
                "Проверьте, что микрофон подключен, выбран в списке и не занят другой программой. "
                "После подключения нажмите \"Обновить\".",
            )
            return

        self.is_testing_microphone = True
        self._set_status("Проверка микрофона: говорите 3 секунды")
        self.record_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self.model_box.configure(state=tk.DISABLED)
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
                "Микрофон удалось открыть, но заметного звука за 3 секунды не обнаружено.\n\n"
                "Проверьте выбранное устройство, уровень входа в Windows и физическую кнопку mute, если она есть.",
            )

    def start_recording(self) -> None:
        if self.is_recording or self.is_recognizing or self.is_testing_microphone:
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
                "Не удалось начать запись.\n\n"
                f"Выбранный микрофон:\n{self.input_device_var.get() or 'не выбран'}\n\n"
                f"Ошибка:\n{exc}\n\n"
                "Проверьте, что микрофон подключен, выбран в списке и не занят другой программой. "
                "После подключения нажмите \"Обновить\".",
            )
            return

        self.is_recording = True
        self.record_started_at = time.perf_counter()
        self._set_status("Запись")
        self.record_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.model_box.configure(state=tk.DISABLED)
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
            self.input_device_box.configure(state="readonly")
            self.refresh_input_button.configure(state=tk.NORMAL)
            self.test_input_button.configure(state=tk.NORMAL)
            messagebox.showwarning("VoiceHelper", "Запись пустая.")
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
            messagebox.showerror("VoiceHelper", f"Не найден файл для блокировки сети:\n\n{target}")
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
            messagebox.showerror("VoiceHelper", f"Не удалось запустить настройку firewall:\n\n{exc}")
            return

        self.firewall_status_var.set("Сеть: ожидает подтверждения Windows")
        self.root.after(5000, self.refresh_firewall_status)

    def disable_firewall_block(self) -> None:
        target = self._firewall_target_path()
        if not target.exists():
            messagebox.showerror("VoiceHelper", f"Не найден файл для разблокировки сети:\n\n{target}")
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
            messagebox.showerror("VoiceHelper", f"Не удалось запустить снятие firewall-правила:\n\n{exc}")
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
        return MODEL_OPTIONS.get(self.model_var.get(), MODEL_OPTIONS[DEFAULT_MODEL_LABEL])

    def _recognize_audio(self) -> None:
        wav_path: Path | None = None
        out_base: Path | None = None
        txt_path: Path | None = None
        started_at = time.perf_counter()

        try:
            with tempfile.NamedTemporaryFile(prefix="voicehelper_", suffix=".wav", delete=False) as wav_file:
                wav_path = Path(wav_file.name)

            sample_rate = self.record_sample_rate or SAMPLE_RATE
            audio_bytes = self._trim_silence(b"".join(self.audio_chunks), sample_rate)
            audio_ms = len(audio_bytes) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000
            if audio_ms < MIN_AUDIO_MS:
                raise RuntimeError("Запись слишком короткая или похожа на тишину.")

            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav.setframerate(sample_rate)
                wav.writeframes(audio_bytes)

            out_base = Path(tempfile.gettempdir()) / f"{wav_path.stem}_out"
            txt_path = out_base.with_suffix(".txt")
            if txt_path.exists():
                txt_path.unlink()

            command = [
                str(WHISPER_EXE),
                "-m",
                str(self._selected_model_path()),
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

            completed = subprocess.run(
                command,
                cwd=str(APP_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )

            elapsed = time.perf_counter() - started_at

            if completed.returncode != 0:
                error_text = completed.stderr.decode("utf-8", errors="replace").strip()
                if not error_text:
                    error_text = completed.stdout.decode("utf-8", errors="replace").strip()
                raise RuntimeError(error_text or f"whisper-cli завершился с кодом {completed.returncode}")

            if not txt_path.exists():
                raise RuntimeError("whisper-cli не создал TXT-файл с результатом.")

            recognized = txt_path.read_text(encoding="utf-8").strip()
            self.ui_queue.put(("recognized", (recognized, elapsed)))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))
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
                recognized, elapsed = value
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", str(recognized))
                self.recognition_time_var.set(f"Распознавание: {elapsed:.1f} с")
                self._set_status("Готово")
                self._schedule_spellcheck(delay_ms=100)
            elif event == "error":
                self._set_status("Ошибка распознавания")
                messagebox.showerror("VoiceHelper", f"Не удалось распознать запись:\n\n{value}")
            elif event == "ready":
                self.is_recognizing = False
                self.record_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                self.model_box.configure(state="readonly")
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

    def _trim_silence(self, audio: bytes, sample_rate: int) -> bytes:
        if not audio:
            return audio

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

    if "--self-test" in sys.argv:
        missing = [path for path in [WHISPER_EXE, *MODEL_OPTIONS.values()] if not path.exists()]
        if missing:
            print("VoiceHelper self-test failed. Missing files:")
            for path in missing:
                print(path)
            raise SystemExit(1)
        print("VoiceHelper self-test passed.")
        print(f"APP_DIR={APP_DIR}")
        print(f"APP_ICON={APP_ICON}")
        print(f"WHISPER_EXE={WHISPER_EXE}")
        raise SystemExit(0)

    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    VoiceHelperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
