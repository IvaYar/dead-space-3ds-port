# DS Game Stable 0.1.2 — native Prod124, корректный CRC_FAIL и диагностические кадры

**Аппаратный run-0001 получен: FAIL кадра и очистки. Эту CIA не повторять.** Pause/Stop вернулись, но более поздний загрузочный поток не завершился за30s; все6 workers остались живы. HOME открывает меню, однако X-закрытие не завершает процесс из-за аварийного retained-loop. [Актуальный разбор](../analysis/native-game-stable-v0.1.2-hardware/report.ru.md). Прежние software proofs ниже остаются историческими результатами подготовки и не подтверждают аппаратный safe_exit. Следующий кандидат пока не готов.

Ниже сохранены идентификация и инструкции **до получения аппаратного FAIL**. Они не являются предложением повторить тест. Старую DS Game Init0.1.1 также не повторять.

Исправлен выход из известного CRC_FAIL: после возврата callbacks запускается cooperative shutdown шести donor threads, GPU drain и обычный выход. Ошибочный кадр остаётся FAIL даже после успешной очистки. Если очистка не завершена, общего PASS и освобождения живых ресурсов нет.

Обычный сценарий после полного совпадения исходного кадра выполняет ещё8 настоящих original callbacks/present. Все8 проверяются по96000 pixels; это пока статичный UI checkpoint Айзека/наушников, не gameplay. Аппаратное расхождение9231pixels ещё не исправлено: сборка собирает адресные данные для его локализации и честно завершает проверку с FAIL при несовпадении.

[Полный отчёт](../analysis/native-game-stable-v0.1.2/report.ru.md), [software release gate](../analysis/native-game-stable-v0.1.2/release-gate.json).

## Файл и идентификация

[native-game.cia](build-native-game-v0.1.2-normal/native-game.cia). **TitleID000400000FDE7500**, HOME **DS Game Stable0.1.2**, ProductCTR-H-DGST. Точные SHA256/размер — [cia-manifest.json](build-native-game-v0.1.2-normal/cia-manifest.json). Этот TitleID не заменяет Prod124/FDE7300 и Init/FDE7400. Промежуточные `-precmd`/`-pre-boundary-fix` и fault CXI не являются кандидатами на устройство.

```text
Bytes  341952
SHA256 8bc86b29d023211d6469f903ba4eed343b3abbb83a901576e8ba096c424e6226
```

Memory profile Prod124, normal20MiB +linear100MiB, contiguous donor arena92MiB; kernel/SVC/permissions прежние. Оригинальные APK/.so/assets/font/картинка не включены в CIA. Старые сборки и аппаратные логи сохранены.

## SD

Нужна уже восстановленная целая **`SD:/3ds/deadspace/`**: original.so, обе receipts, assets, apk-assets, test-output/font-subset. Подходит прежняя приватная копия `porting/private/native-game-v0.1.0-sd/3ds/`; оригинальные файлы не меняются. Не удалять эту папку после установки CIA. [Подробный перечень](README-native-game-prod124.ru.md).

Новые данные:

```text
SD:/3ds/ds-native-game-v0.1.2/run-NNNN/
SD:/3ds/deadspace/test-output/native-game-stable-v012/
```

В run сохраняются `native-game.log`, `result.json`, `validation.json`, `ready.txt`, `exit.txt` после полной очистки; raw checkpoints и `.raw.gx` с GX/PICA командами. Worker/object snapshots — диагностические private данные. Никакие старые run не перезаписываются.

`validation.json` разделяет `frame_status`, `cleanup_status`, `cleanup_complete`, число реально выполненных callbacks/sequence и CRC. `result.status=failed` вместе с `safe_exit=true` означает **неуспешный кадр с подтверждённой очисткой**, а не игровой PASS. При неполной очистке — blocked/retained/safe_exit=false без успешного exit marker.

## Один будущий запуск после разрешения

1. Проверить SHA256 по manifest, установить только текущую обычную CIA. Настройки Luma/прошивки не менять.
2. Открыть **DS Game Stable0.1.2**, дождаться READY, нажатьA один раз. START доступен между вернувшимися callbacks; нажатие до завершения проверки сохраняет FAIL и запускает выход.
3. При **FRAME + SEQUENCE SAVED** нажать START один раз для штатной остановки. При CRC_FAIL очистка запускается автоматически. Ожидание естественного завершения loader ограничено30s, затем подтверждаются остальные workers/GPU. Это не гарантия времени любого SDK/original вызова.
4. Сохранить **всю** `SD:/3ds/ds-native-game-v0.1.2/` после возврата. При STOPPED/нештатном исходе сохранить уже созданные файлы; не повторять запуск ради диагностики. Raw/GX и производные изображения игры оставлять приватными.

Main-thread STOPPED при незавершённой очистке обслуживает HID/APT, но не делает unsafe free ради выхода. Аварийное зависание внутри original/SDK calls и worker-import fatal этим этапом не исключены. Присутствие картинки, успешная установка или результат эмулятора не являются hardware PASS.

## Автоматическая проверка будущего результата

Сначала скопировать полученную аппаратную папку в отдельный архив без изменений, затем:

```powershell
python porting/tools/analyze_native_game_run.py PATH_TO_ARCHIVED_RUN --compare porting/analysis/azahar-native-game-v0.1.2-normal-cxi/Azahar/sdmc/3ds/ds-native-game-v0.1.2/run-0001 --output NEW_ANALYSIS.json
```

Инструмент проверяет raw/CRC/парное чтение, GX/PICA packet bounds, transfer flags/dims и предлагает одинаковые input states. Digest — подсказка для сравнения, не замена проверки входов или полного framebuffer. Сравнение новых raw с frozen reference:

```powershell
python porting/tools/analyze_native_game_image.py --extra PATH_TO_CAPTURE.raw --tag NEW_UNIQUE_TAG
```

## Программные проверки кандидата

Финальные3 normal CXI +3 poison CRC_FAIL +1 принудительный black CRC_FAIL +1 удержание при неполной очистке +3 actual CIA payload. Все10 обычных очисток подтвердили6kernel joins/0handles, balanced IO, GPU/GSP release/обе heap free, memory exceptions0. Искусственное удержание подтвердило отсутствие ложного PASS/free; это не safe_exit.

Проверки не изменяют базовые GPU/shader/thread sources и не запускают ARM suite. Builder отказывается перезаписывать evidence и требует положительные/отрицательные software proofs перед изготовлением CIA. Повторять уже пройденные серии без изменения кода/нового сбоя не требуется.
