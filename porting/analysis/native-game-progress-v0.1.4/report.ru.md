# Progress 0.1.4: автоматическое завершение при длительной загрузке

**Аппаратное дополнение 02.11.2026:** пользователь успешно выполнил два выхода. run-0001 — автоматический CRC_FAIL shutdown без зарегистрированного START, B76,6с; run-0002 — реальный HOME→X, B81,7с. Оба1attempt/безSTOPPED/6kernel joins/0handles/balancedIO/cleanupcomplete. FrameFAIL остаётся. [Новый аппаратный отчёт](../native-game-progress-v0.1.4-hardware/report.ru.md). Повтор этой CIA для проверки выхода не нужен; далее оригинальный экран сложности/управление. Ниже сохранён программный результат **до аппаратного feedback**.

Программный этап завершён. **В Azahar подтверждены 11 завершений процесса**, включая реальный payload одной новой CIA. Два отрицательных случая сохраняют blocked/FAIL и живые ресурсы. На настоящей 3DS эта версия не запускалась. [Release gate](release-gate.json), [изменения относительно Close0.1.3](entry.diff).

## Ожидание и реальные признаки прогресса

Аппаратный Close0.1.3 читал данные и превысил60с, затем завершился в фоне до повторного START. В новой реализации нет этого промежуточного лимита60с:

- **30с без прогресса** — переход в STOPPED/retained.
- **180с общего ожидания** — переход в STOPPED/retained даже при непрерывном прогрессе.
- Общий бюджет создаётся один раз для pthread generation token; START/HOME/APT и повторная очистка его не сбрасывают.

`native_loader_io_monitor.h` — отдельный adapter нового native entry вокруг прежних `DSIOOps`. Исходные DSIO/DS7/GPU не менялись. Короткая LightLock защищает per-token counters и отпускается **до** обращения к SDK IO. Учитываются реально завершённые positive reads/bytes, закрытые файлы, завершённые IO operations, ошибки и текущие операции. Token отделяет поздний loader от main/audio/других workers; одно лишь наличие active handle не означает прогресс.

Idle budget обновляют positive bytes/completed files конкретного loader и увеличение штатного task-progress word `object+0x24`. Повторный EOF, ошибки, sleep/wait changes, active operations и нажатия кнопок срок не продлевают. Для безопасного завершения по-прежнему нужен **kernel join**, а не progress/done flag.

Проверенного счётчика **завершённых donor jobs** нет: `completed_IO_ops` не выдаётся за число jobs. `object+0x24` — progress исходной задачи, не счётчик jobs; `done` DS7 относится к потоку. В диагностике явно `completed_donor_jobs_available=false`. Jobs/audio/periodic останавливаются после kernel exit loader, как в подтверждённом аппаратном retry.

## Отмена, HID и APT

Каждый оборот ожидания после bounded join10ms обслуживает HID/APT. START защёлкивается в close request; HOME остаётся deferred до quiescence; системный close сохраняется в `close_pending`. Нажатие не продлевает бюджет и не теряется как в прежнем полностью неполлируемом wait.

**Режим кооперативной отмены — finish-in-flight.** Прекращается дальнейшее продвижение сцены, остаются только необходимые original callbacks для уже опубликованных delegate, затем текущий Run завершается и joins подтверждают отсутствие пользователей. В исследованном Run0xb6e6c нет проверенного early-abort контракта. Принудительный thread exit, fake read errors, вызов destructor с живыми пользователями или запись произвольных cancel-полей не добавлены. Немедленная отмена посреди чтения не заявляется.

Если idle/hard budget исчерпан, программа честно сохраняет STOPPED/FAIL и ресурсы. В этом состоянии продолжается HID/APT и неблокирующий kernel poll. **Если loader позже завершился, cleanup автоматически продолжается без START.** Новый бюджет при этом не создаётся. Если loader действительно никогда не возвращается, safe_exit невозможен без нарушения lifetime: сохраняется blocked/retained, никакого фиктивного PASS/free.

HOME handover происходит только после остановки donor, IO/JNI/sensor/handles и GPU drain/Fini. Затем обычный SDK принимает wakeup-cancel от X и возвращает процесс. Исполняющийся original callback/SDK вызов не прерывается: пределы проверяются на вернувшихся main boundaries. Универсальная обработка произвольно зависшего syscall вне этих границ не доказана.

## Проверки

| Сценарий | Циклы | Подтверждение |
|---|---:|---|
| Normal, одна SD/core, последовательные load/exit | 2 | Frozen frame+8sequence, kernel/heap exit |
| CRC_FAIL600, первый loader | 1 | Реальный FAIL сохранён, auto cleanup |
| CRC_FAIL600, поздний RunB | 1 | Реальный FAIL сохранён, auto cleanup |
| Поздний pending delegate + замедленные IO | 2 подряд | Автоматический выход за68,6/70,8с, без START и STOPPED |
| START во время такого ожидания | 1 | Запрос учтён, бюджет не сброшен, exit≈68,5с |
| HOME во время такого ожидания → SDK cancel | 1 | Deferred HOME, exit≈68,6с после quiescence |
| System close во время такого ожидания | 1 | SDK close flag учтён, exit≈68,6с |
| Остановка IO → idle STOPPED → возобновление | 1 | До release6живых workers; после kernel exit автоматическая cleanup, **START не нажимался** |
| Реальный CIA payload | 1 | Exact frame+8sequence, kernel/heap exit |
| IO остаётся остановленным | 1 отрицательный | Idle refusal, START/HOME учтены,6живых workers, без frees/exit |
| Прогресс продолжается, общий deadline исчерпан | 1 отрицательный | Hard refusal при12,051с тестового бюджета, без frees/exit |

Все11 завершённых процессов: **6kernel joins,0worker handles, balanced IO/dirs, GPU/GSP release, обе heap освобождены,0guest memory exceptions**. Normal проверен по всем96000pixels и8дополнительным настоящим кадрам. CRC `ea733050`, cap600 и baseline не менялись. Отрицательные тесты проверяют отказ разрушать живые ресурсы; они не означают PASS очистки. [Семь испорченных release proofs отклонены](gate-negative-tests.json).

Замедление — реальная задержка3ms после positive read **только token B**. В финальных случаях B завершил56134436bytes/10897positive reads/79files. Неподвижный IO блокируется в adapter до SDK read, с active operation, чтобы проверить отсутствие ложного heartbeat. Для коротких отрицательных тестов idle уменьшен до3с, hard — до12с; производственная CIA использует30/180с. Проверки выполняются между original callbacks: idle fixture обнаружен около5,4с, включая занявший main original callback. Это не гарантия прерывания foreign calls за3с.

APT fixture инжектирует deferred HOME на safe boundary и проходит настоящий SDK jump/wakeup-cancel/aptShouldClose/process exit. Только неподдерживаемый Azahar screenshot-ready handshake заменён test-only shim. System fixture отдельно выставляет SDK exit flag. **В normal CXI и CIA нет ни shim, ни искусственного замедления/зависания.** Физические HOME/X, Luma и системное закрытие на приставке остаются аппаратной проверкой.

## Предварительные сбои и границы доказательства

[Все предварительные опыты сохранены](preliminary-experiments.json). Первая stall-инъекция ошибочно тормозила main IO и была отклонена; финальная привязана к token B. Проверка stale wait metadata была исправлена: после STOPPED `loader-wait.json` сохраняет результат исчерпанного окна, а итоговую очистку доказывают `close-state.json`, attempt snapshots и kernel/host proof.

У первой normal-серии прошли два процесса, затем host завершился во время bootstrap третьего. Причина этого host обрыва в данном этапе не установлена; он не назван guest PASS и не скрыт. Финальные последовательные серии **по два** normal и slow прошли, плюс отдельный CIA payload. Стабильность произвольного числа reload в одной Azahar DLL не заявляется; прежние похожие host проблемы не являются доказанной причиной нового обрыва.

В реальном зависании FS IPC может блокироваться и main journal IO; это не эмулируется задержкой adapter. Early-abort, неизвестные runnable/import paths, настоящий аппаратный timing и будущая память игровой сцены остаются рисками. Изображение9231pixels/LINEAR-aware oracle и EA-фрагменты этим этапом не исправлялись.

## Сохранность и кандидат

Сохранены68новых защищённых файлов Close0.1.3/аппаратного архива/пользовательского README и375прежних SHA-записей baseline. Store и private master1752files проверены. Старые39SD не тронуты; новые cards используют shared immutable assets и собственные writable seeds. GPU/shader/DS7/DS6/DS8 byte-identical прежним,20/100/92МиБ и Prod124 прежние. Новые snapshots имеют `threads-a<attempt>-<stage>.json` и не затирают предыдущую попытку. Полного ARM suite, аппаратных запусков, очистки и push нет.

**Одна CIA:** `3ds/build-native-game-v0.1.4r2-normal/native-game.cia`, **DS Game Progress0.1.4**, TitleID **000400000FDE7700**, **347072bytes**. И SMDH, и заново сгенерированный баннер показывают0.1.4; изображение баннера проверено визуально, а CIA payload совпал с протестированным CXI.

CIA SHA256: `89973ea6d2607222895c28f1062d93db610461268befebf8cc19bc92dd34521f`.

Payload SHA256: `f043ad040622405790abc004efdc51de81138adcf47bfc11bf2717f5938e3b3c`.

Новый logroot **SD:/3ds/ds-native-game-v0.1.4/run-NNNN/**, appdata `native-game-progress-v014`. Старый полный SD:/3ds/deadspace/ подходит без копирования ресурсов. [Будущий согласованный тест/feedback](../../3ds/README-native-game-progress.ru.md).

Готова к одному отдельному аппаратному испытанию, не запущена агентом. После аппаратного automatic exit и HOME/X proof следующий этап — оригинальный экран выбора сложности, затем input и бюджет управляемой сцены.
