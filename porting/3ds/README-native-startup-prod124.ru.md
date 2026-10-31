# DS Startup Test 0.1.0 — New3DS Prod124

**Аппаратный PASS подтверждён:** получен run-0003 с main/READY/actual124MiB/START, пользователь подтвердил возврат HOME. [Аппаратный отчёт](../analysis/native-startup-prod124-v0.1.0/hardware-report.ru.md). Повторный запуск не требуется. Дополнительный run-0002 содержит64MiB и сохранён отдельно.

Изолированный эксперимент основан на аппаратно успешном Legacy startup с неизменённым ELF и кучами2+2MiB. Из функциональных настроек меняется только New3DS memory mode **Legacy→Prod124**. Аппаратный запуск выполнил пользователь. Агент не запускал приставку, не менял Luma/прошивку/настройки и не выполнял push.

## Файл

[startup-prod124.cia](build-native-startup-v0.1.0-prod124/startup-prod124.cia), **146880bytes**. SHA256:

```text
a9a07b6ba105ca95fa139c2fb5ea69a155b5a7e8b7b08720e73b5dd8a03f5911
```

TitleID **000400000FDE7200**, HOME **DS Startup Test0.1.0**, productCTR-H-DSST — прежние. Установка заменит только предыдущий startup-тест. Старые CIA на компьютере и игровые/DS34 title остаются отдельными. Имя/версия иконки намеренно не меняются, поэтому идентичность нового файла определяется SHA и измеренным лимитом.

ELF SHA256 `29fd6587561fdc13f2a68e5528366eacfea21ed181efc66afe23150f99f9e839` совпадает с Legacy и178MiB. Компилятор/линкер не запускались. Сохранены stack256KiB, kernel2.44, SVC permissions, службы/зависимости, код, banner и icon. Игры/ресурсов/DS34/PICA в этой CIA нет; SDK gfx/console выводят текст на LCD.

## Проверки

В готовом exheader **SystemModeExt=Prod(1), AccessDesc=Prod(1)**: соответствие1≤1 выполнено. В сравнении с Legacy изменены только offsets0x20d/0x60d,00→01; с Dev1 — те же02→01. Пересчитана производная подпись AccessDescriptor, RSA public key прежний. Прочие настройки и весь ExeFS побайтно совпали. [Полное сравнение](../analysis/native-startup-prod124-v0.1.0/exheader-comparison.json).

Три последовательных запуска actual CIA payload в одном Azahar core/SD: main→READY→START, GSP release и освобождение обеих куч до host unload; новых memory errors нет. Измерено **130023424bytes=124MiB**, current до heap409600bytes, delta4194304bytes, APP layout ID6. Нижний экран READY визуально проверен. Последующий аппаратный PASS main/READY/START/HOME зафиксирован отдельно по файлам пользователя; counters совпали с Azahar.

**Старая строка `Declared N3DS mode: 178 MiB` и JSON declared178 остаются в неизменённом ELF.** Они не являются измерением. Для этого теста ожидаются actual `pre_heap_limit_bytes` и `APP_region_bytes` **130023424**. Патчить надпись нельзя: это нарушило бы условие неизменности кода.

## Один запуск после отдельного разрешения

1. Проверить SHA именно `startup-prod124.cia`, поместить на SD, установить обычным CIA installer. Игровые файлы не нужны. Настройки приставки/Luma не менять. Старое178MiB приложение не запускать повторно.
2. Открыть **DS Startup Test0.1.0** один раз. Ожидается **MAIN REACHED / READY - START exits** на нижнем экране, пустой верхний. A ничего не запускает. Зафиксировать limit/current/probe и факт READY; строка declared178 ожидаема.
3. Нажать **START один раз**, подтвердить возврат в HOME.
4. Сохранить новый `SD:/3ds/ds-native-startup-v0.1.0/run-NNNN/` целиком: ready.txt, result.json, exit.txt. Путь тот же, поскольку ELF тот же; существующие run программа пропускает. Архивировать отдельно как Prod124 и указать SHA CIA, чтобы не спутать с Legacy run-0001.
5. При FAIL не повторять запуск и не переходить к другой сборке. При отсутствии папки не запускать приложение снова ради её создания.

## Что даст результат

| Результат | Вывод и следующий отдельный этап |
|---|---|
| READY, limit124MiB, START→HOME | Prod и повышение app limit работают; исследовать специфику Dev1/переразметки SYSTEM/запуска через HOME. Параллельно обоснован отдельный программный бюджет игры под124. |
| Чёрные экраны, READY/папки нет | Общий путь явных non-Legacy modes/NS/PM/loader остаётся приоритетным. Это не игровой OOM и не повод менять GPU. Kernel/SVC исследовать только отдельными последующими изменениями, без автоматического запуска. |
| READY, но limit64MiB | Запрос Prod не реализован как ожидается: проверить фактический installed title/launch flags/forced compatibility limit. Не считать Prod124 PASS. |
| READY/limit124MiB, но START не вернул HOME | Инициализация прошла, полный exit gate не прошёл; исследовать APT/HOME/cleanup отдельно. exit.txt сам по себе не доказывает выход. |

Legacy64, Prod124 и Dev1 отличаются не только доступным heap: [исследование режимов](../analysis/native-startup-prod124-v0.1.0/report.ru.md). Prod124 startup не выдаётся за готовую игровую CIA. [Замер игры без изменения её резервов](../analysis/native-game-memory-v0.1.0/report.ru.md).

Сборка: `python porting/tools/build_native_startup_prod124.py`; проверка: `python porting/tests/smoke_native_startup_prod124.py`. Существующие build/evidence не перезаписываются. [Gate и SHA](../analysis/native-startup-prod124-v0.1.0/release-gate.json).
