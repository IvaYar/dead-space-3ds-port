# После меню: туман и смешивание текстур

**Новейшее продолжение:** [LIGHTING.ru.md](LIGHTING.ru.md), [DEFAULT-SURFACE.ru.md](DEFAULT-SURFACE.ru.md),551 тест. Старый glLightModelfv пройден; native2605 завершён с GL0. В промежуточном кадре виден коридор, итоговый кадр остаётся чёрным. Следующий шаг — последующие проходы и развитие сцены. Далее описана предыдущая точка DS30/31.

Цель — запуск следующей сцены оригинального английского донора1.1.33. На нижний экран интерфейс пока не переносится, стерео не добавляется. Пользователь заинтересован в этих функциях позже, после работающего порта.

## DS30: настоящий туман

Опция `--fog`, четыре GLES API: `glFogf`, `glFogx`, `glFogfv`, `glFogxv`. Поддержаны LINEAR/EXP/EXP2, density/start/end/color, typed queries, fixed16.16 и необработанный enum в `glFogx(FOG_MODE,...)`. Недопустимые параметры не меняют прежнее состояние.

Для расстояния используется разрешённое ES1.1 приближение `abs(eye.z)`. Фактор вычисляется в вершине, переносится через clipping и интерполируется с учётом clip W; затем смешиваются RGB после текстурирования, до blending. Alpha остаётся исходной. Режим flat color не превращает fog в константу. 21 ARM-тест проверяет реальные пиксели, перспективу, clipping, modelview/projection, texture replace, alpha test и blending.

Подтверждённый native run `engine-fog-first-scene`: принят выбор Easy и галочка, кадры1–2603 вернулись, на2604 прошёл прежний `glFogx` и началась отрисовка дальше. Новая остановка — `texture environment mode unsupported`, enum`0x8570` (`GL_COMBINE`). GL error500 относится к этой честной остановке на следующем режиме, а не к успешному завершению графической проверки. Логи, result и отдельный `fog-build-manifest.json` сохраняют hashes именно той промежуточной сборки.

## DS31: texture combiners

Опция `--combine` включает состояния двух units через существующие `glTexEnv*`/`glGetTexEnv*`. Legacy GL99 сохраняется. Раздельные RGB/alpha functions, источники TEXTURE/CONSTANT/PRIMARY_COLOR/PREVIOUS, operands, масштабы1/2/4 и DOT3_RGB/RGBA действительно вычисляют выходные пиксели. Данные первой texture unit поступают в PREVIOUS второй; PRIMARY_COLOR сохраняет входной цвет фрагмента. Отключённая unit пропускает вход без изменений.

Обычные mode/enums в fixed-вызовах не масштабируются; numeric RGB/alpha scale трактуется как16.16. Реальные floating, fixed, integer и vector entrypoints покрыты21 ARM-тестом. Проверены FBO RGBA, функции/источники/операнды, отдельные units, alpha textures, DOT3, ошибочные параметры, выход в legacy mode и туман после combiner. Texture crossbar не заявлен и отвергается.

Подтверждённый запуск с обоими адаптерами:71 texture names,52 776 980 логических байт,5 144 580 резидентных; 263 выгрузки/199 загрузок, failures0. Donor arena:84 774 912 байт, refusals0. Кадры Normal2160/Easy2400 совпадают с прежними PNG побайтово, так что новые функции не изменили меню. `analysis/menu-frame` содержит текущие run/result/build-manifest и снимки; `check_menu_frame.py` проверяет их вместе с21+21 тестами и новым guard на lighting.

Команда текущего профиля:

```powershell
python porting/tests/smoke_engine_azahar.py --case graphics --explore --capture-frame 2800 --timeout-seconds 600 --resume-focus --touch --private-files --apk-assets --shared-arena --framebuffers --font-subset --allocator-compat --fog --combine --memory-mib 178 --cpu-percent 400 --tap-events 2300:160:134,2600:284:225
```

Источник математического контракта — [OpenGL ES1.1.12, разделы3.7.12 и3.8](https://registry.khronos.org/OpenGL/specs/es/1.1/es_full_spec_1.1.pdf). Поддержка lighting, mipmap sampling и другие неподдержанные операции по-прежнему останавливаются явно.

## Экраны и будущие функции

Сейчас изображение движка выводится на верхний экран400×240, нижний320×240 используется как источник касаний с масштабированием координат. Основной геймплей планируется сверху. Собственные кнопки/панели снизу возможны; перенос именно игровых элементов потребует разделить HUD и сцену либо изменить UI донора. Это отдельная работа после базовой совместимости.

Стерео требует двух согласованных видов сцены и управления глубиной, а также достаточной производительности. Есть [официальный пример devkitPro](https://github.com/devkitPro/3ds-examples/blob/master/graphics/gpu/stereoscopic_2d/source/main.cpp). Он показывает возможность платформы, а не готовую поддержку в этом порте. [Nintendo подтверждает](https://en-americas-support.nintendo.com/app/answers/detail/a_id/363/p/172/c/898), что нижний экран только2D, а New2DSXL вообще не отображает стерео3D.

До играбельного порта остаются 3D renderer, производительность, звук, управление и реальные аппаратные проверки. Проверяемое меню на CPU400/178MiB — контрольная точка, а не доказательство скорости на консоли. Новая CIA не выпускалась; последний аппаратный этап8 сохраняется. Подготовка первой аппаратной диагностики требует отдельно проверить соответствующий native runtime и память; дата пока не определена.
