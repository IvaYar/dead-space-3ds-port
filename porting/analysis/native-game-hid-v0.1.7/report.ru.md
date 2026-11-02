# HID 0.1.7: наблюдение raw HID и оригинальное меню

Этот отчёт описывает завершение программного этапа до аппаратного испытания. Затем пользователь выполнил один тест: **raw D-pad, навигация Normal/Easy, оригинальное подтверждение A и предусмотренный безопасный выход подтверждены на New 3DS**. [Принятый аппаратный отчёт](../native-game-hid-v0.1.7-hardware/report.ru.md). Текущую CIA повторять не нужно. Исторические программные выводы ниже сохранены; [текущий gate](release-gate.json), [аудит восьми завершившихся процессов](software-audit.json), [сценарий выполненного испытания](../../3ds/README-native-game-hid.ru.md).

## Где теряется DOWN

В аппаратном 0.1.6 меню готово (`ready=1`), CRC не блокирует ввод, но для подтверждённого пользователем физического D-pad DOWN нет ни `CONTROL`, ни `HID_REJECT`. Потеря находится **до host → Android dispatch**. Старый лог не содержит raw HID, поэтому отличить отсутствие события в HID shared memory от пропуска опроса нельзя. Точная аппаратная причина остаётся открытой; исправление на железе пока не подтверждено.

Проверены фактические ARM-инструкции libctru из итогового ELF: `hidScanInput`, `hidKeysDown`, `hidKeysHeld`, восемь слотов HID ring, 72 сочетания. Маски правильные: DDOWN `0x80`, DUP `0x40`, START `0x08`, CPAD_DOWN `0x80000000`; общий KEY_DOWN объединяет D-pad и Circle Pad. Getters не поглощают событие. Дополнительный `hidScanInput` в штатном sensor path обнуляет Down при удерживаемой кнопке, но сохраняет Held. Нажатие и отпускание между опросами главного цикла оставляют оба getters нулевыми. [SDK proof](SDK-tests.json) использует реальные SDK-инструкции с fixture shared memory, а не физическую приставку.

Ввод основного SDK и `ds12_sensor_3ds.c` не изменён. Отдельный collector только читает опубликованное состояние HID shared memory, проверяет индекс/временную метку до и после чтения, сохраняет переходы под LightLock. Он не вызывает `hidScanInput`, JNI, donor, графику или файловый IO. Тесты Azahar используют реальные эмулируемые HID shared memory и аналоговые значения Circle Pad.

## Путь события

`HIDRAW(ms,id,index,held,down,up,circle)` → ограниченная очередь → `HIDHOST(raw,mapped,SDKdown,SDKheld,age_ms)` → `HIDMAP` → `HIDCOMPAT ENTER` → `HIDORIGINAL RETURN(duration_ms)` → `HIDACK` после следующего оригинального draw.

Host переводит ↑/↓ в события исходного touchscreen pipeline: `DS23Touch` → исходный `NativeOnPointerEvent`, module 1000, DOWN/UP `0006000c/0008000c`. Координаты исходной области 320×240 масштабируются штатным DS23; выбор меняет оригинальный движок. ACK читает исходные checked widgets Normal/Easy. После A наблюдаются исходные `phase=3, closing=1`, затем два callback и штатный выход. B доставляется исходным `NativeOnKeyDown/Up`, module 600, Android key 4, isSystemKey 0; **первый LayerDifficulty игнорирует BACK**, принудительного возврата нет.

Очередь содержит максимум 64 перехода; удержание не генерирует повторов. Переполнение регистрируется и прекращает игровой прогон, непрочитанные события не перезаписываются. Барьер готовности исключает старые нажатия из preflight/загрузки; кнопку, удерживаемую до ready, нужно отпустить и нажать снова. Перед следующим pointer press проверяются завершение предыдущего pointer и ACK. Противоположные направления подавляются, одинаковое направление D-pad/Circle Pad объединяется. START защёлкивается отдельно от очереди. Collector останавливается, kernel-join завершается и thread освобождается **до** donor shutdown и `gfxExit`.

Номинальный период collector — 4 мс, это не гарантия задержки. В итоговом Azahar CPU100 максимальный raw gap в готовом меню **135,719 мс**, при старте — около 904 мс; интервалы главного цикла достигают 202,5 с. Очередь сохраняет только реально наблюдавшиеся переходы и не восстанавливает событие, полностью пропущенное самим raw наблюдателем. Новые `max_ready_raw_sample_gap_ms` и `max_game_main_sample_gap_ms` позволят проверить это на железе. [Семь ARM-проверок очереди](queue-tests.json) включают короткий импульс, удержание, пяти-минутный разрыв consumer, overflow и барьер ready.

## Итоговые программные прогоны

| Сценарий | Результат |
|---|---|
| Raw preflight, D-pad U/D/L/R, A/B, START, отдельный Circle Pad | PASS; исходный движок не загружался |
| DOWN отсутствует, затем X | X заблокирован с missing=80; START выходит без загрузки игры |
| Короткие импульсы, по два host frame | Easy → Normal → Easy, A подтверждён; SDK Down/Held в main равны нулю |
| Удержание с отдельными отпусканиями | Те же переходы, без повторных pointer actions |
| Circle Pad down/up и физический D-pad down | Та же оригинальная навигация и A |
| START на старте исходного движка | Штатный shutdown |
| Искусственная пауза main 2 с, только test CXI | DOWN переживает 2054,936 мс очереди и меняет исходный выбор на Easy |
| HOME/X fixture, только test CXI | Quiescence перед передачей HOME; штатный SDK close |

Обычный release не содержит искусственной паузы или HOME fixture. Полные menu trials завершают 4323 callback. У всех загружавших движок прогонов: kernel join пяти native workers, остаток handles 0, IO сбалансирован, GL/failed submits 0, invalid-memory accesses 0. Отдельный HID thread также joined/freed. Это программные проверки, а не новое аппаратное доказательство отсутствия UAF.

Prod124 сохранён: normal peak **19881984 bytes**, linear **104635264 / 104857600**, kernel peak commit **126779392 / 130023424**. Linear headroom всего **222336 bytes**; игровой сцене ещё нужны отдельные проверки. GPU runtime и shaders побайтно равны 0.1.6; native shutdown functions тоже. 375 защищённых файлов и 1752 исходных файлов ресурсов сверены по SHA.

CRC по-прежнему **FAIL**, baseline `ea733050` не менялся. Аудит независимо пересчитал raw/readback и packed CRC; меню Normal `0ded835d`, Easy `223b5e75` в Azahar, оба отличаются от baseline и оба принимают ввод. Усечённый GX dump только у дорогого начального callback помечен как частичный; он не выдаётся за полный command trace. Игровые captures/ресурсы остаются private.

## Медленная загрузка

[Сохранённый аппаратный профиль и новые измерения](performance.json). В hardware 0.1.6 самый дорогой **NativeOnDrawFrame 4132 — 297416,915 мс (~4:57)**, 1146 glDrawElements, 201 page saves, 166 loads, 367 page CRC на **1069965312 bytes**. `ds15_resident` 220268,407 мс включает CRC 50720,375 мс; `ds34_begin_draw` 63097,015 мс, TexImage 13382,961 мс. Это подготовка исходных font/menu atlas с интенсивным texture paging и CPU/IO работой, а не ожидание кнопки. Нулевые reads исходного loader здесь не означают отсутствия IO texture pager. Замеры вложены: складывать их или выдавать разность за отдельно измеренный чистый IO нельзя.

Итоговый release воспроизводит тот же объём работы: slow draw около **199,9–202,5 с guest ticks** при CPU100. Номер callback меняется с scheduling. Исходные операции не пропускались; оптимизации загрузки на этом этапе нет и аппаратное ускорение не заявляется. Стабильное меню в Azahar **44,85–45,18 FPS** с диагностикой, test stall trial 42,05 FPS; прежний hardware 0.1.6 — **23,20 FPS** с диагностикой. Эти разные среды нельзя использовать как доказательство ускорения железа. Время около 48 с host wall при ускоренном прогоне также не является временем ожидания на приставке.

## Кандидат

`porting/3ds/build-native-game-v0.1.7-release/native-game.cia`, **360384 bytes**, TitleID `000400000FDE7A00`, название `DS HID Menu 0.1.7`.

SHA256: `e475440fd0cda08abb561d25ffd3c5de82a4030fc3fe59cdb6b8344e90367906`.

Payload побайтно равен проверенному CXI: `d2377e36b31d6547b0a8aead26c9e85d90416627884d9bd423d6fe4434eef318`. Проверка физических кнопок доступна сразу, **X запускает движок после PASS, A в preflight только проверяется**. После A в оригинальном меню намеренно выполняются два callback и safe exit. First-scene audio NULL/fog ограничения не исправлялись; управляемая сцена Айзека не заявляется.

Перепроверка evidence без запуска/перезаписи:

```powershell
python porting/tools/audit_native_game_hid.py --runs release:raw,release:missing,release:pulse,release:hold,release:circle,release:early,releasestall:stall,releasehome:home
```

`package_native_game_hid.py` отказывается создавать ещё одну CIA поверх существующей. Все старые builds/evidence, hardware incoming и assets сохранены; Git index не менялся, push и hardware tests не выполнялись.
