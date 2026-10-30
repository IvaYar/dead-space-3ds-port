# Официальный devkitPro simple_tri — контроль v0.1.0

Подготовлен к отдельному согласованию аппаратного испытания. **На настоящей3DS не запускался. Не является исправлением GPU или игрой.** Azahar PASS не гарантирует работу на приставке; предыдущие control зависали. Эта версия сохраняет upstream без защитных изменений: GPU стартует сразу, A gate, timeout, SD logger и PSC observer отсутствуют. Возможен полный зависон с необходимостью удерживать POWER. Не запускать оба варианта подряд как автоматический набор.

`main.c` и shader побайтно соответствуют devkitPro/3ds-examples commit **be2001fee08cf8ec7d3366e095e83f6f75da8942**. SDK прежний: libctru2.7.0/Citro3D1.7.1. Один и тот же ELF упакован двумя способами:

- `3dsx/simple_tri.3dsx`: стандартный формат для Homebrew Launcher. Предлагаемый первый отдельный тест.
- `cia-same-profile/simple_tri-profile.cia`: дополнительный вариант с профилем прежнего control — Legacy64MB, stack256KiB, CPU VRAM read-only. **TitleID000400000FDE6A00**, ProductCodeCTR-H-C3DT, version1. Это отдельное Application, не заменяет DS34/FDE6800 или Control/FDE6900, не системный title. Access/kernel/ARM9 capabilities совпадают с control, кроме program ID. У самого официального примера собственного CIA/RSF нет. Этот вариант требует отдельного согласования, не устанавливать для первого3DSX теста.

После разрешения одного3DSX запуска:

1. Скопировать `simple_tri.3dsx` в `SD:/3ds/official-simple-tri/simple_tri.3dsx`. CIA для этого не нужна.
2. Открыть через Homebrew Launcher. Отрисовка начинается сразу. На верхнем экране ожидается белый треугольник на голубом фоне; нижний экран не содержит диагностического меню.
3. Сделать фото, нажать START один раз, отметить возврат в HBL или зависание. При зависании после восстановления не повторять автоматически запуск.
4. Передать фото, модель приставки, способ запуска и версию HBL/CFW, факт появления треугольника и результат START. **Новых control.log/result.json на SD этот upstream пример не создаёт.** Старые журналы других версий не относятся к этому запуску.

Если3DSX работает, базовый SDK-путь на этой среде подтверждён; следующий отдельно разрешённый запуск того же ELF в CIA сможет проверить влияние установленного приложения и профиля. Такая пара не выделяет только объём памяти: loader задаёт также права и адреса. Если3DSX не работает, результат не определяет конкретно FILL, DISPLAY или доставку IRQ. Не следует сразу менять backend/VRAM permissions; для IRQ уже подготовлен отдельный control observer v0.1.1.

В `validation` результаты Azahar software renderer, фотографии frontend observations60/90/120, сравнение и проверка контейнера. Оба формата показали одинаковую картинку:16000 белых/79999 голубых пикселей и один чёрный в углу(399,0), причина последнего не установлена. START привёл к guest GSP ReleaseRight/free heap; libretro shutdown signal отсутствовал. Недопустимых обращений к памяти в журнале0; прочие service stubs эмулятора остаются. CIA проверялась как extracted NCCH payload, установка через FBI не выполнялась.

Архив содержит только контрольные binaries, сохранённые upstream source/Makefile/README, license, manifest и выбранные результаты. APK, `.so`, игровые ресурсы, оригинальный движок, DS34 и SDK дистрибутив отсутствуют. Полное сравнение и ограничения — `validation/comparison.md`.

Воспроизводимая подготовка (эмуляторные проверки, без аппаратного запуска):

```powershell
python porting/tools/build_official_simple_tri.py
python porting/tests/smoke_official_simple_tri.py --format 3dsx
python porting/tests/smoke_official_simple_tri.py --format cia
python porting/tools/package_official_simple_tri.py
```

Источник примера и Public Domain Mark: https://github.com/devkitPro/3ds-examples/tree/be2001fee08cf8ec7d3366e095e83f6f75da8942/graphics/gpu/simple_tri ; upstream README сохранён. Citro3D LICENSE приложен.
