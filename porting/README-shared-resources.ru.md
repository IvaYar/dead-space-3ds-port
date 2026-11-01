# Единые ресурсы Azahar: изолированный Windows/NTFS pilot

Один normal native CXI cycle прошёл с общими read-only assets. Старые39 SD-наборов, baseline и диагностика сохранены. GPU/native-game/shutdown и исходный проверенный runner не менялись; новой CIA и аппаратного запуска нет. [Подробный результат](analysis/shared-resource-store-pilot/report.ru.md), [машинный proof](analysis/shared-resource-store-pilot/result.json).

## Минимальная схема

`tools/azahar_resource_store.py` создаёт **одну новую verified-копию** по content ID в приватном `.local/azahar-resource-store/datasets/<SHA256>/`. Старый `private/native-game-v0.1.0-sd` не переименовывается и не получает новые права. ID вычисляется из отсортированного перечня1752 relative paths/размеров/SHA256; manifest хранится внутри приватного dataset.

```text
.local/azahar-resource-store/datasets/<id>/
    manifest.json
    data/assets/
    data/apk-assets/
    data/libEAMGameDeadSpace_orig.so
    data/*-verified.txt
    data/test-output/font-subset/Ascender_Uni.ttf

<новый-run>/Azahar/sdmc/3ds/deadspace/
    assets/       -> NTFS junction на readonly dataset/data/assets
    apk-assets/   -> NTFS junction на readonly dataset/data/apk-assets
    libEAMGameDeadSpace_orig.so           # отдельная копия
    *-verified.txt                       # отдельные копии
    test-output/font-subset/              # отдельная копия
    test-output/<appdata, saves, pages>/  # собственные writable файлы
```

Только два крупных каталога общие. Донор/receipts/subset font копируются независимо: это всего4,336МиБ/run, позволяет создавать отдельные donor/font fault fixtures и не требует Windows file symlink privileges. Hard links не используются ни для writable, ни для остальных файлов.

Dataset защищается inheritable NTFS ACL, запрещающим текущему пользователю обычную запись/append/delete и оставляющим read/execute. Обычного read-only атрибута недостаточно. Перед attach проверяются полный SHA inventory, ID и отказ writable-open; без защиты/поддержки junction helper останавливается, writable fallback отсутствует. Владелец компьютера может намеренно изменить ACL — это защита от обычных runner writes, а не от администратора.

API для новых изолированных readonly-runs:

```python
from azahar_resource_store import ensure_dataset, prepare_card
dataset = ensure_dataset(master_deadspace_directory)
layout = prepare_card(new_analysis_root / 'Azahar/sdmc/3ds/deadspace', dataset)
```

`prepare_card` принимает только новый SD внутри workspace analysis и отказывается перезаписывать существующий. Старые run не преобразуются автоматически. Не запускать recursive delete/copy по junction как по обычному каталогу: обслуживающие инструменты должны явно исключать reparse points и не обходить target при удалении ссылки. В этом этапе удаления junction/данных не было.

## Совместимость и границы

| Runner/сценарий | Статус |
|---|---|
| Normal `smoke_native_game_stable.py` | Реально проверен preparation-only адаптером; original runner остался byte-identical |
| CRC/poison/прочие native варианты | Общий readonly assets layout возможен, но дополнительные эмуляторные циклы в этом пилоте не выполнялись |
| `smoke_engine_azahar.py` | Пока обычные независимые копии: он переписывает achievements.sb даже в обычной подготовке, а asset-negative cases меняют/удаляют ресурс |
| Saved state / restore | Старые snapshots не менялись. Формат writable SD остаётся обычным; новый save/restore в этом пилоте не проверялся |

Для mutating runners простейший следующий шаг — оставить существующий full-copy режим либо отдельно копировать изменяемое поддерево и подключать общими только остальные каталоги. Полноценный CoW/overlay FS сейчас не нужен и не реализован. Одновременное глобальное monkeypatching `shutil.copytree` не используется.

У прошедшего пилота код всех frame/CRC/kernel join/GPU/IO checks тот же. Адаптер меняет только подготовку SD и import root; [diff](analysis/shared-resource-store-pilot/host-preparation.diff) сохранён. Generated host runner находится в `.local/shared-resource-pilot/host-runner.py`, его SHA есть в proof. Baseline по-прежнему читается из сохранённого источника, target CRC не менялся.

Одноразовый replay из свежего workspace/evidence root:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python porting/tests/smoke_shared_resources_pilot.py
```

Существующий pilot откажется перезаписывать. Для следующего эксперимента нужны новый run ID/отдельный output, а не удаление текущего evidence. На другом компьютере dataset пересоздаётся и проверяется из private master; ACL должен соответствовать пользователю той машины. Для восстановления нужны точные dataset ID/manifest, CXI, DLL, runner и writable snapshot, если он использовался.

## Git и публикация

`.local`, все Azahar SD и writable `test-output`, Python caches и worker/destructor dumps явно игнорируются после старых широких разрешений. Для пилота разрешены только выбранные численные JSON, текстовый отчёт и preparation diff. Полный dataset manifest остаётся private.

Добавлен `tools/check_staged_private_files.py` и opt-in `.githooks/pre-commit`. Guard проверяет **staged blob из index**, не текущий рабочий файл: private paths, binary/artifact extensions, ELF/MZ/ZIP signatures при переименовании, binary NUL/non-UTF8, object/stack JSON, size>5MiB. Собственные source/docs и численные proofs разрешены. Новые бинарные публикации требуют отдельного review; guard намеренно консервативен.

Проверки synthetic fixtures:

```powershell
python porting/tests/test_private_publication_guard.py
python porting/tools/check_staged_private_files.py
```

Восемь проверок прошли в disposable temporary Git repositories; реальный index не менялся. Hook **не активирован автоматически**, существующая конфигурация hooks не перезаписана. При желании включить его локально:

```powershell
git config --local core.hooksPath .githooks
```

Ignore не убирает уже tracked файлы; прежние72 object JSON не удалялись из индекса/истории. Локальный hook можно обойти, поэтому при дальнейшей публикации эту же проверку стоит запускать в CI. Автоматически определить право на произвольный текстовый контент невозможно; это дополнение к narrow publication allowlist.

## Экономия

В новый run копируется4,336МиБ начальных файлов вместо556,340МиБ. **552,004МиБ assets/run** больше не дублируются. Сам pilot с logs/raw/results занял около8,6МиБ выделения файлов без обхода junction; store — около559,1МиБ с manifest.

Первая инициализация store требует новой копии: на этом этапе общая папка проекта стала больше, старые наборы не очищались. Для39 ранее выделенных SD переход только `assets/apk-assets` даёт около21,02ГиБ логической экономии; с вычетом нового store — **около20,48ГиБ**. По выделению существующих файлов оценка около20,57ГиБ net, без MFT/directory overhead. Данные измерений: [storage-metrics.json](analysis/shared-resource-store-pilot/storage-metrics.json).

После этого возвращаемся к позднему runnable Run0xb6e6c и pending APT close HOME→X. Этот pilot не исправляет аппаратный cleanup FAIL и не разрешает повторную проверку прежней CIA.
