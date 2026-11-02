# Оригинальная сцена после сложности: audio Init, fog/COMBINE и первый prologue

**Новейшее продолжение 02.11.2026:** [UV/Morton этап](../regional-texture-residency/report.ru.md) дошёл до оригинального персонажа и обучения движению в Chapter I; current normal `morton06`, управление пока не подтверждено. Исторические результаты ниже сохранены.

**Продолжение 02.11.2026:** [отдельный этап texture working set](../native-scene-textures/report.ru.md) устранил ранние17 повторных uploads (14,429→0,451 s/callback), продвинул original prologue до вращающейся станции и установил новый поздний видимый working set32,64 MiB. До Айзека пока не дошли. Текущий normal CXI — `visible05`; приведённые ниже scene14/16 результаты сохранены как предыдущий этап.

После настоящего original A в Azahar получены **оригинальная вступительная сцена, планета, астероиды и титры IronMonkey**. **Айзек и управляемый gameplay пока не достигнуты.** Прежние audio NULL reads воспроизведены и отсутствуют в итоговом пути с original audio Init. Fog и необходимые texture COMBINE states работают через существующий DS34/PICA backend. Ограничение двумя callbacks снято; вместо него действуют программные временные бюджеты и остановка на возврате main callback. CIA, аппаратных испытаний, commit и push нет.

[Численные результаты и воспроизводимый аудит](result.json). Пример настоящего кадра: [scene16, callback 4339](../azahar-native-menu-v0.1.7-scene16-repeat/screen-4339.png); более поздний титр в отдельном длинном опыте: [scene10, callback 4399](../azahar-native-menu-v0.1.7-scene10-pressure/screen-4399.png). Это framebuffer оригинальной игры, не тестовая сцена. Синтетический fixture ниже используется только для отдельной проверки GPU-математики.

## Audio: что было пропущено

Контроль `scene04:combine` повторил два прежних чтения: Read8 по `0x3c` и Read32 по `0x30`, donor-relative `265f80/265f98`. До COMBINE-поддержки более ранний `scene01:confirmed` останавливался на новом GPU reject `0x8570` и до этих чтений не дошёл. Контроль `scene01:faults` оказался прогоном без A: слишком близко поставленные schedule points схлопнулись из-за публикации guest state раз в 120 callbacks; он не считается воспроизведением ошибки.

Разобраны original DEX и ARM. `EAMAudioCoreWrapper.NativeStartup` в данном donor — пустой экспорт. Java отдельно выполняет `AndroidEAAudioCore.Startup`, создаёт AudioTrack и вызывает native:

```text
Init(AudioTrack, bufferFrames, channels, sampleRate)
write(short[], sampleOffset, sampleCount) -> число samples
```

В исследовательском адаптере используются **1024 buffer frames, stereo, 22050 Hz, signed PCM16**. Это допустимые параметры выбранного emulator sink, не измеренный Android `getMinBufferSize` и не будущая конфигурация аппаратного звука. Original Init вызывается после JNI_OnLoad, перед NativeOnCreate. Он получает настоящий объект compatibility JNI, сохраняет JavaVM/AudioTrack globals, методы play/stop/write и short array. Включён оригинальный mixer; PCM потребляется с ограниченной задержкой по частоте. **Слышимого NDSP/backend ещё нет.** Синхронный PCM dump не создаётся.

В generated DS10 добавлены typed short arrays, границы и sample units, корректные varargs для `write`, VM `DetachCurrentThread`. Сам адаптер не выделяет Java TLS, audio worker пользуется retained globals. Это узкий native JNI adapter, не реализация всей Java VM. Неподдержанные методы остаются fail closed.

Первый `scene02:audio` выявил ошибку разбора varargs и NULL VM detach; процесс остановлен с host после сохранения диагностики, гостевые ресурсы не освобождались насильно. `scene05:audiofixed` устранил varargs, но ещё имел NULL detach и завершился host deadline 180 s. Они остаются FAIL. Не выдавать отсутствие старых двух NULL в этих попытках за safety PASS.

Активный mixer выявил зависимость shutdown: **audio нужно остановить, пока job workers ещё обслуживают его задания**. Прежняя последовательность jobs→audio оставляла Submit worker на semaphore. `scene07:fog` сохранил этот отказ без опасного освобождения. Итоговая последовательность: original loader drain → Pause/Stop → audio flag/wake/interrupt/kernel join → jobs join → periodic join → original Audio Release → JNI/IO cleanup → GPU drain/Fini. Original destructor с освобождением буферов до wake не вызывается. Новые нормальные прогоны и HOME fixture подтверждают завершение всех пяти workers, ноль handles и balanced IO.

## Fog и GPU scene states

Старый backend, clipping/lighting, uploads, streaming, synchronization, CPU FBO и форматы framebuffer сохранены. В generated копии добавлены:

- GLES COMBINE → PICA TEV, включая проверенные MODULATE/INTERPOLATE; `GL_PREVIOUS` на unit0 означает PRIMARY_COLOR. Первый численный fixture обнаружил ошибку этого отображения; она исправлена до итоговых runs.
- Fog использует прежний `ds30_factor` в eye space и прежнее clipping/interpolation. Фактор передаётся в свободных z-компонентах существующего vertex layout в texcoord2; отдельная постоянная 8×8 ramp занимает 256 bytes VRAM. TEV смешивает RGB после двух игровых текстур, alpha проходит неизменённой. Нового большого vertex/staging buffer нет.
- Неподдержанные stencil/offset/прочие GPU states не игнорируются: reject сохраняет GL error и останавливает опыт после возврата callback. Утверждать поддержку всех GPU states нельзя.

Отдельный `scene-gpu-test-f5`: **8 сравнений реальных CPU/PICA pixels PASS**, maximum channel error **1/255**; control exact, fog, textured fog, alpha blend, COMBINE, TexSubImage и replacement. Fixture также включает deferred residency. Первые f2 captures оказались некорректными при прямом fwrite из незавершённого readback; fixture получил ожидание VBlank и копию после invalidate. Старые FAIL сохранены; runtime ради них не менялся. Основной game readback по-прежнему использует прежние drain/CRC checks.

## Память и причина остановки

Без адресного pager fallback `scene08:memory` остановился с `GL_OUT_OF_MEMORY` после запроса **1048592 bytes** в normal heap. Уменьшение CPU residency до 5 MiB (`scene09:trim`) не помогло: затем не разместилась страница **4194320 bytes**. Наличие суммарно свободных байтов не гарантировало подходящий contiguous block.

В generated DS15 отказ allocation теперь позволяет вытеснить дополнительные **незакреплённые LRU pages**, сохранив точный backing и старое содержимое, и повторить allocation. Save failure/пины/старый level остаются под прежними ограничениями. Это ограниченный обход конечного набора pages; бюджет памяти не расширяется. Проверка с принудительным отказом malloc подтверждает сохранность трёх страниц и отсутствие GL error после успешного восстановления.

В итоговых runs остаются **32 / 14 allocator refusals, включая успешные retries**; HOME fixture — 5. Это реальные отказы allocator, а не ноль failures. Donor refusals, invalid frees, unmapped reads/writes, GL errors и failed submits — **0** в итоговых runs. Runtime failures в ранних опытах не скрыты.

После A отдельно проверено deferred CPU residency для default GPU draws: на cache hit канонические pixels не читаются; на miss DS34 получает residency перед конвертацией/upload. CPU/FBO и main menu до A используют прежний порядок. Все texture/FBO dirty paths сохранены. Эта правка **не устранила scene thrashing**: последующие callbacks всё ещё выполняют около **17 texture allocations + 17 page loads**, часто заново создавая GPU atlas. GPU cache budget остаётся 8 MiB, CPU budget 6 MiB. Увеличивать их за счёт почти полного linear heap нельзя.

| Наблюдаемый максимум | Итоговые runs |
|---|---:|
| Normal live / allocator footprint | 17397376 / 19881984 bytes |
| Normal reservation | 20971520 bytes |
| Linear used / reservation | 104635264 / 104857600 bytes |
| Linear headroom | **222336 bytes** |
| Kernel commit / Prod124 limit | 126840832 / 130023424 bytes |
| VRAM used | 4192768 bytes |
| Donor brk peak + mmap | 67112960 + 5467×4096 bytes |
| Donor arena used / reserved | 89505792 / 89653248 bytes |

Это наблюдения allocator wrappers и boundary samples, не доказательство отсутствия всех внутренних libc transients. Commit на 12288 bytes больше loading-profile build; ни normal/linear reservation, ни arena не увеличивались. Код/arena сохраняются до kernel process teardown после остановки workers/GPU, как раньше.

## Достигнутый state и производительность

Подтверждён переход из modal LayerDifficulty в **original opening prologue**. Difficulty modal перестаёт находиться по проверенному vtable; у app+c4/d0 наблюдается vtable donor `435858`, у c0/cc — `427e60`. Это точные наблюдения объектов; им не присвоены недоказанные названия C++ классов.

Original audio открыл `AMB_FAN_DRONE_01.sps`, `PrologueCinematic_FullVO_v2.sps`, `10_Entering_Zero-G.sps` и UI confirm sound. Файлы присутствуют и открылись успешно. Эти paths подтверждают prologue, **не загрузку первой управляемой главы**. `isaac.m3g` и `01_gov_01.scene.sb` есть в master resources, но их фактическая загрузка на достигнутом этапе не доказана. Часть игровых данных могла быть предзагружена до A; отсутствие нового open не доказывает отсутствие ресурса в памяти.

Итоговые нормальные runs: **4341 / 4339 completed callbacks**, соответственно 18 / 16 после original ACK4323. Оба завершились по **240 s guest scene budget** на main boundary; host elapsed 62,047 / 60,813 s. В первом run строка reason ошибочно содержала literal «120s», хотя compile parameter был 240; во втором label исправлен, записано `limit_ms=240000 elapsed_ms=243865`. Deadline проверяется после callback и потому может быть превышен на длительность одного callback. Независимый host deadline 180 s ограничивает зависание в невозвращающемся callback.

Отдельный ранний `scene10:pressure` дошёл до 4399 и завершился через START; его параметры/меньшая плотность captures отличаются, поэтому он не сравнивается как benchmark. HOME fixture `scene15home:home` остановился перед callback4330, когда исходная сцена и mixer уже работали; handover выполнен после quiescence.

Тяжёлая первая подготовка сцены: около **28,64 s/callback**. Затем **14,45–14,50 s/callback**, то есть потолок около **0,069 FPS ещё без present/diagnostics**. В repeat callback4339: DS34 begin draw 14,022 s, residency 8,473 s, page loads17, page saves0; эти интервалы вложены. Stable menu — около 45,1–45,7 FPS в Azahar CPU100/OpenGL с диагностикой. Ни одна цифра не является новым hardware измерением.

**Следующий барьер — scene texture working set / GPU cache eviction и стоимость upload/residency при имеющемся linear budget.** Продлевать сцену на тысячи таких callbacks сейчас бессмысленно: после двух контролируемых повторов подтверждена та же причина остановки. Следующий этап должен адресно исследовать этот working set, затем продолжить prologue до реального персонажа. Никакой ручной замены сцены или искусственного выбора игрового state нет; управление вне проверенного original menu не добавлялось.

## Сохранение loading и остальных контрактов

Новый [builder](../../tools/build_native_scene.py) явно импортирует **оба** `texture_source` / `framebuffer_source` из `build_native_loading.py`, проверяет их до дополнительных transforms и сохраняет clean backing при последующих pressure evictions. Старый HID builder по-прежнему не используется как источник якобы включённой оптимизации.

Время engine request → menu ready **278,027 / 277,575 s**, HOME fixture 278,612 s. Warm callback **161,567 / 161,601 s**, HOME 162,548 s. Прежний instrumented baseline — 315,733 / 199,932 s. **Сохранён примерно −12% total gain**: warm saves38/loads166 вместо201/166, строгая page CRC32 и DS27 побайтно прежние. CPU cache до A — 6 MiB. Не заявлять hardware acceleration.

Аудит итоговых трёх runs: **154 captures** независимо проверены по raw CRC и RGB565 CRC, GX traces без truncation; **33 полных пары menu frames** побайтно равны frozen loadclean (11×3). HID queue/collector/original nav/A ACK, sticky FRAME FAIL/`ea733050`, safe_exit, START и HOME сохранены. Старый EA/headphone artifact и 9231-pixel discrepancy не исследовались и не исправлялись.

**17 ARM contracts PASS**, **8 GPU comparisons PASS**. SHA совпадают для **375 защищённых файлов** и **1752 master/store resources**. Старые builds, SD, hardware evidence и CIA не менялись; неуспешные preliminary trials сохранены отдельно. Сырые dumps/stack snapshots/APK/.so/assets/сборки остаются private, в выбранные summaries не включаются.

Перепроверка сохранённого evidence без новой сборки/эмулятора:

```powershell
python porting/tools/audit_native_scene.py
```

Новые попытки требуют свежих revision/attempt. Пример параметров последнего normal CXI:

```powershell
python porting/tools/build_native_scene.py --revision NEWREV --callbacks 12000 --audio --scene-gpu --fog --pressure-evict --lazy-scene-residency --scene-seconds 240
python porting/tests/smoke_native_scene.py --revision NEWREV --attempt NEWATTEMPT --cpu 100 --opengl --pulse --sequence 3120:UP,3360:DOWN,3600:UP,3840:DOWN,4080:B,4320:A
```

**Оснований готовить аппаратную экспериментальную CIA пока нет.** Есть воспроизводимый оригинальный prologue и устранение первых blockers, но нет Айзека/управления, приемлемой scene performance или запаса linear memory. Новые hardware trials и push требуют отдельного разрешения.
