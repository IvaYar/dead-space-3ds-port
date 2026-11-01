# Оригинальный native-frame в Prod124 — 31.10.2026

Ветка **feat/native-game-prod124**, исходная база5737b62. Исследования Dev1/GX/PICA не повторялись. По актуальным аппаратным материалам DS34 UV-mask и startup Legacy/Prod124 прошли, Dev1178 не дал наблюдаемого READY. Недостижение main у178 не доказано напрямую отсутствующими логами; внутренний startup отказ остаётся неизвестным.

**Результат текущей работы: оригинальный кадр и safe_exit в реальном app limit124MiB прошли в Azahar.** Подготовлена отдельная CIA после программных gate. Аппаратный game result ещё неизвестен; push и изменения приставки/Luma не выполнялись.

## Области памяти и действительный расход

Начальная конфигурацияh2 коммитила40+132=172MiB до main, независимо от фактической заполненности. Mem1 из предыдущей сессии измерял состояние на границах callbacks. Чтобы не пропустить transient staging, в **отдельную копию** добавлены wrappers внешних malloc/calloc/realloc/memalign/free, linear и VRAM API. Они передают прежние аргументы, возвращают исходные results и не меняют owners/lifetime. Пиковые значения снимаются сразу после allocation/перед free.

Вызовы libc, полностью разрешённые внутри её собственного object, могут обходить wrappers: это не доказательство абсолютного object-live peak. Глубина фактического использования стеков тоже не измерялась. При этом **полный process commit включает зарезервированные heaps/стеки/код**, измеряется отдельно и задаёт проверенную верхнюю потребность приложения для этого запуска.

Финальные измерения трёх циклов actual CIA payload:

| Область | Зарезервировано / наблюдаемый максимум | Важные границы |
|---|---|---|
| Port executable | text356352,RO57344,page-rounded data+BSS106496bytes | Всего520192bytes code/data commit |
| Port BSS | 97368bytes, внутри предыдущей строки | Не добавлять повторно |
| Main stack | 262144bytes | Отдельно от normal heap |
| Normal heap | **20MiB**; observed live≈**12,504MiB**, footprint≈12,785MiB | Сюда уже входят donor image/file/runtime/worker stacks |
| Linear heap | **100MiB**; observed allocated peak≈**95,038MiB** |92MiB donor+до3,038MiB остального |
| Donor arena | **92MiB** непрерывного linear block | DS9 sbrk high-water **16781312bytes=16MiB+4KiB**, mmap peak0 |
| SDK/GPU linear budget | **8MiB**; observed transient peak **3185536bytes≈3,038MiB** | Включает display buffers/command buffer/vertex stream/staging |
| GPU VRAM | observed peak1816832bytes≈**1,733MiB** | Отдельная VRAM6MiB, не часть FCRAM app124 |
| Donor file |4499468bytes≈4,291MiB normal | Retained исходный ELF, внутри normal20 |
| Donor prepared image |4792320bytes≈4,570MiB normal | Page-aligned contiguous VA; RX/RW отдельно |
| Donor BSS |301068bytes | Внутри prepared image, не добавлять повторно |
| Trampolines |12288bytes normal |3page-aligned RX pages |
| Six donor stacks |4×256KiB+2×32KiB=**1114112bytes** |1,0625MiB — уже внутри normal20; не сокращались |
| Runtime custom allocations | peak2457779bytes≈2,344MiB | Подмножество normal, не отдельная arena |
| Временный RGB565 compare |192000bytes normal | Наблюдение результата; не генерация кадра |
| Временный font load |47036bytes normal | Освобождён после проверки; не встроен в CIA |

Donor PT_LOAD: RX file/memory4336060bytes, RW file147096/memory448164/BSS301068bytes. Image4792320 включает выравнивание/gap. Для кода требуется непрерывность виртуального образа и page alignment, а не отдельный большой физически contiguous RX блок. Для donor sbrk требуется contiguous VA/backing: сохранён один `linearMemAlign` block, он физически contiguous по тому же SDK-контракту.

Крупнейший normal request4792320bytes — prepared image. Крупнейший внешний linear request кроме donor576000bytes. Vertex stream8190×64=524160bytes; C3D command buffer0x40000bytes, размеры framebuffer/texture/staging backend не менялись. Wrappers обнаружили transient linear3,038MiB вместо прежних post-callback≈2,288MiB — на этом основан новый запас, а не предположение, что4MiB всегда достаточно.

**Пиковый process commit =126611456bytes=120,74609375MiB**. Лимит130023424bytes=124MiB. **Свободно по commit3411968bytes=3,25390625MiB**. Все memory queries успешны, refusals/runtime failures0. Это снижение на52MiB относительно h2; оно вызвано изменением резервов, не фиктивным пересчётом «занятости».

Непересекающаяся сумма allocator/backing maxima — около32–33MiB FCRAM, плюс отдельная VRAM. Она меньше полного commit из-за большого запаса donor arena и свободных частей heaps. Это не одновременно живые объекты, не минимальный требуемый budget и не peak всего геймплея. [Точные числа и ограничения](memory-report.json).

## Как выбран бюджет

Normal capacity = round-up-to4MiB(observed allocator footprint + largest normal request +1MiB) = **20MiB**. SDK/GPU linear allowance = round-up-to4MiB(observed transient other-linear peak +1MiB) = **8MiB**. Общие heaps ограничены120MiB, оставляя≈3,25MiB вне heaps для дополнительного аппаратного accounting. Linear=120−20=100MiB; arena=100−8=**92MiB**.

92 — не заявленный минимальный размер движка: это максимальная сохранённая arena при данном консервативном разделе бюджета. Наблюдаемый sbrk16MiB+4KiB имеет около76MiB запаса; DS9 API допускает меньший page-aligned pool, не требует ровно128. Для будущих сцен/mmap эти92MiB ещё не доказаны достаточными. Никакие донорские allocation failures не заменяются успехом.

До конструкторов проверены RW spans, page alignment image/arena/trampolines и совпадение size. Arena virtual0x3018a000/96468992bytes, physical0x2018a000..0x25d89fff; физическая разность концов равнаsize−1. Client-range GPU validation использует **фактические92MiB**, не прежние128. Ничего не перемещается после передачи в donor; arena/RX/стеки остаются живыми до completion/join как вh2.

## Изоляция изменений

Начальный observe control сохранял40/132/128/guard178/mode178 и добавлял только наблюдение, проверки областей и отдельные diagnostic identifiers/namespace. Он прошёл тот же original frame и safe_exit. Затем:

| Стадия | Единственный новый фактор | Результат |
|---|---|---|
| observe | Контроль с observation/новым title/namespace |1frame+safe_exit PASS |
| arena |128→92MiB arena во всех согласованных местах |1PASS |
| linear |132→100MiB linear heap |1PASS |
| normal |40→20MiB normal heap |1PASS |
| guard |Минимальный app limit178→124, пока mode178 |1PASS |
| prod |Тот же ELF guard-stage; только mode178→124 |Clean серия3PASS |
| CIA |Упаковка того же финального ELF/CXI |Actual payload3PASS |

Между C-стадиями изменяется одна строка profile defines; body идентичен. Между guard/prod **ELF и весь ExeFS одинаковы**, в настройках exheader только02→01 в0x20d/0x60d, а также пересчитана подпись AccessDescriptor. Kernel2.44/SVC не менялись, actual/AccessDesc1/1. Набор compile flags унаследован; старый `DS_NEW3DS_178` не используется в компилируемых адаптерах и не определяет exheader/strong heap values.

Рабочие GPU/shader и cooperative thread overlays побайтно копировались изh2; оригинальные source/runtime/backend не редактировались. Baseline261files совпали по SHA. [Gate](release-gate.json), [builder](../../tools/build_native_game_prod124.py), [аудит](../../tools/audit_native_game_prod124.py).

## Программные результаты и сохранённый host crash

Каждый завершённый цикл получил оригинальный checkpoint на callback351/352 и **96000/96000 pixels baseline match**. Код игры сам строит draw calls; baseline image читается только host runner для сравнения. GL_error0, CPU fallback0, failed_submits0, новых guest memory errors0. Сохранены GPU completion, шесть kernel joins Result0,0worker handles, balanced IO94/94 в первом и73/73 в следующих циклах, GSP release и normal/linear free до host unload.

**Начальная Prod124 CXI серия не прошла целиком:** первые2цикла PASS, третий reload упал внутри azahar_libretro.dll,0xc0000005/RVA326ccf, Windows Event1000. Сигнатура совпала с прежним h1; причинная связь с memory profile не доказана. [Запись](initial-host-crash.json). Сбой не удалён, не переименован в guest PASS и не считается исправленным.

После него **тот же неизменённый CXI** прошёл3цикла в новом `-r2`; лишь после этого создана CIA. Её собственный extracted payload прошёлещё3цикла. [CXI clean series](../azahar-native-game-v0.1.0-p124p-cxi-r2/result.json), [CIA series](../azahar-native-game-v0.1.0-p124p-cia/result.json). Установка через HOME Menu не эмулируется этим тестом. Известная нестабильность host emulator остаётся материальным ограничением проверки.

## Готовая CIA и следующие шаги

`3ds/build-native-game-v0.1.0-p124p/native-game.cia`, **337856bytes**, SHA256 **`9fea6c2923d555511dd19a5d0177041592979dbd22fe8f07a4228a509082e815`**, title **000400000FDE7300 / DS Game Prod124**. Payload/CXI SHA `903ef34b697d39750c0bd7a88c92c6964e22f0ee309694055933d4af57428bc1`.

Новый SD log root `3ds/ds-native-game-prod124-v0.1.0/run-NNNN/`, appdata namespace `native-game-prod124-v010`, исходные игровые файлы те же. CIA не содержит original .so/APK/assets/font/frame/RomFS. [Инструкция и SD](../../3ds/README-native-game-prod124.ru.md).

**Можно согласовывать одно аппаратное испытание**, учитывая известный host crash и ещё не проверенные hardware RX/cache/большой linear allocation. Автоматического разрешения нет. Если software/pass не подтвердится на устройстве, фиксировать последнюю stage/Result и не повторять тест самовольно. GPU/shader не переписывать без новых фактов.

Prod124 подходит для проверенного одного original UI/startup кадра в Azahar. Для непрерывного gameplay нужно измерять пики новых уровней, decompression, texture cache и mapping lifetimes. Если124 позднее окажется недостаточно, наиболее обоснованы measured сокращение/streaming и lifetime-aware поэтапные allocations; они не увеличивают общий лимит. Dev1 исследовать отдельно через SYSTEM/HOME/NS, без изменения конфигурации приставки и без обещания, что176+MiB доступны обычному HOME launch. Возвращаться к178 ради этого checkpoint сейчас не требуется.
