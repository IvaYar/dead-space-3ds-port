# Первый настоящий кадр: логотип EA в Azahar

28 октября 2026 года достигнута контрольная точка **вывода изображения игры**. Оригинальный SD-движок завершает восемь `NativeOnDrawFrame`; его вызовы GLES рисуют логотип EA, кадр отправляется на виртуальный LCD Azahar. Это программный рендер вызовов игры, а не показ заранее подготовленной картинки.

![Логотип EA, кадр 8](analysis/first-frame/first-game-frame.png)

Также сохранён [снимок обоих экранов самого эмулятора](analysis/first-frame/azahar-screen.png). Меню, игровой процесс, управление и звук ещё не подтверждены. Устанавливаемая CIA для этого продолжения не создавалась; на настоящей консоли новый runtime пока не проверяется.

## Доказательство кадра

| Показатель | Результат |
| --- | --- |
| Эмулятор | Azahar libretro 2126.2, New3DS |
| Размер верхнего экрана |400×240, RGB565|
| Завершённый callback снимка | NativeOnDrawFrame №8 |
| Оригинальный caller draw | offset `003244e0` выбранного donor ELF |
| Накопленные draw calls / triangles |15 /30|
| Прошедшие фрагменты / texture samples |629370 /251370|
| Размер raw / CRC32 |192000 bytes / `f25373dd`|
| Рабочие потоки самого движка |6 запущены|
| Оригинальные acceleration callbacks |6 вернулись, датчик выключен с result0|
| Ошибка GLES на контрольной точке |0|

Журнал — `analysis/azahar-smoke/engine-graphics.log`; результат с SHA текущей CXI — `engine-graphics-result.json`. `analysis/first-frame/` содержит raw framebuffer, метаданные, PNG без диагностического текста и снимок LCD. `tools/check_first_frame.py` проверяет hashes, завершение callbacks, счётчики, CRC raw и декодирование PNG. Снимок LCD совпадает с реконструированным буфером с допуском1 для расширения RGB565 и наблюдаемым смещением представления на одну строку; сами PNG при проверке не изменяются. Машинный итог — `analysis/first-frame-result.json`.

Первая версия кадра №2 показывала начало fade-in и была очень тёмной. На №8 логотип уже читается. Diagnostic console/probe pixels очищаются из обоих буферов перед запуском игры; последующие сообщения идут только в файл. Перед остановкой выполняются cache flush, swap и ожидание VBlank.

## Что позволило пройти запуск

**Память и стек.** Emulator CXI теперь использует New3DS `SystemModeExt: 124MB`, что подтверждено native-отчётом130023424 bytes памяти приложения. Два donor arenas имеют размеры20+80MiB; mmap остаётся private anonymous RW, с проверкой границ. Main stack libctru явно увеличен до256KiB: один RSF StackSize не задавал размер перемещённого в heap стека CRT. Основной поток после инициализации сервисов получает обычный native priority0x30; pthread workers наследуют приоритет создателя и получают yield после успешного создания.

Большой шрифт загружается повторно, а растущие файловые буферы временно живут одновременно. При map64MiB свободная память могла быть раздроблена: новый непрерывный блок19MiB не помещался. При80MiB эта ветка проходит без отказов. На последнем проверенном снимке: break16781312 bytes,8908 mapped pages, map peak16927 pages; запущенные workers могут влиять на пиковые значения и число texture uploads. Это статистика arenas, не измерение полного расхода процесса. Профиль Java GetTotalRAM по-прежнему сообщает прежний compatibility budget64MiB; физическая RAM консоли этим свойством не измеряется.

**Каталоги.** Исправлены корни `appdata:/`, допускается один дополнительный разделитель, который генерирует игра (`appdata://var`). Traversal и неизвестные mounts не разрешаются. `stat("/")` обращается к реальному каталогу приватного виртуального mount; отсутствующий корень раньше вызывал бесконечную рекурсию поиска родительского каталога и переполнение стека. Внешние cache root, `published` и `Downloaded.indicate` отображаются на существующее дерево ресурсов. `mkdir` пишет только в отдельный `test-output/` эмулятора.

`ds20_dirs.c/h` предоставляет opaque directory handles, `opendir`, `readdir_r`, `closedir` и opt-in binding mkdir. Native `DIR` не передаётся движку. Bionic ARM dirent имеет размер280 bytes и d_name по offset19; inode/offset64-bit, тип и имя пакуются отдельно. Проверены EOF, ошибки, capacity8, stale handles, сохранность выходного буфера при ошибках. ABI сверялся с [AOSP Gingerbread dirent.h](https://raw.githubusercontent.com/aosp-mirror/platform_bionic/android-2.3.3_r1/libc/include/dirent.h).

**Матрицы и рисование.** `ds21_matrices.c/h` добавляет modelview/projection/texture matrices, раздельные стеки, load/multiply, translate/scale/rotate и ortho/frustum в float/fixed вариантах, а также getters. `ds22_draw.c/h` исполняет unlit triangles/list/strip/fan, clip в однородных координатах, viewport/scissor, цвета, nearest/bilinear texture sampling, простые texture environments, alpha test и blending. Работают client arrays и element buffers; все ссылки проверяются до изменения пикселей. Поверхность имеет цвет и не имеет depth/stencil attachments.

Для native client pointers регистрируются собственные readable mappings процесса: donor image/arenas и RW mapping, содержащий стек. Horizon объединяет heap и перемещённый стек в один большой регион; query показывает реальную доступную границу, а не отдельную object allocation. Время жизни client pointer остаётся обязанностью GL caller. Неподдерживаемые состояния останавливают диагностику, а не возвращают фиктивный успех.

Всего **99 opt-in GLES bindings и4 filesystem bindings**. Strict ELF preflight остаётся **154 resolved /234 missing /4 weak-zero**, поскольку эти дополнительные профили не включены в production registry. Неполная обычная привязка по-прежнему отказывается изменять image. Старый hardware RX/cache backend, page limit и entire I-cache SVC0x94 не менялись.

## Проверки и границы результата

Прошёл **331 core ARM-тест**, включая30 новых проверок директорий/матриц/реальных пикселей; прежние14 isolated sensor-тестов относятся к другому ELF и имеют отдельный checker. Для текущей CXI проходят все9 engine-сценариев Azahar. Guarded baseline/sensor/graphics CPU audits тоже повторены. `check_engine_progress.py`, `check_sensor_progress.py` и `check_first_frame.py` проходят.

CPU graphics audit намеренно сохраняет маленькие20+20MiB arenas и останавливается на первом отказе памяти. Это тест guard-профиля; он **не означает**, что native-путь всё ещё не прошёл шрифт. `run_worker_experiment.py` — дополнительная исследовательская модель initial worker slices; она не является полноценным scheduler и не заменяет native-проверку. Старые memory/worker experiment JSON — исторические эксперименты с собственными core hashes, а не свидетельства текущего успешного кадра.

Есть известное JNI-ограничение: при загрузке один outstanding string loan вызывает отказ PopLocalFrame. На снимке pending=1, failures=4, frame-depth=1, string-loans=1. Три прочие ошибки относятся к ожидаемым fallback-обращениям к отсутствующим bootstrap assets. Кадры3–8 и callbacks датчика возвращаются, но loan и один frame остаются удержанными. Нельзя называть JNI полностью исправленным; следующий шаг — выяснить lifetime конкретной строки и корректно обработать его, не освобождая borrowed bytes преждевременно.

Renderer пока **CPU**, без PICA200 acceleration. Lighting, fog, custom FBOs, mipmap sampling, различающиеся min/mag filters и texture combiners явно не поддерживаются. Assets read-only; fd-based appdata reads/writes, APK bootstrap assets и полноценные сохранения требуют продолжения. Производительность и физическая калибровка датчика не измерены. Движок останавливается после первого наглядного кадра; это не готовый игровой порт.

## Продолжение

Сначала исправить оставшийся JNI loan/frame lifetime и проверить более длинный запуск до меню, затем недостающие GLES состояния, сохранения, управление/звук и ускорение. Не заменять unknown APIs успешными заглушками. Hardware stage8 и исходные APK/ZIP/.so/шрифты не изменять; новую SD-проверку сейчас не просить.

Быстрая проверка уже собранного состояния из корня:

```powershell
python porting/tools/check_engine_progress.py
python porting/tools/check_first_frame.py
python porting/tools/check_sensor_progress.py
```

Повторное получение изображения:

```powershell
python porting/tests/smoke_engine_azahar.py --case graphics
python porting/tools/export_native_frame.py
Copy-Item porting/analysis/azahar-smoke/engine-graphics-screen.png porting/analysis/first-frame/azahar-screen.png
python porting/tools/check_first_frame.py
```

Azahar-сценарии выполнять последовательно: они используют одну приватную SD. После rebuild нужно обновить привязанные к ELF/CXI результаты тестов до checker. Для зависшего исследования есть `capture_native_stop.py --frame 8`: он изолирует DLL в отдельном процессе и явно не объявляет checkpoint проверенным. В репозиторий добавлены код и доказательство кадра игры Electronic Arts; коммерческие APK, donor .so, шрифты, cache и toolchain остаются локально.
