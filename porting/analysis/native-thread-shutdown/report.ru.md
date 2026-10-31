# Native donor shutdown: software PASS, 31.10.2026

Все шесть donor-потоков завершены кооперативно. Финальный CXI `3ds/build-native-frame-v0.1.0-s16/native-frame.cxi`, SHA256 `50feded2db3aad2c5acad7c2d046683d9390224104851c4b1c29d65c98a19d8e`.

В одном экземпляре Azahar выполнены **три последовательных load → оригинальный кадр → START → shutdown → unload** с одной private SD. Во всех циклах `passed=true`, `safe_exit=true`, шесть kernel joins с Result=0, оставшихся worker handles=0, ошибок памяти/guest exceptions=0. RGB565-представление всех 96000 пикселей совпало с сохранённым оригинальным GPU baseline. Это прежний startup/UI checkpoint с Айзеком и наушниками, ещё не управляемая игровая сцена.

Основной результат: [result.json](result.json). Полные software результаты: [s16/result.json](../azahar-native-frame-v0.1.0-s16/result.json). Ветка `fix/native-donor-shutdown`, HEAD прежний `d30fcc5`; commit/push и аппаратных запусков нет. **CIA в этом этапе не создана.**

## Что делают шесть потоков

Адреса ниже — offsets относительно загруженного donor image; токены относятся к исследованному запуску. Названия функций по ближайшему экспортированному символу из objdump не принимались за действительные имена stripped-функций.

| Токен | Entry / настоящий callback | Назначение и ресурсы | Состояние после Pause/Stop | Корректное завершение |
|---|---|---|---|---|
| `0x201` | `0x360d9c` → `0x368010` | Периодический dispatcher зарегистрированных callbacks: защищённый список function/argument, собственные mutexes, интервал 50 ms. Более узкое название подсистемы не установлено; прежняя рабочая метка «heap worker» отвергнута. | `usleep(50000)`, run/thread word `image+0x46cc24` ненулевой. Pause/Stop этот service не уничтожают. | Повторена только операция stop из `0x360dfc`: очистка run word. Sleep разбужен кооперативно, затем kernel join ≤1000 ms. Mutexes под работающим потоком не уничтожаются. |
| `0x302` | `0x24c7f8` → IRunnable.Run `0x355340` | Первый worker общего scheduler/jobs; runnable object, task/event queues, временный scheduler semaphore, EAThread registry/refcount. | `sem_timedwait`, в данном запуске `0x31188964`, caller `0x353ed0`. | Штатный request-stop `0x35532c(runnable)`, распространение stop event через оригинальный scheduler, пробуждение семафора, kernel join ≤1000 ms. |
| `0x403` | `0x24c7f8` → IRunnable.Run `0x355340` | Второй worker того же scheduler; отдельная очередь/временный semaphore, тот же владелец pool. | `sem_timedwait`, `0x31188924`, caller `0x353ed0`. | Тот же оригинальный request-stop, отдельный подтверждённый kernel join. |
| `0x504` | `0x24c914` → C callback `0x29bf3c` → `0x29bcec` | Аудиомикшер/producer; общий audio object, PCM buffers/counters, EA semaphore из object+`0xd8`, engine lock. Это разбор shutdown-зависимости; вывод звука не реализовывался. | `sem_wait(0x302f1248)`, caller `0x24bbac`. Проверяет общий running byte, но сам Pause не означает уничтожение worker. | Из оригинального audio destructor `0x275634` выделены **stop и wake**, без его ранних frees: `image+0x44d4bd=0`, оригинальный EA post(2), затем kernel join. |
| `0x605` | `0x24c914` → C callback `0x271a10` | PCM output/consumer того же audio object; sample counts, output buffer, периодический sleep. | `nanosleep({4294967,295000000})`, caller `0x271b64`: ровно `0xffffffff` milliseconds, около 49.7 суток. Одна запись running=0 не прерывает уже начавшийся sleep. | После audio stop sleep получает кооперативный `EINTR`; исходный loop заново читает running=0 и возвращается. Kernel join ≤1000 ms. Источник насыщенного периода в аудиоконфигурации здесь не исправлялся и не объявляется доказанным. |
| `0x706` | `0x24c914` → `0x320624` → virtual Run `0x0b60bc` | Конечная оригинальная startup-загрузка игровых ресурсов; использует game managers, файловые/decoder contexts, общие resource locks и jobs. | Выполняет конечную загрузку; `wait_kind=0` не означает, что поток завершился. | Естественный return исходного loader, bounded kernel join ≤30000 ms **до остановки jobs и любой разрушающей очистки**. 10000 ms в промежуточном варианте было недостаточно. |

Стеки: 256 KiB у `201/302/403/706`, 32 KiB у `504/605`. Все шесть donor threads detached на уровне Bionic/EAThread; адаптер намеренно создаёт joinable libctru threads и сохраняет их kernel handles до реального завершения.

## Это были живые потоки, а не ошибка счётчика

В s1 до Pause, после Pause, после Stop и после bounded join у всех шести `Worker.done=0`; прямой `svcWaitSynchronization(saved_handle,0)` давал **timeout `0x09401bfe`**, а не invalid handle. В финальном s16, перед освобождением handles, у всех шести `done=1` и **kernel Result=0**, включая завершение TLS destructors и libctru `svcExitThread`.

`wait_kind=0` в прежней диагностике был неполон: она не отмечала timed semaphore waits и nanosleep. В изолированной native-копии добавлены эти наблюдения. `ds7_stats` считает/освобождает detached threads только после kernel join=0; основной DS7 и его platform backend не исправлялись, потому что ошибка учёта не подтвердилась.

## Штатный lifecycle и отвергнутый путь

DEX оригинального APK показывает: `onPause` вызывает NativeOnPause, `onStop` — NativeOnStop. `onDestroy` получает NativeGetExitCode и вызывает `java.lang.System.exit`; NativeOnDestroy export отсутствует. Pause/Stop сохраняют persistent services для продолжения работы, а не завершают процесс.

**NativeOsExit не является NativeOnDestroy.** Его Java callsite находится в `onCreate` — это очистка состояния при повторном создании. Прямая попытка вызвать его на нашем раннем checkpoint в s2–s5 запустила разрушение общих объектов при ещё работающем loader. Main заблокировался на resource lock (`0x302f5908`, semaphore `0x302f5914`), а в s5 получен guest Undefined Instruction / PC=0 у loader. Причинная интерпретация: разрушение раньше quiescence небезопасно; точный источник повреждённого указателя не доказан. Этот путь удалён из финального shutdown.

Диагностический host-процесс s5 пришлось остановить после guest failure. Это отмена неуспешного emulator test, **не механизм завершения donor-потоков** и не safe_exit PASS. Все файлы этого запуска сохранены. Обнаружение guest exceptions добавлено в итоговый runner.

В DS8 зарегистрированы 87 pending original destructors. Их массовый вызов до остановки пользователей не используется: среди них есть разрушающие общие resource managers. Полный оригинальный destructor graph для in-process unload в этом этапе не реализуется.

## Минимальный механизм

Финальная последовательность в отдельном native main:

1. Сохранить настоящий GPU checkpoint и дождаться его GPU completion.
2. NativeOnPause → NativeOnStop.
3. Дождаться естественного окончания конечного loader, максимум 30 s.
4. Послать оригинальные job stop events; bounded join двух workers.
5. Послать оригинальный audio running=0 и EA semaphore wake; кооперативно прервать sleep; bounded join двух audio workers.
6. Очистить оригинальный periodic-service run word, прервать sleep; bounded join dispatcher.
7. Подтвердить kernel completion каждого потока, освободить thread handles/stacks; проверить нулевые active/finished counts.
8. Выполнить имеющиеся JNI, stdio, appdata/DSIO cleanup; проверить file balance/dirs. Закрыть sensor, пустой post-present frame, drain GPU, C3D_Fini и обычный возврат main.

Sleep в **native-копии** DS7/DS6 заменён на timed condition wait со state gate. До stop сохраняются запрошенные длительности и yield; sticky interrupt адресуется конкретному проверенному токену. При shutdown sleep возвращает `-1`/Bionic errno `EINTR=4`, заполняет remaining при необходимости. Поток продолжает оригинальный код и сам возвращается. Ни terminate/cancel thread, ни обход TLS teardown, ни longjmp через чужой стек не применяются.

Оригинальные opcode prefixes stop routines, object vtables и pinned donor CRC проверяются до использования offsets. Это версия-зависимый checkpoint adapter; перенос на другую `.so` потребует повторной проверки, а не слепого применения offsets.

При любом timeout/несовпадении/ошибке cleanup остаётся FAIL и удерживаются donor image, стеки оставшихся threads, арены и GPU allocations. Наличие кадра не открывает safe_exit gate.

## Повторная проверка и lifetime

| Цикл в одном Azahar / SD | Original callback | Отличий pixels / 96000 | Kernel exits | Handles после cleanup | Файлы open/close | Safe exit |
|---|---|---|---|---|---|---|
| 1, холодные private appdata | 351 | 0 | 6/6 | 0 | 94/94 | PASS |
| 2, тот же save namespace | 352 | 0 | 6/6 | 0 | 73/73 | PASS |
| 3, тот же save namespace | 351 | 0 | 6/6 | 0 | 73/73 | PASS |

В каждом цикле JNI cleanup освободил 13 ресурсов, открытых directories=0, sleep реально вернул EINTR двум потокам. GLES error=0, CPU fragments/samples=0, failed GPU submits=0. Проверены и guest JSON/log, и kernel handle completion, и host log: ReleaseRight, освобождение **132 MiB linear heap** (`0x30000000`) и **40 MiB normal heap** (`0x08000000`) в каждом отдельном цикле. Старые cleanup-маркеры предыдущего цикла не учитываются.

В host log остаются прежние APT/PTM stubs и отказы QueryMemory (`svc=0x02`) при проверке непригодных адресов диагностическим reader: он проверяет mapping/permissions **до memcpy** и пропускает такие адреса. Это не unmapped Read/Write. Отдельно проверены отсутствие реальных invalid accesses, assertions и guest exceptions; ошибочный s5 с PC=0 этим критериям не соответствует.

Donor image, его глобальные объекты, registry synchronization words и арены намеренно остаются выделенными до штатного завершения **процесса**. Пользователей уже нет, GPU остановлен; оба heap затем действительно освобождаются. Это проверка повторных запусков процесса, **не поддержка повторной загрузки donor внутри того же процесса**. Утечек между этими тремя запусками и ошибок доступа к освобождённой памяти в Azahar не обнаружено; исчерпывающая проверка любой ошибки внутри ещё mapped памяти этим эмулятором не заявляется.

## Сохранение baseline и готовность CIA

Инвентарь перед работой: 218 файлов. **215 SHA256 не изменились**; три ожидаемых изменения — native main, его builder и его runner. Сохранены основной CPU/GPU harness, исходники runtime/DS7/DS6/DS8/GPU, SDK, r5 build и аппаратные результаты. Аппаратно успешный UV shader и копия RGBA8 → RGB8 renderer совпадают с прежними байтами; новых GPU исправлений нет. Локальный `preservation.json` и полные object/stack dumps остаются private evidence.

Изменения находятся только в отдельной native ветке/варианте. Генерируемые копии runtime включены в build manifest; исходный emulator harness не переписывался. Все прежние s1–s15/аппаратные отчёты сохранены. `.so`, APK, assets, private SD и изображения оригинальной игры исключены из публичного Git/пакетов.

Gate `build_native_frame.py --cia` теперь требует общий PASS, safe exit, точный frame baseline, ≥3 успешных последовательных циклов в одном core/SD, шесть kernel joins, 0 worker handles, balanced files, освобождение обоих heap, отсутствие guest memory exceptions и совпадение CXI/исходников/runner hashes. Девять dry-run проверок gate прошли, включая отказ при одном оставшемся handle, незавершённом join, нарушении file balance, stale CXI/runner и safe_exit=false. makerom при этих проверках был mock, CIA не создавалась.

**Готовить первую отдельную experimental native-game CIA теперь можно: software safe_exit gate открыт.** Аппаратных проверок native RX/cache semantics и исходной игры ещё нет. Следующий этап — подготовить CIA и приватную SD-поставку этого же checkpoint, согласовать один аппаратный запуск, проверить original frame + safe return. Только после него переходить к непрерывной оригинальной сцене и вводу Айзека. Изготовление/запуск CIA не входят в выполненную здесь проверку потоков.

Воспроизводимость без перезаписи evidence: выбрать новый revision, затем `python porting/tools/build_native_frame.py --revision NEW` и `python porting/tests/smoke_native_frame.py --revision NEW --cycles 3`. Существующие revision/output directories builder и runner переписывать отказываются. Никаких full552, FPS/audio/control work, git push или hardware trials в этом этапе не выполнялось.
