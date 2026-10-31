# Измерение native-game checkpoint — 31.10.2026

Цель — отделить реально используемые allocator backing/пулы от заранее зарезервированных172MiB. Создана **только Azahar CXI** `3ds/build-native-game-v0.1.0-mem1/native-game.cxi`, SHA256 `b04c5dab3ad84f9ecb094e166a96d9d57843518c0168351cd1ddee0bb02cf62c`. Игровая CIA не создавалась, аппаратный запуск запрещён.

Сгенерирована отдельная копия `tests/native_game.c`: добавлены read-only `mallinfo`, linearSpaceFree, DS9/runtime stats, RESLIMIT_COMMIT и записи на границах стадий/каждого draw. **Не менялись** heaps40+132MiB, arena128MiB, guard>=178, lifetime, оригинальные callbacks, GPU/backend/shader или cooperative shutdown. Все generated GPU/thread overlays побайтно скопированы изh2. [Единственный source diff](entry-instrumentation.diff). Baseline native_game.c и прежние builders/runners сохранены.

Запущен **один** цикл неизменённого `smoke_native_game.py --container cxi --revision mem1 --cycles1`: оригинальный checkpoint достигнут на callback352, **96000/96000 pixels совпали с GPU baseline**, GL0/memory errors0, шесть истинных kernel joins,0worker handles, balanced IO94/94, safe_exit и освобождение обеих куч PASS. [Результат](../azahar-native-game-v0.1.0-mem1-cxi/result.json). Полный ARM suite не запускался.

## Измерения

366 samples от preflight до after_shutdown, все memory queries Result0. [Полные counters и вычисления](measurements.json).

| Категория | Bytes | MiB | Как учитывать |
|---|---:|---:|---|
| Фактический process commit | 181137408 | 172,7461 | Все40+132MiB уже зарезервированы; свободные внутренние части не уменьшают commit |
| Донорская arena allocation | 134217728 | 128 | Реальный большой block, внутри linear132; не прибавлять второй раз к172 |
| DS9 sbrk точный high-water | **16781312** | **16,0039** | Backing allocator донорского heap, не сумма live C++ объектов |
| DS9 mmap peak | **0** | **0** | Во всём checkpoint успешных mapped pages не было |
| Normal malloc sampled max uordblks | **13110272** | **12,5029** | Включает donor ELF/image, trampolines, runtime, normal ресурсы/потоки |
| Normal malloc sampled max arena | 13406208 | 12,7852 | Включает free bins/allocator slack, но не весь резерв40MiB |
| Runtime exact peak | 2457779 | 2,3439 | **Подмножество normal malloc**; отдельно к normal не добавлять |
| Linear sampled max кроме arena128 | **2399104** | **2,2880** | SDK display/GPU/прочие allocations; не включает VRAM |
| Static code/data+stack/extra commit | 782336 | 0,7461 | Commit минус172MiB heaps в этой сборке/эмуляторе |

Сумма непересекающихся measured maxima/backing составляет33073024bytes≈**31,54MiB**; с normal allocator arena вместо uordblks —33368960bytes≈**31,82MiB**. Это **не новый process commit** и не доказанный минимальный бюджет: реально приложение всё ещё коммитит172,7461MiB. Сэмплы после callbacks могут пропустить кратковременный native/linear peak внутри callback/worker. DS9/runtime high-water обновляются самими allocator routines, но относятся только к своим пулам.

Не складывать runtime2,34 с normal12,50, donor arena128 с её sbrk16,00 или текущую свободную linear память с уже учтёнными allocations. Занятая карта ресурсов не равна числу физически затронутых CPU/GPU страниц; их точная residency этим probe не измеряется.

## Возможно ли124MiB

**Для наблюдённого одного startup/UI кадра — выглядит возможным, но ещё не доказано.**128MiB — выбранная ёмкость host arena в entry point, а не минимальный размер, потребованный этим выполнением: реальные sbrk запросы достигли16MiB, mmap peak0, refusals/runtime failures0. DS9 API допускает page-aligned shared pool до128MiB, не требует всегда ровно128.

Текущая игровая сборка124 не поддерживает: pre-main40+132 не поместятся, initialize явно требует178, а отдельный arena block128 сам по себе больше всего app limit124. В этом probe эти условия намеренно сохранены. Перенос выделения128 после main недостаточен.

Пример **будущего бюджета для отдельной программной проверки**, не выполненное изменение: normal20MiB, linear100MiB, из них arena96 +4MiB SDK/GPU pool. Total120MiB, ещё≈3,25MiB после static/stack в режиме124. Это сохраняет большой запас относительно измеренных normal≈12,8 и donor≈16,0, но всё равно требует проверки адресов/фрагментации/пиков и всех путей отказа. Нельзя объявить96 достаточными для следующих сцен.

После аппаратного startup Prod124 PASS следующая отдельная работа может проверить этот бюджет в Azahar: сначала размер arena, затем размеры heap/guard по отдельным проверяемым шагам, с точным original frame comparison и прежним safe_exit. Не менять оригинальный donor, GPU backend или размеры baseline. За каждым сокращением должен стоять замер и достаточный запас, а не подмена allocation failure успешным кадром.

Для непрерывной сцены потребуются loader/map peaks при сменах уровней, пиковые textures/streaming/decompression, native allocator transient high-water и остаток на стеки/системные charges. Ни управляемая сцена, ни аппаратный game peak этим измерением не доказаны. Любые buffers/арены/RX/стеки должны жить до GPU completion и завершения всех пользователей, как в текущем safe_exit.

Наблюдатель добавляет timing/SD overhead, что объясняет допустимый сдвиг номера callback; содержимое кадра и завершение проверены отдельно. Первую сборку probe остановил `-Werror` на форматировании добавленных statements; исправлены только переносы строк generated source, без исполнения неуспешного build. Новых аппаратных CIA, настроек Luma/firmware и push нет.
