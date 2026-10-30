# Dead Space Mobile → New Nintendo 3DS

Экспериментальный порт Android ARM32-библиотеки Dead Space Mobile. **Играбельной сборки пока нет.** Исходники оригинального движка отсутствуют; проект реализует загрузчик ELF и необходимые сервисы Android/JNI для выбранного SD-донора 1.1.33.

**В Azahar сохранены настоящие игровые кадры CPU renderer и PICA200**, включая вступительную сцену и меню Normal/Easy. CPU baseline прошёл552 ARM-теста; подробные ограничения и результаты GPU-последовательностей сохранены в HANDOFF. Управляемый gameplay, звук и аппаратная игровая CIA пока не подтверждены.

**Аппаратный статус30.10.2026:** официальный Citro3D simple_tri RGBA8→RGB8 показал треугольник и нормально вышел как через HBL, так и в CIA с нашим профилем. Изолированный RGB8→RGB565 вариант дал тонкую голубую полоску и зависание с необходимостью POWER, хотя Azahar прошёл. Это воспроизводит сбой без DS34 и его диагностической обвязки, но не определяет конкретную причину среди framebuffer/fill/transfer/completion. Повторять неработающие тесты не нужно. Сравнение: [stock CIA PASS](porting/analysis/hardware/official-simple-tri-profile-cia-v0.1.0-user-result.json), [RGB565 CIA FAIL](porting/analysis/hardware/simple-tri-rgb565-v0.1.0-user-result.json). Следующий RGB8→RGB8 эксперимент пока только запланирован.

![Настоящее меню Azahar: выбран Easy после касания](porting/analysis/menu-frame/easy.png)

Продолжение: **[HANDOFF.md](HANDOFF.md)**. Текущие адаптеры: [LIGHTING.ru.md](porting/LIGHTING.ru.md), [DEFAULT-SURFACE.ru.md](porting/DEFAULT-SURFACE.ru.md). Машинные сводки: [lighting-result.json](porting/analysis/lighting-result.json) и [engine-progress.json](porting/analysis/engine-progress.json).

Первый логотип EA описан в [FIRST-FRAME.ru.md](porting/FIRST-FRAME.ru.md). Legacy profile124MiB сохранён; расширенный178MiB включает128MiB donor arena. Strict preflight154/234/4 и прежний аппаратный RX backend сохранены. Новые адаптеры включаются явно. Частичная геометрия и законченный чёрный кадр хранятся раздельно; завершение callback не считается доказательством работающего игрового процесса.

Готовы [нижний HID-слой](porting/SENSOR-BACKEND.ru.md) и [его JNI-интеграция](porting/SENSOR-JNI.ru.md). Отдельная native-проверка Azahar получила 40 показаний. Аппаратные оси и калибровка пока не подтверждены. GitHub обновляется только по явной просьбе пользователя.

В репозитории находятся собственные исходники, инструменты сборки, тесты, инструкции и журналы. Выбранные исходники официальных devkitPro simple_tri/immediate сохранены с upstream URL/commit/SHA256 и Public Domain README для сравнения. APK, оригинальная игровая библиотека, извлечённые ресурсы, toolchain, полные сторонние проекты, эмулятор и его виртуальная SD **не загружаются**. Они остаются в исходной локальной папке. Это резервная копия разработки, не дистрибутив игры.

Рабочая среда: Windows/PowerShell, Python, локальный devkitARM 16.1/libctru 2.7.0, Unicorn 2.1.4 и Azahar libretro 2126.2. Зависимости Python перечислены в [requirements-tools.txt](porting/requirements-tools.txt). При свежем клонировании потребуются собственные игровые файлы и восстановление локальных зависимостей; одних файлов Git для запуска тестов недостаточно. Исторические результаты сохранены как свидетельства, а не как обещание сборки в произвольной среде.
