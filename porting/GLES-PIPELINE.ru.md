# Состояния pipeline и первая загруженная текстура игры

**Следующий результат:** [ANDROID-JUMP.ru.md](ANDROID-JUMP.ru.md) — setjmp/longjmp реализованы и проверены; оба эмулятора прошли прежний барьер и остановились на JNI NewString UTF-16 /slot163. Теперь253 core-теста, strict preflight154/234/4; первый игровой upload сохранён. Ниже предыдущий checkpoint.

**Unicorn и Azahar загрузили первую текстуру, переданную оригинальным движком:** 512×512 RGBA/UNSIGNED_BYTE, 1 048 576 байт. CRC32 CPU-store `a738ea1c` совпадает с исходным буфером игры в Unicorn и с CPU-store в native-проверке Azahar. Это первый подтверждённый игровой texture upload, а не собственный тестовый рисунок. Изображения игры на экране ещё нет: треугольники и texture sampling не реализованы.

Прежний барьер `glIsEnabled(GL_CULL_FACE)` пройден. Новая остановка в обоих эмуляторах — **`setjmp`**, caller offset `0x00397168`, второй `NativeOnDrawFrame`. Аудит завершает выполнение перед отсутствующим импортом; подставлять вместо него возврат 0 нельзя.

## Изменения

`ds16_pipeline.c/h` хранит состояние culling/front-face, depth function/write mask/range, alpha function/reference, blend factors, shade model, polygon offset и stencil function/masks/operations. Enable/Disable/IsEnabled и integer queries согласованы с этим состоянием. Также сохраняются флаги lighting, отдельных LIGHT0–7, color material и normalize/rescale normal. Расчёта освещения пока нет. Неподдерживаемые состояния продолжают явно останавливать аудит.

Добавлены 18 GL entry points, всего теперь **67 opt-in привязок**. Помимо setters, реализованы GetFloatv/GetFixedv/GetBooleanv для уже поддержанных состояний контекста. Запросы сохраняют число компонентов и конвертируют типы: fixed enum возвращается без масштабирования, boolean в fixed — 0 или 65536; выходящие за диапазон значения насыщаются. Unknown/null queries не записывают фиктивные значения. Значения alpha/depth range ограничиваются [0,1]; перевёрнутый depth range разрешён. Ref stencil clamped к нулю, поскольку текущая поверхность имеет **0 stencil bits**.

Внутренние CPU helpers проверяют направление грани, восемь alpha/depth comparisons и рассчитывают blending с ограничением результата и SRC_ALPHA_SATURATE. Они проверены самостоятельно, но ещё не подключены к rasterizer. Нет новых depth/stencil attachments, stencil/lighting renderer или draw API. Сохранение состояния и проверка арифметики не означают появления игровой сцены. Очистка цвета по-прежнему не зависит от cull/alpha/depth/blend tests.

Для Unicorn лимит отслеживаемых runtime allocations увеличен с 1 до **4 MiB**, как в native-аудите Azahar: старый лимит ошибочно не оставлял места для RGBA-store размером 1 MiB вместе с прочими живыми выделениями. Это диагностический лимит allocator, не измеренная память приставки. Test-only newlib heap Unicorn остаётся 2 MiB и не воспроизводит весь native heap; полная эквивалентность распределения памяти не заявляется. Production preflight неизменен: **152 resolved /236 missing /4 weak-zero**. Все GL-привязки подключаются только после его отказа в graphics-режиме.

`ds15_level` даёт внутренний заимствованный immutable view изображения для будущего renderer/диагностики; его lifetime заканчивается при replacement/delete/close. CPU-аудит записывает GL arguments и CRC входных RGBA-пикселей до upload, затем сверяет их с сохранённым изображением. Native-аудит вычисляет CRC из своего store независимо. GL error в точке остановки — 0.

## Проверки

Прошли **18 новых ARM-тестов**: default/mutated state, независимые enable flags, cull direction/modes, все alpha comparisons, depth comparisons/range/mask, blending/aliasing/clamping, enum validation с сохранением прежнего состояния, stencil state, typed vector queries и их размеры, насыщение fixed, unknown queries и прежняя семантика Clear. Отдельный Android softfp ELF проверяет вызовы с float/enum аргументами и typed getters через загрузчик.

В Azahar собственный native probe проверил две классификации граней, два alpha comparison, четыре компонента blend и typed query. Перед входом в игру его состояния сбрасываются. Ниже **последующий путь оригинального движка**:

```text
GLES context bindings: 67; software clear only
...
STOP unsupported: setjmp
Phase: NativeOnDrawFrame
Caller offset: 00397168
GLES error at stop: 00000000
GLES counters: queries=7 clears=0 pixels=0 flushes=0
GLES texture stores: names=1 bytes=1048576 uploads=1 patches=0
GLES first texture: 512x512 format=1908 bytes=1048576 CRC32=a738ea1c
Sensor shutdown: result=0 active=0 events=0 delay=3
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

На одной текущей core-сборке повторно прошли **240 ARM-тестов**: 122 runtime +20 JNI +16 platform +8 sensor/JNI +17 GLES +17 arrays +22 textures +18 pipeline. Свидетельства отдельного sensor ELF на 14 тестов остаются валидны: **254 теста двух сборок**. Все девять engine-сценариев Azahar прошли на текущем CXI, три CPU-режима пересозданы, оба checker проверили hashes. Hardware stage8 RX/cache не менялись. **Новых CIA и проверок на приставке нет.**

## Продолжение

Следующий блок — исследовать путь `setjmp` и совместимость Android ARM32 `jmp_buf`/`longjmp`: размер и layout, callee-saved registers, SP/LR, softfp/VFP, сохранение контекста и возврат в исходный frame. Не связывать Android буфер напрямую с native libc без проверки ABI и не заменять nonlocal jump заглушкой. После него продолжать по фактически наблюдаемому пути движка. Матрицы, геометрия, PICA200/citro3d, texture sampling и звук остаются впереди.

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_pipeline.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

После пересборки core повторять семь предыдущих test-скриптов, три CPU-режима и девять smoke-cases. Azahar запускать последовательно из-за общей приватной SD. Свидетельства: `analysis/pipeline-tests.json`, `analysis/engine-graphics-entry.json`, `analysis/azahar-smoke/engine-graphics.log`, `analysis/engine-progress.json`. Последний из них содержит данные первого игрового upload и совпадение CRC.

Контракты состояния, conversions и blending: Khronos [GLES 1.1 §3–4 и §6.1](https://registry.khronos.org/OpenGL/specs/es/1.1/es_full_spec_1.1.pdf), [AlphaFunc](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glAlphaFunc.xml), [BlendFunc](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glBlendFunc.xml). Это реализация части API, не полный GLES renderer.

Все изменения локальные. GitHub обновлять только по прямому запросу пользователя.
