# DS Game Prod124 — один оригинальный кадр

**Следующая сборка DS Game Init0.1.1 уже испытана:** начальный шум исчез, но CRC gate не пройден после600callbacks, затем STOPPED без обработки START/HOME; shutdown не запускался. [Актуальный разбор](../analysis/native-game-target-init-v0.1.1/hardware-report.ru.md). Обе старые CIA не повторять; следующая задача — отдельный безопасный выход при известном CRC_FAIL без подмены игрового PASS.

**Последние аппаратные run-0002/run-0003 достигли оригинальной отрисовки:** выполнены209конструкторов, native RX и389/306callbacks. Пользователь видел EA и Айзека, затем выключил Power. Вне рисунка виден шум; полного кадра/result/выхода нет. Признаков OOM в логах нет, shutdown ещё не достигнут. [Разбор обоих запусков](../analysis/native-game-prod124-v0.1.0/hardware-runs-0002-0003.ru.md). Найден дефект неинициализированного color target, блокирующий CRC всего экрана; [отдельный кандидат DS Game Init0.1.1](README-native-game-target-init.ru.md) программно проверен и ждёт отдельного согласования hardware. Эту старую CIA ради диагностики повторно запускать не требуется.

**История run-0001:** остановка preflight из-за удалённой `SD:/3ds/deadspace/`. В следующих двух запусках ресурсы уже загружались. [Прежний разбор](../analysis/native-game-prod124-v0.1.0/hardware-report.ru.md). Полного hardware game/safe_exit PASS по-прежнему нет.

**Программный PASS:** оригинальный native-entry checkpoint работает при настоящем лимите124MiB в Azahar, совпадает с сохранённым GPU baseline и корректно завершает шесть donor-потоков. Подготовлена отдельная экспериментальная CIA **для согласования аппаратного испытания**. Приставку агент не запускал; это ещё не аппаратный game PASS и не непрерывный gameplay.

## Файл

[native-game.cia](build-native-game-v0.1.0-p124p/native-game.cia), **337856bytes**. SHA256:

```text
9fea6c2923d555511dd19a5d0177041592979dbd22fe8f07a4228a509082e815
```

TitleID **000400000FDE7300**, HOME **DS Game Prod124**, productCTR-H-DG24. Title отличается от старой h2/FDE7100 и startup/FDE7200; они не заменяются. New3DS SystemModeExt и AccessDesc — **Prod1/1**, kernel2.44, SVC permissions сохранены. Профиль предполагает New3DS family и прежний Luma RX/cache backend; настройки Luma/firmware не менять.

Новый бюджет **20MiB normal +100MiB linear**. Из linear92MiB принадлежат непрерывной донорской арене,8MiB оставлены SDK/GPU, включая transient staging. Main stack256KiB сохранён. Игра загружается из локального оригинального donor и сама выполняет209 конструкторов/JNI/lifecycle/draw callbacks. Runtime не читает картинку baseline; CRC выбирает известный момент оригинальной отрисовки. Checkpoint — экран Айзека/наушников, ещё не управляемая сцена.

## Обоснование и проверки

Размеры получены из измерений allocator peak/footprint и largest requests с запасом, затем проверены отдельными шагами. Арена128→92, linear132→100, normal40→20, guard178→124 и memory mode178→124 менялись **по одному фактору**. Исходные GPU/shader/thread overlays побайтно сохранены. Старые исходники/бинарники/baseline не переписаны.

Финальный process commit **126611456bytes=120,746MiB**, до app limit остаётся **3411968bytes=3,254MiB**. Donor sbrk high-water16,004MiB; normal allocated peak≈12,504MiB; прочий linear transient peak≈3,038MiB. GPU VRAM peak≈1,733MiB учитывается отдельно от FCRAM124. Это данные одного checkpoint, не доказанный budget поздних сцен.

Финальные **три CXI и три actual CIA-payload** цикла в одном core/SD: каждый кадр96000/96000pixels совпал с GPU baseline, GL/memory errors0, шесть истинных kernel joins,0worker handles, balanced IO, GPU completion, GSP release и обе кучи освобождены до host unload. Виртуальные RW spans/выравнивание и непрерывность linear arena проверены до конструкторов. [Отчёт памяти](../analysis/native-game-prod124-v0.1.0/report.ru.md), [машинные данные](../analysis/native-game-prod124-v0.1.0/memory-report.json), [gate](../analysis/native-game-prod124-v0.1.0/release-gate.json).

**Известная нестабильность эмулятора:** начальная серия Prod124 упала на третьем reload внутри `azahar_libretro.dll`,0xc0000005/RVA326ccf. Такая сигнатура раньше наблюдалась уh1. Первая серия не объявлена PASS; исходные данные сохранены. После неё тот же CXI без изменений прошёл3цикла и готовая CIA ещё3. Причина host crash не установлена и не считается исправленной; связь с профилем не доказана. [Запись сбоя](../analysis/native-game-prod124-v0.1.0/initial-host-crash.json).

В последних аппаратных запусках подтверждены выделение92MiB donor arena, проверка native RX и исполнение исходного кода. Полный контрольный кадр, GPU completion gate и реальный game shutdown в Prod124 ещё не подтверждены. Прежние аппаратные DS34 и startup Prod124 PASS сохраняются в своих пределах.

## Файлы SD

**Папка обязательна для игры**, даже если startup-тесты работали без неё. Готовый каталог `porting/private/native-game-v0.1.0-sd/3ds/` копируется **целиком в корень SD**, чтобы получился `SD:/3ds/deadspace/`. Локальная копия проверена и сохранилась:1752files/583364704bytes. В run-0002/run-0003 ресурсы уже успешно загружались; восстановление нужно только при их отсутствии.

Используются прежние локально предоставленные файлы. В CIA нет APK, оригинальной `.so`, font, игровых ресурсов или изображения кадра. На SD должны находиться:

```text
SD:/3ds/deadspace/
    libEAMGameDeadSpace_orig.so
    assets-verified.txt
    apk-assets-verified.txt
    assets/                         # исходное дерево coreassets
    apk-assets/                     # исходные APK assets, включая EAMCore.ini
    test-output/font-subset/Ascender_Uni.ttf
```

Проверенная приватная копия на компьютере: `porting/private/native-game-v0.1.0-sd/3ds/deadspace/`,1752files/583364704bytes. Набор не менялся. `.so`:4499468bytes/CRC9fd95635, font47036bytes/CRC71dcae12. Не перезаписывать отличающиеся файлы и не публиковать эту папку. Полные правила прежней подготовки SD — [README h2](README-native-game.ru.md).

Новая диагностика: **`SD:/3ds/ds-native-game-prod124-v0.1.0/run-NNNN/`**. Новое appdata namespace: `3ds/deadspace/test-output/native-game-prod124-v010/`; h2 namespace не используется. Существующие run не перезаписываются.

## Один аппаратный запуск — после отдельного разрешения

1. Проверить SHA файла, установить отдельный title **DS Game Prod124**. При запуске ожидается READY. Ничего не должно автоматически запускать оригинальный код до A; после открытия отпустить кнопку запуска.
2. На READY нажать **A один раз**. Идут preflight/resources → RX/cache → constructors/JNI → оригинальные callbacks → GPU completion → **FRAME SAVED**. Ожидается экран Айзека/наушников на верхнем LCD.
3. Нажать **START один раз**, дождаться cooperative shutdown и возврата HOME. Loader допускает bounded ожидание до30s. Изображение или exit.txt сами по себе не означают полного PASS.
4. Сохранить весь новый run: result.json, native-game.log, frame.raw, exit.txt и снимки состояния потоков. Для проверки нужны exact baseline comparison, шесть joins и наблюдение HOME. При STOPPED/FAIL не повторять запуск. При неполном shutdown код/арена/стеки/GPU-память удерживаются как в baseline, принудительного уничтожения нет.

Эта инструкция не разрешает запуск. Агент не проводил hardware trials или git push. Прежде чем переходить к непрерывной сцене/управлению, нужен аппаратный original-frame+safe-HOME результат именно этой CIA.

Воспроизведение: `tools/build_native_game_prod124.py --step observe/arena/linear/normal/guard/prod` с соответствующей проверкой каждой стадии через `tests/smoke_native_game_prod124.py`; упаковка `--step cia --proof-attempt r2` привязана к текущей clean CXI-серии. `tools/audit_native_game_prod124.py` читает сохранённые результаты и проверяет SHA/границы/gate. Готовые каталоги не перезаписываются. Полный ARM suite не требуется.
