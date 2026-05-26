# Dicta: описание поставки для ИБ

Дата: 2026-05-22
Статус: пилотная локальная версия

## Назначение

Dicta - локальное Windows-приложение для диктовки текста голосом. Пользователь нажимает "Записать" или `Ctrl+Shift+Space`, диктует, нажимает ту же кнопку "Стоп" или повторно `Ctrl+Shift+Space`, получает текст в окне приложения и копирует его кнопкой "Скопировать" либо опциональной галочкой "Автокопия" в окне "Настройки".

Приложение не является почтовым клиентом, не отправляет письма, не создает черновики, не подключается к облачным сервисам распознавания речи и не выполняет интеграцию с Gmail, Outlook или другими почтовыми системами.

## Состав папки

```text
Dicta/
  Dicta.exe
  manifest.json
  SHA256SUMS.txt
  assets/
    app_icon.ico
    app_icon.png
  docs/
    IB_PACKAGE_DESCRIPTION.md
    PROGRAM_LOGIC.md
    ROADMAP.md
    STAGE_0_2_1_MICROPHONE.md
    STAGE_0_2_2_DIAGNOSTICS.md
    STAGE_0_2_3_ERROR_MESSAGES.md
    STAGE_0_3_SPEED.md
    STAGE_0_4_CONVENIENCE.md
    STAGE_0_5_PERFORMANCE.md
    STAGE_1_0_CORPORATE_PILOT.md
    STAGE_1_1_BACKEND_THREADS.md
    UPDATE_PROCEDURE.md
    USER_CHECKLIST.md
  scripts/
    diagnose_dicta.cmd
    diagnose_dicta.ps1
    verify_dicta_package.cmd
    verify_dicta_package.ps1
    generate_dicta_manifest.ps1
    benchmark_dicta_models.cmd
    benchmark_dicta_models.ps1
    compare_dicta_backends.cmd
    compare_dicta_backends.ps1
    check_firewall_block.cmd
    check_firewall_block.ps1
    check_russian_spellcheck.cmd
    check_russian_spellcheck.ps1
    check_dicta_security.cmd
    check_dicta_security.ps1
    list_audio_devices.cmd
    list_audio_devices.ps1
    audit_dicta_network.cmd
    audit_dicta_network.ps1
  _internal/
  models/
    README_MODELS.txt               code-only artifact
    ggml-small-q5_1.bin             copied manually before recognition
  .tools/
    whisper.cpp-build-compat/
      bin/
        whisper-cli.exe
    whisper.cpp-build-avx2/          optional
      bin/
        whisper-cli.exe
    whisper.cpp-build-vulkan/        optional
      bin/
        whisper-cli.exe
    whisper.cpp-build-cuda/          optional
      bin/
        whisper-cli.exe
    whisper.cpp-build-openvino/      optional
      bin/
        whisper-cli.exe
```

## Назначение компонентов

| Компонент | Назначение |
|---|---|
| `Dicta.exe` | Основное GUI-приложение. Записывает звук с микрофона, запускает локальный `whisper-cli.exe`, показывает распознанный текст. |
| `manifest.json` | Машинно-читаемый состав поставки: версия пакета, тип пакета, дата генерации, исходный commit и список файлов с SHA256. |
| `SHA256SUMS.txt` | Контрольные SHA256-суммы файлов code-only поставки. Используется скриптом `verify_dicta_package.ps1`. |
| `_internal/` | Runtime PyInstaller: Python, Tkinter, sounddevice, CFFI и служебные DLL. Нужен для запуска без установки Python на ПК. |
| `models/ggml-small-q5_1.bin` | Рабочая локальная модель Whisper в формате ggml. Это веса модели, не пользовательские данные и не журналы. В GitHub Actions code-only artifact не входит и копируется вручную рядом с `Dicta.exe`. |
| `.tools/whisper.cpp-build-compat/bin/whisper-cli.exe` | Локальный scalar compat backend whisper.cpp без AVX/AVX2/FMA/F16C/SSE4.2/BMI2. Работает как fallback на старых CPU. |
| `.tools/whisper.cpp-build-avx2/bin/whisper-cli.exe` | Optional optimized backend whisper.cpp для современных CPU. Если не запускается, приложение использует compat backend. |
| `.tools/whisper.cpp-build-vulkan/bin/whisper-cli.exe` | Optional GPU backend whisper.cpp для проверки Vulkan на реальных ПК. |
| `.tools/whisper.cpp-build-cuda/bin/whisper-cli.exe` | Optional GPU backend whisper.cpp для проверки NVIDIA CUDA на реальных ПК. |
| `.tools/whisper.cpp-build-openvino/bin/whisper-cli.exe` | Optional backend whisper.cpp для проверки OpenVINO на реальных ПК. |
| `assets/` | Иконка приложения. На функциональность и обработку данных не влияет. |
| `docs/` | Документация для ИБ и пользователя. |
| `scripts/diagnose_dicta.ps1` | Единая диагностика: состав поставки, хэши, self-test, аудиоустройства, орфография, firewall, временные файлы, сетевой аудит. |
| `scripts/diagnose_dicta.cmd` | Запуск единой диагностики двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/verify_dicta_package.ps1` | Проверяет `manifest.json` и SHA256-суммы файлов поставки без запуска GUI. |
| `scripts/verify_dicta_package.cmd` | Запуск проверки целостности двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/generate_dicta_manifest.ps1` | Создает `manifest.json` и `SHA256SUMS.txt` во время сборки поставки. |
| `scripts/benchmark_dicta_models.ps1` | Локальная проверка скорости рабочей модели `small-q5_1`. |
| `scripts/benchmark_dicta_models.cmd` | Запуск бенчмарка двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/compare_dicta_backends.ps1` | Локальное сравнение backend/thread-кандидатов `whisper.cpp`; если вручную подготовлен `faster-whisper`, показывает его как experimental result. |
| `scripts/compare_dicta_backends.cmd` | Запуск сравнения backend двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/check_firewall_block.ps1` | Проверяет наличие outbound block firewall-правила для конкретного `Dicta.exe`. |
| `scripts/check_firewall_block.cmd` | Запуск проверки firewall двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/check_russian_spellcheck.ps1` | Проверяет доступность русского локального Windows Spell Checking API для `Dicta.exe`. |
| `scripts/check_russian_spellcheck.cmd` | Запуск проверки русского словаря двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/check_dicta_security.ps1` | Проверяет наличие локальных файлов, рабочей модели, правила firewall и временных хвостов в `%TEMP%`. |
| `scripts/check_dicta_security.cmd` | Запуск общей проверки двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/list_audio_devices.ps1` | Выводит список устройств записи, которые видит Dicta через sounddevice/PortAudio. |
| `scripts/list_audio_devices.cmd` | Запуск списка аудиоустройств двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/audit_dicta_network.ps1` | Наблюдает TCP-подключения процесса Dicta в течение заданного времени. |
| `scripts/audit_dicta_network.cmd` | Запуск сетевого аудита двойным кликом; окно остается открытым до нажатия клавиши. |

## Чем создано

- Python 3.14.4 - код GUI и управляющая логика.
- Tkinter - стандартный GUI toolkit Python.
- sounddevice 0.5.5 - доступ к микрофону.
- comtypes 1.4.16 - локальный вызов Windows COM API для проверки орфографии.
- Windows Spell Checking API - штатный локальный механизм проверки орфографии Windows.
- whisper.cpp - локальный speech-to-text движок.
- PyInstaller 6.20.0 - упаковка Python-приложения в Windows EXE с папкой runtime.
- Pillow - подготовка PNG/ICO иконки.
- CMake/GCC - сборка совместимого `whisper-cli.exe`.

## Работа с данными

Обрабатываются только:

- звук с микрофона во время активной записи;
- временный WAV-файл в `%TEMP%`;
- временный TXT-файл результата в `%TEMP%`;
- текст в окне приложения;
- текст, переданный локальному Windows Spell Checking API для проверки орфографии;
- слово, добавленное пользователем в локальный пользовательский словарь Windows через пункт "Добавить в словарь";
- текст в буфере обмена после нажатия "Скопировать" или после включенной опции "Автокопия";
- технический файл `%LOCALAPPDATA%\Dicta\performance_profile.json` с результатами локального бенчмарка рабочей модели.
- технический файл `%LOCALAPPDATA%\Dicta\backend_profile.json` с результатами локального бенчмарка backend и числа потоков.
- технический файл `%LOCALAPPDATA%\Dicta\settings.json` с настройками галочек интерфейса.

Не обрабатываются целенаправленно:

- почта;
- адресная книга;
- файлы пользователя;
- браузерные cookies;
- учетные данные;
- сетевые ресурсы;
- документы вне ручного копирования пользователем или включенного пользователем автокопирования.

В штатном сценарии временные WAV/TXT-файлы удаляются после распознавания. Если процесс аварийно завершен во время распознавания, в `%TEMP%` теоретически могут остаться файлы вида `dicta_*.wav` или `dicta_*_out.txt`; это проверяется скриптом `scripts/check_dicta_security.ps1`.

Файлы `performance_profile.json`, `backend_profile.json` и `settings.json` не содержат аудио, текста диктовок или истории распознаваний. В `performance_profile.json` хранится только время локального benchmark-запуска рабочей модели. В `backend_profile.json` хранятся только времена локального backend/thread-бенчмарка, выбранный backend и выбранное число потоков для режима "Авто". В `settings.json` хранятся только значения галочек "Автокопия", "Форматировать", "Команды пунктуации" и выбранный backend.

## Сеть и firewall

По функциональной логике приложение не использует облачные API и не делает сетевые запросы для распознавания или проверки орфографии. Распознавание выполняется локально: `Dicta.exe` вызывает локальный `whisper-cli.exe`, который использует рабочую модель из папки `models`. Проверка орфографии выполняется локально через Windows Spell Checking API.

Для дополнительного контроля в интерфейсе, во вкладке "Настройки" -> "Безопасность", есть кнопки:

- "Блокировать сеть" - создает Windows Firewall outbound block rule для текущего `Dicta.exe`;
- "Разблокировать" - удаляет это правило;
- индикатор "Сеть" - показывает наличие правила для текущего пути к EXE.

Firewall-правило привязано к конкретному пути `Dicta.exe`. Если папку приложения перенесли или переименовали, правило нужно создать заново из нового расположения.

## Проверки для ИБ

Из корня распакованной папки `Dicta`:

Запуск двойным кликом из Проводника:

```text
scripts\diagnose_dicta.cmd
scripts\verify_dicta_package.cmd
scripts\check_firewall_block.cmd
scripts\check_russian_spellcheck.cmd
scripts\check_dicta_security.cmd
scripts\audit_dicta_network.cmd
```

Запуск из PowerShell:

```powershell
.\scripts\diagnose_dicta.ps1 -Root "."
.\scripts\verify_dicta_package.ps1 -Root "."
.\scripts\check_firewall_block.ps1
.\scripts\check_russian_spellcheck.ps1
.\scripts\check_dicta_security.ps1 -Root "."
.\scripts\audit_dicta_network.ps1 -ProgramPath ".\Dicta.exe" -Seconds 30
```

`check_firewall_block.ps1` должен вернуть `[OK] Outbound firewall block is enabled for this exact Dicta.exe.` после нажатия "Блокировать сеть" в приложении и подтверждения UAC.

`diagnose_dicta.ps1` сохраняет полный отчет в `diagnostics\dicta_diagnostic_YYYYMMDD_HHMMSS.txt`. Отчет можно передать ИБ или разработчику без скриншотов окна.

`verify_dicta_package.ps1` проверяет хэши code-only файлов из `SHA256SUMS.txt`. Если после проверки в `models` вручную добавлены `.bin` модели, скрипт может показать предупреждение о дополнительных файлах; это не означает изменение code-only артефакта.

## Важные ограничения

- Пилотная сборка не подписана кодовой подписью организации.
- Для создания/удаления firewall-правила Windows запрашивает права администратора через UAC.
- PyInstaller-сборки могут вызывать вопросы у антивируса/EDR из-за упакованного runtime. Это не признак вредоносности само по себе, но для промышленного внедрения желательно провести проверку средствами организации и подписать EXE.
