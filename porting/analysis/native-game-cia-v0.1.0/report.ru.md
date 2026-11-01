# Первая experimental native-game CIA, 31.10.2026

**Дополнение после аппаратного испытания пользователя:** h2 зависла до намеренного A, оба экрана чёрные, READY не наблюдался, выключение удержанием Power. Аппаратный статус — FAIL, причина не установлена; дальнейшие запуски пока не предлагать. [Новая запись](../hardware/native-game-v0.1.0-h2-user-result.json), [startup-разбор](../native-game-h2-user-hang/report.ru.md). Всё ниже — сохранённый отчёт о подготовке и software tests до этого hardware результата; он не подтверждает аппаратную совместимость.

**CIA собрана и проверена как CIA, включая штатную установку в Azahar.** Это один оригинальный startup/UI кадр с Айзеком/наушниками, не gameplay. Аппаратный запуск не выполнялся и не разрешался автоматически.

- CIA: `3ds/build-native-game-v0.1.0-h2/native-game.cia`,336320 bytes; SHA256 `90fb19919c1b132e30fed0936802375d2ccecfdbb7d9c504d5edbef131d35622`.
- Название HOME **DS Native Game0.1.0**, Title ID **000400000FDE7100**, product `CTR-H-DSNG`. Прежние диагностические titles/baseline не заменяются.
- CXI/извлечённый CIA payload/установленный `.app` имеют один SHA256: `ca6682dd98a63555de53267c47c9d5a29b80b279f6c31adbc817c1e0d80357e0`.
- Ветка `feat/native-game-cia`, HEAD прежнийd30fcc5. Без commit/push. APK/оригинальные библиотеки/ресурсы/снимки кадра не включены в CIA или распространяемый ZIP.

## Что изменено относительно s16

Созданы отдельные `tests/native_game.c`, `tools/build_native_game.py`, `tests/smoke_native_game.py`, `tests/smoke_installed_native_game.py`, инструкция `3ds/README-native-game.ru.md`. Основные native-frame main/builder/runner и его s16 доказательства не изменялись.

Новый main — копия рабочего entry point: новое имя/SD diagnostics root/private appdata namespace и журнал переходов стадий, подробные результаты RX flush/query. Повторяющаяся стадия DrawFrame в финальном h2 не пишет SD на каждом callback. Процедуры кооперативного shutdown не переписывались. Генерируемые DS7/DS6/DS8 adapters, C renderer и shader вh2 побайтно равныs16; полные UV outputs и RGBA8→RGB8/flags1000 сохранены. CPU/GPU baseline harness не менялся.

Builder проверяет все hashes/три safe-exit цикла s16, компилирует новый main с теми же SDK/overlays, создаёт отдельный CXI. CIA разрешается только после трёх успешных циклов нового CXI и сверки hashes. Пакет разрешается только после проверки CIA container, её payload и installed-content runs. Runtime читает donor с SD; ни donor binary, ни baseline pixels не компилируются в приложение. Выбор момента кадра остаётся по CRC реального output из original callbacks.

## Проверена именно собранная CIA

1. `ctrtool --verify`: все content/exheader/ExeFS/sections hashes GOOD. Ожидаемые homebrew ошибки подписи только Ticket, TMD, AccessDescriptor. Они не маскируются под Nintendo signatures; нужен CFW. `CIA-container-audit.txt`, `preflight.json`.
2. Из **готовой CIA** извлечён NCCH payload; offset14592/size306688, TitleID проверен. Его bytes, а не произвольный старый ELF/CXI, выполнены в Azahar libretro2126.2 три раза.
3. Официальный Qt Azahar2126.2 `--install` установил **эту CIA** в новый изолированный portable user directory. Лог Service.AM подтверждает successful installation. Установленный `00000000.app` побайтно равен CIA payload. `CIA-install.log`, `CIA-install.json`.
4. Этот **установленный `.app`** выполнен тем же Azahar libretro core ещё три раза. Wrapper только выбирает установленный файл после проверки его hash и повторно использует все исходные проверки; результаты помечены `loaded_installed_content=true`.

| Финальный h2 | Циклов | Exact96000 pixels | Шесть kernel exits/0handles | START/оба heap freed | Memory/guest exceptions |
|---|---|---|---|---|---|
| CXI до сборки CIA | 3 | PASS | PASS | PASS | 0 |
| Payload извлечён из CIA | 3 | PASS | PASS | PASS | 0 |
| `.app` после штатной установки CIA | 3 | PASS | PASS | PASS | 0 |

Во всех девяти: оригинальные209 constructors/JNI/lifecycle/draw callbacks; CPU fragments/samples0, GLES0, failed submits0; полный BGR8→RGB565 baseline match, без загрузки сохранённой картинки. Состояния `done=1` дополнительно подтверждены `svcWaitSynchronization(saved_handle,0)==0`, затем handles/stacks освобождены. JNI cleanup13, IO open/close balanced, directories0; GPU завершён до возврата main. Normal40MiB и linear132MiB heap освобождены **в каждом** процессе до host unload. Последовательные циклы используют один core/SD внутри каждого набора; старые cleanup markers не учитываются.

Исходное изображение финального installed cycle просмотрено: тот же экран Айзека/наушников. Оригинальные raw/PNG остаются private evidence.

## Ранний неуспешный прогон не скрыт

Ранний h1 прошёл два цикла, после чего в третьем упал **host DLL** `azahar_libretro.dll`, Windows exception `0xc0000005`, RVA326ccf (`movzx r10d,byte ptr[rdx+3]`). Guest exception или frame result не были получены. Точная причина/связь с guest state не установлена; это не доказанный guest use-after-free и не доказанный исправленный emulator bug.

Первый запуск сохранён в `analysis/azahar-native-game-v0.1.0-cxi/`, сводка `initial-host-crash.json`. Повторный h1/a2 прошёл все3 cycles. Финальный h2 уменьшил лишний диагностический SD I/O; его девять циклов прошли без этого сбоя. Не утверждаем, что сокращение I/O исправило DLL. Риск остаётся явно зафиксированным; h1 не выпускается вместоh2, его сбой не переименован в PASS.

## Native совместимость: статическая проверка и её пределы

`preflight.json` проверяет pinned donor ELF attributes **ARMv5TE/Thumb1/VFPv2** (совместимый ISA для ARMv6K/VFPv2 New3DS), отдельно размещённые image/arena/trampolines и page ranges. Donor RX `[0,4337664)`/1059pages не пересекается с RW `[4337664,4792320)`. Ещё3 RX pages принадлежат fail-stop trampolines. Relocations/imports закончены до FlushProcessDataCache→ControlProcessMemory RX→QueryProcessMemory полного покрытия/permRX→entire I-cache invalidate→constructors. На native ошибка любого шага не пропускается; на emulator RX остаётся честно `native_verified=false`.

Профиль178MiB, normal40MiB/linear132MiB;128MiB shared donor arena оставляет4MiB linear для GPU/прочих буферов. Итоговый NCCH имеет только `.code`,banner,icon,logo, без RomFS. Скомпилированная программа/stack укладываются в оставшийся application budget; индивидуальные allocations проверяются. Это **не замер native peak** и не доказательство будущей3D gameplay памяти.

Exheader допускает нужные ControlProcessMemory/FlushProcessDataCache/QueryProcessMemory SVC, SD read/write/GSP/HID, application affinity толькоcore0; donor threads наследуют core0. Нет переноса чужого process-private VA в cache operation другого translation context. Подтверждение ABI SVC94 и GetSystemInfo выполнено по официальным pinned [Luma v10.0](https://github.com/LumaTeam/Luma3DS/blob/37544a0eb9f7e66a01823631ea9dfd0dc3a62ed9/k11_extension/source/svc.c) и [Luma v13.3](https://github.com/LumaTeam/Luma3DS/blob/043e2d2497f972f9194f869ff41da299835ecf41/k11_extension/source/svc.c); registry/method hashes сохранены в `references.json`. Значение probe1 для Luma согласуется с существующим ds_exec_open. Это проверка исходников, не опрос прошивки устройства пользователя.

Существующий аппаратный stage8 подтверждал маленькие native RX/C++ fixtures, аппаратный DS34 UV Mask — shader/route. **Ни один из них не является hardware PASS большого original-game bootstrap.** Остаются реальные permissions/cache coherence/1062pages, GPU адреса и команды исходного кадра, linear peak, SD timing/30s bounded loader join и совпадение checkpoint CRC при настоящей PICA. При timeout/unsupported call сохраняется FAIL и активная память не освобождается.

## SD и пакет

Приватная SD-папка `porting/private/native-game-v0.1.0-sd/3ds/deadspace/`:1728 core assets/414822611bytes,20 APK assets/163995411bytes, donor4499468bytes, derived font47036bytes и2 receipts. Всего1752файла/583364704bytes. Все source-copy SHA256 совпали; `SD-summary.json`, полный private inventory `private-SD-manifest.json` (ignored). Сам APK не нужен. Точное дерево/установка/извлечение логов в [README](../../3ds/README-native-game.ru.md).

Логи выделены в **SD:/3ds/ds-native-game-v0.1.0/run-NNNN/**, mkdir выбирает новый свободный номер. Private appdata `test-output/native-game-v010` не заменяет старый native-frame namespace. Общий disposable texture-pages adapter сохранён из baseline; в этом checkpoint paging-файлов не появилось. Сохранённые reference frame/отчёты не читаются renderer и не перезаписываются. Не копировать private originals в распространяемый ZIP.

**Можно согласовать один экспериментальный hardware trial финальной CIA**, с указанными ограничениями и сохранённым ранним host crash. Сборка не объявляется аппаратно совместимой/готовым портом. До отдельного согласования ничего на New3DS не запускать. После hardware frame+safe HOME proof — отдельная задача непрерывной оригинальной сцены и ввода Айзека; FPS/audio/control здесь не реализовывались. git push/full ARM suite не выполнялись.
