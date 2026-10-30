# Официальный simple_tri и аппаратный CLEAR control — 30.10.2026

Первопричина аппаратного FAIL пока не установлена. Ошибок DS34, требующих исправления по результатам этого сравнения, не доказано; backend/SDK/control не изменялись. Счётчик GX 1/2 по-прежнему не определяет конкретную зависшую команду. Нового аппаратного результата observer v0.1.1 нет.

Зафиксирован devkitPro/3ds-examples **be2001fee08cf8ec7d3366e095e83f6f75da8942**. `upstream.json` содержит URL и SHA256 всех полученных файлов. `main.c`, `vshader.v.pica`, Makefile и immediate/main.c сохранены побайтно. Сборка использует прежние libctru2.7.0-1 и Citro3D1.7.1, commit9f21cf7b380ce6f9e01a0420f19f0763e5443ca7. Правок SDK нет.

| Участок | Официальные simple_tri / immediate | Наш CLEAR control | Значение различия |
|---|---|---|---|
| Начало | gfxInitDefault → C3D_Init(DEFAULT) → target → sceneInit | gfxInitDefault → bottom console → TOP RGB565/swap → A → C3D_Init → target | Иной порядок подготовки LCD и дополнительные обращения console/SD могут менять timing. Ошибка не доказана. |
| Gfx framebuffer | gfxInitDefault: TOP/BOTTOM RGB8, linear FCRAM | TOP переключён в RGB565; bottom console | Выходная плотность пикселей и stride различны. |
| Render target | 240×400 RGBA8 + D24S8 | 240×400 RGB8 + D24S8 | Color384000 против288000 bytes, depth384000 в обоих случаях; меняются режим fill и граница color allocation. |
| VRAM | C3D_RenderTargetCreate → vramAlloc color, depth сначала в противоположном банке | Тот же SDK allocator и политика банков | Не предполагаем одинаковые runtime адреса в разных процессах. Alignment SDK128, размеры всех этих буферов кратны128. |
| Clear | C3D_RenderTargetClear(ALL,0x68B0D8FF,0) | ALL,0x00102030,0 | Оба идут через C3D_FrameBufClear/GX_MemoryFill, не CPU memset VRAM. |
| Fill controls | color0x0201/depth0x0201 (32-bit) | color0x0101 (24-bit)/depth0x0201 | Это реальное различие аппаратного пути, но корректное кодирование SDK; оно не доказывает неисправность24-bit fill. |
| Transfer | RGBA8 → RGB8, flags0x1000 | RGB8 → RGB565, flags0x2100 | В обоих случаях flip/raw/tiled-output/scaling выключены; input/output dims0x019000f0. Комбинации согласованы с framebuffer форматами. |
| Кадр | FrameBegin(SYNCDRAW) → clear → FrameDrawOn → draw → FrameEnd(0) | bounded VBlank → FrameBegin(NONBLOCK), clear → FrameDrawOn → FrameEnd(0) | Стандартный пример содержит PICA draw; это не изоляция одной команды CLEAR. |
| Очередь | SDK FILL → PICA → DISPLAY; максимум3 in flight | CLEAR: FILL → DISPLAY | Успех simple_tri не определяет, какое IRQ отсутствовало в старом CLEAR. |
| Cache | FrameEnd(0): SDK flush всего linear heap до gxCmdQueueRun | Та же функция/флаги; readback invalidate только после retirement | Добавлять новый flush наугад оснований нет. В stock примере CPU readback отсутствует. |
| Completion | SDK GX IRQ handler → queue accounting → SDK onQueueFinish/swap; блокирующий wait | Тот же handler/onQueueFinish, ограниченный poll, дополнительные диагностические Run/Submit wrappers | В stock ELF нет wrappers и event callbacks приложения. Формат/время/обвязка одновременно различны: пока это список кандидатов, не локализованная причина. |
| Завершение | sceneExit освобождает VBO/program, затем C3D_Fini/gfxExit | Наш control удерживает GPU memory, пока queue pending | Upstream оставлен без изменений; его ожидания не ограничены и он не содержит защиты от прежнего аппаратного зависания. |
| Сборка | Upstream Makefile собирает .3dsx, собственного RSF/CIA нет | Наш RSF Application/Legacy64MB/stack256KiB/VRAM:r | Нельзя назвать наш CIA-профиль «официальным». |

Точная расчётная цепочка stock (c/d/f — адреса color/depth/gfx, не аппаратный capture):

```c
GX_MemoryFill(c, 0x68B0D8FF, c+384000, 0x0201,
              d, 0,          d+384000, 0x0201); // byte offsets
GX_ProcessCommandList(...); // сформирован SDK для настоящего triangle draw
GX_DisplayTransfer(c, 0x019000f0, f, 0x019000f0, 0x1000);
```

`FrameEnd(0)` формирует DISPLAY после cache flush и запускает SDK gxCmdQueueRun. Следующий SYNCDRAW сначала синхронизирует VBlank, затем ждёт gxCmdQueueWait(queue,-1), Stop/Clear выполняются только после completion. libctru2.7.0 увеличивает lastEntry по PSC0/PPF/P3D/DMA, игнорирует PSC1/VBlank; привязки IRQ к конкретному command ID нет. Используем уже сохранённый аудит, не повторяем его эксперименты.

`immediate` подтверждает тот же RGBA8/RGB8, clear, render target и цикл кадра; отличается способом подачи треугольника. Он изучен статически, отдельная сборка/аппаратный запуск не делались. c3dgl — дополнительная OpenGL1.1-обвязка Citro3D; не используется в этом контроле и не является доказанным исправлением общего CLEAR пути.

Собран один ELF с неизменёнными main/shader, без console, SD logger, A gate, callbacks, wrappers или fault injection. GNU make отсутствует; Python воспроизводит CFLAGS/ASFLAGS/LDFLAGS/bin2s/3dsxtool правила сохранённого Makefile. Отличие поиска библиотек — явный путь к прежнему pinned Citro3D. Компилятор/архитектура прежние; upstream тоже использует hard-float ARMv6K, дополнительного отличия ABI здесь нет. Из ELF создан штатный3DSX, затем отдельная CIA с **тем же ELF**, прежним RSF AccessControl/SystemControl и новым TitleID000400000FDE6A00. Отличаются только упаковка/метаданные, исходники не меняются между вариантами.

В Azahar2126.2 software LCD PASS для3DSX и extracted CIA NCCH. На frontend observations60/90/120:16000 белых,79999 голубых пикселей и один чёрный угол(399,0). Этот пиксель сохранён, причина не установлена; кадры двух вариантов идентичны, это не заявление о побитово идеальном framebuffer. Цикл1 остановлен строгой host-проверкой ровно двух цветов; cycle1.json/PNG сохранены. Цикл2 допускает только точно этот дополнительный пиксель с явным отчётом, и проверяет остальную картинку. GPU исходники/сборка между циклами не менялись. Invalid memory accesses в host logs0. Есть ожидаемые Azahar service stubs, включая ConfigureNew3DSCPU: отчёты не заявляют отсутствие всех сообщений Error. После START guest вызвал GSP ReleaseRight и освободил heap; libretro shutdown callback не пришёл. Реальная установка FBI и возврат в настоящий HBL не проверены.

Azahar различает среды запуска: в3DSX linear heap0x30000000, main heap0x05be6000 bytes; в CIA linear heap0x14000000, main heap0x01faa000, linear allocation0x02000000 в обоих. Это наблюдение эмулятора, не обещание адресов/профиля настоящего HBL. Пара не изолирует только SystemMode: меняются loader permissions/address layout/runtime environment. Поэтому не выпускалась третья CIA с угаданными правами или иным memory mode.

Следующий минимальный аппаратный тест к отдельному согласованию: **только stock3DSX через Homebrew Launcher**, одно открытие, фото верхнего экрана и результат START. Рендер начинается немедленно, без A; при той же аппаратной проблеме возможно полное зависание, штатный timeout отсутствует. Это проверяет базовый SDK/консоль/HBL без нашего CIA-профиля и диагностической обвязки. PASS позволит следующим отдельным тестом сравнить тот же ELF в подготовленной CIA; FAIL не локализует fill/transfer/IRQ, для этого уже подготовлен observer v0.1.1. Оба варианта пока hardware NOT TESTED и самостоятельно не запускаются. Игра/DS34 не менялись.

Источники: [simple_tri](https://github.com/devkitPro/3ds-examples/blob/be2001fee08cf8ec7d3366e095e83f6f75da8942/graphics/gpu/simple_tri/source/main.c), [Makefile](https://github.com/devkitPro/3ds-examples/blob/be2001fee08cf8ec7d3366e095e83f6f75da8942/graphics/gpu/simple_tri/Makefile), [immediate](https://github.com/devkitPro/3ds-examples/blob/be2001fee08cf8ec7d3366e095e83f6f75da8942/graphics/gpu/immediate/source/main.c), [libctru2.7.0 gxqueue](https://github.com/devkitPro/libctru/blob/v2.7.0/libctru/source/gpu/gxqueue.c), [Citro3D framebuffer](https://github.com/devkitPro/citro3d/blob/9f21cf7b380ce6f9e01a0420f19f0763e5443ca7/source/framebuffer.c), [renderqueue](https://github.com/devkitPro/citro3d/blob/9f21cf7b380ce6f9e01a0420f19f0763e5443ca7/source/renderqueue.c), [c3dgl](https://github.com/SomeRandoLameo/c3dgl).
