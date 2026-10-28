# Продолжение Dead Space Mobile → New Nintendo 3DS

Актуально: 28 октября 2026. Обновлено после двух циклов GPU исправления/проверки: появился настоящий кадр игры через PICA, но визуальная эквивалентность ещё не достигнута. Это главный хэндофф; старые записи в HANDOFF.ru.md и WORK-IN-PROGRESS.ru.md сохраняют историю и местами устарели.

Пользователь возобновил разработку с целью первого корректного GPU кадра и разрешил отдельный коммит с отправкой в GitHub после проверки отсутствия оригинальных ресурсов. Последующие push требуют отдельной просьбы. Общаться по-русски. Рабочая папка: `C:\Users\jarom\Desktop\Dead_space_mobile`, PowerShell. Репозиторий: `IvaYar/dead-space-3ds-port`, private, main. Продолжать с результатов ниже, не повторять уже доказанные гипотезы. Полные 552 ARM-теста нужны перед важным этапом совместимости, а не после каждой локальной GPU правки.

## Что действительно работает

- Порт использует оригинальную Android ARM32 SD English 1.1.33 библиотеку через совместимый ABI/JNI/libc/GLES слой. Донор, APK и исходные ресурсы не изменены.
- CPU renderer показывает настоящие полные кадры вступительной сцены: планета, корабль, станция, титры. `porting/analysis/scene-vertex-frame/first-game-frame.png`: frame4628, 240 callbacks после реального выбора Easy и подтверждения. Это ещё не управляемый геймплей.
- Последний CPU кадр после восстановления Azahar checkpoint: `porting/analysis/scene-checkpoint-frame/first-game-frame.png`, frame2828, 360 callbacks после подтверждения2468: станция и надпись DEAD SPACE. GL error0, arena refusals0, paging failures0. Прежний чёрный2605 был ранним состоянием, а не окончательным барьером CPU renderer.
- До последних GPU hooks полный набор26 ARM suites прошёл552 теста. Core SHA256 `46532d21f007b639a500bc12526bc3202dc5e855492edae50b97cb2e79f7bece`; CPU178 CXI `ffb0be375d0bbef61f1fd58faf0f052a41326d0825995a52eb49cd7cc6a2e8d8`. Эти бинарники ещё лежат в build-emulator; текущие исходники новее. НЕ выдавать старый manifest за сборку последних GPU hooks.
- Оптимизированы sampler lookup, transform matrix access, per-draw vertex cache, pixel fast paths и буферизация журналирования. Одинаковая sampler fixture снизилась514976→304952 ARM instructions с неизменным pixel SHA. Это не измерение FPS на приставке.
- Реальный save/restore Azahar работает после60 warm-up retro_run перед unserialize (MUST_INITIALIZE). После restore2469 удалось дойти до2828. Хостовый runner в конце упал на локальном `import re`, мешавшем построить отчёт; эти два import теперь удалены, module-level import сохранён. Игра завершила capture нормально. В scene-checkpoint-frame отчёт восстановлен из журнала и помечен recovered, без выдуманного host elapsed.
- Последняя аппаратная проверка пользователя: STAGE8 PASSED. Исполнительный RX/cache backend ds_exec.c/ds_cache.s не менялся. Нового игрового CIA и проверки полного движка на консоли нет. Звук и управляемый gameplay не подтверждены.

## Текущая разработка: DS34 PICA GPU backend

Citro3D1.7.1 собран из официального commit `9f21cf7b380ce6f9e01a0420f19f0763e5443ca7`, Zlib license, без изменения существующего SDK. Bootstrap проверяет hash. Библиотека и исходники SDK только локально, `porting/toolchain/citro3d*`. Воспроизведение: `python porting/tools/bootstrap_citro3d.py`.

Код: `ds34_gpu.h`, `ds34_gpu_3ds.c`, `ds34_gpu.v.pica`; weak hooks в ds13/ds15/ds22/ds26. CPU сохраняет проверку данных, clipping, culling, vertex lighting; GPU получает прошедшие проверку треугольники. CPU FBO остаётся CPU, изменения текстуры инвалидируют GPU cache. Неподдержанные состояния явно останавливаются. Пока нет GPU fog/stencil/offset/COMBINE/projectiveUV/default-readback; NPOT repeat отказ. Default GPU depth24/stencil8; CPU default16/8.

Три независимые сборки и SD, не перезаписывают CPU baseline:

1. `python porting/tools/build_gpu_probe.py`, `python porting/tests/smoke_gpu_probe.py`: настоящий PICA RGB triangle PASS, `analysis/azahar-gpu-probe/result.json`.
2. `python porting/tools/build_gpu_gles.py`, `python porting/tests/smoke_gpu_gles.py`: PASS по реальным пикселям всех 7 случаев. Scissor, 2×2 RGBA, ALPHA blending, 256×256 RGBA (256 KiB), single-buffer output, переход через 8190 вершин внутри одного GLES draw, draw→clear→draw. 19 GPU draws/2766 triangles/4 uploads, CPU fragments=samples=0. Дополнительный вариант обеих команд с `--engine-memory` повторяет профиль движка (178 MiB, heap40/linear132, предварительная arena128): тоже PASS, отдельные build-gpu-gles-memory и analysis/azahar-gpu-gles-memory. Это fixtures, не игра.
3. `python porting/tools/build_gpu_engine.py`: engine_azahar.c с DS_PICA_BACKEND, TitleID000400000FDE6600, только CXI для эмулятора. Последняя сборка `b0e3f85c35ffe3af8586316e33e0536401bc0cd750389fdd0389cb80f109643f`. Кадр180 теперь показывает оригинальный экран с Айзеком/наушниками. GL0, 387 draws/3006 triangles/4 uploads/1 MiB VRAM; CPU fragments=samples=0. `analysis/gpu-engine-first/first-game-frame.png`, CRC ea733050, PNG SHA256 `3410c1d5776fa32c658747f30a373292d781d078e412248d589a0866d80808a5`; 12323 ненулевых пикселя, 824 RGB565 значения. Это первый видимый GPU кадр, НЕ полная визуальная эквивалентность и НЕ playable CIA.

### Результат текущего этапа и ближайший блокер

Цикл1: гипотеза scratch **подтверждена пикселями**. До исправления верхняя белая полоса 256 KiB текстуры была красной (последняя порция scratch), старые маленькие случаи проходили. Evidence: `analysis/azahar-gpu-gles/large-before/`. Исправление: полный immutable Morton staging на upload, удерживаемый в Entry до блокирующего FrameBegin; общий staging cap4 MiB, при нехватке памяти — drain/retry, затем явный отказ. После исправления полосы правильные, но игровой кадр180 оставался полностью чёрным (CRC91875ccc). Отчёт `analysis/gpu-engine-first/cycle1-result.json`.

`sync_gpu` теперь делает DetachOutput→FrameEnd→блокирующий FrameBegin(0)→восстановление output. Это реальное завершение очереди без показа промежуточного кадра, перед повторным использованием stream/удалением VRAM/staging. FrameSplit ожиданием НЕ является; C3D_FrameSync сам по себе ждёт VBlank, очередь завершает FrameBegin. Clear теперь сначала делает FrameSplit(0), иначе немедленно добавляемый GX_MemoryFill обгоняет предыдущие PICA draws. Проверены rollover и clear ordering в fixture. CPU и SDK исходники не менялись; старые debug traces выключены по умолчанию (`DS34_TRACE` — compile-time opt-in).

Цикл2: fixture в профиле движка воспроизвела отсутствие ВСЕХ треугольников при исправном clear. Причина — default base_paddr=0x18000000 в BufInfo_Init и 28-битные attribute offsets: GPU stream после arena128 попадает в высокую New3DS FCRAM. DS34 задаёт base_paddr физическому адресу самого stream и проверяет BufInfo_Add. После этого обе fixture конфигурации PASS с одинаковыми PNG; игровой кадр появился. Evidence до address fix: `analysis/azahar-gpu-gles-memory/address-before/`. Итоговый подробный отчёт: `analysis/gpu-engine-first/gpu-session-result.json`; рядом согласованные run-result.json/run.log/build-manifest.json/raw/png.

**Следующий конкретный визуальный блокер:** мелкий текст GPU имеет пропуски/сдвиги строк относительно исторического CPU headphones frame120. Рисунок Айзека и значок узнаваемы; эталон сравнивался визуально, кадры120/180 и тайминг различаются, побитовое равенство не доказано. Не включать GPU auto-menu на основании одного видимого кадра. Следующий полезный эксперимент — маленькая текстура с тонкими горизонтальными линиями/шахматкой и atlas UV с дробными координатами, NEAREST и LINEAR; сравнить реальные GPU samples с DS22 (texel centers/UV rounding/filtering). Это гипотеза следующего сеанса, ещё НЕ установленная причина.

Отдельный установленный риск перед железом: Citro3D1.7.1 `C3D_TexBind(1,NULL)` читает tex->param по адресу0xC до проверки NULL. Backend так отключает неактивный unit1; Azahar пишет `unmapped Read32 @0x0000000C`, но продолжает исполнение. Это есть и в fixture, и в engine. Не объявлять hardware-safe; нужен безопасный путь отключения sampler без чтения NULL. В этой сессии после двух циклов новые исправления не делались.

552 ARM suites не запускались: менялся только optional DS34 и изолированные GPU fixtures/tooling. CPU178 CXI проверен повторно: прежний SHA `ffb0be375d0bbef61f1fd58faf0f052a41326d0825995a52eb49cd7cc6a2e8d8`. Оригинальные assets/CPU checkpoint/CPU build не изменялись.

Запуск реального GPU движка, PowerShell:

```powershell
$env:DEADSPACE_EMULATOR_ROOT=(Resolve-Path 'porting/analysis/azahar-gpu-engine').Path
python porting/tests/smoke_engine_azahar.py --case graphics --explore --gpu --capture-frame 180 --timeout-seconds 120 --cpu-percent 400 --resume-focus --private-files --apk-assets --shared-arena --framebuffers --memory-mib 178 --font-subset --allocator-compat --fog --combine --lighting --default-depth
python porting/tools/export_native_frame.py --emulator-root porting/analysis/azahar-gpu-engine --output-directory porting/analysis/gpu-engine-first
```

В GPU SD отдельно скопированы assets/apk-assets/receipts/font-subset из основной SD; saves/paging отдельные. Не запускать два native теста на одной SD. Разные GPU SD допускают независимые процессы. `--gpu` запрещён с обычной основной SD и CPU checkpoint. Пока CPU CRC auto-menu не подходит для GPU без отдельного подтверждения визуальной эквивалентности.

## Проверки и продолжение

- После GPU исправления: отдельная GPU GLES fixture → GPU engine visible first frame/headphones → menu → расширение реально нужных состояний3D. Не подменять изображение картинкой и не отключать игровые проходы ради успеха.
- До main rebuild сохранить CPU evidence/manifest. Сейчас нужная копия уже в scene-checkpoint-frame. Main build: `python porting/tools/build_emulator_runtime.py`; затем26 suites отдельно их main(), не unittest discovery (унаследованные fixtures так не запускаются).
- Suites: emulator_runtime, jni10, platform_jni, sensor_jni, gles_state, arrays, textures, pipeline, jump, strings, assets, first_frame, touch, private_files, apk_assets, jni_monitors, shared_memory, emulator_threads, framebuffers, texture_pages, font_profile, allocator_compat, fog, combine, lighting, default_surface. Сумма552, first_frame32, lighting28, default_surface12.
- `check_scene_progress.py --folder analysis/scene-vertex-frame --historical` и scene-trace-frame historical — существующие свидетельства. Legacy check_engine_progress/check_sensor_progress/check_first_frame ещё местами ожидают551/31/старый2605; требуется согласовать после финальной актуальной сборки, а не заявлять PASS без запуска.
- Авто-menu выбирает Easy только по точным CPU CRC95a4497f/416337f3. Live `--control-file` поддерживает pressed/x/y, scene_frames2..3600 и screenshot sequence. После confirm управление передаётся HID. JSON list теперь явно отвергается.
- Checkpoint `analysis/emulator-checkpoints/menu600` только локально;33,257,084 bytes, hash ea397a16fcfac4f9ab302da7003b4afc3d91e6022728538ef92cfa5daad048a2. Требует той же CPU CXI/DLL/profile и snapshot private SD. Не публиковать private save data.
- Активных наших smoke jobs к сохранению нет. Старый Python PID25180 существовал до этой работы; не трогать без проверки. Нельзя перезаписывать бинарник работающего native теста: runner хеширует CXI в конце.
- Git allowlist сохраняет только код/документы/выбранные evidence. APK, оригинальная .so, игровые assets, SDK, emulator private SD, savestates, tokens не добавлять через -f.

Честная текущая граница: видимая CPU вступительная сцена; расширенные GPU GLES fixtures PASS; первый видимый оригинальный GPU headphones кадр с оставшимися отличиями мелкого текста. Полный корректный игровой GPU кадр, меню, 3D gameplay и аппаратная безопасность GPU backend ещё не подтверждены. Аппаратных результатов после stage8 нет.
