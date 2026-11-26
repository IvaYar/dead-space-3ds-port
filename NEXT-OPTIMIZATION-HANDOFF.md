# Следующий этап: v0.2.0-performance-preview

Я сохранил этот milestone после теста на своей New Nintendo 3DS LL. HQ, Circle Pad,
камера C-Stick и нижний Render FPS HUD работают. Я наблюдал около6–10 Render FPS,
местами почти20. Это не контролируемый benchmark и не стабильные15 FPS.
В этом milestone-saving PR новых оптимизаций нет.

## Checkpoint и восстановление

Тег v0.2.0-performance-preview указывает на опубликованные исходники. Точные140
SHA256 и identity локальной CIA — docs/performance-preview/milestone.json.
Lab source:14c2d63efa18e10248b6d3c922f4e7c8cb135816;
verification:70f3b4e2cd4a89071bb0c5618fe942e4955c73b4.
Сборка: playable/BUILD.md и playable_build.py, pinned playable/dependencies.json.
Original donor/assets/font/HQ cache и packaging inputs нужны отдельно, здесь их нет.
Phase9 и предыдущие экспериментальные CIA сохранены. Не переписывать историю,
не трогать их evidence и не расширять memory budgets ради прохождения проверок.

## Архитектура

Актуальный build tree — playable/src; porting содержит исторические эксперименты.
Original ARM32 engine исполняется нативно через Bionic/JNI/IO/thread compatibility.
Circle Pad доставляет original JNI pointer events в исходный joystick/controller;
C-Stick использует original Xperia module1100/pointer2. Physics/time не патчились.
GLES1.x переводится в Citro3D/PICA200; CPU transform, prevalidation, clipping и
emission сохранены вместе с CPU/FBO fallback. Stream48B уже был достигнут ранее;
повторного64→48 выигрыша в этой фазе нет. HQ ETC1/ETC1A4, Morton/LZ4 backing и
GPU drain-before-free сохранены. CPU/L2 requested через SDK/ptm:sysm, readback неизвестен.
Runtime /3ds/ds-8fps27/, donor /3ds/deadspace/, HQ /3ds/ds-hq-prepared/etcq/.

HUD считает TOP generations после успешных FRAME_END/frame_sync/restart, а не
callbacks/VBlank/pixel changes.128 timestamps, sliding около2s с показом реальной
длины окна, максимум2Hz на main boundary. Нет heap, CRC/readback или SD IO в HUD.
fps-off.txt проверяется при запуске; view-trace.txt включает дополнительные QA traces.

## Профили и память

Числа и scope: docs/performance-preview/RESULTS.md. После устранения matrix IO
в эмуляторе draw около90% callback, preparation43%, emission42%, CPU gpu_end4%.
Nested scopes не складывать, gpu_end не является GPU execution timestamp.
Главный чистый аппаратный bottleneck после исправления logging ещё не установлен.
Прежние hardware2.431/s включали SD logging и иной CRC observer. Не переводить
их в новые физические FPS через emulator speedup. HUD6–10 не является средним FPS.
Linear margin345KiB, commit margin~1.82MiB в выбранной эмуляторной сцене.
Budgets124/20/100/85.5MiB не менялись; full-campaign peaks пока неизвестны.

## Успешные и неудачные изменения

Приняты bounded optional matrix sample и flush вне callback, подавление camera
trace без QA marker, guard бесполезного color-material tracking, per-draw matrix
views и однократный transform disabled texcoord default. CPU micro-paths дали
1.19/0.89/1.27% меньший ARM instruction count на целевом workload; не складывать
их и не называть физическим ускорением. После intro600 normal не делает повторные
stream FNV audits/GX shadow capture; developer path и GPU fences сохранены.
INTEGER SHORT/FIXED/UBYTE specialization прошла correctness, но не ускорила свой
benchmark и ухудшила float workload: DS_P8_INTEGER=0. Float snprintf в HUD заменён
integer formatting после выявления потенциальных newlib dtoa allocations.
Checker со старым stride64 исправлен для reference48; сравниваются consumed bytes.
Сравнение actual CIA в Azahar дало median callback на5.92–5.93% меньше, host scenario
на1.17–1.85% короче. Кеш ОС и async HID не контролировались; это не hardware speedup.

## PICA200 vertex shaders

Отдельный modelview PoC расширен scale/translation/shear0.125. Actual CPU
reference и GPU interpreter дали одинаковое изображение fixture. Это не
production fast path. У76 sampled world matrices actual SDK f32tof24 дал неточные
coefficients: exact-coefficient gate пропустил0/76. Decimal trace не raw replay,
а консервативный gate не доказывает невозможность полезного f24 renderer.
Production native transform остаётся OFF. Нужны exact raw matrix/vertex/index/state
replay, perspective/clipping/depth/lighting/interpolation/FBO/order coverage и
измеримый end-to-end выигрыш. Простой перенос arbitrary CPU matrices не доказан.

## Известные проблемы и следующие направления

Historical FRAME CRC ea733050 FAIL не исправлен. Legacy debug digest ожидает
vertex64 при stream48 и не является full fidelity oracle; reference не менять.
Два strict emulator runs запоздали с neutral на step53, на54 восстановились;
повторные ON/OFF прошли. Причина не установлена; async HID timing — гипотеза.
Нельзя объявлять regression исключённой или ослаблять исходный oracle.

1. Получить чистый аппаратный профиль без routine hot traces: отдельно CPU
transform/validation/clipping/emission, submission/waits и observer cost.
2. Снять bounded exact draw replay полезного opaque/unlit subset, проверить
precision/clipping до попытки production native path.
3. Исследовать reuse внутри draw, validation duplication, clipping. Не кешировать
client pointers между draws без lifetime proof и не расширять GPU buffers.
4. Проверить stick release на железе и источник intermittent neutral FAIL.
5. Разобрать historical CRC mismatch отдельно от speed work; позднее NDSP audio.

Каждая гипотеза: profile→targeted differential→benchmark→keep/reject→checkpoint.
Native fast path включать лишь после correctness coverage и end-to-end выигрыша.
