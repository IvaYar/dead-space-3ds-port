# Original Menu 0.1.5: полученный аппаратный run-0001

Оригинальный Select Difficulty достигнут на настоящей New Nintendo 3DS. Фото пользователя и независимо декодированный hardware raw `explore-4440.raw` показывают Normal/Easy с выделенным Normal. Пользователь ждал меню примерно 8 минут, нажал DOWN без видимой реакции, затем спустя ещё примерно 5–7 минут оказался в HOME. Это один уже выполненный запуск, новых аппаратных испытаний агент не запускал.

**Возврат в HOME штатный, причина — исчерпание лимита 12000 callbacks.** Нет зарегистрированных START/HOME/A-confirm или остановки из-за ошибки draw/present. `result.json` и `validation.json`: safe_exit=true, cleanup_complete=true, одна попытка shutdown. Пять оставшихся workers имеют done=1/kernel_wait=0, после join рабочих handles нет (main pseudo-record не worker). Loader к этому моменту уже отсутствует. IO174/174, stdio/appdata/IOactive/dirs0, GL_error0, failed_submits0. Есть exit.txt и PROCESS return. Независимого аппаратного замера освобождения SDK heaps или доказательства отсутствия любого use-after-free эти логи не дают. Исходный shutdown и порядок удержания code/arenas сохранены. HOME→X именно этой версии здесь не тестировался.

**Навигацию блокирует ошибка допуска ввода в pilot.** `native_menu_input.h` разрешает A/UP/DOWN только после одного из трёх наблюдавшихся в Azahar CRC меню: 7296717d/223b5e75/0ded835d. Физическое меню имеет CRC95b893de. Ни один записанный hardware FRAMECRC не попал в разрешённый набор; никакого CONTROL-события движку не отправлено. Исходный HID held-mask не логировался, поэтому сам захват физической кнопки этим запуском не доказан. Это не проблема действий пользователя и не подтверждённая ошибка оригинального игрового input pipeline. B не требуется для разблокировки A. Существовавший guard нужен из-за активации сцены при повторном касании уже выбранной строки, однако привязка допуска к полному emulator framebuffer непригодна для hardware.

Следующее исправление должно определять готовность/выделение оригинального меню независимо от совпадения полного изображения с Azahar и сохранять запрет опасного повторного касания. Простое снятие guard или добавление аппаратного CRC без проверки остальных состояний не доказывает корректность. Нужна software-проверка исходных fade/same-row/stale-observation случаев и минимальный журнал захвата/отклонения кнопки. Существующий frozen CRC oracle ea733050 и честный FRAME FAIL остаются без изменений.

## Реальные timings

По SDK ticks стабильные окна frame4560…12000 дают **24,02 FPS**, включая диагностические readback/CRC/raw/GX/JSON. Средние на callback: original callback16,10мс, present17,00мс, diagnostics8,29мс. Queue wait3,09мс и VBlank12,73мс уже входят в измеряемые участки; повторно складывать их нельзя. Последние Citro3D drawing samples2,847…3,272мс — выборка последнего draw, не полное суммарное GPU время окна.

Тяжёлое окно frame4321…4440: **473285,745мс = 7мин53с**, в том числе callback470513,476мс; present1833,871мс и diagnostics911,414мс. Текущая агрегация не позволяет приписать все470с одному конкретному вызову или отделить font rasterization от остальной работы callback. Другие большие окна: первый49,58с (callback46,35с) и frame961…108021,69с (callback18,75с). Это повод для адресных измерений font/atlas/loading, а не для переписывания GPU.

Сумма всех окон callback loop — **1036,760с (~17мин17с)**, до первого сохранённого menu capture —722,046с (~12мин02с). Они исключают preflight и shutdown; пользовательские 8мин и5–7мин приблизительны. Точное время первого видимого LCD меню по этим данным не восстановлено; наблюдения пользователя не заменяются расчётной суммой окон.

Prod124 соблюдён: commit126763008≤130023424bytes; normal peak footprint19746816bytes (~18,83МиБ). Linear peak104635264/104857600bytes оставляет лишь222336bytes (~217КиБ) временного запаса. Donor refusals0/runtime allocation failures0. Успешный статический экран не доказывает достаточную память для сцены. Управляемый Айзек и подтверждение сложности этим запуском не достигнуты.

## Сохранение и воспроизведение

Все **214файлов/29615916bytes** сохранены отдельной копией в private `analysis/hardware/native-game-menu-v0.1.5-user-run-0001/`, исходная `porting/ds-native-game-v0.1.5/run-0001/` не изменялась. Manifest содержит SHA256/размер каждого файла. Все100raw/readback pairs независимо проверены zlib и bytewise RGB565;100GX файлов имеют заявленные размеры, observer не заявил усечения. Это проверка целостности снимков, не равенство baseline и не полный анализ каждого PICA register.

Фото остаётся в сообщении пользователя; приватный PNG получен именно из оригинального hardware raw. Ни raw, PNG, dumps, игровые ресурсы, ни CIA в publication allowlist не добавлены. Прежний software release gate сохранён отдельно; текущий gate отмечает hardware_tested=true, menu=true, buttons=false, safe_exit=true, ready_for_one_separate_hardware_test=false. **Повтор той же CIA не нужен.**

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python porting/tools/analyze_native_game_menu_hardware.py
```

[Машинный результат](hardware-result.json), [manifest](archive-manifest.json), [наблюдения пользователя](user-observations.json). Новых CIA, сборок, emulator/hardware запусков, изменений baseline, staging/commit или push при разборе не было.
