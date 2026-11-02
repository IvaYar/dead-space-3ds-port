# Menu Controls 0.1.6: оригинальное состояние ввода и задержка pager

**Последующее аппаратное испытание:** original menu и guard ready1 подтверждены, но DOWN не зарегистрирован, аппаратный выбор сложности не получен. START exit штатный; startup9:14, индивидуальный тяжёлый callback4:57, hardware23,20FPS. [Аппаратный разбор](../native-game-controls-v0.1.6-hardware/report.ru.md). Повтор этой CIA не нужен. Ниже сохранён отчёт software этапа; успешный ввод относится к Azahar.

В Azahar OpenGL исправлен ввод оригинального Select Difficulty. UP/DOWN переключают Normal/Easy, A подтверждает выбор: после оригинальных callbacks слой переходит в phase3/closing1, затем pilot завершает два callback после A и штатно выходит. Новая сборка сохраняет exploratory FRAME FAIL и frozen oracle ea733050. Программно проверена одна новая CIA; на приставке0.1.6 не запускалась.

**B доставляет original Android BACK DOWN/UP, но возврат с первого difficulty screen не работает:** оригинальный обработчик LayerDifficulty явно игнорирует BTN_BACK. Принудительный pop слоя, ручное изменение состояния игры и имитация возврата не добавлялись. Это открытое ограничение, а не доказанный успешный возврат B. START остаётся отдельным штатным выходом.

## Допуск ввода

`native_menu_engine_state.h` читает live modal reference оригинального application singleton, проверяет LayerDifficulty vtable и его phase2/transition0/closing0. Затем вызывает **оригинальный readonly widget-map lookup** с заимствованными именами BTN_NORMAL/BTN_EASY и читает их checked-state. Ничего в original object graph не записывается. Это отличается от предварительной гипотезы profile getter: enum difficulty включает также SOFT/HARD/NIGHTMARE и не является двухпозиционным UI индексом; неудачные p3–p6 сохранены, этот подход не используется в итоговом guard.

`native_menu_controls.h` больше не получает CRC/framebuffer. Он использует собственные edges по hidKeysHeld, реальные original selection/готовность и защиту короткого pending pointer pulse. Повторное касание уже выбранной строки не отправляется, поскольку оригинальный обработчик может трактовать его как подтверждение. A и D-pad проходят через прежний DS23 softfp `NativeOnPointerEvent`; B — `NativeOnKeyDown/Up`, module600/key4/isSystemKey0. Навигация не меняет выделение своими средствами. Нажатия, состояние и причины отказа пишутся в MENUSTATE/CONTROL/HID_REJECT.

**Регрессия несовпадающего изображения проверена двумя способами:**12групп ARM contract checks включают hardware CRC95b893de, произвольный другой CRC и нулевой CRC при готовом меню; события допускаются, FRAME FAIL сохраняется. В настоящих integration runs кадр3360 имеет7296717d≠ea733050, вслед за ним original DOWN3361 реально меняет checked-state и следующий сохранённый кадр показывает Easy. Последовательность DOWN→UP→DOWN→A подтверждена оригинальными объектами и raw. Эти CRC используются только офлайн для диагностики; runtime admission их не читает. Unit lookup является ABI fixture, интеграционные прогоны исполняют оригинальный lookup/объекты/движок без fixture.

Численные точки исследованного donor contract: singleton slot44a1b4, live modal+d8, LayerDifficulty vtable427dd8, phase+cc, base transition+18, closing+44, checked-state button+64. Верифицированный donor/resources остаётся обязательным, контракт не заявлен переносимым на другую .so. APK/.so/код движка не публикуются.

## Причина долгой загрузки

В присланном hardware0.1.5 логе TEXALLOC локализует **callback4343:129выделений текстур** внутри окна4321…4440длительностью473285,745мс. Отдельного timestamp входа/выхода4343 старый лог не содержит: точное аппаратное время только этого callback не восстановлено. Большой callback относится к первой подготовке ресурсов/атласов меню; вторичные allocations4375/4376 также попадают в окно.

Последовательность всех129texture allocations (размеры, linear/VRAM policy и результат) совпала у hardware4343, software p5 и итогового fast callback. Это дополнительное подтверждение воспроизведения той же фазы; оно не превращает software timings в аппаратные измерения отдельных вызовов.

Новые CALLBACKJSON измеряют каждый медленный NativeOnDrawFrame и вложенные glDrawElements/glDrawArrays/glTexImage/SubImage/clear/finish/readback, DS34 begin/end, CPU texture residency и CRC. Есть количество вызовов, максимальная длительность, donor caller offset, обработанные CRC bytes, texture page saves/loads, loader IO bytes/reads/completions и queue/VBlank waits. Короткие кадры суммируются прежним PERFJSON. Вложенные времена пересекаются: их нельзя просто складывать.

Воспроизведение этой фазы в Azahar CPU100:

| Метрика одного тяжёлого callback | До исправления p5 | Итоговый final2 |
|---|---:|---:|
| Всего SDK guest time |382729,663мс|202122,103мс|
| glDrawElements |1146вызовов|1146вызовов|
| Texture page saves / loads |201 /166|201 /166|
| CRC страниц |367вызовов|367вызовов|
| Bytes через page CRC |1069965312|1069965312|
| Время page CRC |212316,621мс|около32053мс|

Причина значительной части задержки — **дополнительная работа совместимости**: рабочий набор атласов не помещается в6МиБ CPU texture residency, pager многократно пишет/читает страницы, для которых прежний побитовый CRC32 повторно обрабатывает более1ГБ. В p4 residency заняла333835,726из382429,001мс. DS34 begin около37,7с, end около0,12с в этой фазе; ожидание завершения loader из старого hardware shutdown — другой этап, оно не объясняет этот профиль. Это не основание пропускать original draw/resource operations.

**Минимальное исправление:** только в изолированной копии native texture-page adapter два вызова page CRC заменены на точный CRC32/IEEE с неизменяемой256-entry таблицей. Размер/CRC header, EOF/error checks, чтение всего payload и сравнение CRC сохранены. Original `ds_crc32` для donor/font/image и независимый bitwise readback не менялись.81ARM test vector сравнен с неизменённым ARM ds_crc32 и host zlib, включая unaligned buffers, полный4МиБ payload и5одноразрядных повреждений. Все повреждения отвергнуты. Никаких доверительных CRC receipts или пропуска проверок нет.

Результат: тяжёлый callback сократился **на47,19% (1,89раза)** по SDK ticks Azahar; сама page CRC — примерно6,6раза. Пять пар сохранённых menu raw из p5/p6 совпадают **побайтно** после замены page CRC. Операции pager и оригинальные1146draws остались. Не утверждается, что новая CIA уже грузится вдвое быстрее на реальной приставке: это предстоит измерить аппаратно. Оставшийся SD paging всё ещё дорогой; его устранение потребует отдельной проверки working set/lifetimes, без изменений baseline и без переписывания GPU.

## Стабильность и границы

Проверенный итоговый source — final2. **Три последовательных запуска в отдельных холодных Azahar processes** прошли одинаковую навигацию, B down/up и A4321→original phase3/closing1 на4323→complete cleanup. Дополнительно: ранний START после720callbacks с6worker joins и HOME fixture перед3900с5worker joins. Во всех пяти: safe_exit=true, active handles0, balanced IO, GL_error/failed_submits0, invalid guest memory accesses0, реальный process teardown/GSP release и освобождение обеих SDK heaps. HOME screenshot readiness shim существует только в fixture; затем выполняется реальный SDK wakeup-cancel после quiescence. В CIA test SDK/shim отсутствует. Физический HOME→X0.1.6 пока не проверен; аппаратное доказательство0.1.4 сохранено.

GPU backend/shaders/runtime файлы **byte-identical0.1.5**, shutdown source после run byte-identical с учётом строки версии. Prod124 сохранён: normal20/linear100/arena85,5МиБ. Peak normal footprint≤18964480bytes (~18,09МиБ), linear104635264/104857600bytes, transient headroom222336bytes. Commit укладывается в130023424bytes. Refusals/runtime allocation failures0. Бюджет первой сцены и отсутствие любого возможного аппаратного use-after-free этим не доказаны.

Stable FPS с диагностикой: **44,62…44,87 CPU100 /51,92 CPU400 в Azahar**. Аппаратное измерение предыдущей0.1.5 остаётся24,02FPS; новых аппаратных FPS нет. Initial font GX observer может сохранять только bounded prefix, если длинный кадр совпадёт с checkpoint: такие случаи отдельно перечисляет software-audit, они не выдаются за полный GX proof. Все стабильные input captures должны быть полными; raw/readback CRC проверяются независимо в любом случае.

Первая сцена с Айзеком **не включена**: прежние original audio NULL-read и fog blockers остаются. После A подтверждено настоящее закрытие оригинального меню, продолжение намеренно ограничено двумя callbacks. Следующая работа — original audio initialization contract и минимально необходимые scene states/память, затем управление. B-return с обязательного первого экрана не имитировать.

## Пакет и воспроизведение

Ровно одна новая CIA: `porting/3ds/build-native-game-v0.1.6-final2/native-game.cia`, **DS Original Menu0.1.6**, TitleID**000400000FDE7900**,355264bytes. SHA256`9475886ff5620d9cd14ca36e3eb8487ace8fee70ddd60d673d55a65d3d5b6e0b`. Payload`cc78537c162466ca0c97cb787e1db368a14f8c05ec5ac5403253d7fc9148be1c` побайтно равен трёхкратно проверенному CXI. Новая writable namespace `native-game-menu-v016`, логи `SD:/3ds/ds-native-game-v0.1.6/run-NNNN/`. Existing `SD:/3ds/deadspace/` подходит.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python porting/tests/test_native_menu_controls.py
python porting/tests/test_native_menu_page_crc.py
python porting/tools/audit_native_game_controls.py --runs final2:confirm,final2:repeat2,final2:repeat3,final2:earlyexit,final2home:home
```

[Software audit](software-audit.json), [input checks](input-tests.json), [page CRC checks](page-crc-tests.json), [профиль](performance.json), [история опытов](experiments.json), [release gate](release-gate.json), [аппаратный протокол](../../3ds/README-native-game-controls.ru.md).375защищённых файлов и1752master/store resources сверены SHA. Старые evidence/SD/CIA и baseline не изменены. Новых аппаратных запусков, staging/commit и push нет. Gate готов к **одному отдельно согласованному** тесту; разрешение на него не подразумевается.
