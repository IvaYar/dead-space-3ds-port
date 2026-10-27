# Изолированный мост акселерометра

Добавлен нижний слой `ds12_sensor` и native HID backend `ds12_sensor_3ds`. В запуск игры он **ещё не подключён**: прежняя контролируемая остановка перед датчиком остаётся. Изображения игры пока нет, новая установка на приставку не нужна.

Модуль включает/выключает акселерометр настоящими HIDUSER-вызовами и получает последнее кешированное показание через `hidScanInput`/`hidAccelRead`. Включение идемпотентно; при неудачном выключении ownership сохраняется для повторной попытки. Вызывающая сторона владеет инициализацией HID и сериализует доступ. Нет отдельного потока, аллокаций и изменения native RX/backend.

Преобразование требует явно заданных соответствия осей, знаков, bias и counts/g для каждого входного канала. Нулевые/повторяющиеся оси, неподдержанные масштабы и NaN/Inf отклоняются до изменения состояния. Выход — m/s², с сохранением составляющей тяжести. Значение 512 counts/g и identity-оси в native-тесте — номинальная конфигурация эмулятора, не аппаратная калибровка и не подтверждённая ориентация EA SDK.

Частота 1–200 Hz ограничивает **передачу** показаний. Она не задаёт частоту самого HID-датчика; повторение кешированных показаний допустимо. Таймер использует 64-битные микросекунды, отклоняет ход назад и не переполняет deadline около UINT64_MAX. Отсутствие данных и ошибка чтения не перезаписывают выход. При неудачном enable датчик не считается включённым.

Изолированный callback `NativeOnAcceleration(FFF)V` проверен отдельно скомпилированным softfp-модулем: env/object, два float в регистрах и третий float на стеке переданы правильно. Это проверка ABI, а не вызов настоящего делегата игры.

Прошли **12 новых ARM-тестов**. Отдельный CXI для Azahar вызвал настоящий libctru HID, получил **40 показаний**, завершил disable/close с active=0 и без ошибок. Последний вектор при identity-конфигурации: `(0, 0, -9.80665)`. На настоящей приставке этот код не запускался. CXI отказывается работать вне эмулятора; CIA не производится.

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

Сборка использует локальный toolchain и icon/banner от предыдущей emulator-сборки; игровой донор для этих изолированных тестов не требуется. Артефакты — `3ds/build-sensor/`; они отделены от `build-emulator/`. Прежние 158 тестов и семь engine-сценариев не менялись; их проверяемые хеши сохранены. Новые свидетельства — `analysis/sensor-progress.json`, `sensor-tests.json`, `sensor-native-result.json` и `analysis/azahar-smoke/sensor-native.log`.

Следующий шаг: прочитать тело Java `SetUpdateFrequency(I)V` выбранного APK и установить смысл его аргумента. Внутренний sampler использует Hz; напрямую приравнивать это к аргументу SDK нельзя. После этого связать JNI-класс AccelerometerAndroidDelegate с сервисом, определить оси относительно DisplayAndroidDelegate, обработать жизненный цикл и проверить callback оригинальной библиотеки. Capability игры остаётся 0 до этой интеграции. Наличие изолированного HID backend не означает, что SDK уже проходит прежний барьер.

Первичные источники для параметров и API: [libctru v2.7.0 HID](https://github.com/devkitPro/libctru/blob/v2.7.0/libctru/source/services/hid.c), [Azahar HID, коэффициент 512](https://github.com/azahar-emu/azahar/blob/master/src/core/hle/service/hid/hid.cpp), [Android SensorEvent, единицы accelerometer](https://developer.android.com/reference/android/hardware/SensorEvent). Аппаратное преобразование осей и калибровка требуют отдельного подтверждения.
