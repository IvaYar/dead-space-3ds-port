# Графический контекст и настоящая очистка framebuffer

**Актуальное продолжение:** [LIGHTING.ru.md](LIGHTING.ru.md) и [DEFAULT-SURFACE.ru.md](DEFAULT-SURFACE.ru.md).551 ARM-тест, настоящая геометрия коридора в промежуточном кадре; завершённый2605-й кадр чёрный. Этот документ сохраняет исторический checkpoint контекста/clear.

Первый запрос игры `glGetIntegerv(GL_VIEWPORT)` обслуживает действующий контекст с размерами прикреплённой поверхности. В предыдущем checkpoint Unicorn и Azahar проходили запросы активных texture selectors и останавливались на **`glIsEnabled(GL_NORMAL_ARRAY)`**, enum `0x8075`, во втором NativeOnDrawFrame. Ранее этот enum ошибочно назван COLOR_ARRAY; название исправлено. Игрового кадра и меню пока нет.

## Реализованный слой

`ds13_gles.c/h` хранит viewport, scissor, текущие server/client texture selectors, цвет очистки, color mask, clear depth/stencil, dither и GL error. Выбран один current context с сериализованным доступом; pixel buffer заимствован у владельца поверхности. Размеры проверяются, выход за ёмкость буфера отклоняется, повторная инициализация текущего контекста запрещена.

Есть 18 привязок: glGetError, glGetIntegerv, glViewport, glScissor, glEnable/Disable/IsEnabled для выбранных capabilities, glClearColor/x, glColorMask, glClearDepthf/x, glClearStencil, glClear, glFlush/Finish, glActiveTexture и glClientActiveTexture. **Это ограниченный набор состояния и software clear, не полная реализация GLES.** Texture selectors 0/1 являются состоянием контекста; изображений текстур и операций upload/draw ещё нет. Неизвестные enums в audit-режиме приводят к явной остановке, а не к фиктивному успешному ответу.

Очистка действительно записывает пиксели, учитывает scissor и RGB write masks, обрезает область по поверхности и корректно обрабатывает большие/отрицательные координаты без переполнения. Viewport не ограничивает clear — это отдельно проверено по контракту GLES. Alpha/depth/stencil attachments отсутствуют; соответствующие размеры равны нулю, очистка отсутствующих плоскостей не пишет цветовой буфер. Ошибка GL сохраняется до glGetError; первый error не затирается следующим.

Поддержаны линейный RGB8, повёрнутый BGR8 и **повёрнутый RGB565**, который фактически использует диагностическая console Azahar. Формат консоли не меняется, её allocation не освобождается. При смене backbuffer через gfxSwapBuffers контекст получает новый pointer с проверкой ёмкости. Native flush hook вызывает GSPGPU_FlushDataCache; неудачный flush сообщает ошибку вместо успешного завершения. CPU clear синхронный, очереди GPU-команд здесь нет.

## Проверка реальной поверхности

Перед запуском оригинального кода graphics-сценарий очищает framebuffer в чёрный и записывает зелёный scissor 40×30. Проверяются пиксели внутри/снаружи области и viewport, затем состояние и счётчики сбрасываются для отдельного учёта вызовов игры.

```text
GLES surface probe: OK 400x240; black clear + green scissor; pixels=97200 format=2
GLES context bindings: 18; software clear only
...
STOP GLES state: glIsEnabled unsupported enum=00008075
GLES counters: queries=3 clears=0 pixels=0 flushes=0
Sensor shutdown: result=0 active=0 events=0 delay=3
Phase: NativeOnDrawFrame
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

97200 записей — 96000 пикселей полной очистки плюс 1200 scissor-пикселей. Это **собственная изолированная проверка**, не отрисовка игры. Сама игра пока сделала три glGetIntegerv и ни одного glClear. Счётчик queries относится к glGetIntegerv; неподдержанный glIsEnabled останавливается отдельно. Разница RGB8 в CPU-модели и RGB565 native-поверхности отражена в конфигурации, а не скрыта.

Прошли **17 новых ARM-тестов**: состояние поверхности, error/reset, изменение viewport, ограничения scissor, color masks, RGB565 quantization, повёрнутый layout, retargeting, сбой flush и отдельно скомпилированный softfp-модуль с настоящими импортами glClearColor/glClearColorx. Padding вокруг pixel buffer остаётся целым.

На текущей сборке повторно прошли все 183 core-теста и девять engine-сценариев Azahar. Дополнительно сохраняются валидные свидетельства 14 sensor-тестов отдельного ELF и native HID-проверки. Итого 197 ARM-тестов двух ELF. Хеши source/output и hardware stage8 backend сверены checker-скриптами. Native RX/кэш и исторические CIA не менялись, графический audit всё ещё отказывается работать на настоящей консоли.

## Режимы и повторение

Обычный protected baseline сохраняет прежний отказ перед датчиком; sensor-only режим — отказ на GL_VIEWPORT. Новый **graphics** включает датчик и графический контекст в приватной SD Azahar; после теста его маркеры удаляются. Ресурсы оригинальной игры не изменяются.

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_gles_state.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

Azahar-сценарии выполнять последовательно. Полный набор после изменения core: test_emulator_runtime.py, test_jni10.py, test_platform_jni.py, test_sensor_jni.py, test_gles_state.py; затем три CPU-трассы и девять smoke-сценариев. Свидетельства — `analysis/gles-tests.json`, `analysis/engine-graphics-entry.json`, `analysis/azahar-smoke/engine-graphics.log`, итог — `analysis/engine-progress.json`.

## Дальнейшая работа

Следующий блок — состояния client vertex arrays, их descriptors/buffer objects и дальнейшая трассировка до первых ресурсных/рисующих операций. Потребуются текстуры, матрицы и реальная геометрия с последующим backend PICA200/citro3d. Нельзя считать get-state/clear готовым renderer или делать выводы о FPS игры. Кадр, shader pipeline, texture uploads и hardware-осевые преобразования сенсора ещё не проверены.

Базовый production preflight намеренно остаётся 152/236/4 с неизменённым образом при отказе; 18 GL-привязок добавляются только после него в экспериментальном graphics-режиме. Это не повод считать оставшиеся отсутствующие импорты реализованными. GitHub не обновлялся; дальнейшая отправка только по явной просьбе пользователя.

Первичные описания контракта: Khronos [glViewport](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glViewport.xml), [glClear](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glClear.xml), [glGet](https://github.com/KhronosGroup/OpenGL-Refpages/blob/main/es1.1/glGet.xml). Формат native-поверхности и функция получения backbuffer проверены по локальному libctru 2.7.0 и фактическому результату Azahar.
