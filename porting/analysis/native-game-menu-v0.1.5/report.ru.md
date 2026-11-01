# Native original menu 0.1.5 — Select Difficulty и кнопки подтверждены, gameplay ограничен

**Получен последующий аппаратный run:** меню и штатный cap12000выход подтверждены; ввод заблокирован ошибкой guard по emulator CRC. Hardware24,02FPS с диагностикой; переход включает окно7мин53с. [Актуальный аппаратный отчёт](../native-game-menu-v0.1.5-hardware/report.ru.md). Повтор этой CIA не нужен. Ниже — сохранённые результаты software этапа; подтверждение кнопок относится к Azahar.

02.11.2026. **Оригинальный Select Difficulty получен в native entry point / DS34 / Prod124. D-pad переключает Normal → Easy → Normal → Easy. A доставляет оригинальное подтверждение.** Полная первая игровая сцена остаётся заблокирована. Подготовлена одна экспериментальная CIA ограниченного меню; аппаратного запуска и push нет.

[Численный audit](software-audit.json), [ARM input checks](input-tests.json), [история опытов](experiments.json), [визуальные наблюдения](visual-observations.json), [CIA gate](release-gate.json), [инструкция одного будущего аппаратного прогона](../../3ds/README-native-game-menu.ru.md).

## Оригинальные callbacks и меню

Сохранён существующий native bootstrap: constructors → JNI_OnLoad → MainActivity_NativeOnCreate → NativeOnSurfaceCreated/Changed → NativeOnDrawFrame. После второго draw остаются оригинальные Resume/WindowFocusChanged. При активной игре оригинальные main updates обслуживают исходный loader/delegate pipeline; первый Run0xb60bc и поздний Run0xb6e6c исполняются обычным движком.

Старый проверочный runner намеренно останавливался после exact intro sequence либо 600 callbacks. Новый отдельный `tests/native_game_menu.c` продолжает реальные callbacks, не устанавливает предполагаемое состояние игры, не рисует собственное меню и не воспроизводит запись команд. Исходный `native_game_progress.c` и его runner не менялись.

В первом длинном опыте следующий экран упёрся в реальный запрос 1024×1024 RGBA8, 4 МиБ, в VRAM. Добавлен узкий allocation/upload adapter: такие атласы размещаются в GPU-доступной linear memory; используется штатный Citro3D путь загрузки FCRAM texture — копирование и cache flush. DS34 по-прежнему владеет immutable staging, текстурой, синхронизацией и освобождением. В новой копии GPU source изменена **только константа cache capacity 4→8 МиБ**. Функции backend, shader, UV, filtering, geometry и original assets не переписывались. Другие runtime/probe файлы побайтно совпадают с 0.1.4.

Azahar OpenGL завершил реальный menu render. Основное изображение доказывается сохранённым SDK BGR8 readback после GPU completion, двумя независимыми CRC и внутренним DS34 texture/vertex audit. Преобразование raw в PNG меняет только представление данных. Файлы остаются private. У скрытого OpenGL frontend его host PNG чёрный: он **не используется как LCD-доказательство**. Software renderer дважды завершился host access violation; это отдельный неуспешный путь, а не успешная проверка меню.

## Ввод и важная особенность оригинального UI

Переиспользован DS23 и выбранный донорский `TouchSurfaceAndroid.NativeOnPointerEvent(IIIFF)V`: module1000, pointer0, DOWN0x6000c/UP0x8000c, softfp. D-pad UP/DOWN дают реальные касания Normal/Easy; A — галочки. Исходная поверхность320×240 масштабируется в400×240. B вызывает оригинальные KeyboardAndroid NativeOnKeyDown/Up(III)V, module600, Android BACK4, isSystemKey0. DEX signatures и native module getter проверены локально.

Проверены два конкретных дефекта первой интеграции:

- Sensor backend тоже вызывает hidScanInput и может потребить hidKeysDown. Новый adapter владеет edges по hidKeysHeld; удержание не создаёт повторов.
- Уже выбранная строка оригинального меню может подтвердить сложность. D-pad не нажимает её повторно. Перед навигацией наблюдается **фактически отрисованный** стабильный original menu; после события старое наблюдение инвалидируется до нового readback. Во время fade ввод ждёт. Зафиксированы исходный Normal7296717d, Normal после переключения223b5e75 и Easy0ded835d. Эти fingerprints допускают ввод и **не являются заменой frame oracle**.

В финальном CPU100 run: DOWN3361 → Easy3480; UP3601 → Normal3720; DOWN3841 → Easy3960; B4081/4201 доставлен без подтверждённого визуального действия «Назад»; A4321 → UP и исходные callbacks до4323 → штатное закрытие. Оригинальные writable saves присутствуют, включая CheckpointSave. Содержимое saves не публикуется. Физический стилус не подключён в этом кнопочном pilot, поэтому он не обходит ограничение продолжения.

Восемь групп ARM-проверок покрывают ABI/координаты, held edges, B release, ожидание fade, запрет повторного нажатия выбранной строки, stale readback и ограниченный pilot. Это не аппаратная проверка кнопок.

## Первая сцена: что действительно достигнуто

Отдельные emulator-only прогоны r8–r10 продолжили оригинальное подтверждение до первой scene render функции. В r8 обнаружилась отсутствующая привязка glFogx в native harness. Подключён **уже существующий DS30 adapter**, ранее проверенный CPU-портом; новый fog renderer здесь не создавался.

При arena80 МиБ три mmap1 609 728 / 1 597 440 / 3 133 440 bytes не помещались; наблюдались9 donor refusals и дополнительные NULL reads. Финальное перераспределение убрало отказы: arena85,5 МиБ, normal20 / linear100, application124. Исследовательский r10 получил brk64,00390625 МиБ +5467 mmap pages =85,359375 МиБ, refusals0/runtime failures0.

Однако r10 сохранил **два NULL-read** в оригинальном коде: reported donor-relative265f80/265f98, чтения0x3c/0x30. По расположению кода это область EAAudioCore; точный контракт отсутствующей инициализации ещё не установлен. Также DS34 явно отвергает fog/stencil/offset, первый фактический reject — fog0xb60. Scene callback вернулся, cleanup дошёл до kernel completion, но `safety_passed=false` из-за NULL reads. Его safe_exit marker не превращён в чистый стабильный run.

**Управляемой сцены с Айзеком нет.** Для выпуска выбран `MENU_ALLOW_SCENE=0`: после A original confirmation выполняются ещё два оригинальных callbacks и безопасный выход до известной проблемной сцены. Отдельный `--scene-probe` допускает полное исследовательское продолжение только в эмуляторе и запрещён package gate. Сцена не подменяется чёрным/заранее записанным кадром.

Circle Pad пока не подключён: после исправления audio NULL contract и нужных scene GPU states следует проверить исходный virtual joystick, look/actions и необходимость нескольких pointer IDs. Текущий DS23 — однопальцевый. Положение Айзека напрямую не изменяется и нажатия игрового процесса не симулируются.

## FPS, CPU/GPU и память

Финальные значения взяты из SDK ticks; окно120 callbacks, readback observation каждые30, полная диагностика каждые120. Это **измерения Azahar**, аппаратные FPS новой CIA ещё неизвестны.

| Стабильное меню | CPU100 / final normal | CPU400 / HOME fixture |
|---|---:|---:|
| Render callbacks / second | 40,62 | 52,07 |
| Original callback, мс/callback | 10,83 | 2,36 |
| Present, мс/callback | 8,49 | 14,01 |
| Диагностика, мс/callback | 5,28 | 2,82 |
| VBlank wait, уже включён в предыдущие интервалы | 7,80 | 13,75 |
| Последние C3D drawing time samples, мс | 0,189–0,223 | 0,106 |

C3D samples в эмуляторе не являются физическими PICA200 timings. GPU queue waits измеряются отдельно и не складываются повторно с present. FPS включает диагностику. Масштабной оптимизации нет.

Первое создание атласов существенно тяжелее steady menu: original callback time в одном120-callback окне достиг383,66s guest ticks наCPU100 /193,03s наCPU400. Полные host runs заняли115,6 /102,9s. Это не аппаратное время запуска и не SD bandwidth. Оригинальный выполняющийся callback не прерывается посреди исполнения; возможна длительная задержка обработки выхода, помимо прежнего in-flight loader wait.

Финальный Prod124: normal20 / linear100 / donor arena85,5 МиБ, application124. Kernel commit126 763 008bytes при limit130 023 424. Normal allocator footprint peak19 419 136bytes; linear used peak104 635 264bytes из104 857 600. **Временный запас linear на пике staging —222 336bytes**, поэтому дальнейшее развитие сцены требует адресного memory review. На проверенных menu/HOME runs donor refusals/runtime failures0. Для будущего gameplay запас arena и heap не доказан.

## Shutdown, CRC и доказательства

Финальные normal и HOME runs: GL0, failed GPU submits0, invalid guest memory accesses0, IO balanced, cleanup complete, PROCESS return и освобождение обеих SDK heaps. После нормального завершения detached loader остаются пять job/audio/periodic handles; все пять имеют kernel_wait0/done1 перед teardown, после join —0 handles. Их число не подменяется прежним startup-шестипоточным snapshot: loader уже завершён и reaped исходным проверенным runtime.

HOME fixture использует прежний SDK screenshot-readiness shim только в test build, затем настоящий SDK wakeup-cancel, `home_pending/close_pending=true`, sourceAPT, handover **после** quiescence и PROCESS return. В CIA нет test SDK/shims. Физический HOME→X новой версии не запускался. Подтверждённое аппаратное состояние0.1.4 сохранено.

CRC oracle по-прежнему **ea733050**, аппаратные9231 pixels/CRC_FAIL не исправлены. Новый exploratory runner сохраняет FRAME FAIL даже при успешном меню/выходе. Старый verifier, 375 protected файлов и полный master/store inventory1752 files проверены SHA; исходные assets, старые SD, baseline и предыдущие CIA сохранены.

В initial font warm callback CPU100 GX observer128КиБ сохранил **неполный prefix**:1146draw inputs, frame2880. Он не выдан за полный command-stream proof. Его raw CRC и internal DS34 audit проверены; все стабильные menu/button captures имеют полные GX traces. Эта граница явно записана в software-audit, старые проверочные правила не менялись.

## Одна CIA и воспроизведение

`porting/3ds/build-native-game-v0.1.5-r14/native-game.cia`,350656bytes, TitleID000400000FDE7800, DS Original Menu0.1.5.

CIA SHA256: `93ca2d9068bfd7ef33ca7bce33f4176dcd89de66d5bb4ede07d5a393e8b6ea43`.

Payload SHA256: `a06ee75b979594306cf9add124c9280ebead361d560c0bb86205073d0455c82f`, побайтно равен проверенному CXI. Создана **ровно одна новая CIA**. Она предназначена для одного отдельно согласованного теста оригинального меню, кнопок и ограниченного выхода.

Повторная проверка без эмулятора:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python porting/tools/audit_native_game_menu.py --runs r14-cpu100,r14home-home
python porting/tests/test_native_menu_input.py
```

Новый replay использует новые revision/attempt, не удаляет текущие evidence. Build tool сохраняет предыдущие каталоги и копирует проверенный runtime/headers; для сборки нужны существующие private prerequisites и toolchain. Packaging повторно откажется создавать вторую CIA поверх существующей.

Следующий этап — устранить оригинальный audio NULL path, затем точечно реализовать необходимые first-scene GPU states и подтвердить memory budget до первого управляемого кадра. Текст/UV/filtering не изменялись ради эмуляторных изображений. Новых аппаратных запусков, cleanup старых данных, commit/index changes и push не было.
