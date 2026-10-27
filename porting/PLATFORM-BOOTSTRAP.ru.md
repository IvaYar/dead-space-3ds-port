# Системный bootstrap: результат на компьютере

**Последний результат:** [JNI-STRINGS.ru.md](JNI-STRINGS.ru.md) — UTF-16/modified UTF-8 реализованы и проверены; движок дошёл до AssetManager.list(""). Первая текстура512×512 RGBA с совпадающей CRC сохранена. Проверены275 core-тестов +14 isolated sensor-тестов и девять engine-сценариев, strict preflight154/234/4. Кадра игры ещё нет. Нижеследующие описания относятся к предыдущим режимам.

**Текущее продолжение:** [SENSOR-JNI.ru.md](SENSOR-JNI.ru.md) — датчик подключён в opt-in режиме, оба эмулятора дошли до `glGetIntegerv(GL_VIEWPORT)`. Проверены 166 core-тестов, 14 sensor-тестов и восемь engine-сценариев. Ниже сохранено описание базового guarded режима, где датчик намеренно не подключается.

Новая установка на приставку сейчас не нужна. В Unicorn ARM11 и Azahar оригинальная библиотека прошла системные свойства, настройку дисплея и первый возврат из `NativeOnDrawFrame`. **Изображения игры и меню пока нет.** С подключённым датчиком второй вызов доходит до первого GLES-запроса; без opt-in остаётся прежний ранний отказ перед акселерометром.

## Что добавлено

`ds11_platform` задаёт явный профиль совместимости. `SystemAndroidDelegate` поддерживает 29 строковых методов; игра действительно запросила 28 из них. Профиль сообщает Nintendo/New Nintendo 3DS, ARM11/PICA200, `armeabi`, один логический дисплей и бюджет приложения 64 MiB. Android API 10 и версия 2.3.3 описывают контракт совместимости, а не ОС приставки. Количества ещё не реализованных устройств ввода и датчиков равны нулю. Данные телефона и идентификаторы пользователя не выдумываются.

Конструкторы поддерживаемых native-сервисов создают разные объекты с проверяемой идентичностью. Для строк теперь действуют локальные/глобальные ссылки; последняя ссылка освобождает слот строки. `PushLocalFrame`, `PopLocalFrame` и `EnsureLocalCapacity` управляют областью жизни ссылок, включая перенос результата во внешнюю область. Активные pins требуют release до удаления. Каждый вход в native lifecycle обрамляется отдельной областью ссылок.

Это исправило накопление локальных ссылок при повторном `Query.isContentReady`: без готового кеша проверено 120 возвратов с **четырьмя живыми ссылками** в конце, без исчерпания пула. Два зарегистрированных исключения — ожидаемые попытки открыть отсутствующие необязательные `EAMCore.ini`/`eamcore.ini`; они не выдаются за ошибку управления ссылками.

`Query.getVersion` возвращает `1.1.33 Universal SD (Default)` из manifest выбранного APK. Его Java-метод запрашивает `PackageInfo.versionName`; строка 1.0.1 в DEX является fallback и здесь не используется. Требуемые данные сохранены в `analysis/android-abi/`.

У выбранной библиотеки обнаружена узкая несовместимость JNI: запрос `isContentReady()Z` вызывается через `CallStaticObjectMethodV`. Включён отдельный opt-in только для этой пары метода/сигнатуры и выбранного проверенного донора. Он возвращает реальный результат проверки квитанции ресурсов. Другие несоответствия типа результата по-прежнему отклоняются.

В приватную SD эмулятора скопированы и сверены по SHA-256 **1728 файлов, 414 822 611 байт**. Квитанция `assets-verified.txt` записывается после полной проверки. Native-проверка сравнивает её точные байты, включая LF; ошибка Windows CRLF в первоначальном генераторе исправлена. Квитанция фиксирует состояние после подготовки: 415 MB не перечитываются на каждом callback. Отдельные отрицательные тесты с отсутствующим и испорченным `achievements.sb` останавливают запуск до конструкторов.

Для дисплея заданы естественные логические размеры 240×400 и выбранная ориентация к поверхности 400×240. DPI 96 — параметр профиля, не измерение панели. Поддержаны float-возвраты JNI и проверяемые состояния ориентации; неподдержанные значения отклоняются. `PowerManagerAndroid.ApplyKeepAwake` в Azahar вызывает настоящий `aptSetSleepAllowed`, в CPU-тесте используется явно обозначенная модель. Cleanup восстанавливает разрешение сна; повторная инициализация активной политики без cleanup отклоняется.

## Проверки и точка остановки

Прошли **158 ARM-тестов**: 122 прежних, 20 JNI/EAIO и 16 новых системных. Отдельный оригинальный softfp-тестовый модуль проверил **168 условий**, включая все 29 свойств, строки, области ссылок, версию, float DPI и управление питанием. После него открытых файлов и heap-блоков ноль. Это отдельный контекст; сохраняемые настоящим EAIO ресурсы игры остаются живыми до завершения экспериментального процесса.

Семь сценариев Azahar: ожидание A, отсутствующий донор, неверный CRC донора, отсутствующий ресурс, неверный CRC ресурса, неподтверждённый кеш и нормальный запуск до следующего диагностического отказа. Результаты привязаны к SHA-256 текущих ELF/CXI. Аппаратный RX/кэш совпадает с прошедшим на консоли этапом 8.

```text
Platform probe: 0 checks=168 properties=29
Platform cleanup: files=0 heap=0
...
Frame 1 returned
Frame 2 begin
JNI accelerometer backend missing: com/ea/blast/DeviceOrientationHandlerAndroidDelegate.SetEnabled (Z)V MISSING
STOP Java adapter
Phase: NativeOnDrawFrame
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

Без ранней диагностики SDK запрашивал модуль 100, получал NULL при объявленном количестве акселерометров 0 и разыменовывал его по смещению `0x31e5a8`. Это сохранено в `analysis/engine-sensor-diagnostic.json`. Точная причина подтверждена машинным кодом выбранного донора, включая константный getter ID акселерометра. Пропускать эту ветку или выдавать статические фиктивные показания не стали.

Для подготовки следующего адаптера отдельно прочитаны объявления **того же APK**: `AccelerometerAndroidDelegate` использует `SetEnabled(Z)V`, `SetUpdateFrequency(I)V` и native-callback `NativeOnAcceleration(FFF)V`. Инструмент `tools/inspect_android_sensor.py` сохраняет сигнатуры и хеши тел методов DEX. Отдельная CPU-трасса `analysis/accelerometer-contract-experiment.json` с искусственно включённым capability служит только обнаружению запроса класса и не входит в успешные проверки native-сервиса.

Следующая работа — настоящий мост HID: включение/выключение датчика, частота обновления, преобразование осей и единиц, callback через softfp. Наличие функций libctru ещё не подтверждает правильность преобразования и работу на консоли. Фиксированная очередь ориентации уже проверена изолированно, но в текущем запуске игры выключена до реализации датчика.

## Воспроизведение

Команды из корня проекта, сценарии Azahar выполняются последовательно:

```powershell
python porting/tools/prepare_emulator_assets.py
python porting/tools/build_emulator_runtime.py
python porting/tests/test_emulator_runtime.py
python porting/tests/test_jni10.py
python porting/tests/test_platform_jni.py
python porting/tools/run_engine_experiment.py
python porting/tests/smoke_engine_azahar.py --case ready
python porting/tests/smoke_engine_azahar.py --case missing
python porting/tests/smoke_engine_azahar.py --case wrong
python porting/tests/smoke_engine_azahar.py --case asset-missing
python porting/tests/smoke_engine_azahar.py --case asset-wrong
python porting/tests/smoke_engine_azahar.py --case content-unverified
python porting/tests/smoke_engine_azahar.py --case present
python porting/tools/check_engine_progress.py
python porting/tools/inspect_android_sensor.py
```

Сводка — [analysis/engine-progress.json](analysis/engine-progress.json), журнал — [analysis/azahar-smoke/engine-present.log](analysis/azahar-smoke/engine-present.log), независимая трасса — [analysis/engine-first-entry-experiment.json](analysis/engine-first-entry-experiment.json). Предыдущий результат EAIO сохранён в `analysis/eaio-baseline/`.

Сборка остаётся **CXI только для эмулятора**, с отказом на реальной приставке. Новый CIA не создавался. Обычный загрузчик всё ещё отказывается связывать донор полностью: реализованы 152 импорта, отсутствуют 236 обязательных и 4 слабых. Ловушки неизвестных функций не считаются реализацией. GLES, звук, управление, полный Android lifecycle и native RX всего модуля пока не проверены.
