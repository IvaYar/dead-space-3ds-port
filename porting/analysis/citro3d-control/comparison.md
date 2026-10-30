# Сравнение независимого контроля и DS34 v0.1.3

Контроль прошёл только Azahar. Аппаратный исход ещё неизвестен; подтверждённого исправления DS34 нет.

| Участок | DS34 v0.1.3 | Независимый контроль |
|---|---|---|
| Код | GLES/DS22/DS34 + собственное состояние | Один standalone C-файл, прямой Citro3D API |
| SDK и CIA | Pinned Citro3D/libctru, Legacy64MB, stack256KiB, CPU VRAM read-only | Те же SHA библиотек; одинаковые RSF Access/SystemControl и бинарные capability bytes кроме Program ID |
| Framebuffer | 240×400 RGB8/D24S8, TOP RGB565 | То же; слова FILL совпадают с native capture, transfer отличается допустимым адресом CPU backbuffer |
| Vertex input | Четыре float4, stride64, stream base physical | Одна float3 позиция, stride12, фиксированный белый RGBA, штатный BufInfo_Init base |
| Shader output | Position/color + два UV | Position/color; W принудительно1 |
| Samplers | Валидная white texture на unit1 даже при отключённой GLES-стадии | Все отключены; texture upload отсутствует |
| Pipeline | GLES-настройки depth/blend/cull/scissor | Стандартные значения Citro3D и TEV PRIMARY_COLOR/REPLACE |
| Cache | Flush stream + общий flush linear heap в FrameEnd(0); invalidate после retirement | Общий flush linear heap тем же FrameEnd(0), проверка VBO после retirement, тот же invalidate readback |
| Clear queue | В общем первом кадре FILL/PICA/DISPLAY | Сначала отдельно FILL/DISPLAY без shader/VBO/PICA, затем FILL/PICA/DISPLAY |
| Completion | Две VBlank-синхронизации и bounded NONBLOCK begin; native3 submitted/1 complete | Bounded эквивалент SDK SYNCDRAW через counters/NONBLOCK; Azahar retirement обоих этапов, checked START exit |
| Lifetime | Память сохраняется до queue completion, выход deferred если busy | То же требование; никакого освобождения по одному лишь таймауту |

Это различия для будущего изолирования, а не список доказанных ошибок. Совпадение профиля памяти не означает одинаковое размещение всех объектов: runtime heap/большой stream/dummy texture DS34 в контроле отсутствуют.

Исходы одного разрешённого аппаратного контроля:

- CLEAR FAILED: PICA draw отсутствует; сначала проверять базовые fill/transfer/SDK/profile/completion.
- CLEAR PASS, TRIANGLE FAILED: минимальный штатный PICA/resource путь ещё не подтверждён; переносить исправления в DS34 рано.
- Оба PASS: базовый native SDK/profile работает; дальше по одной гипотезе проверять отмеченные DS34 state/resource отличия.

Пакет не является предполагаемым GPU-исправлением. Основа схемы треугольника — официальный [devkitPro simple_tri](https://github.com/devkitPro/3ds-examples/tree/master/graphics/gpu/simple_tri); фактическая проверка/сравнение регистров сохранены в comparison.json и двух emulator result.json.
