# Изолированный Legacy startup — 31.10.2026

Ветка `diag/native-startup-legacy`. Пользователь поручил подготовить отдельный startup-test с изменением **только New3DS memory mode**. Старый178MiB startup аппаратно FAIL с чёрными экранами/без папки; малые кучи не устранили симптом. Гипотеза172MiB отложена. Никакого нового аппаратного запуска или push агент не выполнял.

## Артефакт и неизменность кода

`3ds/build-native-startup-v0.1.0-legacy/startup-legacy.cia`, **146880bytes**, SHA256 **`0bc9e96b059c0a0c4d4125afb5525ff7f0726eb9a96a03799c4b74786b1d9fe9`**. Не пересобирался код: скопирован сохранённый ELF SHA256 `29fd6587561fdc13f2a68e5528366eacfea21ed181efc66afe23150f99f9e839`, прежние SMDH и banner. В командах только makerom/ctrtool; компилятор и линкер не запускались.

TitleID **000400000FDE7200**, productCTR-H-DSST, HOME DS Startup Test0.1.0, версия1 оставлены прежними, чтобы exheader не имел дополнительных изменений идентификаторов. Это отдельный CIA-файл, но не отдельный установленный title: при согласованной установке он заменит старый startup, не игру. Прежние файлы CIA/ZIP на компьютере сохранены.

RSF отличается ровно одной строкой: `SystemModeExt: 178MB` → `SystemModeExt: Legacy`. [RSF diff](memory-mode-only.rsf.diff).

## Сравнение готовых exheader из реальных CIA

Из обоих CIA извлечён реальный NCCH и его полный2048-byte exheader. Никакие поля не сравнивались только по предполагаемому RSF.

| Offset от начала exheader | Смысл | Было | Стало |
|---|---|---|---|
| 0x20d | New3DS memory mode в actual ACI | 02 | 00 |
| 0x60d | То же поле в AccessDescriptor ACI copy | 02 | 00 |
| 0x400..0x4ff | Производная RSA-подпись изменённого AccessDescriptor | прежняя | пересчитана |

За пределами256-byte подписи отличаются **ровно два байта** — два представления одного memory mode. В подписи изменились255bytes. Итого1791 из2048bytes совпали. RSA public key0x500..0x5ff побайтно тот же. Нельзя утверждать «всего два байта отличаются во всём exheader», скрывая подпись; **настройка изменилась только одна**. NCCH/TMD hashes/signatures также закономерно пересчитываются вне exheader.

Kernel2.44, SVC permissions (включая0x54/0x70/0x7d), heap-related static code/data, main stack, priority/affinity, службы/зависимости и все идентификаторы **не менялись**. Весь ExeFS, включая executable/icon/banner, совпал побайтно. Сохранены2+2MiB heaps и SDK allocator wrapper. [Машинный diff](exheader-comparison.json), [ctrtool](CIA-container-audit.txt), [build manifest](../../3ds/build-native-startup-v0.1.0-legacy/build-manifest.json).

ctrtool подтвердил New3DS64MB и kernel2.44; content/exheader/section hashes GOOD. Ожидаемые ошибки test/homebrew signatures Ticket/TMD/AccessDescriptor остались теми же тремя категориями, новых ошибок контейнера не появилось. Они не считаются аппаратным proof.

## Azahar

Протестирован payload, извлечённый **из готовой Legacy CIA**; он побайтно совпал с отдельно собранным CXI. Три последовательных цикла с одной SD и одним core:

- main/READY и валидный pre-main probe;
- START с реальным завершением guest до host unload;
- GSP ReleaseRight и освобождение normal/linear heap;
- нет новых unmapped/exception/assertion сообщений, game/DS34/PICA calls0.

Каждый цикл: limit **67108864=64MiB**, current до heap **409600**, current после heap **4603904**, delta **4194304=4MiB**, APP region67108864, raw layout ID**6**. Нижний экран READY визуально проверен по сохранённому PNG. [Финальные три цикла](../azahar-native-startup-legacy-v0.1.0-r2/result.json).

Надпись и JSON `declared_New3DS_mode_MiB=178` намеренно остались от прежнего ELF; это статическая метка, не измерение. В инструкции явно отделены метка и фактический64MiB counter. Код ради надписи не менялся.

Первый host adapter ошибочно ожидал raw layout0 (Old3DS), хотя New3DS Legacy дал6; при этом все три guest READY/START проверки уже прошли. Его общий результат помечен `passed=false, adapter_validation_failed=true`, исходная диагностика сохранена в `azahar-native-startup-legacy-v0.1.0`. Исправлена только внешняя проверка ожидаемого ID6, затем выполнены новые три цикла в отдельном `-r2`. ELF/CIA между ними не менялись. Ошибочная host-проверка не выдаётся за сбой или исправление guest.

Новый runner — небольшой adapter сохранённого startup smoke test с проверкой его SHA и заменой двух host-путей/имени CIA. Прежние harness/runner не переписаны. Установка и HOME Menu на реальной консоли не тестировались. Программный PASS не является аппаратным PASS.

## Один аппаратный эксперимент для согласования

Проверить идентичность установленного **Legacy CIA** по указанному SHA, один раз открыть прежнюю иконку startup, зафиксировать READY/limit/current, нажать START, подтвердить HOME, сохранить новый run при его наличии. Аппаратное разрешение **пока не получено**. [Подробная инструкция](../../3ds/README-native-startup-legacy.ru.md).

Если READY+HOME появятся, смена memory mode устранит симптом этого startup при неизменных kernel/SVC/code. После этого потребуется исследовать совместимость расширенного профиля для игры: Legacy64 не вмещает нынешние172MiB и не является окончательным решением.

Если Legacy тоже FAIL, следующим отдельным кандидатом будет kernel2.44→2.33 на том же ELF и Legacy profile, с прежними SVC. Лишь после анализа результата — отдельная проверка конкретных SVC permissions, по одному изменению, опираясь на аппаратно успешный DS34. Несколько полей одновременно не менять; автоматических повторов/следующих аппаратных тестов нет. Эти следующие варианты сейчас не создавались.

## Сохранность

SHA-проверка192 защищённых файлов включает GPU/shader/runtime, s16 safe_exit, h2, старый ZIP, прежний startup build и его Azahar evidence. Изменений нет. Исходные APK/.so/игровые ресурсы в CIA не входят. Полный ARM suite не запускался. [Готовность и сверка](release-gate.json).
