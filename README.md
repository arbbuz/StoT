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

В поставке 1.0 дополнительно создаются:

```text
manifest.json
SHA256SUMS.txt
```

Проверка целостности code-only пакета:

```powershell
.\scripts\verify_voicehelper_package.ps1 -Root ".\dist\VoiceHelper"
```

## Что делает текущий MVP

- записывает звук с микрофона;
- распознает русский текст локально через `whisper.cpp`;
- показывает результат в большом текстовом поле;
- позволяет скопировать текст в буфер обмена;
- поддерживает горячую клавишу `Ctrl+Shift+Space` для "Записать/Стоп";
- может автоматически копировать текст после распознавания, если включена галочка "Автокопия";
- применяет базовое форматирование текста и голосовые команды пунктуации "точка", "запятая", "новый абзац";
- позволяет выбрать модель: `tiny-q5_1`, `base-q5_1`, `small-q5_1`;
- позволяет выбрать профиль скорости: `Авто`, `Быстро`, `Баланс`, `Точно`;
- позволяет выбрать backend: `Авто`, `Vulkan`, `CUDA`, `OpenVINO`, `AVX2`, `Compat`;
- может запустить локальный backend-бенчмарк и автоматически выбрать самый быстрый доступный `whisper.cpp` backend;
- может запустить локальный бенчмарк моделей и автоматически выбрать модель для профиля `Авто`;
- показывает таймер записи и время распознавания;
- держит верхнюю панель компактной: запись/стоп, копирование, автоформат, очистка, уровень микрофона и кнопка "Настройки";
- показывает контекстное меню в поле текста: вырезать, копировать, вставить, выделить всё; на подчеркнутом слове там же доступны варианты исправления орфографии;
- показывает статус сетевой блокировки и позволяет запустить создание firewall-правила;
- обрезает тишину в начале и конце записи;
- использует простой локальный VAD для удаления длинной тишины перед распознаванием;
- удаляет временный WAV и промежуточный TXT после распознавания.
- использует локальную иконку приложения `assets/app_icon.ico`.

## Локальные зависимости

Ожидаемые файлы:

- `.tools/whisper.cpp-build-compat/bin/whisper-cli.exe` - scalar compat fallback
- `.tools/whisper.cpp-build-avx2/bin/whisper-cli.exe` - optional, если подготовлена AVX2-сборка
- `.tools/whisper.cpp-build-vulkan/bin/whisper-cli.exe` - optional, если подготовлена Vulkan-сборка
- `.tools/whisper.cpp-build-cuda/bin/whisper-cli.exe` - optional, если подготовлена CUDA-сборка
- `.tools/whisper.cpp-build-openvino/bin/whisper-cli.exe` - optional, если подготовлена OpenVINO-сборка
- `models/ggml-tiny-q5_1.bin`
- `models/ggml-base-q5_1.bin`
- `models/ggml-small-q5_1.bin`

Модели, `whisper-cli.exe`, собранные `dist/build` и архивы поставки не входят в git-репозиторий: это тяжелые локальные артефакты пилота.

## Ограничения

На текущем ПК распознавание работает, но скорость ограничена слабым CPU. Для первого теста используется модель `ggml-base-q5_1.bin`.

## Firewall

В exe-версии в "Настройки" -> "Безопасность" есть кнопки "Блокировать сеть" и "Разблокировать". Они создают или удаляют правило Windows Firewall для текущего `VoiceHelper.exe` через `netsh advfirewall` и вызывают стандартный UAC-запрос Windows. Результат пишется в `%TEMP%\voicehelper_firewall.log`.

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

Для проверки manifest и SHA256:

```powershell
.\scripts\verify_voicehelper_package.ps1 -Root ".\dist\VoiceHelper"
```

Для наблюдения сетевой активности запущенного приложения:

```powershell
.\scripts\audit_voicehelper_network.ps1 -ProgramPath ".\dist\VoiceHelper\VoiceHelper.exe" -Seconds 30
```

Для локального бенчмарка моделей:

```powershell
.\scripts\benchmark_voicehelper_models.ps1
```

Для сравнения backend на текущем ПК:

```powershell
.\scripts\compare_voicehelper_backends.ps1
```

GPU backend и `faster-whisper` являются optional. Если рядом с приложением нет Vulkan/CUDA/OpenVINO-сборок `whisper-cli.exe`, VoiceHelper продолжит работать через AVX2 или Compat. `faster-whisper` не входит в обязательные зависимости и проверяется только при ручной подготовке локальной CTranslate2-модели.

## Удобство диктовки

- `Ctrl+Shift+Space` запускает запись, повторное нажатие останавливает ее.
- Галочка "Автокопия" в "Настройки" -> "Текст" копирует итоговый текст в буфер обмена после распознавания.
- Галочка "Форматировать" убирает двойные пробелы, делает первую букву заглавной, нормализует переносы строк и ставит точку в конце.
- Галочка "Команды пунктуации" заменяет слова "точка", "запятая", "новый абзац" на соответствующую пунктуацию.
- Кнопка "Автоформат" на основной панели применяет эти правила к тексту, который уже находится в окне; повторное нажатие возвращает прежний вариант.
- Правый клик в поле текста открывает меню вырезания, копирования, вставки и выделения всего текста; если кликнуть по подчеркнутому слову, сверху появляются варианты орфографического исправления.

Состояние галочек хранится в `%LOCALAPPDATA%\VoiceHelper\settings.json`. В этом файле нет аудио, распознанного текста или истории диктовок.

## Документы пилота

- `docs\USER_CHECKLIST.md` - короткая инструкция и чек-лист пользователя.
- `docs\IB_PACKAGE_DESCRIPTION.md` - состав поставки и пояснения для ИБ.
- `docs\UPDATE_PROCEDURE.md` - процедура обновления и отката.
- `docs\STAGE_1_0_CORPORATE_PILOT.md` - изменения версии 1.0.
