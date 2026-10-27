# Вершинные массивы и буферы: дошли до создания текстуры

**Следующее продолжение:** [GLES-TEXTURES.ru.md](GLES-TEXTURES.ru.md) — CPU texture stores реализованы и проверены, оба эмулятора прошли glGenTextures и остановились на GL_CULL_FACE. Теперь 222 core-теста и 49 GL bindings. Ниже сохранён предыдущий checkpoint arrays/buffers.

Новый graphics-запуск в Unicorn и Azahar проходит прежние проверки client arrays и останавливается на **`glGenTextures(1, ...)`**, caller offset `0x3394a0`, второй NativeOnDrawFrame. Пока это создание имени первой текстуры, не загрузка её изображения. Игрового кадра и меню нет. Приставка для этих проверок не нужна.

Уточнение предыдущего отчёта: enum **0x8075 — GL_NORMAL_ARRAY**. Ранее он был неверно назван GL_COLOR_ARRAY; значение массива цветов — 0x8076. Сам числовой enum в трассировке был записан правильно. Названия в текущих документах исправлены.

## Что реализовано

`ds14_arrays.c/h` хранит независимые дескрипторы позиции, нормали, цвета и texcoords двух client texture units. Поддержаны enable/disable client state, размеры/типы/stride/pointer, GetPointerv и соответствующие integer queries. Pointer-call запоминает текущий ARRAY_BUFFER; последующий BindBuffer не меняет уже записанный дескриптор. ClientActiveTexture выбирает свой texcoord-дескриптор, независимо от server ActiveTexture.

Добавлены реальные buffer objects: Gen/Bind/Is/DeleteBuffers, BufferData, BufferSubData и GetBufferParameteriv. Gen резервирует имя; IsBuffer становится true после первого bind. Ненулевое незанятое имя можно создать bind-вызовом. Store копирует переданные байты, subdata изменяет только заданный диапазон. Поддержаны STATIC_DRAW и DYNAMIC_DRAW, предусмотренные GLES 1.1.

Пул ограничен 32 объектами на контекст, общий CPU data store — 2 MiB. Это диагностический host-memory бюджет, не измеренная GPU-память. Ошибки размера, enum, диапазона и исчерпание памяти возвращают GL error. При неудачном realloc прежние данные сохраняются; отрицательные размеры/offset и переполнение индекса не превращаются в длинное копирование. Новое хранилище с NULL data обнуляется для детерминированной диагностики; стандарт GLES не обещает определённых исходных байтов такого store.

DeleteBuffers сбрасывает все bindings удалённого объекта в текущем контексте, включая ссылки array descriptors, и освобождает память. Close контекста освобождает оставшиеся stores. Повторная инициализация незакрытого контекста отказывает, чтобы не потерять ownership. Shared contexts, map/unmap и индексы для draw пока не реализованы.

Внутренний staging helper копирует один **сырой атрибут** только после проверки buffer bounds, index×stride, offset и ёмкости выхода. Для client memory backend обязан заранее зарегистрировать живой читаемый диапазон; есть обновление и удаление диапазонов. Произвольные указатели не разыменовываются helper-ом. Это подготовка данных, а не draw и не преобразование fixed/normalized компонентов в shader-входы.

Для начального snapshot SDK добавлены matrix-mode selector, blend/fog flags и запрос binding фактически прикреплённой default framebuffer. Эти поля хранят состояние; матричных преобразований, FBO objects, rasterization/blending/fog renderer пока нет. Неизвестные API/состояния продолжают диагностически останавливать запуск.

## Проверки

Прошли **17 новых ARM-тестов**: reservation/creation имён, независимость bindings, pool exhaustion, реальный upload/subdata, pointer capture, типы и диапазоны, OOM с сохранением старого store, NULL/zero-sized stores, delete/detach, client-range lifetime, проверка overflow при staging и освобождение памяти. Отдельный softfp ELF импортирует и вызывает настоящие GL entry points через loader/registry.

В Azahar дополнительная native-проверка загрузила 24 байта, обновила 12 байт, получила 12 байт через staging и проверила результат; после удаления не осталось объектов и байтов store:

```text
GLES buffer probe: OK upload=24 sub=12 readback=12 active=0
GLES context bindings: 33; software clear only
...
STOP unsupported: glGenTextures
Phase: NativeOnDrawFrame
Caller offset: 003394a0
GLES counters: queries=5 clears=0 pixels=0 flushes=0
Sensor shutdown: result=0 active=0 events=0 delay=3
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

Это собственный изолированный buffer probe. Настоящая игра пока прошла пять integer state queries и не выдала clear/draw; нельзя выдавать readback тестовых данных за обработку игровой геометрии.

На текущем core повторно прошли **200 тестов** (122 runtime +20 JNI +16 platform +8 sensor/JNI +17 GLES state +17 arrays). Сохраняется отдельный валидный набор 14 sensor-тестов другого ELF: всего **214 ARM-тестов**. Девять сценариев Azahar прошли на одной текущей CXI-сборке. Checker сверяет source/output hashes и неизменность hardware stage8 RX/cache. Нового CIA нет, аппаратная графика не проверялась.

## Повторение и следующий шаг

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_arrays.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

После изменения core также повторить прежние пять test-скриптов, три CPU-режима и все девять smoke-cases; Azahar запускать последовательно. Свидетельства — `analysis/arrays-tests.json`, `analysis/engine-graphics-entry.json`, `analysis/azahar-smoke/engine-graphics.log` и `analysis/engine-progress.json`.

Следующий блок — настоящие texture objects: имена, binding, параметры, image storage и загрузка/проверка форматов ресурсов. Затем матрицы, геометрия и backend PICA200/citro3d. Одних успешных GenTextures и фиктивных handles недостаточно. Базовый production guard остаётся 152/236/4; graphics-registry добавляет 33 адреса только в opt-in режиме и не объявляет весь GLES реализованным.

Изменения локальные. GitHub обновлять только по прямому запросу пользователя.

Первичные контракты: Khronos [DeleteBuffers](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glDeleteBuffers.xml), [BufferData](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glBufferData.xml), [VertexPointer](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glVertexPointer.xml), [GetPointerv](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glGetPointerv.xml).
