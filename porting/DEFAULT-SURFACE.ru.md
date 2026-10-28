# DS33: глубина и трафарет основного экрана

**Обновление:** ранний native2605 завершён и сверяется `check_lighting_progress.py`. GL0, failures0, промежуточный коридор виден, итоговый кадр чёрный. Ниже сохранены детали реализации и история первой попытки.

`--default-depth` подключает собственные depth16/stencil8 для default framebuffer, цвет которого заимствуется у LCD. Для400×240 это288000 байт; обычный профиль без флага сохраняет прежний surface без depth/stencil.

Используются существующие корректные GL clear/scissor/write masks и fragment tests DS26. Запросы DEPTH_BITS/STENCIL_BITS/STENCIL_REF соответствуют реальным буферам. Изменение заимствованного color pointer при swap не меняет owned depth/stencil; очисткой управляет игра. Промежуточные FBO имеют отдельные attachments и не затрагивают default storage.

Буферы инициализируются depth=1/stencil=0, освобождаются при закрытии контекста. Поддержаны конфигурации16/0,0/8,16/8; повторное подключение и неизвестные bit depths отвергаются без изменения состояния.

`tests/test_default_surface.py`:12 ARM-тестов, включая реальные пиксели/occlusion, depth compare/write mask, scissor depth clear, stencil masks/zfail, сохранение глубины при color swap, FBO isolation, bits queries и RGB565 CTR layout. Вместе с DS32 и прежней базой проходят551 тест.

Первый native lighting run без этих буферов прошёлglLightModelfv и завершил2630 callbacks, но target2800 не достигнут за600s, последний LCD чёрный. Повторный ранний capture2605 с default depth/stencil проверяется отдельно. До визуальной проверки результата не считать3D-сцену работающей; прохождение математических тестов и GL0 не доказывают наличие видимого окружения или игрового процесса.
