# simple_tri RGB8 → RGB565 v0.1.0

Диагностический вариант официального devkitPro simple_tri, который уже показал треугольник и вышел по START на настоящей New3DS в форматах3DSX и CIA. **Этот RGB565-вариант пока проверен только в Azahar. Аппаратный запуск требует отдельного согласования.** Это не исправление DS34 и не игровой билд.

Гипотеза: прежние native DS34/Control могли останавливаться из-за отличия RGB8→RGB565 от успешно проверенного RGBA8→RGB8. В этом варианте сохранены геометрия, тот же shader object, SDK, SYNCDRAW, draw, FrameEnd, штатные обработчики, профиль CIA и отсутствие диагностической обвязки. Runtime разница ограничена:

- Render target240×400 RGB8 вместо RGBA8, depthD24S8 прежний.
- TOP LCD RGB565 вместо RGB8; переключение после gfxInitDefault, без дополнительного swap/wait, без уменьшения исходного gfx allocation.
- Transfer RGB8→RGB565, flags0x2100 вместо0x1000.
- Clear color0x0068B0D8 вместо0x68B0D8FF: та же RGB(104,176,216), упакованная под RGB8. Отбрасывание alpha без перепаковки изменило бы цвет фона.

Color buffer288000 bytes, depth384000; SDK fill controls0101/0201. Это проверка согласованной комбинации форматов, **не отдельная проверка только FILL или только DISPLAY**. Здесь по-прежнему есть triangle draw; успех не докажет работоспособность прежней CLEAR-only очереди или всего DS34.

TitleID **000400000FDE6B00**, ProductCTR-H-C3DF, version1, имя в HOME Menu **tri RGB565 v0.1.0**. Отдельная Application, не заменяет работающий stock FDE6A или прежние FDE68/FDE69. Capabilities, Legacy64MB/stack256KiB/CPU VRAM read-only совпадают со stock, кроме ID. Записи прошивки, NAND или постоянных системных настроек в изменённый код не добавлялись.

После отдельного разрешения **одного** аппаратного запуска:

1. Скопировать `simple-tri-rgb565.cia` на SD и установить через FBI → SD → файл → Install CIA.
2. Вернуться в HOME Menu, выбрать именно **tri RGB565 v0.1.0**. GPU стартует сразу, **без A gate и без timeout**.
3. Ожидается белый треугольник на голубом фоне сверху. Сфотографировать оба экрана; нажать START один раз, отметить возврат в HOME Menu.
4. При зависании выключить удержанием POWER; **не повторять запуск**. Передать фото, факт появления треугольника, результат START и необходимость POWER.

Пример **не пишет control.log/result.json на SD**. Возможен полный hang; Azahar PASS не гарантирует безопасности на железе. Другие тесты из старых архивов вслед за этим запускать не нужно.

Интерпретация: PASS покажет, что эта комбинация форматов работает в stock-style draw loop; дальше нужно изолировать различия CLEAR-only/polling/wrappers/console/SD. FAIL при прежнем stock PASS укажет на отличие конфигурации форматов и подготовки framebuffer, но не определит конкретно FILL, DISPLAY или IRQ delivery. Не менять SDK/permissions/игровой backend по одному фото.

В validation: единственный короткий Azahar2126.2 software LCD run actual CIA payload, observations60/90/120. Получены16000 белых,79999 RGB(107,178,222) пикселей и прежний чёрный угол(399,0); причина угла не выяснена. Квантование RGB565 проверено, PNG просмотрен. Host invalid-access messages0; штатные Azahar service stubs остаются. После START наблюдались guest GSP ReleaseRight и heap free; libretro shutdown callback не пришёл. Native IRQ/queue counters не добавлялись. Реальная установка FBI эмулятором не проверена.

В архиве одна CIA, README/license, source/reference, точный diff, manifest и выбранная validation. Оригинальных ресурсов игры, APK/.so, DS34, SDK, ELF, fault binary нет. Upstream commitbe2001fee08cf8ec7d3366e095e83f6f75da8942; Public Domain README и Citro3D license приложены. Рабочие stock/CPU/GPU baseline сохранены.

Подготовка из репозитория:

```powershell
python porting/tools/build_simple_tri_rgb565.py
python porting/tests/smoke_simple_tri_rgb565.py
python porting/tools/package_simple_tri_rgb565.py
```
