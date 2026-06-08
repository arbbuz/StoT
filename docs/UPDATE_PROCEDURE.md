# Dicta: процедура обновления

## Коротко

Dicta обновляется заменой всей папки приложения. Один `Dicta.exe` отдельно переносить нельзя: рядом должны оставаться `_internal`, `.tools`, `models`, `assets`, `docs`, `scripts`, `manifest.json` и `SHA256SUMS.txt`.

## Перед обновлением

1. Закрыть `Dicta.exe`.
2. Если в старой папке есть вручную добавленная рабочая модель, сохранить ее отдельно или оставить старую папку как источник:

```text
models\ggml-small-q5_1.bin
```

3. Если включалась блокировка сети, учесть, что firewall-правило привязано к конкретному пути `Dicta.exe`.

## Установка новой версии

1. Скачать artifact `Dicta-windows-code-only` из GitHub Actions workflow `Build Dicta EXE`.
2. Распаковать `Dicta-windows-code-only.zip` целиком в отдельную папку `Dicta`.
3. Вручную скопировать рабочую модель в папку `models` рядом с новым `Dicta.exe`:

```text
models\ggml-small-q5_1.bin
```

4. Запустить проверку целостности code-only пакета:

```text
scripts\verify_dicta_package.cmd
```

5. Запустить:

```text
scripts\diagnose_dicta.cmd
```

6. Открыть `Dicta.exe` и проверить:
   - главное окно открывается;
   - нужный микрофон выбран в `Настройки` -> `Запись`;
   - `Проверить` показывает уровень микрофона;
   - короткая диктовка распознается;
   - `Автоформат` применяет форматирование, повторное нажатие возвращает прежний текст;
   - `Скопировать` помещает текст в буфер обмена.

## Автоматическая сборка в GitHub Actions

После каждого `push` в любую ветку запускается workflow:

```text
.github\workflows\build-dicta.yml
```

Workflow собирает Windows-пакет `dist\Dicta` без модели и публикует artifact:

```text
Dicta-windows-code-only
```

Внутри artifact находится ZIP:

```text
Dicta-windows-code-only.zip
```

Модель Whisper не включается в artifact намеренно. В папке `models` будет только `README_MODELS.txt` с напоминанием, что `ggml-small-q5_1.bin` нужно скопировать вручную.

## Локальная code-only сборка

Для локальной сборки без модели:

```powershell
.\scripts\prepare_dicta_assets.ps1 -SkipModels
.\scripts\build_dicta_exe.ps1 -SkipModels -PackageVersion "1.1-pilot-code-only"
```

For a branch-specific local package, pass an explicit package folder under `dist`:

```powershell
.\scripts\build_dicta_exe.ps1 -PackageVersion "1.1-pilot-protocol" -DistRoot "dist\DictaProtocol"
```

`-DistRoot` defaults to `dist\Dicta`. The build script stages PyInstaller output under `build\pyinstaller-dist`, then clears and repopulates only the selected package folder under `dist`.

Результат появится в:

```text
dist\Dicta
```

## Ручная установка без GitHub artifact

1. Распаковать или скопировать новую папку `Dicta` целиком.
2. Запустить проверку целостности code-only пакета:

```text
scripts\verify_dicta_package.cmd
```

3. Вручную скопировать `ggml-small-q5_1.bin` в папку `models` рядом с новым `Dicta.exe`.
4. Запустить:

```text
scripts\diagnose_dicta.cmd
```

5. Открыть `Dicta.exe` и проверить:
   - главное окно открывается;
   - нужный микрофон выбран в `Настройки` -> `Запись`;
   - `Проверить` показывает уровень микрофона;
   - короткая диктовка распознается;
   - `Автоформат` применяет форматирование, повторное нажатие возвращает прежний текст;
   - `Скопировать` помещает текст в буфер обмена.

## После обновления

Если используется firewall-блокировка:

1. Открыть `Настройки` -> `Безопасность`.
2. Нажать `Блокировать сеть` из новой папки приложения.
3. Подтвердить UAC.
4. Проверить:

```text
scripts\check_firewall_block.cmd
```

## Откат

1. Закрыть новую версию.
2. Вернуть старую папку `Dicta`.
3. Если путь изменился, заново создать firewall-правило из старой папки через `Настройки` -> `Безопасность` -> `Блокировать сеть`.
4. Запустить `scripts\diagnose_dicta.cmd` в старой папке.

## Что не переносится автоматически

Dicta не переносит историю диктовок, потому что она не хранится. Технические профили и настройки лежат в:

```text
%LOCALAPPDATA%\Dicta\performance_profile.json
%LOCALAPPDATA%\Dicta\backend_profile.json
%LOCALAPPDATA%\Dicta\settings.json
```

В этих файлах нет аудио, распознанного текста или истории диктовок. `backend_profile.json` хранит только технические времена backend/thread-бенчмарка, выбранный backend и выбранное число потоков.
