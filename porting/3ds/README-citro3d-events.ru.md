# Citro3D CLEAR IRQ v0.1.1

Один диагностический CLEAR, без TRIANGLE/DS34/игры. Это наблюдение за незавершённой очередью, не исправление GPU. Проверено в Azahar2126.2; аппаратный исход ещё неизвестен. Возможность повторного зависания/необходимости POWER сохраняется.

GPU-пакеты побайтно совпали с аппаратным CLEAR v0.1.0: FILL→DISPLAY, RGB8/D24S8 target240×400, RGB565 output, flags0x2100, прежние размеры/адреса и порядок. SDK/профиль памяти/capabilities прежние. Title ID **000400000FDE6900**, title version2: заменяется только прежний **Citro3D Control**, не DS34 GPU Test и не системный титул. Новая SD-папка сохраняет прежние результаты.

## Один аппаратный запуск пользователем

1. Установить `citro3d-control-v0.1.1.cia` через FBI. Открыть **Citro3D CLEAR IRQ**, убедиться в версии0.1.1 и надписи CLEAR only.
2. Нажать **A один раз**. Выполняется только CLEAR. TRIANGLE не запускается ни при каком исходе.
3. Сфотографировать итог. START делает проверку SDK queue; при `GX completion pending; memory retained` выход откладывается, память не освобождается. Не нажимать A повторно. При полном зависании может потребоваться выключение POWER.
4. После выключения скопировать всю **`SD:/3ds/citro3d-control-v0.1.1/`** в проект. Нужны control.log, result.json и **все events-*.json**. При неполном наборе прислать имеющиеся; последний доступный checkpoint важнее наличия result.json. Самостоятельно повторять запуск не нужно.

Новый hardware run агент не выполнял. Никаких гарантий безопасности на железе из emulator PASS не следует. Существуют операции без собственного deadline: SDK FrameEnd, GSP/SD/APT и финальное освобождение после idle check.

## Что записывается

Используется публичный `gspSetEventCallback` libctru2.7.0 только для не занятых этим standalone-приложением слотов PSC0/PSC1/PPF. Настоящий SDK GX handler вызывается **до** этих callbacks. Citro3D VBlank callbacks, onQueueFinish и порядок SDK dispatch не заменяются. IRQ linker interception не используется.

Callback выполняет только svcGetSystemTick и небольшие32-bit atomic записи: count, first/last ticks, порядок событий, run tag, SDK queue fields. Нет SD/stdio, allocation, sleep, mutex или64-bit atomics. ELF call graph проверен. Небольшая ненулевая задержка наблюдения всё же существует; это не измерение физического момента окончания GPU операции.

Снимки пишет основной поток: **before-submit**, **after-submit**, **timeout** при ошибке, result и exit-precheck. Файлы events-NNNN-label.json уникальны и не перезаписывают ранние checkpoints. После timeout поздние события сохраняются при изменении counters с ограничением частоты4Hz. Сам callback никогда не вызывает файловый код. Первая запись на SD происходит до Run, следующая — после его возврата; между самими GPU-командами дополнительной файловой записи не добавлено.

64-bit ticks хранятся двумя32-bit словами под sequence check. `stable:false` использует последнее согласованное значение, а `events_consistent:false` запрещает делать вывод о пропаже события по этому снимку. Согласованность events не делает весь снимок SDK queue глобально атомарным. `sample_tick` — конец считывания. `first_us/last_us` рассчитаны основным потоком по **номинальному SDK tick_hz268111856**, сырые ticks сохраняются.

`callback_queue` — поля после SDK handler; успешный FrameBegin может уже очистить queue в основном потоке. Поэтому total0 после retirement — штатный reset, не потеря команд. Сравнивать нужно прежде всего снимки, где total2/submitted2, и изменения относительно before-submit. Ненулевые counters до Run или first_run0 означают фоновые/ранние события и требуют осторожной атрибуции. Run tag программный, не hardware command ID.

## Интерпретация

| Устойчивый согласованный результат после Run | Что он означает |
|---|---|
| PSC0 доставлен, PPF нет | Есть fill-уведомление, не наблюдается transfer-уведомление; искать transfer/PPF delivery. Это ещё не доказательство физического hang DISPLAY. |
| PPF доставлен, PSC0 нет | Есть transfer-уведомление, не наблюдается fill-уведомление; искать fill/PSC0 delivery. |
| PSC0 и PPF доставлены, SDK completed2 | Ожидаемый completion; после FrameBegin queue может стать0/0/0. |
| Оба доставлены, но total2/completed1 сохраняется | Проверять queue lifecycle/accounting и принадлежность событий. Краткий разрыв возможен: SDK handler выполняется раньше observer. |
| Ни PSC0, ни PPF | По одному completed нельзя определить операцию; проверить доставку/регистрацию/прочие eligible IRQ и более поздние снимки. |
| PSC1 равен0 | Само по себе не ошибка. SDK не считает PSC1 отдельной командой. Для dual-buffer FILL используемая Azahar доставляет только PSC0. |

В Azahar2126.2 фактически PSC0=1/PSC1=0/PPF=1. В [реализации dual-buffer FILL](https://github.com/azahar-emu/azahar/blob/2126.2/src/video_core/gpu.cpp#L188) отправляется один PSC0; ранее ожидаемый обязательный PSC1 был ошибкой проверки. PSC1 остаётся полезным вспомогательным наблюдением на железе, но не условием успеха/освобождения памяти.

Отсутствие события может означать как незавершённую операцию, так и потерю уведомления. Наблюдение callbacks не читает аппаратные finish bits и не решает эту неоднозначность само по себе.

В validation сохранены normal/fault emulator reports, logs/checkpoints, clear PNG и проверка call graph. Отдельный НЕРАСПРОСТРАНЯЕМЫЙ emulator-only fault build проверяет все3 recorder-функции программным вызовом до регистрации и затем сбрасывает тестовые данные; настоящие GPU события учитываются с нуля после установки callbacks. Этот же build искусственно истекает wait, не меняя SDK queue/пакеты. В обычной CIA ни selftest, ни fault activation нет.

## Воспроизведение на ПК

```powershell
python porting/tools/build_citro3d_events.py
python porting/tests/smoke_citro3d_events.py
python porting/tools/build_citro3d_events.py --fault-test
python porting/tests/smoke_citro3d_events.py --fault-test
python porting/tools/package_citro3d_events.py
```
