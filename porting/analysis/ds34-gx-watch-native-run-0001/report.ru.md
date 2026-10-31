# DS34 GX Watch 0.2.0: аппаратный run-0001, 31.10.2026

Получены и прочитаны **все5 файлов** `porting/run-0001/`: gpu-test.log, observation.json, first-frame.pica, result.json, ready.txt. Точные bytes сохранены в `analysis/hardware/ds34-gx-watch-v0.2.0-user-run-0001/`, размеры/SHA256 — archive-manifest.json. В полученной папке нет frame.raw, late-*.json, exit.txt или фото; видимость кадра пользователем не подтверждена.

Пользователь уточнил: **«в хоум не вернула, но сообщение вывело. Пришлось через кнопку повер выключать опять»**. START обработан, обычного выхода в HOME не было, потребовался POWER. Это не полный CPU freeze: основной поток завершил RAM-наблюдение, сохранил результат и позднее обработал попытку выхода, намеренно удержав GPU memory.

## Подтверждённые данные

| Проверка | Native результат |
|---|---|
| Среда/сборка | native, version0.2.0, fault=false |
| Приём заявок | все3 submit вернулись с Result0; массив FILL→PICA→DISPLAY |
| Сразу после настоящего Run | total3/submitted3/completed0, capacity32 |
| Доставленные events | только **PSC0**, order1, SDK queue на callback3/3/1 |
| Отсутствующие events в окне | P3D,PPF; вспомогательные PSC1/DMA также0 |
| Decision через2000мс | **3/3/1, SDK idle=false** |
| VBlank |13/13→133/133, оба+120; обе диагностические VBlank-фазы пройдены |
| NONBLOCK | вызван, вернул false; Clear не выполнялся |
| Согласованность |257 snapshots, все queue_stable/events_consistent; overflow0 |
| SD внутри окна | critical_io_blocked0; запись началась после close и вернулась |
| GLES | до End0; после диагностического отказа1280/0x500 |

Все253 snapshots после первого доставленного PSC0 показывают согласованные3/3/1, idle=false и те же event counts. На конец окна приходящие события и SDK accounting **согласуются**: один PSC0 соответствует completed1. Признаков «три IRQ доставлены, но SDK посчитал только один» здесь нет. Неподтверждённую общую ошибку accounting не объявлять причиной этого запуска.

GL1280 возник после timeout/NONBLOCK в fail-пути backend (`GPU frame unavailable`), тогда как initial_error_before_End=0. Это диагностическое следствие незавершения, не доказательство исходного неверного GLES enum.

Теперь установлено то, чего не хватало в v0.1.0: **первый batch действительно остаётся busy после успешного возврата Run**, оба VBlank работают, filesystem не участвует в критическом окне. Сценарий «остановились только на дополнительном FrameSync» текущего наблюдаемого отказа не объясняет; SDK busy измерен независимо, без этого unbounded wait. При этом Result0 не доказывает исполнение GPU, а callbacks фиксируют доставку после SDK handler.

## PICA dump и адреса

Native `first-frame.pica`:1168 bytes, SHA256 **ffd8bbc608ff1f476de21c9e089e3736e29e875c68ca7a4a8f6452c4181e0357** — **побайтно совпадает** с успешным Azahar `analysis/azahar-ds34-gx-watch-v0.2.0/first-frame.pica`. Это уже равенство PICA bytes, не только GX metadata. Оно не доказывает равенство native vertex payload, CPU/GPU cache visibility или физическое исполнение этих команд.

Офлайн разобраны82 packets с byte masks. Native stream содержит DRAWARRAYS, NUMVERTICES6, финальные framebuffer flush/invalidate и **GPUREG_FINALIZE=12345678**. Очевидного отсутствия финализации command list нет. RGBA8 color-buffer register=2, color physical18000000, depth18300000 соответствуют framebuffer setup. Inactive sampler1=1805DC00 соответствует ранее загруженной8×8 white texture и не перекрывает color buffer.

VBO physical base **201C9C00**, offset0, stride64,4 attributes,6 vertices/384 bytes, ожидаемый диапазон `[201C9C00,201C9D80)`. Format/permutation/attribute counts согласованы с DS34Vertex и SDK BufInfo setup. Для этого кадра старый overflow attribute offset/high-FCRAM не проявляется. Самих384 vertex bytes с устройства нет; не утверждать их тождество или cache correctness. Полный masked register decode — `pica-registers.json`. Проверки не доказывают допустимость всего PICA state для native GPU.

## Что это сужает

**FILL получил ожидаемый completion PSC0.** Загрузочная TEXCOPY и подготовка shader/stream дошли до End, все3 заявки отправлены. PICA/P3D и DISPLAY/PPF завершения **не подтверждены**. Основной следующий кандидат — выполнение PICA command list, shader/pipeline/resource state либо его completion delivery. Отсутствие PPF может быть следствием незавершённого PICA/зависимости обработки batch; отдельно исправным DISPLAY этим не доказан.

По этим данным нельзя честно объявить «PICA физически зависла» или «потерялся именно IRQ»: нет ниP3D, ниPPF, и физические status registers не снимались. Но это уже конкретный draw/command-list путь, а не повод снова менять RGB8/RGB565, CIA/HBL profile, общий VBlank или расширять память наугад.

## Следующий шаг

Сохранённый native PICA stream использовать для **точечного сравнения DS34 shader/attribute/sampler/pipeline setup с аппаратно успешным stock**, сохраняя доказанную RGBA8/RGB8 FILL/output цепочку. Прежде чем менять renderer, найти проверяемое нарушение/существенное отличие этого state или ресурса. Из проверенных здесь адресов, stride и FINALIZE конкретная правка пока не следует; не выдавать произвольное отключение shader/pass/texture за найденное исправление.

Если статический разбор не даст доказанной ошибки, следующий единственный контроль должен различать конкретно DS34 PICA/resource setup и stock-safe PICA при той же внешней FILL/output цепочке и observer — с заранее зафиксированным списком изменённых параметров. Это отдельное решение, а не уже созданная CIA и не автоматический повтор v0.2.0. Из текущего результата не следует необходимость новой общей серии диагностики.

В этом сеансе только чтение/архивирование и офлайн разбор. **Новых сборок, runtime/аппаратных тестов, правок backend/SDK или push нет.** Прежние software/package/build reports сохранены как история подготовки, не переписаны в аппаратный PASS.
