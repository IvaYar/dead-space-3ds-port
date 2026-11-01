# Stable0.1.2 hardware run-0001: frame FAIL, другой loader, cleanup FAIL

01.11.2026. Пользователь передал `porting/ds-native-game-v0.1.2/run-0001/` и три фото в сообщении. **Аппаратный выход не прошёл. Эту CIA не повторять.** Прежние software PASS сохранены, но не означают исправление аппаратного завершения. Новая CIA в этом разборе не создавалась и на устройстве агент ничего не запускал.

## Полученные данные и сообщение пользователя

27 файлов побайтно архивированы в `analysis/hardware/native-game-stable-v0.1.2-user-run-0001/`. [Manifest с размерами/SHA](archive-manifest.json), [машинный результат](hardware-result.json), [проверка captures](capture-audit.json). Исходная папка пользователя не менялась. Raw/GX/object dumps и производные изображения остаются приватными; фотографии доступны в сообщении, локальное архивирование самих фотографий не заявляется.

Пользователь сообщил: после START видел сначала `FRAME FAIL: see log / Cooperative shutdown running`, затем `STOPPED / FAIL: cleanup incomplete / Resources retained; see log`. Анимации подтормаживали, но прошли. HOME открыл главный экран; X оставил консоль на «Программа закрывается». Повторный HOME вернул главный экран; при POWER ожидаемый экран выключения не появился, консоль потухла. Позднее пользователь уточнил: на экране закрытия ждал около двух минут, POWER удерживал; длительность удержания не сообщена. Это не сообщение о неработающем коротком нажатии POWER. Факт системного повреждения, процесс termination и успешный аппаратный safe_exit этими наблюдениями не доказаны.

На первых двух фото верхний экран показывает исходную заставку Айзека/наушников с нижними фрагментами. Третье фото подтверждает экран закрытия в HOME Menu; длительность остановки берётся только из слов пользователя, не из фотографии.

Ожидаемый установленный кандидат — DS Game Stable0.1.2/FDE7500, CIA SHA `8bc86b29d023211d6469f903ba4eed343b3abbb83a901576e8ba096c424e6226`. Название/версия совпадают с фото и логами, hash установленного файла независимо не измерен.

## Где остановился выход

Все600 callbacks/present вернулись. Кадр не прошёл gate, `frame_status=FAIL`, `last_crc565=bf2a6bfd`, expected `ea733050`; sequence не запускалась. Лог доказывает **автоматическое** начало shutdown после CRC_FAIL, а не запуск очистки кнопкой START:

```text
FULL FRAME CRC GATE NOT REACHED after 600 original callbacks
FRAME FAIL: CRC_FAIL: full frame gate not reached; beginning cooperative shutdown
CALL MainActivity_NativeOnPause
RETURN MainActivity_NativeOnPause
CALL MainActivity_NativeOnStop
RETURN MainActivity_NativeOnStop
LOADER natural completion=110
FAIL phase=shutdown lifecycle frame=600: worker/GPU shutdown incomplete
START: cleanup incomplete; live resources retained
```

110 — timeout по результату ограниченного kernel join30000ms. Это не invalid handle: у всех шести workers `done=0`, kernel poll `0x09401bfe` (timeout). `active_threads=6` — свежий snapshot на main boundary, не прежние cached нули. До job/audio/periodic signals, JNI/файловой очистки, GPU Fini, exit marker и возврата процесса **не дошло**. Это не доказательство GPU hang: до остановки кадры/парные readbacks проходили с завершённой очередью, failed submits0/GL0.

Ресурсы намеренно удержаны, `safe_exit=false`, `cleanup_status=retained`. Ложного PASS/free нет, но пользователь не получает обычный выход. Увеличение времени ожидания само по себе не исправляет установленную ниже ошибку классификации loader.

## Почему Azahar не проверил этот loader

| Свойство | Финальный software negative600 | Hardware600 |
|---|---:|---:|
| Generic thread entry |0x24c914|0x24c914|
| Generic callback |0x320624|0x320624|
| Token |0x706|0x806|
| Runnable vtable offset |0x428378|0x428390|
| Virtual Run offset |0xb60bc|0xb6e6c|
| Uploads / CPU fragments |4 /0|6 /8103|

Текущий helper проверяет generic entry/callback, но не конкретный virtual Run. **На устройстве он принимает другой, более поздний runnable за прежний конечный startup loader.** Ранее проверенное естественное завершение Run0xb60bc не доказывает естественного завершения Run0xb6e6c при остановленном main loop.

В четырёх snapshots позднего потока одинаковая сохранённая цепочка wait stack: return0x3357d8 →0x321b64 →0xb7084. Это история последнего sleep/wait, **не аппаратно снятый текущий PC**. Записан sleep1ms. Целевой статический разбор оригинальной библиотеки показывает:

- 0x320624 диспетчеризует virtual Run через vtable[0].
- 0x335790 опрашивает поле объекта+0x10 и byte+0x14, отпускает mutex и спит1ms между проверками. Путь не содержит общего deadline.
- 0x307468 меняет состояние синхронизации, записывает delegate и снова ждёт через0x321b50/0x335790. Поздний Run находится на этом пути.

Нужна проверка того, кто должен выполнить delegate/снять состояние ожидания. Зависимость от обслуживания main-thread callbacks — конкретная гипотеза по этому пути; полное назначение синхронизации и безопасная cancel-последовательность ещё не доказаны. Просто записывать нули в поля, прерывать sleep, останавливать jobs раньше loader или вызывать весь destructor нельзя: это не обеспечивает return пользователя ресурсов. NativeOsExit уже ранее был небезопасен, повторно не используется.

## HOME → X и POWER

В main-thread `fatal` есть бесконечный цикл `aptMainLoop(); hidScanInput(); ...`, который **игнорирует false из aptMainLoop**. Переход в HOME обслуживается, а требование закрыть приложение не приводит к его завершению. Это дефект завершения приложения и соответствует наблюдаемому зависанию «Программа закрывается».

Исправление не может состоять в обычном `return/gfxExit/free` из этого цикла, пока живы шесть пользователей ресурсов. Сначала нужен кооперативный stop позднего runnable и quiescence; закрытие должно учитываться как pending request. Принудительный unsafe free или новый фиктивный safe_exit не добавлены. Дополнительная причина отсутствия экрана POWER по имеющимся файлам не установлена; SD не содержит системного trace после HOME.

## Что новое установлено об изображении

Хеш `bf2a6bfd` впервые появляется уже на callback88; проверка ни разу не получила `ea733050`. Raw на351/352/400/534/600 одинаков: BGR8 CRC `9b99050c`. Последний raw **побайтно совпал с предыдущим аппаратным0.1.1**, не только по CRC. Расхождение9231pixels уже есть до поздних uploads/clear; объяснять его исключительно новым состоянием после600 больше нельзя.

Все9 парных captures согласованы: два invalidate/readback без новой команды дают одинаковый raw CRC, независимый RGB565 CRC совпадает с buffer-based CRC и host zlib. Размер/stride/формат и реальные GX transfer240×400/flags1000 корректны. Это существенно сужает readback/CRC направление, но не является абсолютным доказательством когерентности GPU texture/vertex cache.

Сопоставлены пары hardware75/software298,76/299,351/351,352/352,400/400. Vertex input FNV/count и texture FNV совпадают. **В каждой паре PICA bytes отличаются ровно двумя32-bit words: GPUREG_TEXUNIT0_ADDR1 (0x85), адресами двух текстур.** Все остальные words, packet headers/masks, uniforms и состояния равны. Адреса текстур могут различаться из-за размещения VRAM; сами FNV не являются криптографической гарантией побайтной идентичности текстур/вершин.

В этих реальных командах texture0 PARAM=`0x6`: min иmag **LINEAR**, что непосредственно следует из pinned libctru enums.h/Citro3D texture.h. Сохранённый предыдущий sampling report уже установил, что используемый Azahar Software ведёт LINEAR как NEAREST. Теперь известно, что этот несовместимый режим реально используется рассматриваемой заставкой. Это конкретный фактор несопоставимости frozen software CRC с hardware, но ещё не доказанный вклад каждого из9231pixels. GPU backend, UV и target CRC не менялись.

Нижние фрагменты остаются отдельным compositing-вопросом: они есть в обоих вариантах; доказанное ранее совпадение551 reference pixels с EA16/17 сохраняется. Hardware показывает537 ненулевых pixels в той области. Это не новый случайный VRAM шум.

## Один адресный software probe

Проверена гипотеза поздней фазы по сдвигу callbacks: первые4uploads появляются hardware75/software298, то есть разница223; поздний runnable на hardware уже534. Поэтому создан **один отдельный software-only CXI с cap850**, принудительным отклонением gate и собственными SD/build/log paths. Production source/CIA/backend и аппаратный лимит600 не менялись. [Manifest/result](late-loader-probe/result.json), инструмент `tools/probe_native_game_late_loader.py`.

Результат:850 callbacks, FAIL gate и успешная software очистка, но runnable всё ещё Run0xb60bc, uploads4/CPUfragments0. **Поздний hardware Run0xb6e6c не воспроизведён; это не проверка исправления hardware выхода.** Простое продление количества кадров не воспроизводит фазу загрузки; повторное произвольное увеличение cap не предлагается. Новых полных ARM/GPU suite, дополнительных CIA и аппаратных запусков нет.

## Дальнейшая работа и статус

1. Воспроизвести именно runnable0xb6e6c и его pending delegate в software через контролируемое состояние/планирование загрузки; различать классы loader по vtable/opcodes до выбора stop-пути.
2. Найти штатную кооперативную stop/drain последовательность позднего runnable, проверить его зависимость от main-thread обслуживания. Сохранить kernel/IO/GPU lifetime guards и настоящий FAIL.
3. Исправить обработку pending APT close совместно с завершением пользователей; отдельно проверить HOME-close request, а не только гостевой START в Azahar.
4. Проверять изображение на одинаковых inputs и с учётом реальной LINEAR фильтрации; не заменять frozen reference новым hardware raw и не переписывать рабочий backend по предположению.

Текущая CIA снята с повторных аппаратных проверок; audit теперь сохраняет software proofs, но выдаёт `hardware_result=FAIL_frame_and_cleanup`, `ready_for_one_separate_hardware_test=false`, `repeat_current_CIA_prohibited=true`. Предыдущий gate сохранён отдельно. Следующий аппаратный кандидат пока **не готов**. Полученных27 файлов и трёх фото достаточно; повторный запуск ради данных не нужен.
