# Экран с персонажем, наушниками и читаемым текстом

**Продолжение:** [INPUT-SAVES.ru.md](INPUT-SAVES.ru.md) —240 кадров с original pointer events и приватными descriptor saves,368 core-тестов. Найден реальный APK bootstrap namespace, который нынешний AssetManager пока обслуживает неполно. Три fallback errors ниже не означают, что файлы отсутствуют в оригинальном APK. Ниже сохранён предыдущий120-frame checkpoint.

28 октября 2026 года оригинальный SD-движок прошёл120 кадров в Azahar. После логотипа EA появился следующий экран: персонаж, значок наушников и надпись «Use headphones for the best experience».

![Кадр120 из буфера оригинальных GLES-вызовов](analysis/headphone-frame/first-game-frame.png)

Это сохранённый framebuffer, нарисованный вызовами игры через наш CPU renderer. Также проверен [снимок LCD эмулятора](analysis/headphone-frame/azahar-screen.png). Главное меню, игровой процесс и звук пока не подтверждены. Новой CIA нет; на приставке этот runtime не проверялся.

## Исправления

**JNI lifetime.** Диагностика показала, что оставшийся borrow относится к строке версии `1.1.33 Universal SD (Default)`. Игра получает указатель, затем уничтожает локальную ссылку закрытием frame. Других JNI-ссылок на эту строку не остаётся. Раньше адаптер отказывал в PopLocalFrame и устанавливал исключение.

Теперь удаление ссылки отделено от освобождения payload: заимствованные UTF-8/UTF-16/critical представления сохраняют память. Local frame закрывается нормально; устаревший handle остаётся недействительным. При наличии живого alias через него можно выполнить Release. При отсутствии alias payload остаётся до cleanup после остановки всех пользователей. Это следует из [контракта JNI для raw data pointers](https://developer.android.com/ndk/guides/jni-tips); указатель не является локальной ссылкой.

Удержание применяется и к строкам из String[]: удаление/замена элемента или всего массива не освобождает заимствованный payload. Это исправляет возможное преждевременное освобождение. Прежние ограничения pool/capacity сохраняются. Один version-string loan по-прежнему существует; нельзя утверждать, что игра его освободила, или преждевременно освобождать его данные. Ограничение для копий byte arrays этим изменением не снималось.

На кадрах8 и120: pending=0, failures=3, refs=11, frame-depth=0, string-loans=1. Три зарегистрированные ошибки относятся к прежним fallback-запросам отсутствующих bootstrap assets; pending exception к контрольной точке отсутствует. На кадре120 закрываются все120 frames, выполнены118 оригинальных acceleration callbacks и запущены6 рабочих потоков.

**Шрифт и текстуры.** ALPHA-текстура должна сохранять RGB исходного цвета в REPLACE/MODULATE/BLEND/ADD; раньше MODULATE умножал цвет на нулевые служебные RGB-компоненты CPU-store. Исправлен shader step согласно таблицам3.15/3.16 [OpenGL ES1.1](https://registry.khronos.org/OpenGL/specs/es/1.1/es_full_spec_1.1.pdf). Новый ARM-тест проверяет реальные пиксели с alpha coverage и blending для четырёх режимов.

Кроме того, атлас256×256 ALPHA выводил общий canonical RGBA store на2097156 bytes — на4 bytes больше прежнего лимита2MiB. Он не загружался с GL_OUT_OF_MEMORY. Только emulator profile получил лимит текстур6MiB и tracked runtime heap8MiB; стандартный DS15 limit2MiB и OOM-тесты сохранены. Upload trace различает отказ бюджета и отказ allocator. На проверенном кадре:5 texture names,7 uploads,2097156 bytes, без отказов uploads и с GL error0. Аппаратный memory profile не менялся.

## Свидетельства

Прошли **336 core ARM-тестов**:24 string,28 asset и31 directory/matrix/draw, включая новые проверки lifetime и glyph coverage; остальные suites повторены для той же core-сборки. Дополнительно актуальны14 isolated sensor-тестов другой сборки. Для текущей CXI прошли9 штатных Azahar cases; guarded CPU baseline/sensor/graphics audits также повторены.

Длинный120-frame запуск использует exploratory runner; его флаг checkpoint_validated остаётся false. Отдельный `check_headphone_frame.py` проверяет именно этот результат: текущие source/core/CXI hashes, завершение каждого callback1–120, GL/JNI состояние, metadata/log agreement, CRC raw, точное декодирование PNG и соответствие настоящему LCD. Итог — [headphone-frame-result.json](analysis/headphone-frame-result.json), passed=true. Снимок визуально проверен. Размер400×240 RGB565, CRC32 `71a807c1`,305 draws,5506 triangles,10296650 passed fragments,3870650 texture samples. Меню этим checker не объявляется подтверждённым.

У более ранней попытки цель300 callbacks упёрлась в watchdog, а ещё одна попытка с увеличенным бюджетом не дошла до stop за лимит runner. Эти попытки не выдаются за успешные проверки. Успешный повтор120 кадров сохранён отдельно с собственной цепочкой hashes. Для более длинного запуска потребуется заново согласовать лимиты runner и watchdog.

Число ранних EA draw calls может отличаться на один из-за момента завершения texture workers. Проверки кадра8 сверяют metadata с журналом, наличие существенного объёма настоящих текстурированных draws и raw/PNG/LCD; они больше не требуют одного фиксированного расписания потоков. Текущий кадр8:14 draws/28 triangles; исторический первый checkpoint15/30 описан в FIRST-FRAME.ru.md.

## Проверка и продолжение

```powershell
python porting/tools/check_first_frame.py
python porting/tools/check_headphone_frame.py
python porting/tools/check_engine_progress.py
python porting/tools/check_sensor_progress.py
```

Повтор длинного снимка — последовательно, без другого Azahar процесса на общей SD:

```powershell
python porting/tests/smoke_engine_azahar.py --case graphics --explore --capture-frame 120
python porting/tools/export_native_frame.py --output-directory porting/analysis/headphone-frame
Copy-Item porting/analysis/azahar-smoke/engine-graphics-explore.log porting/analysis/headphone-frame/engine-frame120.log
Copy-Item porting/analysis/azahar-smoke/engine-graphics-explore-result.json porting/analysis/headphone-frame/engine-frame120-result.json
Copy-Item porting/analysis/azahar-smoke/engine-graphics-screen.png porting/analysis/headphone-frame/azahar-screen.png
python porting/tools/check_headphone_frame.py
```

Следующая работа: выяснить переход после headphones screen, продлить запуск в согласованных границах времени и наблюдать реальные запросы движка. Ввод, звук, остальные GLES состояния, сохранения и ускорение PICA200 остаются в работе. Произвольные заглушки успеха не добавлять. Hardware stage8 RX/cache, оригинальные APK/.so/cache не менялись. GitHub обновлять только по новому явному запросу.
