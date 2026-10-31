# Dead Space Mobile → New Nintendo 3DS

Экспериментальный порт Android ARM32-библиотеки Dead Space Mobile. **Играбельной сборки пока нет.** Исходники оригинального движка отсутствуют; проект реализует загрузчик ELF и необходимые сервисы Android/JNI для выбранного SD-донора 1.1.33.

**В Azahar сохранены настоящие игровые кадры CPU renderer и PICA200**, включая вступительную сцену и меню Normal/Easy. CPU baseline прошёл552 ARM-теста; подробные ограничения и результаты GPU-последовательностей сохранены в HANDOFF. Управляемый gameplay, звук и аппаратная игровая CIA пока не подтверждены.

**Аппаратный статус31.10.2026:** DS34 с исправленными UV-масками прошёл полный путь RGBA8→RGB8, GPU completion, pixel check и возврат HOME. Отдельные startup-тесты с тем же ELF и кучами2+2MiB прошли main/READY/START/HOME в Legacy64 и **New3DS Prod124MiB**. Dev1178MiB зависает до наблюдаемого READY; точная причина ещё не установлена. [DS34 hardware PASS](porting/analysis/hardware/ds34-uv-mask-v0.2.1-user-result.json), [Prod124 hardware PASS](porting/analysis/native-startup-prod124-v0.1.0/hardware-report.ru.md).

Оригинальный кадр через отдельный native entry point совпадает с GPU baseline в Azahar, все шесть donor-потоков кооперативно завершаются, safe_exit PASS. Игровая CIA h2 с резервом172MiB пока получила аппаратный FAIL; аппаратный оригинальный игровой кадр не подтверждён. Следующая работа — отдельная программная проверка игрового бюджета под124MiB с сохранением GPU backend и safe_exit. [Native game](porting/3ds/README-native-game.ru.md), [измерения памяти](porting/analysis/native-game-memory-v0.1.0/report.ru.md).

![Настоящее меню Azahar: выбран Easy после касания](porting/analysis/menu-frame/easy.png)

Продолжение: **[HANDOFF.md](HANDOFF.md)**. Текущие адаптеры: [LIGHTING.ru.md](porting/LIGHTING.ru.md), [DEFAULT-SURFACE.ru.md](porting/DEFAULT-SURFACE.ru.md). Машинные сводки: [lighting-result.json](porting/analysis/lighting-result.json) и [engine-progress.json](porting/analysis/engine-progress.json).

Первый логотип EA описан в [FIRST-FRAME.ru.md](porting/FIRST-FRAME.ru.md). Аппаратно проверенный Prod124 startup сохранён отдельно; прежний игровой вариант178MiB включает128MiB donor arena. Strict preflight154/234/4 и прежний RX backend сохранены; аппаратные RX/cache semantics оригинального игрового запуска ещё не подтверждены. Новые адаптеры включаются явно. Частичная геометрия и законченный чёрный кадр хранятся раздельно; завершение callback не считается доказательством работающего игрового процесса.

Готовы [нижний HID-слой](porting/SENSOR-BACKEND.ru.md) и [его JNI-интеграция](porting/SENSOR-JNI.ru.md). Отдельная native-проверка Azahar получила 40 показаний. Аппаратные оси и калибровка пока не подтверждены. GitHub обновляется только по явной просьбе пользователя.

В репозитории находятся собственные исходники, инструменты сборки, тесты, инструкции и журналы. Выбранные исходники официальных devkitPro simple_tri/immediate сохранены с upstream URL/commit/SHA256 и Public Domain README для сравнения. APK, оригинальная игровая библиотека, извлечённые ресурсы, toolchain, полные сторонние проекты, эмулятор и его виртуальная SD **не загружаются**. Они остаются в исходной локальной папке. Это резервная копия разработки, не дистрибутив игры.

Рабочая среда: Windows/PowerShell, Python, локальный devkitARM 16.1/libctru 2.7.0, Unicorn 2.1.4 и Azahar libretro 2126.2. Зависимости Python перечислены в [requirements-tools.txt](porting/requirements-tools.txt). При свежем клонировании потребуются собственные игровые файлы и восстановление локальных зависимостей; одних файлов Git для запуска тестов недостаточно. Исторические результаты сохранены как свидетельства, а не как обещание сборки в произвольной среде.
