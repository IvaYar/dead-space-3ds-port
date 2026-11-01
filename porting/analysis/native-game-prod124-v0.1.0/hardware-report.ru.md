# Prod124 game: остановка preflight из-за отсутствующих SD-файлов

31.10.2026 пользователь сообщил: приложение открылось, после A перестало реагировать, выключено Power. Передана папка `porting/ds-native-game-prod124-v0.1.0/run-0001/`. Затем на вопрос о `SD:/3ds/deadspace/` подтвердил: **«Нет, я удалил её ещё очень давно, а она нужна?»**

**Причина этой preflight-остановки установлена:** обязательная папка оригинального кода/ресурсов удалена. Сразу после успешной проверки environment код вызывает `receipt("sdmc:/3ds/deadspace/assets-verified.txt",...)`; при отсутствии папки fopen возвращает ошибку и initialize возвращает−1. Журнал заканчивается именно на этом участке до любых REGIONJSON/Memory image/graphics setup. Приложение вызывает штатный `fatal`, который показывает STOPPED, пишет blocked result и входит в бесконечный SleepThread без обработки кнопок. Это объясняет наблюдаемое отсутствие реакции; новой неисправности GX/PICA этим результатом не доказано.

## Подтверждённые аппаратные данные

- READY и main достигнуты; A обработана.
- `Environment=native`, `appbytes=130023424=124MiB`, Luma raw `0d030300`.
- `RESLIMIT_COMMIT limit=130023424`, current **126611456=120,746MiB** — normal20+linear100 SDK heaps действительно зарезервированы на устройстве.
- `FAIL phase=preflight frame=0: initialization/frame blocked`.
- `game_called=false`, `frame_saved=false`, draws/submits/active_threads/RXpages=**0**, `safe_exit=false`.
- Donor arena92MiB, RX/cache, constructors, игровые потоки и DS34 ещё не достигнуты. Подтверждён общий linear heap100MiB, а не успешная передача арены движку.

Исходные ready.txt/result.json/native-game.log сохранены без изменений. [Архив](../hardware/native-game-prod124-v0.1.0-user-run-0001/), [машинная запись и SHA](../hardware/native-game-prod124-v0.1.0-user-result.json). Expected CIA SHA `9fea6c2923d555511dd19a5d0177041592979dbd22fe8f07a4228a509082e815`; идентичность установленного файла отдельно не измерялась. Power hold duration отдельно не уточнялась. Frames/exit markers отсутствуют.

## Что восстановить

Startup2+2MiB тесты не исполняли donor и не требовали игровых файлов. Эта CIA содержит port loader/адаптеры/GPU, но читает оригинальную библиотеку, coreassets/APK assets и font с SD. Они не включаются в CIA или публичный Git.

На компьютере готова **`porting/private/native-game-v0.1.0-sd/3ds/`**. Каталог `3ds` нужно скопировать целиком в корень SD, получив **`SD:/3ds/deadspace/`** с `.so`, двумя receipts, `assets/`, `apk-assets/` и `test-output/font-subset/Ascender_Uni.ttf`.

Проверено наличие1752files/583364704bytes, CRC donor9fd95635, font71dcae12 и точные обе строки receipts. Приватная копия сохранена, заново извлекать APK не требуется. Для устранения отсутствующих файлов **новая CIA не нужна**; это не обещание, что последующие аппаратные стадии автоматически пройдут. Дальнейший hardware original-frame/exit test требует отдельного согласования после восстановления SD.

Обнаружено также ограничение интерфейса ошибок текущего baseline: generic preflight error не называет конкретный отсутствующий файл, а fatal не даёт START даже до появления donor-пользователей. Это поведение не выдаётся за safe_exit PASS. В этом обновлении код не менялся и новая CIA не создавалась.

Сохранены software6-cycle PASS и все прежние baseline.261защищённый файл совпал по SHA. Агент не запускал Azahar/приставку, не менял backend/профиль/ресурсы и не делал push. Обновлены только hardware archive и документы.
