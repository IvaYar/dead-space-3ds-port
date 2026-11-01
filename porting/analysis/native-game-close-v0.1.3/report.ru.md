# Native-game Close 0.1.3: поздний loader и APT close

**Дополнение после аппаратуры:** manual START retry exit подтверждён; первый automatic wait60с завершился timeout при продолжающемся IO. HOME/X не проверен; текущий ready gate закрыт, повторCIA не нужен. [Аппаратный разбор](../native-game-close-v0.1.3-hardware/report.ru.md). Ниже сохранён отчёт программного этапа до получения hardware.

01.11.2026. Программные проверки прошли. Подготовлена одна новая experimental CIA; аппаратного запуска и push не было. Аппаратно исправление ещё не подтверждено. Старую Stable 0.1.2 не повторять.

## Причина и исправление

На аппаратуре generic callback `0x320624` выполнял поздний virtual Run `0xb6e6c`, а прежние software tests — первый `0xb60bc`. Поздний Run публикует delegate через `0x307468` и ждёт его выполнения главным потоком. Остановка main updates и обычный join оставляли его ждать бесконечно. Новый helper проверяет конкретные vtable/Run и известные delegate, а завершение подтверждает kernel join, не просто флаг `done`.

Поздний класс действительно воспроизведён без изменения original assets, игровых часов, кода или полей runnable: тест даёт первому loader закончить работу, затем продолжает оригинальные callbacks. Отдельная остановка на втором delegate получает **тот же аппаратный путь** `0x3357d8 → 0x321b64 → 0xb7084`, token `0x806`, sync state `1`, byte busy `0`, flag68 `0`, kernel timeout. Это состояние проверяет runner и повторно независимо проверяет release audit.

Исправление обслуживает pending delegate через настоящий `NativeOnDrawFrame` **перед NativeOnPause/Stop**, сохраняя правильный Update context. Оба delegate передают этот контекст дальше; вызов helper с NULL не подходит. Защитный предел — не более двух таких callbacks для двух известных delegate. После acknowledge loader ещё читает игровые данные, поэтому jobs/audio/periodic остаются работающими до его kernel exit.

Для первого loader сохранён hard deadline 30 секунд, для позднего — 60 секунд. Это не попытка замаскировать первоначальный deadlock: сначала устранено ожидание main delegate, затем отдельная диагностика доказала реальные непрерывные чтения — около 61 МБ за первые 30 секунд. С новым порядком точные pending cases завершили B за 35,6–38,3 секунды гостевого времени. Через каждые 5 секунд журнал содержит IO progress и memory sample. Это не прогноз задержки на настоящем устройстве.

После B завершаются jobs/audio/periodic, проверяются kernel completion, закрываются IO/JNI/sensor и worker handles, заканчивается и дренируется GPU queue, затем вызывается C3D_Fini. Код, donor registry и арены живут до teardown процесса. Ранее завершившиеся workers пропускаются при повторной попытке; неизвестный класс/состояние/timeout сохраняет FAIL и ресурсы.

## HOME → X и STOPPED

В libctru `APTCMD_WAKEUP_CANCEL` устанавливает close flag `0x400` и **не восстанавливает GSP/VBlank** как обычный resume. Поэтому просто выйти из старого retained-loop и начать GPU shutdown после X недостаточно.

Новая политика временно запрещает HOME во время работы donor. `aptCheckHomePressRejected()` превращается в deferred HOME request на безопасной main boundary. Сначала выполняется cooperative shutdown, затем разрешается HOME и вызывается стандартный `aptJumpToHomeMenu()`. В HOME уже нет живых пользователей donor/GPU; после X настоящий `aptMainLoop=false` ведёт к возврату процесса. HOME может открыться с задержкой до окончания ограниченной очистки. Возврат из HOME без X показывает завершённый checkpoint; START закрывает его, игровой render не возобновляется.

Recoverable STOPPED после возврата shutdown имеет отдельный цикл: сохраняет blocked/retained, обслуживает START и deferred HOME/APT close, разрешает одну безопасную повторную попытку. При повторном отказе ресурсы удерживаются, ложного PASS/exit нет. Imported-call fatal, где неизвестно владение runtime gate/стеком, не переводится в этот цикл и не делает небезопасный unwind/free. Универсальный выход из произвольно зависшего оригинального вызова не заявляется.

## Финальная матрица Azahar

Все строки используют один финальный native source SHA и byte-identical generated host checks. Старый `smoke_native_game_stable.py` остался неизменным. [Машинный release gate](release-gate.json).

| Сценарий | Циклы | Результат |
|---|---:|---|
| Normal, одна SD и один core, load/exit подряд | 3 | PASS кадра + 8 точных кадров, выход |
| Принудительный CRC_FAIL600, первый loader | 1 | Frame FAIL сохранён, выход |
| Точный pending второго delegate позднего B | 2 подряд | Frame FAIL сохранён, один original cleanup callback, kernel exit |
| Принудительный CRC_FAIL600 с поздним B | 1 | Frame FAIL сохранён, выход |
| Normal → deferred HOME → SDK wakeup-cancel → process return | 1 | PASS кадра, выход |
| STOPPED с живым поздним B → HOME → retry → SDK cancel | 1 | До retry 6 живых workers; Frame FAIL сохранён, затем выход |
| Реальный payload новой CIA | 1 | PASS кадра + 8 кадров, выход |
| Неустранимая injected incomplete cleanup | 1 | Ожидаемый blocked/retained, safe_exit=false, без free/exit marker |

**10 завершённых процессов:** каждый имеет 6 actual kernel joins, 0 worker handles, balanced IO, drained GPU/GSP release, освобождение обеих heap и 0 guest memory exceptions. Нормальные кадры проверены по всем 96 000 RGB565 pixels; CRC `ea733050` и исходный baseline не менялись. Семь поддельных release proofs (живой worker/handle, неполный join/cleanup, отсутствие heap release, неправильные pixels/статус кадра) отклонены [gate tests](gate-negative-tests.json).

Граница APT-теста существенна: HOME request инжектируется на main boundary, затем проходит **реальный libctru APT jump, получение cancel, aptShouldClose, aptMainLoop и SDK/process exit**. У Azahar нет настоящего HOME Menu и он бесконечно ждёт screenshot-ready handshake. Только эта функция заменена заглушкой в отдельной test-копии `apt.o`; установленный SDK не менялся. Новая CIA и обычные CXI используют оригинальный libctru, без заглушки. Физическая HOME-кнопка, системное меню и Luma проверяются только согласованным аппаратным тестом.

Исследовательские FAIL не скрыты: [10 предварительных опытов](experiments.json), включая два ошибочных NULL-context вызова с guest exceptions и неподдерживаемый HOME screenshot wait. Их source/CXI/логи сохранены в отдельных build/run; они не входят в release gate. Финальная матрица выполнена заново на общем финальном source. [Diff относительно 0.1.2](entry.diff).

## Сохранность и память

Все 431 защищённые SHA-записи прежних baseline, Stable 0.1.2, аппаратного архива и принятого resource-store pilot совпали. GPU backend, UV shader, DS7/DS6/DS8 runtime в финальных сборках byte-identical прежнему runtime. Все 1752 файла store и private master повторно проверены. Старые 39 SD-наборов не удалялись, не перемещались и не мигрировались. Новые isolated cards используют shared read-only assets и собственные writable данные; hard links нет.

Размеры heap/linear/arena и Prod124 остались прежними: 20/100/92 МиБ. В точном late test normal allocator footprint достиг 18 878 464 bytes (около 18 МиБ), donor brk 67 112 960 bytes и mmap 3919 pages; отказов allocator не было. Это software budget proof; реальный пик поздней загрузки ещё требует аппаратного подтверждения.

## Кандидат и следующий шаг

`3ds/build-native-game-v0.1.3-normal/native-game.cia`, **DS Game Close 0.1.3**, TitleID `000400000FDE7600`, **345024 bytes**.

CIA SHA256: `74f94904ea59e0f1468273dff92f65156e55ece7de82a5a88c40c4ca990fe3e0`.

CXI/payload SHA256: `c679c04feee5ee9aebae467a425ad43183fa53aa756aa404c2e98955dc9baad2`.

Новый журнал: **SD:/3ds/ds-native-game-v0.1.3/run-NNNN/**; appdata namespace `native-game-close-v013`. Полный прежний `SD:/3ds/deadspace/` подходит без изменений. Оригинальных игровых файлов в CIA нет. [Инструкция и ожидаемый feedback](../../3ds/README-native-game-close.ru.md).

Нерешённые риски: реальный HOME/Luma/GSP lifecycle; скорость и пик памяти позднего IO на SD; другой неизвестный runnable/import вне проверенных путей. Расхождение 9231 pixels, LINEAR-aware oracle и сохранённые нижние EA-фрагменты остаются прежними вопросами. Hardware CRC_FAIL не превращается в PASS благодаря исправленной очистке.

После аппаратного подтверждения обоих выходов можно переходить к минимальному оригинальному экрану выбора сложности. Управление Айзеком/полноценная сцена потребуют отдельного ограничения памяти, поддержки нужных input exports и проверки новых фоновых задач. Новые GPU исследования, звук и gameplay в этом этапе не начинались.
