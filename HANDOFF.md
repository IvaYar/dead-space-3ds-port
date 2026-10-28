# Продолжение Dead Space Mobile → New Nintendo 3DS

Актуально: 28 октября 2026, около 14:00 UTC. Это главный хэндофф; старые записи в HANDOFF.ru.md и WORK-IN-PROGRESS.ru.md сохраняют историю и местами устарели.

Пользователь остановил разработку и попросил сохранить всё в GitHub. После этой отправки не делать новые push без отдельной просьбы. Общаться по-русски. Рабочая папка: `C:\Users\jarom\Desktop\Dead_space_mobile`, PowerShell. Репозиторий: `IvaYar/dead-space-3ds-port`, private, main. Следующий сеанс должен продолжить разработку, а не повторять пройденные этапы.

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
2. `python porting/tools/build_gpu_gles.py`, `python porting/tests/smoke_gpu_gles.py`: настоящие игровые GLES bindings → GPU, PASS. Scissor, 2×2 RGBA, ALPHA texture blending;9 draws/18 triangles/2 uploads, CPU fragments=samples=0. Проверены реальные пиксели; картинки в `analysis/azahar-gpu-gles/`. Это fixture, не кадр игры.
3. `python porting/tools/build_gpu_engine.py`: engine_azahar.c с DS_PICA_BACKEND, TitleID000400000FDE6600, только CXI для эмулятора. Последняя сборка812247b906735d94f11f0e92a7d0dcab923d7a890f666db496c46c8e82b38aeb. Настоящие команды игры поступают в GPU, GL0; кадры8/60/180 пока ЧЁРНЫЕ. НЕ считать GPU-перенос законченным и не выдавать этот CXI за playable CIA.

### Ближайшее исправление

Вероятная причина чёрных игровых GPU текстур: переиспользование64KiB scratch до завершения DMA. В Citro3D `C3D_SyncTextureCopy` **внутри frame не ждёт**, а делает FrameSplit и добавляет GX_TextureCopy в очередь. Наш цикл upload сразу перезаписывает scratch следующей порцией; маленькая2×2 fixture помещается в одну порцию и проходит, реальные256×256/512×128 текстуры требуют4 порции и портятся. Это сильная гипотеза из прочитанного SDK, ещё не исправлена/не подтверждена повторным тестом.

Не считать `C3D_FrameSplit(C3D_FRAME_SYNCDRAW)` ожиданием: SYNCDRAW относится к FrameBegin, не к Split. Публичного GetQueue нет, GX_BindQueue возвращает void. Найти корректное управление временем жизни staging: например, полная ограниченная staging allocation, удерживаемая до завершения очереди; либо загрузка вне frame с настоящим ожиданием, без поломки порядка draw/clear. Аналогично проверить stream reuse в sync_gpu/drop: нынешний FrameSplit не гарантирует завершения чтения старых вершин GPU. Проверить clear ordering (C3D_RenderTargetClear напрямую GX_MemoryFill).

Диагностика локально: isolated SD `analysis/azahar-gpu-engine/Azahar/sdmc/3ds/deadspace/gpu-draw-trace.txt` и gpu-texture-trace.txt. Вывод texture trace показывает исходные ненулевые texels. Текущая последняя сборка включает ограниченный debug trace в ds34; убрать/сделать opt-in после исправления. Маленькую GPU fixture расширить текстурой больше64KiB, чтобы воспроизвести ошибку осмысленным тестом.

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

Пользователь хочет законченный порт, но честная текущая граница: видимая CPU вступительная сцена, рабочий небольшой GPU GLES тест, незаконченная интеграция GPU в игру. Аппаратных результатов после stage8 нет.
