# VoiceHelper

Локальный прототип для диктовки в текст без облачных сервисов.

## Запуск

```powershell
python -m pip install -r requirements.txt
python voicehelper.py
```

После упаковки в exe:

```powershell
.\dist\VoiceHelper\VoiceHelper.exe
```

Повторная сборка exe:

```powershell
.\scripts\prepare_voicehelper_assets.ps1
.\scripts\build_voicehelper_exe.ps1
```

## GitHub Actions

После push в ветку `main` запускается workflow `.github/workflows/build-windows-exe.yml`.

Workflow:

- скачивает pinned `whisper.cpp` Windows x64 release для optional AVX2 backend;
- собирает scalar compat backend `whisper.cpp` из исходников без AVX/AVX2/FMA/F16C/SSE4.2/BMI2;
- не скачивает и не упаковывает модели `tiny/base/small q5_1`;
- собирает `VoiceHelper.exe` через PyInstaller;
- упаковывает `dist/VoiceHelper` в ZIP;
- публикует ZIP в GitHub Actions artifacts.

GitHub artifact является code-only пакетом. Перед использованием распознавания нужно вручную скопировать модели в папку `models` рядом с `VoiceHelper.exe`:

```text
models\ggml-tiny-q5_1.bin
models\ggml-base-q5_1.bin
models\ggml-small-q5_1.bin
```

## Что делает текущий MVP

- записывает звук с микрофона;
- распознает русский текст локально через `whisper.cpp`;
- показывает результат в большом текстовом поле;
- позволяет скопировать текст в буфер обмена;
- позволяет выбрать модель: `tiny-q5_1`, `base-q5_1`, `small-q5_1`;
- позволяет выбрать профиль скорости: `Авто`, `Быстро`, `Баланс`, `Точно`;
- может запустить локальный бенчмарк моделей и автоматически выбрать модель для профиля `Авто`;
- показывает таймер записи и время распознавания;
- показывает статус сетевой блокировки и позволяет запустить создание firewall-правила;
- обрезает тишину в начале и конце записи;
- использует простой локальный VAD для удаления длинной тишины перед распознаванием;
- удаляет временный WAV и промежуточный TXT после распознавания.
- использует локальную иконку приложения `assets/app_icon.ico`.

## Локальные зависимости

Ожидаемые файлы:

- `.tools/whisper.cpp-build-compat/bin/whisper-cli.exe` - scalar compat fallback
- `.tools/whisper.cpp-build-avx2/bin/whisper-cli.exe` - optional, если подготовлена AVX2-сборка
- `models/ggml-tiny-q5_1.bin`
- `models/ggml-base-q5_1.bin`
- `models/ggml-small-q5_1.bin`

Модели, `whisper-cli.exe`, собранные `dist/build` и архивы поставки не входят в git-репозиторий: это тяжелые локальные артефакты пилота.

## Ограничения

На текущем ПК распознавание работает, но скорость ограничена слабым CPU. Для первого теста используется модель `ggml-base-q5_1.bin`.

## Firewall

В exe-версии есть кнопки "Блокировать сеть" и "Разблокировать". Они создают или удаляют правило Windows Firewall для текущего `VoiceHelper.exe` через `netsh advfirewall` и вызывают стандартный UAC-запрос Windows. Результат пишется в `%TEMP%\voicehelper_firewall.log`.

Скрипт для ручного создания firewall-правила:

```powershell
.\scripts\add_voicehelper_firewall_block.ps1
```

На этапе Python-прототипа это правило блокирует сеть для `python.exe`. Для будущей собранной версии лучше передавать путь к `VoiceHelper.exe`.

## ИБ-проверка пилота

```powershell
.\scripts\check_voicehelper_security.ps1
```

Скрипт проверяет наличие локального движка, моделей, firewall-правил VoiceHelper и временных WAV/TXT-файлов в `%TEMP%`.

Для проверки exe-сборки:

```powershell
.\scripts\check_voicehelper_security.ps1 -Root ".\dist\VoiceHelper"
```

Для наблюдения сетевой активности запущенного приложения:

```powershell
.\scripts\audit_voicehelper_network.ps1 -ProgramPath ".\dist\VoiceHelper\VoiceHelper.exe" -Seconds 30
```

Для локального бенчмарка моделей:

```powershell
.\scripts\benchmark_voicehelper_models.ps1
```

## Документы пилота

- `pilot_user_instruction.tmp.md` - инструкция для руководителя.
- `pilot_feedback_log.tmp.md` - журнал обратной связи.
- `security_package_description.tmp.md` - состав поставки и пояснения для ИБ.
