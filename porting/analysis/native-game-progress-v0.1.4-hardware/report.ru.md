# Progress 0.1.4: два аппаратных выхода подтверждены

Получены 02.11.2026 от пользователя два запуска настоящей New Nintendo 3DS. Пользователь сообщил об успешном закрытии через START и HOME→X, отсутствии зависания и возвращении штатной работы консоли. Загрузка, анимации и закрытие субъективно очень медленные. **Автоматическая очистка при CRC_FAIL и физический HOME→X теперь подтверждены для этих запусков. Frame FAIL сохранён. Повтор этой CIA для проверки выхода не нужен.**

## Фактический путь каждого запуска

| Показатель | run-0001 | run-0002 |
|---|---|---|
| Триггер по guest trace | CRC_FAIL после 600 callbacks; source=none | HOME requested before validation; 453 completed callbacks, result frame=454 |
| Ожидание late Run0xb6e6c | 76557 ms (drain log: 76544) | 81663 ms (drain log: 81643) |
| Бюджет | idle30000 / hard180000 ms | тот же |
| Итог IO loader | 56134436 bytes / 10897 positive reads / 79 files | тот же |
| IO completions / errors / active в конце | 53330 / 0 / 0 | тот же |
| Попытки shutdown / STOPPED | 1 / false | 1 / false |
| Kernel joins / оставшиеся worker handles | 6 / 0 | 6 / 0 |
| Общие IO opens/closes / active / dirs | 174/174 / 0 / 0 | 153/153 / 0 / 0 |
| Итог | automatic process return, safe_exit=true | cleanup → HOME handover → should_close=1 → APT process return |
| Сохранённые captures с независимой CRC/GX проверкой | 9 | 6 |

`threads-a1-before_pause.json` фиксирует живой B/token0x806, его virtual Runoffset0xb6e6c; `after_loader_wait` — done1/kernel0. В `after_quiesce` все6workers done1/kernel0; после reaping/join worker handles отсутствуют. Pause/Stop выполняются после loader, затем jobs/audio/periodic завершаются, IO сбалансировано. GPU finish/drain/C3D_Fini находятся перед `exit.txt`/cleanup_complete в неизменённом проверенном коде. Маркер и PROCESS return присутствуют в обоих запусках. Отдельного аппаратного измерения SDK heap освобождения нет: сохранение code/arena до kernel process teardown — ожидаемая lifetime policy, не утечка, которую следует исправлять преждевременным free.

В wait samples bytes и completed IO растут и после старого лимита60с. Нет idle/hard refusal; последний idle209/208ms. Проверенного счётчика donor completed jobs по-прежнему нет; IO completions/jobs не отождествляются. `pumps=0`: pending-delegate shutdown pump на этих аппаратных выходах не упражнялся.

Пользователь назвал первый тест «START», однако **зарегистрированного START нет**: START_seen=false, source=none, нет CANCEL START acknowledged. Это подтверждает, что фактическая очистка не потребовала START/retry; точный момент физического нажатия неизвестен, отдельное подтверждение регистрации кнопки из этого теста не следует. Повторять тест для уточнения не требуется. Во втором HOME присутствует во всех wait samples; `close_pending` становится true уже после реального SDK возврата из HOME с should_close=1. Сообщение пользователя о X согласуется с trace; это аппаратный путь, а не эмуляторный shim.

## Производительность и графика

Измерено только окно ожидания loader: 76,6/81,7с. Полное время A→картинка, длительность анимаций, FPS и время от кнопки до выхода не измерены. Значительная часть закрытия ожидает завершения оригинального in-flight Run: немедленной отмены посреди чтения не реализовано, её безопасный donor contract не установлен. Нельзя выдавать это за GPU hang или заключать о физической скорости SD по IO byte counters. Следующий этап должен измерить чтение/декодирование/рендер и стоимость диагностики перед адресной оптимизацией; произвольное увеличение timeout не нужно.

Последний сохранённый raw каждого запуска byte-identical Stable0.1.2/Close0.1.3 hardware capture; **9231/96000 pixels** по-прежнему отличаются от frozen software reference. CRCbf2a6bfd против ea733050. Независимые readback CRC, command completeness и transfer checks проходят для всех15captures. У run-0002 причина FAIL — ранний HOME до validation, не завершённая CRC_FAIL-проверка600callbacks. Ни один выход не превращает frame в PASS. Readable hardware text/фото, Azahar GPU и software baseline остаются разными источниками; GPU/UV/shader/filtering не менялись.

## Сохранение и границы

- Оригиналы `porting/ds-native-game-v0.1.4/run-0001` и `run-0002` не менялись.
- Архивы `analysis/hardware/native-game-progress-v0.1.4-user-run-0001` (34files/3128442bytes) и `...run-0002` (28files/2147091bytes) содержат все62files/5275533bytes; source/archive SHA256 совпали с [manifest](archive-manifest.json).
- [Наблюдения пользователя](user-observations.json) отделены от измерений; фотография имеется в сообщении, локальный файл не архивирован. На ней ещё cooperative shutdown running — итог подтверждают логи и сообщение о возврате консоли.
- [Программный gate до получения hardware](software-release-gate-before-hardware.json) сохранён. Текущий gate учитывает hardware, исторический CIA manifest не переписывается.
- Ожидалась CIA SHA89973ea6d2607222895c28f1062d93db610461268befebf8cc19bc92dd34521f, TitleID000400000FDE7700, DS Game Progress0.1.4. Установленный бинарник независимо с устройства не извлекался/не хешировался; экран и формат логов соответствуют версии.

Воспроизводимая проверка полученных файлов без запуска эмулятора/консоли:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python porting/tools/analyze_native_game_progress_hardware.py
python porting/tools/audit_native_game_progress.py
```

Обе проверки выполнены успешно: подтверждены исходные62files/архивы,15captures и аппаратные shutdown snapshots; полный повторный audit сохранил11software process exits/2retained negative cases, SHA native/headers/CIA/runtime/GPU/shader,68protected+375старых файлов и1752files master/store. `git diff --check` прошёл. Raw/stack/capture-audit остаются ignored; staged-publication guard прошёл при пустом index (0staged files), что не является отдельным review всего worktree.

На hardware пока не упражнялись forced idle/hard refusal, STOPPED→automatic continuation, неизвестные runnable, зависший FS IPC/foreign callback, непосредственный системный close до HOME, большие серии перезапусков и память будущей сцены. Для fixture idle/hard/STOPPED/START/system close остаются отдельные сохранённые Azahar proofs. Два реальных успешных запуска не гарантируют бесконечную устойчивость и не доказывают будущий игровой бюджет памяти.

Следующий приоритет — оригинальный экран выбора сложности в Prod124 и далее управление с сохранением проверенного shutdown. Повторные аппаратные диагностики этого checkpoint не нужны. Новых сборок, эмуляторных/аппаратных запусков, удаления/миграции ресурсов и push при разборе feedback не было.
