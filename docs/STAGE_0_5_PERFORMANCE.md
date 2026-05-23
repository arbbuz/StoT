# Dicta 0.5: производительность

Дата: 2026-05-23
Статус: реализовано в пилотной сборке

## Что добавлено

- Список backend в "Настройки" -> "Производительность":
  - "Авто";
  - "Vulkan";
  - "CUDA";
  - "OpenVINO";
  - "AVX2";
  - "Compat".
- Автоподбор backend по локальному бенчмарку.
- В версии 1.1 backend-бенчмарк дополнительно подбирает число потоков `-t` для каждого доступного `whisper.cpp` backend.
- Кнопка "Backend тест" в этой же вкладке для проверки доступных `whisper.cpp` backend на текущем ПК.
- CLI-бенчмарк backend:

```text
Dicta.exe --benchmark-backends
```

- Скрипт сравнения backend на реальном ПК:

```text
scripts\compare_dicta_backends.cmd
```

- Optional hook для экспериментального `faster-whisper`:
  - не является заменой `whisper.cpp`;
  - не входит в обязательные зависимости;
  - не скачивает модели автоматически;
  - используется только при ручной подготовке локальной CTranslate2-модели.

## Как работает автоподбор backend

1. Dicta ищет локальные `whisper-cli.exe` в папках `.tools`.
2. Если выбран backend "Авто", приложение использует лучшую пару backend + `-t` из сохраненного backend-бенчмарка.
3. Если бенчмарк еще не выполнялся, Dicta пробует доступные backend в порядке:
   - Vulkan;
   - CUDA;
   - OpenVINO;
   - AVX2;
   - Compat.
4. Если выбран конкретный backend, Dicta пробует его первым.
5. Если выбранный backend отсутствует или падает, приложение сохраняет fallback на следующий доступный backend.

Сохраненный результат backend-бенчмарка:

```text
%LOCALAPPDATA%\Dicta\backend_profile.json
```

В этом файле нет аудио, распознанного текста или истории диктовок. Хранятся только технические времена запуска backend/thread-кандидатов, выбранный backend и выбранное число потоков.

## Где ожидаются GPU backend

GPU backend являются optional. Если их нет, приложение продолжает работать через AVX2 или Compat.

Ожидаемые локальные пути:

```text
.tools\whisper.cpp-build-vulkan\bin\whisper-cli.exe
.tools\whisper.cpp-build-cuda\bin\whisper-cli.exe
.tools\whisper.cpp-build-openvino\bin\whisper-cli.exe
```

Для подготовки таких backend используется локальная сборка `whisper.cpp`. По актуальной документации `whisper.cpp` CMake-флаги:

```text
Vulkan:   -DGGML_VULKAN=1
CUDA:     -DGGML_CUDA=1
OpenVINO: -DWHISPER_OPENVINO=1
```

OpenVINO требует установленный OpenVINO runtime/toolkit и корректные переменные окружения. CUDA требует установленный NVIDIA CUDA Toolkit. Vulkan требует драйвер GPU с поддержкой Vulkan.

## Сравнение с faster-whisper

`faster-whisper` в 0.5 оформлен как экспериментальный optional backend для сравнения на реальных ПК.

Чтобы включить его в `scripts\compare_dicta_backends.cmd`, нужно вручную подготовить:

1. Python-пакет `faster-whisper` в окружении, из которого запускается исходная версия, либо упаковать его отдельно для экспериментальной сборки.
2. Локальную CTranslate2-модель.
3. Переменную окружения с путем к модели:

```text
DICTA_FASTER_WHISPER_MODEL=C:\path\to\faster-whisper-model
```

Опциональные переменные:

```text
DICTA_FASTER_WHISPER_DEVICE=cpu
DICTA_FASTER_WHISPER_COMPUTE_TYPE=int8
```

Для GPU-проверки faster-whisper можно использовать `DICTA_FASTER_WHISPER_DEVICE=cuda` и подходящий `compute_type`, если целевой ПК и локальное окружение это поддерживают.

## Поставка

GitHub Actions artifact остается code-only и не включает модели `.bin`.

Модели Whisper по-прежнему нужно вручную скопировать рядом с `Dicta.exe`:

```text
models\ggml-tiny-q5_1.bin
models\ggml-base-q5_1.bin
models\ggml-small-q5_1.bin
```

Optional GPU backend и faster-whisper не являются обязательными для запуска. Базовый fallback остается `.tools\whisper.cpp-build-compat\bin\whisper-cli.exe`.
