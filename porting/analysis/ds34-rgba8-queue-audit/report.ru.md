# DS34 RGBA8 v0.1.0: точечный разбор native очереди, 31.10.2026

Прочитаны **все7 файлов** `porting/ds34-rgba8-v0.1.0.zip`: gpu-test.log, queue-00…04.json, ready.txt. Архив2558 bytes, SHA256 `0576186e878a28343ca682b01b3168247215c3edc1e8b384f485f7f57be2a53c`. Оригинальные bytes сохранены в `analysis/hardware/ds34-rgba8-v0.1.0-repeat-user/`; archive-manifest.json содержит размеры/хеши и исходные имена `New folder/*`. Это **повторный аппаратный запуск**, отдельный от первого текстового FAIL. Больше эту версию не запускать. В архиве нет frame/raw/result/exit файлов или PICA payload; это перечень полученных файлов, не независимый аудит всей SD.

## Что установлено

1. Header: `environment=native bytes=288000 layout=1 flags=00001000`. ATTACH OK есть. queue-02 содержит единственный TEXCOPY256 bytes, queue-03 — его retirement1/1. Первоначальная загрузка нейтральной texture не является местом текущей остановки; вывод не переносится на первую draw-очередь.
2. В первом кадре пройдены clear, vertex cache flush, DrawArrays и вызов `C3D_FrameEnd(0)`. Это подготовка/постановка команд, не доказательство выполненной растеризации.
3. `SDK FRAME END OK` ms4213/vb25,25 означает, что C3D_FrameEnd вернулся. Его штатный путь выполнил flush linear heap, подготовил display transfer и вернулся из gxCmdQueueRun. Результаты отдельных GSP submits этот fixture **не записывает**; SDK их игнорирует. Нет доказательства, что все заявки успешно приняты или исполнены.
4. `SDK SYNC OK` ms4243/vb27,27 означает возврат из первого явного C3D_FrameSync. Оба Citro3D VBlank counters изменились; это не ожидание FILL/PICA/DISPLAY.
5. Последняя строка `SDK FRAME BEGIN` ms4253/vb27,27 стоит перед следующим C3D_FrameBegin(SYNCDRAW). **Внутри него сначала есть ещё один VBlank wait**, затем gxCmdQueueWait(queue,-1), затем Stop/Clear. В точном ELF второй VBlank wait **заинлайнен** в C3D_FrameBegin: адрес111450 вызывает gspWaitForAnyEvent, затем переход к gxCmdQueueWait по адресу1113dc. Простое оборачивание публичного символа C3D_FrameSync не поймает этот встроенный wait.

Гипотеза «очередь не завершилась, следующий Begin ждёт GX» согласуется с логом и остаётся основной рабочей, **но пока не доказана**. Из последних меток нельзя отличить второй VBlank wait, GX wait и описанные ниже окна SD-записи. START сканируется во внешнем loop: при блокировке внутри любого из этих участков нажатие не обработается, даже если другие потоки/прерывания работают.

## queue-00…04 и точные команды

| Файл | Момент снимка | total/submitted/completed | Значение |
|---|---|---|---|
| queue-00 | before-run при C3D init | 0/0/0 | Пустая SDK queue |
| queue-01 | before-clear | 0/0/0 | Пустая queue очищается |
| queue-02 | before-run | 1/0/0 | TEXCOPY нейтральной texture |
| queue-03 | before-clear | 1/1/1 | Эта TEXCOPY учтена завершённой |
| queue-04 | **before-run** первого кадра | 3/0/0 | FILL, PICA, DISPLAY ещё до вызова настоящего Run |

Значения0/0 из queue-04 **нельзя использовать как post-FrameEnd live counters**. Wrapper сначала копирует поля и words, затем вызывает настоящий Run. Снимок сохраняется на SD позднее, при `SDK FRAME END OK`, но содержимое не обновляется. В используемом libctru MAX_PARALLEL_CMDS=3, поэтому Run обычно пытается отправить сразу все3 заявки. Порядок массива не является гарантированным порядком физических completion событий.

```
FILL:    01000102 1f000000 68b0d8ff 1f05dc00 1f300000 00000000 1f35dc00 02010201
PICA:    01000101 14189c00 00000490 00000000 00000000 00000000 00000000 00000000
DISPLAY: 01000103 1f000000 14000000 019000f0 019000f0 00001000 00000000 00000000
```

- **FILL / GX_MemoryFill**: color `[1f000000,1f05dc00)`,384000 bytes, clear68B0D8FF; depth `[1f300000,1f35dc00)`,384000 bytes, clear0. Packed control02010201 означает0201 для каждого32-bit buffer. Для учёта этой команды SDK ожидает **PSC0**; PSC1 может наблюдаться отдельно, но **не увеличивает lastEntry**. Отсутствие PSC1 не считать ошибкой. Это один dual-buffer GX command, не две queue entries.
- **PICA / GX_ProcessCommandList**: CPU virtual command-list pointer14189C00,1168 bytes (`0x490`), конец1418A090; flags0 (включая отсутствие per-list flush request). Общий flush linear heap выполняет FrameEnd(0). Ожидаемое уведомление завершения command list — **P3D**. Header и длина не доказывают корректность register stream, shader, vertex data или native cache visibility. Самих1168 bytes из native памяти в архиве нет.
- **DISPLAY / GX_DisplayTransfer**: VRAM source1F000000 → LCD CPU virtual destination14000000; обе dimensions019000F0 = width240/height400. Flags1000: RGBA8 input, RGB8 output, flip/raw/tiled-output/scaling0. Полезный output `[14000000,14046500)`,288000 bytes. Ожидаемый completion — **PPF**.

Начальная TEXCOPY: `01000104 14249b80 1f05dc00 00000100 00000000 00000000 00000008 00000000`. Source linear14249B80, destination1F05DC00, размер256 bytes. Destination начинается **сразу после исключительной границы** color buffer, не внутри него. Для TEXCOPY ожидаетсяPPF; в queue-03 учтено1/1. Это не доказывает, что последующий DISPLAY завершился: это другая команда/другой момент.

Известные color/depth/LCD/command-list диапазоны выровнены, не перекрываются, sizes соответствуют SDK. TOP allocation, созданный gfxInitDefault, имеет запас576000 bytes на каждый из двух буферов; полезный LEFT transfer288000 bytes помещается. Проверены только адреса/границы, имеющиеся в metadata; vertex/shader payload и их runtime addresses в native архиве не сняты.

Все5 queue JSON **семантически полностью совпадают** с сохранённым успешным Azahar запуском, включая адреса и все GX words. Это равенство metadata, не доказательство равенства1168 PICA bytes или vertex/texture contents на железе и в эмуляторе.

## Проверка именно используемого SDK и ELF

Проверены hashes pinned libctru2.7.0 source gxqueue.c/gx.c/gspgpu.c/gfx.c, Citro3D1.7.1 commit9f21cf7b380ce6f9e01a0420f19f0763e5443ca7 source renderqueue/framebuffer/base и libraries, записанные в build manifest. Stock и DS34 используют те же libraries. Дизассемблирован **существующий** DS34 ELF: реальный gxCmdQueueInterrupt вызывается из gspEventThreadMain, weak stub не является конечным handler. Сохранён `linked-functions.asm.txt`, контроль `result.json`; воспроизведение — `python porting/tools/audit_ds34_native_queue.py`, только чтение/статический анализ, не сборка и не runtime test.

Цепочка исходников:

- `toolchain/citro3d-source/source/renderqueue.c`: FrameEnd не ждёт completion; FrameSync ждёт только изменения **обоих** frameCounter; FrameBegin(SYNCDRAW) делает ещё FrameSync, затем WaitAndClearQueue(-1).
- `analysis/gpu-clear-audit/upstream/gxqueue.c`: curEntry увеличивается **перед** gspSubmitGxCommand, return Result не проверяется; lastEntry увеличивается по подходящим доставленным IRQ. PSC1/VBlank игнорируются; PSC0/P3D/PPF/DMA учитываются без command-ID attribution. Поэтому даже live submitted3 означает попытки отправки, а не три успешных GSP Result.
- gxCmdQueueWait читает глобальный isRunning, а не только q->lastEntry. При одной active queue это штатная модель SDK; для диагностики полезны **и** counters, **и** `gxCmdQueueWait(q,0)`. Положительный timeout SDK здесь не применять: уже известное ns/ticks несовпадение не является новой гипотезой; использовать timeout0 и собственный внешний deadline.
- `analysis/gpu-clear-audit/upstream/gspgpu.c`: event thread вызывает SDK GX interrupt handler (включая onQueueFinish), **затем** public event callback, затем LightEvent/gspLastEvent notification. Отсутствие public callback не доказывает отсутствие физического IRQ: SDK handler/onQueueFinish могли не вернуться. Если VBlank counters перестанут двигаться, учитывать остановку event delivery/thread. onQueueFinish/swap — отдельный возможный участок, а не автоматически «PICA зависла».

## PHASE и SD: границы доказательства

`ds34_diagnostic_mark` сначала выполняет dump_records (fopen/fprintf/fclose отдельных queue JSON), затем берёт время/счётчики, пишет PHASE через fprintf и вызывает fflush(journal). В compiled ELF dump_records заинлайнен в mark. Время метки не является GPU completion timestamp; часть задержки приходится на filesystem. `fflush` не является общей гарантией физического fsync SD, и его return здесь не логируется.

Полная последняя строка показывает, что данные дошли до файла, **но не доказывает возврат её fflush и вход в SDK**. Возможна и симметричная ситуация: FrameBegin уже вернулся, а последующий mark перед `SDK FRAME BEGIN OK` остановился в dump_records при создании queue-05. Отсутствие queue-05 в полученном архиве уменьшает объём доступных доказательств, но не является отдельным stack trace. Поэтому текущая локализация — окно между последней mark и отсутствующей следующей mark, а не доказанный адрес CPU wait.

Новых пикселей/readback/retirement первого кадра в полученных данных не подтверждено. Не утверждать, что кадр обязательно не появлялся: пользователь его видимость не описал, TOP swap/readback отдельно не измерены.

## Сравнение с аппаратно успешным simple_tri

Stock native queue capture отсутствует. Сравниваем реальные DS34 words с **ожидаемыми аргументами из успешно запущенного stock source и того же SDK**, не выдаём stock addresses/IRQ за измеренные.

| Участок | Stock simple_tri | DS34 RGBA8 test |
|---|---|---|
| gfx/target/FILL/transfer | gfxInitDefault, RGBA8/D24S8,384000/384000,68B0D8FF/0,0201/0201,RGBA8→RGB8/1000 | те же параметры, подтверждённые queue-04 |
| CIA permissions | Legacy64MB/stack256KiB/CPU VRAM:r | те же capability bytes кроме identity; TitleFDE6D вместоFDE6A |
| Команды | ожидаемо FILL→PICA→DISPLAY | реально такой массив из3 entries |
| Подготовка | Begin(SYNCDRAW) → clear → FrameDrawOn → draw → End | Begin(SYNCDRAW) → FrameDrawOn → FrameSplit → clear → FrameDrawOn → draw → End |
| После End | следующий loop → Begin(SYNCDRAW), один VBlank wait | явный FrameSync, затем Begin(SYNCDRAW), то есть **два** VBlank waits |
| PICA/resources | stock shader, float3 position + fixed white,1 triangle | DS34 shader/4×float4 stream,2 triangles/scissor, inactive sampler/white texture |
| Allocations | stock VBO/program + SDK | дополнительно DS34 stream524160 bytes, нейтральная texture256 bytes, CPU runtime и recorder; конкретные stock runtime addresses неизвестны |
| Наблюдение | нет SD/logger/console/wrappers/readback | BOTTOM console, A gate, Run/Clear recorders, main-thread SD, readback только после present |
| Cache | SDK whole-linear flush в End(0) | тот же flush + vertex flush; invalidate/readback ещё не подтверждены |

Общая невозможность SDK/CIA-профиля работать противоречит stock PASS; общий RGB8 LCD/fill формат также не выделяется этим FAIL. **PICA/state/vertex/sampler путь — первый GPU-кандидат для измерения**, поскольку он существенно отличается от stock. Но FILL, DISPLAY, delivery/accounting, второй VBlank и SD пока не исключены; данных для достоверного назначения «зависшей команды №1» нет.

## Один следующий аппаратный запуск: конкретный план различения

Это **план**, новая CIA/3DSX не создана, hardware run не выполняется. Подготовку и отдельный запуск согласовать позднее. Не менять game backend, форматы, shader/геометрию, порядок трех GX commands или SDK handlers; не повторять старую v0.1.0. Нужен только первый диагностический кадр, не все9 и не игра.

1. В отдельном harness сохранить указатель именно SDK queue. Имеющийся Run wrapper дополнить **post-Run** bounded memory snapshot после настоящего Run; pre-Run оставить. Записывать total/curEntry/lastEntry/maxEntries с адресом queue, фазой и system ticks. Не менять поля/queue callback, не захватывать SDK lock.
2. После завершённого attach, до первого draw-submit, занять только свободные публичные callbacks PSC0/PSC1/P3D/PPF (их не использует этот harness/Citro3D). Сохранить VBlank/onQueueFinish и настоящий GX IRQ handler. Callback — только32-bit atomic counters/ordinal и защищённые от разрыва timestamps, без SD/stdio/allocation/waits. Нулевой baseline/снимок непосредственно до submit отделяет старый PPF от white TEXCOPY. SDK обрабатывает IRQ до этих callbacks; это измерение **доставки**, не прямой status GPU.
3. Чтобы отличить принятие заявки от попытки отправки, повторно использовать уже проверенный memory-only recorder Result `gspSubmitGxCommand`: полный command header/words, Result и порядковый номер. Он может вызываться под SDK lock/из event thread; никаких файловых операций там. Успешный Result подтверждает принятие SDK/GSP-путём, не исполнение GPU. Не пытаться снова оборачивать gxCmdQueueInterrupt: прежняя проблема same-translation-unit/weak stub известна; теперь факт достижимости реального handler проверен.
4. **Убрать файловый I/O из окна наблюдения после FrameEnd.** Сразу после его возврата записать атомарный stage END_RETURNED и снимок queue/events/VBlank в RAM; аналогично до и после каждого шага, флаг записи на SD отдельно. В течение внешнего deadline около2 секунд опрашивать только счётчики и `gxCmdQueueWait(q,0)` с коротким svcSleepThread, без unbounded FrameSync/FrameBegin и без consume/clear GSP events. Это пассивная проверка queue running state, counters не очищает. Отдельно наблюдать продвижение обоих VBlank counters; если требуется воспроизвести два интервала, отметить две ограниченные фазы ожидания counters, не блокироваться в gspWaitForAnyEvent.
5. **C3D_FRAME_NONBLOCK — лишь диагностическая развилка.** После сохранённого pre-check snapshot можно один раз вызвать Begin(NONBLOCK) без SYNCDRAW; при busy он вернёт false, при успехе Stop/Clear изменят counters, поэтому сохранить память до вызова и before-clear recorder. Не совмещать NONBLOCK с SYNCDRAW: иначе внутри останется unbounded VBlank wait. Можно вообще обойтись gxCmdQueueWait(q,0) до решения о продолжении; это минимальнее и полностью пассивно.
6. До Run скопировать PICA command-list payload в ограниченный diagnostic RAM buffer с проверкой CPU linear-heap range/length/alignment (текущий1168 bytes); сохранить его после окна. Одни pointers не позволяют проверить native GPU state offline. Не читать произвольные physical addresses и не писать CPU в VRAM. Такой capture позволит разбирать PICA stream после одного запуска, если события укажут именно на него.
7. После deadline/idle сохранить отдельный result/snapshots/events/submits/PICA, затем вывести статус. При busy не входить в Fini и не освобождать GPU ресурсы; обрабатывать HID в доступном main loop. Начальная загрузка, FrameEnd, GSP/SD/APT всё ещё могут блокироваться: план не обещает отсутствия hard hang. Если запись SD зависнет после окна, последняя сохранённая фаза сама не докажет GPU hang. Независимый watchdog со своим файлом рассматривать только при фактическом подтверждении SD-сбоя, не добавлять сейчас наугад.

| Что покажет один запуск | Следующий обоснованный вывод |
|---|---|
| Submit Result error или live submitted<3 | Сначала dispatch/GSP/SDK submission; ещё не «GPU не дорисовал» |
| submitted3, PSC0 и PPF доставлены, P3D нет | PICA completion/P3D delivery — основной кандидат; разобрать сохранённые PICA words. PPF не доказывает завершение PICA |
| submitted3, PSC0 и P3D есть, PPF нет | DISPLAY/PPF delivery — основной кандидат |
| P3D и PPF есть, PSC0 нет | Dual-buffer FILL/PSC0 delivery; PSC1 не заменяет PSC0 в SDK accounting |
| PSC0/P3D/PPF есть, а running/counters устойчиво не сходятся | Проверять attribution, races/accounting и согласованность снимков. Один snapshot не атомарен относительно SDK |
| queue idle/3-3-3, а VBlank перестал двигаться | Event-thread/onQueueFinish/swap/VBlank notification, не автоматически PICA stall |
| queue idle и VBlank движется; Begin(NONBLOCK) успешен | Незавершение GX в измеренном окне не воспроизведено; искать различия unbounded wait/SD/timing, не объявлять NONBLOCK исправлением |
| Все completion callbacks отсутствуют | Не локализована ни одна команда; отличать dispatch, event thread и отсутствие уведомлений по submit/VBlank/runtime snapshots |

Отсутствующий callback не различает физическое незавершение и потерю/блокировку уведомления. Если после этого остаётся именно такая неоднозначность, не запускать серию вариантов: сохранить результат и решить, нужен ли один дополнительный контроль того же пути с stock PICA/resource setup либо безопасное чтение status через проверенный SDK. Сейчас такой второй контроль не выпускается и не требуется для первого наблюдения.

Текущим этапом ограничиваемся архивированием, исходниками/ELF и планом. Без новых CIA, runtime/аппаратных тестов, изменений backend, RGB565, больших ARM suites или push.
