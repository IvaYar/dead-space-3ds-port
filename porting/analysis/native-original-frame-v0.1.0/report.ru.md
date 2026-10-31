# Native original frame0.1.0: кадр совпал, safe exit заблокирован

31.10.2026, ветка `feat/native-original-frame`. Реализован отдельный `tests/engine_native_frame.c`, builder `tools/build_native_frame.py`, runner `tests/smoke_native_frame.py`. Emulator harness/старые CPU/GPU builds/SDK/оригинальный donor и прежние hardware evidence сохранены. SHA256 inventory220 файлов before/after совпал (`preservation.json`, ignored). Ни hardware execution, ни push, ни552 теста не выполнялись.

## Реальное исполнение и выбор кадра

Новый entry point вызывает существующие ELF relocation/init/runtime/JNI/assets/GLES модули,209 оригинальных constructors, JNI_OnLoad, NativeOnCreate/SurfaceCreated/SurfaceChanged, реальные NativeOnDrawFrame, resume/focus events и необходимый существующий HID accelerometer backend. Адаптер акселерометра нужен исходному initialization even для заставки; управление/FPS/звук не разрабатывались.

Изначально выбран сохранённый кадр180. Прогонr3 показал, что номер callback не задаёт ту же стадию асинхронной загрузки: на180 новый entry point ещё отображал EA logo (совпадает с более ранним стабильным исходным GPU кадром16/17). Поэтому окончательный checkpoint определён **заранее заданным содержимым исходного baseline180**, CRC565 ea733050, стабильным также181…189. Кандидат не читает/не копирует baseline image, не рисует вручную и не воспроизводит сохранённый command stream. Он исполняет donor callbacks до появления именно этого оригинального кадра, максимум600. Хост затем сравнивает полное изображение независимо отguest CRC.

## Финальный r5

| Проверка | Результат |
|---|---|
| Отдельный CXI |`3ds/build-native-frame-v0.1.0-r5/native-frame.cxi` |
| CXI SHA256 |`a0f71f75e4ba066a05037b8777ed5d23e431d7f63adafca90deeb8de6051414b` |
| Исходный baseline |saved original GPU callback180/RGB565 CRCea733050 |
| Фактический callback нового запуска |351 |
| Framebuffer |BGR8/288000 bytes; стандартное приведение вRGB565/192000 bytes |
| Полное сравнение |**96000 pixels,0 различий, точное равенство** |
| GLES/CPU fragment/sample |0/0/0 |
| GPU draws/triangles/uploads |753/5394/4 |
| Submits |710,failed0 |
| Completion callbacks |PSC0=0,P3D=354,PPF=355 (включают внутренние splits/uploads, не по одному на callback) |
| GPU lifetime audit |passed перед capture; vertex/texture staging retained до retirement |
| Invalid host memory accesses |0 |
| Frame BGR8 SHA256 |`5f7b056c0fcca775927102c3620f5153c499b57054514fe22010da030972a204` |
| START lifecycle |NativeOnPause иNativeOnStop вернулись |
| Worker shutdown |**6 live после bounded join** |
| Общий runner PASS / safe exit |**false / false** |
| CIA |**не создана**, gate закрыт |

`analysis/azahar-native-frame-v0.1.0-r5/result.json`, `frame-before-exit.json`, `guest-result.json`, `native-frame.log`, PNG/host log содержат software evidence. Raw — в private SD. PNG просмотрен: исходный экран Айзека/наушников совпадает с известным GPU baseline.5.625s host elapsed не означает FPS/native frame time. Эмулятор не проверяет native memory protection/cache. **На реальной New3DS этот игровой entry point не запускался.**

## Native память, RX и ресурсы

Прежний `ds_exec_page` рассчитан максимум на16 защищённых страниц: для original donor нужен1059-page executable segment и3 страницы fail-stop trampolines. Не изменяя baseline DSExec, entry point использует существующий `ds_exec_open`/Luma handle и два page-aligned RX range с FlushProcessDataCache→ControlProcessMemory RX→QueryProcessMemory verify→existing entire-I-cache invalidation. Native query обязан покрывать весь диапазон с permRX; emulator branch честно отмечает native_verified=false. Код и арены не освобождаются и не становятся повторно доступными heap до остановки workers/процесса.

Сегменты donor: RX `[0,4337664)`, RW `[4337664,4792320)`, включая page alignment. Writable segment не попадает вRX. Native profile178MiB, heap40MiB/linear132MiB, donor shared arena128MiB. В финальном Azahar: image0848F000/4792320 bytes,arena3018A000/134217728,trampoline08922000/12288. Эти VAs — emulator observation, не обещание физических адресов native запуска. Stream по-прежнему использует свой physical base для допустимых offsets. Основной C backend не изменён.

Аппаратно успешный shader SHBIN скопирован из основного source и проверен побайтно против UV Mask. Для C backend сделана изолированная копия проверенных RGBA8/RGB8 substitutions: DS13_BGR8_CTR+TOP check,outputRGB8,present capacity×3; DS34_CAPTURE_RGBA задаётRGBA8 target/input/clear. Дополнительно native_finish закрывает пустой post-present frame без ещё одного LCD transfer. Hook Begin/Sync использует bounded SDK queue/VBlank waits, wrappers только сохраняют queue pointer/submit errors; новые общие IRQ recorder frameworks не создавались. Стандартный SDK handler сохранён.

Private SD подготовлена из прежнего verified источника, содержимое сверено SHA256:1728 files/414822611 bytes основных assets и20 files/163995411 bytes APK assets. Donor4499468 bytes совпал; проверены receipts, CRC9fd95635,EAMCore.ini3119/33c9beb3, derived font47036/71dcae12. Успешный реальный checkpoint загрузил4 GPU textures, без missing import/JNI на пройденном пути. Неиспользуемые неподдержанные функции/JNI slots имеют258 fail-stop traps суммарно, а не успешные пустые stubs.397 binding entries не означают полную поддержку всех дальнейших игровых путей.

## Точно установленный блокер выхода

1. В donor **нет** `Java_com_ea_blast_MainActivity_NativeOnDestroy`. Есть NativeOnPause иNativeOnStop; проверено по export table и ARM body, а не предположению об Android lifecycle.
2. Обе существующие callbacks возвращаются, после чего `ds7_shutdown(100000000)` сообщает **live=6**. Именно ветвь `if(live)return -1` останавливает shutdown **до освобождения GPU/donor**.
3. Реализация `ds7_shutdown` устанавливает stopping=1, запрещает новые pthread_create и делает bounded joins. Она **не посылает donor-specific quit signal**, не отменяет workers и не будит сама все их cond/semaphore waits. Timeout join не означает завершение потока.
4. Экспортированные JNI EAIO/Audio/RWFilesystem Shutdown имеют4-byte bodies и не дают доказанного протокола остановки этих6 workers. Не вызывать случайные C++ destructors/не переписывать alive counters, не принудительно free donor pages.

Условия native GPU/present самого этого кадра программно выполнены. Следующая необходимая зависимость — корректное прекращение использования donor image/arenas/потоковых ресурсов и только затем безопасное C3D/GSP/APT завершение. Точный внутренний quit protocol этих6 original workers пока не установлен; это граница результата, не заявление о невозможности порта.

**Минимальный промежуточный этап:** сохранить достигнутый content checkpoint, записать6 entry offsets/wait kinds/objects через существующий `ds7_debug_threads` после OnStop, сопоставить с исходными worker routines и добавить подтверждённое cooperative shutdown действие. Проверка: все bounded joins успешны/live0, затем native_finish→queue drain→C3D_Fini→полный exit.txt→guest HOME cleanup. Это узкая работа с thread lifetime, не новый graphics backend и не повтор shader/FILL исследования. После общего software PASS — создание CIA из того же проверенного ELF, проверка NCCH/capabilities/hashes и только отдельное согласование hardware.

## Циклы реализации, без скрытого PASS

- Первый compiled candidate: namespace содержал точки, запрещённые существующим файловым адаптером; остановка до constructors. Исправлено только имя нового private namespace.
- r2:209 constructors/JNI дошли до callback2; выявлена обязательная зависимость от существующего accelerometer/orientation backend. Подключён готовый адаптер, без разработки управления.
- r3:180 настоящих callbacks иEA logo, но не нужный content checkpoint; дополнительно выявлен отсутствующий NativeOnDestroy. Host prematurely прочёл частично перезаписанный result.json и выбросил JSONDecodeError. Runner исправлен на ожидание полной записи и надёжное завершение собственного emulator process на ошибке; r3 не объявлялся PASS.
- r4: compilation type errorCRC pointer, затем host load отказал из-за отсутствующего CXI; donor не исполнялся. Исправлен cast и проверка наличия готовой сборки до запуска core.
- r5: нужный content checkpoint точен, но bounded shutdown6 workers оставил общий FAIL. Следующие runtime прогоны без новой shutdown реализации не нужны.

Во всех случаях старые emulator harness/builds/private SD не изменялись. Предыдущие candidate CXI/manifests/logs сохранены отдельно. Готовые original .so/APK/assets не попадают в Git или релизы; новые screenshots/raw тоже остаются локальными ignored evidence. Подготовлен только экспериментальный CXI, **никакой игровой CIA/публичного пакета нет**.
