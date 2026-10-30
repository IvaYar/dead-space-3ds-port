# Citro3D Control v0.1.0 — независимый clear/triangle

Это подготовленный контрольный тест, **не исправление DS34**. Он проверен в Azahar. Аппаратный запуск ещё не выполнялся и требует отдельного разрешения пользователя. Прежняя проблема GX/PICA200 не объявляется устранённой; при настоящем GPU stall может снова потребоваться выключение POWER.

Гипотеза: базовый путь pinned Citro3D/libctru под тем же CIA-профилем способен завершить очистку/перенос framebuffer, затем простой PICA draw без состояния DS34. Тест связывает только собственный standalone C entry point и стандартные SDK-библиотеки: GLES, DS34, original engine, APK/.so и игровые ресурсы отсутствуют.

Используется прямой API по структуре официального [devkitPro simple_tri](https://github.com/devkitPro/3ds-examples/tree/master/graphics/gpu/simple_tri): linear VBO с тремя позициями float3, фиксированный белый RGBA attribute, projection, position/color shader и TEV PRIMARY_COLOR/REPLACE. Отличия от примера явно ограничены: RGB8 render target и RGB565 output для совпадения с DS34, два конечных этапа вместо непрерывного цикла, журнал/A gate/ограниченные ожидания/readback. Это адаптированный контроль, а не неизменённая сборка upstream-примера.

Совпадают с DS34 v0.1.3: хеши библиотек SDK, compiler architecture/options, Legacy64MB, stack256KiB, read-only CPU VRAM, AccessControl/SystemControl RSF, бинарные ARM11 local/kernel/ARM9 capability bytes кроме Program ID, target240×400 RGB8/D24S8, TOP RGB565, transfer flags0x2100. Даже слова команды FILL в контрольном треугольнике совпадают с аппаратным DS34 capture. Отдельный Title ID **000400000FDE6900**, Product Code CTR-H-C3DC; прежний DS34 Test не заменяется.

Расположение выделений памяти не обязано совпадать: нет дополнительного runtime heap8MiB, packed vertex stream DS34 и white dummy texture. Shader, attributes, sampler и часть pipeline state отличаются намеренно. Совпадение Memory profile не доказывает правильность всех DS34 resource addresses/cache contents.

Проверки выполняются за два кадра:

1. **CLEAR:** FILL → DISPLAY. Инициализация shader/VBO и PICA draw ещё не выполнялись. Полученный framebuffer должен быть однотонным тёмным RGB(16,32,48).
2. **TRIANGLE:** FILL → PICA → DISPLAY. Белый треугольник по центру на том же фоне; input VBO из36 bytes проверяется после завершения. Текстуры не включаются.

Если CLEAR не проходит, искать basic fill/transfer, профиль/SDK и completion до DS34 shader/UV. Если CLEAR проходит, а TRIANGLE нет — минимальный SDK PICA/resource путь всё ещё не подтверждён. Если оба проходят на железе — базовый SDK/profile работает, дальше по одной гипотезе изолировать отличия DS34. Ни один исход сам по себе не доказывает конкретную ошибку DS34.

После отдельного разрешения на аппаратный запуск:

1. Установить `citro3d-control-v0.1.0.cia` и открыть **Citro3D Control**. До A GPU-проверки не запускаются; START выходит.
2. Нажать A один раз. Ожидать CLEAR PASS, TRIANGLE PASS, CONTROL PASSED. При ошибке сохранить последнее сообщение.
3. Нажать START для проверяемого выхода. Пока GX queue busy, память сохраняется, C3D_Fini не вызывается; обычный выход тогда может остаться недоступен.
4. Скопировать всю папку `SD:/3ds/citro3d-control-v0.1.0/`: control.log, result.json, stage-*-queue.json, *.pica, triangle-vertices.bin и clear/triangle.raw, если появились. Прежние DS34 папки не изменяются. Ориентироваться на stages_completed текущего result, а не на старые raw-файлы.

VBlank и FrameBegin(NONBLOCK) ограничены2000 мс. После таймаута тест останавливается до readback и не освобождает активную GPU память. Не все операции ограничены таймаутом: SDK FrameEnd, GSP/SD-вызовы, APT и финальное освобождение после idle check могут блокироваться. Пример не гарантирует восстановления после произвольного аппаратного hang.

Сохранение CPU framebuffer использует проверенный RGB565 column-major путь и cache invalidation после реального queue retirement; неисправный OpenGL capture не используется. В validation — именно данные Azahar для payload этой CIA, не native PASS. Fault-проверка использует другую, не распространяемую emulator-only сборку: искусственно отказывает ожиданию после CLEAR, сохраняет failure JSON и проверяет выход после настоящего idle check. Она не имитирует электрическое/аппаратное зависание GPU.

Воспроизведение подготовки (только ПК/Azahar):

```powershell
python porting/tools/build_citro3d_control.py
python porting/tests/smoke_citro3d_control.py
python porting/tools/build_citro3d_control.py --fault-test
python porting/tests/smoke_citro3d_control.py --fault-test
python porting/tools/compare_citro3d_control.py
python porting/tools/package_citro3d_control.py
```
