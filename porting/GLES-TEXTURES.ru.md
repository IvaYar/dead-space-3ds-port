# Текстуры: CPU-хранилище, форматы и следующий барьер

**Следующий результат:** [GLES-PIPELINE.ru.md](GLES-PIPELINE.ru.md) — CULL_FACE пройден, игра действительно загрузила текстуру 512×512 RGBA, CRC32 совпадает в двух эмуляторах. Новая остановка — setjmp. Теперь 240 core-тестов и 67 GL-привязок. Ниже сохранён предыдущий checkpoint.

В graphics-режиме оригинальный движок в **Unicorn и Azahar прошёл `glGenTextures(1, ...)`**. Следующая остановка — `glIsEnabled(GL_CULL_FACE)`, enum `0x0b44`, второй `NativeOnDrawFrame`. Игрового кадра и меню пока нет. Новая проверка на приставке не требуется; CIA не создавался.

## Реализовано

`ds15_textures.c/h` добавляет 16 привязок GLES; вместе с контекстом и буферами их теперь 49. Они подключаются только в opt-in graphics-аудите **после** неизменённой базовой проверки 152 resolved /236 missing /4 weak-zero. Неизвестные API и состояния по-прежнему останавливают выполнение.

Есть настоящие texture objects: Gen/Bind/Is/Delete, резервирование имён до первого bind, создание произвольного свободного имени, общий default object 0, отдельные binding и TEXTURE_2D enable двух server texture units. ClientActiveTexture не меняет выбор server unit. Удаление освобождает уровни изображения и сбрасывает все привязки удалённого объекта в текущем контексте.

TexImage2D копирует пиксели в CPU RGBA8, TexSubImage2D обновляет выбранный прямоугольник. Поддержаны ALPHA, LUMINANCE, LUMINANCE_ALPHA, RGB, RGBA с UNSIGNED_BYTE, а также RGB565, RGBA4444 и RGBA5551. Входные packed ushort читаются в порядке little endian целевых ARM-платформ. UNPACK_ALIGNMENT 1/2/4/8 определяет шаг входных строк; padding последней строки не читается. PACK_ALIGNMENT сохраняется для будущего readback, самого glReadPixels ещё нет.

MIN/MAG filters и WRAP_S/T сохраняются и запрашиваются через integer/fixed/float entry points. Это состояние для будущего renderer: фактическая фильтрация и выборка текстур пока не выполняются. Enum-параметры fixed передаются без сдвига 16.16. Автоматическая генерация mipmap при включении явно останавливает аудит; false поддержан. Уровни mipmap можно загрузить отдельно. Compressed/copy texture APIs не реализованы и не подменяются успехом.

Диагностические ограничения: 32 имени, уровни 0–10, максимальная сторона 1024, power-of-two или нулевая сторона, border 0. Общий бюджет CPU-пикселей — 2 MiB, метаданные дополнительно учитываются runtime allocator. Это **не измеренный бюджет PICA200**. Общий runtime budget и временное сосуществование старого/нового store могут вызвать OOM раньше; неудачная замена сохраняет прежние пиксели. NULL image data обнуляется для детерминированного теста, хотя GLES не определяет начальное содержимое такого изображения.

Внутренний helper читает один RGBA8 texel после проверки объекта, уровня и координат. Это staging для будущего renderer, не объявление GL-расширения. Close контекста освобождает оставшиеся stores и метаданные. Контекст по-прежнему помещается в выделенный CPU-harness участок менее 4096 байт.

## Проверки и фактический прогресс игры

Прошли **22 новых ARM-теста**: реальные пиксели и subimage, все форматы, row alignment, уровни, независимые units, default object, параметры и их ABI, переполнение адреса, ошибочные размеры/типы, исчерпание пула, OOM при bind/replacement, удаление и cleanup. Отдельный softfp ELF вызывает настоящие GL-импорты через loader/registry, в том числе функции с девятью аргументами.

Native-проверка Azahar загрузила 16 байт изображения, изменила 4 байта, прочитала texel и проверила результат. После удаления — ноль имён и байтов store:

```text
GLES texture probe: OK upload=16 sub=4 readback=4 active=0
GLES context bindings: 49; software clear only
...
STOP GLES state: glIsEnabled unsupported enum=00000b44
GLES counters: queries=5 clears=0 pixels=0 flushes=0
GLES texture stores: names=1 bytes=0 uploads=0 patches=0
Sensor shutdown: result=0 active=0 events=0 delay=3
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

Загрузка пикселей выше принадлежит **собственному probe**, а не игре. Сама игра пока зарезервировала одно имя текстуры, затем запросила GL_CULL_FACE; bind/image upload ещё не наблюдались. Пять integer queries пройдены, clear/draw игры отсутствуют. Caller offset прежнего glGenTextures нельзя выдавать за адрес новой остановки: observer сейчас вызывается из нашего GL-адаптера.

На одной текущей core-сборке повторно прошли **222 теста**: 122 runtime +20 JNI +16 platform +8 sensor/JNI +17 GLES +17 arrays +22 textures. Отдельные 14 sensor-тестов другого ELF сохраняют валидные hashes: всего 236 ARM-тестов двух сборок. Все девять engine-сценариев Azahar проверены на текущем CXI. Оба checker прошли, hardware stage8 RX/cache и старые CIA не изменялись. Полный native RX и графика на физической приставке всё ещё не проверены.

## Продолжение

Следующий участок — состояния графического pipeline, начиная с CULL_FACE, затем матрицы/геометрия и renderer PICA200/citro3d. Новые возможности подключать с проверкой поведения и данных. Не скрывать оставшиеся вызовы через no-op или фиктивные ответы; не возвращаться к уже пройденному GL_VIEWPORT.

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_textures.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

После пересборки core повторять также шесть прежних test-скриптов, три CPU-режима и все девять smoke-cases. Azahar запускать последовательно: сценарии используют общую приватную SD. Свидетельства: `analysis/textures-tests.json`, `analysis/engine-graphics-entry.json`, `analysis/azahar-smoke/engine-graphics.log`, `analysis/engine-progress.json`.

Изменения остаются локально. **GitHub обновлять только по прямому запросу пользователя.**

Контракты сверены с Khronos: [GLES 1.1 §3.6–3.7](https://registry.khronos.org/OpenGL/specs/es/1.1/es_full_spec_1.1.pdf), [TexImage2D](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glTexImage2D.xml), [TexSubImage2D](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glTexSubImage2D.xml), [TexParameter](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glTexParameter.xml), [PixelStorei](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glPixelStorei.xml). Реализованный участок не является полным GLES 1.1 renderer.
