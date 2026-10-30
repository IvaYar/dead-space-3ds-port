# Статический аудит CLEAR — 29 октября 2026

Итог: **ошибка, объясняющая аппаратный FAIL, не доказана**. Исполняемый код, SDK и CIA не изменены. `completed=1/2` — состояние SDK-учёта событий, не доказательство физического зависания GPU и не индекс конкретной операции. Новых запусков на приставке/в Azahar и новых CIA нет.

Два прохода: (1) аргументы, память, cache/lifetime; (2) event dispatch/completion и фактическая линковка. На этом аудит ограничен, дальнейшее наблюдение требует нового согласованного теста.

## Версии и доказательства

- libctru **2.7.0-1** из существующего toolchain/manifest.json; исходные reference-файлы взяты из tag v2.7.0. URL/SHA256 в sources.json. Проверяемые ветви queue/IRQ/wait сопоставлены с существующей библиотекой и control.elf, а не только с новым upstream master.
- Citro3D **1.7.1**, изолированный pinned commit `9f21cf7b380ce6f9e01a0420f19f0763e5443ca7`; использованы существующие source/framebuffer.c, renderqueue.c, base.c.
- Native evidence: analysis/hardware/citro3d-control-v0.1.0-user/. CLEAR содержит type2/type3, оба submit0; submitted2/completed1 сохраняются при обоих EXIT PRECHECK. TRIANGLE, shader/VBO/readback не достигнуты.
- В control.elf инструкция **0x0010aa58** вызывает `gxCmdQueueInterrupt` по **0x00106b28**. Это реальный handler с инкрементом lastEntry, не weak stub. Дизассемблирование сохранено в *.asm.txt. `C3D_FrameBegin` по0x00103848 вызывает настоящий gxCmdQueueWait по0x00106e60.

## Точная цепочка и аргументы

1. `gfxInitDefault()` → `gfxInit(GSP_BGR8_OES,GSP_BGR8_OES,false)` → linearAlloc framebuffers. TOP первоначально получает два буфера по576000 bytes (240×800×3). `gfxSetScreenFormat(TOP,RGB565)` не уменьшает выделение; нужный размер384000 меньше прежнего. `gfxGetFramebuffer(TOP,LEFT)` возвращает backbuffer, в этом запуске **0x1408ca00**.
2. `C3D_Init(C3D_DEFAULT_CMDBUF_SIZE)` → init GX queue capacity32, `GX_BindQueue(&ctx->gxQueue)`, callback `onQueueFinish`; Citro3D отдельно устанавливает VBlank0/1 callbacks. `C3D_RenderTargetCreate(240,400,GPU_RB_RGB8,GPU_RB_DEPTH24_STENCIL8)` выделяет color через vramAlloc, depth предпочтительно в противоположном VRAM bank. `C3D_RenderTargetSetOutput(target,TOP,LEFT,0x2100)`.
3. Control ждёт изменения обоих VBlank counters и вызывает `C3D_FrameBegin(C3D_FRAME_NONBLOCK)` до успеха/deadline. В SDK это `gxCmdQueueWait(queue,0)`; только после его успеха Stop/Clear queue и открытие нового frame. Начальный GX WAIT прошёл.
4. `C3D_RenderTargetClear(target,C3D_CLEAR_ALL,0x00102030,0)` → `C3D_FrameBufClear()` →

```text
GX_MemoryFill(
  0x1f000000, 0x00102030, 0x1f046500, 0x0101,
  0x1f300000, 0x00000000, 0x1f35dc00, 0x0201)
```

Цвет:24-bit fill, depth:32-bit fill, trigger bit0 обоих включён. `GX_MemoryFill` пакует header0x01000102, controls word0x02010101 и вызывает submitGxCommand→gxCmdQueueAdd: команда пока в bound queue. `C3D_FrameDrawOn(target)` помечает target used. PICA draw отсутствует.

5. `C3D_FrameEnd(0)` → FrameSplit(0), но в этом clear-only кадре PICA list не появился (native queue это подтверждает). Затем GSPGPU_FlushDataCache всей linear heap, target transfer, gxCmdQueueRun. `C3D_FrameBufTransfer()` берёт тот же gfx backbuffer и вызывает:

```text
GX_DisplayTransfer(
  0x1f000000, 0x019000f0,
  0x1408ca00, 0x019000f0, 0x00002100)
```

`0x019000f0` = width240/height400. Header0x01000103; flags: IN_RGB8(1<<8), OUT_RGB565(2<<12), output linear, no raw copy/flip/scaling. Queue содержит ровно FILL→DISPLAY.

6. `gxCmdQueueRun()` включает глобальный isRunning. DoCommands разрешает максимум3 одновременно: обе команды сразу передаются в gspSubmitGxCommand. Наш Submit wrapper только копирует аргументы/result в память, вызывает исходную функцию и не делает I/O/не меняет events. Run wrapper пишет диагностику в основном потоке до/после исходного Run; callbacks не заменяются.
7. gspSubmitGxCommand заносит32 bytes в15-slot shared command ring с DSB/атомарным header update; при переходе empty→nonempty вызывает TriggerCmdReqQueue. Нулевой return означает успешное enqueue/trigger, **не** подтверждение исполнения/валидации GPU-операции.
8. После FrameEnd control снова ждёт VBlank и repeatedly FrameBegin(NONBLOCK), при busy спит1мс. Deadline2000мс сработал через2009мс. Поскольку SDK queue не retired, CPU invalidate/readback не выполняются.

## Память, форматы и lifetime

| Объект | CPU virtual / physical | Диапазон, размер | Проверка |
|---|---|---|---|
| Color RGB8 | 1f000000 / 18000000 | [1f000000,1f046500),288000 bytes | В VRAM bank A; 240×400×3; размер целого числа8×8 tiles |
| Depth D24S8 | 1f300000 / 18300000 | [1f300000,1f35dc00),384000 bytes | В bank B; 240×400×4; с color не пересекается |
| TOP RGB565 | 1408ca00 / 2008ca00 | запись[1408ca00,140bb800),192000 bytes | В FCRAM linear allocation; выделено576000, достаточно |

Указанные адреса/концы выровнены минимум на8 и128 bytes; width/height кратны8 и16. Оба VRAM диапазона внутри6MiB, destination не перекрывает source/depth. Virtual addresses именно так принимает GX API; подставлять physical address в этот API не требуется. Enum RGB8/RGB565 и flags согласованы с числом bytes и локальными SDK headers. **Ошибки кодирования не найдено; это не аппаратное доказательство работоспособности каждой комбинации PPF formats.**

VRAM mapped CPU read-only: CPU туда не пишет, fill/transfer делают GPU. Target/CPU framebuffers не освобождаются и формат не меняется после Run. Source/queue/submission arguments остаются живы. FrameEnd(0) использует штатный общий flush linear heap до отправки очереди; VRAM не содержит dirty CPU writes. Return общего SDK flush не записан, поэтому его фактический native успех не доказан логом. Ошибка CPU readback cache/orientation не объясняет этот timeout: вызов InvalidateDataCache ещё не достигнут. После timeout ресурсы удерживаются; EXIT PRECHECK не достиг Fini/gfxExit.

## Что означает completion

В libctru v2.7.0 `gxCmdQueueInterrupt` при isRunning увеличивает lastEntry для PSC0/PPF/P3D/DMA, игнорируя PSC1 и оба VBlank. Нет проверки типа текущей команды, operation ID или generation. Это число обработанных подходящих IRQ; submitted — число переданных в shared command ring команд. MAX_PARALLEL_CMDS=3 допускает одновременную отправку FILL/DISPLAY. Нельзя интерпретировать lastEntry как индекс зависшей команды.

`gxCmdQueueWait` проверяет **глобальный isRunning**, а не переданный queue pointer. В контроле активна одна SDK queue, поэтому это не доказанная ошибка использования. При timeout0 и busy он возвращает false до gspWaitForAnyEvent; Stop/Clear ещё не вызываются. Бинарный код перечитывает флаг; snapshot использует volatile queue fields. Данные1/2 — настоящие SDK fields, не наш отдельный счётчик.

В GSP event thread каждый извлечённый IRQ сначала передаётся GX handler, затем event callback, затем sticky LightEvent/gspLastEvent. Поэтому очистка/чтение публичного event основным потоком не отменяет уже выполненный GX increment. Однослотовый gspLastEvent может объединять уведомления для waiters, но не является источником lastEntry. Само ожидание VBlank не «крадёт» PSC0/PPF у очереди.

Уточнение30.10 после проверки наблюдателя: физические fill channels нельзя отождествлять с relay events GSP. [Azahar2126.2](https://github.com/azahar-emu/azahar/blob/2126.2/src/video_core/gpu.cpp#L188) для dual-buffer MemoryFill доставляет только PSC0 (код явно моделирует такое поведение GSP). Ранее обязательный PSC1 в этой формулировке был ошибочным ожиданием; его ноль сам по себе не дефект. SDK намеренно не учитывает PSC1 как ещё одну команду. Для DISPLAY ожидается PPF. И PSC0-only, и PPF-only дают1/2. Теоретически возможны потерянная доставка, неожиданный поздний IRQ или неверный lifecycle queue; исходный hardware log не содержит event IDs и hardware finish status. **Нельзя точно выбрать FILL, DISPLAY или потерю completion по этим данным.**

При lastEntry<numEntries `onQueueFinish` не вызывается. Поэтому запланированный TOP swap не происходит; чёрный верхний экран также не доказывает, что backbuffer не был записан. Нельзя пропускать wait, считать timeout успешным, насильно обнулять queue или освобождать GPU память.

## Сравнение с официальным кодом

Структура frame loop и fill/transfer headers соответствует [devkitPro simple_tri](https://github.com/devkitPro/3ds-examples/blob/master/graphics/gpu/simple_tri/source/main.c), pinned Citro3D framebuffer/renderqueue и [libctru v2.7.0 gx.c](https://github.com/devkitPro/libctru/blob/v2.7.0/libctru/source/gpu/gx.c). Существенное отличие от simple_tri: тот использует RGBA8 render target / RGB8 output (flags0x1000), контроль — RGB8/RGB565 (0x2100), унаследованные от DS34. Сам по себе опубликованный enum не доказывает, что аппаратный transfer здесь завершился. Профиль CIA также не является неизменённой upstream-сборкой примера: независимая проверка была именно под нашим прежним профилем.

Сохранены только ссылки/хеши reference sources; полный vendor source в git не добавляется. Ни unsupported-формат, ни плохая memory permission, ни ошибка SDK IRQ dispatch данным аудитом не доказаны. Permissions/форматы/SDK наугад не менялись.

Примечание вне причины: positive timeout в gxCmdQueueWait документирован как ns, а реализация прибавляет его к ticks. Здесь используются0 и−1; этот вопрос не объясняет текущий сбой и SDK не патчился.

## Один следующий минимальный тест

Предлагается **один CLEAR-only запуск с прежними двумя командами и аргументами**, без смены форматов и без TRIANGLE. В standalone control после C3D_Init добавить только пассивные callbacks PSC0/PSC1/PPF через gspSetEventCallback, атомарные counters в памяти и снимки queue перед Run/на timeout. VBlank callbacks Citro3D и queue onQueueFinish не заменять; IRQ-dispatch не оборачивать слабым linker wrapper (этот путь ранее оказался недостижимым).

Эти callbacks вызываются после SDK GX handler, поэтому дадут тип реально доставленного события. PSC0 без PPF сузит поиск к PPF/transfer/delivery; PPF без PSC0 — к fill/completion delivery; оба события при lastEntry1 потребуют разбирать isRunning/current queue lifecycle. Отсутствие callback не доказывает физический GPU hang: hardware завершение/потерю IRQ можно различать лишь дополнительным наблюдением status, если понадобится. Это информационный тест, не предполагаемое исправление.

Новая сборка **не создана**. Готов план точечной инструментации; перед реальным запуском нужны разрешение на её подготовку, программная проверка и отдельное согласование аппаратного теста. Нынешние нерабочие архивы повторно не запускать.
