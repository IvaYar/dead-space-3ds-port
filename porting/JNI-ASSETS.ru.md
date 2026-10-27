# Каталоги ресурсов и JNI String[]: пройдены в двух эмуляторах

**Новее:** [FIRST-FRAME.ru.md](FIRST-FRAME.ru.md) — memory/root paths пройдены, CPU renderer вывел логотип EA на LCD Azahar. Ниже — прежний checkpoint DS19; его mmap guard остаётся только в маленьком CPU-профиле.

DS19 реализует `AssetManager.list(String)` и JNI-массивы строк. Оригинальная игра получила **12 записей корня**, прочитала их через GetObjectArrayElement/GetStringChars и освободила результат. Прежняя остановка на `list("")` пройдена в Unicorn ARM11 и Azahar.

Текущая остановка — **диагностический отказ области памяти** при загрузке `fonts/Ascender_Uni.ttf`: `mmap`, **13139968 bytes**, Android errno12, второй `NativeOnDrawFrame`. Проверки прекращают выполнение при первом отказе, до продолжения донорского allocator recovery. Это политика диагностической сборки, не реализация восстановления после OOM. Изображения игры и меню ещё нет; новая CIA не выпускалась. Проверка на приставке не требуется, GitHub не обновлялся.

## Реализация и границы

- `3ds/source/ds19_assets.c`: проверка пути, преобразование JNI modified UTF-8 → UTF-16 → файловый UTF-8, двухпроходное чтение каталога с проверкой размера, сортировкой и устранением повторов. Ошибка не публикует частичный массив.
- `3ds/source/ds19_assets_3ds.c`: настоящий read-only `opendir/readdir/closedir` на приватной SD эмулятора. Отсутствующий каталог/обычный файл возвращают пустой массив; прочие ошибки становятся pending exception. Неизвестный backend явно останавливает диагностику.
- `ds10_jni.c/h`: slots172–174 — NewObjectArray/GetObjectArrayElement/SetObjectArrayElement; slot171 различает byte[] и String[]. Поддерживается компонент **java/lang/String**, не произвольный JVM object array. CallObjectMethod/V/A реально проверены отдельной softfp-библиотекой.
- Массив хранит identity элемента, удерживает payload и возвращает отдельные local references. Обычная строка может пережить удаление исходного JNI handle; элемент может пережить удаление массива через local/global alias. Замена/очистка элемента освобождает последний payload. UTF/UTF-16/critical pins и local frames сохраняют прежние ограничения.
- Лимиты:8 массивов,2048 элементов в массиве,2048 дополнительных filename payloads на контекст,128 JNI refs,255 modified UTF-8 bytes на строку. Обычный NewString-пул остаётся8; элементы каталога не занимают все refs заранее. `DS10Context` остаётся меньше8192 bytes. Ошибки capacity/OOM/типа/границ проверены, включая rollback после частичной аллокации.

**Пространство имён — виртуальный корень `published/`.** Пустая строка означает `assets/published/`; `published/…` и `appbundle:/published/…` — его aliases. Open и list используют одну нормализацию. Это профиль совместимости порта, а не побайтовое воспроизведение AssetManager исходного APK. APK содержит отдельные bootstrap assets, включая `EAMCore.ini`, `bundled-game.zip`, downloadcontent и другие; они пока не добавлены в виртуальный корень. Нельзя считать их уже доступными или создавать фиктивный `data.zip`.

Native backend возвращает filesystem UTF-8, включая supplementary characters; JNI хранит UTF-16 и modified UTF-8. Traversal, абсолютные пути, backslash, colon, control characters и некорректное кодирование отклоняются. Имена, превышающие modified UTF-8 budget после преобразования, вызывают явный отказ.

Исправлен `GetExternalStorageDirectory`: раньше он ошибочно возвращал тот же `appdata:/`, что и внутренний каталог. Проверка DEX выбранного APK подтверждает `getFilesDir()` для внутреннего каталога и `getExternalFilesDir(null)` через BootstrapActivity для внешнего. Теперь внешний alias — `/sdcard/Android/data/com.ea.deadspace/files`; игра добавляет `ea/deadspace/published/…`. В `ds_io.c` разрешён именно этот дополнительный prefix с прежней проверкой каждого компонента. Статическое доказательство: `analysis/android-abi/directory-delegate-contract.json`, генератор `tools/verify_directory_delegate.py`.

## Проверки

Прошёл **301 core ARM-тест**: прежние275 и26 новых. Отдельные14 sensor-тестов относятся к другому ELF; их прежние свидетельства проверены checker. Все **девять engine-сценариев Azahar**, три CPU-режима и оба progress checker проходят для текущей сборки.

Отдельная исходная Android softfp-библиотека без libc imports исполняет JNI-вызовы в Azahar и Unicorn:

| Каталог виртуального корня | Имена | CRC32 имён UTF-8 с NUL-разделителями |
| --- | ---: | --- |
| пустой путь |12|4446bc5d|
| data |13|739d00c8|
| textures |151|0dada22c|

Итого **378 checks,176 имён, CRC32-xor3a761eb9**. Значения получены из реальных source-каталогов и записаны в `analysis/asset-directory-contract.json`; native fixture сверяет с ними реальные результаты backend. После завершения fixture: **files=0, heap=0**. Это относится к тестовому модулю, не к полному teardown остановленного движка.

Игра на остановке: lists1/names12/gets12/sets0, дополнительные strings0/arrays0; UTF-16 stats new16=1/newUTF=33/get16=12/getUTF=30/errors0. Первая игровая текстура по-прежнему512×512 RGBA,1048576 bytes, source/store/native CRC32 **a738ea1c**; GL error0, queries7, clear/draw0. Strict preflight **154 resolved /234 missing /4 weak-zero**, opt-in GL bindings67. JNI slots не уменьшают количество ELF imports.

CPU experiment теперь моделирует настоящий read-only stat исходных файлов через layout связанного newlib; преобразование в Bionic выполняется ARM-кодом. Прежний test-only `_stat_r` возвращал ENOSYS, что мешало сравнивать файловую ветку с Azahar. Модель не является 3DS filesystem implementation. Native Azahar использует настоящий stat libctru/newlib.

## Следующий блок — память загрузки шрифта

`Ascender_Uni.ttf` — **15904488 bytes**, SHA256 `dbca62a9b2ec00b6251c7fd5db72e1e87e4488cf9c3eac975c0a7db5e70d948c`. Шрифт и исходные архивы не изменялись. При текущих раздельных arenas20+20MiB занято break16781312 bytes и4097 mapped pages, всего33562624 bytes. Дополнительные13139968 bytes не помещаются в оставшуюся map-область. Общий процессный расход и предел пригодной аппаратной конфигурации этими цифрами не измерены.

До добавления guard в CPU-диагностике наблюдалось продолжение после нескольких отказов и `memcpy` с destination=NULL. Поэтому `ds9_memory_observer` сообщает отказ после освобождения lock; emulator audit завершает процесс с логом и выключает датчик. Callback выключен по умолчанию и сбрасывается при init; без него сохраняются прежние `-1/MAP_FAILED` и Android errno. Остановка в observer не означает, что выполнен полный поиск рабочего бюджета или что любой отказ mmap фатален для игры.

Следует исследовать lifetime/пики донорского allocator и согласовать split/shared arenas с полным бюджетом New3DS, затем снова пройти именно эту ветку. Не снимать guard и не увеличивать память вслепую. Также остаются реальные APK bootstrap assets и запись/создание `appdata://published/var`: сейчас этот путь отклоняется. Далее — недостающие GL matrix/geometry calls, renderer, sampling и звук. Нельзя превращать неизвестные вызовы в успешные заглушки.

Основные команды из корня проекта:

```powershell
python porting/tools/build_emulator_runtime.py
python porting/tests/test_assets.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/verify_directory_delegate.py
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

Azahar cases выполнять последовательно: они используют одну приватную SD. Для полного обновления свидетельств после rebuild повторить все прежние core suites, baseline/sensor/graphics CPU и девять Azahar cases до checker. Hardware backend `ds_exec.c/ds_cache.s`, cache SVC0x94, последний hardware stage8 и старые CIA не изменены. Новая сборка остаётся emulator-only и отказывает на настоящей консоли до исполнения donor.

Контракты интерфейсов: [Android AssetManager.list](https://developer.android.com/reference/android/content/res/AssetManager#list(java.lang.String)), [JNI object arrays](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#newobjectarray).
