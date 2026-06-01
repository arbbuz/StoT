# Dicta

Локальный прототип для диктовки в текст без облачных сервисов.

## Запуск

```powershell
python -m pip install -r requirements.txt
python dicta.py
```

После упаковки в exe:

```powershell
.\dist\Dicta\Dicta.exe
```

Повторная сборка exe:

```powershell
.\scripts\prepare_dicta_assets.ps1
.\scripts\build_dicta_exe.ps1
```

Чтобы локально скачать и упаковать дополнительную модель `ggml-small.bin` для профиля "Качество":

```powershell
.\scripts\prepare_dicta_assets.ps1 -IncludeQualityModels
.\scripts\build_dicta_exe.ps1
```

## GitHub Actions

После push в ветку `main` запускается workflow `.github/workflows/build-windows-exe.yml`.

Workflow:

- скачивает pinned `whisper.cpp` Windows x64 release для optional AVX2 backend;
- собирает scalar compat backend `whisper.cpp` из исходников без AVX/AVX2/FMA/F16C/SSE4.2/BMI2;
- не скачивает и не упаковывает модель `small q5_1`;
- собирает `Dicta.exe` через PyInstaller;
- упаковывает `dist/Dicta` в ZIP;
- публикует ZIP в GitHub Actions artifacts.

GitHub artifact является code-only пакетом. Перед использованием распознавания нужно вручную скопировать рабочую модель в папку `models` рядом с `Dicta.exe`:

```text
models\ggml-small-q5_1.bin
```

Для повышения качества распознавания можно дополнительно положить в `models` более тяжелую модель. Dicta покажет ее в "Настройки" -> "Производительность" и позволит выбрать профиль "Качество":

```text
models\ggml-small.bin
models\ggml-medium-q5_0.bin
models\ggml-medium.bin
models\ggml-large-v3-turbo-q5_0.bin
models\ggml-large-v3-turbo.bin
```

Опциональный локальный перевод EN<->RU включается только при наличии отдельного translation pack рядом с `Dicta.exe`. Основной code-only пакет не включает Argos runtime и модели перевода.

Translation pack полностью portable: он не требует установленный Python на целевом ПК. Argos запускается через постоянный `argos-worker.exe`, поэтому первый перевод может включать холодную загрузку runtime/модели, а следующие переводы идут через уже запущенный worker.

```text
.tools\argos-translate\
  argos-worker\argos-worker.exe
  argos-worker\_internal\...
  packages\translate-en_ru-1_9\
  packages\translate-ru_en-1_9\
translation\glossary_en_ru.json
scripts\argos_translate_worker.py
```

В настройках Dicta показывает статус runtime, моделей EN->RU/RU->EN и glossary. Перевод выполняется вручную:

- `В русский` переводит текущий английский текст через optional Argos pack.
- `В English` переводит текущий русский текст через optional Argos pack.

Список режимов отвечает только за язык распознавания: `Русский текст` или `English text`.

Локально pack можно подготовить из Argos spike:

```powershell
.\scripts\prepare_argos_translation_pack.ps1
```

Проверка полного пути перевода:

```powershell
python dicta.py --translation-test
```

## Русская постобработка распознавания

После режима `Русский текст` Dicta запускает консервативную ru-RU постобработку через Windows Spell Checking API и `dicta_dictionary_ru.json`. Автозамена применяется только к длинным русским словам с единственным уверенным вариантом исправления или к точечным заменам из словаря: например, `Екатеринбурх -> Екатеринбург`.

Корректор не трогает числа, email, URL, слова с латиницей, аббревиатуры, короткие слова и слова с дефисом. Неоднозначные варианты Windows suggestions не применяются автоматически. В нижнем статусе показывается только счетчик `Исправлено: N`, а пары исправлений пишутся в `%LOCALAPPDATA%\Dicta\postprocess_corrections.log`; полный распознанный текст в лог не сохраняется. Последнюю автокоррекцию можно откатить кнопкой `Откатить`.

Формат `dicta_dictionary_ru.json` поддерживает `phrase_replacements`, `known_words`, `protected_words`, `replacements` и `blocked_pairs`. Порядок применения: фразовые замены, проверка Windows Spell Checking API, защита `known_words`, защита `protected_words`, точечные `replacements`, запрет `blocked_pairs`, затем единственный уверенный Windows suggestion.

Пользовательское наполнение словаря выполняется из поля текста. На подчеркнутом слове контекстное меню позволяет выбрать `Исправить и запомнить`, `Считать словом Dicta` или `Добавить в словарь Windows`. Если автокоррекция ошиблась, кнопка `Откатить` возвращает исходный текст и записывает отклоненную пару в словарь, чтобы такая автозамена не повторялась. Выделенный текст можно добавить в `known_words` через пункт `Добавить выделенное в словарь Dicta`.

В поставке 1.1 дополнительно создаются:

```text
manifest.json
SHA256SUMS.txt
```

Проверка целостности code-only пакета:

```powershell
.\scripts\verify_dicta_package.ps1 -Root ".\dist\Dicta"
```

## Что делает текущий MVP

- записывает звук с микрофона;
- распознает русский текст локально через `whisper.cpp`;
- показывает результат в большом текстовом поле;
- позволяет скопировать текст в буфер обмена;
- поддерживает горячую клавишу `Ctrl+Shift+Space` для "Записать/Стоп";
- может автоматически копировать текст после распознавания, если включена галочка "Автокопия";
- применяет базовое форматирование текста и голосовые команды пунктуации: "точка", "запятая", "двоеточие", "точка с запятой", "многоточие", "вопросительный знак", "восклицательный знак", "кавычки", "кавычки открываются", "кавычки закрываются", "скобка открывается", "скобка закрывается", "тире", "новая строка", "новый абзац";
- консервативно исправляет уверенные ru-RU опечатки распознавания через Windows Spell Checking API;
- использует единую рабочую модель `small-q5_1`;
- позволяет выбрать backend: `Авто`, `Vulkan`, `CUDA`, `OpenVINO`, `AVX2`, `Compat`;
- может запустить локальный backend-бенчмарк и автоматически выбрать самую быструю пару `whisper.cpp` backend + `-t`;
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
- `.tools/whisper.cpp-build-sse42/bin/whisper-cli.exe` - optional CPU fallback без AVX2
- `.tools/whisper.cpp-build-vulkan/bin/whisper-cli.exe` - optional, если подготовлена Vulkan-сборка
- `.tools/whisper.cpp-build-cuda/bin/whisper-cli.exe` - optional, если подготовлена CUDA-сборка
- `.tools/whisper.cpp-build-openvino/bin/whisper-cli.exe` - optional, если подготовлена OpenVINO-сборка
- `dicta_dictionary_ru.json` - локальные ru-RU автозамены и исключения постобработки
- `models/ggml-small-q5_1.bin`
- `models/ggml-small.bin` - optional quality model, если скопирована локально
- `models/ggml-medium-q5_0.bin`, `models/ggml-medium.bin` - optional quality models
- `models/ggml-large-v3-turbo-q5_0.bin`, `models/ggml-large-v3-turbo.bin` - optional maximum-quality models

Модели, `whisper-cli.exe`, собранные `dist/build` и архивы поставки не входят в git-репозиторий: это тяжелые локальные артефакты пилота.

## Ограничения

Для пилота минимальная обязательная модель - `ggml-small-q5_1.bin`. Для снижения ручных правок после распознавания можно выбрать профиль "Качество"; он использует самую качественную доступную локальную модель из списка выше. Модели ниже `small-q5_1` не используются в пользовательском сценарии из-за недостаточной практической точности.

## Backend performance

Dicta проверяет backend через "Настройки" -> "Производительность" -> "Backend тест" или командой:

```powershell
.\dist\Dicta\Dicta.exe --benchmark-backends --allow-missing-models --model-key small-q5_1
```

Порядок fallback: `Vulkan`, `CUDA`, `OpenVINO`, `AVX2`, `SSE4.2`, `Compat`. Если `AVX2` падает с illegal instruction на старом CPU, Dicta отключает его в текущей сессии и пробует следующий backend. `SSE4.2` - промежуточный CPU backend: быстрее scalar `Compat`, но без AVX2-инструкций.

## Firewall

В exe-версии в "Настройки" -> "Безопасность" есть кнопки "Блокировать сеть" и "Разблокировать". Они создают или удаляют правило Windows Firewall для текущего `Dicta.exe` через `netsh advfirewall` и вызывают стандартный UAC-запрос Windows. Результат пишется в `%TEMP%\dicta_firewall.log`.

Скрипт для ручного создания firewall-правила:

```powershell
.\scripts\add_dicta_firewall_block.ps1
```

На этапе Python-прототипа это правило блокирует сеть для `python.exe`. Для будущей собранной версии лучше передавать путь к `Dicta.exe`.

## ИБ-проверка пилота

```powershell
.\scripts\check_dicta_security.ps1
```

Скрипт проверяет наличие локального движка, рабочей модели, firewall-правил Dicta и временных WAV/TXT-файлов в `%TEMP%`.

Для проверки exe-сборки:

```powershell
.\scripts\check_dicta_security.ps1 -Root ".\dist\Dicta"
```

Для проверки manifest и SHA256:

```powershell
.\scripts\verify_dicta_package.ps1 -Root ".\dist\Dicta"
```

Для наблюдения сетевой активности запущенного приложения:

```powershell
.\scripts\audit_dicta_network.ps1 -ProgramPath ".\dist\Dicta\Dicta.exe" -Seconds 30
```

Для локальной проверки скорости рабочей модели:

```powershell
.\scripts\benchmark_dicta_models.ps1
```

Для сравнения backend на текущем ПК:

```powershell
.\scripts\compare_dicta_backends.ps1
```

GPU backend и `faster-whisper` являются optional. Если рядом с приложением нет Vulkan/CUDA/OpenVINO-сборок `whisper-cli.exe`, Dicta продолжит работать через AVX2 или Compat. `faster-whisper` не входит в обязательные зависимости и проверяется только при ручной подготовке локальной CTranslate2-модели.

## Удобство диктовки

- `Ctrl+Shift+Space` запускает запись, повторное нажатие останавливает ее.
- Галочка "Автокопия" в "Настройки" -> "Текст" копирует итоговый текст в буфер обмена после распознавания.
- Галочка "Форматировать" убирает двойные пробелы, делает первую букву заглавной, нормализует переносы строк и ставит точку в конце.
- Галочка "Команды пунктуации" заменяет слова "точка", "запятая", "двоеточие", "точка с запятой", "многоточие", "вопросительный знак", "восклицательный знак", "кавычки", "кавычки открываются", "кавычки закрываются", "скобка открывается", "скобка закрывается", "тире", "новая строка", "новый абзац" на соответствующую пунктуацию.
- Кнопка "Автоформат" на основной панели применяет эти правила к тексту, который уже находится в окне; повторное нажатие возвращает прежний вариант.
- Правый клик в поле текста открывает меню вырезания, копирования, вставки и выделения всего текста; если кликнуть по подчеркнутому слову, сверху появляются варианты орфографического исправления.

Состояние галочек хранится в `%LOCALAPPDATA%\Dicta\settings.json`. В этом файле нет аудио, распознанного текста или истории диктовок.

## Документы пилота

- `docs\USER_CHECKLIST.md` - короткая инструкция и чек-лист пользователя.
- `docs\IB_PACKAGE_DESCRIPTION.md` - состав поставки и пояснения для ИБ.
- `docs\UPDATE_PROCEDURE.md` - процедура обновления и отката.
- `docs\STAGE_1_0_CORPORATE_PILOT.md` - изменения версии 1.0.
- `docs\STAGE_1_1_BACKEND_THREADS.md` - изменения версии 1.1.
