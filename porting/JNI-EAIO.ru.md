# JNI/EAIO: результат продолжения на эмуляторе

**История предыдущего блока.** Описанная ниже остановка на `SystemAndroidDelegate` уже пройдена. Текущий результат: 158 ARM-тестов, семь сценариев Azahar, первый возврат `NativeOnDrawFrame`, диагностическая остановка на адаптере акселерометра. Строковые ссылки и локальные области также расширены. Актуальные ограничения, свидетельства и команды — [PLATFORM-BOOTSTRAP.ru.md](PLATFORM-BOOTSTRAP.ru.md); прежние свидетельства EAIO сохранены в `analysis/eaio-baseline/`.

Проверки на приставке сейчас не требуются. Добавлен отдельный мост `ds10_jni`, который проходит прежнюю остановку на EAIO. Оригинальная функция игры **`Java_com_ea_EAIO_EAIO_Startup` вызывается и возвращается** в Unicorn и Azahar. Следующая остановка — запрос `com/ea/blast/SystemAndroidDelegate` при первом `NativeOnDrawFrame`. Игровой кадр пока не отрисован.

## Что реализовано

Таблица JNI расширена для выбранных сервисов. Классы и методы сопоставляются по полному имени, сигнатуре и признаку static/instance. Методы нельзя вызвать с чужим receiver, неправильным типом результата или произвольным method ID. Неизвестные методы вызывают диагностический отказ. Поддерживаются необходимые варианты вызова через обычные аргументы, `va_list` и массив восьмибайтовых `jvalue`; отдельный softfp-модуль проверяет переходы, включая 64-битный `skip`.

`MainActivity.GetInstance` и `getAssets` возвращают типизированные ссылки на native-сервисы приложения и менеджера ресурсов. `EAIO.Startup` передаёт AssetManager настоящему native-экспорту игры. Это не Java-интерпретатор: исходные Java-байткоды не выполняются.

Реализованы локальные и глобальные ссылки на поддерживаемые объекты, проверка идентичности и `GetObjectClass` для объектов сервисов. Ссылки имеют уникальные токены: удалённая ссылка не становится ссылкой на вновь созданный объект; ссылка другого контекста не принимается. Отдельные ссылки на один объект имеют одну идентичность. Удаление последней ссылки освобождает связанный массив или поток. Повторная инициализация контекста с живыми ссылками отклоняется; отдельная cleanup-функция освобождает оставшиеся ресурсы после остановки пользователей JNI.

Массивы `byte[]` создаются с нулями, поддерживают проверку длины и границ region-операций. `GetByteArrayElements` возвращает копию с `isCopy=true`; release поддерживает запись обратно, COMMIT с удержанием копии и ABORT без записи обратно. Неверный указатель, режим или удаление pinned-массива отклоняются.

`AssetManager.open` реализован для обеих обнаруженных сигнатур: с одним String и со String/accessMode. Ресурсы читаются через существующий readonly-мост SD; относительные имена сопоставляются с `published/`, пути с выходом за каталог отклоняются. `InputStream.read(byte[], offset, length)` заполняет только выбранную часть массива, возвращает -1 при EOF и 0 при нулевой длине. `skip(long)` обрабатывает отрицательное значение и запросы больше 32 бит; close освобождает дескриптор и допускает повторный вызов. Отсутствующий файл и ошибка операции выставляют pending exception для JNI-проверок.

## Свидетельства

Отдельный собственный ARM softfp-модуль вызвал JNI через настоящие function pointers, открыл `data/achievements.sb`, прочитал **3568 байт** и вычислил **CRC32 `4a8d9499`**. В Azahar чтение идёт с его виртуальной SD через native FILE backend. В Unicorn тот же ARM-модуль работает с тестовым backend, содержащим неизменённые байты этого ресурса.

Проверено 201 условие внутри модуля: вызовы разных JNI-семейств, padding вокруг области чтения, EOF, нулевая длина, 64-битный skip, два открытия и закрытие. После изолированной проверки открытых файлов и живых heap-блоков **ноль**. Её startup-callback — отдельный тестовый обработчик; оригинальная EAIO-функция проверяется последующим запуском игры, в другом контексте.

```text
JNI I/O probe: 0 checks=201 bytes=3568 CRC32=4a8d9499
JNI I/O cleanup: files=0 heap=0
...
JNI NativeEAIOStartup returned: com/ea/EAIO/EAIO.Startup (Landroid/content/res/AssetManager;)V
JNI FindClass: com/ea/blast/SystemAndroidDelegate.  MISSING
JNI runtime: startup=1 refs=10 failures=1
STOP Java adapter
Phase: NativeOnDrawFrame
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

Всего прошли **142 ARM-проверки**: 122 прежние и 20 новых проверок JNI. Шесть сценариев Azahar: ожидание A, отсутствующий/повреждённый донор, отсутствующий/повреждённый ресурс и нормальный запуск до следующего ожидаемого отказа. При плохом ресурсе изолированная проверка останавливается до запуска конструкторов игры и очищает ресурсы.

Во время настоящего `EAIO_Startup` игра сохраняет свой массив на **64 KiB** и ссылки на Java-сервисы. Они остаются живыми до завершения экспериментального процесса; их нельзя путать с нулевыми счётчиками после отдельной I/O-проверки.

Сводный отчёт — `analysis/engine-progress.json`, полный журнал — `analysis/azahar-smoke/engine-present.log`, трассировка запросов — `analysis/engine-first-entry-experiment.json`, новые unit-проверки — `analysis/jni10-tests.json`. Предыдущий барьер сохранён в `analysis/engine-baseline/`.

## Ограничения и следующий блок

Мост предназначен для текущего однопоточного bootstrap. Полноценные JVM, Java-исключения с иерархией классов, reflection, выполнение Java-конструкторов, наследование произвольных классов и работа из нескольких Java-потоков не реализованы. Базовые UTF-строки сохраняют ограничения прежнего bootstrap: восемь объектов по 256 байт, без глобальных ссылок на строки. Удаление ссылки на pinned byte-array сейчас явно отклоняется.

Лимиты: 128 ссылок, восемь массивов до 1 MiB каждый с общим лимитом runtime heap, 16 копий array elements, восемь потоков файлов. Это лимиты диагностики, а не оценка требований всей игры.

Метаданные `openFd`, `list` и методов AssetFileDescriptor доступны для lookup, поскольку оригинальный startup кэширует их IDs. **Их выполнение не реализовано и явно останавливается.** Подготовленный method ID не считается реализованной операцией. ELF-счётчик поэтому по-прежнему 152 привязки, 236 обязательных отсутствующих и четыре слабых.

Следующий блок — `SystemAndroidDelegate`: свойства системы и поддерживаемых устройств. После него трассировка покажет следующие реальные запросы. Графика, звук, полный native RX и итоговый расход памяти игры остаются непроверенными. CIA не создавался; механизм RX/кэша прошедшего этапа 8 не изменялся.

## Повторение

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_emulator_runtime.py
python porting/tests/test_jni10.py
python porting/tools/run_engine_experiment.py
python porting/tests/smoke_engine_azahar.py --case ready
python porting/tests/smoke_engine_azahar.py --case missing
python porting/tests/smoke_engine_azahar.py --case wrong
python porting/tests/smoke_engine_azahar.py --case asset-missing
python porting/tests/smoke_engine_azahar.py --case asset-wrong
python porting/tests/smoke_engine_azahar.py --case present
python porting/tools/check_engine_progress.py
```

Первичные API-источники: [таблица и функции JNI](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html), [AssetManager](https://developer.android.com/reference/android/content/res/AssetManager), [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html). Требуемые игрой сигнатуры дополнительно подтверждены её реальными запросами в трассировке.
