# Controls 0.1.6 hardware: guard готов, DOWN не зарегистрирован, START exit подтверждён

Получен один аппаратный run-0001. Пользователь измерил **9мин14с от стартового A до Select Difficulty**, нажал нижнюю кнопку **крестовины D-pad** (подтвердил отдельно, это не Circle Pad), Easy не выделилась даже после ожидания более4мин. После START вернулся в HOME примерно за1–2с. Фото показывает исходное меню с выделенным Normal и подпись DS Menu Controls0.1.6 / FRAME FAIL.

## Что установлено по логу

**Новый guard работает на настоящей 3DS:** начиная с frame4200зафиксированы59наблюдений phase2/transition0/closing0, ready1/selection1, original BTN_NORMAL checked4/BTN_EASY0. Это реальное оригинальное состояние при аппаратном CRC95b893de, отличающемся от Azahar. Прежняя проблема framebuffer admission не повторилась. Все59stable raw побайтно совпадают с original hardware menu0.1.5.

**Само нажатие DOWN в журнал не попало.** Нет ни CONTROL, ни HID_REJECT. Все записанные MENUSTATE имеют held0/down0. Эти snapshots редкие (обычно каждые120callbacks); отдельный relevant DOWN edge адаптер тоже обязан был бы записать, но такого edge нет. Поэтому нет доказательства доставки ввода оригинальному движку, выбора Easy или подтверждения сложности. Причина пока **не установлена**: данные не позволяют отличить потерю короткого нажатия между scans/длинными callbacks от другой проблемы захвата HID. Не объявлять неисправность крестовины и не приписывать пользователю использование Circle Pad.

Следующий адресный шаг — воспроизвести короткие физические pulse между render samples и влияние дополнительного sensor hidScanInput, добавить независимые timestamps/raw button transitions и диагностировать захват/удержание событий до render boundary. Нельзя снимать guard или принудительно менять выделение/оригинальное состояние, чтобы скрыть отсутствие события. Это направление следующего исследования, а не уже доказанная причина или готовое исправление.

**START зарегистрирован и завершил приложение штатно:** sourceSTART,11208callbacks (меньше cap12000), одна попытка shutdown, cleanupcomplete/safe_exit=true. Пять оставшихся workers done1/kernel_wait0; после join0worker handles; IO174/174/active0, stdio/appdata/dirs0, GL_error0/failedsubmits0, exit.txt/PROCESS return. Ни STOPPED, ни HOME/APT-close request нет. Независимого аппаратного измерения освобождения SDK heaps/доказательства отсутствия любых UAF нет. Скорость1–2с — наблюдение пользователя, точного timestamp START→HOME в логах нет. HOME→X этой версии здесь не проверялся.

## Реальная задержка и производительность

Теперь измерен индивидуальный **NativeOnDrawFrame4132:297416,915мс (~4мин57с)**. Тот же129-entry texture allocation sequence, что в старом hardware4343и software probes. Счётчики подтверждают исходную рабочую нагрузку:1146glDrawElements,201texture page saves/166loads,367точных табличных CRC на1069965312bytes. Original resource loader IO за этот callback0bytes/0reads/0completions; это не ожидание загрузочного worker.

Вложенные измерения callback4132:

| Участок | Время |
|---|---:|
| glDrawElements, включая residency/GPU preparation |283844,947мс|
| CPU texture residency, включая CRC и paging |220268,407мс|
| Табличный page CRC, входит в residency |50720,375мс|
| DS34 begin: CPU preparation/uploads/waits |63097,015мс|
| DS34 end: CPU submission |197,344мс|
| glTexImage2D |13382,961мс|
| Измеренное queue wait |95,479мс|
| Измеренное VBlank wait |1339,810мс|

Нельзя складывать вложенные времена. Разность residency−CRC около169,55с включает IO/paging/allocations/остальную обработку, их точные доли пока не разделены. Статистика loader IO не учитывает texture-page stdio, поэтому0resource_bytes не означает отсутствие SD IO. Главный остаточный расход остаётся в compatibility pager, не в измеренном ожидании GPU completion.

Полное120-callback window с тяжёлой фазой —305597,874мс; в0.1.5соответствующее окно473285,745мс. Часть загрузки стала короче, но **полный измеренный пользователем запуск всё равно9:14**. Сумма SDK loop windows до первого saved menu552702,079мс (~9:12,7), без initialization; согласуется по порядку с наблюдением. Старый пользовательский замер0.1.5был приблизительным, поэтому гарантированный процент ускорения всего startup по пользовательским временам не заявляется. Индивидуальное старое callback4343не имело отдельного timer; нельзя выдавать473с за его точное измерение.

Stable hardware menu: **23,20FPS с диагностикой** (frame4320…11160). Средние на callback: original16,31мс, present16,73мс, diagnostics8,24мс; queue3,10/VBlank12,46мс уже входят в соответствующие измерения. Память в Prod124: peak normal19746816bytes (~18,83МиБ), linear104635264/104857600bytes (headroom222336bytes), commit126775296/130023424bytes, runtime allocation failures/donor refusals0. FRAME FAIL/ea733050 и исходное расхождение изображения сохранены. Gameplay не начат.

## Evidence и текущий gate

Все **200files/27664767bytes** скопированы отдельно в private `analysis/hardware/native-game-controls-v0.1.6-user-run-0001/`. Исходная `porting/ds-native-game-v0.1.6/run-0001/` не менялась. Проверены SHA256/размеры каждой копии;93raw/readback CRC пары независимо проверены zlib/RGB565,93GX файла имеют заявленные размеры и не помечены усечёнными. Полного анализа каждого GPU register этим не заявляется. Фотография остаётся в сообщении пользователя.

Прежний software release gate сохранён в этом каталоге. Текущий gate: hardware_tested=true, guard_ready/menu/safe_START_exit=true, hardware_buttons_confirmed=false, root_cause=false, ready_for_one_separate_hardware_test=false. **Повтор этой CIA ради тех же данных не нужен.**

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python porting/tools/analyze_native_game_controls_hardware.py
```

[Численный результат](hardware-result.json), [наблюдения](user-observations.json), [manifest](archive-manifest.json). Код игры/runner/input/GPU/shaders/baseline не менялись при разборе; новых сборок/CIA/emulator/hardware запусков, staging/commit/push нет.
