# Хэндофф: продолжение Dead Space Mobile → New 3DS

Состояние на 27 октября 2026 года. Общение с пользователем — по-русски. Он просил работать поэтапно и перенести промежуточные проверки в эмулятор, чтобы не переставлять SD после каждого изменения. Текущая задача: продолжить реализацию порта; новой проверки на приставке пока не просить. Последний запрос пользователя — сохранить проект в его GitHub и оставить хэндофф.

## Где продолжать

Основная рабочая папка с полными локальными данными: `C:\Users\jarom\Desktop\Dead_space_mobile`. Shell — PowerShell. Этот Git-репозиторий хранит исходники, скрипты, инструкции и свидетельства; `.gitignore` использует allowlist. APK, ZIP, игровые ресурсы и донор, toolchain, reference и приватная SD эмулятора остаются только локально. Не добавлять их через `git add -f`. Не отправлять токены и данные авторизации в Git.

Сначала прочитать:

1. `porting/PLATFORM-BOOTSTRAP.ru.md` — актуальное состояние и команды.
2. `porting/analysis/engine-progress.json` — итог проверки согласованности свидетельств.
3. `porting/3ds/source/ds10_jni.c`, `ds11_platform.c`, `ds11_platform_3ds.c` и соответствующие headers.
4. `porting/tools/run_engine_experiment.py`, `porting/tests/engine_azahar.c`, `porting/tests/test_platform_jni.py`.

`JNI-EAIO.ru.md` и значительная часть `EMULATOR-FIRST.ru.md` описывают предыдущие остановки; их верхние заметки ссылаются на актуальный документ. Не начинать заново с EAIO/SystemAndroidDelegate: они уже пройдены.

## Подтверждённый результат

- Пользовательская консоль — семейство New Nintendo 3DS; CIA устанавливался FBI, запускался из HOME Menu. Этапы 1–8 прошли на устройстве; точный журнал этапа 8 — `analysis/hardware/stage8-v0.8.0-user.log` внутри `porting`.
- На компьютере проходят **158 ARM-тестов**: 122 runtime/regression, 20 JNI/EAIO, 16 platform/JNI. **Семь сценариев Azahar** прошли на одной текущей сборке.
- Оригинальные 209 конструкторов завершились; JNI_OnLoad вернул 00010004 и сохранил правильный JavaVM. Вернулись NativeOnCreate, NativeOnSurfaceCreated, NativeOnSurfaceChanged и настоящая EAIO_Startup.
- Первый NativeOnDrawFrame вернулся, второй остановлен ранним диагностическим отказом перед отсутствующим адаптером акселерометра. **Ни игрового кадра, ни меню ещё нет.** Это возврат callback, не результат рендеринга.
- Реализованы 29 строковых System properties (игра запросила 28), конструкторы сервисов, opaque JNI refs для строк/объектов/массивов, global/local refs, Push/PopLocalFrame/EnsureLocalCapacity, float DPI, профиль дисплея и управление sleep policy через настоящий APT в native build. Cleanup восстанавливает разрешение сна; активную политику нельзя сбросить reinit без cleanup.
- Изолированный softfp platform-модуль проверяет 168 условий/29 свойств; I/O-модуль — 201 условие, 3568 байт и CRC32 4a8d9499. После каждого изолированного модуля файлов/heap-блоков 0. Ресурсы настоящего EAIO остаются живыми до завершения экспериментального процесса.
- Без готового asset receipt проверены 120 callback, 4 живые ссылки в конце, исчерпания пула нет. Два исключения в этом пути — отсутствующие необязательные EAMCore.ini/eamcore.ini.

## Следующий конкретный блок

Нужен настоящий адаптер акселерометра/HID: включение/выключение, частота, чтение, оси/единицы, native callback softfp. Пока capability=0. При попытке включить ориентацию стоит осознанный отказ `accelerometer backend missing` на `DeviceOrientationHandlerAndroidDelegate.SetEnabled(Z)V`, до известного NULL dereference.

Без раннего отказа оригинальный SDK запрашивал модуль ID 100, получал NULL и читал адрес 0 по смещению 0x31e5a8 выбранного донора. Getter ID акселерометра в том же доноре — mov r0,#100; bx lr. Это **не доказательство проблемы AudioTrack**. Диагностика сохранена в `analysis/engine-sensor-diagnostic.json`. Не пропускать ветку и не подменять успех фиктивными показаниями.

Из того же APK извлечены объявления DEX:

```text
com/ea/blast/AccelerometerAndroidDelegate
  <init>()V
  SetEnabled(Z)V
  SetUpdateFrequency(I)V
  NativeOnAcceleration(FFF)V  [native]
```

Инструмент `tools/inspect_android_sensor.py` проверяет SHA DEX, читает объявления и сохраняет `analysis/android-abi/candidate-sd-sensors.json`. Локальный DEX `candidate-sd-classes.dex` не коммитится. Отдельная `analysis/accelerometer-contract-experiment.json` искусственно выставляла capability=1 **только в CPU-модели**, чтобы найти следующий запрос класса; это исследование, не работающий sensor backend и не часть 158 успешных тестов.

Для исследования просмотрены первичные источники: libctru v2.7.0 `hid.h`/`hid.c` (HIDUSER_EnableAccelerometer/DisableAccelerometer, hidScanInput/hidAccelRead), Android SensorEvent (ускорение в m/s²), Azahar HID `hid.cpp` (коэффициент 512). Правильность преобразования осей и калибровки ещё не подтверждена. Не объявлять поддержку датчика только по наличию API. Можно продолжить независимо на CPU-моделях и Azahar, а аппаратную проверку объединить позднее.

## Не ломать проверенную основу

`ds_exec.c` и `ds_cache.s` должны совпадать с hardware stage 8. Хеши:

```text
ds_exec.c  09b92e8a9d1f63928c9fc5d1b55e301721e06d54370ffc3604b202d5d73f5746
ds_cache.s 1ef11401b18567eb183ff76cec9c59fc05ddec1dd988af6446a14fdf748ef6c3
```

Не возвращать диапазонный I-cache SVC 0x93: ранее был Arm11 data abort при cache maintenance. Стабильный backend использует полную инвалидацию SVC 0x94. Аппаратный backend ограничен 16 страницами; исполнение всего модуля на настоящей консоли ещё не проверено. Azahar не проверяет native RX/cache. Текущий engine-audit.cxi **только для эмулятора**, имеет отказ на реальном устройстве и не собирается в CIA.

Обычный production resolver отказывается полностью связывать донор: **152 реализованных импорта, 236 обязательных отсутствуют, 4 weak-null**; образ при отказе не меняется. В эксперименте неизвестные функции связаны со стоп-ловушками; это инструментирование, не реализация. Не уменьшать missing заглушками успешного возврата.

Полноценные GLES/PICA200, звук, управление, Java VM, C++ exceptions и Android lifecycle не реализованы. После датчика продолжать по реальным запросам/ловушкам. Нельзя гарантировать число этапов или срок до играбельной сборки.

## Донор, ресурсы и зависимости

Выбран SD 1.1.33 из пользовательского `DeadSpace-1.1.33-Universal.zip`:

```text
porting/analysis/candidate-sd/libEAMGameDeadSpace_orig.so
SHA-1   3c4a1b844eddbf3b9f0d2d946433bc429cc64b2e
SHA-256 dd42272365d0abd8ad9c89450bb7f869ee4ac0ad548525758e6a1e7df4d3c1eb
CRC32   9fd95635
Размер  4499468 байт
```

`analysis/candidate-sd/assets` — 1728 файлов/414822611 байт, `published` — 1727 файлов/414822553 байт. Они SHA-256 сверены и скопированы в `analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace/assets`. `prepare_emulator_assets.py` пишет квитанцию `assets-verified.txt` **байтами ASCII с LF**. Windows write_text добавлял CRLF и ломал точное сравнение; исправлено. Runtime доверяет квитанции подготовки, не перечитывает весь кеш каждый frame.

APK versionName: `1.1.33 Universal SD (Default)`, versionCode 1155. Строка DEX 1.0.1 — fallback, не текущая версия. В оригинальном доноре isContentReady()Z вызван через ObjectMethodV; есть узкий opt-in для этого метода после проверки выбранного донора. Остальные несоответствия JNI family/сигнатур отвергаются.

Локальный toolchain: `porting/toolchain/devkitpro/devkitARM/bin`, GCC 16.1/libctru 2.7.0; makerom/ctrtool/bannertool — в `toolchain/extras`. Python Unicorn 2.1.4/zstandard — в `toolchain/python`. Azahar libretro 2126.2 — `toolchain/azahar-libretro/azahar_libretro.dll`. `bootstrap_toolchain.py` восстанавливает часть зависимостей; при свежем клоне нужны также свои APK/ресурсы, DEX и Azahar. Старые fixtures для emulator build генерируются builders этапов 1–8; они не хранятся как бинарники в Git. В исходной рабочей папке всё уже есть.

Vita reference локально: `porting/reference/deadspace-vita`, commit 3eaa3c4b8a0201eec746f7676e0bddcffc5d5638, MIT. Его донор другой. Не копировать offsets, fake handles или нулевые sensor-заглушки. Reference не включён в Git.

## Как проверить изменения

Полные команды в PLATFORM-BOOTSTRAP.ru.md. Сначала build, затем 122+20+16 тестов и CPU trace. Семь сценариев Azahar выполнять **последовательно**: у них общая приватная SD. В конце `python porting/tools/check_engine_progress.py` проверяет source/output hashes, backend stage8, hardware evidence и согласованность результатов и пишет `analysis/engine-progress.json`. При изменении C/core требуются новые результаты с новым hash; старые не выдавать за текущие. `.gitattributes` отключает преобразование концов строк для сохранения хешей исходников и свидетельств.

Снимки прошлых барьеров: `analysis/engine-baseline/` и `analysis/eaio-baseline/`. Пакеты этапов 1–8 и их исторические manifests не переписывать задним числом. Полные локальные данные и старые CIA не удалять.

Продолжать действия автономно в уже разрешённой области, без повторного вопроса «продолжать?». О результатах сообщать кратко и честно: что заработало, какие проверки прошли, где остановился оригинальный код. Для каждого шага не требовать приставку; аппаратный запуск согласовывать на существенном результате, без обещаний отсутствия сбоя.
