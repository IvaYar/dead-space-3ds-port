# JNI-строки: история адаптера

**Текущее состояние:** [SCENE-RENDERER.ru.md](SCENE-RENDERER.ru.md). Меню, касания, fog и texture combiners пройдены в Azahar; следующий запрос — `glLightModelfv`. Проходят511 core ARM-тестов. Английский донор1.1.33, перевод отложен. Более ранние «новейшие» записи ниже сохранены как история.

**Новейшее продолжение:** [INPUT-SAVES.ru.md](INPUT-SAVES.ru.md): original touch callback, приватные descriptor saves,240 кадров и368 core-тестов. Меню пока нет; следующим требует исправления APK AssetManager namespace.

**Актуальное продолжение:** [HEADPHONE-SCREEN.ru.md](HEADPHONE-SCREEN.ru.md). В Azahar завершены120 кадров, экран с персонажем/наушниками и текстом. Local frames закрываются: заимствованный version-string payload живёт независимо от удалённой JNI reference до cleanup. Прежний запрет pinned PopLocalFrame ниже описывает историческую реализацию DS18, а не текущий контракт. Проходят24 string-теста и336 core-тестов. Каталоги — [JNI-ASSETS.ru.md](JNI-ASSETS.ru.md).

Движок в **Unicorn и Azahar прошёл JNI NewString /slot163**. Новая остановка — **`android/content/res/AssetManager.list("")`**, сигнатура `(Ljava/lang/String;)[Ljava/lang/String;`, второй `NativeOnDrawFrame`. Запрос пустого пути подтверждён диагностикой аргумента; `list` ещё не реализован.

Первая текстура игры512×512 RGBA остаётся в CPU-store:1048576 bytes, CRC32 `a738ea1c`, совпадающий с входом игры в Unicorn и с native-store Azahar. GL error0, queries7, clear/draw0. Игрового изображения и меню ещё нет.

## Реализовано

`ds18_strings.c/h` кодирует UTF-16 code units в **JNI modified UTF-8** и декодирует их обратно. Embedded NUL представлен C0 80; supplementary characters остаются парой суррогатных code units и дают шесть байт. Lone surrogates сохраняются. Неправильные continuation bytes, усечённые/overlong sequences и обычный четырёхбайтный UTF-8 отклоняются. При ошибке counted codec не изменяет выходной буфер.

В таблице JNI `ds10_jni.c` добавлены 8 entry points и обновлены 4 прежних:

| Slots | Операции |
| --- | --- |
|163–166|NewString, GetStringLength, GetStringChars, ReleaseStringChars|
|167–170|NewStringUTF, GetStringUTFLength, GetStringUTFChars, ReleaseStringUTFChars|
|220–221|GetStringRegion, GetStringUTFRegion|
|224–225|GetStringCritical, ReleaseStringCritical|

Длина UTF-16 считается в code units, длина modified UTF-8 — в байтах. Regions используют UTF-16 start/length, проверяют диапазоны до записи и не добавляют terminator. Весь выход GetStringUTFChars завершается NUL; wide/UTF/critical getters возвращают заимствованные стабильные представления с isCopy=false. Отдельные pin counters проверяют release family и указатель. Изменять borrowed storage нельзя.

Строка владеет копией UTF-16 и своим byte representation; изменение исходного input buffer её не меняет. Local/global aliases удерживают один payload до последней ссылки. Удаление ссылки и PopLocalFrame с pinned строкой явно отказывают до release; это ограничение существующего bounded адаптера. Cleanup после остановки всех пользователей освобождает даже оставшиеся pinned payloads. Critical restrictions JNI остаются обязанностью вызывающего кода; JVM/GC здесь нет.

Сохраняются ограничения:8 payloads на контекст, максимум255 encoded bytes на строку, не более255 UTF-16 units на вход. Multibyte data может исчерпать byte budget раньше. UTF-16 storage выделяется отдельно, чтобы не раздувать фиксированный context area; DS10Context остаётся меньше8192 bytes. Allocation/reference/pool failure возвращает NULL с pending exception flag и не оставляет payload. Exception types полноценной JVM не моделируются. Bootstrap `ds_jni.c/h` этапа3 не изменён.

Strict ELF preflight остался **154 resolved /234 missing /4 weak-zero**: дополнительные JNI slots не являются ELF imports. Отказ от неполной привязки и неизменность donor image проверяются. Opt-in GL registry по-прежнему67.

## Свидетельства

Прошли **22 новых ARM-теста**: empty strings, embedded NUL, Cyrillic/BMP/границы encoding, paired/lone surrogates, modified UTF-8 roundtrip и malformed input, копия input, byte limits, OOM, pool/reference exhaustion, release families, aliases, local frames/escape/pinned-pop, regions/guards, critical borrows, stale/foreign refs, force cleanup и atomic codec output. Отдельный softfp ELF вызывает таблицу JNI, включая пятиаргументные regions.

Собственный native probe в Azahar выполнил **43 проверки** на7 UTF-16 units /17 modified UTF-8 bytes. После cleanup — files0/heap0. Дальше идёт уже оригинальный движок:

```text
String probe: 0 checks=43 units=7 bytes=17
String cleanup: files=0 heap=0
...
JNI AssetManager.open IOException: android/content/res/AssetManager.data.zip  EXCEPTION
JNI CallMethod: android/content/res/AssetManager.list (Ljava/lang/String;)[Ljava/lang/String;
JNI AssetManager.list requested: android/content/res/AssetManager.
JNI unimplemented method: android/content/res/AssetManager.list (Ljava/lang/String;)[Ljava/lang/String; MISSING
JNI strings: new16=1 newUTF=32 get16=0 getUTF=29 regions=0 errors=0
GLES first texture: 512x512 format=1908 bytes=1048576 CRC32=a738ea1c
Jump contexts: saves=20 restores=0 refusals=0
STOP Java adapter
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

После отсутствующего data.zip движок перешёл к directory enumeration. Строковая часть в этом пути не дала ошибок; на unsupported list устанавливается pending exception и аудит останавливается. Адрес прежнего NewString caller0022e72c не является адресом новой остановки: нынешний observer вызван из нашего метода dispatch.

На текущей core-сборке повторно прошли **275 ARM-тестов**:253 предыдущих +22 strings. Отдельные14 sensor-тестов другого ELF сохраняют валидные hashes — всего289 тестов двух сборок. Три CPU-режима и девять engine-сценариев Azahar обновлены; оба checker прошли. Hardware stage8 RX/cache и старые CIA не изменялись. Нового CIA и запроса на проверку приставки нет.

## Продолжение

Следующий блок — настоящее AssetManager.list и JNI object arrays: перечислять реальные имена в корректном пространстве Android assets, проверять пути и границы, реализовать ArrayLength/GetObjectArrayElement с верными типами и lifetime. Сейчас byte-array bridge не является object-array bridge. Сверить list semantics с существующим open, которое добавляет published/ для обычных путей. Не подставлять пустой список или фиктивный data.zip. После этого снова идти по наблюдаемым запросам игры.

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_strings.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

После rebuild core повторять девять предыдущих test-скриптов, три CPU-режима и девять smoke-cases. Azahar запускать последовательно из-за общей SD. Свидетельства: `analysis/strings-tests.json`, `analysis/engine-graphics-entry.json`, `analysis/azahar-smoke/engine-graphics.log`, `analysis/engine-progress.json`.

Первичные контракты Oracle: [JNI string operations](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#newstring), [modified UTF-8](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html#modified-utf-8-strings). Все изменения локальные. GitHub обновлять только по прямому запросу пользователя.
