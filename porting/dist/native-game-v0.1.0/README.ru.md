# DS Native Game 0.1.0 — один оригинальный кадр, эксперимент для New 3DS

**Это кандидат на первое аппаратное испытание, не готовый игровой порт. Аппаратный запуск ещё не согласован и не выполнялся.** CIA исполняет оригинальный ARM-код и его draw callbacks; изображение из файла/видеозаписи в приложение не загружается. Checkpoint — исходный экран с Айзеком и рекомендацией использовать наушники, ещё не управляемая 3D-сцена.

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

## Один запуск — только после отдельного согласования

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

1062 RX pages, native instruction/data cache coherence, реальные GPU адреса/команды исходного кадра, запас linear memory, скорость SD и30s loader budget, а также точное совпадение CRC с аппаратной PICA. Подтверждённый ранее shader/route не является аппаратным PASS всего игрового bootstrap. Минимальные fixtures native RX уже проходили на New3DS, но этот большой donor image на железе ещё не запускался.

Подробности: `porting/analysis/native-game-cia-v0.1.0/report.ru.md`, `preflight.json`, `CIA-install.json`, результаты `azahar-native-game-v0.1.0-h2-{cxi,cia,cia-installed}`. Аппаратных запусков, push, FPS/audio/control work или полного ARM-набора здесь не было.
