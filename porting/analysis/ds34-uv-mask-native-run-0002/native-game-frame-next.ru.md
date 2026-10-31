# Следующий этап: первый оригинальный игровой кадр на native DS34

Точка начала: DS34 UV Mask hardware run-0002 PASS, включая raw pixels/P3D/PPF/queue retirement/START→HOME. Основной shader уже исправлен двумя строками и выдаёт точный hardware-successful SHBIN. Новые аппаратные запуски этим результатом не разрешены.

## Что уже можно использовать

- Существующие `ds_elf`, runtime bindings, JNI bridge, assets/files, allocator/thread modules; работающие emulator callbacks `NativeOnSurfaceCreated`, `NativeOnSurfaceChanged`, `NativeOnDrawFrame`. Их существующие игровые/сценические исследования не повторять.
- Подтверждённый renderer setup из `3ds/build-ds34-gx-watch-v0.2.0/ds34_gpu_rgba8_rgb8.c` плюс исправленный основной shader. Overlay C source в UV Mask ELF тот же; отдельных новых GPU ресурсов для этого исправления не требуется.
- `ds_exec.c` и stage8 RX/cache path. `ds_exec_open` уже различает emulator/native; native path получает process handle, а `ds_exec_make_rx` выполняет RX protection/cache maintenance. Это основа исполнения donor code, не причина снимать guard старого audit entry point.

## Конкретная граница интеграции

Текущий `tests/engine_azahar.c:449` отказывается работать вне emulator. Этот файл — исследовательский entry point: он содержит terminating traps, audit clocks, marker-driven fixtures и ожидаемый production preflight bound154/missing234/weak4 (`:507`). Историческое выполнение до оригинального кадра достигнуто после добавления необходимых bindings в exploratory path; цифры preflight не означают, что именно234 импортов нужны первому кадру. **Не убирать guard одной строкой и не выдавать старый CXI за native игру.**

Следующий кодовый этап — отдельный native entry point с явным runtime-needed bootstrap и однозначным отказом при реально требуемом неподдержанном import/JNI, используя уже реализованные модули. Исходники `ds_exec`/JNI/GLES backend целиком не переписывать. Инициализацию/thread lifetimes переносить из известного игрового пути без серии синтетических GPU probes.

Для graphics integration зафиксировать ровно проверенную цепочку:

| Место | Конкретная настройка |
|---|---|
| TOP с начала процесса | GSP_BGR8_OES,288000 bytes, DS13_BGR8_CTR |
| Target/input | RGBA8, depth24/stencil8,240×400, clearRGB<<8\|255 |
| Display transfer | RGBA8→RGB8,flags1000 |
| Shader | исправленный основной DS34 shader, полный UV output |
| Present/readback | capacity width×height×3; captured layoutBGR8 |

Не подставлять основной C backend с его прежним default RGB8→RGB565 вместо этой согласованной цепочки. `DS34_CAPTURE_RGBA` в одиночку меняет target/input, но не все output/layout/capacity sites: использовать точный существующий overlay либо явно opt-in native configuration с теми же согласованными заменами. При переносе сохранить CPU fallback для FBO и архитектуру DS22→DS34.

Минимальная аппаратная диагностика использовала Legacy64MB. Оригинальному существующему engine path требуется больше памяти; сохранённый178MiB build использует40MiB normal heap/132MiB linear и128MiB donor arena. Его native execution, cache и application profile **не подтверждены** нынешним маленьким draw test. Подготовку выполнять в отдельном build/SD root, сохраняя CPU/GPU baselines и локальные исходные game assets. Native-needed imports, assets readiness и lifetime проверять по существующим bootstrap checkpoints, а не возвращением к552 ARM тестам.

## Следующий проверяемый результат

Сначала подготовить и проверить отдельный engine candidate в Azahar: оригинальная donor .so действительно вызывает draw callback, используются её реальные textures/geometry, GLES error0, CPU fragments/samples0 для GPU screen path, readback согласован сBGR8. Уже известные game checkpoints использовать как reference. Recorded PNG/replay и синтетический прямоугольник не считать игровым кадром. Подготовка такой сборки ещё не выполнена в сеансе получения run-0002.

После программной подготовки — конкретная reviewable сборка и **отдельное согласование** одного следующего hardware запуска. Цель сначала живой оригинальный кадр/меню, затем существующая3D-сцена и HID/touch mapping для управления Айзеком. Аудио, эффекты и RGB565 оптимизация остаются последующими этапами. До native game результата не заявлять playable CIA.
