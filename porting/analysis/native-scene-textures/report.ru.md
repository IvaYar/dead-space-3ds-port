# Texture working set оригинального пролога: устранён ранний лишний paging, поздняя сцена ещё не помещается

**Продолжение 02.11.2026:** [UV/Morton этап](../regional-texture-residency/report.ru.md) выбрал lossless backing вместо невыгодного rectangle cache, ускорил late callback в2,24× и достиг оригинального персонажа в Chapter I/MOVEMENT CONTROLS. Ниже сохранён предыдущий этап visible05.

02.11.2026. Только Azahar CPU100/OpenGL, CXI. **Айзек и управляемый gameplay не достигнуты. Thrashing устранён на начальном участке, но не во всём прологе.** [Числа и аудит](result.json), [проверяющий инструмент](../../tools/audit_scene_textures.py).

Рабочий normal build: `porting/3ds/build-native-game-v0.1.7-visible05/native-game.cxi`. `visible05home` — отдельная HOME fixture. Сборки, SD, captures и адресные traces остаются private. Новых CIA, аппаратных запусков, commit/push нет. Старый EA/headphone artifact отложен.

## Установленная причина 17 повторных загрузок

На исходном DS22→DS34 пути `ds34_begin_draw()` подготавливал samplers, CPU residency и GPU uploads **до** CPU clipping/culling. Нулевое число вышедших треугольников не отменяло уже выполненную загрузку. Поэтому даже полностью отсечённые draw calls загрязняли GPU LRU cache.

Новый baseline `thrash03:baseline` воспроизводит прежнюю проблему: каждый callback раннего устойчивого участка загружает **17 pages / 37 634 048 bytes**, создаёт 17 GPU textures и вытесняет 17 записей. Это 16 разных canonical pages общей ёмкостью **33 439 744 bytes**; один 4 MiB atlas загружается дважды. В callbacks нет новых `glTexImage2D` или `glTexSubImage2D`, а traced evictions имеют причину capacity/LRU, не dirty. Следовательно, это повторное создание GPU cache entries, а не пересоздание текстур самой игрой.

Из 34 исходных draw calls раннего участка получаются только 7–9 непустых GPU draws. После clipping/culling реально нужны три текстуры общей ёмкостью **4 718 592 bytes (4,5 MiB)**; весь сохранённый GPU cache на этом участке — **4 980 992 bytes (4,75 MiB)**, включая прежнюю неиспользуемую запись.

Причина установлена сочетанием исходного кода, новых RAM traces hit/miss/upload/eviction и отдельного теста полностью clipped/culled geometry. Пустые draws больше не выполняют uploads.

## Адресное исправление

Новый opt-in `--visible-textures` оставляет проверку GPU states в начале draw и переносит материализацию samplers/TEV/resources на первый треугольник, прошедший существующие DS22 clipping/culling. Пока синхронный draw выполняется, GL state и заимствованные sampler objects неизменны. Если треугольников нет, pending draw закрывается без uploads.

Ни CPU clipping, ни исходные callbacks игры не заменены. Dirty invalidation при TexSubImage, FBO, replacement/delete сохранён. `release_staging`, `sync_gpu`, `frame`, `ds34_present`, `ds34_native_finish` побайтно совпадают с frozen scene16 по телам функций; retire/delete по-прежнему использует прежний blocking GPU drain. **CPU budget 6 MiB / GPU budget 8 MiB / CACHE32 / linear100 MiB / arena85,5 MiB не менялись.**

Трассировка ограничена RAM buffer512 entries; повторные hit/видимые треугольники агрегируются по объекту. IO выполняется после возврата callback и вне измеряемого интервала callback. Переполнение не скрывается. Полные private traces содержат адреса, summary их не публикует.

## Измерения до/после

Основное сравнение: новый baseline `thrash03:baseline` и normal `visible05:detailed`, одинаковые CPU100/OpenGL, свежие writable SD, original HID pulses и instrumentation. Раннее устойчивое окно — callbacks4328…4338. Исторический scene16 (~14,48 s) остаётся отдельным сохранённым измерением.

| Показатель / callback | Baseline | Исправление |
|---|---:|---:|
| Median callback time | 14 428,521 ms | **451,247 ms** |
| Min…max callback time | 14 413,226…14 462,939 ms | 445,314…451,460 ms |
| Page loads | 17 | **0** |
| GPU allocations / evictions | 17 / 17 | **0 / 0** |
| GPU upload bytes | 37 634 048 | **0** |
| Page saves | 0 | 0 |

**31,975× быстрее, −96,873% времени callback.** Повтор `visible05:repeat`: median450,450 ms, те же нулевые steady uploads/page loads. Это emulator callback time, без present/capture/host IO, не hardware FPS.

Первый тяжёлый callback: **28 485,353 → 16 358,826 ms**; loads40→12, GPU allocations41→13, upload bytes62 619 904→34 472 192. Затем остаются два коротких этапа подготовки примерно1,60/2,13 s с1/2 loads; после них — устойчивые~0,45 s. Полная таблица каждого измеренного callback находится в `runs.*.callbacks` result.json.

Callback номера не являются доказательством одинакового игрового времени: original ACK в разных процессах бывает4322/4323, а ускорение меняет длительность реальных callbacks. Поэтому сравнение steady участка не объявляется побайтовым сравнением движущихся кадров по одному номеру.

## Дальнейшее продвижение и следующий барьер

После ускорения исполнение дошло до следующего явного reject: projective texture coordinates около callback4400. Добавлен opt-in `--projective-texture0`: sampler0 использует PICA `GPU_TEX_PROJECTION` и отдельный `texcoord0w`; shader сохраняет оригинальный q до деления на pixel. Для sampler1 поддержан только **постоянный положительный q внутри треугольника**: деление перед интерполяцией в этом случае математически эквивалентно. Для переменного q sampler1 по-прежнему fail closed. У sampler units отдельные живые descriptor copies, поэтому один texture object можно одновременно bind в обоих units с разными texture modes.

Проверено **15 CPU/PICA pixel comparisons**, включая patterned textures, постоянный/переменный q unit0, один texture object в двух units, постоянный q unit1, fog/COMBINE/blend/dirty/replacement. Maximum channel error≤2/255; полностью clipped/culled draws дают0 uploads/0 triangles. Отдельно подтверждён отказ unit1 с переменным q (`GL_INVALID_ENUM=1280`). Неподдержанный режим не аппроксимирован.

Продолжение original callbacks после этого показывает **вращающуюся космическую станцию/корабль, астероиды и титры Developed by IronMonkey Studios**. Normal `visible04:onward` дошёл до4437, `visible05:detailed` до4436: **114 completed callbacks после actual original ACK** в обоих случаях, затем cooperative exit по900 s guest budget. Это дальнейший original opening prologue. **Айзека нет. Открытие `isaac.m3g` / `01_gov_01.scene.sb` на достигнутом пути не доказано.** Изменения donor state вручную и замены сцены нет.

При приближении камеры к станции возникает уже **настоящий видимый working set**: в стабильных поздних callbacks4420…4436 участвуют **25 textures / 34 226 432 bytes (32,64 MiB)**. Cache8 MiB не может их удержать. Поздний callback выполняет **29 GPU allocations/evictions, 29 page loads**, читает **51 003 396 canonical bytes**, создаёт **51 003 648 GPU bytes** и занимает **~19,89 s**. Разница252 bytes связана с минимальным физическим GPU texture size8×8 у логической1×1 texture.

Это другая фаза сцены: сравнивать её19,89 s с ранним baseline14,43 s как регрессию того же кадра нельзя. Полное сценовое thrashing и переход до Айзека **остаются незавершёнными**.

Сохранён read-only capacity model реальной последовательности96 sampler requests позднего callback4430. Повторный LRU при8 MiB даёт29 misses/51 003 648 upload bytes, при10/12 MiB —28 misses/46 809 344 bytes. Это модель ёмкости без VRAM placement, pins и fragmentation, не allocator test. В runtime бюджеты не повышались. Даже такой рост не устраняет барьер.

Следующий адресный этап: измерить UV regions/tile reuse **видимых** станционных материалов и спроектировать bounded regional residency либо подходящее представление без потери исходных texels. Измерять общий lifetime/peak, clipping/filter/wrap seams и CRC до интеграции. Снова пропускать полноразмерные невидимые textures уже не требуется; простая перестановка LRU или длительный прогон при~20 s/callback не решают нехватку ёмкости. Отдельный будущий барьер — variable-q sampler1, если он встретится дальше.

## Память и сохранённые контракты

| Показатель normal visible05 | Наблюдение |
|---|---:|
| Normal live peak / allocator footprint peak | 17 397 376 / 19 881 984 bytes |
| Linear peak / reservation | 104 635 264 / 104 857 600 bytes |
| Минимальный запас по global linear peak | **222 336 bytes**, прежний |
| Linear free на раннем steady boundary | 8 610 944 bytes |
| Минимум linear free на наблюдаемых scene boundaries | 4 416 384 bytes |
| Kernel commit / limit | 126 861 312 / 130 023 424 bytes |
| VRAM peak | 4 192 768 bytes |
| Donor arena used / reserved | 89 505 792 / 89 653 248 bytes |

Глобальный peak включает startup transients. Boundary свободная память не разрешает слепо увеличивать cache, поскольку не отражает следующий staging peak. Новый commit на20 480 bytes выше прежнего scene16 — bounded RAM diagnostics; normal/linear reservations прежние. В окончательных visible05 detailed/repeat/HOME runtime allocation refusals0; ранний visible04 имел38 успешно восстановленных отказов, baseline29. Они сохранены в result и не объявлены нулём для всех запусков. Donor refusals/invalid frees/unmapped/failed submits/GL errors в пяти audited runs —0.

**17 ARM pager/FBO/audio contracts PASS.** Generated `ds10_jni.c`, `ds15_textures.c`, `ds22_draw.c`, `ds26_framebuffer.c`, SD page implementation, CRC header и HID headers побайтно равны frozen scene16. Порядок audio→jobs shutdown прежний; оригинальный mixer работает через timed emulator PCM sink, слышимого NDSP звука не добавлено.

Пять audited runs: baseline, два long normal, normal repeat со START и HOME fixture. **400 raw/RGB565 capture CRC проверены**, GX capture truncation0; **55 menu raw pairs побайтно равны loadclean**. Sticky FRAME FAIL / expected `ea733050` сохранены: `software_checks_passed` означает checks эксперимента, не golden-frame PASS игры. Движущиеся кадры пролога не имеют нового утверждённого golden CRC. Артефакт EA и прежний9231-pixel discrepancy не маскировались.

START на4410 и HOME перед4330 завершились с5 kernel joins,0 оставшихся handles, balanced IO, collector joined/freed, cleanup complete и safe_exit. Budget exits также безопасны. Late original callbacks продолжались с работающим mixer.

Loading gain сохранён: engine request→ready **275,60…276,49 s** в corrected normal runs, warm159,60…160,67 s; baseline этого опыта277,29/161,10 s. Warm во всех случаях **38 saves /166 loads**, прежний instrumented loading baseline315,73/199,93 s остаётся отдельным историческим результатом. Нового аппаратного ускорения не заявляется.

Проверены SHA **375 protected files**, **1752 master/store resources** и frozen scene16 manifest. Cleanup pilot по-прежнему STOP/rollback: исходные старые SD сохранены. Все новые cards подготовлены через `ensure_dataset/prepare_card` с двумя read-only junction и собственным writable state. Старые физические resource trees не восстанавливались и не мигрировались.

## Воспроизведение и сохранённые неуспешные опыты

Read-only recheck, без новой сборки или запуска игры:

```powershell
python porting/tools/audit_scene_textures.py
```

Новые сборки/запуски требуют свежих revision/attempt:

```powershell
python porting/tools/build_native_scene.py --revision NEWREV --callbacks 12000 --audio --scene-gpu --fog --pressure-evict --lazy-scene-residency --scene-seconds 900 --texture-trace --visible-textures --projective-texture0
python porting/tests/smoke_native_scene.py --revision NEWREV --attempt NEWATTEMPT --cpu 100 --opengl --pulse --sequence 3120:UP,3360:DOWN,3600:UP,3840:DOWN,4080:B,4320:A
```

Host deadline180 s остаётся прежним. До900 s guest budget процесс успел безопасно завершиться; увеличение длительности само по себе не предлагается как исправление позднего paging.

Сохранены failed preliminary trials: `thrash01` — compiler warning/error диагностического header; `thrash02:baseline` — слишком подробные hit records переполнили trace, процесс удержал ресурсы и не объявлен safe_exit; `visible01:first` — projective reject; `visible02` — shader output collision, CXI не получен; `visible03:onward` — unit1 projective reject. После исправления trace агрегации и exact projective paths итоговые normal/HOME/START runs прошли свои software safety checks. Старые evidence не перезаписывались.

**Оснований создавать новую аппаратную CIA нет:** поздний видимый working set превышает cache, performance недостаточна, Айзек/управляемый кадр не достигнуты. Hardware и push требуют отдельного разрешения пользователя.
