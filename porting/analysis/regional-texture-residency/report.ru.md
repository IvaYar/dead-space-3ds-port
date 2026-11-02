# UV residency: выбрана lossless Morton backing; оригинальный персонаж достигнут в Chapter I

02.11.2026. Только Azahar CPU100/OpenGL, CXI. **Игра сама прошла opening prologue и показала оригинального персонажа в RIG в коридоре Chapter I — Honorable Intentions. Управление персонажем пока не подтверждено.** [Кадр4951](../azahar-native-menu-v0.1.7-morton05-long2/screen-4951.png), [числа и аудит](result.json).

Поздний callback ускорен **19,935→8,889 s, 2,243×**. Canonical paging устранён на проверенном steady участке, но **полные GPU cache misses/uploads ещё остаются**. Бюджеты CPU6/GPU8 MiB/CACHE32, normal20/linear100/arena85,5 MiB прежние. Сцену, timestep, original callbacks, UV, shader, texels и правила sampling не заменяли. CIA, аппаратных испытаний, commit/push нет.

## Дополнение: выборочный гибрид, read-only оценка рекомендаций

После рекомендаций по сочетанию Morton backing и regional residency отдельно проверен **выборочный** вариант; прежняя модель rectangle для всех draws не считалась его опровержением. [Host model](../../tools/model_hybrid_regions.py), [результаты](hybrid-4430.json). Новых сборок/эмулятора/runtime изменений нет.

На сохранённом callback4430 перебраны все1024 подмножества10 подходящих textures для каждого origin quantum1/8/16/32/64 —5120 вариантов. Остальные textures сохраняются целиком. Budget8 MiB/CACHE32, pin обоих samplers,4 повторения того же callback; проверена сходимость последнего цикла. IO считается по реальным compressed lengths текущих Morton blocks, а не пропорционально площади UV.

| Политика | GPU misses | Compressed reads /callback |
|---|---:|---:|
| Текущие полные textures | 29 | 18 405 917 bytes |
| Лучшее чтение без увеличения misses | **29** | **16 973 245 bytes (−7,8%)** |
| Минимум чтения среди всех вариантов | **38** | **15 429 589 bytes (−16,2%)** |

**Ни один вариант не уменьшил число GPU misses ниже29.** Минимум GPU population при quantum1 даёт47 misses/29 155 584bytes вместо29/51 003 648; уменьшение объёма uploads само по себе скрывает рост числа операций. Модель оптимистична: одинаковый callback повторяется, не учтены moving UV, дополнительные seek/open/CRC, извлечение регионов, allocator fragmentation и GPU drain. Предполагается region-level pinning; существующий object-level pinning потребовал бы отдельной проверки.

Независимость LZ4 blocks уже реализована, но **partial-read API и offset index отсутствуют**: loader последовательно декодирует весь image и проверяет full decoded CRC. В1024×1024 RGBA8 image каждый256-KiB block охватывает **1024×64 texels**, поскольку native Morton layout использует8×8 tiles, расположенные строками. Уменьшение региона по X поэтому часто не уменьшает число читаемых blocks. Прямой view узкого rectangle также не подходит из-за другого tile-row stride.

Для полноценного partial loading нужны проверенный index compressed offsets, decoded CRC каждого независимо опубликованного блока (сейчас есть encoded CRC блока и decoded CRC целого image), bounded decode/extraction scratch и доказательство sampling/lifetime. Нельзя просто пропустить full CRC при чтении subset: coherent payload+encoded-CRC corruption сейчас ловится full decoded CRC.

**Решение: региональный runtime не внедрять по этим данным.** Сохранять проверенный lossless full-image path. Действительно полезная новая гипотеза — выборочные стабильные regions с учётом реальной block geometry, либо независимо индексируемые двухмерные tile groups, но только после существенно лучшей модели. Это ещё не измеренное ускорение и не основание менять backend/кэши. Возвращать64-KiB chunks вслепую также не следует: этот вариант уже дал~11 s против~8,89 s текущего пути.

Повторная проверка только модели: `python porting/tools/model_hybrid_regions.py`. Original-character milestone до5106, tests, memory и safe_exit ниже остаются прежними.

## Исследование UV и выбор решения

Новая opt-in `--uv-trace` собирает нормализованные UV уже прошедших существующие clipping/culling треугольников, отдельно по draw/unit. Вызов не выделяет память и не пишет на SD; bounded RAM384 records сохраняется после callback. Основной диагностический диапазон4386…4500; geometry не меняется.

Контроль `regionuv01:baseline` воспроизвёл late working set25 textures/32,64 MiB и29 allocations/loads. На callback4430 сохранены UV footprints реальных visible draws. Многие материалы используют почти весь1024×1024 atlas, разные его части или repeat за пределами0…1. Целый atlas нужен нескольким draws с различными UV bounds.

Проверена read-only модель одного power-of-two rectangle на draw с halo1 texel для linear filtering, сохранением repeat/clamp и origin quantum1/16/32/64 texels. Даже по **уже отсечённой геометрии**, то есть оптимистичнее pre-draw оценки, получаются примерно **37,4…40,5 MB /61…63 keys**. При прежних8 MiB/CACHE32 модель даёт61…63 misses. Это не выигрыш по числу загрузок и заметно превышает ёмкость cache. Точные варианты/число draw units находятся в `uv_analysis` result.json.

Это модель, не выпущенная реализация cropping. Разбиение треугольников по tiles потребовало бы нового clipping на projective UV, согласования двух samplers и доказательства отсутствия filtering/raster seams. Такой риск без подтверждённого выигрыша не принят. **Regional cropping не включён; исходные границы примитивов и texture sampling сохранены.**

Выбрана ограниченная альтернатива: сохранять уже построенный **полный Morton RGBA8 image** после первого canonical upload и повторно загружать его без полного canonical reload и повторной Morton-конвертации. Для сокращения SD reads используется [LZ4 v1.10.0](https://github.com/lz4/lz4/tree/v1.10.0/lib), без потерь; source/headers/BSD2-Clause LICENSE и SHA находятся в `3ds/vendor/lz4-v1.10.0`. Остальная часть GPU backend сохраняется.

## Реализация и lifetime

- GPU LRU остаётся32 entries/8 MiB. Отдельные128 metadata keys ограничивают disposable disk snapshots; это не дополнительный pixel cache в RAM. Ключ содержит DS15 object, physical dimensions и wrap для padded axes.
- При первом miss читаются проверенные canonical pixels, применяется прежнее Morton/ABGR-преобразование и сохраняется сжатый образ. Последующие misses используют его; CPU/FBO продолжает работать с canonical DS15.
- Новая texture создаётся в linear memory через стандартный `C3D_TexInit`. Она заполняется **до bind/publication**, полностью проверяется и публикуется через checked `GSPGPU_FlushDataCache`. После публикации данные неизменны до прежнего `drop()` с blocking drain. Нет CPU записи в VRAM и нет освобождения живого staging.
- `release_staging`, `sync_gpu`, `frame`, `scene_materialize_draw`, `ds34_present`, `ds34_native_finish` совпадают с visible05 по телам функций; shader и DS22 clipping/packing побайтно прежние. Существующие checks blend/fog/COMBINE/unsupported states сохранены.
- TexSubImage, image replacement/delete и FBO dirty удаляют соответствующие GPU entries **и derived backing**. LRU eviction удаляет только GPU copy; bounded disk metadata может пережить его. Старый donor object не используется после original lifetime callback.

Store format2 содержит magic/version/raw size/decoded CRC/block size, затем bounded LZ4 blocks по256 KiB с точными raw/encoded lengths и encoded CRC. Проверяются header, размеры, `LZ4_decompress_safe`, полный decoded CRC, EOF, read/close errors. Ошибка не становится cache hit и не даёт опубликованную texture. После полного закрытия нового файла metadata заменяется атомарно на render thread; shared assets не затрагиваются.

Scratch для codec+CRC **282 676 bytes**, плюс bounded metadata/diagnostics. Нормальный и linear reservations не расширялись. Нет отдельных staging buffers для новых linear images; они сразу заполняются в собственное GPU-visible storage. Этот lifetime проверен реальным GPU reload.

CRC32 store ускорена slicing-by4 с тем же IEEE результатом. Это новый компонент: исходные `ds_crc32`, canonical page implementation и `native_menu_page_crc.h` не менялись. На ARM проверены73 vectors против прежней bytewise реализации, включая offsets0…7 и4 MiB; known vector`123456789` даёт`cbf43926`. Уменьшения проверяемых данных нет.

## Производительность

Одинаковое steady окно4420…4435, CPU100/OpenGL, свежие SD, original pulses. Физические upload/population bytes учитываются даже при прямом заполнении linear texture; их нельзя объявлять нулём из-за отсутствия отдельного TextureCopy.

| За callback, median | UV baseline | Morton final repeat |
|---|---:|---:|
| Callback | 19 935,467 ms | **8 889,340 ms** |
| Canonical page loads | 29 | **0** |
| Compressed Morton loads | 0 | **29** |
| GPU allocations / evictions | 29 /29 | **29 /29** |
| GPU image population | 51 003 648 bytes | **51 003 648 bytes** |
| SD payload/header reads | 51 003 396 canonical bytes | **18 405 917 compressed bytes** |

**2,243× быстрее; callback time уменьшен примерно на55,4%, чтение — на63,9%. GPU thrashing целиком не устранён.** Повтор и длинный run подтверждают тот же steady режим. Все measured callbacks и отдельные read/decode/CRC timings сохранены в result.json.

Предварительные варианты сохранены:64 KiB blocks давали~11,01 s, отдельная сборка codec-O3 практически не изменила это (~10,96 s);256 KiB blocks дали~9,59 s, exact slicing CRC —~8,89 s. После этого эксперименты с codec прекращены. Более крупный scratch учтён в kernel commit и memory checks.

Ранний участок: **~449 ms/callback**, zero steady page loads/allocations/uploads. Прежнее ускорение около32× против исходных14,43 s сохраняется.

В первом коридоре Chapter I измерены~**5,61 s/callback**,14 GPU allocations/evictions,0 canonical loads,14 Morton loads/~12,59 MB reads и34,55 MB populated GPU bytes. Это другая сцена; её ускорение относительно старого backend не заявляется, поскольку старый контроль туда не дошёл.

## Реальное продвижение

`morton05:long2` выполнил original callbacks до **4951**, **628 после ACK4323**, и завершился на main boundary по3600 s guest budget: elapsed3600820 ms. Host326 s, независимый deadline600 s. Камера прошла наружные конструкции станции; затем игра сама перешла в коридор с original Chapter I title, pause icon и персонажем в RIG. На4927 открыт original VO `sounds/sfx/vo/vandal/DS2_01.sps`.

Это визуальное достижение первого оригинального персонажа — цели этапа «до Айзека». **Конкретное имя/identity model `isaac.m3g` не устанавливалось по выдуманным названиям классов или отсутствующим opens**: ресурс мог быть предзагружен. Появление персонажа подтверждено изображением, не одним аудиопутём. Игровая сцена и position не задавались вручную; original game clock не ускорялся искусственным timestep.

Дополнительный `morton06:chapter` с тем же renderer/codec дошёл до **5106 /784 callbacks после ACK4322**, включая около180 callbacks первого коридора и оригинальное обучение MOVEMENT CONTROLS. Выход по4500 s guest budget, host394,109 s, GL0/refusals0/failed submits0 и **safe_exit**. [Кадр5106](../azahar-native-menu-v0.1.7-morton06-chapter/screen-5106.png). Прежние builds сохранены. Текущий normal candidate — `porting/3ds/build-native-game-v0.1.7-morton06/native-game.cxi`; `morton05home` остаётся отдельной fixture.

**Управляемый gameplay пока не подтверждён.** Существующий HID adapter передаёт A/UP/DOWN только при подтверждённом `LayerDifficulty.ready`; после перехода в Chapter I этот guard больше не открывает menu pointer events. Дальнейшая задача — исследовать original gameplay pointer/input contract и подключить движение/камеру через него. Также остаются низкая производительность, повторные GPU uploads и отсутствие audible NDSP backend.

## Корректность и проверки

Итоговая `scene-gpu-test-morton05fbo2`:

- **16 CPU/PICA comparisons PASS**, max channel error2/255. Есть fog/COMBINE/blend, clipped/culled0uploads, patterned projective UV, shared object в двух units, TexSubImage/replacement.
- **FBO clear→sample после принудительного GPU eviction** даёт CPU/GPU byte-exact pixels: stale derived backing не используется.
- Кадры до и после принудительного eviction/reload побайтно одинаковы; DS34 sequence audit проходит.
- **21 store checks PASS**, включая incompressible/compressible4 MiB roundtrips и block boundary262145 bytes; **14 повреждений/ошибок отклонены**: header/length/payload, согласованный encoded CRC при изменённых decoded texels, truncation, trailing byte, wrong size, missing file.
- **73 exact CRC vectors PASS** против старой bytewise CRC.

Независимый host decoder читает LZ4 blocks, проверяет их через host zlib, затем NumPy строит Morton ABGR из сохранённых canonical DS15 pages. На позднем station repeat **25/25 textures, все34 226 432 bytes побайтно совпали**. В первом Chapter I run независимо декодированы27 snapshots/38 437 120 bytes; для26 есть canonical backing для bytewise comparison, один canonical image остался resident. Это ограничение доказательства указано, а не подменено успехом всех27 сравнений.

**855 raw captures восьми successful runs** независимо проверены raw CRC и RGB565 CRC, GX truncation отсутствует. **85 menu pairs побайтно совпали с frozen loadclean.** У HOME fixture8 совпавших menu pairs; ранние3120/3240/3360 **не совпали**, их CRC не скрыты и baseline не заменён. Сохраняется прежний минимум8 comparisons из старого auditor; все capture CRC проверяются независимо. Эти три кадра не объявлены доказанно равными или исправленными.

Sticky FRAME FAIL / expected`ea733050` и прежний EA/headphone artifact сохранены; moving prologue не получил искусственный golden CRC. `software_checks_passed` относится к checks этапа, а не к прохождению старого intro oracle.

## Память, shutdown и сохранение проекта

У `morton05:repeat/long2`: normal live/footprint peaks **17 397 376 /19 881 984 bytes**; global linear peak **104 635 264 /104 857 600**, прежний запас **222 336 bytes**. Kernel commit **127 193 088 /130 023 424**; donor arena **89 505 792 /89 653 248**; VRAM peak **4 192 768 bytes**. Минимум linear free на наблюдаемых scene boundaries~4,42 MB. Эти boundary samples не заменяют transient peak.

Commit вырос примерно на324 KiB относительно visible05 из-за bounded codec/CRC/UV scratch и кода. Это не рост cache budgets. Во всех audited successful runs проверяются memory limits; normal candidate не допускает публикации texture после failed load/flush. Donor/runtime refusals и invalid accesses сохранены в численных summary, а не исключены из подсчёта.

START на4440 и HOME перед4440 проверены с активным Morton store и mixer. Длинное продолжение до Chapter I также завершилось cooperative shutdown:5 kernel joins,0 remaining handles, balanced IO, collector joined/freed, cleanup complete/safe_exit. Audio остановлен/joined до jobs; NDSP звук не добавлен. DS10/DS15/DS22/DS26/SD page CRC/HID headers побайтно visible05; loading warm38 saves/166 loads и прежний loading gain сохранены.

Проверяются SHA375 protected files,1752 master/store resources и source/manifest LZ4. Старые games/builds/SD/resources не перезаписывались. Новые cards используют shared-resource-store junction; canonical и Morton pages — собственные writable outputs. Cleanup STOP/rollback остаётся действующим. Для исторического projective06 fixture сохранён exact pre-Morton probe source по его прежнему SHA в `.local/source-snapshots/<SHA>/`; старый аудит проверяет этот snapshot, не заменяет ожидаемый digest текущим исходником.

## Harness и сохранённые неуспешные пробы

Первый длинный `morton05:long` **не прошёл safety**: старый host-frame cap150000 закончился внутри callback4774 раньше guest budget3600 s. Это не successful shutdown. Runner исправлен на независимый host deadline без конфликтующего cap; `long2` до4951 завершился безопасно. Deadline default180 s сохранён, для длинных проверок явно задан600 s.

Первая HOME attempt стартовала до завершения build и отказала до запуска игры; свежая `home2` прошла. Первая FBO fixture не подключила15 explicit FBO bindings и вызвала NULL function pointer; это test harness FAIL. Исправленная `fbo2` прошла. Failed directories сохранены отдельно; они не включены в successful checks.

## Повторная проверка

Read-only audit сохранённого evidence, без новой игры/сборки:

```powershell
python porting/tools/audit_regional_textures.py
```

Новые revision/attempt обязательны:

```powershell
python porting/tools/build_native_scene.py --revision NEWREV --callbacks 12000 --audio --scene-gpu --fog --pressure-evict --lazy-scene-residency --scene-seconds 4500 --texture-trace --visible-textures --projective-texture0 --uv-trace --morton-backing --fast-morton-codec
python porting/tests/smoke_native_scene.py --revision NEWREV --attempt NEWATTEMPT --cpu 100 --opengl --pulse --sequence 3120:UP,3360:DOWN,3600:UP,3840:DOWN,4080:B,4320:A --deadline 600
```

**Новую CIA не создавали. Аппаратные проверки и push требуют отдельного разрешения.** Следующий этап может начинаться с уже достигнутого original Chapter I и исследования gameplay input; повторять доказанный невыгодный whole-draw rectangle cache и завершённое исследование первых17 invisible uploads не требуется.
