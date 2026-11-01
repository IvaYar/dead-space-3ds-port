# New3DS Prod124: изолированный startup и исследование Dev1 — 31.10.2026

Ветка `diag/native-startup-prod124`. Подготовлен ровно один аппаратный кандидат: startup Prod124 из аппаратно успешного Legacy ELF. На устройстве агент ничего не запускал; Luma/прошивка/конфигурация не менялись. Предыдущие Legacy hardware PASS и Dev1178 hardware FAIL сохранены.

## Готовый вариант

CIA `3ds/build-native-startup-v0.1.0-prod124/startup-prod124.cia`,146880bytes, SHA256 **`a9a07b6ba105ca95fa139c2fb5ea69a155b5a7e8b7b08720e73b5dd8a03f5911`**. TitleID000400000FDE7200, HOME DS Startup Test0.1.0, версия/icon/banner сохранены. Это отдельный файл, устанавливаемый поверх предыдущего startup title, не игры.

ELF **`29fd6587561fdc13f2a68e5528366eacfea21ed181efc66afe23150f99f9e839`** побайтно тот же. Код не компилировался. Сохранены2+2MiB heaps, stack256KiB, kernel2.44, все SVC/службы/зависимости. RSF отличается от Legacy ровно `SystemModeExt: Legacy`→`124MB`. [RSF diff](memory-mode-only.rsf.diff).

Готовые exheader извлечены из всех трёх реальных CIA:

| Вариант | actual mode0x20d | AccessDesc0x60d | Согласованность |
|---|---:|---:|---|
| Legacy hardware PASS | 0 | 0 | 0≤0 |
| Prod124 candidate | **1** | **1** | **1≤1** |
| Dev1178 hardware FAIL | 2 | 2 | 2≤2 |

Prod124 отличается от обоих предшественников только этими двумя представлениями одного поля и производной RSA-подписью AccessDescriptor0x400..0x4ff. Подпись меняет254bytes относительно Legacy и256 относительно178. RSA public key и все прочие настройки совпали; **весь ExeFS идентичен**. Поэтому прежний178 пакет также не имеет очевидного конфликта actual>AccessDesc:02/02 согласованы. Это не доказательство совместимости его системного режима. [Все byte diffs](exheader-comparison.json), [ctrtool](CIA-container-audit.txt).

ctrtool подтвердил snake prod124MB и kernel2.44; hashes не имеют FAIL. Три прежние категории неподписанных homebrew Ticket/TMD/AccessDescriptor ожидаемы. Программный runner проверяет payload, извлечённый именно из готовой CIA, а не другой ELF.

**Три Azahar PASS** в одном core/SD: main/READY, START, GSP release, обе кучи освобождены до host unload, новых unmapped/exception/assertion нет. Actual limit/APP region **130023424=124MiB**, current до heap409600, после4603904, delta4194304bytes, APP layout ID6. [Результаты](../azahar-native-startup-prod124-v0.1.0/result.json). PNG READY визуально проверен.

В неизменённом ELF остаётся declared178 — статическая строка/JSON metadata. Для результата важны реальные counters и exheader. Путь SD также прежний; новые run создаются без перезаписи. Аппаратного PASS Prod124 пока нет. [Инструкция и исходы](../../3ds/README-native-startup-prod124.ru.md).

## Что означает178MiB для системы

По опубликованным результатам reverse engineering FCRAM partition номинально такой:

| Режим New3DS | Физическая APPLICATION | Доступно приложению | SYSTEM | BASE | Layout ID |
|---|---:|---:|---:|---:|---:|
| Legacy при old-mode64 | 124MiB | **64MiB** | 100MiB | 32MiB | 6 |
| Prod | 124MiB | **124MiB** | 100MiB | 32MiB | 6 |
| Dev1 | 178MiB | **178MiB** | **46MiB** | 32MiB | 7 |

Legacy и Prod имеют одинаковую физическую раскладку; Legacy снижает предоставляемый app limit. Dev1 перераспределяет54MiB из SYSTEM в APPLICATION. Это номинальная карта; фактический SYSTEM устройства/расход Luma этим startup не измеряется. [Memory map](https://www.3dbrew.org/wiki/Memory_map), [Extended Header: mode/AccessDesc/Legacy](https://www.3dbrew.org/w/index.php?mobileaction=toggle_view_mobile&title=NCCH%2FExtended_Header).

Первичный исходник Luma13.3 PM при layout6 читает New3DS mode из exheader и для Legacy задаёт old-mode limit. Это согласуется с аппаратным Legacy limit64 и его APP layout6; простой лимит процесса и глобальная физическая раскладка — разные вещи. Там же reslimit initialization исходит из фактических APP/SYSTEM region sizes. [Pinned launch.c](https://github.com/LumaTeam/Luma3DS/blob/043e2d2497f972f9194f869ff41da299835ecf41/sysmodules/pm/source/launch.c#L230), [reslimit.c](https://github.com/LumaTeam/Luma3DS/blob/043e2d2497f972f9194f869ff41da299835ecf41/sysmodules/pm/source/reslimit.c#L255).

Dev1 требует другого глобального memory layout; его нельзя получить увеличением `__ctru_heap_size` или поздним выделением памяти в уже работающем Prod. Запуск/возврат обслуживают NS/APT/HOME, а не только CRT приложения. Документация HOME описывает reboot при несовпадении текущего APPMEMTYPE с default. [HOME startup](https://3dbrew.org/wiki/Home_Menu).

Официальный config template Luma13.3 прямо предупреждает о краше HOME для non-normal layout в контексте **autoboot homebrew**, включая Dev1. Это **не доказательство**, что данный CIA обязан зависать при обычном запуске: контекст autoboot отличается, версии/настройки пользователя не опрошены. Это подтверждённое ограничение, объясняющее приоритет проверки системного перехода и жизненного цикла HOME. [Pinned Luma config template](https://github.com/LumaTeam/Luma3DS/blob/043e2d2497f972f9194f869ff41da299835ecf41/arm9/data/config_template.ini#L162).

Вывод-**гипотеза**: прежний FAIL может происходить при попытке перехода к Dev1/инициализации системного окружения178, до наблюдаемого main. Уменьшение SYSTEM, отсутствие готового перехода или ограничения HOME согласуются с симптомом, но точный отказ NS/PM не локализован. По отсутствию логов нельзя объявить конкретный service/OOM/firmware bug доказанным. Prod124 проверяет повышение app limit без требования Dev1 layout7. Инструкций менять системные настройки, autoboot, firmware или Luma здесь нет.

Исходники Luma скачаны по pinned commit, URL/SHA в [references.json](references.json), copies остаются локально. Прямой web fetch3dbrew возвращал403; использованы доступные индексированные тексты этих страниц. Их сведения не выдаются за измерение SYSTEM пользователя. Установка/запуск CIA в Azahar не воспроизводит полный системный HOME→NS→FIRM переход настоящей консоли.

## Интерпретация одного следующего аппаратного теста

- **READY/actual124/START→HOME:** нормальный New3DS Prod запускается с теми же kernel/SVC/code; исследовать178-специфику SYSTEM/HOME/глобального режима отдельно. Можно переходить к отдельной программной проверке бюджета игрового checkpoint под124.
- **Тот же black-screen FAIL:** приоритет общий путь явных non-Legacy requests/NS/PM/loader. Нельзя обвинять172MiB или donor — их в startup нет. Actual/AccessDesc уже сверены; дальнейшие проверки kernel/SVC нужны только отдельно, не все сразу.
- **READY/actual64:** запрос124 не реализован ожидаемым образом; различить идентичность установленного файла и принудительный compatibility limit/launch flags. Это не Prod124 PASS.
- **READY/actual124, но HOME нет:** startup gate пройден, exit gate нет; разбирать APT/HOME/cleanup по имеющимся данным без автоматического повторения.

Новая hardware-проверка ещё не разрешена и не выполнялась. Не повторять178 и не выпускать игровую CIA под124 на основании этого startup.

## Память оригинального кадра

Отдельно выполнен **один** Azahar-only native-game memory probe с неизменными40+132MiB/arena128, GPU и shutdown overlays h2. Прежний harness и baseline не редактировались. Original frame совпал96000/96000pixels, шесть kernel joins и safe_exit PASS. Подробные counters/границы применимости — [отчёт памяти](../native-game-memory-v0.1.0/report.ru.md).

Наблюдаемая составляющая backing/allocator use около32MiB намного меньше172MiB reservation, поэтому124 для одного checkpoint **правдоподобны, но не проверены**. В текущем h2 есть явный guard>=178 и обязательный128MiB block; без отдельного обоснованного изменения он124 не поддерживает. Для всех сцен памяти ещё недостаточно данных.
