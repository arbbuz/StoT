# VoiceHelper: описание поставки для ИБ

Дата: 2026-05-22
Статус: пилотная локальная версия

## Назначение

VoiceHelper - локальное Windows-приложение для диктовки текста голосом. Пользователь нажимает "Записать", диктует, нажимает "Стоп", получает текст в окне приложения и вручную копирует его кнопкой "Скопировать".

Приложение не является почтовым клиентом, не отправляет письма, не создает черновики, не подключается к облачным сервисам распознавания речи и не выполняет интеграцию с Gmail, Outlook или другими почтовыми системами.

## Состав папки

```text
VoiceHelper/
  VoiceHelper.exe
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
    USER_CHECKLIST.md
  scripts/
    diagnose_voicehelper.cmd
    diagnose_voicehelper.ps1
    benchmark_voicehelper_models.cmd
    benchmark_voicehelper_models.ps1
    check_firewall_block.cmd
    check_firewall_block.ps1
    check_russian_spellcheck.cmd
    check_russian_spellcheck.ps1
    check_voicehelper_security.cmd
    check_voicehelper_security.ps1
    list_audio_devices.cmd
    list_audio_devices.ps1
    audit_voicehelper_network.cmd
    audit_voicehelper_network.ps1
  _internal/
  models/
    ggml-tiny-q5_1.bin
    ggml-base-q5_1.bin
    ggml-small-q5_1.bin
  .tools/
    whisper.cpp-build-compat/
      bin/
        whisper-cli.exe
    whisper.cpp-build-avx2/          optional
      bin/
        whisper-cli.exe
```

## Назначение компонентов

| Компонент | Назначение |
|---|---|
| `VoiceHelper.exe` | Основное GUI-приложение. Записывает звук с микрофона, запускает локальный `whisper-cli.exe`, показывает распознанный текст. |
| `_internal/` | Runtime PyInstaller: Python, Tkinter, sounddevice, CFFI и служебные DLL. Нужен для запуска без установки Python на ПК. |
| `models/*.bin` | Локальные модели Whisper в формате ggml. Это веса модели, не пользовательские данные и не журналы. |
| `.tools/whisper.cpp-build-compat/bin/whisper-cli.exe` | Локальный scalar compat backend whisper.cpp без AVX/AVX2/FMA/F16C/SSE4.2/BMI2. Работает как fallback на старых CPU. |
| `.tools/whisper.cpp-build-avx2/bin/whisper-cli.exe` | Optional optimized backend whisper.cpp для современных CPU. Если не запускается, приложение использует compat backend. |
| `assets/` | Иконка приложения. На функциональность и обработку данных не влияет. |
| `docs/` | Документация для ИБ и пользователя. |
| `scripts/diagnose_voicehelper.ps1` | Единая диагностика: состав поставки, хэши, self-test, аудиоустройства, орфография, firewall, временные файлы, сетевой аудит. |
| `scripts/diagnose_voicehelper.cmd` | Запуск единой диагностики двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/benchmark_voicehelper_models.ps1` | Локальный бенчмарк моделей для выбора профиля скорости. |
| `scripts/benchmark_voicehelper_models.cmd` | Запуск бенчмарка двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/check_firewall_block.ps1` | Проверяет наличие outbound block firewall-правила для конкретного `VoiceHelper.exe`. |
| `scripts/check_firewall_block.cmd` | Запуск проверки firewall двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/check_russian_spellcheck.ps1` | Проверяет доступность русского локального Windows Spell Checking API для `VoiceHelper.exe`. |
| `scripts/check_russian_spellcheck.cmd` | Запуск проверки русского словаря двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/check_voicehelper_security.ps1` | Проверяет наличие локальных файлов, моделей, правила firewall и временных хвостов в `%TEMP%`. |
| `scripts/check_voicehelper_security.cmd` | Запуск общей проверки двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/list_audio_devices.ps1` | Выводит список устройств записи, которые видит VoiceHelper через sounddevice/PortAudio. |
| `scripts/list_audio_devices.cmd` | Запуск списка аудиоустройств двойным кликом; окно остается открытым до нажатия клавиши. |
| `scripts/audit_voicehelper_network.ps1` | Наблюдает TCP-подключения процесса VoiceHelper в течение заданного времени. |
| `scripts/audit_voicehelper_network.cmd` | Запуск сетевого аудита двойным кликом; окно остается открытым до нажатия клавиши. |

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
- текст в буфере обмена после нажатия "Скопировать".
- технический файл `%LOCALAPPDATA%\VoiceHelper\performance_profile.json` с результатами локального бенчмарка моделей.

Не обрабатываются целенаправленно:

- почта;
- адресная книга;
- файлы пользователя;
- браузерные cookies;
- учетные данные;
- сетевые ресурсы;
- документы вне ручного копирования пользователем.

В штатном сценарии временные WAV/TXT-файлы удаляются после распознавания. Если процесс аварийно завершен во время распознавания, в `%TEMP%` теоретически могут остаться файлы вида `voicehelper_*.wav` или `voicehelper_*_out.txt`; это проверяется скриптом `scripts/check_voicehelper_security.ps1`.

Файл `performance_profile.json` не содержит аудио, текста диктовок или истории распознаваний. В нем хранятся только время локального benchmark-запуска по моделям и выбранная модель для профиля "Авто".

## Сеть и firewall

По функциональной логике приложение не использует облачные API и не делает сетевые запросы для распознавания или проверки орфографии. Распознавание выполняется локально: `VoiceHelper.exe` вызывает локальный `whisper-cli.exe`, который использует локальные модели из папки `models`. Проверка орфографии выполняется локально через Windows Spell Checking API.

Для дополнительного контроля в интерфейсе есть кнопки:

- "Блокировать сеть" - создает Windows Firewall outbound block rule для текущего `VoiceHelper.exe`;
- "Разблокировать" - удаляет это правило;
- индикатор "Сеть" - показывает наличие правила для текущего пути к EXE.

Firewall-правило привязано к конкретному пути `VoiceHelper.exe`. Если папку приложения перенесли или переименовали, правило нужно создать заново из нового расположения.

## Проверки для ИБ

Из корня распакованной папки `VoiceHelper`:

Запуск двойным кликом из Проводника:

```text
scripts\diagnose_voicehelper.cmd
scripts\check_firewall_block.cmd
scripts\check_russian_spellcheck.cmd
scripts\check_voicehelper_security.cmd
scripts\audit_voicehelper_network.cmd
```

Запуск из PowerShell:

```powershell
.\scripts\diagnose_voicehelper.ps1 -Root "."
.\scripts\check_firewall_block.ps1
.\scripts\check_russian_spellcheck.ps1
.\scripts\check_voicehelper_security.ps1 -Root "."
.\scripts\audit_voicehelper_network.ps1 -ProgramPath ".\VoiceHelper.exe" -Seconds 30
```

`check_firewall_block.ps1` должен вернуть `[OK] Outbound firewall block is enabled for this exact VoiceHelper.exe.` после нажатия "Блокировать сеть" в приложении и подтверждения UAC.

`diagnose_voicehelper.ps1` сохраняет полный отчет в `diagnostics\voicehelper_diagnostic_YYYYMMDD_HHMMSS.txt`. Отчет можно передать ИБ или разработчику без скриншотов окна.

## Важные ограничения

- Пилотная сборка не подписана кодовой подписью организации.
- Для создания/удаления firewall-правила Windows запрашивает права администратора через UAC.
- PyInstaller-сборки могут вызывать вопросы у антивируса/EDR из-за упакованного runtime. Это не признак вредоносности само по себе, но для промышленного внедрения желательно провести проверку средствами организации и подписать EXE.
