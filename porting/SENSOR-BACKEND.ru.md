# Изолированный мост акселерометра

**Обновление:** JNI-интеграция уже выполнена в отдельном режиме запуска — см. [SENSOR-JNI.ru.md](SENSOR-JNI.ru.md). Ниже описан нижний слой и его изолированный тест; `game_adapter_enabled=false` в его отчёте относится к этому отдельному тестовому CXI.

Добавлен нижний слой `ds12_sensor` и native HID backend `ds12_sensor_3ds`. В opt-in режиме он уже подключён к JNI игры; обычный guarded режим сохраняет прежнюю контролируемую остановку. Изображения игры пока нет, новая установка на приставку не нужна.

Модуль включает/выключает акселерометр настоящими HIDUSER-вызовами и получает последнее кешированное показание через `hidScanInput`/`hidAccelRead`. Включение идемпотентно; при неудачном выключении ownership сохраняется для повторной попытки. Вызывающая сторона владеет инициализацией HID и сериализует доступ. Нет отдельного потока, аллокаций и изменения native RX/backend.

Преобразование требует явно заданных соответствия осей, знаков, bias и counts/g для каждого входного канала. Нулевые/повторяющиеся оси, неподдержанные масштабы и NaN/Inf отклоняются до изменения состояния. Выход — m/s², с сохранением составляющей тяжести. Значение 512 counts/g и identity-оси в native-тесте — номинальная конфигурация эмулятора, не аппаратная калибровка и не подтверждённая ориентация EA SDK.

Частота 1–200 Hz ограничивает **передачу** показаний. Она не задаёт частоту самого HID-датчика; повторение кешированных показаний допустимо. Таймер использует 64-битные микросекунды, отклоняет ход назад и не переполняет deadline около UINT64_MAX. Отсутствие данных и ошибка чтения не перезаписывают выход. При неудачном enable датчик не считается включённым.

Изолированный callback `NativeOnAcceleration(FFF)V` проверен отдельно скомпилированным softfp-модулем: env/object, два float в регистрах и третий float на стеке переданы правильно. Это проверка ABI, а не вызов настоящего делегата игры.

Прошли **14 ARM-тестов** нижнего слоя, включая добавленную проверку Android delay-кодов. Отдельный CXI для Azahar вызвал настоящий libctru HID, получил **40 показаний**, завершил disable/close с active=0 и без ошибок. Последний вектор при identity-конфигурации: `(0, 0, -9.80665)`. На настоящей приставке этот код не запускался. CXI отказывается работать вне эмулятора; CIA не производится.

```text
Backend=0 init=0 enable=0 close=0 active=0
Samples=40 errors=0 latest=0.00000 0.00000 -9.80665
SENSOR BACKEND PASSED
```

Команды из корня проекта; Azahar не запускать одновременно с другими smoke-тестами:

```powershell
python porting/tools/build_sensor.py
python porting/tests/test_sensor.py
python porting/tests/smoke_sensor_azahar.py
python porting/tools/check_sensor_progress.py
python porting/tools/check_engine_progress.py
```

Сборка использует локальный toolchain и icon/banner от предыдущей emulator-сборки; игровой донор для этих изолированных тестов не требуется. Артефакты — `3ds/build-sensor/`; они отделены от `build-emulator/`. После JNI-интеграции полный core-набор расширен до 166 тестов, а engine-сценариев стало восемь; результаты обновлены на новой сборке. Свидетельства нижнего слоя — `analysis/sensor-progress.json`, `sensor-tests.json`, `sensor-native-result.json` и `analysis/azahar-smoke/sensor-native.log`.

Смысл Java `SetUpdateFrequency(I)V` уже проверен, добавлен отдельный API Android delay-кодов и opt-in JNI-класс AccelerometerAndroidDelegate. Прежний барьер SDK пройден до GLES. Остаётся подтвердить физические оси/калибровку, дальнейший lifecycle и вызов настоящего обработчика ускорения игры после графического bootstrap. Текущий графический барьер подробно разобран в SENSOR-JNI.ru.md.

Первичные источники для параметров и API: [libctru v2.7.0 HID](https://github.com/devkitPro/libctru/blob/v2.7.0/libctru/source/services/hid.c), [Azahar HID, коэффициент 512](https://github.com/azahar-emu/azahar/blob/master/src/core/hle/service/hid/hid.cpp), [Android SensorEvent, единицы accelerometer](https://developer.android.com/reference/android/hardware/SensorEvent). Аппаратное преобразование осей и калибровка требуют отдельного подтверждения.
