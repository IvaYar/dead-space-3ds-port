# Read-only resource store: один Azahar pilot PASS

01.11.2026. Реализация и ограничения — [README](../../README-shared-resources.ru.md). [Основной proof](result.json), [security checks](security-tests.json), [размеры](storage-metrics.json), [изменение подготовки](host-preparation.diff).

**Один normal CXI cycle прошёл:** исходный кадр и8 дополнительных original callbacks совпали с frozen RGB565 baseline по всем96000 pixels. Guest status passed, safe_exit true,6kernel joins/0handles, IO94/94, GPU/GSP и обе heap освобождены, memory exceptions0. Проверен прежний CXI `e3bc6ec7757db965c805e542a0181491612448e01999a31438103164e06eb776`; native source, GPU backend и thread shutdown не менялись, новая CIA не создавалась. Это software proof хранения данных, не hardware cleanup proof.

Источник — старый полный private SD,1752files/583364704bytes. В новый content-addressed dataset `a46655efb24fab59c7649322986eea2ae0a5827454bca4c5e71be3d13818ceef` выполнено одно копирование с SHA256 каждого файла. Master не модифицируется и не переводится в readonly. Новый dataset защищён NTFS ACL. Только assets/apk-assets подключены junction; все writable каталоги, донор, receipts и subset font находятся в run как отдельные regular files. Hard links не используются.

Подтверждено:

- Все1752 SD-path SHA совпали с dataset manifest; manifest ID пересчитан из содержимого.
- Store и исходный master прошли полный SHA audit до/после; запись в реальный asset через junction запрещена.
- Создание/append/read собственного save работает, файл не разделяется с dataset, nlink1.
- После закрытия guest один байт **отдельной run-копии** донора был изменён и восстановлен; store/master не изменились.
- Повторный attach к существующему card отказал до перезаписи.
- Frozen original runner SHA `f14b3842eab6eafd66a0210e0fd3d68877ea3229f7d2326f84df0a9ecf83a0f4` сохранён. Generated runner SHA и storage helper/driver SHA зафиксированы в result.
- 68328 файлов старых39 resource subsets имеют прежние size/mtime по inventory ревизии. Они не удалялись, не перемещались и не превращались в ссылки.

Общий store —1753files с manifest,583707695bytes содержимого/586299856bytes выделения. Run без обхода двух junction —74 обычных файла,8922242bytes содержимого/9031344bytes выделения, включая диагностические outputs. Per-run seeds4546682bytes, общие assets578818022bytes.

Для39 копий потенциально перестанут дублироваться22573902858bytes логического содержимого. С вычетом новой однократной dataset-копии —21990538154bytes≈20,48ГиБ. Измеренное выделение файлов даёт оценку22088493272bytes≈20,57ГиБ net. Это будущая миграция с отдельным разрешением, **не уже освобождённое место**; текущий этап добавил новый store и run.

Security guard:8 host tests PASS на synthetic staged fixtures, включая force-add ignored private path, asset path/extension, object dump по имени/содержимому, переименованные ZIP/ELF и unsafe index blob при safe-looking worktree. Проверка реального staged списка видела0 файлов, это не подменяет результаты synthetic tests. Реальный index и hooksPath не менялись. Gitignore теперь явно закрывает store/SD/caches/dumps; история tracked файлов сохранена.

Пилот намеренно не переключает все runners. Старый `smoke_engine_azahar.py` пишет achievements.sb даже в обычном setup, поэтому ему пока нужен independent-copy режим. CRC/poison modes, reload cycles, новых checkpoint save/restore и аппаратных запусков в этом этапе не было. Требования CRC/safe_exit не ослаблены; старые manifests и baseline не заменены.

Следующая основная задача остаётся прежней: кооперативно завершить именно поздний Run0xb6e6c, затем корректно обработать HOME→X. Готовой новой аппаратной CIA этот этап не выпускает.
