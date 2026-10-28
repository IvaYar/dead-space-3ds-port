# APK assets, JNI monitors и общий пул памяти

Текущая контрольная точка: **360 завершённых кадров**, настоящий APK namespace, общий пул памяти100MiB. Более длинный запуск завершил368 callbacks и остановился на369-м: `glGenFramebuffersOES`, caller offset `00378aec`. Кадр остановки зависит от расписания загрузочных потоков; фиксируется конкретный сохранённый журнал. Меню, игровой процесс и звук ещё не подтверждены. Новой CIA нет, проверка на приставке не требуется.

![Кадр360: экран с персонажем и наушниками](analysis/apk-assets-frame/first-game-frame.png)

Внешне это прежний экран. Существенный результат — устранены реальные ограничения чтения APK, JNI-синхронизации и памяти; загрузка дошла до создания внеэкранного framebuffer. Создание имени FBO нельзя подменять успешной заглушкой: следующий блок требует настоящих attachments, переключения цели рисования и согласованного доступа к texture store.

## APK namespace

Раньше AssetManager использовал внешний `published/` cache. Это оставлено как отдельный legacy profile для прежних регрессий. Новый opt-in `--apk-assets` извлекает20 настоящих файлов выбранного SD APK, проверяет APK SHA256, размеры, ZIP CRC и методы сжатия. В APK7 элементов непосредственно под assets/. `EAMCore.ini` действительно существует:3119 bytes, CRC32 `33c9beb3`. `data.zip` отсутствует; его открытие правильно вызывает IOException. Байтам игры ничего не подставляется.

`tools/prepare_apk_assets.py` размещает локальные копии только в приватной SD эмулятора, оставляя оригинальные APK/.so/cache нетронутыми. Извлечённые файлы и bundled-game.zip не публикуются. Manifest: [emulator-apk-assets.json](analysis/emulator-apk-assets.json), источник: [apk-asset-namespace-contract.json](analysis/android-abi/apk-asset-namespace-contract.json).

DS19 exact-path profile сохраняет буквальный `published/`, не принимает traversal, некорректный MUTF8 и псевдосхемы. Open/list используют один backend. DS25 открывает настоящие read-only файлы через общую таблицу дескрипторов. Сжатый в APK `EAMCore.ini` доступен как InputStream, но `openFd` возвращает IOException. Дескрипторы предоставляются только ZIP_STORED entries — bundled-game.zip и downloadcontent/config.properties. Это соответствует [контракту Android AssetManager.openFd](https://developer.android.com/reference/android/content/res/AssetManager#openFd(java.lang.String)).

AssetFileDescriptor указывает на отдельную извлечённую копию: offset0, настоящая длина. `FileDescriptor.getInt$` возвращает shared-I/O descriptor; generation защищает от случайного закрытия переиспользованного слота. `fcntl` поддерживает только F_DUPFD: дубликаты разделяют offset, исходный close не уничтожает дубликат, последний close закрывает файл. Приватные read/write ownership flags передаются дубликатам. Остальные команды fcntl возвращают ошибку.

## JNI synchronization

Оригинальный EAIO после отказа openFd синхронизирует чтение InputStream через JNI slots217/218. Реализованы MonitorEnter/MonitorExit поверх настоящих recursive DS7 mutexes: ключ — identity payload, общая для local/global aliases. Проверяются владелец, глубина рекурсии, неверные ссылки и ограничение16 monitor entries. Очистка занятого monitor возвращает отказ, сохраняя context. Монитор удерживает payload до освобождения; код не разблокирует чужой поток принудительно. Контракт: [JNI Monitor Operations](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#monitor-operations).

12 ARM-тестов проверяют lifetime, aliases, ошибочный owner, повторные входы, ограничение ёмкости и cleanup. Это не реализация всей JVM: общие JNI reference tables и файловый backend по-прежнему требуют согласованного использования. Реальный EAIO проходит этот путь в Azahar; отдельная новая многопоточная contention-проба именно JNI monitor не добавлялась. Блокирующий механизм общий с ранее проверенным DS7 pthread backend.

## Память и потоки

Длинный запуск впервые достиг sbrk request ещё16MiB сверх занятого16MiB+4KiB. Прежний фиксированный20MiB brk отказывал. Попытка33+67MiB сохраняла общий бюджет100MiB, но не обеспечила непрерывного mmap участка19705856 bytes при загрузке шрифта. Оба неудачных прогона сохранены как исторические диагностические журналы; они не являются проверками нынешнего бинарника.

Новый `ds9_memory_init_shared` использует **те же100MiB**: brk растёт снизу, mmap ищет свободные страницы сверху. Живые mappings не перемещаются. Пересечение, нехватка непрерывного места, неподдерживаемые mmap режимы и неверные unmap по-прежнему возвращают ошибки. Страницы brk нельзя освобождать через munmap. Отдельные12 тестов проверяют общее владение, границы неполной страницы, zero-fill, частичный unmap, восстановление свободного места и отсутствие overcommit. Старый disjoint режим сохранён, guarded Unicorn profile остаётся20+20MiB.

При дальнейшей загрузке впервые подтверждено исчерпание старого32-slot semaphore pool: observer event5. Только emulator build задаёт DS7_SEMAPHORE_COUNT=64; default остаётся32. Четыре дополнительных теста проверяют реальные независимые счётчики, ENOSPC на65-м, сохранение объекта при отказе и повторное использование. В текущем длинном журнале semaphore exhaustion нет.

В точке следующего запроса: brk33558528 bytes, mmap13327 pages (54587392 bytes), суммарно88145920 bytes из104857600. Отказов arena нет. Наличие свободной памяти не гарантирует прохождение следующих сцен.

## Проверки и продолжение

Текущая core-сборка проходит **420 ARM-тестов**. Сохраняются9 стандартных Azahar cases,3 guarded CPU audits, отдельные120-frame headphones и240-frame input/save captures. Новый360-frame APK/shared capture и длинный прогон до FBO проверяет `tools/check_apk_assets.py`; результат [apk-assets-result.json](analysis/apk-assets-result.json). Общая проверка — `tools/check_engine_progress.py`. Все runtime witnesses должны ссылаться на текущие core/CXI/source hashes. Исторические числа в более ранних документах относятся к своим этапам.

Воспроизведение нового профиля:

```powershell
python porting/tools/prepare_apk_assets.py
python porting/tools/build_emulator_runtime.py
python porting/tests/test_apk_assets.py
python porting/tests/test_jni_monitors.py
python porting/tests/test_shared_memory.py
python porting/tests/test_emulator_threads.py
python porting/tests/smoke_engine_azahar.py --case graphics --explore --capture-frame 360 --timeout-seconds 150 --resume-focus --touch --tap-frame 160 --private-files --apk-assets --shared-arena
```

Для исследования следующей остановки заменить capture-frame на600 и timeout-seconds на180. Azahar cases запускать последовательно: используется одна приватная SD. Копии сохранений остаются в ignored `analysis/apk-assets-state/`; в проект включаются только receipt hashes. При обновлении capture сохранять raw/json/PNG, LCD, run.log и run-result.json вместе. Exporter отклоняет framebuffer от незавершённого предыдущего запуска.

Следующая работа: изучить вызов `00378aec` и последовательность OES framebuffer/renderbuffer API, реализовать корректную смену render target и attachment storage с осмысленными GL errors и проверками. Не обещать меню до реального кадра. Native RX/cache backend stage8 не менялся. GitHub обновлять только по новому явному запросу пользователя.
