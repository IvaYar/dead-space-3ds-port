# Ограниченная оптимизация загрузки после HID 0.1.7

Устранена повторная запись неизменённых CPU texture pages. В Azahar CPU100 время от запроса оригинального движка до ready меню сократилось **с 315,733 до 277,759 с (−12,03%)**, тяжёлый callback — **с 199,932 до 162,226 с (−18,86%)**. Повтор: 278,127 / 162,519 с. Это программные измерения; аппаратное ускорение пока не измерено. **Новой CIA нет, аппаратных запусков и push не было.**

[Полные численные результаты и проверки](result.json), [аппаратные 259 с вне тяжёлого draw](hardware-breakdown.json), [page lineage](page-working-set.json), [ARM pager contracts](pager-tests.json), [проверяемая правка](paging.diff), [границы экспериментов](experiments.json).

## Причина 201 сохранения и 166 загрузок

Два разных кэша нельзя смешивать: DS15 хранит канонические CPU RGBA pixels с resident limit **6 МиБ**, DS34 хранит GPU textures с прежним budget **8 МиБ**. GPU backend не менялся. Канонические страницы 1024×1024×4 имеют размер **4 МиБ**. Две такие страницы требуют 8 МиБ, поэтому не помещаются вместе в 6 МиБ; LRU многократно вытесняет одну при обращении к другой.

Существующий DS22 подготавливает каноническую CPU texture residency до выбора GPU draw path. Поэтому наличие GPU-копии само по себе не предотвращает CPU paging. Этот порядок не переделывался: отложенная CPU residency потребует отдельного доказательства lifetime и fallback semantics.

В baseline trace тяжёлого callback четыре page lineage по 4 МиБ прочитаны **47, 36, 29 и 6 раз**; всего больших загрузок 121, остальные — меньшие страницы. Наблюдается чередование крупных source pages при исходной подготовке font/menu atlas. Совпадают исходные 1146 draw calls, 34 TexImage calls и 129 GPU texture allocations; обязательные игровые операции не пропускались.

Дополнительная проблема: `spill()` безусловно вызывал `save()` и для ранее загруженной страницы, которая после загрузки **не изменялась**. Старый файл при этом ещё существовал: load его не удаляет. Save вычислял CRC, создавал новый файл, записывал всю страницу, закрывал файл и удалял старую копию.

Из 201 save **163** оказались повторной записью прежнего snapshot: одинаковые размер и CRC относительно старого token, суммарно **511180800 bytes (487,5 МиБ)**. Семь прежних tokens созданы ещё до тяжёлого callback; если считать только tokens, созданные внутри него, получится 156 — это неполный подсчёт. Наиболее дешёвая адресная оптимизация — сохранить эти неизменённые backing-копии.

## Что изменено

В отдельной generated копии DS15 `spill()` создаёт snapshot только при отсутствии действующего backing token. Повторное вытеснение неизменённой загруженной страницы освобождает RAM, сохраняя существующий файл. **Любая запись через TexSubImage инвалидирует snapshot соответствующего level, FBO clear/draw — snapshot level 0.** Замена image/delete/close используют прежний `level_clear` с удалением backing. GPU uploads и CPU reads не считаются изменением канонических пикселей.

`DS15Level` не расширен, дополнительного кэша pixels нет. Меняются только generated `ds15_textures.c` и `ds26_framebuffer.c` через [build_native_loading.py](../../tools/build_native_loading.py). Основные source, прежний native entry point, HID/guard/queue, native shutdown и GPU/shaders остаются прежними. Для следующих экспериментальных сборок нужно явно перенести этот opt-in transform; старый builder HID 0.1.7 автоматически оптимизацию не включает.

Ранее выполненная **табличная CRC32 не переделывалась**. Generated DS27 и `native_menu_page_crc.h` побайтно совпадают с HID 0.1.7. У каждого реального load сохранены header/size/EOF/ferror/close/CRC checks. Количество CRC уменьшилось вместе с количеством ненужных записей; проверки существующих файлов не отключались. Контракт проверен на изменяемых страницах, а не только на readonly menu.

Исследование копирований: TexImage создаёт CPU RGBA store; GPU upload строит Morton/ABGR staging, а большой linear atlas затем копируется штатным C3D upload path. Эти копии имеют разные layout/lifetime и в данном этапе не устранялись. Изменений GPU staging, flush, sync или retirement нет. Удалены полные повторные копирования CPU page в backing file.

## До / после в одной среде

Azahar libretro/OpenGL, CPU100, свежий изолированный writable SD на каждый процесс; одинаковые page instrumentation, ресурсы, Prod124 и сценарий HID. Все времена ниже — SDK guest ticks, **не ускоренный host wall time и не hardware time**.

| Показатель | Контроль loadbase | loadclean | Повтор loadclean |
|---|---:|---:|---:|
| Engine request → menu ready, с | 315,733 | 277,759 | 278,127 |
| Самый долгий callback, с | 199,932 | 162,226 | 162,519 |
| Остальное время до ready, с | 115,801 | 115,533 | 115,608 |
| Page saves в тяжёлом callback | 201 | 38 | 38 |
| Page loads в тяжёлом callback | 166 | 166 | 166 |
| Write payload, bytes | 554541056 | 43360256 | 43360256 |
| Read payload, bytes | 515424256 | 515424256 | 515424256 |
| Page CRC operations | 367 | 204 | 204 |
| CRC input bytes | 1069965312 | 558784512 | 558784512 |
| Normal allocator peak, bytes | 19881984 | 19881984 | 19881984 |
| Linear peak, bytes | 104635264 | 104635264 | 104635264 |
| Kernel peak commit, bytes | 126828544 | 126828544 | 126828544 |

В первом сравнении backing save time **30,815 → 3,688 с**, load time **128,800 → 118,211 с**. Внутри них page CRC **32,054 → 16,740 с**, остальное backing time **127,561 → 105,159 с**. Эти интервалы вложены; не прибавлять их к callback. Non-CRC backing time включает stdio/FS IPC, внутренние копирования и scheduling, это не отдельно измеренная физическая скорость SD. Число/размеры reads не изменились, поэтому изменение их времени не выдаётся за устранение загрузок или гарантию такого же выигрыша на hardware.

Все 166 load requests имеют одинаковую **последовательность размеров и CRC** в контрольном и обоих оптимизированных процессах. Это не побайтовое сравнение всех page payloads. Побайтовое сравнение выполнено отдельно для полных rendered frames, см. проверки ниже.

Linear headroom остался **222336 bytes**, normal heap headroom по footprint **1089536 bytes**. CPU residency limit не увеличен: ещё 2 МиБ не укладываются в измеренный запас normal heap, GPU/linear также тесны. Instrumentation содержит bounded RAM array размером около 48 КиБ; kernel commit на **49152 bytes** больше frozen 0.1.7 release, одинаков у контрольной и оптимизированной сборок, и ниже лимита124 МиБ на3194880bytes. Это расход диагностики, а не рост cache budget.

## Аппаратные 258,683 с вне тяжёлого callback

Для сохранённого hardware HID 0.1.7 время engine request → ready **559327,446 мс**. Отдельный draw4082 — **300644,235 мс**, остаток **258683,211 мс**. Новых hardware измерений в этом этапе нет.

| Участок исходного аппаратного прогона | Время, с |
|---|---:|
| Bootstrap до engine init return | 2,647 |
| Draw callbacks в полных окнах до frame4080 | 117,283 |
| Present в этих окнах | 67,127 |
| Диагностика в этих окнах | 53,788 |
| Остальное внутри этих окон | 13,249 |
| Непокрытые края около тяжёлого callback / ready | 4,588 |
| Всего вне тяжёлого callback | 258,683 |

В callback2 потрачено **45,892 с**, одновременно учтены 2507752 resource bytes / 5670 positive reads. В callback928 — **15,126 с**, 5832040 bytes / 1289 reads. Другие записанные >100мс callbacks до тяжёлого: 1, 281, 282, 927. Resource counters включают concurrent loader activity; эти значения не являются чистым IO timing только данного callback. В сумме записанные долгие callbacks объясняют около63,264с из117,283с, остальные54,019с приходятся на множество обычных callbacks.

В present уже входят queue/VBlank waits; отдельно подсчитанные до frame4080 **55,624 с VBlank / 7,822 с queue** нельзя прибавлять к таблице. Диагностика действительно существенна: readbacks, CRC кадра, dumps и синхронная запись trace на SD. Её не отключали и не урезали ради цифры ускорения. Достоверно распределить оставшиеся13,249с между HID/APT/sensor/report/scheduling задним числом старый профиль не позволяет. Края4,588с также оставлены отдельной категорией, а не объявлены «чистым IO».

В software без тяжёлого callback получено около115,5–115,8с; узкая paging-правка эту часть практически не ускорила. Причины различия hardware/software времени нельзя свести к одному множителю. **Переносить −12% прямо на аппаратные559с как измеренный результат нельзя.**

## Проверки и границы этапа

Два сравниваемых варианта: instrumented baseline и одна оптимизация clean backing. Всего **четыре завершённых Azahar процесса**: baseline, optimized, optimized repeat, optimized HOME/X fixture. В optimized normal отсутствует HOME fixture. После original A по-прежнему выполняются два callback и safe exit; игровой процесс не включён.

- **26 полных пар rendered frames** совпали побайтно (13 checkpoint frames для каждого optimized run), включая Normal/Easy, B, A-переход и два завершающих callback. Независимо пересчитаны raw/readback/RGB565 CRC для всех сохранённых кадров каждого процесса. FNV/input и native cleanup guards из прежнего HID audit сохранены.
- Навигация Normal→Easy→Normal→Easy и original A ACK прошли в обоих optimized runs. B down/up доставлены; первый исходный экран по-прежнему игнорирует BACK. Короткие HID pulses захватываются, admission не зависит от framebuffer.
- Kernel join оставшихся пяти native workers,0handles, balanced IO, collector joined/freed, GPU/SDK heaps teardown, GL/failed submits/invalid accesses0 во всех четырёх процессах. HOME передан SDK после quiescence.
- **13 ARM pager/FBO tests** прошли: повторное чтение без новых saves, TexSubImage, FBO clear/draw после reload, image replacement, deletion/retained attachment, save/load failures, pinning/oversize budgets. Одна первоначальная проверка ошибочно использовала glClearColor для ожидаемого цвета draw; fixture исправлен на glColor4f, исходный FAIL сохранён отдельно. Runtime для этого исправления не менялся.
- 375 защищённых файлов и1752 master/store resources сверены по SHA. Исходные ресурсы, старые SD/evidence, baseline, hardware reports и CIA не менялись. `FRAME FAIL`, frozen `ea733050` и старые9231pixels остаются открытыми.

Read-only перепроверка существующих evidence, с обновлением только summaries:

```powershell
python porting/tools/audit_native_loading.py
```

Новые эксперименты требуют свежих revision/attempt; builder и smoke runner отказываются затирать существующие результаты. Runtime-проверки используют обычный `smoke_native_game_hid.py`, исходный runner не изменён. Packaging для этого этапа не выполняется.

**Этап оптимизации завершён.** Выигрыш ограниченный, но проверяемый; остаются166реальных больших reads и дорогая подготовка атласов. Дальнейшие варианты residency/cache перераспределения, оптимизации staging и изменения интенсивности диагностики здесь не начинались. Следующий приоритет — original audio NULL/fog, продолжение после A и первая сцена с Айзеком в Prod124.
