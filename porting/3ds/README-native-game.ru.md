# DS Native Game 0.1.0 — один оригинальный кадр, эксперимент для New 3DS

**Актуально01.11.2026:** аппаратная0.1.1 устранила случайный фон, но завершила600callbacks с CRC_FAIL и перешла в STOPPED без обработки кнопок. Original rendering есть, полный frame/safe_exit PASS пока нет. [Последний разбор](../analysis/native-game-target-init-v0.1.1/hardware-report.ru.md). Следующие абзацы описывают историю предыдущих сборок.

**Последние аппаратные Prod124 run-0002/run-0003:** оригинальный код/RX/209конструкторов и389/306draw callbacks выполнены, видны EA и Айзек. Шум вне рисунка мешает full-frame gate; safe_exit и HOME не достигнуты. [Разбор](../analysis/native-game-prod124-v0.1.0/hardware-runs-0002-0003.ru.md). Подготовлен программно проверенный отдельный [DS Game Init0.1.1](README-native-game-target-init.ru.md) с однократной очисткой color target, ожидающий отдельного разрешения на hardware test. Ниже сохранена история предыдущих этапов; исходнаяh2 не менялась.

**Новый отдельный профиль Prod124 программно проверен:** [DS Game Prod124 / CIA и инструкция](README-native-game-prod124.ru.md). Heaps20+100MiB, arena92MiB, commit120,746MiB; оригинальный кадр и safe_exit прошли3CXI+3CIA-payload цикла. Начальный известный host crash Azahar сохранён отдельно. Аппаратного game PASS пока нет. Этот документ ниже описывает сохранённую старуюh2/FDE7100, её размеры172MiB не уменьшались; новый titleFDE7300 её не заменяет.

**[Startup Prod124](README-native-startup-prod124.ru.md) получил аппаратный PASS main/READY/START/HOME**, actual limit124MiB подтверждён в run-0003. Это была база отдельной программной проверки игрового бюджета124; дальнейшая аппаратная оригинальная отрисовка описана выше. [Измерение checkpoint](../analysis/native-game-memory-v0.1.0/report.ru.md) показало donor sbrk≈16MiB и normal malloc≈12,5MiB при прежнем process commit172,75MiB. Основнаяh2/heap/arena/backend не менялись. [Аппаратный отчёт Prod124](../analysis/native-startup-prod124-v0.1.0/hardware-report.ru.md).

**Legacy startup получил аппаратный PASS main/READY/START/HOME:** [отчёт](../analysis/native-startup-legacy-v0.1.0/hardware-report.ru.md). Тот же ELF2+2MiB, kernel2.44/SVC/code сохранены, менялся только New3DS memory mode. Подтверждён реальный limit64MiB. Смена режима устранила симптом малого теста; Legacy не вместит нынешние172MiB игры. Следующий приоритет — совместимый расширенный профиль. Игровая CIA не исправлялась и её аппаратный FAIL остаётся открытым.

**Обновление аудита памяти:** 40+132MiB подтверждены в ELF; реальная CIA заявляет New3DS178MiB. С учётом image/stack и модельного TLS-допуска остаётся около5,25MiB, поэтому превышение пока не доказано. Игровая CIA не изменена. Отдельный [startup-only тест2+2MiB](README-native-startup.ru.md) с тем же профилем178MiB **тоже получил аппаратный FAIL**, папки нет. Следующий приоритет — профиль/ранний startup; размер172MiB не объясняет оба случая. [Разбор нового FAIL](../analysis/native-startup-hardware-fail-v0.1.0/report.ru.md), [прежний расчёт бюджета](../analysis/native-startup-memory-v0.1.0/report.ru.md).

**Актуальный аппаратный результат: FAIL.** Пользователь сообщил о зависании до намеренного нажатия A: оба экрана остались чёрными, READY не появился, кнопки не реагировали; консоль выключена удержанием Power. Затем подтвердил: **диагностической папки на SD нет**. Причина пока не установлена. **Повторный запуск h2 пока не выполнять; отсутствующие логи повторно не запрашиваются.** В готовом ELF проверяется ранний startup, включая резервирование172MiB до main и отличие профиля178MiB от аппаратно успешного DS34 Legacy/64MiB. Это гипотеза, а не установленная причина. [Запись аппаратного результата](../analysis/hardware/native-game-v0.1.0-h2-user-result.json), [разбор раннего startup](../analysis/native-game-h2-user-hang/report.ru.md).

CIA исполняет оригинальный ARM-код и его draw callbacks; изображение из файла/видеозаписи в приложение не загружается. Checkpoint — исходный экран с Айзеком и рекомендацией использовать наушники, ещё не управляемая 3D-сцена. Ни запуск donor, ни достижение кадра в этом аппаратном испытании пока не подтверждены.

Название в HOME: **DS Native Game 0.1.0**. Title ID **`000400000FDE7100`**, product code `CTR-H-DSNG`. Файл `native-game.cia`, 336320 bytes, SHA256:

```text
90fb19919c1b132e30fed0936802375d2ccecfdbb7d9c504d5edbef131d35622
```

Сборка: `porting/3ds/build-native-game-v0.1.0-h2/`. Распространяемый локальный пакет: `porting/dist/native-game-v0.1.0.zip`. **В CIA/ZIP нет APK, оригинальной `.so`, игровых ресурсов, derived font или изображения оригинального кадра.** Встроены только port runtime, DS34/backend/shader и собственные HOME icon/banner metadata.

## Что проверено

RGBA8 → RGB8/flags1000, TOP BGR8/288000 bytes, UV shader и код GPU/thread adapters побайтно совпадают с safe_exit baseline s16. Оригинальный код сам строит кадр; CRC `ea733050` только выбирает известный момент остановки, максимум600 callbacks. Baseline picture не является входом renderer.

Финальный h2 прошёл девять циклов в Azahar2126.2: три CXI, три payload, извлечённого **из собранной CIA**, и три `.app`, **установленного штатным `Azahar --install` из этой CIA**. Все96000 pixels после BGR8→RGB565 совпали с GPU baseline, GLES0, failed submits0, шесть kernel exits/0handles, JNI/files cleanup, GPU completion/ReleaseRight и освобождение обоих heap. START действительно завершал guest до host unload. Аппаратные RX/cache semantics Azahar не проверяет.

В раннем h1 один раз упал **host** `azahar_libretro.dll`, access violation `0xc0000005`, RVA326ccf, на третьей загрузке. Guest exception не зафиксирован; точная причина не доказана. Сбой не повторился при повторных трёх h1 cycles и девяти финальных h2 cycles. Он сохранён в отчёте и не объявляется исправленным core bug.

## Какие файлы нужны на SD

Подготовленная **приватная** папка на этом компьютере:

```text
porting/private/native-game-v0.1.0-sd/
└── 3ds/deadspace/
    ├── libEAMGameDeadSpace_orig.so
    ├── assets-verified.txt
    ├── apk-assets-verified.txt
    ├── assets/                         # 1728 файлов, сохранённое дерево assets/published/...
    ├── apk-assets/                     # 20 извлечённых APK assets, в том числе EAMCore.ini
    └── test-output/font-subset/Ascender_Uni.ttf
```

Всего1752 файла/583364704 bytes; все скопированные игровые assets сверены SHA256 с прежней verified private SD. `.so` —4499468 bytes, CRC32 `9fd95635`; derived font —47036 bytes, CRC32 `71dcae12`; EAMCore.ini —3119 bytes, CRC32 `33c9beb3`. Раскладка должна совпадать, receipts нельзя заменять фиктивными строками. Сам APK на SD не нужен.

Копируется каталог **`3ds` в корень SD**, чтобы пути стали `SD:/3ds/deadspace/...`. Используются только уже локально предоставленные файлы пользователя. Не публиковать `private/`, его архив или содержимое SD. При наличии этих путей на карте сначала сравнить файлы; отличающиеся originals/baseline не перезаписывать. CIA можно положить в `SD:/cias/native-game.cia`.

Нужна New Nintendo3DS/2DS family с Luma3DS kernel extension (ABI проверен по исходникам v10.0 иv13.3; bootstrap требует ≥10.0), SD с доступом на запись и свободным местом для служебных данных/логов. Old3DS и stock firmware не поддерживаются. Профиль памяти178MiB; heap40MiB normal+132MiB linear, из linear128MiB занимает donor arena. Это не проверка фактического native peak.

## Историческая инструкция первого испытания — сейчас приостановлена после FAIL

1. Установить `native-game.cia` обычным локальным CIA installer на подготовленной New3DS. Убедиться в названии и Title ID выше; старые диагностические приложения не заменяются.
2. Открыть **DS Native Game 0.1.0**. На READY нажать **A один раз**: preflight → RX/cache →209 original constructors → JNI/lifecycle → original draws → GPU completion → frame capture.
3. Дождаться **FRAME SAVED** и исходного изображения на верхнем экране. Нажать **START один раз**. Loader ожидается до30s, остальные workers завершаются по stop events/flags с bounded joins. После успешной очистки приложение вернётся в HOME.
4. Не считать видимую картинку самостоятельным PASS. При STOPPED/FAIL не повторять запуск: сохранить результат и логи; активные ресурсы намеренно удерживаются, успешный выход не имитируется.

START до A просто выходит без запуска donor и не считается аппаратным испытанием кадра. Звук, управление и непрерывная сцена этим приложением не проверяются.

## Извлечение и критерии логов

Каждый запуск создаёт новую свободную папку **`SD:/3ds/ds-native-game-v0.1.0/run-NNNN/`**. Она не совпадает с прежними `ds-native-frame`/`ds34-*` hardware logs и не перезаписывает существующий run. Скопировать **всю новую run-папку**, включая:

- `native-game.log`, `result.json`, `exit.txt`, `ready.txt`;
- `frame.raw` (288000 bytes; приватное изображение игры);
- `threads-*.json`, `destructors.json` — приватная диагностика объектов/стеков.

Прислать архив этой run-папки и сообщить, вернул ли START консоль в HOME. Сырые дампы/изображения остаются локальной private evidence, не публикуются.

Ожидаемые признаки: `environment=native`, RX pages1062/ranges2 и успешные RX queries,209 constructors, `frame_saved=true`, GL_error0, failed_submits0, P3D/PPF completion, kernel joins0 для loader/jobs/audio/periodic, `SHUTDOWN live workers=0`, IO open/close balance, `safe_exit=true` и `exit.txt`. Номер callback/число submits могут отличаться из-за реального времени загрузки.

При ошибке cache/RX, allocation, unsupported import/JNI/GLES, timeout или cleanup программа сохраняет FAIL и не освобождает память, ещё доступную потокам/GPU. Отдельные fail-stop paths могут оставлять приложение остановленным; HOME-return при таком FAIL не обещается.

## Что ещё предстоит доказать на настоящей приставке

1062 RX pages, native instruction/data cache coherence, реальные GPU адреса/команды исходного кадра, запас linear memory, скорость SD и30s loader budget, а также точное совпадение CRC с аппаратной PICA. Подтверждённый ранее shader/route не является аппаратным PASS всего игрового bootstrap. Минимальные fixtures native RX уже проходили на New3DS; выполнение большого donor image в сообщённом чёрном экране пока не подтверждено.

Подробности подготовки: `porting/analysis/native-game-cia-v0.1.0/report.ru.md`, `preflight.json`, `CIA-install.json`, результаты `azahar-native-game-v0.1.0-h2-{cxi,cia,cia-installed}`. Последующий аппаратный FAIL пользователя записан отдельно в начале этой инструкции. Новых сборок/повторных запусков после FAIL, push, FPS/audio/control work или полного ARM-набора не выполнялось.
