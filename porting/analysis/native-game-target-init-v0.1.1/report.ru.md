# Начальное содержимое color target: изолированный эксперимент

Исходная причина исследования — [аппаратные run-0002/run-0003](../native-game-prod124-v0.1.0/hardware-runs-0002-0003.ru.md). GPU/backend/shader, оригинальная библиотека, проверки RX/cache, arena92MiB, heaps20+100MiB, Prod124 и кооперативное завершение сохранены. Оригинальный код сам формирует изображение; порт не загружает эталонную картинку.

## Различие

В локальных исходниках используемой Citro3D `source/renderqueue.c:278` создание render target выделяет VRAM и вызывает FrameBufAttrib/Color/Depth/FinishInit без очистки. В исходном startup `graphics_setup`/`ds34_attach` также нет начального заполнения. Donor не гарантирует запись каждого пикселя; точный CRC всего экрана зависит от прежнего содержимого VRAM.

Добавлен wrapper вызова `C3D_RenderTargetCreate`: после успешного создания RGBA8 target240×400 один раз выполняется `C3D_SyncMemoryFill` на384000bytes цветовой поверхности. Control0x0201 задаёт32-bit fill. Заполнение идёт через GPU, **не через CPU memset по read-only VRAM**. По используемым исходникам Citro3D вне FrameBegin оно ждёт PSC0 до возврата, поэтому поверхность готова до первого original draw. Depth не меняется. Это дополнительная операция инициализации ресурса; изменение существующего shader/command list/игровой отрисовки не потребовалось.

Два entry point отличаются только первой строкой `TARGET_INITIAL_RGBA`: poison **0x7f11abff**, black **0x000000ff**. Общие технические изменения: отдельные идентификаторы/log root/appdata и сохранение `comparison-miss.raw` при исчерпании прежних600callbacks. Эти изменения одинаковы в обоих вариантах; исходный CRC и условие PASS не ослаблены. Старый entry point не изменён. `entry.diff` рядом с каждой сборкой содержит полное сравнение.

## Программная проверка

| Вариант | Результат |
|---|---|
| Poison CXI,600 original callbacks | Ожидаемый FAIL полного кадра.33733/96000 пикселей сохраняют исходный цвет BGRab117f. GL0,1209submits/failed0. Safe_exit не запускался. |
| Black CXI,3 последовательных загрузки | 3PASS; baseline96000/96000;6kernel joins/0handles; balanced IO; обе кучи освобождены до host unload. |
| Black actual CIA payload, первая серия | 2PASS; на третьем reload известный host DLL crash до guest READY. Серия не считается PASS. |
| Тот же Black CIA payload, отдельная серия r2 | 3PASS подряд, все проверки кадра/выхода без изменений. |

В успешных циклах checkpoint выбран на callback351/352; кадр совпадает с прежним RGB565 GPU baseline. Проверялись не только CRC, но все96000 пикселей в host runner. Игровые `.raw`/PNG остаются локально и не публикуются. Poison screenshot воспроизводит именно незакрашенные полосы справа/снизу; это диагностическое заполнение, а не вручную нарисованный игровой кадр. У negative теста status blocked/safe_exit=false; такой результат не подменён PASS.

Зафиксирован Windows Event1000 от01.11.2026 00:03:41+08:00: `azahar_libretro.dll`, exception0xc0000005, RVA326ccf — ранее наблюдавшаяся сигнатура h1/p124p. [Запись](initial-CIA-host-crash.json), исходная серия `../azahar-native-game-v0.1.1-black-cia/`. Причина не устранена, связь с очисткой target не доказана; шесть гостевых потоков и ресурсы успешно завершились в двух первых циклах до host reload. Не скрывать этот сбой.

Успешные [CXI](../azahar-native-game-v0.1.1-black-cxi/result.json) и [CIA r2](../azahar-native-game-v0.1.1-black-cia-r2/result.json), [negative metadata](poison-result.json), [release gate](release-gate.json). Повторять эти запуски без новой причины не требуется.

## Память и сохранение baseline

ELF по-прежнему запрашивает normal20MiB, linear100MiB, main stack256KiB. Process commit126611456bytes=120,746MiB, запас до124MiB3411968bytes. Очистка не выделяет дополнительный framebuffer. Kernel2.44, SVC и остальные ACI/AccessDesc permissions совпадают с p124p; SystemModeExt/AccessDesc1/1.261protected files и старая p124p CIA проверены по SHA. Семь generated runtime/GPU/shader файлов совпадают побайтно. Контейнер проверен ctrtool --verify: hash failures нет, только три ожидаемые ошибки homebrew-подписей. RomFS отсутствует, original.so/assets/font/frame в CIA не включены.

## Что остаётся аппаратно неизвестным

Дефект начального содержимого доказан в программном эксперименте; именно он объясняет наблюдаемый шум и может блокировать CRC gate/START. Он **не доказывает**, что в двух аппаратных запусках не было дополнительного сбоя. Нет аппаратного raw, GPU completion gate и lifecycle shutdown. Однократный новый fill и последующий safe_exit на New3DS ещё не испытывались. Ошибки всё ещё переходят в fail-stop с сохранением живых ресурсов; START до FRAME SAVED этим экспериментом не добавлен.

Следующий один отдельно согласованный тест кандидата должен проверить: исчезли шумовые области → сохранён точный оригинальный кадр → START завершает6потоков/GPU и возвращает HOME. Если исчезнет шум, но full-frame или exit снова не пройдут, нужны логи достигнутой стадии, а не очередной автоматический повтор. Никаких hardware запусков, push, новых ARM-suite или изменений Luma не выполнялось.
