# DS Startup Test 0.1.0 — Legacy, только memory mode

**Аппаратный PASS получен:** пользователь прислал ready/result/exit и подтвердил возврат в HOME после START. Измерено64MiB limit,400KiB commit до heap,4MiB heap delta. [Аппаратный отчёт](../analysis/native-startup-legacy-v0.1.0/hardware-report.ru.md). Повторный запуск не требуется.

CIA малого startup, аппаратный запуск выполнил пользователь. Агент аппаратных запусков не выполнял. Это проверка startup: без оригинального движка, игровых файлов, DS34/Citro3D/PICA. Стандартные SDK gfx/console используются для текста на LCD.

## Подготовленный файл

- [startup-legacy.cia](build-native-startup-v0.1.0-legacy/startup-legacy.cia), **146880 bytes**.
- SHA256: `0bc9e96b059c0a0c4d4125afb5525ff7f0726eb9a96a03799c4b74786b1d9fe9`.
- Title ID **000400000FDE7200**, HOME **DS Startup Test 0.1.0**, product `CTR-H-DSST`.
- Это **тот же Title ID**, что у прежнего startup0.1.0: установка заменит только этот тест. Игровая CIA FDE7100 и DS34 UV Mask FDE6F00 не заменяются. Оба исходных CIA-файла на компьютере сохранены.
- Взяты сохранённые ELF, icon и banner; компилятор/линкер не запускались. ELF SHA256 `29fd6587561fdc13f2a68e5528366eacfea21ed181efc66afe23150f99f9e839`, совпадает с178MiB-вариантом.

Меняется только **New3DS SystemModeExt178MB → Legacy**. Сохранены кучи2+2MiB, stack256KiB, kernel2.44, SVC permissions, службы, идентификаторы и весь код. В фактическом exheader изменены два представления этого поля — offsets **0x20d** и **0x60d**, значение **02→00**. Также закономерно пересчитана подпись AccessDescriptor0x400..0x4ff; RSA public key тот же. Остальные настройки exheader и весь ExeFS побайтно совпали. Подпись не выдаётся за изменение kernel/SVC. [Полное сравнение](../analysis/native-startup-legacy-v0.1.0/exheader-comparison.json).

**Надпись `Declared N3DS mode: 178 MiB` и JSON-поле `declared_New3DS_mode_MiB:178` остаются прежними**, потому что они зашиты в неизменённый ELF. Для этого эксперимента они не отражают режим упаковки. Фактический режим подтверждают exheader, `pre_heap_limit_bytes` и `APP_region_bytes`; в Azahar они равны67108864bytes/64MiB, layout ID6. Не менять надпись патчем кода в этом эксперименте.

## Программная проверка

Три последовательных запуска **payload из готовой Legacy CIA** в одном Azahar core/SD: main→READY→START, GSP ReleaseRight, освобождение обеих куч **до host unload**. Ошибок unmapped/exception/assertion не обнаружено. Каждый цикл: limit67108864, current до heap409600, delta4194304bytes. Нижний экран READY визуально проверен. [Результаты](../analysis/azahar-native-startup-legacy-v0.1.0-r2/result.json).

Эти три цикла — программный PASS. Последующий аппаратный PASS main/READY/START/HOME зафиксирован отдельно по полученным файлам и ответу пользователя. Legacy64MiB не является решением для оригинального движка с нынешним бюджетом172MiB.

## Инструкция после отдельного разрешения

1. Проверить SHA256 именно `startup-legacy.cia`, поместить его, например, в `SD:/cias/` и установить обычным CIA installer. В HOME название и версия **не изменятся**: одинаковые метаданные нужны для изоляции эксперимента. Не запускать старый файл178MiB по ошибке. Игровые ресурсы/APK/.so не требуются.
2. Один запуск **DS Startup Test 0.1.0**. Ожидается нижний экран **MAIN REACHED / READY - START exits**; верхний пустой. A ничего не запускает. Записать показанные limit/current и результат probe. Старая строка178MiB ожидаема, см. пояснение выше.
3. Нажать **START один раз**, подтвердить возврат в HOME. `exit.txt` отмечает только намерение выйти; возврат нужно наблюдать отдельно.
4. Если появилась диагностика, сохранить целиком новый `SD:/3ds/ds-native-startup-v0.1.0/run-NNNN/`: `ready.txt`, `result.json`, `exit.txt`. Путь **тот же**, поскольку ELF тот же; существующие run программа пропускает. Сохранить папку на компьютере отдельно, например `startup-legacy-user-run-NNNN`, и указать SHA CIA. При недоступном SD ожидается сообщение на экране; START остаётся доступным.
5. При чёрных экранах или отсутствии выхода результат FAIL; повторных запусков и автоматического перехода к другим тестам эта инструкция не разрешает. Если папка отсутствует, её не нужно создавать повторным запуском.

PASS покажет, что переход на Legacy устраняет симптом **этого малого startup** при kernel2.44 и прежних permissions. Он не докажет совместимость большого игрового бюджета или аппаратную причину внутри системы. При таком же FAIL следующая отдельная проверка — kernel version, затем по необходимости SVC permissions, по одному фактору и с новым согласованием. В этой сборке они не менялись.

Сборщик `python porting/tools/build_native_startup_legacy.py` перепаковывает сохранённый ELF и отказывается перезаписывать готовые build/evidence. Runner `python porting/tests/smoke_native_startup_legacy.py` использует сохранённый startup smoke test с заменой только host-путей и имени CIA, исходный runner не редактируется. [Отчёт](../analysis/native-startup-legacy-v0.1.0/report.ru.md).
