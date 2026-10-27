# Акселерометр подключён к JNI: первая остановка GLES

**Продолжение после этой остановки:** [GLES-TEXTURES.ru.md](GLES-TEXTURES.ru.md). GL_VIEWPORT, начальные client-array состояния и glGenTextures уже пройдены в graphics-режиме; текущий барьер — GL_CULL_FACE. Этот документ сохраняет описание sensor-only режима.

В отдельном режиме с датчиком оригинальная библиотека в Unicorn и Azahar прошла прежний барьер `AccelerometerAndroidDelegate` и дошла до **`glGetIntegerv(GL_VIEWPORT)`**. Это запрос графического состояния, не отрисованный кадр. Изображения игры пока нет. Приставка для этого продолжения не требуется; новые CIA не создавались.

## Что изменилось

По телу DEX выбранного APK установлено: `SetUpdateFrequency(I)V` сохраняет аргумент в `mSensorDelay`, а при активном listener выключает и включает его заново. Значение — Android delay code/микросекунды, **не Hz**. Проверены также поле и начальное значение 3 в конструкторе.

По первичному SensorManager Android **2.3.3** соответствие такое:

| Код | Интервал |
| --- | --- |
| 0 | FASTEST, передача при каждом вызове pump |
| 1 | 20 000 µs |
| 2 | 60 000 µs |
| 3 | 200 000 µs |
| ≥4 | Запрошенные микросекунды |

Отрицательные значения отклоняются. Код 2 здесь именно 60 000, не значение из более новых Android. Инструмент `tools/verify_sensor_delay.py` проверяет исходный SHA DEX, инструкции setter/constructor и хеш исходника AOSP. Свидетельство — `analysis/android-abi/sensor-delay-contract.json`. Исходник AOSP кешируется локально и не включён в allowlist Git.

`ds12_jni_sensor` привязывает инициализированный, выключенный sampler и softfp-callback к JNI-контексту. Только после успешной привязки профиль сообщает один акселерометр. Реализованы конструктор, SetEnabled и SetUpdateFrequency с проверками receiver, method ID и типов. Повторное создание singleton явно отклоняется; без backend конструктор отказывает. Результат ошибки native-сервиса не выдаётся за успешное включение.

Контекст удерживает global reference объекта датчика. Для callback создаётся отдельная локальная ссылка receiver и область JNI; после возврата она освобождается вместе с временными ссылками callback. Cleanup отключает датчик до освобождения контекста. Если disable не удался, возвращает UINT32_MAX и сохраняет контекст для повторной попытки. Владелец закрывает sampler после остановки пользователей JNI.

Есть два явных режима:

- Обычный `--case present` оставляет capability=0 и проверяет прежний ранний отказ; это регрессионный барьер.
- `--case sensor` временно записывает маркер в **приватную SD Azahar** и подключает настоящий HID backend. Калибровка identity/512 counts/g указана как экспериментальная, без аппаратного подтверждения. Маркер убирается после теста. На настоящей консоли весь engine-audit по-прежнему отказывает до выполнения игрового кода.

В Unicorn `--sensors` использует явно помеченную injected CPU-модель, а не native HID. Её результаты сохраняются отдельно от обычной трассы. В обоих режимах неизвестные импорты остаются стоп-ловушками; GLES не подменяется нулевыми результатами.

## Полученный результат

```text
JNI SensorDelay: com/ea/blast/AccelerometerAndroidDelegate.SetUpdateFrequency 3
JNI SensorEnabled: com/ea/blast/AccelerometerAndroidDelegate.SetEnabled 0
JNI SensorEnabled: com/ea/blast/AccelerometerAndroidDelegate.SetEnabled 1
STOP unsupported: glGetIntegerv
Phase: NativeOnDrawFrame
Caller offset: 003235b0
Sensor shutdown: result=0 active=0 events=0 delay=3
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

CPU-трасса показывает аргумент `0x0ba2`, то есть GL_VIEWPORT; caller offset совпадает с native-журналом. Частота, запрошенная SDK, — NORMAL (200 ms). HID при завершении отключён. **Настоящий NativeOnAcceleration игры ещё не вызван**: остановка GLES наступает до возврата второго draw callback и очередного pump. Правильность softfp и области JNI отдельно подтверждают тестовые callbacks; это не заменяет дальнейшую проверку оригинального обработчика.

Проверены **166 тестов на ARM core** (122 runtime +20 JNI/EAIO +16 platform +8 sensor/JNI), **14 отдельных sensor-тестов**, восемь engine-сценариев Azahar и отдельный native sensor-тест с 40 показаниями. Оба checker проверяют текущие source/output hashes и совпадение native RX backend с аппаратным stage8. Суммарно это 180 ARM-тестов двух отдельных тестовых ELF, а не аппаратная проверка.

## Продолжение

Следующий блок — минимальный настоящий GLES 1.x context/state и последующий renderer PICA200/citro3d. Первый запрос — GL_VIEWPORT. Нельзя просто возвращать фиктивный viewport и объявлять графику реализованной; нужно связать состояние контекста, поверхность и будущий рендеринг. Импорты production не изменились: 152 реализованных, 236 обязательных отсутствуют, четыре weak-null.

Физические оси/калибровка датчика и работа на реальной консоли остаются непроверенными. Экспериментальная identity-конфигурация допускается для текущей трассировки до графического барьера и не объявляется готовым управлением наклоном.

После обычной подготовки и сборки `build_emulator_runtime.py`:

```powershell
python porting/tests/test_sensor_jni.py
python porting/tools/verify_sensor_delay.py
python porting/tools/run_engine_experiment.py --sensors
python porting/tests/smoke_engine_azahar.py --case sensor
python porting/tools/check_engine_progress.py
```

После изменения sensor core также собрать `build_sensor.py`, выполнить `test_sensor.py`, `smoke_sensor_azahar.py` и `check_sensor_progress.py`. Полный прежний набор и семь обычных engine-сценариев выполнены заново на текущей сборке. Azahar-сценарии выполнять последовательно. Свидетельства: `analysis/engine-progress.json`, `analysis/engine-sensor-entry.json`, `analysis/azahar-smoke/engine-sensor.log`, `analysis/sensor-jni-tests.json`, `analysis/sensor-progress.json`.

Все новые изменения остаются **локально**. По просьбе пользователя GitHub обновлять только после отдельного явного запроса.
