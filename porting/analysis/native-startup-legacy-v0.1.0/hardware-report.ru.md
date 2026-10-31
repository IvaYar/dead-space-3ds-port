# Legacy startup: аппаратный PASS — 31.10.2026

Получена пользовательская папка `porting/ds-native-startup-v0.1.0/run-0001/`: `ready.txt`, `result.json`, `exit.txt`. Оригиналы сохранены, побайтные копии с проверкой SHA256 помещены в [hardware archive](../hardware/native-startup-legacy-v0.1.0-user-run-0001/). Пользователь отдельно подтвердил: **«Да, вернулась в HOME»** после START.

**Итог: PASS малого Legacy startup — main/READY/START/HOME.** Агент аппаратное обеспечение не запускал. Идентичность установленного CIA отдельно не измерялась; ожидается подготовленный Legacy-файл SHA256 `0bc9e96b059c0a0c4d4125afb5525ff7f0726eb9a96a03799c4b74786b1d9fe9`, TitleID000400000FDE7200. Старые даты файлов SD отражают часы консоли и не используются для датировки запуска.

## Что установлено по файлам

| Показатель | Аппаратное значение |
|---|---:|
| environment | native |
| main_entered / probe_valid | true / true |
| pre_heap_limit_bytes | 67108864 = **64 MiB** |
| pre_heap_current_bytes | 409600 = **400 KiB** |
| pre_heap_available_bytes | 66699264 |
| normal / linear heap | 2097152 / 2097152 = **2+2 MiB** |
| post_heap_current_bytes | 4603904 |
| heap_commit_delta_bytes | 4194304 = **4 MiB** |
| APP_region_bytes / APP_memtype_raw | 67108864 / **6** |
| heap_wrapper_calls | 1 |
| state / START_exit_requested | START_exit_requested / true |
| game_called / DS34_called / PICA_submits | false / false / 0 |

Память измерена на устройстве, а не выведена из nominal exheader. Счётчики и START state совпали с Legacy Azahar. Статическое поле `declared_New3DS_mode_MiB:178` осталось от неизменённого ELF; реальный лимит **64 MiB**. `exit.txt` сам по себе свидетельствует о намерении выйти; фактический HOME теперь подтверждён отдельно пользователем. Это подтверждение обычного выхода startup, не аппаратный тест шести donor joins.

SHA256 полученных файлов:

- result.json: `be820edd4868ba004ebba95895b80602b6ee16055de68848e51081245bdce2d9`.
- ready.txt: `8cf48d0c0d210602f0f7699f5a7ad8ceac39ca50db9b06863eeadd1c12f124c3`.
- exit.txt: `ca09942c8ced8681e1e5b82f8c9661d9493c80a88aaf92c4e56878b97139292f`.

[Машинная аппаратная запись](../hardware/native-startup-legacy-v0.1.0-user-result.json).

## Вывод для дальнейшей работы

В подготовленных178MiB и Legacy пакетах один и тот же ELF/ExeFS; kernel2.44 и SVC permissions совпадают. Меняется только memory mode и его подпись/копия в дескрипторе. После прежнего FAIL178MiB вариант Legacy дал main/READY и HOME. **Смена режима устранила наблюдавшееся зависание этого малого startup.** Внутренняя причина несовместимости расширенного режима пока не установлена.

Нет основания менять kernel или SVC сейчас: этот набор уже работает в Legacy. Условный путь «если Legacy тоже FAIL, проверить kernel/SVC» не наступил. Нельзя автоматически переносить этот вывод на игровой h2: его собственный большой linear allocation, RX loader и оригинальные callbacks на устройстве ещё не проверены.

Legacy64 не вмещает неизменённый бюджет игры172MiB. Следующий приоритет — установить, как получить пригодный расширенный memory mode на этой аппаратной конфигурации, сохраняя рабочий Legacy startup как baseline. Поэтапное выделение памяти само по себе не увеличит лимит64MiB. Размер donor arena, heaps основного процесса и backend вслепую не уменьшаются.

Если потребуется следующий аппаратный эксперимент для различения «любой extended mode» и «именно178MiB», минимальный кандидат — тот же startup ELF с единственной сменой Legacy→124MB. Его возможный успех не решит бюджет172MiB. Сначала нужен статический разбор расширенного профиля и его требований; никаких новых CIA или аппаратных запусков в этом обновлении нет. Каждый следующий аппаратный тест требует отдельного согласования.

192 защищённых файла сверены по прежним SHA, изменений нет. GPU/shader, оригинальный движок, s16 safe_exit, h2, ZIP и прежние software/hardware evidence сохранены. Игровой кадр/потоки/GPU этим тестом не запускались. Push не выполнялся.
