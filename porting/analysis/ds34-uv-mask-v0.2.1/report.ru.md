# DS34 PICA: неполная запись UV-выходов, 31.10.2026

На ветке `test/ds34-full-output-mask` подготовлен один изолированный вариант. **Аппаратных запусков и push нет.** HEAD при начале `d30fcc5`; исходные незакоммиченные изменения сохранены. Прочитаны актуальные HANDOFF, native GX Watch run-0001, предыдущий queue audit и подтверждения аппаратного simple_tri 3DSX/CIA. Исследования RGB565/basic FILL не повторялись.

## Конкретное отличие и граница доказательства

В аппаратном DS34 dump загружены именно восемь инструкций и семь descriptors сохранённого DS34 SHBIN. В DVLE выходы `o0…o3` объявлены с mask `0xF`. Инструкции записывают `o0.xyzw`, `o1.xyzw`, **только `o2.xy` и `o3.xy`**. Следовательно, `o2.zw/o3.zw` за всю invocation не записываются. Это проверено по machine words и descriptors, а не только по shader source. У аппаратно успешного simple_tri оба выхода полностью записываются по одному разу.

| Выход | DVLE mask | DS34 число записей x/y/z/w | Вариант |
|---|---:|---|---|
| o0 position | F | 1/1/1/1 | прежнее |
| o1 color | F | 1/1/1/1 | прежнее |
| o2 UV0 | F | 1/1/0/0 | 1/1/1/1 |
| o3 UV1 | F | 1/1/0/0 | 1/1/1/1 |

Реальная PICA имеет требование однократной записи настроенных выходных компонент; нарушение может остановить GPU: [3dbrew GPU/Pitfalls](https://www.3dbrew.org/wiki/GPU/Pitfalls#Configued_Output_components_must_be_written_exactly_once). В DS34 VSH_OUTMAP_MASK=`0xF` включает все четыре output registers, SH_OUTMAP_TOTAL=4, totals1/2=3, CLOCK=`0x303`. Маршрутизация `o2=1F1F0D0C`, `o3=1F1F0F0E` означает, что rasterizer использует только UV.xy. Это не эквивалентно записи VSH.zw. [Официальный simple_tri shader](https://github.com/devkitPro/3ds-examples/blob/be2001fee08cf8ec7d3366e095e83f6f75da8942/graphics/gpu/simple_tri/source/vshader.v.pica) пишет все компоненты обоих выходов; официальный textured_cube также делает full-register `mov outtc0, intex`.

Дополнительная локальная подсказка: `analysis/gpu-research/c3dgl/shaders/c3dgl.v.pica:88` специально записывает неиспользуемую outtc0.w с комментарием о hardware hang при неполной записи output registers. Его README явно говорит, что проект не испытан на железе; этот комментарий **не самостоятельное аппаратное доказательство**. Основание теста — точное расхождение masks в нашем реальном dump и аппаратное ограничение, а не чужой emulator PASS.

**Доказано несовпадение объявленных и записанных компонент. Причинность именно native run-0001 ещё не доказана.** Предположение: PICA не заканчивает vertex output, DRAWARRAYS не retired, command processor не достигает FINALIZE/P3D; DISPLAY не получает завершения как следствие незавершённого PICA. Это объяснение согласуется с наблюдением PSC0=1/P3D=PPF=0/queue3/3/1, но физические GPU status не измерены. Новая сборка проверяет, достаточно ли полной записи UV для устранения отказа.

## Сравнение участка PICA

| Участок | Аппаратно успешный официальный simple_tri | DS34 GX Watch native run-0001 | Вывод |
|---|---|---|---|
| SDK/init | gfxInitDefault, C3D_Init, pinned Citro3D1.7.1/libctru2.7.0 | те же libs и C3D_Init; дополнительно BOTTOM console, runtime, upload white | Общую неисправность SDK/profile stock PASS не поддерживает |
| Command memory | C3D default 0x40000 linear bytes; FrameEnd(0) | тот же allocator/размер; cmd pointer14189C00,1168 bytes | 16-byte alignment,82 bounded packets, finalization присутствуют |
| Submit/flush | FrameEnd формирует очередь, flush всего linear heap до Run | тот же CPU-код SDK; дополнительно explicit vertex flush384 bytes | Отсутствующего command-list flush по source нет; native cache visibility не измерена |
| Shader/program | 8 instructions, position+color, scratch r0, constants, 2 full outputs | 8 instructions, projection c0…c3, scale c4,4 outputs; UV partial | Найдено конкретное расхождение покрытия output writes |
| Uniforms | OrthoTilt, projection + shader constants | OrthoTilt,20 finite float32 values c0…c4,scale1111 | NaN/Inf в сохранённых uniforms нет |
| Attributes | float3 loader v0 + fixed white v1 | четыре float4 v0…v3; count4,perm3210 | Формат/stride/permutation согласованы |
| Vertex storage | 36 bytes/3 vertices/stride12; default base18000000 + offset | stream524160 bytes; используется384/6/stride64; base201C9C00/offset0 | Нет известного 28-bit offset overflow; native vertex payload отсутствует |
| VBO lifetime | static pointer, free только при выходе | immutable до blocking Begin/retirement; при busy не освобождается | Прежние исправления lifetime сохранены |
| Render buffers | RGBA8+D24S8,384000 bytes каждый, target240×400 | те же размеры; physical18000000/18300000 | Различий размеров/пересечения по текущим данным нет |
| Sampler | нет | white8×8 RGBA8/256 bytes,physical1805DC00,TEXUNIT1 enabled,TEV не использует | Отличие сохранено: не смешивать с UV экспериментом; известный L4 VRAM bug к RGBA8 неприменим |
| White lifetime | нет | linear staging→flush→blocking out-of-frame upload→free | CPU write в VRAM отсутствует; событие upload завершено до arm |
| Draw/pipeline | triangle3; default cull/depth/blend; no scissor | два triangles6; cullnone,depthoff,RGB mask,scissor | Отличия сохранены; не объявляются причиной без проверки |
| Порядок | clear→DrawOn→draw→End | DrawOn→empty Split→clear→draw→End | Split до первого draw пуст; полученный batch всё равно FILL/PICA/DISPLAY |
| Выход | RGBA8→RGB8,flags1000,TOP BGR8 | тот же путь,288000 bytes; observer и readback | Форматный обход уже сделан; повторять RGB565/FILL нет причины |
| Завершение | stock SYNCDRAW и обычный IRQ path, нет native dump/counters | bounded observer поверх того же handler; PSC0 only | Реальные stock GPU addresses и P3D counters не снимались; source-сравнение не выдаётся за native capture |

Финализация, размеры, адреса и lifetime повторно не исследовались широкими тестами: использованы сохранённые отчёты и pinned SDK source. Новый офлайн аудит проверил существенный ранее не проверенный invariant покрытия VSH outputs, соответствие его machine code реальному native upload, finite uniforms и сохранение аппаратных packet constraints. Это специализированный декодер DP4/MUL/MOV/END, **не универсальный валидатор всех допустимых состояний PICA200**.

## Ровно один изменяемый фактор

В shader удалены `.xy` только у destinations двух MUL; sources/swizzles сохранены. Picasso выдаёт тот же280-byte SHBIN с изменениями `7C:AC→AF`, `84:EC→EF`; это `000542AC→000542AF`, `000557EC→000557EF`, mask C→F. Восемь instruction words, DVLE, uniform locations, output maps/clocks не меняются. Никаких новых instructions/uniforms/buffers.

Для максимальной изоляции новый SHBIN заменяет единственное его вхождение в **копии прежнего ELF**: меняются ровно два байта `35C44` и `35C4C`. CPU code, размер ELF, linker layout, allocations, адреса и все существующие observer/IRQ/cache routines побайтно прежние. Новая identity только в CIA packaging. Baseline ELF/SDK/backend/shader source не изменены. Подтверждённое source-исправление находится в отдельном тестовом `3ds/build-ds34-uv-mask-v0.2.1/ds34_gpu.v.pica` и воспроизводимом builder; `shader.diff` рядом с этим отчётом.

В данном случае добавление DS34 shader целиком в stock потребовало бы также менять входы/vertex data/uniforms/output routing. Поэтому выбран меньший эксперимент: исправить только один установленный invariant существующего DS34, сохранив весь остальной native-failed путь. Новая диагностическая обвязка не создавалась.

## Azahar и единственный будущий hardware test

`python porting/tests/smoke_ds34_uv_mask.py` — один новый runtime run, actual extracted NCCH новой CIA, Software renderer. Все24 GX words, включая адреса, совпали с native run-0001. PICA1168 bytes/82 packets отличается **только bytes F0 и F4** (два descriptors). Кадр288000 bytes/96000 pixels полностью совпал с baseline;1draw/2triangles,CPU fragments/samples0,GL0,PSC0/P3D/PPF1/1/1,queue3/3/3 до clear,100ms RAM window,overflow0,criticalIO0. Нет invalid accesses и новых service errors относительно прежнего host log. Обычные stub warnings/ConfigureNew3DSCPU error эмулятора остались прежними. A gate, сохранность старой run-0001 и START→guest GSP release/free heap до host unload PASS. PNG просмотрен.

Эмулятор принимает и старый неполный shader, поэтому этот PASS подтверждает отсутствие наблюдаемой регрессии, **не причинность hardware hang**. Готова отдельная CIA **DS34 UV Mask0.2.1**, TitleID000400000FDE6F00. Runtime версия/SD root оставлены GX Watch0.2.0 для сохранения ELF; новая run-NNNN не переписывает прошлые логи. SHA и инструкция в пакете/manifest/README.

Предлагается к отдельному согласованию один запуск нового варианта: A один раз, сохранить новый run и фото, проверить START. Полный PASS: P3D+PPF,queue3/3/3,Pixel OK,HOME. Это поддержит causal explanation и даст основание перенести две строки в основной shader. Прежние1/0/0 и3/3/1 опровергнут достаточность полной UV-записи как единственного исправления; новый общий диагностический релиз автоматически не следует. P3D без PPF — частичный прогресс, не успех всего пути. Отсутствие достоверных данных — неопределённый результат.

## Приближение к игре

Теперь есть конкретная минимальная shader correction вместо очередной замены всего PICA setup. При hardware PASS сохраняются архитектура DS34, его4×float4 stream, uniforms и sampler; тот же shader может обслуживать исходную игру. **Живой игровой кадр этим не запущен.** Остаются отдельный native engine entry point/import/JNI bootstrap, assets/thread lifetime и затем существующее HID mapping/управление Айзеком. Emulator-only guard не снят. Полные552 теста, старые GPU runtime suites, RGB565, native game launch и git push не выполнялись.
