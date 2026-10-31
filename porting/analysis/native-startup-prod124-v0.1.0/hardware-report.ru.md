# Prod124 startup: аппаратный PASS — 31.10.2026

Пользователь прислал в `porting` две папки: `run-0002` и `run-0003`. Содержимое различено по фактическим memory counters, а не статическому declared178 и не одному номеру run. Оригиналы сохранены; копии в отдельных hardware archives сверены SHA256. Даты SD2011 года не используются как доказательство времени запуска.

**`run-0003`: аппаратный PASS Prod124 main/READY/START/HOME.** После проверки файлов пользователь отдельно подтвердил **«Да, вернуло в HOME»** на вопрос именно о последнем Prod124 запуске. `exit.txt` сам по себе этого не доказывает.

## Фактический результат Prod124

| Поле | Значение |
|---|---:|
| environment | native |
| main_entered / probe_valid | true / true |
| pre_heap_limit_bytes / APP_region_bytes | **130023424 = 124MiB** |
| APP_memtype_raw | **6** |
| pre_heap_current_bytes | **409600 = 400KiB** |
| pre_heap_available_bytes | 129613824 |
| normal_heap_bytes / linear_heap_bytes | 2097152 / 2097152 |
| heap_commit_delta_bytes | **4194304 = 4MiB** |
| post_heap_current_bytes | 4603904 |
| heap_wrapper_calls | 1 |
| state / START_exit_requested | START_exit_requested / true |
| game_called / DS34_called / PICA_submits | false / false / 0 |

Счётчики совпадают с программной проверкой Prod124. Статические `declared_New3DS_mode_MiB:178` и `hardware_compatibility_claimed:false` оставлены самим неизменённым ELF; аппаратный итог определяется actual counters, полученными файлами и отдельным подтверждением HOME, а не редактированием guest JSON.

Ожидается подготовленный CIA SHA256 **`a9a07b6ba105ca95fa139c2fb5ea69a155b5a7e8b7b08720e73b5dd8a03f5911`**, TitleID000400000FDE7200. Идентичность установленного файла отдельно не измерялась; observed124 отличает этот результат от Legacy64. [Prod124 archive](../hardware/native-startup-prod124-v0.1.0-user-run-0003/), [машинная запись](../hardware/native-startup-prod124-v0.1.0-user-result.json).

SHA256 исходных файлов:

- result.json: `1da67bf731a8be4e035698bf91195eb9f7f95eee9f9a901ad18beb3bd60e59e0`.
- ready.txt: `8cf48d0c0d210602f0f7699f5a7ad8ceac39ca50db9b06863eeadd1c12f124c3`.
- exit.txt: `ca09942c8ced8681e1e5b82f8c9661d9493c80a88aaf92c4e56878b97139292f`.

## Дополнительная папка run-0002

Она содержит native main/READY/START с **64MiB limit**, layout6 и теми же2+2MiB heaps. Её result.json побайтно совпал с прежним Legacy run-0001 (`be820edd...`); из этого нельзя определить независимость запусков. Файл не является Prod124 proof. Возврат HOME для этой дополнительной папки отдельно не спрашивался. [Отдельный архив64MiB](../hardware/native-startup-legacy-v0.1.0-user-run-0002/).

Номер run не является глобальным ID диагностики: текущий `porting/run-0002` содержит startup logs, тогда как прежний аппаратный DS34 run-0002 уже сохранён в отдельном старом hardware archive. Эти материалы не смешиваются и не перезаписываются агентом.

## Что теперь установлено

Нормальный New3DS **Prod124 работает на устройстве** с этим startup ELF, kernel2.44, SVC permissions и2+2MiB heaps, включая возврат HOME. Подготовленные Legacy/Prod124/Dev1178 варианты имели одинаковые ELF/ExeFS и остальные настройки; переключение только memory mode дало Legacy PASS, Prod124 PASS, Dev1178 FAIL.

Это сужает исследование178 к специфике Dev1/global layout7/SYSTEM/HOME/NS-перехода. Общий запрет всех non-Legacy режимов и общая несовместимость kernel2.44/SVC для startup не подтверждаются. Точный внутренний отказ178 по-прежнему не локализован; nominal SYSTEM46MiB сам по себе не доказывает OOM конкретной службы.

**Для первого игрового кадра появилась аппаратно проверенная база124MiB.** Отдельный предыдущий software memory probe позволяет обоснованно проверить бюджет одного checkpoint под124, но эта задача ещё не выполнена: h2 по-прежнему резервирует172MiB, требует178 и выделяет arena128. Не объявлять игровую CIA совместимой с124 и не уменьшать arena/heap без отдельной программной проверки кадра/пиков/lifetime/safe_exit.

Исследование ограничений178 остаётся отдельным направлением. Автоматического повторения аппаратного теста или изменения Luma/прошивки/настроек нет. Original game callbacks/RX/GPU и шесть donor joins в этом startup вообще не вызывались; их аппаратный успех не заявляется.

239 защищённых файлов сверены по SHA, изменений нет. Новых CIA не создавалось; агент не запускал приложение в Azahar или на устройстве, push нет. Обновлены только архивы, факт аппаратного результата и документы. Build-time manifest/release-gate сохранены как историческая запись готовности **до** пользовательского hardware test.
