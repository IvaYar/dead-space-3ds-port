# Android ARM32 setjmp/longjmp: прежний барьер пройден

**Следующий результат:** [JNI-STRINGS.ru.md](JNI-STRINGS.ru.md) — NewString и UTF-16 операции реализованы, оба эмулятора дошли до AssetManager.list(""). Теперь275 core-тестов; первый игровой texture upload сохранён. Ниже исторический jump checkpoint.

Оригинальный движок в **Unicorn и Azahar прошёл `setjmp`**. Теперь он останавливается на **JNIEnv slot 163 — `NewString` (UTF-16)**, caller offset `0x0022e72c`, второй `NativeOnDrawFrame`. Это следующий JNI entry point, не NewStringUTF: последний уже реализован в slot 167. Игрового кадра пока нет.

Первая игровая текстура сохраняется: 512×512 RGBA, 1 048 576 байт, CRC32 `a738ea1c`. CRC входа игры и CPU-store Unicorn совпадают с native-store Azahar. GL error0, queries7, clear/draw0; renderer не добавлен.

## Реализация DS17

`ds17_jump.c/.s/.h` содержит отдельные ARM entry points для setjmp/longjmp и _setjmp/_longjmp. Буфер Android — **64 слова /256 байт**. Layout закреплён по AOSP Gingerbread: magic0, mask1, d8–d15 начиная со слова2, FPSCR18, r4–r14 начиная с19, reserved начиная с30. Наш адаптер использует reserved30/31 для owner TLS и собственного tag.

Путь игры передаёт buffer, выровненный на **4 байта**, а не на8. Поэтому VFP сохраняется через VMOV и 32-битные loads/stores. C helpers вызываются с выравниванием стека8, а исходный caller SP восстанавливается точно. Возврат через BX LR поддерживает ARM/Thumb. Значение longjmp0 преобразуется в1, отрицательные значения сохраняются. Перед переходом возвращаются core/VFP/FPSCR; после восстановления регистров C-вызовов нет. Native newlib jmp_buf не переинтерпретируется.

Это самостоятельная реализация буфера, не C-wrapper вокруг native setjmp: такой wrapper сохранил бы уже завершившийся frame. Registry указывает непосредственно на assembly entry points. Проверяются null/alignment, magic/tag, совпадение owner текущего потока, SP/LR и профиль mask. Проверка освобождает state gate до перехода. Ошибочный restore приводит к fatal path, а не к успешному возврату.

**Ограничения:** POSIX signal delivery не реализована. Setjmp сохраняет пустую mask профиля, longjmp отказывается от nonempty mask; underscore-пара её игнорирует. Sigsetjmp/siglongjmp не экспортируются. Frame lifetime и валидность произвольного указателя остаются обязанностью вызывающего кода: owner/tag не доказывают, что stack frame ещё жив. Нельзя смешивать этот буфер с контекстом native newlib или стороннего producer. Сохранение контекста не является C++ exception unwinding.

Четыре новых binding разрешили **два** дополнительных импорта выбранного донора. Текущий strict preflight: **154 resolved /234 missing /4 weak-zero**; отказ при неполной привязке и неизменность image проверяются. Старые документы со152/236 описывают предыдущие checkpoints. GL-registry остаётся67 и включается отдельно, только в graphics-аудите.

## Проверки

Прошли **13 новых ARM-тестов**: переход через несколько frames, ARM/Thumb interworking, zero→one/positive/negative returns, nested contexts, underscore-пара, r4–r14/VFP/FPSCR, 4 mod8 SP и buffer, canaries/reserved bytes, layout, owner/mask/magic/alignment rejection, fatal path и atomic registry capacity. Отдельно проверяется metadata экспортов строгим ELF loader.

В тестовом Thumb ELF обнаружилась особенность GNU ld: автоматический ARM veneer наследовал размер Thumb body и выходил за executable segment. Исправлена **сборка fixture**: hidden Thumb bodies вызываются через явно размеченные ARM exports. Loader не ослаблялся. Probe wrapper остаётся активным до возврата тестовой функции; он не оборачивает сам setjmp. Сохранение Thumb LR действительно проверяется.

Azahar выполнил по8 сценариев двух fixture-модулей: **18 сохранений и18 настоящих восстановлений** контекста, без отказов. Дополнительный переход в nested case объясняет отличие числа restores от числа сценариев. После probe counters сбрасываются перед игрой:

```text
Jump probe ARM: OK cases=8 core/VFP=OK
Jump probe Thumb: OK cases=8 core/VFP=OK
Jump probe counters: saves=18 restores=18 refusals=0
...
Production preflight: bound=154 missing=234 weak=4
Production guard: REFUSED; image unchanged
...
STOP unsupported: JNIEnv slot 163
Phase: NativeOnDrawFrame
Caller offset: 0022e72c
GLES first texture: 512x512 format=1908 bytes=1048576 CRC32=a738ea1c
Jump contexts: saves=20 restores=0 refusals=0
ENGINE EXPERIMENT STOPPED
No game frame rendered.
```

**Сама игра пока вызвала setjmp20 раз и longjmp0 раз.** Реальный возврат назад доказан собственными fixtures, не игровым error path. Перед новым JNI-барьером наблюдалась попытка `AssetManager.open("data.zip")` с IOException; игра очистила pending exception и продолжила. В точке остановки pending_exception0, live_refs17. После реализации NewString нужно исследовать дальнейшее восстановление/поиск ресурсов, не подменяя отсутствующий data.zip пустым файлом.

На текущем core повторно прошли **253 теста**: прежние240 +13 jump. Отдельный валидный sensor ELF сохраняет14 тестов: всего267 ARM-тестов двух сборок. Три CPU-режима и девять engine-сценариев Azahar пересозданы, оба checker прошли. Stage8 native RX/cache и старые CIA не изменялись. Нового CIA и проверки на приставке нет.

## Продолжение

Следующий блок — полноценное bounded `NewString(const jchar *, jsize)` и остальные нужные UTF-16 операции: длина в code units, embedded NUL, surrogate code units, modified UTF-8, pin/release, lifetime/local frames, отказ при исчерпании ёмкости. В наблюдаемом вызове длина0, но добавлять только фиктивную пустую строку нельзя. Затем идти по новому фактическому пути; matrices/geometry/PICA200, sampling/звук остаются впереди.

```powershell
python porting/tools/verify_jump_abi.py
python porting/tools/build_emulator_runtime.py
python porting/tests/test_jump.py
python porting/tools/run_engine_experiment.py --graphics
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

После rebuild core повторять восемь прежних test-скриптов, три CPU-режима и девять smoke-cases; Azahar последовательно, его SD общая. Источники AOSP/hashes закрепляет `analysis/android-abi/jump-abi-contract.json`; свидетельства — `analysis/jump-tests.json`, `analysis/engine-graphics-entry.json`, `analysis/azahar-smoke/engine-graphics.log`, `analysis/engine-progress.json`.

Первичные контракты: AOSP [machine/setjmp.h](https://github.com/aosp-mirror/platform_bionic/blob/android-2.3.3_r1/libc/arch-arm/include/machine/setjmp.h), [setjmp.S](https://github.com/aosp-mirror/platform_bionic/blob/android-2.3.3_r1/libc/arch-arm/bionic/setjmp.S), [_setjmp.S](https://github.com/aosp-mirror/platform_bionic/blob/android-2.3.3_r1/libc/arch-arm/bionic/_setjmp.S), Oracle [JNI NewString](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#newstring).

Все изменения локальные. GitHub обновлять только по прямому запросу пользователя.
