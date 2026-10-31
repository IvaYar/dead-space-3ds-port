# Переход к игровым кадрам через RGBA8 → RGB8 — 30.10.2026

Временно обойти неработающую комбинацию RGB8 → RGB565 технически возможно. Базовый RGBA8 → RGB8 уже показал треугольник и штатный выход на этой New3DS в HBL и CIA. Это основание перенести конфигурацию в DS34, но не аппаратный PASS DS34 или игры. RGB8 → RGB8 не является обязательным промежуточным аппаратным этапом.

Текущий запрос разрешает подготовить минимальный RGB8 → RGB8 и спланировать интеграцию. Аппаратных запусков и push нет. Рабочие исходники DS34, CPU/GPU binaries, SDK, управление, звук и игровая логика сохранены. Старые ограничения в HANDOFF описывают предыдущие сеансы; текущий запрос разрешает именно эту подготовку.

## Полное сравнение рабочей и нерабочей сборок

Основание: сохранённый upstream `analysis/official-simple-tri/upstream/graphics/gpu/simple_tri/source/main.c`, `3ds/build-simple-tri-rgb565/main.c`, оба build manifests, `analysis/simple-tri-rgb565/source.diff`, аппаратные отчёты `analysis/hardware/official-simple-tri-profile-cia-v0.1.0-user-result.json` и `simple-tri-rgb565-v0.1.0-user-result.json`. Новых догадок о потерянном IRQ по суммарному счётчику нет.

| Параметр | Рабочий stock RGBA8 → RGB8 | Нерабочий RGB8 → RGB565 | Новый RGB8 → RGB8 |
|---|---|---|---|
| Target | GPU_RB_RGBA8 | GPU_RB_RGB8 | прежний GPU_RB_RGB8 |
| Target dimensions | 240×400 | те же | те же |
| Color VRAM bytes | 384000 | 288000 | прежние 288000 |
| Depth | D24S8, 384000 bytes | тот же | тот же |
| Clear word | 0x68B0D8FF | 0x0068B0D8 | прежний 0x0068B0D8 |
| Видимый исходный RGB | (104,176,216) | тот же до квантования выхода | тот же |
| Color/depth FILL controls | 0x0201 / 0x0201 | 0x0101 / 0x0201 | прежние 0x0101 / 0x0201 |
| Инициализация | gfxInitDefault, без смены TOP | добавлен gfxSetScreenFormat(TOP,RGB565) сразу после gfxInitDefault | удалена только эта смена TOP |
| Новый swap/wait при смене формата | отсутствует | не добавлялся | не добавлялся |
| LCD TOP | RGB8 (GSP_BGR8_OES в CPU API) | RGB565 | RGB8 по умолчанию |
| Transfer input/output | RGBA8 / RGB8 | RGB8 / RGB565 | RGB8 / RGB8 |
| Transfer flags | 0x1000 | 0x2100 | 0x1100 |
| Transfer dims | 0x019000f0 → 0x019000f0 | те же | те же |
| Полезные bytes LEFT LCD | 288000 | 192000 | 288000 |
| Шаг столбца в CTR layout | 240×3 = 720 bytes | 240×2 = 480 bytes | 720 bytes |
| Исходное выделение TOP | два буфера по 576000 bytes, включая место RIGHT | не уменьшается при переключении в RGB565 | прежнее |
| CIA Title ID | 000400000FDE6A00 | 000400000FDE6B00 | 000400000FDE6C00 |
| RSF Title / Product | SIMPLE-TRI / CTR-H-C3DT | TRI-RGB565 / CTR-H-C3DF | TRI-RGB8 / CTR-H-C3DR |
| HOME SMDH | simple_tri | tri RGB565 v0.1.0 | tri RGB8 v0.1.0 |
| CIA version | 1 | 1 | 1 |

В старом переходе ровно четыре замены исходника: clear word; выражение input/output formats; добавленная строка TOP switch; target format. Размер allocation, packing FILL и шаг LCD меняются вследствие этих замен. Выход RGB565 дополнительно квантует каналы; численные emulator pixels не являются измерением native pixels. Меньший color buffer может сдвинуть следующие allocations; реальные адреса/IRQ/длительность двух аппаратных запусков не снимались, равенство адресов не утверждается.

Изменились main.o/ELF/CIA/extracted CXI и связанные hash, map/debug/source paths; RSF/SMDH identity и Program ID изменены для отдельной установки. Banner скопирован из stock. Перечисленные различия упаковки не означают другую архитектуру или права. Профиль Legacy64MB, stack256KiB, CPU VRAM read-only, RSF AccessControl/SystemControl и бинарные capability bytes (кроме Program ID) прежние. Компилятор, C/LD flags, libctru2.7.0 и Citro3D1.7.1 прежние. Shader shbin/object/header скопированы побайтно, не перекомпилированы. Подтверждение сравнения и хеши — `comparison.json`.

Геометрия/VBO/projection/TEV/pipeline, C3D_Init, SYNCDRAW, порядок clear → FrameDrawOn → draw → FrameEnd(0), штатные SDK handlers, cache flush, START/sceneExit/Fini и lifetime не менялись. Queue остаётся FILL → PICA → DISPLAY. Ни в одном из трёх вариантов нет DS34, console, SD logger, Run/Submit wrappers, A gate, bounded timeout или fault injection. Различаются также контекст проверок и доступность свидетельств: рабочий запуск подтверждён фото и возвратом HOME, нерабочий — текстом о полоске/зависании/POWER; START в нерабочем запуске не описан. Локальные hashes не доказывают hash установленной на устройстве CIA.

## Минимальный RGB8 → RGB8

Исходник нового теста строится **из сохранённого нерабочего RGB8 → RGB565**, а не из заново собранного stock. Меняется один логический параметр — выходной формат. Физически нужны две согласованные правки: `GX_TRANSFER_OUT_FORMAT(...RGB565)` → `...RGB8` и удаление `gfxSetScreenFormat(TOP,RGB565)`. Оставить одну из них означало бы несовпадение transfer и LCD, то есть другой эксперимент. Source RGB8, 24-bit FILL, clear word, shader object и весь draw/wait code сохраняются. Новая identity — отдельное изменение упаковки для сохранения установленного рабочего контроля, не графическая гипотеза.

| Возможный аппаратный исход (сейчас НЕ выполняется) | Допустимый вывод |
|---|---|
| Правильный устойчивый треугольник и START → HOME | RGB8 source/24-bit clear работает в этом stock контексте; отличие искать в RGB565 output/TOP switch/их сочетании. Не доказано, что RGB565 вообще сломан или что DS34 уже работает. |
| Полоска/чёрный экран и зависание | Отказ сохраняется без RGB565 output/TOP switch; RGB8 target/fill/source-transfer остаются подозреваемыми. FILL и transfer по отдельности не локализованы. Рабочий RGBA8 → RGB8 всё равно остаётся приоритетным обходом. |
| Изображение есть, но цвет/геометрия неверны | Completion/видимость частично подтверждены; packing/layout/transfer требуют отдельного разбора этого результата. Это не полный PASS. |
| Верный кадр, но START не возвращает HOME | Вывод и жизненный цикл расходятся; не переносить PASS на освобождение ресурсов/выход. |
| Чёрный экран, но START возвращает HOME | Процесс выходит; отображение не подтверждено. Без readback/events нельзя сказать, где исчез кадр. |
| Недостаточный/иной результат | Сохранить точное наблюдение, не угадывать IRQ и не запускать варианты автоматически. |

Azahar здесь проверяет сборку, каналы, геометрию и guest cleanup, но уже не воспроизводил аппаратный FAIL RGB565. Новый emulator PASS не разрешает аппаратный запуск и не решает прежний native blocker. Тест подготовлен как резерв; запускать его перед интеграцией рабочего пути не требуется.

## Конкретная интеграция в DS34

1. Добавить отдельный opt-in `DS34_OUTPUT_RGB8` и build variant directory, сохранив default CPU/GPU binaries. Не переименовывать диагностический `DS34_CAPTURE_RGBA` в исправление: он меняет только source и по-прежнему выводит RGB565. Новый opt-in должен согласовать **всю** конфигурацию ниже и отражаться в manifest. SDK и архитектуру backend не менять.
2. В `3ds/source/ds34_gpu_3ds.c` выбрать `GPU_RB_RGBA8`, `GX_TRANSFER_FMT_RGBA8` и output `GX_TRANSFER_FMT_RGB8`, flags0x1000; dimensions240×400 и D24S8 оставить. `ds34_clear` пакует `RGB<<8|255`. Сохранить RGB-only write mask: альфа промежуточного target остаётся1, как у default surface без alpha; не менять GLES alpha-test/blend/FBO semantics. Одна замена только target или только transfer не годится.
3. В entry point задать TOP RGB8 с самого gfxInit (включая BOTTOM RGB8 при console); убрать позднее переключение TOP в RGB565. Console и её CPU cache flush должны затрагивать только BOTTOM. После attach/present не делать CPU clear/flush/swap TOP: им владеет Citro3D. SYNCDRAW, DrawArrays, FrameEnd и проверенный SDK IRQ lifecycle сохранить; не включать новые диагностические wrappers ради переноса формата.
4. В `ds34_attach` для нового варианта принимать `DS13_BGR8_CTR` вместо текущего обязательного `DS13_RGB565_CTR`, проверяя соответствующий TOP format до C3D init. В `ds34_present` убрать жёсткое `w*h*2`: для нового вывода `w*h*3`, 288000 bytes. `DS13Context.pixels/layout/capacity` должны описывать реальный RGB8 LCD, а не RGBA8 target. Получение framebuffer pointer и lifetime относительно completion не переписывать без отдельной причины.
5. Capture/readback/CRC использовать `layout=DS13_BGR8_CTR` (1), CTR column layout, 3 bytes/pixel и invalidate288000 bytes **после** retirement. `engine_azahar.c::graphics_setup`, `save_surface`, `ds13_target` и `export_native_frame.py` уже знают BGR8; проверить их использование новым build profile. Старый native fixture/readback и его ожидаемые RGB565 raw/CRC требуют отдельной адаптации, а не сравнения разного packing. CPU reference CRC auto-menu не переносить на RGB8 GPU кадры.
6. Цена обхода для одного target: +96000 bytes VRAM (color384000 вместо288000); LEFT display transfer +96000 bytes/frame. После gfxInitDefault выделение TOP уже рассчитано на RGB8, поэтому это не новая переразметка памяти игры. При двух targets считать добавку на каждый. На этом этапе не оптимизировать.
7. Собрать отдельно opt-in DS34 и проверить один короткий emulator case с настоящим draw, clear и present, затем короткий запуск **оригинального** engine callback до EA/headphones frame в отдельной SD. Сохранить raw/layout/hash/manifest; не повторять sampling/OpenGL/text или весь552. Гипотеза аппаратной сборки: «та же проверенная RGBA8/32-bit FILL → RGB8 цепочка завершает DS34 draw/present». Проверять на железе только отдельным действием пользователя; пока такой DS34 binary не создан и native PASS не заявлен.

## От первого вывода к управляемой сцене

Первый минимальный следующий шаг — реализовать opt-in DS34 RGBA8 → RGB8 по пунктам1–5 и подготовить **один** DS34 кадр с согласованным LCD/layout. Это полезнее ещё одной аппаратной серии исследования RGB565. После отдельного подтверждения native DS34 completion подключать оригинальный render callback и ресурсы.

Полноценная игра имеет независимый блокер: `tests/engine_azahar.c` намеренно отказывает при `!exec.emulator`; production import audit сохраняет bound154/missing234/weak4. Смена формата не делает этот harness native-safe. Не удалять guard и не упаковывать emulator-only CXI как «игровую CIA». Для первого **живого** оригинального кадра нужен минимальный native engine entry point: существующий проверенный stage8 RX/cache/constructor путь, точный runtime-needed import/JNI набор bootstrap → OnDrawFrame, корректные thread/cache lifetimes, локальные исходные assets, разрешённый memory profile. Составить список реально вызываемых импортов по существующим trace; не повторять полный ARM-аудит. Оригинальные shaders/texture/resource uploads и игровые проходы сохранять. Проигрывание сохранённого PNG или command replay не считать работающей сценой.

Порядок результатов: native DS34 draw/present и штатный выход → живые EA/headphones кадры оригинального движка → меню и загрузка сцены → видимая 3D-сцена → подключение уже существующего HID/touch mapping для движения/камеры/действия → короткий управляемый фрагмент. Управление, звук и игровую логику до базового native rendering не менять; звук подключать после управляемого фрагмента, если он не нужен bootstrap. Мелкий текст/эффекты/форматы оптимизировать позднее, только при реальном блокере.
