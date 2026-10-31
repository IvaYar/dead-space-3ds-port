# DS34 UV Mask0.2.1: аппаратный PASS run-0002

31.10.2026 получены фото консоли и все7 файлов `porting/run-0002/`. Пользователь дополнительно подтвердил START: **«Да, вернуло в HOME»**. Прочитаны все файлы,26 RAM snapshots и весь PICA stream; проверен каждый пиксель frame.raw. Точные bytes архивированы в `analysis/hardware/ds34-uv-mask-v0.2.1-user-run-0002/`, sizes/SHA256 — archive-manifest.json. Фото доступно в сообщении пользователя, локального файла фото нет. Это один пользовательский аппаратный запуск; агент новых запусков не выполнял.

## Подтверждённый результат

| Проверка | Native результат |
|---|---|
| Environment/fault | native / false |
| Submit | FILL/PICA/DISPLAY — все3 вернулись Result0 |
| Events | PSC0→P3D→PPF, по одному; completed после callbacks1→2→3 |
| Decision до NONBLOCK/Clear | total3/submitted3/completed3, idle=true |
| RAM window |100ms,26 stable/consistent snapshots,2 VBlank-фазы |
| Overflow/critical I/O |0/0 |
| Timeout/NONBLOCK | timeout=false, NONBLOCK success |
| GLES | initial0, после ожидания0 |
| Drawing |1draw/2triangles, CPU fragments/samples0 |
| Raw |288000 bytes BGR8, проверены все96000 pixels |
| Pixel counts |5120 белых,90880 фон RGB(104,176,216), scissor x40…103/y40…119 |
| Frame comparison |native raw побайтно совпал с Azahar candidate raw |
| Exit |EXIT BEGIN→EXIT GPU DRAINED, exit.txt полный; пользователь подтвердил HOME |

`result.json` сохраняет version0.2.0 и GPU_fixed_claimed=false из неизменённого observer; это ожидаемая историческая строка, не отсутствие исправления. Вариант однозначно сопоставлен по реальному shader upload и полученному результату. Device CIA hash независимо не снимался. Ожидаемые CIA SHA256 `5e853550bede4aa6a911959c122dcc6aa595c673071d6f52aacf37e1086284ee`/TitleID000400000FDE6F00.

100ms — время диагностического окна, **не время GPU кадра и не FPS**. Наличие полного кадра, P3D/PPF, queue3/3/3 и exit — совместное подтверждение draw/present/retirement, а не только успешного submit.

## Сравнение с неработавшим native run-0001

Все24 GX words **совпали, включая адреса**. PICA1168 bytes/82 packets отличается **ровно bytesF0 иF4**: `AC→AF`, `EC→EF`, descriptors000542AC→000542AF и000557EC→000557EF. Восемь shader instruction words, DVLE, output mapping, uniforms, framebuffer/scissor/sampler/vertex state прежние. Новый native dump побайтно совпадает с ранее испытанным Azahar UV Mask dump.

Native PICA SHA256: `05b59185d7fb0aded20862db216bfa99ce5603caf5cd3454fce3bd97165c3cb4`.

Native frame.raw SHA256: `9964d7d74243520bf9451222df91869be3c17a255fccf9c0ab5e2ef6d70d94d6`.

В предыдущем запуске PSC0=1,P3D=PPF=0,queue3/3/1,busy через2000ms и HOME не достигнут. После единственного изменения — полной записи UV.xyzw вместо только.xy — P3D иPPF получены, кадр верен, очередь завершена и HOME достигнут. **Контролируемая пара аппаратных результатов подтверждает устранение наблюдавшегося DS34 first-frame отказа этой правкой.** Внутренний физический механизм зависания GPU не снимался; интерпретация о незавершённом VSH output согласуется с данными, но не является прямым измерением внутренних status registers. Не распространять PASS на RGB565, большой vertex stream, textured gameplay,178MiB native memory profile или всю игру.

## Перенос минимального исправления

В рабочий `3ds/source/ds34_gpu.v.pica` перенесены только две destination-mask правки. Исходник до изменения сохранён здесь как `shader-before.v.pica`. Основной C backend, SDK, game logic/input/audio/native entry point не менялись.

Picasso собрал основной source в `integrated.shbin`; он **побайтно равен SHBIN аппаратно успешного варианта**. Все16 объявленных output components position/color/UV0/UV1 записываются ровно по одному разу. `integration.json` фиксирует проверку. Поэтому лишний повтор того же эмуляторного бинарника не запускался: его payload уже прошёл Azahar и теперь native PICA upload.

Из145 файлов прежнего preservation inventory изменён намеренно только основной shader source; остальные144, включая старые binaries/packages/hardware evidence/C backend/SDK libs/GPU engine baseline, сохранены. Старые manifests описывают исторические inputs, их hashes не переписывались под новый source. Рабочие аппаратные CIA и raw evidence сохранены. Текущая ветка `test/ds34-full-output-mask`; commit/push не выполнялись.

## Подготовка оригинального игрового кадра

Дальнейший конкретный путь описан в `native-game-frame-next.ru.md`: использовать подтверждённый RGBA8→RGB8 DS34, выделить native entry point на существующих runtime/JNI/assets/RX-cache модулях, сохранить emulator-only audit guard. Текущий test — настоящий PICA draw через DS34, но **синтетический кадр, game_called=false**. Оригинальная игровая сцена и управление Айзеком ещё не испытаны на железе.

Повторных/дополнительных аппаратных запусков не делать. Полные552 и старые GPU suites не запускались. Полученный единственный результат достаточен для завершённой shader correction; новая серия общих GPU probes не нужна.
