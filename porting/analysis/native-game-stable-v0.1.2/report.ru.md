# Native-game Stable 0.1.2: выход при FAIL и адресная диагностика

**Получен hardware FAIL:** более поздний Run0xb6e6c не завершился за30s, cleanup retained/6active, HOME→X не завершает приложение. Этот документ сохраняет результаты software подготовки; они не означают исправленный аппаратный выход. [Актуальный hardware разбор](../native-game-stable-v0.1.2-hardware/report.ru.md). Повтор текущей CIA запрещён; следующий кандидат не готов.

01.11.2026. База Git `8b1839c`, ветка `feat/native-game-prod124`, исходное рабочее дерево чистое. Новых аппаратных запусков, push, полного ARM suite, изменений оригинальных файлов или GPU backend нет. [Release gate](release-gate.json), [инструкция и CIA](../../3ds/README-native-game-stable.ru.md).

## 1. Выход при CRC_FAIL

**Исправлен и проверен в Azahar.** Main после возврата из `run()` при известном, полностью инициализированном lifecycle запускает существующий cooperative shutdown. CRC_FAIL больше не отправляется в бесконечный `fatal` до shutdown. Ошибка автоматически запускает очистку, дополнительное нажатие START не требуется.

Результаты кадра и очистки независимы: `result.json.status=failed`, `validation.json.frame_status=FAIL`, `cleanup_status=complete`, `safe_exit=true` после успешного завершения. Успешная очистка не превращает ошибочный кадр в PASS. При исчерпании цикла записывается реальное число выполненных callbacks 600 вместо прежнего значения счётчика 601.

Последовательность: Pause/Stop → естественный конец loader ≤30000 ms → штатные stop/wake для двух jobs, двух audio и periodic worker, каждый kernel wait ≤1000 ms → проверка завершения/handles → JNI/файлы/сенсор → закрытие пустого GPU frame/drain ≤2000 ms → C3D_Fini → exit marker → итоговый статус → gfxExit/возврат main. Проверенные тела stop routines и runtime-копии потоков не менялись. Донорские code/arena/global registries остаются выделенными до завершения процесса; стеки не освобождаются до kernel completion, GPU память — до завершения её пользователей.

Это ограничения ожиданий конкретных потоков и очереди, **не общий watchdog для любого кода**: исходные lifecycle, scheduler stop, SDK/GSP/SD/APT вызовы всё ещё могут блокироваться внутри себя. Между callbacks теперь обслуживаются APT/HID и START; прервать произвольный зависший original callback безопасным способом этот этап не обещает.

| Ветвь | Поведение |
|---|---|
| CRC_FAIL после 600 вернувшихся callbacks | frame FAIL; автоматический cooperative shutdown; нормальный выход только при завершённой очистке |
| Ошибка readback/audit/JNI/event pump после полного initialize | FAIL с причиной; тот же защищённый shutdown |
| Несовпадение одного из восьми последовательных кадров | FAIL всей последовательности; сохранённый первый кадр не даёт общий PASS |
| Незавершённая очистка/неожиданные workers/GPU busy | blocked/cleanup retained; без exit marker, gfxExit и освобождения живых ресурсов |
| initialize не завершил lifecycle | консервативное удержание; не вызывается donor shutdown по неизвестным частичным объектам |
| fatal из неизвестного import/JNI/GLES/конструктора | нет longjmp/forced termination; стек и ресурсы сохраняются |

Для main-thread STOPPED обслуживаются HID/APT; START пишет причину удержания. При действительно незавершённой очистке обычный выход всё ещё запрещён. В импортированном вызове может удерживаться DS7 gate, поэтому `fatal` не вызывает `ds7_stats` повторно даже на main. Свежий снимок получается на известной границе после возврата callback/shutdown. Статистику неизвестной импортированной ошибки следует считать cached, а не доказательством отсутствия потоков. Worker-thread fatal не запускает APT с чужого потока. Эти аварии не объявлены проверенными безопасными выходами.

## 2. Различия изображения

Использованы неизменённые hardware raw/log `native-game-target-init-v0.1.1-user-run-0001`, frozen RGB565 `gpu-safety/first-game-frame.raw`, BGR8 из прежнего успешного native-game и EA sequence 8–17. [Точная статистика](hardware-image-comparison.json), [дополнительные факты](image-findings.json). Производные изображения находятся только в ignored `private-images/`.

Подтверждены прежние **9231/96000** отличающихся RGB565 пикселей, bbox **x52..340/y61..195**. 5005 отличаются по каждому каналу максимум на один уровень; у 4226 отличие больше. Максимальные абсолютные RGB565 delta R/G/B: 23/45/23. Каналы R/G/B отличаются в 2908/8590/6020 пикселях. В RGB8 отличаются 14013 пикселей. CRC hardware BGR8 `9b99050c`, quantized RGB565 `bf2a6bfd`, frozen reference `ea733050`.

Различия сосредоточены на рисунке и деталях текста: крупнейшие связные области 2793 pixels в x176..319/y129..156, 2330 в x185..242/y69..126, 1332 в x115..170/y61..124. В y0..49 и y220..239 отличий нет. Посчитаны все строки/колонки, сетка 20×20, signed channel histograms, 295 связных компонент и распределения по фазам 2/4/8/16/32/64. Простого чередования чётных/нечётных строк/колонок нет: x 4583/4648, y 4557/4674 отличий. Это не доказательство отсутствия любой cache-ошибки.

Глобальные преобразования не исправляют снимок: RGB/BGR swap даёт11931 отличий, vertical flip19067, horizontal19054, 180°19817, row-major22287. Среди сдвигов ±2 pixels минимум при dx=dy=0; сдвиг x+1 уже10831 отличий. Подтверждён layout `BGR8_CTR`: offset=(x*240+239-y)*3, шаг колонки720 bytes, весь capture288000 bytes. GPU путь остаётся RGBA8 target → GX RGB8 → LCD BGR8 storage, flags1000/dims240×400; название RGB8 transfer не означает RGB-порядок байтов CPU.

Основной CRC gate не менялся: BGR8 → little-endian RGB565 → `ds_crc32`, target `ea733050`. Добавлены известный CRC vector `123456789→cbf43926`, независимый побайтовый RGB565 CRC без u16 buffer, проверка zlib на хосте и два invalidate/readback без GPU submit между ними. В Azahar они согласованы, ошибочных cache/CRC совпадений не обнаружено. Сервис cache synchronization в Azahar не подтверждает аппаратную когерентность; на старом hardware raw нет парных чтений и записанных адресов. Аппаратные cache/readback-ошибки окончательно не исключены.

Отдельный принудительно отрицательный **чёрный software прогон до600** сохранил RGB565 baseline точно: 0 отличий, `ea733050`; на уровне RGB8 относительно старого native checkpoint отличаются всего2 пикселя, не меняющие RGB565. [Сравнение](software600-image-comparison.json). Простое объяснение «снимок после600 обязательно другой» не подтверждается. Но hardware600 уже имел6 uploads/CPU fallback8103 и позднюю загрузку, тогда как software600 —4 uploads/CPU fragments0. Сравнимость исходного состояния hardware и software пока не доказана.

**Причина всех9231 отличий не установлена.** Ранее уже установлено, что Azahar Software не применяет LINEAR фильтрацию как реальный GPU; это возможный фактор, а не доказанный разбор всех различий этой пары. Нельзя считать испорченный accelerated OpenGL контроль эталоном, повторять старые sampling исследования, менять UV/backend по фотографии, заменять CRC или добавлять допуск.

## 3. Фрагменты под Айзеком — отдельный результат

В y180..219 reference551/hardware537 ненулевых пикселей; отличаются404. В reference три компоненты:274 pixels x183..211/y180..195,146 x149..171/y180..189,131 x227..248/y180..190.

**Все551 ненулевой reference pixel точно совпадают с EA кадром16 и17 в тех же координатах.** В новых software captures счётчик GLES clears остаётся0 до600. Это доказательство сохранения изображения предыдущей заставки в общем target, отдельное от аппаратного расхождения. Глобальная очистка нового target уже исправлена и на hardware подтверждена; она не определяет семантическую границу следующей сцены.

Дополнительный reset target «когда кажется, что появился Айзек» не добавлен: у нас нет подтверждённого контракта transition/повторного использования framebuffer. Он изменил бы эталон и мог бы убрать нужное накопление fade/compositing. Для исправления нужен отдельный разбор исходных draw/clear/swap намерений движка на границе заставок.

## 4. Последовательные оригинальные кадры и программные проверки

Native entry point после точного checkpoint выполняет **ещё8 настоящих callbacks/draw/present**, сохраняет каждый и требует полного RGB565 равенства всех96000 pixels baseline. В этом коротком окне изображение статично: это9 реальных кадров одного UI checkpoint, не9 различных сцен и не gameplay. Более ранние captures фиксируют разные стадии fade. Предел600 не увеличивался, звук/управление/меню не добавлялись.

Финальные серии в одном core/SD на серию:

- Normal CXI:3 последовательных frame+sequence+safe_exit PASS.
- Poison CXI:3 настоящих frame FAIL после600, каждый с6 kernel joins/0handles/IO balance/GSP release/обоими heap free.
- Forced gate rejection на black CXI:1 frame FAIL после600 с теми же доказательствами очистки.
- Incomplete cleanup fault:1 ожидаемый blocked;6 active threads, safe_exit=false, exit marker отсутствует, разрушения ресурсов/heap free/GSP release до остановки host нет. Это PASS проверки удержания, не гостевой PASS и не безопасный выход.
- Финальный CIA actual payload:3 последовательных frame+sequence+safe_exit PASS. Во всех успешных очистках memory exceptions0, failed submits0; independent readback/CRC и целостность command captures проверены.

Первая предварительная normal серия до добавления command recorder дала2 успешных цикла, затем host access violation до READY третьего. Windows Event1000 подтверждает прежнюю сигнатуру `azahar_libretro.dll/c0000005/RVA326ccf`. Она сохранена как FAIL в `-precmd`, причиной гостевой ошибки не объявлена и не исправлена. Host-only CIA path ошибка первого запуска runner возникла до загрузки guest; её исправление не меняет проверки. Сохранён предыдущий runner и побайтно проверено единственное отличие `ROOT.mkdir(exist_ok=True)`.

Архивы `-precmd` и `-pre-boundary-fix` содержат промежуточные версии/проверки, локальные и не предлагаемые к аппаратному запуску. Финальная небольшая правка перенесла DS7 snapshot из потенциально reentrant fatal в границу после shutdown; финальные перечисленные серии выполнены заново на окончательном source. Предварительный gate не используется как доказательство финальной CIA.

## 5. Одна финальная CIA и будущая диагностика

Готова одна текущая experimental **DS Game Stable0.1.2/FDE7500**; SHA/размер в [manifest](../../3ds/build-native-game-v0.1.2-normal/cia-manifest.json). Fault варианты остаются локальными CXI. Оригинальных файлов, картинок и RomFS в CIA нет. Сохранены375 защищённых файлов SHA; runtime GPU/shader/thread copies совпали с baseline. Prod12420+100MiB/arena92MiB и permissions прежние; commit126750720 bytes≈120,879MiB, measured normal footprint13406208 bytes≈12,785MiB. Этот бюджет не доказывает поддержку поздней аппаратной загрузки или gameplay.

На каждом выбранном checkpoint сохраняются raw + bounded `.raw.gx`: исходные GX descriptors и полные PICA command lists. Лог содержит результат парного readback, виртуальный/physical адреса transferred buffer и next buffer, vertex input FNV/count, texture digest, clears/viewport, submits/events. Recorder не меняет команд, не пишет/выделяет память в SDK wrapper; сохраняет файлы main после GPU completion. Возможное переполнение явно помечается, а не скрывается.

Нужные checkpoints: первые callbacks после uploads≥4, следующий и+8,351/352/400/534/600, failure raw; при совпадении — первый frame и8 sequence. Лог FRAMECRC отражает каждый проверявшийся кадр. Это позволяет сопоставить одинаковые входы по состоянию, а не одному callback number. FNV не криптографическая гарантия: одинаковые digests требуют проверки команд/параметров.

`analyze_native_game_run.py RUN --compare SOFTWARE_RUN --output NEW.json` автоматически проверяет raw CRC, независимый RGB565, GX/PICA packet bounds, transfer dimensions/flags и находит кандидатов одинакового input digest. Проверен на software600 против normal checkpoint: [capture audit](software-capture-audit.json). Полученную аппаратную папку сначала архивировать без изменений, затем анализировать этой командой. Новых общих контролей или серии CIA наугад не требуется.

## 6. До управляемой сцены

Остались: получить одинаковое раннее hardware/software draw state и локализовать расхождение; отдельно решить transition compositing фрагментов; подтвердить cleanup на реальной консоли; учесть поздний memory peak/loader progress; затем открыть короткое окно оригинального меню/загрузки3D и закрывать только реально встретившиеся GPU состояния. Управление Айзеком имеет смысл после устойчивой сцены. Звук, произвольный in-process unload/reinitialize и полноценный gameplay не проверены. HOME lifecycle в реальной ОС и блокировки внутри SDK/original calls эмулятором не гарантированы.
