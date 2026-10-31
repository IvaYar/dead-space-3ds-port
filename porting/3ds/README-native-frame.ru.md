# DS Native Frame0.1.0 — исходный кадр и safe_exit проверены в Azahar

Актуальный вариант: **`build-native-frame-v0.1.0-s16/native-frame.cxi`**, SHA256 `50feded2db3aad2c5acad7c2d046683d9390224104851c4b1c29d65c98a19d8e`. Все шесть donor workers завершены кооперативно, включая finite loader, два job workers, два audio workers и periodic callback service. GPU backend и аппаратно рабочий shader не менялись.

Три последовательных запуска/выхода в одном Azahar с одной private SD прошли: точное совпадение всех96000 pixels с прежним RGB565 GPU baseline,6 kernel joins,0 worker handles, закрытие всех файлов/JNI, GPU drain, ReleaseRight и освобождение обоих heap при каждом выходе. `passed=true,safe_exit=true`; ошибок памяти/guest exceptions не обнаружено. Это оригинальный startup/UI frame с Айзеком/наушниками, ещё не gameplay.

Точная причина одного затянувшегося ожидания — PCM worker спал `0xffffffff`ms, около49.7суток. Native adapter после original stop flags/events возвращает ему EINTR из interruptible sleep; поток сам читает stop и возвращается. Force terminate не используется. На любом timeout/error ресурсы удерживаются и safe_exit остаётся FAIL. Донор и его арены удерживаются до окончания процесса после остановки пользователей/GPU; in-process reload пока не поддерживается.

[Отчёт по шести потокам](../analysis/native-thread-shutdown/report.ru.md), [software evidence](../analysis/azahar-native-frame-v0.1.0-s16/result.json). Ветка `fix/native-donor-shutdown`. Все r5/s1–s15/hardware результаты сохранены. Для проверки изменений нужен новый revision: builder/runner не перезаписывают существующие manifests/output directories. Runner по умолчанию проверяет три цикла.

**Можно готовить отдельную experimental native-game CIA: software gate открыт. CIA в этом этапе не создавалась, hardware runs/push не выполнялись.** `--cia` требует ≥3 PASS cycles, реальные kernel exits/0handles, balanced files, освобождение обоих heap, отсутствие exceptions и совпадение hashes CXI/исходников/runner. Native RX/cache semantics и исходный кадр на настоящей приставке ещё не проверены. Перед аппаратным запуском нужно его отдельное согласование. Оригинальные `.so/APK/assets` и изображения не включаются в Git/публичные пакеты.

## История r5 — кадр получен, safe_exit тогда был заблокирован

Отдельный entry point `porting/tests/engine_native_frame.c` исполняет оригинальную donor .so через существующие runtime/JNI/GLES модули. `tests/engine_azahar.c` и готовые CPU/GPU baseline не менялись. Текущая проверяемая сборка — `3ds/build-native-frame-v0.1.0-r5/native-frame.cxi`; **это программный кандидат, не готовая к аппаратному запуску игровая CIA**.

Используются аппаратно подтверждённый полный UV shader, RGBA8 target/input, RGB8 output/flags1000, TOP BGR8/288000 bytes. Копия backend содержит прежние согласованные RGBA8/RGB8 замены и закрытие пустого post-present frame при shutdown; основной C backend не переписывался.

Цель задана заранее содержимым сохранённого оригинального GPU baseline callback180: RGB565 CRC32 `ea733050` (тот же кадр сохраняется в callback181…189). Исходный кадр — заставка с Айзеком и рекомендацией использовать наушники, ещё не игровая3D-сцена. Асинхронный loader изменяет номер callback между запусками: новый entry point выполняет настоящие draw callbacks, пока их реальный output не совпадёт с этим изображением, максимум600 callbacks. CRC только выбирает момент остановки; исходные картинки/текстуры поступают из donor/resources, сохранённое изображение в приложение не загружается.

Azahar r5 получил нужный кадр на callback351. После стандартного приведения BGR8 к RGB565 **все96000 pixels совпали побайтно**, различий0. GLES0,CPU fragments/samples0,753 GPU draws/5394 triangles/4 uploads,710 submits без ошибок. Весь checkpoint прошёл GPU retirement/readback/audit. Однако после START `NativeOnPause` и `NativeOnStop` вернулись, а bounded `ds7_shutdown` оставил6 donor workers. **Общий software test FAIL по safe exit, safe_exit=false. CIA не создана.**

Логи: `analysis/azahar-native-frame-v0.1.0-r5/result.json`, `native-frame.log`, `frame-before-exit.json`, `original-frame.png`; raw находится в изолированной private SD. Подробный разбор/зависимости/следующий минимальный шаг — `analysis/native-original-frame-v0.1.0/report.ru.md`.

Существующие параметры ресурсов:

- 178MiB application profile,40MiB normal heap/132MiB linear heap,128MiB donor arena.
- Оригинальная библиотека4499468 bytes/CRC9fd95635;1728 основных assets и20 APK assets, исходный donor и ресурсы только на локальной private SD.
- Проверяются receipts, donor CRC, EAMCore.ini и derived font; в host preflight все скопированные assets сверены SHA256 с прежним verified SD.
- Donor RX1059 pages и fail-stop trampolines3 pages обрабатываются двумя диапазонами; writable donor pages не попадают вRX. Реальные native protection/cache semantics в Azahar не проверяются.
- Неиспользованные неподдержанные imports/JNI имеют fail-stop traps, не фиктивные успешные реализации; дальнейшие игровые пути могут потребовать новых bindings.

Результат создаётся в новой свободной `SD:/3ds/ds-native-frame-v0.1.0/run-NNNN/`, private appdata — `SD:/3ds/deadspace/test-output/native-frame-v010/`. Существующий emulator save namespace не меняется. На ошибке donor/code/arenas/GPU resources удерживаются, освобождение под живыми workers запрещено.

Builder `python porting/tools/build_native_frame.py --revision r5` откажется переписывать имеющийся manifest; runner `python porting/tests/smoke_native_frame.py --revision r5` также не переписывает имеющиеся результаты. Следующей реализации нужен новый revision. Команда builder с `--cia` проверяет общий PASS, точное совпадение baseline, safe exit и hash CXI; текущий результат этот gate не проходит. Не обходить gate и не выдавать этот CXI за готовую игровую CIA.

Следующий минимальный промежуточный этап — завершение6 donor workers после сохранения уже полученного оригинального кадра: определить их entry/wait states через существующий DS7 debug API и реализовать подтверждённый shutdown protocol, затем повторить software checkpoint, проверить нулевой live count, закрытие GPU и возврат guest в HOME. Нельзя просто выставить success flag, отключить join или освободить donor image. После общего software PASS — сборка/проверка отдельной CIA и согласование одного аппаратного испытания.

В этом этапе аппаратных запусков/push/full552/FPS/audio/control work нет. Оригинальные .so/APK/ресурсы не включены в публичные исходники или пакет; distributable CIA/package пока отсутствуют.
